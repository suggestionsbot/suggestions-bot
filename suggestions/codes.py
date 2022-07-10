from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUGGESTION_MESSAGE_DELETED = 1
    MISSING_PERMISSIONS = 2
    MISSING_SUGGESTIONS_CHANNEL = 3
    MISSING_LOG_CHANNEL = 4
    SUGGESTION_NOT_FOUND = 5
    OWNER_ONLY = 6

    @classmethod
    def from_value(cls, value: int) -> ErrorCode:
        return ErrorCode(value)
