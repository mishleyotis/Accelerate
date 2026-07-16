"""peer_patterns Cloud Run Job entrypoint.

Usage (local):
  python -m workers.peer_patterns.main --subvertical CU
  python -m workers.peer_patterns.main --all --dry-run

Reads every ACTIVE run's subcap_scores for the target subvertical(s),
clusters entities via the pure helpers in service.py, writes the result
to peer_archetypes.

State transitions:
  --subvertical X with no ACTIVE runs in X
    → exits 0 with a "no-op" summary; no peer_archetypes rows written
  cohort < 3 entities
    → writes a single "insufficient_data" archetype row
  --dry-run
    → prints the archetypes JSON; no DB writes
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DMA Insights peer_patterns worker")
    parser.add_argument("--subvertical", help="single subvertical code (e.g. CU)")
    parser.add_argument("--all", action="store_true",
                        help="run for every distinct subvertical")
    parser.add_argument("--catalogue-version", default=None,
                        help="override catalogue version filter")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    if not args.subvertical and not args.all:
        print("peer_patterns: one of --subvertical or --all required",
              file=sys.stderr)
        return 2

    if args.dry_run:
        # Synthesize the no-IO summary path so an operator can confirm
        # scope before flipping to live.
        print(json.dumps({
            "mode": "dry-run",
            "subvertical": args.subvertical,
            "all": args.all,
            "catalogue_version": args.catalogue_version,
            "next_step": "Without --dry-run, the worker reads subcap_scores "
                         "from ACTIVE runs, clusters via KMeans, writes "
                         "peer_archetypes rows.",
        }, indent=2))
        return 0

    import asyncio

    from workers.peer_patterns.live import run

    result = asyncio.run(run(
        subvertical=args.subvertical,
        all_subverticals=args.all,
        catalogue_version=args.catalogue_version,
    ))
    # Best-effort counter flush so the admin pill shows archetypes
    # written. `result` is whatever the live runner returns — typically
    # None or a dict; we tolerate both.
    try:
        from workers._runner import get_current_tracker
        ex = get_current_tracker()
        if ex is not None and isinstance(result, dict):
            ex.update(
                rows_added=int(result.get("archetypes_written", 0) or 0),
                rows_updated=int(result.get("archetypes_updated", 0) or 0),
            )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("peer_patterns"):
        sys.exit(main())
