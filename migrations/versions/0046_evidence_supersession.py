"""A re-scan replaced a row and told nobody, so every citation of it orphaned

0043 and `persist.carry_links_across_remint` MOVE an evidence row's cell links
onto its re-mint when a second scan re-lands the same package source with
better content. That move is right — leaving the links on both made one
document reach every one of its subcaps twice, and each cell counted one
source as two items toward the `<3` thin-evidence line.

What it did not do is record that the move happened. `evidence_index` has no
column saying "this row was replaced by that one", so the relationship between
`E-XXX-008` and `E-XXX-008-R2` exists only as a shared id prefix — a rule held
in the shape of a string, which is the same class as the remediation text that
inverted with it.

The consequence is not theoretical, and it is corpus-wide:

    families of (bare id + its re-mints)              5,331
    member rows                                      11,440
    bare ids now carrying NO cell links                4,366

Every one of those 4,366 is an id a promoted payload may cite, and ET-07
refuses a citation whose row links to no capability cell — correctly, on the
information it had. Measured on the reference client the moment its context
page was resubmitted: 7 of 7 cited ids blocked, and 7 of 7 had a re-mint twin
carrying between 6 and 141 links. Not one was a real orphan. It had not
surfaced before only because validation runs at SUBMIT and no page had been
resubmitted since 0043 ran.

`carry_links_across_remint`'s own docstring says the superseded row is retained
so that "an old payload's citation of it still resolves". It resolves — to a
row with nothing behind it. Retention without a forward pointer is how.

WHAT THIS ADDS

`evidence_index.superseded_by` names the newest member of the row's family,
and `resolve_evidence_id()` is the ONE implementation of the resolution rule.
It lives in the database rather than in each service because the connector and
the API both need it, and a rule with two callers fixed at one of them is the
defect this migration exists to repair. Both roles get EXECUTE.

The resolution is deliberately conservative: it moves a citation forward ONLY
when the successor actually carries links. A row that still works keeps
working, and a family where nothing carries links resolves to itself, so a
genuine orphan is still reported as one.

Revision ID: 0046
Revises: 0045
Create Date: 2026-08-09
"""
from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


# One hop, and only onto a successor that carries links. Written once, here,
# because `apps/mcp` (ET-07) and `apps/api` (the evidence drawer) both resolve
# citations and two copies of this rule is exactly what 0043 taught.
_RESOLVER = """
CREATE OR REPLACE FUNCTION resolve_evidence_id(p_e_id text) RETURNS text
  LANGUAGE sql STABLE
  SET search_path = public
  AS $fn$
    SELECT coalesce(
      (SELECT s.e_id
         FROM evidence_index s
        WHERE s.e_id = (SELECT i.superseded_by FROM evidence_index i
                         WHERE i.e_id = p_e_id)
          AND EXISTS (SELECT 1 FROM evidence_subcap_links l
                       WHERE l.e_id = s.e_id)),
      p_e_id)
  $fn$
"""

# The newest member of each family supersedes every earlier one. Newest is by
# the -R<n> suffix, not by link count: the suffix is what `_land_evidence`
# increments when it re-scans, so it is the only ordering that means "this is
# the current registration". Link count is a property of the linker and would
# make the pointer flip whenever links moved.
_BACKFILL = """
WITH fam AS (
  SELECT e_id,
         regexp_replace(e_id, '-R[0-9]+$', '')                    AS base,
         coalesce(substring(e_id from '-R([0-9]+)$')::int, 0)     AS rn
    FROM evidence_index
), newest AS (
  SELECT base, e_id AS head, rn
    FROM (SELECT base, e_id, rn,
                 row_number() OVER (PARTITION BY base ORDER BY rn DESC) AS k
            FROM fam) ranked
   WHERE k = 1
)
UPDATE evidence_index ei
   SET superseded_by = n.head
  FROM fam f
  JOIN newest n ON n.base = f.base
 WHERE ei.e_id = f.e_id
   AND f.rn < n.rn
"""


def upgrade() -> None:
    op.execute("ALTER TABLE evidence_index "
               "ADD COLUMN IF NOT EXISTS superseded_by TEXT")
    op.execute(
        "COMMENT ON COLUMN evidence_index.superseded_by IS "
        "'The newest registration of this same source, when a later scan "
        "re-landed it with better content and `carry_links_across_remint` "
        "moved the cell links onto that row. NULL means this row is current. "
        "Resolve through it with resolve_evidence_id() rather than reading it "
        "directly: the rule is that a citation moves forward only onto a "
        "successor that actually carries links, so a row that still works "
        "keeps working and a genuine orphan is still reported as one.'")

    # Not a foreign key: the successor is in this same table and a FK would
    # make the ingest tier's delete-and-relands order-dependent for no gain —
    # the resolver already treats a dangling pointer as "no successor".
    op.execute("CREATE INDEX IF NOT EXISTS evidence_index_superseded_by "
               "ON evidence_index (superseded_by) "
               "WHERE superseded_by IS NOT NULL")

    op.execute(_BACKFILL)
    op.execute(_RESOLVER)
    op.execute("REVOKE ALL ON FUNCTION resolve_evidence_id(text) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION resolve_evidence_id(text) TO svc_api")
    op.execute("GRANT EXECUTE ON FUNCTION resolve_evidence_id(text) TO svc_mcp")
    op.execute("GRANT EXECUTE ON FUNCTION resolve_evidence_id(text) TO svc_worker")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS resolve_evidence_id(text)")
    op.execute("DROP INDEX IF EXISTS evidence_index_superseded_by")
    op.execute("ALTER TABLE evidence_index DROP COLUMN IF EXISTS superseded_by")
