"""
Data models and enumerations for the Backdoors & Breaches Discord bot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class CardType(str, Enum):
    """Types of cards in Backdoors & Breaches."""
    INITIAL = "initial"
    PIVOT = "pivot"
    PERSIST = "persist"
    C2 = "c2"
    PROCEDURE = "procedure"
    INJECT = "inject"
    CONSULTANT = "consultant"

    @classmethod
    def from_str(cls, value: str) -> CardType:
        """Parse card type string with alias normalization."""
        val = value.strip().lower()
        aliases = {
            "initial": cls.INITIAL,
            "initial compromise": cls.INITIAL,
            "initial_compromise": cls.INITIAL,
            "pivot": cls.PIVOT,
            "pivot & escalate": cls.PIVOT,
            "pivot and escalate": cls.PIVOT,
            "pivot_and_escalate": cls.PIVOT,
            "persist": cls.PERSIST,
            "persistence": cls.PERSIST,
            "c2": cls.C2,
            "c2 & exfil": cls.C2,
            "c2 and exfil": cls.C2,
            "c2_and_exfil": cls.C2,
            "command and control": cls.C2,
            "procedure": cls.PROCEDURE,
            "procedures": cls.PROCEDURE,
            "inject": cls.INJECT,
            "injects": cls.INJECT,
            "consultant": cls.CONSULTANT,
            "consultants": cls.CONSULTANT,
        }
        if val in aliases:
            return aliases[val]
        # Fallback to direct enum match if possible
        for item in cls:
            if item.value == val:
                return item
        raise ValueError(f"Unknown card type: {value}")

    @property
    def display_name(self) -> str:
        """Human-readable title for this card type."""
        names = {
            CardType.INITIAL: "Initial Compromise",
            CardType.PIVOT: "Pivot & Escalate",
            CardType.PERSIST: "Persistence",
            CardType.C2: "C2 & Exfiltration",
            CardType.PROCEDURE: "Procedure",
            CardType.INJECT: "Inject",
            CardType.CONSULTANT: "Consultant",
        }
        return names.get(self, self.value.capitalize())

    @property
    def emoji(self) -> str:
        """Discord emoji indicator for this card type."""
        emojis = {
            CardType.INITIAL: "🎯",
            CardType.PIVOT: "🔀",
            CardType.PERSIST: "⚓",
            CardType.C2: "📡",
            CardType.PROCEDURE: "🛠️",
            CardType.INJECT: "💉",
            CardType.CONSULTANT: "👔",
        }
        return emojis.get(self, "🃏")

    @property
    def embed_color(self) -> int:
        """Discord embed color (hex integer) matching physical card backings."""
        colors = {
            CardType.INITIAL: 0xDC2626,     # Red
            CardType.PIVOT: 0xF59E0B,       # Yellow / Gold
            CardType.PERSIST: 0x8B5CF6,     # Purple
            CardType.C2: 0x78350F,          # Brown
            CardType.PROCEDURE: 0x2563EB,   # Blue
            CardType.INJECT: 0x64748B,      # Grey / Slate
            CardType.CONSULTANT: 0x10B981,  # Green
        }
        return colors.get(self, 0x3B82F6)

    @property
    def is_attack_vector(self) -> bool:
        """Check if this card type is one of the 4 core attack vectors."""
        return self in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2)


@dataclass
class Card:
    """Represents an individual Backdoors & Breaches card."""
    id: str
    name: str
    type: CardType
    deck_id: str
    deck_title: str
    image_path: Optional[str] = None
    details: str = ""
    tools: str = ""
    documentation: str = ""
    detection: List[str] = field(default_factory=list)

    @property
    def clean_details(self) -> str:
        """Convert raw HTML tags in details to clean Discord markdown."""
        if not self.details:
            return ""

        text = self.details
        # Replace <li> tags with markdown bullets
        text = re.sub(r'<\s*li\s*>', '\n• ', text, flags=re.IGNORECASE)
        text = re.sub(r'<\s*/\s*li\s*>', '', text, flags=re.IGNORECASE)

        # Convert <a href="URL">TEXT</a> to [TEXT](URL)
        def replace_link(match):
            href = match.group(1).strip()
            label = match.group(2).strip() or href
            return f"[{label}]({href})"

        text = re.sub(
            r'<\s*a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)<\s*/\s*a\s*>',
            replace_link,
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )

        # Strip any other leftover HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Clean up excessive newlines and whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)


@dataclass
class Deck:
    """Represents a full deck or expansion pack."""
    id: str
    title: str
    link: Optional[str] = None
    revdate: Optional[str] = None
    cards: List[Card] = field(default_factory=list)

    def get_cards_by_type(self, card_type: CardType) -> List[Card]:
        """Filter cards in this deck by card type."""
        return [c for c in self.cards if c.type == card_type]

    def get_card_by_name(self, name: str) -> Optional[Card]:
        """Find card by case-insensitive name match."""
        name_clean = name.strip().lower()
        for c in self.cards:
            if c.name.lower() == name_clean:
                return c
        return None


@dataclass
class Player:
    """Represents a participant in a game."""
    user_id: int
    display_name: str
    hand: List[Card] = field(default_factory=list)
    consultants: List[Card] = field(default_factory=list)
    is_incident_master: bool = False


@dataclass
class ThreatSlot:
    """Represents one of the 4 attack vector slots in the active scenario."""
    category: CardType
    card: Card
    discovered: bool = False
    discovered_turn: Optional[int] = None
    discovered_by: Optional[str] = None
    mitigated: bool = False


class GamePhase(str, Enum):
    """Lifecycle phases of a B&B game."""
    LOBBY = "lobby"
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"
    ENDED = "ended"


@dataclass
class GameAction:
    """Audit log entry of an in-game action."""
    turn: int
    player_name: str
    action_type: str
    description: str
    roll: Optional[int] = None
    modifier: int = 0
    success: Optional[bool] = None
    card_name: Optional[str] = None


@dataclass
class PlayResult:
    """Comprehensive outcome of playing a procedure card."""
    success: bool
    natural_roll: int
    hand_bonus: int
    extra_modifiers: int
    total_roll: int
    is_nat_1: bool
    is_nat_20: bool
    card: Card
    target_vector: Optional[CardType]
    discovered_card: Optional[Card]
    inject_drawn: Optional[Card]
    message: str
    cooldown_turns: int = 0
