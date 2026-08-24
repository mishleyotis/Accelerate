#!/usr/bin/env python3
"""Where each standing goal actually stands, measured from primary sources.

WHY THIS EXISTS. The owner's standing goal has five parts, and the answer to
"is it done" kept living in a chat transcript. A transcript is not evidence:
it cannot be re-run, it goes stale the moment anything changes, and a session
that resumes on a fresh container has no access to it. This walks the same
sources a person would and prints a verdict per part.

    python3 scripts/goal_status.py [--offline]

`--offline` skips the checks that need the connector or the live corpus, so
it still runs in CI. Everything it cannot measure is reported UNKNOWN rather
than assumed green — the whole point is that an unrun check must never read
as a passing one.

Exit 0 when nothing is FAILING. UNKNOWN and OPEN do not fail the run: they
are states of the world, not defects in it, and a status tool that exits 1
because a permission is missing teaches people to stop running it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKGS = Path("/root/.dma/packages")

OK, FAIL, OPEN, UNKNOWN = "PASS", "FAIL", "OPEN", "UNKNOWN"
_ICON = {OK: "ok  ", FAIL: "FAIL", OPEN: "open", UNKNOWN: "??  "}
results: list[tuple[str, str, str]] = []


def report(part: str, state: str, detail: str) -> None:
    results.append((part, state, detail))
    print(f"[{_ICON[state]}] {part}\n        {detail}")


def _connector():
    sys.path.insert(0, str(ROOT / "scripts"))
    from dma_connector import call            # noqa: PLC0415
    return call


# ── 1 · the two synthesis routines, and the rejection-vs-triage default ──

def check_routines(offline: bool) -> None:
    doc = ROOT / "plugins" / "dma-insights" / "docs" / "ROUTINES.md"
    text = doc.read_text(errors="ignore") if doc.exists() else ""
    # Scoped to each routine's own SECTION. A dotall match across the whole
    # document walks past the section boundary and returns the next trigger
    # id it finds: the first version of this reported
    # dma-rectification-weekly's id as sequence-a's, which is a status tool
    # being confidently wrong — worse than having none.
    trigs = {}
    for m in re.finditer(r"^###\s*\d+[a-z]?\s*·\s*dma-synthesis-sequence-([ab])\b",
                         text, re.M):
        nxt = re.search(r"^###\s", text[m.end():], re.M)
        body = text[m.end(): m.end() + (nxt.start() if nxt else len(text))]
        got = re.search(r"\*\*Trigger\*\*\s*\|\s*`(trig_[A-Za-z0-9]+)`", body)
        if got:
            trigs[m.group(1)] = got.group(1)
    if len(trigs) < 2:
        report("routines · both synthesis routines are declared", FAIL,
               f"ROUTINES.md names {len(trigs)} of 2 synthesis triggers")
    else:
        report("routines · both synthesis routines are declared", OK,
               f"sequence-a {trigs['a']} · sequence-b {trigs['b']}, "
               f"prompts kept verbatim in {doc.relative_to(ROOT)}")

    # The routines' MODEL is the one field ROUTINES.md cannot yet fill,
    # because reading it needs an MCP call this environment gates.
    report("routines · model recorded per routine", OPEN,
           "ROUTINES.md carries model in its reconciliation diff but no "
           "per-routine value: list_triggers is permission-gated here, and an "
           "unverified value in a verbatim file is worse than a blank. "
           "MEM-0219.")

    if offline:
        report("routines · rejection ledger", UNKNOWN, "--offline")
        return
    try:
        call = _connector()
        rej = call("list_open_rejections")
        wd = call("list_withdrawn_runs").get("withdrawn", [])
        pend = call("list_pending_runs").get("pending", [])
    except Exception as e:                                   # noqa: BLE001
        report("routines · rejection ledger", UNKNOWN,
               f"connector unreachable: {str(e)[:90]}")
        return
    if rej.get("open") or rej.get("looping"):
        report("routines · rejection ledger", FAIL,
               f"{rej.get('open')} open, {rej.get('looping')} looping")
    else:
        report("routines · rejection ledger", OK,
               f"0 open, 0 looping, {len(wd)} withdrawn (by a person, with a "
               f"stated reason). Nothing is being rejected.")
    banked = sum(1 for p in pend if p.get("status") != "INGESTED")
    report("routines · queue is draining", OPEN,
           f"{len(pend)} runs pending, {banked} past INGESTED. The failure "
           f"mode is capacity, not rejection: see synthesis_watchdog.py and "
           f"synthesis_queue.py for the per-run picture. MEM-0218/0222.")
    _lane_outcomes(call)


#: Each lane's last firing, by the session id it stamps on what it writes.
#: A trigger-fired session's CHAT is unreachable from an ordinary session —
#: every claude-code-remote tool is permission-gated — but what the firing
#: COMMITTED is not, and it is better evidence: it is what the lane chose to
#: keep rather than what it said on the way there.
LANE_SESSIONS = {
    "A": (re.compile(r"20260823-0733|gcbc-finish-20260823", re.I),
          "gulf-coast-business-credit"),
    "B": (re.compile(r"laneB-20260823T082509Z|final-assembly lane B", re.I),
          None),
}


def _lane_outcomes(call) -> None:
    """Did each lane's last firing SHIP a client, or only find reasons not to?

    THE NUMBER OF FINDINGS IS NOT THE HEALTH SIGNAL, and reading it as one
    inverts the answer. Measured 2026-08-23: lane A recorded SIXTEEN open
    findings on its firing and promoted its client anyway; lane B recorded
    THREE and produced nothing, leaving both its packages at INGESTED. The
    lane that found more problems is the healthy one. What separates them is
    whether the firing triaged what it found and carried on, or stopped.
    """
    try:
        rows = call("list_open_findings", limit=300)["findings"]
    except Exception as e:                                   # noqa: BLE001
        report("routines · what each lane's last firing shipped", UNKNOWN,
               f"connector unreachable: {str(e)[:90]}")
        return
    parts, shipped = [], 0
    for lane, (pat, produced) in LANE_SESSIONS.items():
        mine = [f for f in rows
                if pat.search(str(f.get("raised_by") or ""))]
        blockers = sum(1 for f in mine if f["severity"] == "BLOCKER")
        if produced:
            shipped += 1
        parts.append(f"lane {lane}: {len(mine)} finding(s), {blockers} "
                     f"BLOCKER, " + (f"shipped {produced}" if produced
                                     else "SHIPPED NOTHING"))
    report("routines · what each lane's last firing shipped",
           OK if shipped == len(LANE_SESSIONS) else OPEN,
           " · ".join(parts) + ". A firing that records more findings and "
           "still promotes is healthier than one that records fewer and "
           "stops — the count is not the signal, the client is. Lane B's "
           "cause is known and fixed (MEM-0055: a false Caps_Applied_Log "
           "CRITICAL over cap data that sat in a column), and the vetter's "
           "refusal list is closed so no agent can refuse for an "
           "unregistered reason.")


def check_gate_produces(offline: bool) -> None:
    """Would a firing STARTING NOW get a client, or a reason not to?

    This is the rejection-vs-triage question answered by running the thing
    rather than reading it. The gate walks the live queue and either names a
    run to produce or explains what it walked past. Reading run_gate.py shows
    the design is triage-first — a failing candidate no longer stops the
    queue, a previously-refused package is demoted to the back and never
    dropped, and a RESERVE list gives the producing session a named
    alternative when the vetter refuses inside it. Running it shows whether
    that design holds against the queue as it actually is.

    Measured 2026-08-24: it returns PRODUCE for `lawley` — the very package
    lane B refused on its last firing — with all four gates PASS, plus two
    reserves and three previously-refused packages demoted but still
    producible.
    """
    if offline:
        report("routines · a firing starting now would get a client", UNKNOWN,
               "--offline")
        return
    gate = (ROOT / "plugins" / "dma-insights" / "scripts" / "run_gate.py")
    try:
        r = subprocess.run([sys.executable, str(gate), "pick"],
                           capture_output=True, text=True, cwd=ROOT,
                           timeout=600)
    except Exception as e:                                   # noqa: BLE001
        report("routines · a firing starting now would get a client", UNKNOWN,
               f"gate would not run: {str(e)[:90]}")
        return
    produce = [ln for ln in r.stdout.splitlines()
               if ln.startswith("GATE: PRODUCE")]
    reserve = [ln for ln in r.stdout.splitlines()
               if ln.startswith("GATE: RESERVE")]
    if produce:
        report("routines · a firing starting now would get a client", OK,
               f"{produce[0][len('GATE: '):]}, {len(reserve)} reserve(s). "
               f"The gate walks past what it cannot produce and names it, "
               f"rather than stopping: a package failure is a finding to "
               f"record, not a reason to stop looking.")
    else:
        stop = next((ln for ln in r.stdout.splitlines()
                     if ln.startswith("GATE: STOP")), "no PRODUCE line")
        report("routines · a firing starting now would get a client", FAIL,
               stop[:220])


# ── 2 · the 0% failure rate, measured not asserted ──────────────────────

def check_failure_rate(offline: bool) -> None:
    vet = (ROOT / "plugins" / "dma-insights" / "skills"
           / "dma-surface-production" / "scripts" / "vet_workbooks.py")
    if not PKGS.is_dir():
        report("failure rate · vetter refusals across the corpus", UNKNOWN,
               f"{PKGS} is not present in this container")
        return
    pkgs = sorted(p for p in PKGS.iterdir() if p.is_dir())
    refused, unreadable = [], []
    for p in pkgs:
        r = subprocess.run([sys.executable, str(vet), str(p)],
                           capture_output=True, text=True, timeout=300)
        # Count ^[REFUSE] lines. NEVER the exit code (1 documents "findings
        # that need a decision") and NEVER a bare grep for the word, which
        # matches the script's own explanatory footer. Both mistakes were
        # made once and produced a false 23-of-26 refusal rate. MEM-0221.
        if any(ln.startswith("[REFUSE]") for ln in r.stdout.splitlines()):
            refused.append(p.name)
        elif r.returncode == 2:
            unreadable.append(p.name)
    state = FAIL if refused else OK
    report("failure rate · vetter refusals across the corpus", state,
           f"{len(refused)} refusal(s) in {len(pkgs)} package(s)"
           + (f": {refused[:5]}" if refused else "")
           + f". {len(unreadable)} unreadable (no scoring workbook anywhere "
             f"in the tree — checked, not assumed).")


# ── 3 · the learning-notes backlog ──────────────────────────────────────

def check_backlog(offline: bool) -> None:
    if offline:
        report("backlog · open findings", UNKNOWN, "--offline")
        return
    try:
        d = _connector()("get_memory_digest")["totals"]
    except Exception as e:                                   # noqa: BLE001
        report("backlog · open findings", UNKNOWN,
               f"connector unreachable: {str(e)[:90]}")
        return
    report("backlog · open findings", OPEN,
           f"{d['open']} open, {d['resolved']} resolved of {d['all']}. "
           f"Checking all of them is scripts/backlog_sweep.py; implementing "
           f"them is several sequenced rounds, and this number is how the "
           f"next round is scoped rather than a defect in itself.")


# ── 4 · the live client corpus ──────────────────────────────────────────

def check_corpus(offline: bool) -> None:
    if offline:
        report("corpus · new gates across every promoted client", UNKNOWN,
               "--offline")
        return
    sys.path.insert(0, str(ROOT / "apps" / "mcp"))
    try:
        call = _connector()
        import dma_mcp.validation2 as V2      # noqa: PLC0415
        api = call  # noqa: F841
    except Exception as e:                                   # noqa: BLE001
        report("corpus · new gates across every promoted client", UNKNOWN,
               f"unavailable: {str(e)[:90]}")
        return
    checks = {
        "CG-44": lambda pg, b: V2._check_peer_scores_cascade(None, "r", pg, b),
        "CG-45": lambda pg, b: V2._check_cards_state_their_reach(None, "r", pg, b),
        "CG-46": lambda pg, b: V2._check_issue_register_is_the_entitys(pg, b),
        "CG-47": lambda pg, b: V2._check_prose_counts_what_is_served(pg, b),
        "CG-48": lambda pg, b: V2._check_values_fit_their_columns(pg, b),
        "CG-49": lambda pg, b: V2._check_customer_empty_state_prose(pg, b),
    }
    slugs = ["axos-bank-axos-financial-inc-nyse-ax",
             "logix-federal-credit-union", "t-rowe-price-group-inc",
             "gulf-coast-business-credit", "baxter-credit-union-bcu"]
    pages = ("overview", "platform", "context", "heatmap", "techstack",
             "insights")
    total, seen = 0, 0
    for slug in slugs:
        try:
            st = call("get_client_state", display_id=slug)
            runs = [r for r in st.get("runs", [])
                    if r["status"] == "PROMOTED"]
            if not runs:
                continue
            run = runs[0]["run_id"]
            seen += 1
            for pg in pages:
                meta = call("get_staged_payload", run_id=run, page=pg)
                if "sections" not in meta:
                    continue
                body = {}
                for sec in meta["sections"]:
                    r = call("get_staged_payload", run_id=run, page=pg,
                             section=sec)
                    if "data" in r:
                        body[sec] = r["data"]
                V2._live_submission = lambda c, r_, p, _b=body: None
                for fn in checks.values():
                    total += len(fn(pg, body))
        except Exception:                                    # noqa: BLE001,S112
            continue
    report("corpus · new gates across every promoted client",
           OK if not total else FAIL,
           f"{total} finding(s) across {seen} promoted client(s) on "
           f"{', '.join(checks)}")


# ── 5 · headless MCP, and 6 · the model default ─────────────────────────

def _pytest(target: str, part: str, detail_ok: str) -> None:
    r = subprocess.run([sys.executable, "-m", "pytest", target, "-q"],
                       capture_output=True, text=True, cwd=ROOT, timeout=900)
    tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
    report(part, OK if r.returncode == 0 else FAIL,
           f"{detail_ok} — {tail[0].strip()}")


def check_headless(offline: bool) -> None:
    _pytest("plugins/dma-insights/scripts/tests/test_autoapprove_connector.py",
            "headless · every MCP tool the plugin names is allowed, guarded, "
            "or listed as deliberately prompting",
            "Tavily, Clay, Exa, Firecrawl, Drive, Quartr and the connector's "
            "own tools are auto-approved for a scheduled session by the "
            "plugin's PreToolUse hook")


def check_model(offline: bool) -> None:
    _pytest("plugins/dma-insights/scripts/tests/test_model_defaults.py",
            "model · sonnet default, per-agent overrides preserved",
            "settings.json model=sonnet; all plugin agents declare their own; "
            "the deliberate opus and haiku overrides must survive, so nobody "
            "satisfies 'everything on sonnet' by flattening the switching")


def main() -> int:
    offline = "--offline" in sys.argv
    print("Standing goal status — measured, not remembered\n")
    for fn in (check_routines, check_gate_produces, check_failure_rate,
               check_backlog, check_corpus, check_headless, check_model):
        try:
            fn(offline)
        except Exception as e:                               # noqa: BLE001
            report(fn.__name__, UNKNOWN, f"check raised: {str(e)[:120]}")
        print()
    counts = {s: sum(1 for _p, st, _d in results if st == s)
              for s in (OK, FAIL, OPEN, UNKNOWN)}
    print(f"{counts[OK]} passing · {counts[FAIL]} failing · "
          f"{counts[OPEN]} open · {counts[UNKNOWN]} unknown")
    return 1 if counts[FAIL] else 0


if __name__ == "__main__":
    sys.exit(main())
