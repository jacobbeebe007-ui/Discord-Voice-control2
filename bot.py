import discord
from discord.ext import commands
from discord import app_commands
from collections import OrderedDict
import json, os, random, io, datetime
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set in your environment or .env file.")

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

LOBBY_MAP_FILE    = "lobby_map.json"
MMR_FILE          = "mmr_data.json"
PRESETS_FILE      = "presets.json"
TEAM_HISTORY_FILE = "team_history.json"
PROVISIONAL_SESSIONS = 3

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

lobby_map:    dict = load_json(LOBBY_MAP_FILE)
mmr_data:     dict = load_json(MMR_FILE)
presets:      dict = load_json(PRESETS_FILE)
team_history: dict = load_json(TEAM_HISTORY_FILE)
team_storage: dict = {}

def get_guild_lobby_map(guild_id: int) -> dict:
    return lobby_map.get(str(guild_id), {})

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ─────────────────────────────────────────────
# HALO REACH RANK SYSTEM
# ─────────────────────────────────────────────

HALO_RANKS = [
    (95.5, "Inheritor",      "021_Inheritor"),
    (91.0, "Reclaimer",      "020_Reclaimer"),
    (86.5, "Forerunner",     "019_Forerunner"),
    (82.0, "Nova",           "018_Nova"),
    (77.5, "Eclipse",        "017_Eclipse"),
    (73.0, "Noble",          "016_Noble"),
    (68.5, "Mythic",         "015_Mythic"),
    (64.0, "Legend",         "014_Legend"),
    (59.5, "Hero",           "013_Hero"),
    (55.0, "Field_Marshall", "012_Field_Marshall"),
    (50.5, "General",        "011_General"),
    (46.0, "Brigadier",      "010_Brigadier"),
    (41.5, "Colonel",        "009_Colonel"),
    (37.0, "Commander",      "008_Commander"),
    (32.5, "Lt_Colonel",     "007_Lt_Colonel"),
    (28.0, "Major",          "006_Major"),
    (23.5, "Captain",        "005_Captain"),
    (19.0, "Warrant_Officer","004_Warrant_Officer"),
    (14.5, "Sergeant",       "003_Sergeant"),
    (10.0, "Corporal",       "002_Corporal"),
    (5.0,  "Private",        "001_Private"),
    (0.0,  "Recruit",        "000_Recruit"),
]

def get_emoji(guild: discord.Guild, name: str) -> str:
    if guild:
        e = discord.utils.get(guild.emojis, name=name)
        if e:
            return str(e)
    return f":{name}:"

def halo_rank(mmr: float) -> tuple:
    for threshold, name, ename in HALO_RANKS:
        if mmr >= threshold:
            return name, ename
    return "Recruit", "000_Recruit"

def rank_display(mmr: float, guild: discord.Guild, provisional: bool = False) -> str:
    rname, ename = halo_rank(mmr)
    remoji = get_emoji(guild, ename)
    prov   = " *" if provisional else ""
    return f"{remoji} {rname}{prov}"

def leaderboard_pos_emoji(rank: int) -> str:
    if rank == 1: return "🥇"
    if rank == 2: return "🥈"
    if rank == 3: return "🥉"
    return f"`#{rank}`"

def is_provisional(data: dict) -> bool:
    return data.get("sessions", 0) < PROVISIONAL_SESSIONS

# ─────────────────────────────────────────────
# MMR HELPERS
# ─────────────────────────────────────────────

WEIGHTS = {"kd": 0.30, "points": 0.25, "obj_time": 0.25, "assists": 0.15, "captures": 0.05}

def normalise(values: list) -> list:
    mn, mx = min(values), max(values)
    if mx == mn:
        return [50.0] * len(values)
    return [(v - mn) / (mx - mn) * 100 for v in values]

def calculate_mmr(players: list) -> list:
    keys = list(WEIGHTS.keys())
    normed = {k: normalise([p[k] for p in players]) for k in keys}
    for i, p in enumerate(players):
        p["mmr"] = round(sum(normed[k][i] * WEIGHTS[k] for k in keys), 1)
    return players

def canonical_name(raw: str) -> str:
    return raw.split("(")[0].strip()

def parse_session_sheet(ws) -> list:
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    players = []
    for row in rows[1:]:
        try:
            raw = str(row[0]).strip() if row[0] else None
            if not raw or raw.lower() in ("none", ""): continue
            kd = 0.0
            try: kd = float(row[4] or 0)
            except: pass
            players.append({
                "raw_name": raw, "name": canonical_name(raw),
                "kd":       kd,
                "kills":    float(row[1] or 0),
                "assists":  float(row[2] or 0),
                "deaths":   float(row[3] or 0),
                "captures": float(row[6] or 0),
                "obj_time": float(row[7] or 0),
                "points":   float(row[9] or 0),
            })
        except: continue
    return players

def parse_leaderboard_sheet(ws) -> list:
    rows = list(ws.iter_rows(values_only=True))
    if not rows: return []
    players = []
    for row in rows[1:]:
        try:
            name = str(row[1]).strip() if row[1] else None
            if not name or name.lower() == "none": continue
            players.append({
                "name":     name,
                "kills":    float(row[3] or 0),
                "assists":  float(row[4] or 0),
                "deaths":   float(row[5] or 0),
                "kd":       float(row[6] or 0),
                "obj_time": float(row[7] or 0),
                "captures": float(row[8] or 0),
                "points":   float(row[9] or 0),
                "sessions": int(row[10] or 1),
            })
        except: continue
    return players

def get_guild_mmr(guild_id: int) -> dict:
    return mmr_data.get(str(guild_id), {})

# ─────────────────────────────────────────────
# MESSAGING HELPERS
# ─────────────────────────────────────────────

