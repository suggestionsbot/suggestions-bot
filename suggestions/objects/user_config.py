from __future__ import annotations

import logging
from typing import Dict, TYPE_CHECKING, Optional

from alaric import AQ
from alaric.comparison import EQ

if TYPE_CHECKING:
    from suggestions import State

log = logging.getLogger(__name__)


class UserConfig:
    """Generic global user configuration"""

    def __init__(self, _id: int, dm_messages_disabled: bool = False):
        self._id: int = _id
        self.dm_messages_disabled: bool = dm_messages_disabled

    @classmethod
    async def from_id(cls, user_id: int, state: State):
        if user_id in state.user_configs:
            return state.user_configs[user_id]

        user_config: Optional[UserConfig] = await state.user_config_db.find(
            AQ(EQ("_id", user_id))
        )
        if not user_config:
            log.info("Created new UserConfig for %s", user_id)
            user_config = cls(_id=user_id)

        state.refresh_user_config(user_config)
        return user_config

    @property
    def user_id(self) -> int:
        return self._id

    def as_dict(self) -> Dict:
        return {"_id": self.user_id, "dm_messages_disabled": self.dm_messages_disabled}

    def as_filter(self) -> Dict:
        return {"_id": self.user_id}