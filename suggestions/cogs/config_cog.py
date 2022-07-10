from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import disnake
from disnake.ext import commands

from suggestions import checks
from suggestions.exceptions import InvalidGuildConfigOption
from suggestions.objects import GuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class ConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @checks.ensure_guild_has_beta()
    @commands.guild_only()
    async def config(self, interaction: disnake.GuildCommandInteraction):
        pass

    @config.sub_command()
    @commands.guild_only()
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
            "User %s modified suggestions channel in guild %s",
            interaction.author.id,
            interaction.guild_id,
        )

    @config.sub_command()
    @commands.guild_only()
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
            "User %s modified logs channel in guild %s",
            interaction.author.id,
            interaction.guild_id,
        )

    @config.sub_command()
    @commands.guild_only()
    async def get(
        self,
        interaction: disnake.GuildCommandInteraction,
        config=commands.Param(
            description="The optional configuration to view",
            choices=["Log channel", "Suggestions channel"],
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

        else:
            raise InvalidGuildConfigOption

        await interaction.send(embed=embed, ephemeral=True)
        log.debug(
            "User %s viewed the %s config in guild %s",
            interaction.author.id,
            config,
            interaction.guild_id,
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
        guild = await self.bot.fetch_guild(interaction.guild_id)
        embed: disnake.Embed = disnake.Embed(
            description=f"Configuration for {guild.name}\n\nSuggestions channel: {suggestions_channel}\n"
            f"Log channel: {log_channel}",
            color=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
        ).set_author(name=guild.name, icon_url=guild.icon.url)
        await interaction.send(embed=embed, ephemeral=True)
        log.debug(
            "User %s viewed the global config in guild %s",
            interaction.author.id,
            interaction.guild_id,
        )


def setup(bot):
    bot.add_cog(ConfigCog(bot))
