from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands

from suggestions import checks, Stats
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.exceptions import InvalidGuildConfigOption
from suggestions.objects import GuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class GuildConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def config(self, interaction: disnake.GuildCommandInteraction):
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
            choices=["Log channel", "Suggestions channel", "Dm responses"],
            default=None,
        ),
    ):
        """Show a current configuration"""
        if not config:
            return await self.send_full_config(interaction)

        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild = await self.bot.fetch_guild(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\n",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=guild.icon.url)

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
        guild = await self.bot.fetch_guild(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\nSuggestions channel: {suggestions_channel}\n"
            f"Log channel: {log_channel}\nDm responses: I {dm_responses} DM users on actions such as suggest",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=guild.icon.url)
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
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.dm_messages_disabled = False
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send(
            "I have enabled DM messages for this guild.", ephemeral=True
        )
        log.debug("Enabled DM messages for guild %s", interaction.guild_id)
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_DM_ENABLE,
        )

    @dm.sub_command()
    async def disable(self, interaction: disnake.GuildCommandInteraction):
        """Disable DM's responses to actions guild wide."""
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.dm_messages_disabled = True
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send(
            "I have disabled DM messages for this guild.", ephemeral=True
        )
        log.debug("Disabled DM messages for guild %s", interaction.guild_id)
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.GUILD_DM_DISABLE,
        )


def setup(bot):
    bot.add_cog(GuildConfigCog(bot))
