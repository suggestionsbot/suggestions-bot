from __future__ import annotations

from cooldowns import Cooldown

"""
For each guild, we need to support a custom cooldown on top of existing cooldowns.

Given a theoretical current max of tens of thousands, with a realistic current
max of low hundreds this could easily result in a lot of long-lived classes.

To combat this, we can store state in redis and fetch as required
"""

import functools
import typing

from disnake import Interaction

from suggestions.objects import PremiumGuildConfig

if typing.TYPE_CHECKING:
    from suggestions import SuggestionsBot


async def user_cooldown_bucket(inter: Interaction) -> int:
    return inter.author.id


async def handle_custom_suggestion_cooldown():
    async def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            inter: Interaction = (
                args[0] if isinstance(args[0], Interaction) else args[1]
            )
            premium_guild_config: PremiumGuildConfig = await PremiumGuildConfig.from_id(
                inter.guild_id, inter.bot.state
            )
            if not premium_guild_config.is_active:
                # No custom cooldowns since no premium
                return

            if not premium_guild_config.uses_custom_cooldown:
                return

            bot: SuggestionsBot = inter.bot
            redis_state = await bot.redis.hgetall(f"PREMIUM_COOLDOWN:{inter.guild_id}")
            cooldown = Cooldown(
                premium_guild_config.cooldown_amount,
                premium_guild_config.cooldown_period.as_timedelta(),
                bucket=user_cooldown_bucket,
            )
            if redis_state is not None:
                cooldown.load_from_state(redis_state)

            async with cooldown(inter):
                await func(*args, **kwargs)

            await bot.redis.hset(
                f"PREMIUM_COOLDOWN:{inter.guild_id}",
                mapping=cooldown.get_state(),
            )
            del cooldown

        return wrapper

    return decorator
