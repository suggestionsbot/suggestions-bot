from __future__ import annotations

import functools
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Callable

import disnake
from alaric import AQ
from alaric.comparison import EQ, Exists
from alaric.logical import AND
from alaric.meta import Negate
from alaric.projections import Projection, SHOW
from commons.caching import NonExistentEntry, TimedCache

from suggestions.exceptions import ErrorHandled, MissingQueueLogsChannel
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import GuildConfig, UserConfig, QueuedSuggestion
from suggestions.qs_paginator import QueuedSuggestionsPaginator
from suggestions.utility import wrap_with_error_handler

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot
    from suggestions.objects import Suggestion

log = logging.getLogger(__name__)


class SuggestionsQueue:
    """
    Approach to suggestions queue.

    If it gets put in the virtual queue, it's always in said queue.
    If its put in a channel, it's always in the channel.
    Although we do track it under the same db table, this just
    saves needing to transition everything between them
    """

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

    async def resolve_queued_suggestion(
        self,
        ih: InteractionHandler,
        queued_suggestion: QueuedSuggestion,
        *,
        was_approved: bool,
    ):
        """Resolve a queued item, doing all the relevant actions"""
        guild_id = ih.interaction.guild_id
        suggestion: Suggestion | None = None
        try:
            guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)

            # If sent to channel queue, delete it
            if not queued_suggestion.is_in_virtual_queue:
                chan = await self.state.fetch_channel(queued_suggestion.channel_id)
                msg = await chan.fetch_message(queued_suggestion.message_id)
                await msg.delete()

            # Send the message to the relevant channel if required
            if was_approved:
                # Send this message through to the guilds suggestion channel
                suggestion = await queued_suggestion.convert_to_suggestion(
                    self.bot.state
                )
                icon_url = await self.bot.try_fetch_icon_url(guild_id)
                guild = await self.state.fetch_guild(guild_id)
                await suggestion.setup_initial_messages(
                    guild_config=guild_config,
                    ih=ih,
                    cog=self.bot.get_cog("SuggestionsCog"),
                    guild=guild,
                    icon_url=icon_url,
                    comes_from_queue=True,
                )
                # We dont send the user a message here because
                # setup_initial_messages does this for us
            else:
                # We may need to send this rejected suggestion to a logs channel
                if guild_config.queued_log_channel_id:
                    embed: disnake.Embed = await queued_suggestion.as_embed(self.bot)
                    channel: disnake.TextChannel = await self.bot.state.fetch_channel(
                        guild_config.queued_log_channel_id
                    )
                    try:
                        await channel.send(embed=embed)
                    except disnake.Forbidden as e:
                        raise MissingQueueLogsChannel from e

                # message the user the outcome
                user = await self.bot.state.fetch_user(
                    queued_suggestion.suggestion_author_id
                )
                user_config: UserConfig = await UserConfig.from_id(
                    queued_suggestion.suggestion_author_id, self.bot.state
                )
                icon_url = await self.bot.try_fetch_icon_url(guild_id)
                guild = self.state.guild_cache.get_entry(guild_id)
                if not (
                    user_config.dm_messages_disabled
                    or guild_config.dm_messages_disabled
                ):
                    # Set up to message users
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
                    await user.send(
                        embeds=[embed, await queued_suggestion.as_embed(self.bot)]
                    )
        except:
            # Don't remove from queue on failure
            if suggestion is not None:
                await self.bot.state.suggestions_db.delete(suggestion)

                if suggestion.message_id is not None:
                    await self.bot.delete_message(
                        message_id=suggestion.message_id,
                        channel_id=suggestion.channel_id,
                    )

            # Re-raise for the bot handler
            raise
        else:
            queued_suggestion.resolved_by = ih.interaction.author.id
            queued_suggestion.resolved_at = self.bot.state.now
            queued_suggestion.still_in_queue = False
            await self.bot.state.queued_suggestions_db.update(
                queued_suggestion, queued_suggestion
            )

    @wrap_with_error_handler()
    async def virtual_approve_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        current_suggestion: QueuedSuggestion = (
            await paginator.get_current_queued_suggestion()
        )
        await self.resolve_queued_suggestion(
            ih, queued_suggestion=current_suggestion, was_approved=True
        )
        await paginator.remove_current_page()
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_ACCEPTED")

    @wrap_with_error_handler()
    async def virtual_reject_button(self, ih: InteractionHandler, pid: str):
        paginator = await self.get_paginator_for(pid, ih)
        current_suggestion = await paginator.get_current_queued_suggestion()
        await self.resolve_queued_suggestion(
            ih, queued_suggestion=current_suggestion, was_approved=False
        )
        await paginator.remove_current_page()
        await ih.send(translation_key="PAGINATION_INNER_QUEUE_REJECTED")

    async def info(self, ih: InteractionHandler):
        guild_id = ih.interaction.guild_id
        guild_config: GuildConfig = await GuildConfig.from_id(guild_id, self.state)
        virtual_count: int = await self.queued_suggestions_db.count(
            AQ(
                AND(
                    EQ("guild_id", guild_id),
                    EQ("still_in_queue", True),
                    Negate(Exists("message_id")),
                ),
            )
        )
        physical_count: int = await self.queued_suggestions_db.count(
            AQ(
                AND(
                    EQ("guild_id", guild_id),
                    EQ("still_in_queue", True),
                    Exists("message_id"),
                ),
            )
        )
        icon_url = await self.bot.try_fetch_icon_url(guild_id)
        guild = self.state.guild_cache.get_entry(guild_id)
        embed = disnake.Embed(
            title="Queue Info",
            timestamp=self.bot.state.now,
            description=f"`{virtual_count}` suggestions currently in a virtual queue.\n"
            f"`{physical_count}` suggestions in a physical queue.\n"
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
            AQ(
                AND(
                    EQ("guild_id", guild_id),
                    EQ("still_in_queue", True),
                )
            ),
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
