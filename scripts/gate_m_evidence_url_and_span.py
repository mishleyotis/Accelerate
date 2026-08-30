#!/usr/bin/env python3
"""Every served evidence item carries a URL, and every excerpt is ONE span.

THE DEFECT THIS MEASURES, and it was reported by the owner opening a drawer:
"I see no URLs on the T. Rowe evidence". Measured 2026-08-23 against the
production API, over the COMPLETE served set rather than a sample — which is
the whole point, because a sample of twenty would have found the twenty that
work:

    T. Rowe Price   894 served items   137 with a URL   (15%)
    Baxter (gold)   154 served items   153 with a URL   (99%)

The URLs were never missing from the package. `01_evidence/evidence_index.json`
carries 752 items with 748 URLs — 99% — and the ingest re-minted every one of
those ids into the `E-TROW-nnn` namespace WITHOUT the url column. 751 of 752
still join back numerically (E-002 -> E-TROW-002) and 747 URLs are recoverable
from the package this minute. Nothing had to be researched again; a field was
dropped in transit and nobody counted.

An evidence item with no URL is not a small blemish. Invariant 4 is
fail-closed evidence: a citation the reader cannot open is a claim they must
take on trust, and the drawer exists precisely so they do not have to.

THE SECOND CHECK, and it is the same failure wearing different clothes. An
"excerpt" that reads

    fact one about the CTO | fact two about modernization | fact three ab

is not a verbatim span of anything. It is three fragments joined with a pipe
and cut mid-word. 480 of 894 T. Rowe excerpts (53%) are that shape; Baxter has
1 of 154 (0.6%). It clears every length floor, so a floor-based check calls it
healthy — which is exactly what happened.

WHY A SEPARATE GATE FROM G. `gate_g_citable_evidence.py` deliberately
DISCLOSES rather than blocks, because thinness is partly a fact about the
public record. Neither of these is: a URL the package already holds, and a
span that was stitched after the fact, are both defects of transit. They fail.

    gate_m_evidence_url_and_span.py --evidence <get_evidence-shaped JSON>
    gate_m_evidence_url_and_span.py --api --entity <slug>     # the live set

Exit 0 clean, 1 on a breach.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: A stitched composite: two or more SENTENCE-LENGTH fragments joined by a
#: pipe. Both halves have to be substantial, because a single pipe inside real
#: prose is not structure — E-482's excerpt is a job posting reading "Platform
#: Engineer | Solutions Engineer | GCP, AWS, Snowflake", which is verbatim and
#: full of pipes. Requiring 30+ characters on each side separates "one quote
#: that happens to contain a pipe" from "three facts glued together".
#:
#: An earlier version of this rule anchored on word characters immediately
#: before the pipe (`[\w]{20,}\s\|`) and matched NOTHING, because the text
#: before a pipe is prose and prose contains spaces. It reported 0 stitched on
#: a set with 480. A check that cannot fire is worse than no check, so this
#: one is asserted against both real corpora in its test.
#:
#: THE THRESHOLD IS MEASURED, and the measurement also names the mechanism.
#: Across the 480 stitched T. Rowe excerpts (1256 fragments) the fragment
#: lengths run min 79, median 140, max 140 — near-uniform, pinned to a
#: 140-character budget, because each one is a FACT TRUNCATED TO FIT and then
#: glued to the next. E-482's job posting runs 17, 18, 50, 52. There is a
#: clean gap between 52 and 79 with nothing in it, so 70 separates them with
#: margin on both sides and is not fitted to either example.
STITCH_FRAGMENT_CHARS = 70


def _is_stitched(text: str) -> bool:
    parts = [p.strip() for p in text.split(" | ")]
    if len(parts) < 2:
        return False
    long_parts = [p for p in parts if len(p) >= STITCH_FRAGMENT_CHARS]
    return len(long_parts) >= 2


URL_RE = re.compile(r"^https?://", re.I)

#: A URL that resolves to the entity's own front door is not a location where
#: the claim can be checked. Explorium/Vibe-Prospecting technographic scans
#: are minted with exactly that: 18 T. Rowe items carry
#: `https://troweprice.com` and nothing more specific, because a machine
#: observation has no document behind it. That is honest as an ORIGIN and
#: dishonest as a CITATION, so it is counted and named rather than passed.
BARE_HOST_RE = re.compile(r"^https?://[^/]+/?$", re.I)


def _url_of(row: dict) -> str:
    for k in ("source_url", "url", "link", "source_link"):
        v = str(row.get(k) or "").strip()
        if v:
            return v
    return ""


def _excerpt_of(row: dict) -> str:
    for k in ("excerpt", "verbatim_quote", "anchor_quote", "quote"):
        v = str(row.get(k) or "").strip()
        if v:
            return v
    return ""


def audit(rows: list) -> dict:
    total = len(rows)
    no_url, bare_host, stitched = [], [], []
    for r in rows:
        eid = r.get("e_id") or r.get("evidence_id") or "(no id)"
        url = _url_of(r)
        if not URL_RE.match(url):
            no_url.append(eid)
        elif BARE_HOST_RE.match(url):
            bare_host.append(eid)
        ex = _excerpt_of(r)
        if ex and _is_stitched(ex):
            stitched.append(eid)
    breaches = []
    if no_url:
        breaches.append(
            f"{len(no_url)} of {total} served evidence items carry no URL "
            f"(e.g. {no_url[:5]}). A citation the reader cannot open is a "
            f"claim they must take on trust. Check the package's own "
            f"01_evidence/evidence_index.json before researching anything: "
            f"on the run that prompted this gate, 747 of them were already "
            f"there and had simply not been carried across.")
    if stitched:
        breaches.append(
            f"{len(stitched)} excerpt(s) are several fragments joined with "
            f"' | ' (e.g. {stitched[:5]}). That is not a verbatim span of any "
            f"source. Take ONE continuous sentence, or register the row with "
            f"no excerpt and let it go out as a gap.")
    warnings = []
    if bare_host:
        warnings.append(
            f"{len(bare_host)} item(s) cite a bare hostname with no path "
            f"(e.g. {bare_host[:5]}). A technographic scan has no document "
            f"behind it; say so in the source name rather than pointing the "
            f"reader at a home page as though the claim were on it.")
    return {"total": total, "no_url": no_url, "bare_host": bare_host,
            "stitched": stitched, "breaches": breaches,
            "warnings": warnings}


def _rows_from(raw) -> list:
    if isinstance(raw, list):
        return raw
    for k in ("items", "found", "evidence", "data"):
        v = raw.get(k) if isinstance(raw, dict) else None
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for kk in ("items", "evidence"):
                if isinstance(v.get(kk), list):
                    return v[kk]
    return []


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--evidence", help="a get_evidence-shaped JSON file")
    ap.add_argument("--api", action="store_true",
                    help="read the live served set through the API")
    ap.add_argument("--entity", help="slug, with --api")
    ap.add_argument("--base", default="https://dmai-api-dukrne5v4a-uc.a.run.app")
    a = ap.parse_args()

    if a.api:
        if not a.entity:
            print("--api needs --entity", file=sys.stderr)
            return 2
        import subprocess
        import urllib.request
        tok = subprocess.run(
            ["gcloud", "auth", "print-identity-token",
             f"--audiences={a.base}"],
            capture_output=True, text=True).stdout.strip()
        req = urllib.request.Request(
            f"{a.base}/v1/entities/{a.entity}/evidence?audience=internal",
            headers={"Authorization": f"Bearer {tok}"})
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = json.loads(r.read())
    elif a.evidence:
        raw = json.loads(Path(a.evidence).read_text())
    else:
        print("nothing to audit: pass --evidence or --api --entity")
        return 0

    rows = _rows_from(raw)
    rep = audit(rows)
    print(f"served evidence items   {rep['total']}")
    print(f"without a URL           {len(rep['no_url'])}")
    print(f"bare-hostname URL       {len(rep['bare_host'])}")
    print(f"stitched excerpts       {len(rep['stitched'])}")
    for b in rep["breaches"]:
        print(f"\nBREACH   {b}")
    for w in rep["warnings"]:
        print(f"\nwarning  {w}")
    return 1 if rep["breaches"] else 0


if __name__ == "__main__":
    sys.exit(main())
