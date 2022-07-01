from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, List, Dict

from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from alaric.projections import PROJECTION, SHOW
from bot_base import NonExistentEntry
from bot_base.caches import TimedCache

if TYPE_CHECKING:
    from alaric import Document
    from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class State:
    """Simplistic way to pass state in a detached manner."""

    def __init__(self, database: SuggestionsMongoManager):
        self._is_closing: bool = False
        self.database: SuggestionsMongoManager = database
        self.autocomplete_cache: TimedCache = TimedCache()
        self.autocomplete_cache_ttl: timedelta = timedelta(minutes=10)

        self._background_tasks: list[asyncio.Task] = []

    @property
    def suggestions_db(self) -> Document:
        return self.database.suggestions

    @property
    def background_tasks(self) -> list[asyncio.Task]:
        return self._background_tasks

    def notify_shutdown(self):
        self._is_closing = True

    async def populate_sid_cache(self, guild_id: int) -> list:
        """Populates a guilds current active suggestion ids"""
        self.autocomplete_cache.delete_entry(guild_id)
        data: List[Dict] = await self.database.suggestions.find_many(
            AQ(AND(EQ("guild_id", guild_id), EQ("state", "open"))),
            projections=PROJECTION(SHOW("suggestion_id")),
            try_convert=False,
        )
        data: List[str] = [d["suggestion_id"] for d in data]
        self.autocomplete_cache.add_entry(
            guild_id, data, ttl=self.autocomplete_cache_ttl
        )
        return data

    def add_sid_to_cache(self, guild_id: int, suggestion_id: str) -> None:
        """Add a suggestion ID to the cache.

        This saves repopulating the entire cache from the database.
        """
        current_values: list = []
        try:
            current_values = self.autocomplete_cache.get_entry(guild_id)
        except NonExistentEntry:
            current_values = [suggestion_id]
        else:
            current_values.append(suggestion_id)
        finally:
            self.autocomplete_cache.add_entry(
                guild_id, current_values, override=True, ttl=self.autocomplete_cache_ttl
            )

    def remove_sid_from_cache(self, guild_id: int, suggestion_id: str) -> None:
        """Removes a suggestion from the cache when it's state is no longer open."""
        try:
            current_values: list = self.autocomplete_cache.get_entry(guild_id)
        except NonExistentEntry:
            return
        else:
            try:
                current_values.remove(suggestion_id)
            except ValueError:
                return
            else:
                self.autocomplete_cache.add_entry(
                    guild_id,
                    current_values,
                    override=True,
                    ttl=self.autocomplete_cache_ttl,
                )

    async def load(self):
        task_1 = asyncio.create_task(self.evict_caches())
        self._background_tasks.append(task_1)

    async def evict_caches(self):
        """Cleans the caches every 10 minutes"""
        while not self._is_closing:
            self.autocomplete_cache.force_clean()
            log.debug("Cleaned state caches")

            # This allows for immediate task finishing rather
            # than being forced to wait the whole 10 minutes
            # between loops for if we wish to gracefully close the task
            remaining_seconds = self.autocomplete_cache_ttl.total_seconds()
            while remaining_seconds > 0:

                remaining_seconds -= 5
                await asyncio.sleep(5)

                if self._is_closing:
                    return
