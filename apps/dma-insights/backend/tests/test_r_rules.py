"""F6 R-rules — exhaustive tests including stress cases.

Each rule:
  - at least one positive sample (rule MATCHES, hit returned)
  - at least one negative sample (rule does NOT match, None returned)
  - edge cases that exercise the gray zone (missing metadata,
    capitalisation, partial matches)

The orchestrator + severity-routing helpers are also tested so the
contract is locked: a `skip` always beats a `quarantine` beats a
`downgrade` beats a `warn` beats an `allow`.
"""
from __future__ import annotations

import pytest

from app.services.parsers.r_rules import (
    RRuleHit,
    detect_r05_client_provided,
    detect_r06_pre_v55_framework,
    detect_r07_test_case,
    evaluate_all_rules,
    highest_severity,
    hits_to_audit_payload,
)

# ── R05 — Client-provided ──────────────────────────────────────────────


class TestR05ClientProvided:
    def test_zennify_owner_returns_none(self):
        h = detect_r05_client_provided(
            file_owner_email="mishley.otiende@zennify.com",
            last_modified_by_email="external@bigcorp.com",
        )
        assert h is None, "Zennify owner should NOT quarantine"

    def test_zennify_last_modifier_returns_none(self):
        """Even if a client uploaded it, if a Zennify analyst opened +
        re-saved, the file should ingest normally."""
        h = detect_r05_client_provided(
            file_owner_email="external@bigcorp.com",
            last_modified_by_email="richard.odhiambo@zennify.com",
        )
        assert h is None

    def test_bot_sa_owner_treated_as_zennify(self):
        h = detect_r05_client_provided(
            file_owner_email="dma@zennify.com",
            last_modified_by_email="external@bigcorp.com",
        )
        assert h is None

    def test_n8n_bot_modifier_treated_as_zennify(self):
        h = detect_r05_client_provided(
            file_owner_email="external@bigcorp.com",
            last_modified_by_email="n8n-workflow-runner@…",
        )
        assert h is None

    def test_both_external_returns_hit(self):
        h = detect_r05_client_provided(
            file_owner_email="ceo@bigcorp.com",
            last_modified_by_email="cfo@bigcorp.com",
            filename="Strategic_Plan_2026.docx",
        )
        assert h is not None
        assert h.rule_id == "R05"
        assert h.action == "quarantine"
        assert h.confidence == 1.0
        assert "bigcorp.com" in h.evidence["owner"]
        assert h.evidence["filename"] == "Strategic_Plan_2026.docx"

    def test_missing_both_metadata_returns_none(self):
        """Defensive: with no signal we don't quarantine — the next
        ingest pass with full metadata will catch it if real."""
        h = detect_r05_client_provided(
            file_owner_email=None, last_modified_by_email=None,
        )
        assert h is None

    def test_capitalisation_does_not_fool_detection(self):
        h = detect_r05_client_provided(
            file_owner_email="Mishley.Otiende@Zennify.COM",
            last_modified_by_email="other@external.com",
        )
        assert h is None, "Mixed-case zennify.com still treated as internal"


# ── R06 — Pre-v5.5 framework ──────────────────────────────────────────


class TestR06PreV55Framework:
    def test_v5_0_cover_page_downgrade(self):
        text = "DMA Assessment Report — Capability Mapping v5.0 (R3)\n..."
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is not None
        assert h.rule_id == "R06"
        assert h.action == "downgrade"
        assert "v5.0" in h.evidence["matched_phrase"].lower()

    def test_v4_0_cover_page_downgrade(self):
        text = "Strategic Maturity Framework v4.0 — AlmaBank — 2024-Q3"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is not None
        assert h.action == "downgrade"

    def test_v5_4_cover_page_downgrade(self):
        text = "DMA Framework v5.4 — Regions Bank — March 2025"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is not None

    def test_v5_5_returns_none(self):
        """v5.5 is the threshold — NOT pre-v5.5."""
        text = "DMA Framework v5.5 — WSFS — March 2025"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is None

    def test_v7_0_returns_none(self):
        text = "Capability Mapping v7.0 — Amalgamated Bank — 2026-04"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is None

    def test_v6_8_returns_none(self):
        text = "DMA Framework v6.8 — ANB — 2025-Q4"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is None

    def test_no_framework_phrase_returns_none(self):
        text = "Some unrelated report content with no version stamp."
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is None

    def test_v5_5_plus_short_circuits_pre_v55_match(self):
        """If the cover page mentions BOTH v5.5+ and a legacy ref
        (e.g. 'upgraded from v4.0'), the v5.5+ wins — file is current."""
        text = "Capability Mapping v7.0 (upgraded from v4.0 framework)"
        h = detect_r06_pre_v55_framework(docx_first_page_text=text)
        assert h is None

    def test_empty_text_returns_none(self):
        assert detect_r06_pre_v55_framework(docx_first_page_text="") is None
        assert detect_r06_pre_v55_framework(docx_first_page_text=None) is None  # type: ignore


