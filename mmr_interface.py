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


class _MMRHubSelect(discord.ui.Select):
    def __init__(self, parent: "MMRHubView"):
        options = [
            discord.SelectOption(label="Leaderboard", value="leaderboard", emoji="🏆"),
            discord.SelectOption(label="MMR Lookup", value="mmr", emoji="🔎"),
            discord.SelectOption(label="Compare", value="compare", emoji="🆚"),
            discord.SelectOption(label="Rivals", value="rivals", emoji="⚔️"),
            discord.SelectOption(label="Session", value="session", emoji="🗂️"),
            discord.SelectOption(label="Podium", value="podium", emoji="🥇"),
            discord.SelectOption(label="Stats Leaders", value="stats", emoji="📊"),
        ]
        super().__init__(
            placeholder="Choose a stats/MMR action…",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )
        self.parent_view = parent

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        handlers = self.parent_view.handlers
        if key == "leaderboard":
            await handlers["leaderboard"](interaction)
        elif key == "mmr":
            await interaction.response.send_modal(_MMRPlayerModal(handlers["mmr"]))
        elif key == "compare":
            await interaction.response.send_modal(_CompareModal(handlers["compare"]))
        elif key == "rivals":
            await interaction.response.send_modal(_RivalsModal(handlers["rivals"]))
        elif key == "session":
            await interaction.response.send_modal(_SessionModal(handlers["session"]))
        elif key == "podium":
            await handlers["podium"](interaction)
        elif key == "stats":
            await handlers["stats"](interaction)


class MMRHubView(discord.ui.View):
    def __init__(self, handlers: dict):
        super().__init__(timeout=None)
        self.handlers = handlers
        self.add_item(_MMRHubSelect(self))
