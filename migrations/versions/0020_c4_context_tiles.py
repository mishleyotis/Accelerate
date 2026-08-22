"""0020 — C4's own shape, resolving a contract/DDL mismatch that was flagged and never settled.

`context_sentiment` was the one writer in the spec carrying an explicit warning:
"GENUINE CONTRACT/DDL MISMATCH — DO NOT FREEZE WITHOUT ADJUDICATION". The
contract's only defined field for C4 is `context_tiles[]`, which had no column;
the DDL instead mirrored `overview_sentiment` with `ratings`, `themes` and
`gap_analysis`, its inline comment reading "O9's prompt at Context depth (C4)".
So whatever a producer submitted for C4 was discarded at promotion, and the
Context sentiment card rendered a hardcoded prototype fixture — Glassdoor 3.8
(n=412), App Store 3.4 (n=8,200), a CFPB index of 24 — under a real client's
name, with evidence chips that opened a drawer saying the id does not resolve.

## The adjudication (2026-08-05)

Sources consulted, in authority order:

  Backend Schema  `context_sentiment` mirrors `overview_sentiment`, comment
                  "O9's prompt at Context depth (C4)"
  TRD             C4 listed as a Context section, run grain
  Surface Spec    C4 has no prompt block of its own. Its ONLY named field, in
                  the O9 Information sources table, is "three tiles: customer,
                  employee, market, each with drilldown rows and evidence chips"
  QA Report       silent — no resolution exists to lean on

The Surface Spec names `context_tiles` and names nothing else, so the contract's
field is the real one and the DDL's three columns are the mirror that was never
authored. **C4 is a RE-PROJECTION of the dataset O9 renders as bars**, not a
second, independently sourced measure — which is why the two cards must never
disagree, and why the ratings continue to live on `overview_sentiment` where O9
already stores them.

Therefore: add the column the contract has always described, and retain the
three mirror columns unbound rather than dropping them. Dropping them would be
the contract half of expand–migrate–contract, and nothing has read them yet, so
there is no migration to do first — but they are the only record of the mirror
reading, and a later stage may yet decide C4 stores its own projection. They
stay, bound to `skip:` with this adjudication named.

Nullable, so every already-promoted row stays valid. No GRANT is needed:
0008 grants at table level, which covers columns added afterwards.
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE context_sentiment "
               "ADD COLUMN IF NOT EXISTS context_tiles JSONB")
    op.execute("""
        COMMENT ON COLUMN context_sentiment.context_tiles IS
          'C4 — three tiles customer|employee|market, each {audience, rows[], '
          'e_ids[]}; rows[] = {source, rating, scale, n, as_of, url, e_id, '
          'note}. Re-projection of overview_sentiment.ratings; reconciled, '
          'never independently sourced.'
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE context_sentiment "
               "DROP COLUMN IF EXISTS context_tiles")
