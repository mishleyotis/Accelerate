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


# ── the money table is REACHABLE, not merely computed ────────────────────
#
# `report()` has carried `by_stage` since the accounting was fixed, and the
# printed report showed wall clock only. "Where did the run's dollars go" is
# the question a $96.65 run needed and the one a reader could not ask
# without writing their own JSON parser.

def _run_with_ledger(tmp_path):
    from fixtures import new_run
    run = new_run(tmp_path, n=4)
    cost.record(run, stage="RESEARCH", elapsed_s=60.0, usd=9.0, turns=40,
                tokens=TOK, model="sonnet")
    cost.record(run, stage="CHALLENGE", elapsed_s=30.0, usd=3.0, turns=12,
                tokens=TOK, model="sonnet")
    cost.record(run, stage="KG", elapsed_s=5.0)
    return run


def test_by_stage_prints_the_money_largest_first(tmp_path, capsys):
    run = _run_with_ledger(tmp_path)
    # $12 against a $5 budget, so the command's own verdict is 1. That is the
    # report's contract and not the flag's — the table prints either way, and
    # a flag that suppressed an over-budget verdict would be worse than none.
    assert cost.main(["report", "--run", run.run_id, "--root", str(run.root),
                      "--by-stage"]) == 1
    out = capsys.readouterr().out
    assert "OVER" in out
    body = out[out.index("usd"):]
    assert body.index("RESEARCH") < body.index("CHALLENGE"), (
        "largest first — a table ordered by stage name buries the answer")
    assert "$9.00" in out and "$3.00" in out
    assert "75%" in out and "25%" in out, "the share is what makes it readable"


def test_a_stage_with_no_money_is_a_dash_and_never_a_zero(tmp_path, capsys):
    """Invariant 9: a derived value is computed or null, never a default that
    looks like data. A KG row with no price is not a free stage."""
    run = _run_with_ledger(tmp_path)
    cost.main(["report", "--run", run.run_id, "--root", str(run.root),
               "--by-stage"])
    line = next(l for l in capsys.readouterr().out.splitlines()
                if l.strip().startswith("KG"))
    assert "—" in line and "$0" not in line


def test_an_unpriced_run_says_so_rather_than_printing_an_empty_table(tmp_path, capsys):
    """A dispatcher that recorded no spend is not a run that cost nothing,
    and a table of dashes reads like one."""
    from fixtures import new_run
    run = new_run(tmp_path, n=4)
    cost.record(run, stage="RESEARCH", elapsed_s=60.0)
    cost.main(["report", "--run", run.run_id, "--root", str(run.root),
               "--by-stage"])
    assert "recorded none" in capsys.readouterr().out


def test_the_flag_is_opt_in_so_the_old_report_is_unchanged(tmp_path, capsys):
    run = _run_with_ledger(tmp_path)
    cost.main(["report", "--run", run.run_id, "--root", str(run.root)])
    out = capsys.readouterr().out
    assert "wall clock" in out and "share" not in out
