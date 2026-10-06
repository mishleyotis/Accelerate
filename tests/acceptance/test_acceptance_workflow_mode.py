"""Acceptance: SCORING, REPORTS and PAGES run as persisted workflows, and no
workflow stage can loop.

Owner, 2026-10-06: "Ensure that for future runs, speed is managed as done
above: for scoring, reporting, promotion. Enforce /workflows and /agents in
the code such that nothing ever gets stuck looping. Self healing should be
important."

The driver is a Python process and cannot start a Workflow, so each workflow
stage ends the driver AWAITING_WORKFLOW with a handoff file. `_play` is the
conducting session: it reads the handoff and plays every agent the workflow
would start through the stub agents (the same fixtures every engine test
uses, through the engine's own refusals). The driver then resumes, verifies
the stage's gate and goes on — to PROMOTE.
"""
from __future__ import annotations

import json
from pathlib import Path

from engine import pipeline as P, pipeline_stub as S, watchdog

from test_acceptance_pipeline import _fresh, _opts


def _wf_opts(tmp_path, **over):
    return _opts(tmp_path, scoring_mode="workflow", report_mode="workflow",
                 pages_mode="workflow", **over)


def _rows_for(doc: dict) -> list[dict]:
    """The agents a workflow invocation would start, in its order."""
    rows = []
    name = Path(doc["workflow"]).name
    for inv in doc["invocations"]:
        if name == "dma-pillar-scoring.js":
            p = inv["pillar"].lower()
            rows += [{"agent": f"scoring-{p}-producer", "prompt_file": b}
                     for b in inv["briefs"] or [""]]
            if inv.get("solutions_brief"):
                rows.insert(0, {"agent": "technographic-scanner",
                                "prompt_file": inv["solutions_brief"]})
            rows.append({"agent": "scoring-critic", "prompt_file": ""})
        elif name == "dma-reports.js":
            seen = set()
            for sec in inv["sections"]:
                if (sec["agent"], inv["report"]) not in seen:
                    seen.add((sec["agent"], inv["report"]))
                    rows.append({"agent": sec["agent"], "prompt_file": sec["brief"]})
            rows.append({"agent": "report-validator", "prompt_file": ""})
        elif name == "dma-page-production.js":
            for pg in inv["pages"]:
                rows += [{"agent": f["agent"], "prompt_file": f["brief"]}
                         for f in pg["fragments"]]
                if pg["challenge_brief"]:
                    rows.append({"agent": "finding-challenger",
                                 "prompt_file": pg["challenge_brief"]})
                    rows.append({"agent": "page-consolidator",
                                 "prompt_file": pg["consolidate_brief"]})
                rows.append({"agent": f"{pg['page']}-surface-producer",
                             "prompt_file": pg["assemble_brief"]})
        else:
            raise AssertionError(f"unexpected workflow {name}")
    return rows


def _play(run, opts, handoff: str, tmp_path, n: int) -> list[str]:
    doc = json.loads(Path(handoff).read_text())
    assert Path(doc["workflow"]).is_file(), doc["workflow"]
    rows = _rows_for(doc)
    batch = tmp_path / f"session_{n}.json"
    batch.write_text(json.dumps(rows))
    opts.dispatcher.dispatch(batch, stage="WORKFLOW", lanes=4, retries=0,
                             ctx=P.Pipeline(run, opts))
    return [r["agent"] for r in rows]


def _drive(run, opts, tmp_path, limit=20):
    """Driver, session, driver … until the run ends. Returns the outcome
    and the stages that were handed over, in order."""
    handed = []
    for n in range(limit):
        out = P.Pipeline(run, opts).run_all()
        if out["outcome"] != "AWAITING_WORKFLOW":
            return out, handed
        handed.append(out["stage"])
        _play(run, opts, out["handoff"], tmp_path, n)
    raise AssertionError(f"still handing over after {limit} turns: {handed}")


def test_a_workflow_mode_run_hands_scoring_reports_and_pages_over_and_promotes(tmp_path):
    run = _fresh(tmp_path)
    opts = _wf_opts(tmp_path)
    out, handed = _drive(run, opts, tmp_path)
    assert out["outcome"] == "COMPLETE", out
    for st in ("SCORING", "REPORTS", "PAGES_A", "PAGES_B"):
        assert st in handed, (st, handed)
    # no writer, validator or page producer ran as a headless lane: the
    # session did that work (the REPORTS probe drain is a search relay)
    headless = {c["agent"] for c in opts.dispatcher.calls if c["stage"] != "WORKFLOW"}
    assert not {a for a in headless if a.startswith("report-")
                or a.endswith("-surface-producer") or a.startswith("scoring-")}, headless
    # promotion stays the driver's, once, on version B
    md = run.open().metadata()
    assert opts.shipper.promotions == [md["connector_run_id"]]
    # every page shipped once per version it belongs to, nothing reshipped
    ships = [(s["run"], s["page"]) for s in opts.shipper.ships]
    assert len(ships) == len(set(ships)), ships


