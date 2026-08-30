#!/usr/bin/env python3
"""Is every scheduled Routine actually doing its job?

    python3 scripts/routine_health.py --file triggers.json [--strict] [--json]
    <list_triggers output> | python3 scripts/routine_health.py --strict

WHY THIS EXISTS. The watchdog watches RUNS — it sweeps the connector and the
research registry and finds work that stopped. Nothing watched the ROUTINES
themselves, and on 2026-08-30 a `list_triggers` call found two of the six
unhealthy with nobody aware of either:

    dma-rectification-weekly   FAILED 2026-08-24, and had stayed failed
                               through six days and no alert. Cause was not a
                               defect at all: "You've hit your individual
                               spend limit … your session limit resets 3pm
                               (UTC)" — a five_hour rate limit, rejected.
    dma-refresh-drift-daily    ABANDONED, fired 2026-08-29T15:05 and still
                               BLOCKED thirteen hours later on a permission
                               prompt for `mcp__Google-Drive__search_files`.

The second one is the more instructive. The plugin's own auto-approve hook
allows that call — verified by running the hook against that exact tool name,
which returns `allow` for every server spelling, because it matches the
SUFFIX and the server segment of a claude.ai connector is an opaque
per-attachment UUID. So the hook did not decide, which means the hook did not
RUN: a stale or partial install, whose `hooks.json` fallback deliberately
allows the call through with a systemMessage rather than blocking it. And a
session cannot heal that itself — `plugin_version.py --heal` fixes the DISK,
while "agents, skills and hooks bind once at session start and do not
reload". A scheduled session has nobody to answer a prompt, so it waits
forever.

Neither failure is visible from inside a run. Both are visible in one field
of `list_triggers`, which is what this reads.

WHAT IT DOES NOT DO. It does not call the API — a script cannot, and a
routine's own session already can. Pipe it `list_triggers` output. That keeps
this runnable in CI over a recorded fixture, and by a session over live
state, with the same code deciding both.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone

#: A last-run status that means the Routine did its job.
HEALTHY = "ROUTINE_RUN_STATUS_SUCCEEDED"

#: What each unhealthy status USUALLY means here, so a reader gets a next
#: move rather than a status word. Measured causes, not guesses — each is a
#: class this project has actually met.
DIAGNOSIS = {
    "ROUTINE_RUN_STATUS_FAILED": (
        "the firing ended in an error. Read the session's post_turn_summary "
        "before assuming a code defect: the one measured instance was a "
        "SPEND LIMIT ('You've hit your individual spend limit', five_hour "
        "rate limit, rejected), which no change to this repo can fix — it is "
        "raised at claude.ai/settings/usage."),
    "ROUTINE_RUN_STATUS_ABANDONED": (
        "the firing started and never finished. The measured instance was "
        "BLOCKED on a permission prompt for a connector read, which a "
        "scheduled session has nobody to answer. Check the session's "
        "`pending_action`: if it names an MCP tool the plugin's "
        "autoapprove_connector hook allows, the hook did not RUN — a stale "
        "or partial install, and the session cannot heal it because hooks "
        "bind once at session start."),
    "ROUTINE_RUN_STATUS_PENDING": (
        "PENDING for longer than two of its own intervals. A firing in "
        "flight is normal and reads IN_FLIGHT; this one has outlived the "
        "schedule that started it, which is an ABANDONED nothing has "
        "reclassified."),
}

#: How many of a Routine's own intervals a PENDING firing may occupy before
#: it stops being "in flight". Two, because one is the firing itself and the
#: second is the slack a long synthesis legitimately needs.
PENDING_INTERVALS = 2

#: A Routine with no recorded run at all. Not a fault on its own — a
#: self-binding Routine wakes its own session and records none — but worth
#: distinguishing from one that ran and succeeded.
NO_RUN = ("no run recorded. A Routine bound to a persistent session records "
          "none by design; one that creates a fresh session per firing "
          "should have a run by now if its cron has come round.")


def _rows(doc) -> list:
    """The triggers list, whatever shape the caller pasted."""
    if isinstance(doc, list):
        return doc
    if isinstance(doc, dict):
        for key in ("triggers", "data", "items", "results"):
            if isinstance(doc.get(key), list):
                return doc[key]
        for v in doc.values():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                return v
    raise SystemExit("could not find a list of triggers in that input")


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def assess(row: dict, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    name = row.get("name") or "?"
    last = row.get("last_run") or {}
    status = last.get("status") or ""
    out = {
        "name": name, "id": row.get("id"),
        "cron": row.get("cron_expression") or row.get("run_once_at"),
        "enabled": bool(row.get("enabled")),
        "last_status": status or None,
        "last_fired_at": last.get("fired_at"),
        "session_id": last.get("session_id"),
        "next_run_at": row.get("next_run_at"),
    }
    if not out["enabled"]:
        reason = (row.get("ended_reason") or row.get("suspension_reason")
                  or "")
        out["verdict"] = "DISABLED"
        out["detail"] = (
            f"disabled — {reason}" if reason else
            "disabled with no ended_reason or suspension_reason, which means "
            "a person paused it. A paused Routine is not a broken one, but "
            "it is also not doing anything.")
        return out
    if not status:
        out["verdict"] = "NO_RUN"
        out["detail"] = NO_RUN
        return out
    if status == HEALTHY:
        out["verdict"] = "HEALTHY"
        out["detail"] = f"last run SUCCEEDED at {last.get('fired_at')}"
        return out

    fired = _parse(last.get("fired_at"))
    if fired:
        out["stale_hours"] = round((now - fired).total_seconds() / 3600, 1)

    if status == "ROUTINE_RUN_STATUS_PENDING":
        # A firing IN FLIGHT is the ordinary state of an hourly Routine most
        # of the time, and calling it unhealthy would make this check cry
        # wolf on every run. The interval comes from the Routine's own
        # schedule — the gap between the firing that is running and the one
        # queued next — so an hourly job gets an hour of slack and a weekly
        # one gets a week, without this script parsing cron.
        nxt = _parse(row.get("next_run_at"))
        interval_h = (((nxt - fired).total_seconds() / 3600)
                      if (nxt and fired and nxt > fired) else None)
        elapsed = out.get("stale_hours")
        if interval_h and elapsed is not None and \
                elapsed <= PENDING_INTERVALS * interval_h:
            out["verdict"] = "IN_FLIGHT"
            out["detail"] = (
                f"firing since {last.get('fired_at')}, {elapsed}h into a "
                f"{interval_h:.1f}h interval — running, not stuck")
            return out

    out["verdict"] = status.rsplit("_", 1)[-1]
    out["detail"] = DIAGNOSIS.get(
        status, f"last run {status}; read the session to find out why")
    return out


def report(doc, now: datetime | None = None) -> dict:
    rows = [assess(r, now) for r in _rows(doc)]
    rows.sort(key=lambda r: (r["verdict"] in ("HEALTHY", "IN_FLIGHT"),
                             r["name"]))
    unhealthy = [r for r in rows
                 if r["verdict"] not in ("HEALTHY", "IN_FLIGHT", "NO_RUN",
                                         "DISABLED")]
    return {"routines": rows, "unhealthy": unhealthy,
            "healthy": sum(1 for r in rows if r["verdict"] == "HEALTHY"),
            "total": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="a saved list_triggers response; "
                                   "omit to read stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any enabled Routine is unhealthy")
    a = ap.parse_args(argv)

    raw = open(a.file).read() if a.file else sys.stdin.read()
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0),
                default=-1)
    if start < 0:
        raise SystemExit("no JSON found in that input")
    out = report(json.loads(raw[start:]))

    if a.json:
        print(json.dumps(out, indent=2))
        return 1 if (a.strict and out["unhealthy"]) else 0

    print(f"{out['healthy']}/{out['total']} routine(s) healthy, "
          f"{len(out['unhealthy'])} needing attention\n")
    for r in out["routines"]:
        mark = {"HEALTHY": "✓", "IN_FLIGHT": "▸", "NO_RUN": "·",
                "DISABLED": "·"}.get(r["verdict"], "✗")
        age = (f"  [{r['stale_hours']}h ago]" if r.get("stale_hours")
               else "")
        print(f"  {mark} {r['name']:30s} {r['verdict']:<10}{age}")
        if r["verdict"] not in ("HEALTHY", "IN_FLIGHT"):
            print(f"      {r['detail']}")
            if r.get("session_id"):
                print(f"      session {r['session_id']} — read its "
                      f"post_turn_summary and pending_action")
    if out["unhealthy"]:
        print(f"\n{len(out['unhealthy'])} routine(s) need attention. A "
              f"Routine that fails silently is indistinguishable from one "
              f"with nothing to do.")
    return 1 if (a.strict and out["unhealthy"]) else 0


if __name__ == "__main__":
    sys.exit(main())
