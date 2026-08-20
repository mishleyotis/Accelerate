"""The pre-synthesis gate: hallucination-shaped inputs are refused by name.

The live acceptance test already ran (all four gates PASS on the real
T. Rowe Price run, and G2 caught the real folder-naming convention on its
first execution). What pins here is the refusal logic — the owner's rule
is that synthesis NEVER starts on an unverified chain, so the failure
paths are the product.
"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import run_gate  # noqa: E402


def _pending(**over):
    row = {"run_id": "r1" * 16, "display_id": "acme-credit-union",
           "request_id": "REQ-1", "status": "INGESTED", "run_seq": 1,
           "is_latest_for_request": True}
    row.update(over)
    return row


def test_g1_refuses_a_stub_bundle(monkeypatch):
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"scored_cells": 3, "evidence": []})
    run_id, detail = run_gate.g1_ingested([_pending()], "acme-credit-union")
    assert run_id is None
    assert "stub" in detail and str(run_gate.MIN_SCORED_CELLS) in detail


def test_g1_refuses_when_no_ingested_latest_run_exists():
    rows = [_pending(status="PROMOTED"),
            _pending(is_latest_for_request=False)]
    run_id, detail = run_gate.g1_ingested(rows, "acme-credit-union")
    assert run_id is None and "no INGESTED" in detail


def test_g1_passes_a_substantial_bundle(monkeypatch):
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"scored_cells": 595,
                                            "evidence": [1] * 876,
                                            "ccg_catalog_version": "v7.0"})
    run_id, detail = run_gate.g1_ingested([_pending()], "acme-credit-union")
    assert run_id and "595 scored cells" in detail


def test_g3_skips_a_client_already_serving_and_current(monkeypatch):
    monkeypatch.setattr(run_gate, "api_get", lambda path: (
        (200, {"requested": [], "due": []}) if "refresh-queue" in path
        else (200, {})))
    verdict, detail = run_gate.g3_serving_state("acme-credit-union")
    assert verdict == "skip" and "re-producing" in detail


def test_g3_produces_when_the_refresh_queue_names_the_client(monkeypatch):
    monkeypatch.setattr(run_gate, "api_get", lambda path: (
        (200, {"requested": [{"display_id": "acme-credit-union"}], "due": []})
        if "refresh-queue" in path else (200, {})))
    verdict, detail = run_gate.g3_serving_state("acme-credit-union")
    assert verdict == "produce" and "refresh" in detail


def test_g3_produces_a_client_not_serving(monkeypatch):
    monkeypatch.setattr(run_gate, "api_get", lambda path: (404, None))
    verdict, detail = run_gate.g3_serving_state("acme-credit-union")
    assert verdict == "produce" and "first production" in detail


def test_g4_refuses_a_shared_request_twin():
    rows = [_pending(),
            _pending(display_id="acme-cu", request_id="REQ-1")]
    ok, detail = run_gate.g4_non_duplicate(rows, "acme-credit-union")
    assert not ok and "acme-cu" in detail and "adjudicate" in detail


def test_g4_refuses_a_prefix_twin():
    rows = [_pending(),
            _pending(display_id="acme-credit-union-2", request_id="REQ-9")]
    ok, detail = run_gate.g4_non_duplicate(rows, "acme-credit-union")
    assert not ok


def test_g4_held_out_twins_do_not_block():
    rows = [_pending(display_id="bok-financial-corporation"),
            _pending(display_id="bok-financial", request_id="REQ-1")]
    ok, _ = run_gate.g4_non_duplicate(rows, "bok-financial-corporation")
    # held-out ids never reach evaluation, but the helper must not crash on
    # them and must not name a held-out id as a twin of anything else
    rows2 = [_pending(), _pending(display_id="bok-financial",
                                  request_id="REQ-2")]
    ok2, detail2 = run_gate.g4_non_duplicate(rows2, "acme-credit-union")
    assert ok2, detail2


def test_the_learner_order_is_the_d7_sequence():
    assert run_gate.LEARNERS[0] == "t-rowe-price-group-inc"
    assert run_gate.HELD_OUT == {"bok-financial-corporation", "bok-financial"}
