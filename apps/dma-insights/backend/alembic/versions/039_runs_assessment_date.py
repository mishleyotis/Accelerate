"""039 - runs.assessment_date + overall_score (run-identity QA fix)

QA audit 2026-06-11 (side-by-side vs the wireframe contract): the Runs
page RUN DATE column, the ClientBar run-selector pill, and the
dashboard/directory card dates all bound to ``runs.started_at`` — which
``package_persist`` sets to ``NOW()`` at ingest. Backfilling the 96-DMA
corpus therefore stamped every run with the ingest day (observed:
``DMA-ASM-ALMA-20260519-0001`` rendering "Jun 11, 2026"). The wireframe
RUN DATE is the *assessment* date.

The parsers already extract the real values — ``RunManifest.assessment_date``
/ ``.overall_score`` and ``PackageManifest.package_date`` / ``.overall_score``
— they were just never persisted. Three nullable columns:

- ``assessment_date`` — the run's official assessment date. Fallback
  chain at persist time: run_manifest.assessment_date → run-id date
  segment (DMA-ASM-{ENTITY}-{YYYYMMDD}) → MANIFEST.package_date → NULL.
- ``assessment_date_source`` — provenance of the chosen value
  (``run_manifest`` / ``run_id`` / ``package_manifest``); NULL when no
  source produced a date (read-side falls back to started_at and the
  UI may flag it).
- ``overall_score`` — the package's official overall maturity score
  (run_manifest.overall_score → MANIFEST.overall_score). When NULL the
  read-side keeps deriving the pillar mean exactly as before, so this
  is purely additive.

Existing rows keep NULLs; ``app.scripts.backfill_run_dates`` repairs
the already-ingested corpus from ``request_id`` without re-ingest.
"""
from alembic import op
import sqlalchemy as sa

revision = "039_runs_assessment_date"
down_revision = "038_entity_inference_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("assessment_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("assessment_date_source", sa.String(24), nullable=True),
    )
    op.add_column(
        "runs",
        sa.Column("overall_score", sa.Numeric(3, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runs", "overall_score")
    op.drop_column("runs", "assessment_date_source")
    op.drop_column("runs", "assessment_date")
