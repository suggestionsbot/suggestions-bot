from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING


import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.logical import AND
from alaric.projections import Projection, SHOW
from commons.caching import NonExistentEntry, TimedCache
from disnake import Guild

from suggestions.exceptions import ErrorHandled
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import GuildConfig, UserConfig, QueuedSuggestion
from suggestions.qs_paginator import QueuedSuggestionsPaginator

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot
    from suggestions.objects import Suggestion

log = logging.getLogger(__name__)


class SuggestionsQueue:
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.paginator_objects: TimedCache = TimedCache(
            global_ttl=timedelta(minutes=15),
            lazy_eviction=False,
            ttl_from_last_access=True,
        )

    @property
    def queued_suggestions_db(self) -> Document:
        return self.bot.db.queued_suggestions

    @property
    def state(self):
        return self.bot.state

    async def get_paginator_for(
        self, paginator_id: str, ih: InteractionHandler
    ) -> QueuedSuggestionsPaginator:
        try:
            return self.paginator_objects.get_entry(paginator_id)
        except NonExistentEntry:
            await ih.send(translation_key="PAGINATION_INNER_SESSION_EXPIRED")
            raise ErrorHandled

    async def next_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        paginator.current_page += 1
        await paginator.original_interaction.edit_original_message(
            embed=await paginator.format_page()
        )
        await ih.send(translation_key="PAGINATION_INNER_NEXT_ITEM")

    async def previous_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        paginator.current_page -= 1
        await paginator.original_interaction.edit_original_message(
            embed=await paginator.format_page()
        )
        await ih.send(translation_key="PAGINATION_INNER_PREVIOUS_ITEM")

    async def stop_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        self.paginator_objects.delete_entry(pid)
        await paginator.original_interaction.edit_original_message(
            components=[],
            embeds=[],
            content=self.bot.get_localized_string(
                "PAGINATION_INNER_QUEUE_EXPIRED", ih.interaction
            ),
        )
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_CANCELLED")

    async def approve_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        current_suggestion: QueuedSuggestion = (
            await paginator.get_current_queued_suggestion()
        )
        suggestion: None = None
        guild_id = ih.interaction.guild_id
        try:
            await paginator.remove_current_page()
            suggestion: Suggestion = await current_suggestion.resolve(
                was_approved=True,
                state=self.bot.state,
                resolved_by=ih.interaction.author.id,
            )
            guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)
            icon_url = await Guild.try_fetch_icon_url(guild_id, self.state)
            guild = self.state.guild_cache.get_entry(guild_id)
            await suggestion.setup_initial_messages(
                guild_config=guild_config,
                interaction=ih.interaction,
                state=self.state,
                bot=self.bot,
                cog=self.bot.get_cog("SuggestionsCog"),
                guild=guild,
                icon_url=icon_url,
                comes_from_queue=True,
            )
        except:
            # Throw it back in the queue on error
            current_suggestion.resolved_by = None
            current_suggestion.resolved_at = None
            current_suggestion.still_in_queue = True
            await self.bot.state.queued_suggestions_db.update(
                current_suggestion, current_suggestion
            )

            if suggestion is not None:
                await self.bot.state.suggestions_db.delete(suggestion)

            raise

        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")

    async def reject_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        current_suggestion = await paginator.get_current_queued_suggestion()
        await paginator.remove_current_page()
        await current_suggestion.resolve(
            was_approved=False,
            state=self.bot.state,
            resolved_by=ih.interaction.author.id,
        )

        guild_id = ih.interaction.guild_id
        try:
            guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)
            icon_url = await Guild.try_fetch_icon_url(guild_id, self.state)
            guild = self.state.guild_cache.get_entry(guild_id)
            embed: disnake.Embed = disnake.Embed(
                description=self.bot.get_localized_string(
                    "QUEUE_INNER_USER_REJECTED", ih
                ),
                colour=self.bot.colors.embed_color,
                timestamp=self.state.now,
            )
            embed.set_author(
                name=guild.name,
                icon_url=icon_url,
            )
            embed.set_footer(text=f"Guild ID {guild_id}")
            user = await self.bot.get_or_fetch_user(
                current_suggestion.suggestion_author_id
            )
            user_config: UserConfig = await UserConfig.from_id(
                current_suggestion.suggestion_author_id, self.bot.state
            )
            if (
                not user_config.dm_messages_disabled
                and not guild_config.dm_messages_disabled
            ):
                await user.send(embed=embed)
        except disnake.HTTPException:
            log.debug(
                "Failed to DM %s regarding their queued suggestion",
                current_suggestion.suggestion_author_id,
            )

        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")

    async def info(self, ih: InteractionHandler):
        guild_id = ih.interaction.guild_id
        guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)
        count: int = await self.queued_suggestions_db.count(
            AQ(AND(EQ("guild_id", guild_id), EQ("still_in_queue", True)))
        )
        icon_url = await Guild.try_fetch_icon_url(guild_id, self.state)
        guild = self.state.guild_cache.get_entry(guild_id)
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
        await ih.send(embed=embed)

    async def view(
        self,
        ih: InteractionHandler,
        previous_button,
        next_button,
        stop_button,
        approve_button,
        reject_button,
    ):
        """View this guilds suggestions queue."""
        guild_id = ih.interaction.guild_id
        guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)
        data: list = await self.queued_suggestions_db.find_many(
            AQ(AND(EQ("guild_id", guild_id), EQ("still_in_queue", True))),
            projections=Projection(SHOW("_id")),
            try_convert=False,
        )
        if not data:
            return await ih.send(translation_key="QUEUE_VIEW_INNER_NOTHING_QUEUED")

        content = None
        if not guild_config.uses_suggestion_queue:
            content = self.bot.get_localized_string(
                "QUEUE_VIEW_INNER_PRIOR_QUEUE", ih.interaction
            )

        paginator = QueuedSuggestionsPaginator(
            bot=self.bot, data=[d["_id"] for d in data], inter=ih.interaction
        )
        pid = self.bot.state.get_new_sq_paginator_id()
        await ih.interaction.send(
            content=content,
            ephemeral=True,
            embed=await paginator.format_page(),
            components=[
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        emoji="\N{BLACK LEFT-POINTING TRIANGLE}\ufe0f",
                        custom_id=await previous_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji="\N{BLACK SQUARE FOR STOP}\ufe0f",
                        custom_id=await stop_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji="\N{BLACK RIGHT-POINTING TRIANGLE}\ufe0f",
                        custom_id=await next_button.build_custom_id(pid=pid),
                    ),
                ),
                disnake.ui.ActionRow(
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_up_vote(),
                        custom_id=await approve_button.build_custom_id(pid=pid),
                    ),
                    disnake.ui.Button(
                        emoji=await self.bot.suggestion_emojis.default_down_vote(),
                        custom_id=await reject_button.build_custom_id(pid=pid),
                    ),
                ),
            ],
        )
        self.paginator_objects.add_entry(pid, paginator)
