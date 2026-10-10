"""
Unit tests for data models and enumerations.
"""


from bnb.models import Card, CardType, Deck


def test_card_type_normalization():
    assert CardType.from_str("initial") == CardType.INITIAL
    assert CardType.from_str("initial compromise") == CardType.INITIAL
    assert CardType.from_str("initial_compromise") == CardType.INITIAL
    assert CardType.from_str("c2") == CardType.C2
    assert CardType.from_str("c2 and exfil") == CardType.C2
    assert CardType.from_str("pivot") == CardType.PIVOT
    assert CardType.from_str("persistence") == CardType.PERSIST
    assert CardType.from_str("procedure") == CardType.PROCEDURE
    assert CardType.from_str("inject") == CardType.INJECT
    assert CardType.from_str("consultant") == CardType.CONSULTANT


def test_card_type_properties():
    assert CardType.INITIAL.is_attack_vector is True
    assert CardType.PIVOT.is_attack_vector is True
    assert CardType.PERSIST.is_attack_vector is True
    assert CardType.C2.is_attack_vector is True
    assert CardType.PROCEDURE.is_attack_vector is False
    assert CardType.INJECT.is_attack_vector is False

    assert CardType.INITIAL.display_name == "Initial Compromise"
    assert CardType.C2.display_name == "C2 & Exfiltration"
    assert CardType.PROCEDURE.emoji == "🛠️"
    assert CardType.INJECT.emoji == "💉"
    assert isinstance(CardType.INITIAL.embed_color, int)


def test_card_clean_details_html_conversion():
    raw_html = '<li><a target="_blank" href="https://example.com/tool">Tool Analysis</a></li><li>Direct link: <a href="https://test.com">https://test.com</a></li>'
    card = Card(
        id="001",
        name="Test Card",
        type=CardType.PROCEDURE,
        deck_id="TestDeck",
        deck_title="Test Deck",
        details=raw_html,
    )
    cleaned = card.clean_details
    assert "[Tool Analysis](https://example.com/tool)" in cleaned
    assert "[https://test.com](https://test.com)" in cleaned
    assert "<" not in cleaned
    assert ">" not in cleaned
    assert "•" in cleaned


def test_deck_filtering():
    c1 = Card("1", "Phish", CardType.INITIAL, "core", "Core")
    c2 = Card("2", "Log Analysis", CardType.PROCEDURE, "core", "Core")
    c3 = Card("3", "Server Analysis", CardType.PROCEDURE, "core", "Core")
    deck = Deck("core", "Core Deck", cards=[c1, c2, c3])

    procs = deck.get_cards_by_type(CardType.PROCEDURE)
    assert len(procs) == 2
    assert deck.get_card_by_name("phish") == c1
    assert deck.get_card_by_name("nonexistent") is None
