from alaric.comparison import EQ
from logoo import Logger

from suggestions.core import BaseCore, SuggestionsQueue
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import GuildConfig, Suggestion, QueuedSuggestion
from suggestions.objects.suggestion import SuggestionState

logger = Logger(__name__)


class SuggestionsResolutionCore(BaseCore):
    def __init__(self, bot):
        super().__init__(bot)
        self.qs_core: SuggestionsQueue = SuggestionsQueue(bot)

    async def approve(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None = None
    ):
        exists = await ih.bot.db.suggestions.count(EQ("_id", suggestion_id))
        if exists == 0:
            await self.approve_queued_suggestion(ih, suggestion_id, response)
        else:
            await self.approve_suggestion(ih, suggestion_id, response)

    async def approve_queued_suggestion(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None = None
    ):
        qs = await QueuedSuggestion.from_id(
            suggestion_id, ih.interaction.guild_id, ih.bot.state
        )
        qs.resolution_note = response
        await ih.bot.db.queued_suggestions.update(qs, qs)

        await self.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=True
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")

    async def approve_suggestion(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None
    ):
        guild_config: GuildConfig = await GuildConfig.from_id(
            ih.interaction.guild_id, ih.bot.state
        )
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, ih.interaction.guild_id, ih.bot.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=ih.bot.state,
            interaction=ih.interaction,
            resolution_note=response,
            resolution_type=SuggestionState.approved,
            bot=self.bot,
        )

        await ih.send(
            self.bot.get_locale("APPROVE_INNER_MESSAGE", ih.interaction.locale).format(
                suggestion_id
            ),
        )
        logger.debug(
            f"User {ih.interaction.author.id} approved suggestion "
            f"{suggestion.suggestion_id} in guild {ih.interaction.guild_id}",
            extra_metadata={
                "author_id": ih.interaction.author.id,
                "guild_id": ih.interaction.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        await ih.bot.stats.log_stats(
            ih.interaction.author.id,
            ih.interaction.guild_id,
            ih.bot.stats.type.APPROVE,
        )

    async def reject(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None = None
    ):
        exists = await ih.bot.db.suggestions.count(EQ("_id", suggestion_id))
        if exists == 0:
            await self.reject_queued_suggestion(ih, suggestion_id, response)
        else:
            await self.reject_suggestion(ih, suggestion_id, response)

    async def reject_queued_suggestion(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None = None
    ):
        qs = await QueuedSuggestion.from_id(
            suggestion_id, ih.interaction.guild_id, ih.bot.state
        )
        qs.resolution_note = response
        qs.resolved_by = ih.interaction.author.id
        await ih.bot.db.queued_suggestions.update(qs, qs)

        await self.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=False
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")

    async def reject_suggestion(
        self, ih: InteractionHandler, suggestion_id: str, response: str | None
    ):
        interaction = ih.interaction
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, ih.bot.state
        )
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, ih.bot.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=ih.bot.state,
            interaction=interaction,
            resolution_note=response,
            resolution_type=SuggestionState.rejected,
            bot=self.bot,
        )

        await ih.send(
            self.bot.get_locale("REJECT_INNER_MESSAGE", interaction.locale).format(
                suggestion_id
            ),
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
        await ih.bot.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            ih.bot.stats.type.REJECT,
        )
