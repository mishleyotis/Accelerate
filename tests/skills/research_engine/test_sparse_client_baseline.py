"""What a LOW-PUBLIC-FOOTPRINT client runs into, measured.

These are the before/after record for the calibration work (plan D). They
assert TODAY's behaviour on purpose, including the parts that are wrong, so
that when the floors gain a mode dimension the change is visible in the diff
rather than absorbed silently. Each one names what it expects to become.

The finding they exist for: fixing the connector binding does NOT save a
sparse run. Even with perfect connectors and perfectly honest absences, a
category cannot pass, because every evidence floor counts EVIDENCE and never
counts an absence — `run_density`'s own docstring says it: "a declared
absence is honest but it is not evidence."
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import contract as C, floors_gate, ledger as L, workbook as W
import fixtures as F


def _cells(wb, n):
    return [c for c in wb.selected_subcaps()][:n]


def test_declare_absence_needs_a_connector_and_web_search_is_not_one(tmp_path):
    """THE DEADLOCK, reproduced. Every volley fires, the primary fires, both
    ladder rungs are supplied — and the absence is still refused, because
    every search ran through web_search. This is the ONE term that blocks;
    `volleys_incomplete` and `primary_unfired` are satisfiable without a
    connector, which is what makes the deadlock so narrow."""
    run = F.new_run(tmp_path, n=6)
    wb = run.open()
    cell = _cells(wb, 1)[0]
    F.fire_volleys(wb, cell, n=0, tool="web_search")

    vs = L.volley_status(wb, cell)
    assert vs["missing"] == [], "every askable volley fired"
    assert vs["enrichment_tools"] == [], "and none of them reached a connector"

    try:
        L.declare_absence(
            wb, cell, actor="research-p1c1-producer",
            ladder=[{"rung": "direct", "query": f'"Acme Credit Union" {cell} rollout'},
                    {"rung": "proxy", "query": f'"Acme Credit Union" {cell} proxy: owner'}],
            proxy_log=("hunted the leadership_title proxy class across the site, "
                       "LinkedIn and the annual report; nothing names one"),
            what_was_hunted=(f"a public artefact naming {cell} across five volleys "
                             f"and two ladder rungs; nothing bears on the cell"))
        raise AssertionError("expected LedgerRefusal — the deadlock did not reproduce")
    except L.LedgerRefusal as e:
        assert "enrichment connector" in str(e)
        assert all(t in str(e) for t in ("exa", "tavily"))


def test_a_fully_absent_category_passes_and_says_it_is_empty(tmp_path):
    """THE HEADLINE. Six cells, every one declared absent through the fully
    legitimate path — real connector rung, full ladder, proxy log.

    Until 2026-09-13 this FAILED, on `coverage_below_floor` and
    `category_items_below_floor`, and that was the second blocker behind the
    stalled run: a client with no public footprint could not be assessed at
    all, however honestly the work was done. Both terms are now advisory.

    A category of honest absences PASSES, and its emptiness is disclosed
    rather than hidden — which is the whole contract of the change.
    """
    run = F.new_run(tmp_path, n=6)
    wb = run.open()
    for c in _cells(wb, 6):
        F.declare_absent(wb, c)
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=None)

    assert g["gate"] == "PASS", g["blocking"]
    assert g["blocking"] == []
    # the emptiness is stated, not buried
    assert {"coverage_below_floor", "category_items_below_floor"} <= set(g["advisory"])
    assert g["evidence_coverage"].startswith("0/6")
    assert g["category_evidence"].startswith("0/")


def test_that_category_reaches_scoring_and_scores_at_the_M2_ceiling(tmp_path):
    """Passing the gate is not the point — being SCORED is (owner: "what
    matters is that all categories are scored").

    And the containment that replaced the coverage floor is visible here: a
    cell with no evidence is capped at M2 by `ceiling_for`, so removing the
    floor cannot let a thin run claim maturity it has not earned.
    """
    from engine import assessment as A, preflight

    run = F.new_run(tmp_path, n=6)
    wb = run.open()
    preflight.record(run, F.preflight_doc())
    cells = _cells(wb, 6)
    for c in cells:
        F.declare_absent(wb, c)
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)

    assert A.research_ready(wb, run.qa_dir) == [], "scoring must be reachable"
    opened = A.open_stage(wb, run.qa_dir)
    assert opened["stage"] == "assessment"
    # the run-level thinness is disclosed on the row that records the opening
    assert opened["density"]["met"] is False
    row = [r for r in wb.rows("Gate_Log") if r.get("Gate") == "SCORING_OPENED"][-1]
    assert "THIN" in str(row["Detail"])

    ceiling, why = A.ceiling_for(wb, wb.scoring_row(cells[0]))
    assert ceiling == 2.0 and "no evidence" in why
    out = A.score(wb, cells[0], score=1.0, confidence="LOW",
                  rationale=("No public artefact names this capability at the entity "
                             "after five volleys and both ladder rungs; the absence is "
                             "declared with its proxy log, so the score sits at the "
                             "floor the evidence ceiling allows."),
                  actor="scoring-p1-producer", evidence_ceiling=ceiling,
                  caps="none applied", ai_applicability="NONE",
                  data_dependency="LOW", data_readiness="UNKNOWN")
    assert out["score"] == 1.0 and out["evidence_ceiling"] == 2.0


def test_an_absence_counts_toward_no_floor_at_all(tmp_path):
    """Stated directly, because it is the mechanism behind the test above."""
    run = F.new_run(tmp_path, n=6)
    wb = run.open()
    for c in _cells(wb, 6):
        F.declare_absent(wb, c)
    g = floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=None)
    assert g["evidence_coverage"].startswith("0/6"), "six absences, zero coverage"
    assert g["category_evidence"].startswith("0/"), "and zero items"


def test_the_floors_come_from_a_hybrid_credit_union(tmp_path):
    """The calibration defect, pinned to the file that carries it.

    Every evidence floor is derived from ONE run — Golden 1 Credit Union, in
    HYBRID mode, i.e. assessed with client-supplied internal documents as
    well as the web. They are applied unchanged to a PUBLIC-mode run of a
    private entity with no filing obligations, and `density_floors()` has no
    mode dimension at all.

    RESOLVED DIFFERENTLY (2026-09-13). Rather than deriving PUBLIC floors, the
    two volume terms became advisory — a floor that the reference itself fails
    in 9 of 16 categories is not a calibration to port to another mode, it is
    an instrument to retire. `density_floors()` therefore keeps its single
    HYBRID-derived shape, and this test keeps pinning that it has no mode
    dimension, because nothing now depends on one.
    """
    ref = json.loads(
        (Path(__file__).resolve().parents[3] / "plugins" / "dma-insights" /
         "references" / "templates" / "gold_reference.json").read_text())
    assert ref["evidence_mode"] == "HYBRID"
    assert "Credit Union" in ref["entity"]

    floors = floors_gate.density_floors()
    assert floors["source"] == "gold_reference.json"
    assert "public" not in json.dumps(floors), (
        "no mode dimension yet — when D2 lands this assertion is what changes")
    assert "public_subset" not in ref, "D0 adds this block"


def test_the_coverage_denominator_ignores_the_runs_own_evidence_mode():
    """The router and the gate disagree about what the run was asked to do.

    `MODE_ANSWERABLE` defers INTERNAL-only diagnostic questions in a PUBLIC
    run — and it is referenced ONLY by the worklist router. The coverage and
    density denominators never narrow by mode, so a PUBLIC run is scored
    against cells its own mode declares unanswerable.

    DEFERRED (2026-09-13), with the reason recorded. Narrowing the denominator
    mattered while coverage gated; it no longer does, so it now buys only a
    slightly more honest disclosed percentage — against a real cost:
    `Mode_Fit` is written by `kg.build` AFTER the cells are seeded by
    `RunWorkbook.create`, and its default "BOTH" is answerable in every mode,
    so no cell is ever zero-answerable today. Not worth that surgery for a
    cosmetic gain. This test stays as the record that the two still disagree.
    """
    import inspect
    assert set(C.MODE_ANSWERABLE["PUBLIC"]) == {"PUBLIC", "BOTH"}
    for mod in (floors_gate, W):
        assert "MODE_ANSWERABLE" not in inspect.getsource(mod), (
            f"{mod.__name__} still ignores evidence_mode — D1 changes this")


def test_evidence_smear_caps_shared_evidence_at_half(tmp_path):
    """The economic boundary of ANY batch-then-map strategy, measured.

    Batched discovery can supply at most half of a cell's citations: at 67%
    and 100% shared the blocking `evidence_smear` term fires. This is what
    makes category-grain batching unviable and capability grain the right
    unit — and it must keep holding after the grain change, or batching has
    simply eroded the containment it was supposed to respect.
    """
    def shared_fraction(shared, distinct):
        run = F.new_run(tmp_path / f"s{shared}d{distinct}", n=6)
        wb = run.open()
        sib = [c for c in wb.selected_subcaps() if c.startswith("P1C1.1")][:5]
        for c in sib:
            F.fire_volleys(wb, c, n=3)
        for s in range(shared):
            L.append_evidence(
                wb, source_name=f"Shared corpus item {s}",
                source_url=f"https://acme.example/shared{s}", tier="T2",
                excerpt=("Acme states a three-year digital transformation programme "
                         "covering quoting, servicing and analytics, with a named owner."),
                subcaps=sib, published="2025-06-01", claim_type="INFERENCE")
        for c in sib:
            for i in range(distinct):
                L.append_evidence(
                    wb, source_name=f"{c} specific source {i}",
                    source_url=f"https://acme.example/{c}/{i}", tier="T2",
                    excerpt=(f"A specific, cell-bearing statement about {c} describing "
                             f"the practice in operation during 2025 with named systems."),
                    subcaps=[c], published="2025-06-01", claim_type="INFERENCE")
        g = floors_gate.run(wb, "P1C1", require_synthesis=False, qa_dir=None)
        return bool(g.get("evidence_smear"))

    assert shared_fraction(1, 0) is True, "100% shared must fire"
    assert shared_fraction(2, 1) is True, "67% shared must fire"
    assert shared_fraction(2, 2) is False, "50% shared is permitted"
    assert shared_fraction(1, 2) is False, "33% shared is permitted"
