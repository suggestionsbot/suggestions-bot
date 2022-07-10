from enum import Enum

from cooldowns import UnknownBucket
from disnake import Interaction


class InteractionBucket(Enum):
    author = 0
    channel = 1
    guild = 2

    def process(self, *args, **kwargs):
        # Handle cogs
        inter: Interaction = args[0] if isinstance(args[0], Interaction) else args[1]
        if self is InteractionBucket.author:
            return inter.author.id

        elif self is InteractionBucket.guild:
            return inter.guild_id

        elif self is InteractionBucket.channel:
            return inter.channel_id

        raise UnknownBucket
