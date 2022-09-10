import os
from unittest.mock import AsyncMock

import disnake
import pytest

from causar import Causar

import suggestions


@pytest.fixture
async def causar(monkeypatch) -> Causar:
    if "suggestions" not in [x[0] for x in os.walk(".")]:
        monkeypatch.chdir("..")

    monkeypatch.setenv("IS_TEST_CASE", "1")

    # Mock these to avoid Task's complaining after tests end
    monkeypatch.setattr(
        "disnake.ext.commands.common_bot_base.CommonBotBase._fill_owners",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "disnake.ext.commands.interaction_bot_base.InteractionBotBase._prepare_application_commands",
        AsyncMock(),
    )

    bot = await suggestions.create_bot()
    await bot.load_cogs()
    return Causar(bot)  # type: ignore
