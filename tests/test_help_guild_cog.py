from typing import cast, NamedTuple

import disnake
from causar import Causar, Injection, TransactionTypes
from causar import transactions as t

from suggestions import SuggestionsBot


async def test_error_code(causar: Causar):
    injection: Injection = await causar.generate_injection("error_code")
    injection.set_kwargs(code=1)

    await causar.run_command(injection)

    assert len(injection.transactions) == 1

    transaction: t.InteractionResponseSent = injection.transactions[0]
    assert transaction.type is TransactionTypes.INTERACTION_RESPONSE_SENT
    assert transaction.ephemeral is True
    assert (
        transaction.content
        == "Error code `1` corresponds to SUGGESTION_MESSAGE_DELETED"
    )


async def test_incorrect_error_code(causar: Causar):
    bot: SuggestionsBot = cast(SuggestionsBot, causar.bot)
    injection: Injection = await causar.generate_injection("error_code")
    injection.set_kwargs(code=-1)

    await causar.run_command(injection)

    assert len(injection.transactions) == 1

    transaction: t.InteractionResponseSent = injection.transactions[0]
    assert transaction.type is TransactionTypes.INTERACTION_RESPONSE_SENT
    assert transaction.ephemeral is True

    embed = disnake.Embed(
        title="Command failed",
        description="No error code exists for `-1`",
        color=bot.colors.error,
        timestamp=bot.state.now,
    )
    assert transaction.content is None
    assert transaction.embed == embed


async def test_instance_info(causar: Causar):
    class Info(NamedTuple):
        guild_id: int
        cluster_id: int
        shard_id: int

    test_guilds: list[Info] = [
        Info(808030843078836254, 5, 44),
        Info(601219766258106399, 2, 15),
        Info(737166408525283348, 2, 19),
        Info(881118111967883295, 1, 0),
        Info(934497725809037312, 2, 11),
        Info(500525882226769931, 3, 24),
    ]

    for info in test_guilds:
        injection: Injection = await causar.generate_injection("instance_info")
        injection.set_kwargs(guild_id=info.guild_id)
        await causar.run_command(injection)
        assert len(injection.transactions) == 1
        transaction: t.InteractionResponseSent = injection.transactions[0]
        assert transaction.type is TransactionTypes.INTERACTION_RESPONSE_SENT
        assert transaction.ephemeral is True
        assert (
            transaction.content == f"Guild `{info.guild_id}` should be in cluster "
            f"`{info.cluster_id}` with the specific shard `{info.shard_id}`",
        )
