from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands, components

from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import ErrorHandled
from suggestions.objects import GuildConfig

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, checks

log = logging.getLogger(__name__)


class SuggestionsQueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state = self.bot.state
        self.queued_suggestions_db: Document = self.bot.db.queued_suggestions
        self.paginator_objects: dict[str, ...] = {}

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    async def get_paginator_for(
        self, paginator_id: str, interaction: disnake.Interaction
    ) -> ...:
        try:
            return self.paginator_objects[paginator_id]
        except KeyError:
            await interaction.send(
                "This pagination session has expired, please start a new one with `/queue view`",
                ephemeral=True,
            )
            raise ErrorHandled

    @components.button_listener()
    async def next_button(
        self, inter: disnake.MessageInteraction, *, paginator_id: str
    ):
        pass

    @components.button_listener()
    async def previous_button(
        self, inter: disnake.MessageInteraction, *, paginator_id: str
    ):
        pass

    @components.button_listener()
    async def stop_button(
        self, inter: disnake.MessageInteraction, *, paginator_id: str
    ):
        pass

    @components.button_listener()
    async def approve_button(
        self, inter: disnake.MessageInteraction, *, paginator_id: str
    ):
        pass

    @components.button_listener()
    async def reject_button(
        self, inter: disnake.MessageInteraction, *, paginator_id: str
    ):
        pass

    @commands.slash_command(dm_permission=False)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_suggestions_channel()
    async def queue(self, interaction: disnake.GuildCommandInteraction):
        pass

    @queue.sub_command()
    async def info(self, interaction: disnake.GuildCommandInteraction):
        """View information about this guilds suggestions queue."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )

    @queue.sub_command()
    async def view(self, interaction: disnake.GuildCommandInteraction):
        """View this guilds suggestions queue."""
        message: disnake.Message = await channel.send(
            embed=await suggestion.as_embed(self.bot),
            components=[
                disnake.ui.Button(
                    emoji=await self.bot.suggestion_emojis.default_up_vote(),
                    custom_id=await self.suggestion_up_vote.build_custom_id(
                        suggestion_id=suggestion.suggestion_id
                    ),
                ),
                disnake.ui.Button(
                    emoji=await self.bot.suggestion_emojis.default_down_vote(),
                    custom_id=await self.suggestion_down_vote.build_custom_id(
                        suggestion_id=suggestion.suggestion_id
                    ),
                ),
            ],
        )


def setup(bot):
    bot.add_cog(SuggestionsQueueCog(bot))
