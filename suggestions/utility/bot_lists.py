import asyncio
import logging

import httpx

from suggestions import constants

log = logging.getLogger(__name__)


async def update_top_gg(
    client: httpx.AsyncClient, *, guild_count: int, total_shards: int
):
    resp = await client.post(
        "https://top.gg/api/bots/474051954998509571/stats",
        headers={"Authorization": f"Bearer {constants.LISTS_TOP_GG_API_KEY}"},
        json={"server_count": guild_count, "shard_count": total_shards},
    )
    if resp.status_code != 200:
        log.critical(
            "Top.gg bot stats update failed with code %s",
            resp.status_code,
            extra={"response.body": resp.text},
        )


async def update_discord_bots_gg(
    client: httpx.AsyncClient, *, guild_count: int, total_shards: int
):
    resp = await client.post(
        "https://discord.bots.gg/api/v1/bots/474051954998509571/stats",
        headers={"Authorization": constants.LISTS_DISCORD_BOTS_GG_API_KEY},
        json={"guildCount": guild_count, "shardCount": total_shards},
    )
    if resp.status_code != 200:
        log.critical(
            "discord.bots.gg bot stats update failed with code %s",
            resp.status_code,
            extra={"response.body": resp.text},
        )


async def update_discord_bot_list(client: httpx.AsyncClient, *, guild_count: int):
    resp = await client.post(
        "https://discordbotlist.com/api/v1/bots/474051954998509571/stats",
        headers={"Authorization": constants.LISTS_DISCORDBOTLIST_API_KEY},
        json={"guilds": guild_count},
    )
    if resp.status_code != 200:
        log.critical(
            "discordbotlist.com bot stats update failed with code %s",
            resp.status_code,
            extra={"response.body": resp.text},
        )


async def main():
    async with httpx.AsyncClient() as client:
        await update_discord_bot_list(client, guild_count=87500)


if __name__ == "__main__":
    asyncio.run(main())
