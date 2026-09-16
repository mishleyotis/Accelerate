"""The budget is ENFORCED, not just reported.

Measured 2026-09-12 on a live run: $96.65 spent against a $20 four-pillar
budget. `cost.record` raises only on a missing duration, `pipeline` called it
with no `usd=` at all inside a bare `except`, and the only verdict on money
was `cost report`'s shell exit code — a command no automated path runs
("reported over budget WITH the figure, and still runs", docs/ROUTINES.md).
Meanwhile `agent_run.py` was already summing each lane's real
`total_cost_usd` into the batch summary and `_count` was throwing it away.

These pin the three halves of the fix: the figure is read, the ceiling bites
INSIDE the stage that spends the money, and a run the ceiling stopped says so
instead of blaming the gate it never reached.
"""
from __future__ import annotations

from engine import pipeline as P, pipeline_stub as S, preflight
from fixtures import new_run, preflight_doc


class CostlyDispatcher(S.StubDispatcher):
    """A dispatcher that reports money, the way `agent_run.py` does."""

    def __init__(self, usd_per_batch, **kw):
        super().__init__(**kw)
        self.usd = usd_per_batch

    def dispatch(self, *a, **k):
        out = super().dispatch(*a, **k)
        out["usd"] = self.usd
        out["turns"] = 40
        return out


def _lane_closes_one_cell(agent, prompt_file, ctx):
    F = S.fixtures()
    wb = ctx.run.open()
    cat = agent.split("-")[1].upper()
    for c in [x for x in wb.selected_subcaps() if x.startswith(cat)]:
        if str((wb.scoring_row(c) or {}).get("Dominant_Claim") or "").strip():
            continue
        eids = F.bank_evidence(wb, c, n=5)
        F.synthesise(wb, c, F.good_synthesis(c, eids), author=agent)
        break


def _drive(tmp_path, *, usd_per_batch=5.0, **over):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = CostlyDispatcher(usd_per_batch,
                            handlers={"research-p": _lane_closes_one_cell,
                                      "finding-challenger": S.lane_noop})
    kw = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
              folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
              log=lambda s: None, until="RESEARCH", max_rounds=10, stall_rounds=0)
    kw.update(over)
    p = P.Pipeline(run, P.Options(**kw))
    return p, disp, p.run_all()


def _rounds(disp):
    return len([c for c in disp.calls if c["stage"] == "RESEARCH"])


def test_the_driver_reads_the_spend_the_dispatcher_reports(tmp_path):
    """`_count` used to read `dispatched` and `attempts` out of the batch
    summary and drop `usd` — the one figure that could stop a runaway run."""
    p, disp, _ = _drive(tmp_path, max_usd=0)
    assert p._spent_usd == 5.0 * _rounds(disp) > 0
    assert p._spent_turns == 40 * _rounds(disp)


def test_the_ceiling_bites_inside_the_research_stage(tmp_path):
    """A between-stages-only guard cannot stop the stage that spends the
    money: ten rounds x sixteen lanes all happen inside ONE stage."""
    p, disp, out = _drive(tmp_path, max_usd=12.0)
    assert out["outcome"] == "STOPPED_BUDGET", out
    assert _rounds(disp) == 3, "must stop mid-stage, not run the ceiling"
    assert p._spent_usd >= 12.0


def test_a_run_the_ceiling_stopped_does_not_blame_the_gate(tmp_path):
    """It was cut short, not refused. Reporting a floors-gate failure sends
    the reader to repair research that simply never finished."""
    _, _, out = _drive(tmp_path, max_usd=12.0)
    assert "budget" in out["reason"] and "cut short, not refused" in out["reason"]
    assert "--max-usd" in out["reason"], "the message must name its own remedy"


def test_zero_disables_the_ceiling(tmp_path):
    """The old reporting-only behaviour stays reachable."""
    p, disp, out = _drive(tmp_path, max_usd=0)
    assert p.budget_usd() is None
    assert out["outcome"] == "STOPPED_AT_UNTIL" and _rounds(disp) == 6


def test_the_default_ceiling_comes_from_the_cost_model(tmp_path):
    """No second copy of the budget: it is BUDGET_PER_PILLAR x pillars."""
    from engine import cost
    p, _, _ = _drive(tmp_path, max_usd=10_000.0)
    p.opts.max_usd = None
    assert p.budget_usd() == cost.BUDGET_PER_PILLAR * 1, "one pillar in this fixture"