class DismissView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)

    @discord.ui.button(label="✕", style=discord.ButtonStyle.secondary)
    async def dismiss(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

    async def on_timeout(self): pass

async def send_minimal(interaction: discord.Interaction, content: str, ephemeral: bool = True):
    await interaction.response.send_message(content, view=DismissView(), ephemeral=ephemeral)

async def followup_minimal(interaction: discord.Interaction, content: str, ephemeral: bool = False):
    await interaction.followup.send(content, view=DismissView(), ephemeral=ephemeral)

def chunk_lines(lines: list, header: str = "", limit: int = 1800) -> list:
    chunks, current = [], header
    for line in lines:
        if len(current) + len(line) + 1 > limit:
            chunks.append(current)
            current = line
        else:
            current = (current + "\n" + line).lstrip("\n")
    if current:
        chunks.append(current)
    return chunks

async def followup_chunked(interaction: discord.Interaction, lines: list, header: str = "", ephemeral: bool = False):
    for chunk in chunk_lines(lines, header):
        await interaction.followup.send(chunk, view=DismissView(), ephemeral=ephemeral)

async def send_single_or_chunked(interaction: discord.Interaction, lines: list, header: str = "", ephemeral: bool = False):
    """Try to send as one message; chunk if over 2000 chars."""
    message = (header + "\n" + "\n".join(lines)).strip()
    if len(message) <= 2000:
        await interaction.followup.send(message, view=DismissView(), ephemeral=ephemeral)
    else:
        await followup_chunked(interaction, lines, header=header, ephemeral=ephemeral)

# ─────────────────────────────────────────────
# GENERAL HELPERS
# ─────────────────────────────────────────────

def find_member_team(guild_id: int, member_id: int):
    for vc_id, members in team_storage.get(guild_id, {}).items():
        if member_id in members:
            return vc_id
    return None

def build_team_summary(guild: discord.Guild, guild_id: int) -> str:
    teams = team_storage.get(guild_id, {})
    if not teams:
        return "No teams assigned yet."
    gmmr = get_guild_mmr(guild_id)
    lines = []
    for vc_id, member_ids in teams.items():
        vc = guild.get_channel(int(vc_id))
        names, mmr_vals = [], []
        for mid in member_ids:
            m = guild.get_member(mid)
            dname = m.display_name if m else f"Unknown({mid})"
            cname = canonical_name(dname)
            pdata = gmmr.get(cname) or gmmr.get(dname)
            if pdata:
                rd = rank_display(pdata["mmr"], guild, is_provisional(pdata))
                names.append(f"{dname} {rd}({pdata['mmr']})")
                mmr_vals.append(pdata["mmr"])
            else:
                names.append(dname)
        avg = f" | avg MMR: {round(sum(mmr_vals)/len(mmr_vals), 1)}" if mmr_vals else ""
        lines.append(f"**{vc.name if vc else vc_id}** ({len(names)}){avg}\n> {', '.join(names)}")
    return "\n".join(lines)

def save_team_to_history(guild_id: int, guild: discord.Guild, label: str = None):
    gid = str(guild_id)
    if gid not in team_history: team_history[gid] = []
    teams = team_storage.get(guild_id, {})
    if not teams: return
    snapshot = {}
    for vc_id, member_ids in teams.items():
        vc = guild.get_channel(int(vc_id))
        vc_name = vc.name if vc else str(vc_id)
        names = [guild.get_member(mid).display_name if guild.get_member(mid) else str(mid) for mid in member_ids]
        snapshot[vc_name] = names
    entry = {"label": label or datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "teams": snapshot}
    team_history[gid].insert(0, entry)
    team_history[gid] = team_history[gid][:10]
    save_json(TEAM_HISTORY_FILE, team_history)

def format_player_stats(data: dict) -> str:
    return (
        f"Kills: {data.get('kills','?')} | Deaths: {data.get('deaths','?')} | "
        f"K/D: {data.get('kd','?')} | Assists: {data.get('assists','?')} | "
        f"Points: {data.get('points','?')} | Obj Time: {data.get('obj_time','?')}s | "
        f"Captures: {data.get('captures','?')}"
    )

# ─────────────────────────────────────────────
# LOBBY MAPPING VIEWS
# ─────────────────────────────────────────────

class LobbyMappingView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild
        vcs = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.source_select = SourceChannelSelect(vcs)
        self.dest_select   = LobbyDestSelect(vcs)
        self.add_item(self.source_select)
        self.add_item(self.dest_select)

    @discord.ui.button(label="💾 Save Mapping", style=discord.ButtonStyle.success, row=2)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        source_ids = self.source_select.selected_ids
        dest_id    = self.dest_select.selected_id
        if not source_ids:
            await send_minimal(interaction, "⚠️ Select at least one source channel.")
            return
        if not dest_id:
            await send_minimal(interaction, "⚠️ Select a lobby destination.")
            return
        gid = str(self.guild.id)
        if gid not in lobby_map: lobby_map[gid] = {}
        dest_ch = self.guild.get_channel(int(dest_id))
        saved = []
        for src_id in source_ids:
            lobby_map[gid][src_id] = int(dest_id)
            src_ch = self.guild.get_channel(int(src_id))
            saved.append(src_ch.name if src_ch else src_id)
        save_json(LOBBY_MAP_FILE, lobby_map)
        await send_minimal(interaction, f"✅ **{', '.join(saved)}** → **{dest_ch.name if dest_ch else dest_id}**")

class SourceChannelSelect(discord.ui.Select):
    def __init__(self, vcs):
        self.selected_ids: list = []
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in vcs[:25]]
        super().__init__(placeholder="1️⃣ Pick source channel(s) to recall FROM...", options=options,
                         min_values=1, max_values=min(len(vcs), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Source(s): **{', '.join(names)}**")

class LobbyDestSelect(discord.ui.Select):
    def __init__(self, vcs):
        self.selected_id = None
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in vcs[:25]]
        super().__init__(placeholder="2️⃣ Pick lobby destination (recall TO)...", options=options,
                         min_values=1, max_values=1, row=1)
    async def callback(self, interaction: discord.Interaction):
        self.selected_id = self.values[0]
        vc = interaction.guild.get_channel(int(self.selected_id))
        await send_minimal(interaction, f"✅ Destination: **{vc.name}**")

# ─────────────────────────────────────────────
# RANDOMISER VIEW
# ─────────────────────────────────────────────

class RandomiseView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        vcs = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.channel_select = RandomChannelSelect(vcs)
        self.add_item(self.channel_select)

    @discord.ui.button(label="🎲 Randomise!", style=discord.ButtonStyle.success, row=1)
    async def randomise(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_vc_ids = self.channel_select.selected_ids
        if len(selected_vc_ids) < 2:
            await send_minimal(interaction, "⚠️ Pick at least 2 voice channels.")
            return
        all_members = list({m.id: m for vc in self.guild.voice_channels for m in vc.members}.values())
        if not all_members:
            await send_minimal(interaction, "⚠️ No members in any voice channel.")
            return
        random.shuffle(all_members)
        buckets = {vc_id: [] for vc_id in selected_vc_ids}
        for i, m in enumerate(all_members):
            buckets[selected_vc_ids[i % len(selected_vc_ids)]].append(m)
        gid = self.guild.id
        team_storage[gid] = {}
        await interaction.response.defer()
        results = []
        for vc_id, members in buckets.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            team_storage[gid][vc_id] = []
            moved, skipped = [], []
            for m in members:
                team_storage[gid][vc_id].append(m.id)
                if m.voice: await m.move_to(vc); moved.append(m.display_name)
                else: skipped.append(m.display_name)
            line = f"**{vc.name}** ({len(moved)}): {', '.join(moved) if moved else 'nobody'}"
            if skipped: line += f" _(not in voice: {', '.join(skipped)})_"
            results.append(line)
        save_team_to_history(gid, self.guild, "🎲 Random")
        await followup_minimal(interaction, "🎲 **Teams randomised!**\n" + "\n".join(results), ephemeral=False)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class RandomChannelSelect(discord.ui.Select):
    def __init__(self, vcs):
        self.selected_ids: list = []
        options = [discord.SelectOption(label=c.name, description=f"{len(c.members)} connected", value=str(c.id)) for c in vcs[:25]]
        super().__init__(placeholder="Pick 2–25 voice channels to use as teams...", options=options,
                         min_values=2, max_values=min(len(vcs), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Teams: **{', '.join(names)}** — click 🎲 Randomise!")

# ─────────────────────────────────────────────
# BALANCED MATCHMAKING VIEW
# ─────────────────────────────────────────────

class MatchmakeView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        vcs = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.channel_select = MatchmakeChannelSelect(vcs)
        self.add_item(self.channel_select)

    @discord.ui.button(label="⚖️ Generate Balanced Teams", style=discord.ButtonStyle.success, row=1)
    async def matchmake(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_vc_ids = self.channel_select.selected_ids
        if len(selected_vc_ids) < 2:
            await send_minimal(interaction, "⚠️ Pick at least 2 voice channels.")
            return
        all_members = list({m.id: m for vc in self.guild.voice_channels for m in vc.members}.values())
        if not all_members:
            await send_minimal(interaction, "⚠️ No members in any voice channel.")
            return
        gmmr = get_guild_mmr(self.guild.id)
        num_teams = len(selected_vc_ids)
        rated, unrated = [], []
        for m in all_members:
            cname = canonical_name(m.display_name)
            pdata = gmmr.get(cname) or gmmr.get(m.display_name)
            if pdata: rated.append((m, pdata["mmr"], pdata))
            else: unrated.append(m)
        rated.sort(key=lambda x: x[1], reverse=True)
        buckets = {vc_id: [] for vc_id in selected_vc_ids}
        direction, idx = 1, 0
        for member, mmr, pdata in rated:
            buckets[selected_vc_ids[idx]].append((member, mmr, pdata))
            idx += direction
            if idx >= num_teams: idx = num_teams - 1; direction = -1
            elif idx < 0: idx = 0; direction = 1
        random.shuffle(unrated)
        for i, m in enumerate(unrated):
            buckets[selected_vc_ids[i % num_teams]].append((m, None, None))
        gid = self.guild.id
        team_storage[gid] = {}
        await interaction.response.defer()
        results = []
        for vc_id, members in buckets.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            team_storage[gid][vc_id] = []
            moved, skipped, mmr_vals = [], [], []
            for m, mmr, pdata in members:
                team_storage[gid][vc_id].append(m.id)
                if mmr is not None:
                    rd = rank_display(mmr, self.guild, is_provisional(pdata))
                    label = f"{m.display_name} {rd}"
                    mmr_vals.append(mmr)
                else:
                    label = f"{m.display_name} ❔"
                if m.voice: await m.move_to(vc); moved.append(label)
                else: skipped.append(label)
            avg = f" | avg MMR: {round(sum(mmr_vals)/len(mmr_vals),1)}" if mmr_vals else ""
            line = f"**{vc.name}**{avg}: {', '.join(moved) if moved else 'nobody'}"
            if skipped: line += f" _(not in voice: {', '.join(skipped)})_"
            results.append(line)
        save_team_to_history(gid, self.guild, "⚖️ Balanced")
        await followup_minimal(interaction, "⚖️ **Balanced teams generated!**\n" + "\n".join(results), ephemeral=False)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class MatchmakeChannelSelect(discord.ui.Select):
    def __init__(self, vcs):
        self.selected_ids: list = []
        options = [discord.SelectOption(label=c.name, description=f"{len(c.members)} connected", value=str(c.id)) for c in vcs[:25]]
        super().__init__(placeholder="Pick 2–25 voice channels to use as teams...", options=options,
                         min_values=2, max_values=min(len(vcs), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Channels: **{', '.join(names)}** — click ⚖️ to generate!")

# ─────────────────────────────────────────────
# PRESET VIEWS
# ─────────────────────────────────────────────

class SavePresetModal(discord.ui.Modal, title="Save Team Preset"):
    preset_name = discord.ui.TextInput(label="Preset Name", placeholder="e.g. Monday Night 6v6", max_length=50)
    preset_note = discord.ui.TextInput(label="Notes (optional)", placeholder="e.g. Competitive lineup, no subs",
                                       required=False, max_length=150, style=discord.TextStyle.paragraph)
    def __init__(self, guild): super().__init__(); self.guild = guild
    async def on_submit(self, interaction: discord.Interaction):
        gid = str(self.guild.id)
        teams = team_storage.get(self.guild.id, {})
        if not teams:
            await send_minimal(interaction, "⚠️ No active teams to save.")
            return
        if gid not in presets: presets[gid] = {}
        snapshot = {}
        for vc_id, member_ids in teams.items():
            vc = self.guild.get_channel(int(vc_id))
            vc_name = vc.name if vc else str(vc_id)
            names = [self.guild.get_member(mid).display_name if self.guild.get_member(mid) else str(mid) for mid in member_ids]
            snapshot[vc_name] = names
        name = str(self.preset_name)
        presets[gid][name] = {"note": str(self.preset_note) if self.preset_note.value else "", "teams": snapshot}
        save_json(PRESETS_FILE, presets)
        await send_minimal(interaction, f"✅ Preset **{name}** saved!")

class LoadPresetView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild
        gp = presets.get(str(guild.id), {})
        if gp: self.add_item(PresetSelect(gp))

class PresetSelect(discord.ui.Select):
    def __init__(self, gp):
        options = [discord.SelectOption(label=n, description=d.get("note","")[:50] or "No notes", value=n) for n,d in list(gp.items())[:25]]
        super().__init__(placeholder="Choose a preset to view...", options=options, row=0)
    async def callback(self, interaction: discord.Interaction):
        preset = presets.get(str(interaction.guild_id), {}).get(self.values[0])
        if not preset:
            await send_minimal(interaction, "⚠️ Preset not found.")
            return
        lines = [f"📋 **{self.values[0]}**"]
        if preset.get("note"): lines.append(f"_{preset['note']}_")
        for vc_name, members in preset["teams"].items():
            lines.append(f"**{vc_name}**: {', '.join(members)}")
        await send_minimal(interaction, "\n".join(lines))

class TeamPresetsView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        self.guild = guild
        gp = presets.get(str(guild.id), {})
        if gp:
            self.preset_select = TeamPresetSelect(gp)
            self.add_item(self.preset_select)

    @discord.ui.button(label="📂 Load Preset", style=discord.ButtonStyle.success, row=1)
    async def load_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        preset_name = self.preset_select.selected_name
        if not preset_name:
            await send_minimal(interaction, "⚠️ Select a preset first.")
            return
        preset = presets.get(str(self.guild.id), {}).get(preset_name)
        if not preset:
            await send_minimal(interaction, f"⚠️ Preset **{preset_name}** not found.")
            return
        vcs_by_name     = {vc.name: vc for vc in self.guild.voice_channels}
        members_by_name = {m.display_name: m for m in self.guild.members}
        gid = self.guild.id
        team_storage[gid] = {}
        loaded, missing_ch, missing_m = [], [], []
        for vc_name, member_names in preset["teams"].items():
            vc = vcs_by_name.get(vc_name)
            if not vc: missing_ch.append(vc_name); continue
            team_storage[gid][str(vc.id)] = []
            found = []
            for mname in member_names:
                m = members_by_name.get(mname)
                if m: team_storage[gid][str(vc.id)].append(m.id); found.append(mname)
                else: missing_m.append(mname)
            loaded.append(f"**{vc_name}**: {', '.join(found) if found else 'nobody'}")
        msg = f"📂 **{preset_name}** loaded!\n" + "\n".join(loaded)
        if missing_ch: msg += f"\n⚠️ Channels not found: {', '.join(missing_ch)}"
        if missing_m:  msg += f"\n⚠️ Members not found: {', '.join(missing_m)}"
        msg += "\n\nUse 🚀 Send Teams to move everyone."
        await send_minimal(interaction, msg)

class TeamPresetSelect(discord.ui.Select):
    def __init__(self, gp):
        self.selected_name = None
        options = [discord.SelectOption(label=n, description=d.get("note","")[:50] or "No notes", value=n) for n,d in list(gp.items())[:25]]
        super().__init__(placeholder="Choose a preset to load...", options=options, row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_name = self.values[0]
        preset = presets.get(str(interaction.guild_id), {}).get(self.selected_name, {})
        lines = [f"📋 **{self.selected_name}**"]
        if preset.get("note"): lines.append(f"_{preset['note']}_")
        for vc_name, members in preset.get("teams", {}).items():
            lines.append(f"**{vc_name}**: {', '.join(members)}")
        lines.append("\nClick 📂 Load Preset to activate.")
        await send_minimal(interaction, "\n".join(lines))

# ─────────────────────────────────────────────
# TEAM HISTORY VIEW
# ─────────────────────────────────────────────

class TeamHistoryView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=60)
        history = team_history.get(str(guild.id), [])
        if history: self.add_item(TeamHistorySelect(history))

class TeamHistorySelect(discord.ui.Select):
    def __init__(self, history):
        options = [discord.SelectOption(label=e["label"][:50], value=str(i)) for i, e in enumerate(history[:25])]
        super().__init__(placeholder="Choose a past team configuration...", options=options, row=0)
    async def callback(self, interaction: discord.Interaction):
        history = team_history.get(str(interaction.guild_id), [])
        idx = int(self.values[0])
        if idx >= len(history):
            await send_minimal(interaction, "⚠️ Entry not found.")
            return
        entry = history[idx]
        lines = [f"📜 **{entry['label']}**\n"]
        for vc_name, members in entry["teams"].items():
            lines.append(f"**{vc_name}** ({len(members)}): {', '.join(members)}")
        await send_minimal(interaction, "\n".join(lines))

# ─────────────────────────────────────────────
# TEAM BUILDER
# ─────────────────────────────────────────────

class TeamBuilderView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=600)
        self.guild = guild
        all_members = list({m.id: m for vc in guild.voice_channels for m in vc.members}.values())
        vcs = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.member_select  = TeamMemberSelect(all_members)
        self.channel_select = TeamChannelSelect(vcs)
        self.add_item(self.member_select)
        self.add_item(self.channel_select)

    @discord.ui.button(label="➕ Assign to Team", style=discord.ButtonStyle.primary, row=2)
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild.id
        chosen = self.member_select.selected_members
        vc_id  = self.channel_select.selected_vc_id
        if not chosen: await send_minimal(interaction, "⚠️ Select members first."); return
        if not vc_id:  await send_minimal(interaction, "⚠️ Select a channel first."); return
        if gid not in team_storage: team_storage[gid] = {}
        if vc_id not in team_storage[gid]: team_storage[gid][vc_id] = []
        added, moved_from = [], []
        for m in chosen:
            if not m: continue
            prev = find_member_team(gid, m.id)
            if prev and prev != vc_id:
                team_storage[gid][prev].remove(m.id)
                prev_vc = self.guild.get_channel(int(prev))
                moved_from.append(f"{m.display_name} (was in {prev_vc.name if prev_vc else prev})")
            if m.id not in team_storage[gid][vc_id]:
                team_storage[gid][vc_id].append(m.id)
                added.append(m.display_name)
        vc  = self.guild.get_channel(int(vc_id))
        msg = f"✅ **{vc.name if vc else vc_id}**: {', '.join(added)}"
        if moved_from: msg += f"\n🔄 {', '.join(moved_from)}"
        msg += f"\n\n{build_team_summary(self.guild, gid)}"
        await send_minimal(interaction, msg)

    @discord.ui.button(label="🚀 Send Teams", style=discord.ButtonStyle.success, row=2)
    async def send_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild.id
        teams = team_storage.get(gid, {})
        if not teams: await send_minimal(interaction, "⚠️ No teams assigned yet."); return
        results = []
        for vc_id, member_ids in teams.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            moved, skipped = [], []
            for mid in member_ids:
                m = self.guild.get_member(mid)
                if m and m.voice: await m.move_to(vc); moved.append(m.display_name)
                elif m: skipped.append(m.display_name)
            line = f"**{vc.name}**: {', '.join(moved) if moved else 'nobody moved'}"
            if skipped: line += f" _(not in voice: {', '.join(skipped)})_"
            results.append(line)
        save_team_to_history(gid, self.guild)
        await send_minimal(interaction, "🚀 **Teams dispatched!**\n" + "\n".join(results), ephemeral=False)

    @discord.ui.button(label="📋 Show Teams", style=discord.ButtonStyle.secondary, row=2)
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await send_minimal(interaction, f"**Current Teams:**\n{build_team_summary(self.guild, self.guild.id)}")

    @discord.ui.button(label="🎲 Randomise Teams", style=discord.ButtonStyle.primary, row=3)
    async def randomise_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🎲 **Randomise Teams**\nPick channels — all players in voice will be shuffled evenly.",
                                                 view=RandomiseView(self.guild), ephemeral=True)

    @discord.ui.button(label="⚖️ Balanced Teams", style=discord.ButtonStyle.primary, row=3)
    async def balanced_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚖️ **MMR Balanced Teams**\nPlayers distributed by rank using a snake draft.",
                                                 view=MatchmakeView(self.guild), ephemeral=True)

    @discord.ui.button(label="💾 Save Preset", style=discord.ButtonStyle.secondary, row=3)
    async def save_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SavePresetModal(self.guild))

    @discord.ui.button(label="📂 Load Preset", style=discord.ButtonStyle.secondary, row=3)
    async def load_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not presets.get(str(self.guild.id)):
            await send_minimal(interaction, "⚠️ No presets saved yet. Use 💾 Save Preset first.")
            return
        await interaction.response.send_message("📂 **Load Preset**\nSelect a preset to preview then click 📂 Load Preset to activate.",
                                                 view=TeamPresetsView(self.guild), ephemeral=True)

    @discord.ui.button(label="🗑️ Clear Teams", style=discord.ButtonStyle.danger, row=4)
    async def clear_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_storage.pop(self.guild.id, None)
        await send_minimal(interaction, "✅ Teams cleared.")

    @discord.ui.button(label="🔁 Recall All to Lobby", style=discord.ButtonStyle.secondary, row=4)
    async def recall_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        gmap = get_guild_lobby_map(self.guild.id)
        if not gmap:
            await send_minimal(interaction, "⚠️ No lobby mappings set. Use `/set_lobby` first.")
            return
        await interaction.response.defer()
        moved_total = 0
        for vc_id_str, lobby_id in gmap.items():
            vc    = self.guild.get_channel(int(vc_id_str))
            lobby = self.guild.get_channel(int(lobby_id))
            if not vc or not lobby: continue
            for member in list(vc.members):
                if member.voice and member.voice.channel == vc:
                    await member.move_to(lobby)
                    moved_total += 1
        await followup_minimal(interaction, f"✅ Recalled **{moved_total}** member(s) to lobbies.", ephemeral=False)

class TeamMemberSelect(discord.ui.Select):
    def __init__(self, members):
        self.selected_members = []
        if members:
            options  = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members[:25]]
            max_vals = min(len(members), 25)
        else:
            options  = [discord.SelectOption(label="No members in voice", value="none")]
            max_vals = 1
        super().__init__(placeholder="1️⃣ Pick member(s)...", options=options, min_values=1, max_values=max_vals, row=0)
    async def callback(self, interaction: discord.Interaction):
        if self.values == ["none"]: await send_minimal(interaction, "⚠️ No members in voice channels."); return
        self.selected_members = [interaction.guild.get_member(int(uid)) for uid in self.values]
        names = ", ".join(m.display_name for m in self.selected_members if m)
        await send_minimal(interaction, f"✅ Selected: **{names}**")

class TeamChannelSelect(discord.ui.Select):
    def __init__(self, vcs):
        self.selected_vc_id = None
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in vcs[:25]]
        super().__init__(placeholder="2️⃣ Pick their team channel...", options=options, min_values=1, max_values=1, row=1)
    async def callback(self, interaction: discord.Interaction):
        self.selected_vc_id = self.values[0]
        vc = interaction.guild.get_channel(int(self.selected_vc_id))
        await send_minimal(interaction, f"✅ Channel: **{vc.name}**")

# ─────────────────────────────────────────────
# SLASH COMMANDS
# ─────────────────────────────────────────────

@bot.tree.command(name="recall", description="[Admin] Move all voice members to their mapped lobby.")
@is_admin()
async def recall(interaction: discord.Interaction):
    gmap = get_guild_lobby_map(interaction.guild.id)
    if not gmap:
        await send_minimal(interaction, "⚠️ No lobby mappings configured. Use `/set_lobby` first.")
        return
    await interaction.response.defer()
    moved_total = 0
    for vc_id_str, lobby_id in gmap.items():
        vc    = interaction.guild.get_channel(int(vc_id_str))
        lobby = interaction.guild.get_channel(int(lobby_id))
        if not vc or not lobby: continue
        for member in list(vc.members):
            if member.voice and member.voice.channel == vc:
                await member.move_to(lobby)
                moved_total += 1
    await followup_minimal(interaction, f"✅ Recalled **{moved_total}** member(s) to their lobbies.", ephemeral=False)


@bot.tree.command(name="set_lobby", description="[Admin] Map voice channel(s) to a lobby destination.")
@is_admin()
async def set_lobby(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🔧 **Lobby Mapper**\n1️⃣ Pick source channels → 2️⃣ Pick destination → 💾 Save",
        view=LobbyMappingView(interaction.guild), ephemeral=True)


@bot.tree.command(name="teams", description="[Admin] Build teams and send members to voice channels.")
@is_admin()
async def teams(interaction: discord.Interaction):
    if not [c for c in interaction.guild.channels if isinstance(c, discord.VoiceChannel)]:
        await send_minimal(interaction, "⚠️ No voice channels found.")
        return
    await interaction.response.send_message(
        "👥 **Team Builder**\n"
        "1️⃣ Pick members → 2️⃣ Pick channel → ➕ Assign → Repeat → 🚀 Send!\n"
        "🎲 Randomise or ⚖️ Balanced for automatic generation\n"
        "💾 Save Preset to store a lineup | 📂 Load Preset to restore one\n"
        "Use 🔁 to recall everyone back between rounds.",
        view=TeamBuilderView(interaction.guild), ephemeral=True)


@bot.tree.command(name="sub", description="[Admin] Swap two players between teams.")
@is_admin()
async def sub(interaction: discord.Interaction, player_out: str, player_in: str):
    gid   = interaction.guild.id
    teams = team_storage.get(gid, {})
    if not teams:
        await send_minimal(interaction, "⚠️ No active teams. Set teams first with `/teams`.")
        return
    guild = interaction.guild

    # Find player_out by display name
    member_out = next((guild.get_member(mid) for mids in teams.values() for mid in mids
                       if guild.get_member(mid) and guild.get_member(mid).display_name.lower() == player_out.lower()), None)
    if not member_out:
        await send_minimal(interaction, f"⚠️ **{player_out}** not found in any team.")
        return

    # Find player_in anywhere in the guild
    member_in = next((m for m in guild.members if m.display_name.lower() == player_in.lower()), None)
    if not member_in:
        await send_minimal(interaction, f"⚠️ **{player_in}** not found in this server.")
        return

    # Find which team player_out is on
    out_vc_id = find_member_team(gid, member_out.id)
    if not out_vc_id:
        await send_minimal(interaction, f"⚠️ **{player_out}** is not assigned to a team.")
        return

    # Remove player_out, add player_in
    team_storage[gid][out_vc_id].remove(member_out.id)
    # Remove player_in from any existing team first
    in_vc_id = find_member_team(gid, member_in.id)
    if in_vc_id:
        team_storage[gid][in_vc_id].remove(member_in.id)
    team_storage[gid][out_vc_id].append(member_in.id)

    # Move in voice if possible
    vc = guild.get_channel(int(out_vc_id))
    voice_note = ""
    if member_in.voice:
        await member_in.move_to(vc)
        voice_note = " and moved to voice channel"

    await send_minimal(interaction,
        f"🔄 **Sub complete!**\n"
        f"**{member_out.display_name}** ← out\n"
        f"**{member_in.display_name}** → in{voice_note}\n"
        f"Team: **{vc.name if vc else out_vc_id}**\n\n"
        f"{build_team_summary(guild, gid)}", ephemeral=False)


@bot.tree.command(name="import_mmr", description="[Admin] Import player stats from your session Excel file.")
@is_admin()
async def import_mmr(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith((".xlsx", ".csv")):
        await send_minimal(interaction, "⚠️ Please upload a `.xlsx` or `.csv` file.")
        return
    await interaction.response.defer(ephemeral=True)
    try:
        import openpyxl
        wb  = openpyxl.load_workbook(io.BytesIO(await file.read()))
        gid = str(interaction.guild_id)
        if gid not in mmr_data: mmr_data[gid] = {}

        skip = ("collective", "summary")
        session_sheets = [s for s in wb.sheetnames if not any(k in s.lower() for k in skip) and s.lower() != "leaderboard"]

        per_player: dict = {}
        for sheet_name in session_sheets:
            players = parse_session_sheet(wb[sheet_name])
            if not players: continue
            players = calculate_mmr(players)
            players_sorted = sorted(players, key=lambda x: x["mmr"], reverse=True)
            session_ranks  = {p["name"]: i+1 for i, p in enumerate(players_sorted)}
            session_size   = len(players)
            for p in players:
                cname = p["name"]
                if cname not in per_player: per_player[cname] = []
                per_player[cname].append({
                    "session":      sheet_name,
                    "mmr":          p["mmr"],
                    "kd":           p["kd"],
                    "kills":        p.get("kills", 0),
                    "deaths":       p.get("deaths", 0),
                    "points":       p["points"],
                    "session_rank": session_ranks.get(p["name"], "?"),
                    "session_size": session_size,
                })

        overall_mmr: dict = {}
        if "Leaderboard" in wb.sheetnames:
            lb_players = parse_leaderboard_sheet(wb["Leaderboard"])
            if lb_players:
                lb_players = calculate_mmr(lb_players)
                for p in lb_players:
                    overall_mmr[p["name"]] = p

        if not per_player and not overall_mmr:
            await interaction.followup.send("⚠️ No valid data found.", ephemeral=True)
            return

        all_names = set(per_player.keys()) | set(overall_mmr.keys())
        imported  = []
        for cname in all_names:
            existing = mmr_data[gid].get(cname, {})
            sessions_list = per_player.get(cname, [])
            lb = overall_mmr.get(cname) or next(
                (v for k, v in overall_mmr.items() if k.lower() == cname.lower()), None)
            existing_sessions = [h["session"] for h in existing.get("history", [])]
            new_history = existing.get("history", [])
            for s in sessions_list:
                if s["session"] not in existing_sessions:
                    new_history.append(s)
            if lb:
                overall = lb["mmr"]
                kd, kills, deaths = lb["kd"], lb.get("kills", 0), lb.get("deaths", 0)
                points, obj_time  = lb["points"], lb["obj_time"]
                assists, captures = lb["assists"], lb["captures"]
                session_count     = lb["sessions"]
            elif sessions_list:
                overall = round(sum(s["mmr"] for s in sessions_list) / len(sessions_list), 1)
                last    = sessions_list[-1]
                kd, kills, deaths = last["kd"], last.get("kills", 0), last.get("deaths", 0)
                points, obj_time, assists, captures = last["points"], 0, 0, 0
                session_count = len(sessions_list)
            else:
                continue
            mmr_data[gid][cname] = {
                "mmr": overall, "kd": kd, "kills": kills, "deaths": deaths,
                "points": points, "obj_time": obj_time, "assists": assists,
                "captures": captures, "sessions": session_count, "history": new_history,
            }
            imported.append((cname, overall, session_count))

        save_json(MMR_FILE, mmr_data)
        imported.sort(key=lambda x: x[1], reverse=True)

        lines = []
        for cname, mmr, sessions in imported:
            rname, ename = halo_rank(mmr)
            remoji = get_emoji(interaction.guild, ename)
            prov   = "*" if sessions < PROVISIONAL_SESSIONS else ""
            lines.append(f"{remoji} **{cname}**{prov} — {mmr} MMR")

        header = f"✅ Imported **{len(imported)}** players!\n_* = Provisional (fewer than {PROVISIONAL_SESSIONS} sessions)_\n"
        await send_single_or_chunked(interaction, lines, header=header, ephemeral=True)

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {e}", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show the Halo Reach MMR leaderboard.")
async def leaderboard(interaction: discord.Interaction):
    gmmr = get_guild_mmr(interaction.guild_id)
    if not gmmr:
        await send_minimal(interaction, "⚠️ No MMR data yet. An admin needs to run `/import_mmr` first.")
        return
    await interaction.response.defer()
    sorted_players = sorted(gmmr.items(), key=lambda x: x[1].get("mmr", 0), reverse=True)
    rank_groups: OrderedDict = OrderedDict()
    for pos, (name, data) in enumerate(sorted_players, 1):
        mmr      = data.get("mmr", 0)
        sessions = data.get("sessions", 0)
        rname, ename = halo_rank(mmr)
        prov  = "*" if sessions < PROVISIONAL_SESSIONS else ""
        entry = f"  `#{pos}` **{name}**{prov} — {mmr} MMR"
        if rname not in rank_groups:
            rank_groups[rname] = {"ename": ename, "entries": []}
        rank_groups[rname]["entries"].append(entry)
    lines = []
    for rname, group in rank_groups.items():
        remoji = get_emoji(interaction.guild, group["ename"])
        lines.append(f"{remoji} **{rname}**")
        lines.extend(group["entries"])
    header  = f"🏆 **Halo Night MMR Leaderboard**\n_* = Provisional (fewer than {PROVISIONAL_SESSIONS} sessions)_\n"
    await send_single_or_chunked(interaction, lines, header=header, ephemeral=False)


@bot.tree.command(name="mmr", description="Look up a player's MMR, rank, and session history.")
async def mmr_lookup(interaction: discord.Interaction, player: str):
    gmmr  = get_guild_mmr(interaction.guild_id)
    match = next((v for k, v in gmmr.items() if k.lower() == player.lower()), None)
    name  = next((k for k in gmmr if k.lower() == player.lower()), player)
    if not match:
        await send_minimal(interaction, f"⚠️ No MMR data found for **{player}**.\nTip: use just the first name e.g. `Jacob`")
        return
    await interaction.response.defer()
    sorted_all      = sorted(gmmr.values(), key=lambda x: x.get("mmr", 0), reverse=True)
    total_players   = len(gmmr)
    rank_pos        = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == match.get("mmr")), "?")
    mmr             = match.get("mmr", 0)
    sessions        = match.get("sessions", 0)
    rname, ename    = halo_rank(mmr)
    remoji          = get_emoji(interaction.guild, ename)
    prov            = " *" if sessions < PROVISIONAL_SESSIONS else ""
    sessions_needed = PROVISIONAL_SESSIONS - sessions
    prov_note       = f"\n_* Provisional — needs {sessions_needed} more session(s) to confirm rank._" if sessions < PROVISIONAL_SESSIONS else ""

    kills  = match.get("kills", 0)
    deaths = match.get("deaths", 0)
    assists = match.get("assists", 0)
    kda    = round((kills + assists) / max(deaths, 1), 2)
    lines = [
        f"**{name}** {remoji} *{rname}*{prov} — Rank **#{rank_pos} / {total_players}**{prov_note}",
        f"Overall MMR: **{mmr}** | Sessions: **{sessions}**",
        f"Kills: {kills} | Deaths: {deaths} | K/D: {match.get('kd','?')} | KDA: {kda} | "
        f"Assists: {assists} | Points: {match.get('points','?')} | "
        f"Obj Time: {match.get('obj_time','?')}s | Captures: {match.get('captures','?')}",
    ]
    history = match.get("history", [])
    if history:
        lines.append("\n📈 **Session Breakdown**")
        prev_mmr = None
        for h in history:
            h_rname, h_ename = halo_rank(h["mmr"])
            h_remoji  = get_emoji(interaction.guild, h_ename)
            s_rank    = h.get("session_rank", "?")
            s_size    = h.get("session_size", "?")
            arrow     = "" if prev_mmr is None else (" ▲" if h["mmr"] > prev_mmr else " ▼" if h["mmr"] < prev_mmr else " ─")
            lines.append(f"> {h_remoji} *{h_rname}* | **{h['session']}**: {h['mmr']} MMR — #{s_rank}/{s_size}{arrow}")
            prev_mmr  = h["mmr"]
    await send_single_or_chunked(interaction, lines, ephemeral=False)


