"""The customer evidence drawer serves what the page redactor would — and
never our own documents.

MEASURED 2026-10-02 on SWBC (CRITICAL). `GET /v1/entities/swbc/evidence
?audience=customer` served rows with origin='internal' — the assessing
firm's own discovery write-up, its source name naming the person it was
prepared for, excerpts about named people and a sales proposal — and the
tier `distribution` census. The route ran one redaction (the ERS grading)
and none of the nets every page section runs. The cell drawer resolves the
same rows into `cells[].items[]` and had the same hole.

Fixture rows are SHAPED like the measured ones and carry no client text.
"""
import copy
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api import redaction                                    # noqa: E402
from dma_api.evidence import INTERNAL_FIELDS, redact_items       # noqa: E402
from dma_api.redaction import (customer_evidence_items,          # noqa: E402
                               redact_evidence_response, redact_section)

EXCERPT = ("The institution's 2025 annual report describes a phased "
           "migration of its agency management platform.")


def _item(e_id, origin="package", source="Annual Report 2025",
          excerpt=EXCERPT, url="https://example-client.example/ar"):
    return {"e_id": e_id, "origin": origin, "source_name": source,
            "source_url": url, "source_domain": "example-client.example",
            "excerpt": excerpt, "claim_type": "FACT", "tier": "T2",
            "recency_band": "CURRENT", "ers": 4.1, "specificity": 3,
            "corroboration": 2, "identity_ok": True, "identity_note": None,
            "linked_subcap_ids": ["P1C1.1.1"]}


INTERNAL = _item("E-X-001", origin="internal",
                 source="Internal discovery write-up prepared for a named "
                        "client sponsor",
                 excerpt="Discovery notes on the sponsor's priorities and the "
                         "proposal we expect to put in front of them.")
VENDOR = _item("E-X-002", source=f"{redaction.VENDOR_NAME} solution brief")
SELLER = _item("E-X-003", excerpt="A line for the account team to raise in "
                                  "the first meeting with the sponsor.")
TOOL = _item("E-X-004", source="Explorium firmographic record")
CLEAN = _item("E-X-005")
ROWS = [INTERNAL, VENDOR, SELLER, TOOL, CLEAN]


def test_an_internal_origin_row_never_reaches_a_customer():
    kept, withheld = customer_evidence_items([INTERNAL, CLEAN])
    assert [i["e_id"] for i in kept] == ["E-X-005"]
    assert withheld == {"internal_origin": 1}


def test_every_net_the_page_redactor_runs_applies_to_an_item():
    kept, withheld = customer_evidence_items(ROWS)
    assert [i["e_id"] for i in kept] == ["E-X-005"]
    assert withheld == {"internal_origin": 1, "vendor_named": 1,
                        "seller_voice": 1, "internal_vocabulary": 1}


def test_a_served_item_loses_the_excluded_classes_and_the_grading():
    (kept,), _ = customer_evidence_items([CLEAN])
    for k in ("tier", "recency_band", "origin") + tuple(INTERNAL_FIELDS):
        assert k not in kept, k
    # the source and its quotation are exactly what a customer DOES get
    assert kept["excerpt"] == EXCERPT and kept["source_name"]
    assert kept["linked_subcap_ids"] == ["P1C1.1.1"]


def test_the_shared_rows_are_never_mutated():
    before = copy.deepcopy(ROWS)
    customer_evidence_items(ROWS)
    assert ROWS == before


@pytest.mark.parametrize("audience", ["customer", "", "Internal ", "analyst",
                                      None])
def test_redact_items_is_default_deny(audience):
    assert [i["e_id"] for i in redact_items(ROWS, audience)] == ["E-X-005"]


def test_the_internal_audience_keeps_every_row():
    assert redact_items(ROWS, "internal") == ROWS


def test_the_response_drops_the_census_and_reports_a_count_not_ids():
    res = {"items": ROWS, "found": [r["e_id"] for r in ROWS],
           "not_found": [], "foreign": [],
           "distribution": {"tiers": {"T2": 5}}, "merged": {"absorbed": 0}}
    out = redact_evidence_response(res, "customer")
    assert "distribution" not in out and "merged" not in out
    assert out["found"] == ["E-X-005"]
    assert out["withheld"] == 4
    assert redact_evidence_response(res, "internal") is res


