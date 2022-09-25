from typing import Optional

from suggestions import ErrorCode


def try_parse_http_error(traceback: str) -> Optional[ErrorCode]:
    """Given an HTTP error try narrow down what caused it."""
    if (
        "message: disnake.Message = await channel.send(" in traceback
        and 'File "/bot/suggestions/cogs/suggestion_cog.py", line 154, in suggest'
        in traceback
    ):
        return ErrorCode.MISSING_PERMISSIONS_IN_SUGGESTIONS_CHANNEL

    elif (
        'File "/bot/suggestions/cogs/suggestion_cog.py", line 150, in suggest'
        in traceback
        and "return await super().get_or_fetch_channel(channel_id)" in traceback
    ):
        return ErrorCode.MISSING_PERMISSIONS_IN_SUGGESTIONS_CHANNEL

    elif (
        'File "/bot/suggestions/cogs/suggestion_cog.py", line 293, in approve'
        in traceback
        and "return await super().get_or_fetch_channel(channel_id)" in traceback
    ):
        return ErrorCode.MISSING_PERMISSIONS_IN_LOGS_CHANNEL

    elif (
        'File "/bot/suggestions/cogs/suggestion_cog.py", line 358, in reject'
        in traceback
        and "return await super().get_or_fetch_channel(channel_id)" in traceback
    ):
        return ErrorCode.MISSING_PERMISSIONS_IN_LOGS_CHANNEL

    return None
