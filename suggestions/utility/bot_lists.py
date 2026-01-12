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


async def main():
    async with httpx.AsyncClient() as client:
        await update_top_gg(client, guild_count=87500, total_shards=78)


if __name__ == "__main__":
    asyncio.run(main())
