from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import disnake

from suggestions.low_level import MessageEditing
from suggestions.objects import Suggestion

if TYPE_CHECKING:
    from suggestions import SuggestionsBot

log = logging.getLogger(__name__)

pending_edits: set[str] = set()


async def update_suggestion_message(
    *,
    suggestion: Suggestion,
    bot: SuggestionsBot,
    time_after: float = 10,
    locale : disnake.Locale
):
    if suggestion.suggestion_id in pending_edits:
        log.debug("Ignoring already existing item %s", suggestion.suggestion_id)
        return

    pending_edits.add(suggestion.suggestion_id)
    await asyncio.sleep(time_after)
    try:
        await MessageEditing(
            bot, channel_id=suggestion.channel_id, message_id=suggestion.message_id
        ).edit(embed=await suggestion.as_embed(bot, locale))
    except (disnake.HTTPException, disnake.NotFound):
        log.error("Failed to update suggestion %s", suggestion.suggestion_id)

    pending_edits.discard(suggestion.suggestion_id)
