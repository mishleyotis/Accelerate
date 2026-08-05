"""The directory's one materialised view (stage 4 / invariant 8)

The directory reads one materialised view for header and rows —
svc_api never touches ingested tables directly (the §03 deny stands);
this view is the sanctioned window: entity identity + every PROMOTED
run + the hero figures already promoted into overview_scores, with
open-alert counts computed from the alerts queue, never stored.

Refresh happens at promote time through a SECURITY DEFINER function
(the view is owned by svc_migrate; svc_mcp may only refresh it whole).

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-05
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW serving_directory AS
        SELECT e.id            AS entity_id,
               e.display_id,
               e.legal_name,
               e.sub_vertical,
               e.size_tier,
               r.id            AS run_id,
               r.request_id,
               r.run_seq,
               r.is_active,
               enum_label(r.status) AS run_status,
               r.composite,
               r.scored_cells,
               r.catalogue_cells,
               r.ccg_catalog_version,
               r.completed_at,
               r.promoted_at,
               os.pillars,
               (SELECT count(*) FROM heatmap_alerts a
                 WHERE a.run_id = r.id AND a.status = 'OPEN') AS open_alerts
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          LEFT JOIN overview_scores os ON os.run_id = r.id
         WHERE r.promoted_at IS NOT NULL
        """
    )
    op.execute("CREATE UNIQUE INDEX serving_directory_run ON serving_directory (run_id)")
    op.execute("CREATE INDEX serving_directory_entity ON serving_directory (entity_id, run_seq DESC)")
    op.execute("GRANT SELECT ON serving_directory TO svc_api")
    # Plain refresh, not CONCURRENTLY: concurrent refresh builds a temp
    # table and svc_migrate holds no TEMP privilege (default deny). The
    # brief exclusive lock is fine at this scale; revisit with traffic.
    op.execute(
        """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
        """
    )
    op.execute("REVOKE ALL ON FUNCTION refresh_serving_directory() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() TO svc_mcp")


def downgrade() -> None:
    op.execute("DROP FUNCTION refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW serving_directory")
