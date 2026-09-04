#!/usr/bin/env python3
"""Dispatch one plugin agent from a session that has no agent-launch tool.

Trigger-fired sessions run under the subagent harness: they carry Bash but
no Agent tool, so the routed pipeline (produce -> challenge -> consolidate,
05-lifecycle/routing.md) cannot fan out in-process. Measured 2026-08-20 on
the first live synthesis firing, which correctly refused to write six pages
inline rather than skip the challenge stage.

This script is the sanctioned fallback: it runs the named agent as a
HEADLESS claude CLI session (`claude -p --agent dma-insights:<name>`), which
applies the agent's own front matter — model tier, effort, skills, tool
bans — exactly as the Agent tool would. The child session reaches the DMA
connector natively (static /mcp + header token), so evidence reads, memory
digests and gate checks all work.

What the child does NOT have: the claude.ai enrichment connectors (Clay,
Exa, Tavily, Vibe-Prospecting, Indeed) — those are attached to the Routine
and exist only in the top session. The DISPATCH-MODE preamble (prepended to
every prompt) tells the agent to emit `search_requests` instead of running
or fabricating external searches; the orchestrating session executes them
through its connectors, registers the evidence, and re-invokes.

Usage:
  agent_run.py --agent finding-challenger --prompt-file /tmp/stage.md
  agent_run.py --agent package-vetter < prompt.md
  agent_run.py --list          # the roster this script will accept

Exit code is the child's. Output is the child's stdout, verbatim.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
AGENTS_DIR = HERE.parent / "agents"
PLUGIN_PREFIX = "dma-insights"
DEFAULT_TIMEOUT = 2400

#: One lane per catalogue category, matching `engine.cost.PARALLEL_LANES`.
#: That module divides projected wall clock by 16 and its own docstring says
#: "parallelism is a property of the DISPATCH, not of the work" — and until
#: --batch existed no dispatch this plugin ships could deliver more than one,
#: so the estimate was dividing by a number nothing supplied. The two
#: constants are pinned equal by a test; if they ever drift, the schedule is
#: lying about the wall clock again.
DEFAULT_LANES = 16

PREAMBLE = """DISPATCH MODE — you are running as a headless session, not an
in-process subagent. Two things differ from your usual footing:
1. You carry the DMA Insights connector tools but NOT the claude.ai
   enrichment connectors (Clay, Exa, Tavily, Vibe-Prospecting, Indeed).
   Where your rulebook requires an external search you cannot run, do NOT
   fabricate and do NOT skip silently: add the exact query, its falsifier
   pairing and the facet it serves to a `search_requests` array in your
   final output. The orchestrating session runs them through the real
   connectors, registers what they return, and re-invokes you with the
   evidence ids.
2. Your final output is read by the orchestrating session, not a human —
   return the JSON or report your role defines, nothing else.
3. ROUTE BEFORE YOU PRODUCE. One surface -> that page's per-surface
   producer, then finding-challenger, then page-consolidator. Only the
   surface-producer submits or promotes; if you are not it, do not call
   submit_page_payload or promote_run, and do not re-produce a page to
   repair a field. The rule and both routing tables are
   skills/dma-surface-production/05-lifecycle/routing.md — read it before
   your first tool call if you did not arrive with it.
4. READ MEMORY FIRST. get_memory_digest, then search_findings scoped to
   your own surfaces, before you author anything. End the production by
   handing what happened to the qa-overseer, which is the only agent that
   writes to the findings memory.
5. A VERDICT NAMES A GATE AND A PATH. The path routes (table above); the
   gate id is explained by 05-lifecycle/1-gates.md and, live, by
   explain_gate(gate_id). Do not repair a gate you have not read.

--- TASK ---
"""

# Points 3-5 are here because the SessionStart hook does NOT reach an
# in-process subagent, and the live Routine dispatches every routed stage
# that way (AUD-0004/AUD-0055). The plugin now declares a SubagentStart hook
# that carries the same rule, and this preamble carries it on the headless
# path — two independent carriers, because the measured failure was having
# exactly one and it not reaching the population that needed it. The module
# docstring mentioned routing.md; a docstring is not sent to the child.


def roster() -> dict:
    """name -> path, from the agents tree's front-matter name fields."""
    out = {}
    for p in sorted(AGENTS_DIR.rglob("*.md")):
        if p.name == "README.md":
            continue
        head = p.read_text(encoding="utf-8")[:2000]
        m = re.search(r"^name:\s*(\S+)\s*$", head, re.M)
        if m:
            out[m.group(1)] = p
    return out


