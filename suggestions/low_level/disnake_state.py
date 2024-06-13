from __future__ import annotations

import typing

import disnake.state

if typing.TYPE_CHECKING:
    from disnake.types import gateway


class PatchedConnectionState(disnake.state.AutoShardedConnectionState):
    """We patch some things into state in order to be able to
    pip install disnake
    without completely breaking expected functionality.

    Ideally this moves completely out of patches but for now alas.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.guild_ids: set[int] = set()

    def parse_guild_create(self, data: gateway.GuildCreateEvent) -> None:
        self.guild_ids.add(int(data["id"]))

    def parse_guild_delete(self, data: gateway.GuildDeleteEvent) -> None:
        self.guild_ids.discard(int(data["id"]))

    def parse_guild_update(self, data: gateway.GuildUpdateEvent) -> None:
        return

    def parse_guild_role_create(self, data: gateway.GuildRoleCreateEvent) -> None:
        return

    def parse_guild_role_delete(self, data: gateway.GuildRoleDeleteEvent) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_role_update(self, data: gateway.GuildRoleUpdateEvent) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_scheduled_event_create(
        self, data: gateway.GuildScheduledEventCreateEvent
    ) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_scheduled_event_update(
        self, data: gateway.GuildScheduledEventUpdateEvent
    ) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_scheduled_event_delete(
        self, data: gateway.GuildScheduledEventDeleteEvent
    ) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_scheduled_event_user_add(
        self, data: gateway.GuildScheduledEventUserAddEvent
    ) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_scheduled_event_user_remove(
        self, data: gateway.GuildScheduledEventUserRemoveEvent
    ) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def parse_guild_members_chunk(self, data: gateway.GuildMembersChunkEvent) -> None:
        return
        # Removing this event parsing as we ripped out the guild cache

    def _add_guild_from_data(self, data):
        # Unsure if this is still needed
        return None  # noqa
