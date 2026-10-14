"""The band reads a raw score kept BESIDE the 2dp display score (MEM-0560;
invariant 6; owner decision A, 2026-10-04).

`overview_scores.band` and `heatmap_workbook_scores.band` were GENERATED
from NUMERIC(4,2) columns, so the band was computed after rounding: SWBC sent
2.0073 and the column held 2.01, and any raw value in [1.995, 2.0),
[2.995, 3.0) or [3.995, 4.0) stored as the next whole number and banded one
tier HIGH.

The owner's adjudication (Backend Schema, authority #1, against invariant 6):
the display columns stay NUMERIC(4,2) exactly as the schema states — never
widened — and an expand-only `*_raw` column carries the unrounded value the
band is generated from. Rows that predate the revision have no raw anywhere;
they are backfilled from the stored 2dp value and MARKED, so their band is
unchanged and nobody mistakes the copy for a raw.

Runs against a migrated database (LOCAL_DATABASE_URL), like the rest of
tests/schema; skips when none is reachable. The migration round-trip runs
the revision's own downgrade/upgrade inside one transaction and rolls it
back, so the database is left exactly as it was found.
"""
import importlib.util
import os
import sys
import types
import uuid
from decimal import Decimal as D
from pathlib import Path

import pytest

pg8000 = pytest.importorskip("pg8000.dbapi")

ROOT = Path(__file__).resolve().parents[2]
MIG = ROOT / "migrations" / "versions" / "0064_composite_raw_beside_the_display_score.py"
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


def _type(db, table, column):
    rows = q(db, """SELECT data_type, numeric_precision, numeric_scale,
                           is_nullable, column_default
                      FROM information_schema.columns
                     WHERE table_schema = 'public' AND table_name = %s
                       AND column_name = %s""", (table, column))
    assert rows, f"{table}.{column} does not exist"
    return tuple(rows[0])


# ── the shape the owner decided ─────────────────────────────────────────
@pytest.mark.parametrize("table,column", [
    ("overview_scores", "composite"),
    ("heatmap_workbook_scores", "score"),
    ("runs", "composite"),
])
def test_the_display_column_stays_numeric_4_2_as_the_schema_states(db, table, column):
    dtype, precision, scale, _, _ = _type(db, table, column)
    assert (dtype, precision, scale) == ("numeric", 4, 2), (
        f"{table}.{column} is {dtype}({precision},{scale}); the Backend Schema "
        "states NUMERIC(4,2) and decision A keeps it — the raw value lives in "
        "its own column, the display column is never widened")


@pytest.mark.parametrize("table,raw", [
    ("overview_scores", "composite_raw"),
    ("heatmap_workbook_scores", "score_raw"),
    ("runs", "composite_raw"),
])
def test_the_raw_column_is_unscaled_and_its_backfill_is_marked(db, table, raw):
    dtype, precision, scale, nullable, _ = _type(db, table, raw)
    assert (dtype, precision, scale, nullable) == ("numeric", None, None, "YES")
    dtype, _, _, nullable, default = _type(db, table, f"{raw}_backfilled")
    assert dtype == "boolean" and nullable == "NO" and "false" in (default or "")


def _gen_expr(db, table):
    return q(db, """SELECT pg_get_expr(d.adbin, d.adrelid)
                      FROM pg_attrdef d
                      JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
                     WHERE d.adrelid = %s::regclass AND a.attname = 'band'""",
             (table,))[0][0]


@pytest.mark.parametrize("table,raw,display", [
    ("overview_scores", "composite_raw", "composite"),
    ("heatmap_workbook_scores", "score_raw", "score"),
])
def test_the_band_is_generated_from_the_raw_value(db, table, raw, display):
    expr = _gen_expr(db, table)
    assert f"COALESCE({raw}, {display})" in expr, expr
    assert expr.count("WHEN") == 4 and "Differentiating" in expr


