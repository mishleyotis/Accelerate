#!/usr/bin/env python3
"""A research run that has stopped says so — and then gets restarted.

    watchdog.py [--root DIR] [--stall-seconds 900] [--json]
    watchdog.py --revive [--dry-run]          # re-dispatch what has stopped
    watchdog.py --run R --revive

WHY THIS EXISTS. AUD-0063: `scripts/synthesis_watchdog.py` is a genuine
unattended stall detector for the SYNTHESIS side — STALLED / READY /
EXPIRING / PROGRESSING, a 900-second threshold, driven hourly — and it exists
precisely because dispatched subagents do not survive a turn boundary. It
never touches a research run, a ledger or a workbook. On the research side
the only INVESTIGATE string in the whole archive was raised on corrupt ledger
lines. So the stage that owns the run directory, the checksum halt and the
category gates had no way to announce that it had stopped.

The pattern was understood; it was simply never extended. This extends it,
reading the same object the agents write: `Run_Metadata.last_written_at` is
the heartbeat, and it is updated by every append.

TWO LATER DEFECTS, BOTH FIXED HERE.

  **It could not see a new DMA.** `sweep` listed `$DMA_RUN_ROOT`, a directory
  that does not survive the container. Every scheduled firing gets a fresh
  one, so the sweep found zero runs and printed "no research runs" — which
  is indistinguishable from a healthy queue, and is how a run that stopped at
  category three stayed stopped. It now reads `engine.registry`, the
  append-only log every `start` writes and pushes to Drive, so a run this
  container has never seen is still VISIBLE — as MISSING_LOCALLY, carrying
  the command that brings its workbook back.

  **It could not restart anything.** Every state was a report. A watchdog
  that detects a stall and takes no action has moved the stall from "nobody
  noticed" to "somebody noticed and nothing happened", which is not the
  improvement it looks like. `--revive` now re-dispatches the stopped stage
  through `scripts/agent_run.py` — the same agents, the same front matter,
  the same refusals — and records what it did. Where dispatch is genuinely
  unavailable it says NOT_RUN with the reason and leaves the resume
  instruction durably, never a silent pass.

It still never takes work away from a session that is merely slow: PROGRESSING
is left alone, and revival targets states that mean STOPPED.
"""
from __future__ import annotations

# Runnable both ways. `python3 -m engine.<mod>` is the documented invocation,
# but every audit and every operator reaches for `python3 <path> --help`
# first, and a relative import dies there. Binding __package__ makes the two
# equivalent instead of making one of them a trap.
if __package__ in (None, ""):  # noqa: E402  (must precede the relative imports)
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from . import contract as C
from . import floors_gate, ledger as L, prelim, registry, runstate
from .workbook import RunWorkbook

STALL_SECONDS = 900


