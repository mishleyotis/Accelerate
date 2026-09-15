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

#: Bash commands that can MOVE a run between stages. Deliberately narrow.
#: It used to match `engine.cli` and `engine.assessment` wholesale, so every
#: one of the 50-200 per-cell `engine.cli evidence` writes a researcher makes
#: in a firing re-opened every workbook in the root and re-injected the same
#: paragraph — thousands of workbook loads and thousands of duplicate
#: paragraphs for a state that only changes at a gate boundary (review,
#: 2026-09-04). A write is not a transition; a gate, a stage flip, a verdict,
#: a package and a dispatch are.
STAGE_COMMANDS = re.compile(
    r"agent_run\.py"
    r"|engine\.cli\s+(gate|handoff|validate|report)\b"
    r"|engine\.assessment\s+(open|gate|critique|rollup)\b"
    r"|engine\.narrative\s+(review|state|preconditions)\b"
    r"|engine\.prelim\s+complete\b"
    r"|engine\.(assemble|ship|watchdog)\b"
    r"|engine/(registry|watchdog)\.py"
    r"|ship_page\.py")

MARKER = "stage_advance.json"

#: `engine.pipeline run --step` finishing a research round. It is matched
#: SEPARATELY from STAGE_COMMANDS because a ROUND_COMPLETE carries a `pending`
#: payload nothing else does, and a checklist is the only form a conductor can
#: act on: a round hands back a relay batch nobody dispatched, gap classes
#: nobody correlated, and a budget nobody counted.
ROUND_COMMAND = re.compile(r"engine\.pipeline\s+run\b")

