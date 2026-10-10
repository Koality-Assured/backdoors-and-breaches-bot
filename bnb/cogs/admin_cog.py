"""
Admin, Help, and Utility Cog for Backdoors & Breaches.
"""

from __future__ import annotations

import logging
import time

import discord
from discord.ext import commands

from bnb.config import Settings
from bnb.deck_loader import DeckLoader
from bnb.ui.embeds import (
    create_help_embed,
    create_rules_embed,
)

logger = logging.getLogger(__name__)


class AdminCog(commands.Cog, name="Admin"):
    """Administration, Help, and Diagnostics."""

    def __init__(self, bot: commands.Bot, deck_loader: DeckLoader, settings: Settings) -> None:
        self.bot = bot
        self.deck_loader = deck_loader
        self.settings = settings
        self.start_time = time.time()

    @commands.hybrid_command(name="bnbhelp", description="Show comprehensive command guide and documentation.")
    async def bnb_help(self, ctx: commands.Context) -> None:
        """Display help embed."""
        embed = create_help_embed(prefix=self.settings.command_prefix)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="bnbrules", description="Quick reference rules for Backdoors & Breaches.")
    async def bnb_rules(self, ctx: commands.Context) -> None:
        """Display rules reference."""
        embed = create_rules_embed()
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="ping", description="Check bot latency and uptime.")
    async def ping(self, ctx: commands.Context) -> None:
        """Check bot response time and uptime."""
        latency_ms = round(self.bot.latency * 1000)
        uptime_seconds = int(time.time() - self.start_time)
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {seconds}s"

        decks_count = len(self.deck_loader.list_decks())
        cards_count = len(self.deck_loader.get_all_cards())

        embed = discord.Embed(
            title="🏓 Pong!",
            color=0x10B981,
        )
        embed.add_field(name="Latency", value=f"`{latency_ms} ms`", inline=True)
        embed.add_field(name="Uptime", value=f"`{uptime_str}`", inline=True)
        embed.add_field(name="Loaded Decks", value=f"`{decks_count}` ({cards_count} cards)", inline=True)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="about", description="About this Backdoors & Breaches Discord bot.")
    async def about(self, ctx: commands.Context) -> None:
        """Display project about info."""
        embed = discord.Embed(
            title="🛡️ About Backdoors & Breaches Discord Bot",
            description=(
                "**Backdoors & Breaches** is an incident response card game developed by "
                "[Black Hills Information Security (BHIS)](https://www.blackhillsinfosec.com) "
                "to simulate real-world cyber attack scenarios and tabletop exercises.\n\n"
                "This open-source bot provides interactive tabletop simulation, facilitation tools, "
                "and a complete card encyclopedia across 10 official decks and expansions."
            ),
            color=0x2563EB,
        )
        embed.add_field(name="Organization", value="[Koality Assured](https://github.com/Koality-Assured)", inline=True)
        embed.add_field(name="License", value="MIT (Game concepts CC BY-SA 4.0 BHIS)", inline=True)
        embed.add_field(name="Repository", value="[GitHub](https://github.com/Koality-Assured/backdoors-and-breaches-bot)", inline=True)
        embed.set_footer(text="Backdoors & Breaches • Community Open Source Edition")
        await ctx.reply(embed=embed)

    @commands.command(name="sync", hidden=True)
    @commands.is_owner()
    async def sync_commands(self, ctx: commands.Context, guild_only: bool = False) -> None:
        """Owner command to force sync application commands."""
        async with ctx.typing():
            if guild_only and ctx.guild:
                self.bot.tree.copy_global_to(guild=ctx.guild)
                synced = await self.bot.tree.sync(guild=ctx.guild)
                await ctx.reply(f"Synced {len(synced)} command(s) to this guild (`{ctx.guild.name}`).")
            else:
                synced = await self.bot.tree.sync()
                await ctx.reply(f"Globally synced {len(synced)} application command(s).")
