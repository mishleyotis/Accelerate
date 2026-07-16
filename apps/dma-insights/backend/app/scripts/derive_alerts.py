"""Corpus-wide thin-evidence alert backfill (QA 2026-06-11).

Fresh ingests derive THIN_EVIDENCE alerts inline (package_persist →
services/alerts_producer). This script backfills the already-ingested
corpus: one derivation per ACTIVE run, identical producer code path —
per-subcap alerts below the per-category aggregation threshold, one
aggregated alert per category above it, severity high/medium per the
wireframe buildAlerts contract, waived (closed) content_keys never
resurrected.

Feeds: Alerts page table, dashboard OPEN ALERTS KPI + Needs-attention
card, sidebar badge, entity open_alerts counts, D6 Health tab dot +
thin-evidence table.

Idempotent (re-derives replace OPEN derived rows only); safe on every
deploy. Pinned in DEPLOYMENT.md §2c between derive_focus_areas and
enrich_corpus.

Usage:
  DATABASE_URL=postgresql+asyncpg://... \
      python -m app.scripts.derive_alerts [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.alerts_producer import derive_thin_evidence_alerts


async def main_async(dry_run: bool, limit: int | None) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as session:
        runs = (await session.execute(text(
            """
            SELECT r.id AS run_id, r.entity_id, e.display_id
            FROM runs r
            JOIN entities e ON e.id = r.entity_id
            WHERE r.status = 'ACTIVE' AND e.status = 'ACTIVE'
            ORDER BY e.display_id
            """ + (" LIMIT :lim" if limit else "")
        ), ({"lim": limit} if limit else {}))).all()

        total_inserted = 0
        total_skipped = 0
        for r in runs:
            counters = await derive_thin_evidence_alerts(
                session, run_id=str(r.run_id), entity_id=str(r.entity_id),
            )
            total_inserted += counters["alerts_inserted"]
            total_skipped += counters["skipped_closed"]

        if dry_run:
            await session.rollback()
        else:
            await session.commit()
    await engine.dispose()
    print(
        f"# derive_alerts: runs={len(runs)} alerts_inserted={total_inserted} "
        f"waived_preserved={total_skipped}"
        + (" [DRY RUN — rolled back]" if dry_run else "")
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="derive_alerts")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    return asyncio.run(main_async(args.dry_run, args.limit))


if __name__ == "__main__":
    raise SystemExit(main())
