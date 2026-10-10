"""
Unit tests for BnbGame engine and state transitions.
"""

from pathlib import Path

import pytest

from bnb.deck_loader import DeckLoader
from bnb.engine import BnbGame, GameManager
from bnb.models import CardType, GamePhase


@pytest.fixture(scope="module")
def loader():
    root = Path(__file__).resolve().parent.parent
    dl = DeckLoader(decks_dir=root / "decks")
    dl.load_all_decks()
    return dl


@pytest.fixture
def new_game(loader):
    game = BnbGame(
        channel_id=1001,
        guild_id=2001,
        incident_master_id=999,
        incident_master_name="IncidentMaster",
        deck_id="CoreV2.2",
        max_turns=5,
        inject_failure_threshold=3,
    )
    game.add_player(101, "Alice")
    game.add_player(102, "Bob")
    return game


def test_game_creation_and_lobby(new_game):
    assert new_game.phase == GamePhase.LOBBY
    assert len(new_game.players) == 3  # IM + Alice + Bob
    assert 101 in new_game.players
    assert 102 in new_game.players


def test_game_start(new_game, loader):
    started = new_game.start_game(loader, hand_size=4)
    assert started is True
    assert new_game.phase == GamePhase.IN_PROGRESS
    assert new_game.turn == 1
    assert len(new_game.threat_slots) == 4

    # Player turn order should be Alice then Bob
    assert new_game.player_order == [101, 102]
    curr_player = new_game.get_current_player()
    assert curr_player.user_id == 101
    assert len(curr_player.hand) == 4


def test_play_turn_validation(new_game, loader):
    new_game.start_game(loader)
    # Bob tries to play on Alice's turn
    with pytest.raises(PermissionError):
        new_game.play_procedure(user_id=102, card_name="Server Analysis")


def test_play_natural_1_critical_failure(new_game, loader):
    new_game.start_game(loader)
    alice = new_game.get_current_player()
    card_name = alice.hand[0].name

    # Force a d20 roll of 1
    result = new_game.play_procedure(
        user_id=alice.user_id,
        card_name=card_name,
        d20_roll=1,
    )
    assert result.is_nat_1 is True
    assert result.success is False
    assert result.inject_drawn is not None
    assert new_game.is_card_on_cooldown(card_name) is True


def test_play_natural_20_critical_success(new_game, loader):
    new_game.start_game(loader)
    alice = new_game.get_current_player()
    card_name = alice.hand[0].name

    # Force a d20 roll of 20 targeting Initial Compromise
    result = new_game.play_procedure(
        user_id=alice.user_id,
        card_name=card_name,
        target_category=CardType.INITIAL,
        d20_roll=20,
    )
    assert result.is_nat_20 is True
    assert result.success is True
    assert result.discovered_card is not None
    assert new_game.threat_slots[CardType.INITIAL].discovered is True


def test_failed_streak_inject_trigger(new_game, loader):
    new_game.start_game(loader)
    alice = new_game.get_current_player()

    # Roll 2 (total = 2 + 3 = 5 < 11 -> Failure 1)
    res1 = new_game.play_procedure(alice.user_id, alice.hand[0].name, d20_roll=2)
    assert res1.success is False
    assert res1.inject_drawn is None
    assert new_game.failed_roll_streak == 1

    # Next player is Bob
    bob = new_game.get_current_player()
    assert bob.user_id == 102
    # Roll 2 -> Failure 2
    res2 = new_game.play_procedure(bob.user_id, bob.hand[0].name, d20_roll=2)
    assert res2.success is False
    assert res2.inject_drawn is None
    assert new_game.failed_roll_streak == 2

    # Round advances back to Alice
    alice = new_game.get_current_player()
    assert alice.user_id == 101
    # Roll 2 -> Failure 3 -> Streak reaches 3 -> Inject drawn!
    res3 = new_game.play_procedure(alice.user_id, alice.hand[0].name, d20_roll=2)
    assert res3.success is False
    assert res3.inject_drawn is not None
    assert new_game.failed_roll_streak == 0


def test_victory_condition(new_game, loader):
    new_game.start_game(loader)
    # Manually uncover all 4 vectors
    for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
        new_game.manual_reveal_vector(vtype, revealed_by="Test")

    assert new_game.phase == GamePhase.VICTORY


def test_defeat_by_turn_limit(new_game, loader):
    new_game.start_game(loader)
    new_game.max_turns = 1

    # Round 1: Alice passes, Bob passes -> advances to round 2 > max_turns
    alice = new_game.get_current_player()
    new_game.pass_turn(alice.user_id)

    bob = new_game.get_current_player()
    new_game.pass_turn(bob.user_id)

    assert new_game.phase == GamePhase.DEFEAT


def test_game_manager():
    gm = GameManager()
    g1 = gm.create_game(101, 1, 999, "IM1")
    assert gm.get_game(101) == g1

    g_user = gm.find_game_by_user(999)
    assert g_user == g1

    gm.delete_game(101)
    assert gm.get_game(101) is None
