from unittest.mock import AsyncMock

import pytest
from bot_base import NonExistentEntry

from suggestions.interaction_handler import InteractionHandler


async def test_send(interaction_handler: InteractionHandler):
    assert interaction_handler.has_sent_something is False

    with pytest.raises(ValueError):
        await interaction_handler.send()

    await interaction_handler.send("Hello world")
    assert interaction_handler.has_sent_something is True
    assert interaction_handler.interaction.send.assert_called_with(
        content="Hello world", ephemeral=True
    )

    interaction_handler.interaction = AsyncMock()
    await interaction_handler.send(
        "Hello world", embed="Embed", file="File", components=["Test"]
    )
    assert interaction_handler.interaction.send.assert_called_with(
        content="Hello world",
        ephemeral=True,
        embed="Embed",
        file="File",
        components=["Test"],
    )


async def test_new_handler(bot):
    assert bot.state.interaction_handlers.cache == {}
    handler: InteractionHandler = await InteractionHandler.new_handler(AsyncMock(), bot)
    assert bot.state.interaction_handlers.cache != {}
    assert handler.has_sent_something is False
    assert handler.is_deferred is True

    handler_2: InteractionHandler = await InteractionHandler.new_handler(
        AsyncMock(), bot, ephemeral=False, with_message=False
    )
    assert handler_2.ephemeral is False
    assert handler_2.with_message is False


async def test_fetch_handler(bot):
    application_id = 123456789
    with pytest.raises(NonExistentEntry):
        await InteractionHandler.fetch_handler(application_id, bot)

    mock = AsyncMock()
    mock.application_id = application_id
    await InteractionHandler.new_handler(mock, bot, with_message=False)
    handler: InteractionHandler = await InteractionHandler.fetch_handler(
        application_id, bot
    )
    assert handler.with_message is False
    assert handler.ephemeral is True
