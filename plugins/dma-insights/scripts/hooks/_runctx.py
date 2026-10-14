#!/usr/bin/env python3
"""What every hook needs before it can say anything: WHICH RUN, and the
engine that reads it.

Not a hook. It is here so the five hooks that answer "is this dispatch worth
making" all resolve the run the same way — a guard that picked a different
run from its neighbour would refuse work on evidence from somewhere else.

RESOLUTION ORDER, most explicit first:
  $DMA_RUN_ID (+ $DMA_RUN_ROOT)  the child's own environment, written by
                                 agent_run.py / the pipeline
  $DMA_RUN_ROOT alone            the run tree this container is driving
  the newest run under the root  the one this session has been writing to

Everything fails OPEN: no run, no engine, an unreadable file — the caller
gets None and stays silent, because a guard that refuses when it cannot see
is a guard that stops the work it was meant to protect.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
SKILL = PLUGIN / "skills" / "dma-research"

#: A run last written to longer ago than this is not this session's run.
RECENT_HOURS = float(os.environ.get("DMA_STAGE_RECENT_HOURS", "12"))


def engine(*names):
    """Import engine modules from the plugin this hook ships in, or raise."""
    if str(SKILL) not in sys.path:
        sys.path.insert(0, str(SKILL))
    import importlib                                          # noqa: PLC0415
    return tuple(importlib.import_module(f"engine.{n}") for n in names)


def run_root() -> Path | None:
    env = os.environ.get("DMA_RUN_ROOT")
    if env:
        return Path(env)
    try:
        (runstate,) = engine("runstate")
    except Exception:                                          # noqa: BLE001
        return None
    return runstate.RUN_ROOT


def locate():
    """The `runstate.Run` this session is driving, or None.

    A run root that IS a run (the child's `--root <run dir>`) and a root that
    CONTAINS runs are both accepted: the first is what agent_run.py passes
    down, the second is what a conductor holds.
    """
    try:
        (runstate,) = engine("runstate")
    except Exception:                                          # noqa: BLE001
        return None
    want = str(os.environ.get("DMA_RUN_ID") or "").strip()
    root = os.environ.get("DMA_RUN_ROOT")
    if want:
        try:
            return runstate.locate(want, Path(root) if root else None)
        except (ValueError, OSError):
            return None
    base = Path(root) if root else runstate.RUN_ROOT
    if not base or not base.is_dir():
        return None
    # the root may itself be one run's directory
    try:
        for wb in base.glob("DMA_Scoring_Workbook_*.xlsx"):
            rid = wb.stem.replace("DMA_Scoring_Workbook_", "")
            try:
                return runstate.locate(rid, base)
            except ValueError:
                break
    except OSError:
        return None
    best, newest = None, None
    try:
        children = [p for p in base.iterdir() if p.is_dir()]
    except OSError:
        return None
    for d in sorted(children):
        try:
            run = runstate.locate(d.name, d)
        except ValueError:
            continue
        if not run.workbook_path.exists():
            continue
        try:
            m = run.workbook_path.stat().st_mtime
        except OSError:
            continue
        if (time.time() - m) / 3600 > RECENT_HOURS:
            continue
        if newest is None or m > newest:
            newest, best = m, run
    return best


def pipeline_state(run) -> dict:
    """`07_qa/pipeline_state.json`, or {} when it cannot be read."""
    if run is None:
        return {}
    try:
        p = Path(run.qa_dir) / "pipeline_state.json"
        return json.loads(p.read_text()) if p.is_file() else {}
    except (OSError, ValueError):
        return {}


def spent_usd(run) -> float | None:
    """What the cost ledger says this run has spent, or None if unmeasured."""
    try:
        (cost,) = engine("cost")
        rows = cost.ledger(run)
    except Exception:                                          # noqa: BLE001
        return None
    vals = [float(r["usd"]) for r in rows
            if isinstance(r, dict) and r.get("usd") is not None]
    return round(sum(vals), 4) if vals else 0.0


def budget(run, state: dict | None = None) -> dict:
    """{"spent", "ceiling", "remaining", "exhausted"} — every figure read.

    `exhausted` is True ONLY when a ceiling is known and has been reached.
    An unknown ceiling is not an exhausted one: a run with no recorded
    budget must not be refused its next lane.
    """
    st = pipeline_state(run) if state is None else state
    spent = st.get("spent_usd")
    if spent is None:
        spent = spent_usd(run)
    cap = st.get("budget_usd")
    try:
        spent = float(spent) if spent is not None else None
        cap = float(cap) if cap is not None else None
    except (TypeError, ValueError):
        spent, cap = None, None
    remaining = (round(cap - spent, 4)
                 if cap is not None and spent is not None else None)
    return {"spent": spent, "ceiling": cap, "remaining": remaining,
            "exhausted": bool(remaining is not None and remaining <= 0)}


def rounds(run, state: dict | None = None) -> dict:
    """{"done", "max", "remaining", "exhausted"} for the run's live stage."""
    st = pipeline_state(run) if state is None else state
    stages = st.get("stages") or {}
    done = 0
    for rec in stages.values():
        if isinstance(rec, dict):
            try:
                done = max(done, int(rec.get("rounds") or 0))
            except (TypeError, ValueError):
                continue
    try:
        (pipeline,) = engine("pipeline")
        cap = int(pipeline.Options.max_rounds)
    except Exception:                                          # noqa: BLE001
        cap = 10
    remaining = max(0, cap - done)
    return {"done": done, "max": cap, "remaining": remaining,
            "exhausted": remaining <= 0}


# ── did the lane write anything? ─────────────────────────────────────────

#: Where a dispatch records what the substrate looked like before the lane
#: ran, so the return can say whether the lane left anything behind.
DISPATCH_DIR = "dispatch"


def fingerprint(run) -> dict:
    """A CHEAP measure of the substrate: stat calls, never a workbook open.

    A hook that opened the workbook on every dispatch and every return would
    cost more than the thing it is measuring. Size and mtime of the workbook,
    the relay queue and the memory notebooks answer the only question asked
    of it — did anything change — and answer it wrongly in exactly one
    direction (a write that changed nothing reads as no write), which is the
    safe direction for an advisory line.
    """
    out = {"wb": None, "relay": None, "memory": None, "qa": None}
    if run is None:
        return out

    def _stat(p: Path):
        try:
            st = p.stat()
            return [int(st.st_mtime), int(st.st_size)]
        except OSError:
            return None

    out["wb"] = _stat(Path(run.workbook_path))
    out["relay"] = _stat(Path(run.qa_dir) / "search_relay.jsonl")
    try:
        mem = sorted((Path(run.root) / "03_memory").glob("*.md"))
        out["memory"] = sum((p.stat().st_size for p in mem), 0) if mem else 0
    except OSError:
        out["memory"] = None
    try:
        out["qa"] = len(list(Path(run.qa_dir).glob("*"))) if Path(run.qa_dir).is_dir() else 0
    except OSError:
        out["qa"] = None
    return out


def _dispatch_file(run, agent: str) -> Path:
    safe = "".join(c for c in str(agent or "agent") if c.isalnum() or c in "-_")
    return Path(run.qa_dir) / DISPATCH_DIR / f"{safe}.json"


def record_dispatch(run, agent: str) -> None:
    """Best-effort: the fingerprint at the moment a lane was dispatched."""
    if run is None or not agent:
        return
    try:
        p = _dispatch_file(run, agent)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"at": int(time.time()),
                                   "fingerprint": fingerprint(run)}, indent=1))
        os.replace(tmp, p)
    except OSError:
        pass


def wrote_since_dispatch(run, agent: str):
    """True / False / None — None when no dispatch was recorded to compare."""
    if run is None or not agent:
        return None
    try:
        p = _dispatch_file(run, agent)
        if not p.is_file():
            return None
        before = (json.loads(p.read_text()) or {}).get("fingerprint")
    except (OSError, ValueError):
        return None
    if not isinstance(before, dict):
        return None
    return fingerprint(run) != before
