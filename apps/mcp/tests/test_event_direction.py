"""AG-05 — one event, one direction, across both pages.

The measured defect, on a promoted run: the context timeline classified a
merger announcement NEGATIVE / CONSTRAINED, and the overview's why-now
used the SAME announcement — same evidence id, same date — as its LEADING
reason to act now. Every per-page gate passed, because neither page held
both halves of the contradiction. The reader holds both.

`signal` is not a mood. It is the direction the event moved the ASSESSED
POSITION of the cells it names, so a why-now trigger and a NEGATIVE
timeline badge on one event are two incompatible claims about the same
history.

The check is symmetric: each of the two pages reads the other's live
staging submission, so whichever is submitted second makes the
comparison, and neither ordering escapes it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation2 import _check_event_direction  # noqa: E402

MERGER_EVENT = {
    "event_date": "2026-06-01", "kind": "M&A",
    "title": "Merger with another credit union announced",
    "body": "A merger with a healthcare-sector credit union was announced.",
    "signal": "NEGATIVE",
    "maturity_effect": "CONSTRAINED — the conversion runs through the "
                       "thinnest layer in the assessment.",
    "capability_ids": ["P4C3.1.1"], "e_ids": ["E-CC-004"],
}
MERGER_SIGNAL = {
    "wn_id": "WN-1", "kind": "M&A", "dated_on": "2026-06-01",
    "trigger": "BCU announced a planned merger with HealthCare Associates "
               "Credit Union on 1 June 2026.",
    "e_ids": ["E-CC-004", "E-BCU-032"],
}


def _context(events):
    return {"timeline": {"events": events}}


def _overview(signals):
    return {"why_now": {"signals": signals}}


def test_the_measured_contradiction_is_caught_from_the_context_side():
    out = _check_event_direction("context", _context([MERGER_EVENT]),
                                 _overview([MERGER_SIGNAL]))
    hits = [r for r in out if "why-now signal" in r["message"]]
    assert len(hits) == 1
    r = hits[0]
    assert r["gate_id"] == "AG-05" and r["severity"] == "block"
    assert r["path"] == "timeline.events[0]"
    assert "both cite E-CC-004" in r["message"]
    assert "WN-1" in r["message"]


def test_the_same_contradiction_is_caught_from_the_overview_side():
    """Whichever page lands second sees the other, so the pair cannot be
    slipped past by submission order."""
    out = _check_event_direction("overview", _overview([MERGER_SIGNAL]),
                                 _context([MERGER_EVENT]))
    assert len(out) == 1
    assert out[0]["gate_id"] == "AG-05"
    assert out[0]["path"] == "why_now.signals[0]"
    assert out[0]["section"] == "why_now"


def test_reclassifying_the_event_neutral_clears_it():
    """The repair the definition asks for: an announcement that adds
    demand and takes no capability away moved no cell, so it is NEUTRAL
    and its pressure is argued in `body` — which is exactly what the
    why-now says about it."""
    fixed = dict(MERGER_EVENT, signal="NEUTRAL",
                 maturity_effect="NEUTRAL — nothing has converted yet.")
    assert _check_event_direction("context", _context([fixed]),
                                  _overview([MERGER_SIGNAL])) == []


def test_a_genuinely_constraining_event_no_why_now_names_is_untouched():
    """A live cap is a real finding. The gate objects to the pair, never to
    a NEGATIVE badge on its own."""
    event = dict(MERGER_EVENT, e_ids=["E-BCU-008"], kind="SECURITY",
                 event_date="2021-10-01", title="Email data breach")
    assert _check_event_direction("context", _context([event]),
                                  _overview([MERGER_SIGNAL])) == []


def test_a_shared_date_and_kind_match_without_a_shared_id():
    """A producer can cite two different sources for one announcement, so
    the id is the strongest match and not the only one."""
    event = dict(MERGER_EVENT, e_ids=["E-CC-002"])
    signal = dict(MERGER_SIGNAL, e_ids=["E-CC-004"])
    out = [r for r in _check_event_direction("context", _context([event]),
                                             _overview([signal]))
           if "why-now signal" in r["message"]]
    assert len(out) == 1
    assert "same date 2026-06-01 and kind M&A" in out[0]["message"]


def test_a_shared_date_alone_is_not_the_same_event():
    """Two things can happen in one month. Without a shared id, a shared
    kind or a shared subject there is no contradiction to report."""
    event = dict(MERGER_EVENT, e_ids=["E-CC-002"], kind="REGULATORY",
                 title="Examination cycle opened", body="An examination.")
    signal = dict(MERGER_SIGNAL, e_ids=["E-CC-004"])
    assert [r for r in _check_event_direction("context", _context([event]),
                                              _overview([signal]))
            if "why-now signal" in r["message"]] == []


def test_the_subject_match_needs_two_content_words_not_boilerplate():
    """'credit', 'union' and 'announced' appear on every row of a
    financial-services timeline, so they cannot be what makes two rows the
    same event."""
    event = dict(MERGER_EVENT, e_ids=["E-CC-002"], kind="",
                 title="Credit union announced something",
                 body="A credit union announced.")
    signal = dict(MERGER_SIGNAL, kind="", e_ids=["E-CC-004"])
    assert [r for r in _check_event_direction("context", _context([event]),
                                              _overview([signal]))
            if "why-now signal" in r["message"]] == []


def test_the_badge_and_the_sentence_are_one_claim():
    """The within-page half needs no sibling: NEGATIVE with an ADVANCED
    clause is two different readings of one event."""
    event = dict(MERGER_EVENT, signal="NEGATIVE",
                 maturity_effect="ADVANCED — it adds scale.")
    out = _check_event_direction("context", _context([event]), {})
    assert len(out) == 1
    assert out[0]["path"] == "timeline.events[0].signal"
    assert "NEGATIVE with a maturity_effect of ADVANCED" in out[0]["message"]


def test_agreeing_badge_and_sentence_pass():
    for signal, effect in (("POSITIVE", "ADVANCED — a platform delivered."),
                           ("NEUTRAL", "NEUTRAL — the cap has lapsed."),
                           ("NEGATIVE", "CONSTRAINED — a live ceiling.")):
        event = dict(MERGER_EVENT, signal=signal, maturity_effect=effect,
                     e_ids=["E-ONLY-001"])
        assert _check_event_direction("context", _context([event]), {}) == []


def test_a_missing_sibling_submission_reports_nothing():
    """A page not yet submitted is nothing to compare. It is not a pass —
    the other page makes the comparison when it lands."""
    assert [r for r in _check_event_direction("context",
                                              _context([MERGER_EVENT]), {})
            if "why-now signal" in r["message"]] == []


def test_other_pages_are_untouched():
    assert _check_event_direction("heatmap", _context([MERGER_EVENT]),
                                  _overview([MERGER_SIGNAL])) == []
