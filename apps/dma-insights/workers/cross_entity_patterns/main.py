"""cross_entity_patterns Cloud Run Job entrypoint.

Usage (local):
  python -m workers.cross_entity_patterns.main --subvertical CU
  python -m workers.cross_entity_patterns.main --all --dry-run

Reads every ACTIVE run's subcap_scores (below-peer-median gaps) + open
issue_register rows for the target subvertical(s), finds the sub-capabilities
that recur across >= 3 entities, and writes cross_entity_patterns.

State transitions:
  --subvertical X with no ACTIVE runs in X → exits 0; no rows written
  cohort < 3 entities                      → one "insufficient_data" row
  --dry-run                                → prints the scope; no DB writes
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="DMA Insights cross_entity_patterns worker")
    parser.add_argument("--subvertical", help="single subvertical code (e.g. CU)")
    parser.add_argument("--all", action="store_true",
                        help="run for every distinct subvertical")
    parser.add_argument("--catalogue-version", default=None,
                        help="override catalogue version filter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.subvertical and not args.all:
        print("cross_entity_patterns: one of --subvertical or --all required",
              file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({
            "mode": "dry-run",
            "subvertical": args.subvertical,
            "all": args.all,
            "catalogue_version": args.catalogue_version,
            "next_step": "Without --dry-run, the worker reads subcap_scores + "
                         "issue_register from ACTIVE runs, finds sub-caps "
                         "recurring across >= 3 entities, writes "
                         "cross_entity_patterns rows.",
        }, indent=2))
        return 0

    import asyncio

    from workers.cross_entity_patterns.live import run

    result = asyncio.run(run(
        subvertical=args.subvertical,
        all_subverticals=args.all,
        catalogue_version=args.catalogue_version,
    ))
    # Best-effort counter flush so the admin pill shows patterns written.
    try:
        from workers._runner import get_current_tracker
        ex = get_current_tracker()
        if ex is not None and isinstance(result, dict):
            ex.update(rows_added=int(result.get("patterns_written", 0) or 0))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("cross_entity_patterns"):
        sys.exit(main())
