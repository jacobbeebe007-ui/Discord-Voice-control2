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
TOKEN =MTQ3NDczMjc0Mzg5OTM0OTA3NA.GxMVxj.woHNeoac7DIaoAfXeOqlll-GO7cDDh6_qRNTu8
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN is not set in your environment or .env file.")

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Persistent storage: {guild_id: {voice_channel_id: lobby_channel_id}}
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

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_guild_lobby_map(guild_id: int) -> dict:
    return lobby_map.get(str(guild_id), {})

def is_admin():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ─────────────────────────────────────────────
# VIEWS
# ─────────────────────────────────────────────

class LobbyMappingView(discord.ui.View):
    """Admin view to map each voice channel to a lobby channel."""
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=120)
        self.guild = guild
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.add_item(ChannelMappingSelect(voice_channels, guild))


class ChannelMappingSelect(discord.ui.Select):
    def __init__(self, voice_channels, guild):
        self.guild = guild
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="Select a voice channel to configure...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        vc_id = self.values[0]
        vc = self.guild.get_channel(int(vc_id))
        view = LobbyPickerView(self.guild, vc)
        await interaction.response.send_message(
            f"Select the **lobby channel** that `{vc.name}` members should be moved to:",
            view=view, ephemeral=True
        )


class LobbyPickerView(discord.ui.View):
    def __init__(self, guild: discord.Guild, source_vc: discord.VoiceChannel):
        super().__init__(timeout=60)
        self.guild = guild
        self.source_vc = source_vc
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.add_item(LobbyPickerSelect(voice_channels, guild, source_vc))


class LobbyPickerSelect(discord.ui.Select):
    def __init__(self, voice_channels, guild, source_vc):
        self.guild = guild
        self.source_vc = source_vc
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="Select lobby/destination channel...",
            options=options,
            min_values=1,
            max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        lobby_id = self.values[0]
        lobby_ch = self.guild.get_channel(int(lobby_id))
        gid = str(self.guild.id)
        if gid not in lobby_map:
            lobby_map[gid] = {}
        lobby_map[gid][str(self.source_vc.id)] = int(lobby_id)
        save_lobby_map(lobby_map)
        await interaction.response.send_message(
            f"✅ Members in `{self.source_vc.name}` will be moved to `{lobby_ch.name}` when recalled.",
            ephemeral=True
        )


class VoiceJoinView(discord.ui.View):
    """Lets any user pick a voice channel to join."""
    def __init__(self, guild: discord.Guild):
        super().__init__(timeout=60)
        voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
        self.add_item(VoiceJoinSelect(voice_channels, guild))


class VoiceJoinSelect(discord.ui.Select):
    def __init__(self, voice_channels, guild):
        self.guild = guild
        options = [
            discord.SelectOption(
                label=f"#{c.name}",
                description=f"{len(c.members)} member(s) connected",
                value=str(c.id)
            )
            for c in voice_channels[:25]
        ]
        super().__init__(placeholder="Pick a voice channel...", options=options)

    async def callback(self, interaction: discord.Interaction):
        vc = self.guild.get_channel(int(self.values[0]))
        member = interaction.guild.get_member(interaction.user.id)
        if member and member.voice:
            await member.move_to(vc)
            await interaction.response.send_message(f"✅ Moved you to **{vc.name}**!", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"⚠️ You must already be in a voice channel for me to move you.\n"
                f"Join any voice channel first, then use `/joinvc` again.",
                ephemeral=True
            )


