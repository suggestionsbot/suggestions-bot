from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from suggestions import State, SuggestionsBot

if TYPE_CHECKING:
    from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class Stats:
    """Delayed stats processing for services at scale."""

    def __init__(self, bot: SuggestionsBot):
        self.state: State = bot.state
        self.bot: SuggestionsBot = bot
        self.database: SuggestionsMongoManager = bot.db
        self._old_guild_count: Optional[int] = None

    async def load(self):
        task_1 = asyncio.create_task(self.push_stats())
        self.state.add_background_task(task_1)

    async def push_stats(self):
        while not self.state.is_closing:
            current_count = len(self.bot.guilds)
            if current_count != self._old_guild_count:
                # Let's actually change it
                await self.database.cluster_guild_counts.insert(
                    {
                        "cluster_id": self.bot.cluster_id,
                        "guild_count": current_count,
                        "timestamp": self.state.now,
                    }
                )
                self._old_guild_count = current_count
                log.debug(
                    "Cluster %s now sees %s guilds", self.bot.cluster_id, current_count
                )

            await self.bot.sleep_with_condition(5 * 60, self.state.is_closing)
