"""Part 9 TechStack workstream — parse-time taxonomy sanitation, the
clean_techstack heal plan, honest 4-state status derivation, real `since`
mining, ABSENT gap-row generation, and the L1-L5 layer ladder.

The sanitation cases are the AUDIT'S REAL NOISE CELLS (verbatim from the
seeded corpus): the 7-language cell, the '22 BI/analytics tools…' prose
blob, the person row ('Archana Deskus (ex-PayPal CTO)…'), the bare date
'2026-03-24', and 'Various'.
"""
from __future__ import annotations

from app.schemas.package import TechStackRow
from app.scripts.clean_techstack import normalize_stored_status, plan_heal
from app.services.parsers.package_techstack import (
    STATUS_ENGINEERING_SIGNAL,
    STATUS_UNKNOWN_VENDOR,
    sanitize_tech_rows,
)
from app.services.parsers.tech_linker import absent_families
from app.services.techstack_read import (
    absent_gap_row,
    compose_note,
    derive_since,
    derive_status,
    dominant_pillar,
    gap_zones_for,
    layer_ladder_fields,
)


def _row(vendor: str, product: str | None = None, status: str = "DETECTED",
         source: str = "Explorium") -> TechStackRow:
    return TechStackRow(vendor=vendor, product=product or vendor,
                        source=source, status=status)


class TestSanitizeAuditNoiseCells:
    def test_seven_language_cell_becomes_engineering_signals(self) -> None:
        out = sanitize_tech_rows(
            [_row("Angular, React, Java, Python, NodeJS, PHP, .NET")],
        )
        assert len(out) == 7
        assert all(r.status == STATUS_ENGINEERING_SIGNAL for r in out)
        assert {r.vendor for r in out} == {
            "Angular", "React", "Java", "Python", "NodeJS", "PHP", ".NET",
        }

    def test_prose_blob_is_dropped_with_degraded_warning(self) -> None:
        warnings: list[str] = []
        out = sanitize_tech_rows(
            [_row("22 BI/analytics tools confirmed: Adobe Analytics,")],
            warnings=warnings,
        )
        assert out == []
        assert len(warnings) == 1
        assert warnings[0].startswith("DEGRADED:techstack_noise_dropped")

    def test_person_row_is_noise(self) -> None:
        out = sanitize_tech_rows(
            [_row("Archana Deskus (ex-PayPal CTO) on Board Risk Overs")],
        )
        assert out == []

    def test_bare_date_is_noise(self) -> None:
        assert sanitize_tech_rows([_row("2026-03-24")]) == []

    def test_generic_label_various_is_noise(self) -> None:
        assert sanitize_tech_rows([_row("Various")]) == []

    def test_ncino_is_platform_canonical(self) -> None:
        out = sanitize_tech_rows([_row("nCino", status="CONFIRMED")])
        assert len(out) == 1
        r = out[0]
        assert r.vendor == "nCino"
        assert r.layer == "application"
        assert r.l3_id == "ncino"
        assert r.status == "CONFIRMED"  # deployment status preserved

    def test_parenthetical_stripped_to_canonical(self) -> None:
        out = sanitize_tech_rows([_row("Salesforce (FSC since 2021)")])
        assert [r.vendor for r in out] == ["Salesforce"]
        assert out[0].l3_id == "salesforce"

    def test_multi_vendor_cell_keeps_catalogue_platforms(self) -> None:
        out = sanitize_tech_rows([_row("MuleSoft, TIBCO, RabbitMQ")])
        # MuleSoft resolves canonical; the co-listed off-catalogue names are
        # treated as qualifiers of the cell, not separate review rows.
        assert [r.product for r in out] == ["MuleSoft"]
        assert out[0].vendor == "Salesforce"  # taxonomy vendor for MuleSoft

    def test_vendor_product_pair_prefers_specific_product(self) -> None:
        out = sanitize_tech_rows([_row("Salesforce", product="Marketing Cloud")])
        assert len(out) == 1
        assert out[0].vendor == "Salesforce"
        assert out[0].product == "Marketing Cloud"

    def test_multi_platform_cell_keeps_both(self) -> None:
        out = sanitize_tech_rows([_row("Salesforce, Tableau")])
        assert {r.product for r in out} == {"Salesforce", "Tableau"}

    def test_unknown_vendor_is_flagged_not_dropped(self) -> None:
        out = sanitize_tech_rows([_row("Acme Widgets Core")])
        assert len(out) == 1
        assert out[0].status == STATUS_UNKNOWN_VENDOR

    def test_alias_resolves_canonical(self) -> None:
        out = sanitize_tech_rows([_row("Amazon Web Services (AWS)")])
        assert len(out) == 1
        assert out[0].product == "AWS"
        assert out[0].layer == "platform"

    def test_idempotent_on_canonical_rows(self) -> None:
        first = sanitize_tech_rows([_row("nCino", status="CONFIRMED")])
        second = sanitize_tech_rows(first)
        assert [(r.vendor, r.product, r.status) for r in second] == \
            [(r.vendor, r.product, r.status) for r in first]