@bot.tree.command(name="rank", description="Check your own current rank and MMR.")
async def rank(interaction: discord.Interaction):
    gmmr  = get_guild_mmr(interaction.guild_id)
    dname = interaction.user.display_name
    cname = canonical_name(dname)
    match = gmmr.get(cname) or gmmr.get(dname) or next(
        (v for k, v in gmmr.items() if k.lower() == cname.lower()), None)
    if not match:
        await send_minimal(interaction,
            f"⚠️ No MMR data found for **{dname}**.\n"
            f"Your Discord display name needs to match your name in the spreadsheet.\n"
            f"Ask an admin to run `/import_mmr` if you haven't been imported yet.")
        return
    sorted_all    = sorted(gmmr.values(), key=lambda x: x.get("mmr", 0), reverse=True)
    total_players = len(gmmr)
    rank_pos      = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == match.get("mmr")), "?")
    mmr           = match.get("mmr", 0)
    sessions      = match.get("sessions", 0)
    rname, ename  = halo_rank(mmr)
    remoji        = get_emoji(interaction.guild, ename)
    prov          = " *" if sessions < PROVISIONAL_SESSIONS else ""
    prov_note     = f"\n_* {PROVISIONAL_SESSIONS - sessions} more session(s) until your rank is confirmed._" if sessions < PROVISIONAL_SESSIONS else ""

    rk = match.get("kills", 0)
    rd = match.get("deaths", 0)
    ra = match.get("assists", 0)
    rkda = round((rk + ra) / max(rd, 1), 2)
    await send_minimal(interaction,
        f"**{dname}** {remoji} *{rname}*{prov} — Rank **#{rank_pos} / {total_players}**{prov_note}\n"
        f"MMR: **{mmr}** | Sessions: **{sessions}**\n"
        f"Kills: {rk} | Deaths: {rd} | K/D: {match.get('kd','?')} | KDA: {rkda} | "
        f"Assists: {ra} | Points: {match.get('points','?')} | "
        f"Obj Time: {match.get('obj_time','?')}s | Captures: {match.get('captures','?')}",
        ephemeral=True)


