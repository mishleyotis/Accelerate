"""Stage 2.4 pass-2 QA bullets:

- A grain mismatch fails and the verdict names both figures and the path.
- A foreign id halts with the contamination message; an invented mint id
  is named as fabrication.
- Band words resolve from the RAW score; the fifth band cannot appear.
- grounded_on is the length of the citation list; ranked claims carry
  their r_layer verdict.
- V4 abstains to a RECORDED NOT_RUN rather than failing closed, and a
  failing SG discloses without blocking the submission.
"""
import hashlib
import math
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "worker"))

import pg8000.dbapi

from dma_mcp.submit import submit_page_payload
from dma_worker.embed import embed_run
from dma_worker.persist import persist_package
from dma_worker.workbook_parser import ParsedScore, WorkbookParse

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


class StubEncoder:
    name = "stub-encoder-384"

    def encode(self, texts):
        out = []
        for t in texts:
            h = hashlib.sha256(t.encode()).digest()
            raw = [(h[i % 32] + i) % 97 - 48 for i in range(384)]
            n = math.sqrt(sum(x * x for x in raw)) or 1.0
            out.append([x / n for x in raw])
        return out


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


ENV = {"produced_at": "2026-08-04T12:00:00Z", "producer_version": "test@1",
       "e_ids": [], "internal_only": []}

MANIFEST = {"run_id": "DMA-ASM-SVB-20260801-01",
            "institution": {"name": "Synthetic Validation Bank"},
            "versions": {"taxonomy": "v7.0"},
            "assessment": {"date": "2026-08-01"},
            "scores": {"overall": 2.1}}

GRAINS = {"pillars": [{"pillar_id": "P1", "name": "Strategy", "score": 2.1,
                       "weight": 0.2, "peer_median": 3.1,
                       "source_cell": "Pillar_Summary!C2"}],
          "categories": []}

EXCERPT = ("The annual report describes a board-approved digital strategy "
           "with tracked KPIs and quarterly refresh checkpoints in place.")


@pytest.fixture()
def seeded():
    try:
        worker = _connect("dmai-worker@digital-maturity-assessor.iam")
        mcp = _connect("dmai-mcp@digital-maturity-assessor.iam")
        admin = _connect("dmai-migrate@digital-maturity-assessor.iam")
    except Exception:
        pytest.skip("no migrated local database")

    def clean():
        cur = admin.cursor()
        for slug in ("synthetic-validation-bank", "synthetic-foreign-bank"):
            cur.execute("SELECT id FROM entities WHERE display_id = %s", (slug,))
            for (eid,) in cur.fetchall():
                for sql in (
                    "DELETE FROM gate_results WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM bundle_centroids WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM bundle_embeddings WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM submission_verdicts WHERE submission_id IN (SELECT id FROM submissions WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s))",
                    "DELETE FROM submissions WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM evidence_subcap_links WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM parser_observations WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM subcap_scores WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM run_manifest WHERE run_id IN (SELECT id FROM runs WHERE entity_id = %s)",
                    "DELETE FROM runs WHERE entity_id = %s",
                    "DELETE FROM evidence_index WHERE entity_id = %s",
                    "DELETE FROM entities WHERE id = %s",
                ):
                    cur.execute(sql, (eid,))
        admin.commit()

    clean()
    wb = WorkbookParse(
        scores=[ParsedScore(subcap_id="P1C1.1.1", pillar_id="P1",
                            category_id="P1C1", capability_id="P1C1.1",
                            name=None, tier=None, score=Decimal("2.97"),
                            source_cell="P1!D2", evidence_quality=None,
                            confidence="HIGH", evidence_refs=["E-001"],
                            rationale="E-001 confirms the strategy exists "
                                      "with KPIs tracked at board level.")],
        observations=[], toggled_out=[], scored_cells=1)
    evidence = [{"e_id": "E-001", "source_name": "AR",
                 "source_url": "https://svb.example/ar", "excerpt": EXCERPT,
                 "tier": None, "ers": None, "published_date": "2025-12-31",
                 "subcaps": ["P1C1.1.1"]}]
    res = persist_package(worker, manifest=MANIFEST, workbook=wb,
                          source_folder_id="synthetic", evidence=evidence,
                          grains=GRAINS)
    # a second entity whose evidence row is FOREIGN to the first
    cur = admin.cursor()
    cur.execute("""INSERT INTO entities (display_id, status, created_at)
                   VALUES ('synthetic-foreign-bank','ACTIVE', now()) RETURNING id""")
    fid = cur.fetchone()[0]
    cur.execute("""INSERT INTO evidence_index (e_id, entity_id, origin, excerpt)
                   VALUES ('E-FRB-200', %s, 'package',
                           'A different institution entirely, with its own long excerpt.')""",
                (fid,))
    admin.commit()
    yield mcp, worker, res
    mcp.rollback()
    clean()
    for c in (worker, mcp, admin):
        c.close()


