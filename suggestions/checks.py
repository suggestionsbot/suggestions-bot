from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from disnake.ext import commands

from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
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
            suggestions.state.guild_configs[guild_id] = guild_exists

    if guild_id not in suggestions.state.guild_configs:
        return None

    return suggestions.state.guild_configs[guild_id]


def ensure_guild_has_suggestions_channel():
    async def check(interaction: disnake.Interaction):
        guild_config: Optional[GuildConfig] = await fetch_guild_config(interaction)

        if not bool(guild_config):
            raise MissingSuggestionsChannel

        if not guild_config.suggestions_channel_id:
            raise MissingSuggestionsChannel

        return True

    return commands.check(check)  # type: ignore


def ensure_guild_has_logs_channel():
    async def check(interaction: disnake.Interaction):
        guild_config: Optional[GuildConfig] = await fetch_guild_config(interaction)

        if not bool(guild_config):
            raise MissingLogsChannel

        if not guild_config.log_channel_id:
            raise MissingLogsChannel

        return True

    return commands.check(check)  # type: ignore
