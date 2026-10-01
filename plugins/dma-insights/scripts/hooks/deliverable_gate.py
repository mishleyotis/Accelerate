#!/usr/bin/env python3
"""The template and gold-standard gates, run by a hook and not by prose.

    PostToolUse on Bash   — a deliverable was just written (`engine.cli
                            report`, `engine.cli strip`, `engine.assemble
                            package|checkpoint`, `engine.techscan render`):
                            run the gates over what the run now holds and
                            record each verdict in the workbook's Gate_Log,
                            which is what the run manifest's `gates` reads.
    PreToolUse on Bash    — a package is about to leave the machine
                            (`drive_fetch.py push-package|push-final|
                            push-artifact`, `engine.assemble package --push`):
                            deny while any recorded GS/TEMPLATE verdict is
                            not PASS, or while none was ever recorded.
    Stop                  — the run is at PACKAGE and a verdict is not PASS:
                            refuse to stop ONCE, with the fix list.

WHY THIS EXISTS. Measured 28-09-2026 (QA audit F-M08-013): `engine.template`
(drift, binding, report-drift) and `engine.gold_standard` (27 GS ids) existed
as tools, and no hook under scripts/hooks called either; enforcement was the
sentence "run the gate on your own output" in the agents' manifests. A gate
that runs when an agent remembers to run it is a gate that runs on the good
days. The verdicts are written to the Gate_Log (one owner — `assemble._gates`
reads it into `run_manifest.gates`), never to the manifest directly.

Fail-open on anything unreadable, like every guard in this plugin: a hook
that errors on its own bug is the one failure a guard may never have. The
gate itself fails CLOSED: a package with a recorded FAIL, or with no
recorded verdict, does not leave the machine.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _runctx  # noqa: E402

#: Commands that write a client deliverable.
DELIVERABLE_WRITE = re.compile(
    r"engine\.cli\s+(?:report|strip)\b|engine\.assemble\s+(?:package|checkpoint)\b"
    r"|engine\.techscan\s+render\b|engine\.reports\b")
#: Commands that carry a deliverable off the machine.
PUSH = re.compile(
    r"drive_fetch\.py[\"']?\s+push-(?:package|final|artifact)\b"
    r"|engine\.assemble\s+package\b[^\n]*--push\b")
#: Working files that ride push-package but are not client deliverables.
#: Measured 2026-09-30 (SWBC): run-assessment step 3 says "push the answered
#: preflight to the client folder" at a point where no gold verdict can exist
#: yet, so the gate denied the command's own instruction every time.
#: `run_manifest.json` is written by `assemble.open_folder` at run start for
#: the same reason: an IN_PROGRESS folder must be findable before anything
#: has been judged. Every deliverable (workbook, reports, scan, evidence
#: index) is still gated.
NON_DELIVERABLE = ("preflight.json", "run_manifest.json")
# A shell operator glued to the token is not part of the name: measured
# 2026-10-01 (Northwest Bank) `--name preflight.json; echo …` captured
# `preflight.json;`, missed the exemption and denied run-assessment step 3.
_PUSH_NAME = re.compile(r"--name[ =][\"']?([^\s\"';&|)`]+)")
_PUSH_FILE = re.compile(r"--file[ =][\"']?([^\s\"';&|)`]+)")
RUN_FLAG = re.compile(r"--run[ =]([\w.:-]+)")
ROOT_FLAG = re.compile(r"--root[ =](\S+)")

GATE_GS = "GS"
GATE_TEMPLATE = "TEMPLATE"
MARKER = "deliverable_gate.block"


def _run_from(cmd: str):
    """The run the command names, else the session's."""
    try:
        (runstate,) = _runctx.engine("runstate")
    except Exception:                                          # noqa: BLE001
        return None
    m = RUN_FLAG.search(cmd or "")
    if m:
        r = ROOT_FLAG.search(cmd or "")
        try:
            run = runstate.locate(m.group(1), Path(r.group(1)) if r else None)
            if run.workbook_path.exists():
                return run
        except (ValueError, OSError):
            pass
    return _runctx.locate()


def gate_verdicts(wb) -> dict:
    """The LATEST verdict per GS/TEMPLATE scope in the Gate_Log."""
    out: dict = {}
    for r in wb.rows("Gate_Log"):
        g = str(r.get("Gate") or "").strip()
        if g not in (GATE_GS, GATE_TEMPLATE):
            continue
        key = f"{g}:{r.get('Scope') or ''}"
        out[key] = {"verdict": str(r.get("Verdict") or ""),
                    "detail": str(r.get("Detail") or ""),
                    "at": str(r.get("Timestamp") or "")}
    return out


