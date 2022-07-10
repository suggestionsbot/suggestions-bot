from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from suggestions import SuggestionsBot


class Emojis:
    """A class to put all emojis in one place."""

    thumbs_up = "👍"
    thumbs_down = "👎"
    tick = "<:nerdSuccess:605265580416565269>"
    cross = "<:nerdError:605265598343020545>"

    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot

    def default_up_vote(self):
        return self.tick if self.bot.is_prod else self.thumbs_up

    def default_down_vote(self):
        return self.cross if self.bot.is_prod else self.thumbs_down
