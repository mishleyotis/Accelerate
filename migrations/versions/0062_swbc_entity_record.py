"""SWBC's entity record is filled from the owner's decision

SWBC (`display_id = 'swbc'`, entity 53d062c3-e309-4033-9438-297b2b8505aa)
was promoted with an EMPTY entity record — `legal_name`, `sub_vertical` and
`size_tier` all NULL — and its run 7968492e is withdrawn. Every header read
"Where  is today", the sub-vertical scope rule saw no sub-vertical and served
every variant cell, and ET-05 checked nothing. The cause was the worker:
`persist_package` wrote identity only when it INSERTED an entity, so a later
package that carried the identity for an entity row already on file changed
nothing (fixed alongside this revision in apps/worker/dma_worker/persist.py —
fill-where-NULL on every ingest). The scan is idempotent over an unchanged
tree, so that fix cannot reach this row by itself; this revision does.

## The values, and who decided them

Owner decision (2026-09-30 binding, recorded in
qa_audit/2026-09-30-swbc/CASE_FACTS.md):

    legal_name                   Southwest Business Corporation
    trading_name                 SWBC
    domain                       swbc.com
    sub_vertical                 IB   (insurance brokers — the primary)
    supplementary_sub_verticals  {IC,CL,RIA}  (0061 — their variant cells
                                 serve too; RB and every other do not)
    size_tier                    mid-size

`size_tier` basis (researched at the owner's request, 2026-10-02): derived
from HEADCOUNT — 2,300 employees (SWBC Executive Summary, Dec 2025) — by the
corpus's documented headcount fallback (>= 1,000 employees => mid-size).
SWBC is a private non-depository with no published asset figure and no
published group revenue figure, so the dollar-denominated tiers have nothing
to read; the fallback is the rung that applies, and it is a stated basis,
not an estimate dressed as one.

## What this does and does not touch

* FILL ONLY WHERE NULL, per column, guarded by `display_id = 'swbc'`. A
  value anyone has since set is left exactly as it is; re-running is a no-op;
  a database with no SWBC row (local, CI) changes nothing.
* `serving_directory` is materialised, so the fill is invisible to every
  reader until it is refreshed: `refresh_serving_directory()` (0013, rebuilt
  by 0061) runs at the end. It is SECURITY DEFINER and owned by svc_migrate,
  which this revision runs as. No grants change.
* Downgrade restores NULL per column ONLY where the value still equals what
  this revision wrote — never a value somebody else set afterwards — then
  refreshes the directory again.

Adding a column later is one entry in `_FILL` below.

Revision ID: 0062
Revises: 0061
Create Date: 2026-10-02
"""
import sqlalchemy as sa
from alembic import op

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None

DISPLAY_ID = "swbc"

#: column -> (value, SQL cast). One line per field; the order is the order
#: the VERIFY lines print in.
_FILL = (
    ("legal_name", "Southwest Business Corporation", "TEXT"),
    ("trading_name", "SWBC", "TEXT"),
    ("domain", "swbc.com", "TEXT"),
    ("sub_vertical", "IB", "TEXT"),
    ("supplementary_sub_verticals", ["IC", "CL", "RIA"], "TEXT[]"),
    ("size_tier", "mid-size", "TEXT"),
)


def _run(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params)


def _refresh() -> None:
    # Only when the view exists — it always does after 0061, but a refresh
    # that raises on a database built some other way would block the chain
    # for a data fix that had nothing to publish.
    exists = _run("SELECT to_regclass('public.serving_directory') IS NOT NULL"
                  ).scalar()
    if exists:
        _run("SELECT refresh_serving_directory()")


def upgrade() -> None:
    for column, value, cast in _FILL:
        n = _run(f"UPDATE entities SET {column} = CAST(:v AS {cast}) "
                 f"WHERE display_id = :d AND {column} IS NULL",
                 v=value, d=DISPLAY_ID).rowcount
        print(f"VERIFY 0062 {DISPLAY_ID}.{column} filled={n}")
    _refresh()
    row = _run("SELECT legal_name, trading_name, domain, sub_vertical, "
               "supplementary_sub_verticals, size_tier FROM entities "
               "WHERE display_id = :d", d=DISPLAY_ID).fetchone()
    print(f"VERIFY 0062 {DISPLAY_ID} entity now: "
          f"{tuple(row) if row else 'no such entity here'}")


def downgrade() -> None:
    for column, value, cast in _FILL:
        n = _run(f"UPDATE entities SET {column} = NULL "
                 f"WHERE display_id = :d "
                 f"AND {column} = CAST(:v AS {cast})",
                 v=value, d=DISPLAY_ID).rowcount
        print(f"VERIFY 0062 downgrade {DISPLAY_ID}.{column} cleared={n}")
    _refresh()
