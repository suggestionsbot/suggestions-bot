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
from bot_base import NonExistentEntry
from bot_base.caches import TimedCache
from disnake import Guild
from disnake.ext import commands, components

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import ErrorHandled
from suggestions.objects import GuildConfig, UserConfig
from suggestions.qs_paginator import QueuedSuggestionsPaginator

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot
    from suggestions.objects import Suggestion

log = logging.getLogger(__name__)


class SuggestionsQueueCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state = self.bot.state
        self.queued_suggestions_db: Document = self.bot.db.queued_suggestions
        self.paginator_objects: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=15), lazy_eviction=False
        )

    async def get_paginator_for(
        self, paginator_id: str, interaction: disnake.Interaction
    ) -> QueuedSuggestionsPaginator:
        try:
            return self.paginator_objects.get_entry(paginator_id)
        except NonExistentEntry:
            await interaction.send(
                self.bot.get_localized_string(
                    "PAGINATION_INNER_SESSION_EXPIRED", interaction
                ),
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
        await inter.send(
            self.bot.get_localized_string("PAGINATION_INNER_NEXT_ITEM", inter),
            ephemeral=True,
        )

    @components.button_listener()
    async def previous_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        paginator.current_page -= 1
        await paginator.original_interaction.edit_original_message(
            embed=await paginator.format_page()
        )
        await inter.send(
            self.bot.get_localized_string("PAGINATION_INNER_PREVIOUS_ITEM", inter),
            ephemeral=True,
        )

    @components.button_listener()
    async def stop_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        self.paginator_objects.delete_entry(pid)
        await paginator.original_interaction.edit_original_message(
            components=[],
            embeds=[],
            content=self.bot.get_localized_string(
                "PAGINATION_INNER_QUEUE_EXPIRED", inter
            ),
        )
        await inter.send(
            self.bot.get_localized_string("PAGINATION_INNER_QUEUE_CANCELLED", inter),
            ephemeral=True,
        )

    @components.button_listener()
    async def approve_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        current_suggestion = await paginator.get_current_queued_suggestion()
        await paginator.remove_current_page()
        suggestion: Suggestion = await current_suggestion.resolve(
            was_approved=True, state=self.bot.state, resolved_by=inter.author.id
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            inter.guild_id, self.state
        )
        icon_url = await Guild.try_fetch_icon_url(inter.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(inter.guild_id)
        await suggestion.setup_initial_messages(
            guild_config=guild_config,
            interaction=inter,
            state=self.state,
            bot=self.bot,
            cog=self.bot.get_cog("SuggestionsCog"),
            guild=guild,
            icon_url=icon_url,
            comes_from_queue=True,
        )
        await inter.send(
            self.bot.get_localized_string("PAGINATION_INNER_QUEUE_ACCEPTED", inter),
            ephemeral=True,
        )

    @components.button_listener()
    async def reject_button(self, inter: disnake.MessageInteraction, *, pid: str):
        await inter.response.defer(ephemeral=True, with_message=True)
        paginator = await self.get_paginator_for(pid, inter)
        current_suggestion = await paginator.get_current_queued_suggestion()
        await paginator.remove_current_page()
        await current_suggestion.resolve(
            was_approved=False, state=self.bot.state, resolved_by=inter.author.id
        )
        try:
            guild_config: GuildConfig = await GuildConfig.from_id(
                inter.guild_id, self.state
            )
            icon_url = await Guild.try_fetch_icon_url(inter.guild_id, self.state)
            guild = self.state.guild_cache.get_entry(inter.guild_id)
            embed: disnake.Embed = disnake.Embed(
                description=self.bot.get_localized_string(
                    "QUEUE_INNER_USER_REJECTED", inter
                ),
                colour=self.bot.colors.embed_color,
                timestamp=self.state.now,
            )
            embed.set_author(
                name=guild.name,
                icon_url=icon_url,
            )
            embed.set_footer(text=f"Guild ID {inter.guild_id}")
            user_config: UserConfig = await UserConfig.from_id(
                inter.author.id, self.bot.state
            )
            if (
                not user_config.dm_messages_disabled
                and not guild_config.dm_messages_disabled
            ):
                await inter.author.send(embed=embed)
        except disnake.HTTPException:
            log.debug(
                "Failed to DM %s regarding there queued suggestion",
                inter.author.id,
            )

        await inter.send(
            self.bot.get_localized_string("PAGINATION_INNER_QUEUE_REJECTED", inter),
            ephemeral=True,
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
        await interaction.response.defer(ephemeral=True, with_message=True)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        count: int = await self.queued_suggestions_db.count(
            AQ(AND(EQ("guild_id", interaction.guild_id), EQ("still_in_queue", True)))
        )
        icon_url = await Guild.try_fetch_icon_url(interaction.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        embed = disnake.Embed(
            title="Queue Info",
            timestamp=self.bot.state.now,
            description=f"`{count}` suggestions currently in queue.\n"
            f"New suggestions will {'' if guild_config.uses_suggestion_queue else 'not'} be "
            f"sent to the suggestions queue.",
            colour=self.bot.colors.embed_color,
        )
        embed.set_author(
            name=guild.name,
            icon_url=icon_url,
        )
        await interaction.send(embed=embed, ephemeral=True)

    @queue.sub_command()
    async def view(self, interaction: disnake.GuildCommandInteraction):
        """View this guilds suggestions queue."""
        await interaction.response.defer(ephemeral=True, with_message=True)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        data: list = await self.queued_suggestions_db.find_many(
            AQ(AND(EQ("guild_id", interaction.guild_id), EQ("still_in_queue", True))),
            projections=Projection(SHOW("_id")),
            try_convert=False,
        )
        if not data:
            return await interaction.send(
                self.bot.get_localized_string(
                    "QUEUE_VIEW_INNER_NOTHING_QUEUED", interaction
                ),
                ephemeral=True,
            )

        content = None
        if not guild_config.uses_suggestion_queue:
            content = self.bot.get_localized_string(
                "QUEUE_VIEW_INNER_PRIOR_QUEUE", interaction
            )

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