def _page(**overrides):
    scores = {**ENV, "e_ids": ["E-001"],
              "composite": 2.1,
              "pillars": [{"pillar_id": "P1", "score": 2.1, "peer_median": 3.1,
                           "delta": -1.0, "peer_n": 5, "peer_basis": "table",
                           "proxy_disclosure": None}],
              "posture": "LAGGING", "posture_basis": "EVIDENCE",
              "framing": ("Early digital maturity with strategy work under "
                          "way across the group and clear peer gaps."),
              "claim_label": "FACT", "confidence": "HIGH",
              "narrative_thread": "Thread " + " ".join(["thread"] * 49)}
    scores.update(overrides)
    return scores


def test_grain_lock_names_both_figures(seeded):
    mcp, _, res = seeded
    payload = {"scores": _page(pillars=[{"pillar_id": "P1", "score": 2.34,
                                         "peer_median": 3.1, "delta": -0.76,
                                         "peer_n": 5, "peer_basis": "table",
                                         "proxy_disclosure": None}])}
    r = submit_page_payload(mcp, res.run_id, "overview", payload,
                            producer_version="test@1")
    cg = [x for x in r["verdict"]["reasons"] if x["gate_id"] == "CG-07"]
    assert cg and "2.34" in cg[0]["message"] and "2.1" in cg[0]["message"]
    assert "pillars[0].score" in cg[0]["path"]


def test_foreign_halts_and_fabricated_mint_is_named(seeded):
    mcp, _, res = seeded
    payload = {"scores": _page(e_ids=["E-001", "E-FRB-200", "E-CC-999"])}
    r = submit_page_payload(mcp, res.run_id, "overview", payload,
                            producer_version="test@1")
    gates = {x["gate_id"]: x for x in r["verdict"]["reasons"]}
    assert "contamination" in gates["ET-01"]["message"]
    assert "fabrication" in gates["ET-02"]["message"]
    assert r["verdict"]["status"] == "fail"


def test_band_words_resolve_from_raw_and_no_fifth_band(seeded):
    mcp, _, res = seeded
    payload = {"scores": _page(
        band="Competing",            # 2.97 raw -> Building; 3.0 display lies
        score=2.97,
        maturity_label="Transformational")}
    r = submit_page_payload(mcp, res.run_id, "overview", payload,
                            producer_version="test@1")
    msgs = [x["message"] for x in r["verdict"]["reasons"] if x["gate_id"] == "CG-08"]
    assert any("does not render" in m for m in msgs)              # M5 hex path
    assert any("2.97" in m and "'Building'" in m for m in msgs)   # raw resolve


def test_grounded_on_is_computed_and_ranked_claims_need_r_layer(seeded):
    mcp, _, res = seeded
    payload = {
        "scores": _page(),
        "findings": {**ENV, "e_ids": ["E-001"], "grounded_on": 3,
                     "items": [{"f_id": "F-1", "title": "Gap in strategy",
                                "rank": 1}]},
    }
    r = submit_page_payload(mcp, res.run_id, "overview", payload,
                            producer_version="test@1")
    gates = {x["gate_id"] for x in r["verdict"]["reasons"]}
    assert "AG-02" in gates and "AG-01" in gates


def test_v4_abstains_recorded_then_discloses_without_blocking(seeded):
    mcp, worker, res = seeded
    # no encoder -> NOT_RUN recorded, submission unaffected
    r0 = submit_page_payload(mcp, res.run_id, "overview", {"scores": _page()},
                             producer_version="test@1")
    w0 = [w for w in r0["verdict"]["warnings"] if w["result"] == "NOT_RUN"]
    assert w0 and "unavailable" in w0[0]["not_run_reason"]
    cur = mcp.cursor()
    cur.execute("""SELECT enum_label(result), not_run_reason FROM gate_results
                    WHERE run_id = %s ORDER BY id""", (res.run_id,))
    rows = cur.fetchall()
    assert rows and rows[0][0] == "NOT_RUN" and rows[0][1]

    # embed the bundle (few members -> the run centroid still forms), then
    # submit off-bundle prose: V4 discloses, the submission still passes
    embed_run(worker, res.run_id, StubEncoder())
    off = _page(framing=("The tasting menu features truffle courses and a "
                         "wine pairing led by the sommelier's own cellar."))
    r1 = submit_page_payload(mcp, res.run_id, "overview", {"scores": off},
                             producer_version="test@1", encoder=StubEncoder())
    # V4 NEVER blocks: the only blocking reasons are the genuinely missing
    # required sections (a full page supplies them or their empty states)
    assert all(x["gate_id"] == "CG-01" for x in r1["verdict"]["reasons"])
    assert not any(w.get("gate_id") == "SG-V4" and w.get("severity") == "block"
                   for w in r1["verdict"]["warnings"])
    sg = [w for w in r1["verdict"]["warnings"] if w.get("result") == "FAIL"]
    if sg:                                   # member floor may abstain instead
        assert sg[0]["nearest"] and sg[0]["similarity"] < sg[0]["threshold"]
    else:
        assert any(w.get("result") == "NOT_RUN"
                   for w in r1["verdict"]["warnings"])
