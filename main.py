import asyncio
import contextlib
import io
import logging
import os
import signal
import sys
import textwrap
from traceback import format_exception
from typing import List

import cooldowns
import disnake
from alaric import AQ
from alaric.comparison import EQ
from alaric.projections import PROJECTION, SHOW
from bot_base.paginators.disnake_paginator import DisnakePaginator
from disnake.ext import commands

from suggestions import SuggestionsBot

from dotenv import load_dotenv

from suggestions.cooldown_bucket import InteractionBucket

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)-7s | %(asctime)s | %(filename)19s:%(funcName)-27s | %(message)s",
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
    log = logging.getLogger(__name__)
    intents = disnake.Intents.none()
    is_prod: bool = True if os.environ.get("PROD", None) else False

    if is_prod:
        total_shards = 53
        offset = int(os.environ["CLUSTER"]) - 1
        num_shards = 10
        shard_ids = [
            i
            for i in range(offset * num_shards, (offset * num_shards) + num_shards)
            if i < total_shards
        ]

        cluster_id = offset + 1
        args = {
            "shard_count": total_shards,
            "cluster": cluster_id,
            "shard_ids": shard_ids,
        }
        log.info("Cluster %s - Handling shards %s", cluster_id, shard_ids)
    else:
        args = {}

    bot = SuggestionsBot(
        intents=intents,
        command_prefix="s.",
        case_insensitive=True,
        strip_after_prefix=True,
        load_builtin_commands=True,
        chunk_guilds_at_startup=False,
        member_cache_flags=disnake.MemberCacheFlags.none(),
        **args,
    )
    if not bot.is_prod:
        bot._test_guilds = [737166408525283348]

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
    async def colors(interaction: disnake.ApplicationCommandInteraction):
        """Shows the bots color palette."""
        await bot.colors.show_colors(interaction)

    @bot.slash_command()
    @cooldowns.cooldown(1, 1, bucket=InteractionBucket.author)
    async def stats(interaction: disnake.GuildCommandInteraction):
        """Get bot stats!"""
        if bot.is_prod:
            shard_id = (interaction.guild_id >> 22) % bot.total_shards
        else:
            shard_id = 0

        python_version = f"{sys.version_info[0]}.{sys.version_info[1]}"
        embed: disnake.Embed = disnake.Embed(
            color=bot.colors.embed_color, timestamp=bot.state.now
        )
        guilds: int = await bot.stats.fetch_global_guild_count()
        embed.add_field(name="Guilds", value=guilds)
        embed.add_field(name="Total shards", value=bot.total_shards)
        embed.add_field(name="Cluster Uptime", value=bot.get_uptime())
        embed.add_field(name="Disnake", value="Custom fork")
        embed.add_field(name="Python", value=python_version)
        embed.add_field(name="Version", value=bot.version)
        embed.set_footer(text=f"Cluster {bot.cluster_id} - Shard {shard_id}")

        await interaction.send(embed=embed, ephemeral=False)
        log.debug("User %s viewed stats", interaction.author.id)
        await bot.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            bot.stats.type.STATS,
        )

    @bot.slash_command()
    @cooldowns.cooldown(1, 1, bucket=InteractionBucket.author)
    async def info(interaction: disnake.CommandInteraction):
        """View bot information."""
        base_site = "https://suggestions.gg/"
        embed: disnake.Embed = disnake.Embed(
            title=bot.user.name,
            description="The only suggestions bot you'll ever need. "
            "Simple usage and management of suggestions for public and staff use.",
            colour=bot.colors.embed_color,
            timestamp=bot.state.now,
        )
        embed.add_field("Bot Author(s)", "Anthony, Ethan (Skelmis)")
        embed.add_field("Website", f"[suggestions.gg]({base_site})")
        embed.add_field("Discord", f"[suggestions.gg/discord]({base_site}/contact)")
        embed.add_field(
            "Github", f"[suggestions.gg/github](https://github.com/suggestionsbot)"
        )
        embed.add_field(
            "Legal",
            f"[Privacy Policy]({base_site}/privacy) | [Terms of Service]({base_site}/terms)",
        )
        embed.add_field("Version", bot.version)
        embed.set_footer(text="© 2022 Anthony Collier")
        await interaction.send(embed=embed)

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
        await interaction.response.defer(ephemeral=True)
        main_guild = await bot.fetch_guild(bot.main_guild_id)
        try:
            member = await main_guild.fetch_member(interaction.author.id)
        except disnake.NotFound:
            return await interaction.send(
                "Looks like you aren't in our support discord.", ephemeral=True
            )

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
        await bot.stats.log_stats(
            interaction.author.id,
            interaction.guild_id,
            bot.stats.type.ACTIVATE_BETA,
        )

    @bot.slash_command(
        dm_permission=False,
        guild_ids=[601219766258106399, 737166408525283348],
        default_member_permissions=disnake.Permissions(administrator=True),
    )
    @commands.is_owner()
    async def shutdown(
        interaction: disnake.ApplicationCommandInteraction,
        cluster_id=commands.Param(
            default=None,
            choices=[str(i) for i in range(1, 7)],
            description="The specific cluster you wish to shut down",
        ),
    ):
        """Gracefully shut the bot down."""
        await interaction.send("Initiating shutdown now.", ephemeral=True)
        if not bot.is_prod:
            await bot.graceful_shutdown()
            return

        if cluster_id:
            cluster_id = int(cluster_id)
            if cluster_id not in list(range(1, 7)):
                return interaction.send("Invalid cluster id", ephemeral=True)

            if cluster_id == bot.cluster_id:
                # Only shut ourselves down
                await bot.graceful_shutdown()
                return

            # Mark all other clusters as responded
            # so only the one we want shuts down
            responded_clusters = list(range(1, 7))
            responded_clusters.remove(cluster_id)
            await bot.db.cluster_shutdown_requests.insert(
                {
                    "responded_clusters": responded_clusters,
                    "timestamp": bot.state.now,
                    "issuer_cluster_id": bot.cluster_id,
                }
            )
            log.info("Asked cluster %s to shut down", cluster_id)
            return

        # We need to notify other clusters to shut down
        responded_clusters = [bot.cluster_id]
        await bot.db.cluster_shutdown_requests.insert(
            {
                "responded_clusters": responded_clusters,
                "timestamp": bot.state.now,
                "issuer_cluster_id": bot.cluster_id,
            }
        )
        log.info("Notified other clusters to shutdown")

        await bot.graceful_shutdown()

    async def graceful_shutdown(bot: SuggestionsBot, signame):
        await bot.graceful_shutdown()

    # https://github.com/gearbot/GearBot/blob/live/GearBot/GearBot.py#L206-L212
    try:
        for signame in ("SIGINT", "SIGTERM", "SIGKILL"):
            asyncio.get_event_loop().add_signal_handler(
                getattr(signal, signame),
                lambda: asyncio.ensure_future(graceful_shutdown(bot, signame)),
            )
    except Exception as e:
        pass  # doesn't work on windows

    # Make sure we don't shutdown due to a previous shutdown request
    cursor = (
        bot.db.cluster_shutdown_requests.raw_collection.find({})
        .sort("timestamp", -1)
        .limit(1)
    )
    items = await cursor.to_list(1)
    if items:
        entry = items[0]
        if bot.cluster_id not in entry["responded_clusters"]:
            log.debug(entry["responded_clusters"])
            entry["responded_clusters"].append(bot.cluster_id)
            log.debug(entry["responded_clusters"])
            await bot.db.cluster_shutdown_requests.upsert({"_id": entry["_id"]}, entry)
            log.debug("Marked old shutdown request as satisfied")

    await bot.load()
    TOKEN = os.environ["PROD_TOKEN"] if bot.is_prod else os.environ["TOKEN"]
    await bot.start(TOKEN)


asyncio.run(run_bot())
