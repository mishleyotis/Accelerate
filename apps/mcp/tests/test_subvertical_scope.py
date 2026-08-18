"""ET-05 — a run cites only its own sub-vertical's variant cells.

Baxter Credit Union is a credit union (SV2 → CU) and its served register
carried 59 cells belonging to insurance carriers, RIAs and insurance
brokers; the citations reaching the payload — verbatim below — are from
`heatmap.focus_areas[*].involved_subcap_ids` and
`heatmap.evidence[*].supports_subcap_ids`.

The serving tier already filters these on READ. This gate exists because
a read filter cannot repair the SENTENCE written beside a cell that does
not apply: if a focus area was reasoned over an insurance-carrier
capability, hiding the id afterwards leaves the reasoning in place.

The derivation is not written twice. `apps/api/dma_api/subverticals.py`
is the source of truth and `dma_mcp/subverticals.py` mirrors it (the two
services are separate images, so an import across the boundary would
resolve in the test run and fail in the container). The last test here is
the anti-drift guard: it reads the API module when it is on disk and
asserts both sides agree.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from dma_mcp.subverticals import (SUBVERTICAL_CODES, resolve_subvertical,
                                  serves, variant_subvertical)
from dma_mcp.validation2 import _check_subvertical_scope

# verbatim from the promoted heatmap payload
FOCUS = {"focus_areas": [{
    "fa_id": "FA-3", "name": "Personalization and proactive engagement",
    "involved_subcap_ids": ["P2C2.1.1", "P2C2.1.IC1", "P2C2.1.IC3",
                            "P2C2.1.RIA1", "P2C2.2.RIA1", "P2C2.4.IC1",
                            "P2C2.7.CU1", "P1C2.7.BK1"],
}]}


def test_the_promoted_focus_area_is_refused_cell_by_cell():
    out = _check_subvertical_scope("heatmap", {"focus_areas": FOCUS}, "CU")
    refused = {r["path"].rsplit("[", 1)[0]: r for r in out}
    assert len(out) == 5                       # IC1 IC3 RIA1 RIA1 IC1
    assert all(r["gate_id"] == "ET-05" and r["severity"] == "block"
               for r in out)
    msg = " ".join(r["message"] for r in out)
    assert "insurance carriers" in msg and "RIAs and broker-dealers" in msg
    assert "credit unions" in msg               # and which run it is
    assert refused


def test_the_entitys_own_variant_and_the_base_cells_stay():
    """P2C2.1.1 is a base cell, P2C2.7.CU1 is this entity's own variant and
    P1C2.7.BK1 is a FAMILY code (the depository family — NCUA is the
    credit-union regulator), so none of the three is evidence of belonging
    to somebody else."""
    kept = {"focus_areas": [{"involved_subcap_ids":
                             ["P2C2.1.1", "P2C2.7.CU1", "P1C2.7.BK1"]}]}
    assert _check_subvertical_scope("heatmap", {"focus_areas": kept}, "CU") == []


def test_the_repaired_focus_area_passes():
    fixed = {"focus_areas": [{**FOCUS["focus_areas"][0],
                              "involved_subcap_ids": ["P2C2.1.1",
                                                      "P2C2.7.CU1"]}]}
    assert _check_subvertical_scope("heatmap", {"focus_areas": fixed}, "CU") == []


def test_every_citation_key_is_reached_not_just_the_named_two():
    """The class is "a section cites a cell", not "a tech row does" — so
    the sweep is over every `*subcap_ids` list and every `subcap_id`
    scalar, wherever it sits."""
    payload = {
        "techstack": {"items": [{"ts_id": "TS-1",
                                 "linked_subcap_ids": ["P2C4.6.RIA1"]}]},
    }
    assert len(_check_subvertical_scope("techstack", payload, "CU")) == 1
    payload = {"cell_evidence": {"cells": [{"subcap_id": "P1C1.3.IC1"}]}}
    assert len(_check_subvertical_scope("heatmap", payload, "CU")) == 1


def test_an_unknown_sub_vertical_refuses_nothing():
    """Absent beats wrong: not knowing who the entity is, is not grounds
    for refusing a citation. The API's `serves` makes the same one-sided
    choice."""
    assert _check_subvertical_scope("heatmap", {"focus_areas": FOCUS},
                                    None) == []


def test_the_derivation_reads_the_terminal_segment_only():
    assert variant_subvertical("P1C1.3.CU1") == "CU"
    assert variant_subvertical("P2C4.6.RIA3") == "RIA"
    assert variant_subvertical("P1C1.3.2") is None        # base cell
    assert variant_subvertical("P1C2.7.BK1") is None      # family code
    assert variant_subvertical("P3C4.2.PEN1") is None     # product line
    assert serves("P1C1.3.IC1", "CU") is False
    assert serves("P1C1.3.IC1", "IC") is True
    assert resolve_subvertical("SV2") == "CU"
    assert resolve_subvertical("Credit Unions") == "CU"
    assert resolve_subvertical("RIA / Broker-Dealer") == "RIA"
    assert resolve_subvertical("nonsuch") is None


def test_the_mirror_agrees_with_its_source_of_truth():
    """The one thing a mirrored derivation may not do is drift. When the
    API module is on disk (the repo, not the connector image), both sides
    are asserted to agree — vocabulary, aliases and the derivation itself."""
    api = (Path(__file__).resolve().parents[3] / "apps" / "api" / "dma_api"
           / "subverticals.py")
    if not api.exists():
        pytest.skip("api module not present (connector image)")
    sys.path.insert(0, str(api.parents[1]))
    from dma_api import subverticals as truth

    assert set(SUBVERTICAL_CODES) == set(truth.SUBVERTICAL_CODES)
    assert truth._SUBVERTICAL_ALIASES == \
        __import__("dma_mcp.subverticals", fromlist=["x"])._SUBVERTICAL_ALIASES
    for cell in ("P1C1.3.CU1", "P1C1.3.IC1", "P2C4.6.RIA1", "P1C1.3.2",
                 "P1C2.7.BK1", "P3C4.2.PEN1", "P4C3.8.IB1", "P1C5.4.IC1"):
        assert variant_subvertical(cell) == truth.variant_subvertical(cell), cell
        for code in ("CU", "IC", None):
            assert serves(cell, code) == truth.serves(cell, code), (cell, code)
    for raw in ("SV2", "Credit Unions", "RIA / Broker-Dealer", "Farm Credit",
                "", None, "nonsuch"):
        assert resolve_subvertical(raw) == truth.resolve_subvertical(raw), raw
