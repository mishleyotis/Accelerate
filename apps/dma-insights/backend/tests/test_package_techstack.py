"""Schema-tolerant tech-stack reader → D7.

Pins the CSV reader (A4_Tech_Stack_Map), the platforms-dict + flat
category→vendor JSON shapes, the comma/paren splitting, the precise
known-vendor prose scan, and the end-to-end fill that lifted D7 from
3/36 packages.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.services.parsers.package_techstack import (
    _clean_vendor,
    extract_tech_from_text,
    load_tech_stack,
    parse_tech_csv,
    parse_tech_json,
)

_BASE = Path(__file__).resolve().parents[1] / "tests/fixtures/dma_packages_batches"


def test_clean_vendor_splits_safely() -> None:
    assert _clean_vendor("MuleSoft, TIBCO, RabbitMQ") == ["MuleSoft", "TIBCO", "RabbitMQ"]
    # parenthetical commas must NOT over-split
    assert _clean_vendor("AWS (CloudFront, S3, Route 53)") == ["AWS"]
    assert _clean_vendor("Salesforce CRM (presence confirmed, util unknown)") == ["Salesforce CRM"]


def test_parse_tech_csv_real() -> None:
    # GESA's A4 map is the schema reference (Technology/Category/Evidence_Level).
    p = next(iter(sorted(_BASE.glob("batch_*/GESA - DMA/**/A4_Tech_Stack_Map.csv"))), None)
    if p is None:
        import pytest
        pytest.skip("GESA A4 csv fixture moved")
    rows = parse_tech_csv(p)
    assert rows
    assert all(r.vendor for r in rows)
    assert any(r.category for r in rows)
    fiserv = next((r for r in rows if "Fiserv" in r.vendor), None)
    assert fiserv is not None and fiserv.category == "Core Banking"
    assert fiserv.confidence == 1.0  # "1-Confirmed"


def test_parse_tech_json_platforms_dict(tmp_path: Path) -> None:
    p = tmp_path / "tech_inventory.json"
    p.write_text(json.dumps({
        "platforms": {
            "salesforce_fsc": {"name": "Salesforce Financial Services Cloud",
                               "evidence_level": 1, "utilization": "HIGH"},
            "mulesoft": {"name": "MuleSoft", "evidence_level": 2},
        }
    }))
    rows = parse_tech_json(p)
    # Part 9.1: rows are taxonomy-canonicalised — both resolve to the
    # Salesforce taxonomy vendor with their canonical product names.
    assert {r.product for r in rows} == {"Financial Services Cloud", "MuleSoft"}
    assert {r.vendor for r in rows} == {"Salesforce"}
    fsc = next(r for r in rows if r.product == "Financial Services Cloud")
    assert fsc.category == "salesforce_fsc" and fsc.confidence == 1.0


def test_parse_tech_json_flat(tmp_path: Path) -> None:
    p = tmp_path / "tech_stack.json"
    p.write_text(json.dumps({
        "run_id": "X", "source": "Vibe", "total_tech_items": 5,
        "zennify_priority_flags": {"salesforce_crm": True},
        "core_banking": "Temenos (presence confirmed)",
        "integration": "MuleSoft, TIBCO, RabbitMQ",
        "cloud_infrastructure": "AWS (CloudFront, S3)",
    }))
    rows = parse_tech_json(p)
    products = {r.product for r in rows}
    assert "Temenos" in products and "MuleSoft" in products and "AWS" in products
    # meta keys excluded
    assert not any(r.vendor in ("X", "Vibe", "5") for r in rows)


def test_extract_tech_from_text_precise() -> None:
    text = ("The client runs Salesforce CRM integrated via MuleSoft, with "
            "Tableau dashboards on AWS. Core banking is Temenos.")
    rows = extract_tech_from_text(text)
    products = {r.product for r in rows}
    assert {"Salesforce", "MuleSoft", "Tableau", "AWS", "Temenos"} <= products
    assert all(r.confidence == 0.3 for r in rows)  # prose = low confidence
    # no false positive on absent vendors
    assert "Workday" not in products


def test_load_tech_stack_empty(tmp_path: Path) -> None:
    assert load_tech_stack(tmp_path) == []


# ---------------------------------------------------------------------
# D1.2 — persist genericization guard
# ---------------------------------------------------------------------
# The persist layer (`persist_package`) is a large async fn that writes
# the tech-insert inline; round-tripping it needs a Postgres double.
# This pins the one-line contract by source assertion (same style as
# test_parser_warnings_round_trip): the `product` COLUMN must fall back
# to the specific `vendor`, never the generic `category` ("CRM",
# "Core Banking") which buried the real vendor on ~169 items.

_PERSIST_SRC = (
    Path(__file__).resolve().parents[1]
    / "app" / "services" / "parsers" / "package_persist.py"
).read_text(encoding="utf-8")


def test_persist_product_column_falls_back_to_vendor_not_category() -> None:
    """`product` must be `(ts.product or ts.vendor)`. A `ts.category`
    fallback genericizes the title ("CRM" instead of "Salesforce")."""
    assert "(ts.product or ts.vendor)[:255]" in _PERSIST_SRC, (
        "persist tech-insert product column must fall back to ts.vendor, "
        "not ts.category — the category genericizes ~169 items."
    )
    # Guard the regression: the product param must NOT chain category.
    assert "(ts.product or ts.category or ts.vendor)" not in _PERSIST_SRC, (
        "ts.category must not sit between product and vendor in the "
        "product column — it shadows the specific vendor."
    )


def test_persist_tech_id_keeps_category_for_dedup_stability() -> None:
    """The dedup KEY (`tech_id`) deliberately keeps the category
    fallback so a row's identity is stable across re-ingests even when
    `product` is absent. Changing it would re-key existing rows and
    break the ON CONFLICT dedup — so this asymmetry is intentional."""
    assert "f\"{ts.vendor}_{ts.product or ts.category or ''}\"" in _PERSIST_SRC, (
        "tech_id must retain its (product or category) fallback so the "
        "dedup key stays stable across re-ingests."
    )
