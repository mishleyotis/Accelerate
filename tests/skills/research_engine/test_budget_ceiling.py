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
