from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import cooldowns
import disnake
from disnake.ext import commands

from suggestions import checks
from suggestions.cooldown_bucket import InteractionBucket
from suggestions.objects import Suggestion, GuildConfig

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State, Stats

log = logging.getLogger(__name__)


# noinspection DuplicatedCode
class SuggestionsMessageCommands(commands.Cog):
    """This cog allows users to manage suggestions via message commands"""

    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.stats: Stats = self.bot.stats

    @commands.message_command(name="Approve suggestion")
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
        await suggestion.mark_approved_by(self.state, interaction.user.id)
        await suggestion.archive_thread_if_required(
            bot=self.bot, guild_config=guild_config, locale=interaction.locale
        )
        await suggestion.edit_message_after_finalization(
            state=self.state,
            bot=self.bot,
            interaction=interaction,
            guild_config=guild_config,
        )
        await interaction.send(
            self.bot.get_locale("APPROVE_INNER_MESSAGE", interaction.locale).format(
                suggestion.suggestion_id
            ),
            ephemeral=True,
        )
        log.debug(
            "User %s approved suggestion %s in guild %s by message command",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.APPROVE_BY_MESSAGE_COMMAND,
        )

    @commands.message_command(name="Reject suggestion")
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
        await suggestion.mark_rejected_by(self.state, interaction.user.id)
        await suggestion.archive_thread_if_required(
            bot=self.bot, guild_config=guild_config, locale=interaction.locale
        )
        await suggestion.edit_message_after_finalization(
            state=self.state,
            bot=self.bot,
            interaction=interaction,
            guild_config=guild_config,
        )
        await interaction.send(
            self.bot.get_locale("REJECT_INNER_MESSAGE", interaction.locale).format(
                suggestion.suggestion_id
            ),
            ephemeral=True,
        )
        log.debug(
            "User %s rejected suggestion %s in guild %s by message command",
            interaction.author.id,
            suggestion.suggestion_id,
            interaction.guild_id,
        )
        await self.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            self.stats.type.REJECT_BY_MESSAGE_COMMAND,
        )


def setup(bot):
    bot.add_cog(SuggestionsMessageCommands(bot))
