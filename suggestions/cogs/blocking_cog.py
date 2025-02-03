import sys
import time
import asyncio
import threading
import traceback
import concurrent.futures

import disnake
import logoo
from disnake.ext import commands

log = logoo.Logger(__name__)


# https://gist.github.com/imayhaveborkedit/97ccc3fd654873b7b0c1540c94b5a069
class BlockingMonitor(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.monitor_thread = StackMonitor(bot)
        self.monitor_thread.start()

    def cog_unload(self):
        self.monitor_thread.stop()

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    @commands.contexts(guild=True)
    async def bmon(self, inter): ...

    @bmon.sub_command()
    async def stop(self, inter):
        if not self.monitor_thread:
            return await inter.send("Not running monitor")

        self.monitor_thread.stop()
        self.monitor_thread = None
        return await inter.send("Stopped")

    @bmon.sub_command()
    async def start(self, inter):
        if self.monitor_thread:
            return await inter.send("Already running")

        self.monitor_thread = StackMonitor(self.bot)
        self.monitor_thread.start()
        return await inter.send("Started")


class StackMonitor(threading.Thread):
    def __init__(self, bot, block_threshold=1, check_freq=2):
        super().__init__(
            name=f"{type(self).__name__}-{threading._counter()}", daemon=True
        )

        self.bot = bot
        self._do_run = threading.Event()
        self._do_run.set()

        self.block_threshold = block_threshold
        self.check_frequency = check_freq

        self.last_stack = None
        self.still_blocked = False
        self._last_frame = None

    @staticmethod
    async def dummy_coro():
        return True

    def test_loop_availability(self):
        t0 = time.perf_counter()
        fut = asyncio.run_coroutine_threadsafe(self.dummy_coro(), self.bot.loop)
        t1 = time.perf_counter()

        try:
            fut.result(self.block_threshold)
            t2 = time.perf_counter()
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError):
            t2 = time.perf_counter()

            frame = sys._current_frames()[self.bot.loop._thread_id]
            stack = traceback.format_stack(frame)

            if (
                stack == self.last_stack
                and frame is self._last_frame
                and frame.f_lasti == self._last_frame.f_lasti
            ):

                self.still_blocked = True
                print("Still blocked...")
                return
            else:
                self.still_blocked = False

            print(f"Future took longer than {self.block_threshold}s to return")
            print("".join(stack))
            log.critical(
                f"Future took longer than {self.block_threshold}s to return",
                extra_metadata={"stack": "".join(stack)},
            )

            self.last_stack = stack
            self._last_frame = frame

        else:
            if self.still_blocked:
                print("No longer blocked")
                self.still_blocked = False

            self.last_stack = None
            return t2 - t1

    def run(self):
        while self._do_run.is_set():
            if self.bot.loop.is_running():
                self.test_loop_availability()
            time.sleep(self.check_frequency)

    def stop(self):
        self._do_run.clear()


def setup(bot):
    bot.add_cog(BlockingMonitor(bot))
