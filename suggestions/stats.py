from __future__ import annotations

import asyncio
import datetime
import logging
from enum import Enum
from typing import TYPE_CHECKING, Optional, Dict, Literal, Union, Type

from alaric.comparison import EQ
from alaric.types import ObjectId
from bot_base.caches import TimedCache
from motor.motor_asyncio import AsyncIOMotorCollection

from suggestions.objects.stats import MemberStats, MemberCommandStats

if TYPE_CHECKING:
    from suggestions import State, SuggestionsBot
    from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class StatsEnum(Enum):
    SUGGEST = "suggest"
    APPROVE = "approve"
    APPROVE_BY_MESSAGE_COMMAND = "approve_by_message_command"
    REJECT = "reject"
    REJECT_BY_MESSAGE_COMMAND = "reject_by_message_command"
    CLEAR = "clear"
    MEMBER_DM_VIEW = "member_dm_view"
    MEMBER_DM_ENABLE = "member_dm_enable"
    MEMBER_DM_DISABLE = "member_dm_disable"
    GUILD_CONFIG_LOG_CHANNEL = "guild_config_log_channel"
    GUILD_CONFIG_SUGGEST_CHANNEL = "guild_config_suggest_channel"
    GUILD_CONFIG_GET = "guild_config_get"
    GUILD_DM_ENABLE = "guild_dm_enable"
    GUILD_DM_DISABLE = "guild_dm_disable"
    GUILD_THREAD_ENABLE = "guild_thread_enable"
    GUILD_THREAD_DISABLE = "guild_thread_disable"
    GUILD_KEEPLOGS_ENABLE = "guild_keeplogs_enable"
    GUILD_KEEPLOGS_DISABLE = "guild_keeplogs_disable"
    ACTIVATE_BETA = "activate_beta"
    STATS = "stats"

    @classmethod
    def from_command_name(cls, name: str) -> Optional[StatsEnum]:
        if name == "Approve Suggestion":
            return cls.APPROVE_BY_MESSAGE_COMMAND
        elif name == "Reject Suggestion":
            return cls.REJECT_BY_MESSAGE_COMMAND

        try:
            return {
                "suggest": cls.SUGGEST,
                "approve": cls.APPROVE,
                "reject": cls.REJECT,
                "clear": cls.CLEAR,
                "dm enable": cls.MEMBER_DM_ENABLE,
                "dm disable": cls.MEMBER_DM_DISABLE,
                "dm view": cls.MEMBER_DM_VIEW,
                "stats": cls.STATS,
                "config get": cls.GUILD_CONFIG_GET,
                "config channel": cls.GUILD_CONFIG_SUGGEST_CHANNEL,
                "config logs": cls.GUILD_CONFIG_LOG_CHANNEL,
                "activate beta": cls.ACTIVATE_BETA,
                "config dm enable": cls.GUILD_DM_ENABLE,
                "config dm disable": cls.GUILD_DM_DISABLE,
                "config thread enable": cls.GUILD_THREAD_ENABLE,
                "config thread disable": cls.GUILD_THREAD_DISABLE,
                "config keeplogs enable": cls.GUILD_KEEPLOGS_ENABLE,
                "config keeplogs disable": cls.GUILD_KEEPLOGS_DISABLE,
            }[name]
        except KeyError:
            log.error("Failed to find StatsEnum for %s", name)
            return None


class Stats:
    """Delayed stats processing for services at scale."""

    def __init__(self, bot: SuggestionsBot):
        self.state: State = bot.state
        self.bot: SuggestionsBot = bot
        self.database: SuggestionsMongoManager = bot.db
        self._old_guild_count: Optional[int] = None
        self.cluster_guild_cache: TimedCache = TimedCache()
        self.member_stats_cache: TimedCache = TimedCache()
        self.type: Type[StatsEnum] = StatsEnum

    async def log_stats(
        self,
        member_id: int,
        guild_id: int,
        stat_type: StatsEnum,
        *,
        was_success: bool = True,
    ):
        member_stats: MemberStats = await MemberStats.from_id(
            member_id, guild_id, self.state
        )

        stat_type_str = str(stat_type.value)
        stats_attr: MemberCommandStats = getattr(member_stats, stat_type_str, False)
        if not stats_attr:
            if stat_type_str not in member_stats.valid_fields:
                log.error(
                    "Failed to find attr '%s' on MemberStats(member_id=%s, guild_id=%s)",
                    stat_type.value,
                    member_id,
                    guild_id,
                )
                return

            stats_attr: MemberCommandStats = MemberCommandStats(stat_type_str)
            setattr(member_stats, stat_type_str, stats_attr)

        if was_success:
            stats_attr.completed_at.append(self.state.now)
        else:
            stats_attr.failed_at.append(self.state.now)

        await self.state.member_stats_db.upsert(member_stats, member_stats)

    def refresh_member_stats(self, member_stats: MemberStats) -> None:
        self.member_stats_cache.add_entry(
            f"{member_stats.member_id}|{member_stats.guild_id}",
            member_stats,
            override=True,
            ttl=datetime.timedelta(minutes=15),
        )

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
