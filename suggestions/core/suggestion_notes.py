import disnake
from disnake import Embed
from logoo import Logger

from suggestions import Colors
from suggestions.core import BaseCore
from suggestions.objects import Suggestion, UserConfig, GuildConfig
from suggestions.interaction_handler import InteractionHandler

logger: Logger = Logger(__name__)


class SuggestionsNotesCore(BaseCore):
    async def modify_note_on_suggestions(
        self, ih: InteractionHandler, suggestion_id: str, note: str | None
    ):
        """Given a note, override the current note for a suggestion.

        This one method handles both adding and removing notes.
        """
        suggestion: Suggestion = await Suggestion.from_id(
            suggestion_id, guild_id=ih.interaction.guild_id, state=ih.bot.state
        )
        suggestion.note = note
        suggestion.note_added_by = (
            ih.interaction.author.id if note is not None else None
        )
        await ih.bot.db.suggestions.upsert(suggestion, suggestion)

        # We should now update the suggestions message
        await suggestion.edit_suggestion_message(ih)

        # We should tell the user a change has occurred
        suggestion_author_id: int = suggestion.suggestion_author_id
        user_config: UserConfig = await UserConfig.from_id(
            suggestion_author_id, ih.bot.state
        )
        if user_config.dm_messages_disabled:
            logger.debug(
                "Not dm'ing %s for a note changed on suggestion %s as they have dm's disabled",
                suggestion_author_id,
                suggestion_id,
                extra_metadata={
                    "guild_id": ih.interaction.guild_id,
                    "suggestion_id": suggestion_id,
                    "author_id": suggestion_author_id,
                },
            )
            return

        guild_config: GuildConfig = await GuildConfig.from_id(
            ih.interaction.guild_id, ih.bot.state
        )
        if guild_config.dm_messages_disabled:
            logger.debug(
                "Not dm'ing %s for a note changed on suggestion %s as the guilds has dm's disabled",
                ih.interaction.author.id,
                suggestion_id,
                extra_metadata={
                    "guild_id": ih.interaction.guild_id,
                    "suggestion_id": suggestion_id,
                },
            )
            return

        jump_url = (
            f"https://discord.com/channels/{ih.interaction.guild_id}/"
            f"{suggestion.channel_id}/{suggestion.message_id}"
        )
        embed: Embed = Embed(
            description=ih.bot.get_localized_string(
                "NOTE_INNER_CHANGE_MADE_DESCRIPTION",
                ih,
                guild_config=guild_config,
                extras={"JUMP": jump_url},
            ),
            colour=Colors.embed_color,
            timestamp=ih.bot.state.now,
        )
        embed.set_footer(
            text=ih.bot.get_localized_string(
                "NOTE_INNER_CHANGE_MADE_FOOTER",
                ih,
                guild_config=guild_config,
                extras={"GUILD_ID": ih.interaction.guild_id, "SID": suggestion_id},
            )
        )

        # Guild is always set here because icon_url populates it
        icon_url = await self.bot.try_fetch_icon_url(ih.interaction.guild_id)
        guild = ih.bot.state.guild_cache.get_entry(ih.interaction.guild_id)
        embed.set_author(name=guild.name, icon_url=icon_url)
        user: disnake.User = await ih.bot.fetch_user(suggestion_author_id)
        await user.send(embed=embed)

        await ih.send(ih.bot.get_localized_string("NOTE_INNER_RESPONSE", ih))