@bot.tree.command(name="compare", description="Compare two players side by side.")
async def compare(interaction: discord.Interaction, player1: str, player2: str):
    gmmr = get_guild_mmr(interaction.guild_id)
    d1   = next((v for k, v in gmmr.items() if k.lower() == player1.lower()), None)
    d2   = next((v for k, v in gmmr.items() if k.lower() == player2.lower()), None)
    n1   = next((k for k in gmmr if k.lower() == player1.lower()), player1)
    n2   = next((k for k in gmmr if k.lower() == player2.lower()), player2)
    if not d1:
        await send_minimal(interaction, f"⚠️ No data found for **{player1}**."); return
    if not d2:
        await send_minimal(interaction, f"⚠️ No data found for **{player2}**."); return

    await interaction.response.defer()
    sorted_all = sorted(gmmr.values(), key=lambda x: x.get("mmr", 0), reverse=True)
    total      = len(gmmr)
    r1         = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == d1.get("mmr")), "?")
    r2         = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == d2.get("mmr")), "?")
    rname1, ename1 = halo_rank(d1.get("mmr", 0))
    rname2, ename2 = halo_rank(d2.get("mmr", 0))
    e1 = get_emoji(interaction.guild, ename1)
    e2 = get_emoji(interaction.guild, ename2)

    def vs(val1, val2, higher_is_better=True):
        try:
            v1, v2 = float(val1), float(val2)
            if higher_is_better:
                w = "⬆️" if v1 > v2 else ("⬇️" if v1 < v2 else "🟰")
            else:
                w = "⬆️" if v1 < v2 else ("⬇️" if v1 > v2 else "🟰")
            return w
        except: return "❔"

    lines = [
        f"**{n1}** {e1} *{rname1}* vs **{n2}** {e2} *{rname2}*\n",
        f"{'Stat':<14} {'▸ ' + n1:<18} {'▸ ' + n2:<18}",
        f"{'-'*52}",
        f"{'Rank':<14} {'#' + str(r1) + '/' + str(total):<18} {'#' + str(r2) + '/' + str(total):<18}",
        f"{'MMR':<14} {str(d1.get('mmr','?')):<18} {str(d2.get('mmr','?')):<18} {vs(d1.get('mmr',0), d2.get('mmr',0))}",
        f"{'Kills':<14} {str(d1.get('kills','?')):<18} {str(d2.get('kills','?')):<18} {vs(d1.get('kills',0), d2.get('kills',0))}",
        f"{'Deaths':<14} {str(d1.get('deaths','?')):<18} {str(d2.get('deaths','?')):<18} {vs(d1.get('deaths',0), d2.get('deaths',0), higher_is_better=False)}",
        f"{'K/D':<14} {str(d1.get('kd','?')):<18} {str(d2.get('kd','?')):<18} {vs(d1.get('kd',0), d2.get('kd',0))}",
        f"{'Assists':<14} {str(d1.get('assists','?')):<18} {str(d2.get('assists','?')):<18} {vs(d1.get('assists',0), d2.get('assists',0))}",
        f"{'Points':<14} {str(d1.get('points','?')):<18} {str(d2.get('points','?')):<18} {vs(d1.get('points',0), d2.get('points',0))}",
        f"{'Obj Time':<14} {str(d1.get('obj_time','?')) + 's':<18} {str(d2.get('obj_time','?')) + 's':<18} {vs(d1.get('obj_time',0), d2.get('obj_time',0))}",
        f"{'Captures':<14} {str(d1.get('captures','?')):<18} {str(d2.get('captures','?')):<18} {vs(d1.get('captures',0), d2.get('captures',0))}",
        f"{'Sessions':<14} {str(d1.get('sessions','?')):<18} {str(d2.get('sessions','?')):<18}",
    ]
    await send_single_or_chunked(interaction, lines, header="", ephemeral=False)


