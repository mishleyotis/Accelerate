"""Research-ledger annotations stored as evidence never reach a customer.

Measured 2026-10-01 on Northwest Bank (run ba6b2090): 20 of 335 stored
evidence rows carried the research ladder's own notes in `excerpt` or
`source_name` — "CURRENCY PROBE RESOLVED", "(Wave 1, E-002)", "Peer-reverse
proxy sweep", "FDIC T1". The drawer and `/evidence` serve stored rows
verbatim, so no page resubmission could reach them; only the serve-side net
can. The strings below are the measured ones, verbatim.

The negatives matter as much: the net matches identifiers and ladder jargon,
never ordinary English, and never a bare evidence id in an id field.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_api.evidence import redact_items          # noqa: E402
from dma_api.redaction import redact_section       # noqa: E402
import internal_ids                                # noqa: E402

MEASURED = [
    "CURRENCY PROBE RESOLVED - THE PROGRAMME IS ALIVE. Northwest posted a Sr.",
    "CONTRADICTS PROBE RESULT — CHECKED, NONE FOUND for fraud.",
    "CURRENCY PROBE RESULT: the only evidence naming any Northwest fraud lead",
    "This CONTRADICTS the hypothesis that the data capability is new.",
    "so technology fell from 16.7% to 13.4% of the cost base (Wave 1, E-002).",
    "plus the Erie PA set already banked at E-009) returned only branch roles",
    "derived from the category's banked record (E-085, E-095 to E-144)",
    "Peer-reverse proxy sweep: innovation, AI and fintech programme",
    "practitioner profiles (org_talent proxy rung for UAT, champions)",
    "Locked peer Fulton Financial ($32.56B) publishes its six-page",
    "LEADERSHIP_TITLE + ARTIFACT_DISCLOSURE PROXY RUNG, full-text verified",
    "over the identical window (-1,096bp vs -864bp, FDIC T1) while ALSO",
]

ORDINARY = [
    "E-NORTHWES-001",                       # a bare id value, as in e_id
    "E-CC-1025",
    "The new evidence contradicts the earlier reading of the filing.",
    "A wave of branch consolidations followed the 2024 merger.",
    "Northwest Bank is a Pennsylvania-chartered savings bank.",
    "Integrate applications to Fiserv Signature using Fiserv Communicator",
    "The bank reports Tier 1 capital of 12.2% under SEC filings.",
    "The connector between the two systems is staged for the next cycle.",
]


@pytest.mark.parametrize("text", MEASURED)
def test_measured_annotations_are_machinery(text):
    assert internal_ids.names_machinery(text), text


@pytest.mark.parametrize("text", ORDINARY)
def test_ordinary_text_is_not_machinery(text):
    assert internal_ids.names_machinery(text) is None, text


def _item(excerpt, source_name="Northwest Bancshares 2025 Form 10-K"):
    return {"e_id": "E-NORTHWES-087", "excerpt": excerpt,
            "source_name": source_name, "source_url": "https://example.test/x",
            "ers": 3.1, "tier": "T1"}


def test_evidence_endpoint_withholds_the_whole_annotated_field():
    out = redact_items([_item(MEASURED[0]), _item("A clean verbatim span "
                        "from the bank's own filing about deposits.")],
                       "customer")
    assert "excerpt" not in out[0]                  # withheld whole
    assert out[0]["e_id"] == "E-NORTHWES-087"       # the chip survives
    assert out[0]["source_name"] == "Northwest Bancshares 2025 Form 10-K"
    assert out[1]["excerpt"].startswith("A clean verbatim span")
    assert "ers" not in out[0] and "ers" not in out[1]


def test_evidence_endpoint_withholds_an_annotated_source_name():
    out = redact_items([_item("A clean verbatim span from the filing.",
                              source_name=MEASURED[7])], "customer")
    assert "source_name" not in out[0] and out[0]["excerpt"]


def test_internal_audience_keeps_the_annotation():
    out = redact_items([_item(MEASURED[0])], "internal")
    assert out[0]["excerpt"] == MEASURED[0]


def test_drawer_items_are_withheld_by_the_page_walker():
    body = {"cells": [{"subcap_id": "P4C1.4.2",
                       "items": [_item(MEASURED[4]), _item("Clean span.")]}]}
    out, report = redact_section("heatmap", "cell_evidence", body, [],
                                 "customer")
    if out is None:                     # section not on this allowlist build
        pytest.skip("heatmap.cell_evidence not served to customer")
    items = out["cells"][0]["items"]
    assert all(MEASURED[4] != i.get("excerpt") for i in items)
    assert report["machinery_named"]
