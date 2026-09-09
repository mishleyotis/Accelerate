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

What the child MAY NOT have: the claude.ai enrichment connectors (Clay,
Exa, Tavily, Vibe-Prospecting, Indeed). This script pre-approves every one
of their namespaces (`ALLOWED`) and the agent manifests declare them, but
binding is the harness's business and a headless child can still find them
absent. So the DISPATCH-MODE preamble (prepended to every prompt) tells the
agent to TRY the connector first and, where it is refused or absent, to emit
`search_requests` instead of running WebSearch in its place or fabricating.
`engine.relay` (MEM-0333) harvests those requests from the lane transcripts,
dispatches `enrichment-web-specialist` lanes over them, reconciles what
returned against the Search_Log, and the ENRICHMENT gate says, per
category, whether any connector was asked at all.

LANES ARE PROCESS GROUPS (owner, 2026-09-07: a paused driver died and its
lanes' children kept running — "50 processes still running, load still
climbing"). Every child is spawned as its own session leader, its pid and
pgid are written to its status file, a timeout kills the whole group, and
SIGTERM/SIGINT/SIGHUP to this process kill every live group before it
exits. `agent_run.py reap` kills the groups a dead driver left behind, and
the lane count is capped by what the host can actually hold.

Usage:
  agent_run.py --agent finding-challenger --prompt-file /tmp/stage.md
  agent_run.py --agent package-vetter < prompt.md
  agent_run.py --list          # the roster this script will accept
  agent_run.py --batch batch.json --lanes 16 --stream [--no-lane-cap]
  agent_run.py reap [--log-dir DIR] [--dry-run] [--force]   # kill orphaned lane groups
  agent_run.py capacity [--lanes N]                         # what the host can hold

Exit code is the child's. Output is the child's stdout, verbatim.
"""
from __future__ import annotations

import argparse
import atexit
import concurrent.futures
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
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

#: The executable a lane runs. Overridable so a test can stand in a script
#: that behaves like a child (prints, spawns, hangs) without a model.
CLAUDE_BIN = os.environ.get("DMA_CLAUDE_BIN", "claude")


def _mcp_config_path() -> str | None:
    """The parent session's own MCP config file, if one is on disk.

    Measured 2026-09-09 (SWBC run DMA-2026-SWBC-001): a headless `claude -p`
    child spawned with no `--mcp-config` cannot see mcp__Exa, mcp__Tavily,
    mcp__Clay, mcp__Vibe_Prospecting or mcp__Indeed AT ALL — not refused,
    absent from its tool registry, `--allowedTools` naming them or not. A
    controlled probe (same host, same command shape, `--mcp-config` added)
    connected mcp__Exa on the first call. Across 16 category lanes and one
    dedicated enrichment lane, this cost a real run 0 enrichment_searches on
    every category (`engine.relay enrichment`) despite ~1,900 logged
    searches — the `search_requests` relay (MEM-0333) is the correct
    fallback for a genuinely absent connector, but it was catching total
    absence, not the rare case it was built for.

    The platform writes this session's config to a fixed, discoverable path
    (`/tmp/mcp-config-<session-id>.json`) once at session start; there is at
    most one such file per container. Passing it through does not widen
    what a lane may call — each agent's own `tools:`/`disallowedTools:`
    front matter still gates that, exactly as `ALLOWED` above only removes
    the permission-PROMPT layer, not the grant. Returns None (silent no-op,
    same behaviour as before this fix) where no such file exists, e.g. a
    local dev container with no platform-injected connectors — the
    search_requests relay remains correct there."""
    import glob
    hits = sorted(glob.glob("/tmp/mcp-config-*.json"),
                  key=lambda p: Path(p).stat().st_mtime, reverse=True)
    return hits[0] if hits else None


#: Resolved once per process; every lane this driver spawns shares it.
MCP_CONFIG = _mcp_config_path()

#: WHAT ONE LANE COSTS THE HOST — an estimate, stated as one. A `claude -p`
#: child is a Node process holding a model context; measured RSS on the
#: 2026-09-07 runs sat in the hundreds of MB and climbed with the transcript.
#: 600 MB per lane plus 1 GB of headroom is the planning figure; set
#: DMA_LANE_MEM_MB when a measurement on your host says otherwise, or pass
#: --no-lane-cap to run the requested count regardless. The cap is REPORTED
#: in the batch summary either way, so a schedule that assumed sixteen lanes
#: on a four-lane box says so instead of running late silently.
LANE_MEM_MB = 600
LANE_MEM_HEADROOM_MB = 1024
LANES_PER_CPU = 2      # lanes mostly wait on a model; two per core is generous

PREAMBLE = """DISPATCH MODE — you are running as a headless session, not an
in-process subagent. Two things differ from your usual footing:
1. You carry the DMA Insights connector tools and, where your manifest
   declares them, the claude.ai enrichment connectors (Clay, Exa, Tavily,
   Vibe-Prospecting, Indeed) — but a headless child is NOT guaranteed the
   binding a top session has. Where your rulebook requires an enrichment
   search, TRY the connector first and log it with the tool that ran it
   (`--tool exa|tavily|clay`). If the call is refused or the tool is absent,
   do NOT run it through WebSearch instead, do NOT fabricate and do NOT skip
   silently: add it to a `search_requests` array in your final output —
   JSON objects {"query", "falsifier", "facet", "subcap", "tool", "proves"}.
   The driver (`engine.relay`) harvests them, runs them through a
   connector-bearing lane, registers what returns, and re-dispatches you
   with the evidence in your brief.
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
    cmd = [CLAUDE_BIN, "-p", "--agent", f"{PLUGIN_PREFIX}:{name}",
           "--permission-mode", "dontAsk",
           "--add-dir", "/root/.dma",
           *(["--mcp-config", MCP_CONFIG] if MCP_CONFIG else []),
           f"--allowedTools={allowed}", prompt]
    try:
        # start_new_session: the child leads its own process group, so a
        # signal aimed at THIS process never reaches it by accident and the
        # streaming path can kill child and grandchildren together. On this
        # path subprocess.run still kills only the direct child at timeout;
        # the driver dispatches with --stream, where the group is killed.
        # DMA_STAGE_GUARD=off in the CHILD. The Stop hook holds a session
        # open while a run has a stage an agent can advance — correct for
        # the driving session, wrong for a lane: a scorer that finishes
        # first sees its three siblings' rows still unscored, is told to
        # dispatch them, and (it now carries `Agent`) re-dispatches scorers
        # already running, writing column D twice. The guard belongs to the
        # conductor, which is the only actor that knows the fan-out.
        r = subprocess.run(cmd, cwd=repo_root, timeout=timeout,
                           capture_output=True, text=True,
                           start_new_session=True,
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


# ── PROCESS GROUPS, AND WHO KILLS THEM ───────────────────────────────────
#
# Measured 2026-09-07 (owner): four paused drivers were killed; their lanes'
# `claude` children — and the children those had spawned — kept running.
# Fifty processes, load at 115 and climbing, until every subprocess was
# force-cleared by hand and the surviving drivers redispatched. Three
# causes, three fixes:
#   1. a child spawned into the parent's group is not killed with the
#      parent → every lane is its own session leader (start_new_session),
#      its pgid recorded, and killed AS A GROUP;
#   2. `for line in proc.stdout` only wakes when a line arrives, so a silent
#      child never met its deadline → reader threads feed a queue and the
#      loop wakes on a clock;
#   3. nothing reaped anything when this process was told to stop → the
#      signal handlers below kill every live group first, and `reap` finds
#      the groups a dead driver left behind from the status files.

_LIVE: dict[int, "subprocess.Popen"] = {}
_LIVE_LOCK = threading.Lock()


def _track(proc) -> None:
    with _LIVE_LOCK:
        _LIVE[proc.pid] = proc


def _untrack(proc) -> None:
    with _LIVE_LOCK:
        _LIVE.pop(proc.pid, None)


def _group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def kill_group(pgid: int, *, proc=None, grace_s: float = 5.0) -> str:
    """SIGTERM the whole group, wait `grace_s`, SIGKILL what is left.

    `proc` is the direct child when we hold it: it is reaped with wait() so a
    zombie does not keep the group "alive" past its grandchildren. Returns
    gone / terminated / killed."""
    if not _group_alive(pgid):
        if proc is not None:
            try:
                proc.wait(timeout=1)
            except Exception:                                   # noqa: BLE001
                pass
        return "gone"
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return "gone"
    deadline = time.monotonic() + grace_s
    if proc is not None:
        try:
            proc.wait(timeout=grace_s)
        except Exception:                                       # noqa: BLE001
            pass
    while time.monotonic() < deadline:
        if not _group_alive(pgid):
            return "terminated"
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        return "terminated"
    if proc is not None:
        try:
            proc.wait(timeout=2)
        except Exception:                                       # noqa: BLE001
            pass
    return "killed"


def reap_live(reason: str = "exit") -> list:
    """Kill every lane this process still holds. Called by the signal
    handlers and at exit; idempotent."""
    with _LIVE_LOCK:
        procs = list(_LIVE.values())
    out = []
    for proc in procs:
        out.append({"pid": proc.pid, "result": kill_group(proc.pid, proc=proc)})
        _untrack(proc)
    if out:
        print(f"agent_run: {reason}: stopped {len(out)} lane group(s): "
              + ", ".join(f"{o['pid']}={o['result']}" for o in out),
              file=sys.stderr, flush=True)
    return out


_REAP_SIGNALS = tuple(s for s in ("SIGTERM", "SIGINT", "SIGHUP") if hasattr(signal, s))


def install_reaper():
    """Route SIGTERM/SIGINT/SIGHUP through reap_live, then exit with the
    conventional 128+signum. Returns the handlers to restore, or None off the
    main thread (where Python refuses to install any)."""
    if threading.current_thread() is not threading.main_thread():
        return None
    prev = {}

    def handler(signum, _frame):
        reap_live(f"signal {signum}")
        raise SystemExit(128 + int(signum))
    for name in _REAP_SIGNALS:
        sig = getattr(signal, name)
        try:
            prev[sig] = signal.signal(sig, handler)
        except (ValueError, OSError):
            pass
    atexit.register(reap_live)
    return prev


def restore_handlers(prev) -> None:
    for sig, h in (prev or {}).items():
        try:
            signal.signal(sig, h if h is not None else signal.SIG_DFL)
        except (ValueError, OSError, TypeError):
            pass


def reap(logs: Path, *, dry_run: bool = False, force: bool = False) -> list:
    """Kill the lane groups a dead driver left behind, from the status files.

    A status file still `running` whose recorded driver pid is gone names an
    orphaned group (the owner's 2026-09-07 shape); `--force` also takes the
    groups of drivers that are alive. Each reaped file is rewritten to say
    what happened, so the table never shows a killed lane as running."""
    out = []
    for f in sorted(Path(logs).glob("*.status.json")):
        try:
            st = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if st.get("state") != "running" or not st.get("pgid"):
            continue
        pgid = int(st["pgid"])
        driver = st.get("driver_pid")
        driver_alive = bool(driver) and _pid_alive(int(driver))
        alive = _group_alive(pgid)
        row = {"agent": st.get("label") or st.get("agent"), "pgid": pgid,
               "driver_pid": driver, "driver_alive": driver_alive, "group_alive": alive}
        if not alive:
            row["result"] = "gone"
            st.update(state="gone", doing="group already exited; status was stale")
        elif driver_alive and not force:
            row["result"] = "skipped: its driver is alive (use --force)"
        elif dry_run:
            row["result"] = "would kill"
        else:
            row["result"] = kill_group(pgid)
            st.update(state="reaped", doing=f"group {row['result']} by agent_run reap",
                      reaped_at=time.time())
        if not dry_run and row["result"] not in ("would kill",) and "skipped" not in row["result"]:
            try:
                f.write_text(json.dumps(st, indent=1, sort_keys=True))
            except OSError:
                pass
        out.append(row)
    return out


# ── HOST CAPACITY ────────────────────────────────────────────────────────

def _mem_available_mb() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError, IndexError):
        return None
    return None


_MEASURE = object()     # "read it from the host"; None means "unknown"


def host_capacity(requested: int, *, mem_mb=_MEASURE, cpus=_MEASURE,
                  per_lane_mb=_MEASURE) -> dict:
    """How many lanes this host can hold, and why. Never below one; never
    above what was asked. Every input is in the result so the cap is a
    measurement a person can dispute, not a number that appeared. Pass
    `mem_mb=None` for a host whose memory could not be read: the request
    stands and the result says the memory bound was not measured."""
    cpus = (os.cpu_count() or 1) if cpus is _MEASURE else (cpus or 1)
    mem = _mem_available_mb() if mem_mb is _MEASURE else mem_mb
    per = (int(os.environ.get("DMA_LANE_MEM_MB") or LANE_MEM_MB)
           if per_lane_mb is _MEASURE else int(per_lane_mb))
    by_cpu = max(1, int(cpus) * LANES_PER_CPU)
    by_mem = max(1, (int(mem) - LANE_MEM_HEADROOM_MB) // max(1, per)) if mem is not None else None
    lanes = max(1, min(int(requested), by_cpu, by_mem if by_mem is not None else requested))
    binding = ("requested" if lanes == requested else
               "memory" if by_mem is not None and lanes == by_mem else "cpu")
    return {"requested": int(requested), "lanes": lanes, "capped": lanes < int(requested),
            "binding": binding, "cpus": cpus, "lanes_per_cpu": LANES_PER_CPU,
            "mem_available_mb": mem, "per_lane_mb": per, "headroom_mb": LANE_MEM_HEADROOM_MB,
            "by_cpu": by_cpu, "by_mem": by_mem,
            "note": ("per-lane memory is an estimate (DMA_LANE_MEM_MB overrides; "
                     "--no-lane-cap runs the requested count)")}


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


def _pump(stream, kind: str, q: "queue.Queue") -> None:
    """Feed one pipe into the queue, line by line, then a None sentinel. A
    daemon thread: if the process is killed mid-line the read ends with it."""
    try:
        for line in stream:
            q.put((kind, line))
    except (OSError, ValueError):
        pass
    finally:
        q.put((kind, None))


def dispatch_streaming(name: str, prompt: str, timeout: int, repo_root: Path,
                       allowed: str, logs: Path, *, label: str | None = None) -> dict:
    """`dispatch`, with the child's events written as they arrive.

    The child is its own process group; the deadline is kept on a clock
    rather than on the next line; stdout and stderr are drained by threads so
    a chatty stderr cannot deadlock the pipe; and pid/pgid/driver_pid are in
    the status file so `reap` can find the group after this process is gone.
    `label` names the transcript when several lanes run the same agent."""
    label = label or name
    logs.mkdir(parents=True, exist_ok=True)
    jsonl = logs / f"{label}.jsonl"
    status = logs / f"{label}.status.json"
    st = {"agent": name, "label": label, "state": "running", "doing": "starting",
          "started_at": time.time(), "last_event_at": time.time(),
          "events": 0, "tools": 0, "driver_pid": os.getpid()}

    def flush_status():
        try:
            status.write_text(json.dumps(st, indent=1, sort_keys=True))
        except OSError:
            pass

    flush_status()
    cmd = [CLAUDE_BIN, "-p", "--agent", f"{PLUGIN_PREFIX}:{name}",
           "--permission-mode", "dontAsk",
           "--add-dir", "/root/.dma",
           "--output-format", "stream-json", "--verbose",
           *(["--mcp-config", MCP_CONFIG] if MCP_CONFIG else []),
           f"--allowedTools={allowed}", prompt]
    events, raw, err_parts = [], [], []
    try:
        proc = subprocess.Popen(cmd, cwd=repo_root, text=True, bufsize=1,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                start_new_session=True,
                                # same reason as `dispatch`: the stage guard
                                # is the conductor's, never a lane's
                                env={**os.environ, "DMA_STAGE_GUARD": "off"})
    except FileNotFoundError:
        st.update(state="failed", doing="claude CLI not on PATH")
        flush_status()
        return {"agent": name, "label": label, "code": 127, "stdout": "", "stderr": "",
                "note": "DISPATCH FAILED: the claude CLI is not on PATH in "
                        "this container"}
    _track(proc)
    st.update(pid=proc.pid, pgid=proc.pid)     # a session leader's pgid is its pid
    flush_status()

    q: "queue.Queue" = queue.Queue()
    threading.Thread(target=_pump, args=(proc.stdout, "out", q), daemon=True).start()
    threading.Thread(target=_pump, args=(proc.stderr, "err", q), daemon=True).start()
    deadline = time.monotonic() + timeout
    open_ends, timed_out = 2, False
    try:
        with jsonl.open("w", encoding="utf-8") as fh:
            while open_ends:
                try:
                    kind, line = q.get(timeout=0.5)
                except queue.Empty:
                    if time.monotonic() > deadline:
                        timed_out = True
                        break
                    continue
                if line is None:
                    open_ends -= 1
                    continue
                if kind == "err":
                    err_parts.append(line)
                    continue
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
                if time.monotonic() > deadline:
                    timed_out = True
                    break
        if timed_out:
            result = kill_group(proc.pid, proc=proc)
            st.update(state="timeout", doing=f"exceeded {timeout}s; group {result}")
            flush_status()
            return {"agent": name, "label": label, "code": 124,
                    "stdout": _final_text(events, "".join(raw)),
                    "stderr": "".join(err_parts), "note":
                    f"DISPATCH TIMEOUT: {name} exceeded {timeout}s (process group "
                    f"{result}) — treat as a failed stage, never as an empty verdict"}
        rc = proc.wait()
    except BaseException:
        # Interrupted (a signal handler raised, or anything else): the lane
        # must not outlive the dispatch that owns it.
        kill_group(proc.pid, proc=proc)
        st.update(state="failed", doing="dispatch interrupted; group killed")
        flush_status()
        raise
    finally:
        _untrack(proc)
    err = "".join(err_parts)
    out = _final_text(events, "".join(raw))
    code, note = verdict_of(name, rc, out, err)
    st.update(state="ok" if code == 0 else "failed",
              doing="done", exit_code=code, transcript=str(jsonl))
    flush_status()
    # The child's own usage rides up to the batch summary and the cost
    # ledger (`--record-run`): turns and USD from the CLI's result event.
    return {"agent": name, "label": label, "code": code, "stdout": out, "stderr": err,
            "note": note, "turns": st.get("num_turns"),
            "usd": st.get("total_cost_usd")}


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
        # A label names the lane's transcript and .out when several rows run
        # the SAME agent (the relay dispatches one enrichment-web-specialist
        # per category); without it sixteen lanes overwrite one file.
        label = str(row.get("label") or name).strip()
        if not _LABEL_OK.match(label):
            raise SystemExit(f"{path}[{i}]: label {label!r} may only carry "
                             f"letters, digits, . _ @ : -")
        out.append({"agent": name, "prompt": text, "label": label})
    return out


_LABEL_OK = re.compile(r"^[A-Za-z0-9_.@:\-]{1,120}$")


# ── RETRIES, TIMINGS, THE COST LEDGER ────────────────────────────────────
#
# Owner issue 9 (2026-09-03): "the assessment takes more than six hours" and
# nothing recorded where the hours went; a lane that timed out or came back
# empty was re-dispatched by hand, once somebody noticed. Two codes and ONLY
# two are retryable: 124 (the child exceeded the timeout) and 125 (it exited
# 0 having produced nothing — MEM-0111's starvation shape). A child that
# failed on its own terms (any other code) is not retried, because a retry
# of a real failure is the same failure at twice the price.
RETRYABLE = (124, 125)
DEFAULT_RETRY_BACKOFF_S = 5.0
_ATTEMPT_NOTE = ("\n\nATTEMPT {k} OF {n}: the previous attempt {why}. Do not "
                 "restart the stage from nothing — read the run's state first "
                 "(`engine.cli orient`, your notebook, the handback) and "
                 "continue from where the work stands.\n")


def _why(code: int) -> str:
    return ("timed out" if code == 124 else
            "produced nothing (exited 0 with an empty verdict)" if code == 125
            else f"failed with exit {code}")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def dispatch_with_retries(run_fn, name: str, prompt: str, timeout: int,
                          repo_root: Path, allowed: str, *, retries: int = 0,
                          backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
                          sleep=time.sleep, label: str | None = None) -> dict:
    """`run_fn` until it returns a non-retryable code or the retries are
    spent. The result carries `attempts`, `started_at`, `ended_at`,
    `elapsed_s` and the per-attempt codes, so the batch summary — and the
    cost ledger — can say what a lane actually cost in wall clock."""
    started = _now()
    t0 = time.monotonic()
    codes = []
    res = None
    extra = {"label": label} if label and label != name else {}
    total = max(0, int(retries)) + 1
    for k in range(1, total + 1):
        p = prompt
        if k > 1:
            p = prompt + _ATTEMPT_NOTE.format(k=k, n=total, why=_why(codes[-1]))
        res = run_fn(name, p, timeout, repo_root, allowed, **extra)
        codes.append(res["code"])
        if res["code"] not in RETRYABLE or k == total:
            break
        sleep(backoff_s * k)
    res = dict(res)
    res.setdefault("label", label or name)
    res.update({"attempts": len(codes), "attempt_codes": codes,
                "started_at": started, "ended_at": _now(),
                "elapsed_s": round(time.monotonic() - t0, 1)})
    if len(codes) > 1 and res["code"] in RETRYABLE:
        res["note"] = (res.get("note") or "") + (
            f" — {len(codes)} attempts, all {_why(res['code'])}; this lane "
            f"needs a person or a bigger timeout, not a fourth try.")
    return res


def _record_cost(record: dict, summary: dict, repo_root: Path) -> dict:
    """Shell `engine.cost record` for the batch, so the run's own ledger
    carries the stage's wall clock, lane count and attempts. Separate from
    the dispatch seam on purpose: a test that fakes `subprocess.run` for
    the children does not fake this."""
    eng = repo_root / "plugins" / "dma-insights" / "skills" / "dma-research"
    cmd = [sys.executable, "-m", "engine.cost", "record",
           "--run", str(record["run"]), "--stage", str(record["stage"]),
           "--elapsed-s", str(summary["elapsed_s"]),
           "--started-at", summary["started_at"], "--ended-at", summary["ended_at"],
           "--lanes", str(summary["lanes"]),
           "--attempts", str(sum(l["attempts"] for l in summary["lanes_detail"])),
           "--note", f"agent_run batch: {summary['ok']}/{summary['dispatched']} ok"]
    if record.get("root"):
        cmd += ["--root", str(record["root"])]
    if summary.get("turns"):
        cmd += ["--turns", str(summary["turns"])]
    if summary.get("usd") is not None:
        cmd += ["--usd", str(summary["usd"])]
    r = subprocess.run(cmd, cwd=eng, capture_output=True, text=True)
    return {"recorded": r.returncode == 0,
            "detail": (r.stdout if r.returncode == 0 else r.stderr).strip()[-400:]}


def run_batch(rows: list, lanes: int, timeout: int, repo_root: Path,
              allowed: str, out_dir: Path | None,
              logs: Path | None = None, *, retries: int = 0,
              backoff_s: float = DEFAULT_RETRY_BACKOFF_S,
              timing_out: Path | None = None,
              record: dict | None = None,
              capacity: dict | None = None) -> int:
    """Run every row, `lanes` at a time. Exit non-zero if ANY lane failed."""
    results, done = [], 0
    batch_started, batch_t0 = _now(), time.monotonic()
    # With --stream every lane writes its own live transcript and status, so
    # a person watching `agent_run.py watch` sees sixteen agents working
    # rather than one Bash call that has not returned yet.
    base = ((lambda n, p, t, rr, al, label=None: dispatch_streaming(
                n, p, t, rr, al, logs, label=label))
            if logs else (lambda n, p, t, rr, al, label=None: dispatch(n, p, t, rr, al)))
    run = (lambda n, p, t, rr, al, label=None: dispatch_with_retries(
        base, n, p, t, rr, al, retries=retries, backoff_s=backoff_s, label=label))
    if logs:
        logs.mkdir(parents=True, exist_ok=True)
        print(f"streaming {len(rows)} lane(s) to {logs}\n"
              f"watch them with: python3 {Path(__file__).name} watch "
              f"--log-dir {logs}", flush=True)
    # Stop means stop: a signal to this process kills every live lane group
    # before it exits (installed on the main thread only; restored after).
    prev_handlers = install_reaper()
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=lanes) as pool:
            futures = {pool.submit(run, r["agent"], r["prompt"], timeout,
                                   repo_root, allowed, r.get("label")): r["agent"]
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
                    (out_dir / f"{res.get('label') or res['agent']}.out").write_text(
                        res["stdout"], encoding="utf-8")
                with _PRINT_LOCK:
                    state = "ok" if res["code"] == 0 else f"FAILED({res['code']})"
                    extra = (f"  {res.get('elapsed_s', 0):.0f}s"
                             + (f", {res['attempts']} attempts"
                                if res.get("attempts", 1) > 1 else ""))
                    print(f"[{done}/{len(rows)}] {res.get('label') or res['agent']:34s} "
                          f"{state}{extra}", flush=True)
                    if res["note"]:
                        print(f"    {res['note']}", file=sys.stderr, flush=True)
    finally:
        restore_handlers(prev_handlers)
    failed = [r for r in results if r["code"] != 0]
    # Streamed children carry their usage (turns, cost) on the status file;
    # sum what is there and say nothing where it is not.
    turns = sum(int(r.get("turns") or 0) for r in results)
    usd_vals = [r.get("usd") for r in results if r.get("usd") is not None]
    summary = {"lanes": lanes, "dispatched": len(rows),
               "ok": len(results) - len(failed),
               "lane_cap": capacity,
               "failed": [{"agent": r["agent"], "label": r.get("label") or r["agent"],
                           "code": r["code"],
                           "attempts": r.get("attempts", 1)} for r in failed],
               "started_at": batch_started, "ended_at": _now(),
               "elapsed_s": round(time.monotonic() - batch_t0, 1),
               "retries_allowed": retries,
               "turns": turns or None,
               "usd": round(sum(usd_vals), 4) if usd_vals else None,
               "lanes_detail": sorted(
                   [{"agent": r["agent"], "label": r.get("label") or r["agent"],
                     "code": r["code"],
                     "attempts": r.get("attempts", 1),
                     "attempt_codes": r.get("attempt_codes", [r["code"]]),
                     "started_at": r.get("started_at"),
                     "ended_at": r.get("ended_at"),
                     "elapsed_s": r.get("elapsed_s")} for r in results],
                   key=lambda d: d["agent"])}
    if timing_out:
        timing_out.parent.mkdir(parents=True, exist_ok=True)
        timing_out.write_text(json.dumps(summary, indent=2, sort_keys=True))
    if record:
        summary["cost_record"] = _record_cost(record, summary, repo_root)
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
    ap.add_argument("--retries", type=int, default=0,
                    help="re-dispatch a lane that timed out (124) or produced "
                         "nothing (125) up to this many times; a lane that "
                         "failed on its own terms is never retried")
    ap.add_argument("--retry-backoff-s", type=float, default=DEFAULT_RETRY_BACKOFF_S,
                    help=f"seconds x attempt between retries "
                         f"(default {DEFAULT_RETRY_BACKOFF_S:g})")
    ap.add_argument("--timing-out", help="with --batch: write the summary "
                                         "(per-lane started/ended/elapsed/"
                                         "attempts) to this JSON file")
    ap.add_argument("--record-run", help="with --batch: append the batch's "
                                         "wall clock to this run's cost ledger "
                                         "(`engine.cost record`)")
    ap.add_argument("--record-root", help="the run root for --record-run")
    ap.add_argument("--record-stage", help="the stage name for --record-run "
                                           "(RESEARCH, SCORING, REPORTS, …)")
    ap.add_argument("--stream", action="store_true",
                    help="stream each child's events to <log-dir>/"
                         "<agent>.jsonl as they happen, and keep a live "
                         "<agent>.status.json beside it. Without this a "
                         "dispatched agent is silent until it exits")
    ap.add_argument("--log-dir", default=None,
                    help="where --stream and `watch` keep transcripts "
                         "(default: $DMA_RUN_ROOT/agent_logs, else "
                         "/root/.dma/agent_logs)")
    ap.add_argument("cmd", nargs="?", choices=["watch", "reap", "capacity"],
                    help="`watch` renders the live status table and exits "
                         "when every agent has stopped; `reap` kills the lane "
                         "process groups a dead driver left running; "
                         "`capacity` prints what this host can hold")
    ap.add_argument("--once", action="store_true",
                    help="with watch: print one snapshot and exit")
    ap.add_argument("--dry-run", action="store_true",
                    help="with reap: say what would be killed, kill nothing")
    ap.add_argument("--force", action="store_true",
                    help="with reap: also kill groups whose driver is still alive")
    ap.add_argument("--no-lane-cap", action="store_true",
                    help="with --batch: run the requested lane count even when "
                         "the host's memory/CPU say fewer")
    a = ap.parse_args(argv)

    if a.cmd == "watch":
        return watch(log_dir_for(a.log_dir), once=a.once)
    if a.cmd == "reap":
        rows = reap(log_dir_for(a.log_dir), dry_run=a.dry_run, force=a.force)
        for r in rows:
            print(f"{str(r['agent']):40s} pgid {r['pgid']:<8} driver "
                  f"{'alive' if r['driver_alive'] else 'dead ':5s}  {r['result']}")
        if not rows:
            print(f"nothing running under {log_dir_for(a.log_dir)}")
        return 0
    if a.cmd == "capacity":
        print(json.dumps(host_capacity(a.lanes), indent=2))
        return 0

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
        cap = host_capacity(lanes)
        if cap["capped"] and not a.no_lane_cap:
            print(f"lane cap: {cap['requested']} requested, running {cap['lanes']} "
                  f"(bound by {cap['binding']}: {cap['cpus']} cpu, "
                  f"{cap['mem_available_mb']} MB available, {cap['per_lane_mb']} MB/lane "
                  f"estimate; --no-lane-cap overrides)", file=sys.stderr, flush=True)
            lanes = cap["lanes"]
        elif cap["capped"]:
            cap["overridden"] = True
        if a.record_run and not a.record_stage:
            ap.error("--record-run needs --record-stage")
        print(f"dispatching {len(rows)} agent(s), {lanes} at a time"
              + (f", up to {a.retries} retr{'y' if a.retries == 1 else 'ies'} "
                 f"per lane" if a.retries else ""),
              file=sys.stderr, flush=True)
        return run_batch(rows, lanes, a.timeout, repo_root, ALLOWED,
                         Path(a.out_dir) if a.out_dir else None,
                         log_dir_for(a.log_dir) if a.stream else None,
                         retries=a.retries, backoff_s=a.retry_backoff_s,
                         timing_out=Path(a.timing_out) if a.timing_out else None,
                         record=({"run": a.record_run, "root": a.record_root,
                                  "stage": a.record_stage}
                                 if a.record_run else None),
                         capacity=cap)

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
    base = ((lambda n, p, t, rr, al, **kw: dispatch_streaming(n, p, t, rr, al, logs, **kw))
            if logs else dispatch)
    res = dispatch_with_retries(base, name, prompt, a.timeout, repo_root, ALLOWED,
                                retries=a.retries, backoff_s=a.retry_backoff_s)
    sys.stdout.write(res["stdout"])
    if res["stderr"]:
        sys.stderr.write(res["stderr"])
    if res["note"]:
        print(f"\n{res['note']}", file=sys.stderr)
    return res["code"]


if __name__ == "__main__":
    sys.exit(main())