def _age(ts: str | None) -> float | None:
    if not ts:
        return None
    try:
        t = _dt.datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except ValueError:
        return None
    return (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds()


def inspect(run: runstate.Run, *, stall_seconds: int = STALL_SECONDS) -> dict:
    try:
        wb = run.open()
    except Exception as e:                                # noqa: BLE001
        return {"run_id": run.run_id, "state": "UNREADABLE", "detail": str(e)}
    md = wb.metadata()
    idle = _age(md.get("last_written_at"))
    tax = C.taxonomy()
    cats = sorted({str(r["SubCap_ID"]).split(".")[0]
                   for r in wb.scoring_rows() if r.get("SubCap_ID")})
    open_work, failed, ungated = [], [], []
    for c in cats:
        w = L.worklist(wb, c)
        if w["pending"] or w["volleyed"]:
            open_work.append(c)
        v = floors_gate.read_verdict(run.qa_dir, c)
        if v is None:
            ungated.append(c)
        elif v.get("gate") == "FAIL":
            failed.append(c)
    drift = wb.verify_handoff_lock()
    budget = L.stats(wb)
    pre = prelim.state(wb)
    folder = str(md.get("client_folder") or "").strip()
    post: dict = {}

    if drift:
        state, detail = "HALTED", "; ".join(drift)
    elif not folder:
        state, detail = "NO_CLIENT_FOLDER", (
            "the run has no '<Entity> - DMA' folder, so nothing about it is "
            "findable from outside this container — open it with "
            "`engine.assemble open`")
    elif pre["blocks_category_dispatch"]:
        state, detail = "PRELIM_OPEN", (
            "PRELIM has not closed: "
            + (", ".join(pre["open"]) or "signed off never recorded")
            + " — no category card will be served until it does")
    elif budget["checkpoint_required"]:
        state, detail = "AT_BUDGET_CEILING", (
            f"{budget['search_ops']} search-ops against a ceiling of "
            f"{budget['search_op_ceiling']}; the run must checkpoint")
    elif idle is not None and idle > stall_seconds and open_work:
        state, detail = "STALLED", (
            f"no write for {int(idle)}s with {len(open_work)} category(ies) "
            f"still open: {', '.join(open_work[:6])}")
    elif failed:
        state, detail = "GATE_FAILED", f"floors gate FAILED on {', '.join(failed)}"
    elif not open_work and not ungated:
        state, detail, post = post_research_state(wb, run, md)
    elif not open_work and ungated:
        state, detail = "UNGATED", (
            f"no open work and no recorded gate verdict for "
            f"{', '.join(ungated[:6])} — running out of cards is not closure")
    else:
        state, detail = "PROGRESSING", (
            f"{len(open_work)} category(ies) open, last write "
            f"{int(idle) if idle is not None else '?'}s ago")

    row = {
        "run_id": md.get("run_id") or run.run_id,
        "entity": md.get("entity_name"),
        "root": str(run.root),
        "workbook": str(run.workbook_path),
        "client_folder": folder or None,
        "state": state, "detail": detail,
        "idle_seconds": None if idle is None else int(idle),
        "categories": len(cats), "open": open_work,
        "gate_failed": failed, "ungated": ungated,
        "prelim_open": pre["open"],
        "search_ops": budget["search_ops"],
        "catalogue_drift": drift,
        "stage": C.stage_of(md),
    }
    row.update(post)
    row["criterion"] = COMPLETION_CRITERIA.get(state, "")
    row["resume"] = resume_plan(row)
    return row


# ── after research: the stage machine the conductor's manifest describes ──
#
# WHY (owner, 2026-09-03, the headless-workflow audit): the states above end
# at READY_FOR_HANDOFF — "every category closed and gated" — and stayed there
# through scoring, the reports and the package. A run that died with three
# pillars scored, or with both reports written and nothing reviewed, read as
# the same resting state as one that had never opened the assessment stage,
# and the only revive plan was "render the four deliverables", which is the
# conductor's whole step list compressed into a sentence.
#
# So the machine continues, computed from the SAME substrate the gates read:
# the workbook's stage, column D, the Gate_Log, Report_Narrative, and the
# client folder's manifest. Each state names the agent that owns the next
# unit of work and the criterion that closes it — which is what turns "the
# scoring agents fire once research is done, the report writers once scoring
# is done" from prose in a manifest into something a hook and the hourly
# watchdog can act on.

#: What "done" means for each state — the gate that closes it, in one line,
#: so a session or a hook reports a criterion rather than an impression.
COMPLETION_CRITERIA = {
    "PRELIM_OPEN": ("`engine.prelim complete` succeeds: all seven sections "
                    "narrated with cited evidence or declared with a ladder"),
    "STALLED": ("`engine.cli gate --category <C> --require-synthesis` "
                "returns PASS for every open category"),
    "GATE_FAILED": ("`engine.cli gate --category <C> --require-synthesis` "
                    "returns PASS — every cell SYNTHESISED and independently "
                    "challenged, or DECLARED ABSENT with its volley ladder"),
    "UNGATED": "a recorded floors-gate verdict of PASS for every category",
    "AT_BUDGET_CEILING": "`engine.memory backup` then a checkpoint, before any search",
    "READY_FOR_HANDOFF": ("`engine.cli validate` FAILS=0, `engine.cli handoff` "
                          "written, `engine.assessment open` flips the stage"),
    "SCORING_OPEN": ("`engine.assessment state` shows scored == subcaps for "
                     "every pillar in scope"),
    "CRITIC_PENDING": ("a SCORING_CRITIC PASS row in Gate_Log for every pillar "
                       "in scope, recorded by scoring-critic"),
    "SCORING_GATE_OPEN": ("`engine.assessment gate` returns PASS and writes "
                          "07_qa/scoring.json; then `engine.assemble "
                          "checkpoint --stage SCORING_PASS --push`"),
    "REPORT_PRECONDITIONS_OPEN": (
        "`engine.narrative preconditions --report assessment` lists nothing: "
        "every stage tab filled (`engine.assessment solution`, `peer-adoption`) "
        "or declared with a real reason (`engine.completeness declare`)"),
    "REPORTS_OPEN": ("`engine.narrative state` reads READY for both reports: "
                     "every section written to its control block AND reviewed "
                     "PASS by an actor that did not write it"),
    "PACKAGE_UNSHIPPED": ("`engine.assemble package --push` verifies and pushes "
                          "the folder; run_manifest.json reads status COMPLETE"),
    "SHIPPED": ("done here — the package scan ingests the folder on its "
                "half-hour cadence and the synthesis lanes produce the pages"),
}


def _manifest(md: dict) -> dict:
    folder = str(md.get("client_folder") or "").strip()
    if not folder:
        return {}
    p = Path(folder) / "run_manifest.json"
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text())
        return doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        return {}