@bot.tree.command(name="rivals", description="Head-to-head session history between two players.")
async def rivals(interaction: discord.Interaction, player1: str, player2: str):
    gmmr = get_guild_mmr(interaction.guild_id)
    d1   = next((v for k, v in gmmr.items() if k.lower() == player1.lower()), None)
    d2   = next((v for k, v in gmmr.items() if k.lower() == player2.lower()), None)
    n1   = next((k for k in gmmr if k.lower() == player1.lower()), player1)
    n2   = next((k for k in gmmr if k.lower() == player2.lower()), player2)
    if not d1:
        await send_minimal(interaction, f"⚠️ No data found for **{player1}**."); return
    if not d2:
        await send_minimal(interaction, f"⚠️ No data found for **{player2}**."); return

    await interaction.response.defer()
    h1 = {h["session"]: h for h in d1.get("history", [])}
    h2 = {h["session"]: h for h in d2.get("history", [])}
    shared = sorted(set(h1.keys()) & set(h2.keys()))

    if not shared:
        await followup_minimal(interaction, f"⚠️ **{n1}** and **{n2}** have no sessions in common.")
        return

    p1_wins, p2_wins, draws = 0, 0, 0
    lines = [f"⚔️ **{n1}** vs **{n2}** — {len(shared)} shared session(s)\n"]
    for session in shared:
        s1 = h1[session]
        s2 = h2[session]
        r1, e1 = halo_rank(s1["mmr"])
        r2, e2 = halo_rank(s2["mmr"])
        em1 = get_emoji(interaction.guild, e1)
        em2 = get_emoji(interaction.guild, e2)
        if s1["mmr"] > s2["mmr"]:
            winner = f"→ **{n1}** wins"
            p1_wins += 1
        elif s2["mmr"] > s1["mmr"]:
            winner = f"→ **{n2}** wins"
            p2_wins += 1
        else:
            winner = "→ Draw"
            draws += 1
        rank1 = f"#{s1.get('session_rank','?')}/{s1.get('session_size','?')}"
        rank2 = f"#{s2.get('session_rank','?')}/{s2.get('session_size','?')}"
        lines.append(
            f"**{session}**\n"
            f"> {em1} {n1}: {s1['mmr']} MMR ({rank1})\n"
            f"> {em2} {n2}: {s2['mmr']} MMR ({rank2})\n"
            f"> {winner}"
        )

    lines.append(f"\n🏆 **Head-to-head:** {n1} {p1_wins} — {p2_wins} {n2}" + (f" ({draws} draw)" if draws else ""))
    await send_single_or_chunked(interaction, lines, ephemeral=False)


