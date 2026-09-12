"""The stage machine after research: scoring, critic, gate, reports, package.

Owner, 2026-09-03: "what hooks signal the scoring agents once research is
done … what hooks invoke the report writing agents and challenging agents
once scoring is done. Ensure it is a cohesive robust workflow."

`engine.watchdog` used to stop at READY_FOR_HANDOFF — every later stage read
as the same resting state, and the only revive plan was "render the four
deliverables". These pin the continuation: each state is computed from the
workbook the gates already read, names the agent that owns the next unit of
work, and carries the criterion that closes it.
"""
from __future__ import annotations

import json

from engine import assessment as A
from engine import narrative as N
from engine import watchdog
from fixtures import make_shippable, researched_run, score_all


def _scored(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    A.open_stage(wb, run.qa_dir)
    return run, wb, cells, ev


def _gated(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    assert A.gate(wb, run.qa_dir)["gate"] == "PASS"
    make_shippable(wb)
    _close_stage_tabs(wb)
    return run, wb, cells, ev


def _close_stage_tabs(wb):
    """The SCORING stage's own catalogue tabs — filled where there is a
    platform to name, declared where the fixture's estate has none. Until
    they are, `engine.narrative write` refuses every section."""
    from engine import completeness
    if not [r for r in wb.rows("Solution_Catalogue") if any(r.values())]:
        A.solution(wb, sol_id="SOL-01", name="Digital onboarding and account opening",
                   platform="Alkami", categories=["P1C1"])
    if not [r for r in wb.rows("Platform_Peer_Adoption") if any(r.values())]:
        completeness.declare(
            wb, "Platform_Peer_Adoption",
            "no peer institution's deployment of the named products could be "
            "examined in this fixture run, so no adoption verdict is recorded")


# ── research closed, assessment not open ──────────────────────────────────

def test_a_gated_research_run_is_told_to_open_the_scoring_stage(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    row = watchdog.inspect(run)
    assert row["state"] == "READY_FOR_HANDOFF"
    assert row["resume"]["agent"] == "research-conductor"
    assert "engine.assessment open" in row["resume"]["prompt"]
    assert "scorers" in row["resume"]["prompt"]
    assert row["criterion"]


# ── the scoring stage, step by step ──────────────────────────────────────

def test_an_open_assessment_stage_with_unscored_rows_routes_to_the_pillar_scorer(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    row = watchdog.inspect(run)
    assert row["state"] == "SCORING_OPEN"
    assert row["state"] in watchdog.ACTIONABLE
    assert row["state"] in watchdog.AGENT_ADVANCEABLE
    assert row["unscored_by_pillar"] == {"P1": len(cells)}
    plan = row["resume"]
    assert plan["actionable"] and plan["agent"] == "scoring-p1-producer"
    assert plan["parallel"] == ["scoring-p1-producer"]
    assert "engine.assessment score" in plan["prompt"]


def test_a_partly_scored_pillar_still_routes_to_its_scorer(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    from fixtures import score_cell
    score_cell(wb, cells[0], ev[cells[0]])
    row = watchdog.inspect(run)
    assert row["state"] == "SCORING_OPEN"
    assert row["unscored_by_pillar"]["P1"] == len(cells) - 1


def test_every_row_scored_and_no_critic_routes_to_the_critic(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    row = watchdog.inspect(run)
    assert row["state"] == "CRITIC_PENDING"
    assert row["critic_missing"] == ["P1"]
    assert row["resume"]["agent"] == "scoring-critic"
    assert "engine.assessment critique" in row["resume"]["prompt"]


def test_a_failed_critic_is_still_the_critics_state_and_says_so(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="FAIL", actor="scoring-critic",
               note="Two rows flatter the evidence: P1C1.1.2 reads M3 on a single "
                    "T3 source; P1C1.1.4 ignores its own counter-evidence.")
    row = watchdog.inspect(run)
    assert row["state"] == "CRITIC_PENDING"
    assert row["critic_failed"] == ["P1"]
    assert "re-scored" in row["resume"]["prompt"]


def test_critic_in_and_gate_not_run_routes_to_the_conductor(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    row = watchdog.inspect(run)
    assert row["state"] == "SCORING_GATE_OPEN"
    assert "never been run" in row["detail"]
    assert row["resume"]["agent"] == "research-conductor"
    assert "engine.assessment gate" in row["resume"]["prompt"]
    assert "checkpoint" in row["resume"]["prompt"]


def test_a_failing_gate_names_its_verdict(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    assert A.gate(wb, run.qa_dir)["gate"] == "FAIL"          # no rollup yet
    row = watchdog.inspect(run)
    assert row["state"] == "SCORING_GATE_OPEN"
    assert "FAIL" in row["detail"] and "rollup_missing" in row["detail"]


# ── the report tier, once the gate has passed ─────────────────────────────

def test_a_passing_gate_with_open_preconditions_routes_to_the_conductor(tmp_path):
    """Found by the hook walk on 2026-09-04: the SCORING gate passes with the
    stage's catalogue tabs still empty, and `engine.narrative write` refuses
    every section until they are filled or declared. That is the conductor's
    unit of work, and it has its own state so the report producers are not
    dispatched into a refusal."""
    run, wb, cells, ev = _scored(tmp_path)
    score_all(wb, cells, ev)
    A.critique(wb, pillar="P1", verdict="PASS", actor="scoring-critic",
               note="Re-derived 4 of 6 rows across the capabilities; ceilings hold; "
                    "differentiation present; would move nothing.")
    A.rollup(wb, headline="Modern rails, unbuilt member-relationship layer: "
                          "sits a band below digital-leader peers")
    assert A.gate(wb, run.qa_dir)["gate"] == "PASS"
    make_shippable(wb)
    row = watchdog.inspect(run)
    assert row["state"] == "REPORT_PRECONDITIONS_OPEN"
    assert row["state"] in watchdog.AGENT_ADVANCEABLE
    assert any("Solution_Catalogue" in p for p in row["preconditions"])
    plan = row["resume"]
    assert plan["agent"] == "research-conductor"
    assert "engine.assessment solution" in plan["prompt"]
    assert "engine.completeness declare" in plan["prompt"]
    assert row["criterion"]
    _close_stage_tabs(wb)
    assert watchdog.inspect(run)["state"] == "REPORTS_OPEN"


def test_a_passing_gate_with_no_report_written_routes_to_both_producers(tmp_path):
    run, wb, cells, ev = _gated(tmp_path)
    row = watchdog.inspect(run)
    assert row["state"] == "REPORTS_OPEN"
    assert row["checkpoint_due"] is True, "SCORING_PASS was never checkpointed"
    plan = row["resume"]
    assert set(plan["parallel"]) == {"report-assessment-producer",
                                     "report-research-producer"}
    assert "SCORING_PASS" in plan["prompt"]
    assert "engine.narrative write" in plan["prompt"]
    for key in ("assessment", "client_research"):
        assert row["reports"][key]["ready"] is False
        assert row["reports"][key]["open"]


def test_written_but_unreviewed_sections_route_to_the_validator():
    """Once every section is written, the open work is the VERDICT, and the
    verdict belongs to an actor that did not write the section."""
    row = {"reports": {
        "assessment": {"ready": False, "open": ["1", "2"],
                       "sections": [{"section": "1", "status": "UNREVIEWED"},
                                    {"section": "2", "status": "UNREVIEWED"}]},
        "client_research": {"ready": True, "open": [], "sections": []},
    }}
    assert watchdog._report_agents(row) == ["report-validator"]


def test_open_sections_route_to_the_producer_and_unreviewed_to_the_validator():
    row = {"reports": {
        "assessment": {"ready": False, "open": ["1", "8"],
                       "sections": [{"section": "1", "status": "UNREVIEWED"},
                                    {"section": "8", "status": "SHORT"}]},
        "client_research": {"ready": False, "open": ["3"],
                            "sections": [{"section": "3", "status": "OPEN"}]},
    }}
    agents = watchdog._report_agents(row)
    assert agents == ["report-assessment-producer", "report-validator",
                      "report-research-producer"]


def test_a_revise_verdict_goes_back_to_the_producer():
    row = {"reports": {
        "client_research": {"ready": False, "open": ["5"],
                            "sections": [{"section": "5", "status": "REVISE"}]}}}
    assert watchdog._report_agents(row) == ["report-research-producer"]


def test_the_checkpoint_stops_being_due_once_pushed(tmp_path):
    run, wb, cells, ev = _gated(tmp_path)
    from engine import assemble
    assemble.checkpoint(run, tmp_path / "client", push=False,
                        stage_reached="SCORING_PASS")
    row = watchdog.inspect(run)
    assert row["state"] == "REPORTS_OPEN"
    assert row["checkpoint_due"] is False
    assert "SCORING_PASS checkpoint has NOT" not in row["resume"]["prompt"]


# ── the criterion travels with the state ──────────────────────────────────

def test_every_actionable_state_states_its_completion_criterion():
    for state in watchdog.ACTIONABLE:
        if state in ("UNREADABLE", "HALTED", "MISSING_LOCALLY", "NO_CLIENT_FOLDER"):
            continue
        assert watchdog.COMPLETION_CRITERIA.get(state), state


def test_the_agent_advanceable_set_excludes_the_decisions_a_person_makes():
    for state in ("UNREADABLE", "HALTED", "MISSING_LOCALLY"):
        assert state not in watchdog.AGENT_ADVANCEABLE
    for state in ("SCORING_OPEN", "CRITIC_PENDING", "REPORTS_OPEN",
                  "PACKAGE_UNSHIPPED", "GATE_FAILED", "PRELIM_OPEN"):
        assert state in watchdog.AGENT_ADVANCEABLE


def test_the_resume_plan_is_serialisable_for_the_hook(tmp_path):
    run, wb, cells, ev = _scored(tmp_path)
    row = watchdog.inspect(run)
    json.dumps(row)                       # a plan a hook cannot print is no plan
