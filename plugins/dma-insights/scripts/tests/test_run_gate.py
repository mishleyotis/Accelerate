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


def test_g3_asks_the_refresh_queue_for_the_internal_audience(monkeypatch):
    """The queue 403s to any audience but `internal`, and an OMITTED audience
    default-denies to `customer` (invariant 5). Called bare, this returned 403
    on every client, the queue was never read, and every serving client was
    skipped — including ones a human had asked to refresh.

    The two tests above cannot see it: their `api_get` stub matches on the path
    substring and discards the rest, so a missing query parameter is invisible
    to them. This one captures the path.
    """
    seen = []

    def _api(path):
        seen.append(path)
        return ((200, {"requested": [], "due": []})
                if "refresh-queue" in path else (200, {}))

    monkeypatch.setattr(run_gate, "api_get", _api)
    run_gate.g3_serving_state("acme-credit-union")
    queue_calls = [p for p in seen if "refresh-queue" in p]
    assert queue_calls == ["/v1/ops/refresh-queue?audience=internal"]


def test_g3_never_claims_no_refresh_is_due_when_it_could_not_look(monkeypatch):
    """"Nobody looked" and "nothing is due" must stay distinguishable.

    The old branch fell through to "no refresh is requested or due" on ANY
    non-200 — a statement of fact it had not established, and the sentence
    that made the 403 invisible for the life of the queue.
    """
    monkeypatch.setattr(run_gate, "api_get", lambda path: (
        (403, {"error": "audience_forbidden"}) if "refresh-queue" in path
        else (200, {})))
    verdict, detail = run_gate.g3_serving_state("acme-credit-union")
    assert verdict == "produce"
    assert "UNREADABLE" in detail and "403" in detail
    assert "no refresh is requested or due" not in detail


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


# ── the walk reaches the whole queue, not a hardcoded eight ──
#
# Owner, 2026-08-22: "ensure that no clients are hardcoded, that it processes
# clients who have not been processed that meet package vetting. Right now it
# is so confined to the list of 10."
#
# It was: LEARNERS + STRESS named eight, minus two held out. The pending queue
# holds 286 runs across 172 entities, so 164 vetted, unprocessed clients could
# never be reached however long the routine ran — and the walk reported
# "sequence complete" having never looked at them.


def _queued(display_id, completed_at="2026-08-17", live_claim=False, **over):
    row = _pending(display_id=display_id, run_id=display_id + "-run",
                   request_id="REQ-" + display_id)
    row["completed_at"] = completed_at
    row["claim"] = {"live": True} if live_claim else None
    row.update(over)
    return row


def test_the_queue_supplies_candidates_no_list_names():
    """The whole point. An entity nobody wrote down still gets gated."""
    pending = [_queued("never-heard-of-this-bank")]
    order = run_gate.queue_order(pending, prefer=[])
    assert order == ["never-heard-of-this-bank"]


def test_the_learner_order_still_leads():
    """It is a curriculum, and the curve it measures is only readable if the
    order holds. Preference, not a fence — and only over what the queue
    actually offers: a learner with nothing pending is not a candidate."""
    pending = [_queued("zzz-other-bank", completed_at="2026-08-20"),
               _queued("t-rowe-price-group-inc", completed_at="2026-01-01")]
    order = run_gate.queue_order(pending, prefer=run_gate.LEARNERS)
    assert order[0] == "t-rowe-price-group-inc", (
        "the learner leads even though its assessment is seven months older")
    assert order[1] == "zzz-other-bank"
    assert len(order) == 2, "learners with nothing pending are not candidates"


def test_the_held_out_control_is_never_admitted_from_the_queue():
    """Widening the source of candidates must not widen what may be produced.
    HELD_OUT subtracts, which is why it survives the change."""
    pending = [_queued("bok-financial"), _queued("bok-financial-corporation"),
               _queued("fine-bank")]
    order = run_gate.queue_order(pending, prefer=run_gate.LEARNERS)
    assert "bok-financial" not in order
    assert "bok-financial-corporation" not in order
    assert "fine-bank" in order


