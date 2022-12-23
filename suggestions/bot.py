from __future__ import annotations

import asyncio
import datetime
import logging
import math
import os
import traceback
from pathlib import Path
from typing import Type, Optional

import aiohttp
import alaric
import disnake
from alaric import Cursor
from bot_base.wraps import WrappedChannel
from cooldowns import CallableOnCooldown
from disnake import Locale, LocalizationKeyError
from disnake.ext import commands
from bot_base import BotBase, BotContext, PrefixNotFound

from suggestions import State, Colors, Emojis, ErrorCode
from suggestions.clunk import Clunk
from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
    ErrorHandled,
    SuggestionNotFound,
    SuggestionTooLong,
    InvalidGuildConfigOption,
    ConfiguredChannelNoLongerExists,
)
from suggestions.http_error_parser import try_parse_http_error
from suggestions.objects import Error
from suggestions.stats import Stats, StatsEnum
from suggestions.database import SuggestionsMongoManager
from suggestions.zonis_routes import ZonisRoutes

log = logging.getLogger(__name__)


class SuggestionsBot(commands.AutoShardedInteractionBot, BotBase):
    def __init__(self, *args, **kwargs):
        self.version: str = "Public Release 3.9"
        self.main_guild_id: int = 601219766258106399
        self.legacy_beta_role_id: int = 995588041991274547
        self.automated_beta_role_id: int = 998173237282361425
        self.beta_channel_id: int = 995622792294830080
        self.base_website_url: str = "https://suggestions.gg"

        self.is_prod: bool = True if os.environ.get("PROD", None) else False

        if kwargs.get("database_wrapper"):
            self.db = kwargs.pop("database_wrapper")
        else:
            self.db: SuggestionsMongoManager = SuggestionsMongoManager(
                os.environ["PROD_MONGO_URL"]
                if self.is_prod
                else os.environ["MONGO_URL"]
            )

        self.colors: Type[Colors] = Colors
        self.state: State = State(self.db, self)
        self.stats: Stats = Stats(self)
        self.clunk: Clunk = Clunk(self.state)
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

        self._has_dispatched_initial_ready: bool = False
        self._initial_ready_future: asyncio.Future = asyncio.Future()

        self.zonis: ZonisRoutes = ZonisRoutes(self)

    async def get_or_fetch_channel(self, channel_id: int) -> WrappedChannel:
        try:
            return await super().get_or_fetch_channel(channel_id)
        except disnake.NotFound as e:
            raise ConfiguredChannelNoLongerExists from e

    async def dispatch_initial_ready(self):
        if self._has_dispatched_initial_ready:
            return

        self._has_dispatched_initial_ready = True
        self._initial_ready_future.set_result(None)
        log.info("Suggestions main: Ready")
        log.info("Startup took: %s", self.get_uptime())
        await self.suggestion_emojis.populate_emojis()

    @property
    def total_cluster_count(self) -> int:
        return math.ceil(self.total_shards / 10)

    @property
    def is_primary_cluster(self) -> bool:
        return bool(os.environ.get("IS_PRIMARY_CLUSTER", False))

    def error_embed(
        self,
        title: str,
        description: str,
        error: Optional[Error] = None,
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
            if error:
                embed.set_footer(
                    text=f"Error code {error_code.value} | Error ID {error.id}"
                )
            else:
                embed.set_footer(
                    text=f"Error code {error_code.value} | Cluster ID {self.cluster_id}"
                )

            log.debug("Encountered %s", error_code.name)
        elif error:
            embed.set_footer(text=f"Error ID {error.id}")

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

    async def persist_error(
        self,
        error: Exception,
        interaction: disnake.ApplicationCommandInteraction | disnake.MessageInteraction,
    ) -> Error:

        if isinstance(interaction, disnake.MessageInteraction):
            cmd_name = interaction.data.custom_id
        else:
            cmd_name = interaction.application_command.qualified_name

        error = Error(
            _id=self.state.get_new_error_id(),
            traceback="".join(traceback.format_exception(error)),
            error=error.__class__.__name__,
            cluster_id=self.cluster_id,
            shard_id=self.get_shard_id(interaction.guild_id),
            command_name=cmd_name,
            created_at=self.state.now,
            guild_id=interaction.guild_id,
            user_id=interaction.author.id,
        )
        await self.db.error_tracking.insert(error)
        return error

    async def on_user_command_error(self, interaction, exception) -> None:
        return await self.on_slash_command_error(interaction, exception)

    async def on_message_command_error(self, interaction, exception) -> None:
        return await self.on_slash_command_error(interaction, exception)

    async def on_slash_command_error(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        exception: commands.CommandError,
    ) -> None:
        await self._push_slash_error_stats(interaction)
        exception = getattr(exception, "original", exception)
        error: Error = await self.persist_error(exception, interaction)

        if isinstance(exception, ErrorHandled):
            return

        attempt_code: Optional[ErrorCode] = try_parse_http_error(traceback.format_exc())
        if attempt_code == ErrorCode.MISSING_PERMISSIONS_IN_SUGGESTIONS_CHANNEL:
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I do not have permission to use your guilds configured suggestions channel.",
                    error_code=attempt_code,
                    error=error,
                ),
                ephemeral=True,
            )

        elif attempt_code == ErrorCode.MISSING_PERMISSIONS_IN_LOGS_CHANNEL:
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I do not have permission to use your guilds configured logs channel.",
                    error_code=attempt_code,
                    error=error,
                ),
                ephemeral=True,
            )

        if isinstance(exception, BetaOnly):
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
                    error=error,
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
                    error=error,
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
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, SuggestionNotFound):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    str(exception),
                    error_code=ErrorCode.SUGGESTION_NOT_FOUND,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, SuggestionTooLong):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "Your suggestion content was too long, please limit it to 1000 characters or less.",
                    error_code=ErrorCode.SUGGESTION_CONTENT_TOO_LONG,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, InvalidGuildConfigOption):
            return await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "The provided guild config choice doesn't exist.",
                    error_code=ErrorCode.INVALID_GUILD_CONFIG_CHOICE,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, CallableOnCooldown):
            return await interaction.send(
                embed=self.error_embed(
                    "Command on Cooldown",
                    f"Ahh man so fast! You must wait {exception.retry_after} seconds to run this command again",
                    error_code=ErrorCode.COMMAND_ON_COOLDOWN,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, ConfiguredChannelNoLongerExists):
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I cannot find your configured channel for this command.\n"
                    "Please ask an administrator to reconfigure one.",
                    error_code=ErrorCode.CONFIGURED_CHANNEL_NO_LONGER_EXISTS,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, LocalizationKeyError):
            gid = interaction.guild_id if interaction.guild_id else None
            return await interaction.send(
                embed=self.error_embed(
                    "Something went wrong",
                    f"Please contact support.\n\nGuild ID: {gid}",
                    error_code=ErrorCode.MISSING_TRANSLATION,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, disnake.NotFound):
            log.debug("disnake.NotFound: %s", exception.text)
            gid = interaction.guild_id if interaction.guild_id else None
            await interaction.send(
                embed=self.error_embed(
                    "Command failed",
                    "I've failed to find something, please retry whatever you were doing.\n"
                    f"If this error persists please contact support.\n\nGuild ID: `{gid}`",
                    error_code=ErrorCode.GENERIC_NOT_FOUND,
                    error=error,
                ),
                ephemeral=True,
            )
            raise exception

        elif isinstance(exception, disnake.Forbidden):
            log.debug("disnake.Forbidden: %s", exception.text)
            await interaction.send(
                embed=self.error_embed(
                    exception.text,
                    "Looks like something went wrong. "
                    "Please make sure I have all the correct permissions in your configured channels.",
                    error_code=ErrorCode.GENERIC_FORBIDDEN,
                    error=error,
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
                    error=error,
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
                    error=error,
                ),
                ephemeral=True,
            )

        raise exception

    async def on_button_error(
        self,
        interaction: disnake.MessageInteraction,
        exception: Exception,
    ):
        if isinstance(exception, LocalizationKeyError):
            error: Error = await self.persist_error(exception, interaction)
            gid = interaction.guild_id if interaction.guild_id else None
            return await interaction.send(
                embed=self.error_embed(
                    "Something went wrong",
                    f"Please contact support.\n\nGuild ID: {gid}",
                    error_code=ErrorCode.MISSING_TRANSLATION,
                    error=error,
                ),
                ephemeral=True,
            )

        raise exception

    async def load_cogs(self):
        count = 0
        extensions = Path("./suggestions/cogs").rglob("*.py")
        for ext in extensions:
            _path = ".".join(ext.parts)
            self.load_extension(_path[:-3])
            count += 1

        log.debug("Loaded %s cogs", count)

    async def load(self):
        self.i18n.load(Path("suggestions/locales"))
        await self.state.load()
        await self.stats.load()
        await self.update_bot_listings()
        await self.push_status()
        await self.watch_for_shutdown_request()
        await self.load_cogs()
        await self.zonis.start()

    async def graceful_shutdown(self) -> None:
        """Gracefully shutdown the bot.

        This can take up to a minute.
        """
        log.debug("Attempting to shutdown")
        self.state.notify_shutdown()
        await self.clunk.kill_all()
        await self.zonis.client.close()
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
                cursor: Cursor = (
                    Cursor.from_document(self.db.cluster_shutdown_requests)
                    .set_sort(("timestamp", alaric.Descending))
                    .set_limit(1)
                )
                items = await cursor.execute()
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
        if not self.is_prod:
            # log.warning("Cancelling bot listing updates as we aren't in production.")
            return

        if not self.is_primary_cluster:
            log.debug("I am not the primary cluster, disabling bot listing updates")
            return

        state: State = self.state
        time_between_updates: datetime.timedelta = datetime.timedelta(minutes=30)

        async def process_update_bot_listings():
            await self.wait_until_ready()

            headers = {"Authorization": f'Bearer {os.environ["SUGGESTIONS_API_KEY"]}'}
            while not state.is_closing:
                url = (
                    "https://garven.suggestions.gg/aggregate/guilds/count"
                    if self.is_prod
                    else "https://garven.dev.suggestions.gg/aggregate/guilds/count"
                )
                async with aiohttp.ClientSession(
                    headers={"X-API-KEY": os.environ["GARVEN_API_KEY"]}
                ) as session:
                    async with session.get(url) as resp:
                        data: dict = await resp.json()
                        if resp.status != 200:
                            log.error("Stopping bot list updates")
                            log.error("%s", data)
                            break

                if data["partial_response"]:
                    log.warning(
                        "Skipping bot list updates as IPC returned a partial responses"
                    )
                    await self.sleep_with_condition(
                        time_between_updates.total_seconds(),
                        lambda: self.state.is_closing,
                    )
                    continue

                body = {
                    "guild_count": data["statistic"],
                    "timestamp": datetime.datetime.now().timestamp(),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        os.environ["SUGGESTIONS_STATS_API_URL"], json=body
                    ) as r:
                        if r.status != 200:
                            log.warning("%s", r.text)

                log.debug("Updated bot listings")
                await self.sleep_with_condition(
                    time_between_updates.total_seconds(),
                    lambda: self.state.is_closing,
                )

        task_1 = asyncio.create_task(process_update_bot_listings())
        state.add_background_task(task_1)
        log.info("Setup bot list updates")

    def get_shard_id(self, guild_id: Optional[int]) -> int:
        # DM's go to shard 0
        shard_id = 0
        if self.is_prod and guild_id:
            shard_id = (guild_id >> 22) % self.total_shards

        return shard_id

    def get_locale(self, key: str, locale: Locale) -> str:
        values = self.i18n.get(key)
        if not values:
            raise LocalizationKeyError(key)

        try:
            return values[str(locale)]
        except KeyError:
            # Default to known translations if not set
            return values["en-GB"]

    async def on_application_command(
        self, interaction: disnake.ApplicationCommandInteraction
    ):
        await self.db.locale_tracking.insert(
            {
                "locale": str(interaction.locale),
                "user_id": interaction.user.id,
                "guild_id": interaction.guild_id,
            }
        )
        await self.process_application_commands(interaction)

    async def push_status(self):
        if not self.is_prod:
            log.warning("Cancelling status updates as we aren't in production")
            return

        async def inner():
            await self._initial_ready_future
            patch = os.environ["UPTIME_PATCH"]
            while not self.state.is_closing:
                appears_down = False
                for shard_id, shard_info in self.shards.items():
                    if shard_info.is_closed():
                        # We consider this as 'down' as sometimes
                        # they fail to reconnect and we don't handle
                        # that edge case as of current
                        log.critical(
                            "Shard %s in cluster %s is reporting as closed",
                            shard_id,
                            self.cluster_id,
                        )
                        appears_down = True

                if not appears_down:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            url=f"https://status.koldfusion.xyz/api/push/{patch}?status=up&msg=OK&ping="
                        ):
                            pass

                await self.sleep_with_condition(60, lambda: self.state.is_closing)

        task_1 = asyncio.create_task(inner())
        self.state.add_background_task(task_1)
        log.info("Setup status notifications")
