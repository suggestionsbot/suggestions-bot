from bot_base.caches import TimedCache


class ClunkCache(TimedCache):
    def __contains__(self, item):
        try:
            entry = self.cache[item]
            if not entry.value.has_requests:
                entry.value.kill()
                self.cache.pop(item)
                return False
        except KeyError:
            return False
        else:
            return True

    def force_clean(self) -> None:
        items = {}
        for k, v in self.cache.items():
            if v.value.has_requests:
                items[k] = v
            else:
                v.value.kill()

        self.cache = items