def _unscored_by_pillar(wb: RunWorkbook) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in wb.scoring_rows():
        cell = str(r.get("SubCap_ID") or "").strip()
        if not cell:
            continue
        sc = str(r.get("Score") or "").strip()
        if not sc:
            out[cell[:2]] = out.get(cell[:2], 0) + 1
    return out


def post_research_state(wb: RunWorkbook, run: runstate.Run, md: dict) -> tuple:
    """(state, detail, extras) for a run whose categories are all gated."""
    from . import assessment as A
    extras: dict = {}
    if C.stage_of(md) != "assessment":
        return ("READY_FOR_HANDOFF",
                "every category closed and gated; the assessment stage is not "
                "open — validate, hand off, then `engine.assessment open`",
                extras)
    unscored = _unscored_by_pillar(wb)
    extras["unscored_by_pillar"] = unscored
    if unscored:
        return ("SCORING_OPEN",
                "assessment stage open; unscored rows by pillar: "
                + ", ".join(f"{p}={n}" for p, n in sorted(unscored.items())),
                extras)
    pillars = sorted({c[:2] for c in wb.selected_subcaps()})
    critics = {}
    for g in wb.rows("Gate_Log"):
        if str(g.get("Gate") or "").strip() == "SCORING_CRITIC":
            critics[str(g.get("Scope") or "").strip()] = \
                str(g.get("Verdict") or "").strip().upper()
    missing = [p for p in pillars if p not in critics]
    failed_c = [p for p in pillars if critics.get(p) not in (None, "PASS")]
    extras["critic_missing"], extras["critic_failed"] = missing, failed_c
    if missing or failed_c:
        return ("CRITIC_PENDING",
                ("no critic verdict on " + ", ".join(missing) if missing else "")
                + ("; critic FAIL on " + ", ".join(failed_c) if failed_c else ""),
                extras)
    last = None
    for g in wb.rows("Gate_Log"):
        if str(g.get("Gate") or "").strip() == "SCORING":
            last = g
    if last is None or str(last.get("Verdict") or "").strip().upper() != "PASS":
        detail = ("the SCORING gate has never been run" if last is None else
                  f"last SCORING gate verdict {last.get('Verdict')}: "
                  f"{str(last.get('Detail') or '')[:200]}")
        return "SCORING_GATE_OPEN", detail, extras
    manifest = _manifest(md)
    extras["checkpoint_due"] = manifest.get("stage_reached") not in (
        "SCORING_PASS", "REPORTS_READY") and manifest.get("status") != "COMPLETE"
    # The report tier's own door. `engine.narrative write` refuses a section
    # while a stage precondition fails — the SCORING gate can PASS with the
    # Solution_Catalogue and Platform_Peer_Adoption tabs still empty, and a
    # run in that shape used to read REPORTS_OPEN here, which sent two report
    # producers to a writer that turned them both away (found by the walk
    # test, 2026-09-04). Ask the door first; while it is shut, the work is
    # the conductor's, not the producers'.
    try:
        from . import narrative as N
        pre = N.stage_preconditions(wb, "assessment", run.qa_dir)
    except Exception as e:                                # noqa: BLE001
        pre = [f"preconditions unreadable: {str(e)[:200]}"]
    if pre:
        extras["preconditions"] = pre
        return ("REPORT_PRECONDITIONS_OPEN",
                "SCORING gate PASS; the report tier's preconditions fail: "
                + "; ".join(p.split("\n")[0][:120] for p in pre[:4])
                + (f"; +{len(pre) - 4} more" if len(pre) > 4 else ""),
                extras)
    try:
        ns = N.state(wb)
        reports = {k: {"open": v["open"], "ready": v["ready"],
                       "sections": [{"section": s["section"],
                                     "status": s["status"], "fix": s["fix"]}
                                    for s in v["sections"]
                                    if s["status"] != "READY"]}
                   for k, v in ns["reports"].items()}
    except Exception as e:                                # noqa: BLE001
        reports = {"_error": str(e)[:200]}
    extras["reports"] = reports
    open_reports = [k for k, v in reports.items()
                    if k != "_error" and not v.get("ready")]
    if "_error" in reports or open_reports:
        return ("REPORTS_OPEN",
                "SCORING gate PASS; reports not READY: "
                + ", ".join(f"{k} ({len(reports[k]['open'])} open)"
                            for k in open_reports)
                + (f"; narrative state unreadable: {reports['_error']}"
                   if "_error" in reports else ""),
                extras)
    if manifest.get("status") == "COMPLETE":
        return ("SHIPPED",
                f"package complete in {md.get('client_folder')}; the package "
                f"scan ingests it", extras)
    return ("PACKAGE_UNSHIPPED",
            "both reports READY and the client folder's manifest is not "
            "COMPLETE — assemble, verify and push the package", extras)


