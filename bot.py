import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import random
import io
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

LOBBY_MAP_FILE   = "lobby_map.json"
MMR_FILE         = "mmr_data.json"
PRESETS_FILE     = "presets.json"
TEAM_HISTORY_FILE = "team_history.json"

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
# UNSC RANK SYSTEM
# ─────────────────────────────────────────────

UNSC_RANKS = [
    (95, "Spartan",    "⭐"),
    (88, "Inheritor",  "🔱"),
    (80, "Reclaimer",  "💠"),
    (72, "Forerunner", "🔷"),
    (63, "Legendary",  "🟣"),
    (54, "Mythic",     "🟤"),
    (45, "Onyx",       "⬛"),
    (36, "Diamond",    "💎"),
    (27, "Platinum",   "🩶"),
    (18, "Gold",       "🥇"),
    (10, "Silver",     "🩵"),
    (0,  "Bronze",     "🟫"),
]

def unsc_rank(mmr: float) -> tuple[str, str]:
    for threshold, name, emoji in UNSC_RANKS:
        if mmr >= threshold:
            return name, emoji
    return "Bronze", "🟫"

def mmr_rank_emoji(rank: int) -> str:
    if rank == 1: return "🥇"
    if rank == 2: return "🥈"
    if rank == 3: return "🥉"
    return f"`#{rank}`"

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

def get_guild_mmr(guild_id: int) -> dict:
    return mmr_data.get(str(guild_id), {})

def parse_session_sheet(ws) -> list:
    """Parse a session worksheet into a list of player stat dicts."""
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    players = []
    for row in rows[1:]:
        try:
            name = str(row[0]).strip() if row[0] else None
            if not name or name.lower() in ("none", ""):
                continue
            kd = 0.0
            try:
                kd = float(row[4] or 0)
            except (TypeError, ValueError):
                kd = 0.0
            players.append({
                "name":     name,
                "kd":       kd,
                "assists":  float(row[2] or 0),
                "captures": float(row[6] or 0),
                "obj_time": float(row[7] or 0),
                "points":   float(row[9] or 0),
            })
        except Exception:
            continue
    return players

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

    async def on_timeout(self):
        pass

async def send_minimal(interaction: discord.Interaction, content: str, ephemeral: bool = True):
    await interaction.response.send_message(content, view=DismissView(), ephemeral=ephemeral)

async def followup_minimal(interaction: discord.Interaction, content: str, ephemeral: bool = False):
    await interaction.followup.send(content, view=DismissView(), ephemeral=ephemeral)

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
        names, team_mmr_vals = [], []
        for mid in member_ids:
            m = guild.get_member(mid)
            dname = m.display_name if m else f"Unknown({mid})"
            pdata = gmmr.get(dname) or next(
                (v for v in gmmr.values() if v.get("discord_id") == mid), None
            )
            if pdata:
                rank_name, rank_emoji = unsc_rank(pdata["mmr"])
                names.append(f"{dname} {rank_emoji}({pdata['mmr']})")
                team_mmr_vals.append(pdata["mmr"])
            else:
                names.append(dname)
        avg = f" | avg MMR: {round(sum(team_mmr_vals)/len(team_mmr_vals), 1)}" if team_mmr_vals else ""
        lines.append(f"**{vc.name if vc else vc_id}** ({len(names)}){avg}\n> {', '.join(names)}")
    return "\n".join(lines)

def save_team_to_history(guild_id: int, guild: discord.Guild, label: str = None):
    """Save current team_storage snapshot to team history (max 10 entries)."""
    gid = str(guild_id)
    if gid not in team_history:
        team_history[gid] = []
    teams = team_storage.get(guild_id, {})
    if not teams:
        return
    snapshot = {}
    for vc_id, member_ids in teams.items():
        vc = guild.get_channel(int(vc_id))
        vc_name = vc.name if vc else str(vc_id)
        names = []
        for mid in member_ids:
            m = guild.get_member(mid)
            names.append(m.display_name if m else str(mid))
        snapshot[vc_name] = names
    import datetime
    entry = {
        "label": label or datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
        "teams": snapshot
    }
    team_history[gid].insert(0, entry)
    team_history[gid] = team_history[gid][:10]  # keep last 10
    save_json(TEAM_HISTORY_FILE, team_history)

