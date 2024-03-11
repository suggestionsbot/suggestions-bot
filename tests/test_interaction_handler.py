from unittest.mock import AsyncMock, call

import pytest
from commons.caching import NonExistentEntry

from suggestions import SuggestionsBot
from suggestions.exceptions import ConflictingHandlerInformation
from suggestions.interaction_handler import InteractionHandler


async def test_send(interaction_handler: InteractionHandler):
    assert interaction_handler.has_sent_something is False

    with pytest.raises(ValueError):
        await interaction_handler.send()

    await interaction_handler.send("Hello world")
    assert interaction_handler.has_sent_something is True
    assert interaction_handler.interaction.send.call_count == 1
    assert interaction_handler.interaction.send.mock_calls == [
        call.send(ephemeral=True, content="Hello world")
    ]

    interaction_handler.interaction = AsyncMock()
    await interaction_handler.send(
        "Hello world", embed="Embed", file="File", components=["Test"]
    )
    assert interaction_handler.interaction.send.call_count == 1
    assert interaction_handler.interaction.send.mock_calls == [
        call.send(
            content="Hello world",
            ephemeral=True,
            embed="Embed",
            file="File",
            components=["Test"],
        ),
    ]


async def test_new_handler(bot: SuggestionsBot):
    mock = AsyncMock()
    mock.client = bot
    mock.id = 1
    assert bot.state.interaction_handlers.cache == {}
    handler: InteractionHandler = await InteractionHandler.new_handler(mock)
    assert bot.state.interaction_handlers.cache != {}
    assert handler.has_sent_something is False
    assert handler.is_deferred is True

    mock.id = 2
    handler_2: InteractionHandler = await InteractionHandler.new_handler(
        mock, ephemeral=False, with_message=False
    )
    assert handler_2.ephemeral is False
    assert handler_2.with_message is False


async def test_fetch_handler(bot: SuggestionsBot):
    application_id = 123456789
    r_1 = await InteractionHandler.fetch_handler(application_id, bot)
    assert r_1 is None

    mock = AsyncMock()
    mock.client = bot
    mock.id = application_id
    await InteractionHandler.new_handler(mock, with_message=False)
    handler: InteractionHandler = await InteractionHandler.fetch_handler(
        application_id, bot
    )
    assert handler.with_message is False
    assert handler.ephemeral is True


async def test_dual_raises(interaction_handler: InteractionHandler):
    with pytest.raises(ConflictingHandlerInformation):
        await interaction_handler.send("Test", translation_key="Blah")
