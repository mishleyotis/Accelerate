"""Backfill subcap->platform tags from the canonical v7.0 catalogue
workbooks and recompute persisted platform fit for every run.

Why this exists
---------------
``platform_fit`` is the deterministic D4 scorer (severity-weighted
gap-to-target per addressable subcap). Its addressability input is
``subcap_scores.platform_tags`` — which packages rarely ship and the
corpus seed left empty for all 64k rows, so EVERY platform card sat in
``INSUFFICIENT_EVIDENCE``. The authoritative mapping has existed all
along in the catalogue: each pillar workbook's capability map carries an
"L3 Platforms" cell per subcap (Salesforce product families, nCino,
Twilio, ...). This script makes that mapping live:

  1. Parse the 4 pillar workbooks with the SAME loader parsers the
     ccg_loader job uses (no duplicate parsing logic).
  2. Map each subcap's L3 product names onto the five scored platform
     ids (PLATFORM_DISPLAY) via a deterministic keyword table.
  3. UPDATE ``subcap_scores.platform_tags`` for rows that don't already
     carry package-shipped tags (package data stays authoritative).
  4. Re-run the SAME ingest-time fit persister
     (``package_persist._persist_platform_scores``) per ACTIVE run so
     ``platform_scores`` reflects the new addressability.

Defensible by construction: the catalogue is the canonical Zennify
capability->platform map (CLAUDE.md "V7.0 is canonical"); the fit
formula is unchanged; package-shipped tags are never overwritten.

Usage:
  export DATABASE_URL=postgresql+asyncpg://...
  python -m app.scripts.apply_catalogue_platforms \
      --workbooks-dir docs/reference/catalogue/v7.0 [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# The product-name → scored-platform keyword map + mapper now live in
# app.services.parsers.tech_linker (shared with the ingest-time linker so
# the offline backfill and `persist_package` map names identically).
from app.services.parsers.tech_linker import map_l3_to_platform as _map_platforms


def _resolve_workbooks_dir(given: str) -> Path:
    """Find the dir that actually holds the `Pillar_*_v7.0.xlsx` workbooks.

    The workbooks live at the app root (`apps/dma-insights/docs/reference/
    catalogue/v7.0`), but this script ships in the backend package one level
    down. A bare `cd backend && python -m ...` resolved the default relative
    path to `backend/docs/...` (absent) → 0 tags → every D4 card sat at fit=0
    (QA 2026-06-15). Try the given path, then app-root-relative, then a bounded
    search, so the tagger works from any CWD and inside the Cloud Run job."""
    candidates = [Path(given)]
    app_root = Path(__file__).resolve().parents[3]  # apps/dma-insights/
    candidates.append(app_root / "docs" / "reference" / "catalogue" / "v7.0")
    candidates.append(app_root / given)
    for cand in candidates:
        if cand.is_dir() and any(cand.glob("Pillar_*_v7.0.xlsx")):
            return cand
    # last resort: locate any matching workbook under the app root
    hits = sorted(app_root.glob("**/Pillar_*_v7.0.xlsx"))
    return hits[0].parent if hits else Path(given)


def _load_catalogue_tags(workbooks_dir: Path) -> dict[str, list[str]]:
    """subcap_id -> [platform ids] from the 4 pillar workbooks."""
    from openpyxl import load_workbook

    try:
        from workers.ccg_loader.parsers import parse_capability_map
    except ModuleNotFoundError:
        # `workers` lives at the app root (apps/dma-insights/), one level
        # above the backend package this script ships in. The backend
        # image bakes both onto PYTHONPATH, but a bare local invocation
        # (`cd backend && python -m app.scripts.apply_catalogue_platforms`)
        # crashed with `No module named 'workers'` — and because the
        # §2c refresh chain is fail-soft, the whole platform-fit
        # backfill silently no-opped (QA audit 2026-06-11: every D4
        # card at fit=0). Self-resolve the app root instead of relying
        # on the caller's PYTHONPATH.
        app_root = Path(__file__).resolve().parents[3]
        if (app_root / "workers").is_dir():
            sys.path.insert(0, str(app_root))
        from workers.ccg_loader.parsers import parse_capability_map

    tags: dict[str, list[str]] = {}
    for wb_path in sorted(workbooks_dir.glob("Pillar_*_v7.0.xlsx")):
        pillar = f"P{wb_path.name.split('_')[1]}"
        wb = load_workbook(wb_path, read_only=True, data_only=True)
        # Same exact-title convention parse_workbook_tabs uses.
        ws = next((w for w in wb.worksheets
                   if w.title.strip() == "2_Capability_Map"), None)
        if ws is None:
            print(f"  ! no capability-map tab in {wb_path.name}", file=sys.stderr)
            continue
        res = parse_capability_map(ws, "v7.0", pillar)
        for row in res.rows:
            sid = row.get("subcap_id")
            mapped = _map_platforms(row.get("l3_platforms"))
            if sid and mapped:
                tags[str(sid)] = mapped
    return tags


async def main_async(args: argparse.Namespace) -> int:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL not set", file=sys.stderr)
        return 2

    wb_dir = _resolve_workbooks_dir(args.workbooks_dir)
    print(f"# workbooks dir: {wb_dir}")
    tags = _load_catalogue_tags(wb_dir)
    print(f"# catalogue platform map: {len(tags)} subcaps tagged "
          f"({sum(len(v) for v in tags.values())} platform links)")
    if not tags:
        return 1

    engine = create_async_engine(dsn, pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    from app.services.parsers.package_persist import _persist_platform_scores

    async with maker() as session:
        # Alias bridge: runs on OLDER catalogue structures (v5.x / v2.x
        # — 17 of the validation corpus's 101) carry subcap ids v7
        # doesn't know. When the catalogue ships bridge rows
        # (ccg_subcap_aliases prior_subcap_id -> current_subcap_id),
        # extend the tag map so those rows inherit the v7 platform
        # mapping through their alias. Empty bridge -> no-op; the v7
        # supplement stays id-aligned-only (never guesses).
        alias_rows = (
            await session.execute(text(
                """
                SELECT prior_subcap_id, current_subcap_id
                FROM ccg_subcap_aliases
                WHERE current_version = 'v7.0'
                  AND migration_action != 'DROPPED'
                """))
        ).all()
        aliased = 0
        for a in alias_rows:
            cur = tags.get(a.current_subcap_id)
            if cur and a.prior_subcap_id not in tags:
                tags[a.prior_subcap_id] = cur
                aliased += 1
        if alias_rows:
            print(f"# alias bridge: {len(alias_rows)} rows -> "
                  f"{aliased} prior-version subcaps inherited v7 tags")

        updated = 0
        # Single statement per platform-set bucket would be fancier; a
        # tight loop over distinct subcap ids keeps it obvious and this
        # runs offline (deploy refresh), not on a hot path.
        for sid, pids in tags.items():
            res = await session.execute(text(
                """
                UPDATE subcap_scores
                   SET platform_tags = CAST(:pids AS varchar[])
                 WHERE subcap_id = :sid
                   AND cardinality(platform_tags) = 0
                """), {"sid": sid, "pids": pids})
            updated += res.rowcount or 0
        print(f"# subcap_scores rows tagged: {updated}")

        runs = (
            await session.execute(text(
                """
                SELECT r.id AS run_id, r.entity_id, e.display_id
                FROM runs r JOIN entities e ON e.id = r.entity_id
                WHERE r.status = 'ACTIVE' ORDER BY e.display_id
                """ + ("" if args.limit is None else " LIMIT :lim")),
                {} if args.limit is None else {"lim": args.limit})
        ).all()
        wrote = 0
        for run in runs:
            n = await _persist_platform_scores(
                session, run_id=run.run_id, entity_id=run.entity_id,
            )
            wrote += n or 0
        await session.commit()
        print(f"# platform_scores recomputed: {wrote} rows across {len(runs)} runs")
    await engine.dispose()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--workbooks-dir", default="docs/reference/catalogue/v7.0")
    p.add_argument("--limit", type=int)
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
