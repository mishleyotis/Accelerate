"""Connector-origin evidence and split discovery spans (RC-08, decision 3).

Two owner decisions of 2026-10-04 (SWBC gold audit) need somewhere to live on
`evidence_index`. Both are EXPAND-ONLY: nullable columns and one new table;
no existing row changes, no column is dropped or retyped.

## 1 · Connector-origin evidence (decision 3)

`evidence_origin_t` has carried `connector` since 0002 and nothing could use
it honestly: register_evidence verifies an excerpt by FETCHING its URL, and a
connector reading — the Indeed connector's employer rating, an aggregation of
the CFPB complaint API — is a tool result, not a page. Producers therefore
either dropped the reading (SWBC's sentiment card shipped one bar while two
auditors pulled 3.1/5 from Indeed and 213 CFPB complaints) or registered it
URL-less, which demotes it to INFERENCE: laundering a measured reading into a
weak claim.

The owner admitted it as evidence with its provenance recorded:

    connector_tool            the tool called   (e.g. Indeed get_company_data)
    connector_query           what it was asked (company, filter, API query)
    connector_retrieved_at    when
    connector_response_sha256 the stored response the excerpt is verified
                              against — instead of a URL fetch

and `connector_responses` holds those responses, content-addressed, so the
verbatim check can be re-run later against the same bytes the producer saw.
The tier is COMPUTED from the tool at registration (Indeed T3, CFPB official
data T1), never taken from the producer.

## 2 · Split discovery spans (RC-08 / D-10)

SWBC's 20 discovery rows were registered origin='internal' and marked
internal_only whole, which left 24 customer drawers arguing over nothing.
The owner default: split each into a SHAREABLE span — the client's own
statement, re-attributed to the client — and an INTERNAL span (seller and
personal remarks).

    customer_attribution  the label a client reads the shareable span under
                          ("Client statement, discovery conversations,
                          September 2026"). NULL = not shareable: an
                          internal-origin row with NULL here never serves to
                          a customer (apps/api redaction).
    split_of              the e_id of the row a span was split from, so the
                          lineage is a column and not a sentence.

## Grants, in this revision (working discipline)

New table: svc_mcp SELECT + INSERT (register_evidence stores and re-reads a
response); nobody else — the api serves the excerpt, never the raw response.
New columns on an existing table inherit its table-level grants: svc_api
already SELECTs evidence_index (it now reads customer_attribution and the
connector trio), svc_mcp already INSERTs and UPDATEs it.

Revision ID: 0063
Revises: 0062
"""
from alembic import op

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS connector_responses (
          sha256        TEXT PRIMARY KEY,         -- of body, computed server-side
          entity_id     UUID REFERENCES entities(id),
          tool          TEXT NOT NULL,
          query         TEXT,
          retrieved_at  TIMESTAMPTZ NOT NULL,
          body          TEXT NOT NULL,            -- the response as returned
          stored_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS connector_responses_entity "
               "ON connector_responses (entity_id, retrieved_at DESC)")

    # One statement per line, so scripts/gen_column_types.py reads each
    # column's type straight off this file.
    op.execute("""
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS connector_tool TEXT;
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS connector_query TEXT;
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS connector_retrieved_at TIMESTAMPTZ;
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS connector_response_sha256 TEXT REFERENCES connector_responses(sha256);
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS customer_attribution TEXT;
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS split_of TEXT REFERENCES evidence_index(e_id);
    """)

    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_mcp') THEN
            EXECUTE 'GRANT SELECT, INSERT ON connector_responses TO svc_mcp';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    for col in ("split_of", "customer_attribution",
                "connector_response_sha256", "connector_retrieved_at",
                "connector_query", "connector_tool"):
        op.execute(f"ALTER TABLE evidence_index DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS connector_responses")
