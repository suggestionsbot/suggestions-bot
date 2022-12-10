import asyncio
import logging

log = logging.getLogger(__name__)


# Modified from https://stackoverflow.com/a/55185488
async def exception_aware_scheduler(
    callee,
    *args,
    retry_count: int = 1,
    sleep_between_tries: float | int = 0,
    **kwargs,
):
    async def inner_task(caller, *args, **kwargs):
        for _ in range(retry_count):
            done, pending = await asyncio.wait(
                [asyncio.create_task(caller(*args, **kwargs))],
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in done:
                if task.exception() is not None:
                    log.error("Task exited with exception:")
                    task.print_stack()

            await asyncio.sleep(sleep_between_tries)

    asyncio.create_task(inner_task(callee, *args, **kwargs))
