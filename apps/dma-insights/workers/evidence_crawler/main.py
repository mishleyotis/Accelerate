"""evidence_crawler Cloud Run Job entrypoint.

Usage (local):
  python -m workers.evidence_crawler.main --dry-run
  python -m workers.evidence_crawler.main --limit 50
  python -m workers.evidence_crawler.main --budget-sec 600 --min-support 0.30

Fills excerpt-empty evidence_index rows that have a fetchable URL by lifting a
cross-encoder-grounded passage from the cited page. Idempotent + additive.
"""
from __future__ import annotations

import argparse
import json
import sys

from workers.evidence_crawler import service as S


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="DMA Insights evidence_crawler worker")
    p.add_argument("--limit", type=int, default=None,
                   help="cap the number of rows attempted (default: all)")
    p.add_argument("--budget-sec", type=float, default=900.0,
                   help="global wall-clock budget; stops early past it")
    p.add_argument("--min-support", type=float, default=S.SUPPORT_FLOOR,
                   help=f"cross-encoder support floor to attach (default "
                        f"{S.SUPPORT_FLOOR})")
    p.add_argument("--dry-run", action="store_true",
                   help="fetch + score but write nothing")
    args = p.parse_args(argv)

    import os
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    import asyncio

    from workers.evidence_crawler.live import run
    result = asyncio.run(run(
        limit=args.limit, budget_sec=args.budget_sec,
        min_support=args.min_support, dry_run=args.dry_run,
    ))
    # Best-effort counter flush for the admin job pill.
    try:
        from workers._runner import get_current_tracker
        ex = get_current_tracker()
        if ex is not None and isinstance(result, dict):
            ex.update(rows_updated=int(result.get("filled", 0) or 0))
    except Exception:
        pass
    print(json.dumps({"evidence_crawler": result}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    from workers._runner import track_job_execution
    with track_job_execution("evidence_crawler"):
        sys.exit(main())
