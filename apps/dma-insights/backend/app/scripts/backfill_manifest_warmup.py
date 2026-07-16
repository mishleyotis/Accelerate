"""Operator-runnable backfill for runs.material_manifest_hash +
runs.artifact_manifest_json on legacy rows.

Per the integrated batched plan Batch 8: when a prod DB pre-dates
migration 033 (material_manifest_hash) or migration 034
(artifact_manifest_json), some runs rows have those columns NULL.
The Batch-2 selective re-ingest path then falls back to the legacy
mtime check on every ingest, losing the per-artifact diff benefit.
The warm-up branch inside ``_ingest_local_dir`` populates these
columns lazily on the next ingest pass -- but that requires the
local corpus to be present.

This script provides a one-shot, deterministic alternative: for
every run whose entity has a ``drive_folder_id`` starting with
``local:`` and whose hash columns are NULL, compute the manifest
from the on-disk corpus and persist it. The script is idempotent
(re-running is a no-op for already-populated rows) and uses a
single batched UPDATE per package so wall-clock stays bounded.

Defense-in-depth: the script
  - never deletes / overwrites a populated hash column
  - emits a per-package log line so the operator can audit progress
  - has a ``--dry-run`` mode that shows what would be updated
    without writing
  - has a ``--all-runs`` mode that re-computes hashes for EVERY run
    (used when the artifact_manifest classifier changes and the
    operator wants to refresh hashes proactively)

Usage:

    export DATABASE_URL=postgresql+asyncpg://...
    # Warmup only the NULL rows (fast):
    python -m app.scripts.backfill_manifest_warmup \\
        --dir tests/fixtures/dma_packages_batches

    # Force refresh ALL runs (slow; use after classifier change):
    python -m app.scripts.backfill_manifest_warmup \\
        --dir tests/fixtures/dma_packages_batches --all-runs

    # Preview (no DB writes):
    python -m app.scripts.backfill_manifest_warmup \\
        --dir tests/fixtures/dma_packages_batches --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text

from app.database import get_sessionmaker
from app.scripts.historical_backfill import _find_local_package_roots
from app.services.artifact_manifest import compute_package_manifest


async def main_async(args: argparse.Namespace) -> int:
    base = Path(args.dir)
    if not base.is_dir():
        print(f"FATAL: --dir path is not a directory: {base}", flush=True)
        return 2

    roots = _find_local_package_roots(base)
    if not roots:
        print(f"FATAL: no package roots discovered under {base}", flush=True)
        return 3

    sm = get_sessionmaker()
    n_inspected = 0
    n_updated = 0
    n_skipped_already_populated = 0
    n_skipped_no_run = 0
    n_skipped_no_changes_needed = 0

    for root in roots:
        client_name = root.name
        for parent in [root, *root.parents]:
            if parent.name.endswith(" - DMA") or parent.name.endswith("- DMA"):
                client_name = parent.name
                break
        folder_key = f"local:{client_name}"
        n_inspected += 1

        # Find the entity's run(s).
        async with sm() as session:
            rows = (await session.execute(
                text(
                    "SELECT r.id::text, r.request_id, "
                    "       r.material_manifest_hash, "
                    "       r.artifact_manifest_json IS NOT NULL "
                    "         AS has_json "
                    "FROM runs r "
                    "JOIN entities e ON e.id = r.entity_id "
                    "WHERE e.drive_folder_id = :fid "
                    "ORDER BY r.completed_at DESC NULLS LAST"
                ),
                {"fid": folder_key},
            )).all()

        if not rows:
            n_skipped_no_run += 1
            continue

        # Decide which rows need backfill. --all-runs forces every row;
        # default mode only fills rows where hash IS NULL OR json IS
        # NULL.
        targets = [
            r for r in rows
            if args.all_runs
            or r.material_manifest_hash is None
            or not r.has_json
        ]
        if not targets:
            n_skipped_already_populated += 1
            continue

        # Compute the manifest once per package.
        try:
            manifest = compute_package_manifest(root)
        except Exception as e:
            print(
                f"ERROR:manifest:{client_name}: "
                f"{type(e).__name__}: {e!s}",
                flush=True,
            )
            continue
        material_hash = manifest.material_manifest_hash
        if not material_hash:
            n_skipped_no_changes_needed += 1
            continue
        manifest_json = json.dumps([
            {"rel_path": e.rel_path, "cls": e.cls,
             "content_hash": e.content_hash, "size_bytes": e.size_bytes}
            for e in manifest.entries
        ])

        # Batched UPDATE per package: one statement updates every
        # target run for this folder. Reduces N round-trips to 1.
        if args.dry_run:
            print(
                f"DRYRUN:{client_name}: would update "
                f"{len(targets)} run(s) (hash={material_hash[:8]}..., "
                f"manifest_files={manifest.material_count})",
                flush=True,
            )
            continue

        async with sm() as session:
            await session.execute(
                text(
                    "UPDATE runs SET "
                    "  material_manifest_hash = :h, "
                    "  artifact_manifest_json = CAST(:m AS JSONB) "
                    "WHERE id = ANY(CAST(:ids AS uuid[]))"
                ),
                {
                    "h": material_hash,
                    "m": manifest_json,
                    "ids": [r.id for r in targets],
                },
            )
            await session.commit()
        n_updated += len(targets)
        print(
            f"OK:{client_name}: updated {len(targets)} run(s) "
            f"[mat={manifest.material_count} cos={manifest.cosmetic_count} "
            f"unk={manifest.unknown_count}]",
            flush=True,
        )

    print(
        f"\nWARMUP BACKFILL: {n_updated} runs updated, "
        f"{n_skipped_already_populated} packages skipped (already "
        f"populated), {n_skipped_no_run} packages skipped (no "
        f"matching run row), {n_skipped_no_changes_needed} packages "
        f"skipped (empty manifest), {n_inspected} inspected total",
        flush=True,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument(
        "--dir", required=True,
        help="Path to the corpus root (e.g. tests/fixtures/dma_packages_batches)",
    )
    p.add_argument(
        "--all-runs", action="store_true",
        help=(
            "Force refresh hash + manifest for EVERY run, not just "
            "NULL rows. Use after a classifier change."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be updated; no DB writes.",
    )
    return asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
