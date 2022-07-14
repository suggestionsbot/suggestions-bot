from datetime import datetime
from typing import List, Dict


class MemberCommandStats:
    def __init__(
        self,
        command_name: str,
        *,
        completed_at: List[datetime] = None,
        failed_at: List[datetime] = None
    ):
        self.command_name: str = command_name
        self.completed_at: List[datetime] = completed_at if completed_at else []
        self.failed_at: List[datetime] = failed_at if failed_at else []

    @property
    def success_count(self) -> int:
        return len(self.completed_at)

    @property
    def failure_count(self) -> int:
        return len(self.failed_at)

    def as_data_dict(self) -> Dict:
        return {"completed_at": self.completed_at, "failed_at": self.failed_at}
