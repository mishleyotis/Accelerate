"""The routing decision, made once in code instead of per session.

WHAT IT COST. Measured 2026-08-30: a session asked to finalise GoEasy called
`get_client_state("goeasy")`, got `unknown_entity`, and fired the ASSESSMENT
INTAKE routine — the entry point for a client with no package. GoEasy's real
id is `goeasy-ltd` and it already had four ingested runs. The firing was
interrupted before it pushed a preflight for research that was already done.

Two mistakes, and the second is the one worth pinning: even with the right
id, "has a package" is not one state. GoEasy's four runs scored ZERO cells
between them — a research package, whose score column is empty by contract.
Sending that to a producer spends a session to be told there is nothing to
serve; sending it to intake spends one redoing finished research. The right
answer was neither, and no prompt sentence reliably produces it because
every session re-derives it from scratch.

These tests drive `decide()` over the connector's own answer shapes. They
carry no database: the question is what to CONCLUDE from a state document,
and that conclusion should be checkable without one.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))

import route_client as RC                                     # noqa: E402


def _state(runs=(), served=(), display_id="acme-bank"):
    return {"display_id": display_id, "runs": list(runs),
            "served_pages": list(served)}


def _run(seq, scored):
    return {"run_id": f"r{seq}", "run_seq": seq, "scored_cells": scored,
            "status": "INGESTED"}


# ── the GoEasy shape, both halves ────────────────────────────────────────

def test_a_research_package_is_neither_an_intake_nor_a_synthesis():
    """THE DEFECT. Four ingested runs, zero scored cells."""
    out = RC.decide(_state([_run(i, 0) for i in (1, 2, 3, 4)],
                           display_id="goeasy-ltd"), "goeasy-ltd")
    assert out["verdict"] == RC.NEEDS_SCORING
    assert "dma-assessment" in out["next"]
    assert "already done" in out["why"], (
        "the verdict must say the research EXISTS, or the reader routes it "
        "back to intake — which is the mistake being fixed")


def test_the_bare_name_does_not_read_as_a_new_client():
    """The first half: `goeasy` against `goeasy-ltd`. It must not resolve
    itself either — picking a client on a trigram score is the same silent
    inference one layer down."""
    out = RC.decide({"error": "unknown_entity", "display_id": "goeasy",
                     "did_you_mean": [{"display_id": "goeasy-ltd",
                                       "legal_name": "goeasy Ltd.",
                                       "similarity": 0.6}]}, "goeasy")
    assert out["verdict"] == RC.AMBIGUOUS
    assert out["verdict"] != RC.NEW_ENGAGEMENT, (
        "a near miss routed to intake is exactly the 2026-08-30 firing")
    assert "goeasy-ltd" in out["next"]


def test_a_genuine_stranger_is_an_intake():
    """The suggestion must not turn every miss into a hold — a client that
    really is new has to reach the intake path."""
    out = RC.decide({"error": "unknown_entity", "display_id": "novel-cu",
                     "did_you_mean": []}, "novel-cu")
    assert out["verdict"] == RC.NEW_ENGAGEMENT
    assert "dma-research" in out["next"]


# ── the other three states ───────────────────────────────────────────────

def test_a_scored_unpromoted_run_is_synthesis_work():
    out = RC.decide(_state([_run(1, 0), _run(2, 640)]), "acme-bank")
    assert out["verdict"] == RC.READY_TO_SYNTHESISE
    assert out["scored_runs"] == 1 and out["runs"] == 2


def test_a_promoted_client_is_a_rerun_and_says_so():
    """A rerun is a different job from a first synthesis and the skill
    requires it be produced knowing what the last one said."""
    out = RC.decide(_state([_run(1, 640)], served=["overview", "heatmap"]),
                    "acme-bank")
    assert out["verdict"] == RC.ALREADY_SERVED
    assert "rerun" in out["why"].lower() or "RERUN" in out["why"]


def test_an_entity_with_no_runs_is_an_intake():
    """It exists in the corpus — perhaps from an earlier request — but
    nothing has been ingested, so intake is right."""
    out = RC.decide(_state([]), "acme-bank")
    assert out["verdict"] == RC.NEW_ENGAGEMENT


def test_one_scored_run_among_many_unscored_still_counts():
    """The check is "is there anything to serve", not "is everything
    scored" — a research package sitting beside a finished assessment must
    not hide the assessment."""
    out = RC.decide(_state([_run(1, 0), _run(2, 0), _run(3, 12)]), "acme")
    assert out["verdict"] == RC.READY_TO_SYNTHESISE


def test_a_null_scored_count_is_not_read_as_scored():
    """`scored_cells: null` is unknown. Treating it as work is the gamble
    the synthesis queue refuses; treating it as scored would be worse."""
    out = RC.decide(_state([{"run_id": "r1", "run_seq": 1,
                             "scored_cells": None}]), "acme")
    assert out["verdict"] == RC.NEEDS_SCORING


# ── the exit codes, which are the machine-readable half ──────────────────

def test_every_verdict_has_a_distinct_exit_code(monkeypatch):
    """A routine branches on these without parsing prose, so two verdicts
    sharing a code would silently merge two different next steps."""
    seen = {}
    for verdict, state in (
            (RC.READY_TO_SYNTHESISE, _state([_run(1, 5)])),
            (RC.NEEDS_SCORING, _state([_run(1, 0)])),
            (RC.NEW_ENGAGEMENT, {"error": "unknown_entity",
                                 "did_you_mean": []}),
            (RC.ALREADY_SERVED, _state([_run(1, 5)], served=["overview"])),
            (RC.AMBIGUOUS, {"error": "unknown_entity", "did_you_mean": [
                {"display_id": "x", "legal_name": "X", "similarity": 0.5}]}),
    ):
        monkeypatch.setattr(RC, "client_state", lambda d, s=state: s)
        code = RC.main(["--client", "acme", "--json"])
        assert code not in seen, (
            f"{verdict} shares exit code {code} with {seen[code]}")
        seen[code] = verdict
    assert 1 not in seen, (
        "exit 1 is the script's own failure; a routine that read it as a "
        "routing answer would act on a crash")


def test_an_unreachable_connector_is_not_a_routing_answer(monkeypatch):
    """UNKNOWN must be distinguishable from every verdict. A connector
    outage that read as NEW_ENGAGEMENT would fire an intake for a client
    that already has a package — the 2026-08-30 firing, caused differently."""
    def _boom(_d):
        raise RuntimeError("connector unreachable")
    monkeypatch.setattr(RC, "client_state", _boom)
    assert RC.main(["--client", "acme"]) == 2
