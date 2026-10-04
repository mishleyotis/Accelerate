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
def test_a_whole_row_span_is_refused():
    """The whole parent is not a split: re-labelling it would publish every
    word of it, the seller remark included."""
    bad = split_problem(PARENT, "ent-1", PARENT_EXCERPT)
    assert bad is not None and "whole_row" in bad, bad
    # the same words under different spacing and case are still the whole row
    respaced = "  " + PARENT_EXCERPT.upper().replace(" ", "   ") + " "
    bad = split_problem(PARENT, "ent-1", respaced)
    assert bad is not None and "whole_row" in bad, bad
    # a strictly shorter verbatim piece is a split
    assert split_problem(PARENT, "ent-1", SPAN) is None


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
        ("E-SSB-902", PARENT_EXCERPT, parent),               # whole row
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
