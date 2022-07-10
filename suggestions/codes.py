from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUGGESTION_MESSAGE_DELETED = 1
    MISSING_PERMISSIONS = 2
    MISSING_SUGGESTIONS_CHANNEL = 3
    MISSING_LOG_CHANNEL = 4
    SUGGESTION_NOT_FOUND = 5
    OWNER_ONLY = 6
    SUGGESTION_CONTENT_TOO_LONG = 7
    INVALID_GUILD_CONFIG_CHOICE = 8
    COMMAND_ON_COOLDOWN = 9

    @classmethod
    def from_value(cls, value: int) -> ErrorCode:
        return ErrorCode(value)
