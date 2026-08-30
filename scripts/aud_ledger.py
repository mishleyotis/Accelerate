#!/usr/bin/env python3
"""What became of each audit finding — and RUN the proof, don't restate it.

    aud_ledger.py            summary by severity and disposition
    aud_ledger.py --open     the findings still open, worst first
    aud_ledger.py --verify   run every named check and report pass/fail
    aud_ledger.py --md       the table, as markdown

WHY THIS EXISTS. A remediation report that lists what was fixed is the same
artefact class as the acceptance ledger AUD-0050 caught claiming CI enforced
invariant 7 while nothing did. So each row names a runnable check, `--verify`
runs them, and a disposition whose check fails is reported as a FAILING CLAIM
rather than a fix.

`OPEN` is a first-class disposition and is printed by default. A ledger that
only shows the closed rows is a scoreboard, not a record.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LEDGER = ROOT / ".qa" / "AUD-DISPOSITIONS.json"
SEV_ORDER = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 3}
DISPOSITIONS = ("FIXED", "DESIGNED_OUT", "MITIGATED", "OPEN")


def load() -> dict:
    doc = json.loads(LEDGER.read_text())
    _refuse_unknown_vocabulary(doc)
    return doc


def _refuse_unknown_vocabulary(doc) -> None:
    """A ledger its own tool cannot read is not a record.

    Fourteen rows were filed `BLOCKING` against a SEV_ORDER that knows only
    `BLOCKER`, and every one of `--md`, `--verify` and the default summary
    died on a KeyError naming a dictionary — for weeks, because nothing runs
    this on a schedule and a traceback in a reporting tool looks like a tool
    problem rather than a data one. The vocabularies are small and closed;
    say which row broke them, and say it before doing any work.
    """
    bad_sev = sorted({r["sev"] for r in doc["findings"]
                      if r["sev"] not in SEV_ORDER})
    bad_disp = sorted({r["disposition"] for r in doc["findings"]
                       if r["disposition"] not in DISPOSITIONS})
    named = {r["id"] for r in doc["findings"]
             if r["sev"] not in SEV_ORDER
             or r["disposition"] not in DISPOSITIONS}
    missing = sorted({c for r in doc["findings"] for c in r.get("checks", ())
                      if c not in doc.get("checks", {})})
    problems = []
    if bad_sev:
        problems.append(f"severity {bad_sev} is not one of "
                        f"{sorted(SEV_ORDER)}")
    if bad_disp:
        problems.append(f"disposition {bad_disp} is not one of "
                        f"{list(DISPOSITIONS)}")
    if missing:
        problems.append(f"check name(s) {missing} have no command in the "
                        f"ledger's `checks` map, so --verify would silently "
                        f"prove nothing")
    if problems:
        raise SystemExit("the ledger is unreadable by its own tool: "
                         + "; ".join(problems)
                         + f" — rows: {sorted(named) or 'see above'}")


def summary(doc) -> int:
    rows = doc["findings"]
    print(f"{len(rows)} findings\n")
    width = max(len(d) for d in DISPOSITIONS)
    print(f"{'':<9}" + "".join(f"{d:>{width + 2}}" for d in DISPOSITIONS)
          + f"{'total':>8}")
    for sev in sorted({r["sev"] for r in rows}, key=lambda s: SEV_ORDER[s]):
        c = Counter(r["disposition"] for r in rows if r["sev"] == sev)
        line = f"{sev:<9}" + "".join(f"{c.get(d, 0):>{width + 2}}"
                                     for d in DISPOSITIONS)
        print(line + f"{sum(c.values()):>8}")
    c = Counter(r["disposition"] for r in rows)
    print(f"{'ALL':<9}" + "".join(f"{c.get(d, 0):>{width + 2}}"
                                  for d in DISPOSITIONS)
          + f"{len(rows):>8}")
    unchecked = [r["id"] for r in rows
                 if r["disposition"] in ("FIXED", "DESIGNED_OUT", "MITIGATED")
                 and not r["checks"]]
    if unchecked:
        print(f"\nCLAIMS WITH NO CHECK: {unchecked} — a disposition with "
              f"nothing to run is an assertion.")
        return 1
    return 0


def show_open(doc) -> int:
    rows = [r for r in doc["findings"] if r["disposition"] == "OPEN"]
    rows.sort(key=lambda r: (SEV_ORDER[r["sev"]], r["id"]))
    for r in rows:
        print(f"[{r['sev']:<7}] {r['id']}  {r['title'][:96]}")
        if r["target"]:
            print(f"            {r['target'][:100]}")
    print(f"\n{len(rows)} open "
          f"({sum(1 for r in rows if r['sev'] == 'BLOCKER')} BLOCKER)")
    return 0


def verify(doc) -> int:
    used = sorted({c for r in doc["findings"] for c in r["checks"]})
    failed = []
    for key in used:
        cmd = doc["checks"][key]
        print(f"── {key}: {cmd}")
        r = subprocess.run(cmd, shell=True, cwd=str(ROOT),
                           capture_output=True, text=True, timeout=1800)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        print(f"   {'PASS' if r.returncode == 0 else 'FAIL'}  {tail[0][:120]}")
        if r.returncode != 0:
            failed.append(key)
    if failed:
        claims = sorted({r["id"] for r in doc["findings"]
                         if set(r["checks"]) & set(failed)})
        print(f"\nFAILING CLAIMS: checks {failed} did not pass, so these "
              f"dispositions are UNPROVEN: {claims}")
        return 1
    print(f"\n{len(used)} check(s) pass; every non-OPEN disposition is "
          f"backed by one that runs.")
    return 0


def markdown(doc) -> int:
    rows = sorted(doc["findings"], key=lambda r: (SEV_ORDER[r["sev"]], r["id"]))
    print("| id | sev | disposition | finding | what was done |")
    print("|---|---|---|---|---|")
    for r in rows:
        note = r["note"].replace("|", "\\|")
        title = r["title"].replace("|", "\\|")
        print(f"| {r['id']} | {r['sev']} | {r['disposition']} | {title} "
              f"| {note} |")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--md", action="store_true")
    a = ap.parse_args(argv)
    doc = load()
    if a.open:
        return show_open(doc)
    if a.verify:
        return verify(doc)
    if a.md:
        return markdown(doc)
    return summary(doc)


if __name__ == "__main__":
    sys.exit(main())
