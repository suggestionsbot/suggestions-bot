from __future__ import annotations

import logging
from datetime import timedelta
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands
from humanize import precisedelta, intcomma

from suggestions import Stats
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import InvalidGuildConfigOption, MessageTooLong
from suggestions.interaction_handler import InteractionHandler
from suggestions.objects import GuildConfig
from suggestions.objects.premium_guild_config import CooldownPeriod, PremiumGuildConfig
from suggestions.stats import StatsEnum

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

logger = logging.getLogger(__name__)


class GuildConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def config(self, interaction: disnake.GuildCommandInteraction):
        """Configure the bot for your guild."""
        pass

    @config.sub_command()
    async def channel(
        self,
        interaction: disnake.GuildCommandInteraction,
        channel: disnake.TextChannel,
    ):
        """Set your guilds suggestion channel."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.suggestions_channel_id = channel.id
        self.state.refresh_guild_config(guild_config)
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        await interaction.send(
            self.bot.get_locale(
                "CONFIG_CHANNEL_INNER_MESSAGE", interaction.locale
            ).format(channel.mention),
            ephemeral=True,
        )
        logger.debug(
            "User %s changed suggestions channel to %s in guild %s",
            interaction.author.id,
            channel.id,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_SUGGEST_CHANNEL,
        )

    @config.sub_command()
    async def logs(
        self,
        interaction: disnake.GuildCommandInteraction,
        channel: disnake.TextChannel,
    ):
        """Set your guilds log channel."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.log_channel_id = channel.id
        self.state.refresh_guild_config(guild_config)
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        await interaction.send(
            self.bot.get_locale("CONFIG_LOGS_INNER_MESSAGE", interaction.locale).format(
                channel.mention
            ),
            ephemeral=True,
        )
        logger.debug(
            "User %s changed logs channel to %s in guild %s",
            interaction.author.id,
            channel.id,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_LOG_CHANNEL,
        )

    @config.sub_command()
    async def queue_channel(
        self,
        interaction: disnake.GuildCommandInteraction,
        channel: disnake.TextChannel,
    ):
        """Set your guilds physical suggestions queue channel."""
        ih: InteractionHandler = await InteractionHandler.new_handler(interaction)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        try:
            # BT-21 doesn't apply here as we are sending not fetching
            message = await channel.send("This is a test message and can be ignored.")
            await message.delete()
        except disnake.Forbidden:
            return await ih.send(
                f"I do not have permissions to delete messages in {channel.mention}. "
                f"Please give me permissions and run this command again.",
            )

        guild_config.queued_channel_id = channel.id
        self.state.refresh_guild_config(guild_config)
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        await ih.send(
            self.bot.get_localized_string(
                "CONFIG_QUEUE_CHANNEL_INNER_MESSAGE",
                ih,
                extras={"CHANNEL": channel.mention},
            )
        )
        logger.debug(
            "User %s changed physical queue channel to %s in guild %s",
            interaction.author.id,
            channel.id,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_QUEUE_CHANNEL,
        )

    @config.sub_command()
    async def queue_log_channel(
        self,
        interaction: disnake.GuildCommandInteraction,
        channel: disnake.TextChannel = None,
    ):
        """Set your guilds suggestion queue log channel for rejected suggestions."""
        ih: InteractionHandler = await InteractionHandler.new_handler(interaction)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.queued_log_channel_id = channel.id if channel else None
        self.state.refresh_guild_config(guild_config)
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        key = (
            "CONFIG_QUEUE_CHANNEL_INNER_MESSAGE_REMOVED"
            if channel is None
            else "CONFIG_QUEUE_LOG_CHANNEL_INNER_MESSAGE"
        )
        msg = self.bot.get_locale(key, interaction.locale)
        if channel is not None:
            msg = msg.format(channel.mention)
        await ih.send(msg)
        logger.debug(
            "User %s changed rejected queue log channel to %s in guild %s",
            interaction.author.id,
            channel.id if channel is not None else None,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_REJECTED_QUEUE_CHANNEL,
        )

    # TODO Re-enable premium features at later date
    # @config.sub_command()
    # async def suggestions_prefix(
    #     self,
    #     interaction: disnake.GuildCommandInteraction,
    #     message: str = commands.Param(
    #         default="",
    #         description="The message to send before the suggestion. This can be a role ping.",
    #     ),
    #     applies_to: str = commands.Param(
    #         default="Both",
    #         description="Whether this message should be sent on suggestions or queued suggestions.",
    #         choices=["Suggestion", "Queued Suggestion", "Both"],
    #     ),
    # ):
    #     """Set a custom message for the suggest command."""
    #     ih: InteractionHandler = await InteractionHandler.new_handler(
    #         interaction, requires_premium=True
    #     )
    #     if len(message) > 1000:
    #         raise MessageTooLong(message)
    #
    #     if (
    #         "@everyone" in message
    #         or "@here" in message
    #         or f"<@&{interaction.guild_id}>" in message
    #     ):
    #         await ih.send(
    #             "Sorry, prefixes cannot contain everyone or here pings. "
    #             "We recommend setting a generic role instead."
    #         )
    #         return None
    #
    #     premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
    #         ih.interaction.guild_id, interaction.bot.state
    #     )
    #     if applies_to == "Suggestion":
    #         premium_guild_config.suggestions_prefix = message
    #     elif applies_to == "Queued Suggestion":
    #         premium_guild_config.queued_suggestions_prefix = message
    #     else:
    #         premium_guild_config.suggestions_prefix = message
    #         premium_guild_config.queued_suggestions_prefix = message
    #
    #     await self.bot.db.premium_guild_configs.upsert(
    #         premium_guild_config, premium_guild_config
    #     )
    #     await ih.send(
    #         "Thanks! I've saved your configuration changes for this. "
    #         "That message will now be sent as a part of those suggestions going forward."
    #     )
    #     return None
    #
    # @config.sub_command()
    # async def suggestions_cooldown(
    #     self,
    #     interaction: disnake.GuildCommandInteraction,
    #     cooldown_amount: int = commands.Param(
    #         default=None,
    #         description="How many times users can run /suggest during the cooldown period.",
    #     ),
    #     cooldown_period: CooldownPeriod = commands.Param(
    #         default=None,
    #         description="The time period to allow cooldown_amount's during.",
    #     ),
    # ):
    #     """Set a custom cooldown for the suggest command."""
    #     ih: InteractionHandler = await InteractionHandler.new_handler(
    #         interaction, requires_premium=True
    #     )
    #     premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
    #         ih.interaction.guild_id, interaction.bot.state
    #     )
    #     premium_guild_config.cooldown_amount = cooldown_amount
    #     premium_guild_config.cooldown_period = cooldown_period
    #     await self.bot.db.premium_guild_configs.upsert(
    #         premium_guild_config, premium_guild_config
    #     )
    #     await ih.send("Thanks! I've saved your configuration changes for this.")

    @config.sub_command()
    async def get(
        self,
        interaction: disnake.GuildCommandInteraction,
        config=commands.Param(
            description="The optional configuration to view",
            choices=[
                "Log channel",
                "Suggestions channel",
                "Dm responses",
                "Threads for suggestions",
                "Keep logs",
                "Anonymous suggestions",
                "Auto archive threads",
                "Suggestions queue",
                "Images in suggestions",
                "Anonymous resolutions",
                "Using channel queue",
                "Queue channel",
                "Queue rejection channel",
                "Ping on suggestion thread creation",
            ],
            default=None,
        ),
    ):
        """Show a current configuration"""
        if not config:
            return await self.send_full_config(interaction)

        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        icon_url = await self.bot.try_fetch_icon_url(interaction.guild_id)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=self.bot.get_locale(
                "CONFIG_GET_INNER_BASE_EMBED_DESCRIPTION", interaction.locale
            ).format(guild.name),
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=icon_url)

        if config == "Log channel":
            log_channel = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_LOG_CHANNEL_SET", interaction.locale
                ).format(guild_config.log_channel_id)
                if guild_config.log_channel_id
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_LOG_CHANNEL_NOT_SET", interaction.locale
                )
            )
            embed.description += log_channel

        elif config == "Ping on suggestion thread creation":
            locale_string = (
                "CONFIG_GET_INNER_USES_THREAD_PINGS_SET"
                if guild_config.ping_on_thread_creation
                else "CONFIG_GET_INNER_USES_THREAD_PINGS_NOT_SET"
            )
            text = self.bot.get_localized_string(locale_string, interaction)

            embed.description += text

        elif config == "Queue channel":
            log_channel = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_QUEUE_LOG_CHANNEL_SET", interaction.locale
                ).format(guild_config.queued_channel_id)
                if guild_config.queued_channel_id
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_QUEUE_LOG_CHANNEL_NOT_SET",
                    interaction.locale,
                )
            )
            embed.description += log_channel

        elif config == "Queue rejection channel":
            log_channel = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_QUEUE_REJECTION_LOG_CHANNEL_SET",
                    interaction.locale,
                ).format(guild_config.queued_log_channel_id)
                if guild_config.queued_log_channel_id
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_QUEUE_REJECTION_LOG_CHANNEL_NOT_SET",
                    interaction.locale,
                )
            )
            embed.description += log_channel

        elif config == "Suggestions channel":
            suggestions_channel = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_SUGGESTION_CHANNEL_SET",
                    interaction.locale,
                ).format(guild_config.suggestions_channel_id)
                if guild_config.suggestions_channel_id
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_SUGGESTION_CHANNEL_NOT_SET",
                    interaction.locale,
                )
            )
            embed.description += suggestions_channel

        elif config == "Dm responses":
            dm_responses = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_DM_RESPONSES_NOT_SET", interaction.locale
                )
                if guild_config.dm_messages_disabled
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_DM_RESPONSES_SET", interaction.locale
                )
            )
            embed.description += self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_DM_RESPONSES_MESSAGE", interaction.locale
            ).format(dm_responses)

        elif config == "Threads for suggestions":
            plural = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_THREADS_SET", interaction.locale
                )
                if guild_config.threads_for_suggestions
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_PARTIAL_THREADS_NOT_SET", interaction.locale
                )
            )
            embed.description += self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_THREADS_MESSAGE", interaction.locale
            ).format(plural)

        elif config == "Keep logs":
            if guild_config.keep_logs:
                embed.description += self.bot.get_locale(
                    "CONFIG_GET_INNER_KEEP_LOGS_SET", interaction.locale
                )
            else:
                embed.description += self.bot.get_locale(
                    "CONFIG_GET_INNER_KEEP_LOGS_NOT_SET", interaction.locale
                )

        elif config == "Anonymous suggestions":
            text = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_SET", interaction.locale
                )
                if guild_config.can_have_anonymous_suggestions
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_NOT_SET", interaction.locale
                )
            )
            embed.description += self.bot.get_locale(
                "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_MESSAGE", interaction.locale
            ).format(text)

        elif config == "Images in suggestions":
            text = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_SET", interaction.locale
                )
                if guild_config.can_have_images_in_suggestions
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_NOT_SET", interaction.locale
                )
            )
            embed.description += self.bot.get_locale(
                "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_MESSAGE", interaction.locale
            ).format(text)

        elif config == "Auto archive threads":
            text = (
                self.bot.get_locale(
                    "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_SET", interaction.locale
                )
                if guild_config.auto_archive_threads
                else self.bot.get_locale(
                    "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_NOT_SET", interaction.locale
                )
            )
            embed.description += self.bot.get_locale(
                "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_MESSAGE", interaction.locale
            ).format(text)

        elif config == "Suggestions queue":
            locale_string = (
                "CONFIG_GET_INNER_SUGGESTIONS_QUEUE_SET"
                if guild_config.uses_suggestion_queue
                else "CONFIG_GET_INNER_SUGGESTIONS_QUEUE_NOT_SET"
            )
            text = self.bot.get_localized_string(locale_string, interaction)

            embed.description += self.bot.get_localized_string(
                "CONFIG_GET_INNER_SUGGESTIONS_QUEUE_MESSAGE",
                interaction,
                extras={"TEXT": text.lower()},
            )

        elif config == "Anonymous resolutions":
            locale_string = (
                "CONFIG_GET_INNER_ANONYMOUS_RESOLUTION_SET"
                if guild_config.anonymous_resolutions
                else "CONFIG_GET_INNER_ANONYMOUS_RESOLUTION_NOT_SET"
            )
            text = self.bot.get_localized_string(locale_string, interaction)

            embed.description += text

        elif config == "Using channel queue":
            locale_string = (
                "CONFIG_GET_INNER_USES_PHYSICAL_QUEUE_NOT_SET"
                if guild_config.virtual_suggestion_queue
                else "CONFIG_GET_INNER_USES_PHYSICAL_QUEUE_SET"
            )

            text = self.bot.get_localized_string(locale_string, interaction)

            embed.description += text

        else:
            raise InvalidGuildConfigOption

        await interaction.send(embed=embed, ephemeral=True)
        logger.debug(
            "User %s viewed the %s config in guild %s",
            interaction.author.id,
            config,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_GET,
        )

    async def send_full_config(self, interaction: disnake.GuildCommandInteraction):
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        log_channel = (
            f"<#{guild_config.log_channel_id}>"
            if guild_config.log_channel_id
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_LOG_CHANNEL_NOT_SET", interaction.locale
            )
        )
        suggestions_channel = (
            f"<#{guild_config.suggestions_channel_id}>"
            if guild_config.suggestions_channel_id
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_SUGGESTION_CHANNEL_NOT_SET",
                interaction.locale,
            )
        )
        queue_channel = (
            f"<#{guild_config.queued_channel_id}>"
            if guild_config.queued_channel_id
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_QUEUE_LOG_CHANNEL_NOT_SET",
                interaction.locale,
            )
        )
        queue_rejection_channel = (
            f"<#{guild_config.queued_log_channel_id}>"
            if guild_config.queued_log_channel_id
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_QUEUE_REJECTION_LOG_CHANNEL_NOT_SET",
                interaction.locale,
            )
        )
        dm_responses = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_DM_RESPONSES_NOT_SET", interaction.locale
            )
            if guild_config.dm_messages_disabled
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_DM_RESPONSES_SET", interaction.locale
            )
        )

        threads_text = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_THREADS_SET", interaction.locale
            )
            if guild_config.threads_for_suggestions
            else self.bot.get_locale(
                "CONFIG_GET_INNER_PARTIAL_THREADS_NOT_SET", interaction.locale
            )
        )
        threads = self.bot.get_locale(
            "CONFIG_GET_INNER_PARTIAL_THREADS_MESSAGE", interaction.locale
        ).format(threads_text)

        if guild_config.keep_logs:
            keep_logs = self.bot.get_locale(
                "CONFIG_GET_INNER_KEEP_LOGS_SET", interaction.locale
            )
        else:
            keep_logs = self.bot.get_locale(
                "CONFIG_GET_INNER_KEEP_LOGS_NOT_SET", interaction.locale
            )

        anon_text = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_SET", interaction.locale
            )
            if guild_config.can_have_anonymous_suggestions
            else self.bot.get_locale(
                "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_NOT_SET", interaction.locale
            )
        )
        anon = self.bot.get_locale(
            "CONFIG_GET_INNER_ANONYMOUS_SUGGESTIONS_MESSAGE", interaction.locale
        ).format(anon_text)

        physical_queue = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_USES_PHYSICAL_QUEUE_NOT_SET", interaction.locale
            )
            if guild_config.virtual_suggestion_queue
            else self.bot.get_locale(
                "CONFIG_GET_INNER_USES_PHYSICAL_QUEUE_SET", interaction.locale
            )
        )

        image_text = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_SET", interaction.locale
            )
            if guild_config.can_have_images_in_suggestions
            else self.bot.get_locale(
                "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_NOT_SET", interaction.locale
            )
        )
        images = self.bot.get_locale(
            "CONFIG_GET_INNER_IMAGES_IN_SUGGESTIONS_MESSAGE", interaction.locale
        ).format(image_text)

        auto_archive_threads_text = (
            self.bot.get_locale(
                "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_SET", interaction.locale
            )
            if guild_config.auto_archive_threads
            else self.bot.get_locale(
                "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_NOT_SET", interaction.locale
            )
        )
        auto_archive_threads = self.bot.get_locale(
            "CONFIG_GET_INNER_AUTO_ARCHIVE_THREADS_MESSAGE", interaction.locale
        ).format(auto_archive_threads_text)

        ping_on_thread_creation = (
            "CONFIG_GET_INNER_USES_THREAD_PINGS_SET"
            if guild_config.ping_on_thread_creation
            else "CONFIG_GET_INNER_USES_THREAD_PINGS_NOT_SET"
        )
        ping_on_thread_creation = self.bot.get_localized_string(
            ping_on_thread_creation, interaction
        )

        locale_string = (
            "CONFIG_GET_INNER_SUGGESTIONS_QUEUE_SET"
            if guild_config.uses_suggestion_queue
            else "CONFIG_GET_INNER_SUGGESTIONS_QUEUE_NOT_SET"
        )
        suggestions_queue = self.bot.get_localized_string(locale_string, interaction)

        locale_string = (
            "CONFIG_GET_INNER_ANONYMOUS_RESOLUTION_SET"
            if guild_config.anonymous_resolutions
            else "CONFIG_GET_INNER_ANONYMOUS_RESOLUTION_NOT_SET"
        )
        anonymous_resolutions = self.bot.get_localized_string(
            locale_string, interaction
        )

        icon_url = await self.bot.try_fetch_icon_url(interaction.guild_id)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\nSuggestions channel: {suggestions_channel}\n"
            f"Log channel: {log_channel}\nDm responses: I {dm_responses} DM users on actions such as suggest\n"
            f"Suggestion threads: {threads}\nKeep Logs: {keep_logs}\nAnonymous suggestions: {anon}\n"
            f"Automatic thread archiving: {auto_archive_threads}\nSuggestions queue: {suggestions_queue}\n"
            f"Channel queue: {physical_queue}\nImages in suggestions: {images}\n"
            f"Anonymous resolutions: {anonymous_resolutions}\nPings in new suggestion threads: {ping_on_thread_creation}\n"
            f"Queue channel: {queue_channel}\nQueue rejection channel: {queue_rejection_channel}",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=icon_url)
        await interaction.send(embed=embed, ephemeral=True)
        logger.debug(
            "User %s viewed the global config in guild %s",
            interaction.author.id,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_GET,
        )

    # TODO Re-enable premium features at later date
    # @config.sub_command()
    # async def get_premium(
    #     self,
    #     interaction: disnake.GuildCommandInteraction,
    # ):
    #     """Show the current premium configuration"""
    #     ih = await InteractionHandler.new_handler(interaction)
    #     premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
    #         ih.interaction.guild_id, interaction.bot.state
    #     )
    #     cooldown_period = (
    #         precisedelta(premium_guild_config.cooldown_period.as_timedelta())
    #         if premium_guild_config.cooldown_period
    #         else "Not set"
    #     )
    #     cooldown_amount = (
    #         intcomma(premium_guild_config.cooldown_amount)
    #         if premium_guild_config.cooldown_period
    #         else "Not set"
    #     )
    #     embed = disnake.Embed(
    #         title="Premium configuration for your guild",
    #         color=self.bot.colors.embed_color,
    #         timestamp=self.bot.state.now,
    #         description=f"Cooldown period: `{cooldown_period}`\n"
    #         f"Cooldown amount per period: `{cooldown_amount}`\n"
    #         f"Suggestions prefix: {premium_guild_config.suggestions_prefix}\n"
    #         f"Queued suggestions prefix: {premium_guild_config.queued_suggestions_prefix}\n",
    #     )
    #     await ih.send(embed=embed)

    @config.sub_command_group()
    async def dm(self, interaction: disnake.GuildCommandInteraction):
        pass

    @dm.sub_command(name="enable")
    async def dm_enable(self, interaction: disnake.GuildCommandInteraction):
        """Enable DM's responses to actions guild wide."""
        await self.modify_guild_config(
            interaction,
            "dm_messages_disabled",
            False,
            self.bot.get_locale("CONFIG_DM_ENABLE_INNER_MESSAGE", interaction.locale),
            "Enabled DM messages for guild %s",
            self.stats.type.GUILD_DM_ENABLE,
        )

    @dm.sub_command(name="disable")
    async def dm_disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable DM's responses to actions guild wide."""
        await self.modify_guild_config(
            interaction,
            "dm_messages_disabled",
            True,
            self.bot.get_locale("CONFIG_DM_DISABLE_INNER_MESSAGE", interaction.locale),
            "Disabled DM messages for guild %s",
            self.stats.type.GUILD_DM_DISABLE,
        )

    @config.sub_command_group()
    async def anonymous(self, interaction: disnake.GuildCommandInteraction):
        pass

    @anonymous.sub_command(name="enable")
    async def anon_enable(self, interaction: disnake.GuildCommandInteraction):
        """Enable anonymous suggestions."""
        await self.modify_guild_config(
            interaction,
            "can_have_anonymous_suggestions",
            True,
            self.bot.get_locale(
                "CONFIG_ANONYMOUS_ENABLE_INNER_SUCCESS", interaction.locale
            ),
            "Enabled anonymous suggestions for guild %s",
            self.stats.type.GUILD_ANONYMOUS_ENABLE,
        )

    @anonymous.sub_command(name="disable")
    async def anon_disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable anonymous suggestions."""
        await self.modify_guild_config(
            interaction,
            "can_have_anonymous_suggestions",
            False,
            self.bot.get_locale(
                "CONFIG_ANONYMOUS_DISABLE_INNER_SUCCESS", interaction.locale
            ),
            "Disabled anonymous suggestions for guild %s",
            self.stats.type.GUILD_ANONYMOUS_DISABLE,
        )

    @config.sub_command_group()
    async def thread(self, interaction: disnake.GuildCommandInteraction):
        pass

    @thread.sub_command(name="enable")
    async def thread_enable(self, interaction: disnake.GuildCommandInteraction):
        """Enable thread creation on new suggestions."""
        await self.modify_guild_config(
            interaction,
            "threads_for_suggestions",
            True,
            self.bot.get_locale(
                "CONFIG_THREAD_ENABLE_INNER_MESSAGE", interaction.locale
            ),
            "Enabled threads on new suggestions for guild %s",
            self.stats.type.GUILD_THREAD_ENABLE,
        )

    @thread.sub_command(name="disable")
    async def thread_disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable thread creation on new suggestions."""
        await self.modify_guild_config(
            interaction,
            "threads_for_suggestions",
            False,
            self.bot.get_locale(
                "CONFIG_THREAD_DISABLE_INNER_MESSAGE", interaction.locale
            ),
            "Disabled thread creation on new suggestions for guild %s",
            self.stats.type.GUILD_THREAD_DISABLE,
        )

    @config.sub_command_group()
    async def ping_on_thread_creation(
        self, interaction: disnake.GuildCommandInteraction
    ):
        pass

    @ping_on_thread_creation.sub_command(name="enable")
    async def ping_on_thread_creation_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Enable pings when a thread is created on a suggestion."""
        await self.modify_guild_config(
            interaction,
            "ping_on_thread_creation",
            True,
            self.bot.get_locale(
                "CONFIG_PING_ON_THREAD_CREATION_ENABLE_INNER_MESSAGE",
                interaction.locale,
            ),
            "Enabled pings on new suggestion threads for guild %s",
            self.stats.type.GUILD_PING_ON_THREAD_CREATE_ENABLE,
        )

    @ping_on_thread_creation.sub_command(name="disable")
    async def ping_on_thread_creation_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Disable pings when a thread is created on a suggestion."""
        await self.modify_guild_config(
            interaction,
            "ping_on_thread_creation",
            False,
            self.bot.get_locale(
                "CONFIG_PING_ON_THREAD_CREATION_DISABLE_INNER_MESSAGE",
                interaction.locale,
            ),
            "Disabled pings on new suggestion threads for guild %s",
            self.stats.type.GUILD_PING_ON_THREAD_CREATE_DISABLE,
        )

    @config.sub_command_group()
    async def keeplogs(self, interaction: disnake.GuildCommandInteraction):
        pass

    @keeplogs.sub_command(name="enable")
    async def keeplogs_enable(self, interaction: disnake.GuildCommandInteraction):
        """Keep suggestions in the suggestions channel instead of moving them to logs channel."""
        await self.modify_guild_config(
            interaction,
            "keep_logs",
            True,
            self.bot.get_locale(
                "CONFIG_KEEPLOGS_ENABLE_INNER_MESSAGE", interaction.locale
            ),
            "Enabled keep logs on suggestions for guild %s",
            self.stats.type.GUILD_KEEPLOGS_ENABLE,
        )

    @keeplogs.sub_command(name="disable")
    async def keeplogs_disable(self, interaction: disnake.GuildCommandInteraction):
        """Move suggestions in the suggestions channel to logs channel when done."""
        await self.modify_guild_config(
            interaction,
            "keep_logs",
            False,
            self.bot.get_locale(
                "CONFIG_KEEPLOGS_DISABLE_INNER_MESSAGE", interaction.locale
            ),
            "Disabled keep logs on suggestions for guild %s",
            self.stats.type.GUILD_KEEPLOGS_DISABLE,
        )

    @config.sub_command_group()
    async def auto_archive_threads(self, interaction: disnake.GuildCommandInteraction):
        pass

    @auto_archive_threads.sub_command(name="enable")
    async def auto_archive_threads_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Automatically archive threads created for suggestions upon suggestion resolution."""
        await self.modify_guild_config(
            interaction,
            "auto_archive_threads",
            True,
            self.bot.get_locale(
                "CONFIG_AUTO_ARCHIVE_THREADS_ENABLE_INNER_MESSAGE", interaction.locale
            ),
            "Enabled auto archive threads on suggestions for guild %s",
            self.stats.type.GUILD_AUTO_ARCHIVE_THREADS_ENABLE,
        )

    @auto_archive_threads.sub_command(name="disable")
    async def auto_archive_threads_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Don't archive threads created for suggestions upon suggestion resolution."""
        await self.modify_guild_config(
            interaction,
            "auto_archive_threads",
            False,
            self.bot.get_locale(
                "CONFIG_AUTO_ARCHIVE_THREADS_DISABLE_INNER_MESSAGE", interaction.locale
            ),
            "Disabled auto archive threads on suggestions for guild %s",
            self.stats.type.GUILD_AUTO_ARCHIVE_THREADS_DISABLE,
        )

    @config.sub_command_group()
    async def suggestion_queue(self, interaction: disnake.GuildCommandInteraction):
        pass

    @suggestion_queue.sub_command(name="enable")
    async def suggestion_queue_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Send all suggestions to a queue for approval before going to your suggestions channel."""
        await self.modify_guild_config(
            interaction,
            "uses_suggestion_queue",
            True,
            self.bot.get_localized_string(
                "CONFIG_SUGGESTIONS_QUEUE_ENABLE_INNER_MESSAGE", interaction
            ),
            "Enabled suggestions queue on suggestions for guild %s",
            self.stats.type.GUILD_SUGGESTIONS_QUEUE_ENABLE,
        )

    @suggestion_queue.sub_command(name="disable")
    async def suggestion_queue_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Send all suggestions directly to your suggestions channel."""
        await self.modify_guild_config(
            interaction,
            "uses_suggestion_queue",
            False,
            self.bot.get_localized_string(
                "CONFIG_SUGGESTIONS_QUEUE_DISABLE_INNER_MESSAGE", interaction
            ),
            "Disabled suggestions queue on suggestions for guild %s",
            self.stats.type.GUILD_SUGGESTIONS_QUEUE_DISABLE,
        )

    @config.sub_command_group()
    async def anonymous_resolutions(self, interaction: disnake.GuildCommandInteraction):
        pass

    @anonymous_resolutions.sub_command(name="enable")
    async def anonymous_resolutions_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Suggesters no longer see who approved or rejected their suggestions."""
        await self.modify_guild_config(
            interaction,
            "anonymous_resolutions",
            True,
            self.bot.get_localized_string(
                "CONFIG_ANONYMOUS_RESOLUTION_ENABLE_INNER_MESSAGE", interaction
            ),
            "Enabled anonymous resolutions on suggestions for guild %s",
            self.stats.type.GUILD_ANONYMOUS_RESOLUTIONS_ENABLE,
        )

    @anonymous_resolutions.sub_command(name="disable")
    async def anonymous_resolutions_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Suggesters see who approved or rejected their suggestions."""
        await self.modify_guild_config(
            interaction,
            "anonymous_resolutions",
            False,
            self.bot.get_localized_string(
                "CONFIG_ANONYMOUS_RESOLUTION_DISABLE_INNER_MESSAGE", interaction
            ),
            "Disabled anonymous resolutions on suggestions for guild %s",
            self.stats.type.GUILD_ANONYMOUS_RESOLUTIONS_DISABLE,
        )

    @config.sub_command_group()
    async def use_channel_queue(self, interaction: disnake.GuildCommandInteraction):
        pass

    @use_channel_queue.sub_command(name="enable")
    async def use_physical_queue_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Set the queue to use a channel for queuing suggestions."""
        await self.modify_guild_config(
            interaction,
            "virtual_suggestion_queue",
            False,
            self.bot.get_localized_string(
                "CONFIG_USE_PHYSICAL_QUEUE_ENABLE_INNER_MESSAGE", interaction
            ),
            "Enabled physical queue on suggestions for guild %s",
            self.stats.type.GUILD_PHYSICAL_QUEUE_ENABLE,
        )

    @use_channel_queue.sub_command(name="disable")
    async def use_physical_queue_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Use a virtual queue for suggestions in this guild."""
        await self.modify_guild_config(
            interaction,
            "virtual_suggestion_queue",
            True,
            self.bot.get_localized_string(
                "CONFIG_USE_PHYSICAL_QUEUE_DISABLE_INNER_MESSAGE", interaction
            ),
            "Disabled physical queue on suggestions for guild %s",
            self.stats.type.GUILD_PHYSICAL_QUEUE_DISABLE,
        )

    @config.sub_command_group()
    async def images_in_suggestions(self, interaction: disnake.GuildCommandInteraction):
        pass

    @images_in_suggestions.sub_command(name="enable")
    async def images_in_suggestions_enable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Allow images in suggestions for this guild."""
        await self.modify_guild_config(
            interaction,
            "can_have_images_in_suggestions",
            True,
            self.bot.get_localized_string(
                "CONFIG_SUGGESTIONS_IMAGES_ENABLE_INNER_MESSAGE", interaction
            ),
            "Enabled images on suggestions for guild %s",
            self.stats.type.GUILD_IMAGES_IN_SUGGESTIONS_ENABLE,
        )

    @images_in_suggestions.sub_command(name="disable")
    async def images_in_suggestions_disable(
        self, interaction: disnake.GuildCommandInteraction
    ):
        """Do not allow images in suggestions for this guild."""
        await self.modify_guild_config(
            interaction,
            "can_have_images_in_suggestions",
            False,
            self.bot.get_localized_string(
                "CONFIG_SUGGESTIONS_IMAGES_DISABLE_INNER_MESSAGE", interaction
            ),
            "Disabled images on suggestions for guild %s",
            self.stats.type.GUILD_IMAGES_IN_SUGGESTIONS_DISABLE,
        )

    async def modify_guild_config(
        self,
        interaction: disnake.GuildCommandInteraction,
        field: str,
        new_value: bool,
        user_message: str,
        log_message: str,
        stat_type: StatsEnum,
    ):
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        setattr(guild_config, field, new_value)
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send(
            user_message,
            ephemeral=True,
        )
        logger.debug(
            log_message,
            interaction.guild_id,
            extra={
                "interaction.author.id": interaction.author.id,
                "interaction.author.global_name": (
                    interaction.author.global_name
                    if interaction.author.global_name
                    else ""
                ),
                "interaction.guild.id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            stat_type,
        )


def setup(bot):
    bot.add_cog(GuildConfigCog(bot))
