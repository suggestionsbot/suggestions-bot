import asyncio
import contextlib
import datetime
import io
import logging
import os
import signal
import sys
import textwrap
from traceback import format_exception

import cooldowns
import disnake
from disnake import Locale
from disnake.ext import commands
from bot_base.paginators.disnake_paginator import DisnakePaginator

from suggestions import SuggestionsBot
from suggestions.cooldown_bucket import InteractionBucket


async def create_bot(database_wrapper=None) -> SuggestionsBot:
    log = logging.getLogger(__name__)
    intents = disnake.Intents.none()
    intents.guilds = True
    is_prod: bool = True if os.environ.get("PROD", None) else False

    if is_prod:
        total_shards = int(os.environ["TOTAL_SHARDS"])
        cluster_id = int(os.environ["CLUSTER"])
        offset = cluster_id - 1
        number_of_shards_per_cluster = int(os.environ["SHARDS_PER_CLUSTER"])
        shard_ids = [
            i
            for i in range(
                offset * number_of_shards_per_cluster,
                (offset * number_of_shards_per_cluster) + number_of_shards_per_cluster,
            )
            if i < total_shards
        ]

        cluster_kwargs = {
            "shard_count": total_shards,
            "cluster": cluster_id,
            "shard_ids": shard_ids,
        }
        log.info("Cluster %s - Handling shards %s", cluster_id, shard_ids)
    else:
        cluster_kwargs = {}

    bot = SuggestionsBot(
        intents=intents,
        command_prefix="s.",
        case_insensitive=True,
        strip_after_prefix=True,
        load_builtin_commands=True,
        chunk_guilds_at_startup=False,
        database_wrapper=database_wrapper,
        member_cache_flags=disnake.MemberCacheFlags.none(),
        **cluster_kwargs,
    )
    if not bot.is_prod:
        bot._test_guilds = [737166408525283348]

    @bot.listen("on_ready")
    async def on_ready():
        await bot.dispatch_initial_ready()

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
            color=bot.colors.embed_color,
            timestamp=bot.state.now,
            description="For more stats, click [here](https://stats.suggestions.gg/)",
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
    async def info(
        interaction: disnake.CommandInteraction,
        support: bool = commands.Param(
            default=False,
        ),
    ):
        """
        {{INFO}}

        Parameters
        ----------
        support: {{INFO_ARG_SUPPORT}}
        """
        await interaction.response.defer()
        if support and bot.is_prod and interaction.guild_id:
            shard_id = bot.get_shard_id(interaction.guild_id)
            shard = bot.get_shard(shard_id)
            latency = shard.latency
            return await interaction.send(
                f"**Guild ID:** `{interaction.guild_id}`\n"
                f"**Average cluster latency:** `{round(bot.latency, 2)}ms`\n"
                f"**Cluster {bot.cluster_id} - Shard {shard_id}:** `{round(latency, 2)}ms`"
            )

        year = datetime.datetime.now().year
        base_site = bot.base_website_url
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
        embed.set_footer(text=f"© {year} Anthony Collier")

        translations = {
            Locale.pt_BR: {
                "author": 651386805043593237,
                "language": "Portuguese, Brazilian",
                "username": "Davi",
            }
        }
        if interaction.locale in translations:
            data = translations[interaction.locale]
            embed.description += f"\n\n{data['language']} translations by {data['username']}(`{data['author']}`)"

        await interaction.send(embed=embed)

    @bot.slash_command()
    @cooldowns.cooldown(1, 1, bucket=InteractionBucket.author)
    async def ping(interaction: disnake.CommandInteraction):
        """
        {{PING}}
        """
        if bot.is_prod:
            shard_id = bot.get_shard_id(interaction.guild_id)
            shard = bot.get_shard(shard_id)
            latency = shard.latency
        else:
            shard_id = 0
            latency = bot.latency

        await interaction.send(
            f"Pong!\n**Average cluster latency:** `{round(bot.latency, 2)}ms`\n"
            f"**Cluster {bot.cluster_id} - Shard {shard_id}:** `{round(latency, 2)}ms`"
        )

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
        await ctx.response.defer(ephemeral=True)
        code = clean_code(code)

        # remove protections on string parsing to allow
        # multi line eval within slash input
        code = "\n".join(code.split("|"))

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
            embed.description = f"```\n{code}\n```"

            embed.set_footer(text=f"Page {page_number}")
            return embed

        paginator: DisnakePaginator = DisnakePaginator(
            1,
            [result[i : i + 2000] for i in range(0, len(result), 2000)],
            try_ephemeral=True,
        )
        paginator.format_page = format_page
        await paginator.start(interaction=ctx)

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

    async def graceful_shutdown(bot: SuggestionsBot, _):
        await bot.graceful_shutdown()

    # https://github.com/gearbot/GearBot/blob/live/GearBot/GearBot.py
    try:
        for signame in ("SIGINT", "SIGTERM", "SIGKILL"):
            asyncio.get_event_loop().add_signal_handler(
                getattr(signal, signame),
                lambda: asyncio.ensure_future(graceful_shutdown(bot, signame)),
            )
    except Exception as e:
        pass  # doesn't work on windows

    return bot
