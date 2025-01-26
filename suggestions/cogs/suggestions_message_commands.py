from __future__ import annotations

from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands
from logoo import Logger

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import Suggestion, GuildConfig
from suggestions.objects.suggestion import SuggestionState

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Stats

logger = Logger(__name__)


# noinspection DuplicatedCode
class SuggestionsMessageCommands(commands.Cog):
    """This cog allows users to manage suggestions via message commands"""

    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.message_command(
        name="Approve suggestion",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_logs_channel_or_keep_logs()
    async def approve_suggestion(self, interaction: disnake.GuildCommandInteraction):
        """Approve this suggestion"""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_message_id(
            message_id=interaction.target.id,
            channel_id=interaction.channel_id,
            state=self.state,
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=self.state,
            interaction=interaction,
            resolution_type=SuggestionState.approved,
            bot=self.bot,
        )
        await interaction.send(
            self.bot.get_locale("APPROVE_INNER_MESSAGE", interaction.locale).format(
                suggestion.suggestion_id
            ),
            ephemeral=True,
        )
        logger.debug(
            "User %s approved suggestion %s in guild %s by message command",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
            extra_metadata={
                "author_id": interaction.author.id,
                "suggestion_id": suggestion.suggestion_id,
                "guild_id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.APPROVE_BY_MESSAGE_COMMAND,
        )

    @commands.message_command(
        name="Reject suggestion",
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    @checks.ensure_guild_has_logs_channel_or_keep_logs()
    async def reject_suggestion(self, interaction: disnake.GuildCommandInteraction):
        """Reject this suggestion"""
        await interaction.response.defer(ephemeral=True, with_message=True)
        suggestion: Suggestion = await Suggestion.from_message_id(
            message_id=interaction.target.id,
            channel_id=interaction.channel_id,
            state=self.state,
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        await suggestion.resolve(
            guild_config=guild_config,
            state=self.state,
            interaction=interaction,
            resolution_type=SuggestionState.rejected,
            bot=self.bot,
        )
        await interaction.send(
            self.bot.get_locale("REJECT_INNER_MESSAGE", interaction.locale).format(
                suggestion.suggestion_id
            ),
            ephemeral=True,
        )
        logger.debug(
            "User %s rejected suggestion %s in guild %s by message command",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
            extra_metadata={
                "author_id": interaction.author.id,
                "suggestion_id": suggestion.suggestion_id,
                "guild_id": interaction.guild_id,
            },
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.REJECT_BY_MESSAGE_COMMAND,
        )


def setup(bot):
    bot.add_cog(SuggestionsMessageCommands(bot))