def test_the_page_handoff_names_every_phase_and_repairs_only_a_failed_page(tmp_path):
    run = _fresh(tmp_path)
    shipper = S.StubShipper(verdicts={("heatmap", 1): ("fail", ["CG-09 status off-vocabulary"])})
    opts = _wf_opts(tmp_path, shipper=shipper, until="PAGES_A")
    first = None
    for n in range(12):
        out = P.Pipeline(run, opts).run_all()
        if out["outcome"] != "AWAITING_WORKFLOW":
            break
        doc = json.loads(Path(out["handoff"]).read_text())
        if out["stage"] == "PAGES_A":
            pages = {p["page"]: p for p in doc["invocations"][0]["pages"]}
            if first is None:
                first = pages
                assert set(pages) == set(P.PAGES_A)
                for p in pages.values():
                    assert not p["repair"] and p["fragments"] and p["assemble_brief"]
                    assert all(Path(f["brief"]).is_file() for f in p["fragments"])
            else:
                # the repair round: heatmap only, assembler only, with its reasons
                assert set(pages) == {"heatmap"}
                hm = pages["heatmap"]
                assert hm["repair"] and not hm["fragments"] and not hm["challenge_brief"]
                assert "CG-09" in " ".join(hm["last_verdict"])
        _play(run, opts, out["handoff"], tmp_path, n)
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    heat = [s for s in shipper.ships if s["page"] == "heatmap"]
    assert [s["status"] for s in heat] == ["fail", "pass"]


def test_a_workflow_that_changes_nothing_stops_the_stage_instead_of_looping(tmp_path):
    run = _fresh(tmp_path)
    opts = _wf_opts(tmp_path, until="REPORTS", stall_rounds=2)
    # walk to the REPORTS handoff, playing the earlier stages
    for n in range(10):
        out = P.Pipeline(run, opts).run_all()
        assert out["outcome"] == "AWAITING_WORKFLOW", out
        if out["stage"] == "REPORTS":
            break
        _play(run, opts, out["handoff"], tmp_path, n)
    # the session never runs the reports workflow: the driver is re-run anyway.
    # The third identical handoff (stall_rounds + 1) is refused instead.
    outs = [P.Pipeline(run, opts).run_all() for _ in range(2)]
    assert outs[0]["outcome"] == "AWAITING_WORKFLOW"
    assert outs[1]["outcome"] == "FAILED" and outs[1]["stage"] == "REPORTS"
    assert "same work" in outs[1]["reason"]
    # re-running the driver (a person, the watchdog, a cron) does not turn
    # the refusal back into a handoff while nothing has changed …
    again = P.Pipeline(run, opts).run_all()
    assert again["outcome"] == "FAILED" and "still refused" in again["reason"]
    # … and an explicit --reset-guard does
    assert P.Pipeline(run, _wf_opts(tmp_path, until="REPORTS", stall_rounds=2,
                                    reset_guard=True)).run_all()["outcome"] == "AWAITING_WORKFLOW"


def test_a_pages_workflow_that_writes_nothing_is_not_handed_forever(tmp_path):
    run = _fresh(tmp_path)
    opts = _wf_opts(tmp_path, until="PAGES_A", stall_rounds=2)
    for n in range(12):
        out = P.Pipeline(run, opts).run_all()
        assert out["outcome"] == "AWAITING_WORKFLOW", out
        if out["stage"] == "PAGES_A":
            break
        _play(run, opts, out["handoff"], tmp_path, n)
    outs = [P.Pipeline(run, opts).run_all() for _ in range(2)]
    assert outs[-1]["outcome"] == "FAILED" and outs[-1]["stage"] == "PAGES_A", outs[-1]
    assert "no section file" in outs[-1]["reason"]
    assert opts.shipper.ships == []
    # a repair at source (section files land) releases the stall guard
    T_play_pages = json.loads((run.qa_dir / P.PAGES_HANDOFF).read_text())
    _play(run, opts, str(run.qa_dir / P.PAGES_HANDOFF), tmp_path, 99)
    assert T_play_pages["invocations"][0]["pages"]
    assert P.Pipeline(run, opts).run_all()["outcome"] == "STOPPED_AT_UNTIL"


def test_the_watchdog_hands_an_orphaned_workflow_to_the_session_not_the_driver(tmp_path):
    run = _fresh(tmp_path)
    opts = _wf_opts(tmp_path, until="SCORING")
    for n in range(10):
        out = P.Pipeline(run, opts).run_all()
        if out["outcome"] == "AWAITING_WORKFLOW" and out["stage"] == "SCORING":
            break
        assert out["outcome"] == "AWAITING_WORKFLOW", out
        _play(run, opts, out["handoff"], tmp_path, n)
    # writes are recent: the workflow is running, nothing to revive
    row = watchdog.inspect(run)
    assert row["state"] == "WORKFLOW_RUNNING", row
    assert row["state"] not in watchdog.AGENT_ADVANCEABLE
    # quiet past the stall window: the session that held it is gone
    row = watchdog.inspect(run, stall_seconds=-1)
    assert row["state"] == "AWAITING_WORKFLOW", row
    assert row["state"] in watchdog.AGENT_ADVANCEABLE
    rev = watchdog.revive(row)
    assert rev["outcome"] == "AWAITING_WORKFLOW"
    assert rev["handoff"].endswith(P.SCORING_HANDOFF)
    assert rev["detail"].startswith("AWAITING_WORKFLOW at SCORING — ")


def test_the_cli_defaults_every_workflow_stage_to_the_workflow(tmp_path):
    import argparse
    src = Path(P.__file__).read_text()
    for flag in ("--scoring-mode", "--report-mode", "--pages-mode", "--research-mode"):
        assert f'"{flag}"' in src, flag
    a = argparse.Namespace(dispatcher="agent_run", lane_timeout=60, until=None,
                           max_wall_min=None, max_usd=None, max_rounds=3, stall_rounds=2,
                           enrichment_heals=0, no_relay=True, lane_retries=0,
                           page_retries=1, ingest_poll_s=0, ingest_timeout_s=1,
                           folder_root=None, no_push=True, allow_stale_install=False,
                           lanes=1, toolkits=None, research_mode=None, run="R")
    o = P._build_opts(a)
    assert (o.research_mode, o.scoring_mode, o.report_mode, o.pages_mode) == \
        ("workflow",) * 4
