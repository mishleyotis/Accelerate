#!/usr/bin/env python3
"""Record the handoff workflows this session starts, so nothing starts them twice.

    PreToolUse on Workflow   — a Workflow({scriptPath, args}) is about to start
    PostToolUse on Workflow  — the tool returned (a run id, if it printed one)

WHY (measured 2026-10-07): every workflow stage ends the driver
AWAITING_WORKFLOW with a handoff file, and the session starts the workflows.
Nothing recorded that it had. The watchdog inferred "running" from the
workbook's last write with a 15-minute window — but a research agent mid-
search and a page producer writing section files both look idle there — so
a live workflow read as orphaned, the Stop hook printed the same Workflow
calls again, and a session that obeyed bought every agent twice.

This hook writes `<root>/07_qa/workflow_inflight.json` BEFORE the workflow
starts (keyed by a digest of its script and args, so the same handoff is one
entry however often it is printed) and adds the runtime's `wf_` run id after
the call returns, which is what `Workflow({resumeFromRunId})` needs to resume
a stopped workflow instead of restarting it. `engine.watchdog` reads the
record as WORKFLOW_RUNNING for up to six hours; the driver forgets it when it
is run as the handoff's `then`, after the workflows returned.

It blocks ONE thing: a second `Workflow` start with the same script and args
while the first is recorded as started and not yet forgotten by the driver —
the double dispatch itself. A start that carries `resumeFromRunId` is a
resume, not a second start, and passes; `DMA_WORKFLOW_RESTART=1` is the
person's override. Everything else fails OPEN: an unreadable event, args
with no run root, an unwritable qa dir — exit 0.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

NAME = "workflow_inflight.json"
#: How long a recorded start is believed (the watchdog's INFLIGHT_MAX_SECONDS).
MAX_SECONDS = 6 * 3600


def _age(ts) -> float | None:
    try:
        t = _dt.datetime.strptime(str(ts), "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None
    return (_dt.datetime.now(_dt.timezone.utc) - t).total_seconds()


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _args(tool_input: dict) -> dict:
    a = tool_input.get("args")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except ValueError:
            return {}
    return a if isinstance(a, dict) else {}


def label_of(args: dict) -> str:
    """Which stage and unit a handoff invocation is, from its own keys."""
    if args.get("cats") or args.get("pillar") and args.get("batches") is not None:
        return f"RESEARCH {','.join(args.get('cats') or [args.get('pillar') or '?'])}"
    if "briefs" in args:
        return f"SCORING {args.get('pillar') or '?'}"
    if "report" in args:
        return f"REPORTS {args.get('report')}"
    if "pages" in args:
        return (f"PAGES_{args.get('version') or '?'} "
                f"{','.join(str(p.get('page')) for p in (args.get('pages') or []) if isinstance(p, dict))}")
    return "WORKFLOW"


def digest_of(tool_input: dict, args: dict) -> str:
    raw = json.dumps({"script": tool_input.get("scriptPath") or tool_input.get("name") or "",
                      "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def duplicate_start(event: dict) -> str:
    """The reason this PreToolUse Workflow start is a SECOND start of a
    workflow already recorded as started, or "" when it is not."""
    if str(event.get("hook_event_name") or event.get("hookEventName") or "") != "PreToolUse":
        return ""
    if os.environ.get("DMA_WORKFLOW_RESTART", "").lower() in ("1", "true", "yes"):
        return ""
    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict) or ti.get("resumeFromRunId"):
        return ""                                  # a resume is not a second start
    args = _args(ti)
    root = str(args.get("root") or "").strip()
    if not root:
        return ""
    f = Path(root) / "07_qa" / NAME
    try:
        doc = json.loads(f.read_text()) if f.is_file() else {}
    except (OSError, ValueError):
        return ""
    prev = ((doc.get("workflows") or {}) if isinstance(doc, dict) else {}).get(
        digest_of(ti, args))
    if not isinstance(prev, dict):
        return ""
    age = _age(prev.get("started_at"))
    if age is None or age > MAX_SECONDS:
        return ""
    wid = prev.get("workflow_run_id")
    return (f"dma-insights: this exact Workflow ({prev.get('label') or 'handoff'}) was "
            f"already started {int(age // 60)} min ago by this run's session and the "
            f"driver has not run `then` since, so starting it again would buy every "
            f"agent twice. "
            + (f"If it stopped partway, RESUME it: Workflow({{resumeFromRunId: \"{wid}\", "
               f"scriptPath, args}}). " if wid else
               "If it stopped partway, resume it by its wf_ run id (/workflows lists it). ")
            + "If it has returned, run the handoff's `then` (the driver forgets the "
              "record). A deliberate restart sets DMA_WORKFLOW_RESTART=1.")


def record(event: dict) -> dict | None:
    """Apply one Workflow tool event to the run's in-flight record; returns
    the entry written, or None when the event is not ours."""
    if str(event.get("tool_name") or "") != "Workflow":
        return None
    ti = event.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    args = _args(ti)
    root = str(args.get("root") or "").strip()
    if not root:
        return None
    qa = Path(root) / "07_qa"
    f = qa / NAME
    try:
        doc = json.loads(f.read_text()) if f.is_file() else {}
    except (OSError, ValueError):
        doc = {}
    if not isinstance(doc, dict) or not isinstance(doc.get("workflows"), dict):
        doc = {"workflows": {}}
    key = digest_of(ti, args)
    hook = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    entry = dict(doc["workflows"].get(key) or {})
    if hook == "PreToolUse" or not entry:
        entry.update({"started_at": entry.get("started_at") or _utcnow(),
                      "label": label_of(args), "run": args.get("run"),
                      "script": ti.get("scriptPath") or ti.get("name") or "",
                      "resumed_from": ti.get("resumeFromRunId") or None})
    if hook == "PostToolUse":
        text = json.dumps(event.get("tool_response"), default=str)
        m = re.search(r"\bwf_[a-z0-9-]{6,}\b", text)
        if m:
            entry["workflow_run_id"] = m.group(0)
            entry["resume"] = (f"Workflow({{resumeFromRunId: \"{m.group(0)}\", "
                               f"scriptPath: \"{entry.get('script')}\", args: <the same args>}})")
    doc["workflows"][key] = entry
    try:
        qa.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(doc, indent=1))
    except OSError:
        return None
    return entry


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                      # noqa: BLE001
        return 0
    try:
        why = duplicate_start(event)
        if why:
            print(json.dumps(_deny(why)))
            return 0
        record(event)
    except Exception:                                      # noqa: BLE001
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
