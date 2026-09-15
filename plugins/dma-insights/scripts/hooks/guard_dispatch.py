#!/usr/bin/env python3
"""PreToolUse on Agent: the belt at the dispatch seam.

A dispatch is the most expensive call this system makes — a lane costs
turns, dollars and wall clock before anything it produces can be judged. The
engine already refuses the states below at the write path, but a refusal
that arrives after the lane has run has already spent the lane. This is the
same rule, stopped at the call.

WHAT IT DENIES, and only these — each positively identified, never inferred:

  NO CONNECTOR BASELINE   the run has no `connectors_baseline.json`. Without
                          one nothing can tell "this session never held the
                          connector" from "it held it and lost it", and those
                          call for opposite responses (connector_contract.py).
                          A lane dispatched into that ambiguity researches
                          against a dead tool and reports thin evidence as
                          absence.
  REFUSING INSTALL        `plugin_version.compare()` says STALE / MISSING /
                          INCOMPLETE / DIVERGED / DISABLED / MANIFEST_SPLIT.
                          A 0.9.12 install ran none of the gates the
                          checkout publishes (measured 2026-09-03); a lane
                          dispatched on it produces work no gate will read.
  BUDGET EXHAUSTED        the cost ledger has reached the run's recorded
                          ceiling. A person decides whether this run is worth
                          another budget — that is why the watchdog excludes
                          AT_USD_CEILING from AGENT_ADVANCEABLE.
  ROUNDS EXHAUSTED        the looping stage has spent `max_rounds`.
  CONTAMINATED PROMPT     a `research-p<x>c<y>-producer` dispatched with a
                          prompt that names ANOTHER category's cell outside a
                          `leads_in` / `also_names` block. The ledger refuses
                          the write (engine/scope.py) — but by then the lane
                          has read the cell, searched for it and spent the
                          turns. Contamination is cheapest to stop at the
                          prompt.

WHAT IT ADDS. When the prompt names a category and `engine.brief correlate
--category X` has something to say, the correlation block is appended to the
prompt through `updatedInput` (capped at CORRELATE_CAP chars). Never for a
different category — a run-wide correlation map in sixteen contexts is the
bloat the mechanism exists to avoid — and never when empty, because a lane
that receives "nothing to correlate" has paid to read it.

A non-DMA Agent call is untouched. Everything fails OPEN.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _runctx as ctx                                          # noqa: E402

SKILL = ctx.SKILL

#: Agents this guard governs. Everything else — a general-purpose subagent, a
#: production producer, a person's one-off — passes untouched.
GOVERNED = re.compile(
    r"^(research-|enrichment-|scoring-|report-)|(-challenger)$", re.I)

#: The lanes that SEARCH. Only these are refused for a missing connector
#: baseline: a scorer and a report writer read a finished workbook and call
#: no connector, so the baseline says nothing about whether their work is
#: sound. Every other refusal here — install, budget, rounds — applies to
#: every governed lane, because they are about the run, not about the tool.
SEARCHING = re.compile(r"^(research-|enrichment-)|(-challenger)$", re.I)

#: `research-p1c1-producer` -> the category it owns.
LANE = re.compile(r"^research-(p\d+c\d+)-producer$", re.I)

#: A cell id anywhere in a prompt: P1C1.3, P1C1.3.CU1, P2C4.11.
CELL = re.compile(r"\bP(\d+)C(\d+)(?:\.[0-9A-Z]+)+\b")

#: The two places a prompt is ALLOWED to name another category's cell: the
#: leads this lane was handed, and the cells a source it holds also names.
CARVE_OUT = re.compile(r"(leads[_ -]?in|also[_ -]?names)", re.I)

#: How much correlation a prompt may carry. `brief correlate` has its own,
#: larger ceiling; this is the dispatch seam's.
CORRELATE_CAP = 2000

#: Install states on which research/scoring/report work is REFUSED.
REFUSING_INSTALL_STATES = ("STALE", "MISSING", "INCOMPLETE", "DIVERGED",
                           "DISABLED", "MANIFEST_SPLIT")


# ── the tool call, read ───────────────────────────────────────────────────

def agent_of(ti: dict) -> str:
    a = ti.get("subagent_type") or ti.get("agent") or ti.get("agent_type") or ""
    if not isinstance(a, str):
        return ""
    return a.split(":")[-1].strip()


def prompt_of(ti: dict) -> str:
    for k in ("prompt", "description", "input", "text"):
        v = ti.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


# ── the five refusals ─────────────────────────────────────────────────────

def baseline_known(run) -> bool | None:
    """True/False, or None when the question could not be asked."""
    if run is None:
        return None
    try:
        scripts = str(ctx.PLUGIN / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import connector_contract                              # noqa: PLC0415
        return connector_contract.baseline_path(run.root).is_file()
    except Exception:                                          # noqa: BLE001
        pass
    try:
        return (Path(run.root) / "connectors_baseline.json").is_file()
    except Exception:                                          # noqa: BLE001
        return None


def install_refusal() -> str:
    """The sentence a refusing install deserves, or "" when it is fine."""
    try:
        scripts = str(ctx.PLUGIN / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        import plugin_version                                  # noqa: PLC0415
        v = plugin_version.compare()
    except Exception:                                          # noqa: BLE001
        return ""                      # cannot measure: do not refuse
    if not isinstance(v, dict) or v.get("ok"):
        return ""
    status = str(v.get("status") or "")
    if status not in REFUSING_INSTALL_STATES:
        return ""
    try:
        detail = plugin_version.summary(v)
    except Exception:                                          # noqa: BLE001
        detail = status
    return (f"this container's plugin is {detail}. A lane dispatched on a "
            f"{status} install runs gates the checkout no longer publishes, "
            f"and its output is judged by none of them (measured 2026-09-03: "
            f"a 0.9.12 install ran none of them). Run `python3 "
            f"plugins/dma-insights/scripts/doctor.py --heal` first — the "
            f"engine's own `start` refuses this state too.")


def stray_cells(agent: str, prompt: str) -> list[str]:
    """Cells of ANOTHER category named outside a leads_in/also_names block."""
    m = LANE.match(agent or "")
    if not m or not prompt:
        return []
    mine = m.group(1).upper()
    spans = carve_outs(prompt)
    stray = []
    for hit in CELL.finditer(prompt):
        cat = f"P{hit.group(1)}C{hit.group(2)}".upper()
        if cat == mine:
            continue
        if any(a <= hit.start() < b for a, b in spans):
            continue
        if hit.group(0).upper() not in stray:
            stray.append(hit.group(0).upper())
    return stray


def carve_outs(prompt: str) -> list[tuple[int, int]]:
    """The character spans a leads_in / also_names block covers.

    A block runs from its marker to the end of the bracketed structure that
    follows it, when one does; otherwise to the next blank line. Both shapes
    occur — the packet's JSON field and the markdown section — and a guard
    that knew only one would deny a correctly-formed prompt.
    """
    out = []
    for m in CARVE_OUT.finditer(prompt):
        start = m.start()
        head = prompt[m.end():m.end() + 60]
        opened = None
        for i, ch in enumerate(head):
            if ch in "[{":
                opened = m.end() + i
                break
            if ch not in ' \t\r\n":=-\'':
                break
        end = None
        if opened is not None:
            end = _matching(prompt, opened)
        if end is None:
            nl = prompt.find("\n\n", m.end())
            end = len(prompt) if nl < 0 else nl
        out.append((start, end))
    return out


def _matching(text: str, start: int) -> int | None:
    """The index just past the bracket opened at `start`, or None."""
    pairs = {"[": "]", "{": "}"}
    close = pairs.get(text[start])
    if not close:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == text[start]:
            depth += 1
        elif ch == close:
            depth -= 1
            if depth == 0:
                return i + 1
    return None


# ── the addition ──────────────────────────────────────────────────────────

def category_in(agent: str, prompt: str) -> str:
    """The category this dispatch is FOR: the agent's own name, else the one
    the prompt states. A prompt that names several states none."""
    m = LANE.match(agent or "")
    if m:
        return m.group(1).upper()
    cats = []
    for hit in re.finditer(r"\b(P\d+C\d+)\b", prompt or ""):
        c = hit.group(1).upper()
        if c not in cats:
            cats.append(c)
    return cats[0] if len(cats) == 1 else ""


def correlation(run, category: str) -> str:
    """`engine.brief correlate --category X`'s prompt, or "".

    Called as a SUBPROCESS and treated as advisory: a non-zero exit, a
    subcommand this engine does not carry, a timeout or unreadable output all
    mean "nothing to append". This runs in front of a dispatch; it may not be
    the reason one fails.
    """
    if run is None or not category:
        return ""
    cmd = [sys.executable, "-m", "engine.brief", "correlate",
           "--run", run.run_id, "--root", str(run.root),
           "--category", category, "--json"]
    try:
        # INSIDE the wrapper's own timeout (hooks.json: 30s). A subprocess
        # budget larger than the hook's is a hook the harness kills mid-call,
        # which reads as a broken hook rather than as "nothing to append".
        r = subprocess.run(cmd, cwd=str(SKILL), capture_output=True,
                           text=True, timeout=20)
    except Exception:                                          # noqa: BLE001
        return ""
    if r.returncode != 0 or not (r.stdout or "").strip():
        return ""
    try:
        doc = json.loads(r.stdout)
    except ValueError:
        return ""
    if not isinstance(doc, dict):
        return ""
    text = str(doc.get("prompt") or "").strip()
    if not text:
        return ""
    if len(text) > CORRELATE_CAP:
        text = text[:CORRELATE_CAP].rsplit("\n", 1)[0] + "\n… (truncated)"
    return text


# ── the decision ──────────────────────────────────────────────────────────

def decide(payload: dict) -> dict | None:
    """The hookSpecificOutput to print, or None to stay silent."""
    if str(payload.get("tool_name") or "") not in ("Agent", "Task"):
        return None
    ti = payload.get("tool_input") or {}
    if not isinstance(ti, dict):
        return None
    agent = agent_of(ti)
    if not agent or not GOVERNED.search(agent):
        return None                    # a non-DMA dispatch is not ours
    prompt = prompt_of(ti)

    why = install_refusal()
    if why:
        return _deny(f"dma-insights: {agent} was not dispatched — {why}")

    run = ctx.locate()
    known = baseline_known(run) if SEARCHING.search(agent) else None
    if known is False:
        return _deny(
            f"dma-insights: {agent} was not dispatched — run "
            f"{getattr(run, 'run_id', '?')} has no connectors_baseline.json. "
            f"It is written once, when the preflight passes, and without it "
            f"nothing can say whether this session NEVER held a connector or "
            f"held it and LOST it — which are opposite problems with opposite "
            f"fixes. A lane dispatched into that ambiguity records a dead "
            f"tool's silence as evidence of absence about the client. Run the "
            f"binding preflight (`engine.cli start` / `engine.pipeline run` "
            f"records it), or dispatch with the waiver "
            f"`--allow-unverified-connectors`, which records that the run "
            f"went without one.")

    state = ctx.pipeline_state(run)
    b = ctx.budget(run, state)
    if b["exhausted"]:
        return _deny(
            f"dma-insights: {agent} was not dispatched — the run has spent "
            f"${b['spent']:.2f} of its ${b['ceiling']:.2f} ceiling. Whether "
            f"this run is worth another budget is a person's decision, not a "
            f"lane's: that is why the watchdog keeps AT_USD_CEILING out of "
            f"AGENT_ADVANCEABLE. Raise the ceiling (`--max-usd`), narrow the "
            f"scope, or close the open cells as declared absences.")
    r = ctx.rounds(run, state)
    if r["exhausted"]:
        return _deny(
            f"dma-insights: {agent} was not dispatched — the stage has run "
            f"{r['done']} of {r['max']} rounds. A stage that did not close in "
            f"its rounds needs a reader, not another lane: `engine.brief "
            f"gaps --run {getattr(run, 'run_id', '<RUN>')}` says which cells "
            f"are still open and why.")

    stray = stray_cells(agent, prompt)
    if stray:
        return _deny(
            f"dma-insights: {agent} was not dispatched — its prompt names "
            f"{', '.join(stray[:6])}"
            + (f" and {len(stray) - 6} more" if len(stray) > 6 else "")
            + f", which belong to another category, outside any `leads_in` or "
            f"`also_names` block. The ledger refuses that write too "
            f"(engine/scope.py) — but by then the lane has read the cell, "
            f"searched for it and spent the turns. A cross-category lead "
            f"travels in a `leads_in` block, or through the handback to the "
            f"lane that owns the cell; it is never pasted into a lane's "
            f"prompt as work.")

    # Nothing refuses this dispatch. Record what the substrate looks like
    # NOW, so `harvest_on_return` can say whether the lane left anything
    # behind — the one question a returning lane's own prose cannot answer.
    try:
        ctx.record_dispatch(run, agent)
    except Exception:                                          # noqa: BLE001
        pass

    block = correlation(run, category_in(agent, prompt))
    if block and prompt and block not in prompt:
        return {"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                "dma-insights: the correlation block for this category was "
                "appended — rows another lane already registered against this "
                "lane's still-open cells, each with its `attach` command. "
                "Attaching cites the existing row instead of minting a "
                "duplicate; declining records that the lane judged rather "
                "than ignored."),
            "updatedInput": dict(ti, **{_prompt_key(ti): prompt + "\n\n" + block}),
        }}
    return None


def _prompt_key(ti: dict) -> str:
    for k in ("prompt", "description", "input", "text"):
        if isinstance(ti.get(k), str) and ti[k].strip():
            return k
    return "prompt"


def _deny(reason: str) -> dict:
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except Exception:                                          # noqa: BLE001
        return 0                       # fail OPEN, on purpose
    if os.environ.get("DMA_DISPATCH_GUARD", "").lower() in ("off", "0", "false"):
        return 0
    try:
        out = decide(payload)
    except Exception:                                          # noqa: BLE001
        return 0
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
