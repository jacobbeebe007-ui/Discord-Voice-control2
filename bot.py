import discord
from discord.ext import commands
from discord import app_commands
import json
import os
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

LOBBY_MAP_FILE = "lobby_map.json"

def load_lobby_map():
    if os.path.exists(LOBBY_MAP_FILE):
        with open(LOBBY_MAP_FILE) as f:
            return json.load(f)
    return {}

def save_lobby_map(data):
    with open(LOBBY_MAP_FILE, "w") as f:
        json.dump(data, f, indent=2)

lobby_map: dict = load_lobby_map()

# In-memory team storage per guild: {guild_id: {vc_id: [member_ids]}}
team_storage: dict = {}

def get_guild_lobby_map(guild_id: int) -> dict:
    return lobby_map.get(str(guild_id), {})

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def find_member_team(guild_id: int, member_id: int):
    """Return the vc_id the member is currently assigned to, or None."""
    for vc_id, members in team_storage.get(guild_id, {}).items():
        if member_id in members:
            return vc_id
    return None

def build_team_summary(guild: discord.Guild, guild_id: int) -> str:
    teams = team_storage.get(guild_id, {})
    if not teams:
        return "No teams assigned yet."
    lines = []
    for vc_id, member_ids in teams.items():
        vc = guild.get_channel(int(vc_id))
        names = []
        for mid in member_ids:
            m = guild.get_member(mid)
            names.append(m.display_name if m else f"Unknown({mid})")
        lines.append(f"**{vc.name if vc else vc_id}** ({len(names)}): {', '.join(names) if names else 'empty'}")
    return "\n".join(lines)

# ─────────────────────────────────────────────
# LOBBY MAPPING VIEWS
# ─────────────────────────────────────────────

class LobbyMappingView(discord.ui.View):
    """
    Step 1: pick multiple source voice channels.
    Step 2: pick the single lobby destination.
    """
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=180)
        self.guild = guild
        self.selected_source_ids: list[str] = []
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.add_item(SourceChannelSelect(voice_channels, self))
        self.add_item(LobbyDestSelect(voice_channels, self))

    @discord.ui.button(label="💾 Save Mapping", style=discord.ButtonStyle.success, row=2)
    async def save(self, interaction: discord.Interaction, button: discord.ui.Button):
        source_ids = self.source_select.selected_ids
        dest_id = self.dest_select.selected_id

        if not source_ids:
            await interaction.response.send_message("⚠️ Select at least one source channel.", ephemeral=True)
            return
        if not dest_id:
            await interaction.response.send_message("⚠️ Select a lobby destination.", ephemeral=True)
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

        save_lobby_map(lobby_map)
        await interaction.response.send_message(
            f"✅ Mapped **{', '.join(saved)}** → **{dest_ch.name if dest_ch else dest_id}**",
            ephemeral=True
        )


class SourceChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels, parent_view: LobbyMappingView):
        self.parent_view = parent_view
        self.selected_ids: list[str] = []
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="1️⃣ Pick source channel(s) to recall FROM...",
            options=options,
            min_values=1,
            max_values=min(len(voice_channels), 25),
            row=0
        )
        parent_view.source_select = self

    async def callback(self, interaction: discord.Interaction):
        self.selected_ids = self.values
        names = [interaction.guild.get_channel(int(v)).name for v in self.values if interaction.guild.get_channel(int(v))]
        await interaction.response.send_message(
            f"✅ Source(s) selected: **{', '.join(names)}** — now pick the lobby destination.",
            ephemeral=True
        )


class LobbyDestSelect(discord.ui.Select):
    def __init__(self, voice_channels, parent_view: LobbyMappingView):
        self.parent_view = parent_view
        self.selected_id: str = None
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="2️⃣ Pick lobby destination (recall TO)...",
            options=options,
            min_values=1,
            max_values=1,
            row=1
        )
        parent_view.dest_select = self

    async def callback(self, interaction: discord.Interaction):
        self.selected_id = self.values[0]
        vc = interaction.guild.get_channel(int(self.selected_id))
        await interaction.response.send_message(
            f"✅ Destination set to **{vc.name}** — click 💾 Save Mapping to confirm.",
            ephemeral=True
        )

