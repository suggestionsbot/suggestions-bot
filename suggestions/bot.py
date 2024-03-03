from __future__ import annotations

import asyncio
import datetime
import gc
import io
import logging
import math
import os
import traceback
from pathlib import Path
from string import Template
from typing import Type, Optional

import aiohttp
import alaric
import disnake
from alaric import Cursor
from bot_base.wraps import WrappedChannel
from cooldowns import CallableOnCooldown
from disnake import Locale, LocalizationKeyError, GatewayParams
from disnake.ext import commands
from bot_base import BotBase, BotContext, PrefixNotFound

from suggestions import State, Colors, Emojis, ErrorCode, Garven
from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
    ErrorHandled,
    SuggestionNotFound,
    SuggestionTooLong,
    InvalidGuildConfigOption,
    ConfiguredChannelNoLongerExists,
    UnhandledError,
    QueueImbalance,
    BlocklistedUser,
    PartialResponse,
    MissingQueueLogsChannel,
    MissingPermissionsToAccessQueueChannel,
    InvalidFileType,
)
from suggestions.http_error_parser import try_parse_http_error
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import Error, GuildConfig, UserConfig
from suggestions.stats import Stats, StatsEnum
from suggestions.database import SuggestionsMongoManager
from suggestions.zonis_routes import ZonisRoutes

log = logging.getLogger(__name__)


