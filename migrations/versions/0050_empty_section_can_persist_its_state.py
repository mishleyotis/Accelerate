"""A section with nothing in it could not say so, because the writer's own row
violated a NOT NULL column.

Measured 2026-08-18, promoting Logix Federal Credit Union. `context.acquisitions`
carries no rows — the institution has grown organically across the assessment
window, and the absence is established by a six-rung ladder rather than assumed.
CG-19 requires exactly that: an empty required list is a claim, so the section
must declare its `empty_state` with the ladder behind it. The payload did.
`promote_run` then died:

    null value in column "status" of relation "context_acquisitions"
    violates not-null constraint

`context_acquisitions` is an item-grain table. With zero items the writer emits
one envelope row to carry `empty_state`, `r_layer` and the narrative thread, and
every item column on that row is NULL by construction — including `status`,
declared NOT NULL.

So the two rules contradicted each other: the gate demanded a stated empty
state, and the schema refused to store one. A section could satisfy either, never
both. The observable consequence was not a loud failure but a silent one — the
previously promoted run served `acquisitions.data = null` with
`"section_not_promoted — no serving row for this run"`, because no row had ever
been written for it. A reader met a blank panel and was told nothing about why,
on a run whose producer had written six rungs of explanation.

    THE_CHECK_AND_THE_STORE_DISAGREE — a payload that passes every gate cannot be
    persisted, and the failure surfaces inside the promote transaction as a driver
    error naming a column rather than a verdict naming a path.

WHY NULLABLE IS CORRECT, NOT A WEAKENING. `status` on a real acquisition row is
one of ANNOUNCED · INTEGRATING · COMPLETE · ABANDONED. On an envelope row for a
register with no acquisitions, none of the four is true, and writing one to
satisfy the constraint would be a sentinel wearing a measurement's clothes —
forbidden by invariant 9 and worse than the blank it replaced. The honest value
is absence.

The vocabulary is still enforced where it means something: `validate_pass1`
polices these fields per ITEM at submit (`_CONTRACT_VOCABULARIES`,
`techstack.techstack.items[*].status` and the issue register's own pair), and
`_check_must_present` refuses an item that omits them. The gate is the
enforcement; the NOT NULL was belt-and-braces that only ever bit the one row
the gate does not describe.

Four tables carry the same latent deadlock — the three others simply happen to
have items on every run promoted so far, so only `context_acquisitions` has
detonated. Fixing one and leaving three would leave the same trap for the first
run whose issue register, tech register or evidence-age panel is legitimately
empty.

Expand only, and reversible: `downgrade` restores NOT NULL, which succeeds
whenever no envelope-only row exists.
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


#: (table, column) — item columns declared NOT NULL on an item-grain serving
#: table, each of which blocks the envelope row that carries an empty state.
_ITEM_COLUMNS = (
    ("context_acquisitions", "status"),
    ("context_issue_register", "severity"),
    ("context_issue_register", "status"),
    ("techstack_items", "status"),
    ("heatmap_evidence_age", "reference_date"),
)


def upgrade() -> None:
    for table, column in _ITEM_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP NOT NULL")


def downgrade() -> None:
    for table, column in _ITEM_COLUMNS:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL")
