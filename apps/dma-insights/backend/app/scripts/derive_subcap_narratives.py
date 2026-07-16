"""Populate `subcap_narratives` (migration 051) for every scored subcap.

The D3 SynthesisDrawer's per-subcap rationale reached 1/94 clients because
the Gemini extractor only ran for one ingested deep-dive DOCX and its
output had no durable table. This script walks every run that has
subcap_scores and composes the deterministic floor narrative
(`services/subcap_synthesis.compose_subcap_narrative`) per subcap from the
run's REAL values — score, band, peer median, thin/cap flags, top linked
evidence excerpt (evidence_index links), and linked insight/rec titles —
then UPSERTs rows with meta='heuristic'.

Idempotent + Gemini-safe: `ON CONFLICT (run_id, subcap_id) DO NOTHING`
means existing rows — including validator-passed meta='llm' rows the
deploy-hot extractor wrote — are NEVER overwritten; re-runs are no-ops.

Runs as a derive-chain step (wave 7: reads subcap_scores / evidence_index /
insight_cards / recommendations, sole writer of subcap_narratives).

Usage:
  DATABASE_URL=... python -m app.scripts.derive_subcap_narratives \
      [--limit N] [--active-only]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.subcap_synthesis import (
    SubcapFacts,
    compose_subcap_narrative,
    is_generic_subcap_name,
)

_INSERT_CHUNK = 500


async def _resolve_names(session, subcap_ids: list[str]) -> dict[str, str]:
    """Best NON-GENERIC catalogue name per subcap across ALL ccg
    versions (newest wins). The run-pinned version often carries
    auto-bootstrap stubs ("Subcap 7", "capability dimension 10") — the
    2026-07 depth stress-test found 2,169 narratives leaking them. A
    subcap with no real name anywhere resolves to nothing and the
    composer renders the bare id instead of a placeholder."""
    if not subcap_ids:
        return {}
    rows = (await session.execute(
        text("""
            SELECT subcap_id, name FROM ccg_subcaps
             WHERE subcap_id = ANY(:ids) AND name IS NOT NULL
             ORDER BY subcap_id, version DESC
        """),
        {"ids": subcap_ids},
    )).all()
    out: dict[str, str] = {}
    for r in rows:
        if r.subcap_id not in out and not is_generic_subcap_name(r.name, r.subcap_id):
            out[r.subcap_id] = r.name
    return out


async def _derive_for_run(session, run_id: str, *, refresh: bool = False) -> tuple[int, int]:
    """Compose + upsert narratives for one run. Returns (composed, skipped).

    Default mode inserts ONLY missing rows (idempotent). ``refresh=True``
    re-composes and OVERWRITES existing meta='heuristic' rows (never the
    validated llm rows) — the repair mode for composer upgrades."""
    existing = {
        r.subcap_id
        for r in (await session.execute(
            text("SELECT subcap_id FROM subcap_narratives WHERE run_id = :rid"),
            {"rid": run_id},
        )).all()
    } if not refresh else set()

    score_rows = (await session.execute(
        text("""
            SELECT s.subcap_id, s.score, s.band, s.peer_median,
                   s.is_thin_evidence, s.cap_applied, s.cap_reason,
                   cs.name AS subcap_name
              FROM subcap_scores s
              JOIN runs r ON r.id = s.run_id
              LEFT JOIN ccg_subcaps cs
                ON cs.version = r.ccg_catalog_version
               AND cs.subcap_id = s.subcap_id
             WHERE s.run_id = :rid
        """),
        {"rid": run_id},
    )).all()
    todo = [r for r in score_rows if r.subcap_id not in existing]
    if not todo:
        return 0, len(score_rows)
    # rank the run's below-peer gaps once so superlatives are honest
    gapped = sorted(
        (r for r in score_rows
         if r.peer_median is not None
         and float(r.peer_median) - float(r.score) > 0.05),
        key=lambda r: float(r.peer_median) - float(r.score), reverse=True)
    gap_rank = {r.subcap_id: i + 1 for i, r in enumerate(gapped)}
    n_gapped = len(gapped)

    # Resolve real names for cells whose run-version catalogue name is a
    # bootstrap stub / missing.
    unresolved = [
        r.subcap_id for r in todo
        if is_generic_subcap_name(r.subcap_name, r.subcap_id)
    ]
    name_fallback = await _resolve_names(session, unresolved)

    # Bulk evidence links: tier-ordered per subcap (top row = best tier).
    ev_rows = (await session.execute(
        text("""
            SELECT e_id, excerpt, tier, UNNEST(linked_subcap_ids) AS sid
              FROM evidence_index
             WHERE run_id = :rid
             ORDER BY tier ASC, e_id ASC
        """),
        {"rid": run_id},
    )).all()
    evidence_by_subcap: dict[str, list] = {}
    for r in ev_rows:
        if r.sid:
            evidence_by_subcap.setdefault(r.sid, []).append(r)

    insight_rows = (await session.execute(
        text("""
            SELECT linked_subcap_id, title FROM insight_cards
             WHERE run_id = :rid AND title IS NOT NULL
             ORDER BY ic_id
        """),
        {"rid": run_id},
    )).all()
    insights_by_subcap: dict[str, list[str]] = {}
    for r in insight_rows:
        if r.linked_subcap_id:
            insights_by_subcap.setdefault(r.linked_subcap_id, []).append(r.title)

    rec_rows = (await session.execute(
        text("""
            SELECT title, target_subcap_ids FROM recommendations
             WHERE run_id = :rid AND title IS NOT NULL
             ORDER BY rec_id
        """),
        {"rid": run_id},
    )).all()
    recs_by_subcap: dict[str, list[str]] = {}
    for r in rec_rows:
        for sid in r.target_subcap_ids or []:
            recs_by_subcap.setdefault(sid, []).append(r.title)

    # v7 use-case playbooks (memoized per catalogue version): gap cells
    # close on the catalogue-validated feature pattern + story count.
    from app.services.use_case_stories import load_playbooks
    playbooks = await load_playbooks(session)

    params: list[dict] = []
    for row in todo:
        evs = evidence_by_subcap.get(row.subcap_id, [])
        pb = playbooks.get(row.subcap_id) or {}
        name = row.subcap_name
        if is_generic_subcap_name(name, row.subcap_id):
            name = name_fallback.get(row.subcap_id)  # None → bare-id lead
        facts = SubcapFacts(
            subcap_id=row.subcap_id,
            name=name,
            score=float(row.score),
            band=str(row.band),
            peer_median=(
                float(row.peer_median) if row.peer_median is not None else None
            ),
            is_thin_evidence=bool(row.is_thin_evidence),
            cap_applied=bool(row.cap_applied),
            cap_reason=row.cap_reason,
            evidence_count=len(evs),
            evidence_e_ids=[e.e_id for e in evs[:6]],
            # Parallel excerpts so the composer can weave the first
            # CITABLE excerpt's substance (AE-depth contract).
            evidence_excerpts=[(e.excerpt or "") for e in evs[:6]],
            top_excerpt=(evs[0].excerpt if evs else None),
            insight_titles=insights_by_subcap.get(row.subcap_id, [])[:2],
            rec_titles=recs_by_subcap.get(row.subcap_id, [])[:2],
            gap_rank=gap_rank.get(row.subcap_id),
            n_gapped=n_gapped or None,
            playbook_features=list(pb.get("features") or []),
            playbook_stories=int(pb.get("n_stories") or 0),
        )
        params.append({
            "rid": run_id,
            "sid": row.subcap_id,
            "md": compose_subcap_narrative(facts),
            "eids": facts.evidence_e_ids,
        })

    conflict_action = (
        """DO UPDATE SET narrative_md = EXCLUDED.narrative_md,
                         evidence_e_ids = EXCLUDED.evidence_e_ids
             WHERE subcap_narratives.meta = 'heuristic'"""
        if refresh else "DO NOTHING"
    )
    for start in range(0, len(params), _INSERT_CHUNK):
        await session.execute(
            text(f"""
                INSERT INTO subcap_narratives
                    (run_id, subcap_id, narrative_md, meta, evidence_e_ids)
                VALUES (CAST(:rid AS uuid), :sid, :md, 'heuristic', :eids)
                ON CONFLICT (run_id, subcap_id) {conflict_action}
            """),
            params[start:start + _INSERT_CHUNK],
        )
    return len(params), len(score_rows) - len(params)


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    composed = skipped = runs_touched = 0
    async with maker() as session:
        conds = []
        if args.active_only:
            conds.append("r.status = 'ACTIVE'")
        if getattr(args, "entity", None):
            conds.append("r.entity_id = (SELECT id FROM entities "
                         "WHERE display_id = :ent)")
        where = ("WHERE " + " AND ".join(conds)) if conds else ""
        run_rows = (await session.execute(
            text(f"""
                SELECT DISTINCT r.id
                  FROM runs r
                  JOIN subcap_scores s ON s.run_id = r.id
                {where}
                ORDER BY r.id
            """),
            ({"ent": args.entity} if getattr(args, "entity", None) else {}),
        )).all()
        run_ids = [str(r.id) for r in run_rows]
        if args.limit is not None:
            run_ids = run_ids[: args.limit]
        if args.refresh:
            # Orphan cleanup: a re-ingest replaces subcap_scores rows,
            # leaving heuristic narratives dangling on (run, subcap)
            # pairs that no longer exist — the depth stress-test found
            # stale pre-fix prose surviving exactly this way. llm rows
            # are never touched.
            orphans = await session.execute(
                text("""
                    DELETE FROM subcap_narratives sn
                     WHERE sn.meta = 'heuristic'
                       AND NOT EXISTS (
                            SELECT 1 FROM subcap_scores s
                             WHERE s.run_id = sn.run_id
                               AND s.subcap_id = sn.subcap_id)
                """),
            )
            await session.commit()
            print(f"# derive_subcap_narratives: orphans_deleted="
                  f"{orphans.rowcount or 0}")
        for rid in run_ids:
            c, s = await _derive_for_run(session, rid, refresh=args.refresh)
            composed += c
            skipped += s
            if c:
                runs_touched += 1
            await session.commit()
    await engine.dispose()

    print(
        f"# derive_subcap_narratives: runs={len(run_ids)} "
        f"touched={runs_touched} composed={composed} existing={skipped}"
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--limit", type=int, help="only first N runs")
    p.add_argument("--active-only", action="store_true",
                   help="only runs with status ACTIVE")
    p.add_argument("--entity", default=None,
                   help="scope to one display_id (per-client processing)")
    p.add_argument("--refresh", action="store_true",
                   help="re-compose + overwrite existing heuristic rows "
                        "(llm rows are never touched)")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
