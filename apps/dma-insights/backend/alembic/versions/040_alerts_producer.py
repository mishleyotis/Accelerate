"""040 - alerts producer columns (thin-evidence derivation)

QA audit 2026-06-11: the `alerts` table had NO producer — 0 rows across
the whole 96-DMA corpus while 53k `subcap_scores.is_thin_evidence` rows
existed. Every alert surface (Alerts page, dashboard OPEN ALERTS KPI +
Needs-attention card, sidebar badge, entity open_alerts, D6 Health
table + tab dot) rendered empty.

`services/alerts_producer.derive_thin_evidence_alerts` now materializes
THIN_EVIDENCE alerts at ingest (package_persist) and via the
`app.scripts.derive_alerts` corpus backfill. The wireframe health table
renders three per-alert fields beyond the base shape (01_data.js
buildAlerts): evidence count (the n/3 mini-bar), recommended action
(PROXY_ESCALATION / TIER_UPGRADE mono chip), and the proxy-searched
flag. Plus the producer's idempotency key:

- ``evidence_count``      — supporting evidence rows for the subcap(s)
- ``recommended_action``  — PROXY_ESCALATION (0 evidence) / TIER_UPGRADE
- ``proxy_searched``      — whether a proxy search already ran
- ``content_key``         — stable derivation key (subcap_id or
  ``CAT:{category_id}`` for aggregated alerts). Re-derives DELETE open
  THIN_EVIDENCE rows per entity and skip content_keys that exist
  CLOSED — a waived alert is never resurrected.

All nullable; manually-raised alert kinds keep NULLs.
"""
from alembic import op
import sqlalchemy as sa

revision = "040_alerts_producer"
down_revision = "039_runs_assessment_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alerts", sa.Column("evidence_count", sa.Integer(), nullable=True),
    )
    op.add_column(
        "alerts",
        sa.Column("recommended_action", sa.String(32), nullable=True),
    )
    op.add_column(
        "alerts", sa.Column("proxy_searched", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "alerts", sa.Column("content_key", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_alerts_entity_kind_key",
        "alerts",
        ["entity_id", "kind", "content_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_alerts_entity_kind_key", table_name="alerts")
    op.drop_column("alerts", "content_key")
    op.drop_column("alerts", "proxy_searched")
    op.drop_column("alerts", "recommended_action")
    op.drop_column("alerts", "evidence_count")
