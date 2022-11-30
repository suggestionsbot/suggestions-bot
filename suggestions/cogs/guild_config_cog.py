from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake import Guild
from disnake.ext import commands

from suggestions import Stats
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import InvalidGuildConfigOption
from suggestions.objects import GuildConfig
from suggestions.stats import StatsEnum

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class GuildConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
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
        log.debug(
            "Updating GuildConfig %s in database for guild %s",
            guild_config,
            interaction.guild_id,
        )
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        await interaction.send(
            f"I have set this guilds suggestion channel to {channel.mention}",
            ephemeral=True,
        )
        log.debug(
            "User %s changed suggestions channel to %s in guild %s",
            interaction.author.id,
            channel.id,
            interaction.guild_id,
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
        log.debug(
            "Updating GuildConfig %s in database for guild %s",
            guild_config,
            interaction.guild_id,
        )
        await self.state.guild_config_db.upsert(guild_config, guild_config)
        await interaction.send(
            f"I have set this guilds log channel to {channel.mention}",
            ephemeral=True,
        )
        log.debug(
            "User %s changed logs channel to %s in guild %s",
            interaction.author.id,
            channel.id,
            interaction.guild_id,
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_LOG_CHANNEL,
        )

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
        icon_url = await Guild.try_fetch_icon_url(interaction.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\n",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=icon_url)

        if config == "Log channel":
            log_channel = (
                f"Log channel: <#{guild_config.log_channel_id}>"
                if guild_config.log_channel_id
                else "Not set"
            )
            embed.description += log_channel

        elif config == "Suggestions channel":
            suggestions_channel = (
                f"Suggestion channel: <#{guild_config.suggestions_channel_id}>"
                if guild_config.suggestions_channel_id
                else "Not set"
            )
            embed.description += suggestions_channel

        elif config == "Dm responses":
            dm_responses = "will not" if guild_config.dm_messages_disabled else "will"
            embed.description += (
                f"Dm responses: I {dm_responses} DM users on actions such as suggest"
            )

        elif config == "Threads for suggestions":
            plural = "will" if guild_config.threads_for_suggestions else "will not"
            embed.description += f"I {plural} create threads for new suggestions"

        elif config == "Keep logs":
            if guild_config.keep_logs:
                embed.description += (
                    "Suggestion logs will be kept in your suggestions channel."
                )
            else:
                embed.description += (
                    "Suggestion logs will be kept in your logs channel."
                )

        else:
            raise InvalidGuildConfigOption

        await interaction.send(embed=embed, ephemeral=True)
        log.debug(
            "User %s viewed the %s config in guild %s",
            interaction.author.id,
            config,
            interaction.guild_id,
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
            else "Not set"
        )
        suggestions_channel = (
            f"<#{guild_config.suggestions_channel_id}>"
            if guild_config.suggestions_channel_id
            else "Not set"
        )
        dm_responses = "will not" if guild_config.dm_messages_disabled else "will"
        plural = "will" if guild_config.threads_for_suggestions else "will not"
        threads = f"I {plural} create threads for new suggestions"
        if guild_config.keep_logs:
            keep_logs = "Suggestion logs will be kept in your suggestions channel."
        else:
            keep_logs = "Suggestion logs will be kept in your logs channel."

        icon_url = await Guild.try_fetch_icon_url(interaction.guild_id, self.state)
        guild = self.state.guild_cache.get_entry(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\nSuggestions channel: {suggestions_channel}\n"
            f"Log channel: {log_channel}\nDm responses: I {dm_responses} DM users on actions such as suggest\n"
            f"Suggestion threads: {threads}\nKeep Logs: {keep_logs}",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=icon_url)
        await interaction.send(embed=embed, ephemeral=True)
        log.debug(
            "User %s viewed the global config in guild %s",
            interaction.author.id,
            interaction.guild_id,
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_CONFIG_GET,
        )

    @config.sub_command_group()
    async def dm(self, interaction: disnake.GuildCommandInteraction):
        pass

    @dm.sub_command()
    async def enable(self, interaction: disnake.GuildCommandInteraction):
        """Enable DM's responses to actions guild wide."""
        await self.modify_guild_config(
            interaction,
            "dm_messages_disabled",
            False,
            "I have enabled DM messages for this guild.",
            "Enabled DM messages for guild %s",
            self.stats.type.GUILD_DM_ENABLE,
        )

    @dm.sub_command()
    async def disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable DM's responses to actions guild wide."""
        await self.modify_guild_config(
            interaction,
            "dm_messages_disabled",
            True,
            "I have disabled DM messages for this guild.",
            "Disabled DM messages for guild %s",
            self.stats.type.GUILD_DM_DISABLE,
        )

    @config.sub_command_group()
    async def anonymous(self, interaction: disnake.GuildCommandInteraction):
        pass

    @anonymous.sub_command()
    async def enable(self, interaction: disnake.GuildCommandInteraction):
        """Enable anonymous suggestions."""
        await self.modify_guild_config(
            interaction,
            "can_have_anonymous_suggestions",
            True,
            "I have enabled DM messages for this guild.",
            "Enabled anonymous suggestions for guild %s",
            self.stats.type.GUILD_DM_ENABLE,
        )

    @anonymous.sub_command()
    async def disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable anonymous suggestions."""
        await self.modify_guild_config(
            interaction,
            "can_have_anonymous_suggestions",
            False,
            "I have disabled DM messages for this guild.",
            "Disabled anonymous suggestions for guild %s",
            self.stats.type.GUILD_DM_DISABLE,
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
            "I have enabled threads on new suggestions for this guild.",
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
            "I have disabled thread creation on new suggestions for this guild.",
            "Disabled thread creation on new suggestions for guild %s",
            self.stats.type.GUILD_THREAD_DISABLE,
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
            "Suggestions will now stay in your suggestions channel instead of going to logs.",
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
            "Suggestions will now be moved to your logs channel when finished.",
            "Disabled keep logs on suggestions for guild %s",
            self.stats.type.GUILD_KEEPLOGS_DISABLE,
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
        log.debug(
            "Updating GuildConfig %s in database for guild %s",
            guild_config,
            interaction.guild_id,
        )
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send(
            user_message,
            ephemeral=True,
        )
        log.debug(
            log_message,
            interaction.guild_id,
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            stat_type,
        )


def setup(bot):
    bot.add_cog(GuildConfigCog(bot))
