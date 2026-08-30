#!/usr/bin/env python3
"""Materialise the staged page payloads of one run into a fixture directory.

WHY THIS EXISTS RATHER THAN THE PAYLOADS BEING COMMITTED.

`tests/skills/test_check_payload_false_positives.py` ends with six cases whose
claim cannot be made from unit fixtures: on a WHOLE payload the connector
accepted, the local checker raises none of the four repaired false-positive
classes. That needs a real passing run, and a real passing run is a real
client's assessment.

Measured on run d7ed1d90 (2026-08-20), the six pages carry 3 work email
addresses at the client's own domains, 7 named individuals' LinkedIn profile
URLs, 45 `r_layer` reasoning records and 34 `internal_only` blocks — about a
named institution, in a repository whose GitHub visibility is public. Staged
rows are verbatim by construction (`staged.py`: "not redacted, not the served
projection"), which is exactly what makes them worth testing against and
exactly what makes them unpublishable.

So the directory stays empty in git and this script fills it on any machine
that already holds connector credentials. The six cases skip in CI — stated in
the README and visible in the run's skip report — and run in one command for
anyone who can legitimately see the content.

    python3 scripts/fetch_staged_fixtures.py <run_id> [--slug logix]

Reassembly follows the tool's own contract: the section index first, then each
section, and a section over the inline budget by numbered part with its
`chunk` strings concatenated in order.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dma_connector import call  # noqa: E402

PAGES = ("overview", "insights", "heatmap", "platform", "context", "techstack")
ROOT = Path(__file__).resolve().parents[1]


def _section(run_id: str, page: str, name: str, described: dict):
    """One section's body, whole — inline if it fits, by part if it does not."""
    if described.get("inline", True):
        got = call("get_staged_payload", run_id=run_id, page=page, section=name)
        if "data" not in got:
            raise RuntimeError(
                f"{page}.{name}: {got.get('error', 'no data')} — "
                f"{got.get('hint', '')[:200]}")
        return got["data"]

    head = call("get_staged_payload", run_id=run_id, page=page, section=name)
    parts = head.get("parts")
    if not parts:
        raise RuntimeError(f"{page}.{name}: expected a part count, got {head}")
    chunks = []
    for i in range(1, parts + 1):
        got = call("get_staged_payload", run_id=run_id, page=page,
                   section=name, part=i)
        if "chunk" not in got:
            raise RuntimeError(f"{page}.{name} part {i}: {got.get('error')}")
        chunks.append(got["chunk"])
    return json.loads("".join(chunks))


def fetch_page(run_id: str, page: str) -> dict:
    index = call("get_staged_payload", run_id=run_id, page=page)
    if "sections" not in index:
        raise RuntimeError(
            f"{page}: {index.get('error', 'no section index')} — "
            f"{index.get('hint', '')[:200]}")
    return {name: _section(run_id, page, name, described)
            for name, described in index["sections"].items()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_id")
    ap.add_argument("--slug", required=True,
                    help="directory under fixtures/staged_runs/ to fill. "
                         "REQUIRED: this defaulted to one client's slug, so "
                         "a run id fetched without --slug landed in that "
                         "client's directory and looked like its data. "
                         "Naming the destination is cheaper than noticing")
    ap.add_argument("--pages", nargs="*", default=list(PAGES))
    args = ap.parse_args()

    out = ROOT / "fixtures" / "staged_runs" / args.slug
    out.mkdir(parents=True, exist_ok=True)

    failed = []
    for page in args.pages:
        try:
            payload = fetch_page(args.run_id, page)
        except Exception as e:                                   # noqa: BLE001
            print(f"  {page:10} FAILED  {e}", file=sys.stderr)
            failed.append(page)
            continue
        path = out / f"{page}.json"
        path.write_text(json.dumps(payload, indent=1, default=str))
        print(f"  {page:10} {len(payload):2} sections  "
              f"{path.stat().st_size:>9,} bytes")

    print(f"\n{out.relative_to(ROOT)} — these payloads are CLIENT CONTENT and "
          f"are gitignored.\nRun the six cases with:  "
          f"python3 -m pytest tests/skills/test_check_payload_false_positives.py")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
