from __future__ import annotations

import datetime
import io
import logging
from typing import TYPE_CHECKING, Optional

import disnake
from alaric import AQ
from alaric.comparison import EQ
from disnake.ext import commands
from disnake.utils import format_dt
from humanize import naturaldate

from suggestions import ErrorCode
from suggestions.objects import Error

if TYPE_CHECKING:
    from suggestions import SuggestionsBot, State

logger = logging.getLogger(__name__)


class HelpGuildCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str) -> None:
        self.bot.stats.increment_event_type(event_type)

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    @commands.contexts(guild=True)
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
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    @commands.contexts(guild=True)
    async def instance_info(
        self,
        interaction: disnake.GuildCommandInteraction,
        guild_id: str = commands.Param(
            description="The ID of the guild you want info on."
        ),
    ):
        """Retrieve information about what instance a given guild sees. This is currently wrong."""
        await interaction.send(
            ephemeral=True, content="This command currently does not work correctly."
        )
        return

        guild_id = int(guild_id)
        shard_id = self.bot.get_shard_id(guild_id)
        cluster_id = (
            1
            if shard_id < 10
            else (
                2
                if shard_id < 20
                else (
                    3
                    if shard_id < 30
                    else 4 if shard_id < 40 else 5 if shard_id < 50 else 6
                )
            )
        )

        await interaction.send(
            f"Guild `{guild_id}` should be in cluster `{cluster_id}` with the specific shard `{shard_id}`",
            ephemeral=True,
        )

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    @commands.contexts(guild=True)
    async def error_information(
        self,
        interaction: disnake.GuildCommandInteraction,
        error_id: str = commands.Param(description="The error id"),
    ):
        """Retrieve information about a given error."""
        error: Optional[Error] = await self.bot.db.error_tracking.find(
            AQ(EQ("_id", error_id))
        )
        if not error:
            return await interaction.send(
                "No error exists with that ID.", ephemeral=True
            )

        embed = disnake.Embed(
            colour=self.bot.colors.embed_color,
            timestamp=self.bot.state.now,
            title=f"Information for error {error.id}",
            description=f"**Command name**: `{error.command_name}`\n\n"
            f"**Shard ID**: `{error.shard_id}` | **Cluster ID**: `{error.cluster_id}`\n"
            f"**User ID**: `{error.user_id}` | **Guild ID**: `{error.guild_id}`\n\n"
            f"**Error**: `{error.error}`\n"
            f"**Error occurred**: `{naturaldate(error.created_at)}` ({format_dt(error.created_at, style='F')})",
        )
        await interaction.send(
            embed=embed,
            ephemeral=True,
            file=disnake.File(io.StringIO(error.traceback), filename="traceback.txt"),
        )


def setup(bot):
    bot.add_cog(HelpGuildCog(bot))
