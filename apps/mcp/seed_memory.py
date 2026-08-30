"""Seed the findings memory from `dma_mcp.seed_corpus`.

Two modes, and the default is the one that proves something:

    python3 apps/mcp/seed_memory.py            # through the DEPLOYED connector
    python3 apps/mcp/seed_memory.py --direct   # straight at a local database

`--remote` (the default) calls the same MCP tools an agent would call, over the
capability URL, against production. That means a successful seed is also a
production test of `record_finding`, `record_refinement`, `resolve_finding` and
`report_recurrence` — including the refusals, since the corpus is written to
pass them and a schema change that breaks one shows up here immediately.

Idempotent by construction: `record_finding` dedups by content hash, sightings
dedup by `source_ref`, and `resolve_finding` is an UPDATE. Re-running adds one
sighting per finding at most (and none at all where the corpus sets a
`source_ref`), never a duplicate finding.

Never writes serving content. Nothing here bypasses a gate, because there is no
gate on the way in — a finding is not a client-facing claim.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dma_mcp.seed_corpus import CORPUS  # noqa: E402


def _remote_caller():
    from scripts.dma_connector import call
    return call


def _direct_caller():
    """A local connection, calling the module functions the tools wrap. Used
    when there is a migrated database on the machine and no deployed service
    to reach."""
    import pg8000.dbapi

    from dma_mcp import memory as mem

    url = os.environ.get(
        "LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
    host = url.split("@")[1].split(":")[0] if "@" in url else "localhost"
    conn = pg8000.dbapi.connect(
        user=os.environ.get("DB_USER", "dmai-mcp@digital-maturity-assessor.iam"),
        password="local", host=host, port=5432, database="dma_insights")

    def call(tool, **kw):
        if tool == "record_finding":
            return mem.record_finding(conn, kw["finding"])
        if tool == "record_refinement":
            return mem.record_refinement(conn, kw["refinement"])
        if tool == "resolve_finding":
            return mem.resolve_finding(conn, kw["finding_id"],
                                       kw["refinement_id"],
                                       verification=kw.get("verification"))
        if tool == "report_recurrence":
            return mem.report_recurrence(conn, kw.pop("finding_id"), **kw)
        if tool == "get_memory_digest":
            return mem.memory_digest(conn, kw.get("days", 7))
        raise SystemExit(f"--direct does not wire {tool}")
    return call


def seed(call, verbose=True) -> dict:
    recorded, refined, resolved, recurred, failed = [], [], [], [], []
    for entry in CORPUS:
        finding = dict(entry["finding"])
        out = call("record_finding", finding=finding)
        if out.get("errors"):
            failed.append({"title": finding["title"], "errors": out["errors"]})
            if verbose:
                print(f"  REFUSED  {finding['title'][:60]}: {out['errors']}")
            continue
        fid = out["finding_id"]
        recorded.append({"finding_id": fid, "title": finding["title"],
                         "deduped": out.get("deduped"),
                         "sightings": out.get("sightings")})
        if verbose:
            print(f"  {fid}  {'(deduped) ' if out.get('deduped') else ''}"
                  f"{finding['title'][:70]}")

        ref = entry.get("refinement")
        rid = None
        if ref:
            payload = dict(ref)
            payload["finding_ids"] = [fid]
            rout = call("record_refinement", refinement=payload)
            if rout.get("errors"):
                failed.append({"title": f"refinement for {fid}",
                               "errors": rout["errors"]})
                if verbose:
                    print(f"     refinement REFUSED: {rout['errors']}")
            else:
                rid = rout["refinement_id"]
                refined.append({"refinement_id": rid, "target": ref["target"]})
                if verbose:
                    print(f"     {rid} -> {ref['target']}")

        if entry.get("resolve") and rid:
            sout = call("resolve_finding", finding_id=fid, refinement_id=rid,
                        verification=ref.get("verification") or "")
            if sout.get("errors"):
                failed.append({"title": f"resolve {fid}",
                               "errors": sout["errors"]})
            else:
                resolved.append(fid)

        rec = entry.get("recurrence")
        if rec and rid:
            payload = dict(rec)
            payload["finding_id"] = fid
            payload.setdefault("after_refinement", rid)
            payload.setdefault("source_ref", f"seed-recurrence:{fid}")
            cout = call("report_recurrence", **payload)
            if cout.get("errors"):
                failed.append({"title": f"recurrence {fid}",
                               "errors": cout["errors"]})
            else:
                recurred.append({"finding_id": fid,
                                 "did_not_hold": cout.get(
                                     "refinement_that_did_not_hold")})
                if verbose:
                    print(f"     RECURRED against "
                          f"{cout.get('refinement_that_did_not_hold')}")

    return {"recorded": recorded, "refinements": refined,
            "resolved": resolved, "recurrences": recurred, "failed": failed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--direct", action="store_true",
                    help="call the module functions against a local database "
                         "instead of the deployed connector")
    ap.add_argument("--digest", action="store_true",
                    help="print the memory digest afterwards")
    args = ap.parse_args()

    call = _direct_caller() if args.direct else _remote_caller()
    print(f"seeding {len(CORPUS)} findings "
          f"({'direct' if args.direct else 'deployed connector'})")
    out = seed(call)
    print(f"\nrecorded={len(out['recorded'])} "
          f"refinements={len(out['refinements'])} "
          f"resolved={len(out['resolved'])} "
          f"recurrences={len(out['recurrences'])} "
          f"failed={len(out['failed'])}")
    for f in out["failed"]:
        print(f"  FAILED {f['title']}: {f['errors']}")
    if args.digest:
        print(json.dumps(call("get_memory_digest", days=7), indent=2,
                         default=str)[:4000])
    return 1 if out["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
