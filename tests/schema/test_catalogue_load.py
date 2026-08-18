"""Stage 0.4 QA bullets as tests (Implementation Plan, catalogue load).

These run wherever a catalogue has been loaded (the workbooks live in
GCS, not the repo) and skip cleanly on an empty catalogue — CI covers
them once the migrate Job context can reach the staging bucket.
"""
import os
import re

import pg8000.dbapi
import pytest

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture(scope="module")
def db():
    host = DSN.split("@")[1].split(":")[0]
    conn = pg8000.dbapi.connect(user="postgres", password="local", host=host,
                                port=5432, database="dma_insights")
    cur = conn.cursor()
    cur.execute("SELECT version FROM ccg_versions WHERE is_current")
    row = cur.fetchone()
    if not row:
        pytest.skip("no catalogue loaded")
    yield conn, row[0]
    conn.rollback()
    conn.close()


def q(db, sql, params=()):
    conn, _ = db
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def test_cell_count_is_851_with_pillar_splits(db):
    _, version = db
    rows = dict(q(db, "SELECT pillar_id, count(*) FROM ccg_subcaps WHERE version=%s GROUP BY 1", (version,)))
    assert rows == {"P1": 205, "P2": 292, "P3": 164, "P4": 190}
    assert sum(rows.values()) == 851


def test_every_cell_resolves_to_a_canonical_name(db):
    _, version = db
    (missing,) = q(db, "SELECT count(*) FROM ccg_subcaps WHERE version=%s AND (name IS NULL OR name = '')", (version,))[0]
    assert missing == 0
    # none returns a raw code as its label
    raw = q(db, r"SELECT count(*) FROM ccg_subcaps WHERE version=%s AND name ~ '^P\d+C\d+'", (version,))[0][0]
    assert raw == 0


def test_renamed_cell_resolves_through_alias_bridge_across_simulated_bump(db):
    conn, version = db
    conn.rollback()
    cur = conn.cursor()
    # Simulate a bump: v-test renames one real cell.
    cur.execute("SELECT subcap_id, name FROM ccg_subcaps WHERE version=%s LIMIT 1", (version,))
    old_id, name = cur.fetchone()
    new_id = old_id + ".9"
    cur.execute("INSERT INTO ccg_versions (version, cell_count) VALUES ('v-test', 1)")
    cur.execute(
        "INSERT INTO ccg_subcaps (subcap_id, version, name, pillar_id, category_id) VALUES (%s,'v-test',%s,'P1','P1C1')",
        (new_id, name))
    cur.execute(
        "INSERT INTO ccg_aliases (from_subcap_id, from_version, to_subcap_id, to_version, reason) VALUES (%s,%s,%s,'v-test','renamed')",
        (old_id, version, new_id))
    # The lineage resolution query (Backend Schema §11): the old id resolves.
    cur.execute(
        """SELECT al.to_subcap_id, s.name
           FROM ccg_aliases al JOIN ccg_subcaps s
             ON s.subcap_id = al.to_subcap_id AND s.version = al.to_version
           WHERE al.from_subcap_id = %s AND al.from_version = %s AND al.to_version = 'v-test'""",
        (old_id, version))
    try:
        resolved = cur.fetchone()
        assert list(resolved) == [new_id, name]
    finally:
        conn.rollback()


def test_every_value_chain_stage_maps_to_at_least_one_cell(db):
    _, version = db
    orphans = q(db, """
        SELECT vc.sub_vertical, vc.name FROM ccg_value_chains vc
        WHERE vc.version = %s AND NOT EXISTS (
          SELECT 1 FROM ccg_vc_mapping m
          WHERE m.version = vc.version
            AND m.subvertical_code = vc.sub_vertical
            AND vc.name = ANY (m.value_chain_stages))
        """, (version,))
    assert not orphans, f"unmapped stages: {list(orphans)[:5]}"


def test_variant_cells_loaded(db):
    _, version = db
    (variants,) = q(db, r"SELECT count(*) FROM ccg_subcaps WHERE version=%s AND subcap_id ~ '\.[A-Z]+\d+$'", (version,))[0]
    assert variants > 0, "sub-vertical variant cells (T2) must load"
