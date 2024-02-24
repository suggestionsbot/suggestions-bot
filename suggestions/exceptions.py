from typing import Optional

import disnake
from disnake.ext.commands import CheckFailure


class BetaOnly(CheckFailure):
    """This command can only be used on guilds with Beta access."""

    def __init__(self, guild_id: Optional[int] = None):
        self.guild_id: Optional[int] = guild_id


class MissingSuggestionsChannel(CheckFailure):
    """This command requires a suggestions channel to run."""


class MissingLogsChannel(CheckFailure):
    """This command requires a logs channel to run."""


class ErrorHandled(disnake.DiscordException):
    """This tells error handlers the error was already handled, and can be ignored."""


class SuggestionNotFound(disnake.DiscordException):
    """Cannot find a suggestion with this id."""


class SuggestionTooLong(disnake.DiscordException):
    """The suggestion content was too long."""


class InvalidGuildConfigOption(disnake.DiscordException):
    """The provided guild config choice doesn't exist."""


class ConfiguredChannelNoLongerExists(disnake.DiscordException):
    """The configured channel can no longer be found."""


class UnhandledError(Exception):
    """Something went wrong."""


class QueueImbalance(disnake.DiscordException):
    """This queued suggestion has already been dealt with in another queue."""


class BlocklistedUser(CheckFailure):
    """This user is blocked from taking this action in this guild."""


class PartialResponse(Exception):
    """A garven route returned a partial response when we require a full response"""
