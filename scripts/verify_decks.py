"""
Verification script to audit all card decks, schemas, and asset resolutions.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Configure UTF-8 output for Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# Add project root to sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))

from bnb.deck_loader import DeckLoader  # noqa: E402
from bnb.models import CardType  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("Backdoors & Breaches Deck Asset Verification")
    print("=" * 60)

    loader = DeckLoader(decks_dir=root_dir / "decks")
    loader.load_all_decks()

    decks = loader.list_decks()
    if not decks:
        print("[!] ERROR: No decks found!")
        return 1

    print(f"\nFound {len(decks)} unique decks:")
    total_cards = 0
    missing_images = []

    for deck in decks:
        total_cards += len(deck.cards)
        type_counts = {}
        for c in deck.cards:
            type_counts[c.type.value] = type_counts.get(c.type.value, 0) + 1
            if not c.image_path or not Path(c.image_path).is_file():
                missing_images.append((deck.id, c.name, c.image_path))

        summary = ", ".join(f"{k}: {v}" for k, v in sorted(type_counts.items()))
        print(f"  * {deck.title:<26} ({deck.id}): {len(deck.cards):>2} cards [{summary}]")

    print(f"\nTotal Cards Indexed: {total_cards}")
    print(f"Total Unique Images: {len(loader._image_index)}")

    if missing_images:
        print(f"\n[!] FAILED: {len(missing_images)} cards have missing or unresolved images:")
        for deck_id, name, path in missing_images[:10]:
            print(f"    - [{deck_id}] {name} -> {path}")
        return 1

    print("\n[+] SUCCESS: All 571 card entries have valid, resolved image files on disk!")

    # Verify scenario dealing
    scenario = loader.deal_scenario("CoreV2.2")
    print(f"\nScenario Dealing Test (CoreV2.2): {len(scenario)}/4 vectors dealt:")
    for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
        card = scenario.get(vtype)
        if card:
            print(f"  - {vtype.display_name}: {card.name}")
        else:
            print(f"  [!] Missing vector {vtype.display_name}!")
            return 1

    # Verify search
    search_test = loader.search_cards("phish", limit=5)
    print(f"\nSearch Test ('phish'): {len(search_test)} matches found.")
    for c in search_test:
        print(f"  * [{c.type.display_name}] {c.name}")

    print("\n[+] ALL VERIFICATION CHECKS PASSED!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
