from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suggestions.database import SuggestionsMongoManager


class Stats:
    """Delayed stats processing for services at scale.

    TODO Replace with statsd
    """

    def __init__(self, database: SuggestionsMongoManager):
        self.database: SuggestionsMongoManager = database
        self._command_usage_cache: dict[str, int] = {}

    def register_command_usage(self, command_name: str) -> None:
        try:
            self._command_usage_cache[command_name] += 1
        except KeyError:
            self._command_usage_cache[command_name] = 1