#: Below this, a "verdict" is not one. A real stage report names its surface,
#: its claims and its basis; 200 characters is far under any of them and well
#: over an empty string, so it separates "produced nothing" from "produced
#: something terse" without guessing at content.
_MIN_VERDICT = 200

#: Phrases a starved child emits instead of doing the work. Each was measured
#: from a real dispatch (MEM-0111): the child says plainly that it was blocked,
#: and the caller used to discard that and read the empty result as a verdict.
_BLOCKED_MARKERS = (
    "was blocked. For security",
    "haven't granted it yet",
    "requested permissions to",
    "blocked_capabilities",
    "permission denied by hook",
)


# WHAT A DISPATCHED CHILD MAY DO, and why the list is this wide.
#
# Measured 2026-08-20 (MEM-0111, MEM-0112, both BLOCKER): this dispatched
# with `--allowedTools=mcp__plugin_dma-insights_connector` alone, and in
# dontAsk mode everything NOT pre-approved is DENIED rather than asked. So
# the child lost Bash and Read too. One probe returned
# `verified_this_session: []` with three tool families blocked; another
# measured 0 of 4 connector-or-python capabilities available, which is 0
# of the 4 mandatory local checkers runnable and 0 of 34 sections
# producible. An agent with no tools does not report that it had no tools:
# it returns an empty verdict, which reads as "looked and found nothing".
#
# The agent's OWN frontmatter still decides which tools it may use — the
# 64 manifests carry `tools:` and `disallowedTools:` and those are
# enforced independently. This list only removes the permission-prompt
# layer that a scheduled container has nobody to answer.
#: The claude.ai connector namespaces the ROSTER declares. Measured across
#: the 64 agent manifests on 2026-08-30: Exa 60, Google_Drive 63, Tavily 59,
#: Clay 36, Quartr 35, Vibe_Prospecting 6, Indeed 6.
#:
#: They were absent from ALLOWED, and in `--permission-mode dontAsk`
#: everything not pre-approved is DENIED rather than asked. So every
#: enrichment call a dispatched child made was refused silently — the
#: MEM-0111 starvation shape, aimed squarely at enrichment, which is why a
#: live run showed "enrichment connectors not being called by the agents".
#:
#: Granting a namespace here is NOT the same as the connector being bound:
#: binding is the harness's business and a Routine-attached connector may
#: still be absent from a headless child. This removes the permission
#: barrier, which is the half this repository controls. The agent's own
#: front matter still decides which of these it may touch — the 64
#: manifests carry `tools:` and `disallowedTools:` and those are enforced
#: independently, so a producer banned from Clay stays banned.
CONNECTOR_NAMESPACES = (
    "mcp__Clay",
    "mcp__Exa",
    "mcp__Tavily",
    "mcp__Vibe_Prospecting",     # Explorium — the technographic source
    "mcp__Indeed",
    "mcp__Quartr",
    "mcp__Google_Drive",
)

ALLOWED = ",".join([
    "mcp__plugin_dma-insights_connector",   # the connector namespace
    *CONNECTOR_NAMESPACES,                  # enrichment, per the roster
    "Bash", "Read", "Glob", "Grep",         # the four local checkers
    "Write", "Edit",                        # denied per-agent where wrong
    "TodoWrite", "Skill", "WebSearch", "WebFetch",
    # The conductor, the surface-producer and the rectifier fan out through
    # the Agent tool. A headless child that is one of them needs the tool
    # pre-approved or dontAsk denies every dispatch it tries (2026-09-03).
    # AskUserQuestion is deliberately absent: nobody can answer it in a
    # child, and its denial is what routes the conductor to
    # `engine.preflight autobind` rather than a hang.
    "Agent",
])

#: Serialise nothing but the writing. Lanes run concurrently; their output
#: must not interleave mid-line into one unreadable stream.
_PRINT_LOCK = threading.Lock()


def verdict_of(name: str, rc: int, out: str, err: str) -> tuple:
    """(exit_code, note) for one finished dispatch.

    The empty-verdict rule (MEM-0111) is applied HERE rather than inline in
    main, so a lane in a batch is held to exactly the same standard as a
    solo dispatch. A batch that graded its children more leniently than
    `--agent` does would be the same defect one level up: sixteen empty
    verdicts reading as sixteen categories that found nothing.
    """
    blocked = [m for m in _BLOCKED_MARKERS if m in out or m in err]
    if rc == 0 and (len(out.strip()) < _MIN_VERDICT or blocked):
        return 125, (
            f"DISPATCH PRODUCED NOTHING: {name} exited 0 with "
            f"{len(out.strip())} characters of output"
            + (f" and reported {blocked[0]!r}" if blocked else "")
            + ". A stage that could not run is not a stage that found "
              "nothing — refusing rather than passing an empty verdict "
              "upward. Check the child's tool grants and --add-dir scope.")
    return rc, ""


