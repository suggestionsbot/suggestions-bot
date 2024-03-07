from __future__ import annotations

from typing import TYPE_CHECKING, Type

import cooldowns
import disnake
from commons.caching import NonExistentEntry
from disnake.ext import commands
from bot_base.paginators.disnake_paginator import DisnakePaginator
from logoo import Logger

from suggestions import Colors
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import Suggestion
from suggestions.objects.suggestion import SuggestionState

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

logger = Logger(__name__)


class VoterPaginator(DisnakePaginator):
    def __init__(
        self,
        data,
        suggestion_id: str,
        title_prefix: str,
        colors: Type[Colors],
        bot: SuggestionsBot,
        locale: disnake.Locale,
    ):
        self.bot: SuggestionsBot = bot
        self.locale: disnake.Locale = locale
        self.colors: Type[Colors] = colors
        self.title_prefix: str = title_prefix.lstrip()
        self.suggestion_id: str = suggestion_id
        super().__init__(
            items_per_page=15, delete_buttons_on_stop=True, input_data=data
        )

    async def format_page(self, page_items: list, page_number: int) -> disnake.Embed:
        embed = disnake.Embed(
            title=self.bot.get_locale(
                "VOTER_PAGINATOR_INNER_EMBED_TITLE", self.locale
            ).format(self.title_prefix, self.suggestion_id),
            description="\n".join(page_items),
            colour=self.colors.embed_color,
        )
        embed.set_footer(
            text=self.bot.get_locale(
                "VOTER_PAGINATOR_INNER_EMBED_FOOTER", self.locale
            ).format(page_number, self.total_pages)
        )
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
                self.bot.get_locale(
                    "DISPLAY_DATA_INNER_OLD_SUGGESTION_TYPE", interaction.locale
                ),
                ephemeral=True,
            )

        if not data:
            return await interaction.send(
                self.bot.get_locale("DISPLAY_DATA_INNER_NO_VOTERS", interaction.locale),
                ephemeral=True,
            )

        vp: VoterPaginator = VoterPaginator(
            data,
            suggestion.suggestion_id,
            title_prefix=title_prefix,
            colors=self.bot.colors,
            bot=self.bot,
            locale=interaction.locale,
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
        if suggestion.state == SuggestionState.cleared:
            return await interaction.send(
                self.bot.get_locale(
                    "VIEW_VOTERS_CLEARED_SUGGESTION", interaction.locale
                ),
                ephemeral=True,
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
            title_prefix=self.bot.get_locale(
                "VIEW_VOTERS_INNER_TITLE_PREFIX", interaction.locale
            ),
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
        if suggestion.state == SuggestionState.cleared:
            return await interaction.send(
                self.bot.get_locale(
                    "VIEW_VOTERS_CLEARED_SUGGESTION", interaction.locale
                ),
                ephemeral=True,
            )

        data = []
        for voter in suggestion.up_voted_by:
            data.append(f"<@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix=self.bot.get_locale(
                "VIEW_UP_VOTERS_INNER_TITLE_PREFIX", interaction.locale
            ),
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
        if suggestion.state == SuggestionState.cleared:
            return await interaction.send(
                self.bot.get_locale(
                    "VIEW_VOTERS_CLEARED_SUGGESTION", interaction.locale
                ),
                ephemeral=True,
            )

        data = []
        for voter in suggestion.down_voted_by:
            data.append(f"<@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix=self.bot.get_locale(
                "VIEW_DOWN_VOTERS_INNER_TITLE_PREFIX", interaction.locale
            ),
        )

    @commands.slash_command(name="view")
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def view_voters_parent(self, interaction: disnake.GuildCommandInteraction):
        pass

    @view_voters_parent.sub_command(name="voters")
    async def view_voters(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(
            description="The suggestion you want to view voters for"
        ),
        filter: str = commands.Param(
            choices=["All voters", "Up voters", "Down voters"],
            default="All voters",
            description="The voters to view for this suggestion",
        ),
    ):
        """View the voters on a given suggestion"""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id=suggestion_id,
            guild_id=interaction.guild_id,
            state=self.state,
        )
        if suggestion.state == SuggestionState.cleared:
            return await interaction.send(
                self.bot.get_locale(
                    "VIEW_VOTERS_CLEARED_SUGGESTION", interaction.locale
                ),
                ephemeral=True,
            )

        data = []
        up_vote: disnake.Emoji = await self.bot.suggestion_emojis.default_up_vote()
        down_vote: disnake.Emoji = await self.bot.suggestion_emojis.default_down_vote()
        if filter in ("All voters", "Up voters"):
            for voter in suggestion.up_voted_by:
                data.append(f"{up_vote} <@{voter}>")
            data.append("")

        if filter in ("All voters", "Down voters"):
            for voter in suggestion.down_voted_by:
                data.append(f"{down_vote} <@{voter}>")

        await self.display_data(
            interaction,
            data=data,
            suggestion=suggestion,
            title_prefix=self.bot.get_localized_string(
                "VIEW_VOTERS_INNER_EMBED_TITLE",
                interaction,
            ),
        )

    @view_voters.autocomplete("suggestion_id")
    async def get_sid_for(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        user_input: str,
    ):
        try:
            values: list[str] = self.state.view_voters_cache.get_entry(
                interaction.guild_id
            )
        except NonExistentEntry:
            values: list[str] = await self.state.populate_view_voters_cache(
                interaction.guild_id
            )
        else:
            if not values:
                logger.debug(
                    "Values was found, but empty in guild %s thus populating",
                    interaction.guild_id,
                    extra_metadata={"guild_id": interaction.guild_id},
                )
                values: list[str] = await self.state.populate_view_voters_cache(
                    interaction.guild_id
                )

        possible_choices = [v for v in values if user_input.lower() in v.lower()]

        if len(possible_choices) > 25:
            return []

        return possible_choices


def setup(bot):
    bot.add_cog(ViewVotersCog(bot))
