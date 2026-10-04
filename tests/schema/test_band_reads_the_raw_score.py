"""The generated band reads the RAW score, not a 2dp copy of it (MEM-0560;
invariant 6).

Invariant 6: four bands, strict less-than, on the RAW score before display
rounding. `overview_scores.composite` and `heatmap_workbook_scores.score`
were NUMERIC(4,2) with `band` GENERATED from the stored — rounded — value,
and `runs.composite` (the directory card's figure) was NUMERIC(4,2) too. So
the raw value was discarded at promotion and the band was computed after
rounding: SWBC's submission sent 2.0073 and the column held 2.01. Both band
Building, so nothing visibly broke; but any raw score in [1.995, 2.0),
[2.995, 3.0) or [3.995, 4.0) stored as the next whole number and banded one
tier HIGH. The producer was then steered to send 2dp "by owner decision",
which made the loss permanent at source.

0064 widens the three columns to unscaled NUMERIC and regenerates `band`
(and `delta`) from them. Display rounding belongs to the one frontend
resolver. Runs against a migrated database (LOCAL_DATABASE_URL), like the
rest of tests/schema; skips when none is reachable.
"""
import os
import uuid
from decimal import Decimal as D

import pytest

pg8000 = pytest.importorskip("pg8000.dbapi")

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql+pg8000://postgres:local@localhost:5432/dma_insights")


def _connect():
    rest = DSN.split("@", 1)[1]
    hostport, _, database = rest.partition("/")
    host, _, port = hostport.partition(":")
    creds = DSN.split("://", 1)[1].split("@", 1)[0]
    user, _, password = creds.partition(":")
    return pg8000.connect(user=user, password=password, host=host,
                          port=int(port or 5432), database=database or "dma_insights")


@pytest.fixture(scope="module")
def db():
    try:
        conn = _connect()
    except Exception as e:                                     # noqa: BLE001
        pytest.skip(f"no migrated local database: {e}")
    yield conn
    conn.rollback()
    conn.close()


def q(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall() if cur.description else None


def _scale(db, table, column):
    rows = q(db, """SELECT numeric_precision, numeric_scale FROM information_schema.columns
                     WHERE table_name = %s AND column_name = %s""", (table, column))
    assert rows, f"{table}.{column} does not exist"
    return rows[0]


@pytest.mark.parametrize("table,column", [
    ("overview_scores", "composite"),
    ("heatmap_workbook_scores", "score"),
    ("runs", "composite"),
])
def test_the_score_columns_keep_the_raw_value(db, table, column):
    precision, scale = _scale(db, table, column)
    assert scale is None and precision is None, (
        f"{table}.{column} is NUMERIC({precision},{scale}) — a scaled column "
        "rounds the raw score before the band is generated (MEM-0560)")


def _run(db):
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    rid = q(db, """INSERT INTO runs (entity_id, run_seq, status, composite)
                   SELECT id, 1, 'PROMOTED', 2.0073 FROM entities WHERE display_id=%s
                   RETURNING id""", (eid,))[0][0]
    return rid


def test_the_workbook_grid_bands_the_raw_score_at_every_window(db):
    """The boundary fixture the golden run cannot exercise: x.996 bands
    BELOW x+1, and x.0 bands at it."""
    db.rollback()
    rid = _run(db)
    vals = [D("1.996"), D("2.0"), D("2.996"), D("3.0"), D("3.996"), D("4.0"),
            D("2.0073")]
    for i, v in enumerate(vals):
        q(db, """INSERT INTO heatmap_workbook_scores
                   (run_id, subcap_id, score, peer_median, promoted_at, producer_version)
                 VALUES (%s, %s, %s, 2.5, now(), 'qa')""", (rid, f"S{i}", v))
    got = {r[0]: (r[1], r[2]) for r in q(
        db, "SELECT score, band, delta FROM heatmap_workbook_scores WHERE run_id=%s", (rid,))}
    assert got[D("1.996")][0] == "Activating"
    assert got[D("2.0")][0] == "Building"
    assert got[D("2.996")][0] == "Building"
    assert got[D("3.0")][0] == "Competing"
    assert got[D("3.996")][0] == "Competing"
    assert got[D("4.0")][0] == "Differentiating"
    assert D("2.0073") in got, "the raw value is stored, not 2.01"
    assert got[D("1.996")][1] is not None, "delta is still generated"
    db.rollback()


def test_the_hero_bands_and_keeps_the_raw_composite(db):
    db.rollback()
    rid = _run(db)
    q(db, """INSERT INTO overview_scores (run_id, composite, promoted_at, producer_version)
             VALUES (%s, 1.996, now(), 'qa')""", (rid,))
    comp, band = q(db, "SELECT composite, band FROM overview_scores WHERE run_id=%s", (rid,))[0]
    assert comp == D("1.996") and band == "Activating", (
        "1.996 stored as 2.00 bands Building — one tier high")
    assert q(db, "SELECT composite FROM runs WHERE id=%s", (rid,))[0][0] == D("2.0073")
    db.rollback()


def test_the_directory_view_survived_the_rebuild_with_its_grants(db):
    rows = q(db, """SELECT has_table_privilege('svc_api', 'serving_directory', 'SELECT'),
                           has_function_privilege('svc_mcp', 'refresh_serving_directory()', 'EXECUTE'),
                           has_function_privilege('svc_worker', 'refresh_serving_directory()', 'EXECUTE')""")
    assert rows[0] == [True, True, True]
    cols = {r[0] for r in q(db, """SELECT attname FROM pg_attribute
                                    WHERE attrelid = 'serving_directory'::regclass
                                      AND attnum > 0""")}
    assert {"composite", "trading_name", "supplementary_sub_verticals"} <= cols
