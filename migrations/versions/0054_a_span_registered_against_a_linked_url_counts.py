"""Recount `citable_evidence_count` under the same rule the listing uses.

0053 counted a link as citable only when ITS OWN evidence row carried a span.
That misses the shape this corpus actually has: the package supplies the cell
links and no spans, and a producer registers the span against the same url
with no links. Under the strict rule a reader saw a quotable citation in the
drawer — the served listing merges the two — over a cell still flagged thin.

The flag and the page disagreeing about the same evidence is worse than either
being wrong on its own, so the SQL now applies the rule in
`packages/shared/evidence_merge.py`: scheme-blind, trailing-slash-trimmed,
lower-cased url equality, scoped to the entity.

No column changes. This is a data migration: the maintenance SQL in
`dma_worker/counts.py` moved, and the stored values have to catch up or they
stay wrong until the next ingest touches the run.

Revision ID: 0054
Revises: 0053
"""
from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None

_RECOUNT = """
UPDATE subcap_scores sc
   SET citable_evidence_count = (
         SELECT count(*)
           FROM evidence_subcap_links l
           JOIN evidence_index e ON e.e_id = l.e_id
          WHERE l.run_id = sc.run_id
            AND l.subcap_id = sc.subcap_id
            AND ((e.excerpt IS NOT NULL AND length(btrim(e.excerpt)) > 0)
                 OR EXISTS (SELECT 1 FROM evidence_index e2
                             WHERE e2.entity_id = e.entity_id
                               AND e2.e_id <> e.e_id
                               AND e2.excerpt IS NOT NULL
                               AND length(btrim(e2.excerpt)) > 0
                               AND e.source_url IS NOT NULL
                               AND e.source_url <> ''
                               AND rtrim(lower(regexp_replace(
                                     e2.source_url, '^https?://', '')), '/')
                                 = rtrim(lower(regexp_replace(
                                     e.source_url, '^https?://', '')), '/'))))
"""

_STRICT = """
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
    op.execute(_RECOUNT)


def downgrade() -> None:
    op.execute(_STRICT)
