"""One category's RESEARCH round as LEAN headless tiers — the job the visible
`workflows/dma-research-tiers.js` runner starts and waits on.

    python3 -m engine.tiers start --run R --root ROOT --category P2C2 [--round N]
    python3 -m engine.tiers wait  --run R --root ROOT --category P2C2 [--timeout 540]
    python3 -m engine.tiers status --run R --root ROOT [--category P2C2]

WHY A JOB AND A RUNNER (owner, 2026-10-09: "fix the context floor too, run
collectors headless" and, once they ran, "I do not see the workflow"). The
lean lanes (agent_run.py `lean_command`) open at ~6.5K tokens instead of the
73.8K an in-session workflow subagent pays; but lanes started by the driver
are invisible in /workflows, and research has been a visible, persisted
workflow since 2026-09-30. So the workflow stays the face — one small haiku
runner per category, a handful of turns — and the work happens in the lanes
this job dispatches: haiku collectors, the sonnet orchestrator, the sonnet
challenger, then the floors gate, every lane's exact cost booked to the ledger.

`start` is idempotent: a job already running for the category is reported,
not started twice. `wait` blocks up to --timeout seconds (inside one Bash
call's ten-minute limit) and prints the job's status; the runner calls it
until the state is `done` or `failed`. The job writes nothing to the driver's
state file — sixteen category jobs run at once — and the lanes of every job
share one host-wide pool (`DMA_LANE_POOL`), so they never oversubscribe it.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Runnable both ways: -m engine.tiers, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    __package__ = "engine"

from . import runstate  # noqa: E402

STATUS_DIR = "tiers"
#: lean lanes the whole host runs at once, across every category job: memory
#: per lean child is ~250-350 MB and the work is I/O-bound, so the CPU count
#: is not the bound; DMA_TIER_LANES overrides
DEFAULT_POOL = 16


def _status_path(run, cat: str) -> Path:
    d = run.qa_dir / STATUS_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{cat.upper()}.json"


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write(path: Path, doc: dict) -> None:
    runstate._write_atomic(path, json.dumps(doc, indent=1, default=str))


def _alive(pid) -> bool:
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def _pool_env(run) -> dict:
    n = int(os.environ.get("DMA_TIER_LANES") or DEFAULT_POOL)
    return {**os.environ, "DMA_LANE_POOL": f"{run.qa_dir / STATUS_DIR / 'lane_pool'}:{n}"}


def start(run, cat: str, rnd: int | None) -> dict:
    path = _status_path(run, cat)
    cur = _read(path)
    if cur.get("state") == "running" and _alive(cur.get("pid")):
        return {**cur, "note": "already running — wait on it; nothing was started twice"}
    log = path.with_suffix(".log")
    argv = [sys.executable, "-m", "engine.tiers", "work", "--run", run.run_id,
            "--root", str(run.root), "--category", cat.upper()]
    if rnd is not None:
        argv += ["--round", str(rnd)]
    with open(log, "a") as fh:
        proc = subprocess.Popen(argv, cwd=str(Path(__file__).resolve().parents[1]),
                                stdout=fh, stderr=subprocess.STDOUT,
                                start_new_session=True, env=_pool_env(run))
    doc = {"category": cat.upper(), "state": "running", "pid": proc.pid,
           "round": rnd, "started_at": time.time(), "log": str(log)}
    _write(path, doc)
    return doc


def wait(run, cat: str, timeout: float) -> dict:
    path = _status_path(run, cat)
    t0 = time.monotonic()
    while True:
        cur = _read(path)
        st = cur.get("state")
        if st in ("done", "failed"):
            return cur
        if st == "running" and not _alive(cur.get("pid")):
            cur.update(state="failed", error="the job process is gone with no result "
                                             f"— read {cur.get('log')}")
            _write(path, cur)
            return cur
        if not st:
            return {"category": cat.upper(), "state": "not_started",
                    "note": "run `engine.tiers start` first"}
        if time.monotonic() - t0 >= timeout:
            return {**cur, "note": "still running — call wait again"}
        time.sleep(5)


def work(run, cat: str, rnd: int | None) -> int:
    """The job: one tiers round for one category, under the real dispatcher."""
    from . import pipeline as P
    path = _status_path(run, cat)
    doc = _read(path) or {"category": cat.upper()}
    doc.update(state="running", pid=os.getpid())
    _write(path, doc)
    t0 = time.monotonic()
    try:
        handoff = json.loads((run.qa_dir / P.RESEARCH_HANDOFF).read_text())
        inv = next((i for i in handoff.get("invocations") or [] if cat.upper() in i["cats"]), None)
        if inv is None:
            raise RuntimeError(f"{cat} is not in the current handoff "
                               f"({run.qa_dir / P.RESEARCH_HANDOFF}) — re-run the driver")
        rnd = int(inv.get("round") if rnd is None and inv.get("round") is not None else (rnd or 0))
        manifest = json.loads(Path((handoff.get("agent_prompts") or {})["manifest"]).read_text())
        p = P.Pipeline(run, P.Options(dispatcher=P.AgentRunDispatcher(), reads=None,
                                      shipper=None, push=False, research_mode="tiers",
                                      log=lambda s: print(s, flush=True)))
        res = p.tier_round([cat.upper()], rnd, manifest)
        g = (res.get("gates") or {}).get(cat.upper()) or {}
        doc.update(state="done", result=res, gate=g.get("gate"),
                   repair_cells=g.get("repair_cells"),
                   usd=round(sum(float(ph.get("usd") or 0) for ph in res["phases"].values()), 4),
                   elapsed_s=round(time.monotonic() - t0, 1), stopped=res.get("stopped"))
        _write(path, doc)
        return 0
    except Exception as e:                                   # noqa: BLE001
        doc.update(state="failed", error=f"{e.__class__.__name__}: {str(e)[:600]}",
                   elapsed_s=round(time.monotonic() - t0, 1))
        _write(path, doc)
        print(doc["error"], file=sys.stderr)
        return 1


def _cats(arg: str) -> list[str]:
    return [c.strip().upper() for c in str(arg or "").split(",") if c.strip()]


def _brief(doc: dict) -> dict:
    """The few fields a runner reports — never the whole round result, which
    a runner re-reading on every wait would pay for in context."""
    phases = ((doc.get("result") or {}).get("phases") or {})
    return {k: v for k, v in {
        "category": doc.get("category"), "state": doc.get("state"),
        "gate": doc.get("gate"), "repair_cells": doc.get("repair_cells"),
        "usd": doc.get("usd"), "elapsed_s": doc.get("elapsed_s"),
        "error": doc.get("error"), "note": doc.get("note"),
        "phases": [f"{ph}: {v.get('lanes')} lanes, {v.get('ok')} ok, "
                   f"${float(v.get('usd') or 0):.2f}, {v.get('elapsed_s')}s"
                   for ph, v in phases.items()] or None,
    }.items() if v is not None}


def wait_all(run, cats: list[str], timeout: float) -> dict:
    """Wait until every named category's job is done or failed (or the timeout
    passes), then report each in brief — one wait call for the whole round."""
    t0 = time.monotonic()
    while True:
        left = max(0.0, timeout - (time.monotonic() - t0))
        rows = [wait(run, c, 0) for c in cats]
        open_ = [r for r in rows if r.get("state") == "running"]
        if not open_ or left <= 0:
            return {"state": "running" if open_ else "done",
                    "done": sum(1 for r in rows if r.get("state") == "done"),
                    "failed": sum(1 for r in rows if r.get("state") in ("failed", "not_started")),
                    "running": [r.get("category") for r in open_],
                    "usd": round(sum(float(r.get("usd") or 0) for r in rows), 4),
                    "categories": [_brief(r) for r in rows] if not open_ else None}
        time.sleep(min(5.0, left) or 0.1)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.tiers", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("start", "wait", "work", "status"):
        sp = sub.add_parser(name)
        sp.add_argument("--run", required=True)
        sp.add_argument("--root")
        sp.add_argument("--category", required=(name != "status"))
        sp.add_argument("--round", type=int, default=None)
        sp.add_argument("--timeout", type=float, default=540)
    a = ap.parse_args(argv)
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    if a.cmd == "start":
        out = [_brief({**start(run, c, a.round), "result": None}) for c in _cats(a.category)]
        print(json.dumps(out[0] if len(out) == 1 else out, indent=1, default=str)); return 0
    if a.cmd == "wait":
        cats = _cats(a.category)
        if len(cats) > 1:
            r = wait_all(run, cats, a.timeout)
            print(json.dumps(r, indent=1, default=str))
            return 0
        r = wait(run, cats[0], a.timeout)
        print(json.dumps(_brief(r), indent=1, default=str))
        return 0 if r.get("state") in ("done", "running", "not_started") else 1
    if a.cmd == "work":
        return work(run, a.category, a.round)
    d = run.qa_dir / STATUS_DIR
    rows = [(_read(f)) for f in sorted(d.glob("*.json"))] if d.is_dir() else []
    if a.category:
        rows = [r for r in rows if r.get("category") == a.category.upper()]
    print(json.dumps(rows, indent=1, default=str)); return 0


if __name__ == "__main__":
    sys.exit(main())
