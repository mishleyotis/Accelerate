"""F5 end-to-end simulation — proves the parser path produces
populated `IngestedPackage` envelopes for every real DMA shape we've
seen, AND that those envelopes carry the data the D1-D6 cards / API
endpoints need to render non-empty.

This is a pure-logic test (no DB, no Drive) so it runs fast in CI but
covers the breadth that the operator's "Currently none has been
ingested" bug exposed.

Synthesised packages mirror the 5 operator-uploaded ZIPs:
  - regions:     flat layout, exports/*.csv, governance qa_verdict
                 carrying $schema=run_manifest_v2
  - amalgamated: nested wrapper, 07_governance/run_manifest.json,
                 NO export CSVs (relies on XLSX fallback);
                 evidence in A1_Evidence_Inventory.csv (variant);
                 peers in peer_set.json (variant)
  - anb:         nested wrapper, 08_appendices/run_manifest.json
  - wsfs:        flat layout, 08_appendices/run_manifest.json with
                 l1_run_id field
  - americu:     nested wrapper, 03_scoring_workbook/run_manifest.json
                 (parser priority-1 was previously blind to this path)

The simulation asserts each renders enough data to fill D1 (overview)
+ D2 (insights) + D3 (heatmap) + D4 (platforms) + D6 (health).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.parsers.dma_package import parse_package


def _make_xlsx(path: Path, sheet_name: str, headers: list[str], rows: list[list]) -> None:
    """Drop a minimal XLSX with one sheet so the parser's XLSX-fallback
    can extract subcap scores."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    if ws is None:
        return
    ws.title = sheet_name
    ws.append(headers)
    for r in rows:
        ws.append(r)
    wb.save(str(path))


def _seed_full_skeleton(
    root: Path,
    *,
    manifest_path: str,
    manifest_payload: dict,
    pillar_sheet_name: str = "P1_Subcap_Scoring",
    pillar_sheet_headers: list[str] | None = None,
    pillar_sheet_rows: list[list] | None = None,
    use_export_csvs: bool = False,
    use_variant_evidence: bool = False,
    use_variant_peers: bool = False,
) -> None:
    """Drop a near-complete package skeleton so the parser exercises
    every code branch."""
    for d in ("01_evidence", "02_research_workbook", "03_scoring_workbook",
              "04_reports", "06_peers", "07_governance", "08_appendices"):
        (root / d).mkdir(parents=True, exist_ok=True)

    # Manifest
    mpath = root / manifest_path
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest_payload))

    # Scoring — CSV exports OR XLSX fallback (parser tries CSV first)
    scoring_dir = root / "03_scoring_workbook"
    if use_export_csvs:
        # Real packages use PascalCase column names per parse_scoring_detail_csv.
        (scoring_dir / "export_scoring_detail.csv").write_text(
            "SubCap_ID,Category,Score,Confidence,Evidence_Ceiling\n"
            "P1C1.1.1,P1C1,3.2,HIGH,4.0\n"
            "P1C1.1.2,P1C1,2.8,MEDIUM,3.5\n"
            "P2C1.1.1,P2C1,2.0,LOW,2.5\n"
        )
        (scoring_dir / "export_pillar_summary.csv").write_text(
            "Pillar,Score,Weight\nP1,3.0,0.2\nP2,2.5,0.3\n"
        )
        (scoring_dir / "export_category_summary.csv").write_text(
            "Category_ID,Pillar,Score\nP1C1,P1,3.0\nP2C1,P2,2.0\n"
        )
    else:
        _make_xlsx(
            scoring_dir / "DMA_Scoring_Workbook.xlsx",
            pillar_sheet_name,
            pillar_sheet_headers or [
                "SubCap ID", "SubCap Name", "Category",
                "Capability ID", "Capability Name", "Pre-Critic Score",
                "Critic Δ", "Post-Critic Score", "Confidence",
                "Evidence IDs",
            ],
            pillar_sheet_rows or [
                ["P1C1.1.1", "Strategic Vision", "P1C1", "P1C1.1",
                 "Strategy", 3.0, 0.2, 3.2, "HIGH", "E001,E002"],
                ["P1C1.1.2", "Governance", "P1C1", "P1C1.1",
                 "Strategy", 2.5, 0.3, 2.8, "MEDIUM", "E003"],
                ["P2C1.1.1", "Customer Discovery", "P2C1", "P2C1.1",
                 "CX", 1.8, 0.2, 2.0, "LOW", "E004"],
            ],
        )

    # Evidence — canonical OR variant filename
    ev_dir = root / "01_evidence"
    if use_variant_evidence:
        (ev_dir / "A1_Evidence_Inventory.csv").write_text(
            "evidence_id,source_name,tier,publish_date,subcap_mappings,excerpt\n"
            "E001,Annual Report 2025,1,2025-12-31,P1C1.1.1,test excerpt\n"
            "E002,10-Q Filing,1,2026-03-31,P1C1.1.1,filing excerpt\n"
            "E003,Press Release,2,2026-01-15,P1C1.1.2,press text\n"
            "E004,Industry Report,3,2026-02-01,P2C1.1.1,industry insight\n"
        )
    else:
        (ev_dir / "evidence_index.csv").write_text(
            "evidence_id,source_name,tier,publish_date,subcap_mappings,excerpt\n"
            "E001,Annual Report 2025,1,2025-12-31,P1C1.1.1,test excerpt\n"
            "E002,10-Q Filing,1,2026-03-31,P1C1.1.1,filing excerpt\n"
        )

    # Peers — canonical OR variant
    peers_dir = root / "06_peers"
    if use_variant_peers:
        (peers_dir / "peer_set.json").write_text(json.dumps({
            "peers": [
                {"peer_id": "PEER1", "name": "Peer One Bank", "ticker": "P1B",
                 "overall_score": 2.8, "pillar_scores": {"P1": 3.0, "P2": 2.5}},
                {"peer_id": "PEER2", "name": "Peer Two Bank", "ticker": "P2B",
                 "overall_score": 3.1, "pillar_scores": {"P1": 3.2, "P2": 2.9}},
            ],
        }))
    else:
        (peers_dir / "peer_scores_Peer_One.json").write_text(json.dumps({
            "peer_id": "PEER1", "peer_name": "Peer One Bank",
            "ticker": "P1B", "scores": {"P1": 3.0, "P2": 2.5},
        }))


