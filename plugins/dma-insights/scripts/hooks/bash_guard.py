#!/usr/bin/env python3
"""One process for every Bash guard, in the pinned order.

    PreToolUse on Bash | mcp__workspace__bash

WHY THIS EXISTS. Measured 28-09-2026 (QA audit F-H01-023): six PreToolUse
guards on every Bash call, each its own Python process (56+42+33+63+45+62
ms ≈ 301 ms of interpreter start-up per call) plus stage_advance on every
Bash result — ≈ 0.9 s of hooks per command, most of it spent starting
interpreters that then said nothing. The guards were already written as
`decide()` functions; this runs them in ONE process, in the order the
manifest pinned, and answers with the first denial or, when no guard
objects, with the auto-approver's decision.

THE ORDER IS THE POLICY. A denial is decided before anything can approve
(test_hooks_wiring pins it against this list): the driver lock, the
credential guard, the never-cat rule, the artefact-write guard, the
actor-scope guard, the deliverable gate — then, and only then,
autoapprove_builtins. Each guard keeps its own file, its own tests and its
own fail-open posture; a guard that cannot import or raises is skipped
here exactly as its own process exiting 0 would have been.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

#: (script, adapter): the adapter turns the module's own decide into a
#: hookSpecificOutput dict (deny) or None. Order is load-bearing.
ORDER = (
    ("guard_driver_lock.py", "driver_lock"),
    ("deny_credential_ops.py", "credential_ops"),
    ("deny_bulk_read.py", "bulk_read"),
    ("deny_artefact_writes.py", "artefact_writes"),
    ("guard_actor_scope.py", "actor_scope"),
    ("deliverable_gate.py", "deliverable_gate"),
)
APPROVER = "autoapprove_builtins.py"


def _load(script: str):
    spec = importlib.util.spec_from_file_location(script[:-3], HERE / script)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _command(payload: dict) -> str:
    ti = payload.get("tool_input") or {}
    cmd = ti.get("command") if isinstance(ti, dict) else ""
    return cmd if isinstance(cmd, str) else ""


def normalise(payload: dict) -> dict:
    """Cowork's `mcp__workspace__bash` is Bash with another name and,
    sometimes, another key for the command."""
    if payload.get("tool_name") != "mcp__workspace__bash":
        return payload
    ti = payload.get("tool_input") or {}
    if isinstance(ti, dict) and "command" not in ti:
        for key in ("cmd", "script", "input"):
            if isinstance(ti.get(key), str):
                ti = {"command": ti[key]}
                break
    return dict(payload, tool_name="Bash", tool_input=ti)


def _adapt(kind: str, module, payload: dict) -> dict | None:
    cmd = _command(payload)
    if kind == "driver_lock":
        why = module.decide(payload)
        return _deny(why) if why else None
    if kind == "credential_ops":
        why = module.decide(cmd)
        return _deny(why) if why else None
    if kind == "bulk_read":
        why = module.decide(cmd)
        return _deny(why) if why else None
    if kind == "artefact_writes":
        why = module.decide(payload)
        return _deny(why) if why else None
    if kind == "actor_scope":
        return module.decide_payload(payload)
    if kind == "deliverable_gate":
        return module.on_pre_tool_use(payload)
    return None


def decide(payload: dict) -> dict | None:
    """The first denial in the pinned order, else the approver's answer."""
    payload = normalise(payload)
    if payload.get("tool_name") != "Bash":
        return None
    for script, kind in ORDER:
        try:
            out = _adapt(kind, _load(script), payload)
        except Exception:                                      # noqa: BLE001
            continue                        # the guard's own fail-open posture
        if out:
            return out
    try:
        return _load(APPROVER).decide(payload)
    except Exception:                                          # noqa: BLE001
        return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:                                          # noqa: BLE001
        return 0
    if not isinstance(payload, dict):
        return 0
    out = decide(payload)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                          # noqa: BLE001
        sys.exit(0)                                            # fail open, silent
