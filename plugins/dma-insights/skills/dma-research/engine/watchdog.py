#!/usr/bin/env python3
"""A research run that has stopped says so.

    watchdog.py --root /home/claude/dma_output [--stall-seconds 900] [--json]

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
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

from . import contract as C
from . import floors_gate, ledger as L, runstate
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

    if drift:
        state, detail = "HALTED", "; ".join(drift)
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

    return {
        "run_id": md.get("run_id") or run.run_id,
        "entity": md.get("entity_name"),
        "workbook": str(run.workbook_path),
        "state": state, "detail": detail,
        "idle_seconds": None if idle is None else int(idle),
        "categories": len(cats), "open": open_work,
        "gate_failed": failed, "ungated": ungated,
        "search_ops": budget["search_ops"],
        "catalogue_drift": drift,
    }


def sweep(root: Path, *, stall_seconds: int = STALL_SECONDS) -> list[dict]:
    root = Path(root)
    out = []
    if not root.exists():
        return out
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        try:
            run = runstate.locate(d.name, d)
        except ValueError:
            continue
        if run.workbook_path.exists():
            out.append(inspect(run, stall_seconds=stall_seconds))
    return out


#: The states that need someone told. Everything else is the run working.
ACTIONABLE = ("UNREADABLE", "HALTED", "STALLED", "GATE_FAILED", "UNGATED",
              "AT_BUDGET_CEILING")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=str(runstate.RUN_ROOT))
    ap.add_argument("--run")
    ap.add_argument("--stall-seconds", type=int, default=STALL_SECONDS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = ([inspect(runstate.locate(a.run, Path(a.root) / a.run),
                     stall_seconds=a.stall_seconds)]
            if a.run else sweep(Path(a.root), stall_seconds=a.stall_seconds))
    if a.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"[{r['state']:<18}] {r['run_id']}  {r['detail']}")
        if not rows:
            print(f"no research runs under {a.root}")
    return 1 if any(r["state"] in ACTIONABLE for r in rows) else 0


if __name__ == "__main__":
    sys.exit(main())
