from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import aiohttp

if TYPE_CHECKING:
    from suggestions import SuggestionsBot

log = logging.getLogger(__name__)


class Garven:
    def __init__(self, bot: SuggestionsBot):
        self._url = (
            "https://garven.suggestions.gg"
            if bot.is_prod
            else "https://garven.dev.suggestions.gg"
        )
        self._session: aiohttp.ClientSession = aiohttp.ClientSession(
            base_url=self._url,
            headers={"X-API-KEY": os.environ["GARVEN_API_KEY"]},
        )
        self.bot: SuggestionsBot = bot

    async def notify_devs(self, *, title: str, description: str, sender: str):
        async with self._session.post(
            "/cluster/notify_devs",
            json={
                "title": title,
                "description": description,
                "sender": sender,
            },
        ) as resp:
            if resp.status != 204:
                log.error(
                    "Error when attempting to notify devs\n\t- %s",
                    await resp.text(),
                )
