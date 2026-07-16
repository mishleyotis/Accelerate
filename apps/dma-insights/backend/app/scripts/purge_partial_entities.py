"""Purge partial-ingest debris + park junk-named entities (2026-06-10).

WHY: before the strict ingest gate landed, the backfill persisted
packages with ZERO subcap scores ("narrative-first" partials). On the
live app these rendered as hollow entities — empty ScoreRing, blank
heatmap, "—" firmographics — alongside entities named after raw Drive
folder IDs and deliverable noise. The operator's decisions:

  1. zero-score entities → DELETE after backup (the next Drive crawl
     then sees the folder as never-ingested; the strict gate keeps it
     out until the scored deliverable lands, at which point it ingests
     cleanly).
  2. scored entities with junk names → flip to status='PENDING_REVIEW'
     (migration-038 admin queue at /api/v1/admin/pending-review; AE
     list/dashboard/cohort surfaces filter status='ACTIVE').
  3. cross-wire REPORT (no auto-fix): document_sections rows whose
     snapshot entity_id differs from the owning run's entity_id — the
     mechanism that put FNBO's SCQA on another client's Overview.

SAFETY CONTRACT
  - DRY-RUN BY DEFAULT: prints the full candidate table and exits 0
    without writing. `--apply` executes.
  - Run `infra/backup-before-heal.sh` BEFORE `--apply` (runbook
    DEPLOYMENT.md §22.5).
  - Per-entity transactions: a failure on one entity never poisons the
    rest; deletes rely on the schema's ON DELETE CASCADE (verified:
    every child of entities/runs cascades; peer_benchmarks is
    cohort-keyed and untouched).
  - Idempotent: a second run finds zero candidates.

Exit codes: 0 = clean (including dry-run); 1 = one or more per-entity
operations failed (details on stdout).
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.services.entity_name_sanity import check_institution_name

_ZERO_SCORE_SQL = """
    SELECT e.id::text AS id, e.display_id, e.name, e.status,
           (SELECT COUNT(*) FROM runs r WHERE r.entity_id = e.id) AS run_count
    FROM entities e
    WHERE NOT EXISTS (
        SELECT 1 FROM runs r
        JOIN subcap_scores s ON s.run_id = r.id
        WHERE r.entity_id = e.id
    )
    ORDER BY e.display_id
"""

_ACTIVE_NAMES_SQL = """
    SELECT e.id::text AS id, e.display_id, e.name
    FROM entities e
    WHERE e.status = 'ACTIVE'
    ORDER BY e.display_id
"""

_CROSS_WIRE_SQL = """
    SELECT DISTINCT ds.run_id::text AS run_id,
           ds.entity_id::text AS section_entity,
           r.entity_id::text AS run_entity,
           se.display_id AS section_entity_display,
           re.display_id AS run_entity_display
    FROM document_sections ds
    JOIN runs r ON r.id = ds.run_id
    LEFT JOIN entities se ON se.id = ds.entity_id
    LEFT JOIN entities re ON re.id = r.entity_id
    WHERE ds.entity_id <> r.entity_id
"""

_SYNTH_RUNS_SQL = """
    SELECT r.request_id, e.display_id
    FROM runs r JOIN entities e ON e.id = r.entity_id
    WHERE r.request_id LIKE 'SYNTH-%'
    ORDER BY e.display_id
