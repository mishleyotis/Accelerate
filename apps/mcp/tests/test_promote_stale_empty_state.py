"""A promoted page must not say its own run is withdrawn — RC-13 / D-31.

SWBC gold audit, 2026-10-04: heatmap.cohort_patterns was produced while run
7968492e was withdrawn. Its empty_state read "this client's own run is
withheld pending repair so it counts toward no cohort", and a ladder rung
read "Status of this client's own run: withdrawn pending repair". The page
was retained (invariant 3), the run was re-promoted, and the promoted page
told its reader the run was withheld — a sentence promotion makes false the
moment it succeeds. Validation ran at submit; the run's status changed
afterwards and nothing re-read the text.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _promote_fake import RUN, Conn, skeleton, wrote_anything  # noqa: E402

from dma_mcp.promote import promote_run


SWBC_REASON = ("A cohort pattern is published only when five or more promoted "
               "runs in the same sub-vertical carry a served score for the "
               "same category. That count has not been established for this "
               "run, and this client's own run is withheld pending repair so "
               "it counts toward no cohort.")
SWBC_RUNG = ("Status of this client's own run: withdrawn pending repair, so it "
             "contributes to no cohort")


def _swbc_cohort_patterns(pages):
    pages["heatmap"]["cohort_patterns"]["empty_state"] = {
        "reason": SWBC_REASON,
        "sources_searched": [SWBC_RUNG, "Promoted runs in the serving corpus"],
        "closure_condition": "Five or more promoted runs, counted at promotion"}
    return pages


def test_swbc_cohort_patterns_is_refused_at_promote():
    conn = Conn(_swbc_cohort_patterns(skeleton()))
    out = promote_run(conn, RUN)
    assert out["promoted"] is False, "a page saying its run is withheld promoted"
    assert out["error"] == "retained_pages_fail_current_gates"
    assert "heatmap" in out["pages"]
    assert out["blocking_by_gate"]["heatmap"].get("CG-STALE"), out["blocking_by_gate"]
    assert conn.rollbacks and not wrote_anything(conn), \
        "the refusal must precede every writer"


def test_both_the_reason_and_the_rung_are_named():
    pages = _swbc_cohort_patterns(skeleton())
    from dma_mcp.promote_checks import stale_run_state
    got = stale_run_state("heatmap", pages["heatmap"])
    paths = [r["path"] for r in got]
    assert any("empty_state.reason" in p for p in paths), paths
    assert any("empty_state.sources_searched" in p for p in paths), paths
    assert all(r["gate_id"] == "CG-STALE" for r in got)


def test_a_withdrawn_application_is_the_client_s_fact_not_the_run_s():
    """HMDA counts applications 'withdrawn'; a why-now signal can be
    withdrawn. Refusing those would be refusing the client's facts."""
    pages = skeleton()
    pages["overview"]["financial_series"]["empty_state"] = {
        "reason": "HMDA counts 41 applications withdrawn by the applicant in "
                  "2024; signal WN-4 was withdrawn after review.",
        "sources_searched": ["FFIEC HMDA: RESOLVED"]}
    from dma_mcp.promote_checks import stale_run_state
    assert stale_run_state("overview", pages["overview"]) == []


def test_the_clean_skeleton_still_promotes():
    """Negative control: without the stale sentence the same run promotes."""
    out = promote_run(Conn(skeleton()), RUN)
    assert out["promoted"] is True, out