def run_gates(run) -> list[dict]:
    """Every gate over what the run holds now, recorded in the Gate_Log."""
    (GS, template, ledger, assemble) = _runctx.engine(
        "gold_standard", "template", "ledger", "assemble")
    wb = run.open()
    results = []

    def record(scope: str, findings, *, gate: str = GATE_GS, fix: str = ""):
        verdict = "PASS" if not findings else "FAIL"
        detail = ("PASS — 0 findings" if not findings else
                  f"{len(findings)} finding(s): " + "; ".join(str(f) for f in findings[:4])
                  + (f"; fix: {fix}" if fix else ""))
        ledger.append_gate(wb, gate=gate, scope=scope, verdict=verdict,
                           detail=detail[:900], blocking=True)
        results.append({"gate": gate, "scope": scope, "verdict": verdict,
                        "findings": len(findings), "detail": detail[:300]})

    # the template binding: the run must be bound to the pins this checkout ships
    b = template.binding_state(wb)
    record("binding", [] if (b.get("bound") and b.get("current")) else
           [b.get("fix") or "not bound"], gate=GATE_TEMPLATE,
           fix="engine.template bind --run <R> --root <ROOT>")
    # the workbook, always present
    record("workbook", GS.workbook_findings(run.workbook_path),
           fix="repair at the source (the workbook), never in the rendered file")
    subcaps = GS._subcap_count(run.workbook_path)
    for key, pattern, kind in assemble.DELIVERABLES:
        if key == "scoring_workbook":
            continue
        hits = sorted(run.deliverables.glob(pattern))
        if not hits:
            continue                       # not written yet: no verdict to record
        if key == "technographic_scan":
            record("scan", GS.scan_findings(run.deliverables),
                   fix="engine.techscan render after the layers are looked at")
        else:
            gs_kind = "research" if key == "research_report" else "assessment"
            record(f"report:{gs_kind}",
                   GS.report_findings(hits[-1], kind=gs_kind, subcaps=subcaps),
                   fix=f"repair the section, then engine.cli report --report "
                       f"{'client_research' if gs_kind == 'research' else 'assessment'}")
    return results


def failing(verdicts: dict) -> list[str]:
    return [f"{k}: {v['verdict']} — {v['detail'][:160]}"
            for k, v in sorted(verdicts.items()) if v["verdict"] != "PASS"]


def push_verdict(cmd: str) -> tuple[str, str | None]:
    """("pass" | "deny" | "not_a_push", reason). The gate fails CLOSED: a
    push with no run in hand, an unreadable workbook or no recorded verdict
    is a deny with the way out, never a silent allow."""
    if not PUSH.search(cmd or ""):
        return "not_a_push", None
    # Exactly one push, a push-package, and both its --file and --name are
    # working files. A `cd … &&` prefix is ordinary and changes nothing here.
    if len(PUSH.findall(cmd)) == 1 and re.search(r"push-package\b", cmd):
        names = [m.group(1) for m in (_PUSH_FILE.search(cmd),
                                      _PUSH_NAME.search(cmd)) if m]
        if _PUSH_FILE.search(cmd) and all(Path(n).name in NON_DELIVERABLE
                                          for n in names):
            return "pass", None
    run = _run_from(cmd)
    if run is None:
        return "deny", (
            "dma-insights deliverable gate: no run is in hand to judge this push by "
            "— name it (`--run <R> --root <ROOT>` in the command, or DMA_RUN_ID / "
            "DMA_RUN_ROOT in the session) so the recorded gold-standard verdicts can "
            "be read. A package nothing has judged does not leave the machine. "
            "(QA audit F-M08-013 / F-K02-024, 28-09-2026)")
    try:
        wb = run.open()
        verdicts = gate_verdicts(wb)
    except Exception as exc:                                   # noqa: BLE001
        return "deny", (f"dma-insights deliverable gate: run {run.run_id}'s workbook "
                        f"could not be read ({type(exc).__name__}), so no verdict can "
                        f"be established; NOT RUN is not a pass.")
    gs = {k: v for k, v in verdicts.items() if k.startswith(GATE_GS + ":")}
    if not gs:
        return "deny", (
            f"dma-insights deliverable gate: no gold-standard verdict is recorded "
            f"for run {run.run_id}, so nothing has established that this package "
            f"meets the Golden 1 gate. The gate runs when a deliverable is written "
            f"(engine.cli report / engine.assemble package); run "
            f"`python3 -m engine.gold_standard package <folder>` and repair each "
            f"finding at its source, then push. (QA audit F-M08-013, 28-09-2026)")
    bad = failing(verdicts)
    if bad:
        return "deny", (
            f"dma-insights deliverable gate: run {run.run_id} carries a verdict that "
            f"is not PASS — " + " | ".join(bad[:4])
            + ". A package with a recorded failure does not leave the machine; "
              "repair at the source, re-render, and the gate re-runs on the write. "
              "(QA audit F-M08-013, 28-09-2026)")
    return "pass", None


