#!/usr/bin/env python3
"""Which synthesis sessions have stopped, and what to say to restart them.

THE FAILURE THIS WATCHES FOR, in the words of the trigger someone had to
hand-write after noticing it:

    "Your turn ended while the pipeline was mid-flight. Your last summary said
     '7 agents running: platform challengers + overview/O5/techstack; awaiting
     verdicts' — but dispatched subagents do not survive a turn boundary, so
     those verdicts will never arrive."

That is the shape of every stall seen so far. A producer fans work out, the
turn ends, and the session is left holding a live claim with nothing running
inside it. From outside it is indistinguishable from a session that is
thinking hard: the claim is live, the run is real, no error was raised. It
stays that way until a human notices and writes a resume by hand — and the
one time that took a while, the redo cost 2.1M output tokens.

Nothing about it is undetectable, though. A producer that is working SUBMITS
pages, so progress is observable from the connector alone:

    STALLED           a live claim whose page fingerprint has not moved
                      between two observations far enough apart to matter
    READY_TO_PROMOTE  six pages PASS, promotable, and nothing promoted —
                      the finish line, unattended. This is the state T. Rowe
                      Price sat in
    EXPIRING          a live claim about to lapse with work unfinished, which
                      is the last moment a resume is cheap
    PROGRESSING       moved since the last look; leave it alone
    UNCLAIMED         nobody is working it; the queue's problem, not this one

It WRITES NOTHING to production. It reads the connector's view, compares it
with the last observation, and prints a plan — one entry per run, with the
resume text to send. What acts on that plan is a routine, so the safeguard
does not depend on the stalled session noticing it has stalled.

    python3 scripts/synthesis_watchdog.py --state .watchdog.json
    python3 scripts/synthesis_watchdog.py --state .watchdog.json --json

The resume text always names what is ALREADY BANKED before it names what is
missing. A resume that says only "carry on" is how work gets done twice.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

#: How long a live claim may show no movement before it is called stalled.
#: A page is minutes of work, not seconds; below this a slow producer would be
#: interrupted mid-section, which costs more than the wait.
STALL_SECONDS = 900

#: How little claim is left before a resume stops being cheap. Under this, the
#: lease lapses before another producer could finish, so the session holding
#: it is the one that has to be woken.
EXPIRING_SECONDS = 1200

PAGES = ("overview", "insights", "heatmap", "platform", "context", "techstack")

STALLED = "STALLED"
READY_TO_PROMOTE = "READY_TO_PROMOTE"
EXPIRING = "EXPIRING"
PROGRESSING = "PROGRESSING"
UNCLAIMED = "UNCLAIMED"
DONE = "DONE"

#: The states a routine should act on. PROGRESSING and UNCLAIMED are reported
#: so a reader can see they were considered, never woken.
ACTIONABLE = (STALLED, READY_TO_PROMOTE, EXPIRING)


def _iso(t) -> str:
    return str(t or "")


def fingerprint(progress: dict) -> str:
    """What "progress" means, reduced to one comparable string.

    Deliberately the SUBMISSION IDS and not a count: a page resubmitted after
    a failed verdict is progress, and a count would call it a stall. Ordered
    by page name so two observations of the same state always match.
    """
    pages = progress.get("pages") or {}
    return "|".join(
        f"{p}:{(pages.get(p) or {}).get('status') or '-'}"
        f":{(pages.get(p) or {}).get('submission_id') or '-'}"
        for p in sorted(PAGES))


def banked(progress: dict) -> tuple:
    pages = progress.get("pages") or {}
    passed = sorted(p for p in PAGES
                    if (pages.get(p) or {}).get("status") == "PASS")
    missing = sorted(p for p in PAGES if p not in passed)
    return passed, missing


def classify(progress: dict, previous: dict | None, now_epoch: float) -> dict:
    """One run's state. `previous` is this run's entry from the last run of
    this script, or None the first time it is seen."""
    claim = progress.get("claim") or {}
    live = bool(claim.get("live"))
    passed, missing = banked(progress)
    fp = fingerprint(progress)
    promoted = [p for p in PAGES
                if ((progress.get("pages") or {}).get(p) or {}).get("promoted_at")]

    out = {
        "fingerprint": fp,
        "passed": passed,
        "missing": missing,
        "promotable": bool(progress.get("promotable")),
        "blocking": len(progress.get("blocking") or []),
        "claim_live": live,
        "claim_held_by": claim.get("held_by"),
        "claim_expires_at": _iso(claim.get("expires_at")),
    }

    if len(promoted) == len(PAGES) and not missing and fp == (previous or {}).get("fingerprint"):
        out["state"] = DONE
        return out
    if out["promotable"] and not promoted:
        # The finish line, unattended. Worth waking whether or not the claim
        # is live: six passing pages that never promoted serve nothing.
        out["state"] = READY_TO_PROMOTE
        return out
    if not live:
        out["state"] = UNCLAIMED
        return out
    if previous and previous.get("fingerprint") == fp:
        since = now_epoch - float(previous.get("seen_at") or now_epoch)
        out["stalled_for_seconds"] = int(since)
        out["state"] = STALLED if since >= STALL_SECONDS else PROGRESSING
        return out
    out["state"] = PROGRESSING
    return out


def resume_text(run_id: str, entity: str, s: dict) -> str:
    """What to send. Banked work FIRST, always.

    The expensive mistake is not the stall, it is the redo after it: a resume
    that says "carry on" gets the finished pages produced a second time.
    """
    passed = ", ".join(s["passed"]) or "none"
    missing = ", ".join(s["missing"]) or "none"
    head = {
        STALLED: (f"Your turn ended while this run was mid-flight, and "
                  f"dispatched subagents do not survive a turn boundary — any "
                  f"verdicts you were waiting on will never arrive. Nothing "
                  f"has moved for {s.get('stalled_for_seconds', 0) // 60} "
                  f"minutes."),
        READY_TO_PROMOTE: ("All six pages PASS and the run is promotable, and "
                           "nothing has been promoted. The work is done and "
                           "serving nothing."),
        EXPIRING: ("Your claim on this run lapses shortly with work "
                   "unfinished. After it lapses another producer may take the "
                   "run and repeat what you have already done."),
    }[s["state"]]
    return (
        f"{head}\n\n"
        f"Run {run_id} ({entity}), read from the connector just now:\n"
        f"  ALREADY BANKED (do NOT reproduce these): {passed}\n"
        f"  still missing: {missing}\n"
        f"  promotable: {s['promotable']}   blocking reasons: {s['blocking']}\n"
        f"  claim: {s['claim_held_by']} live={s['claim_live']} "
        f"expires {s['claim_expires_at']}\n\n"
        f"Before dispatching anything, establish what already exists and do "
        f"not redo it. A section whose payload is banked gets RE-VALIDATED, "
        f"not re-produced:\n"
        f"  python3 plugins/dma-insights/scripts/artifact_store.py find "
        f"--root <artifacts-dir> --run {run_id[:8]}\n"
        f"Then call get_run_progress yourself and continue from what it says, "
        f"not from what this message says — this was true when it was written."
    )


def plan(runs: list, state: dict, now_epoch: float) -> list:
    out = []
    for r in runs:
        run_id = r.get("run_id")
        if not run_id:
            continue
        s = classify(r.get("progress") or {}, state.get(run_id), now_epoch)
        s["run_id"] = run_id
        s["entity"] = r.get("entity_name") or r.get("display_id") or ""
        s["seen_at"] = now_epoch
        if s["state"] in ACTIONABLE:
            s["resume"] = resume_text(run_id, s["entity"], s)
        out.append(s)
    return out


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:                                   # noqa: BLE001
        return {}


#: Keys the queue has been known to return its rows under. `pending` is what
#: the deployed connector uses.
QUEUE_KEYS = ("pending", "runs", "rows", "items")


def queue_rows(payload):
    """The queue's rows, or a refusal — never a silent empty list.

    THE BUG THIS REPLACES, and it is the worst possible one to have here:
    `payload.get("runs") or []`. The connector nests its rows under
    `pending`, so `runs` was always None, `rows` was always [], and the
    watchdog could never see a single run — claimed, stalled or promotable —
    whatever the real state was. Verified against the live connector
    2026-08-23: the top-level keys are `pending` (286 rows),
    `duplicate_requests`, `surplus_runs`.

    Every firing since it shipped reported a quiet queue while unable to look
    at one. A watchdog that cannot see is worse than no watchdog: it
    manufactures the reassurance that nothing is stalled, which is the exact
    condition it exists to deny.

    So an unrecognised shape RAISES. The whole point of this file is that "I
    looked and found nothing" and "I could not look" are different answers,
    and the second must never be able to impersonate the first.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"list_pending_runs returned {type(payload).__name__}, not a "
            f"queue — the watchdog cannot report on a queue it did not get")
    for key in QUEUE_KEYS:
        if isinstance(payload.get(key), list):
            return payload[key]
    raise RuntimeError(
        f"list_pending_runs returned a dict carrying no row list under any "
        f"of {QUEUE_KEYS}; its keys are {sorted(payload)}. Refusing to report "
        f"an empty queue from a response this code does not understand — "
        f"that is exactly how this watchdog went blind before")


