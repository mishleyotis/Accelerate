"""Stage 2.4/2.5 QA bullets — pass-1 validation and the submit flow:

- A verdict names the gate, the JSON path and the concrete conflict.
- An explicit empty state passes where a missing required field fails.
- An invented field, a fabricated-looking id and a broken envelope are
  each caught with their own gate.
- Resubmission supersedes cleanly; the verdict is retrievable.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pg8000.dbapi

from dma_mcp.gates import GATES, ensure_gate_registry, explain_gate
from dma_mcp.submit import get_validation_verdict, submit_page_payload
from dma_mcp.validation import validate_pass1

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"

ENVELOPE_OK = {"produced_at": "2026-08-04T12:00:00Z",
               "producer_version": "test@1",
               "e_ids": [], "internal_only": []}


def _min_section(**fields):
    return {**ENVELOPE_OK, **fields}


# ── pure pass-1 checks (no DB) ─────────────────────────────────────────
def test_verdicts_name_gate_path_and_conflict():
    payload = {"techstack": {
        **ENVELOPE_OK,
        "items": "not-a-list",
        "invented_field": 1,
        "empty_state": {"reason": "x"},           # no sources_searched
    }}
    reasons = validate_pass1("techstack", payload)
    by_gate = {r["gate_id"]: r for r in reasons}
    assert by_gate["CG-03"]["path"] == "techstack.items"
    assert "must be list" in by_gate["CG-03"]["message"]
    assert by_gate["CG-04"]["path"] == "techstack.invented_field"
    assert by_gate["CG-06"]["path"] == "techstack.empty_state"
    assert all(r["severity"] == "block" for r in reasons)


def test_explicit_empty_state_passes_where_missing_field_fails():
    bare = {"techstack": _min_section()}                     # items missing
    with_empty = {"techstack": _min_section(
        empty_state={"reason": "no register derivable from the package",
                     "sources_searched": ["profile", "workbook", "research"]})}
    missing = [r for r in validate_pass1("techstack", bare) if r["gate_id"] == "CG-02"]
    assert missing and missing[0]["path"] == "techstack.items"
    assert not [r for r in validate_pass1("techstack", with_empty)
                if r["gate_id"] in ("CG-02", "CG-06")]


def test_envelope_is_required_even_on_empty_states():
    payload = {"techstack": {
        "empty_state": {"reason": "r", "sources_searched": ["a"]}}}
    gates = {r["gate_id"] for r in validate_pass1("techstack", payload)}
    assert "CG-05" in gates


def test_id_pattern_discipline():
    payload = {"techstack": _min_section(
        items=[{"ts_id": "TS-01x", "vendor": "V", "product": "P",
                "layer": "DATA", "status": "CONFIRMED"}],
        e_ids=["E-047", "e-bad"])}
    reasons = validate_pass1("techstack", payload)
    paths = {r["path"] for r in reasons if r["gate_id"] == "ET-03"}
    assert "techstack.e_ids[1]" in paths
    assert "techstack.items[0].ts_id" in paths


def test_unknown_page_and_unknown_section():
    assert validate_pass1("nonsuch", {})[0]["gate_id"] == "CG-01"
    r = validate_pass1("insights", {"landscape": _min_section(tiles=[]),
                                    "insights": _min_section(cards=[]),
                                    "bonus": {}})
    assert [x for x in r if x["gate_id"] == "CG-04" and x["section"] == "bonus"]


# ── the DB flow ────────────────────────────────────────────────────────
@pytest.fixture()
def run_row():
    try:
        mcp = pg8000.dbapi.connect(user="dmai-mcp@digital-maturity-assessor.iam",
                                   password="local", host=HOST, port=5432,
                                   database="dma_insights")
        admin = pg8000.dbapi.connect(user="dmai-migrate@digital-maturity-assessor.iam",
                                     password="local", host=HOST, port=5432,
                                     database="dma_insights")
    except Exception:
        pytest.skip("no migrated local database")
    cur = admin.cursor()
    # pre-clean: an earlier crashed run may have left the entity behind
    cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-submit-bank'")
    for (old,) in cur.fetchall():
        cur.execute("""DELETE FROM gate_results WHERE run_id IN
                         (SELECT id FROM runs WHERE entity_id = %s)""", (old,))
        cur.execute("""DELETE FROM submission_verdicts WHERE submission_id IN
                         (SELECT id FROM submissions WHERE run_id IN
                            (SELECT id FROM runs WHERE entity_id = %s))""", (old,))
        cur.execute("""DELETE FROM submissions WHERE run_id IN
                         (SELECT id FROM runs WHERE entity_id = %s)""", (old,))
        cur.execute("DELETE FROM runs WHERE entity_id = %s", (old,))
        cur.execute("DELETE FROM entities WHERE id = %s", (old,))
    admin.commit()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-submit-bank','ACTIVE', now()) RETURNING id""")
    eid = cur.fetchone()[0]
    cur.execute("""INSERT INTO runs (entity_id, request_id, run_seq, status)
                   VALUES (%s,'DMA-ASM-SSB-20260801-02',1,'INGESTED') RETURNING id""",
                (eid,))
    rid = cur.fetchone()[0]
    admin.commit()
    yield mcp, str(rid)
    mcp.rollback()
    cur.execute("DELETE FROM gate_results WHERE run_id = %s", (rid,))
    cur.execute("""DELETE FROM submission_verdicts WHERE submission_id IN
                     (SELECT id FROM submissions WHERE run_id = %s)""", (rid,))
    cur.execute("DELETE FROM submissions WHERE run_id = %s", (rid,))
    cur.execute("DELETE FROM runs WHERE id = %s", (rid,))
    cur.execute("DELETE FROM entities WHERE id = %s", (eid,))
    admin.commit()
    mcp.close()
    admin.close()


