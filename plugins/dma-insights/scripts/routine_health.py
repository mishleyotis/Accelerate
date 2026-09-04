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
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    # `enabled` is ABSENT from the records the API returned on 2026-09-03
    # (six Routines, none carrying the key). Read as `bool(None)`, every one
    # of them was reported DISABLED — "a person paused it" — which is the
    # wrong diagnosis for a field that was never sent. A missing key is
    # unknown, not False; the schedule itself (next_run_at against now) is
    # what says whether the Routine is firing.
    enabled = row.get("enabled")
    out = {
        "name": name, "id": row.get("id"),
        "cron": row.get("cron_expression") or row.get("run_once_at"),
        "enabled": None if enabled is None else bool(enabled),
        "last_status": status or None,
        "last_fired_at": last.get("fired_at"),
        "session_id": last.get("session_id"),
        "next_run_at": row.get("next_run_at"),
    }
    if enabled is not None and not enabled:
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

    fired = _parse(last.get("fired_at"))
    if fired:
        out["stale_hours"] = round((now - fired).total_seconds() / 3600, 1)

    # THE SCHEDULE ITSELF, before the last run's status. Measured 2026-09-03:
    # all six Routines read `last_run SUCCEEDED` and `next_run_at` three to
    # four DAYS in the past — nothing had fired since 2026-08-30, and a check
    # that trusted the last status alone would have called every one of them
    # HEALTHY. A Routine whose next scheduled firing is more than two of its
    # own intervals overdue is not firing, whatever its last run said; the
    # measured cause was the account's usage limit, which pauses every
    # Routine and writes no reason into the record.
    nxt = _parse(row.get("next_run_at"))
    if nxt and fired and nxt > fired and status != "ROUTINE_RUN_STATUS_PENDING":
        interval_h = (nxt - fired).total_seconds() / 3600
        overdue_h = (now - nxt).total_seconds() / 3600
        if overdue_h > PENDING_INTERVALS * max(interval_h, 1.0):
            out["verdict"] = "OVERDUE"
            out["overdue_hours"] = round(overdue_h, 1)
            out["detail"] = (
                f"next_run_at {row.get('next_run_at')} is {overdue_h:.0f}h in "
                f"the past against a {interval_h:.1f}h interval — the schedule "
                f"has not fired, whatever the last run said. The measured "
                f"cause is an account-level pause (a usage or spend limit "
                f"suspends every Routine and records no reason on it); check "
                f"claude.ai/settings/usage and the Routines UI, then the "
                f"trigger's own `enabled` state.")
            return out

    if status == HEALTHY:
        out["verdict"] = "HEALTHY"
        out["detail"] = f"last run SUCCEEDED at {last.get('fired_at')}"
        return out

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


#: The canon that says which Routines are supposed to exist. Parsed rather
#: than duplicated here, for the same reason `test_routines_canon.py` reads
#: it: a second copy of the list is a second answer to the question.
CANON = Path(__file__).resolve().parents[1] / "docs" / "ROUTINES.md"

#: `### 2a · dma-synthesis-sequence-a — `8 */12 * * *` · LIVE (`trig_…`, …)`
_CANON_HEAD = re.compile(r"^### 2[a-z-]* · ([a-z0-9-]+) — .*$", re.M)


#: A heading state that means "this Routine is supposed to exist". LIVE is
#: the ordinary one. NOT CREATED is a Routine the canon still requires and
#: that nothing has managed to create yet — on 2026-08-30 lane A's create
#: call was refused by the session harness's permission classifier. Reading
#: only LIVE would drop it from the required set the moment its heading was
#: made honest, which is the blindness this whole check exists to end: the
#: heading would then be accurate AND the routine unmonitored.
_REQUIRED_STATES = ("LIVE", "NOT CREATED")


def declared_live(canon: Path = CANON) -> list[str]:
    """The Routine names the canon says must exist.

    A name counts only when its own heading carries one of
    `_REQUIRED_STATES`, because the canon also carries DELETED sections kept
    as history — 2a-ii is one — and reading those as required would demand
    the rebuild of a Routine somebody deliberately removed.
    """
    try:
        text = canon.read_text()
    except OSError:
        return []
    return [m.group(1) for m in _CANON_HEAD.finditer(text)
            if any(s in m.group(0) for s in _REQUIRED_STATES)]


def _prompt_of(doc, name: str, tid: str | None) -> str | None:
    """The live prompt for one Routine, when the input carries prompts.

    `list_triggers` returns them; a caller that hand-built a summary may
    not. None means "not supplied", which is never read as "matches" —
    a drift check that treats missing data as agreement is a check that
    reports green on no evidence.
    """
    for r in _rows(doc):
        if r.get("name") == name or (tid and r.get("id") == tid):
            p = r.get("prompt")
            return p if isinstance(p, str) else None
    return None


