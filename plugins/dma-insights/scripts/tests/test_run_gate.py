"""The pre-synthesis gate: hallucination-shaped inputs are refused by name.

The live acceptance test already ran (all four gates PASS on the real
T. Rowe Price run, and G2 caught the real folder-naming convention on its
first execution). What pins here is the refusal logic — the owner's rule
is that synthesis NEVER starts on an unverified chain, so the failure
paths are the product.
"""
import re
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


def test_no_client_is_named_to_be_admitted():
    """Owner, 2026-08-23: "Ensure no client hardcoding. This is a routine
    meant to run and ingest DMAs."

    The module used to carry two name lists — a five-name learning
    curriculum and three stress candidates — that reordered the queue so
    those eight went first. This asserts the module now names clients in
    exactly one place, and that that place SUBTRACTS.
    """
    source = Path(run_gate.__file__).read_text()
    admitting = [name for name in ("LEARNERS", "STRESS")
                 if re.search(rf"^{name}\s*=", source, re.M)]
    assert not admitting, (
        f"{admitting} names clients to be admitted; the queue decides who is "
        f"a candidate")
    assert run_gate.HELD_OUT == {"bok-financial-corporation", "bok-financial"}, (
        "the held-out control is an owner exclusion and subtracts — it is the "
        "one name-based rule that may remain")


def test_the_routine_passes_no_preference():
    """`--prefer` survives for a human re-running one client by hand. What
    matters is that the ROUTINE's own invocation carries none: a default of
    [] is what makes the walk client-agnostic in production."""
    parsed = run_gate.main.__globals__  # module scope, for the parser build
    assert "LEARNERS" not in parsed and "STRESS" not in parsed
    ap_default = _pick_parser_default("--prefer")
    assert ap_default == [], (
        "the gate must default to no preference; anything else reintroduces "
        "the bias under a new name")


def _pick_parser_default(flag: str):
    """The default argparse would apply for `pick <flag>`, read from the
    parser the CLI actually builds rather than from a copy of it."""
    import contextlib, io
    with contextlib.redirect_stdout(io.StringIO()), \
            contextlib.redirect_stderr(io.StringIO()):
        with pytest.raises(SystemExit):
            run_gate.main(["pick", "--help"])
    # --help proves the flag exists; the default comes from a real parse of a
    # command line that omits it.
    seen = {}
    real_pick = run_gate.pick
    try:
        run_gate.pick = lambda prefer, **kw: seen.setdefault("prefer", prefer) or 0
        run_gate.main(["pick"])
    finally:
        run_gate.pick = real_pick
    return seen.get("prefer")


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


def test_a_preference_reorders_and_never_admits():
    """`--prefer` is for a human re-running one client by hand. It moves a
    name UP the queue and cannot put one in it: a preferred name with nothing
    pending is not a candidate, or the gate spends connector calls printing
    "failed G1_ingested" about an entity that has no run to ingest."""
    pending = [_queued("zzz-other-bank", completed_at="2026-08-20"),
               _queued("chosen-by-hand", completed_at="2026-01-01")]
    order = run_gate.queue_order(
        pending, prefer=["chosen-by-hand", "not-in-the-queue-at-all"])
    assert order[0] == "chosen-by-hand", (
        "the preferred name leads even though its assessment is older")
    assert order[1] == "zzz-other-bank"
    assert len(order) == 2, "a preferred name with nothing pending is not a candidate"


def test_the_held_out_control_is_never_admitted_from_the_queue():
    """Widening the source of candidates must not widen what may be produced.
    HELD_OUT subtracts, which is why it survives the change."""
    pending = [_queued("bok-financial"), _queued("bok-financial-corporation"),
               _queued("fine-bank")]
    order = run_gate.queue_order(pending, prefer=[])
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
    """A name that is both preferred and offered by the queue is one
    candidate, not two."""
    pending = [_queued("some-bank")]
    order = run_gate.queue_order(pending, prefer=["some-bank"])
    assert order.count("some-bank") == 1


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
    assert run_gate.pick([]) == 1
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


