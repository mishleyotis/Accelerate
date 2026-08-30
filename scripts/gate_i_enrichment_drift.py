#!/usr/bin/env python3
"""Gate I — a client is not done while enrichment is stranded.

THE PATTERN, reported by the owner on 2026-08-19 after three rounds of the
same defects: "the work was done but it is not showing". An enrichment ran —
in a producer session, in a scheduled scan, under a different account — and
the surface a reader opens did not have it. Leadership, why-now, sentiment
and the tech register each did this at least once.

There was no safeguard, and the absence was the root cause: nothing recorded
that a facet had been enriched, so nothing could notice that the promotion
lagged it. Migration 0051 records both halves; this gate is where the
recording turns into a refusal.

TWO MODES, because they answer different questions.

  (default)   THE MECHANISM. Is the safeguard actually wired — does promote
              record promotion state, does the drift view classify, does the
              summary refuse? Runs in CI with no database and no client.
              A safeguard nobody exercises is a comment.

  --entity X  THIS CLIENT. Is it done? Reads the live ledger through the
              connector and exits non-zero while any facet is
              `enriched_not_promoted` or `never_enriched`.

WHY NOT AT PROMOTE. A promote carrying five of seven facets forward is
better than no promote, and refusing it strands the five. "Done" is a claim
about the whole client; promote is a claim about one transaction. The
refusal belongs on the claim it contradicts.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "mcp"))

from dma_mcp import ledger  # noqa: E402


def check_mechanism() -> list[str]:
    """The wiring, asserted from the source rather than assumed."""
    bad = []

    promote = (ROOT / "apps" / "mcp" / "dma_mcp" / "promote.py").read_text()
    if "record_promotion_for_sections" not in promote:
        bad.append(
            "promote.py does not record promotion state. Every facet would "
            "stay at its last recorded version for ever, so the drift view "
            "would report `enriched_not_promoted` on work that IS live — a "
            "safeguard crying wolf is one that gets switched off.")
    if "ledger.summary" not in promote:
        bad.append(
            "promote.py does not report the drift back to its caller. The "
            "producer that just promoted is the one person positioned to fix "
            "a stranded facet, and telling them is free at that moment.")

    bundle = (ROOT / "apps" / "mcp" / "dma_mcp" / "bundle.py").read_text()
    if "ledger.summary" not in bundle:
        bad.append(
            "get_client_state does not report the drift. It is the call a "
            "producer makes to orient itself before touching a client.")

    migration = ROOT / "migrations" / "versions" / \
        "0051_enrichment_ledger_and_promotion_state.py"
    if not migration.exists():
        bad.append("migration 0051 is gone: there is no ledger to read.")
    else:
        src = migration.read_text()
        for want, why in (
            ("CREATE TABLE enrichment_ledger", "nothing records enrichment"),
            ("CREATE TABLE facet_promotion_state", "nothing records promotion"),
            ("CREATE VIEW enrichment_drift", "nothing compares the two"),
            ("next_enrichment_version", "versions would be minted client-side, "
                                        "so two producers collide"),
            ("ON DELETE CASCADE", "the ledger becomes a veto on deleting an "
                                  "entity"),
        ):
            if want not in src:
                bad.append(f"migration 0051 no longer creates `{want}` — {why}.")

    # The refusal itself, exercised rather than trusted.
    stranded = [{"facet": "leadership", "state": "enriched_not_promoted",
                 "enrichment_version": 2, "promoted_version": 1,
                 "enriched_at": None, "promoted_at": None}]
    if ledger.summary(stranded)["done"] is not False:
        bad.append("the summary calls a client done with a stranded facet.")
    clean = [{"facet": f, "state": "current", "enrichment_version": 1,
              "promoted_version": 1, "enriched_at": None, "promoted_at": None}
             for f in ledger.FACETS]
    if ledger.summary(clean)["done"] is not True:
        bad.append("the summary refuses a client whose every facet is current, "
                   "which makes the gate impossible to satisfy.")
    return bad


def check_entity(display_id: str) -> tuple[int, dict | None]:
    """The live ledger for one client, through the connector."""
    env = dict(os.environ)
    env["PATH"] = "/opt/google-cloud-sdk/bin:" + env.get("PATH", "")
    env.pop("CLOUDSDK_AUTH_ACCESS_TOKEN", None)   # the harness's junk token
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dma_connector.py"),
         "get_client_state", json.dumps({"display_id": display_id})],
        capture_output=True, text=True, env=env, timeout=300)
    if r.returncode != 0:
        print(f"gate I: could not read {display_id}: {r.stderr[-300:]}")
        return 2, None
    state = json.loads(r.stdout)
    if state.get("error"):
        print(f"gate I: {state['error']} for {display_id}")
        return 2, None
    return 0, state.get("enrichment")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity", help="display_id of a client to check live")
    args = ap.parse_args()

    if args.entity:
        rc, enrichment = check_entity(args.entity)
        if rc:
            return rc
        if not enrichment:
            print(f"gate I FAILED: {args.entity} reports no enrichment state. "
                  "The connector is older than migration 0051, or the ledger "
                  "read failed — either way the safeguard is not running.")
            return 1
        for row in enrichment["facets"]:
            mark = {"current": "ok  ", "enriched_not_promoted": "STUCK",
                    "never_enriched": "NONE"}.get(row["state"], "??  ")
            print(f"  {mark} {row['facet']:<20} "
                  f"enriched v{row['enrichment_version'] or '-'} "
                  f"promoted v{row['promoted_version'] or '-'}")
        if not enrichment["done"]:
            print(f"\ngate I FAILED: {args.entity} is not done.\n"
                  f"  {enrichment['reason']}")
            return 1
        print(f"\ngate I passed: every facet of {args.entity} is promoted at "
              "its newest enrichment.")
        return 0

    bad = check_mechanism()
    if bad:
        print(f"gate I FAILED: the enrichment safeguard is not wired "
              f"({len(bad)} problem(s)).\n")
        for b in bad:
            print(f"  · {b}\n")
        return 1
    print(f"gate I passed: the enrichment ledger is wired across "
          f"{len(ledger.FACETS)} facets, promote records promotion state, and "
          "a stranded facet refuses completion.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
