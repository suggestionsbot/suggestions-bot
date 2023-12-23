from __future__ import annotations

import datetime
import io
import logging
import os
import typing
from typing import TYPE_CHECKING, Optional

import aiohttp
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

log = logging.getLogger(__name__)


class HelpGuildCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state

    @commands.Cog.listener()
    async def on_socket_event_type(self, event_type: str) -> None:
        self.bot.stats.increment_event_type(event_type)

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

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
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

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(kick_members=True),
        guild_ids=[601219766258106399, 737166408525283348],
        name="bot_status",
    )
    async def show_bot_status(
        self,
        interaction: disnake.GuildCommandInteraction,
    ):
        """See bot status information"""
        await interaction.response.defer(ephemeral=True)

        red_circle = "🔴"
        green_circle = "🟢"
        url = (
            "https://garven.suggestions.gg/cluster/status"
            if self.bot.is_prod
            else "https://garven.dev.suggestions.gg/cluster/status"
        )

        embed = disnake.Embed(
            timestamp=datetime.datetime.utcnow(),
            title="Bot infrastructure status",
        )
        down_shards: list[str] = [str(i) for i in range(53)]
        down_clusters: list[str] = [str(i) for i in range(1, 7)]
        avg_bot_latency: list[float] = []
        async with aiohttp.ClientSession(
            headers={"X-API-KEY": os.environ["GARVEN_API_KEY"]}
        ) as session:
            async with session.get(url) as resp:
                data: dict[str, dict | bool] = await resp.json()
                if resp.status != 200:
                    log.error("Something went wrong: %s", data)

        if data.pop("partial_response") is not None:
            embed.set_footer(text="Partial response")

        for cluster_id, v in data["clusters"].items():
            cluster_is_up = v.pop("cluster_is_up")
            if cluster_is_up:
                down_clusters.remove(str(cluster_id))

            for shard_id, d in v["shards"].items():
                latency = d["latency"]
                is_currently_up = d["is_currently_up"]
                if is_currently_up:
                    down_shards.remove(str(shard_id))

                if latency:
                    avg_bot_latency.append(latency)

        bot_latency = (sum(avg_bot_latency) / len(avg_bot_latency)) * 1000

        def calculate_extra(var) -> str:
            if not var:
                return ""

            ai = f"\n{red_circle} "
            ai += "("
            for i in var:
                ai += f"`{i}`, "

            ai = ai.rstrip(", ")
            ai += ")"
            return ai

        additional_shard_info = calculate_extra(down_shards)
        additional_cluster_info = calculate_extra(down_clusters)

        embed.description = (
            f"{green_circle} **Shards:** `{53 - len(down_shards)}`\n"
            f"{red_circle} **Shards:** `{len(down_shards)}`{additional_shard_info}\n\n"
            f"{green_circle} **Clusters:** `{6 - len(down_clusters)}`\n"
            f"{red_circle} **Clusters:** `{len(down_clusters)}`{additional_cluster_info}\n\n"
            f"Average bot latency: `{round(bot_latency, 3)}ms`"
        )
        await interaction.send(ephemeral=True, embed=embed)


def setup(bot):
    bot.add_cog(HelpGuildCog(bot))
