"""A4 — CI database seeder.

Ingests the 5 sanitized DMA fixtures from
`tests/fixtures/dma_packages_sanitized/` into the live CI Postgres so
E2E tests (Playwright personas, cross-user persistence, smoke probes)
have populated data to render.

The script is idempotent: re-running against an already-seeded DB is
a no-op (the underlying `persist_package` UPSERTs via `request_id`).

State branches:
  - cold_start         → seeds all 5 fixtures from cold
  - already_seeded     → every fixture's run_id already exists in
                          `runs.request_id` → reports + exits 0
  - partial_seed       → some fixtures already seeded (re-runs
                          intelligently)
  - fixture_missing    → fixture dir not on disk → regenerates first
  - db_unreachable     → exits 2 with diagnostic (alembic head check
                          is upstream of this — caller runs migrations
                          first)

Usage:
    # Run in CI after `alembic upgrade head`:
    python -m app.scripts.seed_ci

    # Force regen + reseed:
    python -m app.scripts.seed_ci --force-regen

    # Only seed a subset (debugging):
    python -m app.scripts.seed_ci --only regions,wsfs

Exit codes:
  0 — every requested fixture is persisted
  1 — at least one fixture failed to parse / persist
  2 — DB unreachable / alembic head missing
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Resolve package + DB imports without depending on env-based config.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


FIXTURE_NAMES = ("regions", "amalgamated", "anb", "wsfs", "americu", "richbank")


async def _ensure_catalogue_bootstrap(fixture_root: Path) -> None:
    """Seed the minimum catalogue rows so seeded runs persist with all
    their subcap_scores. Idempotent.

    Rows seeded:
      - `ccg_catalog_versions` v7.0 (FK target for `runs.ccg_catalog_version`)
      - `ccg_pillars` x 4 (P1..P4)
      - `ccg_categories` x 16 (P{1..4}C{1..4})
      - `ccg_l1_capabilities` x 16 (one per category, slug-derived)
      - `ccg_subcaps` x all IDs the fixtures reference, so the
        `CatalogueResolver.resolve_subcap()` lookup hits and the
        score rows actually INSERT instead of incrementing unresolved.

    Production catalogue load fills all 25 ccg_* tables from the 4
    pillar workbooks; that's the `workers/ccg_loader` job. For CI
    seeding we only need the rows the parser will reference.
    """
    from sqlalchemy import text

    from app.database import get_sessionmaker

    # Discover every subcap_id any fixture references.
    # We parse the fixtures on disk directly — no dependency on the
    # generator module, which lives in tests/ and isn't shipped in the
    # production backend image.
    from app.services.parsers.dma_package import parse_package
    subcap_ids: set[str] = set()
    for name in FIXTURE_NAMES:
        path = fixture_root / name
        if not path.exists():
            continue
        try:
            pkg = parse_package(path)
            subcap_ids.update(s.subcap_id for s in (pkg.subcap_scores or []))
        except Exception:
            pass

    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            text("""
                INSERT INTO ccg_catalog_versions (
                    version, released_at, source_sha256s, loader_run_id,
                    frozen_at, notes
                ) VALUES (
                    'v7.0', NOW(),
                    CAST('{"seed_ci": "bootstrap"}' AS JSONB),
                    gen_random_uuid(),
                    NOW(),
                    'seeded by app.scripts.seed_ci for CI'
                ) ON CONFLICT (version) DO NOTHING
            """),
        )

        # 4 pillars
        for pid, name in (("P1", "Strategy"), ("P2", "Customer Experience"),
                          ("P3", "Process Automation"), ("P4", "Data & AI")):
            await session.execute(
                text("""
                    INSERT INTO ccg_pillars (
                        version, pillar_id, name, description,
                        category_count, l1_capability_count, subcap_count
                    ) VALUES ('v7.0', :pid, :name, :name, 4, 4, 16)
                    ON CONFLICT DO NOTHING
                """),
                {"pid": pid, "name": name},
            )

        # 16 categories + 16 capabilities (one capability per category)
        for p in (1, 2, 3, 4):
            for c in (1, 2, 3, 4):
                cat_id = f"P{p}C{c}"
                await session.execute(
                    text("""
                        INSERT INTO ccg_categories (
                            version, category_id, pillar_id, name
                        ) VALUES ('v7.0', :cat, :pid, :name)
                        ON CONFLICT DO NOTHING
                    """),
                    {"cat": cat_id, "pid": f"P{p}",
                     "name": f"Category {cat_id}"},
                )
                await session.execute(
                    text("""
                        INSERT INTO ccg_l1_capabilities (
                            version, l1_id, category_id, name
                        ) VALUES ('v7.0', :l1, :cat, :name)
                        ON CONFLICT DO NOTHING
                    """),
                    {"l1": f"{cat_id}.1", "cat": cat_id,
                     "name": f"Capability {cat_id}.1"},
                )

        # Subcap rows for every ID the fixtures reference. The
        # resolver requires the row to exist for the score INSERT
        # to land; without this every score-insert silently
        # increments the `unresolved` counter and skips.
        for sid in sorted(subcap_ids):
            # Derive category + capability from the v7 ID shape:
            # "P{p}C{c}.{ord}.{sub}"  →  cat="P{p}C{c}",  l1="P{p}C{c}.1"
            cat = sid.rsplit(".", 2)[0]
            l1 = f"{cat}.1"
            await session.execute(
                text("""
                    INSERT INTO ccg_subcaps (
                        version, subcap_id, l1_id, name, description,
                        solution_type, tier, zennify_status
                    ) VALUES (
                        'v7.0', :sid, :l1, :name, 'seed_ci stub',
                        'Hybrid', 'T1', 'Active'
                    )
                    ON CONFLICT DO NOTHING
                """),
                {"sid": sid, "l1": l1, "name": f"Subcap {sid}"},
            )

        await session.commit()


async def _seed_one(fixture_path: Path, *, dry_run: bool) -> dict:
    """Parse + persist one fixture. Returns a result dict the CLI
    summarises in the final report."""
    from sqlalchemy import text

    from app.database import get_sessionmaker
    from app.services.parsers.dma_package import parse_package
    from app.services.parsers.package_persist import persist_package

    name = fixture_path.name
    pkg = parse_package(fixture_path)
    run_id_target = pkg.run_manifest.run_id
    if not run_id_target:
        return {"fixture": name, "ok": False,
                "error": "parser returned empty run_id"}

    # Dry-run skips ALL DB IO — parse-only smoke for fixture validity.
    if dry_run:
        return {"fixture": name, "ok": True, "state": "dry_run",
                "run_id": run_id_target,
                "subcaps": len(pkg.subcap_scores or []),
                "evidence": len(pkg.evidence or []),
                "peers": len(pkg.peers or [])}

    # Idempotency probe: short-circuit if the run already exists.
    sm = get_sessionmaker()
    async with sm() as session:
        prior = (await session.execute(
            text("SELECT id, status FROM runs WHERE request_id = :rid"),
            {"rid": run_id_target},
        )).first()
        if prior is not None:
            return {
                "fixture": name, "ok": True, "state": "already_seeded",
                "run_id": run_id_target, "db_id": str(prior.id),
                "subcaps": len(pkg.subcap_scores or []),
                "evidence": len(pkg.evidence or []),
            }

    # Persist
    async with sm() as session:
        try:
            # MANUAL_BACKFILL is the only data_source value that fits
            # the existing runs_data_source_chk CHECK constraint without
            # an additional migration; CI seeding is functionally an
            # admin-driven manual ingest.
            db_run_id, warnings = await persist_package(
                session, pkg,
                data_source="MANUAL_BACKFILL",
                drive_folder_id=f"ci-seed-fixture-{name}",
            )
            await session.commit()
            return {
                "fixture": name, "ok": True, "state": "seeded",
                "run_id": run_id_target, "db_id": db_run_id,
                "subcaps": len(pkg.subcap_scores or []),
                "evidence": len(pkg.evidence or []),
                "peers": len(pkg.peers or []),
                "warnings": len(warnings),
            }
        except Exception as e:
            await session.rollback()
            return {"fixture": name, "ok": False,
                    "error": f"{type(e).__name__}: {e}"}


def _ensure_fixtures(fixture_root: Path, force_regen: bool) -> None:
    """Regenerate fixtures if missing or forced. Idempotent.

    State branches:
      - all_present + !force_regen → no-op (production CI path; fixtures
                                      shipped pre-generated in the image).
      - missing + generator_available → regenerate from generator
                                         (dev-only path; tests/ exists).
      - missing + generator_unavailable → hard exit with actionable
                                           error (production image must
                                           ship pre-generated fixtures
                                           — bug in Dockerfile if seen).
      - force_regen → require generator (dev-only).
    """
    if not force_regen and all(
        (fixture_root / n).exists() for n in FIXTURE_NAMES
    ):
        return  # production-CI hot path — fixtures already on disk
    # We need the generator module — only available in dev, not in
    # the production backend image (tests/ is not COPY'd).
    sys.path.insert(0, str(fixture_root.parent.parent))
    try:
        from tests.fixtures.dma_packages_sanitized.generate_fixtures import (
            regenerate,
        )
    except ModuleNotFoundError as e:
        missing = [
            n for n in FIXTURE_NAMES if not (fixture_root / n).exists()
        ]
        raise RuntimeError(
            "seed_ci: fixtures missing and generator unavailable.\n"
            f"  Fixture root: {fixture_root}\n"
            f"  Missing fixtures: {missing}\n"
            f"  Generator import failed: {e}\n"
            "  Fix: either ship pre-generated fixtures in the image "
            "(backend.Dockerfile COPY backend/tests/fixtures/"
            "dma_packages_sanitized) or run in a dev env where tests/ "
            "is on disk."
        ) from e
    regenerate(fixture_root)


async def _check_db() -> tuple[bool, str]:
    """Probe DB + alembic head — caller exits 2 if either fails."""
    try:
        from sqlalchemy import text

        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from app.database import get_engine
        engine = get_engine()
        async with engine.connect() as conn:
            row = await conn.execute(
                text("SELECT version_num FROM alembic_version")
            )
            db_head = row.scalar_one_or_none()
        cfg_path = Path(__file__).resolve().parents[2] / "alembic.ini"
        cfg = Config(str(cfg_path))
        cfg.set_main_option(
            "script_location", str(cfg_path.parent / "alembic"),
        )
        code_head = ScriptDirectory.from_config(cfg).get_current_head()
        if db_head != code_head:
            return False, (
                f"alembic drift: db={db_head} code={code_head} — "
                f"run `alembic upgrade head` first"
            )
        return True, code_head or "unknown"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


async def main() -> int:
    parser = argparse.ArgumentParser(prog="seed_ci")
    parser.add_argument(
        "--only",
        help="comma-separated subset of fixture names to seed",
        default="",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="parse + idempotency-check only; do not persist",
    )
    parser.add_argument(
        "--force-regen", action="store_true",
        help="regenerate fixtures from generate_fixtures.py before seeding",
    )
    parser.add_argument(
        "--skip-db-check", action="store_true",
        help="skip alembic head check (use only when DB intentionally bare)",
    )
    args = parser.parse_args()

    # backend/app/scripts/seed_ci.py → parents[2] = backend/
    # The fixtures live at backend/tests/fixtures/... — sibling to app/.
    fixture_root = (
        Path(__file__).resolve().parents[2]
        / "tests" / "fixtures" / "dma_packages_sanitized"
    )
    _ensure_fixtures(fixture_root, args.force_regen)

    selected = (
        tuple(s.strip() for s in args.only.split(",") if s.strip())
        if args.only else FIXTURE_NAMES
    )
    invalid = [s for s in selected if s not in FIXTURE_NAMES]
    if invalid:
        print(f"unknown fixture(s): {invalid}", file=sys.stderr)
        return 1

    if not args.skip_db_check and not args.dry_run:
        ok, msg = await _check_db()
        if not ok:
            print(f"seed_ci: DB check failed — {msg}", file=sys.stderr)
            return 2
        print(f"seed_ci: DB ready (alembic head {msg})")
        # Bootstrap the catalogue version parent row so the
        # runs.ccg_catalog_version FK passes for each seeded run.
        await _ensure_catalogue_bootstrap(fixture_root)
        print("seed_ci: catalogue v7.0 bootstrap row ensured")

    started = time.time()
    results: list[dict] = []
    for name in selected:
        path = fixture_root / name
        if not path.exists():
            results.append({"fixture": name, "ok": False,
                            "error": f"fixture dir missing: {path}"})
            continue
        results.append(await _seed_one(path, dry_run=args.dry_run))

    # Report
    print()
    print(f"seed_ci: {len(results)} fixture(s), {time.time()-started:.1f}s")
    print("-" * 60)
    ok_count = sum(1 for r in results if r["ok"])
    new_count = sum(1 for r in results if r.get("state") == "seeded")
    skip_count = sum(1 for r in results if r.get("state") == "already_seeded")
    fail_count = len(results) - ok_count
    for r in results:
        if r["ok"]:
            marker = {
                "seeded": "+", "already_seeded": "=", "dry_run": "?",
            }.get(r.get("state", ""), "✓")
            print(
                f"  [{marker}] {r['fixture']:13} "
                f"run_id={r['run_id']:40} "
                f"subcaps={r.get('subcaps',0):>3} "
                f"evidence={r.get('evidence',0):>3} "
                f"peers={r.get('peers',0):>2}"
            )
        else:
            print(f"  [!] {r['fixture']:13} {r['error']}")
    print(f"summary: ok={ok_count} new={new_count} skip={skip_count} fail={fail_count}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
