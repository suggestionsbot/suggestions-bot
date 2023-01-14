import re
from typing import Optional

from suggestions import ErrorCode

failed_suggestion_channel_fetch = re.compile(
    r".*File \"/bot/suggestions/cogs/suggestion_cog\.py\", line \d+, in suggest"
    r".*\n {4}channel: WrappedChannel = await self\.bot\.get_or_fetch_channel\("
)
failed_suggestion_channel_send = re.compile(
    r'.*File "/bot/suggestions/cogs/suggestion_cog\.py", line \d+, in suggest.*\n'
    r" {4}message: disnake\.Message = await channel\.send\("
)
failed_log_channel_fetch = re.compile(
    r'.*File "/bot/suggestions/cogs/suggestion_cog\.py", line \d+, in (reject|approve).*\n'
    r' {4}await suggestion\.resolve\(\n {2}File "/bot/suggestions/objects/suggestion\.py", '
    r"line \d+, in resolve\n {4}await self\.edit_message_after_finalization\(\n {2}File "
    r'"/bot/suggestions/objects/suggestion\.py", line \d+, in edit_message_after_finalization\n'
    r" {4}channel: WrappedChannel = await bot\.get_or_fetch_channel\(\n"
)


def try_parse_http_error(traceback: str) -> Optional[ErrorCode]:
    """Given an HTTP error try narrow down what caused it."""
    if failed_suggestion_channel_fetch.search(traceback):
        return ErrorCode.MISSING_FETCH_PERMISSIONS_IN_SUGGESTIONS_CHANNEL

    elif failed_log_channel_fetch.search(traceback):
        return ErrorCode.MISSING_FETCH_PERMISSIONS_IN_LOGS_CHANNEL

    elif failed_suggestion_channel_send.search(traceback):
        return ErrorCode.MISSING_SEND_PERMISSIONS_IN_SUGGESTION_CHANNEL

    return None
