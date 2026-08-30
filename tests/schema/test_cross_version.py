"""Cross-version catalogue integrity (v5.0 ↔ v7.0).

Most existing DMAs were scored against v5.0 (user, 2026-08-04); their runs
pin to it while new runs pin to the current version. Comparability across
a bump is: same id in both versions → direct; alias row → renamed;
neither → NOT_COMPARABLE, rendered as such and never a silent drop to
zero (Backend Schema §11). These tests activate when both versions are
loaded and skip cleanly otherwise.
"""
import os

import pg8000.dbapi
import pytest

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture(scope="module")
def db():
    host = DSN.split("@")[1].split(":")[0]
    conn = pg8000.dbapi.connect(user="postgres", password="local", host=host,
                                port=5432, database="dma_insights")
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM ccg_subcaps WHERE version = 'v5.0'")
    if cur.fetchone()[0] == 0:
        pytest.skip("v5.0 catalogue not loaded")
    cur.execute("SELECT count(*) FROM ccg_subcaps WHERE version = 'v7.0'")
    if cur.fetchone()[0] == 0:
        pytest.skip("v7.0 catalogue not loaded")
    yield conn
    conn.rollback()
    conn.close()


def q(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def test_current_version_is_v7(db):
    rows = q(db, "SELECT version FROM ccg_versions WHERE is_current")
    assert [r[0] for r in rows] == ["v7.0"], (
        "loading the historical v5.0 must not steal is_current")


def test_v5_has_17_categories(db):
    (n,) = q(db, "SELECT count(DISTINCT category_id) FROM ccg_subcaps WHERE version='v5.0'")[0]
    assert n == 17, "v5.0 carried 17 categories (user-confirmed)"


def test_every_v5_cell_resolves_or_is_explicitly_not_comparable(db):
    rows = q(db, """
        SELECT
          count(*) FILTER (WHERE v7.subcap_id IS NOT NULL)                        AS direct,
          count(*) FILTER (WHERE v7.subcap_id IS NULL AND al.to_subcap_id IS NOT NULL) AS bridged,
          count(*) FILTER (WHERE v7.subcap_id IS NULL AND al.to_subcap_id IS NULL)     AS not_comparable
        FROM ccg_subcaps v5
        LEFT JOIN ccg_subcaps v7
          ON v7.version = 'v7.0' AND v7.subcap_id = v5.subcap_id
        LEFT JOIN ccg_aliases al
          ON al.from_version = 'v5.0' AND al.from_subcap_id = v5.subcap_id
         AND al.to_version = 'v7.0'
        WHERE v5.version = 'v5.0'
        """)
    direct, bridged, not_comparable = rows[0]
    total = direct + bridged + not_comparable
    # Every v5 cell lands in exactly one bucket; the NOT_COMPARABLE set is
    # ALLOWED (a killed category cannot resolve) but must be a known,
    # reported quantity — the run-diff surface renders it as such.
    assert total == q(db, "SELECT count(*) FROM ccg_subcaps WHERE version='v5.0'")[0][0]
    print(f"v5→v7 resolution: {direct} direct, {bridged} bridged, {not_comparable} NOT_COMPARABLE")


def test_bridged_targets_exist_in_v7(db):
    orphans = q(db, """
        SELECT al.from_subcap_id, al.to_subcap_id FROM ccg_aliases al
        WHERE al.from_version = 'v5.0' AND al.to_version = 'v7.0'
          AND NOT EXISTS (SELECT 1 FROM ccg_subcaps s
                          WHERE s.version = 'v7.0' AND s.subcap_id = al.to_subcap_id)
        """)
    assert not orphans, f"alias targets missing from v7.0: {list(orphans)[:5]}"
