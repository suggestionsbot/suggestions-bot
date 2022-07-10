import asyncio
import contextlib
import datetime
import io
import logging
import os
import sys
import textwrap
from traceback import format_exception
from typing import List

import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.projections import PROJECTION, SHOW
from bot_base.paginators.disnake_paginator import DisnakePaginator
from disnake.ext import commands

from suggestions import SuggestionsBot

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s | %(asctime)s | %(filename)18s:%(funcName)-21s | %(message)s",
    datefmt="%d/%m/%Y %I:%M:%S %p",
)

disnake_logger = logging.getLogger("disnake")
disnake_logger.setLevel(logging.INFO)
gateway_logger = logging.getLogger("disnake.gateway")
gateway_logger.setLevel(logging.WARNING)
client_logger = logging.getLogger("disnake.client")
client_logger.setLevel(logging.WARNING)
http_logger = logging.getLogger("disnake.http")
http_logger.setLevel(logging.WARNING)
shard_logger = logging.getLogger("disnake.shard")
shard_logger.setLevel(logging.WARNING)

suggestions_logger = logging.getLogger("suggestions")
suggestions_logger.setLevel(logging.DEBUG)


async def run_bot():
    intents = disnake.Intents.none()
    # intents.guilds = True  # noqa
    # intents.members = True  # noqa
    # intents.messages = True  # noqa
    # intents.message_content = True  # noqa

    bot = SuggestionsBot(
        intents=intents,
        command_prefix="s.",
        case_insensitive=True,
        strip_after_prefix=True,
        load_builtin_commands=True,
        # test_guilds=[737166408525283348],
        chunk_guilds_at_startup=False,
        member_cache_flags=disnake.MemberCacheFlags.none(),
    )

    log = logging.getLogger(__name__)

    @bot.listen("on_ready")
    async def on_ready():
        log.info("Suggestions main: Ready")
        log.info(bot.get_uptime())
        await bot.suggestion_emojis.populate_emojis()

    @bot.slash_command(
        dm_permission=False,
        guild_ids=[601219766258106399, 737166408525283348],
        default_member_permissions=disnake.Permissions(administrator=True),
    )
    @commands.is_owner()
    async def shutdown(interaction: disnake.ApplicationCommandInteraction):
        """Gracefully shut the bot down."""
        await interaction.send("Initiating shutdown now.", ephemeral=True)
        await bot.graceful_shutdown()

    @bot.slash_command(
        dm_permission=False,
        guild_ids=[601219766258106399, 737166408525283348],
        default_member_permissions=disnake.Permissions(administrator=True),
    )
    @commands.is_owner()
    async def colors(interaction: disnake.ApplicationCommandInteraction):
        """Shows the bots color palette."""
        await bot.colors.show_colors(interaction)

    @bot.slash_command()
    async def stats(interaction: disnake.ApplicationCommandInteraction):
        """Get bot stats!"""
        package_version = disnake.__version__
        python_version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        embed: disnake.Embed = disnake.Embed(
            title=f"Stats for {bot.user.name}",
            description=f"Bot Version: {bot.version}\nGuilds: {len(bot.guilds)}\nShards: {len(bot.shards)}\n---\n"
            f"Running on Python {python_version} and Disnake {package_version} "
            f"with an uptime of {bot.get_uptime()}",
        )
        await interaction.send(embed=embed, ephemeral=False)

    def clean_code(content):
        """Automatically removes code blocks from the code."""
        # remove ```py\n```
        if content.startswith("```") and content.endswith("```"):
            return "\n".join(content.split("\n")[1:])[:-3]
        else:
            return content

    @bot.slash_command(
        dm_permission=False,
        guild_ids=[601219766258106399, 737166408525283348],
        default_member_permissions=disnake.Permissions(administrator=True),
    )
    @commands.is_owner()
    async def eval(ctx, code):
        """
        Evaluates given code.
        """
        code = clean_code(code)

        local_variables = {
            "disnake": disnake,
            "commands": commands,
            "bot": bot,
            "interaction": ctx,
        }

        stdout = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout):
                exec(
                    f"async def func():\n{textwrap.indent(code, '    ')}",
                    local_variables,
                )

                obj = await local_variables["func"]()
                result = f"{stdout.getvalue()}\n-- {obj}\n"

        except Exception as e:
            result = "".join(format_exception(e, e, e.__traceback__))  # noqa

        async def format_page(code, page_number):
            embed = disnake.Embed(title=f"Eval for {ctx.author.name}")
            embed.description = f"```{code}```"

            embed.set_footer(text=f"Page {page_number}")
            return embed

        paginator: DisnakePaginator = DisnakePaginator(
            1,
            [result[i : i + 2000] for i in range(0, len(result), 2000)],
        )
        paginator.format_page = format_page
        await paginator.start(interaction=ctx)

    @bot.slash_command(
        dm_permission=False,
    )
    async def activate(interaction: disnake.GuildCommandInteraction):
        pass

    @activate.sub_command()
    async def beta(interaction: disnake.GuildCommandInteraction):
        """Activate beta for your guild."""
        main_guild = await bot.fetch_guild(bot.main_guild_id)
        member = await main_guild.fetch_member(interaction.author.id)
        role_ids: List[int] = [role.id for role in member.roles]
        if bot.beta_role_id not in role_ids:
            return await interaction.send(
                "You do not have beta access.", ephemeral=True
            )

        initial_check = await bot.db.beta_links.find(
            AQ(EQ("user_id", interaction.author.id)),
            projections=PROJECTION(SHOW("user_id"), SHOW("guild_id")),
        )
        if initial_check:
            guild = await bot.fetch_guild(initial_check["guild_id"])
            return await interaction.send(
                f"You have already activated beta on {guild.name}.", ephemeral=True
            )

        await bot.db.beta_links.insert(
            {"user_id": interaction.author.id, "guild_id": interaction.guild_id}
        )
        await bot.db.guild_configs.insert({"_id": interaction.guild_id})
        await interaction.send(
            "Thanks! I have activated beta for you in this guild.", ephemeral=True
        )
        log.info(
            "Activated beta for %s in guild %s",
            interaction.author.id,
            interaction.guild_id,
        )

    # await bot.db.guild_configs.insert({"_id": 737166408525283348})
    await bot.load()
    TOKEN = os.environ["PROD_TOKEN"] if bot.is_prod else os.environ["TOKEN"]
    await bot.start(TOKEN)


asyncio.run(run_bot())
