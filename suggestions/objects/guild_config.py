from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional

from alaric import AQ
from alaric.comparison import EQ

if TYPE_CHECKING:
    from suggestions import State

log = logging.getLogger(__name__)


class GuildConfig:
    def __init__(
        self,
        _id: int,
        log_channel_id: Optional[int] = None,
        suggestions_channel_id: Optional[int] = None,
        **kwargs,
    ):
        self._id: int = _id
        self.log_channel_id: Optional[int] = log_channel_id
        self.suggestions_channel_id: Optional[int] = suggestions_channel_id

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
        if guild_id in state.guilds_configs:
            return state.guilds_configs[guild_id]

        guild_config: Optional[GuildConfig] = await state.guild_config_db.find(
            AQ(EQ("_id", guild_id))
        )
        if not guild_config:
            log.info("Created new GuildConfig for %s", guild_id)
            return GuildConfig(_id=guild_id)

        return guild_config

    def as_dict(self) -> Dict:
        return {
            "_id": self.guild_id,
            "log_channel_id": self.log_channel_id,
            "suggestions_channel_id": self.suggestions_channel_id,
        }

    def as_filter(self) -> Dict:
        return {"_id": self.guild_id}
