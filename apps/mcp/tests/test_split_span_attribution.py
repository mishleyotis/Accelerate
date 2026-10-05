"""A customer attribution is minted with a NEW split span, never added to an
existing row (RC-08 / D-10; adversarial review of fix/serving-redaction-
evidence, 2026-10-04).

The first cut of the split path had two ways to put `customer_attribution`
on a row that already existed:

  · "THE WHOLE ROW IS THE SHAREABLE SPAN": a split whose excerpt equalled the
    parent's UPDATEd the attribution onto the PARENT. On the review's own
    fixture that parent carried the seller remark the same test registered as
    the internal span — one call made the whole internal row shareable;
  · the DEDUP branch: re-registering an existing internal span with an
    attribution filled it in, undoing "an internal span never serves".

`evidence_index` is shared by every run of an entity and the api reads it
live, so either UPDATE changed what customers saw on runs already promoted,
outside promotion and under an unchanged ETag, with no tool to take it back.

Now: an attribution exists only on a span minted by this call, strictly
shorter than its parent; the dedup path never writes one; and the database
refuses an attribution, its mint instant or the lineage changing after the
INSERT (migration 0063's `evidence_span_fixed_at_mint`).

OWNER DECISION 2026-10-05 — whole-row sharing. A discovery row that is
ENTIRELY a client statement may be shared whole. The first rule refused any
span equal to its parent (`split_span_whole_row`), and a producer published
five rows with only the closing full stop trimmed: the rule's wording met,
its intent not. Now a whole-row span is minted as a NEW row — split_of the
parent, the parent's full excerpt, the customer attribution — when the
producer says so with `whole_row: true`. Every guarantee above stands: the
parent is never touched and never served, the dedup path never writes an
attribution, and the content-hash dedup cannot fold the span into its
parent because a span's identity includes its lineage (migration 0065's
`evidence_dedup_lineage_uq`), while registering the same span twice is
still the idempotent retry.

The pure rules run without a database; the mint paths run against the
migrated local database named by LOCAL_DATABASE_URL and skip honestly
without one.
"""
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.register import register_evidence, split_problem  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]

PARENT_EXCERPT = ("The sponsor said there is no single customer profile "
                  "across the lines of business, and asked for a proposal "
                  "covering about five hundred users.")
PARENT = ("E-CC-1", "ent-1", "internal", PARENT_EXCERPT)
SPAN = "there is no single customer profile across the lines of business"
SELLER_SPAN = "asked for a proposal covering about five hundred users"
LABEL = "Client statement, discovery conversations, September 2026"


# ── pure rules ─────────────────────────────────────────────────────────────
def test_a_whole_row_span_is_refused_unless_declared():
    """The whole parent, sent as an ordinary split, is refused: on a row that
    carries a seller remark it would publish every word of it. It is shared
    whole only when the producer declares the row is entirely the client's
    statement (`whole_row: true`, owner decision 2026-10-05)."""
    bad = split_problem(PARENT, "ent-1", PARENT_EXCERPT)
    assert bad is not None and "whole_row" in bad, bad
    # the same words under different spacing and case are still the whole row
    respaced = "  " + PARENT_EXCERPT.upper().replace(" ", "   ") + " "
    bad = split_problem(PARENT, "ent-1", respaced)
    assert bad is not None and "whole_row" in bad, bad
    # a strictly shorter verbatim piece is a split
    assert split_problem(PARENT, "ent-1", SPAN) is None
    # the message says how to share a row whole on purpose
    assert "whole_row" in split_problem(PARENT, "ent-1", PARENT_EXCERPT)


def test_a_declared_whole_row_span_is_accepted():
    assert split_problem(PARENT, "ent-1", PARENT_EXCERPT,
                         whole_row=True) is None
    respaced = "  " + PARENT_EXCERPT.upper().replace(" ", "   ") + " "
    assert split_problem(PARENT, "ent-1", respaced, whole_row=True) is None


def test_a_declared_whole_row_must_be_the_whole_row():
    """`whole_row: true` on a shorter span — or one that is not verbatim — is
    a contradiction, refused rather than guessed at."""
    bad = split_problem(PARENT, "ent-1", SPAN, whole_row=True)
    assert bad is not None and bad.startswith("split_whole_row_mismatch"), bad
    bad = split_problem(PARENT, "ent-1", PARENT_EXCERPT + " More.",
                        whole_row=True)
    assert bad is not None and "not_verbatim" in bad, bad
    # the foreign and non-internal refusals still come first
    assert "foreign" in split_problem(PARENT, "ent-2", PARENT_EXCERPT,
                                      whole_row=True)
    public = ("E-CC-1", "ent-1", "producer", PARENT_EXCERPT)
    assert "only an internal-origin row" in split_problem(
        public, "ent-1", PARENT_EXCERPT, whole_row=True)


