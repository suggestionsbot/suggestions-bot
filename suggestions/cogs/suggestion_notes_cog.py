import cooldowns
import disnake
from commons.caching import NonExistentEntry
from disnake.ext import commands
from logoo import Logger

from suggestions.cooldown_bucket import InteractionBucket
from suggestions.core import SuggestionsNotesCore
from suggestions.interaction_handler import InteractionHandler

logger: Logger = Logger(__name__)


class SuggestionNotesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.state = bot.state
        self.core: SuggestionsNotesCore = SuggestionsNotesCore(bot)

    @commands.slash_command(
        default_member_permissions=disnake.Permissions(manage_guild=True),
    )
    @commands.contexts(guild=True)
    @cooldowns.cooldown(1, 3, bucket=InteractionBucket.author)
    async def notes(self, interaction: disnake.GuildCommandInteraction):
        """{{NOTES}}"""
        pass

    @notes.sub_command()
    async def add(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(),
        note: str = commands.Param(),
    ):
        """
        {{NOTES_ADD}}

        Parameters
        ----------
        suggestion_id: str {{NOTES_ADD_ARG_SUGGESTION_ID}}
        note: str {{NOTES_ADD_ARG_NOTE}}
        """
        note: str = note.replace("\\n", "\n")
        await self.core.modify_note_on_suggestions(
            await InteractionHandler.new_handler(interaction), suggestion_id, note
        )

    @notes.sub_command()
    async def remove(
        self,
        interaction: disnake.GuildCommandInteraction,
        suggestion_id: str = commands.Param(),
    ):
        """
        {{NOTES_REMOVE}}

        Parameters
        ----------
        suggestion_id: str {{NOTES_REMOVE_ARG_SUGGESTION_ID}}
        """
        await self.core.modify_note_on_suggestions(
            await InteractionHandler.new_handler(interaction), suggestion_id, None
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
                    f"Values was found, but empty in guild {interaction.guild_id} thus populating",
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
    bot.add_cog(SuggestionNotesCog(bot))
