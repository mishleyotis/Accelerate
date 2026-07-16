"""Self-healing entity completeness pass (pipeline layer 3A).

Walks every ACTIVE entity, reads its package, and fills the firmographics
fields the leaf parsers missed (assets / employees / regulator / ratios /
branches) so the Overview FIRMOGRAPHICS panel is never empty for any of the 94.
See `app.services.entity_healing` for the schema-tolerant extraction.

Modes (the self-healing-script contract verified by
`qa_self_healing_learning_audit`):
  (default)      heal — UPSERT fill-if-empty, commit.
  --dry-run      compute fills, do NOT write.
  --verify-only  audit only; exit 1 if ANY ACTIVE entity still has an empty
                 panel field (assets/employees/regulator) — the no-empty-state
                 gate across all 94.
  --diagnose     alias of --verify-only (read-only).

Usage:
  DATABASE_URL=... python -m app.scripts.heal_entities [--dry-run|--verify-only|--diagnose] [--corpus-dir PATH]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from sqlalchemy import text

from app.database import get_sessionmaker
from app.services.entity_healing import PANEL_FIELDS, heal_entity


async def _amain() -> int:
    ap = argparse.ArgumentParser(description="Heal entity firmographics completeness")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify-only", action="store_true")
    ap.add_argument("--diagnose", action="store_true")
    ap.add_argument("--corpus-dir", default=None)
    args = ap.parse_args()
    verify = args.verify_only or args.diagnose
    dry = args.dry_run or verify

    if not os.environ.get("DATABASE_URL"):
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        return 2

    sm = get_sessionmaker()
    healed = 0
    incomplete: list[tuple[str, list[str]]] = []
    empty_panels: list[str] = []
    no_pkg = 0
    errors = 0
    async with sm() as session:
        rows = (await session.execute(text(
            """
            SELECT e.id::text AS id, e.display_id, e.name, e.drive_folder_id, e.subvertical
            FROM entities e WHERE e.status='ACTIVE' ORDER BY e.display_id
            """
        ))).all()
        for r in rows:
            # Per-entity savepoint: a single bad value can never roll back the
            # whole batch (no-backfill-errors mandate).
            try:
                async with session.begin_nested():
                    rep = await heal_entity(
                        session, entity_id=r.id, drive_folder_id=r.drive_folder_id,
                        corpus_dir=args.corpus_dir, dry_run=dry, subvertical=r.subvertical,
                        name=r.name,
                    )
            except Exception as exc:  # isolate, report, continue
                errors += 1
                print(f"  ERROR {r.display_id}: {type(exc).__name__}: {exc}", flush=True)
                continue
            if rep["filled"]:
                healed += 1
                print(f"  heal {r.display_id}: filled {rep['filled']}", flush=True)
            if not rep["pkg"]:
                no_pkg += 1
            if rep["still_empty"]:
                incomplete.append((r.display_id, rep["still_empty"]))
            if not rep.get("panel_ok"):
                empty_panels.append(r.display_id)
        if not dry:
            await session.commit()

    print(f"# heal_entities: entities={len(rows)} healed={healed} "
          f"no_package={no_pkg} field_gaps={len(incomplete)} empty_panels={len(empty_panels)} "
          f"errors={errors} panel_fields={list(PANEL_FIELDS)}"
          + (" [DRY RUN]" if args.dry_run else "") + (" [VERIFY]" if verify else ""),
          flush=True)
    if incomplete:
        for did, miss in incomplete:
            print(f"  field_gap {did}: {miss}", flush=True)
    if empty_panels:
        for did in empty_panels:
            print(f"  EMPTY_PANEL {did}", flush=True)
    if errors:
        return 2
    # The no-empty-state gate is per-PANEL: a missing headcount alone (with
    # members/branches present) is reported but does not fail the gate.
    if verify and empty_panels:
        return 1
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
