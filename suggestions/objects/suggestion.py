from __future__ import annotations

import datetime
import logging
from enum import Enum
from typing import TYPE_CHECKING, Literal, Union, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from bot_base.wraps import WrappedChannel
from disnake import Embed

from suggestions.exceptions import ErrorHandled, SuggestionNotFound

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Colors, ErrorCode

log = logging.getLogger(__name__)


class SuggestionState(Enum):
    pending = 0
    approved = 1
    rejected = 2

    @staticmethod
    def from_str(value: str) -> SuggestionState:
        mappings = {
            "pending": SuggestionState.pending,
            "approved": SuggestionState.approved,
            "rejected": SuggestionState.rejected,
        }
        return mappings[value.lower()]

    def as_str(self) -> str:
        if self is SuggestionState.rejected:
            return "rejected"

        elif self is SuggestionState.approved:
            return "approved"

        return "pending"


class Suggestion:
    """An abstract wrapper encapsulating all suggestion functionality."""

    def __init__(
        self,
        _id: str,
        guild_id: int,
        suggestion: str,
        suggestion_author_id: int,
        created_at: datetime.datetime,
        state: Union[Literal["open", "approved", "rejected"], SuggestionState],
        *,
        total_up_votes: Optional[int] = None,
        total_down_votes: Optional[int] = None,
        channel_id: Optional[int] = None,
        message_id: Optional[int] = None,
        resolved_by: Optional[int] = None,
        resolution_note: Optional[str] = None,
        resolved_at: Optional[datetime.datetime] = None,
        **kwargs,
    ):
        """

        Parameters
        ----------
        guild_id: int
            The guild this suggestion is in
        suggestion: str
            The suggestion content itself
        _id: str
            The id of the suggestion
        suggestion_author_id: int
            The id of the person who created the suggestion
        created_at: datetime.datetime
            When this suggestion was created
        state: Union[Literal["open", "approved", "rejected"], SuggestionState]
            The current state of the suggestion itself

        Other Parameters
        ----------------
        resolved_by: Optional[int]
            Who changed the final state of this suggestion
        resolution_note: Optional[str]
            A note to add to the suggestion on resolve
        resolved_at: Optional[datetime.datetime]
            When this suggestion was resolved
        channel_id: Optional[int]
            The channel this suggestion is currently in
        message_id: Optional[int]
            The current message ID. This could be the suggestion
            or the log channel message.
        total_up_votes: Optional[int]
            How many up votes this had when closed
        total_down_votes: Optional[int]
            How many down votes this had when closed
        """
        self._id: str = _id
        self.guild_id: int = guild_id
        self.suggestion: str = suggestion
        self.suggestion_author_id: int = suggestion_author_id
        self.created_at: datetime.datetime = created_at
        self.state: SuggestionState = (
            SuggestionState.from_str(state)
            if not isinstance(state, SuggestionState)
            else state
        )

        self.channel_id: Optional[int] = channel_id
        self.message_id: Optional[int] = message_id
        self.resolved_by: Optional[int] = resolved_by
        self.resolved_at: Optional[datetime.datetime] = resolved_at
        self.resolution_note: Optional[str] = resolution_note
        self.total_up_votes: Optional[int] = total_up_votes
        self.total_down_votes: Optional[int] = total_down_votes

    @property
    def suggestion_id(self) -> str:
        return self._id

    @property
    def color(self) -> disnake.Color:
        from suggestions import Colors

        if self.state is SuggestionState.rejected:
            return Colors.rejected_suggestion

        elif self.state is SuggestionState.approved:
            return Colors.approved_suggestion

        return Colors.pending_suggestion

    @classmethod
    async def from_id(cls, suggestion_id: str, state: State) -> Suggestion:
        """Returns a valid Suggestion instance from an id.

        Parameters
        ----------
        suggestion_id: str
            The suggestion we want
        state: State
            Internal state to marshall data

        Returns
        -------
        Suggestion
            The valid suggestion

        Raises
        ------
        ValueError
            No suggestion found with that id
        """
        suggestion: Optional[Suggestion] = await state.suggestions_db.find(
            AQ(EQ("_id", suggestion_id))
        )
        if not suggestion:
            raise SuggestionNotFound(f"No suggestion found with the id {suggestion_id}")

        return suggestion

    @classmethod
    async def new(
        cls,
        suggestion: str,
        guild_id: int,
        author_id: int,
        state: State,
    ) -> Suggestion:
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

        Returns
        -------
        Suggestion
            A valid suggestion.
        """
        suggestion_id = state.get_new_suggestion_id()
        suggestion: Suggestion = Suggestion(
            guild_id=guild_id,
            suggestion=suggestion,
            state=SuggestionState.pending,
            _id=suggestion_id,
            suggestion_author_id=author_id,
            created_at=state.now,
        )
        await state.suggestions_db.insert(suggestion)
        state.add_sid_to_cache(guild_id, suggestion_id)
        return suggestion

    def as_filter(self) -> dict:
        return {"_id": self.suggestion_id}

    def as_dict(self) -> dict:
        data = {
            "guild_id": self.guild_id,
            "state": self.state.as_str(),
            "suggestion": self.suggestion,
            "_id": self.suggestion_id,
            "suggestion_author_id": self.suggestion_author_id,
            "created_at": self.created_at,
        }

        if self.resolved_by:
            data["resolved_by"] = self.resolved_by
            data["resolution_note"] = self.resolution_note

        if self.resolution_note:
            data["resolved_at"] = self.resolved_at

        if self.message_id:
            data["message_id"] = self.message_id
            data["channel_id"] = self.channel_id

        if self.total_up_votes is not None:
            data["total_up_votes"] = self.total_up_votes
            data["total_down_votes"] = self.total_down_votes

        return data

    async def as_embed(self, bot: SuggestionsBot) -> Embed:
        if self.resolved_by:
            return await self._as_resolved_embed(bot)

        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        return (
            Embed(
                description=f"**Submitter**\n{user.display_name}\n\n"
                f"**Suggestion**\n{self.suggestion}",
                colour=self.color,
                timestamp=bot.state.now,
            )
            .set_thumbnail(user.display_avatar)
            .set_footer(
                text=f"User ID: {self.suggestion_author_id} | sID: {self.suggestion_id}"
            )
        )

    async def _as_resolved_embed(self, bot: SuggestionsBot) -> Embed:
        results = (
            f"**Results**\n{await bot.suggestion_emojis.default_up_vote()}: **{self.total_up_votes}**\n"
            f"{await bot.suggestion_emojis.default_down_vote()}: **{self.total_down_votes}**"
        )

        text = "Approved" if self.state == SuggestionState.approved else "Rejected"
        embed = Embed(
            description=f"{results}\n\n**Suggestion**\n{self.suggestion}\n\n"
            f"**Submitter**\n<@{self.suggestion_author_id}>\n\n"
            f"**{text} By**\n<@{self.resolved_by}>\n\n",
            colour=self.color,
            timestamp=bot.state.now,
        ).set_footer(text=f"sID: {self.suggestion_id}")

        if self.resolution_note:
            embed.description += f"**Response**\n{self.resolution_note}"

        return embed

    async def mark_approved_by(
        self, state: State, resolved_by: int, resolution_note: Optional[str] = None
    ):
        assert state.suggestions_db.collection_name == "suggestions"
        self.state = SuggestionState.approved
        self.resolved_at = state.now
        self.resolved_by = resolved_by
        if resolution_note:
            self.resolution_note = resolution_note

        state.remove_sid_from_cache(self.guild_id, self.suggestion_id)
        await state.suggestions_db.update(self, self)
        await self.try_notify_user_of_decision(state.bot)

    async def mark_rejected_by(
        self, state: State, resolved_by: int, resolution_note: Optional[str] = None
    ):
        assert state.suggestions_db.collection_name == "suggestions"
        self.state = SuggestionState.rejected
        self.resolved_at = state.now
        self.resolved_by = resolved_by
        if resolution_note:
            self.resolution_note = resolution_note

        state.remove_sid_from_cache(self.guild_id, self.suggestion_id)
        await state.suggestions_db.update(self, self)
        await self.try_notify_user_of_decision(state.bot)

    async def try_delete(
        self,
        bot: SuggestionsBot,
        interaction: disnake.GuildCommandInteraction,
    ):
        try:
            channel: WrappedChannel = await bot.get_or_fetch_channel(self.channel_id)
            message: disnake.Message = await channel.fetch_message(self.message_id)
        except disnake.HTTPException:
            await interaction.send(
                embed=bot.error_embed(
                    "Command failed",
                    "Looks like this suggestion was deleted.",
                    footer_text=f"Error code {ErrorCode.SUGGESTION_MESSAGE_DELETED.value}",
                ),
                ephemeral=True,
            )
            raise ErrorHandled

        if not self.resolved_by:
            # We need to store results
            # -1 As the bot shouldn't count
            default_up_vote = await bot.suggestion_emojis.default_up_vote()
            default_down_vote = await bot.suggestion_emojis.default_down_vote()
            for reaction in message.reactions:
                if str(reaction.emoji) == str(default_up_vote):
                    self.total_up_votes = reaction.count - 1

                elif str(reaction.emoji) == str(default_down_vote):
                    self.total_down_votes = reaction.count - 1

        await message.delete()

        self.message_id = None
        self.channel_id = None
        await bot.db.suggestions.update(self, self)

    async def try_notify_user_of_decision(self, bot: SuggestionsBot):
        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        guild = await bot.fetch_guild(self.guild_id)
        text = "approved" if self.state == SuggestionState.approved else "rejected"
        embed: Embed = Embed(
            description=f"Hey, {user.mention}. Your suggestion has been "
            f"{text} by <@{self.resolved_by}>!\n\nYour suggestion ID (sID) for reference "
            f"was **{self.suggestion_id}**.",
            timestamp=bot.state.now,
            color=self.color,
        ).set_footer(text=f"Guild ID: {self.guild_id} | sID: {self.suggestion_id}")
        try:
            embed.set_author(name=guild.name, icon_url=guild.icon.url)
        except AttributeError:
            pass

        try:
            await user.send(embed=embed)
        except disnake.HTTPException:
            log.debug("Failed to dm %s to tell them about there suggestion", user.id)