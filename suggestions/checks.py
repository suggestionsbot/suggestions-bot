from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from disnake.ext import commands

from suggestions.exceptions import (
    MissingSuggestionsChannel,
    MissingLogsChannel,
    BlocklistedUser,
)

if TYPE_CHECKING:
    from suggestions import SuggestionsBot
    from suggestions.objects import GuildConfig


async def fetch_guild_config(interaction: disnake.Interaction) -> Optional[GuildConfig]:
    guild_id: int = interaction.guild_id
    suggestions: SuggestionsBot = interaction.client  # type: ignore
    if guild_id not in suggestions.state.guild_configs:
        guild_exists: Optional[GuildConfig] = await suggestions.db.guild_configs.find(
            AQ(EQ("_id", interaction.guild_id))
        )
        if bool(guild_exists):
            suggestions.state.refresh_guild_config(guild_exists)

    if guild_id not in suggestions.state.guild_configs:
        return None

    return suggestions.state.guild_configs.get_entry(guild_id)


def ensure_guild_has_suggestions_channel():
    async def check(interaction: disnake.Interaction):
        guild_config: Optional[GuildConfig] = await fetch_guild_config(interaction)

        if not bool(guild_config):
            raise MissingSuggestionsChannel

        if not guild_config.suggestions_channel_id:
            raise MissingSuggestionsChannel

        return True

    return commands.check(check)  # type: ignore


def ensure_guild_has_logs_channel_or_keep_logs():
    async def check(interaction: disnake.Interaction):
        guild_config: Optional[GuildConfig] = await fetch_guild_config(interaction)

        if not bool(guild_config):
            raise MissingLogsChannel

        if not guild_config.log_channel_id and not guild_config.keep_logs:
            raise MissingLogsChannel

        return True

    return commands.check(check)  # type: ignore


def ensure_user_is_not_blocklisted():
    async def check(interaction: disnake.Interaction):
        guild_config: Optional[GuildConfig] = await fetch_guild_config(interaction)

        if not bool(guild_config):
            return True

        if interaction.author.id in guild_config.blocked_users:
            raise BlocklistedUser

        return True

    return commands.check(check)  # type: ignore


def ensure_guild_has_subscription():
    async def check(interaction: disnake.Interaction):
        entitlements: list[disnake.Entitlement] = [
            e
            for e in interaction.entitlements
            if e.is_active() and e.sku_id == interaction.bot.guild_subscription_sku_id
        ]
        if entitlements is None:
            return await interaction.response.require_premium()

        return True

    return commands.check(check)  # type: ignore
