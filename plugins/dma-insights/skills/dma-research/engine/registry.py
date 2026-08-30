#!/usr/bin/env python3
"""The list of DMAs that exist, kept where a fresh container can read it.

    python3 -m engine.registry log    --run R [--root DIR]
    python3 -m engine.registry list   [--json] [--open-only]
    python3 -m engine.registry beat   --run R --position "P1C1 card 3"
    python3 -m engine.registry close  --run R --outcome PACKAGED
    python3 -m engine.registry pull   |  push

WHY THIS EXISTS. The watchdog asked "which runs are stalled?" by listing
`$DMA_RUN_ROOT` — a directory that does not survive the container. Every
scheduled firing gets a fresh one, so the sweep found zero runs and reported
a quiet queue, which is indistinguishable from a healthy one and is how a
research run that stopped at category three stayed stopped. The synthesis
watchdog had the same shape of blindness on its own side and solved it by
round-tripping its state through Drive; this is that solution applied to the
side that owns the run directory.

The registry is APPEND-ONLY JSONL, one line per event, because a registry
that rewrites rows loses the history that makes a stall legible: the last
heartbeat's position is what tells the next firing where to resume, and an
overwritten row cannot say a run went quiet after moving.

It is a POINTER, never a source of truth. The workbook stays the run; a
registry row carries only what is needed to FIND the workbook again —
run id, entity, root, workbook path, client folder — plus the heartbeat.
"""
from __future__ import annotations

# Runnable both ways: -m engine.registry, or by path for --help.
if __package__ in (None, ""):  # noqa: E402
    import os as _os
    import sys as _sys
    _sys.path.insert(0, _os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    __package__ = "engine"

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from pathlib import Path

from . import runstate

#: Where the registry lives locally. Beside the run root, not inside a run.
REGISTRY_NAME = "dma_run_registry.jsonl"

#: The Drive ledger name the routine round-trips it under.
DRIVE_SESSION = "dma-run-registry"

OPEN_OUTCOMES = ("STARTED", "HEARTBEAT")
CLOSED_OUTCOMES = ("PACKAGED", "ABANDONED", "SUPERSEDED")


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def registry_path(root: Path | None = None) -> Path:
    """`$DMA_RUN_REGISTRY`, else beside `$DMA_RUN_ROOT`."""
    env = os.environ.get("DMA_RUN_REGISTRY")
    if env:
        return Path(env)
    base = Path(root) if root else runstate.RUN_ROOT
    return base.parent / REGISTRY_NAME if base.name else base / REGISTRY_NAME


def _append(row: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, default=str) + "\n")
    return path


def log(run: runstate.Run, *, event: str = "STARTED",
        position: str | None = None, detail: str | None = None,
        path: Path | None = None) -> dict:
    """Record that this DMA exists, or that it just moved."""
    md = {}
    try:
        md = run.open().metadata()
    except Exception:                                       # noqa: BLE001
        pass                       # a run whose workbook is gone still logs
    row = {
        "at": _utcnow(), "event": event,
        "run_id": md.get("run_id") or run.run_id,
        "entity": md.get("entity_name"), "entity_id": md.get("entity_id"),
        "sub_vertical": md.get("sub_vertical"),
        "evidence_mode": md.get("evidence_mode"),
        "root": str(run.root), "workbook": str(run.workbook_path),
        "client_folder": md.get("client_folder"),
        "position": position or (md.get("checkpoint") or None),
        "detail": detail,
    }
    p = _append(row, path or registry_path())
    return {**row, "registry": str(p)}


def read(path: Path | None = None) -> list[dict]:
    p = path or registry_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except ValueError:
            continue           # a torn line loses itself, never the registry
    return out


def latest(path: Path | None = None) -> dict[str, dict]:
    """The last event per run id, in registry order."""
    by_run: dict[str, dict] = {}
    for row in read(path):
        rid = row.get("run_id")
        if rid:
            by_run[rid] = row
    return by_run


def open_runs(path: Path | None = None) -> list[dict]:
    """Runs the registry has not seen closed — the watchdog's worklist."""
    return [r for r in latest(path).values()
            if str(r.get("event") or "") not in CLOSED_OUTCOMES]


# ── surviving the container ──────────────────────────────────────────────