def test_submit_supersedes_and_verdicts_are_retrievable(run_row):
    mcp, rid = run_row
    bad = {"techstack": {**ENVELOPE_OK, "items": "wrong"}}
    r1 = submit_page_payload(mcp, rid, "techstack", bad,
                             producer_version="test@1")
    assert r1["verdict"]["status"] == "fail"
    assert r1["verdict"]["reasons"][0]["gate_id"] == "CG-03"

    good = {"techstack": _min_section(
        items=[], layers=[], dropped=[], compliance_attestations=[],
        empty_state={"reason": "nothing detected yet",
                     "sources_searched": ["profile", "research", "scan"]})}
    r2 = submit_page_payload(mcp, rid, "techstack", good,
                             producer_version="test@1")
    assert r2["verdict"]["status"] == "pass", r2["verdict"]["reasons"]

    # supersession: r1 is marked superseded by r2; r2 is live
    v1 = get_validation_verdict(mcp, r1["submission_id"])
    v2 = get_validation_verdict(mcp, r2["submission_id"])
    assert v1["superseded"] is True and v2["superseded"] is False
    assert v1["verdict"]["reasons"][0]["gate_id"] == "CG-03"

    # no producer_version -> refused before staging
    r3 = submit_page_payload(mcp, rid, "techstack", good, producer_version="")
    assert r3["submission_id"] is None
    assert r3["verdict"]["reasons"][0]["path"] == "producer_version"


def test_gate_registry_seeds_and_explains(run_row):
    mcp, _ = run_row
    assert ensure_gate_registry(mcp) == len(GATES)
    g = explain_gate(mcp, "SG-V4")
    assert g["family"] == "safeguard" and g["is_client_visible"] is True
    assert 8 <= len(g["plain_label"].split()) <= 18
    assert g["on_failure"] == "disclose"
    cg = explain_gate(mcp, "CG-07")
    assert cg["family"] == "corpus" and "0.05" in cg["what_it_checks"]
    assert explain_gate(mcp, "XX-99")["error"] == "unknown_gate"
