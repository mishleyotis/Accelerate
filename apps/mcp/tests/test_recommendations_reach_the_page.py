"""CG-39 — a run whose analyst wrote recommendations must serve some.

Owner, 2026-08-23, reading a promoted platform page: "Gulf has platforms with
no recommendations. Is there a synthesis layer that challenges
recommendations, enhances them, confirms validity?"

Measured on that run. get_report_bundle returned SEVEN recommendations, each
with a category, an evidence_basis of real e_ids and a named offering:

    REC-1  Integrate FactorSoft <-> Salesforce …      P4C3 / P2C2
    REC-2  Deliver as managed / staff-augmentation …  P3C1 / P1C4
    REC-3  Operationalize Pardot: nurture journeys …  P2C1 / P3C1

The promoted page served four platform tiles reading "5 cells · 0 recs" — one
of them Marketing Cloud Account Engagement (Pardot), which is exactly what
REC-3 is about. platform_fits_raw was empty.

Nothing was wrong with the analysis. The write path had no read path, and a
client saw four cards recommending nothing.

The gate is deliberately WEAK: one served recommendation clears it. It does
not judge the mapping — CG-30 owns fit agreement and the producer owns the
argument. It catches only the case where the whole set was dropped, which is
the one that reached a client.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dma_mcp.gates import GATES  # noqa: E402
from dma_mcp.validation2 import (  # noqa: E402
    _check_recommendations_reach_the_platform_page as check,
)


class _Cur:
    def __init__(self, n=0, raises=False):
        self._n, self._raises = n, raises

    def execute(self, *a, **kw):
        if self._raises:
            raise RuntimeError("relation does not exist")

    def fetchone(self):
        return [self._n]


class _Conn:
    def __init__(self, n=0, raises=False):
        self._c = _Cur(n, raises)

    def cursor(self):
        return self._c


def tiles(n=4):
    return {"platform_story": {"platforms": [
        {"platform": f"P{i}", "fit_score": 50.0} for i in range(n)]}}


def served(n=1):
    return {"recommendations": {"recommendations": [
        {"rec_id": f"REC-{i}"} for i in range(n)]}}


# ── the case that reached a client ────────────────────────────────────────

def test_seven_in_the_bundle_and_none_on_the_page_blocks():
    """Gulf Coast, exactly as measured."""
    out = check(_Conn(7), "run-1", "platform", tiles(4))
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "CG-39" and r["severity"] == "block"
    assert "7 recommendation" in r["message"]
    assert "4 tile" in r["message"]
    assert "get_report_bundle" in r["message"], "the message names the fix"


def test_one_served_recommendation_clears_it():
    """Deliberately weak. The gate is not judging the mapping."""
    assert check(_Conn(7), "r", "platform", {**tiles(), **served(1)}) == []


def test_all_seven_served_clears_it():
    assert check(_Conn(7), "r", "platform", {**tiles(), **served(7)}) == []


# ── the cases that must NOT block ─────────────────────────────────────────

def test_a_run_with_no_recommendations_is_an_honest_absence():
    """Nothing was dropped, so there is nothing to report. A gate that fired
    here would punish a run for an analysis it never had."""
    assert check(_Conn(0), "r", "platform", tiles()) == []


def test_no_tiles_is_cg30s_case_not_this_one():
    """A platform page with no tiles at all is a different defect, and two
    gates blocking on one cause is how a repair gets scoped twice."""
    assert check(_Conn(7), "r", "platform",
                 {"platform_story": {"platforms": []}}) == []


@pytest.mark.parametrize("page", ["overview", "heatmap", "insights",
                                  "context", "techstack"])
def test_it_only_runs_on_the_platform_page(page):
    assert check(_Conn(7), "r", page, tiles()) == []


def test_an_unreadable_bundle_manufactures_no_verdict():
    """THE DIRECTION THAT MATTERS. A check that could not run must not report
    a defect — nor silently report cleanliness. It returns nothing and the
    other gates still speak."""
    assert check(_Conn(raises=True), "r", "platform", tiles()) == []


def test_a_malformed_payload_does_not_raise():
    for bad in (None, [], "x", {"platform_story": "not-a-dict"},
                {"platform_story": {"platforms": "no"}}):
        assert check(_Conn(7), "r", "platform", bad) == []


# ── the registry ──────────────────────────────────────────────────────────

def test_cg39_is_registered_and_blocks():
    """A gate absent from the registry answers unknown_gate to explain_gate,
    and CG-22 refuses a payload naming one."""
    assert "CG-39" in GATES
    entry = GATES["CG-39"]
    assert entry[-1] == "block"
    why = " ".join(str(x) for x in entry)
    assert "Pardot" in why, "the registry carries the measurement, not a slogan"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
