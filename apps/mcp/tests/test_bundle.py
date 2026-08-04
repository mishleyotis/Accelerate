"""Stage 2.3 QA bullets — the read tools, against a synthetic seeded run:

- Every score in the bundle carries a source cell.
- Stated pillar/category grains are served as stated (names, medians,
  source cells) and capability rollups declare their computed basis.
- Prior runs are returned so a rerun is not synthesised as a first run.
"""
import os
import sys
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "apps" / "worker"))

import pg8000.dbapi

from dma_mcp.bundle import (get_capability_catalogue, get_client_state,
                            get_report_bundle)
from dma_worker.persist import persist_package
from dma_worker.workbook_parser import ParsedScore, WorkbookParse

DSN = os.environ.get("LOCAL_DATABASE_URL", "postgresql://postgres:local@localhost:5432/dma_insights")
HOST = DSN.split("@")[1].split(":")[0] if "@" in DSN else "localhost"


def _connect(user):
    return pg8000.dbapi.connect(user=user, password="local", host=HOST,
                                port=5432, database="dma_insights")


MANIFEST = {"run_id": "DMA-ASM-SBB-20260801-01",
            "institution": {"name": "Synthetic Bundle Bank"},
            "versions": {"taxonomy": "v7.0"},
            "assessment": {"date": "2026-08-01"},
            "scores": {"overall": 2.1}}

GRAINS = {
    "pillars": [{"pillar_id": "P1", "name": "Strategy, Governance & Culture",
                 "score": 2.1, "weight": 0.2, "peer_median": 3.1,
                 "source_cell": "Pillar_Summary!C2"}],
    "categories": [{"category_id": "P1C1", "name": "Digital Strategy & Vision",
                    "pillar_id": "P1", "score": 2.05, "peer_median": 3.5,
                    "priority_score": 7.5, "priority_tier": "HIGH",
                    "source_cell": "Category_Detail!D2"}],
}


def _wb():
    return WorkbookParse(
        scores=[ParsedScore(subcap_id="P1C1.1.1", pillar_id="P1",
                            category_id="P1C1", capability_id="P1C1.1",
                            name=None, tier=None, score=Decimal("2.1"),
                            source_cell="P1_Subcap_Scoring!D2",
                            evidence_quality=None, confidence="HIGH",
                            evidence_refs=["E-001"]),
                ParsedScore(subcap_id="P1C1.1.2", pillar_id="P1",
                            category_id="P1C1", capability_id="P1C1.1",
                            name=None, tier=None, score=Decimal("2.3"),
                            source_cell="P1_Subcap_Scoring!D3",
                            evidence_quality=None, confidence="HIGH")],
        observations=[], toggled_out=[], scored_cells=2)


EVIDENCE = [{"e_id": "E-001", "source_name": "AR",
             "source_url": "https://sbb.example/ar",
             "excerpt": "The annual report names a board-approved digital strategy programme.",
             "tier": None, "ers": None, "published_date": "2025-12-31",
             "subcaps": ["P1C1.1.1"]}]


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
        cur.execute("SELECT id FROM entities WHERE display_id = 'synthetic-bundle-bank'")
        for (eid,) in cur.fetchall():
            for sql in (
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
    r1 = persist_package(worker, manifest=MANIFEST, workbook=_wb(),
                         source_folder_id="synthetic", evidence=EVIDENCE,
                         grains=GRAINS)
    r2 = persist_package(worker, manifest=MANIFEST, workbook=_wb(),
                         source_folder_id="synthetic", evidence=EVIDENCE,
                         grains=GRAINS)
    yield mcp, r1, r2
    mcp.rollback()
    clean()
    for c in (worker, mcp, admin):
        c.close()


def test_bundle_serves_stated_grains_and_source_cells(seeded):
    mcp, _, r2 = seeded
    b = get_report_bundle(mcp, r2.run_id)
    assert len(b["scores"]) == 2
    assert all(s["source_cell"] for s in b["scores"])
    p1 = b["rollups"]["pillars"][0]
    assert (p1["name"], p1["score"], p1["peer_median"], p1["source_cell"]) == \
        ("Strategy, Governance & Culture", 2.1, 3.1, "Pillar_Summary!C2")
    c1 = b["rollups"]["categories"][0]
    assert c1["priority_tier"] == "HIGH" and c1["source_cell"] == "Category_Detail!D2"
    # capabilities declare their computed basis — never mistakable for stated
    cap = b["rollups"]["capabilities"]["P1C1.1"]
    assert cap["basis"] == "computed_mean_of_subcaps" and cap["score"] == 2.2
    # evidence rides with its run-scoped links
    ev = {e["e_id"]: e for e in b["evidence"]}
    assert ev["E-SBB-001"]["linked_subcap_ids"] == ["P1C1.1.1"]


def test_catalogue_pins_the_run_version_with_names(seeded):
    mcp, _, r2 = seeded
    cat = get_capability_catalogue(mcp, r2.run_id)
    assert cat["ccg_catalog_version"] == "v7.0"
    assert len(cat["subcaps"]) == 851
    assert cat["pillars"][0]["name"] == "Strategy, Governance & Culture"
    assert cat["categories"][0]["name"] == "Digital Strategy & Vision"


def test_client_state_returns_prior_runs_newest_first(seeded):
    mcp, r1, r2 = seeded
    st = get_client_state(mcp, "synthetic-bundle-bank")
    assert [r["run_seq"] for r in st["runs"]] == [2, 1]
    assert st["runs"][0]["run_id"] == r2.run_id and st["runs"][1]["run_id"] == r1.run_id
    assert st["served_pages"] == []   # nothing promoted yet — the true state
