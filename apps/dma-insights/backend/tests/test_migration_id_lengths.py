"""CI guard: alembic revision IDs must fit alembic's VARCHAR(32) column.

ROOT CAUSE FORENSICS (2026-05-24)
---------------------------------
Migration `021_runs_data_source_drive_backfill` (35 chars) tripped:

    psycopg.errors.StringDataRightTruncation:
      value too long for type character varying(32)
    [SQL: UPDATE alembic_version SET version_num=…]

Alembic's `alembic_version.version_num` defaults to VARCHAR(32). Any
revision ID longer than 32 chars causes the version-tracking UPDATE
to fail, which rolls back the entire migration transaction — the
schema change appears to have run (it printed "Running upgrade") but
the state-bookkeeping write fails and undoes everything. The operator
gets a SQLAlchemy error with no indication that the column is the
cause.

Two-layer fix landed alongside this guard:
  1. Rename the offending revision to fit (021_runs_drive_backfill,
     23 chars).
  2. `alembic/env.py` now ALTERs `alembic_version.version_num` to
     VARCHAR(128) on every run as defence in depth.

This test is the third layer: AUTHOR-TIME validation. Any new
migration with an oversized ID fails the suite before it can ever
reach a database.

State-branch contract:
  all_ids_fit            → test passes
  one_or_more_overrun    → test fails with file + length + ID list
  versions_dir_missing   → test errors out (suite can't run)
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Alembic's default — keep author-time enforcement tight so we never
# rely on the env.py widener to bail us out in prod.
MAX_REVISION_ID_LENGTH = 32

VERSIONS_DIR = (
    Path(__file__).resolve().parent.parent / "alembic" / "versions"
)

_REVISION_RE = re.compile(
    r"""^\s*revision\s*(?::\s*[A-Za-z_|]+)?\s*=\s*["']([^"']+)["']""",
    re.MULTILINE,
)


def _all_migration_files() -> list[Path]:
    assert VERSIONS_DIR.is_dir(), (
        f"alembic versions dir missing: {VERSIONS_DIR}"
    )
    return sorted(p for p in VERSIONS_DIR.glob("*.py") if p.name != "__init__.py")


def test_versions_dir_has_migrations() -> None:
    """Sanity check the suite is actually scanning the right path."""
    files = _all_migration_files()
    assert len(files) >= 20, (
        f"Expected ≥ 20 migrations under {VERSIONS_DIR}, found {len(files)}"
    )


@pytest.mark.parametrize("migration_file", _all_migration_files(), ids=lambda p: p.name)
def test_revision_id_fits_alembic_default_column(migration_file: Path) -> None:
    """Every revision ID must be ≤ 32 chars.

    The exception list below is empty by design — any tolerated overrun
    would have to be paired with a documented prod operational fix
    (manual ALTER on every existing database) and an env.py widener
    that ran BEFORE the offending migration could ever land. We have
    the widener; we still enforce the limit so new migrations don't
    rely on it.
    """
    text = migration_file.read_text(encoding="utf-8")
    m = _REVISION_RE.search(text)
    assert m, f"{migration_file.name}: no `revision = '...'` line found"

    rev = m.group(1)
    assert len(rev) <= MAX_REVISION_ID_LENGTH, (
        f"{migration_file.name}: revision ID '{rev}' is {len(rev)} chars "
        f"(> {MAX_REVISION_ID_LENGTH}). Alembic's alembic_version.version_num "
        f"column is VARCHAR(32) by default; longer IDs fail the version "
        f"UPDATE with StringDataRightTruncation. Shorten the slug — keep "
        f"the leading `0NN_` prefix + a short, meaningful suffix."
    )


def test_filename_matches_revision_id() -> None:
    """`021_runs_drive_backfill.py` must declare revision='021_runs_drive_backfill'.

    Drift between filename and ID is a common source of "I renamed the
    file but alembic still complains" confusion.
    """
    drifts = []
    for f in _all_migration_files():
        text = f.read_text(encoding="utf-8")
        m = _REVISION_RE.search(text)
        if not m:
            continue
        rev = m.group(1)
        stem = f.stem
        if stem != rev:
            drifts.append(f"{f.name}: revision='{rev}' but filename stem='{stem}'")
    assert not drifts, (
        "Filename ↔ revision-ID drift detected:\n  " + "\n  ".join(drifts)
    )


def test_down_revisions_resolve() -> None:
    """Every `down_revision` must reference an existing migration ID."""
    files = _all_migration_files()
    all_ids: set[str] = set()
    down_refs: list[tuple[str, str]] = []
    down_re = re.compile(
        r"""^\s*down_revision\s*(?::\s*[A-Za-z_|]+)?\s*=\s*["']([^"']+)["']""",
        re.MULTILINE,
    )
    rev_re = _REVISION_RE
    for f in files:
        text = f.read_text(encoding="utf-8")
        rm = rev_re.search(text)
        if rm:
            all_ids.add(rm.group(1))
        dm = down_re.search(text)
        if dm:
            down_refs.append((f.name, dm.group(1)))

    bad = [
        (fname, ref) for fname, ref in down_refs if ref not in all_ids
    ]
    assert not bad, (
        "down_revision pointing at missing revision:\n  "
        + "\n  ".join(f"{fname} → '{ref}'" for fname, ref in bad)
    )
