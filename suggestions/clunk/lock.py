import asyncio
from typing import Coroutine

from suggestions import State


class ClunkLock:
    """Custom request processing for the 21st century.

    Example:

    We need to edit a message 9 times.
    Each time the message is edited we simply increment a counter.

    For bulk operations this causes rate-limits to be hit
    as we process the edits one by one until we exhaust the requests.

    Given a FIFO queue however, we can in theory skip requests
    to reduce the amount of edits required to reach the same result.

    For example, the below two approaches would result in the same
    output for the end user but the proposed design would only
    make two requests instead of the nine requests it currently takes
    which should alleviate errors we run into due to rate-limits.

    Currently:
    +---+---+---+---+---+---+---+---+---+
    | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 |
    +---+---+---+---+---+---+---+---+---+

    Proposed:
    +---+---+
    | 1 | 9 |
    +---+---+

    Find the generic version here: https://workbin.dev/?id=1664955297537152
    """

    def __init__(self, state: State):
        self._state: State = state
        self.__killed: bool = False
        self.is_currently_running: bool = False
        self._next_request: Coroutine | None = None
        self._event: asyncio.Event = asyncio.Event()
        self._current_request: Coroutine | None = None

    @property
    def has_requests(self) -> None:
        return self._current_request is not None

    @property
    def __is_closing(self) -> bool:
        return self._state.is_closing or self.__killed

    async def wait(self) -> None:
        """Block until all requests are processed."""
        while self.has_requests:
            await asyncio.sleep(0)

    async def kill(self) -> None:
        """Kill any current requests inline with a graceful shutdown."""
        self.__killed = True
        if not self._event.is_set():
            self._event.set()

    async def run(self) -> None:
        """Begin processing the queue in the background.

        Notes
        -----
        The program lifetime must be longer then the
        lifetime of the tasks enqueued otherwise tasks
        may fail to be awaited before the program dies.
        """
        if self.is_currently_running:
            return

        asyncio.create_task(self._run())
        self.is_currently_running = True

    async def _run(self) -> None:
        while not self.__is_closing:
            await self._event.wait()
            if self.__is_closing:
                break

            await self._current_request

            if self._next_request:
                self._current_request = self._next_request
                self._next_request = None
            else:
                self._current_request = None
                self._event.clear()

        self.is_currently_running = False
        # Cancel any remaining coros to supress
        # warnings since we want to shut this down
        if self._current_request:
            asyncio.create_task(self._current_request).cancel()
        if self._next_request:
            asyncio.create_task(self._next_request).cancel()

    def enqueue(self, request: Coroutine) -> None:
        """Add a request to the queue for processing

        Parameters
        ----------
        request: Coroutine
            The request to queue for processing
        """
        if self._current_request:
            # We are already processing a request
            # so queue this for future running
            if self._next_request:
                # Cancel the old coroutine to supress warnings
                # about 'func' was never awaited
                asyncio.create_task(self._next_request).cancel()
            self._next_request = request
        else:
            # We aren't processing any requests
            # so queue this for immediate running
            self._current_request = request
            self._event.set()
