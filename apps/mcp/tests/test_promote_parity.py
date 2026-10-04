"""CG-PAR — promote holds the staged pages to the committed gold shape.

RC-02 (SWBC gold audit, 2026-10-04): no parity measurement ever touched run
7968492e before it was promoted. Gate J ran only in CI against a synthetic
pair, compared top-level keys, and called any non-empty list filled. Run
after the fact against the gold, the run's firmographics stated 4 of 10
fields (6 held) where every gold run states at least 14 of 15; its sentiment
carried no gap_analysis where every gold run carries one.

These tests drive promote_run itself with a payload SHAPED like that run
(placeholder values — the gate reads shape) against the real committed gold.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _promote_fake import ENV, RUN, Conn, skeleton, wrote_anything  # noqa: E402

from dma_mcp.promote import promote_run  # noqa: E402

pytestmark = pytest.mark.real_parity
ROOT = Path(__file__).resolve().parents[3]


def _pc():
    """Imported per test so the promote-driven case runs (and fails on its
    assertion) against a connector that predates the module."""
    from dma_mcp import promote_checks
    return promote_checks


def _par():
    from dma_mcp import parity
    return parity


def _field(stated):
    return {"field": "f", "value": "v" if stated else None, "unit": "u",
            "as_of": "2025" if stated else None, "confidence": "HIGH",
            "quarantined": not stated, "recency_band": "CURRENT",
            "quarantine_reason": None if stated else "held",
            "source_e_id": "E-1"}


def swbc_shaped() -> dict:
    """The skeleton, with the two overview sections the audit measured."""
    pages = skeleton()
    pages["overview"]["firmographics"] = {
        **ENV, "e_ids": ["E-1"], "narrative_thread": "t " * 50,
        "fields": [_field(True)] * 4 + [_field(False)] * 6,
        "undated_pct": 0.9, "identity_mismatch": False}
    pages["overview"]["sentiment"] = {
        **ENV, "e_ids": ["E-1"], "narrative_thread": "s " * 50,
        "bars": [{"source": "s", "audience": "customer", "rating": 4.9,
                  "scale": "1-5", "n": 10, "as_of": "2025", "e_id": "E-1",
                  "url": "u", "trend_vs_prior": None}],
        "themes": [{"theme": "t", "audience": "customer",
                    "cap_statement": "c", "mapped_subcap_ids": ["P1C1.1.1"]}]}
    return pages


def test_promote_of_a_swbc_shaped_run_returns_a_cg_par_refusal():
    conn = Conn(swbc_shaped())
    out = promote_run(conn, RUN)
    assert out["promoted"] is False, "a structurally thin run promoted"
    assert out["blocking_by_gate"]["overview"].get("CG-PAR"), \
        out["blocking_by_gate"]
    assert out["promote_checks"]["parity"]["gold_runs"] == [
        "gold-40971653", "gold-c1351d25", "gold-d7ed1d90"]
    assert not wrote_anything(conn), "the refusal precedes every writer"


def test_the_refusal_names_the_structural_gaps_and_warns_on_the_share():
    """Owner decision B: the held share beyond the cap and the missing
    gap_analysis refuse; the stated share against the gold is a warning."""
    live = {p: {"payload": b} for p, b in swbc_shaped().items()}
    reasons, report = _pc().gold_parity(live, sub_vertical="CU")
    firmo = [r for r in reasons["overview"]
             if r["path"] == "overview.firmographics.fields"]
    assert firmo and firmo[0]["kind"] == "held_beyond_cap", \
        reasons["overview"][:5]
    gap = [r for r in reasons["overview"]
           if r["path"] == "overview.sentiment.gap_analysis"]
    assert gap and gap[0]["kind"] == "key_absent"
    assert "gold-40971653" in gap[0]["message"]
    share = [w for w in report["warnings"]
             if w["path"] == "overview.firmographics.fields"
             and w["kind"] == "stated_share"]
    assert share and share[0]["severity"] == "warn", report["warnings"][:5]


def test_a_gold_run_meets_cg_par():
    """Positive control, leave-one-out: each gold run against the others."""
    gold = _par().load_gold()
    for label, pages in _par().gold_runs(gold).items():
        res = _par().check_run(pages, gold, exclude=[label],
                               sub_vertical=gold["runs"][label]["sub_vertical"])
        assert label not in res["compared_against"]
        assert res["blocking"] == [], (label, res["blocking"][:3])


def test_a_parity_check_that_cannot_run_refuses(monkeypatch):
    """CHECK_NEVER_RAN_READS_AS_UNKNOWN: a missing gold is not _par()."""
    def boom(*a, **k):
        raise FileNotFoundError("surface_gold.json")
    monkeypatch.setattr(_par(), "check_run", boom)
    reasons, report = _pc().gold_parity(
        {p: {"payload": b} for p, b in skeleton().items()})
    assert reasons and reasons["overview"][0]["gate_id"] == "CG-PAR"
    assert "unchecked is not parity" in reasons["overview"][0]["message"]


def test_peers_identified_not_scored_are_disclosed_not_refused():
    """Owner (settled): peers may be identified and not scored. With no peer
    figure anywhere in the run, the peer-comparison nulls are one fact."""
    gold = _par().load_gold()
    pages = json.loads(json.dumps(_par().gold_runs(gold)["gold-40971653"]))
    pillars = pages["overview"]["sections"]["scores"]["data"]["o"]["pillars"]
    i = pillars["keys"].index("peer_median")
    pillars["rows"] = [r[:i] + "0" + r[i + 1:] for r in pillars["rows"]]
    res = _par().check_run(pages, gold, exclude=["gold-40971653"],
                           sub_vertical="CU")
    assert not any(g["key"] == "pillars[].peer_median"
                   for g in res["blocking"] + res["warnings"])
    assert any(d["key"] == "pillars[].peer_median" for d in res["disclosed"])


def test_the_deployed_connector_carries_the_gold_it_checks_against():
    """The promote path reads dma_mcp/surface_gold.json because fixtures/ is
    not in the connector's image; it must be the committed gold."""
    assert _par().gold_path().read_bytes() == \
        (ROOT / "fixtures" / "surface_gold.json").read_bytes()
