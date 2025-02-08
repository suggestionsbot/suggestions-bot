from __future__ import annotations

import asyncio
import datetime
import logging
import random
import string
from datetime import timedelta
from typing import TYPE_CHECKING, List, Dict, Set, Any

import disnake
from alaric import AQ
from alaric.comparison import EQ, Exists
from alaric.logical import AND
from alaric.meta import Negate
from alaric.projections import PROJECTION, SHOW
from commons.caching import NonExistentEntry, TimedCache
from logoo import Logger

from suggestions.objects import GuildConfig, UserConfig, PremiumGuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot
    from alaric import Document
    from suggestions.database import SuggestionsMongoManager
    from suggestions.interaction_handler import InteractionHandler

log = logging.getLogger(__name__)
logger = Logger(__name__)


class State:
    """Simplistic way to pass state in a detached manner."""

    def __init__(self, database: SuggestionsMongoManager, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self._is_closing: bool = False
        self.database: SuggestionsMongoManager = database

        # Timed caches
        self.autocomplete_cache_ttl: timedelta = timedelta(minutes=10)
        self.autocomplete_cache: TimedCache[int, list[str]] = TimedCache(
            global_ttl=self.autocomplete_cache_ttl, lazy_eviction=False
        )
        self.guild_cache_ttl: timedelta = timedelta(minutes=15)
        self.guild_cache: TimedCache[int, disnake.Guild] = TimedCache(
            global_ttl=self.guild_cache_ttl,
            lazy_eviction=False,
            ttl_from_last_access=True,
        )
        self.view_voters_cache: TimedCache[int, list[str]] = TimedCache(
            global_ttl=self.autocomplete_cache_ttl,
            lazy_eviction=False,
            ttl_from_last_access=True,
        )
        self.object_cache: TimedCache[int, Any] = TimedCache(
            global_ttl=timedelta(hours=1), lazy_eviction=False
        )

        self.guild_configs: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=30),
            lazy_eviction=False,
            ttl_from_last_access=True,
        )
        self.premium_guild_configs: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=30),
            lazy_eviction=False,
            ttl_from_last_access=True,
        )
        self.user_configs: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=30),
            lazy_eviction=False,
            ttl_from_last_access=True,
        )

        self.existing_error_ids: Set[str] = set()
        self.existing_paginator_ids: Set[str] = set()
        self.existing_suggestion_ids: Set[str] = set()
        self._background_tasks: list[asyncio.Task] = []

        self.interaction_handlers: TimedCache[int, InteractionHandler] = TimedCache(
            global_ttl=timedelta(minutes=20), lazy_eviction=False
        )

    @property
    def is_closing(self) -> bool:
        return self._is_closing

    @is_closing.setter
    def is_closing(self, value):
        self._is_closing = value

    def get_new_error_id(self) -> str:
        """See get_new_suggestion_id, except its for errors"""
        error_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        while error_id in self.existing_error_ids:
            error_id = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            logger.critical("Encountered an existing error id")

        self.existing_error_ids.add(error_id)
        return error_id

    def get_new_sq_paginator_id(self) -> str:
        pag_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
        while pag_id in self.existing_paginator_ids:
            pag_id = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            logger.critical("Encountered an existing paginator id")

        self.existing_paginator_ids.add(pag_id)
        return pag_id

    def get_new_suggestion_id(self) -> str:
        """Generate a new SID, ensuring uniqueness."""
        suggestion_id = "".join(
            random.choices(string.ascii_lowercase + string.digits, k=8)
        )
        while suggestion_id in self.existing_suggestion_ids:
            suggestion_id = "".join(
                random.choices(string.ascii_lowercase + string.digits, k=8)
            )
            logger.critical("Encountered an existing SID")

        self.existing_suggestion_ids.add(suggestion_id)
        return suggestion_id

    def add_background_task(self, task: asyncio.Task) -> None:
        self._background_tasks.append(task)

    def remove_background_task(self, task: asyncio.Task) -> None:
        self._background_tasks.remove(task)

    @property
    def suggestions_db(self) -> Document:
        return self.database.suggestions

    @property
    def queued_suggestions_db(self) -> Document:
        return self.database.queued_suggestions

    @property
    def guild_config_db(self) -> Document:
        return self.database.guild_configs

    @property
    def premium_guild_config_db(self) -> Document:
        return self.database.premium_guild_configs

    @property
    def user_config_db(self) -> Document:
        return self.database.user_configs

    @property
    def member_stats_db(self) -> Document:
        return self.database.member_stats

    @property
    def now(self) -> datetime.datetime:
        return datetime.datetime.now()

    @property
    def background_tasks(self) -> list[asyncio.Task]:
        return self._background_tasks

    def notify_shutdown(self):
        self.is_closing = True

    def refresh_guild_config(self, guild_config: GuildConfig) -> None:
        self.guild_configs.add_entry(guild_config.guild_id, guild_config, override=True)

    def refresh_premium_guild_config(self, guild_config: PremiumGuildConfig) -> None:
        self.premium_guild_configs.add_entry(
            guild_config.guild_id, guild_config, override=True
        )

    def refresh_user_config(self, user_config: UserConfig) -> None:
        self.user_configs.add_entry(user_config.user_id, user_config, override=True)

    def refresh_guild_cache(self, guild: disnake.Guild) -> None:
        self.guild_cache.add_entry(guild.id, guild, override=True)

    async def populate_sid_cache(self, guild_id: int) -> list:
        """Populates a guilds current active suggestion ids"""
        self.autocomplete_cache.delete_entry(guild_id)
        data: List[Dict] = await self.database.suggestions.find_many(
            AQ(AND(EQ("guild_id", guild_id), EQ("state", "pending"))),
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        data: List[str] = [d["_id"] for d in data]

        queued_data: List[Dict] = await self.database.queued_suggestions.find_many(
            AQ(
                AND(EQ("guild_id", guild_id), Negate(Exists("resolved_at"))),
            ),
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        queued_data: List[str] = [
            d["_id"] for d in queued_data if isinstance(d["_id"], str)
        ]
        data.extend(queued_data)

        self.autocomplete_cache.add_entry(guild_id, data, override=True)
        logger.debug(
            "Populated sid cache for guild %s",
            guild_id,
            extra_metadata={"guild_id": guild_id},
        )
        return data

    async def populate_view_voters_cache(self, guild_id: int) -> list:
        self.view_voters_cache.delete_entry(guild_id)
        data: List[Dict] = await self.database.suggestions.find_many(
            AQ(AND(EQ("guild_id", guild_id), Negate(EQ("state", "cleared")))),
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        data: List[str] = [d["_id"] for d in data]
        self.view_voters_cache.add_entry(guild_id, data, override=True)
        logger.debug(
            "Populated view voter cache for guild %s",
            guild_id,
            extra_metadata={"guild_id": guild_id},
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
            self.autocomplete_cache.add_entry(guild_id, current_values, override=True)

        logger.debug(
            "Added sid %s to cache for guild %s",
            suggestion_id,
            guild_id,
            extra_metadata={"guild_id": guild_id, "suggestion_id": suggestion_id},
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
                )
                logger.debug(
                    "Removed sid %s from the cache for guild %s",
                    suggestion_id,
                    guild_id,
                    extra_metadata={
                        "guild_id": guild_id,
                        "suggestion_id": suggestion_id,
                    },
                )

    async def load(self):
        task_1 = asyncio.create_task(self.evict_caches())
        self.add_background_task(task_1)

        # Populate existing suggestion id's
        suggestion_ids: List[Dict] = await self.suggestions_db.get_all(
            {},
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        for entry in suggestion_ids:
            self.existing_suggestion_ids.add(entry["_id"])

        suggestion_ids: List[Dict] = await self.queued_suggestions_db.get_all(
            {},
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        for entry in suggestion_ids:
            if isinstance(entry["_id"], str) and len(entry["_id"]) == 8:
                self.existing_suggestion_ids.add(entry["_id"])

        error_ids: List[Dict] = await self.bot.db.error_tracking.get_all(
            {},
            projections=PROJECTION(SHOW("_id")),
            try_convert=False,
        )
        for entry in error_ids:
            self.existing_error_ids.add(entry["_id"])

    async def fetch_channel(self, channel_id: int) -> disnake.TextChannel:
        try:
            return self.object_cache.get_entry(channel_id)
        except NonExistentEntry:
            chan = await self.bot.fetch_channel(channel_id)
            self.object_cache.add_entry(channel_id, chan)
            return chan  # type: ignore

    async def fetch_user(self, user_id: int) -> disnake.User:
        try:
            return self.object_cache.get_entry(user_id)
        except NonExistentEntry:
            user = await self.bot.fetch_user(user_id)
            self.object_cache.add_entry(user_id, user)
            return user

    async def fetch_guild(self, guild_id: int) -> disnake.Guild:
        # Need guild cache instead of object as used else where
        try:
            return self.guild_cache.get_entry(guild_id)
        except NonExistentEntry:
            guild = await self.bot.fetch_guild(guild_id)
            self.guild_cache.add_entry(guild_id, guild)
            return guild

    async def evict_caches(self):
        """Cleans the caches every 10 minutes"""
        while not self.is_closing:
            old_length = len(self.autocomplete_cache)
            self.autocomplete_cache.force_clean()
            if len(self.autocomplete_cache) != old_length:
                log.debug("Cleaned autocomplete caches")

            # This allows for immediate task finishing rather
            # than being forced to wait the whole 10 minutes
            # between loops for if we wish to gracefully close the task
            remaining_seconds = self.autocomplete_cache_ttl.total_seconds()
            while remaining_seconds > 0:
                remaining_seconds -= 5
                await asyncio.sleep(5)

                if self.is_closing:
                    return
