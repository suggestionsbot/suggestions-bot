import asyncio
import logging
import os

import alaric
from alaric import Cursor
from dotenv import load_dotenv
from logoo import PrimaryLogger


import suggestions

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-8s | %(asctime)s | %(filename)19s:%(funcName)-27s | %(message)s",
    datefmt="%d/%m/%Y %I:%M:%S %p",
)
# logging.getLogger("asyncio").setLevel(logging.DEBUG)

disnake_logger = logging.getLogger("disnake")
disnake_logger.setLevel(logging.INFO)
gateway_logger = logging.getLogger("disnake.gateway")
gateway_logger.setLevel(logging.WARNING)
client_logger = logging.getLogger("disnake.client")
client_logger.setLevel(logging.WARNING)
http_logger = logging.getLogger("disnake.http")
http_logger.setLevel(logging.WARNING)
shard_logger = logging.getLogger("disnake.shard")
shard_logger.setLevel(logging.WARNING)

httpx_logger = logging.getLogger("httpx")
httpx_logger.setLevel(logging.WARNING)

logoo_logger = logging.getLogger("logoo")
logoo_logger.setLevel(logging.INFO)

suggestions_logger = logging.getLogger("suggestions")
suggestions_logger.setLevel(logging.DEBUG)
member_stats_logger = logging.getLogger("suggestions.objects.stats.member_stats")
member_stats_logger.setLevel(logging.INFO)


async def run_bot():
    # tracemalloc.start()
    log = logging.getLogger(__name__)
    bot = await suggestions.create_bot()

    logger: PrimaryLogger = PrimaryLogger(
        __name__,
        base_url="https://logs.suggestions.gg",
        org="default",
        stream="prod_bot" if bot.is_prod else "test_bot",
        username=os.environ["LOGOO_USER"],
        password=os.environ["LOGOO_PASSWORD"],
        poll_time=15,
        global_metadata={
            "cluster": bot.cluster_id,
            "bot_version": bot.version,
        },
    )
    await logger.start_consumer()

    # Make sure we don't shutdown due to a previous shutdown request
    cursor: Cursor = (
        Cursor.from_document(bot.db.cluster_shutdown_requests)
        .set_sort(("timestamp", alaric.Descending))
        .set_limit(1)
    )
    items = await cursor.execute()
    if items:
        entry = items[0]
        if bot.cluster_id not in entry["responded_clusters"]:
            entry["responded_clusters"].append(bot.cluster_id)
            await bot.db.cluster_shutdown_requests.upsert({"_id": entry["_id"]}, entry)
            log.debug("Marked old shutdown request as satisfied")

    await bot.load()
    TOKEN = os.environ["PROD_TOKEN"] if bot.is_prod else os.environ["TOKEN"]

    log.info("About to start SuggestionsBot | %s", bot.version)
    log.info("We are in prod" if bot.is_prod else "We are launching in non-prod")
    await bot.start(TOKEN)


asyncio.run(run_bot())
