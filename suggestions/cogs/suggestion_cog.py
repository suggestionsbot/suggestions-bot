from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

import disnake
from bot_base import NonExistentEntry
from bot_base.wraps import WrappedChannel
from disnake import TextInputStyle
from disnake.ext import commands

from suggestions import checks, ErrorCode
from suggestions.objects import Suggestion, GuildConfig

if TYPE_CHECKING:
    from alaric import Document
    from suggestions import SuggestionsBot, State

log = logging.getLogger(__name__)


class SuggestionsCog(commands.Cog):
    def __init__(self, bot: SuggestionsBot):
        self.bot: SuggestionsBot = bot
        self.state: State = self.bot.state
        self.suggestions_db: Document = self.bot.db.suggestions

    @commands.Cog.listener()
    async def on_ready(self):
        log.info(f"{self.__class__.__name__}: Ready")

    @commands.slash_command(dm_permission=False)
    @checks.ensure_guild_has_suggestions_channel()
    @checks.ensure_guild_has_beta()
    @commands.guild_only()
    async def suggest(self, interaction: disnake.GuildCommandInteraction):
        """Create a new suggestion."""
        custom_id = f"suggestions_create_modal:{interaction.id}"
        await interaction.response.send_modal(
            custom_id=custom_id,
            title="Suggest something",
            components=[
                disnake.ui.TextInput(
                    label="Suggestion",
                    placeholder="Placeholder suggestions",
                    custom_id="actual_suggestion",
                    max_length=1000,
                    style=TextInputStyle.paragraph,
                ),
            ],
        )

        guild: disnake.Guild = await self.bot.fetch_guild(interaction.guild_id)

        modal_inter: disnake.ModalInteraction = await self.bot.wait_for(
            "modal_submit",
            check=lambda i: i.custom_id == custom_id
            and i.author.id == interaction.author.id,
            timeout=60,
        )
        suggestion: Suggestion = await Suggestion.new(
            suggestion=modal_inter.text_values["actual_suggestion"],
            guild_id=interaction.guild_id,
            state=self.state,
            author_id=interaction.author.id,
        )
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        channel: WrappedChannel = await self.bot.get_or_fetch_channel(
            guild_config.suggestions_channel_id
        )
        message: disnake.Message = await channel.send(
            embed=await suggestion.as_embed(self.bot)
        )
        suggestion.message_id = message.id
        suggestion.channel_id = channel.id
        await self.state.suggestions_db.upsert(suggestion, suggestion)

        try:
            await message.add_reaction(self.bot.suggestion_emojis.default_up_vote())
            await message.add_reaction(self.bot.suggestion_emojis.default_down_vote())
        except disnake.Forbidden as e:
            await self.suggestions_db.delete(suggestion.as_filter())
            try:
                await message.delete()
            except disnake.Forbidden:
                raise commands.MissingPermissions(
                    missing_permissions=["Add Reactions", "Manage Messages"]
                )
            raise commands.MissingPermissions(missing_permissions=["Add Reactions"])
        except disnake.HTTPException:
            await self.suggestions_db.delete(suggestion.as_filter())
            try:
                await message.delete()
            except disnake.Forbidden:
                raise commands.MissingPermissions(
                    missing_permissions=["Use External Emojis", "Manage Messages"]
                )
            raise commands.MissingPermissions(
                missing_permissions=["Use External Emojis"]
            )

        await modal_inter.send("Thanks for your suggestion!", ephemeral=True)

        try:
            embed: disnake.Embed = disnake.Embed(
                description=f"Hey, {interaction.author.mention}. Your suggestion has been sent "
                f"to {channel.mention} to be voted on!\n\n"
                f"Please wait until it gets approved or rejected by a staff member.\n\n"
                f"Your suggestion ID (sID) for reference is **{suggestion.suggestion_id}**.",
                timestamp=self.state.now,
                color=self.bot.colors.embed_color,
            )
            embed.set_author(
                name=guild.name,
                icon_url=guild.icon.url,
            )
            embed.set_footer(
                text=f"Guild ID: {interaction.guild_id} | sID: {suggestion.suggestion_id}"
            )
            await interaction.author.send(embed=embed)
        except disnake.HTTPException as e:
            log.debug(
                "Failed to DM %s regarding there suggestion",
                interaction.author.id,
            )
            raise e

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @checks.ensure_guild_has_logs_channel()
    @checks.ensure_guild_has_beta()
    @commands.guild_only()
    async def approve(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(description="The sID you wish to approve"),
        response: Optional[str] = commands.Param(
            description="An optional response to add to the suggestion", default=None
        ),
    ):
        """Approve a suggestion."""
        suggestion: Suggestion = await Suggestion.from_id(suggestion_id, self.state)
        await suggestion.try_delete(self.bot, interaction)
        await suggestion.mark_approved_by(self.state, interaction.author.id, response)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        channel: WrappedChannel = await self.bot.get_or_fetch_channel(
            guild_config.log_channel_id
        )
        message: disnake.Message = await channel.send(
            embed=await suggestion.as_embed(self.bot)
        )
        suggestion.message_id = message.id
        suggestion.channel_id = channel.id
        await self.state.suggestions_db.upsert(suggestion, suggestion)
        await interaction.send(f"You have approved **{suggestion_id}**", ephemeral=True)

    @approve.autocomplete("suggestion_id")
    async def approve_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

    @commands.slash_command(
        dm_permission=False,
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @checks.ensure_guild_has_logs_channel()
    @checks.ensure_guild_has_beta()
    @commands.guild_only()
    async def reject(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(description="The sID you wish to approve"),
        response: Optional[str] = commands.Param(
            description="An optional response to add to the suggestion", default=None
        ),
    ):
        """Reject a suggestion."""
        suggestion: Suggestion = await Suggestion.from_id(suggestion_id, self.state)
        await suggestion.try_delete(self.bot, interaction)
        await suggestion.mark_rejected_by(self.state, interaction.author.id, response)
        guild_config: GuildConfig = await GuildConfig.from_id(
            interaction.guild_id, self.state
        )
        channel: WrappedChannel = await self.bot.get_or_fetch_channel(
            guild_config.log_channel_id
        )
        message: disnake.Message = await channel.send(
            embed=await suggestion.as_embed(self.bot)
        )
        suggestion.message_id = message.id
        suggestion.channel_id = channel.id
        await self.state.suggestions_db.upsert(suggestion, suggestion)
        await interaction.send(f"You have rejected **{suggestion_id}**", ephemeral=True)

    @reject.autocomplete("suggestion_id")
    async def approve_suggestion_id_autocomplete(self, inter, user_input):
        return await self.get_sid_for(inter, user_input)

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

        possible_choices = [v for v in values if user_input.lower() in v.lower()]

        if len(possible_choices) > 25:
            return []

        return possible_choices


def setup(bot):
    bot.add_cog(SuggestionsCog(bot))
