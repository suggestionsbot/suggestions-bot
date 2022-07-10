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

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
        guild_ids=[601219766258106399, 737166408525283348],
    )
    @commands.guild_only()
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


def setup(bot):
    bot.add_cog(HelpGuildCog(bot))