def _drift(name: str, live_prompt: str, canon: Path) -> str | None:
    """A one-line description of how the live prompt differs from canon."""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import routine_sync                                  # noqa: PLC0415
        sec = next((v for v in routine_sync.sections(canon).values()
                    if v["name"] == name and v["live"]), None)
        if not sec or not sec["prompt"]:
            return None
        c = routine_sync.compare(sec["prompt"], live_prompt)
        if c["in_sync"]:
            return None
        moved = [k for k, m in c["markers"].items() if m["canon"] != m["live"]]
        return (f"the prompt that FIRES is not the prompt in "
                f"docs/ROUTINES.md ({c['live_chars']} chars live vs "
                f"{c['canon_chars']} in the canon"
                + (f"; differs on: {', '.join(moved)}" if moved else "")
                + "). The canon is the intended text, so the Routine is "
                  "running behind it: `routine_sync.py push --routine "
                  "<key>` renders the update_trigger call that closes it")
    except Exception:                                        # noqa: BLE001
        # A drift check that crashes must not take the health report with
        # it — the run-outcome verdicts above are the older, load-bearing
        # half and they stand on their own.
        return None


def report(doc, now: datetime | None = None,
           canon: Path = CANON) -> dict:
    rows = [assess(r, now) for r in _rows(doc)]

    # A Routine that does not exist reports nothing, and "nothing" was
    # being read as "nothing wrong": on 2026-08-30 this script answered
    # `0/0 routine(s) healthy` and exit 0 for an account carrying no
    # Routines at all, while the canon declared six LIVE — so the
    # readiness board's routines lane went green on an empty schedule.
    # That is the same shape as the failures this file was written for:
    # from inside the app a deleted Routine and a healthy one both look
    # like silence. The canon is the list of what should be there, so
    # absence is now a verdict rather than an empty table.
    present = {r["name"] for r in rows}
    for name in declared_live(canon):
        if name in present:
            continue
        rows.append({
            "name": name, "id": None, "cron": None, "enabled": False,
            "last_status": None, "last_fired_at": None,
            "session_id": None, "next_run_at": None,
            "verdict": "MISSING",
            "detail": ("declared LIVE in docs/ROUTINES.md and absent from "
                       "list_triggers — nothing is scheduled to do this "
                       "work. Either recreate it from that section's fenced "
                       "prompt, or record the deletion there; an "
                       "undocumented absence is drift, not a decision."),
        })

    # PROMPT DRIFT IS A HEALTH PROBLEM, and until 2026-08-31 nothing here
    # looked at it. A Routine can be enabled, firing on schedule and
    # SUCCEEDING every time while running a prompt nobody has read in weeks
    # — which is exactly what happened: the intake's STEP 0a was fixed in
    # the canon, pushed to the default branch, and the Routine went on
    # firing the old text and stopping on a stale plugin. Every row here
    # said HEALTHY. It was, at doing the wrong thing.
    for r in rows:
        if r["verdict"] not in ("HEALTHY", "IN_FLIGHT", "NO_RUN"):
            continue
        live_prompt = _prompt_of(doc, r["name"], r.get("id"))
        if live_prompt is None:
            continue
        d = _drift(r["name"], live_prompt, canon)
        if d:
            r["verdict"] = "PROMPT_DRIFT"
            r["detail"] = d

    rows.sort(key=lambda r: (r["verdict"] in ("HEALTHY", "IN_FLIGHT"),
                             r["name"]))
    unhealthy = [r for r in rows
                 if r["verdict"] not in ("HEALTHY", "IN_FLIGHT", "NO_RUN",
                                         "DISABLED")]
    return {"routines": rows, "unhealthy": unhealthy,
            "healthy": sum(1 for r in rows if r["verdict"] == "HEALTHY"),
            "declared": len(declared_live(canon)),
            "missing": [r["name"] for r in rows
                        if r["verdict"] == "MISSING"],
            "total": len(rows)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--file", help="a saved list_triggers response; "
                                   "omit to read stdin")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true",
                    help="exit 1 when any enabled Routine is unhealthy")
    ap.add_argument("--canon", default=str(CANON),
                    help="the ROUTINES.md whose LIVE sections say which "
                         "Routines must exist; a Routine declared there and "
                         "absent from the input is MISSING. Point it at an "
                         "empty file to check only what the input carries.")
    a = ap.parse_args(argv)

    raw = open(a.file).read() if a.file else sys.stdin.read()
    start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0),
                default=-1)
    if start < 0:
        raise SystemExit("no JSON found in that input")
    out = report(json.loads(raw[start:]), canon=Path(a.canon))

    if a.json:
        print(json.dumps(out, indent=2))
        return 1 if (a.strict and out["unhealthy"]) else 0

    print(f"{out['healthy']}/{out['total']} routine(s) healthy, "
          f"{len(out['unhealthy'])} needing attention "
          f"({out['declared']} declared LIVE in the canon, "
          f"{len(out['missing'])} missing)\n")
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
