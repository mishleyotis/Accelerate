"""Two registry defects that only look like small ones.

AUD-0028 · `evidence_origin_t` has four labels and the INSERT hardcoded one,
so `internal` could never be written — migration 0045 records that no row
has ever carried it.
AUD-0029 · and an internal source with no public URL was silently demoted
from FACT to INFERENCE, which hides that internal material entered the run.
AUD-0125 · `identifiers.find_fabricated()` was written to reject a
client-supplied id and was called nowhere in production.
"""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import register                       # noqa: E402
from dma_mcp.identifiers import find_fabricated    # noqa: E402


def test_all_four_origin_labels_are_reachable():
    assert register._ORIGINS == ("package", "producer", "connector", "internal")


def test_the_insert_no_longer_hardcodes_an_origin():
    src = Path(register.__file__).read_text()
    stmt = src[src.index("INSERT INTO evidence_index"):]
    stmt = stmt[:stmt.index("ON CONFLICT")]
    assert "'producer'" not in stmt, \
        "the origin column is still a literal, so `internal` is unreachable"


def test_the_origin_argument_is_read_and_validated():
    src = Path(register.__file__).read_text()
    assert 'item.get("origin")' in src
    assert "not in _ORIGINS" in src


def test_an_internal_source_keeps_its_claim_type_and_is_labelled():
    """The demotion is right for an unsourced PUBLIC claim and wrong for an
    internal one: a client's own board pack is evidence of a different kind,
    not weaker evidence."""
    src = Path(register.__file__).read_text()
    branch = src[src.index("if not source_url and claim == \"FACT\":"):]
    branch = branch[:branch.index("\n\n")]
    assert 'origin == "internal"' in branch
    assert "KEPT" in branch
    assert "redacted from every" in branch


def test_the_public_demotion_still_happens_and_names_the_alternative():
    src = Path(register.__file__).read_text()
    assert "downgraded to \"\n                \"INFERENCE" in src or \
           "downgraded to " in src
    assert "origin='internal'" in src


# ── AUD-0125 · the fabrication check is wired ───────────────────────────

def test_find_fabricated_is_called_from_the_validator():
    src = Path(__file__).resolve().parents[1].joinpath(
        "dma_mcp", "validation2.py").read_text()
    assert "find_fabricated" in src
    assert "_check_prose_citations_resolve" in src
    # and it is REACHED — outside the `if cited:` block, because a payload
    # whose only references are in prose has an empty `cited` map.
    call = src.index("reasons.extend(_check_prose_citations_resolve")
    guard = src.index("    if cited:")
    block_end = src.index("    # Prose citations, OUTSIDE")
    assert guard < block_end <= call


def test_find_fabricated_keeps_claim_order_and_dedupes():
    out = find_fabricated(["E-047", "E-CC-999", "E-047", "E-001"],
                          {"E-001"})
    assert out == ["E-047", "E-CC-999"]


def test_a_prose_citation_is_collected_from_a_plain_string():
    from dma_mcp.validation2 import _walk_strings
    payload = {"insights": {"insights": [
        {"body": "The board pack names it [E-047], per the 2025 filing."}]}}
    found = [(p, t) for p, t in _walk_strings(payload, "")]
    assert any("E-047" in t for _, t in found)
    from dma_mcp.identifiers import find_ids
    assert "E-047" in find_ids(found[0][1])


# ── AUD-0045 · a self-REJECTED item is not a recommendation ─────────────

def test_ag01_reads_the_verdict_it_used_to_only_count():
    from dma_mcp import validation2 as V
    src = Path(V.__file__).read_text()
    assert "_REJECTING_VERDICTS" in src and "_ACCEPTING_VERDICTS" in src
    assert "REJECT" in V._REJECTING_VERDICTS
    assert "SHIP" in V._ACCEPTING_VERDICTS
    # and the verdict is READ, not merely present
    blk = src[src.index("# ── AG-01"):src.index("# ── AG-03")]
    assert "_REJECTING_VERDICTS" in blk
    assert "rl.get(\"verdict\")" in blk


def test_the_two_vocabularies_do_not_overlap():
    from dma_mcp import validation2 as V
    assert not (V._ACCEPTING_VERDICTS & V._REJECTING_VERDICTS)


# ── AUD-0046 · the grain lock can see the field the contract names ──────

def test_cg07_reads_dma_impact_current():
    """The contract says of dma_impact[]: 'current MUST equal what the
    heatmap serves — assert it'. No key in _SCORE_KEYS was named `current`,
    so the one field the contract tells you to assert was invisible."""
    from dma_mcp import validation2 as V
    assert "current" in V._SCORE_KEYS
    assert "target" not in V._SCORE_KEYS, (
        "a target is where the client is GOING; comparing it to today's "
        "served figure would reject every improvement")


# ── AUD-0030 · the intake record has a reader ───────────────────────────

def test_get_run_progress_reports_what_the_intake_could_not_read():
    from dma_mcp import claims
    src = Path(claims.__file__).read_text()
    assert "parser_observations" in src
    assert "intake_observations" in src
    assert "GRANT SELECT ON parser_observations TO svc_mcp" in (
        Path(__file__).resolve().parents[3]
        / "migrations" / "versions"
        / "0057_the_intake_record_gets_a_reader.py").read_text()
