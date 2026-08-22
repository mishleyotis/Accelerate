"""One sub-vertical, one name, wherever a reader meets it.

REPORTED 2026-08-19: "I still see CU on the clients page as well as at the
header of the Logix Page instead of Credit Union."

The directory built its own name table keyed `SV1`..`SV9` and fell back to the
RAW stored value when a key missed. Logix's stored sub_vertical is the bare
string `CU`, so the table produced `{"CU": "CU"}` — a label that is the code —
and the browser's own table, which knew `CU` meant Credit Unions, was
overwritten by it. Baxter's row says `SV2`, which that table happened to know.
One corpus, one kind of institution, two names on two pages.

Three name tables existed for one fact: the directory's, the connector's
(lower-case, written for prose) and the browser's (a third key space). The
resolver that already reads 61 corpus spellings now decides the label too.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.subverticals import (  # noqa: E402
    SUBVERTICAL_CODES, SUBVERTICAL_DISPLAY, UNKNOWN_SUBVERTICAL,
    display_name, resolve_subvertical,
)


def test_the_bare_code_gets_a_name_not_itself():
    """The exact reported defect."""
    assert display_name("CU") == ("CU", "Credit Unions")


def test_every_spelling_this_corpus_writes_lands_on_one_name():
    """Measured across the pending queue and the promoted clients: these are
    real stored values, and every one of them is the same institution type."""
    for raw in ("CU", "SV2", "Credit Union", "Credit Unions",
                "SV2 — Credit Unions", "SV2_CREDIT_UNIONS",
                "SV2 Credit Unions"):
        assert display_name(raw) == ("CU", "Credit Unions"), raw


def test_a_compound_manifest_string_still_resolves():
    assert display_name("Regional Bank (SV1)")[0] == "RB"
    assert display_name("SV5 — RIAs & Broker-Dealers (Canada)")[0] == "RIA"


def test_a_value_naming_two_sub_verticals_resolves_to_neither():
    """`resolve_subvertical` refuses to pick by ordering, and the display path
    must not undo that by printing the raw string — printing the raw string is
    how `CU` reached the header."""
    code, label = display_name("Insurance & Wealth — mutual/fraternal (IC/AM)")
    assert code == UNKNOWN_SUBVERTICAL
    assert "IC" not in label and "AM" not in label
    assert label != "Insurance & Wealth — mutual/fraternal (IC/AM)"


def test_an_absent_value_says_so_rather_than_rendering_empty():
    for raw in (None, "", "   "):
        code, label = display_name(raw)
        assert code == UNKNOWN_SUBVERTICAL and label.strip()


def test_every_code_the_vocabulary_admits_has_a_name():
    """`SUBVERTICAL_CODES` is closed, so a code with no name is a programming
    error rather than a data one — and a fallback that made one printable is
    exactly what shipped the code to a client."""
    missing = [c for c in SUBVERTICAL_CODES if c not in SUBVERTICAL_DISPLAY]
    assert missing == [], f"no display name for {missing}"


def test_no_display_name_is_its_own_code():
    for code, label in SUBVERTICAL_DISPLAY.items():
        assert label.strip().upper() != code, \
            f"{code} is labelled with itself, which is what the reader saw"


def test_the_directory_no_longer_carries_a_second_name_table():
    src = (ROOT / "apps" / "api" / "dma_api" / "main.py").read_text()
    assert "_SUBVERTICAL_NAMES = {" not in src, \
        "the directory has its own name table again — two tables for one fact " \
        "is how the two clients came to be named differently"
    assert "subverticals.display_name(sub_vertical)" in src


def test_the_resolver_and_the_display_agree_on_the_code():
    """Both are read by different callers — `resolve_subvertical` for scoping,
    `display_name` for the label. A page that says Credit Unions while the
    scope filter thinks the client is something else is worse than either."""
    for raw in ("CU", "SV2", "Regional Bank (SV1)", "SV9 Farm Credit"):
        assert display_name(raw)[0] == resolve_subvertical(raw)
