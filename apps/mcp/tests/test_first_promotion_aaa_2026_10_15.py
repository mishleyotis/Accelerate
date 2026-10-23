"""AAA Western and Central New York, first promotion 2026-10-15.

Run e7a59709 promoted with all six pages PASS and still read incomplete:
  1. every peer median null — the IB cohort read 2 entities while six scored
     brokerages sat in the store (test_cohort_benchmarks.py holds that one);
  2. the opportunity card served 2 platforms — six of eight candidates were
     INSUFFICIENT_EVIDENCE at mean evidence strength 0.0, judged on the
     alphabetically-first UNEVIDENCED cells of a run whose gaps all tie;
  3. pages staged before the pages they read — "the technology register is
     not promoted", "techstack page not yet shipped", and a heatmap evidence
     index ending at E-228 while other pages cited E-229 … E-253.
Each is a first-promotion defect: on a rerun the previous promotion hides it.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))
sys.path.insert(0, str(ROOT / "packages" / "shared"))

import platform_fit as PF  # noqa: E402

from dma_mcp import promote_checks as PC  # noqa: E402


# ── 2. the evidence state is judged on the claim, then the evidence ──────

def _service_cloud(evidenced_strength=0.56, evidenced_score=1.0):
    """28 cells at one score, as AAA's were: the five that sort first carry
    no evidence (P1C2.2.x), twenty-three carry a T3-undated citation."""
    cells = [PF.Cell(f"P1C2.2.{i}", 1.0, "P1C2") for i in range(1, 6)]
    cells += [PF.Cell(f"P2C3.{i}.1", evidenced_score, "P2C3",
                      evidence_strength=evidenced_strength) for i in range(1, 24)]
    return PF.Candidate("Salesforce Service Cloud", "Service Cloud", cells=cells,
                        readiness="amber")


def test_a_tied_run_is_judged_on_its_evidenced_cells_not_the_alphabetically_first():
    cand = _service_cloud()
    assert PF.state_for(cand) == PF.STATE_READY
    top = PF.top_contributors(cand)
    assert all(c["evidence_strength"] is not None for c in top), top
    # the verdict and the cells printed beside it agree
    assert PF.mean_evidence_strength(cand) == sum(
        c["evidence_strength"] for c in top) / len(top)


def test_the_old_order_was_the_defect():
    """core_of still orders by damped opportunity — the neutral prior puts an
    unevidenced cell (0.82) above a T4-undated one (0.754). Judging the floor
    on THAT order is what read 0.0 for AAA's six candidates."""
    cand = _service_cloud(evidenced_strength=0.385)
    old = PF.core_of(cand)[:PF.TOP_N]
    assert all(c.evidence_strength is None for c in old)
    assert PF.mean_evidence_strength(cand) > PF.EVIDENCE_FLOOR


def test_a_bigger_unevidenced_claim_still_reads_insufficient():
    """Negative control: evidence never outranks a larger gap. The cells
    driving the score are the unevidenced ones, honestly."""
    cand = _service_cloud(evidenced_score=2.5)
    assert PF.state_for(cand) == PF.STATE_INSUFFICIENT


def test_the_fit_score_itself_does_not_move():
    a, b = _service_cloud(), _service_cloud()
    b.cells = list(reversed(b.cells))
    assert PF.score(a)["fit_score"] == PF.score(b)["fit_score"]


# ── 3. a page staged before what it reads ─────────────────────────────────

AAA_TEXT = {
    "overview": {"opportunity": {"empty_state": {
        "reason": "Greenfield reads zero because the technology register is not "
                  "promoted, so zero means unmeasured."}}},
    "insights": {"landscape": {"r_layer": {
        "counter": "The register on disk is a draft (techstack page not yet "
                   "shipped); rows may change."}}},
    "heatmap": {"evidence_age": {"empty_state": {
        "reason": "24 later workbook rows are not yet registered and are left "
                  "out until they are."}},
                "safeguard_gates": {"empty_state": {
        "closure_condition": "The app populates gates[] from gate_results when "
                             "the run is promoted."}}},
}


def test_order_text_refuses_each_aaa_sentence_and_nothing_else():
    paths = {r["path"] for page, p in AAA_TEXT.items()
             for r in PC.order_text(page, p)}
    assert paths == {"overview.opportunity.empty_state.reason",
                     "insights.landscape.r_layer.counter",
                     "heatmap.evidence_age.empty_state.reason"}


def test_order_text_leaves_the_client_s_own_facts_alone():
    ok = {"why_now": {"narrative_thread":
          "No source shows the domain was registered before 2019, and a promoted "
          "technology register would measure greenfield."}}
    assert PC.order_text("overview", ok) == []


def _live(index, cited, form_pages=None):
    live = {"heatmap": {"payload": {"evidence": {"evidence": [{"e_id": e} for e in index]}}},
            "platform": {"payload": {"recommendations": {"e_ids": cited}}}}
    for page, ids in (form_pages or {}).items():
        live[page] = {"payload": {"x": {"rows": [{"e_id": i} for i in ids]}}}
    return live


def test_an_evidence_index_that_stops_before_the_citations_refuses_the_heatmap():
    index = [f"E-{i:03d}" for i in range(1, 229)]
    gaps = PC.evidence_index_gaps(_live(index, ["E-034", "E-229", "E-241"],
                                        {"techstack": ["E-249", "E-252"]}))
    assert len(gaps) == 1 and gaps[0]["gate_id"] == "CG-ORDER"
    msg = gaps[0]["message"]
    assert "omits 4" in msg and "E-229" in msg and "platform.recommendations" in msg


def test_a_citation_in_the_other_id_form_is_not_a_gap():
    index = [f"E-{i:03d}" for i in range(1, 229)]
    assert PC.evidence_index_gaps(_live(index, ["E-AAAWESTE-247", "E-034"])) == []


def test_no_index_is_not_this_check_s_business():
    assert PC.evidence_index_gaps({"platform": {"payload": {"r": {"e_ids": ["E-9"]}}}}) == []
