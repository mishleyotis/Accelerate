"""One round, then hand back — `--step` and the state that carries a run.

Measured 2026-09-14: the enrichment connectors bind ONCE, at the session
start of the account that holds them, so the only actor in the arrangement
that can run a relay request is the conductor's own in-process subagent. The
driver can prepare that work and it can never do it. A driver that keeps
looping over a category whose gap only the conductor can close therefore
spends a fresh lane's context floor per round to rediscover a tool this
container does not have — the $96.65 shape, in a new costume.

So the round becomes the unit of work: `--step` runs exactly one research
round, says what is outstanding, backs the notebooks up and returns
ROUND_COMPLETE at exit 0. The conductor services the batch with its own
subagents and steps again. The handover is the state on disk, never this
process — a step that cannot be resumed from a cold container is not a step.

And the ENRICHMENT gate gains the verdict the vocabulary was missing: a
batch sitting on disk with its requests still OPEN is work in flight, not a
gap. PENDING_ORCHESTRATOR spends no heal and discloses nothing. Only a
request a connector REFUSED (recorded BLOCKED) is a measured gap again.

The fixture vocabulary is deliberately the relay suite's own — `_fresh`,
`_opts`, `_lane_web_only`, `REQ` — so these tests and those describe one run
tree rather than two.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine import cost, ledger as L, memory, pipeline as P, pipeline_stub as S, relay

from test_relay_and_enrichment import (REQ, _flag, _fresh, _lane_web_only, _opts,
                                       _result, _transcript)
from test_round_budget import _incremental_lane


def _state(run) -> dict:
    return json.loads((run.qa_dir / P.STATE_NAME).read_text())


def _enrichment_rows(run) -> list[dict]:
    return [g for g in run.open().rows("Gate_Log") if g.get("Gate") == "ENRICHMENT"]


def _asks_and_closes_one_cell(agent, prompt_file, ctx):
    """A research lane that closes ONE cell per dispatch and emits a search
    request it could not run — the two facts a step has to carry: the
    category is not finished, and the relay owes the conductor a search."""
    _incremental_lane(exa_once=False)(agent, prompt_file, ctx)
    _transcript(ctx.run.root / "agent_logs", agent,
                [_result(json.dumps({"search_requests": [REQ]}))])


def _step(run, tmp_path, dispatcher, **over):
    """One `--step` invocation, from a pipeline built fresh — so nothing but
    the run tree crosses between steps."""
    kw = dict(step=True, until=None, enrichment_heals=1)
    kw.update(over)
    return P.Pipeline(run, _opts(tmp_path, dispatcher, **kw)).run_all()


def _ready(tmp_path, dispatcher, n=3):
    """A run standing at RESEARCH. A step advances ONE stage, so the stages
    in front of it (KG, here) are stepped through the same way a conductor
    would step through them."""
    run = _fresh(tmp_path, n=n)
    while True:
        p = P.Pipeline(run, _opts(tmp_path, dispatcher, step=True, until=None))
        nxt = p.plan()["next"]
        if nxt in (None, "RESEARCH"):
            return run
        out = p.run_all()
        assert out["outcome"] == "ROUND_COMPLETE", out


# ═══════════════════════════════════════════════════════════════════════════
# the step itself
# ═══════════════════════════════════════════════════════════════════════════

def test_a_step_runs_one_research_round_and_returns_round_complete(tmp_path):
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    out = _step(run, tmp_path, disp)
    assert out["outcome"] == "ROUND_COMPLETE", out
    assert out["stage"] == "RESEARCH"
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 1, (
        "exactly one round — a step that runs two is not a step")
    assert out["resume"], "a step names the command that continues it"
    st = _state(run)["stages"]["RESEARCH"]
    assert st["rounds"] == 1


def test_round_complete_is_a_clean_stop(tmp_path, monkeypatch):
    """`watchdog --revive` reads the exit code and records RESOLVED or
    FAILED from it. A step that handed back for the conductor to work has
    not failed, so a sweep must not re-dispatch it as one."""
    assert "ROUND_COMPLETE" in P.EXIT_ZERO_OUTCOMES
    run = _fresh(tmp_path, n=3)
    monkeypatch.setattr(P.Pipeline, "run_all",
                        lambda self: {"outcome": "ROUND_COMPLETE", "stage": "RESEARCH",
                                      "reason": "round 1 complete", "stages_run": []})
    assert P.main(["run", "--run", run.run_id, "--root", str(run.root),
                   "--dispatcher", "stub", "--json"]) == 0


def test_the_second_step_continues_where_the_first_stopped(tmp_path):
    """THE HANDOVER IS THE STATE ON DISK. Each step builds its own Pipeline
    from the run tree and nothing else: a conductor that stepped, serviced a
    batch and stepped again is a different process every time, and possibly
    a different container."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    first = _step(run, tmp_path, disp)
    assert first["outcome"] == "ROUND_COMPLETE", first
    done_after_one = [c for c in run.open().scoring_rows()
                      if str(c.get("Dominant_Claim") or "").strip()]
    assert len(done_after_one) == 1

    second = _step(run, tmp_path, disp)
    assert second["outcome"] == "ROUND_COMPLETE", second
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 2, (
        "the second step dispatched a second round")
    done_after_two = [c for c in run.open().scoring_rows()
                      if str(c.get("Dominant_Claim") or "").strip()]
    assert len(done_after_two) == 2, "it continued the work, it did not redo it"


