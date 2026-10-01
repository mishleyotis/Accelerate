"""Two stops that end on a person, and a sweep that must not spend money on
them.

MEASURED 2026-09-14. `watchdog.inspect` never read `pipeline_state.json`, so
a run the dollar ceiling had stopped looked exactly like one whose gates had
failed — FLOORS FAIL rows are what a half-finished research stage leaves
behind. `GATE_FAILED` is in `AGENT_ADVANCEABLE`, so the hourly `--revive`
re-ran `engine.pipeline run` on it. Paired with a driver that started every
process at $0 spent, that is a fresh budget every hour, forever.

And `resume_plan` had no branch for `BLOCKED_NO_CONNECTOR` at all: it fell
through to the default and reported "the run is working" for a run that
structurally cannot advance — while `COMPLETION_CRITERIA` for the same state
says the opposite, in the same module.
"""
from __future__ import annotations

import json

import pytest

from engine import watchdog as W


def _row(state, **kw):
    return {"state": state, "run_id": "R-1", "root": "/tmp/r", "entity": "Acme",
            **kw}


# ── the states a person owns ───────────────────────────────────────────

def test_a_budget_stopped_run_has_its_own_state():
    assert "AT_USD_CEILING" in W.COMPLETION_CRITERIA
    assert "raise" in W.COMPLETION_CRITERIA["AT_USD_CEILING"].lower()


@pytest.mark.parametrize("state", ["AT_USD_CEILING", "BLOCKED_NO_CONNECTOR"])
def test_those_states_are_actionable_but_never_auto_revived(state):
    """Someone is told; no agent is dispatched. The whole point of the
    distinction `--revive` walked past once already."""
    assert state in W.ACTIONABLE
    assert state not in W.AGENT_ADVANCEABLE


@pytest.mark.parametrize("state", ["AT_USD_CEILING", "BLOCKED_NO_CONNECTOR"])
def test_resume_plan_names_the_person_rather_than_an_agent(state):
    plan = W.resume_plan(_row(state))
    assert plan["actionable"] is False, plan
    assert plan.get("agent") is None
    assert plan["why"] and plan["why"] != "the run is working"
    assert plan.get("needs") == "person"


def test_no_actionable_state_reports_the_run_as_working():
    """The default branch is for a run that IS working. A state that reached
    ACTIONABLE has already been judged not to be."""
    for state in W.ACTIONABLE:
        plan = W.resume_plan(_row(state, open=["P1C1"], gate_failed=["P1C1"],
                                  ungated=["P1C1"]))
        assert plan["why"] != "the run is working", state


def test_the_dollar_ceiling_is_not_the_search_op_ceiling():
    """`AT_BUDGET_CEILING` is the 60-search-op checkpoint wall, which an
    agent clears itself. Reusing it for money would have hidden the stop
    that needs a person inside the one that does not."""
    assert W.COMPLETION_CRITERIA["AT_BUDGET_CEILING"] != \
        W.COMPLETION_CRITERIA["AT_USD_CEILING"]
    assert "AT_BUDGET_CEILING" in W.AGENT_ADVANCEABLE


# ── read from the driver's own record ──────────────────────────────────

def test_inspect_reads_the_budget_stop_from_the_pipeline_state(tmp_path):
    from engine import preflight, pipeline as P, pipeline_stub as S
    from fixtures import new_run, preflight_doc
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    (run.qa_dir).mkdir(parents=True, exist_ok=True)
    (run.qa_dir / "pipeline_state.json").write_text(json.dumps({
        "pipeline_version": 1, "stages": {}, "pages": {}, "connector": {},
        "package": {}, "invocations": [], "last_outcome": "STOPPED_BUDGET",
        "spent_usd": 96.65, "budget_usd": 20.0}))
    row = W.inspect(run)
    assert row["state"] == "AT_USD_CEILING", row
    assert "96.65" in row["detail"] and "20" in row["detail"]


def test_a_run_that_merely_failed_a_gate_is_still_agent_work(tmp_path):
    """The narrowing must not swallow the ordinary case."""
    from engine import preflight
    from fixtures import new_run, preflight_doc
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    (run.qa_dir).mkdir(parents=True, exist_ok=True)
    (run.qa_dir / "pipeline_state.json").write_text(json.dumps(
        {"stages": {}, "last_outcome": "FAILED"}))
    assert W.inspect(run)["state"] != "AT_USD_CEILING"
