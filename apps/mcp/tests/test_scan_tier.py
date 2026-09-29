"""ET-11 — a machine technographic scan is a T1 source.

Measured 28-09-2026 (QA audit F-J04-015): on the staged goeasy heatmap 5 of
6 technographic rows carried tier T3. The engine's ledger refuses that
shape at the write; this is the submit-time twin over the rows
`get_evidence` resolved. The tokens the server matches on are a copy of the
engine's, and the last test holds the copy equal to its owner.
"""
import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dma_mcp import validation2 as V
from dma_mcp.gates import GATES
from dma_mcp.validation2 import _check_scan_tier

_ENGINE_CONTRACT = (Path(__file__).resolve().parents[3] / "plugins" / "dma-insights"
                    / "skills" / "dma-research" / "engine" / "contract.py")


def _row(e_id, tier, name, url="https://x.example/p"):
    return {"e_id": e_id, "stored_id": e_id, "excerpt": "x" * 80, "tier": tier,
            "claim_type": "INFERENCE", "source_name": name, "source_url": url,
            "published_date": "2025-03-01", "recency_band": "CURRENT"}


def test_a_scan_at_t3_is_refused_and_the_reason_names_row_provider_tier_and_rule():
    out = _check_scan_tier(
        [_row("E-GSY-085", "T3", "appsruntheworld.com technographic customer record",
              "https://www.appsruntheworld.com/customers-database/customers/view/goeasy")],
        {"E-GSY-085": "evidence"})
    assert len(out) == 1
    r = out[0]
    assert r["gate_id"] == "ET-11" and r["severity"] == "block"
    assert r["path"] == "evidence.e_ids"
    assert "E-GSY-085" in r["message"] and "T3" in r["message"] and "T1" in r["message"]
    assert "appsruntheworld" in r["message"]


def test_a_scan_at_t1_and_every_non_scan_row_pass():
    rows = [_row("E-1", "T1", "BuiltWith technology profile", "https://builtwith.com/x"),
            _row("E-2", "T3", "Trade press"),
            _row("E-3", "T4", "Internal memo on the scanning programme"),
            _row("E-4", "T2", "Annual report 2025")]
    assert _check_scan_tier(rows, {r["e_id"]: "evidence" for r in rows}) == []


def test_an_untiered_scan_is_refused_too():
    out = _check_scan_tier([_row("E-9", None, "Hubbl scan 2026-06")], {"E-9": "evidence"})
    assert len(out) == 1 and "untiered" in out[0]["message"]


def test_every_offending_row_is_named_once():
    rows = [_row(f"E-{i}", "T3", "Wappalyzer profile") for i in range(4)]
    out = _check_scan_tier(rows, {r["e_id"]: "cell_evidence" for r in rows})
    assert sorted(o["message"].split()[0] for o in out) == sorted(r["e_id"] for r in rows)


def test_et11_is_registered_in_the_gate_census_with_the_five_field_shape():
    assert "ET-11" in GATES
    name, plain, what, why, on_fail = GATES["ET-11"]
    assert on_fail == "block" and plain is None and "T1" in what


def test_the_servers_copy_of_the_tokens_equals_the_engines_owner():
    """RULE_HELD_IN_TWO_PLACES_DRIFTS: the engine's contract owns the
    vocabulary; the server carries a copy because the two are separate
    images. This is the test that makes the copy safe to carry."""
    spec = importlib.util.spec_from_file_location("engine_contract", _ENGINE_CONTRACT)
    assert spec is not None, _ENGINE_CONTRACT
    src = _ENGINE_CONTRACT.read_text(encoding="utf-8")
    # read the literals rather than import: the engine package pulls in
    # its own tree, and the point is the text the two files carry
    import ast
    tree = ast.parse(src)
    owner = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = getattr(node.targets[0], "id", None)
            if tgt in ("SCAN_TIER", "SCAN_SOURCE_TOKENS", "FACT_TIERS"):
                owner[tgt] = ast.literal_eval(node.value)
    assert owner["SCAN_TIER"] == V.SCAN_TIER
    assert owner["SCAN_SOURCE_TOKENS"] == V.SCAN_SOURCE_TOKENS
    assert owner["FACT_TIERS"] == V.FACT_TIERS
