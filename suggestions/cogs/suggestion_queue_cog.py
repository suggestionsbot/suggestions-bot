from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import cooldowns
import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.projections import Projection, SHOW
from bot_base import NonExistentEntry
from bot_base.caches import TimedCache
from disnake.ext import commands, components

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import ErrorHandled
from suggestions.objects import GuildConfig
from suggestions.qs_paginator import QueuedSuggestionsPaginator

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot

log = logging.getLogger(__name__)


class SuggestionsQueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state = self.bot.state
        self.queued_suggestions_db: Document = self.bot.db.queued_suggestions
        self.paginator_objects: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=15), lazy_eviction=False
        )

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    async def get_paginator_for(
        self, paginator_id: str, interaction: disnake.Interaction
    ) -> QueuedSuggestionsPaginator:
        try:
            return self.paginator_objects.get_entry(paginator_id)
        except NonExistentEntry:
            await interaction.send(
                "This pagination session has expired, please start a new one with `/queue view`",
                ephemeral=True,
            )
            raise ErrorHandled

    @components.button_listener()
    async def next_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        paginator.current_page += 1
        await paginator.original_interaction.edit_original_message(
            embed=await paginator.format_page()
        )
        await inter.send("Viewing next item in queue.", ephemeral=True)

    @components.button_listener()
    async def previous_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        paginator.current_page -= 1
        await paginator.original_interaction.edit_original_message(
            embed=await paginator.format_page()
        )
        await inter.send("Viewing previous item in queue.", ephemeral=True)

    @components.button_listener()
    async def stop_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        self.paginator_objects.delete_entry(pid)
        await paginator.original_interaction.edit_original_message(
            components=[], embeds=[], content="This queue has expired."
        )
        await inter.send("I have cancelled this queue for you.", ephemeral=True)

    @components.button_listener()
    async def approve_button(self, inter: disnake.MessageInteraction, *, pid: str):
        paginator = await self.get_paginator_for(pid, inter)

    @components.button_listener()
    async def reject_button(self, inter: disnake.MessageInteraction, *, pid: str):
        paginator = await self.get_paginator_for(pid, inter)

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
        await interaction.response.defer(ephemeral=True, with_message=True)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        data: list = await self.queued_suggestions_db.find_many(
            AQ(EQ("guild_id", interaction.guild_id)),
            projections=Projection(SHOW("_id")),
            try_convert=False,
        )
        if not data:
            return await interaction.send(
                "Your guild has no suggestions in the queue.", ephemeral=True
            )

        content = None
        if not guild_config.uses_suggestion_queue:
            content = "These suggestions were queued before your guild disabled the suggestions queue."

        paginator = QueuedSuggestionsPaginator(
            bot=self.bot, data=[d["_id"] for d in data], inter=interaction
        )
        pid = self.bot.state.get_new_sq_paginator_id()
        await interaction.send(
            content=content,
            ephemeral=True,
            embed=await paginator.format_page(),
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f",
                        custom_id=await self.previous_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji="\N{BLACK SQUARE FOR STOP}\ufe0f",
                        custom_id=await self.stop_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f",
                        custom_id=await self.next_button.build_custom_id(pid=pid),
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_up_vote(),
                        custom_id=await self.approve_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_down_vote(),
                        custom_id=await self.reject_button.build_custom_id(pid=pid),
                    ),
                ),
            ],
        )
        self.paginator_objects.add_entry(pid, paginator)


def setup(bot):
    bot.add_cog(SuggestionsQueueCog(bot))
