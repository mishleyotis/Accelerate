"""ET-04 — a cited id resolves to a row that carries its excerpt.

Invariant 4 is fail-closed in three parts: the id resolves, it belongs to
this entity and run, and it CARRIES A VERBATIM EXCERPT of 50-500
characters. The first two were enforced and the third was not, so a
citation could resolve to a row with an empty excerpt and render as a
chip a reader opens onto nothing — a claim of a source, with no source
behind it.

Two halves, because the excerpt appears on two sides of the boundary: the
store's row (checked against what get_evidence returns) and the payload's
own copy on the run's evidence index.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp.validation import _check_payload_excerpts
from dma_mcp.validation2 import _check_excerpt_completeness

# 122 characters, verbatim from a filing — the shape a grounded excerpt has
GOOD = ("The credit union completed a core platform migration to a cloud "
        "environment during 2025, with member servicing unaffected.")


def _row(e_id, excerpt):
    return {"e_id": e_id, "stored_id": e_id, "excerpt": excerpt,
            "published_date": "2026-03-01", "recency_band": "CURRENT"}


def test_an_empty_excerpt_is_refused_and_the_reason_names_the_id():
    out = _check_excerpt_completeness([_row("E-BCU-053", "")],
                                      {"E-BCU-053": "issue_register"})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "ET-04" and r["severity"] == "block"
    assert r["section"] == "issue_register"
    assert "E-BCU-053" in r["message"] and "EMPTY excerpt" in r["message"]


def test_a_whitespace_only_excerpt_is_the_same_refusal():
    out = _check_excerpt_completeness([_row("E-BCU-001", "   \n  ")],
                                      {"E-BCU-001": "findings"})
    assert [x["gate_id"] for x in out] == ["ET-04"]


def test_a_clipped_excerpt_is_refused_with_its_length():
    short = "Board-approved digital strategy."           # 32 chars
    out = _check_excerpt_completeness([_row("E-CC-004", short)],
                                      {"E-CC-004": "why_now"})
    assert len(out) == 1 and "32-character" in out[0]["message"]


def test_the_corrected_row_passes():
    assert _check_excerpt_completeness([_row("E-CC-004", GOOD)],
                                       {"E-CC-004": "why_now"}) == []


def test_the_payload_half_polices_its_own_copy():
    """heatmap.evidence carries the excerpt the chip renders; an empty one
    there never reaches the store check because the id resolves fine."""
    body = {"evidence": [
        {"e_id": "E-BCU-060", "excerpt": "", "tier": "T1"},
        {"e_id": "E-BCU-061", "excerpt": GOOD, "tier": "T1"},
    ]}
    out = _check_payload_excerpts("evidence", body)
    assert len(out) == 1
    assert out[0]["gate_id"] == "ET-04"
    assert out[0]["path"] == "evidence.evidence[0].excerpt"
    assert "empty excerpt" in out[0]["message"]


def test_the_payload_half_holds_the_same_50_500_band():
    long_span = "x " * 300                               # 600 chars
    out = _check_payload_excerpts("evidence", {"evidence": [
        {"e_id": "E-1", "excerpt": long_span}]})
    assert len(out) == 1 and "50-500" in out[0]["message"]
    assert _check_payload_excerpts("evidence", {"evidence": [
        {"e_id": "E-1", "excerpt": GOOD}]}) == []