# ── R07 — Test-case / sample-data ─────────────────────────────────────


class TestR07TestCase:
    def test_nyumba_zetu_skipped(self):
        h = detect_r07_test_case(folder_name="Nyumba Zetu - DMA")
        assert h is not None
        assert h.rule_id == "R07"
        assert h.action == "skip"
        assert h.confidence == 1.0

    def test_nyumba_zetu_underscore_variant(self):
        h = detect_r07_test_case(folder_name="nyumba_zetu_test")
        assert h is not None
        assert h.action == "skip"

    def test_sample_bank_skipped(self):
        h = detect_r07_test_case(folder_name="sample-bank-foo")
        assert h is not None
        assert h.action == "skip"

    def test_acme_bank_placeholder(self):
        h = detect_r07_test_case(
            folder_name="ACME-BANK-Test", entity_name="Acme Bank",
        )
        assert h is not None
        assert h.action == "skip"

    def test_real_bank_returns_none(self):
        h = detect_r07_test_case(
            folder_name="RegionsBank_DMA_20260518",
            entity_name="Regions Bank",
        )
        assert h is None

    def test_amalgamated_returns_none(self):
        """Real client; no test-marker token."""
        h = detect_r07_test_case(
            folder_name="Amalgamated_Bank_DMA_2026",
            entity_name="Amalgamated Bank",
        )
        assert h is None

    def test_generic_test_token_warns_not_skips(self):
        """A folder with 'test' in the name (operator may have meant
        a real client called e.g. 'Test Federal Credit Union') gets a
        warn rather than a hard skip — admin decides."""
        h = detect_r07_test_case(folder_name="MyBank-test-2026")
        assert h is not None
        assert h.action == "warn"
        assert h.confidence < 1.0

    def test_word_boundary_test_does_not_false_positive(self):
        """'NorthWest' must NOT match the 'test' substring rule."""
        h = detect_r07_test_case(folder_name="NorthWest Bank DMA")
        assert h is None
        h = detect_r07_test_case(folder_name="Latest Federal Bank")
        assert h is None  # 'latest' contains 'test' but only as a substring

    def test_demo_token_warns(self):
        h = detect_r07_test_case(folder_name="Bank-demo-fixture")
        assert h is not None
        assert h.action == "warn"


# ── Orchestrator ──────────────────────────────────────────────────────


