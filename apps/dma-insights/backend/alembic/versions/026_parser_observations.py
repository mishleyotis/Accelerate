"""026 — parser_observations: self-improvement observation log.

Revision ID: 026_parser_observations
Revises: 025_new_write_surfaces

Problem this solves
====================
The 2026-06 operator mandate: "The scripting codes and parsing
segments should always check for new structures and self improve the
code base and their catalogue of parsing techniques."

Today, parsers (e.g. `research_workbook.parse_per_pillar_sheets`,
`dma_package._scoring_from_xlsx_fallback`) use a static `ALIASES` dict
to map known column-header variants to canonical fields. When a
workbook ships a NEW variant (e.g. "Sub_Capability_ID" instead of the
known "SubCap_ID" / "subcap_id"), the parser falls through to either
the LLM column-mapper OR drops the column silently. Either way, the
information is lost — the next code change to the ALIASES dict has to
be reverse-engineered from operator complaints.

This migration adds the `parser_observations` table — one canonical
row per (parser_name, observation_kind, observed_value). Each row
upserts on (kind, value) so a recurring variant accumulates an
`occurrence_count` and updates `last_seen`. Once a variant crosses a
threshold (e.g. seen 5+ times across distinct runs), the operator (or
a future nightly job) can promote it into the source code's ALIASES
dict with a one-line diff + safe redeploy.

Schema
------
parser_observations(
  id                  bigserial PK
  parser_name         varchar(64)   NOT NULL  -- e.g. 'research_workbook'
  observation_kind    varchar(64)   NOT NULL  -- e.g. 'unknown_column',
                                              --      'unknown_sheet',
                                              --      'unmatched_subcap_id_format'
  observed_value      varchar(255)  NOT NULL  -- the raw thing observed
  canonical_guess     varchar(64)             -- best-effort canonical
                                              -- field this should map to
                                              -- (NULL if no guess)
  sample_context      jsonb                   -- e.g. {"sheet": "P1C1",
                                              --       "row_idx": 4,
                                              --       "neighbor_headers":[...]}
  occurrence_count    integer       NOT NULL DEFAULT 1
  distinct_runs       integer       NOT NULL DEFAULT 1
  first_seen          timestamptz   NOT NULL DEFAULT NOW()
  last_seen           timestamptz   NOT NULL DEFAULT NOW()
  -- de-dup key
  UNIQUE (parser_name, observation_kind, observed_value)
)

State branches (UPSERT contract)
---------------------------------
  - first sighting: INSERT row with count=1, distinct_runs=1
  - same (parser, kind, value) seen again: UPDATE
      occurrence_count += 1
      distinct_runs = max(distinct_runs, |distinct run_ids seen so far|)
      last_seen = NOW()
      sample_context: NEVER overwrite — first context wins (cheapest
                      capture; loop-prevention)
  - different observed_value, same (parser, kind): INSERT new row

The table is OBSERVATION-ONLY: it never blocks ingest. Write failures
are logged + swallowed by the caller (`record_parser_observation`
helper).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "026_parser_observations"
down_revision = "025_new_write_surfaces"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parser_observations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("parser_name", sa.String(64), nullable=False),
        sa.Column("observation_kind", sa.String(64), nullable=False),
        sa.Column("observed_value", sa.String(255), nullable=False),
        sa.Column("canonical_guess", sa.String(64)),
        sa.Column("sample_context", postgresql.JSONB),
        sa.Column(
            "occurrence_count",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "distinct_runs",
            sa.Integer,
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "first_seen",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "last_seen",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "parser_name",
            "observation_kind",
            "observed_value",
            name="uq_parser_observations_natural_key",
        ),
    )
    # Hot path: admin endpoint lists by last_seen DESC, filtered by
    # parser_name and/or observation_kind.
    op.create_index(
        "ix_parser_observations_last_seen",
        "parser_observations",
        ["last_seen"],
        postgresql_using="btree",
    )
    op.create_index(
        "ix_parser_observations_parser_kind",
        "parser_observations",
        ["parser_name", "observation_kind"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_parser_observations_parser_kind",
        table_name="parser_observations",
    )
    op.drop_index(
        "ix_parser_observations_last_seen",
        table_name="parser_observations",
    )
    op.drop_table("parser_observations")