def dispatch(name: str, prompt: str, timeout: int, repo_root: Path,
             allowed: str) -> dict:
    """Run ONE agent to completion. Safe to call from several threads.

    subprocess.run blocks the calling thread and nothing else, so N of these
    in a thread pool are N real concurrent `claude -p` children. The work is
    entirely I/O-bound waiting on those children, which is why threads are
    the right primitive and the GIL is not in the way.
    """
    cmd = ["claude", "-p", "--agent", f"{PLUGIN_PREFIX}:{name}",
           "--permission-mode", "dontAsk",
           "--add-dir", "/root/.dma",
           f"--allowedTools={allowed}", prompt]
    try:
        # DMA_STAGE_GUARD=off in the CHILD. The Stop hook holds a session
        # open while a run has a stage an agent can advance — correct for
        # the driving session, wrong for a lane: a scorer that finishes
        # first sees its three siblings' rows still unscored, is told to
        # dispatch them, and (it now carries `Agent`) re-dispatches scorers
        # already running, writing column D twice. The guard belongs to the
        # conductor, which is the only actor that knows the fan-out.
        r = subprocess.run(cmd, cwd=repo_root, timeout=timeout,
                           capture_output=True, text=True,
                           env={**os.environ, "DMA_STAGE_GUARD": "off"})
    except subprocess.TimeoutExpired:
        return {"agent": name, "code": 124, "stdout": "", "stderr": "",
                "note": f"DISPATCH TIMEOUT: {name} exceeded {timeout}s — "
                        f"treat as a failed stage, never as an empty verdict"}
    except FileNotFoundError:
        return {"agent": name, "code": 127, "stdout": "", "stderr": "",
                "note": "DISPATCH FAILED: the claude CLI is not on PATH in "
                        "this container"}
    out, err = r.stdout or "", r.stderr or ""
    code, note = verdict_of(name, r.returncode, out, err)
    return {"agent": name, "code": code, "stdout": out, "stderr": err,
            "note": note}


# ── LIVE VISIBILITY ──────────────────────────────────────────────────────
#
# THE COMPLAINT, and it is structural rather than a missing print statement
# (owner, 2026-08-31): "I have no visibility onto how the agents are doing
# the research or how they think through challenges. I cannot even see them
# on the background task list."
#
# Both halves are true and they have the same cause. `dispatch` ran the child
# through `subprocess.run(capture_output=True)`, which returns nothing until
# the process exits — so a forty-minute researcher is a black box for forty
# minutes. And because the children are spawned INSIDE one Bash call, the
# harness sees a single task, not sixteen agents: there is nothing for a task
# list to show. Neither is fixed by logging harder at the end.
#
# The claude CLI can emit events as they happen — `--output-format
# stream-json` with `--print` — so the fix is to read that stream line by
# line and land it somewhere a person can watch. Each agent gets its own
# JSONL transcript and a small status file; `agent_run.py watch` renders
# them as a table that updates.
#
# OPT-IN, deliberately. `--stream` selects this path and the default is
# unchanged, because a run is in flight in another session as this lands and
# a rewritten dispatch path that breaks the return contract would cost more
# than the blindness it cures.
#
# EVERY LINE IS LOGGED VERBATIM before anything tries to interpret it. The
# event schema is the CLI's, not ours; a parser that recognises nothing must
# still leave a complete transcript behind, because "the monitor showed
# nothing" is the exact failure being fixed and it must never be caused BY
# the monitor.

def log_dir_for(explicit: str | None = None) -> Path:
    """Where transcripts land: --log-dir, else the run root, else /root/.dma.

    Run-scoped by preference so two runs in one container cannot overwrite
    each other's transcripts, which is the same reason the connector
    baseline is run-scoped.
    """
    if explicit:
        return Path(explicit)
    root = os.environ.get("DMA_RUN_ROOT")
    return (Path(root) / "agent_logs") if root else Path("/root/.dma/agent_logs")