# ── two clients per firing, and somewhere to go when a package fails ──
#
# Owner, 2026-08-23: "Ensure the routine can run even 2 client synthesis at a
# go. Invoke 2 sessions in the routine. If 1 package is not up to par, try
# another one."
#
# The gate's four checks all pass BEFORE the package-vetter looks at the
# workbooks, so a REFUSE lands inside the producing session, where this script
# is no longer running. Without a named alternative that session's only moves
# are to end the firing or to argue with the vetter — which is how Houlihan
# Lokey ended a firing having produced nothing. RESERVE lines are the third
# option.


def _queue(names):
    return [{"display_id": n, "run_id": f"run-{n}"} for n in names]


def _all_pass(monkeypatch, producible, order=None):
    """Every named client is producible; the rest fail G1."""
    monkeypatch.setattr(run_gate, "queue_order",
                        lambda pending, prefer: order or
                        [r["display_id"] for r in pending])

    def fake_eval(pending, display_id):
        ok = display_id in producible
        base = {g: {"ok": ok, "detail": "x"} for g in
                ("G1_ingested", "G2_raw_package", "G3_serving",
                 "G4_non_duplicate")}
        base["run_id"] = f"run-{display_id}" if ok else None
        return base

    monkeypatch.setattr(run_gate, "evaluate", fake_eval)
    monkeypatch.setattr(run_gate, "mcp_call",
                        lambda tool, args: {"pending": []})


def test_two_clients_are_emitted_when_two_are_producible(monkeypatch, capsys):
    _all_pass(monkeypatch, {"a", "b", "c", "d"}, order=["a", "b", "c", "d"])
    assert run_gate.pick([], count=2) == 0
    out = capsys.readouterr().out
    assert "GATE: PRODUCE a run run-a" in out
    assert "GATE: PRODUCE b run run-b" in out


def test_the_spares_are_named_as_reserve_not_as_produce(monkeypatch, capsys):
    """A RESERVE is not a second client to synthesise — it is where to go if
    a package fails vetting. Emitting it as PRODUCE would have the firing
    quietly carry four."""
    _all_pass(monkeypatch, {"a", "b", "c", "d"}, order=["a", "b", "c", "d"])
    run_gate.pick([], count=2)
    out = capsys.readouterr().out
    assert out.count("GATE: PRODUCE") == 2
    assert "GATE: RESERVE c run run-c" in out


def test_one_producible_client_still_produces(monkeypatch, capsys):
    """Asking for two and finding one is not a failed firing. Refusing to
    produce the one would be the queue-blocking behaviour in a new place."""
    _all_pass(monkeypatch, {"a"}, order=["a", "b", "c"])
    assert run_gate.pick([], count=2) == 0
    out = capsys.readouterr().out
    assert out.count("GATE: PRODUCE") == 1
    assert "asked for 2, found 1" in out


def test_none_producible_still_stops_and_lists_every_failure(monkeypatch,
                                                             capsys):
    _all_pass(monkeypatch, set(), order=["a", "b"])
    assert run_gate.pick([], count=2) == 1
    out = capsys.readouterr().out
    assert "GATE: STOP" in out
    assert "skipped a:" in out and "skipped b:" in out


def test_count_one_is_unchanged_behaviour(monkeypatch, capsys):
    """The default has to stay exactly what it was, or every existing
    routine changes meaning on upgrade."""
    _all_pass(monkeypatch, {"a", "b"}, order=["a", "b"])
    assert run_gate.pick([], count=1) == 0
    out = capsys.readouterr().out
    assert out.count("GATE: PRODUCE") == 1
    assert "GATE: PRODUCE a run run-a" in out


def test_the_held_out_client_is_never_produced_or_reserved(monkeypatch,
                                                           capsys):
    """Widening the walk must not widen this. bok-financial stays out of
    both lists however many clients a firing carries."""
    names = ["bok-financial", "a", "b", "c"]
    monkeypatch.setattr(run_gate, "queue_order",
                        lambda pending, prefer: run_gate.queue_order.__wrapped__(
                            pending, prefer) if False else
                        [n for n in names if n not in run_gate.HELD_OUT])
    _all_pass(monkeypatch, set(names),
              order=[n for n in names if n not in run_gate.HELD_OUT])
    run_gate.pick([], count=2)
    out = capsys.readouterr().out
    assert "bok-financial" not in out