def test_the_raw_columns_are_granted_in_the_revision(db):
    got = q(db, """SELECT
        has_column_privilege('svc_api', 'overview_scores', 'composite_raw', 'SELECT'),
        has_column_privilege('svc_mcp', 'overview_scores', 'composite_raw', 'INSERT'),
        has_column_privilege('svc_api', 'heatmap_workbook_scores', 'score_raw', 'SELECT'),
        has_column_privilege('svc_mcp', 'heatmap_workbook_scores', 'score_raw', 'INSERT'),
        has_column_privilege('svc_worker', 'runs', 'composite_raw', 'INSERT'),
        has_column_privilege('svc_mcp', 'runs', 'composite_raw', 'SELECT')""")[0]
    assert list(got) == [True] * 6
    # and nothing new reaches the api role on the ingested tier
    assert q(db, "SELECT has_column_privilege('svc_api', 'runs', "
                 "'composite_raw', 'SELECT')")[0][0] is False


# ── behaviour: the band at every boundary window ────────────────────────
def _2dp(v):
    """NUMERIC(4,2) assignment rounds half away from zero."""
    from decimal import ROUND_HALF_UP
    return v.quantize(D("0.01"), rounding=ROUND_HALF_UP)


def _run(db, composite=None, composite_raw=None):
    eid = f"probe-{uuid.uuid4().hex[:8]}"
    q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
    return q(db, """INSERT INTO runs (entity_id, run_seq, status, composite, composite_raw)
                    SELECT id, 1, 'PROMOTED', %s, %s FROM entities WHERE display_id=%s
                    RETURNING id""", (composite, composite_raw, eid))[0][0]


WINDOWS = [(D("1.996"), "Activating"), (D("2.0"), "Building"),
           (D("2.996"), "Building"), (D("3.0"), "Competing"),
           (D("3.996"), "Competing"), (D("4.0"), "Differentiating"),
           (D("1.995"), "Activating"), (D("2.0073"), "Building")]


def test_the_hero_bands_the_raw_composite_and_displays_it_at_2dp(db):
    db.rollback()
    for raw, band in WINDOWS:
        rid = _run(db)
        # what the promote writer does: one payload value into both columns
        q(db, """INSERT INTO overview_scores
                   (run_id, composite, composite_raw, promoted_at, producer_version)
                 VALUES (%s, %s, %s, now(), 'qa')""", (rid, raw, raw))
        comp, kept, got, filled = q(db, """SELECT composite, composite_raw, band,
                                                  composite_raw_backfilled
                                             FROM overview_scores WHERE run_id=%s""",
                                    (rid,))[0]
        assert kept == raw, "the raw value is stored as stated"
        assert comp == _2dp(raw), "the display column rounds as NUMERIC(4,2) does"
        assert got == band, f"raw {raw} (displayed {comp}) banded {got}, not {band}"
        assert filled is False
    db.rollback()


def test_the_grid_bands_the_raw_score_and_keeps_delta_at_2dp(db):
    db.rollback()
    rid = _run(db)
    for i, (raw, _) in enumerate(WINDOWS):
        q(db, """INSERT INTO heatmap_workbook_scores
                   (run_id, subcap_id, score, score_raw, peer_median, promoted_at, producer_version)
                 VALUES (%s, %s, %s, %s, 2.5, now(), 'qa')""", (rid, f"S{i}", raw, raw))
    got = {r[0]: (r[1], r[2], r[3]) for r in q(
        db, """SELECT score_raw, band, score, delta FROM heatmap_workbook_scores
                WHERE run_id=%s""", (rid,))}
    for raw, band in WINDOWS:
        assert got[raw][0] == band, f"{raw} banded {got[raw][0]}"
        assert got[raw][1] == _2dp(raw)
        assert got[raw][2] is not None, "delta is still generated"
    db.rollback()


def test_a_row_written_without_a_raw_bands_as_it_always_did(db):
    """A pre-0064 writer still running during a rolling deploy writes only the
    display column. Its band must be what 0008 gave it, never NULL."""
    db.rollback()
    rid = _run(db)
    q(db, """INSERT INTO overview_scores (run_id, composite, promoted_at, producer_version)
             VALUES (%s, 1.996, now(), 'qa')""", (rid,))
    assert q(db, "SELECT composite, composite_raw, band FROM overview_scores "
                 "WHERE run_id=%s", (rid,))[0] == [D("2.00"), None, "Building"]
    db.rollback()


def test_runs_keeps_the_display_composite_and_the_raw_beside_it(db):
    db.rollback()
    rid = _run(db, composite=D("2.0073"), composite_raw=D("2.0073"))
    assert q(db, "SELECT composite, composite_raw, composite_raw_backfilled "
                 "FROM runs WHERE id=%s", (rid,))[0] == [D("2.01"), D("2.0073"), False]
    db.rollback()


