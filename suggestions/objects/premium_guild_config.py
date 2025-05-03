from __future__ import annotations

import typing
from datetime import timedelta
from enum import Enum
from typing import Optional

import logoo
from alaric import AQ
from alaric.comparison import EQ
from commons.caching import NonExistentEntry

if typing.TYPE_CHECKING:
    from suggestions import State

logger = logoo.Logger(__name__)


class CooldownPeriod(str, Enum):
    Hour = "Hour"
    Day = "Day"
    Week = "Week"
    Fortnight = "Fortnight"
    Month = "Month"

    def as_timedelta(self) -> timedelta:
        if self is self.Hour:
            return timedelta(hours=1)
        elif self is self.Day:
            return timedelta(days=1)
        elif self is self.Week:
            return timedelta(weeks=1)
        elif self is self.Fortnight:
            return timedelta(weeks=2)
        elif self is self.Month:
            return timedelta(weeks=4)
        else:
            raise NotImplementedError


class PremiumGuildConfig:
    __slots__ = [
        "_id",
        "suggestions_prefix",
        "queued_suggestions_prefix",
        "cooldown_period",
        "cooldown_amount",
    ]

    def __init__(
        self,
        _id: int,
        cooldown_amount: int = None,
        cooldown_period: str | CooldownPeriod = None,
        suggestions_prefix: str = "",
        queued_suggestions_prefix: str = "",
    ):
        self._id = _id
        self.cooldown_period = (
            CooldownPeriod[cooldown_period]
            if isinstance(cooldown_period, str)
            else cooldown_period
        )
        self.cooldown_amount = cooldown_amount
        self.suggestions_prefix = suggestions_prefix
        self.queued_suggestions_prefix = queued_suggestions_prefix

    def as_dict(self):
        return {
            "_id": self._id,
            "suggestions_prefix": self.suggestions_prefix,
            "queued_suggestions_prefix": self.queued_suggestions_prefix,
            "cooldown_period": self.cooldown_period,
            "cooldown_amount": self.cooldown_amount,
        }

    def as_filter(self):
        return {"_id": self._id}

    def __repr__(self):
        return f"PremiumGuildConfig({self.as_dict()})"

    @property
    def guild_id(self) -> int:
        return self._id

    @classmethod
    async def from_id(self, guild_id: int, state: State) -> PremiumGuildConfig:
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
        guild_config: Optional[PremiumGuildConfig] = (
            await state.premium_guild_config_db.find(AQ(EQ("_id", guild_id)))
        )
        if not guild_config:
            logger.info(
                "Created new PremiumGuildConfig for %s",
                guild_id,
                extra_metadata={"guild_id": guild_id},
            )
            guild_config = self(_id=guild_id)

        return guild_config
