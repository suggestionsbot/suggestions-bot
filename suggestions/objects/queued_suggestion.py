from __future__ import annotations

import datetime
from typing import Optional, TYPE_CHECKING

from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from disnake import Embed
from logoo import Logger

from suggestions.exceptions import UnhandledError, SuggestionNotFound
from suggestions.objects import Suggestion

if TYPE_CHECKING:
    from suggestions import State, SuggestionsBot

logger = Logger(__name__)


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
        related_suggestion_id: Optional[str] = None,
        message_id: Optional[int] = None,
        channel_id: Optional[int] = None,
    ):
        self._id: str = _id
        self.guild_id: int = guild_id
        self.suggestion: str = suggestion
        self.is_anonymous: bool = is_anonymous
        self.image_url: Optional[str] = image_url
        self.still_in_queue: bool = still_in_queue
        self.channel_id: Optional[int] = channel_id
        self.message_id: Optional[int] = message_id
        self.resolved_by: Optional[int] = resolved_by
        self.created_at: datetime.datetime = created_at
        self.suggestion_author_id: int = suggestion_author_id
        # For example saying why it didn't get approved
        self.resolution_note: Optional[str] = resolution_note
        self.resolved_at: Optional[datetime.datetime] = resolved_at

        # If this queued suggestion get approved,
        # this field will be the id of the created suggestion
        self.related_suggestion_id: Optional[str] = related_suggestion_id

    @property
    def is_resolved(self) -> bool:
        return self.resolved_by is not None

    @property
    def is_in_virtual_queue(self) -> bool:
        return self.message_id is None

    @classmethod
    async def from_message_id(
        cls, message_id: int, channel_id: int, state: State
    ) -> QueuedSuggestion:
        """Return a suggestion from its sent message.

        Useful for message commands.

        Parameters
        ----------
        message_id : int
            The message id
        channel_id : int
            The channel id
        state : State
            Our internal state

        Returns
        -------
        QueuedSuggestion
            The found suggestion

        Raises
        ------
        SuggestionNotFound
            No suggestion exists for this data
        """
        suggestion: QueuedSuggestion | None = await state.queued_suggestions_db.find(
            AQ(
                AND(
                    EQ("message_id", message_id),
                    EQ("channel_id", channel_id),
                )
            )
        )
        if not suggestion:
            raise SuggestionNotFound(
                f"This message does not look like a suggestions message."
            )

        return suggestion

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

        # Try to populate id on returned object
        return await state.queued_suggestions_db.find(suggestion.as_dict())

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

        if self.related_suggestion_id:
            data["related_suggestion_id"] = self.related_suggestion_id

        if self.message_id is not None:
            data["message_id"] = self.message_id
            data["channel_id"] = self.channel_id

        return data

    async def as_embed(self, bot: SuggestionsBot) -> Embed:
        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        if self.is_anonymous:
            submitter = "Anonymous"
        else:
            submitter = user.display_name

        embed: Embed = Embed(
            description=f"**Submitter**\n{submitter}\n\n"
            f"**Suggestion**\n{self.suggestion}",
            colour=bot.colors.embed_color,
            timestamp=self.created_at,
        )
        if not self.is_anonymous:
            embed.set_thumbnail(user.display_avatar)
            embed.set_footer(
                text=f"Queued suggestion | Submitter ID: {self.suggestion_author_id}"
            )

        if self.image_url:
            embed.set_image(self.image_url)

        return embed

    async def convert_to_suggestion(self, state: State) -> Suggestion:
        if not self._id:
            # It is not expected to reach this as this object should
            # have two distinct states:
            # 1. This object is created for a suggestion, inserted into
            #    the database and is then disregarded
            # 2. When we get here the object should have been retrieved
            #    via the queue system so the object should have an attached id
            logger.critical("QueuedSuggestion(%s) does not have an id", self.as_dict())
            raise UnhandledError(
                f"QueuedSuggestion({self.as_dict()}) does not have an id"
            )

        suggestion = await Suggestion.new(
            suggestion=self.suggestion,
            guild_id=self.guild_id,
            author_id=self.suggestion_author_id,
            state=state,
            image_url=self.image_url,
            is_anonymous=self.is_anonymous,
        )
        self.related_suggestion_id = suggestion.suggestion_id
        await state.queued_suggestions_db.update(self, self)
        return suggestion

    async def resolve(
        self, *, state: State, was_approved, resolved_by
    ) -> Optional[Suggestion]:
        self.resolved_by = resolved_by
        self.resolved_at = state.now
        self.still_in_queue = False
        if was_approved:
            return await self.convert_to_suggestion(state)

        await state.queued_suggestions_db.update(self, self)
