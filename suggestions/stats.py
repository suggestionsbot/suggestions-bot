from __future__ import annotations

import asyncio
import datetime
import logging
import math
from typing import TYPE_CHECKING, Optional, Dict, Literal, Union

from alaric.comparison import EQ
from alaric.types import ObjectId
from bot_base.caches import TimedCache
from motor.motor_asyncio import AsyncIOMotorCollection


if TYPE_CHECKING:
    from suggestions import State, SuggestionsBot
    from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class Stats:
    """Delayed stats processing for services at scale."""

    def __init__(self, bot: SuggestionsBot):
        self.state: State = bot.state
        self.bot: SuggestionsBot = bot
        self.database: SuggestionsMongoManager = bot.db
        self._old_guild_count: Optional[int] = None
        self.cluster_guild_cache: TimedCache = TimedCache()

    async def fetch_global_guild_count(self) -> int:
        if not self.bot.is_prod:
            return len(self.bot.guilds)

        total_count: int = 0
        raw_collection: AsyncIOMotorCollection = (
            self.database.cluster_guild_counts.raw_collection
        )
        total_cluster_count = self.bot.total_cluster_count
        for i in range(1, total_cluster_count + 1):
            if i not in self.cluster_guild_cache:
                query = EQ("cluster_id", i)
                cursor = (
                    raw_collection.find(query.build()).sort("timestamp", -1).limit(1)
                )
                items = await cursor.to_list(1)  # Known to be one
                entry: Dict[
                    Literal["cluster_id", "_id", "guild_count", "timestamp"],
                    Union[int, ObjectId, datetime.datetime],
                ] = items[0]
                self.cluster_guild_cache.add_entry(
                    i,
                    entry["guild_count"],
                    ttl=datetime.timedelta(minutes=5),
                )
                total_count += entry["guild_count"]
                continue

            total_count += self.cluster_guild_cache.get_entry(i)

        return total_count

    async def load(self):
        try:
            query = EQ("cluster_id", self.bot.cluster_id)
            cursor = (
                self.database.cluster_guild_counts.raw_collection.find(query.build())
                .sort("timestamp", -1)
                .limit(1)
            )
            items = await cursor.to_list(1)
            entry: Dict[
                Literal["cluster_id", "_id", "guild_count", "timestamp"],
                Union[int, ObjectId, datetime.datetime],
            ] = items[0]
            self._old_guild_count = entry["guild_count"]
        except:
            pass

        task_1 = asyncio.create_task(self.push_stats())
        self.state.add_background_task(task_1)

    async def push_stats(self):
        while not self.state.is_closing:
            current_count = len(self.bot.guilds)
            if current_count != self._old_guild_count and current_count != 0:
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

            await self.bot.sleep_with_condition(5 * 60, lambda: self.state.is_closing)
