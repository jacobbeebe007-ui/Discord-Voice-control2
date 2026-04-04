"""Halo 3 Orbital Jump approval roster (persistent UI across restarts)."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from halo_bot.checks import is_admin
from halo_bot.constants import ORBITAL_MAX_SLOTS
from halo_bot.pure import parse_names
from halo_bot.storage import ORBITAL_FILE, orbital_jump_data, save_json

log = logging.getLogger(__name__)


def get_orbital_state(guild_id: int) -> dict:
    gid = str(guild_id)
    if gid not in orbital_jump_data:
        orbital_jump_data[gid] = {
            "message": "Spartans approved for Orbital Jump. Lock and load.",
            "emoji": "🚀",
            "approved": [],
        }
    return orbital_jump_data[gid]


def save_orbital_state():
    save_json(ORBITAL_FILE, orbital_jump_data)


def orbital_embed(guild: discord.Guild) -> discord.Embed:
    state = get_orbital_state(guild.id)
    approved = state.get("approved", [])[:ORBITAL_MAX_SLOTS]
    used = len(approved)
    remaining = ORBITAL_MAX_SLOTS - used
    icon = state.get("emoji", "🚀")

    embed = discord.Embed(
        title=f"{icon} Halo 3 — Orbital Jump Roster",
        description=state.get("message", ""),
        color=0x2E8B57,
    )
    if approved:
        lines = [f"{i}. {name}" for i, name in enumerate(approved, 1)]
        embed.add_field(name="✅ Approved Spartans", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="✅ Approved Spartans", value="_No approvals yet._", inline=False)
    embed.add_field(name="📦 Positions", value=f"**{used}/{ORBITAL_MAX_SLOTS}**")
    embed.add_field(name="🪂 Remaining", value=f"**{remaining}**")
    embed.set_footer(text="UNSC Deployment Console")
    return embed


async def refresh_orbital_panel(
    client: discord.Client,
    guild: discord.Guild,
    channel_id: int,
    message_id: int,
) -> None:
    ch = client.get_channel(channel_id)
    if ch is None:
        try:
            ch = await client.fetch_channel(channel_id)
        except Exception:
            log.warning("Orbital panel channel %s not found", channel_id)
            return
    try:
        msg = await ch.fetch_message(message_id)
        await msg.edit(embed=orbital_embed(guild), view=OrbitalJumpView())
    except Exception:
        log.exception("Failed to refresh orbital panel message %s", message_id)


class OrbitalAddModal(discord.ui.Modal, title="Add Approved Spartans"):
    names = discord.ui.TextInput(
        label="Names (comma or new line separated)",
        style=discord.TextStyle.paragraph,
        placeholder="Chief, Arbiter, Johnson",
        max_length=500,
    )

    def __init__(self, channel_id: int, message_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        state = get_orbital_state(interaction.guild_id)
        existing = state.get("approved", [])
        incoming = parse_names(str(self.names.value))
        added = 0
        for name in incoming:
            if name not in existing and len(existing) < ORBITAL_MAX_SLOTS:
                existing.append(name)
                added += 1
        state["approved"] = existing[:ORBITAL_MAX_SLOTS]
        save_orbital_state()
        await refresh_orbital_panel(
            interaction.client, interaction.guild, self.channel_id, self.message_id
        )
        await interaction.response.send_message(
            f"✅ Added **{added}** Spartan(s).", ephemeral=True
        )


class OrbitalRemoveModal(discord.ui.Modal, title="Remove Approved Spartans"):
    names = discord.ui.TextInput(
        label="Names to remove (comma or new line)",
        style=discord.TextStyle.paragraph,
        placeholder="Type exact names to remove",
        max_length=500,
    )

    def __init__(self, channel_id: int, message_id: int):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        state = get_orbital_state(interaction.guild_id)
        existing = state.get("approved", [])
        targets = set(parse_names(str(self.names.value)))
        before = len(existing)
        state["approved"] = [n for n in existing if n not in targets]
        removed = before - len(state["approved"])
        save_orbital_state()
        await refresh_orbital_panel(
            interaction.client, interaction.guild, self.channel_id, self.message_id
        )
        await interaction.response.send_message(
            f"🗑️ Removed **{removed}** Spartan(s).", ephemeral=True
        )


class OrbitalEditMessageModal(discord.ui.Modal, title="Edit Orbital Jump Message"):
    message = discord.ui.TextInput(
        label="Message text",
        style=discord.TextStyle.paragraph,
        placeholder="Mission briefing or requirements...",
        max_length=800,
    )

    def __init__(self, channel_id: int, message_id: int, current_message: str):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id
        self.message.default = current_message

    async def on_submit(self, interaction: discord.Interaction):
        state = get_orbital_state(interaction.guild_id)
        state["message"] = str(self.message.value).strip()
        save_orbital_state()
        await refresh_orbital_panel(
            interaction.client, interaction.guild, self.channel_id, self.message_id
        )
        await interaction.response.send_message("✏️ Message updated.", ephemeral=True)


class OrbitalEmojiModal(discord.ui.Modal, title="Set Orbital Jump Emoji"):
    emoji = discord.ui.TextInput(
        label="Emoji or text symbol",
        placeholder="🚀 or <:custom:1234567890>",
        max_length=50,
    )

    def __init__(self, channel_id: int, message_id: int, current_emoji: str):
        super().__init__()
        self.channel_id = channel_id
        self.message_id = message_id
        self.emoji.default = current_emoji

    async def on_submit(self, interaction: discord.Interaction):
        state = get_orbital_state(interaction.guild_id)
        value = str(self.emoji.value).strip()
        state["emoji"] = value or "🚀"
        save_orbital_state()
        await refresh_orbital_panel(
            interaction.client, interaction.guild, self.channel_id, self.message_id
        )
        await interaction.response.send_message("🎨 Orbital emoji updated.", ephemeral=True)


class OrbitalJumpView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Administrator permissions required.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="➕ Add", style=discord.ButtonStyle.success, row=0, custom_id="orbital:add"
    )
    async def add_people(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(
            OrbitalAddModal(interaction.channel_id, interaction.message.id)
        )

    @discord.ui.button(
        label="➖ Remove", style=discord.ButtonStyle.danger, row=0, custom_id="orbital:remove"
    )
    async def remove_people(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        await interaction.response.send_modal(
            OrbitalRemoveModal(interaction.channel_id, interaction.message.id)
        )

    @discord.ui.button(
        label="✏️ Edit Message",
        style=discord.ButtonStyle.primary,
        row=1,
        custom_id="orbital:edit_msg",
    )
    async def edit_message(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        current = get_orbital_state(interaction.guild_id).get("message", "")
        await interaction.response.send_modal(
            OrbitalEditMessageModal(
                interaction.channel_id, interaction.message.id, current
            )
        )

    @discord.ui.button(
        label="🎨 Set Emoji", style=discord.ButtonStyle.secondary, row=1, custom_id="orbital:emoji"
    )
    async def set_emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        current = get_orbital_state(interaction.guild_id).get("emoji", "🚀")
        await interaction.response.send_modal(
            OrbitalEmojiModal(interaction.channel_id, interaction.message.id, current)
        )

    @discord.ui.button(
        label="🧹 Reset", style=discord.ButtonStyle.secondary, row=2, custom_id="orbital:reset"
    )
    async def reset_roster(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._require_admin(interaction):
            return
        state = get_orbital_state(interaction.guild_id)
        state["approved"] = []
        save_orbital_state()
        await interaction.response.defer(ephemeral=True)
        await interaction.message.edit(
            embed=orbital_embed(interaction.guild), view=OrbitalJumpView()
        )
        await interaction.followup.send("🧹 Orbital Jump roster reset.", ephemeral=True)


class OrbitalCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="orbital_jump",
        description="[Admin] Manage the Halo 3 Orbital Jump approval roster (0/16).",
    )
    @is_admin()
    async def orbital_jump(self, interaction: discord.Interaction):
        state = get_orbital_state(interaction.guild_id)
        state["approved"] = state.get("approved", [])[:ORBITAL_MAX_SLOTS]
        save_orbital_state()
        await interaction.response.send_message(
            "🛰️ **Orbital Jump Control** — Admins can manage approvals with the panel below.",
            embed=orbital_embed(interaction.guild),
            view=OrbitalJumpView(),
            ephemeral=False,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(OrbitalCog(bot))
    bot.add_view(OrbitalJumpView())