class TestHealPlan:
    def test_noise_row_plans_delete(self) -> None:
        assert plan_heal(vendor="Various", product="Various",
                         status="active", source="Explorium",
                         has_evidence=False) == []

    def test_language_row_plans_engineering_flag(self) -> None:
        out = plan_heal(vendor="React", product="React", status="DETECTED",
                        source="tech_stack_explorium.csv", has_evidence=False)
        assert [r.status for r in out] == [STATUS_ENGINEERING_SIGNAL]

    def test_legacy_active_normalises_before_classification(self) -> None:
        out = plan_heal(vendor="Salesforce", product="Salesforce",
                        status="active", source="report", has_evidence=True)
        assert len(out) == 1
        assert out[0].status == "CONFIRMED"

    def test_multi_cell_plans_replacement_rows(self) -> None:
        out = plan_heal(vendor="Angular, React, Java", product=None,
                        status="DETECTED", source="Explorium",
                        has_evidence=False)
        assert len(out) == 3
        assert all(r.status == STATUS_ENGINEERING_SIGNAL for r in out)

    def test_normalize_stored_status(self) -> None:
        assert normalize_stored_status("active", True) == "CONFIRMED"
        assert normalize_stored_status("active", False) == "DETECTED"
        assert normalize_stored_status("CONFIRMED_REMOVED", False) == "CONFIRMED_REMOVED"
        assert normalize_stored_status(STATUS_UNKNOWN_VENDOR, True) == STATUS_UNKNOWN_VENDOR


class TestDeriveStatus:
    def test_confirmed_passthrough(self) -> None:
        assert derive_status("CONFIRMED", []) == "CONFIRMED"

    def test_removed_passthrough(self) -> None:
        assert derive_status("CONFIRMED_REMOVED", [1]) == "CONFIRMED_REMOVED"

    def test_detected_with_t1_t3_evidence_confirms(self) -> None:
        assert derive_status("DETECTED", [2, 5]) == "CONFIRMED"

    def test_detected_with_only_marketing_tier_is_claimed(self) -> None:
        assert derive_status("DETECTED", [4, 5]) == "CLAIMED"

    def test_detected_without_evidence_is_inferred(self) -> None:
        assert derive_status("DETECTED", []) == "INFERRED"

    def test_low_tier_evidence_stays_inferred(self) -> None:
        assert derive_status("DETECTED", [7]) == "INFERRED"

    def test_legacy_active_uses_evidence_ladder(self) -> None:
        assert derive_status("active", [1]) == "CONFIRMED"
        assert derive_status("active", []) == "INFERRED"


class TestDeriveSince:
    def test_quarter_in_vendor_sentence(self) -> None:
        assert derive_since(
            "nCino",
            ["The bank selected nCino for loan origination in Q3 2025. "
             "Separately, it was founded in 1934."],
        ) == "2025-Q3"

    def test_month_precision(self) -> None:
        assert derive_since(
            "Tableau", ["Enterprise rollout of Tableau began in April 2023."],
        ) == "2023-04"

    def test_date_in_unrelated_sentence_is_ignored(self) -> None:
        assert derive_since(
            "Tableau",
            ["The company was founded in 1934. It uses Tableau for reporting."],
        ) is None

    def test_no_evidence_returns_none(self) -> None:
        assert derive_since("Salesforce", []) is None