def sessions_holding(result: list) -> list:
    """Which sessions are working, and which are only holding.

    Owner, 2026-08-23: "The watchdog is to check for any running sessions in
    the synthesis routines."

    A claim names its holder, and the queue row is the only place a watchdog
    without MCP tools can learn who is working. Grouping by holder turns four
    unrelated rows into the signal that matters: ONE PRODUCER SHOULD HOLD ONE
    RUN. A holder carrying several at once, none of them progressing, is the
    stall signature this file exists to make visible — measured live on
    2026-08-23, when one holder had three runs at 0 of 6 pages while a fourth
    session held one run at 6 of 6 and had not promoted it.

    This reports; it never releases. A lease belongs to its holder until it
    lapses, and taking one from a session that is merely slow is how two
    producers end up on one client's six pages.
    """
    by_holder: dict = {}
    for s in result:
        if not s.get("claim_live"):
            continue
        by_holder.setdefault(s.get("claim_held_by") or "(unnamed)", []).append(s)
    out = []
    for holder, runs in sorted(by_holder.items()):
        pages = sum(len(r.get("passed") or []) for r in runs)
        out.append({
            "holder": holder,
            "runs_held": len(runs),
            "pages_passed": pages,
            "states": sorted({r.get("state") for r in runs}),
            "entities": [r.get("entity") for r in runs],
            "expires": min((r.get("claim_expires_at") or "") for r in runs),
            # A producer holding more than one run is either batching (which
            # the routine forbids: one client per session) or leaking leases.
            "holds_more_than_one": len(runs) > 1,
            # Nothing passed across every run it holds: either it just
            # started, or it stopped. The next firing's fingerprint decides.
            "no_pages_yet": pages == 0,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=".watchdog.json",
                    help="where the last observation is kept")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--now", type=float, default=None,
                    help="epoch seconds, for tests")
    ap.add_argument("--promote-ready", action="store_true",
                    help="promote every run the walk classified "
                         "READY_TO_PROMOTE — six pages PASS, promotable, "
                         "nothing promoted. Opt-in: the watchdog observes "
                         "unless asked. Each one is re-read and re-checked "
                         "immediately before promoting.")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import time

    from dma_connector import call

    now = args.now if args.now is not None else time.time()
    pending = call("list_pending_runs")
    rows = queue_rows(pending)

    # NARROW BEFORE ASKING. The queue holds 286 pending runs across 171
    # entities; a per-run get_run_progress over all of them is 286 round trips
    # to answer a question about the handful anyone is working. The queue row
    # already carries the claim, so the filter costs nothing — and a watchdog
    # slow enough to be run rarely is a watchdog that misses stalls.
    #
    # Runs already carried on the state file stay in scope even without a live
    # claim: that is how READY_TO_PROMOTE is still seen after a lease lapses,
    # which is the likeliest way to reach it.
    known = set(_load(Path(args.state)))
    watch = [r for r in rows
             if r.get("run_id")
             and ((r.get("claim") or {}).get("live") or r["run_id"] in known)]
    if len(watch) > 40:                    # a runaway filter, not a real queue
        raise SystemExit(f"{len(watch)} runs matched — refusing to poll that "
                         f"many; check the claim field in list_pending_runs")
    runs = [{**r, "progress": call("get_run_progress", run_id=r["run_id"])}
            for r in watch]

    path = Path(args.state)
    state = _load(path)
    result = plan(runs, state, now)
    path.write_text(json.dumps({s["run_id"]: s for s in result}, indent=1),
                    encoding="utf-8")

    holders = sessions_holding(result)
    if args.json:
        print(json.dumps({"runs": result, "sessions": holders}, indent=1))
    else:
        act = [s for s in result if s["state"] in ACTIONABLE]
        print(f"{len(result)} run(s) watched · {len(act)} actionable")
        for s in result:
            print(f"  {s['state']:17s} {s['run_id'][:8]}  {s['entity'][:34]:34s} "
                  f"banked {len(s['passed'])}/6")
        for s in act:
            print("\n" + "─" * 68)
            print(s["resume"])

    # PROMOTING FROM HERE, rather than from a heredoc in the routine prompt.
    #
    # The prompt used to carry an inline `python3 - <<'PY' … PY` block that
    # re-read the run and called promote_run. It was indented inside the
    # prompt's numbered list, and an unquoted-terminator heredoc needs its
    # terminator at column 0 — so as written it could not run at all. Beyond
    # that, a routine prompt is the worst place for logic: nothing tests it,
    # and a copy-paste error in it fails at 03:23 with nobody reading.
    #
    # So the decision lives here, where the tests are. It stays OPT-IN: the
    # watchdog observes by default, and only promotes when the caller asks.
    promoted, refused = [], []
    if args.promote_ready:
        ready = [s for s in result if s["state"] == READY_TO_PROMOTE]
        for s in ready:
            fresh = call("get_run_progress", run_id=s["run_id"])
            # RE-READ AND RE-CHECK, never promote on the strength of the
            # observation above: it may be a minute old, and a run that
            # acquired a blocking verdict in between must not be promoted
            # because a cached view said it was clean.
            if not fresh.get("promotable") or fresh.get("blocking"):
                refused.append({"run_id": s["run_id"],
                                "blocking": fresh.get("blocking")})
                print(f"  REFUSED  {s['run_id'][:8]} — no longer promotable: "
                      f"{fresh.get('blocking')}")
                continue
            call("promote_run", run_id=s["run_id"])
            after = call("get_run_progress", run_id=s["run_id"])
            stamps = {p.get("promoted_at") for p in
                      (after.get("pages") or {}).values()
                      if isinstance(p, dict)} - {None}
            # Invariant 3: promotion is atomic across all six pages. More than
            # one promoted_at means it was not, and that is a defect to report
            # rather than an outcome to retry.
            if len(stamps) > 1:
                print(f"  ATOMICITY FAILURE {s['run_id'][:8]}: six pages "
                      f"carry {len(stamps)} distinct promoted_at values "
                      f"{sorted(stamps)} — reporting, not retrying")
                refused.append({"run_id": s["run_id"],
                                "atomicity": sorted(stamps)})
                continue
            promoted.append(s["run_id"])
            print(f"  PROMOTED {s['run_id'][:8]}  {s['entity'][:40]}")
        if not ready:
            print("  nothing was READY_TO_PROMOTE")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
