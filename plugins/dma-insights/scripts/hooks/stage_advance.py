#!/usr/bin/env python3
"""The stage machine, at the moments a session can act on it.

    PostToolUse on Agent/Task   — a dispatched agent has returned
    PostToolUse on Bash         — a headless dispatch (agent_run.py) or an
                                  engine gate command has finished
    Stop                        — the session is about to end

WHY THIS EXISTS (owner, 2026-09-03, the headless-workflow audit): "check
where hooks are required … what hooks signify agent completion and what
criteria is being looked at; what hooks signal the scoring agents once
research is done …; what hooks invoke the report writing agents and
challenging agents once scoring is done."

Until now every one of those transitions lived in prose — the conductor's
manifest, step 3 to step 9 — and a prose transition is one a compacted
session forgets. The state itself was already computable: the floors gates,
`engine.assessment gate`, `engine.narrative state` and the client folder's
manifest are all read from the workbook, and `engine.watchdog` already turns
the research half into a state with a resume plan. This hook runs that
machine at the three moments that matter and puts the answer where the
session will read it:

  * after an agent returns: WHAT STATE the run is in now, THE CRITERION that
    closes it, and THE NEXT AGENT(S) to dispatch with the prompt to dispatch
    them with — as `additionalContext`, never as a block. A producer's
    return is expensive and already exists; the hook adds the next step.
  * on Stop: if the run the session was driving has a stage an AGENT can
    advance, refuse to stop ONCE per state and hand back the same next
    step. `stop_hook_active` and a marker file under the run's 07_qa make
    this a nudge and not a loop: the same state twice in a row is allowed
    to stop, because a stage that did not move after one re-dispatch needs
    a reader, not a third attempt.

WHAT IT NEVER DOES. It dispatches nothing, writes nothing to the workbook,
and never blocks a tool result. It reads the runs THIS container holds
(`$DMA_RUN_ROOT`, else the engine's default root), only those written to
within RECENT_HOURS — a run somebody else is driving, or one that finished
last week, is not this session's to keep alive. States a PERSON must decide
(HALTED, UNREADABLE, MISSING_LOCALLY) are reported and never block. It fails
OPEN and silent: an unreadable event, a missing engine, a workbook that
cannot be opened — no output, exit 0.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
SKILL = PLUGIN / "skills" / "dma-research"
AGENT_RUN = PLUGIN / "scripts" / "agent_run.py"

#: A run last written to longer ago than this is not this session's run.
RECENT_HOURS = float(os.environ.get("DMA_STAGE_RECENT_HOURS", "12"))

#: Bash commands that mean a stage may have moved. Anything else on Bash is
#: ignored so the hook does not open a workbook after every `ls`.
STAGE_COMMANDS = re.compile(
    r"agent_run\.py|engine\.(cli|assessment|narrative|assemble|prelim|"
    r"completeness|ship|watchdog)\b|engine/(registry|watchdog)\.py|"
    r"ship_page\.py")

MARKER = "stage_advance.json"


def _engine():
    """Import the research engine from the plugin this hook ships in."""
    if str(SKILL) not in sys.path:
        sys.path.insert(0, str(SKILL))
    from engine import runstate, watchdog                 # noqa: PLC0415
    return runstate, watchdog


def _run_root(runstate) -> Path:
    env = os.environ.get("DMA_RUN_ROOT")
    return Path(env) if env else runstate.RUN_ROOT


def recent_runs(hours: float = RECENT_HOURS) -> list[dict]:
    """The runs this container holds that were written to recently, each with
    the watchdog's state, criterion and resume plan."""
    try:
        runstate, watchdog = _engine()
    except Exception:                                      # noqa: BLE001
        return []
    root = _run_root(runstate)
    if not root.is_dir():
        return []
    want = os.environ.get("DMA_RUN_ID")
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        if want and d.name != want:
            continue
        try:
            run = runstate.locate(d.name, d)
        except ValueError:
            continue
        if not run.workbook_path.exists():
            continue
        try:
            age_h = (time.time() - run.workbook_path.stat().st_mtime) / 3600
        except OSError:
            continue
        if age_h > hours and not want:
            continue
        try:
            row = watchdog.inspect(run)
        except Exception as e:                             # noqa: BLE001
            row = {"run_id": d.name, "root": str(d), "state": "UNREADABLE",
                   "detail": str(e)[:200], "resume": {"actionable": False}}
        out.append(row)
    return out


def _advanceable(row: dict, watchdog) -> bool:
    plan = row.get("resume") or {}
    return (row.get("state") in watchdog.AGENT_ADVANCEABLE
            and bool(plan.get("actionable")))


