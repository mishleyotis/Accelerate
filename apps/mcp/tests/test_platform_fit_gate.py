"""CG-30 — the fit on the card is the fit the engine computed.

Reported 2026-08-19: "Platform fit scores calculation is very different from
Baxter's." Four definitions of one number were in play. The contract's rule
has always been that the producer EXPLAINS the fit and never recomputes or
re-ranks it; there was no engine to read from, so nothing could enforce it.

These cases pin the enforcement, including the two failure modes that are not
a wrong number: a card with no score at all, and a correct score in the wrong
order.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

from dma_mcp import validation2 as V  # noqa: E402

CHECK = V._check_platform_fit_is_the_engine_s


def page(*platforms):
    return {"platform_story": {"platforms": list(platforms)}}


def test_a_card_with_no_fit_score_is_refused():
    """Five nulls is exactly what the reported client shipped. A platform page
    whose cards cannot be ranked is not a ranking."""
    out = CHECK(None, "run", "platform", page({"platform": "X", "fit_score": None}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "read the number" in out[0]["message"].lower()


def test_another_page_is_not_this_gate_s_business():
    assert CHECK(None, "run", "overview", page({"platform": "X"})) == []


def test_a_section_with_no_platforms_is_not_a_violation():
    """An absent section is CG-01's business. Two gates refusing one payload
    for the same reason sends a producer to the wrong field."""
    assert CHECK(None, "run", "platform", {"platform_story": {}}) == []
    assert CHECK(None, "run", "platform", {}) == []


def test_the_gate_names_a_handful_not_a_wall():
    out = CHECK(None, "run", "platform",
                page(*[{"platform": f"P{i}", "fit_score": None} for i in range(20)]))
    assert len(out) <= 6


def test_an_engine_that_cannot_run_is_a_refusal_not_a_pass():
    """This module's whole subject is checks that report clean because they
    never ran. `conn=None` makes the engine raise; the gate must say so."""
    out = CHECK(None, "run", "platform", page({"platform": "X", "fit_score": 70.0}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "refusal, not a pass" in out[0]["message"]


class _Cur:
    """The four reads `fit.platform_fit` makes, answered from fixtures."""

    def __init__(self, cells):
        self.cells, self._rows = cells, []

    def execute(self, sql, args=None):
        if "FROM runs WHERE id" in sql:
            self._rows = [("run",)]
        elif "FROM subcap_scores" in sql:
            self._rows = [(sid, sc, cat, None, [area])
                          for sid, sc, cat, area in self.cells]
        else:
            self._rows = []

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _Conn:
    def __init__(self, cur):
        self._cur = cur

    def cursor(self):
        return self._cur


CELLS = [("P1C1.1.1", 2.0, "P1C1", "integration"),
         ("P1C1.1.2", 1.5, "P1C1", "integration")]


def test_a_score_the_engine_did_not_produce_is_refused():
    conn = _Conn(_Cur(CELLS))
    out = CHECK(conn, "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": 91.4, "alignment": 0.5, "readiness": "green"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "the engine computes" in out[0]["message"]


def test_the_engine_s_own_number_passes():
    conn = _Conn(_Cur(CELLS))
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration",
         "alignment": 0.5, "readiness": "green"}])["platforms"][0]
    out = CHECK(conn, "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": got["fit_score"], "rank": got["rank"],
                      "alignment": 0.5, "readiness": "green"}))
    assert out == [], out


def test_a_correct_score_in_the_wrong_order_is_still_refused():
    """The reader takes the top card as the recommendation, so the ordering
    is the claim — not a presentation detail."""
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "MuleSoft", "l3_area": "Integration",
         "alignment": 0.5, "readiness": "green"}])["platforms"][0]
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": got["fit_score"], "rank": 3,
                      "alignment": 0.5, "readiness": "green"}))
    assert [r["gate_id"] for r in out] == ["CG-30"]
    assert "wrong order" in out[0]["message"]


def test_the_refusal_carries_the_basis_that_explains_the_right_number():
    """A producer told only "that is wrong" resubmits a guess."""
    out = CHECK(_Conn(_Cur(CELLS)), "run", "platform",
                page({"platform": "MuleSoft", "l3_area": "Integration",
                      "fit_score": 91.4, "alignment": 0.5, "readiness": "green"}))
    assert "multiplier" in out[0]["message"]


def test_an_area_that_reaches_no_cell_is_named_rather_than_scored_silently():
    from dma_mcp import fit as fit_mod
    got = fit_mod.platform_fit(_Conn(_Cur(CELLS)), "run", [
        {"platform": "Nowhere", "l3_area": "Nothing here", "alignment": 0.5}])
    assert got["unmatched"] and got["unmatched"][0]["platform"] == "Nowhere"
