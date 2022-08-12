from __future__ import annotations

import asyncio
import datetime
import logging
import math
import os
from pathlib import Path
from typing import Type, Optional

import aiohttp
import disnake
from cooldowns import CallableOnCooldown
from disnake.ext import commands
from bot_base import BotBase, BotContext, PrefixNotFound

from suggestions import State, Colors, Emojis, ErrorCode
from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
    ErrorHandled,
    SuggestionNotFound,
    SuggestionTooLong,
    InvalidGuildConfigOption,
)
from suggestions.stats import Stats, StatsEnum
from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class SuggestionsBot(commands.AutoShardedInteractionBot, BotBase):
    def __init__(self, *args, **kwargs):
        self.version: str = "Public Release 3.3"
        self.main_guild_id: int = 601219766258106399
        self.legacy_beta_role_id: int = 995588041991274547
        self.automated_beta_role_id: int = 998173237282361425
        self.beta_channel_id: int = 995622792294830080
        self.base_website_url: str = "https://suggestions.gg"

        self.is_prod: bool = True if os.environ.get("PROD", None) else False
        self.db: SuggestionsMongoManager = SuggestionsMongoManager(
            os.environ["PROD_MONGO_URL"] if self.is_prod else os.environ["MONGO_URL"]
        )
        self.colors: Type[Colors] = Colors
        self.state: State = State(self.db, self)
        self.stats: Stats = Stats(self)
        self.suggestion_emojis: Emojis = Emojis(self)
        self.old_prefixed_commands: set[str] = {
            "changelog",
            "channel",
            "help",
            "info",
            "invite",
            "ping",
            "prefix",
            "serverinfo",
            "sid",
            "stats",
            "suggestions",
            "vote",
        }
        self.converted_prefix_commands: set[str] = {"suggest", "approve", "reject"}
        super().__init__(
            *args,
            **kwargs,
            leave_db=True,
            do_command_stats=False,
            activity=disnake.Activity(
                name="suggestions",
                type=disnake.ActivityType.watching,
            ),
        )

        # Sharding info
        self.cluster_id: int = kwargs.get("cluster", 0)
        self.total_shards: int = kwargs.get("shard_count", 0)

    @property
    def total_cluster_count(self) -> int:
        return math.ceil(self.total_shards / 10)

    def error_embed(
        self,
        title: str,
        description: str,
        *,
        footer_text: Optional[str] = None,
        error_code: Optional[ErrorCode] = None,
    ) -> disnake.Embed:
        # TODO Also show a button to self diagnose with a link for more info
        embed = disnake.Embed(
            title=title,
            description=description,
            color=self.colors.error,
            timestamp=self.state.now,
        )
        if footer_text and error_code:
            raise ValueError("Can't provide both footer_text and error_code")
        elif footer_text:
            embed.set_footer(text=footer_text)
        elif error_code:
            embed.set_footer(
                text=f"Error code {error_code.value} | Cluster {self.cluster_id}"
            )

            log.debug("Encountered %s", error_code.name)

        return embed

    async def process_commands(self, message: disnake.Message):
        try:
            prefix = await self.get_guild_prefix(message.guild.id)
            prefix = self.get_case_insensitive_prefix(message.content, prefix)
        except (AttributeError, PrefixNotFound):
            prefix = self.get_case_insensitive_prefix(
                message.content, self.DEFAULT_PREFIX
            )

        as_args: list[str] = message.content.split(" ")
        command_to_invoke: str = as_args[0]
        if not command_to_invoke.startswith(prefix):
            # Not our prefix
            return

        command_to_invoke = command_to_invoke[len(prefix) :]

        if command_to_invoke in self.old_prefixed_commands:
            embed: disnake.Embed = disnake.Embed(
                title="Maintenance mode",
                description="Sadly this command is in maintenance mode.\n"
                # "You can read more about how this affects you [here]()",
                "You can read more about how this affects you by following our announcements channel.",
                colour=disnake.Color.from_rgb(255, 148, 148),
            )
            return await message.channel.send(embed=embed)

        elif command_to_invoke in self.converted_prefix_commands:
            embed: disnake.Embed = disnake.Embed(
                description="We are moving with the times, as such this command is now a slash command.\n"
                "You can read more about how this affects you as well as ensuring you can "
                # "use the bots commands [here]()",
                "use the bots commands by following our announcements channel.",
                colour=disnake.Color.magenta(),
            )
            return await message.channel.send(embed=embed)

        ctx = await self.get_context(message, cls=BotContext)
        if ctx.command:
            log.debug(
                "Attempting to invoke command %s for User(id=%s)",
                ctx.command.qualified_name,
                ctx.author.id,
            )

        await self.invoke(ctx)

    async def _push_slash_error_stats(
        self, interaction: disnake.ApplicationCommandInteraction
    ):
        stat_type: Optional[StatsEnum] = StatsEnum.from_command_name(
            interaction.application_command.qualified_name
        )
        if not stat_type:
            return

        await self.stats.log_stats(
            interaction.author.id, interaction.guild_id, stat_type, was_success=False
        )

    async def on_slash_command_error(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        exception: commands.CommandError,
    ) -> None:
        await self._push_slash_error_stats(interaction)
        exception = getattr(exception, "original", exception)

        if isinstance(exception, ErrorHandled):
            return

        elif isinstance(exception, BetaOnly):
            embed: disnake.Embed = disnake.Embed(
                title="Beta restrictions",
                description="This command is restricted to beta guilds only, "
                "please check back at a later date.",
                colour=self.colors.beta_required,
            )
            return await interaction.send(embed=embed, ephemeral=True)

        elif isinstance(exception, MissingSuggestionsChannel):
            return await interaction.send(
                embed=self.error_embed(
                    "Missing Suggestions Channel",
                    "This command requires a suggestion channel to use.\n"
                    "Please contact an administrator and ask them to set one up "
                    "using the following command.\n`/config channel`",
                    error_code=ErrorCode.MISSING_SUGGESTIONS_CHANNEL,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, MissingLogsChannel):
            return await interaction.send(
                embed=self.error_embed(
                    "Missing Logs Channel",
                    "This command requires a log channel to use.\n"
                    "Please contact an administrator and ask them to set one up "
                    "using the following command.\n`/config logs`",
                    error_code=ErrorCode.MISSING_LOG_CHANNEL,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, commands.MissingPermissions):
            perms = ",".join(i for i in exception.missing_permissions)
            return await interaction.send(
                embed=self.error_embed(
                    "Missing Permissions",
                    f"I need the following permissions in order to run this command.\n{perms}\n"
                    f"Please contact an administrator and ask them to provide them for me.",
                    error_code=ErrorCode.MISSING_PERMISSIONS,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, SuggestionNotFound):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "No suggestion exists with this id.",
                    error_code=ErrorCode.SUGGESTION_NOT_FOUND,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, SuggestionTooLong):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "Your suggestion content was too long, please limit it to 1000 characters or less.",
                    error_code=ErrorCode.SUGGESTION_CONTENT_TOO_LONG,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, InvalidGuildConfigOption):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "The provided guild config choice doesn't exist.",
                    error_code=ErrorCode.INVALID_GUILD_CONFIG_CHOICE,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, CallableOnCooldown):
            return await interaction.send(
                embed=self.error_embed(
                    "Command on Cooldown",
                    f"Ahh man so fast! You must wait {exception.retry_after} seconds to run this command again",
                    error_code=ErrorCode.COMMAND_ON_COOLDOWN,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, disnake.NotFound):
            log.debug("disnake.NotFound: %s", exception.text)
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "Failed to find data, are you sure everything is setup correct?",
                    error_code=ErrorCode.GENERIC_NOT_FOUND,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, disnake.Forbidden):
            log.debug("disnake.Forbidden: %s", exception.text)
            await interaction.send(
                embed=self.error_embed(
                    exception.text,
                    "Looks like something went wrong. "
                    "Please make sure I have all the correct permissions in your configured channels.",
                    error_code=ErrorCode.GENERIC_FORBIDDEN,
                ),
                ephemeral=True,
            )
            raise exception

        elif isinstance(exception, commands.NotOwner):
            await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "You do not have permission to run this command.",
                    error_code=ErrorCode.OWNER_ONLY,
                ),
                ephemeral=True,
            )
            raise exception

        elif isinstance(exception, disnake.HTTPException):
            if exception.code == 40060:
                log.debug(
                    "disnake.HTTPException: Interaction has already been acknowledged"
                )
                return

        if interaction.deferred_without_send:
            gid = interaction.guild_id if interaction.guild_id else None
            # Fix "Bot is thinking" hanging on edge cases...
            await interaction.send(
                embed=self.error_embed(
                    "Something went wrong",
                    f"Please contact support.\n\nGuild ID: {gid}",
                    error_code=ErrorCode.UNHANDLED_ERROR,
                ),
                ephemeral=True,
            )

        raise exception

    async def load(self):
        await self.state.load()
        await self.stats.load()
        await self.update_bot_listings()
        await self.watch_for_shutdown_request()

        count = 0
        extensions = Path("./suggestions/cogs").rglob("*.py")
        for ext in extensions:
            _path = ".".join(ext.parts)
            self.load_extension(_path[:-3])
            count += 1

        log.debug("Loaded %s cogs", count)

    async def graceful_shutdown(self) -> None:
        """Gracefully shutdown the bot.

        This can take up to a minute.
        """
        log.debug("Attempting to shutdown")
        self.state.notify_shutdown()
        await asyncio.gather(*self.state.background_tasks)
        log.info("Shutting down")
        await self.close()

    async def watch_for_shutdown_request(self):
        if not self.is_prod:
            log.info("Not watching for shutdown as not on prod")
            return

        state: State = self.state

        async def process_watch_for_shutdown():
            await self.wait_until_ready()
            log.debug("Started listening for shutdown requests")

            while not state.is_closing:
                cursor = (
                    self.db.cluster_shutdown_requests.raw_collection.find({})
                    .sort("timestamp", -1)
                    .limit(1)
                )
                items = await cursor.to_list(1)
                if not items:
                    await self.sleep_with_condition(15, lambda: self.state.is_closing)
                    continue

                entry = items[0]
                if not entry or (
                    entry and self.cluster_id in entry["responded_clusters"]
                ):
                    await self.sleep_with_condition(15, lambda: self.state.is_closing)
                    continue

                # We need to respond
                log.info(
                    "Received request to shutdown from cluster %s",
                    entry["issuer_cluster_id"],
                )
                entry["responded_clusters"].append(self.cluster_id)
                await self.db.cluster_shutdown_requests.upsert(
                    {"_id": entry["_id"]}, entry
                )
                state.remove_background_task(process_watch_for_shutdown.__task)
                break

            asyncio.create_task(self.graceful_shutdown())

        task_1 = asyncio.create_task(process_watch_for_shutdown())
        process_watch_for_shutdown.__task = task_1
        state.add_background_task(task_1)

    async def update_bot_listings(self) -> None:
        """Updates the bot lists with current stats."""
        if not self.is_prod or 1 == 1:  # Disable for now
            log.warning("Cancelling bot listing updates as we aren't in production.")
            return

        state: State = self.state
        time_between_updates: datetime.timedelta = datetime.timedelta(minutes=30)

        async def process_update_bot_listings():
            await self.wait_until_ready()

            headers = {"Authorization": f'Bearer {os.environ["SUGGESTIONS_API_KEY"]}'}
            while not state.is_closing:
                body = {
                    "guildCount": len(self.guilds),
                    "timestamp": str(datetime.datetime.now()),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        os.environ["SUGGESTIONS_STATS_API_URL"], json=body
                    ) as r:
                        pass

                log.debug("Updated bot listings")

                remaining_seconds = time_between_updates.total_seconds()
                while remaining_seconds > 0:

                    remaining_seconds -= 5
                    await asyncio.sleep(5)

                    if state.is_closing:
                        return

        task_1 = asyncio.create_task(process_update_bot_listings())
        state.add_background_task(task_1)
        log.info("Setup bot listing updates")

    def get_shard_id(self, guild_id: Optional[int]) -> int:
        # DM's go to shard 0
        shard_id = 0
        if self.is_prod and guild_id:
            shard_id = (guild_id >> 22) % self.total_shards

        return shard_id
