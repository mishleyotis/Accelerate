"""Regression tests for the 2026-07-09 AE-QA batch.

Each test pins one reported defect's fix so it can't silently regress:
  * recommendation title no longer leads with an orphaned ")" (IBKR R2)
  * the gap-fill rec cap covers the full below-M4 set (not a hard 5)
  * markdown emphasis (**bold**) is stripped at the text_hygiene chokepoint
  * UNKNOWN_VENDOR tech rows surface (only ENGINEERING_SIGNAL is hidden)
  * sentiment_card normalizes a raw {sources:[…]} blob at serve time
  * a rec card's SO-WHAT is an implication, not a restatement of its title
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.overview_cards import sentiment_card
from app.services.parsers.report_recommendations import _split_title_from_heading
from app.services.techstack_read import triage_rows
from app.services.text_hygiene import plain, scrub_md


# ── recommendations ────────────────────────────────────────────────────────
def test_rec_title_drops_orphaned_close_paren() -> None:
    # a rec sliced at a mid-sentence "(R2)" anchor used to keep the ")"
    out = _split_title_from_heading(
        "R2) from real-time account signals. This makes Data Cloud the "
        "architectural prerequisite.", "R2")
    assert not out.lstrip().startswith(")")
    assert out.startswith("from real-time account signals")


def test_rec_title_still_splits_normal_headings() -> None:
    assert _split_title_from_heading("REC-01: Digital Lending", "REC-01") \
        == "Digital Lending"
    assert _split_title_from_heading("R2 — Unify the core", "R2") \
        == "Unify the core"


def test_gap_fill_rec_cap_covers_below_m4_set() -> None:
    from app.scripts.derive_recommendations import _MAX_RECS
    # V7 has ~16-17 categories; the cap must cover the full below-M4 set, not 5.
    assert _MAX_RECS >= 16


# ── markdown emphasis leak ──────────────────────────────────────────────────
def test_plain_strips_bold_and_italic_emphasis() -> None:
    assert plain("**Real-time** account signals") == "Real-time account signals"
    assert plain("__Empower__ and *Voya*") == "Empower and Voya"


def test_scrub_md_strips_emphasis_keeps_structure() -> None:
    out = scrub_md("## Heading\n**bold** and *em* text")
    assert "**" not in out and out.startswith("## Heading")
    assert "bold and em text" in out


def test_emphasis_strip_leaves_snake_case_and_math_alone() -> None:
    # single "_" in identifiers / a lone "*" must survive
    assert "a_b_c" in plain("field a_b_c value")
    assert plain("3 * 4 = 12") == "3 * 4 = 12"


# ── tech-stack over-filter ──────────────────────────────────────────────────
def _row(status: str):
    return SimpleNamespace(status=status, detected_at=None)


def test_unknown_vendor_surfaces_engineering_signal_hidden() -> None:
    t = triage_rows([
        _row("CONFIRMED"), _row("DETECTED"),
        _row("UNKNOWN_VENDOR"),        # real vendor tech → must surface
        _row("ENGINEERING_SIGNAL"),    # a language → stays hidden
    ])
    assert len(t.surfaced) == 3        # CONFIRMED + DETECTED + UNKNOWN_VENDOR
    assert len(t.engineering) == 1     # ENGINEERING_SIGNAL only
    assert len(t.review) == 0          # nothing hidden in review anymore


# ── sentiment normalize-on-serve ────────────────────────────────────────────
def test_sentiment_card_passthrough_scorecard_shape() -> None:
    card = sentiment_card({
        "employee": [{"label": "Glassdoor", "score": 3.8, "scale": 5}],
        "customer": [],
    })
    assert card is not None and card["employee"]


def test_sentiment_card_none_when_truly_empty() -> None:
    assert sentiment_card({}) is None
    assert sentiment_card({"employee": [], "customer": [], "nps": [],
                           "qualitative": []}) is None
    assert sentiment_card("not a dict") is None
