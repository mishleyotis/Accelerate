"""Tests for the pure sheets_client helpers (no GCP creds required)."""
from __future__ import annotations

from typing import ClassVar

from app.services.sheets_client import (
    fuzzy_match_assignee,
    rows_to_dicts,
)


class TestRowsToDicts:
    def test_basic(self) -> None:
        values = [
            ["request_id", "entity", "assigned_to"],
            ["REQ-A1", "AlmaBank", "Mishley"],
            ["REQ-A2", "WSFS", "Richard"],
        ]
        out = rows_to_dicts(values)
        assert len(out) == 2
        assert out[0]["entity"] == "AlmaBank"
        assert out[1]["assigned_to"] == "Richard"

    def test_padding(self) -> None:
        """Trailing empty columns are filled with ''."""
        values = [
            ["a", "b", "c"],
            ["1"],
        ]
        out = rows_to_dicts(values)
        assert out == [{"a": "1", "b": "", "c": ""}]

    def test_empty_returns_empty(self) -> None:
        assert rows_to_dicts([]) == []


class TestFuzzyMatchAssignee:
    """State-branch matrix for fuzzy_match_assignee."""

    KNOWN: ClassVar[list[str]] = ["Mishley", "Richard", "Sam", "Kevin", "Chris", "Carlie", "Tom"]

    def test_exact_match(self) -> None:
        assert fuzzy_match_assignee("Mishley", self.KNOWN) == "Mishley"

    def test_case_insensitive_exact_match(self) -> None:
        assert fuzzy_match_assignee("mishley", self.KNOWN) == "Mishley"

    def test_fuzzy_within_levenshtein_2(self) -> None:
        # 'Mishly' → 'Mishley' (distance 1)
        assert fuzzy_match_assignee("Mishly", self.KNOWN) == "Mishley"

    def test_fuzzy_within_levenshtein_2_more(self) -> None:
        # 'Mishl' → 'Mishley' — Levenshtein distance 2 (insert 'e','y')
        assert fuzzy_match_assignee("Mishl", self.KNOWN) == "Mishley"

    def test_too_far_returns_none(self) -> None:
        # 'Alexandria' is > 2 edits from any known name → no_match
        assert fuzzy_match_assignee("Alexandria", self.KNOWN) is None

    def test_empty_input(self) -> None:
        assert fuzzy_match_assignee(None, self.KNOWN) is None
        assert fuzzy_match_assignee("", self.KNOWN) is None
        assert fuzzy_match_assignee("   ", self.KNOWN) is None