def test_a_step_past_research_advances_exactly_one_stage(tmp_path):
    """THE DECISION, pinned: `--step` past RESEARCH is one STAGE, not a
    no-op and not a run to PROMOTE. The flag means "advance once and hand
    back" whatever stage the run is standing on, so a conductor scripting it
    keeps a checkpoint between every stage rather than only inside one."""
    run = _fresh(tmp_path, n=3)
    disp = S.StubDispatcher(S.default_handlers())
    assert P.Pipeline(run, _opts(tmp_path, disp)).run_all()["outcome"] == "STOPPED_AT_UNTIL"
    p = P.Pipeline(run, _opts(tmp_path, disp, step=True, until=None))
    assert p.plan()["next"] == "HANDOFF"
    out = p.run_all()
    assert out["outcome"] == "ROUND_COMPLETE", out
    assert out["stage"] == "HANDOFF"
    assert P.Pipeline(run, _opts(tmp_path, disp)).plan()["next"] == "SCORING", (
        "exactly one stage: the next step owns SCORING")


# ═══════════════════════════════════════════════════════════════════════════
# what the step hands back
# ═══════════════════════════════════════════════════════════════════════════

def test_pending_names_the_batch_on_disk_the_open_categories_and_the_budget(tmp_path):
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    out = _step(run, tmp_path, disp)
    pend = out["pending"]

    assert len(pend["relay_batches"]) == 1, pend
    bf = Path(pend["relay_batches"][0])
    assert bf.is_file(), "a batch the conductor is told to service must exist"
    assert json.loads(bf.read_text())["requests"] >= 1

    assert pend["open_categories"] == ["P1C1"], (
        "one cell of three closed, so the category's floors gate is open")
    assert pend["stalled"] == []
    assert pend["rounds_remaining"] == P.Options.max_rounds - 1

    spent = round(sum(float(r["usd"]) for r in cost.ledger(run)
                      if r.get("usd") is not None), 4)
    assert pend["budget"]["spent"] == spent, "the budget is the ledger's, not a second tally"
    cap = pend["budget"]["ceiling"]
    assert cap is None or pend["budget"]["remaining"] == round(cap - spent, 4)


def test_pending_carries_a_null_gaps_field_until_brief_grows_one(tmp_path):
    """`brief.gaps` is being built alongside this. The field is null rather
    than absent, so a conductor reading the payload never has to ask which
    shape of it arrived."""
    from engine import brief
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    pend = _step(run, tmp_path, disp)["pending"]
    assert "gaps" in pend
    if not callable(getattr(brief, "gaps", None)):
        assert pend["gaps"] is None


