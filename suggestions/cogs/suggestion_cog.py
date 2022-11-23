from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional, cast

import cooldowns
import disnake
from bot_base import NonExistentEntry
from bot_base.wraps import WrappedChannel
from disnake import Guild
from disnake.ext import commands, components

from suggestions import checks, Stats
from suggestions.clunk import ClunkLock
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import SuggestionTooLong
from suggestions.objects import Suggestion, GuildConfig, UserConfig
from suggestions.objects.stats import MemberStats
from suggestions.objects.suggestion import SuggestionState

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats
        self.suggestions_db: Document = self.bot.db.suggestions

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

        lock: ClunkLock = self.bot.clunk.acquire(suggestion_id)
        await lock.run()

        if member_id in suggestion.down_voted_by:
            suggestion.down_voted_by.discard(member_id)
            suggestion.up_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            # await suggestion.update_vote_count(self.bot, inter)
            lock.enqueue(suggestion.update_vote_count(self.bot, inter))
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_UP_VOTE_INNER_MODIFIED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            # log.debug(
            #     "Member %s modified their vote on %s to an up vote",
            #     member_id,
            #     suggestion_id,
            # )
            return

        suggestion.up_voted_by.add(member_id)
        await self.state.suggestions_db.upsert(suggestion, suggestion)
        # await suggestion.update_vote_count(self.bot, inter)
        lock.enqueue(suggestion.update_vote_count(self.bot, inter))
        await inter.send(
            self.bot.get_locale(
                "SUGGESTION_UP_VOTE_INNER_REGISTERED_VOTE",
                inter.locale,
            ),
            ephemeral=True,
        )
        # log.debug("Member %s up voted suggestion %s", member_id, suggestion_id)

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

        lock: ClunkLock = self.bot.clunk.acquire(suggestion_id)
        await lock.run()

        if member_id in suggestion.up_voted_by:
            suggestion.up_voted_by.discard(member_id)
            suggestion.down_voted_by.add(member_id)
            await self.state.suggestions_db.upsert(suggestion, suggestion)
            # await suggestion.update_vote_count(self.bot, inter)
            lock.enqueue(suggestion.update_vote_count(self.bot, inter))
            await inter.send(
                self.bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_MODIFIED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            # log.debug(
            #     "Member %s modified their vote on %s to a down vote",
            #     member_id,
            #     suggestion_id,
            # )
            return

        suggestion.down_voted_by.add(member_id)
        await self.state.suggestions_db.upsert(suggestion, suggestion)
        # await suggestion.update_vote_count(self.bot, inter)
        lock.enqueue(suggestion.update_vote_count(self.bot, inter))
        await inter.send(
            self.bot.get_locale(
                "SUGGESTION_DOWN_VOTE_INNER_REGISTERED_VOTE",
                inter.locale,
            ),
            ephemeral=True,
        )
        # log.debug("Member %s down voted suggestion %s", member_id, suggestion_id)

    @commands.slash_command(dm_permission=False)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_suggestions_channel()
    async def suggest(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion: str = commands.Param(description="Your suggestion"),
        image: disnake.Attachment = commands.Param(
            default=None, description="An image to add to your suggestion."
        ),
    ):
        """Create a new suggestion."""
        if len(suggestion) > 1000:
            raise SuggestionTooLong

        await interaction.response.defer(ephemeral=True)
        icon_url = await Guild.try_fetch_icon_url(interaction.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        image_url = image.url if isinstance(image, disnake.Attachment) else None
        suggestion: Suggestion = await Suggestion.new(
            suggestion=suggestion,
            guild_id=interaction.guild_id,
            state=self.state,
            author_id=interaction.author.id,
            image_url=image_url,
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        try:
            channel: WrappedChannel = await self.bot.get_or_fetch_channel(
                guild_config.suggestions_channel_id
            )
            channel: disnake.TextChannel = cast(disnake.TextChannel, channel)
            message: disnake.Message = await channel.send(
                embed=await suggestion.as_embed(self.bot),
                components=[
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_up_vote(),
                        custom_id=await self.suggestion_up_vote.build_custom_id(
                            suggestion_id=suggestion.suggestion_id
                        ),
                    ),
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_down_vote(),
                        custom_id=await self.suggestion_down_vote.build_custom_id(
                            suggestion_id=suggestion.suggestion_id
                        ),
                    ),
                ],
            )
        except disnake.Forbidden as e:
            self.state.remove_sid_from_cache(
                interaction.guild_id, suggestion.suggestion_id
            )
            await self.suggestions_db.delete(suggestion.as_filter())
            raise e

        suggestion.message_id = message.id
        suggestion.channel_id = channel.id
        await self.state.suggestions_db.upsert(suggestion, suggestion)

        try:
            embed: disnake.Embed = disnake.Embed(
                description=self.bot.get_locale(
                    "SUGGEST_INNER_SUGGESTION_SENT", interaction.locale
                ).format(
                    interaction.author.mention,
                    channel.mention,
                    suggestion.suggestion_id,
                ),
                timestamp=self.state.now,
                color=self.bot.colors.embed_color,
            )
            embed.set_author(
                name=guild.name,
                icon_url=icon_url,
            )
            embed.set_footer(
                text=self.bot.get_locale(
                    "SUGGEST_INNER_SUGGESTION_SENT_FOOTER", interaction.locale
                ).format(interaction.guild_id, suggestion.suggestion_id)
            )
            user_config: UserConfig = await UserConfig.from_id(
                interaction.author.id, self.bot.state
            )
            if user_config.dm_messages_disabled or guild_config.dm_messages_disabled:
                await interaction.send(embed=embed, ephemeral=True)
            else:
                await interaction.send(
                    self.bot.get_locale("SUGGEST_INNER_THANKS", interaction.locale),
                    ephemeral=True,
                )
                await interaction.author.send(embed=embed)
        except disnake.HTTPException as e:
            log.debug(
                "Failed to DM %s regarding there suggestion",
                interaction.author.id,
            )

        if guild_config.threads_for_suggestions:
            try:
                await suggestion.create_thread(message)
            except Exception as e:
                log.debug(
                    "Failed to create a thread on suggestion %s with error %s",
                    suggestion.suggestion_id,
                    str(e),
                )
            else:
                log.debug("Created a thread on suggestion %s", suggestion.suggestion_id)

        log.debug(
            "User %s created new suggestion %s in guild %s",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
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
        suggestion_id: str = commands.Param(description="The sID you wish to approve"),
        response: Optional[str] = commands.Param(
            description="An optional response to add to the suggestion", default=None
        ),
    ):
        """Approve a suggestion."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        await suggestion.mark_approved_by(self.state, interaction.author.id, response)
        await suggestion.edit_message_after_finalization(
            state=self.state,
            bot=self.bot,
            interaction=interaction,
            guild_config=guild_config,
        )

        await interaction.send(
            self.bot.get_locale("APPROVE_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
            ephemeral=True,
        )
        log.debug(
            "User %s approved suggestion %s in guild %s",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
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
        suggestion_id: str = commands.Param(description="The sID you wish to reject"),
        response: Optional[str] = commands.Param(
            description="An optional response to add to the suggestion", default=None
        ),
    ):
        """Reject a suggestion."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        await suggestion.mark_rejected_by(self.state, interaction.author.id, response)
        await suggestion.edit_message_after_finalization(
            state=self.state,
            bot=self.bot,
            interaction=interaction,
            guild_config=guild_config,
        )

        await interaction.send(
            self.bot.get_locale("REJECT_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
            ephemeral=True,
        )
        log.debug(
            "User %s rejected suggestion %s in guild %s",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
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
        """Remove a suggestion and any associated messages."""
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
        log.debug(
            "User %s cleared suggestion %s in guild %s",
            interaction.user.id,
            suggestion_id,
            interaction.guild_id,
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
                log.debug(
                    "Values was found, but empty in guild %s thus populating",
                    interaction.guild_id,
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