@bot.tree.command(name="stats", description="Show top performers by stat category.")
async def stats(interaction: discord.Interaction):
    gmmr = get_guild_mmr(interaction.guild_id)
    if not gmmr:
        await send_minimal(interaction, "⚠️ No MMR data yet. An admin needs to run `/import_mmr` first.")
        return
    await interaction.response.defer()

    categories = [
        ("mmr",      "🏆 Top MMR",         True),
        ("kd",       "🎯 Best K/D",         True),
        ("kills",    "💀 Most Kills",       True),
        ("deaths",   "☠️ Fewest Deaths",    False),
        ("assists",  "🤝 Most Assists",     True),
        ("obj_time", "⏱️ Most Obj Time",    True),
        ("captures", "🚩 Most Captures",    True),
        ("points",   "⭐ Most Points",      True),
    ]

    lines = ["📊 **Stat Leaders**\n"]
    for key, label, higher_is_better in categories:
        valid = [(name, data) for name, data in gmmr.items() if data.get(key) is not None]
        if not valid: continue
        best_name, best_data = sorted(valid, key=lambda x: x[1].get(key, 0), reverse=higher_is_better)[0]
        val   = best_data.get(key, "?")
        rname, ename = halo_rank(best_data.get("mmr", 0))
        remoji = get_emoji(interaction.guild, ename)
        suffix = "s" if key == "obj_time" else ""
        lines.append(f"{label}: **{best_name}** {remoji} — {val}{suffix}")

    await send_single_or_chunked(interaction, lines, ephemeral=False)


