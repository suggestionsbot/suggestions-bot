from __future__ import annotations

import os
from typing import TYPE_CHECKING

from zonis import client

from suggestions.scheduler import exception_aware_scheduler

if TYPE_CHECKING:
    from suggestions import SuggestionsBot


class ZonisRoutes:
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        url = (
            "wss://garven.suggestions.gg/ws"
            if self.bot.is_prod
            else "wss://garven.dev.suggestions.gg/ws"
        )
        self.client: client.Client = client.Client(
            url=url,
            identifier=str(bot.cluster_id),
            secret_key=os.environ["ZONIS_SECRET_KEY"],
            override_key=os.environ.get("ZONIS_OVERRIDE_KEY"),
        )
        self.client.register_class_instance_for_routes(self, "guild_count")

    async def start(self):
        self.client.load_routes()
        await exception_aware_scheduler(
            self.client._connect, retry_count=5, sleep_between_tries=30
        )

    @client.route()
    async def guild_count(self):
        return len(self.bot.guilds)
