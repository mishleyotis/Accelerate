"""Repair runs.assessment_date for already-ingested rows (migration 039).

QA audit 2026-06-11: every backfilled run carried ``started_at = NOW()``
(the ingest wall-clock) and the UI's RUN DATE bound to it — so the whole
96-DMA corpus rendered the ingest day instead of the assessment date.
Fresh ingests now persist ``assessment_date`` via ``package_persist``
(fallback chain in ``parsers/run_id.compute_assessment_date``); this
script repairs rows ingested BEFORE that fix **without re-ingest**, by
re-deriving the date from ``request_id`` alone:

  DMA-ASM-{ENTITY}-{YYYYMMDD}-{NNNN} → YYYYMMDD  (source='run_id')
  REQ-{8 hex} / unparseable           → left NULL (read-side falls back
                                        to started_at; UI may flag it)

``overall_score`` is deliberately NOT repaired here — the official value
only exists inside the package manifests, which this script does not
have. NULL keeps the read-side pillar-mean derivation, identical to the
pre-039 behavior; the next re-ingest of an entity fills it.

Idempotent (only touches rows where assessment_date IS NULL); safe on
every deploy. Run once after migrating to 039:

  DATABASE_URL=postgresql+asyncpg://... \
      python -m app.scripts.backfill_run_dates [--dry-run]
"""
from __future__ import annotations

import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.parsers.run_id import compute_assessment_date


async def main_async(dry_run: bool = False) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as session:
        rows = (await session.execute(text(
            """
            SELECT id, request_id FROM runs
            WHERE assessment_date IS NULL
            ORDER BY created_at
            """
        ))).all()

        repaired = 0
        unparseable = 0
        for r in rows:
            adate, source = compute_assessment_date(None, r.request_id, None)
            if adate is None:
                unparseable += 1
                continue
            if not dry_run:
                await session.execute(
                    text(
                        """
                        UPDATE runs
                        SET assessment_date=:adate,
                            assessment_date_source=:src
                        WHERE id=:rid AND assessment_date IS NULL
                        """
                    ),
                    {"adate": adate, "src": source, "rid": r.id},
                )
            repaired += 1

        if not dry_run:
            await session.commit()
    await engine.dispose()
    print(
        f"# backfill_run_dates: scanned={len(rows)} repaired={repaired} "
        f"left_null={unparseable} (REQ-hex / unparseable ids — read-side "
        f"falls back to started_at)"
        + (" [DRY RUN]" if dry_run else "")
    )
    return 0


def main() -> int:
    dry = "--dry-run" in sys.argv[1:]
    return asyncio.run(main_async(dry_run=dry))


if __name__ == "__main__":
    raise SystemExit(main())
