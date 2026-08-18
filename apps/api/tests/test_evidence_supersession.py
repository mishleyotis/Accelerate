"""A citation of a re-scanned row must open on the row that replaced it.

0043 and `persist.carry_links_across_remint` MOVE an evidence row's cell
links onto its re-mint when a later scan re-lands the same source with better
content. The move is right; what shipped without it was any record that the
move happened. `evidence_index` had no column saying "this row was replaced by
that one", so the relationship between `E-XXX-008` and `E-XXX-008-R2` existed
only as a shared id prefix.

Measured on production 2026-08-09, corpus-wide:

    re-mint families                    5,331
    member rows                        11,440
    bare ids now carrying NO links      4,366

and on the reference client, the moment its context page was resubmitted,
7 of 7 cited ids blocked ET-07 while 7 of 7 had a twin carrying between 6 and
141 links. Not one was a real orphan.

These tests run against the migrated database, not a fake cursor, because the
rule is a SQL function: `resolve_evidence_id()` lives in the database so that
the connector's ET-07 and the API's evidence drawer share ONE implementation.
A fixture-driven test of a SQL function tests the fixture.
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

DSN = os.environ.get("LOCAL_DATABASE_URL", "")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"
ENT = "sup-test"


@pytest.fixture()
def seeded():
    try:
        conn = pg8000.dbapi.connect(user="postgres", password="local", host=HOST,
                                    port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = conn.cursor()
    cur.execute("SELECT to_regprocedure('resolve_evidence_id(text)')")
    if cur.fetchone()[0] is None:
        conn.close()
        pytest.skip("0046 not applied to this database")

    eid, rid = str(uuid.uuid4()), str(uuid.uuid4())

    def clean():
        # Child rows before parents: `runs.entity_id` references `entities`,
        # and a teardown that deletes the entity first aborts every later
        # statement in the transaction rather than cleaning anything.
        cur.execute("DELETE FROM evidence_subcap_links WHERE e_id LIKE 'E-SUP-%'")
        cur.execute("DELETE FROM evidence_index WHERE e_id LIKE 'E-SUP-%'")
        cur.execute("""DELETE FROM runs WHERE entity_id IN
                       (SELECT id FROM entities WHERE display_id LIKE %s)""",
                    (ENT + "%",))
        cur.execute("DELETE FROM entities WHERE display_id LIKE %s", (ENT + "%",))
        conn.commit()

    clean()
    cur.execute("INSERT INTO entities (id, display_id, legal_name) "
                "VALUES (%s, %s, 'Supersession Test CU')", (eid, ENT))
    # The bare row: the first scan. Short excerpt, and after the move it holds
    # no links at all — the state 4,366 corpus rows are in.
    cur.execute(
        """INSERT INTO evidence_index (e_id, entity_id, origin, source_name,
                                       source_url, excerpt, claim_type, tier)
           VALUES ('E-SUP-001', %s, 'package', 'Annual Report',
                   'https://example.org/ar', %s, 'FACT', 'T1')""",
        (eid, "the shorter first-scan excerpt, " + "x" * 40))
    # The re-mint: the second scan, fuller excerpt, and it carries the links.
    cur.execute(
        """INSERT INTO evidence_index (e_id, entity_id, origin, source_name,
                                       source_url, excerpt, claim_type, tier,
                                       superseded_by)
           VALUES ('E-SUP-001-R2', %s, 'package', 'Annual Report',
                   'https://example.org/ar', %s, 'FACT', 'T1', NULL)""",
        (eid, "the fuller second-scan excerpt with the passage intact, "
              + "y" * 60))
    cur.execute("UPDATE evidence_index SET superseded_by = 'E-SUP-001-R2' "
                "WHERE e_id = 'E-SUP-001'")
    # A third row with a successor that carries NO links: a real orphan, and
    # the negative control for the resolver moving too eagerly.
    cur.execute(
        """INSERT INTO evidence_index (e_id, entity_id, origin, source_name,
                                       excerpt, claim_type, tier, superseded_by)
           VALUES ('E-SUP-009', %s, 'package', 'Orphan Source',
                   %s, 'FACT', 'T3', 'E-SUP-009-R2')""",
        (eid, "an excerpt nobody linked, " + "z" * 40))
    cur.execute(
        """INSERT INTO evidence_index (e_id, entity_id, origin, source_name,
                                       excerpt, claim_type, tier)
           VALUES ('E-SUP-009-R2', %s, 'package', 'Orphan Source',
                   %s, 'FACT', 'T3')""",
        (eid, "a re-scan of a source nothing links, " + "z" * 40))
    cur.execute("INSERT INTO runs (id, entity_id) VALUES (%s, %s)", (rid, eid))
    for sub in ("P1C1.1.1", "P1C1.1.2", "P1C1.1.3"):
        cur.execute(
            """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id)
               VALUES ('E-SUP-001-R2', %s, %s)""", (sub, rid))
    conn.commit()
    yield conn, cur, eid, rid
    clean()
    conn.close()


def test_the_resolver_moves_a_citation_onto_the_row_that_replaced_it(seeded):
    _, cur, _, _ = seeded
    cur.execute("SELECT resolve_evidence_id('E-SUP-001')")
    assert cur.fetchone()[0] == "E-SUP-001-R2"


def test_a_successor_that_carries_no_links_does_not_capture_the_citation(seeded):
    """The negative control on the resolver's own eagerness. E-SUP-009 was
    superseded, but its successor links nothing, so moving the citation would
    trade one orphan for another while making the drawer LOOK repaired. A
    genuine orphan must still resolve to itself so ET-07 still reports it."""
    _, cur, _, _ = seeded
    cur.execute("SELECT resolve_evidence_id('E-SUP-009')")
    assert cur.fetchone()[0] == "E-SUP-009"


def test_a_current_row_and_an_unknown_id_both_resolve_to_themselves(seeded):
    _, cur, _, _ = seeded
    cur.execute("SELECT resolve_evidence_id('E-SUP-001-R2')")
    assert cur.fetchone()[0] == "E-SUP-001-R2"
    cur.execute("SELECT resolve_evidence_id('E-NOT-REGISTERED')")
    assert cur.fetchone()[0] == "E-NOT-REGISTERED"


def test_the_drawer_opens_on_the_fuller_excerpt_and_says_what_was_cited(seeded):
    """The reader-facing half. Before 0046 this drawer showed the shorter
    first-scan excerpt of a row linked to nothing; the version of the source
    we deliberately stopped using."""
    _, cur, eid, _ = seeded
    data = {"cells": [{"subcap_id": "P1C1.1.1", "e_ids": ["E-SUP-001"]}]}
    computed.cell_items(cur, data, eid)
    item = data["cells"][0]["items"][0]
    assert item["e_id"] == "E-SUP-001-R2"
    assert "fuller second-scan excerpt" in item["excerpt"]
    # The resolution is disclosed, not silent: the payload's id and the row
    # actually shown are both on the surface.
    assert item["cited_as"] == "E-SUP-001"
    assert data.get("unresolved_citations") is None


def test_an_unresolvable_citation_is_still_counted_not_absorbed(seeded):
    _, cur, eid, _ = seeded
    data = {"cells": [{"subcap_id": "P1C1.1.1",
                       "e_ids": ["E-SUP-001", "E-NOT-REGISTERED"]}]}
    computed.cell_items(cur, data, eid)
    assert len(data["cells"][0]["items"]) == 1
    assert data["unresolved_citations"] == 1


def test_resolution_never_crosses_an_entity_boundary(seeded):
    """Invariant 4. A resolved id belonging to another institution must not
    open, however cleanly the pointer resolves."""
    conn, cur, eid, _ = seeded
    other = str(uuid.uuid4())
    cur.execute("INSERT INTO entities (id, display_id, legal_name) "
                "VALUES (%s, 'sup-test-other', 'Another CU')", (other,))
    conn.commit()
    data = {"cells": [{"subcap_id": "P1C1.1.1", "e_ids": ["E-SUP-001"]}]}
    computed.cell_items(cur, data, other)
    assert data["cells"][0]["items"] == []
    assert data["unresolved_citations"] == 1
    cur.execute("DELETE FROM entities WHERE id = %s", (other,))
    conn.commit()
