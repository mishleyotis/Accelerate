"""0065 — a whole discovery row is shared as its OWN span (owner decision
2026-10-05; RC-08 / D-10).

Pins the schema half of the decision, against the migrated database:

  * the revision chain (0065 revises 0064) and that it is expand-only — no
    column dropped, added or retyped;
  * the dedup key includes the lineage: `evidence_dedup_lineage_uq` on
    (entity_id, content_hash, coalesce(split_of, '')) exists, unique, and
    0005's `evidence_dedup_uq` is gone — so a whole-row span is a distinct
    row from its parent, while two unsplit rows with the same content and
    the same span of the same parent still collide;
  * the mint trigger accepts the whole row and refuses a longer or reworded
    span (verbatim, case- and whitespace-blind), and an attribution still
    cannot be added to, changed on or taken from a minted row;
  * grants on evidence_index are what they were.

Skips when no migrated database is reachable; every write is rolled back.
"""
import importlib.util
import os
import re
import sys
import types
from pathlib import Path

import pytest

pg8000 = pytest.importorskip("pg8000.dbapi")

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations" / "versions" / "0065_whole_row_share_is_its_own_span.py"
DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql+pg8000://postgres:local@localhost:5432/dma_insights")

PARENT = ("The member said every branch keys new accounts by hand and the "
          "call centre cannot see a loan application in flight.")
LABEL = "Client statement, discovery conversations, October 2026"


def _connect():
    rest = DSN.split("@", 1)[1]
    hostport, _, database = rest.partition("/")
    host, _, port = hostport.partition(":")
    creds = DSN.split("://", 1)[1].split("@", 1)[0]
    user, _, password = creds.partition(":")
    return pg8000.connect(user=user, password=password, host=host,
                          port=int(port or 5432),
                          database=database or "dma_insights")


@pytest.fixture(scope="module")
def db():
    try:
        conn = _connect()
    except Exception as e:                                     # noqa: BLE001
        pytest.skip(f"no migrated local database: {e}")
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture(scope="module")
def m():
    prior = sys.modules.get("alembic")
    sys.modules["alembic"] = types.SimpleNamespace(op=None)
    try:
        spec = importlib.util.spec_from_file_location("_m0065", MIG)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if prior is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = prior
    return mod


def q(conn, sql, args=()):
    cur = conn.cursor()
    cur.execute(sql, args)
    try:
        return [list(r) for r in cur.fetchall()]
    except Exception:                                          # noqa: BLE001
        return []


# ── the revision ───────────────────────────────────────────────────────────
def test_the_revision_chain_and_that_it_is_expand_only(m):
    assert (m.revision, m.down_revision) == ("0065", "0064")
    src = MIG.read_text()
    upgrade = src.split("def upgrade()", 1)[1].split("def downgrade()", 1)[0]
    assert not re.search(r"DROP\s+COLUMN|ADD\s+COLUMN|ALTER\s+COLUMN|"
                         r"DROP\s+TABLE|DELETE\s+FROM|UPDATE\s+evidence_index",
                         upgrade, re.I), "0065 changes no column and no row"
    # the new key is built before the old one is dropped
    assert upgrade.index("evidence_dedup_lineage_uq") < \
        upgrade.index("DROP INDEX IF EXISTS evidence_dedup_uq")


def test_the_dedup_key_includes_the_lineage(db):
    db.rollback()
    rows = q(db, """SELECT i.indisunique, pg_get_indexdef(i.indexrelid)
                      FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
                     WHERE c.relname = 'evidence_dedup_lineage_uq'""")
    assert rows, "0065 not applied — run `alembic upgrade head`"
    unique, ddl = rows[0]
    assert unique is True
    assert re.search(r"\(entity_id, content_hash, COALESCE\(split_of, "
                     r"''::text\)\)", ddl), ddl
    assert q(db, "SELECT 1 FROM pg_class WHERE relname = 'evidence_dedup_uq'") \
        == [], "0005's lineage-blind key would fold a span into its parent"


def test_grants_on_evidence_index_are_unchanged(db):
    db.rollback()
    got = {r[0]: r[1] for r in q(db, """
        SELECT grantee, string_agg(privilege_type, ',' ORDER BY privilege_type)
          FROM information_schema.role_table_grants
         WHERE table_name = 'evidence_index'
           AND grantee IN ('svc_api', 'svc_mcp', 'svc_worker')
         GROUP BY grantee""")}
    if not got:
        pytest.skip("service roles not provisioned in this database")
    assert got.get("svc_api") == "SELECT"
    assert got.get("svc_mcp") == "INSERT,SELECT,UPDATE"
    assert got.get("svc_worker") == "DELETE,INSERT,SELECT,UPDATE"


