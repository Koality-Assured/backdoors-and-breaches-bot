"""
Unit tests for DeckLoader and asset indexer.
"""

from pathlib import Path

import pytest

from bnb.deck_loader import DeckLoader
from bnb.models import CardType


@pytest.fixture(scope="module")
def loader():
    root = Path(__file__).resolve().parent.parent
    dl = DeckLoader(decks_dir=root / "decks")
    dl.load_all_decks()
    return dl


def test_deck_count(loader):
    decks = loader.list_decks()
    assert len(decks) == 10


def test_card_count_and_images(loader):
    all_cards = loader.get_all_cards()
    assert len(all_cards) == 571

    # Verify every card has a valid image path
    for card in all_cards:
        assert card.image_path is not None, f"Card {card.name} missing image path"
        assert Path(card.image_path).is_file(), f"Card {card.name} image {card.image_path} does not exist"


def test_deck_lookup(loader):
    deck = loader.get_deck("CoreV2.2")
    assert deck is not None
    assert deck.id == "CoreV2.2"

    # Lowercase lookup
    deck_lower = loader.get_deck("corev2.2")
    assert deck_lower is not None

    # Title lookup
    deck_title = loader.get_deck("Cloud Security Expansion")
    assert deck_title is not None
    assert deck_title.id == "CloudSecurity"


def test_deal_scenario(loader):
    scenario = loader.deal_scenario("CoreV2.2")
    assert len(scenario) == 4
    assert CardType.INITIAL in scenario
    assert CardType.PIVOT in scenario
    assert CardType.PERSIST in scenario
    assert CardType.C2 in scenario


def test_card_search(loader):
    results = loader.search_cards("phish")
    assert len(results) > 0
    assert any("phish" in c.name.lower() for c in results)

    # Filter by type
    proc_results = loader.search_cards("analysis", card_type=CardType.PROCEDURE)
    assert len(proc_results) > 0
    assert all(c.type == CardType.PROCEDURE for c in proc_results)
