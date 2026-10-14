"""A ROUND_COMPLETE is a handover, and a handover needs a checklist.

`engine.pipeline run --step` stops a research round cleanly and names what is
outstanding in its `pending` payload: the relay batches nobody has serviced,
the categories still open, the budget and the rounds that remain. Until now
that payload arrived as JSON in a transcript and the conductor had to
reconstruct the next move from it. These pin the rendering — every
outstanding thing beside the command that closes it — the memory-backup
announcement, and the Stop hook's gap-based blocker with its three allowed
stops.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "stage_advance.py"


def _mod():
    spec = importlib.util.spec_from_file_location("stage_advance", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def run(tmp_path: Path) -> Path:
    d = tmp_path / "run-round"
    (d / "07_qa").mkdir(parents=True)
    (d / f"DMA_Scoring_Workbook_{d.name}.xlsx").write_bytes(b"stub")
    (d / "07_qa" / "pipeline_state.json").write_text(json.dumps({}))
    return d


@pytest.fixture()
def sa(run, monkeypatch):
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    monkeypatch.delenv("DMA_STAGE_GUARD", raising=False)
    return _mod()


PENDING = {
    "outcome": "ROUND_COMPLETE", "stage": "RESEARCH",
    "pending": {
        "relay_batches": ["/runs/r1/briefs/relay_r2/batch.md"],
        "open_categories": ["P2C3"],
        "stalled": ["P4C1"],
        "budget": {"spent": 6.5, "ceiling": 20.0, "remaining": 13.5},
        "rounds_remaining": 7,
        "gaps": {"categories": {
            "P1C1": {"open_cells": ["P1C1.3"], "undeclared_empty": ["P1C1.3"],
                     "unserviced_requests": 2, "stalled_rounds": 0,
                     "challenge_deferred": [], "proposals_unattached": 3},
            "P3C2": {"open_cells": [], "undeclared_empty": [],
                     "unserviced_requests": 0, "stalled_rounds": 2,
                     "challenge_deferred": ["P3C2.1"], "proposals_unattached": 0},
        }},
    },
}


def _event(text: str, command="python3 -m engine.pipeline run --run R --step"):
    return {"hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_input": {"command": command},
            "tool_response": {"stdout": text}}


def _ctx(out) -> str:
    return (out or {}).get("hookSpecificOutput", {}).get("additionalContext", "")


# ── the checklist ────────────────────────────────────────────────────────

def test_every_outstanding_thing_arrives_with_the_command_that_closes_it(sa):
    text = _ctx(sa.round_complete(_event(json.dumps(PENDING))))
    assert "ROUND COMPLETE" in text
    # the relay batch, with the actor that can service it
    assert "relay_r2/batch.md" in text
    assert "enrichment-web-specialist" in text
    assert "agent_run.py" in text
    # the gap classes, each with its command
    assert "EMPTY AND UNDECLARED" in text and "engine.cli absence" in text
    assert "engine.brief correlate --category P1C1" in text
    assert "research-challenger" in text          # challenge_deferred
    assert "P4C1" in text                         # stalled
    assert "engine.cli gate --category P2C3" in text
    # and the budget that bounds how many more of these there can be
    assert "$6.50 spent of $20.00" in text
    assert "7 remaining" in text


def test_it_only_speaks_on_a_round_complete(sa):
    assert sa.round_complete(_event("PASS at RESEARCH")) is None
    assert sa.round_complete(_event("")) is None


def test_a_driver_that_did_not_print_its_payload_is_recomputed_and_says_so(sa):
    """Without `--json` the driver prints one line and the payload never
    reaches the transcript. The checklist is then read from the substrate."""
    text = _ctx(sa.round_complete(_event("\nROUND_COMPLETE at RESEARCH: one round ran")))
    assert "recomputed from the run" in text
    assert "--json" in text


# ── the memory backup ────────────────────────────────────────────────────

def test_a_round_with_no_recorded_backup_announces_not_run(sa, run):
    text = _ctx(sa.round_complete(_event(json.dumps(PENDING))))
    assert "MEMORY BACKUP — NOT_RUN" in text
    assert "03_memory" in text


def test_a_partial_backup_is_announced(sa, run):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"memory_backup": {"at": "2026-09-14T10:00:00Z", "status": "PARTIAL"}}))
    text = _ctx(sa.round_complete(_event(json.dumps(PENDING))))
    assert "MEMORY BACKUP — PARTIAL" in text


def test_a_resolved_backup_says_nothing(sa, run):
    """A hook that speaks on success trains people to ignore it."""
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"memory_backup": {"at": "2026-09-14T10:00:00Z", "status": "RESOLVED"}}))
    text = _ctx(sa.round_complete(_event(json.dumps(PENDING))))
    assert "MEMORY BACKUP" not in text


def test_a_backup_that_could_not_run_is_announced_with_its_reason(sa, run):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"memory_backup": {"at": "2026-09-14T10:00:00Z",
                           "status": "NOT_RUN: drive_fetch.py absent"}}))
    text = _ctx(sa.round_complete(_event(json.dumps(PENDING))))
    assert "MEMORY BACKUP — NOT_RUN" in text
    assert "drive_fetch.py absent" in text


# ── the Stop blocker ─────────────────────────────────────────────────────

def test_a_persons_blocker_never_holds_the_stop(sa):
    """BLOCKED_NO_CONNECTOR and AT_USD_CEILING are somebody's decision; the
    watchdog already keeps both out of AGENT_ADVANCEABLE and the gaps
    blocker must not put them back."""
    for state in ("BLOCKED_NO_CONNECTOR", "AT_USD_CEILING", "HALTED",
                  "UNREADABLE", "MISSING_LOCALLY"):
        assert sa._gaps_blocker({"state": state, "run_id": "r"}) == "", state


def test_an_exhausted_budget_never_holds_the_stop(sa, run):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"spent_usd": 21.0, "budget_usd": 20.0}))
    assert sa._gaps_blocker({"state": "STALLED", "run_id": run.name}) == ""


def test_exhausted_rounds_never_hold_the_stop(sa, run):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"spent_usd": 1.0, "budget_usd": 20.0,
         "stages": {"RESEARCH": {"rounds": 999}}}))
    assert sa._gaps_blocker({"state": "STALLED", "run_id": run.name}) == ""


def test_stop_hook_active_never_blocks(sa):
    assert sa.on_stop({"hook_event_name": "Stop", "stop_hook_active": True}) is None


def test_the_stage_guard_off_switch_still_reaches_only_the_conductor(sa, monkeypatch):
    """agent_run.py sets DMA_STAGE_GUARD=off in every lane; the Stop guard
    must stay out of them."""
    monkeypatch.setenv("DMA_STAGE_GUARD", "off")
    assert sa.on_stop({"hook_event_name": "Stop"}) is None


def test_an_unserviced_relay_batch_holds_the_stop_with_the_next_dispatch(sa, run,
                                                                         monkeypatch):
    (run / "07_qa" / "pipeline_state.json").write_text(json.dumps(
        {"spent_usd": 1.0, "budget_usd": 20.0,
         "relay_batches": [str(run / "briefs" / "relay_r1" / "batch.md")],
         "stages": {"RESEARCH": {"rounds": 1}}}))
    ctx = sa._ctx()
    relay, = ctx.engine("relay")
    monkeypatch.setattr(relay, "requests",
                        lambda r: {"q1": {"status": "OPEN"}})
    brief, = ctx.engine("brief")
    monkeypatch.setattr(brief, "gaps", lambda wb, r: {"categories": {}})
    monkeypatch.setattr(ctx.locate().__class__, "open",
                        lambda self: None, raising=False)
    why = sa._gaps_blocker({"state": "STALLED", "run_id": run.name})
    assert "STOP HELD" in why
    assert "enrichment-web-specialist" in why
    assert "relay_r1" in why
