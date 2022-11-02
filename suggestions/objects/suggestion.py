from __future__ import annotations

import datetime
import logging
from enum import Enum
from typing import TYPE_CHECKING, Literal, Union, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from bot_base.wraps import WrappedChannel
from disnake import Embed, Guild

from suggestions import ErrorCode
from suggestions.exceptions import ErrorHandled, SuggestionNotFound
from suggestions.low_level import MessageEditing
from suggestions.objects import UserConfig, GuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Colors

log = logging.getLogger(__name__)


class SuggestionState(Enum):
    pending = 0
    approved = 1
    rejected = 2
    cleared = 3

    @staticmethod
    def from_str(value: str) -> SuggestionState:
        mappings = {
            "pending": SuggestionState.pending,
            "approved": SuggestionState.approved,
            "rejected": SuggestionState.rejected,
            "cleared": SuggestionState.cleared,
        }
        return mappings[value.lower()]

    def as_str(self) -> str:
        if self is SuggestionState.rejected:
            return "rejected"

        elif self is SuggestionState.approved:
            return "approved"

        elif self is SuggestionState.cleared:
            return "cleared"

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
        state: Union[
            Literal["open", "approved", "rejected", "cleared"],
            SuggestionState,
        ],
        *,
        total_up_votes: Optional[int] = None,
        total_down_votes: Optional[int] = None,
        up_voted_by: Optional[list[int]] = None,
        down_voted_by: Optional[list[int]] = None,
        channel_id: Optional[int] = None,
        message_id: Optional[int] = None,
        resolved_by: Optional[int] = None,
        resolution_note: Optional[str] = None,
        resolved_at: Optional[datetime.datetime] = None,
        image_url: Optional[str] = None,
        uses_views_for_votes: bool = False,
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

            This is based off the old reaction system.
        total_down_votes: Optional[int]
            How many down votes this had when closed

            This is based off the old reaction system.
        up_voted_by: Optional[list[int]]
            A list of people who up voted this suggestion

            This is based off the new button system
        up_voted_by: Optional[list[int]]
            A list of people who up voted this suggestion

            This is based off the new button system
        down_voted_by: Optional[list[int]]
            A list of people who down voted this suggestion

            This is based off the new button system
        image_url: Optional[str]
            An optional url for an image attached to the suggestion
        uses_views_for_votes: bool
            A simple flag to make backwards compatibility easier.

            Defaults to `False` as all old suggestions will use this
            value since they don't have the field in the database
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
        self.uses_views_for_votes: bool = uses_views_for_votes

        self.channel_id: Optional[int] = channel_id
        self.message_id: Optional[int] = message_id
        self.resolved_by: Optional[int] = resolved_by
        self.resolved_at: Optional[datetime.datetime] = resolved_at
        self.resolution_note: Optional[str] = resolution_note
        self._total_up_votes: Optional[int] = total_up_votes
        self._total_down_votes: Optional[int] = total_down_votes
        self.up_voted_by: set[int] = set(up_voted_by) if up_voted_by else set()
        self.down_voted_by: set[int] = set(down_voted_by) if down_voted_by else set()
        self.image_url: Optional[str] = image_url

    @property
    def total_up_votes(self) -> Optional[int]:
        if self._total_up_votes:
            return self._total_up_votes

        if not self.uses_views_for_votes:
            return None

        return len(self.up_voted_by)

    @property
    def total_down_votes(self) -> Optional[int]:
        if self._total_down_votes:
            return self._total_down_votes

        if not self.uses_views_for_votes:
            return None

        return len(self.down_voted_by)

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
    async def from_message_id(
        cls, message_id: int, channel_id: int, state: State
    ) -> Suggestion:
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
        Suggestion
            The found suggestion

        Raises
        ------
        SuggestionNotFound
            No suggestion exists for this data
        """
        suggestion: Suggestion | None = await state.suggestions_db.find(
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
    async def from_id(
        cls, suggestion_id: str, guild_id: int, state: State
    ) -> Suggestion:
        """Returns a valid Suggestion instance from an id.

        Parameters
        ----------
        suggestion_id: str
            The suggestion we want
        guild_id: int
            The guild its meant to be in.
            Secures against cross guild privledge escalation
        state: State
            Internal state to marshall data

        Returns
        -------
        Suggestion
            The valid suggestion

        Raises
        ------
        SuggestionNotFound
            No suggestion found with that id
        """
        suggestion: Optional[Suggestion] = await state.suggestions_db.find(
            AQ(EQ("_id", suggestion_id))
        )
        if not suggestion:
            raise SuggestionNotFound(
                f"No suggestion found with the id {suggestion_id} in this guild"
            )

        if suggestion.guild_id != guild_id:
            log.critical(
                "Someone in guild %s looked up a suggestion not from their guild"
            )
            raise SuggestionNotFound(
                f"No suggestion found with the id {suggestion_id} in this guild"
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

        Other Parameters
        ----------------
        image_url: Optional[str]
            An image to attach to this suggestion.

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
            image_url=image_url,
            uses_views_for_votes=True,
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
            "uses_views_for_votes": self.uses_views_for_votes,
        }

        if self.resolved_by:
            data["resolved_by"] = self.resolved_by
            data["resolution_note"] = self.resolution_note

        if self.resolution_note:
            data["resolved_at"] = self.resolved_at

        if self.message_id:
            data["message_id"] = self.message_id
            data["channel_id"] = self.channel_id

        if self.uses_views_for_votes:
            data["up_voted_by"] = list(self.up_voted_by)
            data["down_voted_by"] = list(self.down_voted_by)

        else:
            data["total_up_votes"] = self._total_up_votes
            data["total_down_votes"] = self._total_down_votes

        if self.image_url is not None:
            data["image_url"] = self.image_url

        return data

    async def as_embed(self, bot: SuggestionsBot) -> Embed:
        if self.resolved_by:
            return await self._as_resolved_embed(bot)

        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        embed: Embed = (
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

        if self.image_url:
            embed.set_image(self.image_url)

        if self.uses_views_for_votes:
            results = (
                f"**Results so far**\n{await bot.suggestion_emojis.default_up_vote()}: **{self.total_up_votes}**\n"
                f"{await bot.suggestion_emojis.default_down_vote()}: **{self.total_down_votes}**"
            )
            embed.description += f"\n\n{results}"

        return embed

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

        icon_url = await Guild.try_fetch_icon_url(self.guild_id, bot.state)
        guild = bot.state.guild_cache.get_entry(self.guild_id)

        embed.set_author(name=guild.name, icon_url=icon_url)

        if self.resolution_note:
            embed.description += f"**Response**\n{self.resolution_note}"

        if self.image_url:
            embed.set_image(self.image_url)

        return embed

    async def mark_approved_by(
        self,
        state: State,
        resolved_by: int,
        resolution_note: Optional[str] = None,
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
        self,
        state: State,
        resolved_by: int,
        resolution_note: Optional[str] = None,
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

    async def mark_cleared_by(
        self,
        state: State,
        resolved_by: int,
        resolution_note: Optional[str] = None,
    ):
        assert state.suggestions_db.collection_name == "suggestions"
        self.state = SuggestionState.cleared
        self.resolved_at = state.now
        self.resolved_by = resolved_by
        self.channel_id = None
        self.message_id = None
        if resolution_note:
            self.resolution_note = resolution_note

        state.remove_sid_from_cache(self.guild_id, self.suggestion_id)
        await state.suggestions_db.update(self, self)

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

        await message.delete()

        self.message_id = None
        self.channel_id = None
        await bot.db.suggestions.update(self, self)

    async def save_reaction_results(
        self,
        bot: SuggestionsBot,
        interaction: disnake.GuildCommandInteraction,
    ) -> None:
        if self.uses_views_for_votes:
            # Saves modifying the existing codebase.
            # This means we can simply return and
            # move onto the next thing no worries
            return None

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

        # We need to store results
        # -1 As the bot shouldn't count
        default_up_vote = await bot.suggestion_emojis.default_up_vote()
        default_down_vote = await bot.suggestion_emojis.default_down_vote()
        for reaction in message.reactions:
            if str(reaction.emoji) == str(default_up_vote):
                self._total_up_votes = reaction.count - 1

            elif str(reaction.emoji) == str(default_down_vote):
                self._total_down_votes = reaction.count - 1

        if self.total_up_votes is None or self.total_down_votes is None:
            log.error("Failed to find our emojis on suggestion %s", self.suggestion_id)

        await bot.db.suggestions.update(self, self)

    async def try_notify_user_of_decision(self, bot: SuggestionsBot):
        user_config: UserConfig = await UserConfig.from_id(
            self.suggestion_author_id, bot.state
        )
        if user_config.dm_messages_disabled:
            log.debug(
                "User %s has dm messages disabled, failed to notify change to suggestion %s",
                self.suggestion_author_id,
                self.suggestion_id,
            )
            return

        guild_config: GuildConfig = await GuildConfig.from_id(self.guild_id, bot.state)
        if guild_config.dm_messages_disabled:
            log.debug(
                "Guild %s has dm messages disabled, failed to notify user %s regarding changes to suggestion %s",
                self.guild_id,
                self.suggestion_author_id,
                self.suggestion_id,
            )
            return

        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        icon_url = await Guild.try_fetch_icon_url(self.guild_id, bot.state)
        guild = bot.state.guild_cache.get_entry(self.guild_id)
        text = "approved" if self.state == SuggestionState.approved else "rejected"
        response = (
            f"**Staff Response:** {self.resolution_note}\n\n"
            if self.resolution_note
            else ""
        )

        embed: Embed = (
            Embed(
                description=f"Hey, {user.mention}. Your suggestion has been "
                f"{text} by <@{self.resolved_by}>!\n\n{response}Your suggestion ID (sID) for reference "
                f"was **{self.suggestion_id}**.",
                timestamp=bot.state.now,
                color=self.color,
            )
            .set_footer(text=f"Guild ID: {self.guild_id} | sID: {self.suggestion_id}")
            .set_author(name=guild.name, icon_url=icon_url)
        )

        try:
            await user.send(embed=embed)
        except disnake.HTTPException:
            log.debug("Failed to dm %s to tell them about their suggestion", user.id)

    async def create_thread(self, message: disnake.Message):
        """Create a thread for this suggestion"""
        if self.state != SuggestionState.pending:
            raise ValueError(
                "Cannot create a thread for suggestions which aren't pending."
            )

        await message.create_thread(name=f"Thread for suggestion {self.suggestion_id}")

    async def update_vote_count(
        self,
        bot: SuggestionsBot,
        interaction: disnake.Interaction,
    ):
        log.debug("Starting to update vote counts")
        try:
            await MessageEditing(
                bot, channel_id=self.channel_id, message_id=self.message_id
            ).edit(embed=await self.as_embed(bot))
        except (disnake.HTTPException, disnake.NotFound):
            await interaction.send(
                embed=bot.error_embed(
                    "Command failed",
                    "Looks like this suggestion was deleted.",
                    footer_text=f"Error code {ErrorCode.SUGGESTION_MESSAGE_DELETED.value}",
                ),
                ephemeral=True,
            )
            raise ErrorHandled

        log.debug("Finished updating vote counts")
