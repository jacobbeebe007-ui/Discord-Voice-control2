from discord import app_commands


def is_admin():
    async def predicate(interaction):
        return interaction.user.guild_permissions.administrator

    return app_commands.check(predicate)
