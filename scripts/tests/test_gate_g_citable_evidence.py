"""G2 — the corpus check behind the ingest fix.

Each case here is a shape that reached production. The empty-string row is
the Logix one: 36 of 62 on run d7ed1d90, invisible to the repair job, the
embedder and the dedup index at once, and populated-looking to everything
written against None.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gate_g_citable_evidence import DISCLOSURE_FLOOR, EXCERPT_MIN, audit

GOOD = "x" * 120


def _rows(*excerpts):
    return [{"e_id": f"E-CC-{i:03d}", "excerpt": e} for i, e in enumerate(excerpts, 1)]


def test_a_clean_register_passes_silently():
    rep = audit(_rows(GOOD, GOOD, GOOD), {})
    assert rep["blockers"] == [] and rep["warnings"] == []
    assert rep["share"] == 1.0


def test_the_empty_string_is_a_blocker_not_a_gap():
    """NULL means nobody had one. '' means the ingest wrote one and it was
    nothing, and only the second is invisible to three separate queries."""
    rep = audit(_rows(GOOD, "", "   "), {})
    assert rep["empty_string"] == 2
    assert any("EMPTY STRING" in b for b in rep["blockers"])


def test_a_null_excerpt_is_not_the_empty_string():
    rep = audit([{"e_id": "E-1", "excerpt": None}, {"e_id": "E-2", "excerpt": GOOD}], {})
    assert rep["empty_string"] == 0, "a NULL row must not be reported as an empty string"


def test_a_fragment_under_the_floor_blocks():
    """The rationale miner accepted 20 characters. Such a row links to cells
    and is refused at ET-04 the moment anyone cites it."""
    rep = audit(_rows(GOOD, "Uses Symitar Episys."), {})
    assert rep["short"] == 1
    assert any(f"{EXCERPT_MIN}-character floor" in b for b in rep["blockers"])


def test_thin_and_silent_blocks():
    rows = _rows(GOOD, *(["x" * 0] and []), *[None] * 0)
    rows = [{"e_id": "E-1", "excerpt": GOOD}] + [{"e_id": f"E-{i}", "excerpt": None}
                                                 for i in range(2, 6)]
    rep = audit(rows, {"overview": {"sections": {"scores": {"data": {"note": "all good"}}}}})
    assert rep["share"] < DISCLOSURE_FLOOR
    assert any("no page says so" in b for b in rep["blockers"])


def test_thin_and_DISCLOSED_is_the_correct_posture():
    """The whole point. An institution whose own domain answers this run's
    verifier with a 403 cannot be researched as deeply as one that does not —
    refusing that run would refuse the finding. What is required is that the
    run knows and states it."""
    rows = [{"e_id": "E-1", "excerpt": GOOD}] + [{"e_id": f"E-{i}", "excerpt": None}
                                                 for i in range(2, 6)]
    pages = {"techstack": {"sections": {"techstack": {"data": {"empty_state": {
        "reason": "its own domain answers this run's evidence verifier with an "
                  "HTTP 403 at the Cloudflare edge, so the material exists and "
                  "cannot be cited"}}}}}}
    rep = audit(rows, pages)
    assert rep["disclosed"] is True
    assert rep["blockers"] == [], "a disclosed absence is a finding, not a defect"
    assert rep["warnings"], "and it is still reported, so nobody has to re-derive it"


def test_disclosure_is_found_wherever_the_run_puts_it():
    """Prose, an empty_state reason or a closure condition all count: the
    check is on the shape of the admission, not on a form of words."""
    rows = [{"e_id": f"E-{i}", "excerpt": None} for i in range(1, 6)]
    for where in ("narrative_thread", "closure_condition", "note"):
        pages = {"overview": {"sections": {"s": {"data": {
            where: "36 ingested rows carry no verbatim excerpt and cannot be cited"}}}}}
        assert audit(rows, pages)["blockers"] == [], f"missed a disclosure in {where}"
