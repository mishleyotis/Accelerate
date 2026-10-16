"""A whole discovery row may be shared — as a NEW span, never the parent
(owner decision 2026-10-05).

0063 refused any split span that was not STRICTLY SHORTER than its parent,
in the database (`evidence_span_fixed_at_mint`) and in register_evidence
(`split_span_whole_row`). The aim was right — re-labelling a parent that
carries a seller remark publishes the remark — but a discovery row that is
ENTIRELY the client's statement had no honest route: a producer published
five such rows with only the closing full stop trimmed, which met the rule's
wording and not its intent.

The owner allowed whole-row sharing, by MINTING a new evidence row:
split_of = the parent, the parent's full excerpt, the customer attribution.
Every 0063 guarantee stands — the attribution is written only by the INSERT
that mints the span, never onto the parent nor onto a row a dedup lands on;
the api serves it only on a run promoted at or after its mint; the internal
parent is never served.

Two things in the schema stood in the way. Both changes are EXPAND-ONLY: no
column is added, dropped or retyped, and no existing row changes.

## 1 · The dedup key includes the lineage

`evidence_dedup_uq (entity_id, content_hash)` (0005) — and content_hash is
url | claim | excerpt — would fold a whole-row span into its parent: same
words, same claim, and neither has a URL. register_evidence would then find
the PARENT on its dedup path and (correctly) refuse to label it.

It is replaced by `evidence_dedup_lineage_uq (entity_id, content_hash,
coalesce(split_of, ''))`: a span's identity includes the row it was split
from. Strictly WEAKER than the old key — every pair of rows the old index
held distinct, the new one holds distinct — so it builds over the existing
rows without a conflict, and every writer that relies on a bare ON CONFLICT
(register_evidence, the worker's ingest) keeps working unchanged:

  * an unsplit row (split_of NULL, every package/producer/connector row)
    dedups exactly as before — '' for all of them;
  * the same span of the same parent registered twice still collides: the
    idempotent retry;
  * a span and its parent, or spans of two different parents, are distinct
    rows. (0063 refused the second with `split_span_exists`; it is now a
    span of its own parent, which is what it is.)

The old index is dropped AFTER the new one exists, in this transaction, so
there is no instant with no dedup key. A plain `CREATE UNIQUE INDEX`, not
CONCURRENTLY: Alembic runs inside the transaction env.py opens, and 0056
set the precedent for a short build on a table of this size; the lock is
held for the build of one btree over evidence_index's few tens of thousands
of rows, and its only writers are the connector and the worker Job.

Readers that looked a row up by (entity_id, content_hash) now add the
lineage — register_evidence's dedup branch, the worker's `_dedup_branch` —
so a lookup can never answer with the span when it meant the parent.

## 2 · The mint trigger allows the whole row, and checks verbatim

`evidence_span_fixed_at_mint()` is replaced. An attributed INSERT is still
refused unless it is a split of an internal row of the same entity; the
length test (`>=` the parent → refused) becomes a VERBATIM test: the span,
whitespace-normalised and case-folded, must be contained in the parent's
excerpt — the whole of it included. That is the rule register_evidence has
always applied, now held in the database too, so it is tighter than 0063's
on every span except the one the owner allowed. UPDATE behaviour is
unchanged: the attribution, its mint instant and the lineage are fixed at
mint, for every role. The intent check — the producer DECLARES the row is
entirely the client's statement (`whole_row: true`) — lives in
register_evidence, which is the only writer that mints spans.

## Grants, in this revision

No table, column or function is added; the trigger function is replaced in
place (`CREATE OR REPLACE` keeps its owner and ACL) and runs as the inserting
role. The new index is on a table whose grants are unchanged — svc_mcp
INSERTs and SELECTs evidence_index, svc_api SELECTs it, svc_worker INSERTs
it (0005, 0063). Re-stated below, idempotently, so the revision says who may
use what it touched.

Revision ID: 0065
Revises: 0064
"""
from alembic import op

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None

#: The verbatim test, in SQL, as register_evidence._normalise states it:
#: runs of whitespace collapsed, trimmed, case-folded.
_NORM = "lower(btrim(regexp_replace(coalesce({x}, ''), '\\s+', ' ', 'g')))"

_FUNCTION = r"""
CREATE OR REPLACE FUNCTION evidence_span_fixed_at_mint() RETURNS trigger
  LANGUAGE plpgsql
  SET search_path = public
  AS $fn$
DECLARE
  p_entity uuid;
  p_origin text;
  p_excerpt text;
  span text;
  whole text;
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
  span := @SPAN@;
  whole := @WHOLE@;
  -- A verbatim piece of the parent, the whole of it included (owner
  -- decision 2026-10-05); a longer or reworded span is refused.
  IF span = '' OR position(span IN whole) = 0 THEN
    RAISE EXCEPTION 'evidence % : a shareable span is a verbatim piece of its parent % (the whole row included)', NEW.e_id, NEW.split_of
      USING ERRCODE = 'check_violation';
  END IF;
  NEW.customer_attribution_at := now();
  RETURN NEW;
END
$fn$
""".replace("@SPAN@", _NORM.format(x="NEW.excerpt")).replace(
    "@WHOLE@", _NORM.format(x="p_excerpt"))

#: 0063's function body, verbatim, for the downgrade.
_FUNCTION_0063 = r"""
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
"""


def _grant(sql: str, role: str) -> None:
    op.execute(f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            EXECUTE '{sql} TO {role}';
          END IF;
        END $$;
    """)


def upgrade() -> None:
    # 1 · the lineage-aware dedup key, built before the old one goes.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS evidence_dedup_lineage_uq
            ON evidence_index (entity_id, content_hash,
                               (coalesce(split_of, '')))
    """)
    op.execute("DROP INDEX IF EXISTS evidence_dedup_uq")
    op.execute("COMMENT ON INDEX evidence_dedup_lineage_uq IS "
               "'Content dedup, scoped to the entity and to the row a span "
               "was split from (0065): a span is never folded into its "
               "parent, and the same span registered twice is one row.'")

    # 2 · the mint trigger: verbatim, the whole row included.
    op.execute(_FUNCTION)

    # Grants (unchanged; re-stated so the revision names them).
    _grant("GRANT SELECT, INSERT, UPDATE ON evidence_index", "svc_mcp")
    _grant("GRANT SELECT ON evidence_index", "svc_api")


def downgrade() -> None:
    # Refuses, by the old unique index, if a whole-row span exists — which
    # is the honest answer: the downgrade would fold it into its parent.
    op.execute(_FUNCTION_0063)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS evidence_dedup_uq "
               "ON evidence_index (entity_id, content_hash)")
    op.execute("DROP INDEX IF EXISTS evidence_dedup_lineage_uq")
