"""0062 fills SWBC's entity record, and only where it is empty.

SWBC promoted with legal_name, sub_vertical and size_tier all NULL; 0062
writes the owner's values (fill-only-where-NULL, guarded by display_id) and
refreshes the materialised directory so a reader sees them. These run the
revision's own upgrade()/downgrade() against the local migrated database,
inside a transaction that is rolled back, and skip without one — the
static checks at the top run everywhere.
"""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations" / "versions" / "0062_swbc_entity_record.py"

EXPECTED = {
    "legal_name": "Southwest Business Corporation",
    "trading_name": "SWBC",
    "domain": "swbc.com",
    "sub_vertical": "IB",
    "supplementary_sub_verticals": ["IC", "CL", "RIA"],
    "size_tier": "mid-size",
}
COLS = tuple(EXPECTED)


@pytest.fixture(scope="module")
def m():
    spec = importlib.util.spec_from_file_location("_m0062", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── static: runs with no database ─────────────────────────────────────
def test_the_revision_chain_and_the_owners_values(m):
    assert m.down_revision == "0061" and m.revision == "0062"
    assert m.DISPLAY_ID == "swbc"
    assert {c: v for c, v, _ in m._FILL} == EXPECTED


def test_every_write_is_guarded_and_fill_only():
    src = MIG.read_text()
    up = src.split("def upgrade", 1)[1].split("def downgrade", 1)[0]
    assert "IS NULL" in up and "display_id = :d" in up
    down = src.split("def downgrade", 1)[1]
    # downgrade clears a column only while it still holds what 0062 wrote
    assert "= CAST(:v AS" in down and "display_id = :d" in down
    assert "refresh_serving_directory()" in src


# ── live: the revision's own functions against the real schema ───────
def _engine():
    sa = pytest.importorskip("sqlalchemy")
    url = os.environ.get(
        "LOCAL_DATABASE_URL",
        "postgresql+pg8000://postgres:local@localhost:5432/dma_insights")
    if url.startswith("postgresql://"):
        url = "postgresql+pg8000://" + url[len("postgresql://"):]
    eng = sa.create_engine(url)
    try:
        conn = eng.connect()
    except Exception:
        pytest.skip("no migrated local database")
    has = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns WHERE table_name='entities'"
        " AND column_name='supplementary_sub_verticals'")).scalar()
    if not has:
        conn.close()
        pytest.skip("database not migrated to 0061")
    conn.rollback()                    # end the probe's autobegun transaction
    return sa, conn


@pytest.fixture()
def db():
    sa, conn = _engine()
    tx = conn.begin()
    # Whatever this database already holds for swbc is set aside inside the
    # transaction, so the test owns the row it asserts about.
    conn.execute(sa.text("UPDATE entities SET display_id = display_id || "
                         "'-held' WHERE display_id = 'swbc'"))
    yield sa, conn
    tx.rollback()
    conn.close()


def _apply(m, conn, fn):
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    ctx = MigrationContext.configure(conn)
    with Operations.context(ctx):
        getattr(m, fn)()


def _row(sa, conn):
    r = conn.execute(sa.text(
        f"SELECT {', '.join(COLS)} FROM entities WHERE display_id='swbc'"
    )).fetchone()
    return dict(zip(COLS, r)) if r else None


def test_an_empty_record_is_filled_and_the_directory_sees_it(m, db):
    sa, conn = db
    eid = conn.execute(sa.text(
        "INSERT INTO entities (display_id) VALUES ('swbc') RETURNING id"
    )).scalar()
    conn.execute(sa.text(
        "INSERT INTO runs (entity_id, request_id, run_seq, status, "
        "promoted_at, is_active) VALUES (:e, 'T-0062', 1, 'PROMOTED', now(), "
        "true)"), {"e": eid})
    _apply(m, conn, "upgrade")
    assert _row(sa, conn) == EXPECTED
    d = conn.execute(sa.text(
        "SELECT legal_name, trading_name, sub_vertical, "
        "supplementary_sub_verticals, size_tier FROM serving_directory "
        "WHERE display_id = 'swbc'")).fetchone()
    assert d is not None, "the directory was not refreshed"
    assert tuple(d) == ("Southwest Business Corporation", "SWBC", "IB",
                        ["IC", "CL", "RIA"], "mid-size")


def test_a_value_already_set_is_never_overwritten(m, db):
    sa, conn = db
    conn.execute(sa.text(
        "INSERT INTO entities (display_id, legal_name, size_tier) "
        "VALUES ('swbc', 'SWBC Holdings', 'large')"))
    _apply(m, conn, "upgrade")
    got = _row(sa, conn)
    assert got["legal_name"] == "SWBC Holdings"
    assert got["size_tier"] == "large"
    assert got["trading_name"] == "SWBC" and got["sub_vertical"] == "IB"
    # and a second run changes nothing
    _apply(m, conn, "upgrade")
    assert _row(sa, conn) == got


def test_downgrade_clears_only_what_this_revision_wrote(m, db):
    sa, conn = db
    conn.execute(sa.text("INSERT INTO entities (display_id) VALUES ('swbc')"))
    _apply(m, conn, "upgrade")
    # somebody corrects one value after the fact
    conn.execute(sa.text("UPDATE entities SET domain = 'swbc.example' "
                         "WHERE display_id = 'swbc'"))
    _apply(m, conn, "downgrade")
    got = _row(sa, conn)
    assert got["domain"] == "swbc.example"
    assert all(got[c] is None for c in COLS if c != "domain")


def test_no_swbc_row_means_nothing_changes(m, db):
    sa, conn = db
    before = conn.execute(sa.text("SELECT count(*) FROM entities "
                                  "WHERE legal_name IS NULL")).scalar()
    _apply(m, conn, "upgrade")
    assert conn.execute(sa.text("SELECT count(*) FROM entities "
                                "WHERE legal_name IS NULL")).scalar() == before
