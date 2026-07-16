"""038 - entity inference review columns (F6 admin pending-review workflow)

The prototype's Admin page (10_pages_f.js:474-497) carries a
"Pending review · Phase 0 entity inferences" card: entities created by
the Drive crawler with an *inferred* identity (name extracted from a
document header / filename token) sit in ``status='PENDING_REVIEW'``
until an ADMIN confirms or rejects the inference. The list endpoint
(``GET /api/v1/admin/pending-review``) already exists; the confirm /
reject transition endpoints need provenance + outcome columns:

- ``inferred_from_source`` — what signal produced the inference
  (e.g. "Entity name from document header · DMA_Assessment_Report_X.gdoc")
- ``inferred_at``        — when the inference was made
- ``confirmed_at``       — set by PATCH /admin/entities/{id}:confirm
                           (PENDING_REVIEW → ACTIVE)
- ``rejection_reason``   — set by PATCH /admin/entities/{id}:reject
                           (PENDING_REVIEW → ARCHIVED)

All nullable — existing rows (created via ingest or ops-sheet, never
inferred) keep NULLs and are unaffected.
"""
from alembic import op
import sqlalchemy as sa

revision = "038_entity_inference_review"
down_revision = "037_widen_loader_run_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("inferred_from_source", sa.Text(), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("inferred_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "entities",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("entities", "rejection_reason")
    op.drop_column("entities", "confirmed_at")
    op.drop_column("entities", "inferred_at")
    op.drop_column("entities", "inferred_from_source")
