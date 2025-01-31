from __future__ import annotations

import typing

import disnake
import logoo
from disnake.ext import components

from suggestions.interaction_handler import InteractionHandler
from suggestions.utility import wrap_with_error_handler

if typing.TYPE_CHECKING:
    from suggestions.cogs.suggestion_queue_cog import SuggestionsQueueCog

logger = logoo.Logger(__name__)
manager = components.get_manager("suggestions")


class QueueButton(components.RichButton):
    pid: str

    @wrap_with_error_handler()
    async def callback(  # type: ignore
        self,
        inter: disnake.MessageInteraction,
    ):
        ih = await InteractionHandler.new_handler(inter)
        cog: SuggestionsQueueCog = ih.bot.cogs.get("SuggestionsQueueCog")  # type: ignore
        await getattr(cog.core, core_mapping[self.__class__])(ih, self.pid)  # type: ignore


@manager.register  # type: ignore
class VirtualApproveButton(QueueButton):
    pass


@manager.register  # type: ignore
class VirtualRejectButton(QueueButton):
    pass


@manager.register  # type: ignore
class QueueStopButton(QueueButton):
    pass


@manager.register  # type: ignore
class QueueNextButton(QueueButton):
    pass


@manager.register  # type: ignore
class QueuePreviousButton(QueueButton):
    pass


core_mapping = {
    VirtualApproveButton: "virtual_approve_button",
    VirtualRejectButton: "virtual_reject_button",
    QueueStopButton: "stop_button",
    QueueNextButton: "next_button",
    QueuePreviousButton: "previous_button",
}
