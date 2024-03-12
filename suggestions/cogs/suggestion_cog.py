from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import cooldowns
import disnake
from commons.caching import NonExistentEntry
from bot_base.wraps import WrappedChannel
from disnake import Guild, ButtonStyle
from disnake.ext import commands, components
from logoo import Logger

from suggestions import checks, Stats
from suggestions.clunk2 import update_suggestion_message
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.core import SuggestionsQueue
from suggestions.exceptions import (
    SuggestionTooLong,
    ErrorHandled,
    MissingPermissionsToAccessQueueChannel,
    MissingQueueLogsChannel,
)
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import Suggestion, GuildConfig, UserConfig, QueuedSuggestion

from suggestions.objects.suggestion import SuggestionState
from suggestions.utility import r2

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

logger = Logger(__name__)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats
        self.suggestions_db: Document = self.bot.db.suggestions

        self.qs_core: SuggestionsQueue = SuggestionsQueue(bot)

    @components.button_listener()
    async def suggestion_up_vote(
        self, inter: disnake.MessageInteraction, *, suggestion_id: str
    ):
        await inter.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, inter.guild_id, self.state
        )
        if suggestion.state != SuggestionState.pending:
            return await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_UP_VOTE_INNER_NO_MORE_CASTING",
                    inter.locale,
                ),
                ephemeral=True,
            )

        member_id = inter.author.id
        if member_id in suggestion.up_voted_by:
            return await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_UP_VOTE_INNER_ALREADY_VOTED",
                    inter.locale,
                ),
                ephemeral=True,
            )

        if member_id in suggestion.down_voted_by:
            suggestion.down_voted_by.discard(member_id)
            suggestion.up_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            # await suggestion.update_vote_count(self.bot, inter)
            # lock.enqueue(suggestion.update_vote_count(self.bot, inter))
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_UP_VOTE_INNER_MODIFIED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} modified their vote on {suggestion_id} to a up vote",
                extra_metadata={
                    "suggestion_id": suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )
        else:
            suggestion.up_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_UP_VOTE_INNER_REGISTERED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} up voted {suggestion_id}",
                extra_metadata={
                    "suggestion_id": suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=self.bot)

    @components.button_listener()
    async def suggestion_down_vote(
        self,
        inter: disnake.MessageInteraction,
        *,
        suggestion_id: str,
    ):
        await inter.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, inter.guild_id, self.state
        )
        if suggestion.state != SuggestionState.pending:
            return await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_NO_MORE_CASTING",
                    inter.locale,
                ),
                ephemeral=True,
            )

        member_id = inter.author.id
        if member_id in suggestion.down_voted_by:
            return await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_ALREADY_VOTED",
                    inter.locale,
                ),
                ephemeral=True,
            )

        if member_id in suggestion.up_voted_by:
            suggestion.up_voted_by.discard(member_id)
            suggestion.down_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_MODIFIED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} modified their vote on {suggestion_id} to a down vote",
                extra_metadata={
                    "suggestion_id": suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )
        else:
            suggestion.down_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_REGISTERED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} down voted {suggestion_id}",
                extra_metadata={
                    "suggestion_id": suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=self.bot)

    @components.button_listener()
    async def queue_approve(self, inter: disnake.MessageInteraction):
        ih = await InteractionHandler.new_handler(inter)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, self.state
        )
        await self.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=True
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")

    @components.button_listener()
    async def queue_reject(self, inter: disnake.MessageInteraction):
        ih = await InteractionHandler.new_handler(inter)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, self.state
        )
        await self.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=False
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")

    @commands.slash_command(
        dm_permission=False,
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_user_is_not_blocklisted()
    @checks.ensure_guild_has_suggestions_channel()
    async def suggest(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion: str = commands.Param(),
        image: disnake.Attachment = commands.Param(default=None),
        anonymously: bool = commands.Param(default=False),
    ):
        """
        {{SUGGEST}}

        Parameters
        ----------
        suggestion: {{SUGGEST_ARG_SUGGESTION}}
        image: {{SUGGEST_ARG_IMAGE}}
        anonymously: {{SUGGEST_ARG_ANONYMOUSLY}}
        """
        if len(suggestion) > 1000:
            raise SuggestionTooLong

        await interaction.response.defer(ephemeral=True)

        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        if anonymously and not guild_config.can_have_anonymous_suggestions:
            await interaction.send(
                self.bot.get_locale(
                    "SUGGEST_INNER_NO_ANONYMOUS_SUGGESTIONS", interaction.locale
                ),
                ephemeral=True,
            )
            raise ErrorHandled

        image_url = None
        if image is not None:
            if not guild_config.can_have_images_in_suggestions:
                await interaction.send(
                    self.bot.get_locale(
                        "SUGGEST_INNER_NO_IMAGES_IN_SUGGESTIONS", interaction.locale
                    ),
                    ephemeral=True,
                )
                raise ErrorHandled

            image_url = await r2.upload_file_to_r2(
                file_name=image.filename,
                file_data=await image.read(use_cached=True),
                guild_id=interaction.guild_id,
                user_id=interaction.author.id,
            )

        if guild_config.uses_suggestion_queue:
            qs = await QueuedSuggestion.new(
                suggestion=suggestion,
                guild_id=interaction.guild_id,
                state=self.state,
                author_id=interaction.author.id,
                image_url=image_url,
                is_anonymous=anonymously,
            )
            if not guild_config.virtual_suggestion_queue:
                # Need to send to a channel
                if guild_config.queued_channel_id is None:
                    raise MissingQueueLogsChannel

                try:
                    queue_channel = await self.bot.state.fetch_channel(
                        guild_config.queued_channel_id
                    )
                except disnake.Forbidden as e:
                    raise MissingPermissionsToAccessQueueChannel from e

                qs_embed: disnake.Embed = await qs.as_embed(self.bot)
                msg = await queue_channel.send(
                    embed=qs_embed,
                    components=[
                        disnake.ui.Button(
                            label="Approve queued suggestion",
                            custom_id=await self.queue_approve.build_custom_id(),
                            style=ButtonStyle.green,
                        ),
                        disnake.ui.Button(
                            label="Reject queued suggestion",
                            custom_id=await self.queue_reject.build_custom_id(),
                            style=ButtonStyle.danger,
                        ),
                    ],
                )
                qs.message_id = msg.id
                qs.channel_id = msg.channel.id
                await self.bot.db.queued_suggestions.upsert(qs, qs)

            logger.debug(
                f"User {interaction.author.id} created new queued"
                f" suggestion in guild {interaction.guild_id}",
                extra_metadata={
                    "author_id": interaction.author.id,
                    "guild_id": interaction.guild_id,
                },
            )
            return await interaction.send(
                ephemeral=True,
                content=self.bot.get_localized_string(
                    "SUGGEST_INNER_SENT_TO_QUEUE",
                    interaction,
                    guild_config=guild_config,
                ),
            )

        icon_url = await Guild.try_fetch_icon_url(interaction.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        suggestion: Suggestion = await Suggestion.new(
            suggestion=suggestion,
            guild_id=interaction.guild_id,
            state=self.state,
            author_id=interaction.author.id,
            image_url=image_url,
            is_anonymous=anonymously,
        )
        await suggestion.setup_initial_messages(
            guild_config=guild_config,
            interaction=interaction,
            state=self.state,
            bot=self.bot,
            cog=self,
            guild=guild,
            icon_url=icon_url,
        )

        logger.debug(
            f"User {interaction.author.id} created new suggestion "
            f"{suggestion.suggestion_id} in guild {interaction.guild_id}",
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.SUGGEST,
        )

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_logs_channel_or_keep_logs()
    async def approve(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(),
        response: Optional[str] = commands.Param(
            default=None,
        ),
    ):
        """
        {{APPROVE}}

        Parameters
        ----------
        suggestion_id: str {{APPROVE_ARG_SUGGESTION_ID}}
        response: str {{APPROVE_ARG_RESPONSE}}
        """
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=self.state,
            interaction=interaction,
            resolution_note=response,
            resolution_type=SuggestionState.approved,
            bot=self.bot,
        )

        await interaction.send(
            self.bot.get_locale("APPROVE_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
            ephemeral=True,
        )
        logger.debug(
            f"User {interaction.author.id} approved suggestion "
            f"{suggestion.suggestion_id} in guild {interaction.guild_id}",
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.APPROVE,
        )

    @approve.autocomplete("suggestion_id")
    async def approve_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_logs_channel_or_keep_logs()
    async def reject(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(),
        response: Optional[str] = commands.Param(
            default=None,
        ),
    ):
        """
        {{REJECT}}

        Parameters
        ----------
        suggestion_id: str {{REJECT_ARG_SUGGESTION_ID}}
        response: str {{REJECT_ARG_RESPONSE}}
        """
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=self.state,
            interaction=interaction,
            resolution_note=response,
            resolution_type=SuggestionState.rejected,
            bot=self.bot,
        )

        await interaction.send(
            self.bot.get_locale("REJECT_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
            ephemeral=True,
        )
        logger.debug(
            f"User {interaction.author} rejected suggestion {suggestion.suggestion_id} "
            f"in guild {interaction.guild_id}",
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.REJECT,
        )

    @reject.autocomplete("suggestion_id")
    async def reject_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def clear(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(description="The sID you wish to clear"),
        response: Optional[str] = commands.Param(
            description="An optional response as to why this suggestion was cleared",
            default=None,
        ),
    ):
        """
        {{CLEAR}}

        Parameters
        ----------
        suggestion_id: str {{CLEAR_ARG_SUGGESTION_ID}}
        response: str {{CLEAR_ARG_RESPONSE}}
        """
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        if suggestion.channel_id and suggestion.message_id:
            try:
                channel: WrappedChannel = await self.bot.get_or_fetch_channel(
                    suggestion.channel_id
                )
                message: disnake.Message = await channel.fetch_message(
                    suggestion.message_id
                )
            except disnake.HTTPException:
                pass
            else:
                await message.delete()

        await suggestion.mark_cleared_by(self.state, interaction.user.id, response)
        await interaction.send(
            self.bot.get_locale("CLEAR_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
            ephemeral=True,
        )
        logger.debug(
            f"User {interaction.user.id} cleared suggestion"
            f" {suggestion_id} in guild {interaction.guild_id}",
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.CLEAR,
        )

    @clear.autocomplete("suggestion_id")
    async def clear_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    async def get_sid_for(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        user_input: str,
    ):
        try:
            values: list[str] = self.state.autocomplete_cache.get_entry(
                interaction.guild_id
            )
        except NonExistentEntry:
            values: list[str] = await self.state.populate_sid_cache(
                interaction.guild_id
            )
        else:
            if not values:
                logger.debug(
                    f"Values was found, but empty in guild {interaction.guild_id} thus populating",
                    extra_metadata={"guild_id": interaction.guild_id},
                )
                values: list[str] = await self.state.populate_sid_cache(
                    interaction.guild_id
                )

        possible_choices = [v for v in values if user_input.lower() in v.lower()]

        if len(possible_choices) > 25:
            return []

        return possible_choices


def setup(bot):
    bot.add_cog(SuggestionsCog(bot))