class TeamBuilderView(discord.ui.View):
    """Admin view: assign members to teams and send them to corresponding voice channels."""

    def __init__(self, guild: discord.Guild, members: list, voice_channels: list):
        super().__init__(timeout=300)
        self.guild = guild
        self.voice_channels = voice_channels
        self.teams: dict = {}
        self.add_item(TeamMemberSelect(members, self))
        self.add_item(TeamChannelSelect(voice_channels, self))

    @discord.ui.button(label="🚀 Send Teams to Channels", style=discord.ButtonStyle.success, row=2)
    async def send_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.teams:
            await interaction.response.send_message("⚠️ No teams assigned yet.", ephemeral=True)
            return
        results = []
        for vc_id, members in self.teams.items():
            vc = self.guild.get_channel(int(vc_id))
            if not vc:
                continue
            moved = []
            for m in members:
                if m.voice:
                    await m.move_to(vc)
                    moved.append(m.display_name)
            results.append(f"**{vc.name}**: {', '.join(moved) if moved else 'nobody was in voice'}")
        summary = "\n".join(results)
        await interaction.response.send_message(f"✅ Teams dispatched!\n{summary}")

    @discord.ui.button(label="🗑️ Clear Teams", style=discord.ButtonStyle.danger, row=2)
    async def clear_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.teams.clear()
        await interaction.response.send_message("Teams cleared.", ephemeral=True)

    @discord.ui.button(label="📋 Show Teams", style=discord.ButtonStyle.secondary, row=2)
    async def show_teams(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.teams:
            await interaction.response.send_message("No teams set up yet.", ephemeral=True)
            return
        lines = []
        for vc_id, members in self.teams.items():
            vc = self.guild.get_channel(int(vc_id))
            names = ", ".join(m.display_name for m in members)
            lines.append(f"**{vc.name if vc else vc_id}**: {names or 'empty'}")
        await interaction.response.send_message("\n".join(lines), ephemeral=True)


class TeamMemberSelect(discord.ui.Select):
    def __init__(self, members, parent_view):
        self.parent_view = parent_view
        self.selected_members = []
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in members[:25]
        ]
        super().__init__(
            placeholder="1️⃣ Select member(s) for a team...",
            options=options,
            min_values=1,
            max_values=min(len(members), 10),
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        self.selected_members = [
            interaction.guild.get_member(int(uid)) for uid in self.values
        ]
        names = ", ".join(m.display_name for m in self.selected_members if m)
        await interaction.response.send_message(
            f"Selected: **{names}** — now pick their voice channel below.",
            ephemeral=True
        )


class TeamChannelSelect(discord.ui.Select):
    def __init__(self, voice_channels, parent_view):
        self.parent_view = parent_view
        options = [
            discord.SelectOption(label=c.name, value=str(c.id))
            for c in voice_channels[:25]
        ]
        super().__init__(
            placeholder="2️⃣ Assign selected members to this channel...",
            options=options,
            min_values=1,
            max_values=1,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        vc_id = self.values[0]
        vc = interaction.guild.get_channel(int(vc_id))
        member_select = self.parent_view.children[0]
        chosen = member_select.selected_members
        if not chosen:
            await interaction.response.send_message("⚠️ Select members first!", ephemeral=True)
            return
        if vc_id not in self.parent_view.teams:
            self.parent_view.teams[vc_id] = []
        for m in chosen:
            if m and m not in self.parent_view.teams[vc_id]:
                self.parent_view.teams[vc_id].append(m)
        names = ", ".join(m.display_name for m in chosen if m)
        await interaction.response.send_message(
            f"✅ Added **{names}** → **{vc.name}**\nUse 📋 Show Teams to review, then 🚀 to send!",
            ephemeral=True
        )


# ─────────────────────────────────────────────
# SLASH COMMANDS
# ─────────────────────────────────────────────

@bot.tree.command(name="recall", description="[Admin] Move all voice channel members to their mapped lobby.")
@is_admin()
async def recall(interaction: discord.Interaction):
    guild = interaction.guild
    gmap = get_guild_lobby_map(guild.id)

    if not gmap:
        await interaction.response.send_message(
            "⚠️ No lobby mappings configured. Use `/set_lobby` first.", ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=False)
    moved_total = 0
    errors = []

    for vc_id_str, lobby_id in gmap.items():
        vc = guild.get_channel(int(vc_id_str))
        lobby = guild.get_channel(int(lobby_id))
        if not vc or not lobby:
            continue
        for member in list(vc.members):
            if member.voice and member.voice.channel == vc:
                try:
                    await member.move_to(lobby)
                    moved_total += 1
                except Exception as e:
                    errors.append(f"{member.display_name}: {e}")

    msg = f"✅ Recalled **{moved_total}** member(s) to their lobby channels."
    if errors:
        msg += f"\n⚠️ Errors: {', '.join(errors)}"
    await interaction.followup.send(msg)


@bot.tree.command(name="set_lobby", description="[Admin] Configure which lobby each voice channel maps to.")
@is_admin()
async def set_lobby(interaction: discord.Interaction):
    view = LobbyMappingView(interaction.guild)
    await interaction.response.send_message(
        "🔧 **Lobby Mapper** — Select a voice channel, then pick where its members go on `/recall`:",
        view=view, ephemeral=True
    )


@bot.tree.command(name="joinvc", description="Pick a voice channel to be moved to.")
async def joinvc(interaction: discord.Interaction):
    view = VoiceJoinView(interaction.guild)
    await interaction.response.send_message(
        "🎙️ **Voice Channel Selector** — Choose a channel below:",
        view=view, ephemeral=True
    )


@bot.tree.command(name="teams", description="[Admin] Build teams and send members to voice channels.")
@is_admin()
async def teams(interaction: discord.Interaction):
    guild = interaction.guild
    voice_members = []
    for vc in guild.voice_channels:
        voice_members.extend(vc.members)
    voice_members = list({m.id: m for m in voice_members}.values())

    if not voice_members:
        await interaction.response.send_message(
            "⚠️ No members are currently in voice channels.", ephemeral=True
        )
        return

    voice_channels = [c for c in guild.channels if isinstance(c, discord.VoiceChannel)]
    view = TeamBuilderView(guild, voice_members, voice_channels)
    await interaction.response.send_message(
        "👥 **Team Builder**\n1. Pick members → 2. Pick their channel → Repeat for each team → 🚀 Send!",
        view=view, ephemeral=True
    )


# ─────────────────────────────────────────────
# ERROR HANDLERS
# ─────────────────────────────────────────────

@recall.error
@set_lobby.error
@teams.error
async def admin_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("❌ You need **Administrator** permissions.", ephemeral=True)
    else:
        raise error


# ─────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"   Slash commands synced.")


if __name__ == "__main__":
    bot.run(TOKEN)
