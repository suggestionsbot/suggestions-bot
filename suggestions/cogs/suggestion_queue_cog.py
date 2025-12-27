from __future__ import annotations

import logging

import cooldowns
import disnake
from disnake.ext import commands, components

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.core import SuggestionsQueue
from suggestions.interaction_handler import InteractionHandler


logger = logging.getLogger(__name__)


class SuggestionsQueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.core: SuggestionsQueue = SuggestionsQueue(bot)

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
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
        )


def setup(bot):
    bot.add_cog(SuggestionsQueueCog(bot))
