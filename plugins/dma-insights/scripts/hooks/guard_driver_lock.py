#!/usr/bin/env python3
"""PreToolUse on Bash: one driver per run.

WHY. `engine.pipeline run` dispatches lanes, spends the run's budget and
writes `07_qa/pipeline_state.json`. Two drivers on one run is not a race for
a row — it is two budgets counted as one, two lane fleets writing one
workbook, and a state file whose rounds counter is the last writer's. The
symptom is a run that reads as stalled while it is actually being driven
twice.

WHAT THIS HOOK IS, AND IS NOT. The PRIMARY belongs in the engine
(`runstate.acquire_driver_lock`) — a lock a hook holds protects only the
sessions that have the hook, and the driver is also started by Routines,
by the watchdog and from a terminal. Another stream owns `engine/`; that
primary DOES NOT EXIST YET (measured 2026-09-14: no `driver.lock`, no
`acquire_driver_lock`, anywhere in the plugin). So this is the belt in front
of an absent brace: it refuses a second driver in a session that HAS the
hook, and it is honest that a session without one is unaffected.

THE LOCK FILE SHAPE IT ASSUMES — stated here so the engine's primary can be
built to match, and tolerant enough that a reasonable variant still reads:

    07_qa/driver.lock            JSON object
      {"pid": 12345,             the driver process, on THIS host
       "host": "abc123",         optional; a different host is not our pid
       "at": "2026-09-14T…Z",    when it was taken (ISO-8601 Z)
       "heartbeat": "…Z",        last liveness write; `at` is used if absent
       "run_id": "…",            optional
       "command": "engine.pipeline run --step …"}   optional, for the reason

  A lock is LIVE when its pid exists on this host AND its heartbeat is
  younger than STALE_AFTER_S. Anything else — no file, unparsable JSON, no
  pid, a dead pid, a stale heartbeat, a lock from another host — ALLOWS the
  command. A driver refused because a hook could not read a file is worse
  than the collision it was guarding against.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _runctx as ctx                                          # noqa: E402

LOCK_NAME = "driver.lock"

#: A heartbeat older than this is a dead driver's, whatever its pid says. The
#: pipeline's own round can take many minutes, so this is generous: refusing a
#: legitimate driver costs more than a late second one.
STALE_AFTER_S = float(os.environ.get("DMA_DRIVER_LOCK_STALE_S", "1800"))

#: The command this guards. `plan`, `status`, `env` and `stages` read and
#: dispatch nothing, so they are not driving anything and are not matched.
DRIVER_CMD = re.compile(r"engine\.pipeline\s+run\b")


def _alive(pid: int) -> bool:
    try:
        os.kill(int(pid), 0)
    except (ProcessLookupError, ValueError, TypeError):
        return False
    except PermissionError:
        return True                    # exists, owned by someone else
    except OSError:
        return False
    return True


def _age_s(doc: dict) -> float | None:
    raw = str(doc.get("heartbeat") or doc.get("at") or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
                "%Y-%m-%dT%H:%M:%S%z"):
        try:
            import datetime as dt                              # noqa: PLC0415
            t = dt.datetime.strptime(raw, fmt)
            if t.tzinfo is None:
                t = t.replace(tzinfo=dt.timezone.utc)
            return (dt.datetime.now(dt.timezone.utc) - t).total_seconds()
        except ValueError:
            continue
    try:
        return max(0.0, time.time() - float(raw))
    except (TypeError, ValueError):
        return None


def lock_path(command: str):
    """The run this command names, and where its lock would live."""
    run_id, root = _run_flags(command)
    if root:
        return Path(root) / "07_qa" / LOCK_NAME, run_id
    run = ctx.locate()
    if run is None:
        return None, run_id
    return Path(run.qa_dir) / LOCK_NAME, (run_id or run.run_id)


def _run_flags(command: str) -> tuple[str, str]:
    try:
        argv = shlex.split(command or "")
    except ValueError:
        return "", ""
    out = {"run": "", "root": ""}
    for name in out:
        want = f"--{name}"
        for i, tok in enumerate(argv):
            if tok == want and i + 1 < len(argv):
                out[name] = argv[i + 1]
            elif tok.startswith(want + "="):
                out[name] = tok.split("=", 1)[1]
    return out["run"], out["root"]


def held_by(path: Path) -> dict | None:
    """The LIVE lock at `path`, or None. Every unknown is None."""
    try:
        if not path or not path.is_file():
            return None
        doc = json.loads(path.read_text())
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(doc, dict):
        return None
    host = str(doc.get("host") or "").strip()
    if host and host != _host():
        return None                    # not a pid we can ask about
    pid = doc.get("pid")
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    if pid == os.getpid() or not _alive(pid):
        return None
    age = _age_s(doc)
    if age is not None and age > STALE_AFTER_S:
        return None                    # heartbeat stopped: the driver is gone
    return dict(doc, pid=pid, age_s=(round(age) if age is not None else None))


def _host() -> str:
    try:
        import socket                                          # noqa: PLC0415
        return socket.gethostname()
    except Exception:                                          # noqa: BLE001
        return ""


def decide(payload: dict) -> str:
    """The reason to deny, or "" to allow."""
    if str(payload.get("tool_name") or "") != "Bash":
        return ""
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return ""
    command = ti.get("command")
    if not isinstance(command, str) or not DRIVER_CMD.search(command):
        return ""
    path, run_id = lock_path(command)
    if path is None:
        return ""
    live = held_by(path)
    if not live:
        return ""
    age = live.get("age_s")
    return (
        f"dma-insights: run {run_id or '?'} already has a driver — pid "
        f"{live['pid']}, "
        + (f"heartbeat {age}s old" if age is not None else "no heartbeat recorded")
        + f", lock at {path}"
        + (f", started as `{str(live.get('command'))[:120]}`"
           if live.get("command") else "")
        + ".\n\nTwo drivers on one run is not a race for a row: it is two "
          "lane fleets writing one workbook, two budgets counted as one, and "
          "a `pipeline_state.json` whose round counter belongs to whoever "
          "wrote last. Watch the live one instead — `python3 -m "
          "engine.pipeline status --run "
        + (run_id or "<RUN>")
        + " --watch` — or, if you know that driver is dead, delete the lock "
          "and say why.\n\nNOTE: this refusal is a HOOK, not the engine. The "
          "engine-side primary (`runstate.acquire_driver_lock`) is not built "
          "yet, so a driver started in a session without this plugin is not "
          "refused by anything.")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except Exception:                                          # noqa: BLE001
        return 0                       # fail OPEN, on purpose
    try:
        why = decide(payload)
    except Exception:                                          # noqa: BLE001
        return 0
    if not why:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": why,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
