#!/usr/bin/env python3
"""What share of real client packages can actually enter the system?

Owner, 2026-08-23: "Did you really fix the detection and ensure at least 70%
of the client would commence synthesis and not get rejected? ... no guessing."

That question has one honest answer and it is a measurement. A routine firing
on 2026-08-23 refused three consecutive packages — its client slot and both
reserves — and produced nobody; one of those refusals was later shown to be
a check looking for a `Caps_Applied_Log` SHEET while 1,035 cap records sat in
a COLUMN it never opened. Nobody knew the refusal rate, so nobody could see
that it had moved.

This runs the real vetter over every package on disk and reports the rate
with its denominators, plus WHY each refusal happened, ranked. It is the
instrument, not an opinion: it invokes `vet_workbooks.py` as a subprocess
per package, exactly as the package-vetter agent does, so what it measures
is what the vetter actually says.

    python3 vet_corpus.py                          # every package on disk
    python3 vet_corpus.py --root /root/.dma/packages --json out.json
    python3 vet_corpus.py --floor 0.70             # exit 1 below the floor

A package with no scoring workbook exits 2 from the vetter (it "could not
read the input"). That is NOT counted as a refusal of a producible package —
a briefing-only folder was never a synthesis input — but it IS counted and
reported separately, because a corpus that is 40% briefing-only is a fact
about the corpus that a refusal rate would otherwise hide.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
VETTER = (HERE.parent / "skills" / "dma-surface-production" / "scripts"
          / "vet_workbooks.py")
DEFAULT_ROOT = Path("/root/.dma/packages")

#: `[LEVEL] message` as vet_workbooks prints it under `=== findings`.
FINDING_RE = re.compile(r"^\[(REFUSE|WARN|PIN)\]\s*(.*)$")

#: Refusal reasons are long and carry counts; cluster them by their opening
#: clause so "26 score(s) outside 1.0-5.0" and "4 score(s) outside 1.0-5.0"
#: rank as one cause rather than two.
def cause(msg: str) -> str:
    m = re.sub(r"\d[\d,.]*", "N", msg)
    return m[:110].rstrip()


def vet(package: Path, timeout: int = 900) -> dict:
    """One package through the real vetter. Never raises: a package that
    crashes the vetter is a finding, not an interruption."""
    try:
        r = subprocess.run(
            [sys.executable, str(VETTER), str(package)],
            capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"package": package.name, "verdict": "TIMEOUT",
                "refusals": [], "warns": [], "pins": [],
                "detail": f"vetter exceeded {timeout}s"}
    except OSError as exc:                                     # noqa: BLE001
        return {"package": package.name, "verdict": "ERROR", "refusals": [],
                "warns": [], "pins": [], "detail": str(exc)}
    out = (r.stdout or "") + (r.stderr or "")
    refusals, warns, pins = [], [], []
    for line in out.splitlines():
        m = FINDING_RE.match(line.strip())
        if not m:
            continue
        {"REFUSE": refusals, "WARN": warns, "PIN": pins}[m.group(1)].append(
            m.group(2))
    if r.returncode == 2:
        verdict = "NOT_AN_INPUT"      # no scoring workbook: never was one
    elif refusals:
        verdict = "REFUSE"
    else:
        verdict = "PRODUCIBLE"        # clean, or warnings the vetter allows
    return {"package": package.name, "verdict": verdict, "exit": r.returncode,
            "refusals": refusals, "warns": warns, "pins": pins,
            "detail": out.strip().splitlines()[-1][:200] if out.strip() else ""}


def measure(root: Path, timeout: int = 900, manifest: list | None = None) -> dict:
    """`manifest` scopes the measurement to a NAMED set of package dirs.

    Without it the rate is "whatever is on disk", which drifts with every
    pull — a rate quoted against "the last 60 delivered DMAs" must be
    computed over exactly those 60. A manifest entry with no directory is
    counted as MISSING, never silently dropped: a package that could not be
    pulled shrinks the sample, and a shrunken sample must say so.
    """
    if manifest is not None:
        packages = [root / name for name in manifest]
        rows = [vet(p, timeout) if p.is_dir() else
                {"package": p.name, "verdict": "MISSING", "refusals": [],
                 "warns": [], "pins": [],
                 "detail": "named in the manifest, not on disk"}
                for p in packages]
    else:
        packages = sorted(p for p in root.iterdir() if p.is_dir()) \
            if root.is_dir() else []
        rows = [vet(p, timeout) for p in packages]
    counts = Counter(r["verdict"] for r in rows)
    # THE DENOMINATOR IS THE ARGUABLE PART, so it is stated rather than
    # chosen quietly. A package that was never a synthesis input cannot be
    # "rejected"; including it would let a corpus of briefing folders drag
    # a healthy vetter below any floor.
    considered = counts["PRODUCIBLE"] + counts["REFUSE"]
    rate = (counts["PRODUCIBLE"] / considered) if considered else None
    causes = Counter()
    for r in rows:
        for msg in r["refusals"]:
            causes[cause(msg)] += 1
    return {"root": str(root), "packages": len(rows), "counts": dict(counts),
            "considered": considered, "producible_rate": rate,
            "refusal_causes": causes.most_common(), "rows": rows}


def render(m: dict) -> str:
    out = [f"packages on disk: {m['packages']}  ({m['root']})", ""]
    for verdict in ("PRODUCIBLE", "REFUSE", "NOT_AN_INPUT", "TIMEOUT",
                    "ERROR", "MISSING"):
        if m["counts"].get(verdict):
            out.append(f"  {verdict:14} {m['counts'][verdict]}")
    out.append("")
    if m["producible_rate"] is None:
        out.append("producible rate: NOT MEASURABLE — no package was a "
                   "synthesis input, so there is no denominator")
    else:
        out.append(f"producible rate: {m['producible_rate']:.1%} "
                   f"({m['counts'].get('PRODUCIBLE', 0)} of {m['considered']} "
                   f"packages that carry scores)")
    if m["refusal_causes"]:
        out += ["", "refusal causes, most common first:"]
        out += [f"  {n:3}  {c}" for c, n in m["refusal_causes"]]
    refused = [r for r in m["rows"] if r["verdict"] == "REFUSE"]
    if refused:
        out += ["", "refused packages:"]
        for r in refused:
            out.append(f"  {r['package']}: {len(r['refusals'])} refusal(s)")
            for msg in r["refusals"][:3]:
                out.append(f"      {msg[:150]}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(DEFAULT_ROOT),
                    help="directory of pulled packages (default %(default)s)")
    ap.add_argument("--json", default=None, help="also write the full result here")
    ap.add_argument("--timeout", type=int, default=900,
                    help="per-package vetter timeout in seconds")
    ap.add_argument("--floor", type=float, default=None,
                    help="exit 1 if the producible rate is below this "
                         "(e.g. 0.70). Omit to report without judging")
    ap.add_argument("--manifest", default=None,
                    help="file of package dir names, one per line — scope "
                         "the measurement to exactly this set; entries not "
                         "on disk count as MISSING and are reported")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if not root.is_dir():
        print(f"no package directory at {root} — pull some first with "
              f"drive_fetch.py pull --client <display_id>", file=sys.stderr)
        return 2
    manifest = None
    if a.manifest:
        manifest = [ln.strip() for ln in
                    Path(a.manifest).read_text().splitlines() if ln.strip()]
        if not manifest:
            print(f"manifest {a.manifest} is empty — refusing to measure "
                  f"nothing and call it a rate", file=sys.stderr)
            return 2
    m = measure(root, a.timeout, manifest)
    print(render(m))
    if a.json:
        Path(a.json).write_text(json.dumps(m, indent=1))
        print(f"\nwrote {a.json}")
    if a.floor is None:
        return 0
    if m["producible_rate"] is None:
        print(f"\nFLOOR NOT EVALUATED: no denominator", file=sys.stderr)
        return 1
    if m["producible_rate"] < a.floor:
        print(f"\nBELOW FLOOR: {m['producible_rate']:.1%} < {a.floor:.0%}",
              file=sys.stderr)
        return 1
    print(f"\nat or above floor: {m['producible_rate']:.1%} >= {a.floor:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