# ── the revision itself: backfill marked, band unchanged, reversible ────
class _Op:
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql):
        self._conn.cursor().execute(sql)


@pytest.fixture(scope="module")
def m():
    prior = sys.modules.get("alembic")
    sys.modules["alembic"] = types.SimpleNamespace(op=None)
    try:
        spec = importlib.util.spec_from_file_location("_m0064", MIG)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if prior is None:
            sys.modules.pop("alembic", None)
        else:
            sys.modules["alembic"] = prior
    return mod


def test_the_revision_chain_and_that_it_never_retypes(m):
    assert (m.revision, m.down_revision) == ("0064", "0063")
    import re
    src = MIG.read_text()
    assert not re.search(r"ALTER\s+COLUMN\s+\w+\s+(SET\s+DATA\s+)?TYPE", src, re.I), (
        "decision A: composite/score are never retyped")


def test_existing_rows_are_backfilled_marked_and_keep_their_band(db, m):
    """Inside ONE transaction: step back to 0063's shape, land legacy rows,
    run the revision's upgrade, check, and roll everything back."""
    db.rollback()
    m.op = _Op(db)
    try:
        m.downgrade()
        assert not q(db, """SELECT 1 FROM information_schema.columns
                             WHERE table_name='overview_scores'
                               AND column_name='composite_raw'""")
        eid = f"probe-{uuid.uuid4().hex[:8]}"
        q(db, "INSERT INTO entities (display_id) VALUES (%s)", (eid,))
        rid = q(db, """INSERT INTO runs (entity_id, run_seq, status, composite)
                       SELECT id, 1, 'PROMOTED', 1.996 FROM entities WHERE display_id=%s
                       RETURNING id""", (eid,))[0][0]
        rid_null = q(db, """INSERT INTO runs (entity_id, run_seq, status)
                            SELECT id, 2, 'SUPERSEDED' FROM entities WHERE display_id=%s
                            RETURNING id""", (eid,))[0][0]
        q(db, """INSERT INTO overview_scores (run_id, composite, promoted_at, producer_version)
                 VALUES (%s, 1.996, now(), 'qa')""", (rid,))
        q(db, """INSERT INTO heatmap_workbook_scores
                   (run_id, subcap_id, score, promoted_at, producer_version)
                 VALUES (%s, 'S1', 3.996, now(), 'qa'), (%s, 'S2', NULL, now(), 'qa')""",
          (rid, rid))
        before_os = q(db, "SELECT band FROM overview_scores WHERE run_id=%s", (rid,))[0][0]
        before_hws = dict(q(db, "SELECT subcap_id, band FROM heatmap_workbook_scores "
                                "WHERE run_id=%s", (rid,)))
        assert before_os == "Building" and before_hws["S1"] == "Differentiating"

        m.upgrade()

        assert q(db, "SELECT composite_raw, composite_raw_backfilled, band "
                     "FROM overview_scores WHERE run_id=%s", (rid,))[0] == \
            [D("2.00"), True, before_os], "backfilled from 2dp, marked, band unchanged"
        hws = {r[0]: r[1:] for r in q(
            db, """SELECT subcap_id, score_raw, score_raw_backfilled, band
                     FROM heatmap_workbook_scores WHERE run_id=%s""", (rid,))}
        assert hws["S1"] == [D("4.00"), True, before_hws["S1"]]
        assert hws["S2"] == [None, False, None], "no value, no backfill, no band"
        assert q(db, "SELECT composite_raw, composite_raw_backfilled FROM runs "
                     "WHERE id=%s", (rid,))[0] == [D("2.00"), True]
        assert q(db, "SELECT composite_raw, composite_raw_backfilled FROM runs "
                     "WHERE id=%s", (rid_null,))[0] == [None, False]

        # A true raw written after the revision is NOT marked, and bands on raw.
        q(db, "UPDATE overview_scores SET composite_raw = 1.996, "
              "composite_raw_backfilled = FALSE WHERE run_id=%s", (rid,))
        assert q(db, "SELECT band FROM overview_scores WHERE run_id=%s",
                 (rid,))[0][0] == "Activating"
    finally:
        db.rollback()
    # the rollback restored the head schema
    assert q(db, """SELECT 1 FROM information_schema.columns
                     WHERE table_name='overview_scores' AND column_name='composite_raw'""")