def _report_agents(row: dict) -> list[str]:
    """Which report-tier agents the open sections call for, producers first."""
    agents: list[str] = []
    for key, v in (row.get("reports") or {}).items():
        if key == "_error" or v.get("ready"):
            continue
        statuses = {s["status"] for s in v.get("sections", [])}
        producer = ("report-assessment-producer" if key == "assessment"
                    else "report-research-producer")
        if statuses & {"OPEN", "SHORT", "REVISE"} and producer not in agents:
            agents.append(producer)
        if "UNREVIEWED" in statuses and "report-validator" not in agents:
            agents.append("report-validator")
    if not agents:
        agents.append("report-validator")
    return agents


#: What each stopped state needs done, and who does it. `agent` is the plugin
#: roster name `scripts/agent_run.py` accepts; None means no agent can fix it
#: unattended and a person is named instead.
def resume_plan(row: dict) -> dict:
    """The single next action for a stopped run, as something runnable.

    A resume string an operator has to interpret is a resume string that
    waits for an operator. This returns the agent to dispatch and the prompt
    to dispatch it with, so `--revive` can act without a reading step."""
    state = row.get("state")
    run_id, root = row.get("run_id"), row.get("root")
    where = f"--run {run_id}" + (f" --root {root}" if root else "")
    base = (f"Resume DMA research run {run_id} for {row.get('entity')}. "
            f"The run root is {root}. Read `engine.cli orient {where}` FIRST "
            f"and work its do_first list in order. ")
    #: THE DRIVER is how a resumable run continues (2026-09-04, issues 6-9):
    #: `engine.pipeline run` reads the workbook, finds the first stage whose
    #: done-predicate is false, and dispatches THAT stage's lanes over a brief
    #: it writes — rather than one hand-written prompt to one agent. Every
    #: actionable state carries it; `agent`, `parallel` and `prompt` stay for a
    #: container without the driver, and `revive` prefers the driver when both
    #: are present because it closes the whole stage rather than one lane.
    pipeline_cmd = ["python3", "-m", "engine.pipeline", "run",
                    "--run", str(run_id)] + (["--root", root] if root else [])

    if state == "HALTED":
        return {"actionable": False, "agent": None,
                "why": "the catalogue moved under this run; a person decides "
                       "whether to re-pin or retire it",
                "detail": row.get("catalogue_drift")}
    if state == "NO_CLIENT_FOLDER":
        return {"actionable": True, "agent": None,
                "command": ["python3", "-m", "engine.assemble", "open",
                            "--run", str(run_id)]
                           + (["--root", root] if root else []),
                "why": "the folder is opened by a command, not an agent"}
    if state == "PRELIM_OPEN":
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    f"PRELIM is open: {', '.join(row.get('prelim_open') or [])}. "
                    f"Close every open PRELIM section — the conductor owns "
                    f"this phase — then `engine.prelim complete` and continue "
                    f"into category dispatch."),
                "why": "PRELIM is the conductor's phase"}
    if state in ("STALLED", "GATE_FAILED", "UNGATED", "AT_BUDGET_CEILING"):
        cats = (row.get("open") or row.get("gate_failed")
                or row.get("ungated") or [])
        cat = cats[0] if cats else None
        agent = (f"research-{cat.lower()}-producer" if cat else
                 "research-conductor")
        what = {
            "STALLED": f"The run went quiet with {len(row.get('open') or [])} "
                       f"category(ies) still open.",
            "GATE_FAILED": f"The floors gate FAILED on "
                           f"{', '.join(row.get('gate_failed') or [])}.",
            "UNGATED": f"No gate verdict was ever recorded for "
                       f"{', '.join(row.get('ungated') or [])}; running out "
                       f"of cards is not closure.",
            "AT_BUDGET_CEILING": "The run hit its search-op ceiling and must "
                                 "checkpoint before any further search.",
        }[state]
        return {"actionable": True, "agent": agent,
                "pipeline": pipeline_cmd,
                "prompt": base + what + " Take it from where it stopped.",
                "why": f"{cat or 'the conductor'} owns the open work"}
    if state == "READY_FOR_HANDOFF":
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    "Every category is closed and gated. Run `engine.cli "
                    "validate` (FAILS=0) and `engine.cli handoff`, write the "
                    "client tabs through `engine.profile`, then OPEN THE "
                    "SCORING STAGE with `engine.assessment open` and dispatch "
                    "the four pillar scorers in parallel. Render the four "
                    "deliverables only after the SCORING gate PASSes."),
                "why": "research is finished; the scoring stage has not opened"}
    if state == "SCORING_OPEN":
        unscored = row.get("unscored_by_pillar") or {}
        pillars = sorted(unscored) or ["P1"]
        agents = [f"scoring-{p.lower()}-producer" for p in pillars]
        return {"actionable": True, "agent": agents[0], "parallel": agents,
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    f"The assessment stage is open and column D is not "
                    f"struck: unscored rows by pillar "
                    f"{json.dumps(unscored, sort_keys=True)}. Score every "
                    f"row of your pillar through `engine.assessment score` — "
                    f"one command per subcap, rationale over 150 characters "
                    f"citing the row's own E-ids, the six overlay columns "
                    f"filled. Done when `engine.assessment state` shows "
                    f"scored == subcaps for your pillar."),
                "why": "column D belongs to the pillar scorers"}
    if state == "CRITIC_PENDING":
        return {"actionable": True, "agent": "scoring-critic",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    f"Every row is scored and the critic pass is owed on "
                    f"{', '.join(row.get('critic_missing') or [])}"
                    + (f"; the critic FAILED {', '.join(row.get('critic_failed') or [])}"
                       " and those pillars must be re-scored then re-critiqued"
                       if row.get("critic_failed") else "")
                    + ". Re-derive a sample per capability and record "
                    "`engine.assessment critique` per pillar; never change a "
                    "score."),
                "why": "the gate will not pass without an independent critic"}
    if state == "SCORING_GATE_OPEN":
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    f"Scores and critic verdicts are in; the SCORING gate is "
                    f"not PASS ({row.get('detail')}). Run `engine.assessment "
                    f"rollup --headline …`, `engine.assessment solution` and "
                    f"`peer-adoption`, then `engine.assessment gate`. Re-"
                    f"dispatch the pillar scorer the gate names for any "
                    f"blocking term, then `engine.assemble checkpoint --stage "
                    f"SCORING_PASS --push` so the scan ingests a scored run."),
                "why": "the rollup and the gate are the conductor's"}
    if state == "REPORT_PRECONDITIONS_OPEN":
        pre = row.get("preconditions") or []
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    "The SCORING gate has PASSED but `engine.narrative write` "
                    "will refuse every section until these hold: "
                    + " | ".join(p.replace("\n", " ")[:300] for p in pre)
                    + ". Fill each stage tab that has content to carry "
                    "(`engine.assessment solution --id … --name … --platform "
                    "…`, `engine.assessment peer-adoption …`) and declare each "
                    "that legitimately has none (`engine.completeness declare "
                    "--sheet <Sheet> --reason '…'`, a real reason — filler is "
                    "refused). Then `engine.assemble checkpoint --stage "
                    "SCORING_PASS --push` if not yet pushed. Done when "
                    "`engine.narrative preconditions --report assessment` "
                    "lists nothing; the report producers are dispatched next."),
                "why": ("the stage tabs are the conductor's to close; a report "
                        "producer sent now is refused at the door")}
    if state == "REPORTS_OPEN":
        agents = _report_agents(row)
        due = row.get("checkpoint_due")
        return {"actionable": True, "agent": agents[0], "parallel": agents,
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    "The SCORING gate has PASSED"
                    + (" and the SCORING_PASS checkpoint has NOT been pushed "
                       "— run `engine.assemble checkpoint --stage SCORING_PASS "
                       "--push` first" if due else "")
                    + ". Reports open: "
                    + json.dumps({k: v.get("open") for k, v in
                                  (row.get("reports") or {}).items()
                                  if k != "_error"}, sort_keys=True)
                    + ". Producers write each OPEN/SHORT/REVISE section "
                    "through `engine.narrative write`; the validator "
                    "reviews every UNREVIEWED one through `engine.narrative "
                    "review`. Done when `engine.narrative state` reads READY "
                    "for both."),
                "why": "the report tier owns the sections; the validator the verdicts"}
    if state == "PACKAGE_UNSHIPPED":
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + (
                    "Both reports read READY. `engine.completeness check`, "
                    "`engine.cli report` (both .docx, gold_standard PASS), "
                    "`engine.techscan render`, `engine.grains "
                    "recommendations`, `engine.assemble checkpoint --stage "
                    "REPORTS_READY --push`, then `engine.assemble package "
                    "--push` and `engine.memory cleanup --apply`. Done when "
                    "run_manifest.json reads status COMPLETE."),
                "why": "the run is finished and nothing has shipped it"}
    if state == "SHIPPED":
        return {"actionable": False, "agent": None,
                "why": "the package is complete; the package scan and the "
                       "synthesis lanes take it from here"}
    if state == "MISSING_LOCALLY":
        return {"actionable": True, "agent": None,
                "command": ["python3", "-m", "engine.registry", "pull"],
                "why": "the workbook is not in this container; recover it "
                       "before anything can resume"}
    if state == "UNREADABLE":
        return {"actionable": False, "agent": None,
                "why": "the workbook could not be opened; a person looks at it"}
    return {"actionable": False, "agent": None, "why": "the run is working"}