@bot.tree.command(name="export", description="[Admin] Download the MMR data file.")
@is_admin()
async def export(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    gid  = str(interaction.guild_id)
    gmmr = mmr_data.get(gid, {})
    if not gmmr:
        await interaction.followup.send("⚠️ No MMR data to export.", ephemeral=True)
        return
    data    = json.dumps({gid: gmmr}, indent=2)
    buffer  = io.BytesIO(data.encode())
    fname   = f"mmr_data_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M')}.json"
    await interaction.followup.send(
        "📦 Here is your current MMR data file:",
        file=discord.File(buffer, filename=fname),
        ephemeral=True
    )


@bot.tree.command(name="presets", description="[Admin] View and load saved team presets.")
@is_admin()
async def view_presets(interaction: discord.Interaction):
    if not presets.get(str(interaction.guild_id)):
        await send_minimal(interaction, "⚠️ No presets saved yet. Use 💾 Save Preset in `/teams`.")
        return
    await interaction.response.send_message("📋 **Saved Team Presets** — select one to view:",
                                             view=LoadPresetView(interaction.guild), ephemeral=True)


@bot.tree.command(name="history", description="[Admin] View past team configurations.")
@is_admin()
async def view_history(interaction: discord.Interaction):
    if not team_history.get(str(interaction.guild_id)):
        await send_minimal(interaction, "⚠️ No team history yet.")
        return
    await interaction.response.send_message("📜 **Team History** — select an entry to view:",
                                             view=TeamHistoryView(interaction.guild), ephemeral=True)

# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@recall.error
@set_lobby.error
@teams.error
@sub.error
@import_mmr.error
@export.error
@view_presets.error
@view_history.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await send_minimal(interaction, "❌ Administrator permissions required.")
    else:
        raise error

# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

# ─────────────────────────────────────────────
# SESSION STATS COMMAND
# ─────────────────────────────────────────────

@bot.tree.command(name="session", description="Look up a player's stats from a specific session.")
async def session_lookup(interaction: discord.Interaction, session: str, player: str):
    gmmr = get_guild_mmr(interaction.guild_id)
    match = next((v for k, v in gmmr.items() if k.lower() == player.lower()), None)
    name  = next((k for k in gmmr if k.lower() == player.lower()), player)
    if not match:
        await send_minimal(interaction, f"⚠️ No data found for **{player}**.")
        return
    history = match.get("history", [])
    entry = next((h for h in history if h["session"].lower() == session.lower()), None)
    if not entry:
        sessions_list = ", ".join(f"`{h['session']}`" for h in history) or "none"
        msg = f"⚠️ **{name}** has no data for session `{session}`.\nAvailable sessions: {sessions_list}"
        await send_minimal(interaction, msg)
        return

    mmr    = entry["mmr"]
    s_rank = entry.get("session_rank", "?")
    s_size = entry.get("session_size", "?")
    rname, ename = halo_rank(mmr)
    remoji = get_emoji(interaction.guild, ename)

    # K/D from session history entry
    kd     = entry.get("kd", "?")
    kills  = entry.get("kills", "?")
    deaths = entry.get("deaths", "?")
    points = entry.get("points", "?")
    assists_val = entry.get("assists", "?")
    captures_val = entry.get("captures", "?")
    try:
        kda = round((float(kills) + float(assists_val)) / max(float(deaths), 1), 2)
    except:
        kda = "?"

    out = "\n".join([
        f"**{name}** \u2014 {entry['session']}",
        f"{remoji} *{rname}* | MMR: **{mmr}** | Session Rank: **#{s_rank}/{s_size}**",
        f"Kills: {kills} | Deaths: {deaths} | K/D: {kd} | KDA: {kda}",
        f"Assists: {assists_val} | Points: {points} | Captures: {captures_val}",
    ])
    await send_minimal(interaction, out, ephemeral=False)


# ─────────────────────────────────────────────
# HALO 3 MATCHMAKING SYSTEM
# ─────────────────────────────────────────────

# Map pool — all standard + DLC maps with Halopedia thumbnail URLs
# URL pattern: https://www.halopedia.org/Special:FilePath/H3_Multiplayer_<Name>.jpg
def h3_img(filename: str) -> str:
    return f"https://www.halopedia.org/Special:FilePath/{filename}"

HALO3_MAPS = [
    # Standard maps
    {"name": "Construct",   "img": h3_img("H3_Multiplayer_Construct.jpg"),   "dlc": False},
    {"name": "Epitaph",     "img": h3_img("H3_Multiplayer_Epitaph.jpg"),     "dlc": False},
    {"name": "Guardian",    "img": h3_img("H3_Multiplayer_Guardian.jpg"),    "dlc": False},
    {"name": "High Ground", "img": h3_img("H3_Multiplayer_High_Ground.jpg"), "dlc": False},
    {"name": "Isolation",   "img": h3_img("H3_Multiplayer_Isolation.jpg"),   "dlc": False},
    {"name": "Last Resort", "img": h3_img("H3_Multiplayer_Last_Resort.jpg"), "dlc": False},
    {"name": "Narrows",     "img": h3_img("H3_Multiplayer_Narrows.jpg"),     "dlc": False},
    {"name": "Sandtrap",    "img": h3_img("H3_Multiplayer_Sandtrap.jpg"),    "dlc": False},
    {"name": "Snowbound",   "img": h3_img("H3_Multiplayer_Snowbound.jpg"),   "dlc": False},
    {"name": "The Pit",     "img": h3_img("H3_Multiplayer_The_Pit.jpg"),     "dlc": False},
    {"name": "Valhalla",    "img": h3_img("H3_Multiplayer_Valhalla.jpg"),    "dlc": False},
    # Heroic DLC
    {"name": "Foundry",     "img": h3_img("H3_Multiplayer_Foundry.jpg"),     "dlc": True},
    {"name": "Rat's Nest",  "img": h3_img("H3_Multiplayer_Rats_Nest.jpg"),   "dlc": True},
    {"name": "Standoff",    "img": h3_img("H3_Multiplayer_Standoff.jpg"),    "dlc": True},
    # Legendary DLC
    {"name": "Avalanche",   "img": h3_img("H3_Multiplayer_Avalanche.jpg"),   "dlc": True},
    {"name": "Blackout",    "img": h3_img("H3_Multiplayer_Blackout.jpg"),    "dlc": True},
    {"name": "Ghost Town",  "img": h3_img("H3_Multiplayer_Ghost_Town.jpg"),  "dlc": True},
    # Mythic DLC
    {"name": "Assembly",    "img": h3_img("H3_Multiplayer_Assembly.jpg"),    "dlc": True},
    {"name": "Citadel",     "img": h3_img("H3_Multiplayer_Citadel.jpg"),     "dlc": True},
    {"name": "Heretic",     "img": h3_img("H3_Multiplayer_Heretic.jpg"),     "dlc": True},
    {"name": "Longshore",   "img": h3_img("H3_Multiplayer_Longshore.jpg"),   "dlc": True},
    {"name": "Orbital",     "img": h3_img("H3_Multiplayer_Orbital.jpg"),     "dlc": True},
    {"name": "Sandbox",     "img": h3_img("H3_Multiplayer_Sandbox.jpg"),     "dlc": True},
]

HALO3_GAMETYPES = [
    "Slayer", "Team Slayer", "Capture the Flag", "Oddball",
    "King of the Hill", "VIP", "Territories", "Assault", "Infection",
]


class MatchmakingMenuView(discord.ui.View):
    """Opening menu — choose mode."""
    def __init__(self):
        super().__init__(timeout=120)

    @discord.ui.button(label="🎲 Single Match", style=discord.ButtonStyle.primary, row=0)
    async def single_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🎲 **Single Match — Choose your settings**",
            view=SingleMatchSetupView(),
            ephemeral=True
        )

    @discord.ui.button(label="🎲🎲 Two Matches", style=discord.ButtonStyle.primary, row=0)
    async def two_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "🎲 **Two Matches — Choose your settings**",
            view=TwoMatchSetupView(),
            ephemeral=True
        )

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=0)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()


