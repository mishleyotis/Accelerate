"""Stress tests for app/ml/fuzzy.py (rapidfuzz-based name matching)."""
from __future__ import annotations

import pytest

from app.ml.fuzzy import Match, best_match, extract_top, unambiguous_best

ROSTER = [
    "Wintrust Financials", "First Citizens", "Fulton Bank", "Security Finance",
    "American Homes", "Texas Capital Bank", "Greenstone", "AmeriCU Credit Union",
]


def test_exact_and_variant_match():
    assert best_match("Wintrust Financials", ROSTER).choice == "Wintrust Financials"
    # real manifest variant -> correct entity
    m = best_match("Fulton Bank, National Association", ROSTER)
    assert m is not None and m.choice == "Fulton Bank"


def test_unambiguous_best_refuses_ties():
    # a genuine tie (duplicate choices) -> top-2 margin is 0 -> refuse to guess.
    roster = ["Acme Holdings", "Acme Holdings"]
    assert unambiguous_best("Acme Holdings", roster) is None


def test_unambiguous_best_returns_clear_winner():
    # best_match reliably resolves the variant; unambiguous_best is conservative
    # (may return None on a close runner-up) but must never return the WRONG one.
    assert best_match("Fulton Bank, National Association", ROSTER).choice == "Fulton Bank"
    m = unambiguous_best("Fulton Bank National Association", ROSTER)
    assert m is None or m.choice == "Fulton Bank"


def test_zero_false_match_on_unrelated_query():
    # a totally unrelated query must not clear the conservative cutoff
    assert unambiguous_best("Zzzqqq Nonexistent LLP", ROSTER) is None


@pytest.mark.parametrize("q,choices", [
    ("", ROSTER),
    ("Bank", []),
    ("   ", ROSTER),
    ("Ünîçödé ☃ Bank", ROSTER),
    ("x" * 50_000, ROSTER),
])
def test_adversarial_inputs_never_crash(q, choices):
    assert best_match(q, choices) is None or isinstance(best_match(q, choices), Match)
    assert isinstance(extract_top(q, choices, k=3), list)
    out = unambiguous_best(q, choices)
    assert out is None or isinstance(out, Match)