def sweep(root: Path, *, stall_seconds: int = STALL_SECONDS,
          use_registry: bool = True) -> list[dict]:
    """Every run this container can see, plus every run the REGISTRY knows.

    The registry half is the fix for the blindness: a fresh container has an
    empty run root, and a sweep that trusts it reports a quiet queue it
    cannot actually see."""
    root = Path(root)
    out, seen = [], set()
    if root.exists():
        for d in sorted(p for p in root.iterdir() if p.is_dir()):
            try:
                run = runstate.locate(d.name, d)
            except ValueError:
                continue
            if run.workbook_path.exists():
                row = inspect(run, stall_seconds=stall_seconds)
                seen.add(row["run_id"])
                out.append(row)
    if not use_registry:
        return out
    for rec in registry.open_runs():
        rid = rec.get("run_id")
        if not rid or rid in seen:
            continue
        seen.add(rid)
        wb_path = Path(str(rec.get("workbook") or ""))
        if wb_path.exists():
            try:
                run = runstate.locate(rid, Path(str(rec.get("root"))))
                out.append(inspect(run, stall_seconds=stall_seconds))
                continue
            except ValueError:
                pass
        row = {
            "run_id": rid, "entity": rec.get("entity"),
            "root": rec.get("root"), "workbook": str(wb_path),
            "client_folder": rec.get("client_folder"),
            "state": "MISSING_LOCALLY",
            "detail": (f"registered {rec.get('at')} as {rec.get('event')} but "
                       f"its workbook is not in this container"),
            "idle_seconds": _age(rec.get("at")), "categories": 0,
            "open": [], "gate_failed": [], "ungated": [], "prelim_open": [],
            "search_ops": None, "catalogue_drift": [],
            "last_position": rec.get("position"),
        }
        row["resume"] = resume_plan(row)
        out.append(row)
    return out


