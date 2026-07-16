"""027 — firmographics.parsed_facts JSONB

Adds a JSONB column for parser-extracted firmographics that don't map
to existing typed columns (`aum_usd float` / `headcount int` /
`hq_address str` / `primary_regulator str`).

The Client Profile DOCX parser
(`app/services/parsers/client_profile._extract_firmographics_facts`)
emits string-form `total_assets` ("$1.5B" / "$3.2B"), `employees_approx`
("1,450"), and `branches` ("37") that the React Overview FirmographicsRows
component reads VERBATIM (no formatting transform). Forcing them through
the existing typed columns would require parsing "$3.2B" → 3.2e9 with
a units lookup and a reverse-formatter on the read side — three
opportunities for drift between parse → persist → render. A JSONB
field stores the strings as-is and round-trips cleanly.

Schema-only change; no data backfill needed (existing rows get NULL
which the endpoint correctly maps to absent fields in the response).
"""
from alembic import op
import sqlalchemy as sa


revision = "027_firmographics_parsed_facts"
down_revision = "026_parser_observations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "firmographics",
        sa.Column(
            "parsed_facts",
            sa.dialects.postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Parser-extracted string-form firmographics that don't map "
                "to typed columns: total_assets, employees_approx, branches. "
                "Populated by package_persist from the Client Profile DOCX "
                "via _extract_firmographics_facts. Consumed by "
                "GET /entities/{id}/overview as the firmographics.parsed_facts "
                "sub-object on the response."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("firmographics", "parsed_facts")
