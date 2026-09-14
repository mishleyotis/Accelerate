"""The ledger says WHICH stage spent the money, and says it once.

Measured 2026-09-14, reading the two writers: `agent_run.py --record-stage`
appends one ledger row per batch with the stage it dispatched (RESEARCH,
CHALLENGE, RELAY), and `Pipeline._record` then appended the SAME spend again
under the stage it was closing — which for a research round is RESEARCH, the
stage that contains the challenge and relay batches. So a run's ledger
overstated by roughly 2x and attributed the challenge lanes' spend to
research. `_over_budget` reads that total, so the ceiling bit at half the
real figure and the per-stage figures could not be used to judge any of the
2026-09 token work.

These pin the three halves: a self-recording dispatcher is not recorded
twice, a stage's spend stays on that stage, and `report` can say so.
"""
from __future__ import annotations

from engine import cost


def _rows(*specs):
    """Ledger rows in the shape `cost.record` writes."""
    out = []
    for stage, usd, turns, tokens in specs:
        out.append({"stage": stage, "elapsed_s": 60.0, "usd": usd, "turns": turns,
                    "tokens": tokens, "model": "sonnet", "lanes": 1, "attempts": 1,
                    "note": "", "started_at": None, "ended_at": None})
    return out


TOK = {"cache_read": 1_000_000, "cache_write": 10_000, "uncached": 5_000,
       "output": 500}


def test_totals_keep_each_stage_s_own_money(tmp_path):
    timings, summary = cost._totals(_rows(
        ("RESEARCH", 5.0, 40, TOK), ("CHALLENGE", 3.0, 20, TOK),
        ("RELAY", 1.0, 10, None), ("RESEARCH", 2.0, 15, None)))
    assert timings["RESEARCH"]["usd"] == 7.0
    assert timings["CHALLENGE"]["usd"] == 3.0
    assert timings["RELAY"]["usd"] == 1.0
    assert timings["RESEARCH"]["turns"] == 55
    assert summary["total_usd"] == 11.0


def test_the_token_fields_survive_into_the_stage(tmp_path):
    """76% of the measured bill is cache reads; a ledger that cannot see
    them cannot tell a context problem from a search problem."""
    timings, _ = cost._totals(_rows(("RESEARCH", 5.0, 40, TOK),
                                    ("RESEARCH", 5.0, 40, TOK)))
    assert timings["RESEARCH"]["tokens"]["cache_read"] == 2_000_000
    assert timings["RESEARCH"]["tokens"]["output"] == 1_000


def test_a_stage_with_no_money_reports_none_not_zero():
    """An unpriced stage and a free one are different facts."""
    timings, _ = cost._totals(_rows(("KG", None, None, None)))
    assert timings["KG"]["usd"] is None


def test_report_separates_research_from_challenge_and_relay(tmp_path):
    from fixtures import new_run
    run = new_run(tmp_path, n=6)
    for stage, usd in (("RESEARCH", 5.0), ("CHALLENGE", 3.0), ("RELAY", 1.0)):
        cost.record(run, stage=stage, elapsed_s=60.0, usd=usd, turns=10,
                    tokens=TOK, model="sonnet")
    rep = cost.report(run)
    by = {r["stage"]: r for r in rep["by_stage"]}
    assert by["RESEARCH"]["usd"] == 5.0
    assert by["CHALLENGE"]["usd"] == 3.0
    assert by["RELAY"]["usd"] == 1.0
    assert rep["total_usd"] == 9.0
    assert 0 < by["RESEARCH"]["share"] < 1


def test_challenge_and_gates_no_longer_share_one_budget():
    """They were mapped to the same 10-minute phase, so `report` could not
    tell which of them was over."""
    assert cost.STAGE_PHASE["CHALLENGE"] != cost.STAGE_PHASE["GATES"]
    assert cost.STAGE_PHASE["CHALLENGE"] in cost.PHASE_MINUTES
    assert cost.STAGE_PHASE["GATES"] in cost.PHASE_MINUTES
    assert "RELAY" in cost.STAGE_PHASE


def test_the_phase_table_still_sums_to_the_same_schedule():
    """Splitting a phase must not quietly buy the run more time."""
    minutes = [v for v in cost.PHASE_MINUTES.values() if v is not None]
    assert sum(minutes) == 65, cost.PHASE_MINUTES


def test_as_baseline_accepts_a_ledger_that_carries_tokens(tmp_path):
    """It refused every real run, because nothing passed --tokens."""
    from fixtures import new_run
    run = new_run(tmp_path, n=6)
    cost.record(run, stage="RESEARCH", elapsed_s=60.0, usd=5.0, turns=40,
                tokens=TOK, model="sonnet")
    out = cost.as_baseline(run, label="test")
    assert out["written_to"]
