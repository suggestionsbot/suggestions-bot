from typing import runtime_checkable, Protocol


@runtime_checkable
class Loadable(Protocol):
    async def load(self):
        ...
