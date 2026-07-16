"""Backfill evidence_index.recency_months (self-healing, deterministic).

evidence_index ships `published_date` for ~74% of rows but `recency_months` was
never populated at ingest, so the freshness signal was published_date-only. This
fills recency_months = age (in months) of each dated evidence row at its run's
ASSESSMENT date (stable, not wall-clock), completing the freshness signal that
`evidence_staleness.compute_band` / the freshness_band trigger consume.

Fill-if-empty only (rows with a published_date and a NULL recency_months);
idempotent. New ingests now compute it inline (package_persist._recency_months).

Usage: DATABASE_URL=... python -m app.scripts.backfill_recency
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text

from app.database import get_sessionmaker


async def _amain() -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    async with sm() as session:
        # age in whole months from published_date to the run's assessment_date
        # (fallback CURRENT_DATE when the run carries no assessment_date).
        res = await session.execute(text(
            """
            UPDATE evidence_index e SET recency_months = GREATEST(0,
                (EXTRACT(YEAR  FROM age(COALESCE(r.assessment_date, CURRENT_DATE), e.published_date)) * 12
               + EXTRACT(MONTH FROM age(COALESCE(r.assessment_date, CURRENT_DATE), e.published_date)))::int)
            FROM runs r
            WHERE e.run_id = r.id
              AND e.published_date IS NOT NULL
              AND e.recency_months IS NULL
            """))
        filled = res.rowcount or 0
        # rows with no run join (run_id NULL) but a published_date → vs today.
        res2 = await session.execute(text(
            """
            UPDATE evidence_index e SET recency_months = GREATEST(0,
                (EXTRACT(YEAR  FROM age(CURRENT_DATE, e.published_date)) * 12
               + EXTRACT(MONTH FROM age(CURRENT_DATE, e.published_date)))::int)
            WHERE e.published_date IS NOT NULL AND e.recency_months IS NULL
            """))
        filled += res2.rowcount or 0
        # the freshness_band trigger fires on UPDATE OF recency_months, so bands
        # refresh automatically; nudge any row the trigger didn't touch.
        cov = (await session.execute(text(
            "SELECT count(*) FILTER (WHERE recency_months IS NOT NULL), "
            "count(*) FILTER (WHERE published_date IS NOT NULL), count(*) FROM evidence_index"
        ))).first()
        await session.commit()
    print(f"# backfill_recency: filled={filled} | recency_now={cov[0]} "
          f"dated={cov[1]} total={cov[2]}", flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
