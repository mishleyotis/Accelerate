"""The worker's hash mirror must equal the generated column, on every input.

WHAT WENT WRONG. `evidence_index.content_hash` is a GENERATED column:

    coalesce(source_url,'') || '|' || coalesce(enum_label(claim_type),'')
                           || '|' || lower(left(regexp_replace(excerpt,…),500))

`EvidenceLander.HASH_SQL` re-implements it so the worker can find a row again
after `ON CONFLICT` fires. It hardcoded the middle segment as `''`, carrying
the comment "the package path never asserts a claim type" — while the INSERT
eleven lines below it passed `ev.get("claim_type")` straight into the column.
The premise was false in the same file that stated it.

Measured against the live column, 2026-08-30, same url and excerpt:

    claim_type NULL   generated af4458b1…   mirror af4458b1…   agree
    claim_type FACT   generated 74b8e86d…   mirror af4458b1…   DIVERGE

So a package evidence item carrying a claim type hashed one way going in and
another coming back, and all three of the worker's lookups missed the row the
unique index had just rejected against:

  * "same id, different content" read TRUE for a row the entity already held
    -> a mint under a suffix, logged `evidence_id_collision`
  * the dedup lookup could not find the kept row -> the item was
    UNATTRIBUTABLE AND DROPPED, logged `evidence_conflict_unresolved`

goeasy-ltd, one package: 316 collisions and 430 dropped items — both recorded
as facts about the package rather than about this expression.

WHY IT IS SHAPED LIKE THIS. A test that re-typed the expected SQL would be a
third copy agreeing with the second, and would have passed against the broken
mirror. So it INSERTS rows and reads `content_hash` back: the comparison is
against what Postgres actually stores, and nothing here knows or restates
what the expression should be.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker.evidence_ids import EvidenceLander                # noqa: E402


@pytest.fixture()
def db():
    try:
        import pg8000.dbapi
        conn = pg8000.dbapi.connect(host="localhost", port=5432,
                                    user="postgres", password="local",
                                    database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM information_schema.columns WHERE "
                "table_name='evidence_index' AND column_name='content_hash'")
    if cur.fetchone() is None:
        conn.close()
        pytest.skip("evidence_index.content_hash is absent in this database")
    yield conn, cur
    conn.rollback()          # nothing this test writes is ever committed
    conn.close()


def _entity(cur) -> str:
    cur.execute("INSERT INTO entities (display_id, legal_name) "
                "VALUES (%s, %s) RETURNING id",
                (f"hashmirror-{uuid.uuid4().hex[:10]}", "Hash Mirror Fixture"))
    return cur.fetchone()[0]


def _claim_types(cur) -> list:
    cur.execute("SELECT enumlabel FROM pg_enum e JOIN pg_type t "
                "ON t.oid = e.enumtypid WHERE t.typname = 'claim_t' "
                "ORDER BY e.enumsortorder")
    return [r[0] for r in cur.fetchall()]


#: Inputs chosen to exercise each transform the expression applies:
#: the url COALESCE, the whitespace collapse, the 500-char truncation and
#: the case fold. A mirror that agreed only on tidy input would still drop
#: real evidence.
CASES = [
    ("https://example.com/a", "A verbatim clause of ordinary length that a "
                              "producer could cite without trimming it."),
    (None, "An item with no source url at all, which the column coalesces."),
    ("https://example.com/b", "  ragged\t\twhitespace   collapses  "),
    ("https://example.com/c", "x" * 700),
    ("https://example.com/d", "MiXeD Case Folds Down"),
]


def _stored_and_mirrored(cur, entity_id, url, ct, excerpt):
    e_id = f"E-HM-{uuid.uuid4().hex[:12]}"
    cur.execute("""INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_url, excerpt, claim_type)
                   VALUES (%s, %s, 'package', %s, %s, %s)
                   RETURNING content_hash""",
                (e_id, entity_id, url, excerpt, ct))
    stored = cur.fetchone()[0]
    cur.execute(f"SELECT {EvidenceLander.HASH_SQL}", (url, ct, excerpt))
    return stored, cur.fetchone()[0]


def test_the_mirror_equals_the_stored_hash_for_every_claim_type(db):
    """THE DEFECT, across the whole enum rather than the one value that
    happened to be in the failing package."""
    conn, cur = db
    entity_id = _entity(cur)
    types = [None] + _claim_types(cur)
    assert len(types) > 1, "claim_t carries no labels; nothing was compared"

    bad = []
    for ct in types:
        for url, excerpt in CASES:
            stored, mirror = _stored_and_mirrored(cur, entity_id, url, ct,
                                                  excerpt)
            if stored != mirror:
                bad.append({"claim_type": ct, "url": url,
                            "excerpt": excerpt[:30], "stored": stored[:12],
                            "mirror": mirror[:12]})
    assert not bad, (
        "HASH_SQL and the generated column disagree, so every lookup after "
        "ON CONFLICT misses the row it just collided with and the item is "
        f"dropped as unattributable: {bad}")


def test_a_claim_type_actually_changes_the_stored_hash(db):
    """The floor. If claim_type made no difference to the digest, the test
    above would pass against a mirror that ignored it — which is exactly the
    bug it exists to catch."""
    conn, cur = db
    types = _claim_types(cur)
    if not types:
        pytest.skip("claim_t carries no labels")
    entity_id = _entity(cur)
    url, excerpt = CASES[0]
    without, _ = _stored_and_mirrored(cur, entity_id, url, None, excerpt)
    with_ct, _ = _stored_and_mirrored(cur, entity_id, url, types[0], excerpt)
    assert without != with_ct, (
        "claim_type does not reach the stored hash at all, so this whole "
        "comparison proves nothing")


def test_the_lookup_finds_a_row_that_carries_a_claim_type(db):
    """The consequence, end to end: the dedup lookup whose miss DROPPED the
    item. Same WHERE clause `_dedup_branch` uses."""
    conn, cur = db
    types = _claim_types(cur)
    if not types:
        pytest.skip("claim_t carries no labels")
    entity_id = _entity(cur)
    url, excerpt = CASES[0]
    _stored_and_mirrored(cur, entity_id, url, types[0], excerpt)
    cur.execute(f"""SELECT e_id FROM evidence_index
                     WHERE entity_id = %s
                       AND content_hash = {EvidenceLander.HASH_SQL}""",
                (entity_id, url, types[0], excerpt))
    assert cur.fetchone() is not None, (
        "the row is stored and the worker cannot find it — this is the miss "
        "that logged evidence_conflict_unresolved and dropped the evidence")


def test_the_mirror_takes_three_parameters(db):
    """A shape check that fails loudly rather than mis-binding: three
    placeholders, bound url, claim_type, excerpt in that order."""
    conn, cur = db
    assert EvidenceLander.HASH_SQL.count("%s") == 3
    cur.execute(f"SELECT {EvidenceLander.HASH_SQL}",
                ("https://x", None, "an excerpt"))
    assert len(cur.fetchone()[0]) == 64
