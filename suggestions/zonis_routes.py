from __future__ import annotations

import logging
import math
import os
from typing import TYPE_CHECKING

import disnake
from zonis import client

from suggestions.scheduler import exception_aware_scheduler

if TYPE_CHECKING:
    from suggestions import SuggestionsBot

log = logging.getLogger(__name__)


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
        self.client.register_class_instance_for_routes(
            self,
            "guild_count",
            "cluster_status",
            "share_with_devs",
            "refresh_premium",
            "shared_guilds",
        )

    async def start(self):
        self.client.load_routes()
        await exception_aware_scheduler(
            self.client._connect,
            retry_count=100,  # Just over 4 hours of retries
            sleep_between_tries=150,  # 2.5 minutes between each
        )

    @client.route()
    async def guild_count(self):
        return len(self.bot.guild_ids)

    @client.route()
    async def cluster_status(self):
        data = {"shards": {}}
        for shard_id, shard_info in self.bot.shards.items():
            data["shards"][shard_id] = {
                "latency": shard_info.latency
                if not math.isnan(shard_info.latency)
                else None,
                "is_currently_up": not shard_info.is_closed(),
            }

        if all(d["is_currently_up"] is False for d in data["shards"].values()):
            data["cluster_is_up"] = False
        else:
            data["cluster_is_up"] = True

        return data

    @client.route()
    async def share_with_devs(self, title, description, sender):
        channel: disnake.TextChannel = await self.bot.get_or_fetch_channel(  # type: ignore
            602332642456764426
        )
        embed = disnake.Embed(
            title=title, description=description, timestamp=self.bot.state.now
        )
        embed.set_footer(text=f"Sender: {sender}")
        await channel.send(embed=embed)

    @client.route()
    async def refresh_premium(self, user_id: int):
        # TODO Implement the ability to refresh premium states for a user
        return True

    @client.route()
    async def shared_guilds(self, guild_ids: list[int]):
        return [gid for gid in guild_ids if gid in self.bot.guild_ids]
