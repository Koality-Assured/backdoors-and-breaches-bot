"""
Tabletop facilitator and assistant tools cog for Backdoors & Breaches.
"""

from __future__ import annotations

import logging
import random
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bnb.config import Settings
from bnb.deck_loader import DeckLoader
from bnb.models import CardType
from bnb.ui.embeds import (
    create_card_embed,
    create_inject_embed,
)
from bnb.ui.views import FacilitatorView

logger = logging.getLogger(__name__)


class AssistantCog(commands.Cog, name="Facilitator"):
    """Tabletop Facilitator and Game Assistant Tools."""

    def __init__(self, bot: commands.Bot, deck_loader: DeckLoader, settings: Settings) -> None:
        self.bot = bot
        self.deck_loader = deck_loader
        self.settings = settings

    async def deck_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete available decks."""
        decks = self.deck_loader.list_decks()
        choices = []
        for d in decks:
            if current.lower() in d.title.lower() or current.lower() in d.id.lower():
                choices.append(app_commands.Choice(name=f"{d.title} ({len(d.cards)} cards)", value=d.id))
        return choices[:25]

    @commands.hybrid_command(name="roll", description="Roll a die (e.g., 20-sided for B&B) with optional modifier.")
    @app_commands.describe(
        sides="Number of sides on the die (default: 20)",
        modifier="Additive modifier (e.g., 3 for hand bonus)",
    )
    async def roll_die(
        self,
        ctx: commands.Context,
        sides: int = 20,
        modifier: int = 0,
    ) -> None:
        """Roll dice with visual embeds."""
        if sides < 2:
            await ctx.reply("A die must have at least 2 sides.", ephemeral=True)
            return
        if sides > 1000:
            await ctx.reply("Max sides is 1000.", ephemeral=True)
            return

        raw_roll = random.randint(1, sides)
        total = raw_roll + modifier

        # Determine color for d20
        if sides == 20:
            if raw_roll == 20:
                color = 0xF59E0B
                footer = "🌟 Natural 20! Critical Success!"
            elif raw_roll == 1:
                color = 0x991B1B
                footer = "🚨 Natural 1! Critical Failure!"
            elif total >= 11:
                color = 0x10B981
                footer = f"✅ Target Met: {total} >= 11 (Success)"
            else:
                color = 0xEF4444
                footer = f"❌ Target Missed: {total} < 11 (Failure)"
        else:
            color = 0x3B82F6
            footer = f"Rolled d{sides} with modifier {modifier:+d}"

        embed = discord.Embed(
            title=f"🎲 Dice Roll: **{total}**",
            color=color,
        )
        mod_str = f" {modifier:+d}" if modifier != 0 else ""
        embed.description = f"{ctx.author.mention} rolled a **d{sides}{mod_str}**:\n`{raw_roll}` (Natural Roll){mod_str} = **`{total}`**"
        embed.set_footer(text=footer)

        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="scenario", description="Deal 4 secret attack vectors privately for running live exercises.")
    @app_commands.describe(deck="Expansion deck to draw vectors from (default: CoreV2.2)")
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def deal_scenario(
        self,
        ctx: commands.Context,
        deck: Optional[str] = None,
    ) -> None:
        """Privately deal the 4 secret threat cards to the caller."""
        deck_id = deck or self.settings.default_deck
        vectors = self.deck_loader.deal_scenario(deck_id)

        if len(vectors) < 4:
            await ctx.reply("Could not assemble all 4 attack vectors from the specified deck.", ephemeral=True)
            return

        embed = discord.Embed(
            title="🔒 Secret Scenario Attack Vectors (Facilitator View)",
            description=f"Generated from deck: **{deck_id}**\nKeep these private while running your tabletop exercise!",
            color=0x2563EB,
        )

        for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
            card = vectors.get(vtype)
            if card:
                details = card.clean_details[:200] + ("..." if len(card.clean_details) > 200 else "")
                embed.add_field(
                    name=f"{vtype.emoji} {vtype.display_name}: {card.name}",
                    value=f"{details}\n*Deck: {card.deck_title}*",
                    inline=False,
                )

        embed.set_footer(text="Backdoors & Breaches • Facilitator Mode")
        view = FacilitatorView(self.deck_loader, deck_id)
        await ctx.reply(embed=embed, view=view, ephemeral=True)

    @commands.hybrid_command(name="inject", description="Draw a random Inject complication card.")
    @app_commands.describe(deck="Deck to draw from (default: any)")
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def draw_inject(
        self,
        ctx: commands.Context,
        deck: Optional[str] = None,
    ) -> None:
        """Draw a random Inject card."""
        inject_card = self.deck_loader.get_random_card(CardType.INJECT, deck)
        if not inject_card:
            await ctx.reply("No Inject cards available for the chosen deck.", ephemeral=True)
            return

        embed = create_inject_embed(inject_card, reason=f"Drawn by {ctx.author.display_name}")
        files: List[discord.File] = []
        if inject_card.image_path:
            try:
                files.append(discord.File(inject_card.image_path, filename="inject.png"))
                embed.set_image(url="attachment://inject.png")
            except Exception:
                pass

        await ctx.reply(embed=embed, files=files)

    @commands.hybrid_command(name="consultant", description="Draw a random Consultant expert card.")
    @app_commands.describe(deck="Deck to draw from (default: any)")
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def draw_consultant(
        self,
        ctx: commands.Context,
        deck: Optional[str] = None,
    ) -> None:
        """Draw a random Consultant card."""
        card = self.deck_loader.get_random_card(CardType.CONSULTANT, deck)
        if not card:
            await ctx.reply("No Consultant cards available in this deck.", ephemeral=True)
            return

        files: List[discord.File] = []
        file_name = None
        if card.image_path:
            try:
                file_name = "consultant.png"
                files.append(discord.File(card.image_path, filename=file_name))
            except Exception:
                pass

        embed = create_card_embed(card, file_attachment_name=file_name)
        await ctx.reply(embed=embed, files=files)