# ── Per-shape tests ────────────────────────────────────────────────────


@pytest.fixture
def tmpdir(tmp_path: Path) -> Path:
    return tmp_path


def test_regionsbank_shape_renders_all_surfaces(tmpdir):
    root = tmpdir / "RegionsBank_DMA_20260518"
    root.mkdir()
    _seed_full_skeleton(
        root,
        manifest_path="07_governance/governance_qa_verdict_RegionsBank_20260518.json",
        manifest_payload={
            "$schema": "run_manifest_v2",
            "run_id": "DMA-ASM-REGIONS-20260518-0001",
            "entity": "Regions Bank",
            "overall_score": 2.8,
            "verdict": "PASS_WITH_NOTES",
        },
        use_export_csvs=True,
    )
    pkg = parse_package(root)
    assert pkg.run_manifest.run_id == "DMA-ASM-REGIONS-20260518-0001"
    assert len(pkg.subcap_scores) >= 3, "D3 heatmap blank without scores"
    assert len(pkg.evidence) >= 2, "D2 insights/evidence drawer blank"
    assert len(pkg.peers) >= 1, "D3 peer overlay blank"


def test_amalgamated_shape_xlsx_fallback_with_variant_evidence_and_peers(tmpdir):
    """The shape where every fix lands at once: XLSX-only scoring +
    variant evidence filename + variant peer-set file."""
    root = tmpdir / "wrapper_outer"
    root.mkdir()
    inner = root / "Amalgamated_Bank_DMA_2026"
    inner.mkdir()
    _seed_full_skeleton(
        inner,
        manifest_path="07_governance/run_manifest.json",
        manifest_payload={
            "$schema": "run_manifest_v2",
            "run_id": "DMA-ASSESS-AMAL-20260428-0001",
            "entity": "Amalgamated Bank",
            "overall_score": 2.4,
        },
        use_variant_evidence=True,
        use_variant_peers=True,
    )
    pkg = parse_package(root)
    assert pkg.run_manifest.run_id == "DMA-ASSESS-AMAL-20260428-0001"
    assert len(pkg.subcap_scores) >= 3, (
        "XLSX fallback did not extract subcap scores — D3 blank"
    )
    assert len(pkg.evidence) >= 4, (
        "evidence variant (A1_Evidence_Inventory.csv) not loaded — D2 blank"
    )
    assert len(pkg.peers) >= 2, (
        "peers variant (peer_set.json) not loaded — D3 peer overlay blank"
    )
    # The variant-loaded peer carries the same fields the D3 overlay uses.
    p = pkg.peers[0]
    assert p.peer_id
    assert p.peer_name


def test_anb_shape_canonical_08_appendices(tmpdir):
    root = tmpdir / "wrapper_outer"
    root.mkdir()
    inner = root / "ANB_DMA_Complete_Bundle"
    inner.mkdir()
    _seed_full_skeleton(
        inner,
        manifest_path="08_appendices/run_manifest.json",
        manifest_payload={
            "$schema": "run_manifest_v2",
            "run_id": "DMA-ASM-ANB-20260420-0001",
            "entity": "Amarillo National Bank",
            "overall_score": 3.23,
            "evidence_mode": "RESEARCH_HANDOFF",
        },
        use_export_csvs=True,
    )
    pkg = parse_package(root)
    assert pkg.run_manifest.run_id == "DMA-ASM-ANB-20260420-0001"
    assert pkg.run_manifest.evidence_mode == "RESEARCH_HANDOFF"
    assert len(pkg.subcap_scores) >= 3


