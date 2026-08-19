#!/usr/bin/env python3
"""PostToolUse hook on submit_page_payload / promote_run — the memory nudge.

Appends every blocking reason to a per-install ledger and, when the same
gate id has now refused twice or more across this install's history, tells
the session to stop repairing blind: read `explain_gate`, search the
findings memory, and record the recurrence so the learning loop sees it.

The ledger is plumbing for a nudge, not the findings memory itself — the
connector's `record_finding` / `report_recurrence` remain the system of
record, written by the qa-overseer. This file never calls the network.
"""
import collections
import json
import os
import sys


def _ledger_path() -> str:
    base = os.environ.get("CLAUDE_PLUGIN_DATA") or os.path.join(
        os.path.expanduser("~"), ".claude", "dma-insights")
    os.makedirs(base, exist_ok=True)
    return os.path.join(base, "verdicts.jsonl")


def _reasons(resp) -> list:
    """Blocking reasons, whatever envelope the response arrived in."""
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except ValueError:
            return []
    if isinstance(resp, list):        # MCP content-block list
        out = []
        for block in resp:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                out.extend(_reasons(block["text"]))
        return out
    if not isinstance(resp, dict):
        return []
    found = []
    for key in ("blocking", "blocking_reasons", "reasons"):
        val = resp.get(key)
        if isinstance(val, list):
            for r in val:
                if isinstance(r, dict) and r.get("gate_id"):
                    found.append({"gate_id": r["gate_id"],
                                  "path": r.get("path"),
                                  "message": str(r.get("message"))[:300]})
    return found


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:
        return 0
    reasons = _reasons(event.get("tool_response"))
    if not reasons:
        return 0
    path = _ledger_path()
    run_id = (event.get("tool_input") or {}).get("run_id")
    with open(path, "a") as f:
        for r in reasons:
            f.write(json.dumps({"run_id": run_id, **r}) + "\n")
    counts = collections.Counter()
    try:
        with open(path) as f:
            for line in f:
                try:
                    counts[json.loads(line).get("gate_id")] += 1
                except ValueError:
                    continue
    except OSError:
        return 0
    repeats = sorted(g for g in {r["gate_id"] for r in reasons}
                     if counts.get(g, 0) >= 2)
    if repeats:
        print("dma-insights: gate(s) "
              + ", ".join(repeats)
              + " have now refused more than once in this install. Before "
              "repairing again: call explain_gate for the gate, "
              "search_findings for its defect class, and have the "
              "qa-overseer record_finding or report_recurrence — a repair "
              "the memory never sees will be re-made by the next session.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
