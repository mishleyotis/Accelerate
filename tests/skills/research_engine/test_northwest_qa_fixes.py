"""Defects measured on the Northwest Bank live run (2026-10-01, N-xx in
qa_audit/2026-10-01-northwest/CASE_FACTS.md) — each pinned at its seam."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from engine import cost, pipeline as P, pipeline_stub as S, preflight, prelim
from fixtures import bank_evidence, new_run, preflight_doc, two_category_selection

ENGINE = Path(__file__).resolve().parents[3] / "plugins" / "dma-insights" / "skills" / "dma-research"


def _run(tmp_path):
    run = new_run(tmp_path, selected=two_category_selection(3))
    preflight.record(run, preflight_doc())
    return run


# ── N-09 · the step-4 estimate is the rate the research handoff uses ─────

def test_the_estimate_is_the_measured_workflow_rate(tmp_path):
    run = _run(tmp_path)
    est = cost.workflow_estimate(run.open())
    cats = len(est["pillars"]) and sum(p["categories"] for p in est["pillars"].values())
    assert est["open_cells"] == 6 and cats == 2
    assert est["research_usd"] == round(6 * P.WORKFLOW_USD_PER_CELL
                                        + 2 * P.CHALLENGE_USD_PER_CATEGORY, 2)


def test_the_estimate_and_the_research_handoff_agree(tmp_path):
    run = _run(tmp_path)
    opts = P.Options(dispatcher=S.StubDispatcher(handlers={}), reads=S.StubReads(),
                     shipper=S.StubShipper(), push=False,
                     folder_root=tmp_path / "out", ingest_poll_s=0,
                     sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
                     max_rounds=2, stall_rounds=0, research_mode="workflow")
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "AWAITING_WORKFLOW", out
    handed = json.loads(Path(out["handoff"]).read_text())["estimate"]
    est = cost.workflow_estimate(run.open())
    assert handed["usd"] == est["research_usd"]
    assert handed["batches"] == est["batches"]


def test_the_cli_estimate_says_over_when_the_ceiling_is_short(tmp_path):
    run = _run(tmp_path)
    cmd = [sys.executable, "-m", "engine.cost", "estimate", "--run", run.run_id,
           "--root", str(run.root)]
    ok = subprocess.run(cmd + ["--max-usd", "50"], cwd=ENGINE, capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "RESEARCH estimate" in ok.stdout and "fits" in ok.stdout
    short = subprocess.run(cmd + ["--max-usd", "0.5"], cwd=ENGINE, capture_output=True, text=True)
    assert short.returncode == 1 and "OVER by" in short.stdout


# ── N-10 · the schedule models the workflows research actually runs as ───

def test_the_schedule_is_one_workflow_per_category(tmp_path):
    run = _run(tmp_path)
    sch = cost.workflow_schedule(run.open(), cpus=4)
    assert sch["mode"] == "workflow"
    assert sch["workflows"] == 2 and sch["agents_per_workflow"] == 2
    assert sch["peak_agents"] == 4
    # one batch per category fits in one wave
    assert sch["research_parallel_min"] == cost.WORKFLOW_BATCH_MIN


def test_workflow_concurrency_follows_the_runtime_cap():
    assert cost.workflow_concurrency(4) == 2
    assert cost.workflow_concurrency(2) == 1
    assert cost.workflow_concurrency(64) == 16


# ── N-15 · comma-joined evidence ids are ids, not one unknown id ─────────

def test_comma_joined_evidence_ids_are_split(tmp_path):
    run = new_run(tmp_path, prelim=False)
    wb = run.open()
    ids = bank_evidence(wb, wb.selected_subcaps()[0], n=2)
    ids = [i if isinstance(i, str) else i.get("evidence_id") for i in ids]
    body = ("Northwest Bancshares is a Pennsylvania-chartered savings bank holding "
            "company with 151 financial centers and $16.8B of assets at FY2025. ") * 3
    with pytest.raises(prelim.PrelimRefusal) as exc:
        prelim.narrate(wb, "firmographics", heading=None, body=body,
                       evidence=["E-998,E-999"])
    assert "E-998, E-999" in str(exc.value)
    out = prelim.narrate(wb, "firmographics", heading=None, body=body,
                         evidence=[",".join(ids)])
    assert out


# ── N-17 · the driver's log lands where the command says to watch ────────

def test_the_driver_log_is_teed_to_the_watched_file(tmp_path):
    seen = []
    log = P._tee_log(tmp_path / P.LOG_NAME, seen.append)
    log("[RELAY] PRELIM connector brief …")
    assert seen == ["[RELAY] PRELIM connector brief …"]
    assert "[RELAY]" in (tmp_path / "pipeline.log").read_text()
