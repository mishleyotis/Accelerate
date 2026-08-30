"""Stage 2.3 QA bullets — get_evidence's three-way split, against a real
database. The critical assertion: a foreign id lands in its OWN bucket,
never merged into not_found, and bare package ids resolve within the
run's entity scope only."""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.evidence_tools import get_evidence

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


@pytest.fixture()
def two_entities():
    try:
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    ids = {}
    for slug, req in (("synthetic-ge-a", "DMA-ASM-GEA-20260801-01"),
                      ("synthetic-ge-b", "DMA-ASM-GEB-20260801-01")):
        cur.execute("""INSERT INTO entities (display_id, legal_name, status, created_at)
                       VALUES (%s,%s,'ACTIVE', now()) RETURNING id""", (slug, slug))
        eid = cur.fetchone()[0]
        cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                       VALUES (%s,%s,1,'INGESTED') RETURNING id""", (eid, req))
        ids[slug] = (eid, cur.fetchone()[0])
    # both entities carry a package item numbered 047, stored qualified
    for slug, token in (("synthetic-ge-a", "GEA"), ("synthetic-ge-b", "GEB")):
        cur.execute(
            """INSERT INTO evidence_index (e_id, entity_id, origin, source_name,
                                           excerpt, published_date, reference_date)
               VALUES (%s,%s,'package','AR',
                       %s,'2025-12-31','2026-08-01')""",
            (f"E-{token}-047", ids[slug][0],
             f"Excerpt for {token} long enough to be a verbatim span of evidence."))
        cur.execute(
            """INSERT INTO evidence_subcap_links (e_id, subcap_id, run_id, link_basis)
               VALUES (%s,'P1C1.1.1',%s,'package')""",
            (f"E-{token}-047", ids[slug][1]))
    # a mint row for entity A (stored raw — the server allocated it)
    cur.execute(
        """INSERT INTO evidence_index (e_id, entity_id, origin, source_name, excerpt)
           VALUES ('E-CC-014', %s, 'producer', 'Case study',
                   'A minted enrichment row with a long enough excerpt to count.')""",
        (ids["synthetic-ge-a"][0],))
    admin.commit()
    yield mcp, ids
    mcp.rollback()
    for slug in ids:
        eid, rid = ids[slug]
        cur.execute("DELETE FROM evidence_subcap_links WHERE run_id = %s", (rid,))
        cur.execute("DELETE FROM evidence_index WHERE entity_id = %s", (eid,))
        cur.execute("DELETE FROM runs WHERE id = %s", (rid,))
        cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    admin.commit()
    mcp.close()
    admin.close()


def test_three_way_split_with_entity_scoped_resolution(two_entities):
    mcp, ids = two_entities
    run_a = ids["synthetic-ge-a"][1]

    out = get_evidence(mcp, run_a, ["E-047", "E-CC-014", "E-999", "E-GEB-047"])

    # the bare package id resolves within run A's entity scope only
    found = {f["e_id"]: f for f in out["found"]}
    assert found["E-047"]["stored_id"] == "E-GEA-047"
    assert "GEA" in found["E-047"]["excerpt"]
    assert found["E-047"]["linked_subcap_ids"] == ["P1C1.1.1"]
    # the mint resolves raw
    assert found["E-CC-014"]["origin"] == "producer"
    # fabricated -> not_found
    assert out["not_found"] == ["E-999"]
    # the OTHER entity's stored id is FOREIGN — its own bucket, with owner
    assert len(out["foreign"]) == 1
    assert out["foreign"][0]["e_id"] == "E-GEB-047"
    assert out["foreign"][0]["belongs_to"] == str(ids["synthetic-ge-b"][0])


def test_fact_level_citation_resolves_to_its_item(two_entities):
    mcp, ids = two_entities
    out = get_evidence(mcp, ids["synthetic-ge-a"][1], ["E-047:F1"])
    assert out["found"][0]["e_id"] == "E-047:F1"
    assert out["found"][0]["stored_id"] == "E-GEA-047"
    assert out["not_found"] == [] and out["foreign"] == []
