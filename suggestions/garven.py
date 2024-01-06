from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

import aiohttp

from suggestions.exceptions import PartialResponse

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
        self._ws_url = (
            "wss://garven.suggestions.gg/ws"
            if bot.is_prod
            else "wss://garven.dev.suggestions.gg/ws"
        )
        self._session: aiohttp.ClientSession = aiohttp.ClientSession(
            base_url=self._url,
            headers={"X-API-KEY": os.environ["GARVEN_API_KEY"]},
        )
        self.bot: SuggestionsBot = bot

    @property
    def http_url(self) -> str:
        return self._url

    @property
    def ws_url(self) -> str:
        return self._ws_url

    @staticmethod
    async def _handle_status(resp: aiohttp.ClientResponse):
        if resp.status > 299:
            raise ValueError(f"Garven route failed {resp.url}")

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

    async def get_shard_info(self, guild_id: int) -> dict[str, str]:
        async with self._session.get(
            f"/aggregate/guilds/{guild_id}/shard_info"
        ) as resp:
            await self._handle_status(resp)
            data = await resp.json()
            return data

    async def get_total_guilds(self) -> int:
        async with self._session.get("/aggregate/guilds/count") as resp:
            await self._handle_status(resp)
            data = await resp.json()
            if data["partial_response"]:
                log.warning("get_total_guilds returned a partial response")
                raise PartialResponse

            return data["statistic"]
