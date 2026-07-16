"""Deploy-time Gemini enrichment for the data-UNAVAILABILITY gaps — resilient,
ledger-tracked, re-probing.

Runs the dedicated prompt formulator + iterative acquisition loop
(:mod:`app.services.enrichment_prompter`) over EVERY registered single-datum gap
(headcount / HQ / assets / regulator / founding year) that no extraction pass
could recover. A sufficient, sourced answer is written back as the column value
+ a citable ``evidence_index`` row + an ``ai_enrichments`` provenance row.

Resilience contract (why this can wire into the deploy chain unconditionally):
  * EVERY discovered gap is registered in ``enrichment_ledger`` up front, so no
    surface is silently skipped — even if a run is budget-capped before it.
  * Each gap is probed inside its OWN try/except; one failure never aborts the
    run or the deploy.
  * The ledger drives RE-PROBING: a gap that got no usable answer (Vertex cold →
    ``deferred``; an error/insufficient loop → ``failed`` with backoff) is picked
    up on the NEXT deploy; a resolved gap (``enriched`` / ``absent``) is skipped.
  * A ``--max-calls`` ceiling bounds Vertex spend per deploy; the unreached gaps
    stay ``pending`` and are enriched on a subsequent run.
  * Offline/creds-less deploy: every gap → ``deferred`` (retry next deploy), 0
    enriched, no hang, exit 0.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.enrich_unavailable --dry-run        # gap census + sample prompt
  python -m app.scripts.enrich_unavailable --status         # ledger state, no Vertex
  python -m app.scripts.enrich_unavailable --limit 5        # smoke (live Vertex)
  python -m app.scripts.enrich_unavailable --max-calls 200  # full corpus, bounded
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
from app.services.enrichment_prompter import (
    build_unavailability_gaps,
    enrich_gap,
    ensure_pending,
    formulate_prompt,
    is_due,
    ledger_for_entity,
    persist_enrichment,
    record_attempt,
)
from app.services.enrichment_triggers import Trigger, TriggerFiring, log_firing


async def _entities(session, limit: int | None) -> list:
    rows = (await session.execute(text(
        """
        SELECT r.id::text rid, e.id::text eid, e.display_id, e.name,
               e.subvertical, f.aum_usd, f.revenue_usd, f.headcount, f.hq_address,
               f.primary_regulator, f.parsed_facts
        FROM runs r JOIN entities e ON e.id = r.entity_id
        LEFT JOIN firmographics f ON f.entity_id = e.id
        WHERE r.status = 'ACTIVE' AND e.status = 'ACTIVE'
        ORDER BY e.display_id
        """ + (f" LIMIT {int(limit)}" if limit else "")))).all()
    return list(rows)


def _firmo(row) -> dict:
    return {
        "aum_usd": float(row.aum_usd) if row.aum_usd is not None else None,
        "revenue_usd": float(row.revenue_usd) if row.revenue_usd is not None else None,
        "headcount": row.headcount, "hq_address": row.hq_address,
        "primary_regulator": row.primary_regulator,
        "parsed_facts": row.parsed_facts or {},
    }


async def _print_status(session) -> None:
    rows = (await session.execute(text(
        "SELECT status, count(*) n FROM enrichment_ledger GROUP BY status "
        "ORDER BY n DESC"))).all()
    total = sum(r.n for r in rows)
    print(f"# enrichment_ledger: {total} tracked gaps")
    for r in rows:
        print(f"    {r.status:10} {r.n}")
    due = (await session.execute(text(
        "SELECT count(*) FROM enrichment_ledger WHERE status IN "
        "('pending','deferred','failed') AND (next_probe_after IS NULL "
        "OR next_probe_after <= NOW())"))).scalar()
    print(f"    → {due} due for (re)probe now")


async def main_async(args: argparse.Namespace) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()

    if args.status:
        async with sm() as session:
            await _print_status(session)
        return 0

    client = None
    if not args.dry_run:
        from app.services.vertex_client import get_vertex_client
        client = get_vertex_client()

    now = dt.datetime.now(dt.UTC)
    census: Counter = Counter()
    tally: Counter = Counter()
    calls = 0
    sample_shown = False
    async with sm() as session:
        rows = await _entities(session, args.limit)
        for row in rows:
            gaps = build_unavailability_gaps(
                entity_name=row.name, subvertical=(row.subvertical or ""),
                firmographics=_firmo(row))
            for g in gaps:
                census[g.field] += 1
            if args.dry_run:
                if gaps and not sample_shown:
                    print(f"\n--- sample prompt ({row.display_id} / {gaps[0].field}) ---")
                    print(formulate_prompt(gaps[0]))
                    print("--- end sample ---\n")
                    sample_shown = True
                continue

            # 1) register every gap so nothing is silently dropped, then read state
            await ensure_pending(session, row.eid, gaps)
            ledger = await ledger_for_entity(session, row.eid)
            for gap in gaps:
                if not is_due(ledger.get(gap.field), now):
                    tally["skipped_resolved_or_backoff"] += 1
                    continue
                if args.max_calls and calls >= args.max_calls:
                    tally["deferred_budget"] += 1     # stays pending → next deploy
                    continue
                calls += 1
                # 2) per-gap resilience: a failure NEVER aborts the run/deploy
                try:
                    outcome = await enrich_gap(
                        gap, client=client, model=args.model,
                        max_rounds=args.max_rounds)
                except Exception as exc:
                    await record_attempt(
                        session, entity_id=row.eid, run_id=row.rid,
                        field=gap.field, surface=gap.surface, status="failed",
                        error=f"{type(exc).__name__}: {exc}", backoff_hours=24)
                    tally["failed"] += 1
                    log_firing(TriggerFiring(
                        trigger=Trigger.G1_EMPTY_FIELD, query=gap.field,
                        engine="gemini", outcome="failed",
                        entity_id=str(row.eid), field=gap.field,
                        ts=now.isoformat()))
                    continue
                if outcome is None:                    # cold/offline/exhausted
                    await record_attempt(
                        session, entity_id=row.eid, run_id=row.rid,
                        field=gap.field, surface=gap.surface, status="deferred",
                        error="no usable response", backoff_hours=6)
                    tally["deferred"] += 1
                    log_firing(TriggerFiring(
                        trigger=Trigger.G1_EMPTY_FIELD, query=gap.field,
                        engine="gemini", outcome="deferred",
                        entity_id=str(row.eid), field=gap.field,
                        ts=now.isoformat()))
                elif not outcome.found:                # model-confirmed absence
                    await record_attempt(
                        session, entity_id=row.eid, run_id=row.rid,
                        field=gap.field, surface=gap.surface, status="absent",
                        rounds=outcome.rounds)
                    tally["absent"] += 1
                    log_firing(TriggerFiring(
                        trigger=Trigger.G1_EMPTY_FIELD, query=gap.field,
                        engine="gemini", outcome="absent",
                        entity_id=str(row.eid), field=gap.field,
                        ts=now.isoformat()))
                else:
                    e_id = await persist_enrichment(
                        session, gap=gap, outcome=outcome, run_id=row.rid,
                        entity_id=row.eid)
                    await record_attempt(
                        session, entity_id=row.eid, run_id=row.rid,
                        field=gap.field, surface=gap.surface, status="enriched",
                        rounds=outcome.rounds, confidence=outcome.confidence,
                        evidence_e_id=e_id, value_preview=str(outcome.value))
                    tally["enriched"] += 1
                    log_firing(TriggerFiring(
                        trigger=Trigger.G1_EMPTY_FIELD, query=gap.field,
                        engine="gemini", outcome="enriched",
                        new_evidence_ids=[e_id] if e_id else [],
                        entity_id=str(row.eid), field=gap.field,
                        ts=now.isoformat()))
                    print(f"  + {row.display_id} {gap.field} = {outcome.value} "
                          f"(conf {outcome.confidence:.2f}, {outcome.rounds} rounds, "
                          f"src {outcome.source_name})")
            await session.commit()      # per-entity commit — progress survives a later error

    if args.dry_run:
        print(f"\n# enrich_unavailable (dry-run): gaps={dict(census)} — "
              f"{sum(census.values())} prompts formulatable, 0 Vertex calls")
    else:
        print(f"\n# enrich_unavailable: discovered={dict(census)} "
              f"vertex_calls={calls} outcomes={dict(tally)}")
        async with sm() as session:
            await _print_status(session)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="gap census + a sample formulated prompt; zero Vertex")
    ap.add_argument("--status", action="store_true",
                    help="print the enrichment_ledger state and exit (no Vertex)")
    ap.add_argument("--limit", type=int, default=None, help="entity cap (smoke)")
    ap.add_argument("--model", default="flash", choices=("flash", "pro"))
    ap.add_argument("--max-rounds", type=int, default=3,
                    help="max iterative follow-up rounds per gap")
    ap.add_argument("--max-calls", type=int, default=0,
                    help="ceiling on Vertex calls this run (0 = unbounded); "
                         "unreached gaps stay pending for the next deploy")
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
