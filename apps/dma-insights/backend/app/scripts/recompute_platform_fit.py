"""Recompute platform fit (engine v2) for every ACTIVE run — Part 7.1.

The ingest-time persister wrote engine-v1 scores (gapxseverityxbreadth
only), which the 2026-06 audit measured as 95/470 red-but-hot cards,
470/470 READY, 42 clamped 99.9 and zero persisted traceability. This
derive-chain step re-scores every ACTIVE run with engine v2
(opportunity x evidence strength, catalogue-adjacency interconnect,
confirmed-absent boost, readiness folded in) and persists
`fit_breakdown` + `sequence_rank` + honest `state`.

Runs in derive-chain wave 5 (after clean_techstack — absent detection —
and derive_insights/derive_recommendations — severity + dependency
inputs). Idempotent: recomputing unchanged inputs rewrites identical
rows.

Prints the acceptance counters (red∧fit≥80, state distribution, fit
distribution, all-identical clients) so the convergence loop can diff
them run-over-run.

Usage:
  DATABASE_URL=... python -m app.scripts.recompute_platform_fit [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.platform_fit_data import (
    compute_v2_rows,
    load_fit_context,
    persist_v2_rows,
)


async def _amain(limit: int | None, entity: str | None = None) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    fits: list[float] = []
    red_hot = 0
    states: Counter[str] = Counter()
    identical_clients = 0
    runs_done = 0
    async with sm() as session:
        runs = (await session.execute(text(
            """
            SELECT r.id AS rid, r.entity_id AS eid, r.ccg_catalog_version AS ver,
                   e.display_id
            FROM runs r JOIN entities e ON e.id = r.entity_id
            WHERE r.status = 'ACTIVE' AND e.status = 'ACTIVE'
            """
            + ("AND e.display_id = :ent " if entity else "")
            + "ORDER BY e.display_id"),
            ({"ent": entity} if entity else {}))).all()
        if limit:
            runs = runs[:limit]
        for run in runs:
            ctx = await load_fit_context(
                session, run_id=run.rid, entity_id=run.eid,
                catalogue_version=run.ver,
            )
            rows, _checks = compute_v2_rows(ctx)
            await persist_v2_rows(
                session, run_id=run.rid, entity_id=run.eid, rows=rows,
            )
            nonzero = [r.fit_score for r in rows if r.fit_score > 0]
            fits.extend(r.fit_score for r in rows)
            red_hot += sum(
                1 for r in rows if r.readiness == "red" and r.fit_score >= 80
            )
            states.update(r.state for r in rows)
            if len(nonzero) >= 2 and len(set(nonzero)) == 1:
                identical_clients += 1
            runs_done += 1
        await session.commit()

    fits.sort()
    n = len(fits)
    med = fits[n // 2] if n else 0.0
    print(
        f"# recompute_platform_fit: runs={runs_done} cards={n} "
        f"fit[min/median/max]={fits[0] if n else 0}/{med}/{fits[-1] if n else 0} "
        f"n99plus={sum(1 for f in fits if f >= 99)} "
        f"red_and_hot={red_hot} all_identical_clients={identical_clients} "
        f"states={dict(states)}",
        flush=True,
    )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--entity", default=None,
                    help="scope to one display_id (per-client processing)")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(_amain(args.limit, entity=args.entity)))


if __name__ == "__main__":
    main()
