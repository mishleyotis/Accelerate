"""derive_insights AE-facing prose (2026-07-06 mandates).

1. The recommendation-derived WHY names the capability in plain language —
   never a raw P#C# subcap code (internal jargon) and never an
   artifact/document title occupying the capability-name slot.
2. Everything quoted in the cross-signal OPPORTUNITY card is VERBATIM
   from the source excerpt/quote: truncation only at a claim boundary,
   marked with an ellipsis — an unquotable row is skipped, not misquoted.
3. The rec-derived WHY family is recognizable template prose so a later
   deepen run can regenerate it with evidence-content analysis.

Pure-logic, no DB (style of tests/test_all_stages_completeness.py).
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.scripts.deepen_narrative import _is_template_prose
from app.scripts.derive_insights import (
    _anchor_display,
    _cards_from_db_recommendations,
    _cross_signal_opportunity_cards,
)

_JARGON_RE = re.compile(r"P[1-4]C\d|\bsub-?cap\b", re.I)


def _rec(**over):
    base = {
        "rec_id": "REC-01",
        "title": "Stand up a marketing automation foundation",
        "description": ("Deploy a marketing automation platform integrated "
                        "with the core so campaign lists stop being manual "
                        "monthly exports."),
        "target_subcap_ids": ["P2C1.1.1", "P2C1.2"],
        "platform_id": "marketing_cloud",
        "root_cause_e_ids": ["E-004", "E-011"],
    }
    base.update(over)
    return SimpleNamespace(**base)


# ── rec-derived WHY: plain capability name, never a code or a doc title ──────

def test_rec_why_names_capability_not_code() -> None:
    cards = _cards_from_db_recommendations(
        [_rec()], {"P2C1.1.1": 1.4}, {"P2C1.1.1": 3.2},
        {"P2C1.1.1": "Digital Marketing Strategy Document"})
    assert len(cards) == 1
    why = cards[0].why_text
    assert "Digital Marketing Strategy runs at 1.4/5" in why
    assert "peer group sits at 3.2" in why
    assert not _JARGON_RE.search(why), why           # no P#C# code, no 'subcap'
    assert "Document" not in why                     # doc title never the capability


def test_rec_why_without_name_falls_back_plainly() -> None:
    # no catalogue name → category display name; still never a raw code
    cards = _cards_from_db_recommendations(
        [_rec(target_subcap_ids=["P4C1.2"])], {"P4C1.2": 1.8},
        {"P4C1.2": 2.6}, {})
    why = cards[0].why_text
    assert "runs at 1.8/5" in why
    assert not _JARGON_RE.search(why), why
    assert "Data Management & Governance" in why


def test_anchor_display_ladder() -> None:
    assert _anchor_display(
        "P2C1.1.1", {"P2C1.1.1": "Customer Journey Mapping Workbook"}) == \
        "Customer Journey Mapping"
    assert "Data Management & Governance" in _anchor_display("P4C1.2", {})
    # unknown category → honest generic phrase, never the raw id
    out = _anchor_display("P9X9.1", {})
    assert not _JARGON_RE.search(out)


def test_rec_why_family_is_regenerable_template() -> None:
    # BOTH branches (with and without a peer median) must be recognized as
    # OUR template family so deepen_narrative regenerates them with
    # evidence-content analysis instead of keeping them as analyst prose.
    with_pm = _cards_from_db_recommendations(
        [_rec()], {"P2C1.1.1": 1.4}, {"P2C1.1.1": 3.2}, {})[0].why_text
    without_pm = _cards_from_db_recommendations(
        [_rec()], {"P2C1.1.1": 1.4}, {}, {})[0].why_text
    assert _is_template_prose(with_pm), with_pm
    assert _is_template_prose(without_pm), without_pm


# ── cross-signal card: verbatim quotes only ──────────────────────────────────

_QUOTABLE = ("The careers page lists four open roles in data engineering and "
             "a head of marketing technology. All four job postings mention "
             "building a unified customer data platform from scratch.")
_UNQUOTABLE = ("one more job posting appears in " + "a continuous run of "
               "words with no sentence ending or clause seam anywhere so "
               "any truncation would slice straight through the middle of "
               "the single claim being made about recruiting and platform "
               "intent across the whole excerpt without a natural stopping "
               "point ever arriving in the text at all")


def _xsig(evidence_rows, quotes=None):
    return _cross_signal_opportunity_cards(
        evidence_rows=evidence_rows,
        absent_families=[("cdp", "Customer Data Platform")],
        strategic_quotes=quotes if quotes is not None else [
            {"quote": "Become the most data-driven lender in our footprint",
             "e_ids": ["E-077"]}],
        family_leafs={"cdp": "P4C1.2"},
        sub_scores={"P4C1.2": 1.8},
    )


def test_xsig_quotes_are_verbatim_and_jargon_free() -> None:
    cards = _xsig([{"e_id": "E-055", "tier": 2, "excerpt": _QUOTABLE}])
    assert len(cards) == 1
    what, why = cards[0].what_text, cards[0].why_text
    m = re.search(r'The research recorded: "([^"]+)"', what)
    assert m is not None
    q = m.group(1)
    core = q[:-2] if q.endswith(" …") else q
    assert core in _QUOTABLE                     # contiguous verbatim span
    # the strategic quote fits → rendered whole, verbatim
    assert '"Become the most data-driven lender in our footprint"' in why
    # score context names no raw code (2026-07-06 jargon rule)
    assert "scores 1.8/5" in why
    assert not _JARGON_RE.search(what + " " + why)


def test_xsig_skips_unquotable_row_for_next_quotable_one() -> None:
    rows = [{"e_id": "E-001", "tier": 1, "excerpt": _UNQUOTABLE},
            {"e_id": "E-055", "tier": 2, "excerpt": _QUOTABLE}]
    cards = _xsig(rows)
    assert len(cards) == 1
    # the tier-1 row had no claim-safe span — the card cites the NEXT row
    # rather than shipping a mid-claim cut of the first.
    assert "[E-055]" in cards[0].what_text
    assert "slice straight through" not in cards[0].what_text


def test_xsig_not_emitted_when_nothing_is_quotable() -> None:
    assert _xsig([{"e_id": "E-001", "tier": 1, "excerpt": _UNQUOTABLE}]) == []
    # …or when the strategic quote itself has no claim-safe span
    long_quote = _UNQUOTABLE.replace("one more job posting appears in ", "")
    assert _xsig([{"e_id": "E-055", "tier": 2, "excerpt": _QUOTABLE}],
                 quotes=[{"quote": long_quote, "e_ids": []}]) == []