def test_the_ledger_gets_the_real_figures_not_an_estimate(tmp_path):
    """`cost.record` was called with no `usd=` at all, so the ledger could
    not contradict the projection."""
    import json
    p, _, _ = _drive(tmp_path, max_usd=0)
    lines = [json.loads(x) for x in
             (p.run.qa_dir / "cost_ledger.jsonl").read_text().splitlines() if x.strip()]
    research = [r for r in lines if r.get("stage") == "RESEARCH"]
    assert research, "the research stage must appear in the ledger"
    assert sum(float(r.get("usd") or 0) for r in research) > 0, (
        "the ledger must carry the spend the dispatcher reported")


# ── the ledger sums to the run, once ───────────────────────────────────
#
# Measured 2026-09-14: `agent_run.py` writes its own ledger row per batch
# (`--record-stage`), and `Pipeline._record` then wrote the same spend again
# under the stage it was closing. For a research round that stage is
# RESEARCH — which contains the CHALLENGE and RELAY batches — so the run
# total roughly doubled AND the challenge lanes' money was reported as
# research. `_over_budget` reads that total, so the ceiling bit at half the
# real figure.


class SelfRecordingDispatcher(CostlyDispatcher):
    """A dispatcher that writes its own ledger rows, as `agent_run.py` does."""

    records_cost = True

    def dispatch(self, batch_path, *, stage, lanes, retries, ctx):
        from engine import cost
        out = super().dispatch(batch_path, stage=stage, lanes=lanes,
                               retries=retries, ctx=ctx)
        cost.record(ctx.run, stage=stage, elapsed_s=1.0, usd=out["usd"],
                    turns=out["turns"], note="agent_run batch")
        return out


def _lane_synthesises_uncontested(agent, prompt_file, ctx):
    """A lane that FINISHES its category and leaves the challenge to the
    challenge stage.

    Both halves matter for measuring that stage. `fixtures.synthesise`
    challenges the cell itself, so a run built with it dispatches no
    challenge lane at all; and since 2026-09-14 the driver challenges only
    categories whose research has CONVERGED, so a lane that closes one cell
    a round never earns one either.
    """
    from engine import ledger as L
    F = S.fixtures()
    wb = ctx.run.open()
    cat = agent.split("-")[1].upper()
    for c in [x for x in wb.selected_subcaps() if x.startswith(cat)]:
        if str((wb.scoring_row(c) or {}).get("Dominant_Claim") or "").strip():
            continue
        eids = F.bank_evidence(wb, c, n=5)
        # `good_synthesis` carries a Challenge_Verdict of its own, which
        # `challenge_batch` reads as "already challenged".
        record = {k: v for k, v in F.good_synthesis(c, eids).items()
                  if k != "Challenge_Verdict"}
        L.append_synthesis(wb, c, record, actor=agent)


def _drive_self_recording(tmp_path, **over):
    run = new_run(tmp_path, n=6)
    preflight.record(run, preflight_doc())
    disp = SelfRecordingDispatcher(5.0,
                                   handlers={"research-p": _lane_synthesises_uncontested,
                                             "finding-challenger": S.lane_noop})
    kw = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
              folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
              log=lambda s: None, until="RESEARCH", max_rounds=2, stall_rounds=0,
              max_usd=0)
    kw.update(over)
    p = P.Pipeline(run, P.Options(**kw))
    return p, disp, p.run_all()


def test_the_ledger_sums_to_the_run_not_twice(tmp_path):
    from engine import cost
    p, disp, _ = _drive_self_recording(tmp_path)
    rows = cost.ledger(p.run)
    dispatched = 5.0 * len(disp.calls)
    assert dispatched > 0
    total = sum(r["usd"] for r in rows if r.get("usd") is not None)
    assert total == dispatched, (
        f"ledger says ${total} for ${dispatched} dispatched — the driver "
        f"re-recorded what the dispatcher already wrote")


