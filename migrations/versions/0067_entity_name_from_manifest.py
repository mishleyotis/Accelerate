"""An entity with no name is named from its own manifest, as written

Entities ingested before the worker's fill-where-NULL fix (4cc95c4b) carry
NULL `legal_name` and NULL `trading_name`. The serving name falls back to
`display_id`, so the app headed Cross Insurance Agency's pages
"cross-insurance-agency" (owner, 2026-10-05: "the entity name is
hyphenated ... names should only be hyphenated if they are originally so").
A slug cannot be turned back into a name — whether a hyphen, an ampersand or
a capital belongs there is exactly what the slug threw away — so the name is
read from where it was written: the run's own `run_manifest.payload`.

## The rule

* Only an entity with BOTH `legal_name` and `trading_name` NULL is touched.
* The value is the newest manifest's institution name, verbatim
  (`manifest.institution.name`, then `entity_name`, `institution_name`,
  `entity.name` — the shapes `persist.institution_of` reads).
* It fills `trading_name`, not `legal_name`: a manifest names the client the
  way the engagement does, which is not a verified legal name (Cross's G-006
  — a same-name firm and a group parent — is still open).
* A value that is the slug itself, or empty, is skipped: that would write the
  defect back as data.
* Re-running is a no-op; `serving_directory` is refreshed at the end.
* Downgrade clears only rows whose trading_name still equals the manifest
  value this revision wrote AND whose legal_name is still NULL.

Revision ID: 0067
Revises: 0066
Create Date: 2026-10-05
"""
import sqlalchemy as sa
from alembic import op

revision = "0067"
down_revision = "0066"
branch_labels = None
depends_on = None

#: The newest manifest's institution name per nameless entity, verbatim.
_CANDIDATES = """
WITH newest AS (
  SELECT DISTINCT ON (r.entity_id)
         r.entity_id,
         NULLIF(btrim(COALESCE(
           m.payload #>> '{manifest,institution,name}',
           m.payload #>> '{manifest,entity_name}',
           m.payload #>> '{manifest,institution_name}',
           m.payload #>> '{manifest,entity,name}')), '') AS name
    FROM runs r
    JOIN run_manifest m ON m.run_id = r.id
   ORDER BY r.entity_id, r.run_seq DESC NULLS LAST, r.completed_at DESC NULLS LAST
)
SELECT e.id, e.display_id, n.name
  FROM entities e
  JOIN newest n ON n.entity_id = e.id
 WHERE e.legal_name IS NULL
   AND e.trading_name IS NULL
   AND n.name IS NOT NULL
   AND lower(n.name) <> lower(e.display_id)
"""


def _run(sql: str, **params):
    return op.get_bind().execute(sa.text(sql), params)


def _refresh() -> None:
    if _run("SELECT to_regclass('public.serving_directory') IS NOT NULL").scalar():
        _run("SELECT refresh_serving_directory()")


def upgrade() -> None:
    rows = _run(_CANDIDATES).fetchall()
    n = 0
    for entity_id, display_id, name in rows:
        n += _run("UPDATE entities SET trading_name = :v "
                  "WHERE id = :i AND legal_name IS NULL AND trading_name IS NULL",
                  v=name, i=entity_id).rowcount
        print(f"VERIFY 0067 {display_id}.trading_name = {name!r}")
    print(f"VERIFY 0067 named={n}")
    _refresh()


def downgrade() -> None:
    n = 0
    for entity_id, display_id, name in _run(
            _CANDIDATES.replace("AND e.trading_name IS NULL",
                                "AND e.trading_name IS NOT NULL")).fetchall():
        n += _run("UPDATE entities SET trading_name = NULL "
                  "WHERE id = :i AND legal_name IS NULL AND trading_name = :v",
                  v=name, i=entity_id).rowcount
    print(f"VERIFY 0067 downgrade cleared={n}")
    _refresh()
