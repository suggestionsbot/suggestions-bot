from typing import cast

from alaric import Document
from causar import Causar, Injection, TransactionTypes, InjectionMetadata
from causar import transactions as t

from suggestions import SuggestionsBot
from suggestions.objects import UserConfig
from tests.helpers import assert_stats_count


async def check_expected_result(
    causar,
    injection_metadata,
    *,
    command_name: str,
    expected_value: bool,
    expected_message: str,
):
    bot: SuggestionsBot = cast(SuggestionsBot, causar.bot)
    db: Document = bot.db.user_configs

    guild = causar.faker.generate_guild(guild_id=881118111967883295)
    member = causar.faker.generate_member(default_member=True, guild=guild)

    r_1 = await db.find({"_id": member.id})
    assert r_1 is None

    injection: Injection = await causar.generate_injection(command_name)
    injection.set_author(member)
    injection.metadata = injection_metadata

    await causar.run_command(injection)
    assert len(injection.transactions) == 1
    transaction: t.InteractionResponseSent = injection.transactions[0]
    assert transaction.type is TransactionTypes.INTERACTION_RESPONSE_SENT
    assert transaction.ephemeral is True
    assert transaction.content == expected_message

    r_2: UserConfig = await db.find({"_id": member.id})
    assert r_2 is not None
    assert r_2.dm_messages_disabled is expected_value


async def check_dm_view_output(causar: Causar, injection_metadata, expected_value: str):
    guild = causar.faker.generate_guild(guild_id=881118111967883295)
    member = causar.faker.generate_member(default_member=True, guild=guild)

    injection: Injection = await causar.generate_injection("dm view")
    injection.set_author(member)
    injection.metadata = injection_metadata

    await causar.run_command(injection)
    assert len(injection.transactions) == 1
    transaction: t.InteractionResponseSent = injection.transactions[0]
    assert transaction.type is TransactionTypes.INTERACTION_RESPONSE_SENT
    assert transaction.ephemeral is True
    assert (
        transaction.content == f"I {expected_value} DM you on actions such as suggest."
    )


async def test_dm_enable(causar: Causar, injection_metadata: InjectionMetadata):
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        should_be_none=True,
    )
    await check_expected_result(
        causar,
        injection_metadata,
        command_name="dm enable",
        expected_value=False,
        expected_message="I have enabled DM messages for you.",
    )
    await check_dm_view_output(causar, injection_metadata, "will")
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        field="member_dm_enable",
        success_count=1,
    )


async def test_dm_disable(causar: Causar, injection_metadata: InjectionMetadata):
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        should_be_none=True,
    )
    await check_expected_result(
        causar,
        injection_metadata,
        command_name="dm disable",
        expected_value=True,
        expected_message="I have disabled DM messages for you.",
    )
    await check_dm_view_output(causar, injection_metadata, "will not")
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        field="member_dm_disable",
        success_count=1,
    )


async def test_dm_view_without_user_config(
    causar: Causar, injection_metadata: InjectionMetadata
):
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        should_be_none=True,
    )
    await check_dm_view_output(causar, injection_metadata, "will")
    await assert_stats_count(
        causar,
        member_id=271612318947868673,
        guild_id=881118111967883295,
        field="member_dm_view",
        success_count=1,
    )
