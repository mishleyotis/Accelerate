"""Cross Insurance Agency's sub-vertical is filled from the owner's binding

Cross Insurance Agency (`display_id = 'cross-insurance-agency'`) has
`entities.sub_vertical` NULL. Its package manifests (seq 2 and seq 3, both
stating `institution.sub_vertical: IB`) were ingested before the worker's
fill-where-NULL fix (4cc95c4b) reached production, and the package scan is
idempotent over an unchanged tree, so no later ingest will land it. With the
column NULL the platform fit engine cannot resolve the entity's sub-vertical,
CG-30 refuses the platform page at promote ("vertical relevance is
UNCHECKED"), and ET-05 checks no variant cell.

## The value, and who decided it

Owner binding at the research preflight (2026-10-01, answered "IB, full
scope"), restated by the owner on 2026-10-05 approving this revision. The
same value is in the run's `run_manifest.json` (`institution.sub_vertical`).

Only `sub_vertical` is filled. The legal name is deliberately left alone:
identity check G-006 (a same-name firm; revenue may belong to the Cross
Financial Corp. group) is open.

## What this does and does not touch

* FILL ONLY WHERE NULL, guarded by display_id; re-running is a no-op; a
  database with no such entity (local, CI) changes nothing.
* `serving_directory` is refreshed at the end, as in 0062.
* Downgrade restores NULL only where the value still equals what this
  revision wrote.

Revision ID: 0066
Revises: 0065
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None

DISPLAY_ID = "cross-insurance-agency"

_FILL = (
    ("sub_vertical", "IB", "TEXT"),
)


def _run(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params)


def _refresh() -> None:
    exists = _run("SELECT to_regclass('public.serving_directory') IS NOT NULL"
                  ).scalar()
    if exists:
        _run("SELECT refresh_serving_directory()")


def upgrade() -> None:
    for column, value, cast in _FILL:
        n = _run(f"UPDATE entities SET {column} = CAST(:v AS {cast}) "
                 f"WHERE display_id = :d AND {column} IS NULL",
                 v=value, d=DISPLAY_ID).rowcount
        print(f"VERIFY 0066 {DISPLAY_ID}.{column} filled={n}")
    _refresh()
    row = _run("SELECT sub_vertical FROM entities WHERE display_id = :d",
               d=DISPLAY_ID).fetchone()
    print(f"VERIFY 0066 {DISPLAY_ID} entity now: "
          f"{tuple(row) if row else 'no such entity here'}")


def downgrade() -> None:
    for column, value, cast in _FILL:
        n = _run(f"UPDATE entities SET {column} = NULL "
                 f"WHERE display_id = :d AND {column} = CAST(:v AS {cast})",
                 v=value, d=DISPLAY_ID).rowcount
        print(f"VERIFY 0066 downgrade {DISPLAY_ID}.{column} cleared={n}")
    _refresh()
