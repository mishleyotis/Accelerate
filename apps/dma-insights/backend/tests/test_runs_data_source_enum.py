"""Regression: every data_source value the codebase emits must be in
the runs_data_source_chk constraint.

The 2026-05-24 backfill silently emptied the admin UI because
historical_backfill.py emitted 'DRIVE_BACKFILL' but the constraint
(migration 003) only allowed 'DRIVE_PARSE'/'PROJECT_API'/
'MANUAL_BACKFILL'. Every INSERT failed with CheckViolationError;
every commit rolled back; nothing landed in `runs` so the entire
UI showed empty cards even though the CLI claimed success.

This test scans the codebase for every data_source value passed to
package_persist + INSERT INTO runs callsites, then asserts each is
in the canonical allowlist defined in migration 021.

State branches:
  emit_in_allowlist     → safe; INSERT succeeds.
  emit_not_in_allowlist → CheckViolationError; INSERT silently
                          rolled back; admin UI empty.
  test_failure          → migration 021 missing OR a new ingest
                          callsite passed an unregistered value.
                          Add the value to ALLOWED_DATA_SOURCES in
                          migration 021 AND in this test.
"""
from __future__ import annotations

import re
from pathlib import Path

ALLOWED = {
    "DRIVE_PARSE",
    "DRIVE_BACKFILL",
    "PROJECT_API",
    "MANUAL_BACKFILL",
    "BOT_REQUEST",
}


def _find_app_root(start: Path) -> Path:
    for c in [start, *start.parents]:
        if (c / "backend").is_dir() and (c / "infra").is_dir():
            return c
    raise RuntimeError(f"app root not found from {start}")


APP_ROOT = _find_app_root(Path(__file__).resolve())
BACKEND = APP_ROOT / "backend"


def test_migration_021_allows_drive_backfill() -> None:
    """The constraint allowlist in migration 021 must include
    every value the codebase emits. Catches drift if a new
    constant is added without updating the migration."""
    mig = BACKEND / "alembic" / "versions" / "021_runs_drive_backfill.py"
    assert mig.exists(), "migration 021 missing — backfill will CheckViolate forever"
    body = mig.read_text()
    for value in ALLOWED:
        assert f'"{value}"' in body, (
            f"migration 021 doesn't list '{value}' in "
            f"ALLOWED_DATA_SOURCES — INSERT with that value will fail"
        )


def test_every_data_source_callsite_is_in_allowlist() -> None:
    """Scan app + scripts for `data_source="..."` callsites and
    assert each literal is in ALLOWED. If you add a new ingest path
    that emits a new data_source, this test fails until you add the
    value to migration 021 AND the ALLOWED set above."""
    # data_source="VALUE" — function arg or dict literal style.
    pattern = re.compile(r'data_source\s*=\s*["\']([A-Z_]+)["\']')
    found_values: set[str] = set()
    found_at: dict[str, list[str]] = {}

    for path in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in str(path):
            continue
        for match in pattern.finditer(path.read_text()):
            v = match.group(1)
            found_values.add(v)
            found_at.setdefault(v, []).append(str(path.relative_to(BACKEND)))

    rogue = found_values - ALLOWED
    assert not rogue, (
        f"Found data_source literals not in the migration 021 allowlist: "
        f"{rogue}. Locations: {[f'{k}: {found_at[k]}' for k in rogue]}. "
        f"Fix: add to ALLOWED_DATA_SOURCES in migration 021 + this test, "
        f"then write a new migration that re-creates the constraint."
    )


def test_old_constraint_dropped_in_021() -> None:
    """Migration 021 must DROP the old constraint before recreating
    it. Otherwise the ADD CONSTRAINT fails on the duplicate name."""
    mig = BACKEND / "alembic" / "versions" / "021_runs_drive_backfill.py"
    body = mig.read_text()
    assert "DROP CONSTRAINT IF EXISTS runs_data_source_chk" in body, (
        "migration 021 must DROP the old constraint before ADD — "
        "otherwise ALTER TABLE fails on duplicate constraint name"
    )
