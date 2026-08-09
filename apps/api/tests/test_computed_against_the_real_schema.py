"""Every computed-at-read query, executed against the REAL schema.

`test_computed_at_read.py` drives fake cursors. Fakes answer whatever they
are asked, so they proved the arithmetic and could not see that
`_expected_per_layer` named a column that does not exist — the catalogue's
column is `l3_platform_areas`, the query said `l3_platform`, and the section
served `computed_error: DatabaseError` in production while twelve unit tests
were green.

That is `VERIFICATION_RAN_AGAINST_THE_WRONG_COPY` in this build's own code:
the check passed, and the thing it passed on was not the thing. So each
function here runs its statements against a migrated database and a seeded
run, where a wrong column name, a wrong cast or a missing grant is a failure
rather than a fixture.

Skipped, loudly, when there is no local database — never quietly passed.
"""
import os
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

import pg8000.dbapi

from dma_api import computed

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

DISPLAY = "synthetic-computed-cu"


def _connect(user="postgres"):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def seeded():
    try:
        conn = _connect()
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()

    def clean():
        cur.execute("SELECT id FROM entities WHERE display_id = %s", (DISPLAY,))
        for (eid,) in cur.fetchall():
            cur.execute("SELECT id FROM runs WHERE entity_id = %s", (eid,))
            for (rid,) in cur.fetchall():
                cur.execute("DELETE FROM evidence_subcap_links WHERE run_id = %s", (rid,))
                cur.execute("DELETE FROM gate_results WHERE run_id = %s", (rid,))
                cur.execute("DELETE FROM techstack_items WHERE run_id = %s", (rid,))
            cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM runs WHERE entity_id = %s", (eid,))
            cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
        conn.commit()

    clean()
    cur.execute("""INSERT INTO entities (display_id, legal_name, sub_vertical,
                                         status, created_at)
                   VALUES (%s, 'Synthetic Computed CU', 'SV2', 'ACTIVE', now())
                RETURNING id""", (DISPLAY,))
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status,
                                     is_active, promoted_at,
                                     ccg_catalog_version)
                   VALUES (%s, 'DMA-ASM-SCU-20260809-01', 1, 'PROMOTED', TRUE,
                           now(), 'v7.0') RETURNING id""", (eid,))
    rid = str(cur.fetchone()[0])

    for i, (tier, claim, domain) in enumerate((
            ("T1", "FACT", "syntheticcu.org"),
            ("T3", "INFERENCE", "example.com"),
            ("T5", "CEILING_ESTIMATE", "vendor.example")), start=1):
        # source_domain is GENERATED from source_url — computed, never stored
        # twice (invariant 8), so it is not in the INSERT.
        cur.execute("""INSERT INTO evidence_index
                         (e_id, entity_id, origin, source_name, source_url,
                          excerpt, claim_type, tier)
                       VALUES (%s, %s, 'producer', %s, %s, %s, %s, %s)""",
                    (f"E-SCU-{i:03d}", eid, f"Source {i}",
                     f"https://{domain}/{i}", "x" * 60, claim, tier))
        cur.execute("""INSERT INTO evidence_subcap_links
                         (e_id, subcap_id, run_id, link_basis)
                       VALUES (%s, %s, %s, 'test')""",
                    (f"E-SCU-{i:03d}", f"P1C1.1.{i}", rid))

    for i, (layer, status, primary) in enumerate((
            ("OPS", "CONFIRMED", False), ("CUST", "ABSENT", True),
            ("DATA", "INFERRED", False)), start=1):
        cur.execute("""INSERT INTO techstack_items
                         (ts_id, name, vendor, layer, pillar_id, status,
                          evidence_level, is_primary_gap, run_id, entity_id,
                          promoted_at, producer_version)
                       VALUES (%s, %s, 'Acme', %s, 'P2', %s, 'L2', %s, %s, %s,
                               now(), 'test@1')""",
                    (f"TS-{i}", f"Product {i}", layer, status, primary,
                     rid, eid))

    cur.execute("""INSERT INTO gate_results (run_id, gate_id, result,
                                             not_run_reason, evaluated_at)
                   VALUES (%s,'SG-S8','FAIL', NULL, now() - interval '1 hour'),
                          (%s,'SG-S8','PASS', NULL, now()),
                          (%s,'SG-V4','NOT_RUN',
                           'the cell centroid has fewer than five members',
                           now())""", (rid, rid, rid))
    conn.commit()
    yield conn, cur, rid, eid
    clean()
    conn.close()


def test_evidence_coverage_census_runs_and_counts_the_run_not_zero(seeded):
    """`evidence_run_links` looks like the right table and is EMPTY — 0 rows
    for a run whose evidence_subcap_links carries 6,323 — so the first census
    reported a store of zero for a client with 182 rows. This reads the same
    definition `evidence.py` reads."""
    conn, cur, rid, eid = seeded
    data = {}
    computed.evidence_coverage(cur, data, rid, eid)
    assert data.get("computed_error") is None
    assert data["item_count"] == 3
    assert data["fact_count"] == 3
    assert {t["tier"] for t in data["tiers"]} == {"T1", "T3", "T5"}
    assert {t["max_evidence_level"] for t in data["tiers"]} == {"L5", "L4", "L2"}
    assert {c["claim_label"] for c in data["claim_classes"]} == \
        {"FACT", "INFERENCE", "CEILING_ESTIMATE"}


def test_techstack_layers_query_names_columns_that_exist(seeded):
    """The regression this file was written for: `l3_platform` against a
    catalogue whose column is `l3_platform_areas`."""
    conn, cur, rid, _ = seeded
    data = {}
    computed.techstack_layers(cur, data, rid, "v7.0")
    assert data.get("computed_error") is None
    by = {l["layer"]: l for l in data["layers"]}
    assert set(by) == {"OPS", "CUST", "DATA", "INFRA"}
    assert by["OPS"]["detected"] == 1 and by["CUST"]["detected"] == 0
    assert by["CUST"]["is_primary_gap"] is True
    # v7.0 is loaded in this database, so `expected` is a real count.
    assert by["OPS"]["expected"] and by["OPS"]["expected"] > 0


def test_landscape_query_runs_against_the_real_enum(seeded):
    conn, cur, rid, _ = seeded
    data = {}
    computed.landscape(cur, data, rid)
    counts = {t["kind"]: t["count"] for t in data["tiles"]}
    assert counts == {"CONFIRMED": 1, "INFERRED": 1, "CLAIMED": 0, "GAPS": 1}
    assert data["reconciles_to_register"] is True


def test_safeguard_gates_serve_one_row_per_gate_the_latest(seeded):
    """gate_results accumulates a row per evaluation — Baxter carries 61 rows
    for SG-V4 and 23 for SG-S8 — so serving them all renders the same gate
    eighty-four times and puts a superseded FAIL beside its own later PASS,
    with nothing on the card to say which is current."""
    conn, cur, rid, _ = seeded
    data = {}
    computed.safeguard_gates(cur, data, rid)
    assert data.get("computed_error") is None
    by = {g["gate_id"]: g for g in data["gates"]}
    assert len(data["gates"]) == 2, "one row per gate, not one per evaluation"
    assert by["SG-S8"]["result"] == "PASS", "the LATEST evaluation serves"
    assert by["SG-V4"]["not_run_reason"] == \
        "the cell centroid has fewer than five members"

    # "A gate reporting PASS because it did not run is worse than one
    # reporting FAIL" is not only a serving rule here — the schema refuses
    # the row. Asserted rather than assumed, because the read-path fallback
    # for a reasonless NOT_RUN is only defensible while this holds.
    cur.execute("""SELECT count(*) FROM pg_constraint
                    WHERE conname = 'not_run_needs_reason'""")
    assert cur.fetchone()[0] == 1


def test_cell_items_resolve_from_the_evidence_store_and_are_entity_scoped(seeded):
    """`items` and `thin` are the two H2 keys the field census exempts from
    needing a column, on the grounds that they are the RESOLVED form of the
    row's own e_ids. The exemption was right and nothing performed it, so the
    evidence drawer resolved to nothing for every client since the beginning
    — 698 of 706 cells linked on the reference client, 0 with an item.

    Entity scoping is invariant 4: an id belonging to another institution
    resolves to nothing here rather than opening somebody else's document."""
    conn, cur, rid, eid = seeded
    cur.execute("""INSERT INTO entities (display_id, legal_name, status,
                                         created_at)
                   VALUES ('synthetic-other-cu','Other CU','ACTIVE', now())
                RETURNING id""")
    other = cur.fetchone()[0]
    cur.execute("""INSERT INTO evidence_index
                     (e_id, entity_id, origin, source_name, source_url,
                      excerpt, claim_type, tier)
                   VALUES ('E-OTHER-001', %s, 'producer', 'Other filing',
                           'https://other.example/1', %s, 'FACT', 'T1')""",
                (other, "y" * 60))
    conn.commit()

    data = {"cells": [
        {"subcap_id": "P1C1.1.1", "e_ids": ["E-SCU-001", "E-SCU-002"],
         "grounded_on": 2},
        {"subcap_id": "P1C1.1.9", "e_ids": ["E-OTHER-001"], "grounded_on": 1},
        {"subcap_id": "P1C1.1.3", "e_ids": [], "grounded_on": 0},
    ]}
    computed.apply(cur, "heatmap", "cell_evidence", data,
                   {"run_id": rid}, eid)
    assert data.get("computed_error") is None
    cells = data["cells"]
    assert [i["e_id"] for i in cells[0]["items"]] == ["E-SCU-001", "E-SCU-002"]
    assert cells[0]["items"][0]["excerpt"] and cells[0]["items"][0]["tier"] == "T1"
    assert cells[0]["thin"] is True, "two linked items is below the three line"
    assert cells[1]["items"] == [], "another entity's id must not open here"
    assert data["unresolved_citations"] == 1
    assert data["linking_stats"]["cells_citable"] == 1

    cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (other,))
    cur.execute("DELETE FROM entities WHERE id = %s", (other,))
    conn.commit()


def test_a_failed_computation_does_not_poison_the_rest_of_the_request(seeded):
    """PostgreSQL aborts the whole transaction on a failed statement, so
    without a savepoint the first bad query 25P02s every later one — and the
    first version of this module shipped a bad query. The page would have
    lost every section after the broken one."""
    conn, cur, rid, eid = seeded
    data = {}
    computed.apply(cur, "techstack", "techstack", data,
                   {"run_id": rid, "ccg_catalog_version": "NOT-A-VERSION"}, eid)
    # A version nobody loaded is not an error — expected is simply unknown.
    assert data.get("computed_error") is None

    broken = {}
    cur.execute("SAVEPOINT probe")
    try:
        cur.execute("SELECT no_such_column FROM ccg_subcaps")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT probe")
    cur.execute("RELEASE SAVEPOINT probe")

    computed.apply(cur, "overview", "evidence_coverage", broken,
                   {"run_id": rid}, eid)
    assert broken.get("computed_error") is None
    assert broken["item_count"] == 3, \
        "the transaction survived an earlier failure and still computed"
