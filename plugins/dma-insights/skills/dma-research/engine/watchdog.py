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
        state, detail = "READY_FOR_HANDOFF", "every category closed and gated"
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
    }
    row["resume"] = resume_plan(row)
    return row


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
    #: THE DRIVER is how a resumable run continues (2026-09-03, issues 6–9):
    #: `engine.pipeline run` reads the workbook, finds the first stage whose
    #: done-predicate is false, and dispatches THAT lane over a brief —
    #: rather than a hand-written resume prompt to one agent. `agent` and
    #: `prompt` stay on the plan for a container without the driver.
    pipeline_cmd = ["python3", "-m", "engine.pipeline", "run", "--run", str(run_id)] \
        + (["--root", root] if root else [])
    base = (f"Resume DMA research run {run_id} for {row.get('entity')}. "
            f"The run root is {root}. Read `engine.cli orient {where}` FIRST "
            f"and work its do_first list in order. ")

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
        return {"actionable": True, "agent": agent, "pipeline": pipeline_cmd,
                "prompt": base + what + " Take it from where it stopped.",
                "why": f"{cat or 'the conductor'} owns the open work"}
    if state == "READY_FOR_HANDOFF":
        return {"actionable": True, "agent": "research-conductor",
                "pipeline": pipeline_cmd,
                "prompt": base + ("Every category is closed and gated. Render "
                                  "the four deliverables, assemble and verify "
                                  "the client folder, and push it to intake."),
                "why": "the run is finished and nothing has shipped it"}
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
        # The driver continues the run from its first undone stage.
        cmd = list(plan["pipeline"])
        if dry_run:
            return {"run_id": row.get("run_id"), "outcome": "DRY_RUN",
                    "state": row.get("state"), "agent": plan.get("agent"),
                    "would_run": " ".join(cmd), "resume_prompt": plan.get("prompt")}
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
    if dry_run:
        return {"run_id": row.get("run_id"), "outcome": "DRY_RUN",
                "state": row.get("state"), "agent": plan["agent"],
                "would_run": f"agent_run.py --agent {plan['agent']}",
                "resume_prompt": plan.get("prompt")}
    pf = Path(tempfile.gettempdir()) / f"revive_{row.get('run_id')}.md"
    pf.write_text(plan.get("prompt") or "")
    r = subprocess.run(
        [sys.executable, str(runner), "--agent", plan["agent"],
         "--prompt-file", str(pf)],
        capture_output=True, text=True, timeout=timeout)
    return {"run_id": row.get("run_id"),
            "outcome": "RESOLVED" if r.returncode == 0 else "FAILED",
            "state": row.get("state"), "agent": plan["agent"],
            "detail": (r.stdout or r.stderr).strip()[-400:]}


#: The states that need someone told. Everything else is the run working.
ACTIONABLE = ("UNREADABLE", "HALTED", "STALLED", "GATE_FAILED", "UNGATED",
              "AT_BUDGET_CEILING", "PRELIM_OPEN", "NO_CLIENT_FOLDER",
              "MISSING_LOCALLY", "READY_FOR_HANDOFF")


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