# ── the route itself ──────────────────────────────────────────────────
class _Conn:
    def __init__(self):
        self._out = []

    def cursor(self):
        return self

    def execute(self, sql, params=None):
        self._out = [(
            "53d062c3-e309-4033-9438-297b2b8505aa", "swbc", None, "IB", None,
            "7968492e-ba03-47fd-93c3-93f5867f1d43", "REQ", 1, True,
            "PROMOTED", 2.01, 760, 851, "v7.0",
            datetime(2026, 9, 30, tzinfo=timezone.utc),
            datetime(2026, 10, 1, tzinfo=timezone.utc),
            date(2026, 9, 30), "STATED", "manifest", date(2027, 3, 30),
            None, "SWBC", ["IC", "CL", "RIA"])] \
            if "FROM serving_directory" in sql else []

    def fetchall(self):
        return self._out

    def close(self):
        pass


@pytest.fixture()
def client(monkeypatch):
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient
    from dma_api import main
    monkeypatch.setattr(main, "_connect", lambda: _Conn())
    monkeypatch.setattr(main, "ev_fetch", lambda *a, **k: {
        "items": copy.deepcopy(ROWS), "found": [r["e_id"] for r in ROWS],
        "not_found": [], "foreign": [],
        "distribution": {"tiers": {"T2": 5}, "total_items": 5},
        "merged": {"absorbed": 0}})
    return TestClient(main.app)


def test_the_customer_route_serves_no_internal_row_and_no_census(client):
    body = client.get("/v1/entities/swbc/evidence?audience=customer").json()
    assert [i["e_id"] for i in body["items"]] == ["E-X-005"]
    assert "distribution" not in body
    blob = repr(body)
    assert "discovery" not in blob.lower()
    assert redaction.VENDOR_NAME.lower() not in blob.lower()


def test_an_omitted_audience_is_the_customer_route(client):
    body = client.get("/v1/entities/swbc/evidence").json()
    assert body["audience"] == "customer"
    assert [i["e_id"] for i in body["items"]] == ["E-X-005"]


def test_the_internal_route_is_unchanged(client):
    body = client.get("/v1/entities/swbc/evidence?audience=internal").json()
    assert len(body["items"]) == 5 and "distribution" in body


# ── the cell drawer: same rule, and the count follows what is served ──
def _cells():
    items = [dict(i, **({"cited_as": "E-OLD-1"} if i is VENDOR else {}))
             for i in ROWS]
    return {"cells": [{
        "subcap_id": "P1C1.1.1",
        "e_ids": [i["e_id"] for i in ROWS[:4]] + ["E-OLD-1", "E-X-005"],
        "items": items, "grounded_on": 6, "synthesis": "A plain synthesis.",
    }]}


def test_the_cell_drawer_withholds_the_same_rows():
    out, report = redact_section("heatmap", "cell_evidence", _cells(), [],
                                 "customer")
    cell = out["cells"][0]
    assert [i["e_id"] for i in cell["items"]] == ["E-X-005"]
    assert report["evidence_items_withheld"] == 4
    # the chips and the drawer agree: a withheld item's id is not a chip
    assert cell["e_ids"] == ["E-X-005"]


def test_grounded_on_counts_what_is_served_not_what_was_stored():
    """Invariant 8: `grounded_on` is computed from the list beside it."""
    out, _ = redact_section("heatmap", "cell_evidence", _cells(), [],
                            "customer")
    cell = out["cells"][0]
    assert cell["grounded_on"] == len(cell["items"]) == 1


def test_the_internal_drawer_keeps_its_items_and_its_count():
    out, _ = redact_section("heatmap", "cell_evidence", _cells(), [],
                            "internal")
    assert len(out["cells"][0]["items"]) == 5
    assert out["cells"][0]["grounded_on"] == 6