class TeamCountSelect(discord.ui.Select):
    def __init__(self, row=0):
        self.selected_count = 2
        options = [
            discord.SelectOption(label=f"{i} Teams", value=str(i), default=(i == 2))
            for i in range(2, 9)
        ]
        super().__init__(placeholder="Number of teams...", options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.selected_count = int(self.values[0])
        await interaction.response.defer()


class MapPoolSelect(discord.ui.Select):
    def __init__(self, row=1):
        self.include_dlc = False
        options = [
            discord.SelectOption(label="Standard maps only", value="standard", default=True),
            discord.SelectOption(label="Standard + all DLC", value="all"),
        ]
        super().__init__(placeholder="Map pool...", options=options, row=row)

    async def callback(self, interaction: discord.Interaction):
        self.include_dlc = self.values[0] == "all"
        await interaction.response.defer()


class SingleMatchSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.team_select = TeamCountSelect(row=0)
        self.map_select  = MapPoolSelect(row=1)
        self.add_item(self.team_select)
        self.add_item(self.map_select)

    @discord.ui.button(label="🎲 Roll!", style=discord.ButtonStyle.success, row=2)
    async def roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps = [m for m in HALO3_MAPS if not m["dlc"] or self.map_select.include_dlc]
        chosen_map      = random.choice(maps)
        chosen_gametype = random.choice(HALO3_GAMETYPES)
        num_teams       = self.team_select.selected_count

        embed = discord.Embed(
            title="🎮 Halo 3 — Match Roll",
            color=0x00aaff
        )
        embed.add_field(name="🗺️ Map",      value=f"**{chosen_map['name']}**", inline=True)
        embed.add_field(name="🎯 Game Type", value=f"**{chosen_gametype}**",   inline=True)
        embed.add_field(name="👥 Teams",     value=f"**{num_teams}**",          inline=True)
        embed.set_image(url=chosen_map["img"])
        embed.set_footer(text="Halo Night Bot — Matchmaking")

        await interaction.response.send_message(embed=embed, ephemeral=False)


class TwoMatchSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=120)
        self.team_select = TeamCountSelect(row=0)
        self.map_select  = MapPoolSelect(row=1)
        self.add_item(self.team_select)
        self.add_item(self.map_select)

    @discord.ui.button(label="🎲 Roll Both Matches!", style=discord.ButtonStyle.success, row=2)
    async def roll(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps  = [m for m in HALO3_MAPS if not m["dlc"] or self.map_select.include_dlc]
        sample = random.sample(maps, min(2, len(maps)))
        m1, m2 = sample[0], sample[1]
        g1     = random.choice(HALO3_GAMETYPES)
        g2     = random.choice(HALO3_GAMETYPES)
        num_teams = self.team_select.selected_count

        embed1 = discord.Embed(title="🎮 Match 1", color=0x00aaff)
        embed1.add_field(name="🗺️ Map",      value=f"**{m1['name']}**", inline=True)
        embed1.add_field(name="🎯 Game Type", value=f"**{g1}**",         inline=True)
        embed1.add_field(name="👥 Teams",     value=f"**{num_teams}**",   inline=True)
        embed1.set_image(url=m1["img"])

        embed2 = discord.Embed(title="🎮 Match 2", color=0xff6600)
        embed2.add_field(name="🗺️ Map",      value=f"**{m2['name']}**", inline=True)
        embed2.add_field(name="🎯 Game Type", value=f"**{g2}**",         inline=True)
        embed2.add_field(name="👥 Teams",     value=f"**{num_teams}**",   inline=True)
        embed2.set_image(url=m2["img"])

        # Show veto view for both matches
        await interaction.response.send_message(
            "⚔️ **Two matches rolled! Each team can veto one option below.**",
            embeds=[embed1, embed2],
            view=VetoView(m1, g1, m2, g2, num_teams, maps),
            ephemeral=False
        )


class VetoView(discord.ui.View):
    """Veto system: each match has a Map veto and a Gametype veto button.
       When vetoed, that slot is rerolled once. Buttons disable after use."""

    def __init__(self, m1, g1, m2, g2, num_teams, maps):
        super().__init__(timeout=300)
        self.m1, self.g1 = m1, g1
        self.m2, self.g2 = m2, g2
        self.num_teams   = num_teams
        self.maps        = maps
        self.vetoed      = set()  # track what's been vetoed

    def _build_embeds(self):
        e1 = discord.Embed(title="🎮 Match 1", color=0x00aaff)
        e1.add_field(name="🗺️ Map",      value=f"**{self.m1['name']}**", inline=True)
        e1.add_field(name="🎯 Game Type", value=f"**{self.g1}**",         inline=True)
        e1.add_field(name="👥 Teams",     value=f"**{self.num_teams}**",   inline=True)
        e1.set_image(url=self.m1["img"])

        e2 = discord.Embed(title="🎮 Match 2", color=0xff6600)
        e2.add_field(name="🗺️ Map",      value=f"**{self.m2['name']}**", inline=True)
        e2.add_field(name="🎯 Game Type", value=f"**{self.g2}**",         inline=True)
        e2.add_field(name="👥 Teams",     value=f"**{self.num_teams}**",   inline=True)
        e2.set_image(url=self.m2["img"])
        return [e1, e2]

    @discord.ui.button(label="🚫 Veto Match 1 Map", style=discord.ButtonStyle.danger, row=0)
    async def veto_m1_map(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m1_map" in self.vetoed:
            await interaction.response.send_message("⚠️ Match 1 map already vetoed.", ephemeral=True); return
        self.vetoed.add("m1_map")
        old = self.m1["name"]
        pool = [m for m in self.maps if m["name"] != self.m1["name"] and m["name"] != self.m2["name"]]
        self.m1 = random.choice(pool) if pool else self.m1
        button.disabled = True
        button.label    = f"✅ M1 Map Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → rerolled to **{self.m1['name']}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 1 Type", style=discord.ButtonStyle.danger, row=0)
    async def veto_m1_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m1_type" in self.vetoed:
            await interaction.response.send_message("⚠️ Match 1 gametype already vetoed.", ephemeral=True); return
        self.vetoed.add("m1_type")
        old = self.g1
        pool = [g for g in HALO3_GAMETYPES if g != self.g1]
        self.g1 = random.choice(pool) if pool else self.g1
        button.disabled = True
        button.label    = "✅ M1 Type Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → rerolled to **{self.g1}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 2 Map", style=discord.ButtonStyle.danger, row=1)
    async def veto_m2_map(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m2_map" in self.vetoed:
            await interaction.response.send_message("⚠️ Match 2 map already vetoed.", ephemeral=True); return
        self.vetoed.add("m2_map")
        old = self.m2["name"]
        pool = [m for m in self.maps if m["name"] != self.m1["name"] and m["name"] != self.m2["name"]]
        self.m2 = random.choice(pool) if pool else self.m2
        button.disabled = True
        button.label    = "✅ M2 Map Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → rerolled to **{self.m2['name']}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 2 Type", style=discord.ButtonStyle.danger, row=1)
    async def veto_m2_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m2_type" in self.vetoed:
            await interaction.response.send_message("⚠️ Match 2 gametype already vetoed.", ephemeral=True); return
        self.vetoed.add("m2_type")
        old = self.g2
        pool = [g for g in HALO3_GAMETYPES if g != self.g2]
        self.g2 = random.choice(pool) if pool else self.g2
        button.disabled = True
        button.label    = "✅ M2 Type Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → rerolled to **{self.g2}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="✅ Lock In", style=discord.ButtonStyle.success, row=2)
    async def lock_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🔒 **Matches locked in! Good luck!**",
            embeds=self._build_embeds(), view=self)


@bot.tree.command(name="matchmaking", description="Roll Halo 3 maps, game types and teams for your night.")
async def matchmaking(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🎮 **Halo 3 Matchmaking**\nChoose a mode to get started:",
        view=MatchmakingMenuView(),
        ephemeral=True
    )


@bot.tree.command(name="help", description="List all available commands.")
async def help_command(interaction: discord.Interaction):
    is_admin_user = interaction.user.guild_permissions.administrator

    everyone_commands = [
        ("`/rank`",            "Check your own current rank, MMR and stats."),
        ("`/mmr [player]`",    "Full stats, rank history and session breakdown for any player."),
        ("`/leaderboard`",     "Full MMR leaderboard grouped by rank."),
        ("`/compare [p1] [p2]`","Side by side stat comparison between two players with winners highlighted."),
        ("`/rivals [p1] [p2]`","Head-to-head session history and win tally between two players."),
        ("`/stats`",           "Top performer in every stat category — MMR, K/D, Kills, Obj Time and more."),
        ("`/session [s] [p]`", "Stats for a specific player in a specific session e.g. `Session 1`."),
        ("`/matchmaking`",     "Roll Halo 3 maps, game types and teams — single or double match with veto system."),
    ]

    admin_commands = [
        ("`/teams`",           "Open the Team Builder — assign, randomise, balance and send teams."),
        ("`/sub [out] [in]`",  "Swap two players between active teams."),
        ("`/recall`",          "Move all voice members back to their mapped lobby channels."),
        ("`/set_lobby`",       "Map voice channels to lobby destinations for `/recall`."),
        ("`/import_mmr`",      "Upload a session Excel file to update all player MMR and history."),
        ("`/export`",          "Download the current MMR data as a JSON file backup."),
        ("`/presets`",         "View and load saved team lineup presets."),
        ("`/history`",         "Browse the last 10 team configurations."),
        ("`/sync`",            "Force re-sync slash commands if any are missing."),
    ]

    lines = ["📖 **Halo Night Bot — Command List**\n"]

    lines.append("**Everyone**")
    for cmd, desc in everyone_commands:
        lines.append(f"> {cmd} — {desc}")

    if is_admin_user:
        lines.append("\n**Admin Only**")
        for cmd, desc in admin_commands:
            lines.append(f"> {cmd} — {desc}")
    else:
        lines.append("\n_Admin commands are hidden. Ask a server admin for help with team management._")

    await send_minimal(interaction, "\n".join(lines), ephemeral=True)


@bot.tree.command(name="sync", description="[Admin] Force sync slash commands if they are missing.")
@is_admin()
async def sync_commands(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    await bot.tree.sync()
    await bot.tree.sync(guild=interaction.guild)
    await interaction.followup.send("✅ Commands synced! New commands should appear within 30 seconds.", ephemeral=True)

@sync_commands.error
async def sync_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await send_minimal(interaction, "❌ Administrator permissions required.")
    else:
        raise error

@bot.event
async def on_ready():
    await bot.tree.sync()
    # Also sync to each guild for instant availability
    for guild in bot.guilds:
        try:
            await bot.tree.sync(guild=guild)
        except Exception:
            pass
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"   Slash commands synced to {len(bot.guilds)} guild(s).")

if __name__ == "__main__":
    bot.run(TOKEN)
