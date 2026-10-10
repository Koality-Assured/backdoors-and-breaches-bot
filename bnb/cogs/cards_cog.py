"""
Card lookup, search, and encyclopedia cog for Backdoors & Breaches.
"""

from __future__ import annotations

import logging
from typing import List, Optional

import discord
from discord import app_commands
from discord.ext import commands

from bnb.config import Settings
from bnb.deck_loader import DeckLoader
from bnb.models import CardType
from bnb.ui.embeds import (
    create_card_embed,
    create_deck_list_embed,
)
from bnb.ui.views import CardPagingView

logger = logging.getLogger(__name__)


class CardsCog(commands.Cog, name="Cards"):
    """Card Encyclopedia and Deck Browsing Commands."""

    def __init__(self, bot: commands.Bot, deck_loader: DeckLoader, settings: Settings) -> None:
        self.bot = bot
        self.deck_loader = deck_loader
        self.settings = settings

    async def card_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> List[app_commands.Choice[str]]:
        """Autocomplete card names across all expansions."""
        matches = self.deck_loader.search_cards(current, limit=25)
        return [
            app_commands.Choice(name=f"{c.type.emoji} {c.name[:80]} ({c.deck_title[:15]})", value=c.name)
            for c in matches
        ]

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

    @commands.hybrid_command(name="card", description="Look up any Backdoors & Breaches card by name.")
    @app_commands.describe(name="Card name")
    @app_commands.autocomplete(name=card_autocomplete)
    async def get_card(self, ctx: commands.Context, *, name: str) -> None:
        """Display full details and high-resolution artwork for a specific card."""
        card = self.deck_loader.get_card(name)
        if not card:
            # Try fuzzy search
            results = self.deck_loader.search_cards(name, limit=1)
            if results:
                card = results[0]

        if not card:
            await ctx.reply(f"❌ Card `{name}` not found in any loaded expansion.", ephemeral=True)
            return

        files: List[discord.File] = []
        attach_name = None
        if card.image_path:
            try:
                attach_name = f"card_{card.id}.png"
                files.append(discord.File(card.image_path, filename=attach_name))
            except Exception as e:
                logger.error("Could not load image %s: %s", card.image_path, e)

        embed = create_card_embed(card, file_attachment_name=attach_name)
        await ctx.reply(embed=embed, files=files)

    @commands.hybrid_command(name="search", description="Search cards by keyword across all decks.")
    @app_commands.describe(
        query="Keyword to search in card names and descriptions",
        deck="Optional deck filter",
    )
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def search_cards(
        self,
        ctx: commands.Context,
        query: str,
        deck: Optional[str] = None,
    ) -> None:
        """Search cards and view results with interactive paging."""
        matches = self.deck_loader.search_cards(query, deck_id=deck, limit=50)
        if not matches:
            await ctx.reply(f"No cards found matching `{query}`.", ephemeral=True)
            return

        if len(matches) == 1:
            card = matches[0]
            files: List[discord.File] = []
            attach_name = None
            if card.image_path:
                try:
                    attach_name = f"card_{card.id}.png"
                    files.append(discord.File(card.image_path, filename=attach_name))
                except Exception:
                    pass
            embed = create_card_embed(card, file_attachment_name=attach_name)
            await ctx.reply(embed=embed, files=files)
            return

        # Multiple results: launch interactive paging view
        paging_view = CardPagingView(matches)
        embed, file_obj = paging_view.get_current_embed_and_file()
        kwargs = {"embed": embed, "view": paging_view}
        if file_obj:
            kwargs["files"] = [file_obj]
        await ctx.reply(**kwargs)

    @commands.hybrid_command(name="decks", description="List all loaded Backdoors & Breaches decks and expansions.")
    async def list_decks(self, ctx: commands.Context) -> None:
        """Display all loaded decks."""
        decks = self.deck_loader.list_decks()
        embed = create_deck_list_embed(decks)
        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="dump", description="Browse cards of a specific type (e.g., procedure, inject).")
    @app_commands.describe(
        card_type="Type of cards to browse",
        deck="Optional expansion deck filter",
    )
    @app_commands.choices(card_type=[
        app_commands.Choice(name="🎯 Initial Compromise", value="initial"),
        app_commands.Choice(name="🔀 Pivot & Escalate", value="pivot"),
        app_commands.Choice(name="⚓ Persistence", value="persist"),
        app_commands.Choice(name="📡 C2 & Exfiltration", value="c2"),
        app_commands.Choice(name="🛠️ Procedure", value="procedure"),
        app_commands.Choice(name="💉 Inject", value="inject"),
        app_commands.Choice(name="👔 Consultant", value="consultant"),
    ])
    @app_commands.autocomplete(deck=deck_autocomplete)
    async def dump_cards(
        self,
        ctx: commands.Context,
        card_type: app_commands.Choice[str],
        deck: Optional[str] = None,
    ) -> None:
        """Browse all cards of a type using interactive pagination."""
        ctype = CardType.from_str(card_type.value)
        cards = [c for c in self.deck_loader.get_all_cards(deck) if c.type == ctype]

        if not cards:
            await ctx.reply(f"No cards of type `{card_type.name}` found in the specified deck.", ephemeral=True)
            return

        paging_view = CardPagingView(cards)
        embed, file_obj = paging_view.get_current_embed_and_file()
        kwargs = {"embed": embed, "view": paging_view}
        if file_obj:
            kwargs["files"] = [file_obj]
        await ctx.reply(**kwargs)
