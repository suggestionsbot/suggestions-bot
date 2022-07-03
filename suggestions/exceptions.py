from typing import Optional

from disnake.ext.commands import CheckFailure


class BetaOnly(CheckFailure):
    """This command can only be used on guilds with Beta access."""

    def __init__(self, guild_id: Optional[int] = None):
        self.guild_id: Optional[int] = guild_id
