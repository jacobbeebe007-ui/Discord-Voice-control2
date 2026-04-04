"""Halo 3 matchmaking rolls and veto UI."""
import random

import discord
from discord import app_commands
from discord.ext import commands

from halo_bot.checks import is_admin
from halo_bot.constants import TIMEOUT_MENU


def h3_img(filename: str) -> str:
    return f"https://www.halopedia.org/Special:FilePath/{filename}"


HALO3_MAPS = [
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
    {"name": "Foundry",     "img": h3_img("H3_Multiplayer_Foundry.jpg"),     "dlc": True},
    {"name": "Rat's Nest",  "img": h3_img("H3_Multiplayer_Rats_Nest.jpg"),   "dlc": True},
    {"name": "Standoff",    "img": h3_img("H3_Multiplayer_Standoff.jpg"),    "dlc": True},
    {"name": "Avalanche",   "img": h3_img("H3_Multiplayer_Avalanche.jpg"),   "dlc": True},
    {"name": "Blackout",    "img": h3_img("H3_Multiplayer_Blackout.jpg"),    "dlc": True},
    {"name": "Ghost Town",  "img": h3_img("H3_Multiplayer_Ghost_Town.jpg"),  "dlc": True},
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
    """Opening menu — admin only, choose mode and settings."""

    def __init__(self):
        super().__init__(timeout=TIMEOUT_MENU)
        self.team_count = 2
        self.include_dlc = False
        team_opts = [discord.SelectOption(label=f"{i} Teams", value=str(i),
                     default=(i == 2)) for i in range(2, 9)]
        self.team_select = discord.ui.Select(
            placeholder="Number of teams...", options=team_opts, row=0)
        self.team_select.callback = self.on_team_select
        self.add_item(self.team_select)
        pool_opts = [
            discord.SelectOption(label="Standard maps only", value="standard", default=True),
            discord.SelectOption(label="Standard + all DLC",  value="all"),
        ]
        self.pool_select = discord.ui.Select(
            placeholder="Map pool...", options=pool_opts, row=1)
        self.pool_select.callback = self.on_pool_select
        self.add_item(self.pool_select)

    async def on_team_select(self, interaction: discord.Interaction):
        self.team_count = int(self.team_select.values[0])
        await interaction.response.defer()

    async def on_pool_select(self, interaction: discord.Interaction):
        self.include_dlc = self.pool_select.values[0] == "all"
        await interaction.response.defer()

    def _get_maps(self):
        return [m for m in HALO3_MAPS if not m["dlc"] or self.include_dlc]

    @discord.ui.button(label="🎲 Single Match", style=discord.ButtonStyle.primary, row=2)
    async def single_match(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps = self._get_maps()
        chosen_map = random.choice(maps)
        chosen_gametype = random.choice(HALO3_GAMETYPES)
        embed = discord.Embed(title="🎮 Halo 3 — Match Roll", color=0x00aaff)
        embed.add_field(name="🗺️ Map",       value=f"**{chosen_map['name']}**",  inline=True)
        embed.add_field(name="🎯 Game Type", value=f"**{chosen_gametype}**",     inline=True)
        embed.add_field(name="👥 Teams",     value=f"**{self.team_count}**",     inline=True)
        embed.set_image(url=chosen_map["img"])
        embed.set_footer(text="Halo Night Bot — Matchmaking")
        await interaction.response.send_message(embed=embed, ephemeral=False)

    @discord.ui.button(label="🎲🎲 Two Matches", style=discord.ButtonStyle.primary, row=2)
    async def two_matches(self, interaction: discord.Interaction, button: discord.ui.Button):
        maps = self._get_maps()
        sample = random.sample(maps, min(2, len(maps)))
        m1, m2 = sample[0], sample[1]
        g1 = random.choice(HALO3_GAMETYPES)
        g2 = random.choice(HALO3_GAMETYPES)

        embed1 = discord.Embed(title="🎮 Match 1", color=0x00aaff)
        embed1.add_field(name="🗺️ Map",       value=f"**{m1['name']}**",    inline=True)
        embed1.add_field(name="🎯 Game Type", value=f"**{g1}**",            inline=True)
        embed1.add_field(name="👥 Teams",     value=f"**{self.team_count}**", inline=True)
        embed1.set_image(url=m1["img"])

        embed2 = discord.Embed(title="🎮 Match 2", color=0xff6600)
        embed2.add_field(name="🗺️ Map",       value=f"**{m2['name']}**",    inline=True)
        embed2.add_field(name="🎯 Game Type", value=f"**{g2}**",            inline=True)
        embed2.add_field(name="👥 Teams",     value=f"**{self.team_count}**", inline=True)
        embed2.set_image(url=m2["img"])

        await interaction.response.send_message(
            "⚔️ **Two matches rolled! Anyone can veto below.**",
            embeds=[embed1, embed2],
            view=VetoView(m1, g1, m2, g2, self.team_count, maps),
            ephemeral=False)

    @discord.ui.button(label="✕ Cancel", style=discord.ButtonStyle.secondary, row=2)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.delete_original_response()


class VetoView(discord.ui.View):
    """Veto system — anyone can click. Each slot rerolls once then locks."""

    def __init__(self, m1, g1, m2, g2, num_teams, maps):
        super().__init__(timeout=300)
        self.m1, self.g1 = m1, g1
        self.m2, self.g2 = m2, g2
        self.num_teams = num_teams
        self.maps = maps
        self.vetoed = set()

    def _build_embeds(self):
        e1 = discord.Embed(title="🎮 Match 1", color=0x00aaff)
        e1.add_field(name="🗺️ Map",       value=f"**{self.m1['name']}**",  inline=True)
        e1.add_field(name="🎯 Game Type", value=f"**{self.g1}**",          inline=True)
        e1.add_field(name="👥 Teams",     value=f"**{self.num_teams}**",   inline=True)
        e1.set_image(url=self.m1["img"])
        e2 = discord.Embed(title="🎮 Match 2", color=0xff6600)
        e2.add_field(name="🗺️ Map",       value=f"**{self.m2['name']}**",  inline=True)
        e2.add_field(name="🎯 Game Type", value=f"**{self.g2}**",          inline=True)
        e2.add_field(name="👥 Teams",     value=f"**{self.num_teams}**",   inline=True)
        e2.set_image(url=self.m2["img"])
        return [e1, e2]

    @discord.ui.button(label="🚫 Veto Match 1 Map",  style=discord.ButtonStyle.danger, row=0)
    async def veto_m1_map(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m1_map" in self.vetoed:
            await interaction.response.send_message(
                "⚠️ Match 1 map already vetoed.", ephemeral=True)
            return
        self.vetoed.add("m1_map")
        old = self.m1["name"]
        pool = [m for m in self.maps
                if m["name"] != self.m1["name"] and m["name"] != self.m2["name"]]
        self.m1 = random.choice(pool) if pool else self.m1
        button.disabled = True
        button.label = "✅ M1 Map Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → **{self.m1['name']}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 1 Type", style=discord.ButtonStyle.danger, row=0)
    async def veto_m1_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m1_type" in self.vetoed:
            await interaction.response.send_message(
                "⚠️ Match 1 type already vetoed.", ephemeral=True)
            return
        self.vetoed.add("m1_type")
        old = self.g1
        pool = [g for g in HALO3_GAMETYPES if g != self.g1]
        self.g1 = random.choice(pool) if pool else self.g1
        button.disabled = True
        button.label = "✅ M1 Type Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → **{self.g1}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 2 Map",  style=discord.ButtonStyle.danger, row=1)
    async def veto_m2_map(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m2_map" in self.vetoed:
            await interaction.response.send_message(
                "⚠️ Match 2 map already vetoed.", ephemeral=True)
            return
        self.vetoed.add("m2_map")
        old = self.m2["name"]
        pool = [m for m in self.maps
                if m["name"] != self.m1["name"] and m["name"] != self.m2["name"]]
        self.m2 = random.choice(pool) if pool else self.m2
        button.disabled = True
        button.label = "✅ M2 Map Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → **{self.m2['name']}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="🚫 Veto Match 2 Type", style=discord.ButtonStyle.danger, row=1)
    async def veto_m2_type(self, interaction: discord.Interaction, button: discord.ui.Button):
        if "m2_type" in self.vetoed:
            await interaction.response.send_message(
                "⚠️ Match 2 type already vetoed.", ephemeral=True)
            return
        self.vetoed.add("m2_type")
        old = self.g2
        pool = [g for g in HALO3_GAMETYPES if g != self.g2]
        self.g2 = random.choice(pool) if pool else self.g2
        button.disabled = True
        button.label = "✅ M2 Type Vetoed"
        await interaction.response.edit_message(
            content=f"🚫 **{interaction.user.display_name}** vetoed **{old}** → **{self.g2}**",
            embeds=self._build_embeds(), view=self)

    @discord.ui.button(label="✅ Lock In", style=discord.ButtonStyle.success, row=2)
    async def lock_in(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="🔒 **Matches locked in! Good luck!**",
            embeds=self._build_embeds(), view=self)


class MatchmakingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="matchmaking",
        description="[Admin] Roll Halo 3 maps, game types and teams for your night.",
    )
    @is_admin()
    async def matchmaking(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            "🎮 **Halo 3 Matchmaking** — set options then choose a mode:",
            view=MatchmakingMenuView(), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MatchmakingCog(bot))