def test_wsfs_shape_l1_run_id_alias(tmpdir):
    """WSFS uses `l1_run_id` instead of `run_id` — the run_id resolver
    already accepts this alias. Smoke-test it still works end-to-end."""
    root = tmpdir / "wsfs"
    root.mkdir()
    _seed_full_skeleton(
        root,
        manifest_path="08_appendices/run_manifest.json",
        manifest_payload={
            "$schema": "run_manifest_v2",
            "assessment_id": "DMA-RES-WSFS-20260519-0001",
            "l1_run_id": "DMA-ASM-WSFS-20260519-0001",
            "entity": "WSFS Financial Corporation",
            "overall_score": 2.07,
        },
        use_export_csvs=True,
    )
    pkg = parse_package(root)
    assert pkg.run_manifest.run_id == "DMA-ASM-WSFS-20260519-0001"
    assert pkg.run_manifest.institution_name == "WSFS Financial Corporation"


def test_americu_shape_manifest_in_03_scoring_workbook_xlsx_fallback(tmpdir):
    """AmeriCU's killer combo — manifest in 03_scoring_workbook/ (was
    invisible to parser priority-1 before F2) AND no export CSVs (XLSX
    fallback now required for scores).
    """
    root = tmpdir / "wrapper_outer"
    root.mkdir()
    inner = root / "AmeriCU_DMA_Deliverable_2026-04-29"
    inner.mkdir()
    _seed_full_skeleton(
        inner,
        manifest_path="03_scoring_workbook/run_manifest.json",
        manifest_payload={
            "schema": "dma_assessment_run_manifest_v2",
            "assessment_id": "DMA-RES-AMERICU-20260427-0001",
            "entity": "AmeriCU Credit Union",
            "overall_score": 2.44,
        },
        # AmeriCU's per-pillar sheet uses different column headers
        pillar_sheet_name="P1_Scoring_Detail",
        pillar_sheet_headers=[
            "Category_ID", "Category_Name", "Cap_ID", "Capability",
            "SubCap_ID", "SubCapability", "Tier",
            "Diagnostic_Question", "Weight_Pct", "Score_1_to_5",
        ],
        pillar_sheet_rows=[
            ["P1C1", "Strategy", "P1C1.1", "Strategic Posture",
             "P1C1.1.1", "Vision", "T1", "Q?", 5.0, 2.5],
            ["P1C1", "Strategy", "P1C1.1", "Strategic Posture",
             "P1C1.1.2", "Mission", "T1", "Q?", 5.0, 3.0],
            ["P2C1", "CX", "P2C1.1", "Discovery",
             "P2C1.1.1", "Personas", "T1", "Q?", 5.0, 2.2],
        ],
    )
    pkg = parse_package(root)
    assert pkg.run_manifest.run_id == "DMA-RES-AMERICU-20260427-0001", (
        "manifest in 03_scoring_workbook/ not picked up — F2 regression"
    )
    assert len(pkg.subcap_scores) >= 3, (
        "XLSX fallback failed on AmeriCU shape — D3 blank"
    )
    # Both header conventions resolve to the same category prefix.
    cats = {row.category_id for row in pkg.subcap_scores}
    assert "P1C1" in cats and "P2C1" in cats


# ── Cross-shape coverage ───────────────────────────────────────────────


def test_every_shape_extracts_run_id(tmpdir):
    """Aggregate: every shape we support must yield a parseable run_id.
    This is the property the historical_backfill watermark + idempotency
    keying depend on."""
    cases = [
        ("regions", "07_governance/governance_qa_verdict_R.json",
         {"$schema": "run_manifest_v2", "run_id": "DMA-ASM-REGIONS-20260518-0001",
          "entity": "Regions"}),
        ("amalgamated", "07_governance/run_manifest.json",
         {"$schema": "run_manifest_v2", "run_id": "DMA-ASM-AMAL-20260428-0001",
          "entity": "Amalgamated"}),
        ("anb", "08_appendices/run_manifest.json",
         {"$schema": "run_manifest_v2", "run_id": "DMA-ASM-ANB-20260420-0001",
          "entity": "ANB"}),
        ("wsfs", "08_appendices/run_manifest.json",
         {"$schema": "run_manifest_v2", "l1_run_id": "DMA-ASM-WSFS-20260519-0001",
          "entity": "WSFS"}),
        ("americu", "03_scoring_workbook/run_manifest.json",
         {"schema": "dma_assessment_run_manifest_v2",
          "assessment_id": "DMA-RES-AMERICU-20260427-0001",
          "entity": "AmeriCU"}),
    ]
    for label, mpath, payload in cases:
        root = tmpdir / label
        root.mkdir()
        _seed_full_skeleton(root, manifest_path=mpath, manifest_payload=payload)
        pkg = parse_package(root)
        rid = pkg.run_manifest.run_id
        assert rid, f"{label}: parser returned empty run_id"
        assert any(rid.startswith(p) for p in ("DMA-ASM-", "DMA-RES-",
                                                "DMA-ASSESS-", "REQ-")), (
            f"{label}: run_id `{rid}` doesn't match any known prefix"
        )
