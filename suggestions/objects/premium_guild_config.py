from __future__ import annotations

import typing
from typing import Optional

import logoo
from alaric import AQ
from alaric.comparison import EQ
from commons.caching import NonExistentEntry

if typing.TYPE_CHECKING:
    from suggestions import State

logger = logoo.Logger(__name__)


class PremiumGuildConfig:
    __slots__ = ["_id", "suggestions_prefix", "queued_suggestions_prefix"]

    def __init__(
        self,
        _id: int,
        suggestions_prefix: str = "",
        queued_suggestions_prefix: str = "",
    ):
        self._id = _id
        self.suggestions_prefix = suggestions_prefix
        self.queued_suggestions_prefix = queued_suggestions_prefix

    def as_dict(self):
        return {
            "_id": self._id,
            "suggestions_prefix": self.suggestions_prefix,
            "queued_suggestions_prefix": self.queued_suggestions_prefix,
        }

    def as_filter(self):
        return {"_id": self._id}

    def __repr__(self):
        return f"PremiumGuildConfig({self.as_dict()})"

    @property
    def guild_id(self) -> int:
        return self._id

    @classmethod
    async def from_id(cls, guild_id: int, state: State) -> PremiumGuildConfig:
        """Returns a valid PremiumGuildConfig instance from an id.

        Parameters
        ----------
        guild_id: int
            The guild we want
        state: State
            Internal state to marshall data

        Returns
        -------
        PremiumGuildConfig
            The valid guilds config
        """
        try:
            gc = state.premium_guild_configs.get_entry(guild_id)
            logger.debug(
                "Found cached PremiumGuildConfig for guild %s",
                guild_id,
                extra_metadata={"guild_id": guild_id},
            )
            return gc
        except NonExistentEntry:
            pass

        guild_config: Optional[PremiumGuildConfig] = (
            await state.premium_guild_config_db.find(AQ(EQ("_id", guild_id)))
        )
        if not guild_config:
            logger.info(
                "Created new PremiumGuildConfig for %s",
                guild_id,
                extra_metadata={"guild_id": guild_id},
            )
            guild_config = cls(_id=guild_id)

        state.refresh_premium_guild_config(guild_config)
        return guild_config
