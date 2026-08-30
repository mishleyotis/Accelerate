"""Stage 2.2 QA bullets — the identifier authority.

The plan's verification is explicit: assert OBJECT IDENTITY of the
compiled pattern at every call site (not equality), match the mint
namespace, and reject a payload minting an evidence id.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import identifiers
from dma_mcp.identifiers import (EID_TOKEN_RE, agent_id_class, find_fabricated,
                                 find_ids, is_mint)


def test_the_compiled_object_is_the_one_every_call_site_uses():
    # `is`, not ==: a second recogniser with the same pattern today is a
    # second recogniser free to drift tomorrow. Every consumer must hold
    # THE module-level object.
    assert identifiers.EID_TOKEN_RE is EID_TOKEN_RE
    assert find_ids.__globals__["EID_TOKEN_RE"] is EID_TOKEN_RE
    assert is_mint.__globals__["MINT_RE"] is identifiers.MINT_RE


def test_matches_and_rejections_from_the_trd_table():
    text = ("Cited [E-047] and [E-7], mint E-CC-001, connector EV-P2C4-013, "
            "note INT-DISCOVERY-04, qualified E-WLI-047 and E-WLI-047-R2. "
            "But e-047 (case), PRE-047, P1C1.1.1 and REC-04 are not evidence ids. "
            "E-047abc must not partially match.")
    found = find_ids(text)
    assert found == ["E-047", "E-7", "E-CC-001", "EV-P2C4-013",
                     "INT-DISCOVERY-04", "E-WLI-047", "E-WLI-047-R2"]


def test_order_is_preserved_for_truncated_cell_recovery():
    assert find_ids("E-089, E-047, E-0")[0] == "E-089"


def test_mint_namespace_is_matched_and_fabrication_is_visible():
    assert is_mint("E-CC-014") and not is_mint("E-014") and not is_mint("EV-X-1")
    # an invented id in the MINT namespace is exactly what the retired
    # system could not see
    fabricated = find_fabricated(["E-047", "E-CC-999", "E-047"],
                                 allowed={"E-047", "E-CC-014"})
    assert fabricated == ["E-CC-999"]


def test_agent_may_create_exactly_its_own_classes():
    assert agent_id_class("IC-101") == "ic_id"
    assert agent_id_class("F-3") == "f_id"
    assert agent_id_class("FA-12") == "fa_id"
    assert agent_id_class("TS-7") == "ts_id"
    assert agent_id_class("WN-2") == "wn_id"
    assert agent_id_class("REC-04") == "rec_id"
    assert agent_id_class("REC-WLI-04") == "rec_id"
    # everything else is rejected — evidence ids above all
    for bad in ("E-047", "E-CC-001", "IS-101", "AG-01", "P1C1.1.1", "ic-101"):
        assert agent_id_class(bad) is None