def _summarise(event: dict, st: dict) -> None:
    """Best-effort: pull what is recognisable, ignore what is not.

    Written defensively on purpose. These shapes are the CLI's and can
    change; an unrecognised event increments `events` and nothing else, so a
    schema drift degrades the SUMMARY and never the transcript.
    """
    st["events"] = st.get("events", 0) + 1
    kind = event.get("type")
    if kind == "assistant":
        for block in (event.get("message") or {}).get("content") or []:
            btype = block.get("type")
            if btype == "tool_use":
                st["tools"] = st.get("tools", 0) + 1
                st["last_tool"] = block.get("name") or "?"
                st["doing"] = f"calling {st['last_tool']}"
            elif btype == "text":
                text = " ".join(str(block.get("text") or "").split())
                if text:
                    st["last_text"] = text[-300:]
                    st["doing"] = "writing"
            elif btype == "thinking":
                st["doing"] = "thinking"
    elif kind == "user":
        st["doing"] = "reading a tool result"
    elif kind == "result":
        st["doing"] = "done"
        st["result_subtype"] = event.get("subtype")
        for key in ("total_cost_usd", "num_turns", "duration_ms",
                    "is_error"):
            if key in event:
                st[key] = event[key]


def _final_text(events: list, raw: str) -> str:
    """The agent's answer, reconstructed from the stream.

    THE COMPATIBILITY REQUIREMENT. `verdict_of` and every caller read this
    as the agent's text, so the fallback chain has to end somewhere real:
    the result event's own text, then the assistant text blocks in order,
    then the raw stream. Returning "" on an unfamiliar shape would turn a
    working stage into a silent empty verdict — the defect class this repo
    keeps meeting.
    """
    for e in reversed(events):
        if e.get("type") == "result":
            for key in ("result", "text", "content"):
                v = e.get(key)
                if isinstance(v, str) and v.strip():
                    return v
    blocks = [b.get("text") for e in events if e.get("type") == "assistant"
              for b in (e.get("message") or {}).get("content") or []
              if b.get("type") == "text" and b.get("text")]
    return "\n".join(blocks) if blocks else raw


def dispatch_streaming(name: str, prompt: str, timeout: int, repo_root: Path,
                       allowed: str, logs: Path) -> dict:
    """`dispatch`, with the child's events written as they arrive."""
    import time
    logs.mkdir(parents=True, exist_ok=True)
    jsonl = logs / f"{name}.jsonl"
    status = logs / f"{name}.status.json"
    st = {"agent": name, "state": "running", "doing": "starting",
          "started_at": time.time(), "last_event_at": time.time(),
          "events": 0, "tools": 0}

    def flush_status():
        status.write_text(json.dumps(st, indent=1, sort_keys=True))

    flush_status()
    cmd = ["claude", "-p", "--agent", f"{PLUGIN_PREFIX}:{name}",
           "--permission-mode", "dontAsk",
           "--add-dir", "/root/.dma",
           "--output-format", "stream-json", "--verbose",
           f"--allowedTools={allowed}", prompt]
    events, raw = [], []
    try:
        proc = subprocess.Popen(cmd, cwd=repo_root, text=True, bufsize=1,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                # same reason as `dispatch`: the stage guard
                                # is the conductor's, never a lane's
                                env={**os.environ, "DMA_STAGE_GUARD": "off"})
    except FileNotFoundError:
        st.update(state="failed", doing="claude CLI not on PATH")
        flush_status()
        return {"agent": name, "code": 127, "stdout": "", "stderr": "",
                "note": "DISPATCH FAILED: the claude CLI is not on PATH in "
                        "this container"}

    deadline = time.time() + timeout
    with jsonl.open("w", encoding="utf-8") as fh:
        for line in proc.stdout:
            fh.write(line)          # VERBATIM, before any interpretation
            fh.flush()
            raw.append(line)
            st["last_event_at"] = time.time()
            try:
                ev = json.loads(line)
            except ValueError:
                st["events"] = st.get("events", 0) + 1
            else:
                events.append(ev)
                _summarise(ev, st)
            flush_status()
            if time.time() > deadline:
                proc.kill()
                st.update(state="timeout",
                          doing=f"exceeded {timeout}s")
                flush_status()
                return {"agent": name, "code": 124,
                        "stdout": _final_text(events, "".join(raw)),
                        "stderr": "", "note":
                        f"DISPATCH TIMEOUT: {name} exceeded {timeout}s — "
                        f"treat as a failed stage, never as an empty verdict"}
    err = proc.stderr.read() if proc.stderr else ""
    rc = proc.wait()
    out = _final_text(events, "".join(raw))
    code, note = verdict_of(name, rc, out, err)
    st.update(state="ok" if code == 0 else "failed",
              doing="done", exit_code=code, transcript=str(jsonl))
    flush_status()
    return {"agent": name, "code": code, "stdout": out, "stderr": err,
            "note": note}