def test_no_code_path_updates_an_attribution():
    """Asserted on the source, because the defect was an UPDATE: the only
    write of `customer_attribution` is the INSERT that mints the span."""
    src = (ROOT / "apps" / "mcp" / "dma_mcp" / "register.py").read_text()
    updates = [m.group(0) for m in re.finditer(
        r"UPDATE\s+evidence_index\s+SET(.*?)WHERE", src, re.S)]
    assert updates, "the date-fill UPDATE should still be there"
    for u in updates:
        assert "customer_attribution" not in u, u
        assert "split_of" not in u, u


# ── the mint paths, against the migrated local database ───────────────────
DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
_U = urlparse(DSN.replace("+pg8000", ""))
HOST, PORT = _U.hostname or "localhost", _U.port or 5432
DB = (_U.path or "/dma_insights").lstrip("/") or "dma_insights"
DISPLAY = "synthetic-split-span-bank"


@pytest.fixture()
def seeded():
    import pg8000.dbapi
    try:
        mcp = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                   password="local", host=HOST, port=PORT,
                                   database=DB)
        admin = pg8000.dbapi.connect(
            user="dmai-migrate@digital-maturity-assessor.iam",
            password="local", host=HOST, port=PORT, database=DB)
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    cur.execute("""SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'evidence_index'
                      AND column_name = 'customer_attribution_at'""")
    if cur.fetchone() is None:
        mcp.close()
        admin.close()
        pytest.fail("the local database predates 0063's customer_attribution_at"
                    " — re-run `alembic upgrade head`")

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = %s",
                    (DISPLAY,))
        for (eid,) in cur.fetchall():
            for sql in (
                """DELETE FROM evidence_dedup_audit WHERE matched_e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                """DELETE FROM evidence_subcap_links WHERE e_id IN
                     (SELECT e_id FROM evidence_index WHERE entity_id = %s)""",
                "DELETE FROM runs WHERE entity_id = %s",
                # Parent and spans go in ONE statement: the self-reference is
                # NO ACTION, checked at the statement's end, and the lineage
                # column cannot be nulled first (it is fixed at mint).
                "DELETE FROM evidence_index WHERE entity_id = %s",
                "DELETE FROM entities WHERE id = %s",
            ):
                cur.execute(sql, (eid,))
        admin.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES (%s,'ACTIVE', now()) RETURNING id""", (DISPLAY,))
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status,
                                     completed_at)
                   VALUES (%s,'DMA-ASM-SSB-20261001-01',1,'INGESTED',
                           '2026-10-01') RETURNING id""", (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, admin, str(rid), str(eid)
    mcp.rollback()
    admin.rollback()
    clean()
    mcp.close()
    admin.close()


def _parent(mcp, rid):
    r = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "claim_type": "FACT",
        "tier": "T2", "source_name": "Internal discovery notes",
        "published_date": "2026-09-01"}, fetch=None)
    assert r["errors"] == [], r
    return r["e_id"]


def _row(mcp, e_id):
    cur = mcp.cursor()
    cur.execute("""SELECT customer_attribution, customer_attribution_at,
                          split_of
                     FROM evidence_index WHERE e_id = %s""", (e_id,))
    row = cur.fetchone()
    return tuple(row) if row is not None else None


def test_the_whole_row_never_gains_an_attribution(seeded):
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    r = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "split_of": parent,
        "customer_attribution": LABEL}, fetch=None)
    assert r["e_id"] is None and any("whole_row" in e for e in r["errors"]), r
    assert _row(mcp, parent) == (None, None, None)


def _whole(mcp, rid, parent, label=LABEL, **kw):
    return register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "split_of": parent,
        "customer_attribution": label, "whole_row": True, **kw}, fetch=None)


def _excerpt(mcp, e_id):
    cur = mcp.cursor()
    cur.execute("SELECT excerpt FROM evidence_index WHERE e_id = %s", (e_id,))
    return cur.fetchone()[0]


def test_a_whole_row_span_is_minted_as_a_new_row(seeded):
    """Owner decision 2026-10-05: a NEW row — split_of the parent, the
    parent's full excerpt, the attribution, stamped by the database — and
    the parent untouched. The content-hash dedup does not fold it into the
    parent although the words, claim and (absent) URL are identical."""
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    r = _whole(mcp, rid, parent)
    assert r["errors"] == [] and r["deduped"] is False, r
    assert r["e_id"] not in (None, parent), r
    attribution, stamped, lineage = _row(mcp, r["e_id"])
    assert (attribution, lineage) == (LABEL, parent)
    assert stamped is not None, "the mint instant is stamped by the database"
    assert _excerpt(mcp, r["e_id"]) == _excerpt(mcp, parent) == PARENT_EXCERPT
    assert _row(mcp, parent) == (None, None, None), "the parent is untouched"


def test_a_whole_row_span_stores_the_parents_exact_excerpt(seeded):
    """The span IS the parent's text: a re-spaced or re-cased copy sent by
    the producer is stored as the parent's own bytes, never the producer's."""
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    sent = PARENT_EXCERPT.replace(" ", "  ")
    r = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": sent, "split_of": parent,
        "customer_attribution": LABEL, "whole_row": True}, fetch=None)
    assert r["errors"] == [], r
    assert _excerpt(mcp, r["e_id"]) == PARENT_EXCERPT


def test_a_whole_row_span_re_registers_idempotently(seeded):
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    first = _whole(mcp, rid, parent)
    assert first["errors"] == [], first
    minted = _row(mcp, first["e_id"])
    again = _whole(mcp, rid, parent)
    assert again["errors"] == [] and again["deduped"] is True, again
    assert again["e_id"] == first["e_id"]
    assert _row(mcp, first["e_id"]) == minted, "a retry writes nothing"
    cur = mcp.cursor()
    cur.execute("""SELECT count(*) FROM evidence_index
                    WHERE split_of = %s""", (parent,))
    assert cur.fetchone()[0] == 1
    # a different label on the same span is a different claim: refused
    other = _whole(mcp, rid, parent,
                   label="Client statement, board pack, August 2026")
    assert other["e_id"] is None and any(
        "split_span_exists" in e for e in other["errors"]), other
    assert _row(mcp, first["e_id"]) == minted


def test_a_whole_row_share_never_backfills_the_parent(seeded):
    """No path writes an attribution onto an existing row: not the parent
    re-registered with a label (no split_of), not a plain re-registration of
    the parent's words, which dedups onto the PARENT — never onto the span
    — and comes back unlabelled."""
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    span = _whole(mcp, rid, parent)
    assert span["errors"] == [], span
    labelled = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "claim_type": "FACT",
        "tier": "T2", "customer_attribution": LABEL}, fetch=None)
    assert labelled["e_id"] is None, labelled
    plain = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "claim_type": "FACT",
        "tier": "T2", "source_name": "Internal discovery notes"}, fetch=None)
    assert plain["errors"] == [] and plain["deduped"] is True, plain
    assert plain["e_id"] == parent, "the parent's words dedup to the parent"
    assert _row(mcp, parent) == (None, None, None)


def test_a_whole_row_span_needs_an_attribution(seeded):
    """An unlabelled whole-row copy would be the parent again under a second
    id — internal, never served, and nothing a reader gains."""
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    r = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "split_of": parent,
        "whole_row": True}, fetch=None)
    assert r["e_id"] is None and any(
        e.startswith("whole_row") for e in r["errors"]), r


def test_whole_row_without_a_split_is_refused(seeded):
    mcp, _admin, rid, _eid = seeded
    r = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": PARENT_EXCERPT, "claim_type": "FACT",
        "tier": "T2", "whole_row": True}, fetch=None)
    assert r["e_id"] is None and any(
        e.startswith("whole_row") for e in r["errors"]), r


def test_dedup_never_backfills_an_attribution(seeded):
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    internal = register_evidence(mcp, rid, {
        "origin": "internal", "split_of": parent, "excerpt": SELLER_SPAN},
        fetch=None)
    assert internal["errors"] == [], internal
    # The same words again, now asking to be shareable: refused, unchanged.
    again = register_evidence(mcp, rid, {
        "origin": "internal", "split_of": parent, "excerpt": SELLER_SPAN,
        "customer_attribution": LABEL}, fetch=None)
    assert again["e_id"] is None, again
    assert any("split_span_exists" in e for e in again["errors"]), again
    assert _row(mcp, internal["e_id"]) == (None, None, parent)
    # and the refusal left the connection usable, not mid-aborted
    cur = mcp.cursor()
    cur.execute("SELECT 1")
    assert list(cur.fetchone()) == [1]


def test_the_shareable_span_is_minted_stamped_and_idempotent(seeded):
    mcp, _admin, rid, _eid = seeded
    parent = _parent(mcp, rid)
    shared = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": SPAN, "split_of": parent,
        "customer_attribution": LABEL}, fetch=None)
    assert shared["errors"] == [] and shared["deduped"] is False, shared
    assert shared["e_id"] != parent
    attribution, stamped, lineage = _row(mcp, shared["e_id"])
    assert attribution == LABEL and lineage == parent
    assert stamped is not None, "the mint instant is stamped by the database"
    # Re-registering the identical shareable span returns it — no new row,
    # no write — so a producer retrying a call is safe.
    again = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": SPAN, "split_of": parent,
        "customer_attribution": LABEL}, fetch=None)
    assert again["errors"] == [] and again["deduped"] is True, again
    assert again["e_id"] == shared["e_id"]
    assert _row(mcp, shared["e_id"]) == (attribution, stamped, lineage)
    # The same words under a DIFFERENT label is a different claim about who
    # may read them: refused, the first label stands.
    other = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": SPAN, "split_of": parent,
        "customer_attribution": "Client statement, board pack, August 2026"},
        fetch=None)
    assert other["e_id"] is None and any(
        "split_span_exists" in e for e in other["errors"]), other
    assert _row(mcp, shared["e_id"])[0] == LABEL


def test_the_database_refuses_an_attribution_after_mint(seeded):
    """Belt and braces under register_evidence: no role can UPDATE a span's
    attribution, its mint instant or its lineage, and an INSERT cannot
    attribute a row that is not a strictly shorter split of an internal
    parent."""
    import pg8000.dbapi
    mcp, _admin, rid, eid = seeded
    parent = _parent(mcp, rid)
    shared = register_evidence(mcp, rid, {
        "origin": "internal", "excerpt": SPAN, "split_of": parent,
        "customer_attribution": LABEL}, fetch=None)
    assert shared["errors"] == [], shared
    cur = mcp.cursor()
    for sql, args in (
        ("UPDATE evidence_index SET customer_attribution = %s WHERE e_id = %s",
         (LABEL, parent)),
        ("UPDATE evidence_index SET customer_attribution = NULL WHERE e_id = %s",
         (shared["e_id"],)),
        ("UPDATE evidence_index SET customer_attribution_at = now() "
         "- interval '1 year' WHERE e_id = %s", (shared["e_id"],)),
        ("UPDATE evidence_index SET split_of = NULL WHERE e_id = %s",
         (shared["e_id"],)),
    ):
        with pytest.raises(pg8000.dbapi.DatabaseError):
            cur.execute(sql, args)
        mcp.rollback()
    for e_id, excerpt, split_of in (
        ("E-SSB-901", SPAN + " (no split)", None),           # no lineage
        ("E-SSB-902", PARENT_EXCERPT + " And more.", parent),  # longer
        ("E-SSB-903", "words the parent never said at any point in "
                      "the discovery conversations", parent),  # not verbatim
    ):
        with pytest.raises(pg8000.dbapi.DatabaseError):
            cur.execute(
                """INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, excerpt,
                      claim_type, tier, customer_attribution, split_of)
                   VALUES (%s, %s, 'internal', 'x', %s, 'FACT', 'T2', %s, %s)""",
                (e_id, eid, excerpt, LABEL, split_of))
        mcp.rollback()
    assert _row(mcp, parent) == (None, None, None)
    # 0065: the WHOLE row is a legal mint in the database (the connector
    # demands `whole_row: true` for it), and it is a distinct row — the
    # lineage-aware dedup key does not fold it into the parent.
    cur.execute(
        """INSERT INTO evidence_index
             (e_id, entity_id, origin, source_name, excerpt,
              claim_type, tier, customer_attribution, split_of)
           VALUES ('E-SSB-904', %s, 'internal', 'x', %s, 'FACT', 'T2', %s, %s)
           RETURNING customer_attribution_at""",
        (eid, PARENT_EXCERPT, LABEL, parent))
    assert cur.fetchone()[0] is not None
    mcp.rollback()
    assert _row(mcp, parent) == (None, None, None)
