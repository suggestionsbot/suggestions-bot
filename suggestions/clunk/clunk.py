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

    def acquire(self, suggestion_id: str) -> ClunkLock:
        key = suggestion_id
        try:
            return self._cache.get_entry(key)
        except NonExistentEntry:
            lock = ClunkLock(self._state)
            self._cache.add_entry(key, lock)
            return lock

    async def kill_all(self) -> None:
        """Kill all current ClunkLock instances."""
        for lock in self._cache.cache.values():
            lock.value.kill()
