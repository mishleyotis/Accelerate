"""Tests for the drive_crawler dispatch table — pure mapping logic."""
from __future__ import annotations

import sys
from pathlib import Path

# Workers package is one level up from the backend root.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workers.drive_crawler.dispatch import (  # noqa: E402
    DISPATCH_TABLE,
    blocks_active_for_kind,
    blocks_run_activation,
    is_authoritative,
    lookup,
)


def test_evidence_handoff_is_authoritative_and_blocks_active() -> None:
    entry = lookup("evidence_handoff_json")
    assert entry is not None
    assert entry.is_authoritative is True
    assert entry.blocks_active is True
    assert "subcap_scores" in entry.target_tables
    assert "evidence_index" in entry.target_tables
    assert "insight_cards" in entry.target_tables
    assert "recommendations" in entry.target_tables


def test_scoring_workbook_targets_subcap_scores_only() -> None:
    entry = lookup("scoring_workbook")
    assert entry is not None
    assert entry.target_tables == ("subcap_scores",)
    assert entry.is_authoritative is False


def test_research_workbook_targets_evidence_index() -> None:
    entry = lookup("research_workbook")
    assert entry is not None
    assert "evidence_index" in entry.target_tables


def test_supplementary_has_empty_target_tables() -> None:
    entry = lookup("supplementary")
    assert entry is not None
    assert entry.target_tables == ()
    assert entry.parser_module == ""


def test_unknown_kind_returns_none() -> None:
    assert lookup("not_a_kind") is None
    assert is_authoritative("not_a_kind") is False
    assert blocks_active_for_kind("not_a_kind") is False


def test_blocks_run_activation_needs_handoff() -> None:
    assert blocks_run_activation([
        "scoring_workbook", "research_workbook",
    ]) is False
    assert blocks_run_activation([
        "scoring_workbook", "evidence_handoff_json",
    ]) is True


def test_dispatch_table_lists_expected_kinds() -> None:
    expected = {
        "evidence_handoff_json", "scoring_workbook", "research_workbook",
        "assessment_report", "client_profile", "issue_register",
        "supplementary",
    }
    assert set(DISPATCH_TABLE.keys()) == expected
