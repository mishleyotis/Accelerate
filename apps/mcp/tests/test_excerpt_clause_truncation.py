"""A clipped excerpt is refused at registration, where the length rule can't see it.

MEM-0129 and MEM-0143, both BLOCKER. Package ingest hard-clipped every
excerpt clause to 140 characters and joined them with " | ". Three such
clauses total 426 and pass the 50-500 verbatim window without a murmur.

What they are is three sentences cut mid-word, and the consequence reached a
client: a producer read a vendor name out of an excerpt THE CITABLE SPAN DOES
NOT CONTAIN, because the name fell past the cut. MEM-0129 tested every
register row against its own cited excerpt and found nine distinct product
names present in zero of them. Repairing that register took it from 41 items
to 27 and CONFIRMED from 9 to 3.

THE SIGNATURE IS UNMISTAKABLE ONCE LOOKED FOR, which is why this is a check
and not a judgement call: on the measured corpus, 4,461 of 4,906 clauses were
exactly 140 characters, against 281 at 139 and the next most common length
(114) appearing 23 times. Prose does not do that.

The rule is a CUT, not a WIDTH. A clause that happens to run 140 characters
and ends at a word boundary is ordinary prose and passes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.register import (            # noqa: E402
    CLAUSE_CLIP_WIDTH, _clause_truncated,
)

W = CLAUSE_CLIP_WIDTH


def clipped(tail: str = "y") -> str:
    """A clause of exactly the clip width, ending mid-word."""
    return "x" * (W - len(tail)) + tail


def clean(tail: str = ".") -> str:
    """The same width, ending at a boundary — ordinary prose."""
    return "x" * (W - len(tail)) + tail


# ── the measured defect ───────────────────────────────────────────────

def test_a_single_clipped_clause_is_refused():
    out = _clause_truncated(clipped())
    assert out and out.startswith("excerpt_clause_truncated:")
    assert f"exactly {W} characters" in out


def test_three_clipped_clauses_pass_the_length_window_and_are_still_refused():
    """The reason this check exists at all: 3 x 140 joined by ' | ' is 426
    characters, comfortably inside 50-500, and looks healthy to every rule
    that was in place."""
    excerpt = " | ".join([clipped()] * 3)
    assert 50 <= len(excerpt) <= 500, len(excerpt)
    out = _clause_truncated(excerpt)
    assert out and "3 clause(s)" in out


def test_the_verdict_says_why_a_truncated_excerpt_is_worse_than_a_short_one():
    """A gate that only refuses teaches nothing. The consequence — a vendor
    name read out of a span that does not contain it — is the point."""
    out = _clause_truncated(clipped())
    assert "does not contain" in out
    assert "9 product names" in out


def test_the_verdict_shows_where_the_cut_landed():
    """Built to the clip width exactly, because a fixture that is merely
    long does not exercise the rule — the first attempt at this test was 136
    characters and passed while proving nothing."""
    words = "the vendor deployed the platform across every region "
    clause = (words * 5)[:W - 6] + "Salesf"
    assert len(clause) == W and clause[-1].isalnum()
    out = _clause_truncated(clause)
    assert out and "First clipped clause ends" in out
    assert "Salesf" in out, "and shows the severed token itself"


# ── a cut, not a width ────────────────────────────────────────────────

@pytest.mark.parametrize("tail", [".", "!", "?", ")", '"', "'", ",", ";", " "])
def test_a_clause_of_the_same_width_ending_cleanly_is_ordinary_prose(tail):
    assert _clause_truncated(clean(tail)) is None, tail


def test_a_clause_one_character_short_is_not_flagged():
    assert _clause_truncated("x" * (W - 1)) is None


def test_a_clause_one_character_long_is_not_flagged():
    assert _clause_truncated("x" * (W + 1)) is None


def test_only_the_clipped_clauses_are_counted():
    excerpt = " | ".join([clipped(), clean(), clipped(), "short clause"])
    out = _clause_truncated(excerpt)
    assert "2 clause(s)" in out


def test_a_digit_is_a_word_character_too():
    """The cut lands mid-token, and a token can be a number — 'in Q3 2 026'
    is as broken as a severed word."""
    assert _clause_truncated("x" * (W - 1) + "7") is not None


# ── real prose must never be refused ──────────────────────────────────

@pytest.mark.parametrize("text", [
    "The bank published a statement on 2 August 2021 describing the "
    "conversion of the acquired platform in under four months.",
    "FINRA BrokerCheck records three customer arbitration awards against "
    "the firm across its entire operating history.",
    "Rated 4.3 over 4,262 ratings on the Android store, a lifetime average "
    "on the channel that carries the whole relationship.",
])
def test_ordinary_excerpts_pass(text):
    assert _clause_truncated(text) is None, text


def test_an_empty_or_missing_excerpt_is_not_this_checks_business():
    """The 50-500 window already refuses those, and two rules reporting one
    defect makes a verdict list nobody reads."""
    assert _clause_truncated("") is None
    assert _clause_truncated(None) is None


# ── it is wired into registration ─────────────────────────────────────

def test_the_check_runs_beside_the_length_rule():
    import inspect
    from dma_mcp import register
    src = inspect.getsource(register.register_evidence)
    assert "_clause_truncated(excerpt)" in src, \
        "the detector exists but register_evidence never calls it"
    assert src.index("excerpt_length") < src.index("_clause_truncated"), \
        ("it belongs immediately after the window it slips past, so a reader "
         "of the code meets the two rules together")


def test_the_clip_width_is_the_measured_one():
    assert CLAUSE_CLIP_WIDTH == 140


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
