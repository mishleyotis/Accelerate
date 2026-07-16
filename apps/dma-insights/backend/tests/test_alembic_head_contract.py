"""Phase 4 alembic migration head + contract regression tests.

Each test pins one structural invariant the audit identified as
silently-breakable:
  - There must be exactly ONE alembic head (multiple heads = the
    Cloud Run migrations job runs an UNDEFINED set of migrations).
  - Every revision ID must fit within the alembic_version column
    (VARCHAR(32) default; longer IDs fail with StringDataRightTruncation
    on the version UPDATE).
  - The docs head reference must match the latest revision on disk
    (drift = operators run migrations against the wrong target).
  - Every migration's revision/down_revision chain is linear (no
    orphans).
  - The chain reaches the head via single-parent links from base.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = BACKEND / "alembic" / "versions"
DEPLOYMENT_MD = BACKEND.parent / "docs" / "DEPLOYMENT.md"
QA_CONTRACT_MD = BACKEND.parent / "docs" / "QA-CONTRACT.md"
STATUS_MD = BACKEND.parent / "docs" / "STATUS.md"


def _parse_revision_chain() -> dict[str, str | None]:
    """Returns {revision_id: down_revision_or_None} for every migration
    file on disk. Used to walk the chain + detect multiple heads."""
    chain: dict[str, str | None] = {}
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        rev_m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        down_m = re.search(r"^down_revision\s*=\s*(?:['\"]([^'\"]+)['\"]|None)",
                           text, re.M)
        if not rev_m:
            continue
        rev = rev_m.group(1)
        down = down_m.group(1) if (down_m and down_m.group(1)) else None
        chain[rev] = down
    return chain


def test_only_one_alembic_head():
    """A revision is a HEAD if no other revision lists it as
    down_revision. There must be exactly one HEAD or alembic exits
    with "Multiple head revisions are present" and the migrations
    Cloud Run Job can't decide what to apply."""
    chain = _parse_revision_chain()
    referenced_as_parent = {d for d in chain.values() if d is not None}
    heads = [rev for rev in chain if rev not in referenced_as_parent]
    assert len(heads) == 1, (
        f"Expected 1 alembic head, found {len(heads)}: {heads}. "
        "Multiple heads break the migrations Cloud Run Job."
    )


def test_every_revision_id_fits_alembic_version_column():
    """alembic_version.version_num defaults to VARCHAR(32). A
    revision ID longer than 32 chars makes the UPDATE post-migration
    raise StringDataRightTruncation -- the migration runs but the
    bookkeeping fails, leaving the DB in an undefined state."""
    chain = _parse_revision_chain()
    too_long = [rev for rev in chain if len(rev) > 32]
    assert not too_long, (
        f"Revision IDs exceed 32 chars: {too_long}. Shorten the slug "
        "(keep the leading `0NN_` prefix). alembic_version.version_num "
        "is VARCHAR(32) -- longer IDs truncate."
    )


def test_revision_chain_is_linear_from_base_to_head():
    """Walk back from each head via down_revision. The chain must
    reach a None (base) without cycles + every revision must be
    reachable. A skipped revision = migrations Cloud Run Job
    silently skips that file."""
    chain = _parse_revision_chain()
    referenced_as_parent = {d for d in chain.values() if d is not None}
    heads = [rev for rev in chain if rev not in referenced_as_parent]
    assert len(heads) == 1
    head = heads[0]

    visited: set[str] = set()
    current: str | None = head
    while current is not None:
        if current in visited:
            pytest.fail(f"Cycle detected at revision '{current}'")
        visited.add(current)
        current = chain.get(current)

    unreachable = set(chain) - visited
    assert not unreachable, (
        f"Migrations unreachable from head: {sorted(unreachable)}. "
        "down_revision chain is broken -- alembic upgrade head would "
        "skip these silently."
    )


def test_filename_matches_revision_id():
    """`021_runs_drive_backfill.py` must declare
    revision='021_runs_drive_backfill'. Drift = operator runs
    `alembic upgrade 021_runs_drive_backfill` and alembic says
    "Can't locate revision identified by '021_runs_drive_backfill'".
    """
    drifts: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        if path.name.startswith("_") or path.name == "__init__.py":
            continue
        stem = path.stem
        text = path.read_text(encoding="utf-8")
        rev_m = re.search(r"^revision\s*=\s*['\"]([^'\"]+)['\"]", text, re.M)
        if rev_m and rev_m.group(1) != stem:
            drifts.append(f"{path.name}: revision='{rev_m.group(1)}' but stem='{stem}'")
    assert not drifts, "Filename ↔ revision-ID drift:\n  " + "\n  ".join(drifts)


def test_docs_reference_current_alembic_head():
    """DEPLOYMENT.md + QA-CONTRACT.md mention a `head=...` marker that
    must match the actual head on disk. Drift = operator runs the
    wrong target during a rollback investigation."""
    chain = _parse_revision_chain()
    referenced_as_parent = {d for d in chain.values() if d is not None}
    heads = [rev for rev in chain if rev not in referenced_as_parent]
    actual_head = heads[0]
    # Strip the leading NNN_ to get the short slug -- docs sometimes
    # use the bare slug ("head=023") and sometimes the full revision.
    short = actual_head.split("_", 1)[0]
    for doc_path in (DEPLOYMENT_MD, QA_CONTRACT_MD):
        if not doc_path.exists():
            continue
        text = doc_path.read_text(encoding="utf-8")
        # Doc must mention either the full revision ID or the short form.
        has_full = actual_head in text
        has_short = re.search(rf"\bhead\s*=\s*{re.escape(short)}\b", text) is not None
        assert has_full or has_short, (
            f"{doc_path.name} does not reference current alembic head "
            f"({actual_head}). Update the doc or revert the migration."
        )


def test_revision_chain_does_not_contain_orphan_down_revisions():
    """Every down_revision string must exist as a revision in some
    other file. Pointing at a deleted/renamed revision means alembic
    upgrade fails with 'Can't locate revision'."""
    chain = _parse_revision_chain()
    all_revisions = set(chain.keys())
    orphans: list[tuple[str, str]] = []
    for rev, down in chain.items():
        if down is not None and down not in all_revisions:
            orphans.append((rev, down))
    assert not orphans, (
        f"down_revision references missing revisions: {orphans}. "
        "Either rename the missing revision or fix the chain."
    )
