"""A connector reading in a package lands as a connector reading.

MEASURED 2026-10-12 (R-INTERAC-20261010). The research engine registered
its Clay Tech Stack and Vibe Prospecting technographic readings with
`Origin = connector` and a source name naming the tool; the ingest wrote
every evidence row as origin 'package' (hardcoded in the INSERT) and never
read the column. `get_evidence` returned E-031/E-035/E-037/E-040 as
`origin: package, connector: null`, and ET-12 — "the register cites no
machine technographic scan" — could never pass for an engine-produced run,
however many scans it ran.

Now both readers carry `origin` and the retrieval time, the INSERT lands a
connector row as 'connector' with its tool, and a re-scan corrects a row an
earlier ingest landed as 'package'. Every other origin is untouched.
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_worker import workbook_parser as WP
from dma_worker.evidence_ids import EvidenceLander

CLAY = "Clay company Tech Stack data point, interac.ca (web-crawl detections), retrieved 2026-10-10"
SPAN = "Imperva, Facebook SDK, SSL by Default, Typekit, CookieYes, React, DocuSign"


def _workbook(tmp_path, origin="connector"):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Evidence_Detail"
    ws.append(["E_ID", "Fact_ID", "Source_Name", "Source_URL", "Tier", "ERS",
               "Date_Published", "Recency", "Claim_Type", "Fact_Count",
               "SubCap_IDs", "Excerpt", "Anchor_Quote", "Retrieved_At",
               "Origin", "Access_Status", "Conflict"])
    ws.append(["E-031", "F1", CLAY, "https://www.interac.ca", "T1", 3.05, None,
               "UNVERIFIED", "INFERENCE", 1, "P4C4.4.4", SPAN, SPAN,
               "2026-10-10T04:13:12Z", origin, "OK", None])
    ws.append(["E-014", "F1", "Interac 2024 Corporate Year in Review",
               "https://www.interac.ca/en/x", "T2", 3.5, "2024", "CURRENT", "FACT",
               1, "P1C2.1.1", "x" * 60, "x" * 60, "2026-10-10T04:13:12Z",
               "public", "OK", None])
    p = tmp_path / "DMA_Scoring_Workbook_x.xlsx"
    wb.save(p)
    return p


def _rows(tmp_path):
    return {r["e_id"]: r for r in WP.parse_evidence_master(str(_workbook(tmp_path)))}


def test_the_workbook_reader_carries_connector_provenance(tmp_path):
    rows = _rows(tmp_path)
    assert rows["E-031"]["origin"] == "connector"
    assert rows["E-031"]["connector_tool"].startswith("Clay company Tech Stack")
    assert rows["E-031"]["connector_retrieved_at"] == datetime(
        2026, 10, 10, 4, 13, 12, tzinfo=timezone.utc)
    assert "origin" not in rows["E-014"]          # a public row is unchanged


def test_the_index_reader_carries_connector_provenance(tmp_path):
    p = tmp_path / "evidence_index.json"
    p.write_text(json.dumps({"items": [
        {"evidence_id": "E-031", "source_name": CLAY, "url": "https://www.interac.ca",
         "tier": "T1", "excerpt": SPAN, "origin": "connector",
         "retrieved_at": "2026-10-10T04:13:12Z"},
        {"evidence_id": "E-001", "source_name": "Intake", "excerpt": "y" * 60,
         "origin": "internal"}]}))
    rows = {r["e_id"]: r for r in WP.parse_evidence_index(str(p))}
    assert rows["E-031"]["origin"] == "connector"
    assert "origin" not in rows["E-001"]          # internal is not this reader's call


def test_the_index_fills_provenance_the_workbook_left_blank():
    wb_rows = [{"e_id": "E-031", "source_name": CLAY, "excerpt": SPAN}]
    ix_rows = [{"e_id": "E-031", "origin": "connector", "connector_tool": CLAY,
                "connector_retrieved_at": None}]
    merged = {r["e_id"]: r for r in WP.merge_evidence_sources(wb_rows, ix_rows)}
    assert merged["E-031"]["origin"] == "connector"


class _Cur:
    """Records every statement; answers the insert as landed."""
    def __init__(self):
        self.calls = []
        self._next = None

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        self._next = ("E-INT-031",) if "INSERT INTO evidence_index" in sql else None

    def fetchone(self):
        return self._next

    def fetchall(self):
        return []


def _lander(cur):
    return EvidenceLander(cur, entity_id="ent", run_id="run", run_seq=1,
                          token="INT", reference_date=None,
                          observe=lambda *a, **k: None)


def _insert(cur):
    return next(p for s, p in cur.calls if s.startswith("INSERT INTO evidence_index"))


def test_a_connector_row_is_inserted_as_connector_with_its_tool(tmp_path):
    cur = _Cur()
    lander = _lander(cur)
    lander._lookup = lambda *a: (None, False)
    lander.land(_rows(tmp_path)["E-031"])
    params = _insert(cur)
    assert params[2] == "connector"
    assert params[-2].startswith("Clay company Tech Stack")
    assert params[-1] is not None


def test_a_package_row_is_inserted_as_package(tmp_path):
    cur = _Cur()
    lander = _lander(cur)
    lander._lookup = lambda *a: (None, False)
    lander.land(_rows(tmp_path)["E-014"])
    params = _insert(cur)
    assert params[2] == "package" and params[-2] is None and params[-1] is None


def test_a_rescan_corrects_a_connector_row_an_earlier_ingest_landed_as_package(tmp_path):
    cur = _Cur()
    lander = _lander(cur)
    lander._lookup = lambda *a: ("E-INT-031", True)     # idempotent re-scan
    lander._map = lambda *a: None
    assert lander.land(_rows(tmp_path)["E-031"]) == "E-INT-031"
    upd = [(s, p) for s, p in cur.calls if s.startswith("UPDATE evidence_index SET origin = 'connector'")]
    assert upd and upd[0][1][-1] == "E-INT-031"
    assert "WHERE e_id = %s AND origin = 'package'" in upd[0][0]


# ── against the real schema (CI runs this; skips without a database) ────

DSN = os.environ.get("LOCAL_DATABASE_URL",
                     "postgresql://postgres:local@localhost:5432/dma_insights")


@pytest.fixture()
def worker_conn():
    pg8000 = pytest.importorskip("pg8000.dbapi")
    host = DSN.split("@")[1].split(":")[0]
    try:
        conn = pg8000.connect(
            user="dmai-worker@digital-maturity-assessor.iam",
            password="local", host=host, port=5432, database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    yield conn
    conn.rollback()
    conn.close()


def test_the_insert_and_the_correction_bind_against_the_schema(worker_conn, tmp_path):
    cur = worker_conn.cursor()
    cur.execute("""INSERT INTO entities (display_id, legal_name)
                   VALUES ('ORIGIN-PROBE','Origin Probe CU') RETURNING id""")
    entity_id = cur.fetchone()[0]
    try:
        ev = _rows(tmp_path)["E-031"]
        lander = EvidenceLander(cur, entity_id=entity_id, run_id=None, run_seq=1,
                                token="OPR", reference_date=None,
                                observe=lambda *a, **k: None)
        stored = lander.land(ev)
        cur.execute("SELECT origin::text, connector_tool FROM evidence_index WHERE e_id=%s",
                    (stored,))
        origin, tool = cur.fetchone()
        assert origin == "connector" and tool.startswith("Clay")
        cur.execute("UPDATE evidence_index SET origin='package', connector_tool=NULL "
                    "WHERE e_id=%s", (stored,))
        lander._correct_origin(stored, ev)
        cur.execute("SELECT origin::text FROM evidence_index WHERE e_id=%s", (stored,))
        assert cur.fetchone()[0] == "connector"
    finally:
        worker_conn.rollback()
