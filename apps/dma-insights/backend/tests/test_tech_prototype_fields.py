"""Tech-stack prototype alignment: status enum, l3_id link, vendor-variant
resolution, and the widened category→layer map (2026-06-23)."""
from __future__ import annotations

from app.services.parsers.package_persist import _layer_for_tech
from app.services.parsers.package_techstack import (
    parse_tech_csv,
    tech_status_from_signals,
)
from app.services.parsers.tech_linker import family_for_vendor, l3_for_tech


class TestStatusEnum:
    def test_confirmed_signals(self) -> None:
        assert tech_status_from_signals("Confirmed") == "CONFIRMED"
        assert tech_status_from_signals("Deployed") == "CONFIRMED"
        assert tech_status_from_signals("In Use") == "CONFIRMED"
        assert tech_status_from_signals("yes") == "CONFIRMED"

    def test_removed_signals(self) -> None:
        assert tech_status_from_signals("Decommissioned") == "CONFIRMED_REMOVED"
        assert tech_status_from_signals("Replaced 2024") == "CONFIRMED_REMOVED"
        assert tech_status_from_signals("Retired") == "CONFIRMED_REMOVED"

    def test_inferred_and_default(self) -> None:
        assert tech_status_from_signals("INFERRED") == "DETECTED"
        assert tech_status_from_signals("") == "DETECTED"
        assert tech_status_from_signals(None) == "DETECTED"

    def test_high_confidence_upgrades_to_confirmed(self) -> None:
        assert tech_status_from_signals(None, confidence=0.9) == "CONFIRMED"
        assert tech_status_from_signals(None, confidence=0.4) == "DETECTED"


class TestFamilyAndL3:
    def test_exact_family(self) -> None:
        assert family_for_vendor("Salesforce") == "salesforce"
        assert family_for_vendor("Databricks") == "databricks"

    def test_vendor_variant_resolves_via_substring(self) -> None:
        # The old exact-only lookup missed these.
        assert family_for_vendor("Salesforce Inc") == "salesforce"
        assert family_for_vendor("nCino LOS") == "ncino"
        assert family_for_vendor("Tableau Server") == "tableau"

    def test_short_keys_stay_exact(self) -> None:
        # "FIS" (len 3) must not substring-match arbitrary text like "First".
        assert family_for_vendor("First National Bank") is None

    def test_unmapped_vendor_is_none(self) -> None:
        assert family_for_vendor("Acme Widgets") is None

    def test_l3_from_vendor_then_product_keyword(self) -> None:
        assert l3_for_tech("Salesforce") == "salesforce"
        # vendor unmapped, but the product names a scored platform
        assert l3_for_tech("Acme", product="Sales Cloud") == "salesforce"
        assert l3_for_tech("Acme", category="Unknown") is None


class TestLayerMap:
    def test_widened_categories(self) -> None:
        assert _layer_for_tech("Data Lake") == "foundation"
        assert _layer_for_tech("Integration / API") == "platform"
        assert _layer_for_tech("Digital Banking") == "platform"
        assert _layer_for_tech("Business Intelligence") == "intelligence"
        assert _layer_for_tech("GenAI Tooling") == "intelligence"

    def test_unknown_defaults_to_application(self) -> None:
        assert _layer_for_tech("Some Random Category") == "application"


class TestParseCsvProtoFields:
    def test_csv_status_and_l3_populated(self, tmp_path) -> None:
        # Part 9.1: parse_tech_csv now runs the taxonomy gate — catalogue
        # platforms keep their deployment status + l3 link; off-catalogue
        # names are persisted flagged (UNKNOWN_VENDOR review queue), never
        # rendered as platforms.
        p = tmp_path / "A4_tech_stack.csv"
        p.write_text(
            "Technology,Category,Status,Evidence_Level\n"
            "Salesforce,CRM,Confirmed,High\n"
            "Legacy COBOL,Core,Decommissioned,Medium\n"
            "Some Tool,Analytics,Inferred,Low\n"
        )
        rows = {r.vendor: r for r in parse_tech_csv(p)}
        assert rows["Salesforce"].status == "CONFIRMED"
        assert rows["Salesforce"].l3_id == "salesforce"
        # Off-catalogue names route to the review queue (not the surface).
        assert rows["Legacy COBOL"].status == "UNKNOWN_VENDOR"
        assert rows["Some Tool"].status == "UNKNOWN_VENDOR"
        assert rows["Some Tool"].l3_id is None