class SuggestionsBot(commands.AutoShardedInteractionBot, BotBase):
    def __init__(self, *args, **kwargs):
        self.version: str = "Public Release 3.22"
        self.main_guild_id: int = 601219766258106399
        self.legacy_beta_role_id: int = 995588041991274547
        self.automated_beta_role_id: int = 998173237282361425
        self.beta_channel_id: int = 995622792294830080
        self.base_website_url: str = "https://suggestions.gg"

        self.is_prod: bool = True if os.environ.get("PROD", None) else False

        db = None
        if "database_wrapper" in kwargs:
            db = kwargs.pop("database_wrapper")

        if db is not None:
            self.db = db
        else:
            self.db: SuggestionsMongoManager = SuggestionsMongoManager(
                os.environ["PROD_MONGO_URL"]
                if self.is_prod
                else os.environ["MONGO_URL"]
            )

        self.colors: Type[Colors] = Colors
        self.state: State = State(self.db, self)
        self.stats: Stats = Stats(self)
        self.garven: Garven = Garven(self)
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
        self.gc_lock: asyncio.Lock = asyncio.Lock()

        # Sharding info
        self.cluster_id: int = kwargs.pop("cluster", 0)
        self.total_shards: int = kwargs.get("shard_count", 0)

        super().__init__(
            *args,
            **kwargs,
            leave_db=True,
            do_command_stats=False,
            activity=disnake.Activity(
                name="suggestions",
                type=disnake.ActivityType.watching,
            ),
            # gateway_params=GatewayParams(zlib=False),
        )

        self._has_dispatched_initial_ready: bool = False
        self._initial_ready_future: asyncio.Future = asyncio.Future()

        self.zonis: ZonisRoutes = ZonisRoutes(self)

    async def launch_shard(
        self, _gateway: str, shard_id: int, *, initial: bool = False
    ) -> None:
        # Use the proxy if set, else fall back to whatever is default
        proxy: Optional[str] = os.environ.get("GW_PROXY", _gateway)
        return await super().launch_shard(proxy, shard_id, initial=initial)

    async def before_identify_hook(
        self, _shard_id: int | None, *, initial: bool = False  # noqa: ARG002
    ) -> None:
        # gateway-proxy
        return

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

    async def on_resumed(self):
        if self.gc_lock.locked():
            return

        async with self.gc_lock:
            await asyncio.sleep(2.0)
            collected = gc.collect()
            log.info(f"Garbage collector: collected {collected} objects.")

    @property
    def total_cluster_count(self) -> int:
        return math.ceil(self.total_shards / 10)

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
        self,
        interaction: disnake.ApplicationCommandInteraction | disnake.MessageInteraction,
    ):
        name = (
            interaction.application_command.qualified_name
            if isinstance(interaction, disnake.ApplicationCommandInteraction)
            else interaction.data["custom_id"].split(":")[0]  # Button name
        )

        stat_type: Optional[StatsEnum] = StatsEnum.from_command_name(name)
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

        if isinstance(exception, UnhandledError):
            return await interaction.send(
                embed=self.error_embed(
                    "Something went wrong",
                    f"Please contact support.",
                    error_code=ErrorCode.UNHANDLED_ERROR,
                    error=error,
                ),
                ephemeral=True,
            )

        attempt_code: Optional[ErrorCode] = try_parse_http_error(
            "".join(traceback.format_exception(exception))
        )
        if attempt_code:
            error.has_been_fixed = True
            await self.db.error_tracking.update(error, error)

        if attempt_code == ErrorCode.MISSING_FETCH_PERMISSIONS_IN_SUGGESTIONS_CHANNEL:
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I do not have permission to use your guilds configured suggestions channel.",
                    error_code=attempt_code,
                    error=error,
                ),
                ephemeral=True,
            )

        elif attempt_code == ErrorCode.MISSING_FETCH_PERMISSIONS_IN_LOGS_CHANNEL:
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I do not have permission to use your guilds configured logs channel.",
                    error_code=attempt_code,
                    error=error,
                ),
                ephemeral=True,
            )

        elif attempt_code == ErrorCode.MISSING_SEND_PERMISSIONS_IN_SUGGESTION_CHANNEL:
            return await interaction.send(
                embed=self.error_embed(
                    "Configuration Error",
                    "I do not have permission to send messages in your guilds suggestion channel.",
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

        elif isinstance(exception, MissingQueueLogsChannel):
            return await interaction.send(
                embed=self.error_embed(
                    "Missing Queue Logs Channel",
                    "This command requires a queue log channel to use.\n"
                    "Please contact an administrator and ask them to set one up "
                    "using the following command.\n`/config queue_channel`",
                    error_code=ErrorCode.MISSING_QUEUE_LOG_CHANNEL,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, MissingPermissionsToAccessQueueChannel):
            return await interaction.send(
                embed=self.error_embed(
                    title="Missing permissions within queue logs channel",
                    description="The bot does not have the required permissions in your queue channel. "
                    "Please contact an administrator and ask them to fix this.",
                    error=error,
                    error_code=ErrorCode.MISSING_PERMISSIONS_IN_QUEUE_CHANNEL,
                )
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

        elif isinstance(exception, BlocklistedUser):
            return await interaction.send(
                embed=self.error_embed(
                    "Blocked Action",
                    "Administrators from this guild have removed your ability to run this action.",
                    error_code=ErrorCode.BLOCKLISTED_USER,
                    error=error,
                ),
                ephemeral=True,
            )

        elif isinstance(exception, InvalidFileType):
            return await interaction.send(
                embed=self.error_embed(
                    "Invalid file type",
                    "The file you attempted to upload is not an accepted type.\n\n"
                    "If you believe this is an error please reach out to us via our support discord.",
                    error_code=ErrorCode.INVALID_FILE_TYPE,
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

        elif isinstance(exception, QueueImbalance):
            return await interaction.send(
                embed=self.error_embed(
                    "Queue Imbalance",
                    f"This suggestion has already been handled in another queue.",
                    error_code=ErrorCode.QUEUE_IMBALANCE,
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

        ih: InteractionHandler = await InteractionHandler.fetch_handler(
            interaction.id, self
        )
        if interaction.deferred_without_send or (
            ih is not None and not ih.has_sent_something
        ):
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
        await self.update_dev_channel()
        await self.watch_for_shutdown_request()
        await self.load_cogs()
        await self.zonis.start()

    async def graceful_shutdown(self) -> None:
        """Gracefully shutdown the bot.

        This can take up to a minute.
        """
        log.debug("Attempting to shutdown")
        self.state.notify_shutdown()
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

    async def update_dev_channel(self):
        if not self.is_prod:
            log.info("Not watching for debug info as not on prod")
            return

        if not self.is_primary_cluster:
            log.info("Not watching for debug info as not primary cluster")
            return

        state: State = self.state

        async def process_watch_for_shutdown():
            await self.wait_until_ready()
            log.debug("Started tracking bot latency")

            while not state.is_closing:
                # Update once an hour
                await self.sleep_with_condition(
                    datetime.timedelta(minutes=5).total_seconds(),
                    lambda: self.state.is_closing,
                )

                await self.garven.notify_devs(
                    title=f"WS latency as follows",
                    description=f"Timestamped for {datetime.datetime.utcnow().isoformat()}",
                    sender=f"N/A",
                )

                data = await self.garven.get_bot_ws_latency()
                shard_data = data["shards"]
                for i in range(0, 75, 5):
                    description = io.StringIO()
                    for o in range(0, 6):
                        shard = str(i + o)
                        try:
                            description.write(
                                f"**Shard {shard}**\nWS latency: `{shard_data[shard]['ws']}`\n"
                                f"Keep Alive latency: `{shard_data[shard]['keepalive']}`\n\n"
                            )
                        except KeyError:
                            # My lazy way of not doing env checks n math right
                            continue

                    if description.getvalue():
                        await self.garven.notify_devs(
                            title=f"WS latency",
                            description=description.getvalue(),
                            sender=f"Partial response: {data['partial_response']}",
                        )

                await self.sleep_with_condition(
                    datetime.timedelta(hours=1).total_seconds(),
                    lambda: self.state.is_closing,
                )

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

            headers = {"Authorization": os.environ["SUGGESTIONS_API_KEY"]}
            while not state.is_closing:
                try:
                    total_guilds = await self.garven.get_total_guilds()
                except PartialResponse:
                    await self.sleep_with_condition(
                        time_between_updates.total_seconds(),
                        lambda: self.state.is_closing,
                    )
                    continue

                body = {
                    "guild_count": int(total_guilds),
                    "shard_count": int(self.shard_count),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        os.environ[
                            "SUGGESTIONS_STATS_API_URL"
                        ],  # This is the bot list API # lists.suggestions.gg
                        json=body,
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

    @property
    def is_primary_cluster(self) -> bool:
        if not self.is_prod:
            # Non-prod is always single cluster
            return True

        shard_id = self.get_shard_id(self.main_guild_id)
        return shard_id in self.shard_ids

    async def _sync_application_commands(self) -> None:
        # In order to reduce getting rate-limited because every cluster
        # decided it wants to sync application commands when it aint required
        if not self.is_primary_cluster:
            log.warning("Not syncing application commands as not primary cluster")
            return

        await super()._sync_application_commands()

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
            return values.get("en-GB", values["en-US"])

    @staticmethod
    def inject_locale_values(
        content: str,
        interaction: disnake.Interaction,
        *,
        extras: Optional[dict] = None,
        user_config: Optional[UserConfig] = None,
        guild_config: Optional[GuildConfig] = None,
    ):
        base_config = {
            "CHANNEL_ID": interaction.channel_id,
            "GUILD_ID": interaction.guild_id,
            "AUTHOR_ID": interaction.author.id,
        }
        if extras is not None:
            base_config = {**base_config, **extras}

        if guild_config is not None:
            guild_data = {}
            for k, v in guild_config.as_dict().items():
                guild_data[f"GUILD_CONFIG_{k.upper()}"] = v

            guild_data.pop("GUILD_CONFIG__ID")
            base_config = {**base_config, **guild_data}

        if user_config is not None:
            user_data = {}
            for k, v in user_config.as_dict().items():
                user_data[f"USER_CONFIG_{k.upper()}"] = v

            user_data.pop("USER_CONFIG__ID")
            base_config = {**base_config, **user_data}

        return Template(content).safe_substitute(base_config)

    def get_localized_string(
        self,
        key: str,
        interaction: disnake.Interaction | InteractionHandler,
        *,
        extras: Optional[dict] = None,
        guild_config: Optional[GuildConfig] = None,
    ):
        if isinstance(interaction, InteractionHandler):
            # Support this so easier going forward
            interaction = interaction.interaction

        content = self.get_locale(key, interaction.locale)
        return self.inject_locale_values(
            content, interaction=interaction, guild_config=guild_config, extras=extras
        )

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
                try:
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
                except (aiohttp.ClientConnectorError, ConnectionRefusedError):
                    log.warning("push_status failed to connect, retrying in 10 seconds")
                    await self.sleep_with_condition(10, lambda: self.state.is_closing)
                except Exception as e:
                    if not self.is_prod:
                        log.error("Borked it")
                        return

                    tb = "".join(traceback.format_exception(e))
                    log.error(
                        "Status update failed: %s",
                        tb,
                    )
                    await self.garven.notify_devs(
                        title="Status page ping error",
                        description=tb,
                        sender=f"Cluster {self.cluster_id}, shard {self.shard_id}",
                    )

        task_1 = asyncio.create_task(inner())
        self.state.add_background_task(task_1)
        log.info("Setup status notifications")
