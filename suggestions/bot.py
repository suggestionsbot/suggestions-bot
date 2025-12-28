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
from typing import Type, Optional, Union, Any

import aiohttp
import alaric
import botocore
import commons
import disnake
import humanize
import redis.asyncio as redis
from alaric import Cursor
from cooldowns import CallableOnCooldown
from disnake import (
    Locale,
    LocalizationKeyError,
    Thread,
    ApplicationCommandType,
)
from disnake.abc import PrivateChannel, GuildChannel
from disnake.ext import commands, components
from disnake.state import AutoShardedConnectionState
from opentelemetry.trace import Status, StatusCode

from suggestions import State, Colors, Emojis, ErrorCode, constants
from suggestions.database import SuggestionsMongoManager
from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
    ErrorHandled,
    SuggestionNotFound,
    MessageTooLong,
    InvalidGuildConfigOption,
    ConfiguredChannelNoLongerExists,
    UnhandledError,
    QueueImbalance,
    BlocklistedUser,
    MissingQueueLogsChannel,
    MissingPermissionsToAccessQueueChannel,
    InvalidFileType,
    SuggestionSecurityViolation,
)
from suggestions.http_error_parser import try_parse_http_error
from suggestions.interaction_handler import InteractionHandler
from suggestions.low_level import PatchedConnectionState
from suggestions.objects import Error, GuildConfig, UserConfig
from suggestions.stats import Stats, StatsEnum

log = logging.getLogger(__name__)


