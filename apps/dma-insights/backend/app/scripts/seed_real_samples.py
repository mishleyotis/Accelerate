"""Seed the 5 in-repo *real-sample* DMA packages into a live Postgres.

`seed_ci.py` ingests the sanitized fixtures (which intentionally carry
no recommendation files, no firmographics, etc. -- they exercise the
*skeleton* path). The real-sample packages under
`tests/fixtures/dma_packages_real_samples/` are the closest in-repo
proxy for production data: they ship the recommendation registers,
client-profile DOCX, evidence facts, and peer tables that light up D4
(recommendations / roadmap) and D5 (timeline / financials / sentiment).

This is the live-validation companion to `seed_ci`: same
`parse_package` + `persist_package` path, but it ALSO bootstraps every
subcap ID the real packages reference into `ccg_subcaps` (the FK target
the score INSERT needs) -- the sanitized bootstrap in `seed_ci` only
covers the sanitized fixtures' IDs.

Idempotent: re-running skips runs whose `request_id` already exists.

Usage (against the local dev Postgres):
    DATABASE_URL=postgresql+asyncpg://... \
    python -m app.scripts.seed_real_samples

Exit codes: 0 all persisted, 1 at least one failed, 2 DB unreachable.
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# backend/app/scripts/seed_real_samples.py -> parents[2] == backend/
REAL_SAMPLES_ROOT = (
    Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "dma_packages_real_samples"
)


async def _bootstrap_catalogue_for(subcap_ids: set[str]) -> None:
    """Ensure v7.0 + pillars/categories/capabilities + every referenced
    subcap exists so the score INSERT FK resolves. Idempotent; additive
    to whatever `seed_ci._ensure_catalogue_bootstrap` already seeded."""
    from sqlalchemy import text

    from app.database import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(text("""
            INSERT INTO ccg_catalog_versions (
                version, released_at, source_sha256s, loader_run_id,
                frozen_at, notes
            ) VALUES (
                'v7.0', NOW(), CAST('{"seed_real_samples":"bootstrap"}' AS JSONB),
                gen_random_uuid(), NOW(), 'seeded by seed_real_samples'
            ) ON CONFLICT (version) DO NOTHING
        """))
        for pid, name in (("P1", "Strategy"), ("P2", "Customer Experience"),
                          ("P3", "Process Automation"), ("P4", "Data & AI")):
            await session.execute(text("""
                INSERT INTO ccg_pillars (
                    version, pillar_id, name, description,
                    category_count, l1_capability_count, subcap_count
                ) VALUES ('v7.0', :pid, :name, :name, 4, 4, 16)
                ON CONFLICT DO NOTHING
            """), {"pid": pid, "name": name})
        # Derive every category + capability the subcap IDs imply (real
        # packages can reference category shapes the 4x4 grid misses).
        cats: set[str] = set()
        for sid in subcap_ids:
            cats.add(sid.rsplit(".", 2)[0])
        for cat_id in sorted(cats):
            pid = cat_id.split("C")[0] if "C" in cat_id else "P1"
            await session.execute(text("""
                INSERT INTO ccg_categories (version, category_id, pillar_id, name)
                VALUES ('v7.0', :cat, :pid, :name) ON CONFLICT DO NOTHING
            """), {"cat": cat_id, "pid": pid, "name": f"Category {cat_id}"})
            await session.execute(text("""
                INSERT INTO ccg_l1_capabilities (version, l1_id, category_id, name)
                VALUES ('v7.0', :l1, :cat, :name) ON CONFLICT DO NOTHING
            """), {"l1": f"{cat_id}.1", "cat": cat_id,
                   "name": f"Capability {cat_id}.1"})
        for sid in sorted(subcap_ids):
            cat = sid.rsplit(".", 2)[0]
            await session.execute(text("""
                INSERT INTO ccg_subcaps (
                    version, subcap_id, l1_id, name, description,
                    solution_type, tier, zennify_status
                ) VALUES (
                    'v7.0', :sid, :l1, :name, 'seed_real_samples stub',
                    'Hybrid', 'T1', 'Active'
                ) ON CONFLICT DO NOTHING
            """), {"sid": sid, "l1": f"{cat}.1", "name": f"Subcap {sid}"})
        await session.commit()


async def _seed_one(pkg_dir: Path) -> dict:
    from sqlalchemy import text

    from app.database import get_sessionmaker
    from app.services.parsers.dma_package import parse_package
    from app.services.parsers.package_persist import persist_package

    name = pkg_dir.name
    try:
        pkg = parse_package(pkg_dir)
    except Exception as e:
        return {"name": name, "ok": False, "error": f"parse: {type(e).__name__}: {e}"}
    run_id = pkg.run_manifest.run_id
    if not run_id:
        return {"name": name, "ok": False, "error": "empty run_id"}

    await _bootstrap_catalogue_for({s.subcap_id for s in (pkg.subcap_scores or [])})

    sm = get_sessionmaker()
    async with sm() as session:
        prior = (await session.execute(
            text("SELECT id FROM runs WHERE request_id = :rid"), {"rid": run_id},
        )).first()
        if prior is not None:
            return {"name": name, "ok": True, "state": "already_seeded",
                    "run_id": run_id,
                    "subcaps": len(pkg.subcap_scores or []),
                    "recs": len(pkg.recommendations or [])}
    async with sm() as session:
        try:
            db_run_id, warnings = await persist_package(
                session, pkg, data_source="MANUAL_BACKFILL",
                drive_folder_id=f"real-sample-{name}",
            )
            await session.commit()
            return {"name": name, "ok": True, "state": "seeded",
                    "run_id": run_id, "db_id": db_run_id,
                    "subcaps": len(pkg.subcap_scores or []),
                    "evidence": len(pkg.evidence or []),
                    "peers": len(pkg.peers or []),
                    "recs": len(pkg.recommendations or []),
                    "warnings": len(warnings)}
        except Exception as e:
            await session.rollback()
            return {"name": name, "ok": False, "error": f"persist: {type(e).__name__}: {e}"}


async def main() -> int:
    if not REAL_SAMPLES_ROOT.exists():
        print(f"real-samples dir missing: {REAL_SAMPLES_ROOT}", file=sys.stderr)
        return 2
    dirs = sorted(p for p in REAL_SAMPLES_ROOT.iterdir() if p.is_dir())
    started = time.time()
    results = [await _seed_one(d) for d in dirs]

    print()
    print(f"seed_real_samples: {len(results)} package(s), {time.time()-started:.1f}s")
    print("-" * 72)
    ok = sum(1 for r in results if r["ok"])
    for r in results:
        if r["ok"]:
            mark = {"seeded": "+", "already_seeded": "="}.get(r.get("state", ""), "?")
            print(f"  [{mark}] {r['name']:24} run_id={r.get('run_id',''):32} "
                  f"subcaps={r.get('subcaps',0):>3} recs={r.get('recs',0):>2} "
                  f"evidence={r.get('evidence',0):>3} peers={r.get('peers',0):>2}")
        else:
            print(f"  [!] {r['name']:24} {r['error']}")
    fail = len(results) - ok
    print(f"summary: ok={ok} fail={fail}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
