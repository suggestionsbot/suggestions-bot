from __future__ import annotations

import logging
import typing

import disnake
from disnake.ext import components
from disnake.ext.components import fields as component_fields
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from suggestions.clunk2 import update_suggestion_message
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import Suggestion, QueuedSuggestion
from suggestions.objects.suggestion import SuggestionState
from suggestions.utility import wrap_with_error_handler

if typing.TYPE_CHECKING:
    from suggestions.cogs.suggestion_cog import SuggestionsCog

log = logging.getLogger(__name__)
manager = components.get_manager("suggestions")


@manager.as_callback_wrapper
async def wrapper(
    _: components.ComponentManager,
    component: components.api.RichComponent,
    inter: disnake.Interaction,
):
    # Ignore if not message interaction
    if not isinstance(inter, disnake.MessageInteraction):
        yield
        return

    component_type = type(component)
    # CamelCase -> base36, snake_case -> base10
    # Check for camelcase based on casing of first char
    new_base = (
        36
        if inter.component.custom_id and inter.component.custom_id[0].isupper()
        else 0
    )

    # Update the parsers in-place...
    for field in component_fields.get_fields(
        component_type, kind=component_fields.FieldType.CUSTOM_ID
    ):
        parser = component_fields.get_parser(field)
        if isinstance(parser, components.parser.IntParser):
            parser.base = new_base

    # Run the component after updating parsers...
    tracer = trace.get_tracer("suggestions-bot-v3")
    btn_name: str = inter.component.custom_id
    try:
        if ":" in btn_name:
            btn_name = btn_name.split(":")[0]

        elif "|" in btn_name:
            btn_name = btn_name.split("|")[0][:-1]
    except:
        pass

    with tracer.start_as_current_span(f"component {btn_name}") as span:
        span.set_attribute("bot.cluster.id", inter.bot.cluster_id)
        span.set_attribute("interaction.author.id", inter.author.id)
        span.set_attribute(
            "interaction.author.global_name",
            inter.author.global_name if inter.author.global_name else "",
        )
        if inter.guild_id:
            span.set_attribute("interaction.guild.id", inter.guild_id)
        yield


@manager.register(identifier="suggestion_up_vote")
@manager.register()
class SuggestionUpVote(components.RichButton):
    suggestion_id: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: disnake.MessageInteraction,
    ) -> None:
        ih: InteractionHandler = await InteractionHandler.new_handler(inter)
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
            log.debug(
                f"Member {member_id} modified their vote on {self.suggestion_id} to a up vote",
                extra={
                    "suggestion.id": self.suggestion_id,
                    "interaction.guild.id": inter.guild_id,
                    "interaction.author.id": member_id,
                },
            )
        else:
            suggestion.up_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_UP_VOTE_INNER_REGISTERED_VOTE")
            log.debug(
                f"Member {member_id} up voted {self.suggestion_id}",
                extra={
                    "suggestion.id": self.suggestion_id,
                    "interaction.guild.id": inter.guild_id,
                    "interaction.author.id": member_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=ih.bot)


@manager.register(identifier="suggestion_down_vote")
@manager.register()
class SuggestionDownVote(components.RichButton):
    suggestion_id: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: disnake.MessageInteraction,
    ) -> None:
        ih: InteractionHandler = await InteractionHandler.new_handler(inter)
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
            log.debug(
                f"Member {member_id} modified their vote on {self.suggestion_id} to a down vote",
                extra={
                    "suggestion.id": self.suggestion_id,
                    "interaction.guild.id": inter.guild_id,
                    "interaction.author.id": member_id,
                },
            )
        else:
            suggestion.down_voted_by.add(member_id)
            await ih.bot.state.suggestions_db.upsert(suggestion, suggestion)
            await ih.send(translation_key="SUGGESTION_DOWN_VOTE_INNER_REGISTERED_VOTE")
            log.debug(
                f"Member {member_id} down voted {self.suggestion_id}",
                extra={
                    "suggestion.id": self.suggestion_id,
                    "interaction.guild.id": inter.guild_id,
                    "interaction.author.id": member_id,
                },
            )

        await update_suggestion_message(suggestion=suggestion, bot=ih.bot)


@manager.register(identifier="queue_approve")
@manager.register()
class SuggestionsQueueApprove(components.RichButton):
    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: disnake.MessageInteraction,
    ) -> None:
        ih = await InteractionHandler.new_handler(inter)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, ih.bot.state
        )
        cog: SuggestionsCog = ih.bot.cogs.get("SuggestionsCog")  # type: ignore
        await cog.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=True
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")


@manager.register(identifier="queue_reject")
@manager.register()
class SuggestionsQueueReject(components.RichButton):
    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: disnake.MessageInteraction,
    ) -> None:
        ih = await InteractionHandler.new_handler(inter)
        qs = await QueuedSuggestion.from_message_id(
            inter.message.id, inter.message.channel.id, ih.bot.state
        )
        cog: SuggestionsCog = ih.bot.cogs.get("SuggestionsCog")  # type: ignore
        await cog.qs_core.resolve_queued_suggestion(
            ih, queued_suggestion=qs, was_approved=False
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")
