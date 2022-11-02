from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suggestions import SuggestionsBot

log = logging.getLogger(__name__)


class Emojis:
    """A class to put all emojis in one place."""

    thumbs_up = "👍"
    thumbs_down = "👎"
    _tick = 605265580416565269  # "<:nerdSuccess:605265580416565269>"
    _cross = 605265598343020545  # "<:nerdError:605265598343020545>"
    tick = None
    cross = None

    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot

        if not self.bot.is_prod:
            # Use the emojis from the test guild
            self._tick = 756633653668479117
            self._cross = 756633653286797443

    async def populate_emojis(self):
        guild_id = self.bot.main_guild_id if self.bot.is_prod else 737166408525283348
        guild = await self.bot.fetch_guild(guild_id)
        self.tick = await guild.fetch_emoji(self._tick)
        self.cross = await guild.fetch_emoji(self._cross)
        log.info("Populated default emojis")

    async def default_up_vote(self):
        if not self.tick:
            await self.populate_emojis()

        return self.tick

    async def default_down_vote(self):
        if not self.cross:
            await self.populate_emojis()

        return self.cross
