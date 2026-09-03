"""The SCORING stage: engine commands, refusals, a gate — and no report before it.

Owner, 2026-09-03: "Report writing starts without scoring happening. Worse
still, the reports do not follow the required format … can the report writing
agents do a preliminary check on scoring and ensure the workbook is complete
before writing any report?" and "The reports and scoring workbook should …
be a clear workflow with clear gating requirements."
"""
from __future__ import annotations

import json

import pytest

from engine import assessment as A
from engine import contract as C
from engine import floors_gate
from engine import ledger as L
from engine import narrative as N
from engine import report_spec as RS
from engine.assessment import ScoringRefusal
from fixtures import (bank_evidence, declare_absent, good_synthesis, new_run,
                      section_record,
                      synthesise)

from fixtures import (RATIONALE, researched_run as _researched,  # noqa: E402
                      score_all as _score_all, score_cell as _score)


# ── the stage opens only on a finished research run ──────────────────────

def test_open_refuses_an_ungated_run(tmp_path):
    run = new_run(tmp_path, n=3)
    with pytest.raises(ScoringRefusal, match="not ready to be scored"):
        A.open_stage(run.open(), run.qa_dir)


def test_open_writes_the_config_tabs_and_flips_the_stage(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    out = A.open_stage(wb, run.qa_dir)
    assert out["stage"] == "assessment"
    assert C.stage_of(wb.metadata()) == "assessment"
    assert len(wb.rows("Pillar_Weights")) == 5
    assert sum(float(r["weight"]) for r in wb.rows("Pillar_Weights")
               if r["pillar_id"] in ("P1", "P2", "P3", "P4")) == pytest.approx(1.0)
    assert len(wb.rows("Maturity_Rubric")) == 5
    assert len(wb.rows("Cap_Triggers")) == len(C.CAP_TRIGGERS)
    assert len(wb.rows("Capability_Definitions")) == 16
    keys = {r["key"] for r in wb.rows("Catalogue_Meta")}
    assert {"catalogue_hash", "pillar_count", "category_count", "subcap_count"} <= keys


def test_scoring_refuses_at_the_research_stage(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    with pytest.raises(ScoringRefusal, match="research stage"):
        _score(wb, cells[0], ev[cells[0]])


# ── one score, and the ways it is refused ────────────────────────────────

def test_a_good_score_lands_in_every_tab_it_belongs_in(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    out = _score(wb, cells[0], ev[cells[0]])
    assert out["level"] == "M3"
    row = wb.scoring_row(cells[0])
    assert float(row["Score"]) == 2.5 and row["Confidence"] == "MEDIUM"
    assert len(str(row["Rationale"])) >= A.RATIONALE_MIN
    ss = [r for r in wb.rows("Subcap_Scores") if r["subcap_id"] == cells[0]]
    assert ss and ss[0]["ai_applicability"] == "ASSISTIVE" and ss[0]["subcap_name"]
    assert any(r["subcap_id"] == cells[0] for r in wb.rows("Caps_Applied_Log"))
    assert L.actor_for(wb, cells[0], "score") == "scoring-p1-producer"


def test_a_score_above_the_evidence_ceiling_is_refused(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    with pytest.raises(ScoringRefusal, match="above the evidence ceiling|exceeds"):
        _score(wb, cells[0], ev[cells[0]], score=4.0, evidence_ceiling=3.0)


def test_an_off_scale_or_off_quarter_score_is_refused(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    with pytest.raises(ScoringRefusal, match="not on the 1.0-5.0 scale"):
        _score(wb, cells[0], ev[cells[0]], score=0)
    with pytest.raises(ScoringRefusal, match="quarter-point"):
        _score(wb, cells[0], ev[cells[0]], score=2.6)


def test_a_thin_or_uncited_rationale_is_refused(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    with pytest.raises(ScoringRefusal, match="150 is the floor"):
        _score(wb, cells[0], ev[cells[0]], rationale="Demonstrates capability.")
    with pytest.raises(ScoringRefusal, match="cites none of the row's own evidence"):
        _score(wb, cells[0], ev[cells[0]],
               rationale=RATIONALE.format(e0="E-900", e1="E-901"))


def test_an_unchallenged_or_unresearched_row_cannot_be_scored(tmp_path):
    run = new_run(tmp_path, n=3)
    wb = run.open()
    cells = wb.selected_subcaps()
    for cell in cells:
        synthesise(wb, cell, good_synthesis(cell, bank_evidence(wb, cell, n=7)))
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    A.open_stage(wb, run.qa_dir)
    # forge the verdict away, the way an out-of-band edit would
    wb.set_scoring(cells[0], {"Challenge_Verdict": "FAIL"})
    with pytest.raises(ScoringRefusal, match="SURVIVED an independent challenge"):
        _score(wb, cells[0], ["E-001", "E-002"])
    # a row nobody researched and nobody declared
    wb.set_scoring(cells[1], {"Evidence_IDs": C.NO_EVIDENCE, "Dominant_Claim": None,
                              "Absence_Claimed": None})
    with pytest.raises(ScoringRefusal, match="absence was never declared"):
        _score(wb, cells[1], [], confidence="LOW")


def test_a_declared_absence_scores_at_the_cap_with_low_confidence(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    empty = cells[-1]
    with pytest.raises(ScoringRefusal, match="LOW confidence"):
        _score(wb, empty, [], score=1.5, confidence="MEDIUM")
    with pytest.raises(ScoringRefusal, match="above the evidence ceiling"):
        _score(wb, empty, [], score=2.5, confidence="LOW")
    out = _score(wb, empty, [], score=1.5, confidence="LOW")
    assert out["evidence_ceiling"] == A.NO_EVIDENCE_CEILING


def test_high_confidence_needs_two_source_identities(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    from fixtures import fire_volleys
    fire_volleys(wb, cell)
    eids = [L.append_evidence(
        wb, source_name=f"Annual Report p{i}", source_url=f"https://acme.example/ar#{i}",
        tier="T2", subcaps=[cell], published="2025-06-01",
        excerpt=("Alkami digital banking went live in Q3 2024 and reached 47 percent "
                 f"member adoption within ninety days, restated at {50+i} percent "
                 "in the 2025 report.")) for i in range(3)]
    syn = good_synthesis(cell, eids); syn["Claim_Label"] = "INFERENCE"
    synthesise(wb, cell, syn)
    synthesise(wb, wb.selected_subcaps()[1],
               good_synthesis(wb.selected_subcaps()[1], bank_evidence(wb, wb.selected_subcaps()[1])))
    floors_gate.run(wb, "P1C1", require_synthesis=True, qa_dir=run.qa_dir)
    A.open_stage(wb, run.qa_dir, force=True)
    with pytest.raises(ScoringRefusal, match="two source identities"):
        _score(wb, cell, eids, confidence="HIGH")


def test_the_overlay_is_a_contract_not_a_courtesy(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    with pytest.raises(ScoringRefusal, match="ai_applicability"):
        _score(wb, cells[0], ev[cells[0]], ai_applicability="MAYBE")
    with pytest.raises(ScoringRefusal, match="data_readiness"):
        _score(wb, cells[0], ev[cells[0]], data_readiness="BLUE")


# ── the critic, the rollup, the gate ─────────────────────────────────────

def test_the_critic_must_not_be_a_scorer(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    _score_all(wb, cells, ev)
    note = ("Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
            "differentiation present; would move nothing.")
    with pytest.raises(ScoringRefusal, match="cannot be its critic"):
        A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-p1-producer", note=note)
    with pytest.raises(ScoringRefusal, match="rubber stamp"):
        A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic", note="fine")
    out = A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic", note=note)
    assert out["verdict"] == "PASS"


def test_rollup_states_every_grain_and_the_dashboard(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    _score_all(wb, cells, ev)
    with pytest.raises(ScoringRefusal, match="headline"):
        A.rollup(wb)
    out = A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                                "sits a band below digital-leader peers")
    assert out["overall"] is not None
    assert {r["pillar_id"] for r in wb.rows("Pillar_Rollup")} >= {"P1", "OVERALL"}
    assert len(wb.rows("Category_Rollup")) == 1
    ps = {r["Pillar"]: r for r in wb.rows("Pillar_Summary")}
    assert ps["OVERALL"]["Maturity"]
    # no peer figure recorded → the gap is NULL, never a sentinel (invariant 9)
    assert ps["P1"]["Gap_to_Peer"] in (None, "")
    from fixtures import bank_peer_medians
    bank_peer_medians(wb, median=3.0)
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    ps = {r["Pillar"]: r for r in wb.rows("Pillar_Summary")}
    assert ps["P1"]["Peer_Median"] == 3.0
    assert abs(float(ps["P1"]["Gap_to_Peer"]) - (float(ps["P1"]["Score"]) - 3.0)) < 1e-9
    cm = wb.rows("Coverage_Map")[0]
    assert cm["evidence_gap"] == 1 and cm["coverage_pct"] is not None
    fields = {r["Field"] for r in wb.rows("Executive_Summary")}
    for want in ("Institution", "Overall Maturity", "Subcaps Scored",
                 "Evidence Gaps (Unknown)", "Headline"):
        assert want in fields, fields


def test_the_scoring_gate_fails_until_everything_holds_then_passes(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    A.open_stage(wb, run.qa_dir)
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "FAIL" and "unscored" in v["blocking"]
    _score_all(wb, cells, ev)
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "FAIL"
    assert {"critic_missing", "rollup_missing"} <= set(v["blocking"]), v["blocking"]
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    v = A.gate(wb, run.qa_dir)
    assert v["gate"] == "PASS", v["blocking"]
    assert (run.qa_dir / "scoring.json").exists()
    assert any(g["Gate"] == "SCORING" and g["Verdict"] == "PASS" for g in wb.rows("Gate_Log"))


def test_no_differentiation_within_a_capability_blocks(tmp_path):
    run, wb, cells, ev = _researched(tmp_path, n=6, absent=0)
    A.open_stage(wb, run.qa_dir)
    for cell in cells:
        _score(wb, cell, ev[cell], score=2.5)          # every subcap identical
    v = A.gate(wb, run.qa_dir)
    assert "no_differentiation" in v["blocking"]


# ── no report before scoring ─────────────────────────────────────────────

def _section(sec, eids):
    return section_record(sec.id, eids, report="assessment")


def test_the_assessment_report_refuses_to_start_before_the_scoring_gate(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    pre = N.stage_preconditions(wb, "assessment", run.qa_dir)
    assert any("research stage" in p for p in pre)
    assert any("SCORING gate" in p for p in pre)
    sec = RS.SPECS["assessment"].section("2")
    with pytest.raises(N.NarrativeRefusal, match="not ready for the Digital Maturity"):
        N.write(wb, "assessment", "2", _section(sec, ev[cells[0]]),
                actor="report-assessment-producer", run=run)


def test_the_research_profile_refuses_before_the_categories_are_gated(tmp_path):
    run = new_run(tmp_path, n=2)
    wb = run.open()
    eids = bank_evidence(wb, wb.selected_subcaps()[0])
    pre = N.stage_preconditions(wb, "client_research", run.qa_dir)
    assert pre and any("NOT_RUN" in p or "not ready" in p for p in pre)
    with pytest.raises(N.NarrativeRefusal, match="not ready for the Client Profile"):
        N.write(wb, "client_research", "8", section_record("8", eids), actor="report-research-producer", run=run)


def test_the_preconditions_clear_once_the_run_is_gated_and_scored(tmp_path):
    run, wb, cells, ev = _researched(tmp_path)
    assert N.stage_preconditions(wb, "client_research", run.qa_dir) == []
    A.open_stage(wb, run.qa_dir)
    _score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    assert A.gate(wb, run.qa_dir)["gate"] == "PASS"
    from fixtures import make_shippable
    make_shippable(wb)
    pre = N.stage_preconditions(wb, "assessment", run.qa_dir)
    assert [p for p in pre if "SCORING" in p or "research stage" in p] == []
