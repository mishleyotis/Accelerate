"""D2: the serve-time rewriter catches residual deficit phrases.

These are the defence-in-depth additions to language_rewrite R2 — the
phrases the brief bans that the prior noun-only rules missed. Anchors
(numbers, E-IDs) must be preserved verbatim.
"""
from __future__ import annotations

import pytest

from app.services.language_rewrite import rewrite_text


@pytest.mark.parametrize(
    ("src", "phrase"),
    [
        ("The customer experience keeps slipping behind competitors.", "slipping behind"),
        ("Inaction erodes loyalty over time.", "erodes"),
        ("It falls behind peers each quarter.", "falls behind"),
        ("Delay widens the gap on analytics.", "widens the gap"),
        ("Legacy systems are holding back delivery.", "holding back"),
        ("Progress was held back by tooling.", "held back"),
    ],
)
def test_deficit_phrase_rewritten(src: str, phrase: str) -> None:
    r = rewrite_text(src)
    assert r.state == "applied", f"no rule fired for {src!r}"
    assert phrase not in r.rewritten_text.lower(), r.rewritten_text


def test_left_unaddressed_dropped_with_anchors_preserved() -> None:
    src = "Left unaddressed, the $1.5B bank misses E-099."
    r = rewrite_text(src)
    assert "left unaddressed" not in r.rewritten_text.lower()
    assert "$1.5B" in r.rewritten_text
    assert "E-099" in r.rewritten_text
    assert r.validation_passed is True


def test_clean_opportunity_text_is_unchanged() -> None:
    src = "Strengthening this capability would lift the customer experience."
    r = rewrite_text(src)
    assert r.state == "no_change_needed"
