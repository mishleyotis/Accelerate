"""0019 — the tech register explains its DMA impact, and its peer coverage is researched.

Asked what the tech-stack drilldown's "DMA assessment impact" was based on, the honest
answer was: nothing. It computed `baseline = score - 1.2` and `target = score + 1.3` for
an absent product — two constants that appear in no source — and presented the result as
movement an AE would take into a meeting. Beside it, "Peer deployment" decided a verdict
per NAMED peer institution from a hash of the row id, over a `peer_coverage` figure that
had no contract field at all and therefore rendered as "—% adopted" on a zero-width bar.

Both are now honest but silent: the impact card lists the register's linked cells at their
served scores, and the peer card says the research has not been done. Silent is better than
wrong and worse than explained. These three columns are what lets the producer explain it.

  dma_impact        The explanation, in the producer's words: which cells this product
                    bears on, what it does and does not reach, and by what mechanism.
                    Traceable prose, not an assertion — the cells are already in
                    `linked_subcap_ids` and their scores are already served, so this field
                    is the REASONING that connects them. A score is never derived here
                    (rule 1: scores come from the workbook), and no projected uplift is
                    claimed, because no source states one.

  peer_coverage     NUMERIC(4,3), 0..1 — the share of the run's NAMED peer set publicly
                    running this product. Constrained to the unit interval so a percentage
                    sent as 62 instead of 0.62 is refused at write time rather than
                    rendering a bar six thousand percent wide.

  peer_deployments  JSONB — the per-peer breakdown behind that share:
                    [{peer, deployed, basis, source_url, as_of}]. A technographic claim
                    about a named institution is a research finding and needs its source
                    attached, which is exactly what the hash could never provide. The
                    count of peers that could NOT be established belongs here too: a
                    coverage figure of 2/5 with three unknowns is not 2/5, and the card
                    has to be able to say so.

All three nullable. A product whose impact the producer has not explained renders the
cell list alone, which is what it does today — this migration adds the capacity to explain,
it does not fabricate an explanation for rows that predate it.
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE techstack_items "
               "ADD COLUMN IF NOT EXISTS dma_impact TEXT")
    op.execute("ALTER TABLE techstack_items "
               "ADD COLUMN IF NOT EXISTS peer_coverage NUMERIC(4,3)")
    op.execute("ALTER TABLE techstack_items "
               "ADD COLUMN IF NOT EXISTS peer_deployments JSONB")
    # A share outside 0..1 is a unit error, and it reaches the page as a bar
    # width. Refused here rather than rendered.
    op.execute("""
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint
                          WHERE conname = 'techstack_peer_coverage_unit') THEN
            ALTER TABLE techstack_items
              ADD CONSTRAINT techstack_peer_coverage_unit
              CHECK (peer_coverage IS NULL
                     OR (peer_coverage >= 0 AND peer_coverage <= 1));
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE techstack_items "
               "DROP CONSTRAINT IF EXISTS techstack_peer_coverage_unit")
    for col in ("dma_impact", "peer_coverage", "peer_deployments"):
        op.execute(f"ALTER TABLE techstack_items DROP COLUMN IF EXISTS {col}")
