"""0018 — leadership contact detail lands with the roster.

The leadership panel is supposed to show a contact route per person: email,
LinkedIn, phone. `overview_leadership` had columns for the person and their
tenure and nothing for reaching them, so the panel rendered a "enrich via Clay"
button that fired a 900ms setTimeout and produced nothing.

The fix is not a request-time call. This application performs no inference and
makes no third-party call while serving (invariant 1), and content enters only
through the connector (invariant 2). Clay runs in the PRODUCER's session, at
synthesis time, and its output is registered as evidence and written into the
roster item like every other promoted field. By the time a page is served the
contact detail is already in Postgres, one row per person, and the panel renders
it in the same read as the name — no spinner, no queue, no click.

Five columns, all nullable, so every already-promoted row stays valid (the expand
half of expand–migrate–contract):

  email             a work address, from a cited source
  linkedin_url      the person's profile
  phone             a switchboard or direct line, from a cited source
  enriched_at       when the contact detail was established
  enrichment_basis  WHERE it came from — a filing, a press release, a Clay
                    technographic scan. "Clay said so" is not a source; the
                    document Clay surfaced is. Without this column a contact
                    route would be the one field on the page with no provenance.

Contact detail for a named individual is internal-only. The producer marks the
paths, and the audience walker strips them for the customer audience — the
existing `internal_only` machinery covers it, so no new redaction path is added
here. This migration adds columns; it does not decide who sees them.
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

COLUMNS = (
    ("email", "TEXT"),
    ("linkedin_url", "TEXT"),
    ("phone", "TEXT"),
    ("enriched_at", "DATE"),
    ("enrichment_basis", "TEXT"),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.execute("ALTER TABLE overview_leadership "
                   f"ADD COLUMN IF NOT EXISTS {name} {kind}")


def downgrade() -> None:
    for name, _ in COLUMNS:
        op.execute(f"ALTER TABLE overview_leadership DROP COLUMN IF EXISTS {name}")
