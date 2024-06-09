from __future__ import annotations

import typing

if typing.TYPE_CHECKING:
    from suggestions import SuggestionsBot


class BaseCore:
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
