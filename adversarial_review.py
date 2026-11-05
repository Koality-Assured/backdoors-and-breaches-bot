#!/usr/bin/env python3
"""Adversarial Security, Quality & Deck Integrity Auditor for Koality-Assured/backdoors-and-breaches-bot.

Performs strict adversarial validation across the repository:
1. Zero-Leak Cryptographic Hash Scan: Scans every token and word across every file against
   cryptographic SHA-256 hashes of private identifiers (account IDs, company names,
   internal project codenames, domains, usernames). Hashing these targets guarantees the audit
   script itself does not expose sensitive strings in a public repository.
2. Pattern Leak Scan: Verifies zero local Windows paths, user profiles, or live secret tokens
   (Discord bot tokens, AWS keys, GitHub PATs).
3. Card Database & Deck Integrity Verification: Ensures all 10 card expansions exist, parse
   valid JSON schemas, maintain 100% asset resolution across all 571 cards, and correctly
   deal 4-vector incident scenarios.
4. Syntax & Type Integrity: Validates 100% clean AST compilation and syntax parsing across all
   Python, JSON, YAML, and TOML files in the repository.
5. Pytest Execution: Runs the comprehensive automated test suite and guarantees a 100% pass rate.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml

# SHA-256 hashes of private identifiers that MUST NOT appear anywhere in the codebase.
# Hashing these ensures the public repository does not leak the target values via the audit script itself.
FORBIDDEN_HASHES: Dict[str, str] = {
    # Real AWS account IDs
    "55ebcead5a2750f58cfa1f2666b939fb2782cdef463f7d35144b811dd2c1f739": "AWS Account Hash 077***",
    "aadaec0bf561fb47bc268441f4477f3b9a1ae27f8a80230accb1ef75616f05cf": "AWS Account Hash 682***",
    "91063785aca71cc0aae154589a2e5f8dc086a337c0de1849d8b848dd019f2f53": "AWS Account Hash 026***",
    "1a4cf100217328d19912869af7ce6a4045adf469fecef3600dfa123c4fe202da": "AWS Account Hash 660***",
    "1d21eb187ae938d6cfa49d94a3b108cfeea3a52446e9864d0671048ce056330f": "AWS Account Hash 057***",
    "7eb1bc27dcd577dbbc76d13c5d43a99ef36b504774ea40031e1a67779b2d4f4e": "AWS Account Hash 648***",
    "972765e0abf03b1c64247aa61112ee6aab2bb913662b28e4cd41197ff729bf17": "AWS Account Hash 688***",
    "464d7afe5f1a8cb05904876a78ef3685c9da0d6df4dbf7125149cfab3070be10": "AWS Account Hash 412***",
    "30ef74ab87e1792ba845a0779a464c7fdc4cd3342d7e77b5d174709c7bb300ed": "AWS Account Hash 961***",
    "41ccd800b3930140e049364aaa9a532eb8f7359d96008e9651acd29b8fddb76e": "AWS Account Hash 450***",
    "dab08fbe1577b214e0e423483f01649c268b713e42f3c08de39825eab5a377a5": "AWS Account Hash 629***",
    "0856e9cd8993ed12c08c536039bff5044e6de2e9f73a26b9e8fc969036b605f0": "AWS Account Hash 673***",
    "89a8ab0a9bd79161a59a21b33d334a6755a66dcb97771557c6d1f784c52450b8": "AWS Account Hash 992***",
    "3f5cfd1a08073e1dcee48f77aa71be728b85625dc347d4c6a8fdbf73dd0d87aa": "AWS Account Hash 135***",
    "944db6fb3568c0722241cfd1ffc4fa315aa6f51cb7e42d72f9d77eb55620857a": "AWS Account Hash 038***",

    # Proprietary corporate entities & identifiers
    "cf7d21665b5498c0123f7512cc407ac574d8249c70f4174d0edfbfab713f9af7": "Entity Name Hash tak***",
    "7626518e064a333ced98412bdf9aadbf42e333e0084fed078d16a3b4c0b5cffc": "Entity Name Hash tak***",
    "de69cd742264d4e3fbc8b95df35e2e96d5d68ae763119019b97c1fec6c281b0d": "Org Name Hash 2k-***",
    "93ac07d758d5634824a161b417f614a12d6078323bf0933335306ae81e5f2439": "Org Name Hash 2ks***",
    "7b2faf5774f12d731ad15adec005d73bcacab03d17b698e0745723beadeda744": "Domain Name Hash 2k.***",
    "b1837abd75fdbc571e8da42402afc6b09bdfb4f2fec78d56e95fb24ac9682a2e": "Project Hash aut***",
    "189c75f4c97ee38ea13c0892361a676141a31a748a79db2a0738c07e46a242b4": "Project Hash pix***",
    "7904791f9bb496a3354bf75641e45feb31e881a00cebcb2508e45bd942a6e430": "Project Hash fra***",
    "993fc867ac79d748c13a4ffbe2b2f4555327de8381611dd3865cfe76e899fce6": "Project Hash sym***",
    "f6828ddd9713116e4ee6d04c12f0ecdcbd9e5499755aca87c345cb600ca8dded": "Project Hash dat***",
    "79b23bf9e922d02169cabc6ee5cbe6bfe45cdd67c7cb4f0fdbd4dff17dd87d31": "Domain Hash aws***",
    "318099ac47f991dbcc87b6816a1c0f8b572b6bf9eaa5e4fa8bafbfbee4698dab": "Directory Identifier Hash d-9***",
    "c8f0007fe810b14c194165603bb97ae66cc651a540131464b52044810237e19f": "User Name Hash rob***",
    "8584dc7e2241cf89ebefd95e783688126ab56ec94589d980309995180cb96174": "Email Hash rob***@2k.***",
}

# Forbidden regex patterns: local Windows developer paths, external drives, live API tokens
FORBIDDEN_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r'c:[\\/]users[\\/]', re.IGNORECASE), "Local Windows User Profile Path"),
    (re.compile(r'c:[\\/]code[\\/](?!ka[\\/]|ka$)', re.IGNORECASE), "Local Non-KA Source Code Path"),
    (re.compile(r'[d-z]:[\\/]code', re.IGNORECASE), "Non-standard Local Drive Source Path"),
    (re.compile(r'\b[MN][A-Za-z\d]{23}\.[\w-]{6}\.[\w-]{27,}\b'), "Live Discord Bot Token"),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "AWS Access Key ID"),
    (re.compile(r'\bghp_[a-zA-Z0-9]{36}\b'), "GitHub Personal Access Token"),
]

EXPECTED_DECKS: List[str] = [
    "CloudSecurity",
    "CoreV1",
    "CoreV2.1",
    "CoreV2.2",
    "CoreV2.2-Expansion",
    "DenSecure",
    "Huntress",
    "ICS-OT",
    "RedCanary",
    "Trimarc",
]

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT))


def audit_cryptographic_and_pattern_leaks() -> List[Tuple[str, str]]:
    """Scan all non-binary repository files for forbidden cryptographic hashes and regex patterns."""
    findings: List[Tuple[str, str]] = []
    token_pattern = re.compile(r'[\w\.-]+')

    skip_dirs: Set[str] = {
        ".git",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
    }
    skip_extensions: Set[str] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pyc",
    }

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for f in files:
            if f in ("adversarial_review.py",):
                continue
            if any(f.lower().endswith(ext) for ext in skip_extensions):
                continue

            fp = Path(root) / f
            rel = fp.relative_to(REPO_ROOT)

            try:
                content = fp.read_text(encoding="utf-8", errors="ignore")

                # 1. Regex pattern check
                for pat, label in FORBIDDEN_PATTERNS:
                    if pat.search(content):
                        findings.append((str(rel), f"Pattern Violation: {label}"))

                # 2. SHA-256 token hash check
                tokens = set(token_pattern.findall(content.lower()))
                for token in tokens:
                    thash = hashlib.sha256(token.encode("utf-8")).hexdigest()
                    if thash in FORBIDDEN_HASHES:
                        findings.append((str(rel), f"Cryptographic Match: {FORBIDDEN_HASHES[thash]}"))

            except Exception as e:
                findings.append((str(rel), f"File read error: {e}"))

    return findings


def audit_deck_integrity() -> Tuple[List[str], Dict[str, int]]:
    """Verify card database JSON schemas, asset resolutions, and game scenario deal integrity."""
    from bnb.deck_loader import DeckLoader
    from bnb.models import CardType

    errors: List[str] = []
    stats: Dict[str, int] = {
        "decks": 0,
        "cards": 0,
        "images": 0,
    }

    loader = DeckLoader(decks_dir=REPO_ROOT / "decks")
    loader.load_all_decks()

    decks = loader.list_decks()
    stats["decks"] = len(decks)
    stats["images"] = len(loader._image_index)

    # 1. Verify all 10 expected expansions are loaded
    loaded_deck_ids = {d.id for d in decks}
    for expected in EXPECTED_DECKS:
        if expected not in loaded_deck_ids:
            errors.append(f"Missing required expansion deck: '{expected}'")

    # 2. Verify total card count across all decks
    total_cards = sum(len(d.cards) for d in decks)
    stats["cards"] = total_cards
    if total_cards != 571:
        errors.append(f"Expected 571 total cards across 10 expansions, found: {total_cards}")

    # 3. Verify every card has valid schema, valid type, and resolved image on disk
    missing_assets = 0
    for d in decks:
        for card in d.cards:
            if not card.name or not card.name.strip():
                errors.append(f"Deck '{d.id}' contains card with empty name: {card.id}")
            if not isinstance(card.type, CardType):
                errors.append(f"Deck '{d.id}' card '{card.name}' has invalid type: {card.type}")
            if not card.image_path or not Path(card.image_path).is_file():
                missing_assets += 1
                if missing_assets <= 5:
                    errors.append(f"Deck '{d.id}' card '{card.name}' image missing: {card.image_path}")

    if missing_assets > 5:
        errors.append(f"... and {missing_assets - 5} additional missing card images.")

    # 4. Verify scenario dealing mechanism (Initial, Pivot, Persist, C2)
    scenario = loader.deal_scenario("CoreV2.2")
    if len(scenario) != 4:
        errors.append(f"CoreV2.2 scenario deal produced {len(scenario)}/4 vectors")
    for vtype in (CardType.INITIAL, CardType.PIVOT, CardType.PERSIST, CardType.C2):
        if vtype not in scenario:
            errors.append(f"Scenario dealing failed to generate vector: {vtype.display_name}")

    return errors, stats


def audit_syntax_and_types() -> List[Tuple[str, str]]:
    """Validate AST compilation for Python, JSON, YAML, and TOML configurations."""
    errors: List[Tuple[str, str]] = []
    skip_dirs = {".git", ".pytest_cache", ".ruff_cache", "__pycache__", "node_modules", "venv", ".venv"}

    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for f in files:
            fp = Path(root) / f
            rel = fp.relative_to(REPO_ROOT)

            # Python syntax & AST validation
            if f.endswith(".py"):
                try:
                    content = fp.read_text(encoding="utf-8")
                    ast.parse(content, filename=str(fp))
                except Exception as e:
                    errors.append((str(rel), f"Python Syntax Error: {e}"))

            # JSON validation
            elif f.endswith(".json") and not f.endswith("package-lock.json"):
                try:
                    with open(fp, "r", encoding="utf-8") as jf:
                        json.load(jf)
                except Exception as e:
                    errors.append((str(rel), f"JSON Parse Error: {e}"))

            # YAML validation
            elif f.endswith((".yaml", ".yml")):
                try:
                    with open(fp, "r", encoding="utf-8") as yf:
                        yaml.safe_load(yf)
                except Exception as e:
                    errors.append((str(rel), f"YAML Parse Error: {e}"))

            # TOML validation
            elif f.endswith(".toml"):
                try:
                    with open(fp, "rb") as tf:
                        tomllib.load(tf)
                except Exception as e:
                    errors.append((str(rel), f"TOML Parse Error: {e}"))

    return errors


def audit_pytest_execution() -> Tuple[bool, str]:
    """Execute pytest to ensure 100% test pass rate across the test suite."""
    cmd = [sys.executable, "-m", "pytest", "-v", "--tb=short", "tests/"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        passed = proc.returncode == 0
        output = proc.stdout if passed else proc.stdout + "\n" + proc.stderr
        return passed, output
    except Exception as e:
        return False, f"Failed to execute pytest: {e}"


def main() -> int:
    print("=" * 80)
    print(" ADVERSARIAL SECURITY, HYGIENE & DECK AUDITOR")
    print(" Koality-Assured / backdoors-and-breaches-bot")
    print("=" * 80)

    # 1. Zero-Leak Cryptographic & Pattern Scan
    print("\n[Phase 1] Executing Zero-Leak Cryptographic Hash & Pattern Leak Scan...")
    leaks = audit_cryptographic_and_pattern_leaks()
    if leaks:
        print(f"  [FAIL] Detected {len(leaks)} sensitive pattern / cryptographic hash violations:")
        for rel, term in leaks:
            print(f"    - {rel}: {term}")
    else:
        print("  [PASS] Cryptographic scan verified 0 company identifiers, user profiles, or secret tokens.")

    # 2. Card Database & Deck Integrity Verification
    print("\n[Phase 2] Verifying 10 Expansions & 571 Card Assets...")
    deck_errors, stats = audit_deck_integrity()
    if deck_errors:
        print(f"  [FAIL] Encountered {len(deck_errors)} deck / card asset validation errors:")
        for err in deck_errors:
            print(f"    - {err}")
    else:
        print(
            f"  [PASS] 100% asset resolution: {stats['decks']} decks, {stats['cards']} cards, "
            f"and {stats['images']} images validated successfully."
        )

    # 3. Syntax & Schema Validation
    print("\n[Phase 3] Validating AST Syntax across Python, JSON, YAML, and TOML files...")
    syntax_errors = audit_syntax_and_types()
    if syntax_errors:
        print(f"  [FAIL] Found {len(syntax_errors)} syntax compilation errors:")
        for rel, err in syntax_errors:
            print(f"    - {rel}: {err}")
    else:
        print("  [PASS] 100% of Python, JSON, YAML, and TOML files parsed with zero syntax errors.")

    # 4. Pytest Execution
    print("\n[Phase 4] Executing Comprehensive Pytest Test Suite...")
    tests_passed, test_output = audit_pytest_execution()
    if not tests_passed:
        print("  [FAIL] Pytest test suite reported failures:")
        print(test_output)
    else:
        # Extract summary line (e.g., '20 passed in 0.19s')
        summary_line = "All unit tests passed"
        for line in reversed(test_output.splitlines()):
            if "passed in" in line:
                summary_line = line.strip("= ")
                break
        print(f"  [PASS] Test suite verified: {summary_line}")

    # Final Verdict
    print("\n" + "=" * 80)
    has_failures = bool(leaks or deck_errors or syntax_errors or not tests_passed)
    if has_failures:
        print(" ADVERSARIAL AUDIT STATUS: FAILED (Violations detected)")
        print("=" * 80)
        return 1

    print(" ADVERSARIAL AUDIT STATUS: ALL CHECKS PASSED (Zero Violations, Merge Ready)")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    sys.exit(main())