def test_an_entity_under_a_live_claim_is_not_offered():
    """A claim is an entity-level fact; offering it puts two producers on one
    client's six pages."""
    pending = [_queued("busy-bank", live_claim=True), _queued("free-bank")]
    order = run_gate.queue_order(pending, prefer=[])
    assert order == ["free-bank"]


def test_the_newest_assessment_comes_first():
    pending = [_queued("older", completed_at="2026-01-02"),
               _queued("newer", completed_at="2026-08-17")]
    assert run_gate.queue_order(pending, prefer=[])[0] == "newer"


def test_no_entity_is_offered_twice():
    pending = [_queued("t-rowe-price-group-inc")]
    order = run_gate.queue_order(pending, prefer=run_gate.LEARNERS)
    assert order.count("t-rowe-price-group-inc") == 1


def test_a_failing_candidate_no_longer_blocks_the_queue(monkeypatch, capsys):
    """The other half of "confined". Any G1/G2/G4 failure used to return
    immediately, so one client with a stub bundle blocked every entity behind
    it until a human noticed."""
    # broken-bank must be gated FIRST or the test proves nothing, so give it
    # the newer assessment — the queue's own ordering rule.
    pending = [_queued("broken-bank", completed_at="2026-08-20"),
               _queued("good-bank", completed_at="2026-08-01")]
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"pending": pending})

    def fake_evaluate(_pending, display_id):
        ok = display_id == "good-bank"
        return {
            "G1_ingested": {"ok": ok, "detail": "stub" if not ok else "fine"},
            "G2_raw_package": {"ok": True, "detail": "traced"},
            "G3_serving": {"ok": True, "detail": "not serving"},
            "G4_non_duplicate": {"ok": True, "detail": "no twin"},
            "run_id": "good-run" if ok else None,
        }

    monkeypatch.setattr(run_gate, "evaluate", fake_evaluate)
    assert run_gate.pick([]) == 0
    out = capsys.readouterr().out
    assert "GATE: PRODUCE good-bank run good-run" in out
    assert "walked past 1" in out, "what was skipped must be visible"
    assert "broken-bank" in out


def test_every_failure_is_still_printed_with_its_gate(monkeypatch, capsys):
    """"Never silently advance past a failure" is kept in the half that
    matters: nothing is silent. Only the blocking is dropped."""
    pending = [_queued("broken-bank")]
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"pending": pending})
    monkeypatch.setattr(run_gate, "evaluate", lambda p, d: {
        "G1_ingested": {"ok": False, "detail": "parsed to only 3 scored cells"},
        "G2_raw_package": {"ok": True, "detail": "traced"},
        "G3_serving": {"ok": True, "detail": "not serving"},
        "G4_non_duplicate": {"ok": True, "detail": "no twin"},
        "run_id": None})
    assert run_gate.pick([]) == 1
    out = capsys.readouterr().out
    assert "G1_ingested: FAIL — parsed to only 3 scored cells" in out
    assert "skipped broken-bank: failed G1_ingested" in out
    assert "not a reason to stop looking" in out


def test_an_empty_queue_says_so_rather_than_claiming_completion(monkeypatch, capsys):
    monkeypatch.setattr(run_gate, "mcp_call", lambda tool, args: {"pending": []})
    assert run_gate.pick(run_gate.LEARNERS) == 1
    assert "offered no unclaimed entity" in capsys.readouterr().out


def test_the_walk_is_bounded_so_selection_cannot_eat_the_session(monkeypatch):
    """A firing produces ONE client. Gating hundreds to find it would spend
    the session on selection; the next firing continues from here."""
    pending = [_queued(f"bank-{i:03d}") for i in range(200)]
    seen = []
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"pending": pending})

    def fake_evaluate(_p, display_id):
        seen.append(display_id)
        return {g: {"ok": True, "detail": "-"} for g in
                ("G1_ingested", "G2_raw_package", "G3_serving",
                 "G4_non_duplicate")} | {"run_id": None}

    monkeypatch.setattr(run_gate, "evaluate", fake_evaluate)
    run_gate.pick([], max_candidates=5)
    assert len(seen) == 5
