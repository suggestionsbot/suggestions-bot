from __future__ import annotations

from typing import TYPE_CHECKING

import disnake
from commons.caching import NonExistentEntry
from disnake.ext import commands
from logoo import Logger

from suggestions.objects import GuildConfig, Suggestion

if TYPE_CHECKING:
    from suggestions import State, SuggestionsBot

logger = Logger(__name__)


class BlacklistCog(commands.Cog):
    def __init__(self, bot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state

    @commands.slash_command()
    async def user(self, interaction: disnake.GuildCommandInteraction): ...

    @user.sub_command_group()
    async def blocklist(self, interaction: disnake.GuildCommandInteraction): ...

    @blocklist.sub_command()
    async def add(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(),
    ):
        """
        {{USER_BLOCKLIST_ADD}}

        Parameters
        ----------
        suggestion_id: str {{SUGGESTION_ID}}
        """
        await interaction.response.defer(ephemeral=True)
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, interaction.guild_id, self.state
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        if suggestion.suggestion_author_id in guild_config.blocked_users:
            return await interaction.send(
                "This user is already blocked from creating new suggestions.",
                ephemeral=True,
            )

        guild_config.blocked_users.add(suggestion.suggestion_author_id)
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send(
            "I have added that user to the blocklist. "
            "They will be unable to create suggestions in the future.",
            ephemeral=True,
        )
        logger.debug(
            "User %s added %s to the blocklist for guild %s",
            interaction.author.id,
            suggestion.suggestion_author_id,
            interaction.guild_id,
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
            },
        )

    @blocklist.sub_command()
    async def remove(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(default=None),
        user_id: str = commands.Param(default=None),
    ):
        """
        {{USER_BLOCKLIST_REMOVE}}

        Parameters
        ----------
        suggestion_id: str {{SUGGESTION_ID}}
        user_id: str {{USER_ID}}
        """
        await interaction.response.defer(ephemeral=True)
        if suggestion_id and user_id:
            return await interaction.send(
                "Providing suggestion_id and user_id at the same time is not supported.",
                ephemeral=True,
            )

        if user_id is None and suggestion_id is None:
            return await interaction.send(
                "Either a suggestion_id or user_id is required.",
                ephemeral=True,
            )

        if suggestion_id:
            suggestion: Suggestion = await Suggestion.from_id(
                suggestion_id, interaction.guild_id, self.state
            )
            user_id = suggestion.suggestion_author_id

        if user_id:
            try:
                user_id = int(user_id)
            except ValueError:
                return await interaction.send("User id is not valid.", ephemeral=True)

        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        guild_config.blocked_users.discard(user_id)
        await self.bot.db.guild_configs.upsert(guild_config, guild_config)
        await interaction.send("I have un-blocklisted that user for you.")
        logger.debug(
            "User %s removed %s from the blocklist for guild %s",
            interaction.author.id,
            user_id,
            interaction.guild_id,
            extra_metadata={
                "author_id": interaction.author.id,
                "guild_id": interaction.guild_id,
            },
        )

    @add.autocomplete("suggestion_id")
    @remove.autocomplete("suggestion_id")
    async def get_sid_for(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        user_input: str,
    ):
        try:
            values: list[str] = self.state.autocomplete_cache.get_entry(
                interaction.guild_id
            )
        except NonExistentEntry:
            values: list[str] = await self.state.populate_sid_cache(
                interaction.guild_id
            )
        else:
            if not values:
                logger.debug(
                    "Values was found, but empty in guild %s thus populating",
                    interaction.guild_id,
                    extra_metadata={"guild_id": interaction.guild_id},
                )
                values: list[str] = await self.state.populate_sid_cache(
                    interaction.guild_id
                )

        possible_choices = [v for v in values if user_input.lower() in v.lower()]

        if len(possible_choices) > 25:
            return []

        return possible_choices


def setup(bot):
    bot.add_cog(BlacklistCog(bot))
