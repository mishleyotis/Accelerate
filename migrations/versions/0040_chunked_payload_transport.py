"""0040 — chunked payload transport: the staging area a whole payload arrives in.

## The defect this exists for (MEM-0030, TRANSPORT_BOUNDS_THE_CONTRACT)

`submit_page_payload` took the payload as an inline JSON object, so a producing
agent had to emit the entire page as literal tokens inside one tool call. A
contract-complete heatmap does not fit. Measured on 2026-08-08 by two
independent producers:

  * Frost Bank        1,128,742 bytes compact (~282k tokens);
                      `cell_evidence` alone 862,351 across 697 served cells.
  * Fisher Investments heatmap 1,598,147 chars; `cell_evidence` 1,208,289
                      across 708 cells. The barest still-compliant reduction —
                      subcap_id/e_ids/synthesis/grounded_on/thin/provenance
                      only — is still 347,509 chars, plus 285,520 for 206
                      alerts.

Rule 17 requires a drawer row for EVERY served cell, so the size is the
contract's, not an authoring choice. The diagnosis it explains: the reference
client `baxter-credit-union-bcu` serves 69 `cell_evidence` rows out of 765
cells — 9%. That was never a synthesis decision; it is roughly what fit through
the interface. Every partial payload validated perfectly, which is why nobody
saw it.

## What these two tables are, and what they are deliberately not

They are a TRANSPORT staging area, not a second content path. A part is inert:
nothing reads it but the assembler, no gate runs over it, no writer can see it,
and `promote_run` does not know it exists. Only the ASSEMBLED whole becomes a
row in `submissions`, and only after the same two validation passes that an
inline payload has always gone through. Invariant 2 is unchanged — content
still enters through the connector and nowhere else; it now arrives in more
than one breath.

**payload_uploads** — one row per upload, opened by the connector, which is
what allocates the id (invariant 10: the server allocates identifiers; a
producer that could name its own upload could append into someone else's).
Bound to (run_id, page) at open, so a part cannot be misrouted to another
page's payload later. `parts_total` is the producer's DECLARED part count,
recorded from the first part and required to agree on every subsequent one —
that declaration is what makes an incomplete transmission detectable rather
than merely smaller than intended.

**payload_upload_parts** — one row per part, keyed by (upload_id, part) so a
retry of part 7 after a dropped connection REPLACES part 7 instead of
duplicating it. `op` is `merge` (shallow-merge an object at a dotted path) or
`append` (extend a list at a dotted path); both are order-insensitive up to the
part index, and assembly always applies parts in ascending index, so the same
set of parts assembles to the same bytes every time.

Atomicity (invariant 3's sibling at the submit boundary): submit refuses unless
the received part set is exactly {1..parts_total}. A gap is named — the missing
indexes, by number — under CG-16, and NO submission row is created. There is no
state in which a partially transmitted payload is submittable.

`ON DELETE CASCADE` on the parts, and an opportunistic sweep of OPEN uploads
older than 48 hours at open time, keep abandoned transmissions from
accumulating. A CLOSED upload keeps its parts: they are the record of what was
assembled into the submission it names, which is the only way to answer "what
exactly did the server validate" after the fact.

Plain `CREATE INDEX`, not CONCURRENTLY: both tables are created empty in this
transaction and nothing can be reading them yet.

Revision ID: 0040
Revises: 0032
Create Date: 2026-08-08

Chained from 0032, not from 0035: the file numbers in this directory are not
the revision order (0031 revises 0035, 0032 revises 0031), and `alembic upgrade
head` refuses to run with more than one head. The head is what it is regardless
of what the next filename says.
"""
from alembic import op

revision = "0040"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE payload_uploads (
          id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
          run_id           UUID NOT NULL REFERENCES runs(id),
          page             page_t NOT NULL,
          producer_version TEXT,
          opened_by        TEXT,
          opened_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
          -- the producer's declared part count, recorded from the first part
          -- and required to agree on every one after it
          parts_total      INTEGER,
          state            TEXT NOT NULL DEFAULT 'OPEN',
          closed_at        TIMESTAMPTZ,
          -- the submission this upload assembled into, once it has
          submission_id    UUID REFERENCES submissions(id),
          CONSTRAINT payload_uploads_state CHECK (state IN ('OPEN', 'CLOSED')),
          CONSTRAINT payload_uploads_parts_total
            CHECK (parts_total IS NULL OR parts_total >= 1),
          CONSTRAINT payload_uploads_closed_has_time
            CHECK (state <> 'CLOSED' OR closed_at IS NOT NULL)
        )
        """
    )
    op.execute("CREATE INDEX payload_uploads_run_page ON payload_uploads "
               "(run_id, page, opened_at DESC)")
    op.execute("CREATE INDEX payload_uploads_open_age ON payload_uploads "
               "(opened_at) WHERE state = 'OPEN'")

    op.execute(
        """
        CREATE TABLE payload_upload_parts (
          upload_id   UUID NOT NULL
                      REFERENCES payload_uploads(id) ON DELETE CASCADE,
          part        INTEGER NOT NULL,
          -- merge: shallow-merge an object at `path`
          -- append: extend the list at `path`
          op          TEXT NOT NULL,
          -- dotted path from the payload root; '' is the root itself
          path        TEXT NOT NULL,
          body        JSONB NOT NULL,
          bytes       INTEGER NOT NULL,
          item_count  INTEGER,
          received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          PRIMARY KEY (upload_id, part),
          CONSTRAINT payload_upload_parts_op CHECK (op IN ('merge', 'append')),
          CONSTRAINT payload_upload_parts_index CHECK (part >= 1),
          CONSTRAINT payload_upload_parts_bytes CHECK (bytes >= 0)
        )
        """
    )

    # The connector, and only the connector. No grant of any kind to svc_api
    # (the boundary) or svc_worker — the same posture as `submissions` in 0006.
    for t in ("payload_uploads", "payload_upload_parts"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_mcp")


def downgrade() -> None:
    for t in ("payload_upload_parts", "payload_uploads"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