def next_step(row: dict) -> str:
    """One paragraph the session can act on: state, criterion, next agent(s),
    and the exact dispatch command."""
    plan = row.get("resume") or {}
    state = row.get("state")
    head = (f"STAGE ADVANCE — run {row.get('run_id')} ({row.get('entity') or '?'}) "
            f"is at {state}: {row.get('detail')}")
    crit = row.get("criterion") or ""
    lines = [head]
    if crit:
        lines.append(f"Completion criterion: {crit}.")
    if plan.get("command"):
        lines.append("Next: run `" + " ".join(plan["command"]) + "`.")
    elif plan.get("agent"):
        agents = plan.get("parallel") or [plan["agent"]]
        lines.append(
            "Next: dispatch " + ", ".join(f"`{a}`" for a in agents)
            + (" in parallel lanes" if len(agents) > 1 else "")
            + f" — {plan.get('why', '')}.")
        lines.append(
            f"Prompt (write to a file, then `python3 {AGENT_RUN} --agent "
            f"{plan['agent']} --prompt-file <file> --stream`; the Agent tool "
            f"with the same text is equivalent): {plan.get('prompt', '')}")
    elif plan.get("why"):
        lines.append(f"Not an agent's to advance: {plan['why']}.")
    if state == "SHIPPED":
        lines.append("Nothing further from the research tier: the package "
                     "scan ingests the folder and the synthesis lanes "
                     "produce the six pages; `engine.ship state` says which "
                     "pages are producible now.")
    return "\n".join(lines)


def _marker_path(row: dict) -> Path | None:
    root = row.get("root")
    if not root:
        return None
    return Path(root) / "07_qa" / MARKER


def _blocked_before(row: dict) -> bool:
    """True when the Stop hook already refused once on THIS state — the
    loop guard. The same state twice means the re-dispatch did not move it."""
    p = _marker_path(row)
    if not p or not p.is_file():
        return False
    try:
        doc = json.loads(p.read_text())
    except (OSError, ValueError):
        return False
    return doc.get("blocked_on") == row.get("state")


def _record_block(row: dict) -> None:
    p = _marker_path(row)
    if not p:
        return
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        # write-then-rename: two hook processes finishing together (a batch
        # of lanes) must leave a marker that is one JSON document or the
        # other, never an interleaving that the next Stop cannot parse
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps({"blocked_on": row.get("state"),
                                   "at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                       time.gmtime()),
                                   "detail": row.get("detail")}, indent=1))
        os.replace(tmp, p)
    except OSError:
        pass


def on_post_tool_use(event: dict) -> dict | None:
    tool = str(event.get("tool_name") or "")
    ti = event.get("tool_input") or {}
    if tool == "Bash":
        cmd = ti.get("command") if isinstance(ti, dict) else ""
        if not isinstance(cmd, str) or not STAGE_COMMANDS.search(cmd):
            return None
    elif tool not in ("Agent", "Task"):
        return None
    rows = recent_runs()
    if not rows:
        return None
    try:
        _, watchdog = _engine()
    except Exception:                                      # noqa: BLE001
        return None
    texts = [next_step(r) for r in rows
             if r.get("state") in watchdog.ACTIONABLE
             or r.get("state") == "SHIPPED"]
    if not texts:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n\n".join(texts)}}


def on_stop(event: dict) -> dict | None:
    if os.environ.get("DMA_STAGE_GUARD", "").lower() in ("off", "0", "false"):
        return None
    if event.get("stop_hook_active"):
        return None                        # already continuing on our account
    rows = recent_runs()
    if not rows:
        return None
    try:
        _, watchdog = _engine()
    except Exception:                                      # noqa: BLE001
        return None
    for row in rows:
        if not _advanceable(row, watchdog):
            continue
        if _blocked_before(row):
            continue                        # nudged once already on this state
        _record_block(row)
        return {"decision": "block",
                "reason": (next_step(row) + "\n\nThe session was about to end "
                           "with this stage runnable by an agent. Dispatch the "
                           "next step above, or state in one line why it "
                           "cannot run here (no connector, no budget, a "
                           "person's decision) and then stop.")}
    return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                      # noqa: BLE001
        return 0
    if not isinstance(event, dict):
        return 0
    hook = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    out = None
    if hook == "PostToolUse":
        out = on_post_tool_use(event)
    elif hook == "Stop":
        out = on_stop(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                      # noqa: BLE001
        sys.exit(0)                                        # fail open, silent
