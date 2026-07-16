"""Pre-warm focus areas for entities whose packages shipped no client
profile (DOCX) — the D3 heatmap focus view's data source.

``services/focus_area_synthesizer.synthesize_focus_areas`` already
implements the honest ladder (DOCX rows verbatim → Gemini clustering →
deterministic heuristic when Vertex is cold) and persists by default,
but it only runs when an AE first opens the focus view. On a freshly
seeded corpus that leaves every profile-less entity rendering the
focus-mode empty state until first click. This script walks entities
with zero ``focus_areas`` rows and invokes the same ladder once, so
the corpus serves populated focus cards immediately after seed/deploy
(complement to ``derive_insights.py``; run both as the post-seed
refresh).

Idempotent: entities with existing rows are skipped (the synthesizer's
DOCX-first rule also guarantees re-runs never clobber extracted rows).

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.derive_focus_areas [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services.focus_area_synthesizer import synthesize_focus_areas


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        # Gap test = zero RENDERABLE rows, not zero rows (2026-06-10):
        # the Client Profile parser also captures DOCX scaffolding
        # ("2 Top Findings…", bare "F-004" ids) which the read path now
        # filters via focus_area_sanity — an entity whose only rows are
        # scaffolding renders the same empty focus view a row-less one
        # does, so it needs the synthesizer just the same.
        from app.services.focus_area_sanity import clean_focus_area

        all_rows = (
            await session.execute(text(
                """
                SELECT e.display_id, fa.title, fa.verbatim_quote
                FROM entities e
                LEFT JOIN runs r
                       ON r.entity_id = e.id AND r.status = 'ACTIVE'
                LEFT JOIN focus_areas fa ON fa.run_id = r.id
                ORDER BY e.display_id
                """),
            )
        ).all()
        renderable: dict[str, int] = {}
        for r in all_rows:
            renderable.setdefault(r.display_id, 0)
            if r.title is not None and clean_focus_area(
                    r.title, r.verbatim_quote or "")[0]:
                renderable[r.display_id] += 1
        gap_ids = sorted(d for d, n in renderable.items() if n == 0)
        if getattr(args, "entity", None):
            gap_ids = [d for d in gap_ids if d == args.entity]
        if args.limit is not None:
            gap_ids = gap_ids[:args.limit]
        rows = [type("R", (), {"display_id": d})() for d in gap_ids]

        filled, skipped = [], []
        for r in rows:
            res = await synthesize_focus_areas(
                session, entity_display_id=r.display_id, persist=True,
            )
            if res.get("ok") and res.get("focus_areas"):
                filled.append(
                    f"{r.display_id}({res.get('data_source', '?')}:"
                    f"{len(res['focus_areas'])})"
                )
            else:
                skipped.append(f"{r.display_id}({res.get('reason', '?')})")
        await session.commit()

        # ── Idempotent enrichment backfill (Part 6.1e) ────────────────
        # Every entity — not just the gap set — gets grounding /
        # pillars_weight / financial_ref / derived-KPI seeding for
        # focus rows that still lack them (rows persisted before the
        # migration-052 synthesizer rewrite, incl. the DOCX-parsed
        # ones). COALESCE-guarded updates + seed-only-when-none KPI
        # inserts make re-runs no-ops.
        from app.services.focus_area_synthesizer import (
            backfill_focus_area_enrichment,
            clean_persisted_focus_areas,
        )

        all_ids = sorted(renderable)
        if getattr(args, "entity", None):
            all_ids = [d for d in all_ids if d == args.entity]
        if args.limit is not None:
            all_ids = all_ids[: args.limit]
        backfilled_rows = backfilled_kpis = titles_fixed = 0
        ground_similarity = linked_seeded = 0
        fa_cleaned = fa_dropped = fa_salvaged = 0
        for did in all_ids:
            res = await backfill_focus_area_enrichment(
                session, entity_display_id=did,
            )
            backfilled_rows += int(res.get("grounded") or 0)
            backfilled_kpis += int(res.get("kpi_rows") or 0)
            titles_fixed += int(res.get("titles_fixed") or 0)
            ground_similarity += int(res.get("grounding_similarity") or 0)
            linked_seeded += int(res.get("linked_insights") or 0)
            # Persisted-data correctness (2026-07): rewrite the STORED title +
            # verbatim_quote to the clean read-path forms and drop pure
            # scaffolding, so every consumer (KPI enricher, evidence drawer)
            # reads validated focus areas — not "2 Top Findings" / "F-003 | …".
            fc = await clean_persisted_focus_areas(session, entity_display_id=did)
            fa_cleaned += int(fc.get("cleaned") or 0)
            fa_dropped += int(fc.get("dropped") or 0)
            fa_salvaged += int(fc.get("salvaged") or 0)
        await session.commit()
    await engine.dispose()

    # Gemini-rung accounting on the summary line (2026-07-05): the
    # 01735cd build's HARD focus_clustering gate failed with the real
    # cause buried in a per-run log.warning — the build log must name it.
    from app.services import focus_area_synthesizer as _fas

    gemini_note = (
        f" gemini[schema_ok={_fas.GEMINI_STATS['schema_ok']} "
        f"plain_ok={_fas.GEMINI_STATS['plain_ok']} "
        f"failed={_fas.GEMINI_STATS['failed']}]"
    )
    print(
        f"# derive_focus_areas: filled={len(filled)} skipped={len(skipped)} "
        f"grounding_backfilled={backfilled_rows} kpi_rows_seeded={backfilled_kpis} "
        f"titles_fixed={titles_fixed} grounding_similarity={ground_similarity} "
        f"linked_insights_seeded={linked_seeded} "
        f"persisted_fa_cleaned={fa_cleaned} fa_salvaged={fa_salvaged} scaffolding_dropped={fa_dropped}"
        f"{gemini_note}"
    )
    if _fas.LAST_GEMINI_ERROR:
        print(f"#   last gemini error: {_fas.LAST_GEMINI_ERROR}")
    if args.verbose:
        for line in filled:
            print("  +", line)
        for line in skipped:
            print("  -", line)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--limit", type=int, help="only first N entities")
    p.add_argument("--entity", default=None,
                   help="scope to one display_id (per-client processing)")
    p.add_argument("--verbose", action="store_true")
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