def test_challenge_spend_is_attributed_to_challenge(tmp_path):
    from engine import cost
    p, disp, _ = _drive_self_recording(tmp_path)
    challenge_calls = [c for c in disp.calls if c["stage"] == "CHALLENGE"]
    assert challenge_calls, "fixture dispatched no challenge lane"
    by = {r["stage"]: r for r in cost.report(p.run)["by_stage"]}
    assert by["CHALLENGE"]["usd"] == 5.0 * len(challenge_calls)
    assert by["RESEARCH"]["usd"] == 5.0 * len(
        [c for c in disp.calls if c["stage"] == "RESEARCH"])


def test_a_dispatcher_that_does_not_self_record_is_still_recorded(tmp_path):
    """The stub, and any lane whose status file carried no cost. Removing
    the driver's record for everyone would leave those runs unpriced."""
    from engine import cost
    p, disp, _ = _drive(tmp_path, max_usd=0)
    total = sum(r["usd"] for r in cost.ledger(p.run) if r.get("usd") is not None)
    assert total == 5.0 * len(disp.calls) > 0


def test_the_real_dispatcher_declares_that_it_records_its_own_cost():
    assert P.AgentRunDispatcher.records_cost is True
    assert getattr(S.StubDispatcher, "records_cost", False) is False


# ── the ceiling survives the process ───────────────────────────────────
#
# `_spent_usd` was a class attribute starting at 0.0 and nothing read the
# ledger back, so a resume — or the hourly `watchdog --revive`, which is
# the one that matters — began every run at zero. A budget is not a ceiling
# if forgetting it costs nothing.


def test_a_resumed_run_remembers_what_it_spent(tmp_path):
    p, disp, out = _drive(tmp_path, max_usd=12.0)
    assert out["outcome"] == "STOPPED_BUDGET"
    spent = p._spent_usd
    p2 = P.Pipeline(p.run, P.Options(
        dispatcher=CostlyDispatcher(5.0, handlers={"research-p": _lane_closes_one_cell,
                                                   "finding-challenger": S.lane_noop}),
        reads=S.StubReads(), shipper=S.StubShipper(), push=False,
        folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
        log=lambda s: None, until="RESEARCH", max_usd=12.0))
    assert p2._spent_usd == spent, "the resume started from zero"
    out2 = p2.run_all()
    assert out2["outcome"] == "STOPPED_BUDGET"
    assert not [c for c in p2.opts.dispatcher.calls if c["stage"] == "RESEARCH"], \
        "it dispatched again on a budget it had already spent"


def test_raising_the_ceiling_is_how_a_resume_continues(tmp_path):
    p, disp, out = _drive(tmp_path, max_usd=12.0)
    p2 = P.Pipeline(p.run, P.Options(
        dispatcher=CostlyDispatcher(5.0, handlers={"research-p": _lane_closes_one_cell,
                                                   "finding-challenger": S.lane_noop}),
        reads=S.StubReads(), shipper=S.StubShipper(), push=False,
        folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
        log=lambda s: None, until="RESEARCH", max_usd=100.0))
    p2.run_all()
    assert [c for c in p2.opts.dispatcher.calls if c["stage"] == "RESEARCH"]


def test_the_outcome_is_recorded_where_the_watchdog_can_read_it(tmp_path):
    import json
    p, disp, out = _drive(tmp_path, max_usd=12.0)
    st = json.loads((p.run.qa_dir / "pipeline_state.json").read_text())
    assert st["last_outcome"] == "STOPPED_BUDGET"
    assert st["spent_usd"] >= 12.0 and st["budget_usd"] == 12.0


# ── the other ceiling, in the same place ───────────────────────────────

def test_the_wall_clock_bites_inside_the_research_stage(tmp_path):
    """It was checked between stages only, while ten rounds of sixteen
    lanes happen inside one."""
    # A clock that advances a minute per reading, against a 5-minute wall.
    # The stage needs six rounds to close six cells and reads the clock
    # about twice a round, so a wall that only bit BETWEEN stages would let
    # all six run — which is what it did.
    import itertools
    ticks = itertools.count(0, 60)
    p, disp, out = _drive(tmp_path, max_usd=0, max_wall_min=5,
                          clock=lambda: next(ticks))
    assert out["outcome"] == "STOPPED_WALL_CLOCK", out
    assert _rounds(disp) < 6, "the wall let the whole stage run"


def test_the_default_wall_clock_is_four_hours():
    """It lived in the conductor's dispatch line and nowhere else, so a
    driver invoked any other way ran unbounded."""
    assert P.Options.max_wall_min == 240.0