def decide_push(cmd: str) -> str | None:
    """The denial reason for a push, or None."""
    state, why = push_verdict(cmd)
    return why if state == "deny" else None


def on_post_tool_use(event: dict) -> dict | None:
    ti = event.get("tool_input") or {}
    cmd = ti.get("command") if isinstance(ti, dict) else ""
    if str(event.get("tool_name") or "") != "Bash" or not isinstance(cmd, str):
        return None
    if not DELIVERABLE_WRITE.search(cmd):
        return None
    run = _run_from(cmd)
    if run is None:
        return None
    try:
        results = run_gates(run)
    except Exception as exc:                                   # noqa: BLE001
        return {"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": (f"dma-insights deliverable gate: could not run on "
                                  f"{run.run_id} ({type(exc).__name__}: {str(exc)[:160]}); "
                                  f"NOT RUN is not a pass — run `python3 -m "
                                  f"engine.gold_standard package <folder>` yourself.")}}
    lines = [f"dma-insights deliverable gate on {run.run_id} (recorded in Gate_Log, "
             f"read by run_manifest.gates):"]
    for r in results:
        lines.append(f"  {r['gate']}:{r['scope']} {r['verdict']}"
                     + (f" — {r['detail']}" if r["verdict"] != "PASS" else ""))
    if any(r["verdict"] != "PASS" for r in results):
        lines.append("A package does not push and the session does not stop at PACKAGE "
                     "while a verdict is not PASS. Repair each finding at its source.")
    return {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                   "additionalContext": "\n".join(lines)}}


def on_pre_tool_use(event: dict) -> dict | None:
    ti = event.get("tool_input") or {}
    cmd = ti.get("command") if isinstance(ti, dict) else ""
    if str(event.get("tool_name") or "") != "Bash" or not isinstance(cmd, str):
        return None
    reason = decide_push(cmd)
    if not reason:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _at_package(run) -> bool:
    st = _runctx.pipeline_state(run)
    stage = str(st.get("stage") or st.get("current_stage") or "").upper()
    if stage == "PACKAGE":
        return True
    try:
        (assemble,) = _runctx.engine("assemble")
        wb = run.open()
        md = wb.metadata()
        folder = assemble.default_folder_root(run) / f"{md.get('entity_name')} - DMA"
        man = folder / "run_manifest.json"
        if man.is_file():
            doc = json.loads(man.read_text(encoding="utf-8"))
            return str(doc.get("stage") or "").upper() == "PACKAGE"
    except Exception:                                          # noqa: BLE001
        pass
    return False


def on_stop(event: dict) -> dict | None:
    if os.environ.get("DMA_STAGE_GUARD", "").lower() in ("off", "0", "false"):
        return None
    if event.get("stop_hook_active"):
        return None
    run = _runctx.locate()
    if run is None or not _at_package(run):
        return None
    try:
        verdicts = gate_verdicts(run.open())
    except Exception:                                          # noqa: BLE001
        return None
    bad = failing(verdicts)
    if not bad and any(k.startswith(GATE_GS + ":") for k in verdicts):
        return None
    if not bad:
        bad = ["GS: no gold-standard verdict recorded for this package"]
    marker = Path(run.qa_dir) / MARKER
    fingerprint = json.dumps(sorted(bad))
    try:
        if marker.is_file() and marker.read_text(encoding="utf-8") == fingerprint:
            return None                     # nudged once already on this state
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(fingerprint, encoding="utf-8")
    except OSError:
        return None
    return {"decision": "block",
            "reason": (f"dma-insights deliverable gate: run {run.run_id} is at PACKAGE "
                       f"with a verdict that is not PASS — " + " | ".join(bad[:4])
                       + ". Repair at the source and re-render (the gate re-runs on the "
                         "write), or state in one line why it cannot be repaired here, "
                         "then stop. (QA audit F-M08-013, 28-09-2026)")}


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                          # noqa: BLE001
        return 0
    if not isinstance(event, dict):
        return 0
    hook = str(event.get("hook_event_name") or event.get("hookEventName") or "")
    out = None
    if hook == "PostToolUse":
        out = on_post_tool_use(event)
    elif hook == "PreToolUse" or (not hook and event.get("tool_name")):
        out = on_pre_tool_use(event)
    elif hook == "Stop":
        out = on_stop(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                          # noqa: BLE001
        sys.exit(0)                                            # fail open, silent
