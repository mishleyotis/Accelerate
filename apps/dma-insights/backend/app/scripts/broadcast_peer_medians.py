"""Cohort-fallback peer-median broadcast (2026-06-10).

The ingest-time broadcast (package_persist) fills
``subcap_scores.peer_median`` from the PACKAGE's own
``category_scores.peer_median``. 11 corpus packages shipped no
category-level peer medians at all, so every peer surface (D1 pillar
ticks, D3 overlay, delta arrows) rendered the dash placeholder for
those entities even though their subvertical cohort is fully
benchmarked in ``peer_benchmarks`` (built from the rest of the corpus's
peer_comparison_table.csv files).

This script broadcasts the COHORT median onto any ACTIVE run's subcap
rows that are still NULL: per entity subvertical, per category
(``peer_benchmarks.subcap_id`` is category-grain, e.g. ``P1C1``),
``peer_median = AVG(median)`` of the cohort rows for that category.
Package-shipped values are never overwritten (``peer_median IS NULL``
guard) — same precedence rule as the ingest broadcast.

Idempotent; safe to run on every deploy (post-deploy-refresh.sh).

Usage:
  DATABASE_URL=postgresql+asyncpg://... python -m app.scripts.broadcast_peer_medians
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


async def main_async() -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as session:
        res = await session.execute(text(
            """
            WITH cohort AS (
                SELECT subvertical, subcap_id AS category_id,
                       AVG(median) AS pm
                FROM peer_benchmarks
                WHERE median IS NOT NULL
                GROUP BY subvertical, subcap_id
            )
            UPDATE subcap_scores ss SET
                peer_median = c.pm,
                peer_gap = ROUND((ss.score - c.pm)::numeric, 2)
            FROM runs r
            JOIN entities e ON e.id = r.entity_id
            JOIN cohort c ON c.subvertical = e.subvertical
            WHERE r.status = 'ACTIVE'
              AND ss.run_id = r.id
              AND ss.peer_median IS NULL
              AND ss.score IS NOT NULL
              AND (ss.parent_category_id = c.category_id
                   OR split_part(ss.subcap_id, '.', 1) = c.category_id)
            """
        ))
        await session.commit()
        n = res.rowcount or 0
        left = (await session.execute(text(
            """
            SELECT count(DISTINCT e.display_id)
            FROM subcap_scores ss
            JOIN runs r ON r.id = ss.run_id AND r.status = 'ACTIVE'
            JOIN entities e ON e.id = r.entity_id
            WHERE ss.peer_median IS NULL AND ss.score IS NOT NULL
            """
        ))).scalar()
    await engine.dispose()
    print(f"# broadcast_peer_medians: rows filled={n}; "
          f"entities still without medians={left} "
          f"(NULL-subvertical or uncovered cohort — honest empty)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
