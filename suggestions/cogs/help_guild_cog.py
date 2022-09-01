from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import disnake
from disnake.ext import commands

from suggestions import ErrorCode

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class HelpGuildCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    async def error_code(
        self,
        interaction: disnake.GuildCommandInteraction,
        code: int = commands.Param(description="The specific error code"),
    ):
        """Retrieve information about a given error code."""
        try:
            code: ErrorCode = ErrorCode.from_value(code)
        except ValueError:
            await interaction.send(
                embed=self.bot.error_embed(
                    "Command failed", f"No error code exists for `{code}`"
                ),
                ephemeral=True,
            )
            return

        await interaction.send(
            f"Error code `{code.value}` corresponds to {code.name}", ephemeral=True
        )

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    async def instance_info(
        self,
        interaction: disnake.GuildCommandInteraction,
        guild_id: str = commands.Param(
            description="The ID of the guild you want info on."
        ),
    ):
        """Retrieve information about what instance a given guild sees."""
        guild_id = int(guild_id)
        shard_id = self.bot.get_shard_id(guild_id)
        cluster_id = (
            1
            if shard_id < 10
            else 2
            if shard_id < 20
            else 3
            if shard_id < 30
            else 4
            if shard_id < 40
            else 5
            if shard_id < 50
            else 6
        )

        await interaction.send(
            f"Guild `{guild_id}` should be in cluster `{cluster_id}` with the specific shard `{shard_id}`",
            ephemeral=True,
        )


def setup(bot):
    bot.add_cog(HelpGuildCog(bot))
