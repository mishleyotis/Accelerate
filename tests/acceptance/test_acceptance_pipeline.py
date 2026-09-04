"""Acceptance: the DRIVER. Issues 6, 7 and 9 as the owner wrote them.

  6  "The reports and the scoring workbook should spin multiple agents /
      subagents with a clear gated workflow."
  7  "Token bleed at promotion … agents should submit to the MCP connector
      as research progresses so promotion is already done at the end;
      parallelize with gating."
  9  "The assessment takes more than 6 hours."

Every test drives `engine.pipeline` with the stub doubles — the lanes are
played by the same fixtures every engine test uses, THROUGH the engine's own
refusals, so a stub run still has to pass every gate a real run passes. What
is asserted is the driver's behaviour: order, gates, re-dispatch, retries,
timings, resume, idempotence, and that no payload byte ever enters a prompt.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from engine import assessment as A, brief, cost, pipeline as P, pipeline_stub as S
from engine import runstate, watchdog

from fixtures import new_run, researched_run, scored_run

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
SKILL = PLUGIN / "skills" / "dma-research"


def _opts(tmp_path, **over):
    kw = dict(dispatcher=S.StubDispatcher.fixture_backed(), reads=S.StubReads(),
              shipper=S.StubShipper(), push=False, folder_root=tmp_path / "client_out",
              ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None)
    kw.update(over)
    return P.Options(**kw)


def _fresh(tmp_path):
    """A started run with an ANSWERED preflight recorded and PRELIM still
    open — the state `engine.cli start` leaves a real run in."""
    from engine import preflight
    from fixtures import preflight_doc
    run = new_run(tmp_path, n=6, prelim=False)
    preflight.record(run, preflight_doc())
    return run


# ═══════════════════════════════════════════════════════════════════════════
# the whole path, in order, with timings
# ═══════════════════════════════════════════════════════════════════════════

def test_a_stub_run_walks_every_stage_in_order_to_promote(tmp_path):
    run = _fresh(tmp_path)
    opts = _opts(tmp_path)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE", out
    assert out["stages_run"] == list(P.STAGES[2:]), out["stages_run"]
    wb = run.open()
    md = wb.metadata()
    assert md["promoted_at"] and md["connector_run_id"] and md["connector_run_id_prev"]
    assert md["connector_run_id"] != md["connector_run_id_prev"]
    assert md["pipeline_version"] == P.PIPELINE_VERSION
    # every stage recorded its verdict AND its wall clock, in two places
    gates = [(g["Gate"], g["Verdict"]) for g in wb.rows("Gate_Log")
             if str(g["Gate"]).startswith("STAGE_")]
    assert gates == [(f"STAGE_{s}", "PASS") for s in P.STAGES[2:]]
    timings = json.loads(md["stage_timings"])
    assert set(timings) == set(P.STAGES[2:])
    assert all("elapsed_s" in t for t in timings.values())
    rep = cost.report(run, wb=wb)
    assert rep["records"] >= len(P.STAGES[2:]) and rep["within"]
    # the lanes ran in the gated order: research before scoring before reports before pages
    order = [c["stage"] for c in opts.dispatcher.calls]
    first = {s: order.index(s) for s in dict.fromkeys(order)}
    assert first["PRELIM"] < first["RESEARCH"] < first["SCORING"] < first["REPORTS"] \
        < first["PAGES_B"]
    assert first["PAGES_A"] < first["PAGES_B"]
    # the driver's own state file says the same
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert st["connector"]["promoted"]["run_id"] == md["connector_run_id"]


def test_issue6_scoring_runs_five_lanes_behind_two_gates(tmp_path):
    """Four pillar scorers … plus the critic, and nothing scores until the
    floors gate PASSED on every category, nothing reports until the SCORING
    gate PASSED. In a one-pillar run that is one scorer, one solutions lane
    and one critic — dispatched, not narrated."""
    run = _fresh(tmp_path)
    opts = _opts(tmp_path, until="SCORING")
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL" and out["stage"] == "SCORING"
    lanes = [(c["stage"], c["agent"]) for c in opts.dispatcher.calls]
    scoring = [a for s, a in lanes if s == "SCORING"]
    assert "scoring-p1-producer" in scoring and "scoring-critic" in scoring
    assert "technographic-scanner" in scoring              # the solutions duty
    assert scoring.index("scoring-p1-producer") < scoring.index("scoring-critic")
    # gate order: research gate rows precede the scoring stage row
    gates = [g["Gate"] for g in run.open().rows("Gate_Log")]
    assert gates.index("STAGE_RESEARCH") < gates.index("STAGE_SCORING")
    assert "SCORING" in gates and gates.index("FLOORS") < gates.index("SCORING")
    # and not one report lane ran
    assert not [a for s, a in lanes if s == "REPORTS"]


def test_issue6_a_critic_fail_redispatches_the_scoring_round(tmp_path):
    """The critic's FAIL is not the end of scoring: the driver runs another
    round (scorers see only unscored rows; the critic re-verdicts)."""
    run = _fresh(tmp_path)
    critic_calls = {"n": 0}
    handlers = S.default_handlers()

    def flaky_critic(agent, prompt_file, ctx):
        critic_calls["n"] += 1
        wb = ctx.run.open()
        if critic_calls["n"] == 1:
            for pillar in sorted({c[:2] for c in wb.selected_subcaps()}):
                A.critique(wb, pillar=pillar, verdict="FAIL", actor="scoring-critic",
                           note="Re-derived 4 of 6 rows: two rationales cite descriptors "
                                "the rubric does not carry; ceilings hold; would move two scores.")
            return
        S.lane_critic(agent, prompt_file, ctx)
    handlers["scoring-critic"] = flaky_critic
    opts = _opts(tmp_path, dispatcher=S.StubDispatcher(handlers), until="SCORING", max_rounds=3)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    assert critic_calls["n"] == 2
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert st["stages"]["SCORING"]["rounds"] == 2


def test_issue6_report_producers_start_from_a_brief_the_driver_wrote(tmp_path):
    run = _fresh(tmp_path)
    opts = _opts(tmp_path, until="REPORTS")
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL"
    reps = [c for c in opts.dispatcher.calls if c["stage"] == "REPORTS"]
    agents = [c["agent"] for c in reps]
    assert agents[:2] == ["report-research-producer", "report-assessment-producer"]
    assert agents[2] == "report-validator"
    for c in reps:
        text = Path(c["prompt_file"]).read_text()
        assert "Your first commands" in text and "engine.cli narrative" in text
        assert "references/templates" in text or "gold_reference" in text
    # the two reports are rendered by the driver, from the workbook
    assert list(run.deliverables.glob("Client_Profile_Research_*.docx"))
    assert list(run.deliverables.glob("DMA_Assessment_Report_*.docx"))


# ═══════════════════════════════════════════════════════════════════════════
# issue 7 · ship as you go
# ═══════════════════════════════════════════════════════════════════════════

def test_issue7_early_pages_ship_to_version_a_while_reports_are_written(tmp_path):
    run = _fresh(tmp_path)
    opts = _opts(tmp_path)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE"
    ships = opts.shipper.ships
    runs_seen = [s["run"] for s in ships]
    a_run, b_run = runs_seen[0], runs_seen[-1]
    assert a_run != b_run, "two ingests, two versions"
    a_pages = [s["page"] for s in ships if s["run"] == a_run]
    b_pages = [s["page"] for s in ships if s["run"] == b_run]
    assert sorted(a_pages) == sorted(P.PAGES_A)
    assert sorted(b_pages) == sorted(("techstack", "heatmap", "overview", "insights",
                                      "platform", "context"))
    # the restage to B produced NO new lanes for the A pages
    b_lanes = [c["agent"] for c in opts.dispatcher.calls if c["stage"] == "PAGES_B"]
    assert "techstack-surface-producer" not in b_lanes and "heatmap-surface-producer" not in b_lanes
    # context ships after overview (O9 before C4)
    assert b_pages.index("overview") < b_pages.index("context")
    # promotion is the LAST call, once, on version B
    assert opts.shipper.promotions == [b_run]
    # exactly two ingests
    assert opts.reads.polls == 2


def test_issue7_nothing_ships_before_the_scored_checkpoint_is_ingested(tmp_path):
    run = _fresh(tmp_path)
    opts = _opts(tmp_path, reads=S.StubReads(never=True), ingest_timeout_s=0)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "INGEST_A"
    assert "did not ingest" in out["reason"]
    assert opts.shipper.ships == [] and not [c for c in opts.dispatcher.calls
                                              if c["stage"].startswith("PAGES")]
    # the checkpoint itself WAS pushed to the client folder (the scan's input)
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert Path(st["connector"]["checkpoint_a"]["folder"]).is_dir()
    # resuming after the scan catches up continues from INGEST_A, not from PRELIM
    opts2 = _opts(tmp_path)
    out2 = P.Pipeline(run, opts2).run_all()
    assert out2["outcome"] == "COMPLETE" and out2["stages_run"][0] == "INGEST_A"
    assert not [c for c in opts2.dispatcher.calls if c["stage"] in ("PRELIM", "RESEARCH", "SCORING")]


def test_issue7_a_page_fail_redispatches_only_that_page_with_the_reasons(tmp_path):
    run = _fresh(tmp_path)
    shipper = S.StubShipper(verdicts={("heatmap", 1): ("fail", [
        "CG-14 heatmap.workbook_scores[3].band: 'Transformational' is not in band_t"])})
    opts = _opts(tmp_path, shipper=shipper)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE", out
    a_calls = [c for c in opts.dispatcher.calls if c["stage"] == "PAGES_A"]
    agents = [c["agent"] for c in a_calls]
    assert agents.count("heatmap-surface-producer") == 2
    assert agents.count("techstack-surface-producer") == 1
    redo = Path(a_calls[-1]["prompt_file"]).read_text()
    assert "CG-14" in redo and "Transformational" in redo
    assert len([s for s in shipper.ships if s["page"] == "heatmap" and s["run"].endswith("-1")]) == 2
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert st["pages"]["heatmap"]["attempts"] >= 2


def test_issue7_a_page_that_keeps_failing_is_a_loud_stage_fail(tmp_path):
    run = _fresh(tmp_path)
    shipper = S.StubShipper(verdicts={("heatmap", n): ("fail", [f"CG-09 attempt {n}"])
                                      for n in range(1, 10)})
    opts = _opts(tmp_path, shipper=shipper, page_retries=1)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "PAGES_A"
    assert "heatmap" in out["reason"] and "CG-09" in out["reason"]
    assert shipper.promotions == []


def test_issue7_a_refused_claim_stops_the_stage_instead_of_writing_past_it(tmp_path):
    run = _fresh(tmp_path)
    shipper = S.StubShipper(refuse_claim={"techstack"})
    opts = _opts(tmp_path, shipper=shipper)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "PAGES_A"
    assert "lease" in out["reason"]


def test_issue7_no_payload_bytes_in_any_page_brief(tmp_path):
    run = _fresh(tmp_path)
    contract = {"page": "x", "sections": {"scores": {"fields": ["e_ids", "narrative_thread"],
                                                     "doc": "the section"}}}
    opts = _opts(tmp_path, reads=S.StubReads(contract=contract))
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE"
    page_briefs = [Path(c["prompt_file"]) for c in opts.dispatcher.calls
                   if c["stage"].startswith("PAGES")]
    assert page_briefs
    for p in page_briefs:
        text = p.read_text()
        assert '"e_ids"' not in text and '"narrative_thread"' not in text
        assert "contracts" in text and ".json" in text      # the PATH, not the bytes
    # the contract files were written to disk once each
    contracts = sorted((run.root / P.SECTIONS_DIR / "contracts").glob("*.json"))
    assert {c.stem for c in contracts} == {"techstack", "heatmap", "overview", "insights",
                                           "platform", "context"}


def test_issue7_a_refused_promote_is_a_failed_stage_not_a_success(tmp_path):
    run = _fresh(tmp_path)
    opts = _opts(tmp_path, shipper=S.StubShipper(refuse_promote=True))
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "PROMOTE"
    assert "incomplete_run" in out["reason"]
    assert not str(run.open().metadata().get("promoted_at") or "").strip()


# ═══════════════════════════════════════════════════════════════════════════
# issue 9 · where the hours go, and not going there twice
# ═══════════════════════════════════════════════════════════════════════════

def test_issue9_a_lane_that_produced_nothing_is_retried_then_a_real_failure_is_loud(tmp_path):
    run = _fresh(tmp_path)
    disp = S.StubDispatcher.fixture_backed(fail_first={"research-p1c1-producer": 1})
    opts = _opts(tmp_path, dispatcher=disp, lane_retries=1, until="RESEARCH")
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    lane = next(c for c in disp.calls if c["agent"] == "research-p1c1-producer")
    assert lane["codes"] == [125, 0]
    # a lane that FAILS on its own terms is never retried, and the stage says so
    run2 = _fresh(tmp_path / "two")
    disp2 = S.StubDispatcher.fixture_backed(broken={"research-p1c1-producer"})
    opts2 = _opts(tmp_path / "two", dispatcher=disp2, lane_retries=3, max_rounds=1)
    out2 = P.Pipeline(run2, opts2).run_all()
    assert out2["outcome"] == "FAILED" and out2["stage"] == "RESEARCH"
    lane2 = next(c for c in disp2.calls if c["agent"] == "research-p1c1-producer")
    assert lane2["codes"] == [1]
    assert "floors gate" in out2["reason"]


def test_issue9_a_second_invocation_redoes_nothing(tmp_path):
    run = _fresh(tmp_path)
    assert P.Pipeline(run, _opts(tmp_path)).run_all()["outcome"] == "COMPLETE"
    opts = _opts(tmp_path)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE" and out["stages_run"] == []
    assert opts.dispatcher.calls == [] and opts.shipper.ships == [] and opts.reads.polls == 0
    # and the ledger did not grow
    rows = cost.ledger(run)
    assert len(rows) == len(P.STAGES[2:])


def test_issue9_resume_after_dying_at_scoring_continues_there(tmp_path):
    run = _fresh(tmp_path)
    out = P.Pipeline(run, _opts(tmp_path, until="HANDOFF")).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL"
    # "the container died": a new driver, new doubles, same run tree
    plan = P.Pipeline(run, _opts(tmp_path)).plan()
    assert plan["next"] == "SCORING" and not plan["complete"]
    assert plan["command"].startswith("python3 -m engine.pipeline run --run")
    opts = _opts(tmp_path)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "COMPLETE" and out["stages_run"][0] == "SCORING"
    assert not [c for c in opts.dispatcher.calls if c["stage"] in ("PRELIM", "RESEARCH")]


def test_issue9_max_wall_clock_stops_cleanly_between_stages_and_resumes(tmp_path):
    run = _fresh(tmp_path)
    clock = {"t": 0.0}

    def tick():
        clock["t"] += 61.0          # every read of the clock is a minute later
        return clock["t"]
    opts = _opts(tmp_path, clock=tick, max_wall_min=2)
    out = P.Pipeline(run, opts).run_all()
    assert out["outcome"] == "STOPPED_WALL_CLOCK"
    assert out["stage"] in P.STAGES and "resume" in out["reason"]
    # nothing half-done: the stage it stopped BEFORE has no record
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert out["stage"] not in st["stages"]
    out2 = P.Pipeline(run, _opts(tmp_path)).run_all()
    assert out2["outcome"] == "COMPLETE"


def test_plan_never_dispatches_and_names_the_blocker(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    plan = P.Pipeline(run, _opts(tmp_path)).plan()
    # the fixture never built the KG, so KG is the first undone stage even
    # though RESEARCH already reads done — the driver walks in ORDER
    assert plan["next"] == "KG"
    done = [s["stage"] for s in plan["stages"] if s["done"]]
    assert done == ["PREFLIGHT", "START", "PRELIM", "RESEARCH"]
    assert "DQ_Bank empty" in plan["blockers"][0]
    # plan is read-only
    assert not (run.qa_dir / P.STATE_NAME).exists()
    assert not (run.root / P.BRIEFS_DIR).exists()


def test_a_run_with_no_binding_is_blocked_at_preflight(tmp_path):
    run = runstate.start(run_id="R-NOBIND", entity_name="X", entity_id="x",
                         sub_vertical="CU", scope_mode="T1_CORE", reference_date="2026-08-29",
                         root=tmp_path / "run", selected=["P1C1.1.1", "P1C1.1.2"])
    out = P.Pipeline(run, _opts(tmp_path)).run_all()
    assert out["outcome"] == "BLOCKED" and out["stage"] == "PREFLIGHT"
    assert "engine.cli start" in out["reason"]


def test_a_stale_install_refuses_the_driver_unless_waived(tmp_path, monkeypatch):
    from engine import cli
    run = _fresh(tmp_path)
    monkeypatch.setattr(cli, "refuse_on_stale_install", lambda: "REFUSED: STALE install")
    out = P.Pipeline(run, _opts(tmp_path, until="PRELIM")).run_all()
    assert out["outcome"] == "REFUSED" and "STALE" in out["reason"]
    out = P.Pipeline(run, _opts(tmp_path, until="PRELIM", allow_stale_install=True)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL"
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())
    assert st["waivers"] and "STALE" in st["waivers"][0]["stale_install"]


def test_the_watchdog_resumes_a_stopped_run_through_the_driver(tmp_path):
    run, wb, cells, ev = researched_run(tmp_path)
    row = watchdog.inspect(run)
    assert row["state"] == "READY_FOR_HANDOFF"
    plan = row["resume"]
    assert plan["pipeline"][:4] == ["python3", "-m", "engine.pipeline", "run"]
    out = watchdog.revive(row, dry_run=True)
    assert out["outcome"] == "DRY_RUN" and "engine.pipeline run" in out["would_run"]


def test_the_cli_runs_the_stub_pipeline_end_to_end(tmp_path):
    """The real command line, the real stub — what stress_pipeline_stub.py
    walks in CI."""
    run = _fresh(tmp_path)
    cmd = [sys.executable, "-m", "engine.pipeline", "run", "--run", run.run_id,
           "--root", str(run.root), "--dispatcher", "stub", "--no-push",
           "--folder-root", str(tmp_path / "client_out"), "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(SKILL), timeout=900)
    assert r.returncode == 0, r.stderr[-1500:] + r.stdout[-800:]
    out = json.loads(r.stdout[r.stdout.index("{"):])
    assert out["outcome"] == "COMPLETE"
    r = subprocess.run([sys.executable, "-m", "engine.pipeline", "plan", "--run", run.run_id,
                        "--root", str(run.root)], capture_output=True, text=True, cwd=str(SKILL))
    assert json.loads(r.stdout)["complete"] is True
    r = subprocess.run([sys.executable, "-m", "engine.pipeline", "env"],
                       capture_output=True, text=True, cwd=str(SKILL))
    env = json.loads(r.stdout)
    assert {c["check"] for c in env["checks"]} >= {"claude CLI", "connector identity",
                                                   "templates vs manifest", "install",
                                                   "agent_run.py", "ship_page.py"}
