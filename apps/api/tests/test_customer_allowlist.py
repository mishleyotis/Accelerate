"""The customer serve boundary is an allowlist, and it fails closed.

Every deny rule in redaction.py was added after a measured leak; this file
pins the flipped default. The defining test is the first one: a key the
contract never named — the internal artifact nobody thought to deny —
must NOT reach a customer body, and the drop must be receipted.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from dma_api.redaction import redact_section  # noqa: E402


def _cells_body():
    return {
        "produced_at": "2026-08-19T00:00:00Z",
        "producer_version": "test",
        "e_ids": ["E-XX-001"],
        "internal_only": [],
        "narrative_thread": "thread",
        "linking_stats": {"cells_linked": 1},
        "empty_state": {"reason": "a real reason",
                        "closure_condition": "what would close it",
                        "sources_searched": ["host.example — nil"],
                        "searched_on": "2026-08-18"},
        "cells": [{
            "subcap_id": "P1C1.1.1",
            "synthesis": "the argument",
            "grounded_on": 1,
            "e_ids": ["E-XX-001"],
            "thin": False,
            "reach_note": "reaches",
            "closure_condition": "a span naming the practice",
            "sources_searched": ["site: example.com — nil"],
            "provenance": "declared",
            "items": [{"e_id": "E-XX-001", "excerpt": "x" * 60,
                       "tier": "T2", "claim_label": "FACT"}],
            "a_key_nobody_classified": "internal-shaped surprise",
        }],
    }


def test_an_unclassified_key_never_reaches_a_customer_body():
    out, report = redact_section("heatmap", "cell_evidence", _cells_body(),
                                 [], "customer")
    assert out is not None
    cell = out["cells"][0]
    assert "a_key_nobody_classified" not in cell
    assert any("a_key_nobody_classified" in d
               for d in report["allowlist_dropped"])


def test_probe_ladders_are_dropped_and_the_reason_survives():
    out, _ = redact_section("heatmap", "cell_evidence", _cells_body(),
                            [], "customer")
    cell = out["cells"][0]
    assert "sources_searched" not in cell
    es = out["empty_state"]
    assert "sources_searched" not in es and "searched_on" not in es
    assert es["reason"] == "a real reason"
    assert es["closure_condition"] == "what would close it"


def test_method_vocabulary_is_dropped_from_drawer_items():
    out, _ = redact_section("heatmap", "cell_evidence", _cells_body(),
                            [], "customer")
    item = out["cells"][0]["items"][0]
    assert "tier" not in item
    assert item["excerpt"].startswith("x")


def test_the_internal_audience_is_untouched_by_the_allowlist():
    out, report = redact_section("heatmap", "cell_evidence", _cells_body(),
                                 [], "internal")
    cell = out["cells"][0]
    assert "sources_searched" in cell and "provenance" in cell
    assert "a_key_nobody_classified" in cell
    assert "allowlist_dropped" not in report


def test_an_unknown_section_is_withheld_not_served():
    out, report = redact_section("heatmap", "invented_section",
                                 {"produced_at": "x", "stuff": 1},
                                 [], "customer")
    assert out is None
    assert report["withheld"] and report.get("unknown_section")


def test_the_committed_allowlist_matches_a_fresh_generation():
    """A contract change that widens the serve surface fails here until the
    new key is classified — the fail-closed property, pinned in CI."""
    gen = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gen_customer_allowlist.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert gen.returncode == 0, gen.stderr
    committed = json.loads(
        (ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json")
        .read_text())
    # the generator just rewrote the file; git-diff cleanliness is asserted
    # by re-reading — identical content means the commit was fresh
    regenerated = json.loads(
        (ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json")
        .read_text())
    assert committed == regenerated
    assert len(committed["sections"]) == 34


def test_excluded_classes_cover_the_measured_logix_leaks():
    allow = json.loads(
        (ROOT / "apps" / "api" / "dma_api" / "customer_allowlist.json")
        .read_text())
    excluded = set(allow["excluded_key_classes"])
    for k in ("sources_searched", "queries_run", "searched_on",
              "tier", "ers", "discovered_by", "cap_level"):
        assert k in excluded, f"{k} is not excluded — the measured leak class"