"""


async def main() -> int:
    apply = "--apply" in sys.argv[1:]
    engine = create_async_engine(get_settings().database_url, echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    failed = 0
    try:
        # ── 1. Zero-score entities (partial-ingest debris) ────────────
        async with sm() as session:
            zero_rows = (await session.execute(text(_ZERO_SCORE_SQL))).all()
        print(
            f"# 1. zero-score entities (delete candidates): "
            f"{len(zero_rows)}", flush=True,
        )
        for r in zero_rows:
            print(
                f"  DELETE  {r.display_id:42} {r.name!r:45} "
                f"runs={r.run_count} status={r.status}", flush=True,
            )
        if apply:
            for r in zero_rows:
                try:
                    # Re-derive INSIDE the transaction: a concurrent
                    # ingest may have scored this entity since dry-run.
                    async with sm() as session:
                        still = (await session.execute(
                            text(
                                "SELECT 1 FROM entities e WHERE e.id = "
                                "CAST(:id AS uuid) AND NOT EXISTS ("
                                "  SELECT 1 FROM runs r JOIN subcap_scores s"
                                "    ON s.run_id = r.id "
                                "  WHERE r.entity_id = e.id)"
                            ),
                            {"id": r.id},
                        )).first()
                        if still is None:
                            print(
                                f"  SKIP    {r.display_id} — gained scores "
                                f"since dry-run scan", flush=True,
                            )
                            continue
                        # The migration-015 hard-delete guard (DB
                        # trigger) blocks DELETE while status=ACTIVE —
                        # archive first, in the SAME transaction.
                        await session.execute(
                            text("UPDATE entities SET status='ARCHIVED' "
                                 "WHERE id = CAST(:id AS uuid)"),
                            {"id": r.id},
                        )
                        await session.execute(
                            text("DELETE FROM entities "
                                 "WHERE id = CAST(:id AS uuid)"),
                            {"id": r.id},
                        )
                        await session.commit()
                        print(f"  DELETED {r.display_id}", flush=True)
                except Exception as e:
                    failed += 1
                    print(
                        f"  ERROR   {r.display_id}: "
                        f"{type(e).__name__}: {e}", flush=True,
                    )

        # ── 2. Junk-named ACTIVE entities (scored) → PENDING_REVIEW ───
        async with sm() as session:
            name_rows = (await session.execute(text(_ACTIVE_NAMES_SQL))).all()
        junk_rows = [
            (r, check_institution_name(r.name)[1])
            for r in name_rows
            if check_institution_name(r.name)[0]
        ]
        print(
            f"\n# 2. junk-named ACTIVE entities (park in PENDING_REVIEW): "
            f"{len(junk_rows)}", flush=True,
        )
        for r, reason in junk_rows:
            print(f"  PARK    {r.display_id:42} {r.name!r:45} ({reason})",
                  flush=True)
        if apply:
            for r, reason in junk_rows:
                try:
                    async with sm() as session:
                        await session.execute(
                            text(
                                "UPDATE entities SET "
                                "  status = 'PENDING_REVIEW', "
                                "  inferred_from_source = :src, "
                                "  inferred_at = NOW(), "
                                "  updated_at = NOW() "
                                "WHERE id = CAST(:id AS uuid) "
                                "  AND status = 'ACTIVE'"
                            ),
                            {
                                "id": r.id,
                                "src": (
                                    f"purge_partial_entities: name "
                                    f"{r.name!r} failed sanity ({reason})"
                                ),
                            },
                        )
                        await session.commit()
                        print(f"  PARKED  {r.display_id}", flush=True)
                except Exception as e:
                    failed += 1
                    print(
                        f"  ERROR   {r.display_id}: "
                        f"{type(e).__name__}: {e}", flush=True,
                    )

        # ── 3. Cross-wire report (no auto-fix) ────────────────────────
        async with sm() as session:
            xw = (await session.execute(text(_CROSS_WIRE_SQL))).all()
            synth = (await session.execute(text(_SYNTH_RUNS_SQL))).all()
        print(
            f"\n# 3. cross-wired document_sections "
            f"(section entity <> run entity): {len(xw)}", flush=True,
        )
        for r in xw:
            print(
                f"  XWIRE   run={r.run_id} sections-of="
                f"{r.section_entity_display} attached-to="
                f"{r.run_entity_display}", flush=True,
            )
        print(f"# 3b. SYNTH-request_id runs (identity-inferred): "
              f"{len(synth)}", flush=True)
        for r in synth:
            print(f"  SYNTH   {r.request_id:24} {r.display_id}", flush=True)

        mode = "APPLIED" if apply else "DRY-RUN (pass --apply to execute)"
        print(
            f"\npurge_partial_entities [{mode}]: "
            f"{len(zero_rows)} zero-score, {len(junk_rows)} junk-named, "
            f"{len(xw)} cross-wired, {failed} failed", flush=True,
        )
    finally:
        await engine.dispose()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