# ─────────────────────────────────────────────
# LOBBY MAPPING VIEWS
# ─────────────────────────────────────────────

class LobbyMappingView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.source_select = SourceChannelSelect(voice_channels)
        self.dest_select   = LobbyDestSelect(voice_channels)
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
        if gid not in lobby_map:
            lobby_map[gid] = {}
        dest_ch = self.guild.get_channel(int(dest_id))
        saved = []
        for src_id in source_ids:
            lobby_map[gid][src_id] = int(dest_id)
            src_ch = self.guild.get_channel(int(src_id))
            saved.append(src_ch.name if src_ch else src_id)
        save_json(LOBBY_MAP_FILE, lobby_map)
        await send_minimal(interaction, f"✅ **{', '.join(saved)}** → **{dest_ch.name if dest_ch else dest_id}**")

class SourceChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels):
        self.selected_ids: list = []
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in voice_channels[:25]]
        super().__init__(placeholder="1️⃣ Pick source channel(s) to recall FROM...", options=options,
                         min_values=1, max_values=min(len(voice_channels), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Source(s): **{', '.join(names)}**")

class LobbyDestSelect(discord.ui.Select):
    def __init__(self, voice_channels):
        self.selected_id = None
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in voice_channels[:25]]
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
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.channel_select = RandomChannelSelect(voice_channels)
        self.add_item(self.channel_select)

    @discord.ui.button(label="🎲 Randomise!", style=discord.ButtonStyle.success, row=1)
    async def randomise(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_vc_ids = self.channel_select.selected_ids
        if len(selected_vc_ids) < 2:
            await send_minimal(interaction, "⚠️ Pick at least 2 voice channels.")
            return
        all_voice_members = list({m.id: m for vc in self.guild.voice_channels for m in vc.members}.values())
        if not all_voice_members:
            await send_minimal(interaction, "⚠️ No members in any voice channel.")
            return
        random.shuffle(all_voice_members)
        buckets = {vc_id: [] for vc_id in selected_vc_ids}
        for i, m in enumerate(all_voice_members):
            buckets[selected_vc_ids[i % len(selected_vc_ids)]].append(m)
        gid = self.guild.id
        team_storage[gid] = {}
        results = []
        await interaction.response.defer()
        for vc_id, members in buckets.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            team_storage[gid][vc_id] = []
            moved, skipped = [], []
            for m in members:
                team_storage[gid][vc_id].append(m.id)
                if m.voice:
                    await m.move_to(vc)
                    moved.append(m.display_name)
                else:
                    skipped.append(m.display_name)
            line = f"**{vc.name}** ({len(moved)}): {', '.join(moved) if moved else 'nobody'}"
            if skipped: line += f" _(not in voice: {', '.join(skipped)})_"
            results.append(line)
        save_team_to_history(self.guild.id, self.guild, "🎲 Random")
        await followup_minimal(interaction, "🎲 **Teams randomised!**\n" + "\n".join(results), ephemeral=False)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class RandomChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels):
        self.selected_ids: list = []
        options = [
            discord.SelectOption(label=c.name, description=f"{len(c.members)} connected", value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(placeholder="Pick 2–25 voice channels to use as teams...", options=options,
                         min_values=2, max_values=min(len(voice_channels), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Teams: **{', '.join(names)}** — click 🎲 Randomise!")

# ─────────────────────────────────────────────
# MMR BALANCED MATCHMAKING VIEW
# ─────────────────────────────────────────────

class MatchmakeView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.channel_select = MatchmakeChannelSelect(voice_channels)
        self.add_item(self.channel_select)

    @discord.ui.button(label="⚖️ Generate Balanced Teams", style=discord.ButtonStyle.success, row=1)
    async def matchmake(self, interaction: discord.Interaction, button: discord.ui.Button):
        selected_vc_ids = self.channel_select.selected_ids
        if len(selected_vc_ids) < 2:
            await send_minimal(interaction, "⚠️ Pick at least 2 voice channels.")
            return
        all_voice_members = list({m.id: m for vc in self.guild.voice_channels for m in vc.members}.values())
        if not all_voice_members:
            await send_minimal(interaction, "⚠️ No members in any voice channel.")
            return
        gmmr = get_guild_mmr(self.guild.id)
        num_teams = len(selected_vc_ids)
        rated, unrated = [], []
        for m in all_voice_members:
            pdata = gmmr.get(m.display_name) or next(
                (v for v in gmmr.values() if v.get("discord_id") == m.id), None
            )
            if pdata:
                rated.append((m, pdata["mmr"]))
            else:
                unrated.append(m)
        rated.sort(key=lambda x: x[1], reverse=True)
        buckets = {vc_id: [] for vc_id in selected_vc_ids}
        direction, idx = 1, 0
        for member, mmr in rated:
            buckets[selected_vc_ids[idx]].append((member, mmr))
            idx += direction
            if idx >= num_teams:
                idx = num_teams - 1
                direction = -1
            elif idx < 0:
                idx = 0
                direction = 1
        random.shuffle(unrated)
        for i, m in enumerate(unrated):
            buckets[selected_vc_ids[i % num_teams]].append((m, None))
        gid = self.guild.id
        team_storage[gid] = {}
        results = []
        await interaction.response.defer()
        for vc_id, members in buckets.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            team_storage[gid][vc_id] = []
            moved, skipped, mmr_vals = [], [], []
            for m, mmr in members:
                team_storage[gid][vc_id].append(m.id)
                rank_name, rank_emoji = unsc_rank(mmr) if mmr is not None else ("?", "❔")
                label = f"{m.display_name}{rank_emoji}" if mmr is not None else f"{m.display_name}❔"
                if m.voice:
                    await m.move_to(vc)
                    moved.append(label)
                else:
                    skipped.append(label)
                if mmr is not None:
                    mmr_vals.append(mmr)
            avg = f" | avg MMR: {round(sum(mmr_vals)/len(mmr_vals),1)}" if mmr_vals else ""
            line = f"**{vc.name}**{avg}: {', '.join(moved) if moved else 'nobody'}"
            if skipped: line += f" _(not in voice: {', '.join(skipped)})_"
            results.append(line)
        save_team_to_history(self.guild.id, self.guild, "⚖️ Balanced")
        await followup_minimal(interaction, "⚖️ **Balanced teams generated!**\n" + "\n".join(results), ephemeral=False)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=1)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()

class MatchmakeChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels):
        self.selected_ids: list = []
        options = [
            discord.SelectOption(label=c.name, description=f"{len(c.members)} connected", value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(placeholder="Pick 2–25 voice channels to use as teams...", options=options,
                         min_values=2, max_values=min(len(voice_channels), 25), row=0)
    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await send_minimal(interaction, f"✅ Channels: **{', '.join(names)}** — click ⚖️ to generate!")

# ─────────────────────────────────────────────
# PRESET SAVE VIEW
# ─────────────────────────────────────────────

class SavePresetModal(discord.ui.Modal, title="Save Team Preset"):
    preset_name = discord.ui.TextInput(label="Preset Name", placeholder="e.g. Monday Night 6v6", max_length=50)
    preset_note = discord.ui.TextInput(label="Notes (optional)", placeholder="e.g. Competitive lineup, no subs",
                                       required=False, max_length=150, style=discord.TextStyle.paragraph)

    def __init__(self, guild: discord.Guild):
        super().__init__()
        self.guild = guild

    async def on_submit(self, interaction: discord.Interaction):
        gid = str(self.guild.id)
        teams = team_storage.get(self.guild.id, {})
        if not teams:
            await send_minimal(interaction, "⚠️ No active teams to save.")
            return
        if gid not in presets:
            presets[gid] = {}
        snapshot = {}
        for vc_id, member_ids in teams.items():
            vc = self.guild.get_channel(int(vc_id))
            vc_name = vc.name if vc else str(vc_id)
            names = []
            for mid in member_ids:
                m = self.guild.get_member(mid)
                names.append(m.display_name if m else str(mid))
            snapshot[vc_name] = names
        name = str(self.preset_name)
        presets[gid][name] = {
            "note":  str(self.preset_note) if self.preset_note.value else "",
            "teams": snapshot
        }
        save_json(PRESETS_FILE, presets)
        await send_minimal(interaction, f"✅ Preset **{name}** saved!")

# ─────────────────────────────────────────────
# LOAD PRESET VIEW
# ─────────────────────────────────────────────

class LoadPresetView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.guild = guild
        gid = str(guild.id)
        guild_presets = presets.get(gid, {})
        if guild_presets:
            self.add_item(PresetSelect(guild_presets, guild))

class PresetSelect(discord.ui.Select):
    def __init__(self, guild_presets: dict, guild: discord.Guild):
        self.guild = guild
        options = [
            discord.SelectOption(
                label=name,
                description=data.get("note", "")[:50] or "No notes",
                value=name
            )
            for name, data in list(guild_presets.items())[:25]
        ]
        super().__init__(placeholder="Choose a preset to load...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        gid = str(self.guild.id)
        preset_name = self.values[0]
        preset = presets.get(gid, {}).get(preset_name)
        if not preset:
            await send_minimal(interaction, f"⚠️ Preset **{preset_name}** not found.")
            return
        lines = [f"📋 **{preset_name}**"]
        if preset.get("note"):
            lines.append(f"_{preset['note']}_")
        lines.append("")
        for vc_name, members in preset["teams"].items():
            lines.append(f"**{vc_name}**: {', '.join(members)}")
        lines.append("\n_Teams shown above are from the saved preset. Use /teams to send players._")
        await send_minimal(interaction, "\n".join(lines))

# ─────────────────────────────────────────────
# TEAM HISTORY VIEW
# ─────────────────────────────────────────────

class TeamHistoryView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        self.guild = guild
        gid = str(guild.id)
        history = team_history.get(gid, [])
        if history:
            self.add_item(TeamHistorySelect(history))

class TeamHistorySelect(discord.ui.Select):
    def __init__(self, history: list):
        options = [
            discord.SelectOption(label=entry["label"][:50], value=str(i))
            for i, entry in enumerate(history[:25])
        ]
        super().__init__(placeholder="Choose a past team configuration...", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        idx = int(self.values[0])
        history = team_history.get(gid, [])
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
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild
        all_voice_members = list({m.id: m for vc in guild.voice_channels for m in vc.members}.values())
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.member_select  = TeamMemberSelect(all_voice_members)
        self.channel_select = TeamChannelSelect(voice_channels)
        self.add_item(self.member_select)
        self.add_item(self.channel_select)

    @discord.ui.button(label="➕ Assign to Team", style=discord.ButtonStyle.primary, row=2)
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild.id
        chosen_members = self.member_select.selected_members
        chosen_vc_id   = self.channel_select.selected_vc_id
        if not chosen_members:
            await send_minimal(interaction, "⚠️ Select members first.")
            return
        if not chosen_vc_id:
            await send_minimal(interaction, "⚠️ Select a channel first.")
            return
        if gid not in team_storage: team_storage[gid] = {}
        if chosen_vc_id not in team_storage[gid]: team_storage[gid][chosen_vc_id] = []
        added, moved_from = [], []
        for m in chosen_members:
            if not m: continue
            prev = find_member_team(gid, m.id)
            if prev and prev != chosen_vc_id:
                team_storage[gid][prev].remove(m.id)
                prev_vc = self.guild.get_channel(int(prev))
                moved_from.append(f"{m.display_name} (was in {prev_vc.name if prev_vc else prev})")
            if m.id not in team_storage[gid][chosen_vc_id]:
                team_storage[gid][chosen_vc_id].append(m.id)
                added.append(m.display_name)
        vc  = self.guild.get_channel(int(chosen_vc_id))
        msg = f"✅ **{vc.name if vc else chosen_vc_id}**: {', '.join(added)}"
        if moved_from: msg += f"\n🔄 {', '.join(moved_from)}"
        msg += f"\n\n{build_team_summary(self.guild, gid)}"
        await send_minimal(interaction, msg)

    @discord.ui.button(label="🚀 Send Teams", style=discord.ButtonStyle.success, row=2)
    async def send_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid   = self.guild.id
        teams = team_storage.get(gid, {})
        if not teams:
            await send_minimal(interaction, "⚠️ No teams assigned yet.")
            return
        results = []
        for vc_id, member_ids in teams.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc: continue
            moved, skipped = [], []
            for mid in member_ids:
                m = self.guild.get_member(mid)
                if m and m.voice:
                    await m.move_to(vc)
                    moved.append(m.display_name)
                elif m:
                    skipped.append(m.display_name)
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
        await interaction.response.send_message(
            "🎲 **Randomise Teams**\nPick channels — all players in voice will be shuffled evenly.",
            view=RandomiseView(self.guild), ephemeral=True
        )

    @discord.ui.button(label="⚖️ Balanced Teams", style=discord.ButtonStyle.primary, row=3)
    async def balanced_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            "⚖️ **MMR Balanced Teams**\nPlayers distributed by UNSC rank using a snake draft.",
            view=MatchmakeView(self.guild), ephemeral=True
        )

    @discord.ui.button(label="💾 Save Preset", style=discord.ButtonStyle.secondary, row=3)
    async def save_preset(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(SavePresetModal(self.guild))

    @discord.ui.button(label="🗑️ Clear Teams", style=discord.ButtonStyle.danger, row=4)
    async def clear_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_storage.pop(self.guild.id, None)
        await send_minimal(interaction, "✅ Teams cleared.")

    @discord.ui.button(label="🔁 Recall All to Lobby", style=discord.ButtonStyle.secondary, row=4)
    async def recall_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = self.guild
        gmap  = get_guild_lobby_map(guild.id)
        if not gmap:
            await send_minimal(interaction, "⚠️ No lobby mappings set. Use `/set_lobby` first.")
            return
        await interaction.response.defer()
        moved_total = 0
        for vc_id_str, lobby_id in gmap.items():
            vc    = guild.get_channel(int(vc_id_str))
            lobby = guild.get_channel(int(lobby_id))
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
        super().__init__(placeholder="1️⃣ Pick member(s)...", options=options,
                         min_values=1, max_values=max_vals, row=0)
    async def callback(self, interaction: discord.Interaction):
        if self.values == ["none"]:
            await send_minimal(interaction, "⚠️ No members in voice channels.")
            return
        self.selected_members = [interaction.guild.get_member(int(uid)) for uid in self.values]
        names = ", ".join(m.display_name for m in self.selected_members if m)
        await send_minimal(interaction, f"✅ Selected: **{names}**")

class TeamChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels):
        self.selected_vc_id = None
        options = [discord.SelectOption(label=c.name, value=str(c.id)) for c in voice_channels[:25]]
        super().__init__(placeholder="2️⃣ Pick their team channel...", options=options,
                         min_values=1, max_values=1, row=1)
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
    guild = interaction.guild
    gmap  = get_guild_lobby_map(guild.id)
    if not gmap:
        await send_minimal(interaction, "⚠️ No lobby mappings configured. Use `/set_lobby` first.")
        return
    await interaction.response.defer()
    moved_total = 0
    for vc_id_str, lobby_id in gmap.items():
        vc    = guild.get_channel(int(vc_id_str))
        lobby = guild.get_channel(int(lobby_id))
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
        view=LobbyMappingView(interaction.guild), ephemeral=True
    )


@bot.tree.command(name="teams", description="[Admin] Build teams and send members to voice channels.")
@is_admin()
async def teams(interaction: discord.Interaction):
    if not [c for c in interaction.guild.channels if isinstance(c, discord.VoiceChannel)]:
        await send_minimal(interaction, "⚠️ No voice channels found.")
        return
    await interaction.response.send_message(
        "👥 **Team Builder**\n"
        "1️⃣ Pick members → 2️⃣ Pick channel → ➕ Assign → Repeat → 🚀 Send!\n"
        "🎲 Randomise or ⚖️ Balanced for automatic generation | 💾 Save Preset to store this lineup\n"
        "Use 🔁 to recall everyone back between rounds.",
        view=TeamBuilderView(interaction.guild), ephemeral=True
    )


@bot.tree.command(name="import_mmr", description="[Admin] Import player stats from your session Excel file.")
@is_admin()
async def import_mmr(interaction: discord.Interaction, file: discord.Attachment):
    if not file.filename.endswith((".xlsx", ".csv")):
        await send_minimal(interaction, "⚠️ Please upload a `.xlsx` or `.csv` file.")
        return
    await interaction.response.defer(ephemeral=True)
    try:
        data = await file.read()
        import openpyxl

        wb = openpyxl.load_workbook(io.BytesIO(data))
        gid = str(interaction.guild_id)
        if gid not in mmr_data:
            mmr_data[gid] = {}

        session_sheets = [s for s in wb.sheetnames if s.lower() not in ("leaderboard", "collective stats")]
        all_imported = []

        for sheet_name in session_sheets:
            ws = wb[sheet_name]
            players = parse_session_sheet(ws)
            if not players:
                continue
            players = calculate_mmr(players)

            for p in players:
                name = p["name"]
                if name not in mmr_data[gid]:
                    mmr_data[gid][name] = {"history": []}
                # Avoid duplicate session entries
                existing_sessions = [h["session"] for h in mmr_data[gid][name].get("history", [])]
                if sheet_name not in existing_sessions:
                    mmr_data[gid][name].setdefault("history", []).append({
                        "session": sheet_name,
                        "mmr":     p["mmr"],
                        "kd":      p["kd"],
                        "points":  p["points"],
                    })
                # Always update current stats to latest session
                mmr_data[gid][name].update({
                    "mmr":      p["mmr"],
                    "kd":       p["kd"],
                    "points":   p["points"],
                    "obj_time": p["obj_time"],
                    "assists":  p["assists"],
                    "captures": p["captures"],
                })
            all_imported.extend(players)

        # If it's the leaderboard format (single sheet), fall back to that
        if not all_imported and "Leaderboard" in wb.sheetnames:
            ws = wb["Leaderboard"]
            rows = list(ws.iter_rows(values_only=True))
            header = [str(h).strip().lower() if h else "" for h in rows[0]]
            def col(n):
                return next((i for i, h in enumerate(header) if n in h), None)
            idx = {"name": col("player name") or col("name"), "kd": col("k/d"),
                   "points": col("total points"), "obj_time": col("time in obj"),
                   "assists": col("total assists"), "captures": col("captures")}
            players = []
            for row in rows[1:]:
                try:
                    name = str(row[idx["name"]]).strip() if row[idx["name"]] else None
                    if not name or name.lower() == "none": continue
                    players.append({"name": name, "kd": float(row[idx["kd"]] or 0),
                                    "points": float(row[idx["points"]] or 0),
                                    "obj_time": float(row[idx["obj_time"]] or 0),
                                    "assists": float(row[idx["assists"]] or 0),
                                    "captures": float(row[idx["captures"]] or 0)})
                except: continue
            players = calculate_mmr(players)
            for p in players:
                mmr_data[gid][p["name"]] = {**mmr_data[gid].get(p["name"], {}), **p}
            all_imported = players

        save_json(MMR_FILE, mmr_data)

        # Build summary sorted by final MMR
        unique = {p["name"]: p for p in all_imported}
        sorted_players = sorted(unique.values(), key=lambda x: x["mmr"], reverse=True)
        lines = []
        for p in sorted_players:
            rank_name, rank_emoji = unsc_rank(p["mmr"])
            lines.append(f"{rank_emoji} **{p['name']}** — {p['mmr']} MMR | {rank_name}")

        await followup_minimal(
            interaction,
            f"✅ Imported **{len(sorted_players)}** players from **{len(session_sheets)}** session(s)!\n\n" + "\n".join(lines),
            ephemeral=True
        )
    except Exception as e:
        await followup_minimal(interaction, f"❌ Error reading file: {e}", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show the UNSC MMR leaderboard.")
async def leaderboard(interaction: discord.Interaction):
    gmmr = get_guild_mmr(interaction.guild_id)
    if not gmmr:
        await send_minimal(interaction, "⚠️ No MMR data yet. An admin needs to run `/import_mmr` first.")
        return
    sorted_players = sorted(gmmr.items(), key=lambda x: x[1].get("mmr", 0), reverse=True)
    lines = ["🏆 **UNSC MMR Leaderboard**\n"]
    for rank, (name, data) in enumerate(sorted_players, 1):
        mmr = data.get("mmr", 0)
        rank_name, rank_emoji = unsc_rank(mmr)
        pos = mmr_rank_emoji(rank)
        lines.append(f"{pos} {rank_emoji} **{name}** — {mmr} MMR | *{rank_name}*")
    await send_minimal(interaction, "\n".join(lines), ephemeral=False)


@bot.tree.command(name="mmr", description="Look up a player's MMR, UNSC rank, and rating history.")
async def mmr_lookup(interaction: discord.Interaction, player: str):
    gmmr  = get_guild_mmr(interaction.guild_id)
    match = next((v for k, v in gmmr.items() if k.lower() == player.lower()), None)
    name  = next((k for k in gmmr if k.lower() == player.lower()), player)
    if not match:
        await send_minimal(interaction, f"⚠️ No MMR data found for **{player}**.")
        return
    sorted_all  = sorted(gmmr.values(), key=lambda x: x.get("mmr", 0), reverse=True)
    rank_pos    = next((i+1 for i, p in enumerate(sorted_all) if p.get("mmr") == match.get("mmr")), "?")
    rank_name, rank_emoji = unsc_rank(match.get("mmr", 0))

    lines = [
        f"**{name}** {rank_emoji} *{rank_name}*",
        f"MMR: **{match.get('mmr', '?')}** | Rank: **#{rank_pos}**",
        f"K/D: {match.get('kd','?')} | Points: {match.get('points','?')} | "
        f"Obj Time: {match.get('obj_time','?')}s | Assists: {match.get('assists','?')} | Captures: {match.get('captures','?')}",
    ]

    # Rating history
    history = match.get("history", [])
    if history:
        lines.append("\n📈 **Rating History**")
        for i, h in enumerate(history):
            h_rank, h_emoji = unsc_rank(h["mmr"])
            # Trend arrow
            if i == 0:
                arrow = ""
            elif h["mmr"] > history[i-1]["mmr"]:
                arrow = " ▲"
            elif h["mmr"] < history[i-1]["mmr"]:
                arrow = " ▼"
            else:
                arrow = " ─"
            lines.append(f"> {h_emoji} **{h['session']}**: {h['mmr']} MMR (*{h_rank}*){arrow}")

    await send_minimal(interaction, "\n".join(lines), ephemeral=False)


@bot.tree.command(name="presets", description="[Admin] View and load saved team presets.")
@is_admin()
async def view_presets(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    guild_presets = presets.get(gid, {})
    if not guild_presets:
        await send_minimal(interaction, "⚠️ No presets saved yet. Use 💾 Save Preset in `/teams`.")
        return
    await interaction.response.send_message(
        "📋 **Saved Team Presets** — select one to view:",
        view=LoadPresetView(interaction.guild), ephemeral=True
    )


@bot.tree.command(name="history", description="[Admin] View past team configurations.")
@is_admin()
async def view_history(interaction: discord.Interaction):
    gid = str(interaction.guild_id)
    history = team_history.get(gid, [])
    if not history:
        await send_minimal(interaction, "⚠️ No team history yet. History is saved when you send or randomise teams.")
        return
    await interaction.response.send_message(
        "📜 **Team History** — select an entry to view:",
        view=TeamHistoryView(interaction.guild), ephemeral=True
    )

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
