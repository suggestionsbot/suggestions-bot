from typing import Protocol, runtime_checkable


@runtime_checkable
class ObjectT(Protocol):
    def as_dict(self) -> dict:
        ...
