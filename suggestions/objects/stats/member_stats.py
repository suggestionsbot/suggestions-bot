from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from bot_base import NonExistentEntry

from .member_command_stats import MemberCommandStats

if TYPE_CHECKING:
    from suggestions import State, Stats

log = logging.getLogger(__name__)


class MemberStats:
    def __init__(
        self,
        member_id: int,
        guild_id: int,
        commands: Dict[str, Dict[str, List[datetime]]] = None,
        **kwargs,
    ):
        self.member_id: int = member_id
        self.guild_id: int = guild_id
        self._fields: List[str] = [
            "suggest",
            "approve",
            "reject",
            "clear",
            "member_dm_view",
            "member_dm_enable",
            "member_dm_disable",
            "guild_config_log_channel",
            "guild_config_suggest_channel",
            "guild_config_get",
            "guild_dm_enable",
            "guild_dm_disable",
            "guild_thread_enable",
            "guild_thread_disable",
            "guild_keeplogs_enable",
            "guild_keeplogs_disable",
            "guild_auto_archive_threads_enable",
            "guild_auto_archive_threads_disable",
            "activate_beta",
            "stats",
            "approve_by_message_command",
            "reject_by_message_command",
            "guild_anonymous_enable",
            "guild_anonymous_disable",
            "view_up_voters",
            "view_down_voters",
            "view_voters",
        ]

        if commands:
            for k, v in commands.items():
                setattr(self, k, MemberCommandStats(k, **v))
        else:
            self._build_default_commands_dict()

        if TYPE_CHECKING:
            self.suggest: MemberCommandStats = ...
            self.approve: MemberCommandStats = ...
            self.approve_by_message_command: MemberCommandStats = ...
            self.reject: MemberCommandStats = ...
            self.reject_by_message_command: MemberCommandStats = ...
            self.member_dm_view: MemberCommandStats = ...
            self.member_dm_enable: MemberCommandStats = ...
            self.member_dm_disable: MemberCommandStats = ...
            self.guild_config_log_channel: MemberCommandStats = ...
            self.guild_config_suggest_channel: MemberCommandStats = ...
            self.guild_config_get: MemberCommandStats = ...
            self.guild_dm_enable: MemberCommandStats = ...
            self.guild_dm_disable: MemberCommandStats = ...
            self.guild_thread_enable: MemberCommandStats = ...
            self.guild_thread_disable: MemberCommandStats = ...
            self.guild_anonymous_enable: MemberCommandStats = ...
            self.guild_anonymous_disable: MemberCommandStats = ...
            self.activate_beta: MemberCommandStats = ...
            self.stats: MemberCommandStats = ...

    @property
    def valid_fields(self) -> List[str]:
        return self._fields

    def _build_default_commands_dict(self) -> None:
        for command_name in self._fields:
            setattr(self, command_name, MemberCommandStats(command_name))

    @classmethod
    async def from_id(cls, member_id: int, guild_id: int, state: State) -> MemberStats:
        key = f"{member_id}|{guild_id}"
        stats: Stats = state.bot.stats
        try:
            return stats.member_stats_cache.get_entry(key)
        except NonExistentEntry:
            pass

        member_stats: Optional[MemberStats] = await state.database.member_stats.find(
            AQ(AND(EQ("member_id", member_id), EQ("guild_id", guild_id)))
        )
        if member_stats:
            stats.refresh_member_stats(member_stats)
            return member_stats

        log.debug(
            "Getting fresh MemberStats object for %s in guild %s",
            member_id,
            guild_id,
        )
        instance = cls(member_id, guild_id)
        stats.refresh_member_stats(instance)
        return instance

    def as_filter(self) -> Dict:
        return {"member_id": self.member_id, "guild_id": self.guild_id}

    def as_dict(self) -> Dict:
        data = {"member_id": self.member_id, "guild_id": self.guild_id}
        commands = {}
        for field in self._fields:
            instance: MemberCommandStats = getattr(
                self, field, MemberCommandStats(field)
            )
            commands[field] = instance.as_data_dict()

        data["commands"] = commands
        return data

    def __repr__(self):
        return f"MemberStats(member_id={self.member_id}, guild_id={self.guild_id})"
