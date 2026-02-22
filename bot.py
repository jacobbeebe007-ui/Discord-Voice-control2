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
# EMOJI HELPERS
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
    """Look up a custom emoji by name from the guild. Falls back to :name:."""
    if guild:
        e = discord.utils.get(guild.emojis, name=name)
        if e:
            return str(e)
    return f":{name}:"

def halo_rank(mmr: float) -> tuple:
    """Returns (rank_name, emoji_name)."""
    for threshold, name, ename in HALO_RANKS:
        if mmr >= threshold:
            return name, ename
    return "Recruit", "000_Recruit"

def rank_display(mmr: float, guild: discord.Guild, provisional: bool = False) -> str:
    """Full rank string: emoji + name + optional provisional marker."""
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
                "kd": kd, "assists": float(row[2] or 0),
                "captures": float(row[6] or 0), "obj_time": float(row[7] or 0),
                "points": float(row[9] or 0),
            })
        except: continue
    return players

def parse_leaderboard_sheet(ws) -> list:
    """Parse the cumulative Leaderboard sheet for overall MMR."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows: return []
    players = []
    for row in rows[1:]:
        try:
            name = str(row[1]).strip() if row[1] else None
            if not name or name.lower() == "none": continue
            players.append({
                "name":     name,
                "kd":       float(row[6] or 0),
                "assists":  float(row[4] or 0),
                "captures": float(row[8] or 0),
                "obj_time": float(row[7] or 0),
                "points":   float(row[9] or 0),
                "sessions": int(row[10] or 1),
            })
        except: continue
    return players

def get_guild_mmr(guild_id: int) -> dict:
    return mmr_data.get(str(guild_id), {})

# ─────────────────────────────────────────────
# DISMISSIBLE VIEW
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
                    label = f"{m.display_name}{rd}"
                    mmr_vals.append(mmr)
                else:
                    label = f"{m.display_name}❔"
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
        vcs_by_name = {vc.name: vc for vc in self.guild.voice_channels}
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

        # Build session history per player
        per_player: dict = {}
        for sheet_name in session_sheets:
            players = parse_session_sheet(wb[sheet_name])
            if not players: continue
            players = calculate_mmr(players)
            # Assign session rank (1 = best in that session)
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
                    "points":       p["points"],
                    "session_rank": session_ranks.get(p["name"], "?"),
                    "session_size": session_size,
                })

        # Compute overall MMR from Leaderboard sheet (cumulative stats)
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

        # Merge everything into mmr_data
        all_names = set(per_player.keys()) | set(overall_mmr.keys())
        imported = []
        for cname in all_names:
            existing  = mmr_data[gid].get(cname, {})
            sessions_list = per_player.get(cname, [])
            lb = overall_mmr.get(cname) or next(
                (v for k, v in overall_mmr.items() if k.lower() == cname.lower()), None
            )
            # Build merged history
            existing_sessions = [h["session"] for h in existing.get("history", [])]
            new_history = existing.get("history", [])
            for s in sessions_list:
                if s["session"] not in existing_sessions:
                    new_history.append({
                        "session":      s["session"],
                        "mmr":          s["mmr"],
                        "kd":           s["kd"],
                        "points":       s["points"],
                        "session_rank": s.get("session_rank", "?"),
                        "session_size": s.get("session_size", "?"),
                    })

            # Overall MMR: from Leaderboard sheet if available, else average sessions
            if lb:
                overall = lb["mmr"]
                kd, points, obj_time, assists, captures = lb["kd"], lb["points"], lb["obj_time"], lb["assists"], lb["captures"]
                session_count = lb["sessions"]
            elif sessions_list:
                overall = round(sum(s["mmr"] for s in sessions_list) / len(sessions_list), 1)
                last = sessions_list[-1]
                kd, points = last["kd"], last["points"]
                obj_time, assists, captures = 0, 0, 0
                session_count = len(sessions_list)
            else:
                continue

            mmr_data[gid][cname] = {
                "mmr": overall, "kd": kd, "points": points,
                "obj_time": obj_time, "assists": assists, "captures": captures,
                "sessions": session_count, "history": new_history,
            }
            imported.append((cname, overall, session_count))

        save_json(MMR_FILE, mmr_data)
        imported.sort(key=lambda x: x[1], reverse=True)

        lines = []
        for cname, mmr, sessions in imported:
            rname, ename = halo_rank(mmr)
            remoji = get_emoji(interaction.guild, ename)
            prov   = " *" if sessions < PROVISIONAL_SESSIONS else ""
            lines.append(f"{remoji} **{cname}** — {mmr} MMR | *{rname}*{prov}")

        await followup_chunked(
            interaction, lines,
            header=f"✅ Imported **{len(imported)}** players!\n",
            ephemeral=True
        )
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

    # Group players under rank banners
    rank_groups: OrderedDict = OrderedDict()
    for pos, (name, data) in enumerate(sorted_players, 1):
        mmr      = data.get("mmr", 0)
        sessions = data.get("sessions", 0)
        rname, ename = halo_rank(mmr)
        prov   = " *" if sessions < PROVISIONAL_SESSIONS else ""
        entry  = f"  `#{pos}` **{name}** — {mmr} MMR{prov}"
        if rname not in rank_groups:
            rank_groups[rname] = {"ename": ename, "entries": []}
        rank_groups[rname]["entries"].append(entry)

    # Build message lines
    lines = []
    for rname, group in rank_groups.items():
        remoji = get_emoji(interaction.guild, group["ename"])
        lines.append(f"{remoji} **{rname}**")
        lines.extend(group["entries"])

    await followup_chunked(interaction, lines, header="🏆 **Halo Night MMR Leaderboard**\n", ephemeral=False)


@bot.tree.command(name="mmr", description="Look up a player's MMR, rank, and session history.")
async def mmr_lookup(interaction: discord.Interaction, player: str):
    gmmr  = get_guild_mmr(interaction.guild_id)
    match = next((v for k, v in gmmr.items() if k.lower() == player.lower()), None)
    name  = next((k for k in gmmr if k.lower() == player.lower()), player)
    if not match:
        await send_minimal(interaction, f"⚠️ No MMR data found for **{player}**.\nTip: use just the first name e.g. `Jacob`")
        return
    await interaction.response.defer()
    sorted_all = sorted(gmmr.values(), key=lambda x: x.get("mmr", 0), reverse=True)
    rank_pos   = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == match.get("mmr")), "?")
    mmr        = match.get("mmr", 0)
    sessions   = match.get("sessions", 0)
    rname, ename = halo_rank(mmr)
    remoji     = get_emoji(interaction.guild, ename)
    prov       = " *" if sessions < PROVISIONAL_SESSIONS else ""

    sessions_needed = PROVISIONAL_SESSIONS - sessions
    prov_note = f"\n_* Provisional rank — needs {sessions_needed} more session(s) to be confirmed._" if sessions < PROVISIONAL_SESSIONS else ""
    total_players = len(gmmr)
    lines = [
        f"**{name}** {remoji} *{rname}* — Rank **#{rank_pos} / {total_players}**{prov}{prov_note}",
        f"Overall MMR: **{mmr}** | Sessions: **{sessions}**",
        f"K/D: {match.get('kd','?')} | Points: {match.get('points','?')} | "
        f"Obj Time: {match.get('obj_time','?')}s | Assists: {match.get('assists','?')} | Captures: {match.get('captures','?')}",
    ]
    history = match.get("history", [])
    if history:
        lines.append("\n📈 **Session Breakdown**")
        prev_mmr = None
        for h in history:
            h_rname, h_ename = halo_rank(h["mmr"])
            h_remoji = get_emoji(interaction.guild, h_ename)
            arrow = "" if prev_mmr is None else (" ▲" if h["mmr"] > prev_mmr else " ▼" if h["mmr"] < prev_mmr else " ─")
            s_rank = h.get("session_rank", "?")
            s_size = h.get("session_size", "?")
            lines.append(f"> {h_remoji} *{h_rname}* | **{h['session']}**: {h['mmr']} MMR — #{s_rank}/{s_size}{arrow}")
            prev_mmr = h["mmr"]

    await followup_chunked(interaction, lines, ephemeral=False)


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
@import_mmr.error
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

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print("   Slash commands synced.")

if __name__ == "__main__":
    bot.run(TOKEN)
