from __future__ import annotations

import asyncio
import datetime
import logging
import os
from pathlib import Path
from typing import Type

import aiohttp
import disnake
from disnake.ext import commands
from bot_base import BotBase, BotContext, PrefixNotFound

from suggestions import State, Colors, Emojis
from suggestions.exceptions import (
    BetaOnly,
    MissingSuggestionsChannel,
    MissingLogsChannel,
)
from suggestions.stats import Stats
from suggestions.database import SuggestionsMongoManager

log = logging.getLogger(__name__)


class SuggestionsBot(commands.AutoShardedInteractionBot, BotBase):
    def __init__(self, *args, **kwargs):
        self.is_prod: bool = True if os.environ.get("PROD", None) else False
        self.db: SuggestionsMongoManager = SuggestionsMongoManager(
            os.environ["PROD_MONGO_URL"] if self.is_prod else os.environ["MONGO_URL"]
        )
        self.colors: Type[Colors] = Colors
        self.state: State = State(self.db)
        self.stats: Stats = Stats(self.db)
        self.suggestion_emojis: Type[Emojis] = Emojis
        self.old_prefixed_commands: set[str] = {
            "changelog",
            "channel",
            "help",
            "info",
            "invite",
            "ping",
            "prefix",
            "serverinfo",
            "sid",
            "stats",
            "suggestions",
            "vote",
        }
        self.converted_prefix_commands: set[str] = {"suggest", "approve", "reject"}
        super().__init__(
            *args,
            **kwargs,
            leave_db=True,
            do_command_stats=False,
        )

    async def on_command_completion(self, ctx: BotContext) -> None:
        if ctx.command.qualified_name == "logout":
            return

        self.stats.register_command_usage(ctx.command.qualified_name)
        log.debug(f"Command executed: `{ctx.command.qualified_name}`")

    async def process_commands(self, message: disnake.Message):
        try:
            prefix = await self.get_guild_prefix(message.guild.id)
            prefix = self.get_case_insensitive_prefix(message.content, prefix)
        except (AttributeError, PrefixNotFound):
            prefix = self.get_case_insensitive_prefix(
                message.content, self.DEFAULT_PREFIX
            )

        as_args: list[str] = message.content.split(" ")
        command_to_invoke: str = as_args[0]
        if not command_to_invoke.startswith(prefix):
            # Not our prefix
            return

        command_to_invoke = command_to_invoke[len(prefix) :]

        if command_to_invoke in self.old_prefixed_commands:
            embed: disnake.Embed = disnake.Embed(
                title="Maintenance mode",
                description="Sadly this command is in maintenance mode.\n"
                # "You can read more about how this affects you [here]()",
                "You can read more about how this affects you by following our announcements channel.",
                colour=disnake.Color.from_rgb(255, 148, 148),
            )
            return await message.channel.send(embed=embed)

        elif command_to_invoke in self.converted_prefix_commands:
            embed: disnake.Embed = disnake.Embed(
                description="We are moving with the times, as such this command is now a slash command.\n"
                "You can read more about how this affects you as well as ensuring you can "
                # "use the bots commands [here]()",
                "use the bots commands by following our announcements channel.",
                colour=disnake.Color.magenta(),
            )
            return await message.channel.send(embed=embed)

        ctx = await self.get_context(message, cls=BotContext)
        if ctx.command:
            log.debug(
                "Attempting to invoke command %s for User(id=%s)",
                ctx.command.qualified_name,
                ctx.author.id,
            )

        await self.invoke(ctx)

    async def on_slash_command_error(
        self,
        interaction: disnake.ApplicationCommandInteraction,
        exception: commands.CommandError,
    ) -> None:
        exception = getattr(exception, "original", exception)
        if isinstance(exception, BetaOnly):
            embed: disnake.Embed = disnake.Embed(
                title="Beta restrictions",
                description="This command is restricted to beta guilds only, "
                "please check back at a later date.",
                colour=self.colors.beta_required,
            )
            return await interaction.send(embed=embed, ephemeral=True)

        elif isinstance(exception, MissingSuggestionsChannel):
            embed: disnake.Embed = disnake.Embed(
                title="Missing Suggestions Channel",
                description="This command requires a suggestion channel to use.\n"
                "Please contact an administrator and ask them to set one up "
                "using the following command.\n`/config channel`",
                color=self.colors.error,
            )
            return await interaction.send(embed=embed, ephemeral=True)

        elif isinstance(exception, MissingLogsChannel):
            embed: disnake.Embed = disnake.Embed(
                title="Missing Logs Channel",
                description="This command requires a log channel to use.\n"
                "Please contact an administrator and ask them to set one up "
                "using the following command.\n`/config logs`",
                color=self.colors.error,
            )
            return await interaction.send(embed=embed, ephemeral=True)

        raise exception

    async def load(self):
        await self.state.load()
        await self.update_bot_listings()

        count = 0
        extensions = Path("./suggestions/cogs").rglob("*.py")
        for ext in extensions:
            _path = ".".join(ext.parts)
            self.load_extension(_path[:-3])
            count += 1

        log.debug("Loaded %s cogs", count)

    async def graceful_shutdown(self) -> None:
        """Gracefully shutdown the bot.

        This can take up to a minute.
        """
        self.state.notify_shutdown()
        await asyncio.gather(*self.state.background_tasks)
        log.info("Shutting down")
        await self.close()

    async def update_bot_listings(self) -> None:
        """Updates the bot lists with current stats."""
        if not self.is_prod:
            log.warning("Cancelling bot listing updates as we aren't in production.")
            return

        state: State = self.state
        time_between_updates: datetime.timedelta = datetime.timedelta(minutes=30)

        async def process():
            await self.wait_until_ready()

            headers = {"Authorization": f'Bearer {os.environ["SUGGESTIONS_API_KEY"]}'}
            while not state.is_closing:
                body = {
                    "guildCount": len(self.guilds),
                    "timestamp": str(datetime.datetime.now()),
                }
                async with aiohttp.ClientSession(headers=headers) as session:
                    async with session.post(
                        os.environ["SUGGESTIONS_STATS_API_URL"], json=body
                    ) as r:
                        print(r)

                log.debug("Updated bot listings")

                remaining_seconds = time_between_updates.total_seconds()
                while remaining_seconds > 0:

                    remaining_seconds -= 5
                    await asyncio.sleep(5)

                    if state.is_closing:
                        return

        task_1 = asyncio.create_task(process())
        state.add_background_task(task_1)
        log.info("Setup bot listing updates")
