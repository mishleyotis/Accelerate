"""Unconsumed-artifact knowledge parsers (Part 12.6) — real-fixture tests.

Covers:
  - zennify_opportunities: header-fingerprint match (NOT filename) on
    the real Acuity fixture + variant normalization
  - uncertainty_register: real uncertainty_bands.json →
    runs.uncertainty_bands structured list
  - org_capability: real A9 CSV rows → sections with polarity
  - generic section-miner caps + pattern-gap recording
  - mine_package_knowledge end-to-end on a real fixture package
"""
from __future__ import annotations

from pathlib import Path

from app.services.nlp import patterns
from app.services.parsers.knowledge_artifacts import (
    PackageKnowledge,
    mine_package_knowledge,
    register_all,
)
from app.services.parsers.org_capability import parse_org_capability
from app.services.parsers.uncertainty_register import parse_uncertainty
from app.services.parsers.zennify_opportunities import parse_opportunities

_CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / \
    "dma_packages_batches"

_ACUITY_OPPS = _CORPUS / "batch_14" / "Acuity Insurance - DMA" / \
    "08_appendices" / "A9_zennify_opportunities.csv"
_TRICO_BANDS = _CORPUS / "batch_04" / "Tri Counties Bank - DMA" / \
    "01_evidence" / "uncertainty_bands.json"
_TRUSTCO_ORG = _CORPUS / "batch_08" / "TrustCo Bank - DMA" / \
    "08_appendices" / "A9_org_capability.csv"


class TestZennifyOpportunities:
    def test_real_acuity_fixture_parses(self) -> None:
        assert _ACUITY_OPPS.is_file(), f"fixture moved: {_ACUITY_OPPS}"
        sections = parse_opportunities(_ACUITY_OPPS, "08_appendices/A9_zennify_opportunities.csv")
        assert sections, "canonical A9 fixture must yield opportunity rows"
        first = sections[0]
        assert first["artifact_kind"] == "zennify_opportunity"
        prov = first["provenance"]
        # Canonical row shape present on every provenance dict.
        for key in ("opportunity_id", "opportunity", "priority",
                    "trigger_evidence", "zennify_offering",
                    "pillar_alignment", "entry_point"):
            assert key in prov
        # The Acuity file's first row cites E-047 + P2C1/P4C3.
        assert prov["opportunity_id"] == "OPP-001"
        assert "E-047" in prov["e_ids"]
        assert any(p.startswith("P") for p in prov["pillar_refs"])
        assert "Zennify offering" in first["body"]

    def test_header_fingerprint_matches_not_filename(self, tmp_path) -> None:
        """A drifted FILENAME with the canonical headers must still match
        via the header fingerprint (the mandate: header-fingerprint, not
        filename)."""
        register_all()
        f = tmp_path / "B3_totally_different_name.csv"
        f.write_text(
            "Opportunity_ID,Opportunity,Priority,Trigger_Evidence,"
            "Zennify_Offering,Pillar_Alignment,Entry_Point\n"
            "OPP-001,CRM greenfield,HIGH,E-001,FSC,P2C1,exec sponsor\n"
        )
        key, conf = patterns.match_artifact(
            f,
            headers=["opportunity_id", "opportunity", "priority",
                     "trigger_evidence", "zennify_offering",
                     "pillar_alignment", "entry_point"],
        )
        assert key == "zennify_opportunities"
        assert conf >= 0.99

    def test_solution_variant_normalizes(self, tmp_path) -> None:
        f = tmp_path / "A6_zennify_opportunities.csv"
        f.write_text(
            "Priority,Opportunity,Solution,Evidence,Signal\n"
            "HIGH,Zero integration middleware,MuleSoft,\"E-121,E-134\",CONFIRMED\n"
        )
        sections = parse_opportunities(f)
        assert len(sections) == 1
        prov = sections[0]["provenance"]
        assert prov["zennify_offering"] == "MuleSoft"
        assert prov["trigger_evidence"] == "E-121,E-134"
        assert set(prov["e_ids"]) == {"E-121", "E-134"}
        assert prov["entry_point"] == "CONFIRMED"


class TestUncertaintyRegister:
    def test_real_bands_json(self) -> None:
        assert _TRICO_BANDS.is_file(), f"fixture moved: {_TRICO_BANDS}"
        sections, bands = parse_uncertainty(
            _TRICO_BANDS, "01_evidence/uncertainty_bands.json",
        )
        assert sections and bands
        assert all(s["artifact_kind"] == "uncertainty" for s in sections)
        p1c1 = next(b for b in bands if b["cap_id"] == "P1C1")
        assert p1c1["total"] == 0.3
        assert "note" in p1c1

    def test_register_csv_with_comment_header(self, tmp_path) -> None:
        f = tmp_path / "A5_uncertainty_register.csv"
        f.write_text(
            "# run_id: DMA-RES-TEST-20260101-0001\n"
            "Cap_ID,Evidence_Count,Avg_ERS,Uncertainty_Band,Notes\n"
            "P1C1.1,14,3.93,±0.4,strong coverage\n"
        )
        sections, bands = parse_uncertainty(f)
        assert len(sections) == 1
        assert bands == [{
            "cap_id": "P1C1.1", "band": "±0.4",
            "evidence_count": "14", "note": "strong coverage",
        }]


class TestOrgCapability:
    def test_real_trustco_csv(self) -> None:
        assert _TRUSTCO_ORG.is_file(), f"fixture moved: {_TRUSTCO_ORG}"
        sections = parse_org_capability(
            _TRUSTCO_ORG, "08_appendices/A9_org_capability.csv",
        )
        assert sections
        assert all(s["artifact_kind"] == "org_capability" for s in sections)
        # Polarity classified (positive/neutral/negative) where signal prose
        # exists.
        assert any(
            s["provenance"].get("polarity") in ("positive", "neutral", "negative")
            for s in sections
        )


class TestGenericMinerAndGaps:
    def test_miner_end_to_end_on_real_package(self) -> None:
        root = _CORPUS / "batch_14" / "Acuity Insurance - DMA"
        warnings: list[str] = []
        k = mine_package_knowledge(root, warnings)
        assert isinstance(k, PackageKnowledge)
        kinds = k.stats["sections_by_kind"]
        assert kinds.get("zennify_opportunity", 0) > 0
        assert kinds.get("generic", 0) > 0
        # Every generic-mined shape records a pattern gap + INFO warning.
        assert k.pattern_gaps
        assert all(g["code"] == "PATTERN_GAP" for g in k.pattern_gaps)
        assert any(w.startswith("INFO/pattern_gap:") for w in warnings)
        # Consumed artifacts never double-mine.
        mined_paths = {s["source_path"] for s in k.sections}
        assert not any("evidence_index" in p for p in mined_paths)
        assert not any("export_" in p for p in mined_paths)
        # Every section carries provenance + the source sha256.
        assert all(s.get("provenance") is not None for s in k.sections)
        assert all(s.get("sha256") for s in k.sections)

    def test_per_artifact_cap(self, tmp_path) -> None:
        from app.services.parsers.section_miner import mine_generic
        f = tmp_path / "huge_register.csv"
        f.write_text(
            "col_a,col_b\n"
            + "\n".join(f"value-{i},detail text long enough {i}" for i in range(500))
        )
        sections = mine_generic(f, cap=200)
        assert len(sections) == 200
