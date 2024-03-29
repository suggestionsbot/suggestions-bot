from __future__ import annotations

from typing import cast, TYPE_CHECKING

import disnake
from commons.caching import NonExistentEntry

from suggestions.exceptions import ConflictingHandlerInformation

if TYPE_CHECKING:
    from suggestions import SuggestionsBot


class InteractionHandler:
    """A generic interaction response class to allow for easier
    testing and generification of interaction responses.

    This class also aims to move the custom add-ons out of
    the underlying disnake classes to help promote easier
    version upgrading in the future.
    """

    def __init__(
        self,
        interaction: (
            disnake.Interaction
            | disnake.GuildCommandInteraction
            | disnake.MessageInteraction
        ),
        ephemeral: bool,
        with_message: bool,
    ):
        self.interaction: (
            disnake.Interaction
            | disnake.GuildCommandInteraction
            | disnake.MessageInteraction
        ) = interaction
        self.ephemeral: bool = ephemeral
        self.with_message: bool = with_message
        self.is_deferred: bool = False

        # This is useful in error handling to stop
        # getting discord "Interaction didn't respond"
        # errors if we haven't yet sent anything
        self.has_sent_something: bool = False

    @property
    def bot(self) -> SuggestionsBot:
        return self.interaction.client  # type: ignore

    async def send(
        self,
        content: str | None = None,
        *,
        embed: disnake.Embed | None = None,
        file: disnake.File | None = None,
        components: list | None = None,
        translation_key: str | None = None,
    ):
        if translation_key is not None:
            if content is not None:
                raise ConflictingHandlerInformation

            content = self.bot.get_localized_string(translation_key, self.interaction)

        data = {}
        if content is not None:
            data["content"] = content
        if embed is not None:
            data["embed"] = embed
        if file is not None:
            data["file"] = file
        if components is not None:
            data["components"] = components

        if not data:
            raise ValueError("Expected at-least one value to send.")

        value = await self.interaction.send(ephemeral=self.ephemeral, **data)
        self.has_sent_something = True
        return value

    @classmethod
    async def new_handler(
        cls,
        interaction: disnake.Interaction,
        *,
        ephemeral: bool = True,
        with_message: bool = True,
        i_just_want_an_instance: bool = False,
    ) -> InteractionHandler:
        """Generate a new instance and defer the interaction."""
        instance = cls(interaction, ephemeral, with_message)

        if not i_just_want_an_instance:
            # TODO Remove this once BT-10 is resolved
            await interaction.response.defer(
                ephemeral=ephemeral, with_message=with_message
            )
            instance.is_deferred = True

        # Register this on the bot instance so other areas can
        # request the interaction handler, such as error handlers
        bot = interaction.client
        if TYPE_CHECKING:
            bot = cast(SuggestionsBot, bot)
        bot.state.interaction_handlers.add_entry(interaction.id, instance)

        return instance

    @classmethod
    async def fetch_handler(
        cls, application_id: int, bot: SuggestionsBot
    ) -> InteractionHandler | None:
        """Fetch a registered handler for the given interaction."""
        try:
            return bot.state.interaction_handlers.get_entry(application_id)
        except NonExistentEntry:
            return None
