"""
This module is standalone for the bot but provides
useful insights and telemetry to repeated information.
"""
import asyncio
import shutil
from pathlib import Path

from dotenv import load_dotenv

from suggestions.telemetry.error_telemetry import *

load_dotenv()


async def main():
    # print(await error_telemetry())
    d = await unique_unhandled_errors()
    path = Path("./error_telemetry_tracebacks")
    shutil.rmtree(path.absolute())
    path.mkdir(parents=True, exist_ok=True)
    for error in d:
        with open(os.path.join(path, f"{error.id}.txt"), "w") as f:
            f.write(error.traceback)


asyncio.run(main())
