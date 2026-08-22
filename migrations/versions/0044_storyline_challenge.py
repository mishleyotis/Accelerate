"""The adversarial record the skill asks for and the contract never declared

`04-craft/7-storyline-challenge.md` tells a producer to put the whole
storyline through five volleys before promoting — the client's executive,
the finance officer, the incumbent vendor, the rival on the shortlist, and
the AE who has to say it aloud — and to record each challenge, the story's
answer, and what changed:

    storyline_challenge: {
      volleys: [{volley, challenger, challenge, answer, outcome, changed}],
      survived
    }

Nothing declared it. Not the contract, so CG-04 never swept it; not the
writer spec, so promote had nowhere to put it; not this schema, so there
was no column to put it in. A producer following the skill wrote the
record and it was dropped in the same transaction that promoted the
storyline it defends — which is the exact shape of 0027 and 0041, and the
reason the field census now runs at item grain.

The record belongs on `overview_exec_summary`: the storyline IS the exec
summary (situation, complication, question, answer), so the challenges to
it are a property of that row and nothing else.

INTERNAL BY CONSTRUCTION. This is the record of arguing against our own
conclusion, which is the r_layer's family — `redaction.CUSTOMER_STRIP_KEYS`
strips it by key for the customer audience, so it does not depend on a
producer remembering to mark it. A client reading "the incumbent vendor
would say X and here is why that does not hold" is reading our sales
preparation, not their assessment.

JSONB, like `r_layer` and `empty_state` on this same table: the list is
per-run, ordered (volley 1..5 is a sequence, not a set), read whole with
its row, and never queried across runs.

Revision ID: 0044
Revises: 0043
Create Date: 2026-08-09
"""
from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE overview_exec_summary "
               "ADD COLUMN IF NOT EXISTS storyline_challenge JSONB")
    op.execute(
        "COMMENT ON COLUMN overview_exec_summary.storyline_challenge IS "
        "'The five adversarial volleys the storyline survived before "
        "promotion: {volleys: [{volley, challenger, challenge, answer, "
        "outcome, changed}], survived}. `changed` is required when outcome "
        "is changed or dropped — it names the difference, not the effort. "
        "Five held outcomes is a finding, not a triumph. INTERNAL: stripped "
        "by key for the customer audience (dma_api.redaction), because it "
        "is our sales preparation and not the client''s assessment.'")


def downgrade() -> None:
    op.execute("ALTER TABLE overview_exec_summary "
               "DROP COLUMN IF EXISTS storyline_challenge")
