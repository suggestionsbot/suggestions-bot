from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Any, overload, List

from disnake import Object, Embed, File, AllowedMentions, DiscordException
from disnake.abc import MISSING
from disnake.message import _edit_handler, Attachment
from disnake.ui import MessageUIComponent, Components, View

if TYPE_CHECKING:
    from suggestions import SuggestionsBot


class MessageEditing:
    """A helper class for editing messages
    without needing to fetch the channel and message objects.
    """

    def __init__(self, bot: SuggestionsBot, *, channel_id: int, message_id: int):
        self.id: int = message_id
        self.bot: SuggestionsBot = bot
        self.channel: Object = Object(id=channel_id)

    @property
    def _state(self):
        return self.bot._connection

    @overload
    async def edit(
        self,
        content: Optional[str] = ...,
        *,
        embed: Optional[Embed] = ...,
        file: File = ...,
        attachments: Optional[List[Attachment]] = ...,
        suppress_embeds: bool = ...,
        delete_after: Optional[float] = ...,
        allowed_mentions: Optional[AllowedMentions] = ...,
        view: Optional[View] = ...,
        components: Optional[Components[MessageUIComponent]] = ...,
    ) -> None: ...

    @overload
    async def edit(
        self,
        content: Optional[str] = ...,
        *,
        embed: Optional[Embed] = ...,
        files: List[File] = ...,
        attachments: Optional[List[Attachment]] = ...,
        suppress_embeds: bool = ...,
        delete_after: Optional[float] = ...,
        allowed_mentions: Optional[AllowedMentions] = ...,
        view: Optional[View] = ...,
        components: Optional[Components[MessageUIComponent]] = ...,
    ) -> None: ...

    @overload
    async def edit(
        self,
        content: Optional[str] = ...,
        *,
        embeds: List[Embed] = ...,
        file: File = ...,
        attachments: Optional[List[Attachment]] = ...,
        suppress_embeds: bool = ...,
        delete_after: Optional[float] = ...,
        allowed_mentions: Optional[AllowedMentions] = ...,
        view: Optional[View] = ...,
        components: Optional[Components[MessageUIComponent]] = ...,
    ) -> None: ...

    @overload
    async def edit(
        self,
        content: Optional[str] = ...,
        *,
        embeds: List[Embed] = ...,
        files: List[File] = ...,
        attachments: Optional[List[Attachment]] = ...,
        suppress_embeds: bool = ...,
        delete_after: Optional[float] = ...,
        allowed_mentions: Optional[AllowedMentions] = ...,
        view: Optional[View] = ...,
        components: Optional[Components[MessageUIComponent]] = ...,
    ) -> None: ...

    async def edit(self, content: Optional[str] = MISSING, **fields: Any) -> None:
        if self._state.allowed_mentions is not None:
            previous_allowed_mentions = self._state.allowed_mentions
        else:
            previous_allowed_mentions = None

        data = {
            "default_flags": MISSING,
            "delete_after": None,
            "embed": MISSING,
            "embeds": MISSING,
            "file": MISSING,
            "files": MISSING,
            "attachments": MISSING,
            "suppress": MISSING,  # deprecated
            "suppress_embeds": MISSING,
            "allowed_mentions": MISSING,
            "view": MISSING,
            "components": MISSING,
            "flags": MISSING,
        }
        data = {**data, **fields}

        await _edit_handler(
            msg=self,  # type: ignore
            previous_allowed_mentions=previous_allowed_mentions,
            content=content,
            **data,
        )

    async def delete(self, delay=None):
        raise DiscordException("MessageEditing.delete is not implemented.")
