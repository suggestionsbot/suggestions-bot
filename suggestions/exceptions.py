from typing import Optional

from disnake.ext.commands import CheckFailure


class BetaOnly(CheckFailure):
    """This command can only be used on guilds with Beta access."""

    def __init__(self, guild_id: Optional[int] = None):
        self.guild_id: Optional[int] = guild_id


class MissingSuggestionsChannel(CheckFailure):
    """This command requires a suggestions channel to run."""


class MissingLogsChannel(CheckFailure):
    """This command requires a logs channel to run."""