def watch(logs: Path, once: bool = False, interval: float = 3.0) -> int:
    """Render every agent's live status as a table.

    Reads the status files rather than the processes, so it works from a
    different shell, a different session, or after the fact.
    """
    import time
    while True:
        rows = []
        for f in sorted(logs.glob("*.status.json")):
            try:
                rows.append(json.loads(f.read_text()))
            except (OSError, ValueError):
                continue
        now = time.time()
        print(f"\n{logs}  —  {len(rows)} agent(s)")
        if not rows:
            print("  nothing yet. Dispatch with --stream to populate this.")
        print(f"  {'agent':34s} {'state':9s} {'for':>7s} {'idle':>6s} "
              f"{'ev':>5s} {'tools':>6s}  doing")
        for r in rows:
            age = now - float(r.get("started_at") or now)
            idle = now - float(r.get("last_event_at") or now)
            print(f"  {r.get('agent','?'):34s} {r.get('state','?'):9s} "
                  f"{age:6.0f}s {idle:5.0f}s {r.get('events',0):5d} "
                  f"{r.get('tools',0):6d}  {str(r.get('doing',''))[:40]}")
            if r.get("last_text"):
                print(f"      last said: {str(r['last_text'])[:100]}")
        if once or all(r.get("state") not in ("running",) for r in rows) \
                and rows:
            return 0
        time.sleep(interval)


def read_batch(path: Path) -> list:
    """[{agent, prompt}] from a batch file, validated before anything runs.

    A batch that is half-wrong should fail before it spends money on the
    half that is right, so every row is checked — agent known, prompt
    non-empty — and the first bad row raises.
    """
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        raise SystemExit(f"{path}: expected a non-empty JSON array of "
                         f"{{agent, prompt_file}} objects")
    names, out = roster(), []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SystemExit(f"{path}[{i}]: not an object")
        name = str(row.get("agent", "")).removeprefix(f"{PLUGIN_PREFIX}:")
        if name not in names:
            raise SystemExit(f"{path}[{i}]: unknown agent {name!r} — a "
                             f"guessed agent name is a route to nothing")
        if row.get("prompt_file"):
            text = Path(row["prompt_file"]).read_text(encoding="utf-8")
        else:
            text = str(row.get("prompt", ""))
        if not text.strip():
            raise SystemExit(f"{path}[{i}]: empty prompt for {name} — a "
                             f"stage with no task is a no-op")
        out.append({"agent": name, "prompt": text})
    return out