def test_the_json_output_carries_the_pending_payload(tmp_path, capsys, monkeypatch):
    """The conductor reads `--json`, not the log. A pending payload the
    command cannot print is a handover that happens in prose."""
    run = _fresh(tmp_path, n=3)
    monkeypatch.setattr(
        P.Pipeline, "run_all",
        lambda self: {"outcome": "ROUND_COMPLETE", "stage": "RESEARCH",
                      "stages_run": [], "pending": self.pending()})
    assert P.main(["run", "--run", run.run_id, "--root", str(run.root),
                   "--dispatcher", "stub", "--step", "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed["pending"]) >= {"relay_batches", "open_categories", "stalled",
                                       "budget", "rounds_remaining", "gaps"}


def test_a_batch_the_conductor_serviced_is_no_longer_pending(tmp_path):
    """THE LIST IS NOT THE ANSWER. `state["relay_batches"]` is append-only —
    nothing removes a path once it is written — so a driver that reported it
    back would hand the conductor its own finished work for the rest of the
    run. The queue is what knows a batch is done."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    first = _step(run, tmp_path, disp)
    batch = first["pending"]["relay_batches"][0]

    # The conductor services it: its subagent runs the query through a
    # connector, logs the row, and closes the request.
    wb = run.open()
    for req in relay.open_requests(run):
        L.append_search(wb, subcap=req["subcap"], facet=req["facet"] or "works",
                        query=req["query"], tool="exa", hits=3, kept=2, outcome="kept 2")
    relay.record(run, [r["id"] for r in relay.open_requests(run)], "SERVED",
                 note="serviced by an in-process subagent", actor="research-conductor",
                 tool="exa")

    second = _step(run, tmp_path, disp)
    assert batch in (_state(run).get("relay_batches") or []), (
        "the batch is still recorded — the record is history, not a queue")
    assert batch not in second["pending"]["relay_batches"], (
        "…and a serviced batch is not outstanding work")


# ═══════════════════════════════════════════════════════════════════════════
# PENDING_ORCHESTRATOR: work in flight is not a gap
# ═══════════════════════════════════════════════════════════════════════════

def test_the_gate_log_admits_pending_orchestrator(tmp_path):
    """The vocabulary had three words and needed a fourth. FAIL would have
    re-dispatched or disclosed the category; NOT_RUN would have read as
    "nobody looked". Neither is true of a batch in flight."""
    assert "PENDING_ORCHESTRATOR" in L.GATE_VERDICTS
    run = _fresh(tmp_path, n=3)
    wb = run.open()
    L.append_gate(wb, gate="ENRICHMENT", scope="P1C1", verdict="PENDING_ORCHESTRATOR",
                  detail="2 relay request(s) with the conductor", blocking=False)
    assert _enrichment_rows(run)[-1]["Verdict"] == "PENDING_ORCHESTRATOR"
    with pytest.raises(L.LedgerRefusal):
        L.append_gate(wb, gate="ENRICHMENT", scope="P1C1", verdict="PENDING", detail="x")


def test_an_unserviced_batch_spends_no_heal_and_discloses_nothing(tmp_path):
    """A heal is a FRESH LANE INSTANCE. Spending one on a category whose
    relay batch has not come back buys a full context floor to rediscover
    that this container holds no connector — and disclosing it states a gap
    over work that is merely unfinished."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    out = _step(run, tmp_path, disp)
    assert out["outcome"] == "ROUND_COMPLETE", out

    row = _enrichment_rows(run)[-1]
    assert row["Verdict"] == "PENDING_ORCHESTRATOR", [r["Verdict"] for r in _enrichment_rows(run)]
    assert _flag(row["Blocking"]) is False, "work in flight never blocks"
    assert "relay request" in row["Detail"]

    st = _state(run)
    assert not (st.get("enrichment_heals") or {}), "no heal was spent"
    assert "P1C1" not in (st.get("enrichment_disclosed") or {}), (
        "a pending batch is not a disclosed gap")


def test_a_request_the_connector_refused_is_a_blocking_fail(tmp_path):
    """The one measurement that turns work in flight back into a measured
    gap: BLOCKED is recorded only by an actor that tried and was refused, and
    `relay.record` will not write it without the refusal text. That is a
    connector saying no, which is exactly what the ENRICHMENT gate exists to
    surface."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    logs = run.root / "agent_logs"
    _transcript(logs, "research-p1c1-producer",
                [_result(json.dumps({"search_requests": [REQ]}))])
    relay.harvest(run, ["P1C1"], logs_dir=logs)
    relay.record(run, [r["id"] for r in relay.open_requests(run)], "BLOCKED",
                 note="mcp__Exa__web_search_exa is not permitted in this session",
                 actor="research-conductor")

    out = _step(run, tmp_path, disp)
    assert out["outcome"] == "ROUND_COMPLETE", out
    row = _enrichment_rows(run)[-1]
    assert row["Verdict"] == "FAIL", [r["Verdict"] for r in _enrichment_rows(run)]
    assert _flag(row["Blocking"]) is True, "a refused connector blocks; it is not pending"
    assert "BLOCKED" in row["Detail"]


def test_a_category_that_reached_a_connector_still_passes_with_a_batch_open(tmp_path):
    """PENDING is about a category with NO connector search. One that ran
    one still passes the gate — the pending batch is more of the same work,
    not a reason to withhold a verdict the Search_Log already supports."""
    def lane(agent, prompt_file, ctx):
        _lane_web_only(with_exa=True, emit_requests=True)(agent, prompt_file, ctx)
    disp = S.StubDispatcher({"research-p": lane, "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    _step(run, tmp_path, disp)
    assert _enrichment_rows(run)[-1]["Verdict"] == "PASS"


# ═══════════════════════════════════════════════════════════════════════════
# the notebook backup: once a round, never fatal
# ═══════════════════════════════════════════════════════════════════════════

def test_the_notebooks_are_backed_up_once_per_step(tmp_path, monkeypatch):
    """The .md notebooks are the only part of the run tree a dead container
    loses outright. A round that ends without a copy has made the run
    resumable for everything except the layer that cannot be rebuilt."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)
    calls = []
    monkeypatch.setattr(memory, "backup",
                        lambda r: calls.append(r.run_id) or {"outcome": "RESOLVED"})
    out = _step(run, tmp_path, disp, push=True)
    assert out["outcome"] == "ROUND_COMPLETE", out
    assert calls == [run.run_id], "one round, one backup"
    assert _state(run)["memory_backup"]["status"] == "RESOLVED"
    assert _state(run)["memory_backup"]["at"]


def test_a_backup_that_raises_does_not_fail_the_round(tmp_path, monkeypatch):
    """The whole point of a resumable round is that it ENDS. A backup that
    cannot run records why and the round carries on."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)

    def boom(_run):
        raise RuntimeError("drive is unreachable from this container")
    monkeypatch.setattr(memory, "backup", boom)
    out = _step(run, tmp_path, disp, push=True)
    assert out["outcome"] == "ROUND_COMPLETE", out
    assert _state(run)["memory_backup"]["status"].startswith("NOT_RUN: RuntimeError")


def test_a_run_told_not_to_push_does_not_talk_to_drive(tmp_path, monkeypatch):
    """`--no-push` means no Drive call, and the notebook backup is a Drive
    call like any other. A test container that reached for a real token
    here would be a test suite with a network dependency."""
    disp = S.StubDispatcher({"research-p": _asks_and_closes_one_cell,
                             "finding-challenger": S.lane_noop})
    run = _ready(tmp_path, disp)

    def boom(_run):
        raise AssertionError("backup ran under --no-push")
    monkeypatch.setattr(memory, "backup", boom)
    assert _step(run, tmp_path, disp, push=False)["outcome"] == "ROUND_COMPLETE"
    assert "memory_backup" not in _state(run)
