import datetime


class Error:
    def __init__(
        self,
        _id: str,
        traceback: str,
        error: str,
        user_id: int,
        guild_id: int,
        command_name: str,
        cluster_id: int,
        shard_id: int,
        created_at: datetime.datetime,
    ):
        self._id: str = _id
        self.error: str = error
        self.user_id: int = user_id
        self.guild_id: int = guild_id
        self.shard_id: int = shard_id
        self.traceback: str = traceback
        self.cluster_id: int = cluster_id
        self.command_name: str = command_name
        self.created_at: datetime.datetime = created_at

    @property
    def id(self) -> str:
        return self._id

    def as_filter(self) -> dict:
        return {"_id": self._id}

    def as_dict(self) -> dict:
        return {
            "_id": self._id,
            "error": self.error,
            "user_id": self.user_id,
            "guild_id": self.guild_id,
            "shard_id": self.shard_id,
            "traceback": self.traceback,
            "cluster_id": self.cluster_id,
            "command_name": self.command_name,
            "created_at": self.created_at,
        }