# ── behaviour, rolled back ────────────────────────────────────────────────
@pytest.fixture()
def entity(db):
    db.rollback()
    eid = q(db, """INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-0065-lineage', 'ACTIVE', now())
                   RETURNING id""")[0][0]
    q(db, """INSERT INTO evidence_index
               (e_id, entity_id, origin, source_name, excerpt, claim_type, tier)
             VALUES ('E-L65-001', %s, 'internal', 'Discovery notes', %s,
                     'FACT', 'T2')""", (eid, PARENT))
    yield eid
    db.rollback()


def _span(db, eid, e_id, excerpt, label=LABEL, split_of="E-L65-001"):
    return q(db, """INSERT INTO evidence_index
                      (e_id, entity_id, origin, source_name, excerpt,
                       claim_type, tier, customer_attribution, split_of)
                    VALUES (%s, %s, 'internal', 'Discovery notes', %s,
                            'FACT', 'T2', %s, %s)
                    RETURNING customer_attribution_at""",
             (e_id, eid, excerpt, label, split_of))


def test_a_whole_row_span_is_a_distinct_row_stamped_at_mint(db, entity):
    got = _span(db, entity, "E-L65-002", PARENT)
    assert got and got[0][0] is not None
    rows = q(db, """SELECT e_id, content_hash, split_of, customer_attribution
                      FROM evidence_index WHERE entity_id = %s
                     ORDER BY e_id""", (entity,))
    assert [r[0] for r in rows] == ["E-L65-001", "E-L65-002"]
    assert rows[0][1] == rows[1][1], "same words, same content hash"
    assert rows[0][2:] == [None, None], "the parent is untouched"
    assert rows[1][2:] == ["E-L65-001", LABEL]


def test_the_same_span_of_the_same_parent_still_collides(db, entity):
    _span(db, entity, "E-L65-002", PARENT)
    cur = db.cursor()
    cur.execute("""INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, excerpt,
                      claim_type, tier, customer_attribution, split_of)
                   VALUES ('E-L65-003', %s, 'internal', 'Discovery notes', %s,
                           'FACT', 'T2', %s, 'E-L65-001')
                   ON CONFLICT DO NOTHING RETURNING e_id""",
                (entity, PARENT, LABEL))
    assert list(cur.fetchall()) == [], "a retry is the idempotent dedup"


def test_two_unsplit_rows_with_the_same_content_still_collide(db, entity):
    cur = db.cursor()
    cur.execute("""INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, excerpt,
                      claim_type, tier)
                   VALUES ('E-L65-009', %s, 'internal', 'Discovery notes', %s,
                           'FACT', 'T2')
                   ON CONFLICT DO NOTHING RETURNING e_id""", (entity, PARENT))
    assert list(cur.fetchall()) == []


@pytest.mark.parametrize("excerpt", [
    PARENT + " And more besides.",                              # longer
    "The member said nothing of the kind about the branches or the call "
    "centre at all.",                                           # reworded
])
def test_a_span_that_is_not_a_verbatim_piece_is_refused(db, entity, excerpt):
    with pytest.raises(pg8000.DatabaseError):
        _span(db, entity, "E-L65-004", excerpt)
    db.rollback()


def test_case_and_whitespace_do_not_make_a_span_unverbatim(db, entity):
    got = _span(db, entity, "E-L65-005", "  " + PARENT.upper().replace(" ", "\n "))
    assert got and got[0][0] is not None


def test_an_attribution_is_still_fixed_at_mint(db, entity):
    _span(db, entity, "E-L65-002", PARENT)
    for sql in ("UPDATE evidence_index SET customer_attribution = 'x' "
                "WHERE e_id = 'E-L65-001'",
                "UPDATE evidence_index SET customer_attribution = NULL "
                "WHERE e_id = 'E-L65-002'",
                "UPDATE evidence_index SET split_of = NULL "
                "WHERE e_id = 'E-L65-002'"):
        cur = db.cursor()
        cur.execute("SAVEPOINT s")
        with pytest.raises(pg8000.DatabaseError):
            cur.execute(sql)
        cur.execute("ROLLBACK TO SAVEPOINT s")
