import discord


def _split_names(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.replace("\n", ",").split(",")]
    return [p for p in parts if p]


class _MMRPlayerModal(discord.ui.Modal, title="MMR Lookup"):
    player = discord.ui.TextInput(
        label="Player name",
        placeholder="Enter a Discord display name",
        max_length=80,
    )

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        await self.handler(interaction, str(self.player.value).strip())


class _CompareModal(discord.ui.Modal, title="Compare Players"):
    names = discord.ui.TextInput(
        label="2 to 4 player names (comma or new line)",
        style=discord.TextStyle.paragraph,
        placeholder="Player1, Player2, Player3",
        max_length=320,
    )

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        players = _split_names(str(self.names.value))
        if len(players) < 2 or len(players) > 4:
            await interaction.response.send_message(
                "⚠️ Enter **2 to 4** player names.", ephemeral=True
            )
            return
        await self.handler(interaction, players)


class _RivalsModal(discord.ui.Modal, title="Rivals Head-to-Head"):
    player1 = discord.ui.TextInput(label="Player 1", max_length=80)
    player2 = discord.ui.TextInput(label="Player 2", max_length=80)

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        await self.handler(
            interaction,
            str(self.player1.value).strip(),
            str(self.player2.value).strip(),
        )


class _SessionModal(discord.ui.Modal, title="Session Lookup"):
    number = discord.ui.TextInput(
        label="Session number",
        placeholder="e.g. 7",
        max_length=8,
    )
    player = discord.ui.TextInput(
        label="Player name",
        placeholder="Enter a Discord display name",
        max_length=80,
    )

    def __init__(self, handler):
        super().__init__()
        self.handler = handler

    async def on_submit(self, interaction: discord.Interaction):
        raw_num = str(self.number.value).strip()
        try:
            session_num = int(raw_num)
        except ValueError:
            await interaction.response.send_message(
                "⚠️ Session number must be an integer.", ephemeral=True
            )
            return
        await self.handler(interaction, session_num, str(self.player.value).strip())


class MMRHubView(discord.ui.View):
    def __init__(self, handlers: dict):
        super().__init__(timeout=None)
        self.handlers = handlers

    @discord.ui.button(label="🏆 Leaderboard", style=discord.ButtonStyle.secondary, row=0)
    async def leaderboard(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.handlers["leaderboard"](interaction)

    @discord.ui.button(label="🔎 MMR", style=discord.ButtonStyle.secondary, row=0)
    async def mmr_lookup(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(_MMRPlayerModal(self.handlers["mmr"]))

    @discord.ui.button(label="🆚 Compare", style=discord.ButtonStyle.secondary, row=0)
    async def compare(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(_CompareModal(self.handlers["compare"]))

    @discord.ui.button(label="⚔️ Rivals", style=discord.ButtonStyle.secondary, row=0)
    async def rivals(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(_RivalsModal(self.handlers["rivals"]))

    @discord.ui.button(label="🗂️ Session", style=discord.ButtonStyle.secondary, row=1)
    async def session(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.send_modal(_SessionModal(self.handlers["session"]))

    @discord.ui.button(label="🥇 Podium", style=discord.ButtonStyle.secondary, row=1)
    async def podium(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.handlers["podium"](interaction)

    @discord.ui.button(label="📊 Stats", style=discord.ButtonStyle.primary, row=1)
    async def stats(self, interaction: discord.Interaction, _: discord.ui.Button):
        await self.handlers["stats"](interaction)