class SuggestionsBot(commands.AutoShardedInteractionBot):
    def __init__(self, *args, **kwargs):
        self.version: str = "Public Release 3.31"
        self.main_guild_id: int = 601219766258106399
        self.legacy_beta_role_id: int = 995588041991274547
        self.automated_beta_role_id: int = 998173237282361425
        self.beta_channel_id: int = 995622792294830080
        self.base_website_url: str = "https://suggestions.gg"
        self._uptime: datetime.datetime = datetime.datetime.now(
            tz=datetime.timezone.utc
        )
        # TODO Set redis and also auto set decoding from bytes to strings
        self.redis: redis.Redis = None

        self.is_prod: bool = (
            True if os.environ.get("INFISICAL_SLUG", None) == "prod" else False
        )

        db = None
        if "database_wrapper" in kwargs:
            db = kwargs.pop("database_wrapper")

        if db is not None:
            self.db = db
        else:
            self.db: SuggestionsMongoManager = SuggestionsMongoManager(
                constants.MONGO_URL
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
        self.gc_lock: asyncio.Lock = asyncio.Lock()

        # Sharding info
        self.cluster_id: int = kwargs.pop("cluster", 0)
        self.total_shards: int = kwargs.get("shard_count", 0)

        super().__init__(
            *args,
            **kwargs,
            activity=disnake.Activity(
                name="suggestions",
                type=disnake.ActivityType.watching,
            ),
            # gateway_params=GatewayParams(zlib=False),
        )

        self.component_manager = components.get_manager()
        self.component_manager.add_to_bot(self)  # type: ignore

        self._has_dispatched_initial_ready: bool = False
        self._initial_ready_future: asyncio.Future = asyncio.Future()

        # This exists on the basis we have patched state
        self.guild_ids: set[int] = self._connection.guild_ids

    def _get_state(self, **options: Any) -> AutoShardedConnectionState:
        return PatchedConnectionState(
            **options,
            dispatch=self.dispatch,
            handlers=self._handlers,
            hooks=self._hooks,
            http=self.http,
            loop=self.loop,
        )

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

    async def get_or_fetch_channel(
        self, channel_id: int
    ) -> Union[GuildChannel, PrivateChannel, Thread]:
        try:
            channel = self.get_channel(channel_id)
            if channel is None:
                channel = await self.fetch_channel(channel_id)

            return channel
        except disnake.NotFound as e:
            raise ConfiguredChannelNoLongerExists from e

    async def dispatch_initial_ready(self):
        if self._has_dispatched_initial_ready:
            return

        self._has_dispatched_initial_ready = True
        self._initial_ready_future.set_result(None)
        log.info("Suggestions main: Ready")
        log.info("Startup took: %s", self.get_uptime())
        print("Suggestions main: Ready")
        print(f"Startup took: {self.get_uptime()}")
        await self.suggestion_emojis.populate_emojis()

    @property
    def uptime(self) -> datetime.datetime:
        """Returns when the bot was initialized."""
        return self._uptime

    def get_uptime(self) -> str:
        """Returns a human readable string for the bots uptime."""
        return humanize.precisedelta(
            self.uptime - datetime.datetime.now(tz=datetime.timezone.utc)
        )

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
        exception = getattr(exception, "original", exception)
        if isinstance(exception, ErrorHandled):
            return None

        with constants.TRACER.start_as_current_span("error handler") as child:
            await self._push_slash_error_stats(interaction)
            error: Error = await self.persist_error(exception, interaction)
            child.set_attribute("error.id", error.id)
            child.set_attribute("error.name", error.error)

            ignorable_exception_types = (
                BetaOnly,
                MissingSuggestionsChannel,
                MissingLogsChannel,
                MissingQueueLogsChannel,
                MissingPermissionsToAccessQueueChannel,
                commands.MissingPermissions,
                SuggestionNotFound,
                MessageTooLong,
                InvalidGuildConfigOption,
                CallableOnCooldown,
                BlocklistedUser,
                InvalidFileType,
                ConfiguredChannelNoLongerExists,
                QueueImbalance,
                commands.NotOwner,
            )
            if isinstance(exception, ignorable_exception_types):
                # all these we dont need to care about being logged
                # as we handle them enough for end users to
                # theoretically fix themselves
                child.set_attribute("error.handled", True)

            else:
                # We want to propagate these as 'unhandled errors'
                # that should be taken a look at by a dev
                child.set_attribute("error.handled", False)
                child.set_status(Status(StatusCode.ERROR))
                child.record_exception(exception)

            if isinstance(exception, UnhandledError):
                log.critical(
                    "An unhandled exception occurred",
                    extra={
                        "error.id": error.id,
                        "interaction.author.id": error.user_id,
                        "interaction.guild.id": error.guild_id,
                        "error.traceback": commons.exception_as_string(exception),
                        "error.code": ErrorCode.UNHANDLED_ERROR.value,
                    },
                )
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

            if (
                attempt_code
                == ErrorCode.MISSING_FETCH_PERMISSIONS_IN_SUGGESTIONS_CHANNEL
            ):
                log.debug(
                    "MISSING_FETCH_PERMISSIONS_IN_SUGGESTIONS_CHANNEL",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": attempt_code.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Configuration Error",
                        "I do not have permission to use your guilds configured suggestions channel.",
                        error_code=attempt_code.value,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif attempt_code == ErrorCode.MISSING_FETCH_PERMISSIONS_IN_LOGS_CHANNEL:
                log.debug(
                    "MISSING_FETCH_PERMISSIONS_IN_LOGS_CHANNEL",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": attempt_code.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Configuration Error",
                        "I do not have permission to use your guilds configured logs channel.",
                        error_code=attempt_code,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif (
                attempt_code == ErrorCode.MISSING_SEND_PERMISSIONS_IN_SUGGESTION_CHANNEL
            ):
                log.debug(
                    "MISSING_SEND_PERMISSIONS_IN_SUGGESTION_CHANNEL",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": attempt_code.value,
                    },
                )
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
                log.critical(
                    "BetaOnly",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                    },
                )
                embed: disnake.Embed = disnake.Embed(
                    title="Beta restrictions",
                    description="This command is restricted to beta guilds only, "
                    "please check back at a later date.",
                    colour=self.colors.beta_required,
                )
                return await interaction.send(embed=embed, ephemeral=True)

            elif isinstance(exception, MissingSuggestionsChannel):
                log.debug(
                    "MissingSuggestionsChannel",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_SUGGESTIONS_CHANNEL.value,
                    },
                )
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
                log.debug(
                    "MissingLogsChannel",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_LOG_CHANNEL.value,
                    },
                )
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
                log.debug(
                    "MissingQueueLogsChannel",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_QUEUE_LOG_CHANNEL.value,
                    },
                )
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
                log.debug(
                    "MissingPermissionsToAccessQueueChannel",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_PERMISSIONS_IN_QUEUE_CHANNEL.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        title="Missing permissions within queue logs channel",
                        description="The bot does not have the required permissions in your queue channel. "
                        "Please contact an administrator and ask them to fix this.",
                        error=error,
                        error_code=ErrorCode.MISSING_PERMISSIONS_IN_QUEUE_CHANNEL,
                    )
                )

            elif isinstance(exception, SuggestionSecurityViolation):
                log.critical(
                    "User %s looked up a suggestion from a different guild",
                    interaction.author.id,
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "suggestion_id": exception.suggestion_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.SUGGESTION_NOT_FOUND.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Command failed",
                        exception.user_facing_message,
                        error_code=ErrorCode.SUGGESTION_NOT_FOUND,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif isinstance(exception, commands.MissingPermissions):
                perms = ",".join(i for i in exception.missing_permissions)
                log.debug(
                    "commands.MissingPermissions: %s",
                    perms,
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_PERMISSIONS.value,
                    },
                )
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
                log.debug(
                    "SuggestionNotFound",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.SUGGESTION_NOT_FOUND.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Command failed",
                        str(exception),
                        error_code=ErrorCode.SUGGESTION_NOT_FOUND,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif isinstance(exception, MessageTooLong):
                log.debug(
                    "MessageTooLong",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.SUGGESTION_CONTENT_TOO_LONG.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Command failed",
                        "Your content was too long, please limit it to 1000 characters or less.\n\n"
                        "I have attached a file containing your content to save rewriting it entirely.",
                        error_code=ErrorCode.SUGGESTION_CONTENT_TOO_LONG,
                        error=error,
                    ),
                    ephemeral=True,
                    file=disnake.File(
                        io.StringIO(exception.message_text), filename="content.txt"
                    ),
                )

            elif isinstance(exception, InvalidGuildConfigOption):
                log.debug(
                    "InvalidGuildConfigOption",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.INVALID_GUILD_CONFIG_CHOICE.value,
                    },
                )
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
                log.debug(
                    "CallableOnCooldown",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.COMMAND_ON_COOLDOWN.value,
                    },
                )
                natural_time = humanize.naturaldelta(exception.retry_after)
                return await interaction.send(
                    embed=self.error_embed(
                        "Command on Cooldown",
                        f"Ahh man so fast! You must wait {natural_time} to run this command again",
                        error_code=ErrorCode.COMMAND_ON_COOLDOWN,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif isinstance(exception, BlocklistedUser):
                log.debug(
                    "BlocklistedUser",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.BLOCKLISTED_USER.value,
                    },
                )
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
                log.debug(
                    "InvalidFileType",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.INVALID_FILE_TYPE.value,
                    },
                )
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
                log.debug(
                    "ConfiguredChannelNoLongerExists",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.CONFIGURED_CHANNEL_NO_LONGER_EXISTS.value,
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Configuration Error",
                        "I cannot find your configured channel for this command.\n"
                        "Please ask an administrator to reconfigure one.\n"
                        "This can be done using: `/config channel`",
                        error_code=ErrorCode.CONFIGURED_CHANNEL_NO_LONGER_EXISTS,
                        error=error,
                    ),
                    ephemeral=True,
                )

            elif isinstance(exception, LocalizationKeyError):
                gid = interaction.guild_id if interaction.guild_id else None
                log.debug(
                    "LocalizationKeyError",
                    extra={
                        "interaction.guild.id": gid,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.MISSING_TRANSLATION.value,
                    },
                )
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
                log.debug(
                    "QueueImbalance",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.QUEUE_IMBALANCE.value,
                    },
                )
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
                log.debug(
                    "disnake.NotFound: %s",
                    exception.text,
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.traceback": commons.exception_as_string(exception),
                        "error.code": ErrorCode.GENERIC_NOT_FOUND.value,
                    },
                )
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
                log.debug(
                    "disnake.Forbidden: %s",
                    exception.text,
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.GENERIC_FORBIDDEN.value,
                    },
                )
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
                log.debug(
                    "commands.NotOwner",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.OWNER_ONLY.value,
                    },
                )
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
                    log.debug(
                        "disnake.HTTPException: Interaction has already been acknowledged",
                        extra={
                            "interaction.guild.id": interaction.guild_id,
                            "interaction.author.id": interaction.author.id,
                            "interaction.author.global_name": interaction.author.global_name,
                        },
                    )
                    raise exception

            elif isinstance(exception, botocore.exceptions.ClientError):
                log.error(
                    "An error occurred during the handling of files",
                    extra={
                        "error.name": exception.__class__.__name__,
                        "error.traceback": commons.exception_as_string(exception),
                    },
                )
                return await interaction.send(
                    embed=self.error_embed(
                        "Command failed",
                        "Something went wrong uploading your file.\n\n"
                        "If this occurs more then once please report it to support.",
                        error_code=ErrorCode.R2_UPLOAD_ISSUE,
                        error=error,
                    ),
                    ephemeral=True,
                )

            ih: InteractionHandler = await InteractionHandler.fetch_handler(
                interaction.id, self
            )
            if ih is not None and not ih.has_sent_something:
                log.critical(
                    "Interaction was never ack'd",
                    extra={
                        "interaction.guild.id": interaction.guild_id,
                        "interaction.author.id": interaction.author.id,
                        "interaction.author.global_name": interaction.author.global_name,
                        "error.code": ErrorCode.UNHANDLED_ERROR.value,
                    },
                )
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

            log.critical(
                "Unhandled error encountered (%s)",
                exception.__class__.__name__,
                extra={
                    "error.name": exception.__class__.__name__,
                    "error.traceback": commons.exception_as_string(exception),
                },
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
        await self.load_cogs()

    async def graceful_shutdown(self) -> None:
        """Gracefully shutdown the bot.

        This can take up to a minute.
        """
        log.debug("Attempting to shutdown")
        self.state.notify_shutdown()
        await asyncio.gather(*self.state.background_tasks)
        # TODO Re-enable premium features at later date
        # await self.redis.aclose()
        log.info("Shutting down")
        await self.close()

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

            headers = {
                "Authorization": constants.get_secret(
                    "LISTS_API_KEY", constants.infisical_client
                )
            }
            while not state.is_closing:
                app_data = await self.application_info()
                total_guilds = app_data.approximate_guild_count

                body = {
                    "guild_count": int(total_guilds),
                    "shard_count": int(self.shard_count),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        constants.get_secret(
                            "LISTS_API_URL", constants.infisical_client
                        ),  # This is the bot list API # lists.suggestions.gg
                        json=body,
                    ) as r:
                        if r.status != 200:
                            log.warning("%s", r.text)

                log.debug("Updated bot listings")
                await commons.sleep_with_condition(
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
            value = values.get("en-GB")
            if value is None:
                value = values["en-US"]
                log.critical(
                    "Missing translation in en-GB file",
                    extra={"translation.key": key},
                )

            return value

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
            "interaction.guild.id": interaction.guild_id,
            "interaction.author.id": interaction.author.id,
            "interaction.author.global_name": interaction.author.global_name,
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
                "interaction.guild.id": interaction.guild_id,
            }
        )
        trace_name = self.get_qualified_name(interaction)
        with constants.TRACER.start_as_current_span(trace_name) as span:
            span.set_attribute("bot.cluster.id", self.cluster_id)
            span.set_attribute("interaction.author.id", interaction.author.id)
            span.set_attribute(
                "interaction.author.global_name",
                (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
            )
            span.set_attribute("interaction.guild.id", interaction.guild_id)
            span.set_attribute(
                "interaction.command.name", self.get_qualified_name(interaction)
            )
            await self.process_application_commands(interaction)

    @staticmethod
    def get_qualified_name(inter: disnake.ApplicationCommandInteraction) -> str:
        base = io.StringIO()
        if inter.data.type == ApplicationCommandType.chat_input:
            base.write("/")

        base.write(inter.data.get("name"))

        try:
            opts = inter.data.get("options", [False])
            for item in opts:
                if item["type"] not in (1, 2):
                    # param
                    continue

                base.write(f" {item['name']}")
                if item.get("options"):
                    for nested in item["options"]:
                        if nested["type"] != 1:
                            # param
                            continue

                        base.write(f" {nested['name']}")
        except:
            pass

        return base.getvalue()

    async def delete_message(self, *, message_id: int, channel_id: int):
        await self._connection.http.delete_message(channel_id, message_id)

    async def try_fetch_icon_url(self, guild_id: int) -> Union[None, str]:
        """Given an id and state, return either the guilds icon or None."""
        if guild_id not in self.state.guild_cache:
            guild = await self.state.bot.fetch_guild(guild_id)
            self.state.refresh_guild_cache(guild)
        else:
            guild = self.state.guild_cache.get_entry(guild_id)

            if not guild.icon:
                # Update cache if we don't have it
                guild = await self.state.bot.fetch_guild(guild_id)
                self.state.refresh_guild_cache(guild)

        return None if not guild.icon else guild.icon.url