# ── acting on it ─────────────────────────────────────────────────────────

def _agent_run() -> Path | None:
    p = Path(__file__).resolve().parents[3] / "scripts" / "agent_run.py"
    return p if p.exists() else None


def revive(row: dict, *, dry_run: bool = False, timeout: int = 3600) -> dict:
    """Re-dispatch one stopped run, or say honestly why it could not be."""
    plan = row.get("resume") or resume_plan(row)
    if not plan.get("actionable"):
        return {"run_id": row.get("run_id"), "outcome": "NOT_RUN",
                "reason": plan.get("why"), "state": row.get("state")}
    if plan.get("command"):
        cmd = list(plan["command"])
        if dry_run:
            return {"run_id": row.get("run_id"), "outcome": "DRY_RUN",
                    "would_run": " ".join(cmd), "state": row.get("state")}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600,
                           cwd=str(Path(__file__).resolve().parents[1]))
        return {"run_id": row.get("run_id"),
                "outcome": "RESOLVED" if r.returncode == 0 else "FAILED",
                "state": row.get("state"),
                "detail": (r.stdout or r.stderr).strip()[-400:]}
    if plan.get("pipeline"):
        # THE DRIVER FIRST. `engine.pipeline run` continues the run from its
        # first undone stage, dispatching that stage's lanes over briefs it
        # writes — so one revive closes a stage rather than one lane of it,
        # and the stage's gate decides when it is done. The agent dispatch
        # below stays for a container without the driver.
        cmd = list(plan["pipeline"])
        if dry_run:
            return {"run_id": row.get("run_id"), "outcome": "DRY_RUN",
                    "state": row.get("state"), "agent": plan.get("agent"),
                    "via": "engine.pipeline run",
                    "would_run": " ".join(cmd),
                    "resume_prompt": plan.get("prompt")}
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           cwd=str(Path(__file__).resolve().parents[1]))
        return {"run_id": row.get("run_id"),
                "outcome": "RESOLVED" if r.returncode == 0 else "FAILED",
                "state": row.get("state"), "agent": plan.get("agent"),
                "via": "engine.pipeline run",
                "detail": (r.stdout or r.stderr).strip()[-400:]}
    runner = _agent_run()
    if runner is None:
        return {"run_id": row.get("run_id"), "outcome": "NOT_RUN",
                "reason": "scripts/agent_run.py is not in this install, so "
                          "no agent can be dispatched from here",
                "state": row.get("state"), "resume_prompt": plan.get("prompt")}
    # THE WHOLE PLAN, not its first name. `parallel` carries the four pillar
    # scorers, or a report producer AND the validator; reviving only
    # `plan["agent"]` did one per hourly firing, so a state the plan asked
    # to close in one pass took four cycles and REPORTS_OPEN never reached
    # the validator at all (review, 2026-09-04).
    agents = [a for a in (plan.get("parallel") or [plan["agent"]]) if a]
    if dry_run:
        return {"run_id": row.get("run_id"), "outcome": "DRY_RUN",
                "state": row.get("state"), "agent": plan["agent"],
                "agents": agents,
                "would_run": "agent_run.py --batch "
                             + ",".join(f"--agent {a}" for a in agents),
                "resume_prompt": plan.get("prompt")}
    pf = Path(tempfile.gettempdir()) / f"revive_{row.get('run_id')}.md"
    pf.write_text(plan.get("prompt") or "")
    if len(agents) > 1:
        batch = Path(tempfile.gettempdir()) / f"revive_{row.get('run_id')}.json"
        batch.write_text(json.dumps([{"agent": a, "prompt_file": str(pf)}
                                     for a in agents]))
        argv = ["--batch", str(batch), "--lanes", str(min(len(agents), 4))]
    else:
        argv = ["--agent", agents[0], "--prompt-file", str(pf)]
    r = subprocess.run([sys.executable, str(runner), *argv],
                       capture_output=True, text=True, timeout=timeout)
    return {"run_id": row.get("run_id"),
            "outcome": "RESOLVED" if r.returncode == 0 else "FAILED",
            "state": row.get("state"), "agent": plan["agent"],
            "agents": agents,
            "detail": (r.stdout or r.stderr).strip()[-400:]}


