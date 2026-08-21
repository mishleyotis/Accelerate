#!/usr/bin/env python3
"""PostToolUse on the dispatch tool — a producer that returns must have filed.

WHY. Storing an artifact was a step in a prompt, which means it was a step
that got skipped. Sections were produced, reported in a transcript, and never
written anywhere durable; the next session found nothing, produced them again,
and had no way to know it was the second time. Nothing detected any of it,
because a missing artifact and an unproduced one look identical.

A prompt cannot fix that — the instruction to store was already there. What
closes it is a check that runs at the moment the work exists and is still
recoverable: the instant a dispatched producer returns.

WHAT IT DOES. On every Agent/Task return whose subagent is a routed DMA
producer, it looks for an artifact from that agent for the live run:

  * found      — silent. A hook that speaks on success trains people to
                 ignore it.
  * not found  — a reminder naming the exact `artifact_store.py put` command,
                 injected as additionalContext so the orchestrator sees it in
                 the turn where the payload is still in hand.

It NEVER blocks. A producer's output is expensive and already exists by the
time this runs; refusing the tool result would throw away the very work the
hook exists to preserve. It also never writes the artifact itself — it cannot
see the payload, only that the agent returned, and a hook that invented a body
would be worse than the gap.

The run and the artifact root come from the session's own state, written at
claim time. Where that is unreadable the hook stays silent rather than
guessing: an enforcement that fires on a wrong run id is noise, and noise gets
switched off.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORE = HERE.parent / "artifact_store.py"
DRIVE = HERE.parent / "drive_fetch.py"
BUNDLES = Path(os.environ.get("DMA_BUNDLE_CACHE", "/root/.dma/bundles"))

# Agents whose whole job is to produce something that must survive the session.
# Checkers and auditors are included: a challenge report nobody kept is a
# challenge that has to be run again before the page can consolidate.
PRODUCER = re.compile(
    r"(-producer|-checker|-auditor|finding-challenger|page-consolidator"
    r"|package-vetter|enrichment-planner)$")


def _context():
    """(run_id, artifact_root) from the session's own state, or (None, None)."""
    root_env = os.environ.get("DMA_ARTIFACT_ROOT")
    run_env = os.environ.get("DMA_RUN_ID")
    if root_env and run_env:
        return run_env, Path(root_env)
    if not BUNDLES.is_dir():
        return None, None
    newest, best = None, None
    for st in BUNDLES.glob("*/state.json"):
        try:
            m = st.stat().st_mtime
            if newest is None or m > newest:
                newest, best = m, st
        except OSError:
            continue
    if best is None:
        return None, None
    try:
        state = json.loads(best.read_text())
    except Exception:                                        # noqa: BLE001
        return None, None
    run = state.get("run_id")
    root = state.get("artifact_root") or str(best.parent / "artifacts")
    return (run, Path(root)) if run else (None, None)


def _already_filed(root: Path, run: str, agent: str) -> bool:
    r = subprocess.run(
        [sys.executable, str(STORE), "find", "--root", str(root),
         "--run", run, "--agent", agent],
        capture_output=True, text=True, timeout=30)
    return bool(r.stdout.strip())


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                        # noqa: BLE001
        return 0

    ti = event.get("tool_input") or {}
    agent = (ti.get("subagent_type") or ti.get("agent") or "")
    if isinstance(agent, str) and ":" in agent:
        agent = agent.split(":")[-1]          # dma-insights:overview-hero-producer
    if not isinstance(agent, str) or not PRODUCER.search(agent):
        return 0

    run, root = _context()
    if not run or root is None:
        return 0                              # cannot locate the run: stay quiet

    try:
        if _already_filed(root, run, agent):
            return 0                          # silent on success, by design
    except Exception:                                        # noqa: BLE001
        return 0

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PostToolUse",
        "additionalContext": (
            f"ARTIFACT CADENCE — {agent} has returned and nothing from it is "
            f"filed for run {str(run)[:8]}. Store it now, while the payload is "
            f"still in hand:\n"
            f"  python3 {STORE} put --root {root} --run {run} "
            f"--page <page> --section <section> --agent {agent} "
            f"--kind <payload|challenge|report> --file <local.json>\n"
            f"  python3 {DRIVE} push-artifact --client <display_id> "
            f"--file <the path put printed> --root {root}\n"
            f"The store verifies the placement and refuses a body that "
            f"disagrees with its name; the push derives the remote path from "
            f"that name rather than taking one. An artifact that is not filed "
            f"is indistinguishable from work never done, and the next session "
            f"will produce it again from scratch."),
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