class TestEvaluateAllRules:
    def test_clean_real_package_returns_no_hits(self):
        hits = evaluate_all_rules(
            folder_name="Amalgamated_Bank_DMA_2026",
            entity_name="Amalgamated Bank",
            file_owner_email="mishley.otiende@zennify.com",
            last_modified_by_email="mishley.otiende@zennify.com",
            docx_first_page_text="Capability Mapping v7.0 — March 2026",
        )
        assert hits == []

    def test_nyumba_zetu_with_external_owner_returns_2_hits(self):
        hits = evaluate_all_rules(
            folder_name="Nyumba Zetu - DMA Test",
            file_owner_email="customer@externalbank.com",
            last_modified_by_email="customer@externalbank.com",
        )
        rule_ids = {h.rule_id for h in hits}
        assert "R05" in rule_ids
        assert "R07" in rule_ids
        # Ordering must be deterministic (sorted by rule_id).
        assert [h.rule_id for h in hits] == sorted(h.rule_id for h in hits)

    def test_highest_severity_picks_skip_over_quarantine(self):
        """R07 skip + R05 quarantine → skip wins (5 > 4)."""
        hits = evaluate_all_rules(
            folder_name="Nyumba Zetu - DMA",
            file_owner_email="external@bigcorp.com",
            last_modified_by_email="external@bigcorp.com",
        )
        assert highest_severity(hits) == "skip"

    def test_highest_severity_picks_quarantine_over_downgrade(self):
        hits = evaluate_all_rules(
            folder_name="ClientCo - DMA",
            file_owner_email="cfo@clientco.com",
            last_modified_by_email="cfo@clientco.com",
            docx_first_page_text="Framework v4.0 — 2024",
        )
        assert highest_severity(hits) == "quarantine"

    def test_audit_payload_is_json_safe(self):
        """The audit payload must round-trip through json.dumps —
        downstream writes it to `import_files.parser_warnings` JSONB."""
        import json
        hits = evaluate_all_rules(
            folder_name="Nyumba Zetu - DMA",
            file_owner_email="x@y.com",
            last_modified_by_email="x@y.com",
        )
        payload = hits_to_audit_payload(hits)
        serialised = json.dumps(payload)
        round_trip = json.loads(serialised)
        assert round_trip["highest_severity"] == "skip"
        assert len(round_trip["r_rules"]) >= 2

    def test_empty_inputs_returns_empty_hits(self):
        hits = evaluate_all_rules(folder_name="")
        assert hits == []
        assert highest_severity(hits) == "allow"


# ── Severity helper edges ─────────────────────────────────────────────


def test_highest_severity_empty_list_defaults_to_allow():
    assert highest_severity([]) == "allow"


def test_highest_severity_priority_ladder():
    """Confirm the canonical priority ladder."""
    for higher, lower in (
        ("skip", "quarantine"),
        ("quarantine", "downgrade"),
        ("downgrade", "warn"),
        ("warn", "allow"),
    ):
        h_a = RRuleHit(rule_id="X1", action=higher, reason="",
                       confidence=1.0, evidence={})
        h_b = RRuleHit(rule_id="X2", action=lower, reason="",
                       confidence=1.0, evidence={})
        assert highest_severity([h_b, h_a]) == higher, (
            f"{higher} should beat {lower}"
        )


def test_rule_registry_has_unique_rule_ids():
    """Sanity: the 3 rules must use distinct IDs so the audit row
    isn't ambiguous. If anyone adds R08 later this test will catch
    duplicate-ID bugs."""
    sample_hits = evaluate_all_rules(
        folder_name="Nyumba Zetu - DMA",
        file_owner_email="x@y.com",
        last_modified_by_email="x@y.com",
        docx_first_page_text="Framework v4.0",
    )
    ids = [h.rule_id for h in sample_hits]
    assert len(ids) == len(set(ids))


# ── Stress / integration sanity ───────────────────────────────────────


@pytest.mark.parametrize("folder", [
    "RegionsBank_DMA_20260518",
    "Amalgamated_Bank_DMA_2026",
    "ANB_DMA_Complete_Bundle",
    "WSFS_DMA_Engagement_Package",
    "AmeriCU_DMA_Deliverable_2026-04-29",
])
def test_all_5_real_packages_produce_no_skip_hits(folder):
    """Sanity check: none of the 5 operator-uploaded real packages
    matches the test-case quarantine rule. If a future package name
    accidentally trips R07, this test surfaces it immediately so we
    don't silently lose a real ingest."""
    hits = evaluate_all_rules(
        folder_name=folder,
        file_owner_email="mishley.otiende@zennify.com",
        last_modified_by_email="mishley.otiende@zennify.com",
        docx_first_page_text="Capability Mapping v7.0 — 2026",
    )
    actions = {h.action for h in hits}
    assert "skip" not in actions, (
        f"Real package {folder!r} would be R07-skipped — adjust patterns"
    )
    assert "quarantine" not in actions