#: The states that need someone told. Everything else is the run working.
ACTIONABLE = ("UNREADABLE", "HALTED", "STALLED", "GATE_FAILED", "UNGATED",
              "AT_BUDGET_CEILING", "PRELIM_OPEN", "NO_CLIENT_FOLDER",
              "MISSING_LOCALLY", "READY_FOR_HANDOFF",
              # the assessment-stage machine (2026-09-03)
              "SCORING_OPEN", "CRITIC_PENDING", "SCORING_GATE_OPEN",
              "REPORT_PRECONDITIONS_OPEN", "REPORTS_OPEN", "PACKAGE_UNSHIPPED")

#: States an AGENT can advance without a person: the ones a stage-advance
#: hook may keep a session working on, and the watchdog may revive.
AGENT_ADVANCEABLE = tuple(s for s in ACTIONABLE
                          if s not in ("UNREADABLE", "HALTED", "MISSING_LOCALLY"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(runstate.RUN_ROOT))
    ap.add_argument("--run")
    ap.add_argument("--stall-seconds", type=int, default=STALL_SECONDS)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-registry", action="store_true",
                    help="sweep only this container's run root. Off by "
                         "default: a fresh container's root is empty, and a "
                         "sweep that trusts it reports a queue it cannot see")
    ap.add_argument("--revive", action="store_true",
                    help="re-dispatch every stopped run through its owning "
                         "agent, rather than only reporting it")
    ap.add_argument("--dry-run", action="store_true",
                    help="with --revive: print what would be dispatched")
    a = ap.parse_args(argv)
    rows = ([inspect(runstate.locate(a.run, Path(a.root) / a.run),
                     stall_seconds=a.stall_seconds)]
            if a.run else sweep(Path(a.root), stall_seconds=a.stall_seconds,
                                use_registry=not a.no_registry))
    revived = []
    if a.revive:
        for r in rows:
            if r["state"] in ACTIONABLE:
                revived.append(revive(r, dry_run=a.dry_run))
    if a.json:
        print(json.dumps({"runs": rows, "revived": revived} if a.revive
                         else rows, indent=2))
    else:
        for r in rows:
            print(f"[{r['state']:<18}] {r['run_id']}  {r['detail']}")
        if not rows:
            print(f"no research runs under {a.root} and none registered in "
                  f"{registry.registry_path()}")
        for v in revived:
            print(f"  -> {v['outcome']:<9} {v['run_id']}  "
                  f"{v.get('agent') or v.get('would_run') or ''}  "
                  f"{v.get('reason') or v.get('detail') or ''}"[:200])
    if a.revive:
        return 0 if all(v["outcome"] in ("RESOLVED", "DRY_RUN")
                        for v in revived) else 1
    return 1 if any(r["state"] in ACTIONABLE for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
