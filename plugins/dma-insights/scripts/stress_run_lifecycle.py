#!/usr/bin/env python3
"""Walk the five lifecycle requirements through the REAL command line.

    python3 scripts/stress_run_lifecycle.py [--workdir DIR] [--keep]

Not a unit test — a walk. Every step below shells out to the engine exactly
as the conductor does, so what this proves is that the commands in the agent
manifest and END-TO-END.md actually run, in that order, against a real
workbook. The unit tests pin the refusals; this pins the SEQUENCE, which is
the thing that was broken: every individual piece of the Golden 1 run worked
and the run still finished with no client folder, no institution profile and
six empty tabs.

Requirements walked, in the order a run meets them:

  2  the binding preflight refuses an unasked question, refuses a binding
     that contradicts the answer, and derives the bases from the file
  1  `start` opens '<Entity> - DMA' with an IN_PROGRESS manifest
  5  `start` registers the run so a later container can find it
  3  `orient` withholds every category card until PRELIM closes
  4  `completeness` blocks a workbook whose tabs are empty
  5  the watchdog sees a run whose container is gone, and revives it

Exit 0 only if every step behaves as stated. Any step that cannot run says
NOT_RUN with the reason rather than being skipped silently.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent / "skills" / "dma-research"

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}"
          + (f"\n          {detail}" if detail and not ok else ""))
    return bool(ok)


def run(*args, expect: int | None = 0, env: dict | None = None):
    """One engine command, as the conductor issues it."""
    import os
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run([sys.executable, "-m", *args], cwd=str(SKILL),
                       capture_output=True, text=True, timeout=900, env=e)
    if expect is not None and r.returncode != expect:
        print(f"    ! {' '.join(args)} -> {r.returncode} (wanted {expect})")
        print("    " + (r.stderr or r.stdout).strip()[-600:].replace(
            "\n", "\n    "))
    return r


def jrun(*args, **kw):
    r = run(*args, **kw)
    try:
        return r, json.loads(r.stdout)
    except ValueError:
        return r, {}


def preflight_doc(entity: str, entity_id: str) -> dict:
    """A filled preflight — a real call report, a real census, a real answer."""
    return {
        "_contract": "preflight-v1",
        "run_id": "",
        "entity": {"name": entity, "entity_id": entity_id,
                   "website": "https://example.invalid", "as_of": "2026-08-30"},
        "financials": {
            "statements": [{
                "source_name": "NCUA Call Report — 2025 Q4",
                "url": "https://mapping.ncua.gov/ResearchCreditUnion",
                "kind": "call_report", "period": "FY2025", "tier": "T1",
                "period_end": "2025-12-31",
                "retrieved_at": "2026-08-30T09:00:00Z"}],
            "revenue_lines": [
                {"line": "Interest income — consumer loans",
                 "amount": 612000000, "currency": "USD", "period": "FY2025",
                 "share_pct": 74.0, "implies_lob": "retail consumer lending",
                 "source": "NCUA Call Report"},
                {"line": "Fee and other operating income",
                 "amount": 215000000, "currency": "USD", "period": "FY2025",
                 "share_pct": 26.0, "implies_lob": "retail deposit services",
                 "source": "NCUA Call Report"}],
            "not_run": ""},
        "lob_census": {
            "lines_of_business": [
                {"lob": "retail consumer lending", "revenue_share_pct": 74.0,
                 "material": True,
                 "basis": "largest call-report revenue line, 74.0% of FY2025"},
                {"lob": "retail deposit services", "revenue_share_pct": 26.0,
                 "material": True,
                 "basis": "fee and other operating income, 26.0% of FY2025"}],
            "candidates": [
                {"sub_vertical": "CU", "verdict": "ACCEPT",
                 "reason": "state-chartered NCUA-insured credit union; both "
                           "material revenue lines are member retail business"},
                {"sub_vertical": "RB", "verdict": "REJECT",
                 "reason": "no OCC or FDIC bank charter exists for this "
                           "entity; deposits are member-owned"}]},
        "binding_question": {
            "asked": True, "tool": "AskUserQuestion",
            "question": "Two material retail revenue lines and no commercial "
                        "book — bind to which sub-vertical, and is the whole "
                        "retail estate in scope?",
            "options": ["CU — all retail lines", "CU — lending only", "RB"],
            "answer": "CU — all retail lines", "answer_sub_vertical": "CU",
            "answered_by": "engagement owner",
            "answered_at": "2026-08-30T09:12:00Z"},
        "mode_question": {
            "asked": True, "tool": "AskUserQuestion",
            "question": "What evidence access does this engagement carry?",
            "options": ["PUBLIC", "HYBRID", "INTERNAL"],
            "answer": "PUBLIC — no internal documents provided",
            "answer_mode": "PUBLIC", "answered_by": "engagement owner",
            "answered_at": "2026-08-30T09:12:00Z"},
        "binding": {"sub_vertical": "CU", "evidence_mode": "PUBLIC",
                    "scope_mode": "T1_CORE"},
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--workdir")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)

    work = Path(a.workdir) if a.workdir else Path(tempfile.mkdtemp(
        prefix="dma-lifecycle-"))
    work.mkdir(parents=True, exist_ok=True)
    root = work / "run"
    registry = work / "registry.jsonl"
    env = {"DMA_RUN_REGISTRY": str(registry)}
    entity, eid, run_id = "Stress Credit Union", "stress-cu", "R-STRESS-LIFE"
    pf = work / "preflight.json"

    print(f"\nworkdir: {work}\n")

    # ── requirement 2 · the binding is a person's answer, not a sentence ──
    print("REQ 2 · the binding preflight")
    r = run("engine.preflight", "init", "--entity", entity,
            "--entity-id", eid, "--out", str(pf))
    check("preflight init writes a skeleton", pf.is_file() and r.returncode == 0)

    r = run("engine.preflight", "check", "--file", str(pf), expect=1)
    check("an empty preflight is refused",
          r.returncode == 1 and "financials" in r.stdout,
          r.stdout[-200:])

    doc = preflight_doc(entity, eid)

    unasked = json.loads(json.dumps(doc))
    unasked["binding_question"]["asked"] = False
    (work / "unasked.json").write_text(json.dumps(unasked))
    r = run("engine.preflight", "check", "--file", str(work / "unasked.json"),
            expect=1)
    check("an unasked binding question is refused",
          "asked is false" in r.stdout, r.stdout[-200:])

    mismatched = json.loads(json.dumps(doc))
    mismatched["binding"]["sub_vertical"] = "RB"
    (work / "mismatch.json").write_text(json.dumps(mismatched))
    r = run("engine.preflight", "check", "--file", str(work / "mismatch.json"),
            expect=1)
    check("a binding that contradicts the owner's answer is refused",
          "the engagement owner answered CU" in r.stdout, r.stdout[-200:])

    pf.write_text(json.dumps(doc, indent=2))
    r = run("engine.preflight", "check", "--file", str(pf))
    check("a complete preflight passes and derives its bases",
          r.returncode == 0 and "PREFLIGHT OK" in r.stdout
          and "revenue line(s) read from" in r.stdout, r.stdout[-300:])

    # ── requirements 1 + 5 · start opens the folder and registers the run ─
    print("\nREQ 1 · the client folder, opened at start")
    r = run("engine.cli", "start", "--run", run_id, "--root", str(root),
            "--entity", entity, "--entity-id", eid,
            "--reference-date", "2026-08-30", expect=2)
    check("start refuses without a preflight",
          r.returncode == 2 and "--preflight" in r.stderr,
          r.stderr[-200:])

    r, out = jrun("engine.cli", "start", "--run", run_id, "--root", str(root),
                  "--entity", entity, "--entity-id", eid,
                  "--reference-date", "2026-08-30",
                  "--preflight", str(pf),
                  "--folder-root", str(work / "clients"), "--no-push",
                  env=env)
    folder = work / "clients" / f"{entity} - DMA"
    check("start succeeds on the preflight", r.returncode == 0,
          r.stderr[-300:])
    check("the client folder exists before any research happens",
          folder.is_dir() and (folder / "run_manifest.json").is_file())
    manifest = json.loads((folder / "run_manifest.json").read_text()) \
        if (folder / "run_manifest.json").is_file() else {}
    check("its manifest says IN_PROGRESS",
          manifest.get("status") == "IN_PROGRESS", str(manifest)[:200])
    check("the binding was derived, not typed",
          out.get("binding", {}).get("sv") == "CU"
          and "engagement owner" in out.get("binding", {}).get("sv_basis", ""),
          json.dumps(out.get("binding", {}))[:250])
    check("the financial statement was banked as evidence",
          out.get("preflight", {}).get("evidence_banked") == ["E-001"],
          json.dumps(out.get("preflight", {}))[:200])

    print("\nREQ 5a · the run is logged where a later container can find it")
    check("the registry carries the run",
          registry.is_file() and run_id in registry.read_text())

    # ── requirement 3 · PRELIM gates category dispatch ───────────────────
    print("\nREQ 3 · PRELIM, before any category")
    r, o = jrun("engine.cli", "orient", "--run", run_id, "--root", str(root),
                "--category", "P1C1")
    check("orient withholds the card while PRELIM is open",
          o.get("next_card") is None
          and "PRELIM is open" in (o.get("next_card_withheld_because") or ""),
          str(o.get("next_card_withheld_because"))[:200])
    check("orient will not call the run clean", o.get("clean") is False)

    r = run("engine.prelim", "state", "--run", run_id, "--root", str(root),
            expect=1)
    check("PRELIM names financials as already closed by the preflight",
          "financials" in r.stdout and "RESEARCHED" in r.stdout,
          r.stdout[-400:])

    r = run("engine.cli", "evidence", "--run", run_id, "--root", str(root),
            "--source", "x", "--tier", "T2",
            "--excerpt", "y" * 60, expect=1)
    check("evidence that reaches no cell is refused unless declared profile",
          r.returncode == 1 and "--profile" in r.stderr, r.stderr[-200:])

    ev = json.loads(run("engine.cli", "evidence", "--run", run_id, "--root",
                        str(root), "--profile", "--source",
                        "NCUA Call Report — 2025 Q4 officer schedule",
                        "--url", "https://mapping.ncua.gov/ResearchCreditUnion",
                        "--tier", "T1", "--published", "2025-12-31",
                        "--excerpt",
                        "Stress Credit Union reports 412,000 members, 38 "
                        "branches and 1,240 full-time employees as at 31 "
                        "December 2025, with a named Chief Digital Officer "
                        "on the officer schedule.").stdout or "{}")
    eid2 = ev.get("e_id", "E-002")

    ok = True
    ok &= run("engine.prelim", "narrate", "--run", run_id, "--root", str(root),
              "--section", "firmographics", "--evidence", eid2,
              "--body", "Stress Credit Union is a state-chartered, federally "
                        "insured credit union serving 412,000 members through "
                        "38 branches with 1,240 full-time employees. Its "
                        "field of membership is geographic, and its balance "
                        "sheet is dominated by consumer lending."
              ).returncode == 0
    # THE FIRMOGRAPHICS TAB, not only the paragraph. `firmographics` closes on
    # both: every must-present field STATED, or ABSENT with the route that was
    # searched (the Client Profile's §1.1/§1.2 and the app's O2 strip read the
    # tab, and a paragraph with an empty tab is how 57 of 138 clients shipped
    # with no firmographics at all).
    for field, value, unit in (("website", "stress-cu.example", "n/a"),
                               ("employees", "1240", "headcount"),
                               ("assets_or_aum_or_revenue", "8.3bn", "USD assets"),
                               ("branches", "38", "count"),
                               ("headquarters", "Fresno, CA", "n/a"),
                               ("founded", "1947", "year"),
                               ("primary_regulator", "NCUA", "n/a"),
                               ("charter", "state-chartered credit union", "n/a"),
                               ("ownership", "member-owned cooperative", "n/a")):
        ok &= run("engine.profile", "firmographic", "--run", run_id, "--root",
                  str(root), "--field", field, "--value", value, "--unit", unit,
                  "--as-of", "2025-12-31", "--evidence", eid2,
                  "--confidence", "High").returncode == 0
    ok &= run("engine.profile", "firmographic", "--run", run_id, "--root", str(root),
              "--field", "cagr", "--state", "ABSENT",
              "--reason", "a credit union publishes no revenue CAGR; the call "
                          "report carries assets and shares by quarter, not a "
                          "growth series",
              "--route", "NCUA 5300 call reports FY2021-FY2025, searched "
                         "2026-08-30").returncode == 0
    # TWO NAMED PEOPLE is the floor: "a Chief Digital Officer reports to the
    # CEO" is a structure a researcher cannot search, match to a platform
    # decision, or date.
    ok &= run("engine.prelim", "narrate", "--run", run_id, "--root", str(root),
              "--section", "leadership", "--evidence", eid2,
              "--body", "Maria Alvarez has been Chief Digital Officer since "
                        "2022, reporting to chief executive Devon Whitfield, "
                        "alongside a CIO who owns the core platform. Both "
                        "roles predate the current programme, so the "
                        "institution is not standing up digital ownership "
                        "for the first time."
              ).returncode == 0
    # And what those named people say in public — the only PRELIM section in
    # the client's own voice, and the one a category finding is weighed against.
    ok &= run("engine.prelim", "narrate", "--run", run_id, "--root", str(root),
              "--section", "thought_leadership", "--evidence", eid2,
              "--body", "Maria Alvarez has spoken twice at industry "
                        "conferences on moving decisioning off the core, and "
                        "the institution's own 2025 report repeats that "
                        "framing. The stated direction is consistent across "
                        "both, so a category finding that contradicts it is "
                        "worth a second source rather than a restatement."
              ).returncode == 0
    # `--signal` is the event's DIRECTION and `--kind` its CLASS: the served
    # C1 surface clusters on one and filters on the other, and the tab used
    # to answer both with a single column drawn from a nine-token list that
    # mapped to neither.
    for d, e_, sig, kind in (
            ("2024-06-06", "Core digital banking platform selected",
             "POSITIVE", "PLATFORM"),
            ("2025-03-12", "AI credit decisioning went live",
             "POSITIVE", "DATA"),
            ("2025-09-08", "Credit-offer engine centralised",
             "NEUTRAL", "STRATEGY")):
        ok &= run("engine.prelim", "timeline", "--run", run_id, "--root",
                  str(root), "--date", d, "--event", e_, "--signal", sig,
                  "--kind", kind, "--evidence", eid2).returncode == 0
    ok &= run("engine.prelim", "peers", "--run", run_id, "--root", str(root),
              "--peer", "Peer Alpha CU", "--peer", "Peer Beta CU",
              "--rule", "US credit unions in the 5-15bn asset band with a "
                        "geographic field of membership and a public core "
                        "platform decision since 2022").returncode == 0
    # ALL FOUR LAYERS, in PRELIM. A layer nothing was found in is an ABSENT
    # row carrying the ladder — never a layer left out, which reads to every
    # later surface as a clean estate. Both contracted providers are named,
    # and a row is CONFIRMED only because a non-broker saw it too: two
    # brokers reselling one crawl is one observation.
    for product, vendor, layer, status, basis in (
            ("Alkami Digital Banking", "Alkami", "CUST", "CONFIRMED",
             "named as the digital banking platform in the 2025 call report"),
            ("Fiserv DNA", "Fiserv", "OPS", "CONFIRMED",
             "named as the core processor in the 2025 call report"),
            ("Snowflake", "Snowflake", "DATA", "INFERRED",
             "two 2025 engineering postings require production Snowflake"),
            ("public cloud hosting", "none named", "INFRA", "ABSENT",
             "searched the call report, the careers site and three vendor "
             "case-study indexes for a named hosting platform; none is "
             "stated anywhere public")):
        ok &= run("engine.cli", "techscan", "record", "--run", run_id, "--root",
                  str(root), "--product", product, "--vendor", vendor,
                  "--layer", layer, "--status", status,
                  "--method", "public_document", "--evidence-id", eid2,
                  "--provider", "clay", "--provider", "web",
                  "--basis", basis).returncode == 0
    check("every PRELIM section closes through the real commands", ok)

    r = run("engine.prelim", "complete", "--run", run_id, "--root", str(root))
    check("PRELIM signs off once its sections are closed", r.returncode == 0,
          r.stderr[-300:])

    r, o = jrun("engine.cli", "orient", "--run", run_id, "--root", str(root),
                "--category", "P1C1")
    check("closing PRELIM releases the category card",
          o.get("next_card") is not None,
          str(o.get("next_card_withheld_because"))[:200])

    # ── requirement 4 · the workbook has content, not just shape ──────────
    print("\nREQ 4 · every tab populated or stated")
    r = run("engine.cli", "validate", "--run", run_id, "--root", str(root))
    check("the workbook passes its SHAPE contract",
          r.returncode == 0 and "FAILS=0" in r.stdout, r.stdout[-200:])
    r = run("engine.completeness", "check", "--run", run_id, "--root",
            str(root), expect=1)
    check("...and completeness still blocks it, naming every empty tab",
          r.returncode == 1 and "DQ_Bank" in r.stdout, r.stdout[-300:])
    # Challenge_Log, not Gate_Log: a run that gated nothing records a
    # NOT_RUN gate row with its reason, so Gate_Log is NEVER_EMPTY and its
    # refusal is a different one.
    r = run("engine.completeness", "declare", "--run", run_id, "--root",
            str(root), "--sheet", "Challenge_Log", "--reason", "n/a",
            expect=1)
    check("a filler reason for an empty tab is refused",
          r.returncode == 1 and "filler" in r.stderr, r.stderr[-200:])
    r = run("engine.completeness", "declare", "--run", run_id, "--root",
            str(root), "--sheet", "Gate_Log", "--reason",
            "this stress walk records no gate at all", expect=1)
    check("a sheet the run cannot exist without may not be declared away",
          r.returncode == 1 and "cannot be declared empty" in r.stderr,
          r.stderr[-200:])
    r = run("engine.completeness", "declare", "--run", run_id, "--root",
            str(root), "--sheet", "Challenge_Log",
            "--reason", "this stress walk stops before any synthesis, so no "
                        "challenge was recorded and none is claimed")
    check("a real reason is accepted as a disclosure", r.returncode == 0,
          r.stderr[-200:])
    r = run("engine.cli", "handoff", "--run", run_id, "--root", str(root),
            expect=1)
    check("the handoff refuses a workbook with unexplained empty tabs",
          r.returncode == 1 and "empty" in (r.stdout + r.stderr).lower(),
          (r.stdout + r.stderr)[-300:])

    # ── requirement 5 · the watchdog sees it, and revives it ─────────────
    print("\nREQ 5b · a stopped run is seen and restarted")
    r, rows = jrun("engine.watchdog", "--root", str(work / "no-such-root"),
                   "--json", expect=None, env=env)
    seen = [x for x in (rows if isinstance(rows, list) else [])
            if x.get("run_id") == run_id]
    check("a container with an EMPTY run root still sees the run",
          bool(seen), json.dumps(rows)[:300] if not seen else "")
    check("a run that is merely working is left alone",
          bool(seen) and seen[0]["state"] == "PROGRESSING"
          and not seen[0]["resume"]["actionable"],
          json.dumps(seen[0] if seen else {})[:250])

    # now force the idle threshold: the run has categories open and has
    # written nothing since, which is what a mid-run stop looks like.
    r, rows = jrun("engine.watchdog", "--root", str(work / "no-such-root"),
                   "--stall-seconds", "0", "--json", expect=1, env=env)
    seen = [x for x in (rows if isinstance(rows, list) else [])
            if x.get("run_id") == run_id]
    check("past the stall threshold it reports STALLED",
          bool(seen) and seen[0]["state"] == "STALLED",
          json.dumps(seen[0] if seen else {})[:250])
    check("it carries a dispatchable resume plan naming an agent",
          bool(seen) and seen[0]["resume"]["actionable"]
          and seen[0]["resume"]["agent"].startswith("research-"),
          json.dumps(seen[0].get("resume") if seen else {})[:250])

    r, out = jrun("engine.watchdog", "--root", str(work / "no-such-root"),
                  "--stall-seconds", "0",
                  "--revive", "--dry-run", "--json", expect=None, env=env)
    revived = (out or {}).get("revived") or []
    check("--revive dispatches rather than reporting",
          any(v.get("outcome") == "DRY_RUN" and v.get("agent")
              for v in revived),
          json.dumps(revived)[:300])

    # the container-is-gone case: hide the workbook, keep the registry
    hidden = work / "hidden"
    shutil.move(str(root), str(hidden))
    r, rows = jrun("engine.watchdog", "--root", str(work / "no-such-root"),
                   "--json", expect=1, env=env)
    gone = [x for x in (rows if isinstance(rows, list) else [])
            if x.get("run_id") == run_id]
    check("a run whose workbook is GONE is reported, not forgotten",
          bool(gone) and gone[0]["state"] == "MISSING_LOCALLY",
          json.dumps(rows)[:300])
    check("and its recovery command is named",
          bool(gone) and gone[0].get("resume", {}).get("command"),
          json.dumps(gone[0].get("resume") if gone else {})[:200])
    shutil.move(str(hidden), str(root))

    passed = sum(1 for _, ok_, _ in RESULTS if ok_)
    print(f"\n{passed}/{len(RESULTS)} checks passed")
    for name, ok_, detail in RESULTS:
        if not ok_:
            print(f"  FAILED: {name}\n          {detail[:300]}")
    if not a.keep and not a.workdir:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"\nkept: {work}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
