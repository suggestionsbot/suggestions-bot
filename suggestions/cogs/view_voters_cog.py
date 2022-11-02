from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Type

import cooldowns
import disnake
from disnake.ext import commands
from bot_base.paginators.disnake_paginator import DisnakePaginator

from suggestions import Stats, Colors
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import Suggestion

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class VoterPaginator(DisnakePaginator):
    def __init__(
        self,
        data,
        suggestion_id: str,
        title_prefix: str,
        colors: Type[Colors],
    ):
        self.colors: Type[Colors] = colors
        self.title_prefix: str = title_prefix.lstrip()
        self.suggestion_id: str = suggestion_id
        super().__init__(
            items_per_page=15, delete_buttons_on_stop=True, input_data=data
        )

    async def format_page(self, page_items: list, page_number: int) -> disnake.Embed:
        embed = disnake.Embed(
            title=f"{self.title_prefix} for suggestion `{self.suggestion_id}`",
            description="\n".join(page_items),
            colour=self.colors.embed_color,
        )
        embed.set_footer(text=f"Page {page_number} of {self.total_pages}")
        return embed


# noinspection DuplicatedCode
class ViewVotersCog(commands.Cog):
    """This cog allows users to view who has voted on a given suggestion."""

    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.suggestions_db: Document = self.bot.db.suggestions

    async def display_data(
        self,
        interaction: disnake.GuildCommandInteraction,
        *,
        data,
        suggestion: Suggestion,
        title_prefix: str,
    ):
        """Display the paginated data to an end user."""
        if not suggestion.uses_views_for_votes:
            return await interaction.send(
                "Suggestions using reactions are not supported by this command.",
                ephemeral=True,
            )

        if not data:
            return await interaction.send(
                "There are no voters to show you for this.",
                ephemeral=True,
            )

        vp: VoterPaginator = VoterPaginator(
            data,
            suggestion.suggestion_id,
            title_prefix=title_prefix,
            colors=self.bot.colors,
        )
        await vp.start(interaction=interaction)

    @commands.message_command(name="View voters")
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def view_suggestion_voters(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """View everyone who voted on this suggestion."""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_message_id(
            message_id=interaction.target.id,
            channel_id=interaction.channel_id,
            state=self.state,
        )

        up_vote: disnake.Emoji = await self.bot.suggestion_emojis.default_up_vote()
        down_vote: disnake.Emoji = await self.bot.suggestion_emojis.default_down_vote()
        data = []
        for voter in suggestion.up_voted_by:
            data.append(f"{up_vote} <@{voter}>")
        data.append("")
        for voter in suggestion.down_voted_by:
            data.append(f"{down_vote} <@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix="Voters",
        )

    @commands.message_command(name="View up voters")
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def view_suggestion_up_voters(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """View everyone who up voted on this suggestion."""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_message_id(
            message_id=interaction.target.id,
            channel_id=interaction.channel_id,
            state=self.state,
        )
        data = []
        for voter in suggestion.up_voted_by:
            data.append(f"<@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix="Up voters",
        )

    @commands.message_command(name="View down voters")
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def view_suggestion_down_voters(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """View everyone who down voted on this suggestion."""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_message_id(
            message_id=interaction.target.id,
            channel_id=interaction.channel_id,
            state=self.state,
        )
        data = []
        for voter in suggestion.down_voted_by:
            data.append(f"<@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix="Down voters",
        )


def setup(bot):
    bot.add_cog(ViewVotersCog(bot))
