from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import cooldowns
import disnake
import orjson
from commons.caching import NonExistentEntry
from cooldowns import Cooldown
from disnake import ButtonStyle
from disnake.ext import commands
from logoo import Logger

from suggestions import checks, Stats, buttons
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.core import SuggestionsQueue, SuggestionsResolutionCore
from suggestions.exceptions import (
    SuggestionTooLong,
    ErrorHandled,
    MissingPermissionsToAccessQueueChannel,
    MissingQueueLogsChannel,
    SuggestionNotFound,
)
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import (
    Suggestion,
    GuildConfig,
    QueuedSuggestion,
    PremiumGuildConfig,
)
from suggestions.utility import r2

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

logger = Logger(__name__)


async def user_cooldown_bucket(inter: disnake.Interaction) -> int:
    return inter.author.id


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats
        self.suggestions_db: Document = self.bot.db.suggestions

        self.qs_core: SuggestionsQueue = SuggestionsQueue(bot)
        self.resolution_core: SuggestionsResolutionCore = SuggestionsResolutionCore(bot)

    async def handle_custom_suggestion_cooldown(self, ih: InteractionHandler):
        premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
            ih.interaction.guild_id, ih.bot.state
        )
        if (
            premium_guild_config.cooldown_amount is None
            or premium_guild_config.cooldown_period is None
        ):
            return True

        bot: SuggestionsBot = ih.bot
        redis_state = await bot.redis.get(f"PREMIUM_COOLDOWN:{ih.interaction.guild_id}")
        cooldown = Cooldown(
            premium_guild_config.cooldown_amount,
            premium_guild_config.cooldown_period.as_timedelta(),
            bucket=user_cooldown_bucket,
        )
        if redis_state is not None and redis_state:
            cooldown.load_from_state(orjson.loads(redis_state))

        await cooldown.increment(ih.interaction)

        await bot.redis.set(
            f"PREMIUM_COOLDOWN:{ih.interaction.guild_id}",
            orjson.dumps(cooldown.get_state()),
        )
        del cooldown
        return None

    @commands.slash_command()
    @commands.contexts(guild=True)
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
            raise SuggestionTooLong(suggestion)

        ih: InteractionHandler = await InteractionHandler.new_handler(interaction)
        entitlements: list[disnake.Entitlement] = [
            e
            for e in interaction.entitlements
            if e.is_active()  # and e.sku_id == interaction.bot.guild_subscription_sku_id
        ]
        if entitlements or 1 == 1:
            # Premium, handle custom cooldowns
            await self.handle_custom_suggestion_cooldown(ih)

        suggestion: str = suggestion.replace("\\n", "\n")

        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        if anonymously and not guild_config.can_have_anonymous_suggestions:
            await ih.send(
                self.bot.get_locale(
                    "SUGGEST_INNER_NO_ANONYMOUS_SUGGESTIONS", interaction.locale
                ),
            )
            raise ErrorHandled

        image_url = None
        if image is not None:
            if not guild_config.can_have_images_in_suggestions:
                await ih.send(
                    self.bot.get_locale(
                        "SUGGEST_INNER_NO_IMAGES_IN_SUGGESTIONS", interaction.locale
                    ),
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

                premium_guild_config: PremiumGuildConfig = (
                    await PremiumGuildConfig.from_id(qs.guild_id, interaction.bot.state)
                )
                qs_embed: disnake.Embed = await qs.as_embed(self.bot)
                msg = await queue_channel.send(
                    content=premium_guild_config.queued_suggestions_prefix or None,
                    embed=qs_embed,
                    components=[
                        await buttons.SuggestionsQueueApprove(
                            label="Approve queued suggestion",
                            style=ButtonStyle.green,
                        ).as_ui_component(),
                        await buttons.SuggestionsQueueReject(
                            label="Reject queued suggestion",
                            style=ButtonStyle.danger,
                        ).as_ui_component(),
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
            return await ih.send(
                content=self.bot.get_localized_string(
                    "SUGGEST_INNER_SENT_TO_QUEUE",
                    interaction,
                    guild_config=guild_config,
                ),
            )

        icon_url = await self.bot.try_fetch_icon_url(interaction.guild_id)
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
            ih=ih,
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
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
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
        await self.resolution_core.approve(
            await InteractionHandler.new_handler(interaction), suggestion_id, response
        )

    @approve.autocomplete("suggestion_id")
    async def approve_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
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
        await self.resolution_core.reject(
            await InteractionHandler.new_handler(interaction), suggestion_id, response
        )

    @reject.autocomplete("suggestion_id")
    async def reject_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
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
        try:
            suggestion_type = "suggestion"
            suggestion: Suggestion = await Suggestion.from_id(
                suggestion_id, interaction.guild_id, self.state
            )
            if suggestion.channel_id and suggestion.message_id:
                await self.bot.delete_message(
                    message_id=suggestion.message_id, channel_id=suggestion.channel_id
                )

            await suggestion.mark_cleared_by(self.state, interaction.user.id, response)
        except SuggestionNotFound:
            # Maybe its a queued suggestion?
            suggestion_type = "queued_suggestion"
            suggestion: QueuedSuggestion = await QueuedSuggestion.from_id(
                suggestion_id, interaction.guild_id, self.state
            )
            if suggestion.channel_id and suggestion.message_id:
                await self.bot.delete_message(
                    message_id=suggestion.message_id, channel_id=suggestion.channel_id
                )

            suggestion.channel_id = None
            suggestion.message_id = None
            await suggestion.resolve(
                state=self.state, resolved_by=interaction.user.id, was_approved=False
            )

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
                "suggestion_id": suggestion_id,
                "suggestion_type": suggestion_type,
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
