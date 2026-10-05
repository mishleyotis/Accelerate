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
    customer_attribution_at
                          the instant the attribution was recorded — the
                          span's mint, stamped by the database, never sent.

### An attribution is fixed at mint, and binds forward only

The first cut of this revision let register_evidence UPDATE an attribution
onto an EXISTING row: onto the parent itself when the "span" was the whole
row, and onto any internal row a re-registration deduplicated to. The
adversarial review (2026-10-04) showed what that does. `evidence_index` is
shared by every run of an entity and the api reads it live, so one call made
on a NEW, unpromoted run exposed a previously withheld internal row on the
LIVE promoted run, and on every historical run citing it — outside promotion
(invariant 3), under an unchanged ETag, and with no tool able to take it back.

So, enforced here and not only in the connector:

  * `customer_attribution` is set ONLY on INSERT, ONLY on a split span
    (`split_of` NOT NULL), ONLY when the span is STRICTLY SHORTER than its
    parent (a whole-row "span" is the parent re-labelled, which is the
    weakening, not a split), and only from an internal parent of the same
    entity. The trigger stamps `customer_attribution_at = now()`.
  * `customer_attribution`, `customer_attribution_at` and `split_of` never
    change after the INSERT. An UPDATE that would change one raises.
  * The api serves a span under its attribution only on a run PROMOTED AT OR
    AFTER `customer_attribution_at` (apps/api evidence.attribution_bound).
    A run promoted before the span existed keeps serving exactly what it
    served — the span is withheld there like any internal row — until it is
    re-promoted, which is the only way a body may change.

## Grants, in this revision (working discipline)

New table: svc_mcp SELECT + INSERT (register_evidence stores and re-reads a
response); nobody else — the api serves the excerpt, never the raw response.
New columns on an existing table inherit its table-level grants: svc_api
already SELECTs evidence_index (it now reads customer_attribution and the
connector trio and customer_attribution_at), svc_mcp already INSERTs and
UPDATEs it — except that an UPDATE changing a span's three split columns is
refused by the trigger above, for every role.

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
        ALTER TABLE evidence_index ADD COLUMN IF NOT EXISTS customer_attribution_at TIMESTAMPTZ;
    """)

    # An attribution exists only on a split span, with its mint instant.
    # NOT VALID then VALIDATE: the scan runs under SHARE UPDATE EXCLUSIVE,
    # not the ACCESS EXCLUSIVE an inline CHECK would hold on a table of tens
    # of thousands of rows. Every existing row has the three columns NULL.
    op.execute("""
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_constraint
                          WHERE conname = 'evidence_index_attribution_is_a_split_span') THEN
            ALTER TABLE evidence_index
              ADD CONSTRAINT evidence_index_attribution_is_a_split_span
              CHECK (customer_attribution IS NULL
                     OR (split_of IS NOT NULL
                         AND customer_attribution_at IS NOT NULL)) NOT VALID;
          END IF;
        END $$;
    """)
    op.execute("ALTER TABLE evidence_index VALIDATE CONSTRAINT "
               "evidence_index_attribution_is_a_split_span")

    # Fixed at mint. SECURITY INVOKER (the default): the parent lookup runs
    # with the inserting role's own SELECT on evidence_index.
    op.execute(r"""
        CREATE OR REPLACE FUNCTION evidence_span_fixed_at_mint() RETURNS trigger
          LANGUAGE plpgsql
          SET search_path = public
          AS $fn$
        DECLARE
          p_entity uuid;
          p_origin text;
          p_excerpt text;
        BEGIN
          IF TG_OP = 'UPDATE' THEN
            IF NEW.customer_attribution IS DISTINCT FROM OLD.customer_attribution
               OR NEW.customer_attribution_at IS DISTINCT FROM OLD.customer_attribution_at
               OR NEW.split_of IS DISTINCT FROM OLD.split_of THEN
              RAISE EXCEPTION 'evidence % : customer_attribution, customer_attribution_at and split_of are fixed when the span is minted; split a new span instead', OLD.e_id
                USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
          END IF;
          -- INSERT
          IF NEW.customer_attribution IS NULL THEN
            NEW.customer_attribution_at := NULL;
            RETURN NEW;
          END IF;
          IF NEW.split_of IS NULL THEN
            RAISE EXCEPTION 'evidence % : a customer attribution belongs only to a span split from an internal row', NEW.e_id
              USING ERRCODE = 'check_violation';
          END IF;
          SELECT entity_id, origin::text, excerpt
            INTO p_entity, p_origin, p_excerpt
            FROM evidence_index WHERE e_id = NEW.split_of;
          IF NOT FOUND OR p_entity IS DISTINCT FROM NEW.entity_id
             OR p_origin IS DISTINCT FROM 'internal' THEN
            RAISE EXCEPTION 'evidence % : split_of % is not an internal row of the same entity', NEW.e_id, NEW.split_of
              USING ERRCODE = 'check_violation';
          END IF;
          IF length(btrim(regexp_replace(coalesce(NEW.excerpt, ''), '\s+', ' ', 'g')))
             >= length(btrim(regexp_replace(coalesce(p_excerpt, ''), '\s+', ' ', 'g'))) THEN
            RAISE EXCEPTION 'evidence % : a shareable span is strictly shorter than its parent %', NEW.e_id, NEW.split_of
              USING ERRCODE = 'check_violation';
          END IF;
          NEW.customer_attribution_at := now();
          RETURN NEW;
        END
        $fn$
    """)
    op.execute("DROP TRIGGER IF EXISTS evidence_span_minted ON evidence_index")
    op.execute("""
        CREATE TRIGGER evidence_span_minted
          BEFORE INSERT ON evidence_index
          FOR EACH ROW
          WHEN (NEW.customer_attribution IS NOT NULL
                OR NEW.customer_attribution_at IS NOT NULL)
          EXECUTE FUNCTION evidence_span_fixed_at_mint()
    """)
    op.execute("DROP TRIGGER IF EXISTS evidence_span_fixed ON evidence_index")
    op.execute("""
        CREATE TRIGGER evidence_span_fixed
          BEFORE UPDATE OF customer_attribution, customer_attribution_at,
                           split_of ON evidence_index
          FOR EACH ROW
          EXECUTE FUNCTION evidence_span_fixed_at_mint()
    """)

    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_mcp') THEN
            EXECUTE 'GRANT SELECT, INSERT ON connector_responses TO svc_mcp';
          END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS evidence_span_fixed ON evidence_index")
    op.execute("DROP TRIGGER IF EXISTS evidence_span_minted ON evidence_index")
    op.execute("DROP FUNCTION IF EXISTS evidence_span_fixed_at_mint()")
    op.execute("ALTER TABLE evidence_index DROP CONSTRAINT IF EXISTS "
               "evidence_index_attribution_is_a_split_span")
    for col in ("customer_attribution_at", "split_of", "customer_attribution",
                "connector_response_sha256", "connector_retrieved_at",
                "connector_query", "connector_tool"):
        op.execute(f"ALTER TABLE evidence_index DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS connector_responses")
