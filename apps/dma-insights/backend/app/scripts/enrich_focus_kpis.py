"""Deploy-time rich-context Gemini KPI enrichment for focus areas.

For every active entity, loads the shared L1 EntityState (so the prompt carries
the FULL client context — scores, the DMA narrative, gaps, financials) and, for
each focus area, formulates a deep KPI prompt
(:mod:`app.services.focus_kpi_enrichment`), acquires reasoned KPIs with a
baseline + target, and writes them to focus_area_kpi_overrides + a citable
evidence row — so the drilldown KPI strip populates like the prototype.

Reuses the resilient enrichment ledger (per focus area, field ``kpi:<fa>``): a FA
whose KPIs could not be acquired (Vertex cold / error) is re-probed on a later
deploy; a resolved FA is skipped. Per-FA try/except + per-entity commit + a
--max-calls ceiling; offline/creds-less deploy defers everything, 0 written,
exit 0.

Usage:
  python -m app.scripts.enrich_focus_kpis --dry-run     # sample prompt, 0 Vertex
  python -m app.scripts.enrich_focus_kpis --status      # ledger state (kpi:* rows)
  python -m app.scripts.enrich_focus_kpis --limit 3 --max-calls 30
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import os
import sys
from collections import Counter

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.enrichment_prompter import ensure_pending, is_due, record_attempt
from app.services.enrichment_prompter import ledger_for_entity as _ledger
from app.services.focus_kpi_enrichment import (
    build_kpi_context,
    build_kpi_prompt,
    enrich_focus_kpis,
    persist_focus_kpis,
)
from app.services.nlp.entity_knowledge import load_entity_state


async def _entities(session, limit):
    return list((await session.execute(text(
        "SELECT r.id::text rid, e.id::text eid, e.display_id, e.subvertical "
        "FROM runs r JOIN entities e ON e.id = r.entity_id "
        "WHERE r.status='ACTIVE' AND e.status='ACTIVE' ORDER BY e.display_id"
        + (f" LIMIT {int(limit)}" if limit else "")))).all())


async def _focus_areas(session, run_id):
    return list((await session.execute(text(
        "SELECT id::text id, title, verbatim_quote, involved_subcap_ids "
        "FROM focus_areas WHERE run_id = CAST(:r AS uuid) ORDER BY title"),
        {"r": run_id})).all())


async def _status(session) -> None:
    rows = (await session.execute(text(
        "SELECT status, count(*) n FROM enrichment_ledger WHERE field LIKE 'kpi:%' "
        "GROUP BY status ORDER BY n DESC"))).all()
    print(f"# focus-KPI ledger: {sum(r.n for r in rows)} tracked focus areas")
    for r in rows:
        print(f"    {r.status:10} {r.n}")


async def main_async(args) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    if args.status:
        async with sm() as s:
            await _status(s)
        return 0
    client = None
    if not args.dry_run:
        from app.services.vertex_client import get_vertex_client
        client = get_vertex_client()
    now = dt.datetime.now(dt.UTC)
    tally: Counter = Counter()
    calls = 0
    sample = False
    async with sm() as session:
        for row in await _entities(session, args.limit):
            try:
                state = await load_entity_state(session, entity_display_id=row.display_id)
            except Exception:
                state = None
            if state is None:
                continue
            # Only enrich KPIs for RENDERABLE focus areas with a clean title —
            # never scaffolding ("2 Top Findings") or a raw "F-003 | …" row. Uses
            # the same read-path filter so KPIs attach to validated focus areas.
            from app.services.focus_area_sanity import clean_focus_area
            fas = []
            for fa in await _focus_areas(session, row.rid):
                keep, disp = clean_focus_area(
                    fa.title or "", fa.verbatim_quote or "",
                    list(fa.involved_subcap_ids or []),
                    subvertical=getattr(row, "subvertical", None))
                if keep:
                    fa = type("FA", (), {
                        "id": fa.id, "title": disp or fa.title,
                        "verbatim_quote": fa.verbatim_quote,
                        "involved_subcap_ids": fa.involved_subcap_ids})()
                    fas.append(fa)
            gaps = [type("G", (), {"field": f"kpi:{fa.id.replace('-', '')[:56]}",
                                   "surface": "focus_kpi"})() for fa in fas]
            await ensure_pending(session, row.eid, gaps)
            ledger = await _ledger(session, row.eid)
            for fa in fas:
                field = f"kpi:{fa.id.replace('-', '')[:56]}"
                if not is_due(ledger.get(field), now):
                    tally["skipped"] += 1
                    continue
                if args.dry_run:
                    ctx = build_kpi_context(state, {
                        "id": fa.id, "title": fa.title,
                        "verbatim_quote": fa.verbatim_quote,
                        "involved_subcap_ids": list(fa.involved_subcap_ids or [])})
                    if not sample:
                        print(f"\n--- sample KPI prompt ({row.display_id} / {fa.title}) ---")
                        print(build_kpi_prompt(ctx)[:1400])
                        print("--- end sample ---\n")
                        sample = True
                    tally["would_probe"] += 1
                    continue
                if args.max_calls and calls >= args.max_calls:
                    tally["deferred_budget"] += 1
                    continue
                calls += 1
                try:
                    ctx = build_kpi_context(state, {
                        "id": fa.id, "title": fa.title,
                        "verbatim_quote": fa.verbatim_quote,
                        "involved_subcap_ids": list(fa.involved_subcap_ids or [])})
                    kpis = await enrich_focus_kpis(
                        ctx, client=client, model=args.model, max_rounds=args.max_rounds)
                except Exception as exc:
                    await record_attempt(session, entity_id=row.eid, run_id=row.rid,
                                         field=field, surface="focus_kpi",
                                         status="failed", error=f"{type(exc).__name__}: {exc}",
                                         backoff_hours=24)
                    tally["failed"] += 1
                    continue
                if not kpis:
                    # Deterministic floor (2026-07-12 directive: baselines
                    # infer from research + entity financials, not an AE
                    # hand-fill): mine disclosed metrics from the run's own
                    # evidence excerpts topically bound to this focus area —
                    # real numbers, each citing the evidence row it came
                    # from. Gemini later REPLACES these public rows with
                    # reasoned baseline→target pairs (same upgrade path).
                    from app.services.focus_area_synthesizer import mine_disclosed_kpis
                    _texts = (await session.execute(text(
                        """
                        SELECT e_id, excerpt FROM evidence_index
                        WHERE run_id = CAST(:rid AS uuid)
                          AND length(COALESCE(excerpt,'')) >= 40
                        ORDER BY tier ASC NULLS LAST LIMIT 400
                        """), {"rid": row.rid})).all()
                    floor = mine_disclosed_kpis(
                        f"{fa.title} {fa.verbatim_quote or ''}",
                        [(t.e_id, t.excerpt) for t in _texts])
                    for k in floor:
                        k["evidence_e_id"] = k.pop("e_id", None)
                    if floor:
                        n = await persist_focus_kpis(
                            session, entity_id=row.eid, run_id=row.rid,
                            fa_id=fa.id, kpis=floor)
                        await record_attempt(
                            session, entity_id=row.eid, run_id=row.rid,
                            field=field, surface="focus_kpi",
                            status="enriched", rounds=len(floor),
                            value_preview=f"{n} mined-floor KPIs")
                        tally["floor_mined"] += 1
                        continue
                    await record_attempt(session, entity_id=row.eid, run_id=row.rid,
                                         field=field, surface="focus_kpi",
                                         status="deferred", error="no usable KPIs",
                                         backoff_hours=6)
                    tally["deferred"] += 1
                else:
                    n = await persist_focus_kpis(session, entity_id=row.eid,
                                                 run_id=row.rid, fa_id=fa.id, kpis=kpis)
                    await record_attempt(session, entity_id=row.eid, run_id=row.rid,
                                         field=field, surface="focus_kpi",
                                         status="enriched", rounds=len(kpis),
                                         value_preview=f"{n} KPIs")
                    tally["enriched"] += 1
                    print(f"  + {row.display_id} · {fa.title[:40]}: {n} KPIs")
            await session.commit()
    print(f"\n# enrich_focus_kpis: vertex_calls={calls} outcomes={dict(tally)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="flash", choices=("flash", "pro"))
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--max-calls", type=int, default=0)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
