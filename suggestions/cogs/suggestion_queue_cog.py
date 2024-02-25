from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import cooldowns
import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from alaric.projections import Projection, SHOW
from commons.caching import NonExistentEntry, TimedCache
from disnake import Guild
from disnake.ext import commands, components

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.core import SuggestionsQueue
from suggestions.exceptions import ErrorHandled
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import GuildConfig, UserConfig, QueuedSuggestion
from suggestions.qs_paginator import QueuedSuggestionsPaginator

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot
    from suggestions.objects import Suggestion

log = logging.getLogger(__name__)


class SuggestionsQueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core: SuggestionsQueue = SuggestionsQueue(bot)

    @components.button_listener()
    async def next_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await self.core.next_button(await InteractionHandler.new_handler(inter), pid)

    @components.button_listener()
    async def previous_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await self.core.previous_button(
            await InteractionHandler.new_handler(inter), pid
        )

    @components.button_listener()
    async def stop_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await self.core.stop_button(await InteractionHandler.new_handler(inter), pid)

    @components.button_listener()
    async def virtual_approve_button(
        self, inter: disnake.MessageInteraction, *, pid: str
    ):
        await self.core.virtual_approve_button(
            await InteractionHandler.new_handler(inter), pid
        )

    @components.button_listener()
    async def virtual_reject_button(
        self, inter: disnake.MessageInteraction, *, pid: str
    ):
        await self.core.virtual_reject_button(
            await InteractionHandler.new_handler(inter), pid
        )

    @components.button_listener()
    async def accept_queued_suggestion(self, inter: disnake.MessageInteraction):
        if inter.message is None:
            raise ValueError("Unhandled exception, expected a message")

        await self.core.accept_queued_suggestion(
            await InteractionHandler.new_handler(inter),
            inter.message.id,
            inter.message.channel.id,
            self.accept_queued_suggestion,
        )

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_suggestions_channel()
    async def queue(self, interaction: disnake.GuildCommandInteraction):
        pass

    @queue.sub_command()
    async def info(self, interaction: disnake.GuildCommandInteraction):
        """View information about this guilds suggestions queue."""
        await self.core.info(await InteractionHandler.new_handler(interaction))

    @queue.sub_command()
    async def view(self, interaction: disnake.GuildCommandInteraction):
        """View this guilds suggestions queue."""
        await self.core.view(
            await InteractionHandler.new_handler(interaction),
            self.previous_button,
            self.next_button,
            self.stop_button,
            self.virtual_approve_button,
            self.virtual_reject_button,
        )


def setup(bot):
    bot.add_cog(SuggestionsQueueCog(bot))