# ─────────────────────────────────────────────
# TEAM BUILDER
# ─────────────────────────────────────────────

class TeamBuilderView(discord.ui.View):
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=600)
        self.guild = guild

        all_voice_members = []
        for vc in guild.voice_channels:
            all_voice_members.extend(vc.members)
        all_voice_members = list({m.id: m for m in all_voice_members}.values())

        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]

        self.member_select = TeamMemberSelect(all_voice_members, self)
        self.channel_select = TeamChannelSelect(voice_channels, self)
        self.add_item(self.member_select)
        self.add_item(self.channel_select)

    @discord.ui.button(label="➕ Assign to Team", style=discord.ButtonStyle.primary, row=2)
    async def assign(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild.id
        chosen_members = self.member_select.selected_members
        chosen_vc_id = self.channel_select.selected_vc_id

        if not chosen_members:
            await interaction.response.send_message("⚠️ Select members first.", ephemeral=True)
            return
        if not chosen_vc_id:
            await interaction.response.send_message("⚠️ Select a channel first.", ephemeral=True)
            return

        if gid not in team_storage:
            team_storage[gid] = {}
        if chosen_vc_id not in team_storage[gid]:
            team_storage[gid][chosen_vc_id] = []

        added = []
        moved_from = []
        for m in chosen_members:
            if not m:
                continue
            # Remove from previous team if already assigned
            prev_vc_id = find_member_team(gid, m.id)
            if prev_vc_id and prev_vc_id != chosen_vc_id:
                team_storage[gid][prev_vc_id].remove(m.id)
                prev_vc = self.guild.get_channel(int(prev_vc_id))
                moved_from.append(f"{m.display_name} (was in {prev_vc.name if prev_vc else prev_vc_id})")
            # Add to new team
            if m.id not in team_storage[gid][chosen_vc_id]:
                team_storage[gid][chosen_vc_id].append(m.id)
                added.append(m.display_name)

        vc = self.guild.get_channel(int(chosen_vc_id))
        summary = build_team_summary(self.guild, gid)

        msg = f"✅ Assigned to **{vc.name if vc else chosen_vc_id}**: {', '.join(added)}"
        if moved_from:
            msg += f"\n🔄 Moved between teams: {', '.join(moved_from)}"
        msg += f"\n\n**Current Teams:**\n{summary}"

        await interaction.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="🚀 Send Teams", style=discord.ButtonStyle.success, row=2)
    async def send_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = self.guild.id
        teams = team_storage.get(gid, {})
        if not teams:
            await interaction.response.send_message("⚠️ No teams assigned yet.", ephemeral=True)
            return

        results = []
        for vc_id, member_ids in teams.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc:
                continue
            moved, skipped = [], []
            for mid in member_ids:
                m = self.guild.get_member(mid)
                if m and m.voice:
                    await m.move_to(vc)
                    moved.append(m.display_name)
                elif m:
                    skipped.append(m.display_name)
            line = f"**{vc.name}** ({len(moved)} moved): {', '.join(moved) if moved else 'nobody'}"
            if skipped:
                line += f" | not in voice: {', '.join(skipped)}"
            results.append(line)

        await interaction.response.send_message("🚀 **Teams dispatched!**\n" + "\n".join(results))

    @discord.ui.button(label="📋 Show Teams", style=discord.ButtonStyle.secondary, row=2)
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        summary = build_team_summary(self.guild, self.guild.id)
        await interaction.response.send_message(f"**Current Teams:**\n{summary}", ephemeral=True)

    @discord.ui.button(label="🗑️ Clear Teams", style=discord.ButtonStyle.danger, row=3)
    async def clear_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        team_storage.pop(self.guild.id, None)
        await interaction.response.send_message("✅ All teams cleared.", ephemeral=True)

    @discord.ui.button(label="🔁 Recall All to Lobby", style=discord.ButtonStyle.secondary, row=3)
    async def recall_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = self.guild
        gmap = get_guild_lobby_map(guild.id)
        if not gmap:
            await interaction.response.send_message(
                "⚠️ No lobby mappings set. Use `/set_lobby` first.", ephemeral=True
            )
            return
        moved_total = 0
        for vc_id_str, lobby_id in gmap.items():
            vc = guild.get_channel(int(vc_id_str))
            lobby = guild.get_channel(int(lobby_id))
            if not vc or not lobby:
                continue
            for member in list(vc.members):
                if member.voice and member.voice.channel == vc:
                    await member.move_to(lobby)
                    moved_total += 1
        await interaction.response.send_message(
            f"✅ Recalled **{moved_total}** member(s) to their lobbies."
        )


