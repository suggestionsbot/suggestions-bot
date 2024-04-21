"""
This module is standalone for the bot but provides
useful insights and telemetry to repeated information.
"""

import asyncio
import shutil
from pathlib import Path

from dotenv import load_dotenv

from suggestions.objects import GuildConfig
from suggestions.telemetry.error_telemetry import *

load_dotenv()

client = AsyncIOMotorClient(os.environ["PROD_MONGO_URL"])
database = client["suggestions-rewrite"]
error_tracking_document = Document(database, "error_tracking")
guild_configs_document = Document(database, "guild_configs", converter=GuildConfig)


async def load_unhandled_errors():
    d = await unique_unhandled_errors()
    path = Path("./error_telemetry_tracebacks")
    try:
        shutil.rmtree(path.absolute())
    except FileNotFoundError:
        pass
    path.mkdir(parents=True, exist_ok=True)
    for error in d:
        with open(os.path.join(path, f"{error.id}.txt"), "w") as f:
            f.write(error.traceback)


async def load_forbidden():
    d = await get_unique_forbidden()
    path = Path("./forbidden_errors")
    try:
        shutil.rmtree(path.absolute())
    except FileNotFoundError:
        pass
    path.mkdir(parents=True, exist_ok=True)
    for error in d:
        with open(os.path.join(path, f"{error.id}.txt"), "w") as f:
            f.write(error.traceback)


async def mark_forbidden_done():
    for item in await get_unique_forbidden():
        item.has_been_fixed = True
        await error_tracking_document.update(item, item)


async def count_with_queues():
    totla = await guild_configs_document.count(AQ(EQ("uses_suggestion_queue", True)))
    print(totla)


async def main():
    await count_with_queues()


asyncio.run(main())
