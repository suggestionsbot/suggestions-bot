import asyncio
import logging
import os

import alaric
from alaric import Cursor
from dotenv import load_dotenv

import suggestions
from suggestions import constants

load_dotenv()

constants.configure_otel()
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

suggestions_logger = logging.getLogger("suggestions")
suggestions_logger.setLevel(logging.DEBUG)
member_stats_logger = logging.getLogger("suggestions.objects.stats.member_stats")
member_stats_logger.setLevel(logging.INFO)


async def run_bot():
    # tracemalloc.start()
    log = logging.getLogger(__name__)
    bot = await suggestions.create_bot()

    await bot.load()
    TOKEN = os.environ["PROD_TOKEN"] if bot.is_prod else os.environ["TOKEN"]

    log.info("About to start SuggestionsBot | %s", bot.version)
    log.info("We are in prod" if bot.is_prod else "We are launching in non-prod")
    await bot.start(TOKEN)


asyncio.run(run_bot())
