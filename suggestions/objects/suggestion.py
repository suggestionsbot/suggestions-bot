from __future__ import annotations

import datetime
from enum import Enum
from typing import TYPE_CHECKING, Literal, Union, Optional, cast

import commons
import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from disnake import Embed
from disnake.ext import commands
from logoo import Logger

from suggestions import ErrorCode
from suggestions.exceptions import (
    ErrorHandled,
    SuggestionNotFound,
    SuggestionSecurityViolation,
)
from suggestions.interaction_handler import InteractionHandler
from suggestions.low_level import MessageEditing
from suggestions.objects import UserConfig, GuildConfig, PremiumGuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Colors

logger = Logger(__name__)


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

    __slots__ = [
        "_id",
        "guild_id",
        "suggestion",
        "suggestion_author_id",
        "created_at",
        "state",
        "note",
        "note_added_by",
        "_total_up_votes",
        "_total_down_votes",
        "up_voted_by",
        "down_voted_by",
        "channel_id",
        "message_id",
        "resolved_by",
        "resolution_note",
        "resolved_at",
        "image_url",
        "uses_views_for_votes",
        "is_anonymous",
        "anonymous_resolution",
        "thread_id",
    ]

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
        note: Optional[str] = None,
        note_added_by: Optional[int] = None,
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
        is_anonymous: bool = False,
        anonymous_resolution: Optional[bool] = None,
        thread_id: Optional[int] = None,
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
        note: Optional[str]
            A note to add to the suggestion embed
        note_added_by: Optional[int]
            Who added the note.

            Should be marked as hidden if not shown.
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
        is_anonymous: bool
            Whether or not this suggestion
            should be displayed anonymous
        anonymous_resolution: Optional[bool]
            Whether or not to show who resolved this suggestion
            to the end suggester
        thread_id: Optional[str]
            The ID of the thread to resolve directly
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
        self.thread_id: Optional[int] = thread_id
        self.resolved_by: Optional[int] = resolved_by
        self.resolved_at: Optional[datetime.datetime] = resolved_at
        self.resolution_note: Optional[str] = resolution_note
        self._total_up_votes: Optional[int] = total_up_votes
        self._total_down_votes: Optional[int] = total_down_votes
        self.up_voted_by: set[int] = set(up_voted_by) if up_voted_by else set()
        self.down_voted_by: set[int] = set(down_voted_by) if down_voted_by else set()
        self.image_url: Optional[str] = image_url
        self.is_anonymous: bool = is_anonymous
        self.anonymous_resolution: Optional[bool] = anonymous_resolution
        self.note: Optional[str] = note
        self.note_added_by: Optional[int] = note_added_by

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
            raise SuggestionSecurityViolation(
                sid=suggestion_id,
                user_facing_message=f"No suggestion found with the id {suggestion_id} in this guild",
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
        is_anonymous: bool
            Whether or not this suggestion should be anonymous

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
            is_anonymous=is_anonymous,
        )
        await state.suggestions_db.insert(suggestion)
        state.add_sid_to_cache(guild_id, suggestion_id)

        logger.debug(
            "Created new suggestion",
            extra_metadata={**suggestion.as_dict(), "suggestion_id": suggestion_id},
        )
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
            "is_anonymous": self.is_anonymous,
            "anonymous_resolution": self.anonymous_resolution,
        }

        if self.note:
            data["note"] = self.note
            data["note_added_by"] = self.note_added_by

        if self.resolved_by:
            data["resolved_by"] = self.resolved_by
            data["resolution_note"] = self.resolution_note

        if self.resolved_at:
            data["resolved_at"] = self.resolved_at

        if self.message_id:
            data["message_id"] = self.message_id

        if self.channel_id:
            data["channel_id"] = self.channel_id

        if self.thread_id:
            data["thread_id"] = self.thread_id

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
        user = await bot.get_or_fetch_user(self.suggestion_author_id)

        if self.resolved_by:
            return await self._as_resolved_embed(bot, user)

        if self.is_anonymous:
            submitter = "Anonymous"
        else:
            submitter = user.display_name

        embed: Embed = Embed(
            description=f"**Submitter**\n{submitter}\n\n"
            f"**Suggestion**\n{self.suggestion}",
            colour=self.color,
            timestamp=bot.state.now,
        )
        if not self.is_anonymous:
            embed.set_thumbnail(user.display_avatar)
            embed.set_footer(
                text=f"User ID: {self.suggestion_author_id} | sID: {self.suggestion_id}"
            )
        else:
            embed.set_footer(text=f"sID: {self.suggestion_id}")

        if self.image_url:
            embed.set_image(self.image_url)

        if self.note:
            note_desc = f"\n\n**Moderator note**\n{self.note}"
            # TODO Resolve BT-44 and add moderator back
            embed.description += note_desc

        if self.uses_views_for_votes:
            results = (
                f"**Results so far**\n{await bot.suggestion_emojis.default_up_vote()}: **{self.total_up_votes}**\n"
                f"{await bot.suggestion_emojis.default_down_vote()}: **{self.total_down_votes}**"
            )
            embed.description += f"\n\n{results}"

        return embed

    async def _as_resolved_embed(
        self, bot: SuggestionsBot, user: disnake.User
    ) -> Embed:
        results = (
            f"**Results**\n{await bot.suggestion_emojis.default_up_vote()}: **{self.total_up_votes}**\n"
            f"{await bot.suggestion_emojis.default_down_vote()}: **{self.total_down_votes}**"
        )

        if self.is_anonymous:
            submitter = "Anonymous"
        else:
            submitter = f"<@{self.suggestion_author_id}>"
        text = "Approved" if self.state == SuggestionState.approved else "Rejected"
        resolved_by_text = (
            "Anonymous" if self.anonymous_resolution else f"<@{self.resolved_by}>"
        )

        embed = Embed(
            description=f"{results}\n\n**Suggestion**\n{self.suggestion}\n\n"
            f"**Submitter**\n{submitter}\n\n"
            f"**{text} By**\n{resolved_by_text}",
            colour=self.color,
            timestamp=bot.state.now,
        )

        if not self.is_anonymous:
            embed.set_thumbnail(user.display_avatar)
            embed.set_footer(
                text=f"User ID: {self.suggestion_author_id} | sID: {self.suggestion_id}"
            )
        else:
            embed.set_footer(text=f"sID: {self.suggestion_id}")

        icon_url = await bot.try_fetch_icon_url(self.guild_id)
        guild = bot.state.guild_cache.get_entry(self.guild_id)

        embed.set_author(name=guild.name, icon_url=icon_url)

        if self.resolution_note:
            embed.description += f"\n\n**Response**\n{self.resolution_note}"

        if self.image_url:
            embed.set_image(self.image_url)

        if self.note:
            note_desc = f"\n\n**Moderator note**\n{self.note}"
            # TODO Resolve BT-44 and add moderator back
            embed.description += note_desc

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
        silently: bool = False,
    ) -> bool:
        """

        Parameters
        ----------
        bot
        interaction
        silently: bool
            Do nothing on failure

        Returns
        -------
        bool
            Whether or not deleting succeeded

        Notes
        -----
        BT-21 doesn't apply to this as we also want to check
        if the message itself has already been deleted or not via fetch
        """
        try:
            channel = await bot.get_or_fetch_channel(self.channel_id)
            message: disnake.Message = await channel.fetch_message(self.message_id)
        except disnake.HTTPException:
            if silently:
                return False

            await interaction.send(
                embed=bot.error_embed(
                    "Command failed",
                    "Looks like this suggestion was deleted.",
                    footer_text=f"Error code {ErrorCode.SUGGESTION_MESSAGE_DELETED.value}",
                ),
                ephemeral=True,
            )
            raise ErrorHandled

        try:
            await message.delete()
        except disnake.HTTPException:
            if silently:
                return False
            raise

        self.message_id = None
        self.channel_id = None
        await bot.db.suggestions.update(self, self)
        return True

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
            channel = await bot.get_or_fetch_channel(self.channel_id)
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
            logger.error(
                "Failed to find our emojis on suggestion %s",
                self.suggestion_id,
                extra_metadata={"suggestion_id": self.suggestion_id},
            )

        await bot.db.suggestions.update(self, self)

    async def try_notify_user_of_decision(self, bot: SuggestionsBot):
        user_config: UserConfig = await UserConfig.from_id(
            self.suggestion_author_id, bot.state
        )
        if user_config.dm_messages_disabled:
            logger.debug(
                "User %s has dm messages disabled, failed to notify change to suggestion %s",
                self.suggestion_author_id,
                self.suggestion_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "author_id": self.suggestion_author_id,
                },
            )
            return

        guild_config: GuildConfig = await GuildConfig.from_id(self.guild_id, bot.state)
        if guild_config.dm_messages_disabled:
            logger.debug(
                "Guild %s has dm messages disabled, failed to notify user %s regarding changes to suggestion %s",
                self.guild_id,
                self.suggestion_author_id,
                self.suggestion_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "author_id": self.suggestion_author_id,
                    "guild_id": self.guild_id,
                },
            )
            return

        user = await bot.get_or_fetch_user(self.suggestion_author_id)
        icon_url = await bot.try_fetch_icon_url(self.guild_id)
        guild = bot.state.guild_cache.get_entry(self.guild_id)
        text = "approved" if self.state == SuggestionState.approved else "rejected"
        resolved_by_text = (
            "" if self.anonymous_resolution else f" by <@{self.resolved_by}>"
        )
        response = (
            f"**Staff Response:** {self.resolution_note}\n\n"
            if self.resolution_note
            else ""
        )

        embed: Embed = (
            Embed(
                description=f"Hey, {user.mention}. Your suggestion has been "
                f"{text}{resolved_by_text}!\n\n{response}Your suggestion ID (sID) for reference "
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
            logger.debug(
                "Failed to dm %s to tell them about their suggestion",
                user.id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "author_id": user.id,
                },
            )

    async def create_thread(self, message: disnake.Message, *, ih: InteractionHandler):
        """Create a thread for this suggestion"""
        if self.state != SuggestionState.pending:
            raise ValueError(
                "Cannot create a thread for suggestions which aren't pending."
            )

        thread = await message.create_thread(
            name=f"Thread for suggestion {self.suggestion_id}"
        )
        self.thread_id = thread.id
        await ih.bot.db.suggestions.update(self, self)
        logger.debug(
            f"Created a thread for suggestion {self.suggestion_id}",
            extra_metadata={"suggestion_id": self.suggestion_id},
        )
        if self.is_anonymous:
            # Don't expose the anon author
            return

        guild_config: GuildConfig = await GuildConfig.from_id(
            ih.interaction.guild_id, ih.bot.state
        )
        if not guild_config.ping_on_thread_creation:
            return

        user_config: UserConfig = await UserConfig.from_id(
            ih.interaction.author.id, ih.bot.state
        )
        if not user_config.ping_on_thread_creation:
            return

        # TODO The ones for guilds as well
        try:
            await thread.send(
                ih.bot.get_localized_string(
                    "SUGGEST_INNER_PING_AUTHOR_IN_THREAD",
                    ih,
                    extras={"AUTHOR_ID": self.suggestion_author_id},
                )
            )
        except:
            # I'd consider it fine if the bot can't send this message
            pass

    async def edit_suggestion_message(
        self,
        ih: InteractionHandler,
    ):
        """A generic method to edit a suggestion message to the new values."""
        bot = ih.bot
        try:
            await MessageEditing(
                bot, channel_id=self.channel_id, message_id=self.message_id
            ).edit(embed=await self.as_embed(bot))
        except (disnake.HTTPException, disnake.NotFound):
            await ih.send(
                embed=bot.error_embed(
                    "Command failed",
                    "Looks like this suggestion was deleted.",
                    footer_text=f"Error code {ErrorCode.SUGGESTION_MESSAGE_DELETED.value}",
                ),
            )
            raise ErrorHandled

    async def edit_message_after_finalization(
        self,
        *,
        guild_config: GuildConfig,
        bot: SuggestionsBot,
        state: State,
        interaction: disnake.GuildCommandInteraction,
    ):
        """
        Modify the suggestion message inline with the guilds
        configuration now that the suggestion has entered one of
        the following states:
         - Approved
         - Rejected
        """
        if guild_config.keep_logs:
            await self.save_reaction_results(bot, interaction)
            # In place suggestion edit
            channel = await bot.get_or_fetch_channel(self.channel_id)
            try:
                message: disnake.Message = await channel.fetch_message(self.message_id)
            except disnake.Forbidden:
                raise SuggestionNotFound(
                    "Failed to find this suggestions message in order to resolve it."
                )

            try:
                await message.edit(embed=await self.as_embed(bot), components=None)
            except disnake.Forbidden:
                raise commands.MissingPermissions(
                    missing_permissions=[
                        "Missing permissions edit suggestions in your suggestions channel"
                    ]
                )

            try:
                if not self.uses_views_for_votes:
                    await message.clear_reactions()
            except disnake.Forbidden:
                raise commands.MissingPermissions(
                    missing_permissions=[
                        "Missing permissions clear reactions in your suggestions channel"
                    ]
                )

        else:
            # Move the suggestion to the logs channel
            await self.save_reaction_results(bot, interaction)
            channel = await bot.get_or_fetch_channel(guild_config.log_channel_id)
            try:
                message: disnake.Message = await channel.send(
                    embed=await self.as_embed(bot)
                )
            except disnake.Forbidden:
                raise commands.MissingPermissions(
                    missing_permissions=[
                        "Missing permissions to send in configured log channel"
                    ]
                )

            # Only delete the original suggestion if we actually
            # managed to send the log message to the new channel
            await self.try_delete(bot, interaction)

            self.message_id = message.id
            self.channel_id = channel.id
            await state.suggestions_db.upsert(self, self)

    async def archive_thread_if_required(
        self, *, guild_config: GuildConfig, bot: SuggestionsBot, locale: disnake.Locale
    ):
        """Attempts to archive the attached thread if the feature is enabled."""
        if not guild_config.auto_archive_threads:
            # Guild does not want thread archived
            logger.debug(
                "Guild %s does not want threads archived",
                guild_config.guild_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                },
            )
            return

        if self.channel_id is None:
            # I don't know why this is none tbh
            logger.critical(
                "Suggestion channel id was none",
                extra_metadata={**self.as_dict(), "suggestion_id": self.suggestion_id},
            )

            # Don't hard crash so we can hopefully keep going
            return

        try:
            if self.thread_id:
                thread = await bot.get_or_fetch_channel(self.thread_id)
            else:
                channel = await bot.get_or_fetch_channel(self.channel_id)
                message: disnake.Message = await channel.fetch_message(self.message_id)

                if not message.thread:
                    # Suggestion has no created thread
                    logger.debug(
                        "No thread for suggestion %s, should have one: %s",
                        self.suggestion_id,
                        "yes" if guild_config.threads_for_suggestions else "no",
                        extra_metadata={
                            "suggestion_id": self.suggestion_id,
                            "guild_id": self.guild_id,
                        },
                    )
                    return

                thread = message.thread
        except disnake.NotFound:
            # While not ideal, we ignore the error here as
            # failing to archive a thread isn't a critical issue
            # worth crashing on. Instead, pass this to the actual
            # suggestion closing logic to handle more gracefully
            #
            # It'll likely still fail there but like, meh. Failing
            # to find the thread here means technically the function worked
            return

        if thread.owner_id != bot.user.id:
            # I did not create this thread
            logger.debug(
                "Thread on suggestion %s is owned by %s",
                self.suggestion_id,
                thread.owner_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                },
            )
            return

        if thread.archived or thread.locked:
            # Thread is already archived or
            # locked so no need to redo the action
            logger.debug(
                "Thread on suggestion %s is already archived or locked",
                self.suggestion_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                },
            )
            return

        await thread.send(
            bot.get_locale("SUGGESTION_OBJECT_LOCK_THREAD", locale),
        )
        await thread.edit(locked=True, archived=True)
        logger.debug(
            "Locked thread for suggestion %s",
            self.suggestion_id,
            extra_metadata={
                "suggestion_id": self.suggestion_id,
                "guild_id": self.guild_id,
            },
        )

    async def resolve(
        self,
        guild_config: GuildConfig,
        bot: SuggestionsBot,
        state: State,
        interaction: disnake.GuildCommandInteraction,
        resolution_type: SuggestionState,
        resolution_note: Optional[str] = None,
    ):
        logger.debug(
            "Attempting to resolve suggestion %s",
            self.suggestion_id,
            extra_metadata={
                "suggestion_id": self.suggestion_id,
                "guild_id": self.guild_id,
            },
        )
        self.anonymous_resolution = guild_config.anonymous_resolutions
        # https://github.com/suggestionsbot/suggestions-bot/issues/36
        if resolution_type is SuggestionState.approved:
            await self.mark_approved_by(state, interaction.author.id, resolution_note)
        elif resolution_type is SuggestionState.rejected:
            await self.mark_rejected_by(state, interaction.author.id, resolution_note)
        else:
            logger.error(
                "Resolving suggestion %s received a resolution_type of %s",
                self.suggestion_id,
                resolution_type,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                },
            )
            await interaction.send(
                embed=bot.error_embed(
                    "Something went wrong",
                    f"Please contact support.",
                    error_code=ErrorCode.SUGGESTION_RESOLUTION_ERROR,
                ),
                ephemeral=True,
            )
            raise ErrorHandled

        await self.archive_thread_if_required(
            bot=bot, guild_config=guild_config, locale=interaction.locale
        )
        await self.edit_message_after_finalization(
            state=state,
            bot=bot,
            interaction=interaction,
            guild_config=guild_config,
        )
        await self.try_notify_user_of_decision(state.bot)

    async def setup_initial_messages(
        self,
        *,
        guild_config: GuildConfig,
        cog,
        guild: disnake.Guild,
        icon_url,
        ih: InteractionHandler,
        comes_from_queue=False,
    ):
        """Encapsulates creation logic to save code re-use"""
        interaction = ih.interaction
        bot = ih.bot
        state = ih.bot.state

        from suggestions import buttons

        components_to_send = [
            await buttons.SuggestionUpVote(
                suggestion_id=self.suggestion_id,
                emoji=await bot.suggestion_emojis.default_up_vote(),
            ).as_ui_component(),
            await buttons.SuggestionDownVote(
                suggestion_id=self.suggestion_id,
                emoji=await bot.suggestion_emojis.default_down_vote(),
            ).as_ui_component(),
        ]

        try:
            premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
                self.guild_id, bot.state
            )
            channel = await bot.get_or_fetch_channel(
                guild_config.suggestions_channel_id
            )
            channel: disnake.TextChannel = cast(disnake.TextChannel, channel)
            message: disnake.Message = await channel.send(
                content=premium_guild_config.suggestions_prefix or None,
                embed=await self.as_embed(bot),
                components=[components_to_send],
            )
            logger.debug(
                "Sent suggestion %s to channel",
                self.suggestion_id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                },
            )
        except disnake.Forbidden as e:
            state.remove_sid_from_cache(interaction.guild_id, self.suggestion_id)
            await state.suggestions_db.delete(self.as_filter())
            raise e
        except Exception as e:
            logger.critical(
                "Error creating the initial message for a suggestion",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "traceback": commons.exception_as_string(e),
                },
            )
            state.remove_sid_from_cache(interaction.guild_id, self.suggestion_id)
            await state.suggestions_db.delete(self.as_filter())
            raise e

        self.message_id = message.id
        self.channel_id = channel.id
        await state.suggestions_db.upsert(self, self)

        if guild_config.threads_for_suggestions:
            try:
                await self.create_thread(message, ih=ih)
            except disnake.HTTPException:
                logger.debug(
                    "Failed to create a thread on suggestion %s",
                    self.suggestion_id,
                    extra_metadata={
                        "suggestion_id": self.suggestion_id,
                        "guild_id": self.guild_id,
                    },
                )
                did_delete = await self.try_delete(
                    bot=bot, interaction=interaction, silently=True
                )
                if not did_delete:
                    # Propagate it to error handlers and let them deal with it
                    raise

                await interaction.send(
                    embed=bot.error_embed(
                        "Missing permissions",
                        "I am unable to create threads in your suggestions channel, "
                        "please contact an administrator and ask them to give me "
                        "'Create Public Threads' permissions.\n\n"
                        "Alternatively, ask your administrator to disable automatic thread creation "
                        "using `/config thread disable`",
                        error_code=ErrorCode.MISSING_THREAD_CREATE_PERMISSIONS,
                    ),
                    ephemeral=True,
                )
                raise ErrorHandled

            else:
                logger.debug(
                    "Created a thread on suggestion %s",
                    self.suggestion_id,
                    extra_metadata={
                        "suggestion_id": self.suggestion_id,
                        "guild_id": self.guild_id,
                    },
                )

        try:
            suggestion_author = (
                f"<@{self.suggestion_author_id}>"
                if comes_from_queue
                else interaction.author.mention
            )
            embed: disnake.Embed = disnake.Embed(
                description=bot.get_locale(
                    "SUGGEST_INNER_SUGGESTION_SENT", interaction.locale
                ).format(
                    suggestion_author,
                    channel.mention,
                    self.suggestion_id,
                ),
                timestamp=state.now,
                color=bot.colors.embed_color,
            )
            embed.set_author(
                name=guild.name,
                icon_url=icon_url,
            )
            embed.set_footer(
                text=bot.get_locale(
                    "SUGGEST_INNER_SUGGESTION_SENT_FOOTER", interaction.locale
                ).format(interaction.guild_id, self.suggestion_id)
            )
            user_config: UserConfig = await UserConfig.from_id(
                interaction.author.id, bot.state
            )
            if comes_from_queue:
                # Send DM to author
                # No need to tell person who in queue its good
                author_config = await UserConfig.from_id(
                    self.suggestion_author_id, bot.state
                )
                if (
                    author_config.dm_messages_disabled
                    or guild_config.dm_messages_disabled
                ):
                    # Nothing we can do
                    logger.debug(
                        "Failed to DM %s regarding their suggestion being created from queue",
                        self.suggestion_author_id,
                        extra_metadata={
                            "suggestion_id": self.suggestion_id,
                            "guild_id": self.guild_id,
                            "author_id": self.suggestion_author_id,
                        },
                    )
                    return

                user = await bot.get_or_fetch_user(self.suggestion_author_id)
                await user.send(embed=embed)

            else:
                # Send everything to author as it is their suggestion
                if (
                    user_config.dm_messages_disabled
                    or guild_config.dm_messages_disabled
                ):
                    await interaction.send(embed=embed, ephemeral=True)
                else:
                    await interaction.send(
                        bot.get_locale("SUGGEST_INNER_THANKS", interaction.locale),
                        ephemeral=True,
                    )
                    await interaction.author.send(embed=embed)
        except disnake.HTTPException:
            logger.debug(
                "Failed to DM %s regarding their suggestion",
                interaction.author.id,
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": self.guild_id,
                    "author_id": interaction.author.id,
                },
            )
