from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND

from suggestions.exceptions import QueueImbalance
from suggestions.objects import QueuedSuggestion

if TYPE_CHECKING:
    from suggestions import SuggestionsBot


log = logging.getLogger(__name__)


class QueuedSuggestionsPaginator:
    def __init__(self, *, bot: SuggestionsBot, data, inter):
        self._current_page_index = 0
        self.bot: SuggestionsBot = bot
        self._paged_data: list[str] = data
        self.original_interaction: disnake.GuildCommandInteraction = inter

    @property
    def current_page(self) -> int:
        """The current page for this paginator."""
        return self._current_page_index + 1

    @current_page.setter
    def current_page(self, value) -> None:
        # Wrap around
        if value > self.total_pages:
            self._current_page_index = 0
        elif value <= 0:
            self._current_page_index = self.total_pages - 1
        else:
            self._current_page_index = value - 1

    @property
    def total_pages(self) -> int:
        """How many pages exist in this paginator."""
        return len(self._paged_data)

    async def remove_current_page(self):
        wrap = self.current_page == self.total_pages
        self._paged_data.pop(self._current_page_index)
        if wrap:
            self.current_page = 1

        if self.total_pages == 0:
            return await self.original_interaction.edit_original_message(
                embeds=[], components=[], content="No more suggestions in queue."
            )

        await self.original_interaction.edit_original_message(
            embed=await self.format_page()
        )

    async def get_current_queued_suggestion(self) -> QueuedSuggestion:
        qs: QueuedSuggestion = await self.bot.db.queued_suggestions.find(
            AQ(
                AND(
                    EQ("_id", self._paged_data[self._current_page_index]),
                )
            )
        )
        if not qs.still_in_queue:
            raise QueueImbalance

        return qs

    async def format_page(self) -> disnake.Embed:
        try:
            suggestion: QueuedSuggestion = await self.get_current_queued_suggestion()
        except QueueImbalance:
            await self.remove_current_page()
            log.debug("Hit QueueImbalance")
        else:
            embed: disnake.Embed = await suggestion.as_embed(self.bot, self.original_interaction)
            if suggestion.is_anonymous:
                embed.set_footer(text=f"Page {self.current_page}/{self.total_pages}")
            else:
                embed.set_footer(
                    text=f"Submitter ID: {suggestion.suggestion_author_id} | "
                    f"Page {self.current_page}/{self.total_pages}"
                )

            return embed
