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
import json
import os
import sys

try:
    import fcntl
except ImportError:                       # non-POSIX: degrade to no lock
    fcntl = None

# The ledger is bounded plumbing, not history: the nudge needs "has this
# gate refused twice in this install", never the full record. Counts live
# in a sidecar read/written under the same lock, so the check is O(1) in
# history; the JSONL keeps only the newest MAX_LEDGER_LINES rows for a
# human reading it, rotated in place.
MAX_LEDGER_LINES = 2000


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
    counts_path = path + ".counts.json"
    run_id = (event.get("tool_input") or {}).get("run_id")
    # One newline-terminated write per EVENT (not per reason), under an
    # exclusive lock: concurrent per-page producers fire PostToolUse
    # together, and interleaved partial appends corrupt JSONL.
    record = "".join(json.dumps({"run_id": run_id, **r}) + "\n"
                     for r in reasons)
    try:
        with open(path, "a+") as f:
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_EX)
            f.write(record)
            f.flush()
            # counts sidecar: read-modify-write inside the same lock
            try:
                with open(counts_path) as cf:
                    counts = json.load(cf)
                if not isinstance(counts, dict):
                    counts = {}
            except (OSError, ValueError):
                counts = {}
            for r in reasons:
                counts[r["gate_id"]] = int(counts.get(r["gate_id"], 0)) + 1
            tmp = counts_path + ".tmp"
            with open(tmp, "w") as cf:
                json.dump(counts, cf)
            os.replace(tmp, counts_path)
            # bound the human-readable ledger: rotate in place past the cap
            f.seek(0)
            lines = f.readlines()
            if len(lines) > MAX_LEDGER_LINES:
                keep = lines[-MAX_LEDGER_LINES:]
                tmp = path + ".tmp"
                with open(tmp, "w") as lf:
                    lf.writelines(keep)
                os.replace(tmp, path)
            if fcntl is not None:
                fcntl.flock(f, fcntl.LOCK_UN)
    except OSError:
        return 0
    repeats = sorted(g for g in {r["gate_id"] for r in reasons}
                     if int(counts.get(g, 0)) >= 2)
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
