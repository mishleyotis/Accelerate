"""Tests for the grounding validator's regex patterns + dataclass flags."""
from __future__ import annotations

from app.services.grounding_validator import (
    RE_AGENT,
    RE_E_ID,
    RE_IC,
    RE_REC,
    RE_SUBCAP,
    ValidationFlags,
)


def test_e_id_regex() -> None:
    text = "Per E-12, the entity supports cross-channel; see also E-7 and E-9999."
    assert RE_E_ID.findall(text) == ["E-12", "E-7", "E-9999"]
    # Does NOT match plain numbers or non-prefixed IDs
    assert RE_E_ID.findall("evidence #12 says") == []


def test_subcap_regex_t1_and_t2() -> None:
    text = "P1C1.2.3 has gap, P2C3.4.2-T2-CIB even more so, P4C2.1.1-T2-RB."
    assert RE_SUBCAP.findall(text) == [
        "P1C1.2.3",
        "P2C3.4.2-T2-CIB",
        "P4C2.1.1-T2-RB",
    ]


def test_subcap_regex_rejects_invalid_shapes() -> None:
    # Invalid pillar (5), missing depth, missing trailing digit
    assert RE_SUBCAP.findall("P5C1.2.3 or P1C1.2 or P1C1") == []
    # Bad T2 region code (lowercase) still partially matches the T1 prefix; the
    # regex must therefore *find* "P1C1.2.3" rather than the full malformed tail
    matches = RE_SUBCAP.findall("P1C1.2.3-T2-cib")
    assert matches == ["P1C1.2.3"], "expected only the T1 portion to match"


def test_ic_and_rec_regex() -> None:
    text = "Per IC-001 and IC-42; recommend REC-7 and REC-12."
    assert RE_IC.findall(text) == ["IC-001", "IC-42"]
    assert RE_REC.findall(text) == ["REC-7", "REC-12"]


def test_agent_regex() -> None:
    text = "Drove via AF-Loan-Approver-01 and FM-AGENT-RETAIL_HUB."
    assert sorted(RE_AGENT.findall(text)) == sorted(
        ["AF-Loan-Approver-01", "FM-AGENT-RETAIL_HUB"]
    )


class TestValidationFlags:
    def test_is_clean_when_empty(self) -> None:
        f = ValidationFlags()
        assert f.is_clean is True

    def test_is_not_clean_when_any_flag_set(self) -> None:
        f = ValidationFlags(fabricated_e_ids=["E-9999"])
        assert f.is_clean is False

        f2 = ValidationFlags(citation_set_mismatch=["E-1"])
        assert f2.is_clean is False

    def test_to_dict_shape(self) -> None:
        f = ValidationFlags(
            fabricated_e_ids=["E-1"],
            fabricated_subcap_ids=["P9C9.9.9"],
        )
        d = f.to_dict()
        assert set(d.keys()) == {
            "fabricated_e_ids",
            "fabricated_subcap_ids",
            "fabricated_ic_ids",
            "fabricated_rec_ids",
            "fabricated_agents",
            "citation_set_mismatch",
        }
        assert d["fabricated_e_ids"] == ["E-1"]
        assert d["fabricated_subcap_ids"] == ["P9C9.9.9"]
