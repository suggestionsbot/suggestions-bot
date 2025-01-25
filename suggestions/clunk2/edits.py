from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import commons
import disnake
from logoo import Logger

from suggestions.low_level import MessageEditing

if TYPE_CHECKING:
    from suggestions.objects import Suggestion
    from suggestions import SuggestionsBot

logger = Logger(__name__)

pending_edits: set[str] = set()


async def update_suggestion_message(
    *,
    suggestion: Suggestion,
    bot: SuggestionsBot,
    time_after: float = 10,
):
    if suggestion.suggestion_id in pending_edits:
        logger.debug(
            "Ignoring already existing item %s",
            suggestion.suggestion_id,
            extra_metadata={
                "guild_id": suggestion.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        return

    pending_edits.add(suggestion.suggestion_id)
    await asyncio.sleep(time_after)
    if suggestion.channel_id is None or suggestion.message_id is None:
        logger.debug(
            "Suggestion %s had a NoneType by the time it was to be edited channel_id=%s, message_id=%s",
            suggestion.suggestion_id,
            suggestion.channel_id,
            suggestion.message_id,
            extra_metadata={
                "guild_id": suggestion.guild_id,
                "suggestion_id": suggestion.suggestion_id,
            },
        )
        pending_edits.discard(suggestion.suggestion_id)
        return

    # We do this to avoid a race condition where the suggestion may have
    # had a value modified between when it was added to the edit queue
    # and the time at which it was actually edited
    up_to_date_suggestion: Suggestion = await bot.state.suggestions_db.find(suggestion)
    try:
        await MessageEditing(
            bot,
            channel_id=up_to_date_suggestion.channel_id,
            message_id=up_to_date_suggestion.message_id,
        ).edit(embed=await up_to_date_suggestion.as_embed(bot))
    except (disnake.HTTPException, disnake.NotFound) as e:
        logger.debug(
            "Failed to update suggestion %s",
            suggestion.suggestion_id,
            extra_metadata={
                "guild_id": suggestion.guild_id,
                "suggestion_id": suggestion.suggestion_id,
                "traceback": commons.exception_as_string(e),
            },
        )

    pending_edits.discard(suggestion.suggestion_id)
