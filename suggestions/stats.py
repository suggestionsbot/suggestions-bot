from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suggestions.database import SuggestionsMongoManager


class Stats:
    """Delayed stats processing for services at scale.

    Implements internal tasks which aggregate statistics
    to reduce load at scale for the database.
    """

    def __init__(self, database: SuggestionsMongoManager):
        self.database: SuggestionsMongoManager = database
        self._command_usage_cache: dict[str, int] = {}

    def register_command_usage(self, command_name: str) -> None:
        try:
            self._command_usage_cache[command_name] += 1
        except KeyError:
            self._command_usage_cache[command_name] = 1

    async def process_command_usage(self):
        command_usages: dict[str, int] = self._command_usage_cache
        self._command_usage_cache = {}
        for field, count in command_usages.items():
            await self.database.command_usage_stats.increment(
                {"command_name": field}, "usage_count", count
            )
