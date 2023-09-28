from __future__ import annotations

from typing import TYPE_CHECKING

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
        self, interaction: disnake.Interaction, ephemeral: bool, with_message: bool
    ):
        self.interaction: disnake.Interaction = interaction
        self.ephemeral: bool = ephemeral
        self.with_message: bool = with_message
        self.is_deferred: bool = False

        # This is useful in error handling to stop
        # getting discord "Interaction didn't respond"
        # errors if we haven't yet sent anything
        self.has_sent_something: bool = False

    async def send(
        self,
        content: str | None = None,
        *,
        embed: disnake.Embed | None = None,
        file: disnake.File | None = None,
        components: list | None = None,
    ):
        data = {}
        if content is not None:
            data["content"] = content
        if embed is not None:
            data["embed"] = embed
        if file is not None:
            data["file"] = file
        if components is not None:
            data["components"] = components

        await self.interaction.send(ephemeral=self.ephemeral, **data)
        self.has_sent_something = True

    @classmethod
    async def new_handler(
        cls,
        interaction: disnake.Interaction,
        bot: SuggestionsBot,
        *,
        ephemeral: bool = True,
        with_message: bool = True,
    ) -> InteractionHandler:
        """Generate a new instance and defer the interaction."""
        instance = cls(interaction, ephemeral, with_message)
        await interaction.response.defer(ephemeral=ephemeral, with_message=with_message)
        instance.is_deferred = True

        # Register this on the bot instance so other areas can
        # request the interaction handler, such as error handlers
        bot.state.interaction_handlers.add_entry(interaction.application_id, instance)

        return instance

    @classmethod
    async def fetch_handler(
        cls, application_id: int, bot: SuggestionsBot
    ) -> InteractionHandler:
        """Fetch a registered handler for the given interaction."""
        return bot.state.interaction_handlers.get_entry(application_id)
