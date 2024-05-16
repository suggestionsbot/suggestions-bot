from __future__ import annotations

from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands
from logoo import Logger

from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import UserConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Stats

logger = Logger(__name__)


class UserConfigCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

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
        logger.debug(
            "Enabled DM messages for member %s",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
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
        logger.debug(
            "Disabled DM messages for member %s",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
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
        logger.debug(
            "User %s viewed their DM configuration",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_DM_VIEW,
        )

    @commands.slash_command()
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def user_config(self, interaction: disnake.CommandInteraction):
        pass

    @user_config.sub_command_group()
    async def ping_on_thread_creation(self, interaction: disnake.CommandInteraction):
        pass

    @ping_on_thread_creation.sub_command(name="enable")
    async def ping_on_thread_creation_enable(
        self, interaction: disnake.CommandInteraction
    ):
        """Enable pings when a thread is created on a suggestion."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        user_config.ping_on_thread_creation = True
        await self.bot.db.user_configs.upsert(user_config, user_config)
        await interaction.send(
            "I have enabled pings on thread creation for you.", ephemeral=True
        )
        logger.debug(
            "Enabled pings on thread creation for member %s",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_PING_ON_THREAD_CREATE_ENABLE,
        )

    @ping_on_thread_creation.sub_command(name="disable")
    async def ping_on_thread_creation_disable(
        self, interaction: disnake.CommandInteraction
    ):
        """Disable pings when a thread is created on a suggestion."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        user_config.ping_on_thread_creation = False
        await self.bot.db.user_configs.upsert(user_config, user_config)
        await interaction.send(
            "I have disabled pings on thread creation for you.", ephemeral=True
        )
        logger.debug(
            "Disabled pings on thread creation for member %s",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_PING_ON_THREAD_CREATE_DISABLE,
        )

    @ping_on_thread_creation.sub_command(name="view")
    async def ping_on_thread_creation_view(
        self, interaction: disnake.CommandInteraction
    ):
        """View your current ping configuration."""
        user_config: UserConfig = await UserConfig.from_id(
            interaction.author.id, self.state
        )
        text = "will" if user_config.ping_on_thread_creation else "will not"
        await interaction.send(
            f"I {text} ping you on when a new thread is created for a suggestion.",
            ephemeral=True,
        )
        logger.debug(
            "User %s viewed their ping configuration",
            interaction.author.id,
            extra_metadata={"author_id": interaction.author.id},
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.MEMBER_PING_ON_THREAD_CREATE_VIEW,
        )


def setup(bot):
    bot.add_cog(UserConfigCog(bot))
