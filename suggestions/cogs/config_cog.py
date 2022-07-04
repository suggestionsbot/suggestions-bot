from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from disnake.ext import commands

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


def setup(bot):
    bot.add_cog(ConfigCog(bot))
