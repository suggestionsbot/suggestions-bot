from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands

from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import UserConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Stats

log = logging.getLogger(__name__)


class UserConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    @commands.slash_command()
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def dm(self, interaction: disnake.CommandInteraction):
        pass

    @dm.sub_command()
    async def enable(self, interaction: disnake.CommandInteraction):
        """Enable DM messages for suggestion actions."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        user_config.dm_messages_disabled = False
        await self.bot.db.user_configs.upsert(user_config, user_config)
        await interaction.send("I have enabled DM messages for you.", ephemeral=True)
        log.debug("Enabled DM messages for member %s", interaction.author.id)
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_DM_ENABLE,
        )

    @dm.sub_command()
    async def disable(self, interaction: disnake.CommandInteraction):
        """Disable DM messages for suggestion actions."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        user_config.dm_messages_disabled = True
        await self.bot.db.user_configs.upsert(user_config, user_config)
        await interaction.send("I have disabled DM messages for you.", ephemeral=True)
        log.debug("Disabled DM messages for member %s", interaction.author.id)
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_DM_DISABLE,
        )

    @dm.sub_command()
    async def view(self, interaction: disnake.CommandInteraction):
        """View your current DM configuration."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        text = "will not" if user_config.dm_messages_disabled else "will"
        await interaction.send(
            f"I {text} DM you on actions such as suggest.", ephemeral=True
        )
        log.debug("User %s viewed there DM configuration", interaction.author.id)
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_DM_VIEW,
        )


def setup(bot):
    bot.add_cog(UserConfigCog(bot))
