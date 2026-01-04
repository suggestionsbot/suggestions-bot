from __future__ import annotations

import asyncio
import datetime
import logging
from enum import Enum
from typing import TYPE_CHECKING, Optional, Type

import alaric
import commons
from alaric import Cursor, AQ
from alaric.comparison import EQ
from commons.caching import TimedCache

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
    MEMBER_PING_ON_THREAD_CREATE_ENABLE = "member_ping_on_thread_create_enable"
    MEMBER_PING_ON_THREAD_CREATE_DISABLE = "member_ping_on_thread_create_disable"
    MEMBER_PING_ON_THREAD_CREATE_VIEW = "member_ping_on_thread_create_view"
    GUILD_CONFIG_LOG_CHANNEL = "guild_config_log_channel"
    GUILD_CONFIG_QUEUE_CHANNEL = "guild_config_queue_channel"
    GUILD_CONFIG_REJECTED_QUEUE_CHANNEL = "guild_config_rejected_queue_channel"
    GUILD_CONFIG_SUGGEST_CHANNEL = "guild_config_suggest_channel"
    GUILD_CONFIG_GET = "guild_config_get"
    GUILD_DM_ENABLE = "guild_dm_enable"
    GUILD_DM_DISABLE = "guild_dm_disable"
    GUILD_THREAD_ENABLE = "guild_thread_enable"
    GUILD_THREAD_DISABLE = "guild_thread_disable"
    GUILD_PING_ON_THREAD_CREATE_ENABLE = "guild_ping_on_thread_create_enable"
    GUILD_PING_ON_THREAD_CREATE_DISABLE = "guild_ping_on_thread_create_disable"
    GUILD_AUTO_ARCHIVE_THREADS_ENABLE = "guild_auto_archive_threads_enable"
    GUILD_AUTO_ARCHIVE_THREADS_DISABLE = "guild_auto_archive_threads_disable"
    GUILD_SUGGESTIONS_QUEUE_ENABLE = "guild_suggestions_queue_enable"
    GUILD_SUGGESTIONS_QUEUE_DISABLE = "guild_suggestions_queue_disable"
    GUILD_ANONYMOUS_RESOLUTIONS_ENABLE = "guild_anonymous_resolutions_enable"
    GUILD_ANONYMOUS_RESOLUTIONS_DISABLE = "guild_anonymous_resolutions_disable"
    GUILD_IMAGES_IN_SUGGESTIONS_ENABLE = "guild_images_in_suggestions_enable"
    GUILD_IMAGES_IN_SUGGESTIONS_DISABLE = "guild_images_in_suggestions_disable"
    GUILD_PHYSICAL_QUEUE_ENABLE = "guild_physical_queue_enable"
    GUILD_PHYSICAL_QUEUE_DISABLE = "guild_physical_queue_disable"
    GUILD_KEEPLOGS_ENABLE = "guild_keeplogs_enable"
    GUILD_KEEPLOGS_DISABLE = "guild_keeplogs_disable"
    GUILD_ANONYMOUS_ENABLE = "guild_anonymous_enable"
    GUILD_ANONYMOUS_DISABLE = "guild_anonymous_disable"
    ACTIVATE_BETA = "activate_beta"
    STATS = "stats"
    VIEW_UP_VOTERS = "view_up_voters"
    VIEW_DOWN_VOTERS = "view_down_voters"
    VIEW_VOTERS = "view_voters"

    @classmethod
    def from_command_name(cls, name: str) -> Optional[StatsEnum]:
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
                "config anonymous enable": cls.GUILD_ANONYMOUS_ENABLE,
                "config anonymous disable": cls.GUILD_ANONYMOUS_DISABLE,
                "config auto_archive_threads enable": cls.GUILD_AUTO_ARCHIVE_THREADS_ENABLE,
                "config auto_archive_threads disable": cls.GUILD_AUTO_ARCHIVE_THREADS_DISABLE,
                "config images_in_suggestions enable": cls.GUILD_IMAGES_IN_SUGGESTIONS_ENABLE,
                "config images_in_suggestions disable": cls.GUILD_IMAGES_IN_SUGGESTIONS_DISABLE,
                "config anonymous_resolutions enable": cls.GUILD_ANONYMOUS_RESOLUTIONS_ENABLE,
                "config anonymous_resolutions disable": cls.GUILD_ANONYMOUS_RESOLUTIONS_DISABLE,
                "Approve suggestion": cls.APPROVE_BY_MESSAGE_COMMAND,
                "Reject suggestion": cls.REJECT_BY_MESSAGE_COMMAND,
                "View up voters": cls.VIEW_UP_VOTERS,
                "View down voters": cls.VIEW_DOWN_VOTERS,
                "View voters": cls.VIEW_VOTERS,
            }[name]
        except KeyError:
            log.debug("Failed to find StatsEnum for %s", name)
            return None


class Stats:
    """Delayed stats processing for services at scale."""

    def __init__(self, bot: SuggestionsBot):
        self.state: State = bot.state
        self.bot: SuggestionsBot = bot
        self.database: SuggestionsMongoManager = bot.db
        self.cluster_guild_cache: TimedCache = TimedCache(lazy_eviction=False)
        self.member_stats_cache: TimedCache = TimedCache(lazy_eviction=False)
        self.type: Type[StatsEnum] = StatsEnum
        self._inter_count: int = 0

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

    async def fetch_approximate_global_guild_count(self) -> int:
        app_data = await self.bot.application_info()
        return app_data.approximate_guild_count

    async def load(self):
        self.state.add_background_task(asyncio.create_task(self.push_inter_stats()))

    async def push_inter_stats(self):
        while not self.state.is_closing:
            await commons.sleep_with_condition(
                datetime.timedelta(hours=1).total_seconds(),
                lambda: self.state.is_closing,
            )
            # Reset to account for database processing time
            count = self._inter_count
            self._inter_count = 0

            if count == 0:
                continue

            await self.bot.db.interaction_events.insert(
                {
                    "count": count,
                    "inserted_at": self.state.now,
                    "cluster": self.bot.cluster_id,
                }
            )

    def increment_event_type(self, event_type: str):
        # We only want interactions for now
        event_type = event_type.lower()
        if event_type != "interaction_create":
            return

        self._inter_count += 1