class TeamMemberSelect(discord.ui.Select):
    def __init__(self, members, parent_view):
        self.parent_view = parent_view
        self.selected_members = []
        if members:
            options = [
                discord.SelectOption(label=m.display_name, value=str(m.id))
                for m in members[:25]
            ]
            max_vals = min(len(members), 25)
        else:
            options = [discord.SelectOption(label="No members in voice", value="none")]
            max_vals = 1
        super().__init__(
            placeholder="1️⃣ Pick member(s) (up to 8 per team)...",
            options=options,
            min_values=1,
            max_values=max_vals,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        if self.values == ["none"]:
            await interaction.response.send_message("No members in voice channels.", ephemeral=True)
            return
        self.selected_members = [interaction.guild.get_member(int(uid)) for uid in self.values]
        names = ", ".join(m.display_name for m in self.selected_members if m)
        await interaction.response.send_message(
            f"✅ Selected: **{names}** — now pick their channel and click ➕ Assign.",
            ephemeral=True
        )


class TeamChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels, parent_view):
        self.parent_view = parent_view
        self.selected_vc_id = None
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="2️⃣ Pick their team channel...",
            options=options,
            min_values=1,
            max_values=1,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.selected_vc_id = self.values[0]
        vc = interaction.guild.get_channel(int(self.selected_vc_id))
        await interaction.response.send_message(
            f"✅ Channel set to **{vc.name}** — click ➕ Assign to confirm.",
            ephemeral=True
        )

# ─────────────────────────────────────────────
# SLASH COMMANDS
# ─────────────────────────────────────────────

@bot.tree.command(name="recall", description="[Admin] Move all voice members to their mapped lobby.")
@is_admin()
async def recall(interaction: discord.Interaction):
    guild = interaction.guild
    gmap = get_guild_lobby_map(guild.id)
    if not gmap:
        await interaction.response.send_message(
            "⚠️ No lobby mappings configured. Use `/set_lobby` first.", ephemeral=True
        )
        return
    await interaction.response.defer()
    moved_total = 0
    for vc_id_str, lobby_id in gmap.items():
        vc = guild.get_channel(int(vc_id_str))
        lobby = guild.get_channel(int(lobby_id))
        if not vc or not lobby:
            continue
        for member in list(vc.members):
            if member.voice and member.voice.channel == vc:
                await member.move_to(lobby)
                moved_total += 1
    await interaction.followup.send(f"✅ Recalled **{moved_total}** member(s) to their lobbies.")


@bot.tree.command(name="set_lobby", description="[Admin] Map voice channel(s) to a lobby destination.")
@is_admin()
async def set_lobby(interaction: discord.Interaction):
    view = LobbyMappingView(interaction.guild)
    await interaction.response.send_message(
        "🔧 **Lobby Mapper**\n"
        "1️⃣ Pick one or more source channels → 2️⃣ Pick the lobby destination → 💾 Save\n"
        "You can run this command multiple times to set up different lobby destinations.",
        view=view, ephemeral=True
    )


@bot.tree.command(name="teams", description="[Admin] Build teams and send members to voice channels.")
@is_admin()
async def teams(interaction: discord.Interaction):
    guild = interaction.guild
    voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
    if not voice_channels:
        await interaction.response.send_message("⚠️ No voice channels found.", ephemeral=True)
        return

    view = TeamBuilderView(guild)
    await interaction.response.send_message(
        "👥 **Team Builder**\n"
        "1️⃣ Pick members → 2️⃣ Pick channel → ➕ Assign → Repeat → 🚀 Send!\n"
        "Players can only be on one team — reassigning moves them automatically.\n"
        "Use 🔁 Recall to pull everyone back to lobby between rounds.",
        view=view,
        ephemeral=True
    )


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@recall.error
@set_lobby.error
@teams.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ Administrator permissions required.", ephemeral=True)
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
