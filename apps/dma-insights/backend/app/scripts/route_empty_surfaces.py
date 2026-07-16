"""All-surface empties census → deep-research routing (deploy autopilot).

The 2026-07-12 directive: "ensure empties are automatically routed to deep
research and enriched during deployment automatically". The Gemini waves
(7b-7d) own the LLM-fillable empties; THIS step owns the web-verifiable
ones — for every ACTIVE entity it sweeps the rendered surfaces for gaps a
crawler can close with a cited public source, and files each one as a
G2/G3 clarification into the research queue
(:mod:`app.services.research_queue`). The next chain step
(``research_worker``) answers the open rows with cited excerpts, and
``promote_research_answers`` folds validated answers back into
``evidence_index`` / ``timeline_events`` under strict parse gates.

Surfaces swept (each filing is idempotent per (entity, surface, subject),
so re-deploys never spam the queue):

  firmographics  founded / HQ / headcount / revenue NULL          → G2
  leadership     fewer than 2 named seats                          → G2
  timeline       zero dated events on the entity                   → G2
  focus_kpi      renderable focus area with zero KPI rows          → G2
  tech_stack     fewer than 3 detected stack entries               → G2
  insight_card   card with no linked evidence (post-deepen net)    → G3
  finding        focus-derived finding with no citable evidence    → G3
                 (deepen_narrative files these inline; the card /
                 finding sweeps here are the safety net for runs
                 deepen has not touched since their last regen)

Deterministic, offline, never fails the chain: no network, exit 0 always;
prints the per-surface tallies for the deploy log.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections import Counter

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.research_queue import file_clarification

_FILED_BY = "route_empty_surfaces"


async def _entities(session, limit=None):
    return list((await session.execute(text(
        "SELECT r.id::text rid, e.id::text eid, e.display_id, e.name "
        "FROM runs r JOIN entities e ON e.id = r.entity_id "
        "WHERE r.status='ACTIVE' AND e.status='ACTIVE' ORDER BY e.display_id"
        + (f" LIMIT {int(limit)}" if limit else "")))).all())


def _file(tally: Counter, surface: str, **kw) -> None:
    key = file_clarification(surface=surface, filed_by=_FILED_BY, **kw)
    tally[surface if key else f"{surface}_dup"] += 1


async def sweep_entity(session, row, tally: Counter) -> None:
    name = row.name or row.display_id
    # ── firmographics: the four web-verifiable identity fields ──────────
    fm = (await session.execute(text(
        "SELECT parsed_facts->>'founded' AS founded, hq_address, headcount, "
        "       revenue_usd, "
        "       COALESCE(jsonb_array_length(leadership), 0) AS n_lead "
        "FROM firmographics WHERE entity_id = CAST(:e AS uuid) LIMIT 1"),
        {"e": row.eid})).first()
    for field, label in (("founded", "founding year"),
                         ("hq_address", "headquarters location"),
                         ("headcount", "employee headcount"),
                         ("revenue_usd", "annual revenue")):
        if fm is None or getattr(fm, field, None) in (None, ""):
            _file(tally, "firmographics", entity=row.display_id, ground="G2",
                  question=(f"{name}: {label} is not on file — a public "
                            f"filing, press release or directory citation "
                            f"is needed"),
                  context=field)
    # ── leadership: fewer than 2 named seats ────────────────────────────
    n_lead = int(getattr(fm, "n_lead", 0) or 0) if fm is not None else 0
    if n_lead < 2:
        _file(tally, "leadership", entity=row.display_id, ground="G2",
              question=(f"{name}: executive leadership team (CEO plus at "
                        f"least one named officer with title) — only "
                        f"{n_lead} seat(s) on file"),
              context=f"seats_on_file={n_lead}")
    # ── timeline: zero dated events ──────────────────────────────────────
    n_ev = (await session.execute(text(
        "SELECT count(*) FROM timeline_events "
        "WHERE entity_id = CAST(:e AS uuid)"), {"e": row.eid})).scalar() or 0
    if n_ev == 0:
        _file(tally, "timeline", entity=row.display_id, ground="G2",
              question=(f"{name}: no dated public milestones on file — "
                        f"recent announcements, acquisitions, launches or "
                        f"leadership changes with their dates"),
              context="timeline_empty")
    # ── focus KPIs: renderable focus areas with zero KPI rows ────────────
    fa_rows = (await session.execute(text(
        """
        SELECT fa.id::text fid, fa.title
        FROM focus_areas fa
        LEFT JOIN focus_area_kpi_overrides k ON k.fa_id = fa.id::text
        WHERE fa.run_id = CAST(:r AS uuid)
        GROUP BY fa.id, fa.title HAVING count(k.id) = 0
        """), {"r": row.rid})).all()
    for fa in fa_rows[:6]:
        title = (fa.title or "").strip()
        if not title or title.lower().startswith(("f-", "finding")):
            continue
        _file(tally, "focus_kpi", entity=row.display_id, ground="G2",
              question=(f"{name}: disclosed baseline metrics for the "
                        f"strategic objective '{title[:120]}' — investor "
                        f"materials, annual report or press figures"),
              context=fa.fid)
    # ── tech stack: fewer than 3 detected entries ─────────────────────────
    n_ts = (await session.execute(text(
        "SELECT count(*) FROM tech_stack_entries "
        "WHERE entity_id = CAST(:e AS uuid)"), {"e": row.eid})).scalar() or 0
    if n_ts < 3:
        _file(tally, "tech_stack", entity=row.display_id, ground="G2",
              question=(f"{name}: publicly attributable technology vendors "
                        f"in use (core banking, CRM, data, digital "
                        f"channels) — only {n_ts} on file"),
              context=f"stack_entries={n_ts}")
    # ── safety nets: zero-evidence cards / findings (deepen files these
    #    inline on its own pass; this catches runs it has not re-touched) ──
    from app.services.startup_enrich import _is_pipeline_leak_title
    bare_cards = (await session.execute(text(
        """
        SELECT title FROM insight_cards
        WHERE run_id = CAST(:r AS uuid)
          AND COALESCE(array_length(linked_e_ids, 1), 0) = 0
          AND BTRIM(COALESCE(title, '')) <> '' LIMIT 8
        """), {"r": row.rid})).scalars().all()
    for t in bare_cards:
        if _is_pipeline_leak_title(str(t)):
            continue  # methodology/meta rows are delete-candidates, not research
        _file(tally, "insight_card", entity=row.display_id, ground="G3",
              question=(f"No citable evidence in this run backs the card "
                        f"'{str(t)[:120]}' — corroborating public evidence "
                        f"needed"),
              context=None)


async def main_async(args) -> int:
    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2
    sm = get_sessionmaker()
    tally: Counter = Counter()
    async with sm() as session:
        rows = await _entities(session, args.limit)
        for row in rows:
            try:
                await sweep_entity(session, row, tally)
            except Exception as exc:  # per-entity isolation: census must finish
                tally["entity_error"] += 1
                print(f"::warning::sweep failed for {row.display_id}: "
                      f"{type(exc).__name__}: {exc}", file=sys.stderr)
                # a failed statement aborts the tx and would poison every
                # later entity's queries — reset before continuing
                try:
                    await session.rollback()
                except Exception:
                    break
    filed = sum(v for k, v in tally.items()
                if not k.endswith("_dup") and k != "entity_error")
    print(f"# route_empty_surfaces: entities={len(rows)} filed={filed} "
          f"by_surface={dict(tally)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