class TestGapRows:
    def test_absent_families_mirror_frontend_rule(self) -> None:
        hay = "Salesforce Sales Cloud · Tableau Server · Fiserv DNA"
        missing = dict(absent_families(hay))
        assert "salesforce" not in missing
        assert "tableau" not in missing
        assert set(missing) == {"databricks", "twilio", "ncino"}

    def test_gap_row_shape(self) -> None:
        row = absent_gap_row(
            family="salesforce", display_name="Salesforce",
            subcaps=[{"subcap_id": "P2C2.1.1", "score": 1.8,
                      "peer_median": 2.6, "thin": False}],
            peer_coverage=0.66,
        )
        assert row.status == "ABSENT"
        assert row.tech_id == "absent-salesforce"
        assert row.primary_gap is True
        assert row.peer_coverage == 0.66
        assert row.linked_subcap_ids == ["P2C2.1.1"]
        assert row.detected_at is None
        assert row.layer_code == "L3"

    def test_gap_row_without_addressable_subcaps_is_not_primary(self) -> None:
        row = absent_gap_row(family="twilio", display_name="Twilio",
                             subcaps=[], peer_coverage=None)
        assert row.primary_gap is False

    def test_gap_zones_grounded_on_real_scores(self) -> None:
        from app.schemas.context import TechSubcapImpact
        row = absent_gap_row(
            family="databricks", display_name="Databricks",
            subcaps=[{"subcap_id": "P4C2.3.1", "score": 1.5,
                      "peer_median": 2.4, "thin": True}],
            peer_coverage=0.22,
        )
        zones = gap_zones_for(row, [TechSubcapImpact(
            subcap_id="P4C2.3.1", name="Advanced analytics", score=1.5,
            peer_median=2.4, thin=True,
        )], "RB cohort")
        assert any("P4C2.3.1" in z and "1.5" in z for z in zones)
        assert any("22%" in z for z in zones)

    def test_gap_zones_empty_for_detected_rows(self) -> None:
        row = absent_gap_row(family="tableau", display_name="Tableau",
                             subcaps=[], peer_coverage=None)
        row = row.model_copy(update={"status": "CONFIRMED"})
        assert gap_zones_for(row, [], "RB cohort") == []


class TestLayerLadder:
    def test_l1_restored_for_p1_dominant_rows(self) -> None:
        code, full, pillar = layer_ladder_fields(
            "application", ["P1C1.1.1", "P1C2.1.1", "P2C1.1.1"],
        )
        assert (code, pillar) == ("L1", "P1")
        assert "Strategy" in (full or "")

    def test_default_ladder_mapping(self) -> None:
        assert layer_ladder_fields("platform", [])[:2] == (
            "L2", "Operations & core banking")
        assert layer_ladder_fields("application", [])[0] == "L3"
        assert layer_ladder_fields("intelligence", [])[0] == "L4"
        assert layer_ladder_fields("foundation", [])[0] == "L5"

    def test_dominant_pillar_majority(self) -> None:
        assert dominant_pillar(["P4C1.1.1", "P4C2.1.1", "P2C1.1.1"]) == "P4"
        assert dominant_pillar([]) is None


class TestComposeNote:
    def test_note_from_real_fields(self) -> None:
        note = compose_note(vendor="Salesforce", product="Marketing Cloud",
                            evidence_count=2, subcap_count=3,
                            source="Explorium")
        assert note == (
            "Marketing Cloud · 2 evidence items · addresses 3 sub-capabilities"
        )

    def test_note_falls_back_to_source(self) -> None:
        assert compose_note(vendor="Fiserv", product="Fiserv",
                            evidence_count=0, subcap_count=0,
                            source="A4_tech_stack_map.csv") == \
            "Detected via A4_tech_stack_map.csv"
