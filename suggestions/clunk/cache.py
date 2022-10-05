from bot_base.caches import TimedCache


class ClunkCache(TimedCache):
    def __contains__(self, item):
        try:
            entry = self.cache[item]
            if not entry.value.has_requests:
                self.delete_entry(item)
                return False
        except KeyError:
            return False
        else:
            return True

    def force_clean(self) -> None:
        self.cache = {k: v for k, v in self.cache.items() if v.value.has_requests}
