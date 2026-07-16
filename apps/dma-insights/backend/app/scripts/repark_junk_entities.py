"""Re-park / re-slug legacy junk-identity ACTIVE entities (runs every deploy).

The operator's deployed dashboard rendered raw Drive folder IDs
("1NYe2zU3wmBEvd8ZRFWEHpAGIUuK1O1L2"), engagement-folder noise ("VNO DMA
Engagement FINAL") and blank names as ACTIVE client cards. The insert-time
gate (entity_name_sanity, in package_persist) parks NEW junk-named entities
in PENDING_REVIEW — but it deliberately never demotes status on update, so
entities persisted BEFORE the gate stay ACTIVE forever and pollute the
directory/dashboard.

This idempotent §2c step closes two holes on every deploy:

1. **Junk NAME → demote.** Any ACTIVE entity whose current name fails
   check_institution_name (or is blank) moves to the migration-038
   PENDING_REVIEW admin queue with provenance. Frontend exclusion is
   automatic (every list reads status='ACTIVE').

2. **Folder-artifact display_id → re-slug.** The local-corpus root-finder
   can root a nested package at a canonical `NN_*` subfolder (e.g.
   Haventree / Wintrust at `03_scoring_workbook/`), so the FIRST run created
   the entity with institution_name="03_scoring_workbook" →
   display_id="03-scoring-workbook-6b9d". A later, correctly-rooted run
   UPDATEs entities.name to the real name but the display_id is the
   immutable UNIQUE key and stays malformed. We re-derive the slug from the
   (now-correct) name via the same `_display_id_for` helper the persist
   layer uses, so the slug matches every other client (haventree-bank-xxxx)
   and the card / route / startup-data filename are clean.

Clean clients are untouched; admins confirm/fix names in /admin.

  DATABASE_URL=... python -m app.scripts.repark_junk_entities [--dry-run]

Exit codes: 0 ok, 2 DB unreachable (DATABASE_URL unset).
"""
from __future__ import annotations

import asyncio
import os
import re
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.entity_name_sanity import check_institution_name
from app.services.parsers.package_persist import _display_id_for

# A display_id whose prefix is a canonical DMA package subfolder name — the
# tell-tale of a mis-rooted ingest. Matches `03-scoring-workbook-…`,
# `04-reports-…`, `08-appendices-…`, `02-research-workbook-…`, etc.
_FOLDER_ARTIFACT_RE = re.compile(
    r"^\d{2}-(scoring-workbook|reports|narrative-deck|peers|governance|"
    r"appendices|evidence|research-workbook|entity-profile|qa)\b",
    re.IGNORECASE,
)


async def main_async(dry_run: bool) -> int:
    url = os.environ.get("DATABASE_URL")
    if not url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(url)
    parked = 0
    reslugged = 0
    async with async_sessionmaker(engine)() as session:
        rows = (await session.execute(text(
            """
            SELECT e.id, e.display_id, e.name,
                   (SELECT r.request_id FROM runs r
                     WHERE r.entity_id = e.id
                     ORDER BY CASE r.status WHEN 'ACTIVE' THEN 0 ELSE 1 END,
                              r.completed_at DESC NULLS LAST, r.created_at DESC
                     LIMIT 1) AS request_id,
                   (SELECT count(DISTINCT LEFT(s.subcap_id, 2))
                      FROM subcap_scores s
                      JOIN runs r2 ON r2.id = s.run_id
                       AND r2.entity_id = e.id AND r2.status = 'ACTIVE'
                     WHERE LEFT(s.subcap_id, 2) IN ('P1','P2','P3','P4')
                   ) AS pillar_count
            FROM entities e
            WHERE e.status = 'ACTIVE'
            ORDER BY e.display_id
            """
        ))).all()
        existing = {r.display_id for r in rows}
        for r in rows:
            junk, reason = check_institution_name(r.name)
            if junk or not (r.name or "").strip():
                reason = reason or "blank_name"
                if not dry_run:
                    await session.execute(text(
                        """
                        UPDATE entities SET status='PENDING_REVIEW',
                            inferred_from_source = COALESCE(inferred_from_source,
                                'repark_junk_entities: ' || :why),
                            inferred_at = COALESCE(inferred_at, NOW()),
                            updated_at = NOW()
                        WHERE id = :id AND status='ACTIVE'
                        """), {"id": r.id, "why": reason})
                parked += 1
                print(f"  parked: {r.name!r} ({reason})")
                continue
            # Incomplete pillar coverage → demote. A real client card shows
            # all four P1-P4 mini-bars; an assessment missing a whole pillar
            # (e.g. ATB ships no P2 subcaps) renders a broken/gap card and
            # should not surface as a complete client. Moves to the
            # PENDING_REVIEW admin queue until a full-coverage run lands.
            if (r.pillar_count or 0) < 4:
                why = (f"incomplete_pillar_coverage {int(r.pillar_count or 0)}/4")
                if not dry_run:
                    await session.execute(text(
                        """
                        UPDATE entities SET status='PENDING_REVIEW',
                            inferred_from_source = COALESCE(inferred_from_source,
                                'repark_junk_entities: ' || :why),
                            inferred_at = COALESCE(inferred_at, NOW()),
                            updated_at = NOW()
                        WHERE id = :id AND status='ACTIVE'
                        """), {"id": r.id, "why": why})
                parked += 1
                print(f"  parked: {r.name!r} ({why})")
                continue
            # Clean name but folder-artifact slug → re-derive the slug.
            if _FOLDER_ARTIFACT_RE.match(r.display_id or ""):
                new_did = _display_id_for(r.name, r.request_id or "0001")
                if new_did != r.display_id and new_did not in existing:
                    if not dry_run:
                        await session.execute(text(
                            "UPDATE entities SET display_id=:new, updated_at=NOW() "
                            "WHERE id=:id"
                        ), {"new": new_did, "id": r.id})
                    existing.discard(r.display_id)
                    existing.add(new_did)
                    reslugged += 1
                    print(f"  reslug: {r.display_id} -> {new_did} ({r.name})")
        if not dry_run:
            await session.commit()
    await engine.dispose()
    print(f"# repark_junk_entities: scanned={len(rows)} parked={parked} "
          f"reslugged={reslugged}" + (" [DRY RUN]" if dry_run else ""))
    return 0


def main() -> int:
    return asyncio.run(main_async("--dry-run" in sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
