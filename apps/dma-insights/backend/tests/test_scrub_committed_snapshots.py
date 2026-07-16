"""D4 — committed-snapshot scrubber (pure-logic).

Pins the four defect-class transforms applied to the committed
startup-data JSON: parser-warning truncation (drops errors.pydantic.dev),
malformed source_url repair, all-zero derived-SCQA drop, and narrative
markdown scrub via `_scrub_node`.
"""
from __future__ import annotations

from app.scripts.scrub_committed_snapshots import (
    _clean_source_url,
    _clean_warning,
    _scrub_node,
)


def test_clean_warning_drops_pydantic_url_blob() -> None:
    raw = (
        "evidence_index.json: 1 validation error for EvidenceRow\n"
        "e_id\n  Input should be a valid string [type=string_type]\n"
        "    For further information visit https://errors.pydantic.dev/2.9/v/x"
    )
    out = _clean_warning(raw)
    assert out == "evidence_index.json: 1 validation error for EvidenceRow"
    assert "errors.pydantic.dev" not in out
    assert "\n" not in out
    assert len(out) <= 200


def test_clean_source_url_strips_enrichment_parenthetical() -> None:
    assert (
        _clean_source_url("https://tcbk.com (Vibe Prospecting enrichment)")
        == "https://tcbk.com"
    )
    # a clean URL is untouched
    assert _clean_source_url("https://sec.gov/x") == "https://sec.gov/x"
    # a non-URL descriptor is left alone (not a malformed URL)
    desc = "N/A — assessed from exhaustive proxy search"
    assert _clean_source_url(desc) == desc


def test_scrub_node_truncates_warnings_and_repairs_url() -> None:
    doc = {
        "parser_warnings": {
            "warning_0": "ok plain warning",
            "warning_1": "x: ValidationError\nvisit https://errors.pydantic.dev/y",
        },
        "acquisitions": [
            {"source_url": "https://acme.io (LeadIQ enrichment)"},
        ],
    }
    out, changes = _scrub_node(doc)
    assert changes == 2
    assert out["parser_warnings"]["warning_1"] == "x: ValidationError"
    assert out["acquisitions"][0]["source_url"] == "https://acme.io"


def test_scrub_node_drops_all_zero_scqa() -> None:
    doc = {"narrative": {"scqa_md": (
        "1. Situation\nAcme scores 0.00 overall across 17 capability "
        "categories. Relative strengths: Strategy (0.0)."
    )}}
    out, changes = _scrub_node(doc)
    assert changes == 1
    assert out["narrative"]["scqa_md"] is None


def test_scrub_node_dejargons_per_pillar_dict_values() -> None:
    doc = {"narrative": {"per_pillar_md": {
        "P1": "Pillar Weight: 25% | Pillar Score: 2.71 | Level: M3",
    }}}
    out, changes = _scrub_node(doc)
    assert changes == 1
    v = out["narrative"]["per_pillar_md"]["P1"]
    assert "M3" not in v and "Pillar Score" not in v
    assert "maturity level 3" in v and "Score: 2.71" in v


def test_scrub_node_is_idempotent() -> None:
    doc = {"narrative": {
        "issue_register_md": "Findings flow through the Severity-to-Maturity "
                             "Cap Matrix and cite E-091, E-099 (P1C1).",
        "per_pillar_md": {"P1": "Pillar Score: 2.71 | Level: M3"},
    }}
    once, c1 = _scrub_node(doc)
    twice, c2 = _scrub_node(once)
    assert c1 > 0
    assert c2 == 0, "second pass must be a no-op (idempotent)"
    assert once == twice


def test_scrub_node_leaves_clean_doc_unchanged() -> None:
    doc = {"narrative": {"scqa_md": "Acme is a healthy regional bank."},
           "parser_warnings": {"warning_0": "institution_name derived"}}
    out, changes = _scrub_node(doc)
    assert changes == 0
    assert out == doc
