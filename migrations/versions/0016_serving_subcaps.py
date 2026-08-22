"""serving_subcaps — the workbook's own cell grain, served read-only

The heatmap drills to four grains (pillar · category · capability · subcap) and
the platform page maps each gap to a named cell. Both need per-cell scores, and
the serving tier has none: H4's writer maps pillars and categories only, and
H2's cell-evidence section covers the evidenced cells (69 of Baxter's 765), not
the scored ones.

The scores do exist, in `subcap_scores` — read from the workbook at ingest and,
per that table's own comment, "never re-derived". They are ingested
MEASUREMENTS, not synthesised content, which is why serving them does not open
the door invariant 2 closes: nothing here is prose, nothing was authored by a
producer, and the connector remains the only way content enters. The same
already happens for `runs.composite` and `scored_cells` through
serving_directory, and invariant 8 asks for exactly this shape — read the
source of truth rather than store a second copy.

So: one granted view, the same pattern as serving_directory. Names come from
the catalogue the run is pinned to (falling back to the current version, since
a run may be pinned to none), never from prose. `delta` and `is_thin_evidence`
are the base table's GENERATED columns — selected, never recomputed.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-05
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
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
          -- The run's pinned catalogue names the cell; an unpinned run falls
          -- back to the current version rather than serving a nameless grid.
          LEFT JOIN ccg_subcaps c
                 ON c.subcap_id = s.subcap_id
                AND c.version = COALESCE(
                      r.ccg_catalog_version,
                      (SELECT version FROM ccg_versions WHERE is_current))
         WHERE r.promoted_at IS NOT NULL
        """
    )
    op.execute("GRANT SELECT ON serving_subcaps TO svc_api")


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS serving_subcaps")
