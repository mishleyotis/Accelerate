"""Thin means nothing quotable reaches the cell, not fewer than three links.

`is_thin_evidence` was `linked_evidence_count < 3` — a count of LINKS, blind to
whether any of them can be cited. On run d7ed1d90 that produced the reading a
reader objected to: P1C1.1.1 carried eight links and was marked thin, while a
cell with three links to unquotable references was not. Three references
nobody can read outrank one verbatim span from a congressional testimony.

Owner instruction, 2026-08-19: "As long as a subcap has 1 specific evidence
that speaks on it, it is not thin, especially if it is above T3 level of
evidence."

So the flag now asks a different question: does ANYTHING quotable reach this
cell. One citable item clears it — an item this run links to the cell whose
evidence row carries a verbatim span.

The three-link fallback is gone rather than demoted, and the first draft of
this migration kept it. Its own test refused it: three references with no span
gave `linked = 3`, which cleared thin over a cell where a reader can open
nothing. That is the same lie as the one being fixed, told in the other
direction — and invariant 4 settles it, because an item with no verbatim
excerpt cannot be cited at all. A count of things that cannot be cited cannot
ground a score.

THE CONSEQUENCE IS VISIBLE AND INTENDED. On run d7ed1d90, 76 of 705 cells are
citable, so most of the grid carries a dashed outline until the register's 36
excerpt-less rows are filled. That is the state of the evidence. The previous
rule hid it behind a link count.

`citable_evidence_count` is maintained the same way `linked_evidence_count` is:
recomputed from the links table by the linker and by ingest, never incremented.
A count with a source of truth is computed from it (invariant 8); it is stored
here only because a generated column cannot join.

The generated column is DROPPED and re-added rather than altered — Postgres has
no ALTER for a generation expression — which means `serving_subcaps` goes with
it and comes back unchanged.

Revision ID: 0053
Revises: 0052
"""
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None

_THIN_NEW = "(COALESCE(citable_evidence_count, 0) < 1)"
_THIN_OLD = "(COALESCE(linked_evidence_count, 0) < 3)"

# Recreated verbatim from 0016. Kept whole rather than patched, because a view
# rebuilt from a diff is a view nobody can read in one go.
_VIEW = """
CREATE VIEW serving_subcaps AS
SELECT s.run_id,
       r.entity_id,
       s.subcap_id,
       s.capability_id,
       s.category_id,
       s.pillar_id,
       c.name              AS subcap_name,
       c.l3_platform_areas,
       c.l4_features,
       s.score,
       s.confidence,
       s.peer_median,
       s.peer_n,
       s.peer_basis,
       s.proxy_disclosure,
       s.delta,
       s.linked_evidence_count,
       s.is_thin_evidence,
       s.source_cell
  FROM subcap_scores s
  JOIN runs r ON r.id = s.run_id
  LEFT JOIN ccg_subcaps c
         ON c.subcap_id = s.subcap_id
        AND c.version = COALESCE(
              r.ccg_catalog_version,
              (SELECT version FROM ccg_versions WHERE is_current))
 WHERE r.promoted_at IS NOT NULL
"""

# An item is CITABLE where its evidence row carries a verbatim span. That is
# the same condition invariant 4 puts on a citation: an id with no excerpt
# cannot be cited, whatever else it carries.
_RECOUNT = """
UPDATE subcap_scores sc
   SET citable_evidence_count = (
         SELECT count(*)
           FROM evidence_subcap_links l
           JOIN evidence_index e ON e.e_id = l.e_id
          WHERE l.run_id = sc.run_id
            AND l.subcap_id = sc.subcap_id
            AND e.excerpt IS NOT NULL
            AND length(btrim(e.excerpt)) > 0)
"""


def upgrade() -> None:
    op.execute("ALTER TABLE subcap_scores "
               "ADD COLUMN IF NOT EXISTS citable_evidence_count INTEGER")
    op.execute(_RECOUNT)
    op.execute("DROP VIEW IF EXISTS serving_subcaps")
    op.execute("ALTER TABLE subcap_scores DROP COLUMN IF EXISTS is_thin_evidence")
    op.execute("ALTER TABLE subcap_scores ADD COLUMN is_thin_evidence BOOLEAN "
               f"GENERATED ALWAYS AS ({_THIN_NEW}) STORED")
    op.execute(_VIEW)
    op.execute("GRANT SELECT ON serving_subcaps TO svc_api")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS serving_subcaps")
    op.execute("ALTER TABLE subcap_scores DROP COLUMN IF EXISTS is_thin_evidence")
    op.execute("ALTER TABLE subcap_scores ADD COLUMN is_thin_evidence BOOLEAN "
               f"GENERATED ALWAYS AS {_THIN_OLD} STORED")
    op.execute(_VIEW)
    op.execute("GRANT SELECT ON serving_subcaps TO svc_api")
    op.execute("ALTER TABLE subcap_scores DROP COLUMN IF EXISTS citable_evidence_count")