def run_batch(rows: list, lanes: int, timeout: int, repo_root: Path,
              allowed: str, out_dir: Path | None,
              logs: Path | None = None) -> int:
    """Run every row, `lanes` at a time. Exit non-zero if ANY lane failed."""
    results, done = [], 0
    # With --stream every lane writes its own live transcript and status, so
    # a person watching `agent_run.py watch` sees sixteen agents working
    # rather than one Bash call that has not returned yet.
    run = ((lambda n, p, t, rr, al: dispatch_streaming(n, p, t, rr, al, logs))
           if logs else dispatch)
    if logs:
        logs.mkdir(parents=True, exist_ok=True)
        print(f"streaming {len(rows)} lane(s) to {logs}\n"
              f"watch them with: python3 {Path(__file__).name} watch "
              f"--log-dir {logs}", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=lanes) as pool:
        futures = {pool.submit(run, r["agent"], r["prompt"], timeout,
                               repo_root, allowed): r["agent"]
                   for r in rows}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            results.append(res)
            done += 1
            # Each lane's transcript goes to its OWN file: sixteen children
            # writing one stream produces a transcript nobody can read, and
            # the orchestrator needs each verdict whole to relay it.
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / f"{res['agent']}.out").write_text(
                    res["stdout"], encoding="utf-8")
            with _PRINT_LOCK:
                state = "ok" if res["code"] == 0 else f"FAILED({res['code']})"
                print(f"[{done}/{len(rows)}] {res['agent']:34s} {state}",
                      flush=True)
                if res["note"]:
                    print(f"    {res['note']}", file=sys.stderr, flush=True)
    failed = [r for r in results if r["code"] != 0]
    summary = {"lanes": lanes, "dispatched": len(rows),
               "ok": len(results) - len(failed),
               "failed": [{"agent": r["agent"], "code": r["code"]}
                          for r in failed]}
    print(json.dumps(summary, indent=2, sort_keys=True))
    if failed:
        print(f"\n{len(failed)} of {len(rows)} lane(s) failed. A batch is "
              f"only as done as its worst lane — re-dispatch those before "
              f"treating the stage as complete.", file=sys.stderr)
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--agent", help="agent name from the plugin roster")
    ap.add_argument("--prompt-file", help="file holding the stage prompt; "
                                          "stdin when omitted")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    ap.add_argument("--no-preamble", action="store_true",
                    help="skip the dispatch-mode preamble (rarely right)")
    ap.add_argument("--list", action="store_true",
                    help="print the accepted roster and exit")
    ap.add_argument("--batch", help="JSON array of {agent, prompt_file} — "
                                    "dispatch them CONCURRENTLY")
    ap.add_argument("--lanes", type=int, default=DEFAULT_LANES,
                    help=f"how many run at once with --batch "
                         f"(default {DEFAULT_LANES})")
    ap.add_argument("--out-dir", help="with --batch: write each lane's "
                                      "stdout to <agent>.out here")
    ap.add_argument("--stream", action="store_true",
                    help="stream each child's events to <log-dir>/"
                         "<agent>.jsonl as they happen, and keep a live "
                         "<agent>.status.json beside it. Without this a "
                         "dispatched agent is silent until it exits")
    ap.add_argument("--log-dir", default=None,
                    help="where --stream and `watch` keep transcripts "
                         "(default: $DMA_RUN_ROOT/agent_logs, else "
                         "/root/.dma/agent_logs)")
    ap.add_argument("cmd", nargs="?", choices=["watch"],
                    help="`watch` renders the live status table and exits "
                         "when every agent has stopped")
    ap.add_argument("--once", action="store_true",
                    help="with watch: print one snapshot and exit")
    a = ap.parse_args(argv)

    if a.cmd == "watch":
        return watch(log_dir_for(a.log_dir), once=a.once)

    names = roster()
    if a.list:
        for n in sorted(names):
            print(n)
        return 0
    if not a.agent and not a.batch:
        ap.error("--agent or --batch is required (or --list)")
    if a.agent and a.batch:
        ap.error("--agent and --batch are mutually exclusive")

    repo_root = HERE.parents[2]
    if a.batch:
        rows = read_batch(Path(a.batch))
        if not a.no_preamble:
            for r in rows:
                r["prompt"] = PREAMBLE + r["prompt"]
        lanes = max(1, min(a.lanes, len(rows)))
        print(f"dispatching {len(rows)} agent(s), {lanes} at a time",
              file=sys.stderr, flush=True)
        return run_batch(rows, lanes, a.timeout, repo_root, ALLOWED,
                         Path(a.out_dir) if a.out_dir else None,
                         log_dir_for(a.log_dir) if a.stream else None)

    name = a.agent.removeprefix(f"{PLUGIN_PREFIX}:")
    if name not in names:
        close = [n for n in names if name in n or n in name]
        raise SystemExit(
            f"unknown agent {a.agent!r} — a guessed agent name is a route "
            f"to nothing (routing.md). "
            + (f"Did you mean: {', '.join(close)}?" if close
               else "agent_run.py --list prints the roster."))

    if a.prompt_file:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = sys.stdin.read()
    if not prompt.strip():
        raise SystemExit("empty prompt — a stage with no task is a no-op")
    if not a.no_preamble:
        prompt = PREAMBLE + prompt

    # THE PACKAGE IS NOT IN THE REPOSITORY. A child's working directory is the
    # checkout, so `/root/.dma/packages/<slug>` is out of scope and every read
    # of it is refused — measured verbatim: "ls in '/root/.dma/packages/...'
    # was blocked. For security, Claude Code may only list files in the
    # allowed working directories for this session: '/home/user/Accelerate'."
    # The package, the bundles and the client memory all live under /root/.dma.
    logs = log_dir_for(a.log_dir) if a.stream else None
    res = (dispatch_streaming(name, prompt, a.timeout, repo_root, ALLOWED, logs)
           if logs else dispatch(name, prompt, a.timeout, repo_root, ALLOWED))
    sys.stdout.write(res["stdout"])
    if res["stderr"]:
        sys.stderr.write(res["stderr"])
    if res["note"]:
        print(f"\n{res['note']}", file=sys.stderr)
    return res["code"]


if __name__ == "__main__":
    sys.exit(main())
