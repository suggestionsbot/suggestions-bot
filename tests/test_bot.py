from typing import cast

from causar import Causar

from suggestions import SuggestionsBot


async def test_cogs_loaded(causar: Causar):
    bot: SuggestionsBot = cast(SuggestionsBot, causar.bot)

    cog_names = [
        "Internal",
        "GuildConfigCog",
        "HelpGuildCog",
        "SuggestionsCog",
        "UserConfigCog",
        "ViewVotersCog",
    ]
    assert len(bot.cogs) == len(cog_names)
    for cog_name in cog_names:
        assert cog_name in bot.cogs
