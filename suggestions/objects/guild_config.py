from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from alaric import AQ
from alaric.comparison import EQ
from commons.caching import NonExistentEntry
from logoo import Logger

if TYPE_CHECKING:
    from suggestions import State

logger = Logger(__name__)


class GuildConfig:
    def __init__(
        self,
        _id: int,
        keep_logs: bool = False,
        dm_messages_disabled: bool = False,
        log_channel_id: Optional[int] = None,
        queued_channel_id: Optional[int] = None,
        queued_log_channel_id: Optional[int] = None,
        threads_for_suggestions: bool = True,
        suggestions_channel_id: Optional[int] = None,
        can_have_anonymous_suggestions: bool = False,
        auto_archive_threads: bool = False,
        uses_suggestion_queue: bool = False,
        virtual_suggestion_queue: bool = True,
        can_have_images_in_suggestions: bool = True,
        anonymous_resolutions: bool = False,
        blocked_users: Optional[list[int]] = None,
        ping_on_thread_creation: bool = True,
        **kwargs,
    ):
        self._id: int = _id
        self.keep_logs: bool = keep_logs
        self.log_channel_id: Optional[int] = log_channel_id
        self.queued_channel_id: Optional[int] = queued_channel_id
        self.queued_log_channel_id: Optional[int] = queued_log_channel_id
        self.auto_archive_threads: bool = auto_archive_threads
        self.dm_messages_disabled: bool = dm_messages_disabled
        self.anonymous_resolutions: bool = anonymous_resolutions
        self.uses_suggestion_queue: bool = uses_suggestion_queue
        self.threads_for_suggestions: bool = threads_for_suggestions
        self.ping_on_thread_creation: bool = ping_on_thread_creation
        self.virtual_suggestion_queue: bool = virtual_suggestion_queue
        self.suggestions_channel_id: Optional[int] = suggestions_channel_id
        self.can_have_anonymous_suggestions: bool = can_have_anonymous_suggestions
        self.can_have_images_in_suggestions: bool = can_have_images_in_suggestions

        if blocked_users is None:
            blocked_users = set()
        self.blocked_users: set[int] = set(blocked_users)

    @property
    def guild_id(self) -> int:
        return self._id

    @classmethod
    async def from_id(cls, guild_id: int, state: State) -> GuildConfig:
        """Returns a valid GuildConfig instance from an id.

        Parameters
        ----------
        guild_id: int
            The guild we want
        state: State
            Internal state to marshall data

        Returns
        -------
        GuildConfig
            The valid guilds config
        """
        try:
            gc = state.guild_configs.get_entry(guild_id)
            logger.debug(
                "Found cached GuildConfig for guild %s",
                guild_id,
                extra_metadata={"guild_id": guild_id},
            )
            return gc
        except NonExistentEntry:
            pass

        guild_config: Optional[GuildConfig] = await state.guild_config_db.find(
            AQ(EQ("_id", guild_id))
        )
        if not guild_config:
            logger.info(
                "Created new GuildConfig for %s",
                guild_id,
                extra_metadata={"guild_id": guild_id},
            )
            guild_config = cls(_id=guild_id)

        state.refresh_guild_config(guild_config)
        return guild_config

    def as_dict(self) -> Dict:
        return {
            "_id": self.guild_id,
            "keep_logs": self.keep_logs,
            "blocked_users": list(self.blocked_users),
            "log_channel_id": self.log_channel_id,
            "queued_channel_id": self.queued_channel_id,
            "queued_log_channel_id": self.queued_log_channel_id,
            "auto_archive_threads": self.auto_archive_threads,
            "dm_messages_disabled": self.dm_messages_disabled,
            "suggestions_channel_id": self.suggestions_channel_id,
            "ping_on_thread_creation": self.ping_on_thread_creation,
            "uses_suggestion_queue": self.uses_suggestion_queue,
            "anonymous_resolutions": self.anonymous_resolutions,
            "virtual_suggestion_queue": self.virtual_suggestion_queue,
            "threads_for_suggestions": self.threads_for_suggestions,
            "can_have_anonymous_suggestions": self.can_have_anonymous_suggestions,
            "can_have_images_in_suggestions": self.can_have_images_in_suggestions,
        }

    def as_filter(self) -> Dict:
        return {"_id": self.guild_id}

    def __repr__(self):
        return f"GuildConfig({self.as_dict()})"
