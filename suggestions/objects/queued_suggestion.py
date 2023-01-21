from __future__ import annotations

import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from suggestions import State


class QueuedSuggestion:
    def __init__(
        self,
        guild_id: int,
        suggestion: str,
        suggestion_author_id: int,
        created_at: datetime.datetime,
        *,
        _id: Optional[str] = None,
        is_anonymous: bool = False,
        still_in_queue: bool = True,
        image_url: Optional[str] = None,
        resolved_by: Optional[int] = None,
        resolution_note: Optional[str] = None,
        resolved_at: Optional[datetime.datetime] = None,
    ):
        self._id: str = _id
        self.guild_id: int = guild_id
        self.suggestion: str = suggestion
        self.is_anonymous: bool = is_anonymous
        self.still_in_queue: bool = still_in_queue
        self.image_url: Optional[str] = image_url
        self.resolved_by: Optional[int] = resolved_by
        self.created_at: datetime.datetime = created_at
        self.suggestion_author_id: int = suggestion_author_id
        # For example saying why it didn't get approved
        self.resolution_note: Optional[str] = resolution_note
        self.resolved_at: Optional[datetime.datetime] = resolved_at

    @classmethod
    async def new(
        cls,
        suggestion: str,
        guild_id: int,
        author_id: int,
        state: State,
        *,
        image_url: Optional[str] = None,
        is_anonymous: bool = False,
    ) -> QueuedSuggestion:
        """Create and return a new valid suggestion.

        Parameters
        ----------
        suggestion: str
            The suggestion content
        guild_id: int
            The guild to attach the suggestion to
        author_id: int
            Who created the suggestion
        state: State
            A back-ref to insert into the database
        image_url: Optional[str]
            An image to attach to this suggestion.
        is_anonymous: bool
            Whether this suggestion should be anonymous

        Returns
        -------
        Suggestion
            A valid suggestion.
        """
        suggestion: QueuedSuggestion = QueuedSuggestion(
            guild_id=guild_id,
            suggestion=suggestion,
            suggestion_author_id=author_id,
            created_at=state.now,
            image_url=image_url,
            is_anonymous=is_anonymous,
        )
        await state.queued_suggestions_db.insert(suggestion)
        return suggestion

    def as_filter(self) -> dict:
        if not self._id:
            raise ValueError(
                "This queued suggestion doesn't have an attached database id."
            )

        return {"_id": self._id}

    def as_dict(self) -> dict:
        data = {
            "guild_id": self.guild_id,
            "created_at": self.created_at,
            "suggestion": self.suggestion,
            "is_anonymous": self.is_anonymous,
            "still_in_queue": self.still_in_queue,
            "suggestion_author_id": self.suggestion_author_id,
        }

        if self._id:
            data["_id"] = self._id

        if self.resolved_by:
            data["resolved_by"] = self.resolved_by
            data["resolved_at"] = self.resolved_at

        if self.resolution_note:
            data["resolution_note"] = self.resolution_note

        if self.image_url is not None:
            data["image_url"] = self.image_url

        return data
