from typing import overload, cast

from alaric import Document
from causar import Causar

from suggestions import SuggestionsBot


@overload
async def assert_stats_count(
    causar: Causar,
    *,
    member_id: int,
    guild_id: int,
    should_be_none: bool,
):
    ...


@overload
async def assert_stats_count(
    causar: Causar,
    *,
    member_id: int,
    guild_id: int,
    field: str,
    success_count: int = 0,
    failure_count: int = 0,
):
    ...


async def assert_stats_count(
    causar: Causar,
    *,
    member_id: int,
    guild_id: int,
    field: str = None,
    success_count: int = 0,
    failure_count: int = 0,
    should_be_none: bool = False,
):
    bot: SuggestionsBot = cast(SuggestionsBot, causar.bot)
    db: Document = bot.db.member_stats

    r_1 = await db.find({"member_id": member_id, "guild_id": guild_id})
    if should_be_none:
        assert r_1 is None
    else:
        assert r_1 is not None
        assert getattr(r_1, field).success_count == success_count
        assert getattr(r_1, field).failure_count == failure_count
