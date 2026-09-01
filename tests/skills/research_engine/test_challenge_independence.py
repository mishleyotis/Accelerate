"""A research challenge must be INDEPENDENT of the synthesis it reviews.

AUD-0113: the original check only refused a challenge whose actor STRING equalled
the synthesis author's — so one agent defeated it by writing its synthesis as
`x-producer` and its own challenge as `x-challenger`. Independence is a property
of the agent RUN, not the label it types. These tests hold the strengthened
rule: a relabel of the same identity is refused, a same-session challenge is
refused whatever the label, and only a genuinely separate run — proven by a
distinct session token, or by a different base identity — is allowed.
"""
import pytest

from engine import ledger as L
from fixtures import new_run

DIMS = {d: "PASS" for d in (
    "evidence_sufficiency", "claim_label_fit", "facet_coverage",
    "contradiction_handling", "ceiling_reasoning", "recency", "synthesis_quality")}
RAT = ("An independent review with enough words to clear the forty-character "
       "rationale floor and say something real about the synthesis.")


@pytest.fixture(autouse=True)
def _no_ambient_session(monkeypatch):
    # The check must not silently pass because the test host happens to export
    # one of these; each test sets sessions explicitly.
    for k in ("DMA_AGENT_SESSION", "CLAUDE_AGENT_ID", "CLAUDE_SESSION_ID"):
        monkeypatch.delenv(k, raising=False)


def _run_with_synthesis(tmp_path, author, session=""):
    run = new_run(tmp_path, n=3, prelim=False)
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.record_provenance(wb, cell, "synthesis", author, session=session)
    wb.save()
    return run, wb, cell


def test_exact_same_actor_is_refused(tmp_path):
    run, wb, cell = _run_with_synthesis(tmp_path, "research-p2c4-producer")
    with pytest.raises(L.LedgerRefusal):
        L.record_challenge(wb, cell, verdict="PASS", actor="research-p2c4-producer",
                           dimensions=dict(DIMS), rationale=RAT)


def test_a_relabel_of_the_same_identity_is_refused(tmp_path):
    # the observed defeat: producer -> challenger, same base identity, no session
    run, wb, cell = _run_with_synthesis(tmp_path, "research-p2c4-producer")
    with pytest.raises(L.LedgerRefusal) as e:
        L.record_challenge(wb, cell, verdict="PASS", actor="research-p2c4-challenger",
                           dimensions=dict(DIMS), rationale=RAT)
    assert "relabel" in str(e.value).lower()


def test_a_genuinely_different_actor_is_allowed(tmp_path):
    # the orchestrator (a different identity) challenging a category producer
    run, wb, cell = _run_with_synthesis(tmp_path, "research-p2c4-producer")
    r = L.record_challenge(wb, cell, verdict="PASS", actor="research-orchestrator",
                           dimensions=dict(DIMS), rationale=RAT)
    assert r["verdict"] == "PASS" and r["challenger"] == "research-orchestrator"


def test_same_session_is_refused_even_with_a_different_label(tmp_path):
    run, wb, cell = _run_with_synthesis(tmp_path, "producer-alpha", session="S-1")
    with pytest.raises(L.LedgerRefusal) as e:
        L.record_challenge(wb, cell, verdict="PASS", actor="reviewer-beta",
                           dimensions=dict(DIMS), rationale=RAT, session="S-1")
    assert "session" in str(e.value).lower()


def test_distinct_sessions_prove_independence_despite_a_shared_base(tmp_path):
    # a REAL per-category challenger agent (a separate run) reviewing the producer:
    # the label base matches, but the distinct session proves two runs.
    run, wb, cell = _run_with_synthesis(tmp_path, "research-p2c4-producer", session="S-A")
    r = L.record_challenge(wb, cell, verdict="PASS", actor="research-p2c4-challenger",
                           dimensions=dict(DIMS), rationale=RAT, session="S-B")
    assert r["verdict"] == "PASS"
