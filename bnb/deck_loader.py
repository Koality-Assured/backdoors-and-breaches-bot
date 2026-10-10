"""
Deck loader, asset indexer, and card search engine for Backdoors & Breaches.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Dict, List, Optional

from bnb.models import Card, CardType, Deck

logger = logging.getLogger(__name__)


class DeckLoader:
    """Manages loading, indexing, image resolution, and querying of B&B decks."""

    def __init__(self, decks_dir: str | Path = "decks") -> None:
        self.decks_dir = Path(decks_dir)
        self.decks: Dict[str, Deck] = {}
        self._image_index: Dict[str, str] = {}
        self._cards_cache: List[Card] = []

    def load_all_decks(self) -> None:
        """Scan decks directory, index assets, and parse all card databases."""
        if not self.decks_dir.exists():
            logger.warning("Decks directory %s does not exist", self.decks_dir)
            return

        # 1. First pass: build global image filename index across all subdirectories
        self._index_all_images()

        # 2. Second pass: parse each deck directory
        self.decks.clear()
        self._cards_cache.clear()

        for item in sorted(self.decks_dir.iterdir()):
            if item.is_dir():
                carddb_path = item / "carddb.json"
                if carddb_path.is_file():
                    deck = self._load_deck(item.name, carddb_path, item)
                    if deck:
                        self.decks[deck.id] = deck
                        # Also allow lookup by slug or lowercase title
                        self.decks[deck.id.lower()] = deck
                        self._cards_cache.extend(deck.cards)

        # De-duplicate lowercase alias references for canonical counting
        unique_decks = {d.id: d for d in self.decks.values()}
        logger.info(
            "Loaded %d decks with %d total cards (%d unique images indexed)",
            len(unique_decks),
            len(self._cards_cache),
            len(self._image_index),
        )

    def _index_all_images(self) -> None:
        """Build a case-insensitive map of image filename -> absolute path."""
        self._image_index.clear()
        for root, _, files in os.walk(self.decks_dir):
            for f in files:
                if f.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                    self._image_index[f.lower()] = os.path.abspath(os.path.join(root, f))

    def _resolve_image(self, raw_path: str, deck_folder: Path) -> Optional[str]:
        """
        Resolve a card image using multi-tier fallback:
        1. Path relative to repo root (e.g. 'decks/CoreV2.2/image.png')
        2. Path relative to deck directory (e.g. 'BNB_CARDS_v2.2_CE-1-27.png')
        3. Global image filename index (resolves expansion packs referencing core cards)
        """
        if not raw_path:
            return None

        # 1. Direct path from project root
        direct_path = Path(raw_path)
        if direct_path.is_file():
            return str(direct_path.resolve())

        # 2. Local to deck folder
        local_path = deck_folder / Path(raw_path).name
        if local_path.is_file():
            return str(local_path.resolve())

        # 3. Global filename lookup
        base_name = Path(raw_path).name.lower()
        if base_name in self._image_index:
            return self._image_index[base_name]

        logger.debug("Could not resolve image for raw path %s in %s", raw_path, deck_folder)
        return None

    def _load_deck(self, deck_id: str, carddb_path: Path, deck_folder: Path) -> Optional[Deck]:
        """Parse a single deck's carddb.json file."""
        try:
            with open(carddb_path, "r", encoding="utf-8") as fp:
                data = json.load(fp)

            deck_title = data.get("title", deck_id)
            link = data.get("link")
            revdate = data.get("revdate")
            cards: List[Card] = []

            for entry in data.get("data", []):
                raw_type = entry.get("type", "")
                try:
                    card_type = CardType.from_str(raw_type)
                except ValueError:
                    logger.warning("Unknown card type '%s' in deck %s", raw_type, deck_id)
                    continue

                card_id = str(entry.get("id", len(cards) + 1))
                name = entry.get("name", "Unnamed Card").strip()
                raw_image = entry.get("image", "")
                image_path = self._resolve_image(raw_image, deck_folder)
                details = entry.get("details", "")

                card = Card(
                    id=card_id,
                    name=name,
                    type=card_type,
                    deck_id=deck_id,
                    deck_title=deck_title,
                    image_path=image_path,
                    details=details,
                )
                cards.append(card)

            return Deck(
                id=deck_id,
                title=deck_title,
                link=link,
                revdate=revdate,
                cards=cards,
            )
        except Exception as exc:
            logger.error("Failed to load deck %s from %s: %s", deck_id, carddb_path, exc)
            return None

    def get_deck(self, name_or_id: str) -> Optional[Deck]:
        """Look up deck by ID, alias, or title."""
        if not name_or_id:
            return None
        key = name_or_id.strip()
        if key in self.decks:
            return self.decks[key]
        if key.lower() in self.decks:
            return self.decks[key.lower()]
        for deck in self.list_decks():
            if deck.title.lower() == key.lower():
                return deck
        return None

    def list_decks(self) -> List[Deck]:
        """Return list of distinct loaded decks."""
        seen = set()
        unique = []
        for deck in self.decks.values():
            if deck.id not in seen:
                seen.add(deck.id)
                unique.append(deck)
        return sorted(unique, key=lambda d: d.title)

    def get_all_cards(self, deck_id: Optional[str] = None) -> List[Card]:
        """Get all cards, optionally filtered by deck ID."""
        if deck_id and deck_id.lower() != "all":
            deck = self.get_deck(deck_id)
            return deck.cards if deck else []
        return list(self._cards_cache)

    def get_card(self, name: str, deck_id: Optional[str] = None) -> Optional[Card]:
        """Find a card by exact or case-insensitive name."""
        cards = self.get_all_cards(deck_id)
        name_clean = name.strip().lower()
        for card in cards:
            if card.name.lower() == name_clean:
                return card
        return None

    def search_cards(
        self,
        query: str,
        deck_id: Optional[str] = None,
        card_type: Optional[CardType] = None,
        limit: int = 25,
    ) -> List[Card]:
        """Search cards by keyword across name, details, and type."""
        pool = self.get_all_cards(deck_id)
        if card_type:
            pool = [c for c in pool if c.type == card_type]

        query_clean = query.strip().lower()
        if not query_clean:
            return pool[:limit]

        matches: List[Card] = []
        for card in pool:
            if query_clean in card.name.lower() or query_clean in card.details.lower():
                matches.append(card)

        # Sort exact prefix/name matches first
        matches.sort(
            key=lambda c: (
                c.name.lower() != query_clean,
                not c.name.lower().startswith(query_clean),
                c.name,
            )
        )
        return matches[:limit]

    def get_random_card(
        self,
        card_type: Optional[CardType] = None,
        deck_id: Optional[str] = None,
    ) -> Optional[Card]:
        """Draw a random card, optionally filtered by type and deck."""
        pool = self.get_all_cards(deck_id)
        if card_type:
            pool = [c for c in pool if c.type == card_type]
        return random.choice(pool) if pool else None

    def deal_scenario(self, deck_id: Optional[str] = None) -> Dict[CardType, Card]:
        """
        Draw the 4 attack vectors for an incident scenario:
        1 Initial Compromise, 1 Pivot & Escalate, 1 Persistence, 1 C2 & Exfiltration.
        """
        pool = self.get_all_cards(deck_id)
        result: Dict[CardType, Card] = {}

        for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
            matching = [c for c in pool if c.type == vtype]
            if not matching and deck_id:
                # Fall back to global card pool if selected deck doesn't have this vector type
                matching = [c for c in self._cards_cache if c.type == vtype]
            if matching:
                result[vtype] = random.choice(matching)

        return result
