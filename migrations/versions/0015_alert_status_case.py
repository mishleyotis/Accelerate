"""serving_directory counts open alerts in the vocabulary they are written in

The view compared heatmap_alerts.status against 'OPEN' while the column's
own documented vocabulary — and alert_action_t, the enum of the actions that
move it (acknowledged · assigned · waived · resolved · reopened) — is
lowercase. Every promoted alert therefore counted as zero, so a run with
eleven open thin-evidence alerts showed an empty alert dashboard and
open_alerts = 0 on its directory row.

Paired with the promote change that initialises the column at all: it has no
DDL default, so before that the value was NULL and neither spelling matched.

Only the count's predicate changes. The view is recreated because a
materialised view's body cannot be altered in place; its indexes, grants and
the SECURITY DEFINER refresh function are recreated with it, unchanged from
0013 — the function has to be dropped first because it depends on the view.

Revision ID: 0015
Revises: 0014
Create Date: 2026-08-05
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_BODY = """
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
                 WHERE a.run_id = r.id AND a.status = 'open') AS open_alerts
          FROM runs r
          JOIN entities e ON e.id = r.entity_id
          LEFT JOIN overview_scores os ON os.run_id = r.id
         WHERE r.promoted_at IS NOT NULL
"""

_FUNCTION = """
        CREATE FUNCTION refresh_serving_directory() RETURNS void
          LANGUAGE sql SECURITY DEFINER
          SET search_path = public
          AS 'REFRESH MATERIALIZED VIEW serving_directory'
"""


def _rebuild(body: str) -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_serving_directory()")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS serving_directory")
    op.execute(f"CREATE MATERIALIZED VIEW serving_directory AS {body}")
    op.execute("CREATE UNIQUE INDEX serving_directory_run ON serving_directory (run_id)")
    op.execute("CREATE INDEX serving_directory_entity "
               "ON serving_directory (entity_id, run_seq DESC)")
    op.execute("GRANT SELECT ON serving_directory TO svc_api")
    op.execute(_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION refresh_serving_directory() FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION refresh_serving_directory() TO svc_mcp")


def upgrade() -> None:
    _rebuild(_BODY)


def downgrade() -> None:
    _rebuild(_BODY.replace("a.status = 'open'", "a.status = 'OPEN'"))
