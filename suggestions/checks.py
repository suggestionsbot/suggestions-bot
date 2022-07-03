from __future__ import annotations

from typing import TYPE_CHECKING, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from disnake.ext import commands

from suggestions.exceptions import BetaOnly

if TYPE_CHECKING:
    from suggestions import SuggestionsBot
    from suggestions.objects import GuildConfig


def ensure_guild_has_beta():
    async def check(interaction: disnake.Interaction):
        if not interaction.guild_id:
            raise BetaOnly

        guild_id: int = interaction.guild_id
        suggestions: SuggestionsBot = interaction.client  # type: ignore
        if guild_id not in suggestions.state.guilds_with_beta:
            guild_exists: Optional[
                GuildConfig
            ] = await suggestions.db.guild_configs.find(
                AQ(EQ("guild_id", interaction.guild_id))
            )
            if bool(guild_exists):
                suggestions.state.guilds_with_beta.add(guild_id)

        if guild_id not in suggestions.state.guilds_with_beta:
            raise BetaOnly(interaction.guild_id)

        return True

    return commands.check(check)  # type: ignore
