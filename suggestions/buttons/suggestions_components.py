from __future__ import annotations

import typing

import logoo
from disnake.ext import components
from disnake.ext.components import interaction

from suggestions import SuggestionsBot
from suggestions.clunk2 import update_suggestion_message
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects.suggestion import SuggestionState
from suggestions.utility import wrap_with_error_handler
from suggestions.objects import Suggestion


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
        bot: SuggestionsBot = inter.bot
        ih: InteractionHandler = await InteractionHandler.new_handler(inter)
        suggestion: Suggestion = await Suggestion.from_id(
            self.suggestion_id, inter.guild_id, bot.state
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
            await bot.state.suggestions_db.upsert(suggestion, suggestion)
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
            await bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_UP_VOTE_INNER_REGISTERED_VOTE")
            logger.debug(
                f"Member {member_id} up voted {self.suggestion_id}",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=bot)


@manager.register  # type: ignore
class SuggestionDownVote(components.RichButton):
    suggestion_id: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: interaction.MessageInteraction,
    ) -> None:
        bot: SuggestionsBot = inter.bot
        await inter.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_id(
            self.suggestion_id, inter.guild_id, bot.state
        )
        if suggestion.state != SuggestionState.pending:
            return await inter.send(
                bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_NO_MORE_CASTING",
                    inter.locale,
                ),
                ephemeral=True,
            )

        member_id = inter.author.id
        if member_id in suggestion.down_voted_by:
            return await inter.send(
                bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_ALREADY_VOTED",
                    inter.locale,
                ),
                ephemeral=True,
            )

        if member_id in suggestion.up_voted_by:
            suggestion.up_voted_by.discard(member_id)
            suggestion.down_voted_by.add(member_id)
            await bot.state.suggestions_db.upsert(suggestion, suggestion)
            await inter.send(
                bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_MODIFIED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} modified their vote on {self.suggestion_id} to a down vote",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )
        else:
            suggestion.down_voted_by.add(member_id)
            await bot.state.suggestions_db.upsert(suggestion, suggestion)
            await inter.send(
                bot.get_locale(
                    "SUGGESTION_DOWN_VOTE_INNER_REGISTERED_VOTE",
                    inter.locale,
                ),
                ephemeral=True,
            )
            logger.debug(
                f"Member {member_id} down voted {self.suggestion_id}",
                extra_metadata={
                    "suggestion_id": self.suggestion_id,
                    "guild_id": inter.guild_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=bot)
