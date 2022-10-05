import asyncio
import logging

from bot_base import NonExistentEntry

from suggestions import State
from suggestions.clunk import ClunkCache, ClunkLock

log = logging.getLogger(__name__)


class Clunk:
    def __init__(self, state: State):
        self._state: State = state
        self._cache: ClunkCache[str, ClunkLock] = ClunkCache(lazy_eviction=False)

    def acquire(self, suggestion_id: str, is_up_vote: bool = True) -> ClunkLock:
        key = f"{suggestion_id}{is_up_vote}"
        try:
            return self._cache.get_entry(key)
        except NonExistentEntry:
            log.debug("Acquired new ClunkLock for (%s, %s)", suggestion_id, is_up_vote)
            lock = ClunkLock(self._state)
            self._cache.add_entry(key, lock)
            return lock

    async def kill_all(self) -> None:
        """Kill all current ClunkLock instances."""
        iters = [c.value.kill() for c in self._cache.cache.values()]
        await asyncio.gather(*iters)
