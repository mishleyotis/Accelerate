"""059 - evidence tier: canonical taxonomy [1, 7], honest NULL for unknown

The 2026-07-06 QA on the live evidence drawer surfaced "Tier 8" rows.
Tier 8 does NOT exist in any research-workbook source-tier taxonomy —
the corpus declares two variants whose union is T1..T7 (Compeer-style
T1_regulatory..T5_marketing; Fulton-style adds T6_specialized_data_provider
and T7_other_credible_source; T10_internal_synthesis is a synthesis
artefact, not a source tier). Every persisted 8 was FABRICATED by the
parser layer: `int(tier or 8)` defaults on NULL-ish input, and
clamp-to-[1,8] on out-of-taxonomy labels ("T10-CONTRADICTORY" → 8,
"T9" → 8). Missing tiers were likewise fabricated as mid-scale 5 at
parse time (those are indistinguishable from real T5 rows now and are
left in place; new ingests store NULL).

This migration makes the column honest:
  1. `tier` becomes nullable — "the source states no canonical tier" is
     representable as NULL instead of an invented number.
  2. The check narrows from [1, 8] to `tier IS NULL OR tier BETWEEN 1
     AND 7` — the canonical taxonomy.
  3. Data heal: rows whose tier is outside [1, 7] (i.e. the fabricated
     8s) are set to NULL. Nothing is invented; re-ingesting the package
     restores a real tier when the source ever states one.

Idempotent: re-running the UPDATE matches zero rows; constraint swap is
guarded by IF EXISTS.
"""
from alembic import op

revision = "059_evidence_tier_canonical"
down_revision = "058_enrichment_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE evidence_index DROP CONSTRAINT IF EXISTS evidence_index_tier_chk"
    )
    op.execute("ALTER TABLE evidence_index ALTER COLUMN tier DROP NOT NULL")
    # Heal fabricated tiers BEFORE re-adding the narrowed check.
    op.execute(
        "UPDATE evidence_index SET tier = NULL WHERE tier IS NOT NULL "
        "AND tier NOT BETWEEN 1 AND 7"
    )
    op.execute(
        "ALTER TABLE evidence_index ADD CONSTRAINT evidence_index_tier_chk "
        "CHECK (tier IS NULL OR tier BETWEEN 1 AND 7)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE evidence_index DROP CONSTRAINT IF EXISTS evidence_index_tier_chk"
    )
    # NOT NULL restore needs a value; 8 (weakest on the legacy scale)
    # marks "unknown" exactly as the pre-055 fabrication did.
    op.execute("UPDATE evidence_index SET tier = 8 WHERE tier IS NULL")
    op.execute("ALTER TABLE evidence_index ALTER COLUMN tier SET NOT NULL")
    op.execute(
        "ALTER TABLE evidence_index ADD CONSTRAINT evidence_index_tier_chk "
        "CHECK (tier BETWEEN 1 AND 8)"
    )
