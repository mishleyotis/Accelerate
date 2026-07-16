"""053 - platform_scores fit_breakdown + sequence_rank (D4 fit engine v2)

The 2026-06 platform audit ("most wrong" page) found the fit engine's
per-factor contributions are computed and thrown away — 95/470 cards
were red-but-hot with zero traceability. `platform_scores` is the
run-scoped table that persists platform cards (migration 005, written
by package_persist + read by routers/platforms.py); fit engine v2
persists its reasoning here:

  - ``fit_breakdown``  — per-factor contributions {opportunity,
    readiness, interconnect, absent_boost, ...} + top contributing
    subcaps + their E-IDs; drives the fit-tile drilldown drawer
    (factor bars + evidence chips).
  - ``sequence_rank``  — position in the prerequisite DAG across
    platforms+recs ("what unlocks what"); consumed by the D1 SCQA
    Answer, why-now plays and the multi-phase roadmap.

All NULL on legacy rows — `PlatformCard` emits them as Optional and
the request-time fit computation stays authoritative for the score
itself until the v2 engine writes rows.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block.
"""
from alembic import op

revision = "053_platform_fit_breakdown"
down_revision = "052_focus_area_grounding"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("fit_breakdown", "JSONB"),
    ("sequence_rank", "SMALLINT"),
)


def upgrade() -> None:
    for col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='platform_scores' AND column_name='{col}'
                ) THEN
                    ALTER TABLE platform_scores ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE platform_scores DROP COLUMN IF EXISTS {col}")
