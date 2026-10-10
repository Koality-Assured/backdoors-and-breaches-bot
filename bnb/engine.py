"""
Core game engine and state machine for Backdoors & Breaches.
Decoupled from Discord I/O for clean testing and reliable state transitions.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Dict, List, Optional

from bnb.deck_loader import DeckLoader
from bnb.models import (
    Card,
    CardType,
    GameAction,
    GamePhase,
    Player,
    PlayResult,
    ThreatSlot,
)

logger = logging.getLogger(__name__)


class BnbGame:
    """Manages the full lifecycle and rules of an individual B&B session."""

    def __init__(
        self,
        channel_id: int,
        guild_id: int,
        incident_master_id: int,
        incident_master_name: str,
        deck_id: str = "CoreV2.2",
        max_turns: int = 10,
        inject_failure_threshold: int = 3,
    ) -> None:
        self.game_id = f"{channel_id}_{int(time.time())}"
        self.channel_id = channel_id
        self.guild_id = guild_id
        self.incident_master_id = incident_master_id
        self.incident_master_name = incident_master_name
        self.deck_id = deck_id
        self.max_turns = max_turns
        self.inject_failure_threshold = inject_failure_threshold

        self.phase: GamePhase = GamePhase.LOBBY
        self.turn: int = 0
        self.players: Dict[int, Player] = {}
        self.player_order: List[int] = []
        self.current_player_idx: int = 0

        self.threat_slots: Dict[CardType, ThreatSlot] = {}
        self.procedure_deck: List[Card] = []
        self.inject_deck: List[Card] = []
        self.consultant_deck: List[Card] = []
        self.discard_procedures: List[Card] = []
        self.active_injects: List[Card] = []

        self.cooldowns: Dict[str, int] = {}
        self.failed_roll_streak: int = 0
        self.active_modifiers: Dict[str, int] = {}
        self.history: List[GameAction] = []

        # Automatically add the Incident Master as a participant
        im_player = Player(
            user_id=incident_master_id,
            display_name=incident_master_name,
            is_incident_master=True,
        )
        self.players[incident_master_id] = im_player

    def add_player(self, user_id: int, display_name: str) -> bool:
        """Add a player to the game lobby."""
        if self.phase != GamePhase.LOBBY:
            return False
        if user_id in self.players:
            return False

        self.players[user_id] = Player(
            user_id=user_id,
            display_name=display_name,
            is_incident_master=(user_id == self.incident_master_id),
        )
        return True

    def remove_player(self, user_id: int) -> bool:
        """Remove a player from the game."""
        if user_id == self.incident_master_id:
            return False  # Cannot remove IM without ending game
        if user_id not in self.players:
            return False

        del self.players[user_id]
        if user_id in self.player_order:
            self.player_order.remove(user_id)
            if self.player_order and self.current_player_idx >= len(self.player_order):
                self.current_player_idx = 0
        return True

    def start_game(self, deck_loader: DeckLoader, hand_size: int = 4) -> bool:
        """
        Start the incident response exercise.
        Deals the 4 secret threat vectors, deals player hands, and initializes draw decks.
        """
        if self.phase != GamePhase.LOBBY:
            return False

        # 1. Deal the 4 attack vectors for the scenario
        scenario_cards = deck_loader.deal_scenario(self.deck_id)
        if len(scenario_cards) < 4:
            # Fall back to global if selected deck lacked all 4 types
            scenario_cards = deck_loader.deal_scenario(None)

        if len(scenario_cards) < 4:
            logger.error("Could not assemble all 4 attack vectors from deck %s", self.deck_id)
            return False

        self.threat_slots = {
            vtype: ThreatSlot(category=vtype, card=card)
            for vtype, card in scenario_cards.items()
        }

        # 2. Prepare procedure deck and inject deck
        all_procedures = [
            c for c in deck_loader.get_all_cards(self.deck_id)
            if c.type == CardType.PROCEDURE
        ]
        if not all_procedures:
            all_procedures = [
                c for c in deck_loader.get_all_cards(None)
                if c.type == CardType.PROCEDURE
            ]
        random.shuffle(all_procedures)

        all_injects = [
            c for c in deck_loader.get_all_cards(self.deck_id)
            if c.type == CardType.INJECT
        ]
        if not all_injects:
            all_injects = [
                c for c in deck_loader.get_all_cards(None)
                if c.type == CardType.INJECT
            ]
        random.shuffle(all_injects)
        self.inject_deck = all_injects

        all_consultants = [
            c for c in deck_loader.get_all_cards(self.deck_id)
            if c.type == CardType.CONSULTANT
        ]
        random.shuffle(all_consultants)
        self.consultant_deck = all_consultants

        # 3. Determine player turn order (Defenders take turns. If only IM is playing, IM takes turns.)
        defenders = [p for p in self.players.values() if not p.is_incident_master]
        if defenders:
            self.player_order = [p.user_id for p in defenders]
        else:
            self.player_order = [self.incident_master_id]

        # 4. Deal hands to participants in turn order
        for uid in self.player_order:
            player = self.players[uid]
            player.hand.clear()
            for _ in range(hand_size):
                if all_procedures:
                    player.hand.append(all_procedures.pop(0))

        self.procedure_deck = all_procedures

        # 5. Initialize turn state
        self.phase = GamePhase.IN_PROGRESS
        self.turn = 1
        self.current_player_idx = 0
        self.failed_roll_streak = 0
        self.cooldowns.clear()
        self.active_injects.clear()

        self._record_action(
            turn=1,
            player_name=self.incident_master_name,
            action_type="start_game",
            description=f"Incident response started with {len(self.player_order)} defenders.",
        )
        return True

    def get_current_player(self) -> Optional[Player]:
        """Return the player whose turn it currently is."""
        if not self.player_order or self.phase != GamePhase.IN_PROGRESS:
            return None
        uid = self.player_order[self.current_player_idx]
        return self.players.get(uid)

    def is_card_on_cooldown(self, card_name: str) -> bool:
        """Check if a procedure card is currently on cooldown."""
        expire_turn = self.cooldowns.get(card_name.strip().lower(), 0)
        return expire_turn >= self.turn

    def play_procedure(
        self,
        user_id: int,
        card_name: str,
        target_category: Optional[CardType] = None,
        d20_roll: Optional[int] = None,
        manual_modifier: int = 0,
    ) -> PlayResult:
        """
        Execute a procedure action:
        - Validates turn and cooldown.
        - Calculates hand bonus (+3 if in hand) and modifiers.
        - Rolls d20 (or accepts forced roll for testing).
        - Handles Nat 1 (Inject trigger), Nat 20 (Auto-success), Success (11+), and Failure.
        - Evaluates attack vector discovery.
        - Checks win/loss conditions.
        - Advances turn.
        """
        if self.phase != GamePhase.IN_PROGRESS:
            raise ValueError("No game is currently in progress.")

        curr_player = self.get_current_player()
        if not curr_player or curr_player.user_id != user_id:
            raise PermissionError("It is not your turn.")

        card_name_clean = card_name.strip()
        card_key = card_name_clean.lower()

        if self.is_card_on_cooldown(card_key):
            raise ValueError(f"'{card_name_clean}' is on cooldown until turn {self.cooldowns[card_key] + 1}.")

        # Find the card either in player's hand or in procedure deck/discards
        card_obj: Optional[Card] = None
        hand_bonus = 0

        for i, c in enumerate(curr_player.hand):
            if c.name.lower() == card_key:
                card_obj = curr_player.hand.pop(i)
                hand_bonus = 3
                # Refill hand from draw pile if available
                if self.procedure_deck:
                    curr_player.hand.append(self.procedure_deck.pop(0))
                break

        if not card_obj:
            # Card played from common pool / procedures list
            for c in self.procedure_deck:
                if c.name.lower() == card_key:
                    card_obj = c
                    break

        if not card_obj:
            # Check threat or any known card
            card_obj = Card(
                id="proc-custom",
                name=card_name_clean,
                type=CardType.PROCEDURE,
                deck_id=self.deck_id,
                deck_title="Custom Procedure",
            )

        # Roll the d20
        natural_roll = d20_roll if d20_roll is not None else random.randint(1, 20)
        extra_modifiers = manual_modifier + sum(self.active_modifiers.values())
        total_roll = natural_roll + hand_bonus + extra_modifiers

        is_nat_1 = natural_roll == 1
        is_nat_20 = natural_roll == 20

        success = False
        discovered_card: Optional[Card] = None
        inject_drawn: Optional[Card] = None
        cooldown_turns = 0
        message = ""

        if is_nat_1:
            # Critical failure: triggers inject, card on cooldown
            success = False
            cooldown_turns = 3
            self.cooldowns[card_key] = self.turn + cooldown_turns
            self.failed_roll_streak += 1
            inject_drawn = self.draw_inject()
            message = f"🚨 Critical Failure (Natural 1)! An Inject was triggered: **{inject_drawn.name}**."

        elif is_nat_20 or total_roll >= 11:
            # Success!
            success = True
            self.failed_roll_streak = 0

            # Determine vector discovery
            discovered_slot = self._attempt_discover_vector(target_category, card_obj, curr_player)
            if discovered_slot:
                discovered_card = discovered_slot.card
                crit_prefix = "🌟 Critical Success (Natural 20)! " if is_nat_20 else "✅ Success! "
                message = f"{crit_prefix}Discovered **{discovered_slot.category.display_name}**: **{discovered_card.name}**!"
            else:
                crit_prefix = "🌟 Critical Success (Natural 20)! " if is_nat_20 else "✅ Success! "
                message = f"{crit_prefix}Procedure succeeded, but the targeted attack vector was already discovered or not present."

        else:
            # Normal failure
            success = False
            cooldown_turns = 2
            self.cooldowns[card_key] = self.turn + cooldown_turns
            self.failed_roll_streak += 1

            if self.failed_roll_streak >= self.inject_failure_threshold:
                self.failed_roll_streak = 0
                inject_drawn = self.draw_inject()
                message = f"❌ Roll failed ({total_roll} < 11). Failed streak reached threshold! Inject drawn: **{inject_drawn.name}**."
            else:
                remaining_fails = self.inject_failure_threshold - self.failed_roll_streak
                message = f"❌ Roll failed ({total_roll} < 11). Card is on cooldown for 2 turns. ({remaining_fails} more failed rolls until an Inject)."

        # Record action in game history
        self._record_action(
            turn=self.turn,
            player_name=curr_player.display_name,
            action_type="play_procedure",
            description=message,
            roll=natural_roll,
            modifier=hand_bonus + extra_modifiers,
            success=success,
            card_name=card_obj.name,
        )

        # Check win or defeat conditions
        self._evaluate_game_completion()

        # If game is still running, advance turn
        if self.phase == GamePhase.IN_PROGRESS:
            self._advance_turn()

        return PlayResult(
            success=success,
            natural_roll=natural_roll,
            hand_bonus=hand_bonus,
            extra_modifiers=extra_modifiers,
            total_roll=total_roll,
            is_nat_1=is_nat_1,
            is_nat_20=is_nat_20,
            card=card_obj,
            target_vector=target_category,
            discovered_card=discovered_card,
            inject_drawn=inject_drawn,
            message=message,
            cooldown_turns=cooldown_turns,
        )

    def _attempt_discover_vector(
        self,
        target_category: Optional[CardType],
        card: Card,
        player: Player,
    ) -> Optional[ThreatSlot]:
        """Resolve which threat vector is discovered by this procedure."""
        if target_category and target_category in self.threat_slots:
            slot = self.threat_slots[target_category]
            if not slot.discovered:
                slot.discovered = True
                slot.discovered_turn = self.turn
                slot.discovered_by = player.display_name
                return slot
            return None

        # If no specific category targeted, discover the first undiscovered vector
        for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
            if vtype in self.threat_slots:
                slot = self.threat_slots[vtype]
                if not slot.discovered:
                    slot.discovered = True
                    slot.discovered_turn = self.turn
                    slot.discovered_by = player.display_name
                    return slot

        return None

    def draw_inject(self) -> Card:
        """Draw an inject card from the deck and add to active injects."""
        if not self.inject_deck:
            fallback = Card(
                id="inj-fallback",
                name="System Instability",
                type=CardType.INJECT,
                deck_id=self.deck_id,
                deck_title="Emergency Injects",
                details="A sudden system glitch occurs, complicating the investigation.",
            )
            self.active_injects.append(fallback)
            return fallback

        card = self.inject_deck.pop(0)
        self.active_injects.append(card)
        return card

    def manual_reveal_vector(self, category: CardType, revealed_by: str) -> Optional[Card]:
        """Allow Incident Master to manually reveal a threat vector."""
        if category in self.threat_slots:
            slot = self.threat_slots[category]
            slot.discovered = True
            slot.discovered_turn = self.turn
            slot.discovered_by = revealed_by
            self._evaluate_game_completion()
            return slot.card
        return None

    def pass_turn(self, user_id: int) -> bool:
        """Pass turn to next player without taking an action."""
        if self.phase != GamePhase.IN_PROGRESS:
            return False
        curr_player = self.get_current_player()
        if not curr_player or curr_player.user_id != user_id:
            return False

        self._record_action(
            turn=self.turn,
            player_name=curr_player.display_name,
            action_type="pass",
            description=f"{curr_player.display_name} passed their turn.",
        )
        self._advance_turn()
        return True

    def _advance_turn(self) -> None:
        """Rotate turn to next player and update round number and cooldowns."""
        if not self.player_order:
            return

        self.current_player_idx = (self.current_player_idx + 1) % len(self.player_order)
        # When wrapping back to first player, advance global round/turn
        if self.current_player_idx == 0:
            self.turn += 1

        # Expire expired cooldowns
        expired = [c for c, exp in self.cooldowns.items() if exp < self.turn]
        for c in expired:
            del self.cooldowns[c]

        # Check turn limit
        if self.turn > self.max_turns and self.phase == GamePhase.IN_PROGRESS:
            self.phase = GamePhase.DEFEAT
            self._record_action(
                turn=self.turn,
                player_name="System",
                action_type="game_over",
                description="Turn limit reached! Attackers successfully completed their objectives.",
            )

    def _evaluate_game_completion(self) -> None:
        """Check if all threat vectors are discovered."""
        if not self.threat_slots:
            return

        all_discovered = all(slot.discovered for slot in self.threat_slots.values())
        if all_discovered and self.phase == GamePhase.IN_PROGRESS:
            self.phase = GamePhase.VICTORY
            self._record_action(
                turn=self.turn,
                player_name="System",
                action_type="victory",
                description="All attack vectors uncovered! Defenders successfully mitigated the incident!",
            )

    def end_game(self, reason: str = "Manually ended") -> None:
        """End the game session immediately."""
        self.phase = GamePhase.ENDED
        self._record_action(
            turn=self.turn,
            player_name="Incident Master",
            action_type="end_game",
            description=f"Game ended: {reason}",
        )

    def _record_action(
        self,
        turn: int,
        player_name: str,
        action_type: str,
        description: str,
        roll: Optional[int] = None,
        modifier: int = 0,
        success: Optional[bool] = None,
        card_name: Optional[str] = None,
    ) -> None:
        self.history.append(
            GameAction(
                turn=turn,
                player_name=player_name,
                action_type=action_type,
                description=description,
                roll=roll,
                modifier=modifier,
                success=success,
                card_name=card_name,
            )
        )


class GameManager:
    """Manages active games across Discord channels and servers."""

    def __init__(self) -> None:
        self.games: Dict[int, BnbGame] = {}

    def get_game(self, channel_id: int) -> Optional[BnbGame]:
        """Get active game for the given channel."""
        return self.games.get(channel_id)

    def create_game(
        self,
        channel_id: int,
        guild_id: int,
        incident_master_id: int,
        incident_master_name: str,
        deck_id: str = "CoreV2.2",
        max_turns: int = 10,
        inject_failure_threshold: int = 3,
    ) -> BnbGame:
        """Create and register a new game session in this channel."""
        game = BnbGame(
            channel_id=channel_id,
            guild_id=guild_id,
            incident_master_id=incident_master_id,
            incident_master_name=incident_master_name,
            deck_id=deck_id,
            max_turns=max_turns,
            inject_failure_threshold=inject_failure_threshold,
        )
        self.games[channel_id] = game
        return game

    def delete_game(self, channel_id: int) -> Optional[BnbGame]:
        """Remove a game session."""
        return self.games.pop(channel_id, None)

    def find_game_by_user(self, user_id: int) -> Optional[BnbGame]:
        """Find the active game a specific user is participating in."""
        for game in self.games.values():
            if user_id in game.players and game.phase in (GamePhase.LOBBY, GamePhase.IN_PROGRESS):
                return game
        return None
