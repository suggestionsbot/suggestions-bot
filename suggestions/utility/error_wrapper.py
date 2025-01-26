import functools
from typing import Callable

from suggestions.interaction_handler import InteractionHandler


def wrap_with_error_handler():
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                inter = (
                    args[1].interaction
                    if isinstance(args[1], InteractionHandler)
                    else args[1]
                )
                await inter.bot.on_slash_command_error(inter, e)

        return wrapper

    return decorator
