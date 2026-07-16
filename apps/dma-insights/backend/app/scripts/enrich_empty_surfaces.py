"""Clear rendered EMPTIES with gap-driven Gemini enrichment queries.

Executor for ``app.services.enrichment_queries`` — the registry built
from the all-94 empties census (836 empty instances across 29 classes).
The sweep walks EVERY active entity x EVERY registered query (never a
sample); the ``firmographics_extraction`` query is pinned to tier 0
(``_CRITICAL_SURFACES``) so the operator's firmographics gap-fill is
dispatched for all 94 clients before any lower-ranked empty class and a
budget cut can never starve it. For every entity x query:

  1. ``build_ctx`` probes the entity's ACTUAL gap; entities with the
     surface already populated return None and are skipped (no tokens
     spent re-deriving known data, no hallucination surface).
  2. The rendered prompt + grounding fingerprint route through the
     synthesis-cache decision gates — a prior validated answer is a
     0-token re-read, per the persistence mandate.
  3. Vertex output goes through the query's ``accept`` (STRICT JSON +
     verbatim-quote / E-ID / id-set validation; absence honesty) and,
     only when accepted, ``persist`` (fill-if-empty domain writes).

Modes:
  --dry-run             gap census only — counts per query, zero Vertex.
  --manifest PATH       write the fully-rendered per-client query
                        manifest (JSONL) — the formulated Gemini queries
                        for every empty, reviewable before any spend.
  (default hot run)     execute misses via Vertex, validate, persist —
                        BOUNDED-PARALLEL under a WALL-CLOCK BUDGET
                        (services.enrichment_runner; --budget-sec /
                        --concurrency, env twins DMA_ENRICH_*). At budget
                        it exits 0 with remaining counts; re-runs RESUME
                        via cache fingerprints (2026-07-05: the
                        sequential unbudgeted sweep burned its whole
                        1500s step timeout in the a52f723 build).
                        Registry order is the priority tier — a budget
                        cut trims the lowest-ranked empty classes first.

  python -m app.scripts.enrich_empty_surfaces --dry-run
  python -m app.scripts.enrich_empty_surfaces --manifest /tmp/queries.jsonl
  python -m app.scripts.enrich_empty_surfaces --queries sentiment_extraction --limit 5
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.services import synthesis_cache_db as cache_db
from app.services.enrichment_queries import ENRICHMENT_QUERIES
from app.services.enrichment_runner import (
    BudgetedEnrichmentRunner,
    EnrichItem,
    VertexGateway,
    env_int,
)
from app.services.enrichment_triggers import Trigger
from app.services.vertex_client import GeminiCall, get_vertex_client, resolve_model_id

# Operator safeguard (2026-07-06): surfaces that must NEVER be starved by the
# wall-clock budget — the firmographics gap-fill the deploy depends on. These
# are moved to the FRONT of the sweep (tier 0) regardless of registry order, so
# EVERY active entity with an empty enrichable firmographics field is probed
# before any lower-ranked empty class. Vertex-cold safe: the gap probe still
# runs, and a cold/offline generation is dropped by the acceptor (nothing
# fabricated) — the fields fill on the Vertex-warm deploy regen.
_CRITICAL_SURFACES: tuple[str, ...] = ("firmographics_extraction",)


class _SafeMap(dict):
    def __missing__(self, key: str) -> str:
        return ""


def _tpl_version(template: str) -> str:
    return "v1-" + hashlib.sha256(template.encode()).hexdigest()[:10]


def _fingerprint(query_name: str, template: str, ctx: dict) -> tuple[str, str]:
    bundle = str(ctx.get("recent_evidence") or "")
    bundle_hash = hashlib.sha256(bundle.encode()).hexdigest()
    fp = hashlib.sha256(
        f"{_tpl_version(template)}|{bundle_hash}|v7.0|{query_name}".encode()
    ).hexdigest()
    return fp, bundle_hash


def _provenance(surface: str, model_alias: str) -> dict:
    return {
        "source": "vertex", "surface": surface,
        "model_id": resolve_model_id(model_alias),
        "synthesized_at": datetime.now(UTC).isoformat(),
    }


async def _process_gap(session, gateway: VertexGateway, name: str,
                       did: str, counts: dict[str, dict[str, int]],
                       args: argparse.Namespace) -> str:
    """One (query, entity) unit: gap probe → cache check → Vertex →
    accept → persist. Returns the runner's outcome label; per-query
    counters are updated in-place (event-loop-only mutation — safe)."""
    q = ENRICHMENT_QUERIES[name]
    try:
        ctx = await q.build_ctx(session, did)
    except Exception as exc:
        await session.rollback()
        if args.verbose:
            print(f"  ctx-err {name}:{did}: {exc}")
        return "context_error"
    if ctx is None:
        counts[name]["skip"] += 1
        return "skip"
    counts[name]["gap"] += 1
    prompt = q.template.format_map(_SafeMap(ctx))
    fp, bundle_hash = _fingerprint(name, q.template, ctx)

    cached = await asyncio.to_thread(
        cache_db.safe_fetch_active, "entity", did, q.surface, fp)
    if cached is not None:
        counts[name]["cache_hit"] += 1
        return "hit"

    t0 = time.monotonic()
    out_text = (await gateway.generate(q.surface, GeminiCall(
        surface=q.surface, model=q.model, prompt=prompt,
        temperature=0.2, max_output_tokens=2048,
    ))).strip()
    counts[name]["called"] += 1

    payload = q.accept(out_text, ctx)
    latency_ms = int((time.monotonic() - t0) * 1000)
    if payload is None:
        counts[name]["blocked"] += 1
        await asyncio.to_thread(
            cache_db.safe_insert_or_supersede,
            target_kind="entity", target_id=did,
            surface=q.surface, model=resolve_model_id(q.model),
            input_fingerprint=fp,
            prompt_template_version=_tpl_version(q.template),
            grounding_bundle_hash=bundle_hash,
            catalogue_version="v7.0", output_text=out_text[:8000],
            validators_passed=False, latency_ms=latency_ms,
        )
        if args.verbose:
            print(f"  blocked {name}:{did}")
        return "validator_blocked"
    counts[name]["accepted"] += 1
    prov = _provenance(q.surface, q.model)
    try:
        rows = await q.persist(session, did, payload, prov)
        await session.commit()
    except Exception as exc:
        await session.rollback()
        print(f"  persist-err {name}:{did}: {exc}")
        return "persist_error"
    counts[name]["persisted_rows"] += rows
    await asyncio.to_thread(
        cache_db.safe_insert_or_supersede,
        target_kind="entity", target_id=did, surface=q.surface,
        model=resolve_model_id(q.model), input_fingerprint=fp,
        prompt_template_version=_tpl_version(q.template),
        grounding_bundle_hash=bundle_hash,
        catalogue_version="v7.0",
        output_text=out_text[:8000],
        output_json={"payload_rows": rows, **prov},
        validators_passed=True, latency_ms=latency_ms,
    )
    return "synthesized"


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2
    engine = create_async_engine(
        dsn, pool_pre_ping=True,
        pool_size=max(2, args.concurrency), max_overflow=4)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    # Queries SUPERSEDED by a dedicated iterative enricher — skipped in the
    # default run so no datum is Gemini-enriched twice (token duplication).
    # focus_kpi_extraction → app.scripts.enrich_focus_kpis (rich-context,
    # baseline+target, ledgered). Still runnable explicitly via --queries.
    _SUPERSEDED = frozenset({"focus_kpi_extraction"})
    names = (args.queries.split(",") if args.queries
             else [n for n in ENRICHMENT_QUERIES if n not in _SUPERSEDED])
    unknown = [n for n in names if n not in ENRICHMENT_QUERIES]
    if unknown:
        print(f"unknown queries: {unknown}", file=sys.stderr)
        return 2
    # Pin the critical firmographics safeguard to the front (stable): a budget
    # cut trims the lowest-ranked empty classes first, so this guarantees every
    # entity's empty firmographics is probed/filled before any of them.
    _orig = {n: i for i, n in enumerate(names)}
    names.sort(key=lambda n: (n not in _CRITICAL_SURFACES, _orig[n]))

    counts: dict[str, dict[str, int]] = {
        n: {"gap": 0, "skip": 0, "cache_hit": 0, "called": 0,
            "accepted": 0, "blocked": 0, "persisted_rows": 0}
        for n in names
    }

    dry = bool(args.dry_run or args.manifest)
    async with maker() as session:
        ents = (await session.execute(text(
            """
            SELECT display_id FROM entities
            WHERE status = 'ACTIVE'
              AND LOWER(COALESCE(name,'')) NOT LIKE '%(synthetic)%'
            ORDER BY display_id
            """ + ("" if args.limit is None else " LIMIT :lim")),
            {} if args.limit is None else {"lim": args.limit})).all()
        dids = [e.display_id for e in ents]

        # ── dry-run / manifest: DB-only gap census, zero Vertex, kept
        # sequential (one session; manifest lines stay ordered). ────────
        if dry:
            manifest_fh = open(args.manifest, "w") if args.manifest else None  # noqa: SIM115
            for did in dids:
                for name in names:
                    q = ENRICHMENT_QUERIES[name]
                    try:
                        ctx = await q.build_ctx(session, did)
                    except Exception as exc:
                        await session.rollback()
                        if args.verbose:
                            print(f"  ctx-err {name}:{did}: {exc}")
                        continue
                    if ctx is None:
                        counts[name]["skip"] += 1
                        continue
                    counts[name]["gap"] += 1
                    if manifest_fh:
                        manifest_fh.write(json.dumps({
                            "display_id": did, "query": name,
                            "empty_class": q.empty_class, "model": q.model,
                            "fingerprint": _fingerprint(
                                name, q.template, ctx)[0],
                            "prompt": q.template.format_map(_SafeMap(ctx)),
                        }) + "\n")
            if manifest_fh:
                manifest_fh.close()
                print(f"# manifest written -> {args.manifest}")

    if dry:
        _print_summary(counts)
        await engine.dispose()
        return 0

    # ── hot path: bounded-parallel budgeted sweep (registry order =
    # census priority; queries are the tier so a budget cut trims the
    # lowest-ranked empty classes first). ───────────────────────────────
    items: list[EnrichItem] = []
    for tier, name in enumerate(names):
        for did in dids:
            def _make(name: str = name, did: str = did):
                async def _proc(sess, gw) -> str:
                    return await _process_gap(sess, gw, name, did,
                                              counts, args)
                return _proc

            items.append(EnrichItem(
                key=f"{name}:{did}", surface=ENRICHMENT_QUERIES[name].surface,
                tier=tier, process=_make(),
                trigger=Trigger.G1_EMPTY_FIELD))

    gateway = VertexGateway(vertex_client=get_vertex_client(),
                            max_calls=args.max_calls)
    runner = BudgetedEnrichmentRunner(
        session_maker=maker, gateway=gateway,
        budget_sec=args.budget_sec, concurrency=args.concurrency)
    result = await runner.run(items, verbose=args.verbose)

    _print_summary(counts)
    print(f"# enrich_empty_surfaces: {result.summary()} "
          f"(items={len(items)} vertex_calls={gateway.calls} "
          f"budget={runner.budget_sec:.0f}s x{runner.concurrency} "
          f"{'cold' if gateway.cold else 'live'})")
    if gateway.cold:
        print(f"#   vertex cold: {gateway.cold_reason[:160]}")
    await engine.dispose()
    return 0


def _print_summary(counts: dict[str, dict[str, int]]) -> None:
    print("# enrich_empty_surfaces summary")
    for name, c in counts.items():
        print(f"  {name:32s} gaps={c['gap']:3d} skip={c['skip']:3d} "
              f"hit={c['cache_hit']:3d} called={c['called']:3d} "
              f"accepted={c['accepted']:3d} blocked={c['blocked']:3d} "
              f"rows={c['persisted_rows']:3d}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queries", help="comma list (default: all)")
    ap.add_argument("--limit", type=int, default=None, help="entity cap")
    ap.add_argument("--max-calls", type=int, default=400)
    ap.add_argument("--budget-sec", type=float, default=None,
                    help="wall-clock budget (default $DMA_ENRICH_BUDGET_SEC "
                         "or 1200) — exits 0 with remaining counts; re-runs "
                         "RESUME via cache fingerprints")
    ap.add_argument("--concurrency", type=int,
                    default=env_int("DMA_ENRICH_CONCURRENCY", 6),
                    help="parallel Vertex workers "
                         "(default $DMA_ENRICH_CONCURRENCY or 6)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--manifest", help="write rendered query manifest JSONL")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    raise SystemExit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