#: Who drains a relay batch. The lanes hold no connector; this actor does.
DRAIN_AGENT = "enrichment-web-specialist"


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
        # MERGE: the announcement key lives in the same marker, and a block
        # that clobbered it would let the next transition command re-inject
        # a paragraph the session has already read.
        try:
            doc = json.loads(p.read_text()) if p.is_file() else {}
            if not isinstance(doc, dict):
                doc = {}
        except (OSError, ValueError):
            doc = {}
        doc.update({"blocked_on": row.get("state"),
                    "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "detail": row.get("detail")})
        tmp.write_text(json.dumps(doc, indent=1))
        os.replace(tmp, p)
    except OSError:
        pass


def _announced_state(row: dict) -> str | None:
    p = _marker_path(row)
    if not p or not p.is_file():
        return None
    try:
        return json.loads(p.read_text()).get("announced")
    except (OSError, ValueError):
        return None


def _record_announcement(row: dict) -> None:
    p = _marker_path(row)
    if not p:
        return
    try:
        doc = json.loads(p.read_text()) if p.is_file() else {}
        if not isinstance(doc, dict):
            doc = {}
    except (OSError, ValueError):
        doc = {}
    doc["announced"] = row.get("state")
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(doc, indent=1))
        os.replace(tmp, p)
    except OSError:
        pass


def _response_text(event: dict) -> str:
    """Whatever text the tool_response carries, flattened."""
    def flat(v):
        if isinstance(v, str):
            return v
        if isinstance(v, dict):
            for k in ("content", "text", "result", "output", "stdout"):
                if k in v:
                    return flat(v[k])
            return json.dumps(v, default=str)
        if isinstance(v, list):
            return "\n".join(flat(i) for i in v if i is not None)
        return "" if v is None else str(v)
    return flat(event.get("tool_response"))


def _pending_from(text: str) -> dict | None:
    """The `pending` payload a `--json` round printed, if it printed one.

    WITHOUT `--json` the driver prints one line and the payload never reaches
    the transcript, so this returns None and the caller RECOMPUTES from the
    substrate. Both paths must work: the conductor's own command is the one
    thing this hook cannot choose.
    """
    if not text or '"pending"' not in text:
        return None
    start = text.find("{")
    while start >= 0:
        try:
            doc = json.loads(text[start:])
        except ValueError:
            start = text.find("{", start + 1)
            continue
        if isinstance(doc, dict) and isinstance(doc.get("pending"), dict):
            return doc["pending"]
        return None
    return None


def _ctx():
    here = str(HERE)
    if here not in sys.path:
        sys.path.insert(0, here)
    import _runctx                                       # noqa: PLC0415
    return _runctx


def _recomputed_pending() -> dict:
    """`pending`, read from the run when the driver did not print it."""
    out = {"relay_batches": [], "open_categories": [], "stalled": [],
           "budget": {}, "rounds_remaining": None, "gaps": None}
    try:
        ctx = _ctx()
        run = ctx.locate()
    except Exception:                                      # noqa: BLE001
        return out
    if run is None:
        return out
    state = ctx.pipeline_state(run)
    out["relay_batches"] = [str(p) for p in (state.get("relay_batches") or [])]
    b = ctx.budget(run, state)
    out["budget"] = {"spent": b["spent"], "ceiling": b["ceiling"],
                     "remaining": b["remaining"]}
    out["rounds_remaining"] = ctx.rounds(run, state)["remaining"]
    try:
        brief, = ctx.engine("brief")
        out["gaps"] = brief.gaps(run.open(), run)
    except Exception:                                      # noqa: BLE001
        out["gaps"] = None
    return out


def _gap_lines(gaps: dict) -> list[str]:
    """One line per gap class per category, each with the command that
    closes it. A gap named without its command is a gap nobody acts on."""
    lines = []
    cats = (gaps or {}).get("categories") or {}
    for cat, row in sorted(cats.items()):
        if not isinstance(row, dict):
            continue
        if row.get("undeclared_empty"):
            n = len(row["undeclared_empty"])
            lines.append(
                f"  [ ] {cat}: {n} cell(s) EMPTY AND UNDECLARED — these are "
                f"what the floors gate refuses. Close each with evidence or "
                f"`engine.cli absence --subcap <CELL>`; re-dispatch with "
                f"`engine.brief dispatch --category {cat}`.")
        if row.get("proposals_unattached"):
            lines.append(
                f"  [ ] {cat}: {row['proposals_unattached']} cross-category "
                f"row(s) proposed and neither attached nor declined — "
                f"`engine.brief correlate --category {cat}` prints them with "
                f"their attach commands.")
        if row.get("unserviced_requests"):
            lines.append(
                f"  [ ] {cat}: {row['unserviced_requests']} relay request(s) "
                f"unserviced — they need the actor that holds the connectors, "
                f"not another research lane.")
        if row.get("challenge_deferred"):
            lines.append(
                f"  [ ] {cat}: {len(row['challenge_deferred'])} synthesis(es) "
                f"unchallenged — dispatch `research-challenger`.")
        if row.get("stalled_rounds"):
            lines.append(
                f"  [ ] {cat}: {row['stalled_rounds']} round(s) changed "
                f"nothing. A third attempt at the same prompt buys the same "
                f"nothing — read the handback before re-dispatching.")
    return lines


def _memory_backup_line(run, state: dict) -> str:
    """What the round's memory backup actually did.

    The notebooks are the only part of the run tree a dead container loses
    outright, and `_backup_memory` NEVER fails a round — which is right, and
    is exactly why a backup that did not run has to be said out loud rather
    than inferred from a round that looks clean.
    """
    rec = state.get("memory_backup")
    if not isinstance(rec, dict):
        return ("MEMORY BACKUP — NOT_RUN: this round recorded no backup at "
                "all. The notebooks under 03_memory/ are the only part of the "
                "run a dead container loses outright. Run `python3 -m "
                "engine.memory backup --run <RUN> --root <ROOT>`, or say why "
                "it cannot run (a run started --no-push does not talk to "
                "Drive).")
    status = str(rec.get("status") or "")
    head = status.split(":", 1)[0].strip().upper()
    if head in ("RESOLVED", "SKIPPED_UNCHANGED", "UNCHANGED"):
        return ""
    if head == "PARTIAL":
        return (f"MEMORY BACKUP — PARTIAL at {rec.get('at')}: {status}. Some "
                f"notebooks reached Drive and some did not; re-run `engine."
                f"memory backup` and read which.")
    return (f"MEMORY BACKUP — {head or 'NOT_RUN'} at {rec.get('at')}: "
            f"{status}. The round carried on, by design — a failed backup "
            f"must not fail a round — so nothing else will tell you.")


def round_complete(event: dict) -> dict | None:
    """The checklist a ROUND_COMPLETE earns: every outstanding thing with the
    command that closes it, and the budget that limits how many more there
    can be."""
    text = _response_text(event)
    if "ROUND_COMPLETE" not in text:
        return None
    pending = _pending_from(text)
    recomputed = False
    if pending is None:
        pending = _recomputed_pending()
        recomputed = True

    lines = ["ROUND COMPLETE — what the round handed back, and what closes "
             "each of it:"]
    batches = [str(b) for b in (pending.get("relay_batches") or [])]
    for b in batches:
        lines.append(
            f"  [ ] RELAY BATCH {b} — serviced by `{DRAIN_AGENT}`, the actor "
            f"that holds the connectors:\n"
            f"        python3 {AGENT_RUN} --agent {DRAIN_AGENT} "
            f"--prompt-file {b} --stream")
    lines += _gap_lines(pending.get("gaps") or {})
    for cat in (pending.get("open_categories") or []):
        lines.append(
            f"  [ ] {cat}: floors gate is not PASS — `engine.cli gate "
            f"--category {cat} --require-synthesis` says what it refuses.")
    for cat in (pending.get("stalled") or []):
        lines.append(f"  [ ] {cat}: STALLED — the last round changed nothing.")

    b = pending.get("budget") or {}
    if b.get("ceiling") is not None:
        lines.append(
            f"  BUDGET: ${b.get('spent') or 0:.2f} spent of "
            f"${b['ceiling']:.2f}; ${b.get('remaining') or 0:.2f} remains.")
    rr = pending.get("rounds_remaining")
    if rr is not None:
        lines.append(f"  ROUNDS: {rr} remaining at this stage.")
    if len(lines) == 1:
        lines.append("  nothing outstanding in the pending payload.")

    try:
        ctx = _ctx()
        run = ctx.locate()
        note = _memory_backup_line(run, ctx.pipeline_state(run)) if run else ""
    except Exception:                                      # noqa: BLE001
        note = ""
    if note:
        lines += ["", note]
    if recomputed:
        lines += ["", "(The driver did not print its `pending` payload — add "
                      "`--json` to `engine.pipeline run` for it. The list "
                      "above was recomputed from the run's own substrate: the "
                      "relay queue, pipeline_state.json and `engine.brief "
                      "gaps`.)"]
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n".join(lines)}}


def on_post_tool_use(event: dict) -> dict | None:
    tool = str(event.get("tool_name") or "")
    ti = event.get("tool_input") or {}
    if tool == "Bash":
        cmd = ti.get("command") if isinstance(ti, dict) else ""
        if not isinstance(cmd, str):
            return None
        if ROUND_COMMAND.search(cmd):
            # A round that handed back is a DIFFERENT announcement from a
            # stage that flipped: it carries a checklist, not a state.
            out = round_complete(event)
            if out:
                return out
        if not STAGE_COMMANDS.search(cmd):
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
    texts = []
    for r in rows:
        if r.get("state") not in watchdog.ACTIONABLE and r.get("state") != "SHIPPED":
            continue
        # Say it ONCE per state per run. The same paragraph after every
        # transition command is context a session pays for and stops
        # reading; the announcement is only news when the state changed.
        if _announced_state(r) == r.get("state"):
            continue
        _record_announcement(r)
        texts.append(next_step(r))
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
    # The watchdog says every run is between states. `engine.brief gaps` reads
    # a finer grain: a relay batch nobody serviced, or a category whose cells
    # are open, are work an agent can still do — and a session that stops on
    # them leaves the run looking finished.
    for row in rows:
        why = _gaps_blocker(row)
        if not why:
            continue
        if _blocked_before(row):
            continue
        _record_block(row)
        return {"decision": "block", "reason": why}
    return None


def _gaps_blocker(row: dict) -> str:
    """The next concrete dispatch, when `engine.brief gaps` says one is owed
    and the run can still afford it. "" in every other case.

    THE THREE WAYS A STOP IS ALLOWED, and they are the point of this function:
      * the blocker is a PERSON's — BLOCKED_NO_CONNECTOR (somebody must
        attach it) or AT_USD_CEILING (somebody must decide this run is worth
        another budget). Neither is advanced by another lane, and the
        watchdog already keeps both out of AGENT_ADVANCEABLE.
      * the budget is spent, or the rounds are. A stage that did not close in
        its rounds needs a reader.
      * there is simply nothing open.
    """
    if row.get("state") in ("BLOCKED_NO_CONNECTOR", "AT_USD_CEILING",
                            "HALTED", "UNREADABLE", "MISSING_LOCALLY"):
        return ""
    try:
        ctx = _ctx()
        run = ctx.locate()
    except Exception:                                      # noqa: BLE001
        return ""
    if run is None or str(getattr(run, "run_id", "")) != str(row.get("run_id")):
        return ""
    state = ctx.pipeline_state(run)
    budget = ctx.budget(run, state)
    rounds_ = ctx.rounds(run, state)
    if budget["exhausted"] or rounds_["exhausted"]:
        return ""                          # a person's call, not a lane's
    try:
        brief, = ctx.engine("brief")
        gaps = brief.gaps(run.open(), run)
    except Exception:                                      # noqa: BLE001
        return ""
    batches = [str(b) for b in (state.get("relay_batches") or [])]
    unserviced = []
    try:
        relay, = ctx.engine("relay")
        unserviced = [r for r in relay.requests(run).values()
                      if r.get("status") == "OPEN"]
    except Exception:                                      # noqa: BLE001
        unserviced = []

    if unserviced and batches:
        return (
            f"STOP HELD — run {run.run_id} has {len(unserviced)} relay "
            f"request(s) nobody has serviced, and the batch that carries them "
            f"is written. They are queries the lanes could not answer with "
            f"the tools they hold; only the actor holding the connectors can. "
            f"The next dispatch:\n\n"
            f"  python3 {AGENT_RUN} --agent {DRAIN_AGENT} --prompt-file "
            f"{batches[-1]} --stream\n\n"
            f"${budget['remaining'] if budget['remaining'] is not None else '?'} "
            f"of budget and {rounds_['remaining']} round(s) remain, so this is "
            f"affordable. If it is not work this session should do, say in one "
            f"line why and stop.")

    lines = _gap_lines(gaps)
    if not lines:
        return ""
    cats = [c for c, rowg in sorted((gaps.get("categories") or {}).items())
            if isinstance(rowg, dict) and (rowg.get("open_cells")
                                           or rowg.get("undeclared_empty"))]
    if not cats:
        return ""
    return (
        f"STOP HELD — run {run.run_id} still has categories an agent can "
        f"advance: {', '.join(cats[:8])}"
        + (f" and {len(cats) - 8} more" if len(cats) > 8 else "")
        + f". ${budget['remaining'] if budget['remaining'] is not None else '?'} "
          f"of budget and {rounds_['remaining']} round(s) remain.\n\n"
        + "\n".join(lines[:8])
        + f"\n\nThe next dispatch:\n  python3 -m engine.brief dispatch --run "
          f"{run.run_id} --root {run.root} --category {cats[0]}\n"
          f"then `python3 {AGENT_RUN} --agent research-{cats[0].lower()}"
          f"-producer --prompt-file <that packet> --stream`.\n\n"
          f"If this is not work this session should do — a person must attach "
          f"a connector, a person must raise the budget — say so in one line "
          f"and stop.")


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