def _drive_fetch() -> Path | None:
    p = Path(__file__).resolve().parents[3] / "scripts" / "drive_fetch.py"
    return p if p.exists() else None


def push(path: Path | None = None) -> dict:
    """The registry to Drive, so the next fresh container can read it."""
    p = path or registry_path()
    if not p.exists():
        return {"outcome": "NOT_RUN", "reason": f"no registry at {p}"}
    df = _drive_fetch()
    if df is None:
        return {"outcome": "NOT_RUN",
                "reason": "drive_fetch.py is not in this install"}
    r = subprocess.run(
        [sys.executable, str(df), "push-ledger", "--file", str(p),
         "--session", DRIVE_SESSION],
        capture_output=True, text=True, timeout=600)
    return ({"outcome": "RESOLVED", "detail": (r.stdout or "").strip()[-200:]}
            if r.returncode == 0 else
            {"outcome": "FAILED",
             "reason": (r.stderr or r.stdout or "").strip()[-300:]})


def pull(dest: Path | None = None) -> dict:
    """Drive's copy back down, merged into the local registry.

    Merged, not replaced: this container may have logged runs Drive has not
    seen yet, and a pull that overwrites them re-creates the blindness."""
    df = _drive_fetch()
    if df is None:
        return {"outcome": "NOT_RUN",
                "reason": "drive_fetch.py is not in this install"}
    tmp = Path(dest or "/root/.dma/ledgers")
    tmp.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [sys.executable, str(df), "pull-ledgers", "--dest", str(tmp)],
        capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        return {"outcome": "FAILED",
                "reason": (r.stderr or r.stdout or "").strip()[-300:]}
    remote = tmp / REGISTRY_NAME
    if not remote.exists():
        hits = sorted(tmp.rglob(REGISTRY_NAME))
        remote = hits[-1] if hits else None
    if remote is None:
        return {"outcome": "NO_SOURCE",
                "reason": f"pull-ledgers brought down no {REGISTRY_NAME}"}
    local = registry_path()
    seen = {json.dumps(r_, sort_keys=True, default=str) for r_ in read(local)}
    added = 0
    for row in read(remote):
        key = json.dumps(row, sort_keys=True, default=str)
        if key not in seen:
            _append(row, local)
            seen.add(key)
            added += 1
    return {"outcome": "RESOLVED", "merged_rows": added,
            "registry": str(local), "from": str(remote)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="engine.registry",
                                 description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, helptext in (("log", "record a run as STARTED"),
                           ("beat", "record a heartbeat with its position"),
                           ("close", "record a run as finished")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("--run", required=True)
        p.add_argument("--root")
        if name == "beat":
            p.add_argument("--position", required=True)
        if name == "close":
            p.add_argument("--outcome", default="PACKAGED",
                           choices=CLOSED_OUTCOMES)
        p.add_argument("--detail")
    ls = sub.add_parser("list", help="the last event per run")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--open-only", action="store_true")
    sub.add_parser("push", help="registry -> Drive")
    pl = sub.add_parser("pull", help="Drive -> registry (merged)")
    pl.add_argument("--dest")

    a = ap.parse_args(argv)
    if a.cmd == "push":
        print(json.dumps(push(), indent=2)); return 0
    if a.cmd == "pull":
        out = pull(Path(a.dest) if a.dest else None)
        print(json.dumps(out, indent=2))
        return 0 if out["outcome"] in ("RESOLVED", "NO_SOURCE") else 1
    if a.cmd == "list":
        rows = open_runs() if a.open_only else list(latest().values())
        if a.json:
            print(json.dumps(rows, indent=2))
        elif not rows:
            print(f"no runs registered in {registry_path()}")
        else:
            for r in rows:
                print(f"[{r.get('event','?'):<9}] {r.get('run_id')}  "
                      f"{r.get('entity') or '?'}  {r.get('at')}  "
                      f"{r.get('position') or ''}")
        return 0
    run = runstate.locate(a.run, Path(a.root) if a.root else None)
    event = {"log": "STARTED", "beat": "HEARTBEAT"}.get(
        a.cmd, getattr(a, "outcome", "PACKAGED"))
    print(json.dumps(log(run, event=event,
                         position=getattr(a, "position", None),
                         detail=a.detail), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
