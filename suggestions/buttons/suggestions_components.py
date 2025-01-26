from __future__ import annotations

import typing

import logoo
from disnake.ext import components
from disnake.ext.components import interaction

from suggestions.clunk2 import update_suggestion_message
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import Suggestion, QueuedSuggestion
from suggestions.objects.suggestion import SuggestionState
from suggestions.utility import wrap_with_error_handler

if typing.TYPE_CHECKING:
    from suggestions.cogs.suggestion_cog import SuggestionsCog

logger = logoo.Logger(__name__)
manager = components.get_manager("suggestions")


@manager.register  # type: ignore
class SuggestionUpVote(components.RichButton):
    suggestion_id: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: components.MessageInteraction,
    ) -> None:
        ih: InteractionHandler = await InteractionHandler.new_handler(inter._wrapped)
        suggestion: Suggestion = await Suggestion.from_id(
            self.suggestion_id, inter.guild_id, ih.bot.state
        )
        if suggestion.state != SuggestionState.pending:
            return await ih.send(
                translation_key="SUGGESTION_UP_VOTE_INNER_NO_MORE_CASTING"
            )

        member_id = inter.author.id
        if member_id in suggestion.up_voted_by:
            return await ih.send(
                translation_key="SUGGESTION_UP_VOTE_INNER_ALREADY_VOTED"
            )

        if member_id in suggestion.down_voted_by:
            suggestion.down_voted_by.discard(member_id)
            suggestion.up_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            # await suggestion.update_vote_count(self.bot, inter)
            # lock.enqueue(suggestion.update_vote_count(self.bot, inter))
            await ih.send(translation_key="SUGGESTION_UP_VOTE_INNER_MODIFIED_VOTE")
            logger.debug(
                f"Member {member_id} modified their vote on {self.suggestion_id} to a up vote",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )
        else:
            suggestion.up_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_UP_VOTE_INNER_REGISTERED_VOTE")
            logger.debug(
                f"Member {member_id} up voted {self.suggestion_id}",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=ih.bot)


@manager.register  # type: ignore
class SuggestionDownVote(components.RichButton):
    suggestion_id: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: interaction.MessageInteraction,
    ) -> None:
        ih: InteractionHandler = await InteractionHandler.new_handler(inter._wrapped)
        suggestion: Suggestion = await Suggestion.from_id(
            self.suggestion_id, inter.guild_id, ih.bot.state
        )
        if suggestion.state != SuggestionState.pending:
            return await ih.send(
                translation_key="SUGGESTION_DOWN_VOTE_INNER_NO_MORE_CASTING"
            )

        member_id = inter.author.id
        if member_id in suggestion.down_voted_by:
            return await ih.send(
                translation_key="SUGGESTION_DOWN_VOTE_INNER_ALREADY_VOTED"
            )

        if member_id in suggestion.up_voted_by:
            suggestion.up_voted_by.discard(member_id)
            suggestion.down_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_DOWN_VOTE_INNER_MODIFIED_VOTE")
            logger.debug(
                f"Member {member_id} modified their vote on {self.suggestion_id} to a down vote",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )
        else:
            suggestion.down_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_DOWN_VOTE_INNER_REGISTERED_VOTE")
            logger.debug(
                f"Member {member_id} down voted {self.suggestion_id}",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=ih.bot)


@manager.register  # type:ignore
class SuggestionsQueueApprove(components.RichButton):
    @wrap_with_error_handler()
    async def callback(self, inter: interaction.MessageInteraction):
        ih = await InteractionHandler.new_handler(inter._wrapped)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, ih.bot.state
        )
        cog: SuggestionsCog = ih.bot.cogs.get("SuggestionsCog")  # type: ignore
        await cog.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=True
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")


@manager.register  # type:ignore
class SuggestionsQueueReject(components.RichButton):
    @wrap_with_error_handler()
    async def callback(self, inter: interaction.MessageInteraction):
        ih = await InteractionHandler.new_handler(inter._wrapped)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, ih.bot.state
        )
        cog: SuggestionsCog = ih.bot.cogs.get("SuggestionsCog")  # type: ignore
        await cog.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=False
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")
