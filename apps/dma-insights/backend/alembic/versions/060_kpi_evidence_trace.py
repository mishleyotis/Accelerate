"""060 - focus-area KPI evidence traceability (D3)

The 2026-07-06 production audit found focus-area KPI rows carrying no
evidence anchor: neither the deterministic seeding
(`focus_area_synthesizer.derive_focus_area_kpis`) nor the Gemini
gap-fill (`enrichment_queries.focus_kpi_extraction`) recorded WHICH
evidence row the number came from, so the KPI strip could not open an
evidence drawer and the value was untraceable.

  focus_area_kpi_overrides:
  - ``evidence_e_id`` — the E-ID of the evidence/excerpt the KPI's
    number was read from (NULL for AE-entered rows; both derive paths
    now populate it).

NULL on legacy rows — read paths default the field so the response
shape stays stable until re-derivation fills it.

Idempotent: ADD COLUMN IF NOT EXISTS within DO $$...END $$ block
(mirrors migration 052).
"""
from alembic import op

revision = "060_kpi_evidence_trace"
down_revision = "059_evidence_tier_canonical"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("focus_area_kpi_overrides", "evidence_e_id", "VARCHAR(16)"),
)


def upgrade() -> None:
    for table, col, coltype in _COLUMNS:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_name='{table}' AND column_name='{col}'
                ) THEN
                    ALTER TABLE {table} ADD COLUMN {col} {coltype};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    for table, col, _ in reversed(_COLUMNS):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {col}")
