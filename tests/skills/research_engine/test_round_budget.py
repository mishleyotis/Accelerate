"""Rounds are a ceiling, not a proxy for progress (owner, 2026-09-07).

The driver refused a category after three rounds while categories were
still gaining ground each round — one hit 100% coverage in round two. The
owner resumed with ten. These pin the two halves of the fix: the ceiling is
ten, and a stage stops early ONLY when consecutive rounds advance nothing it
measures — so a big budget cannot spin on a stalled stage, and a moving
stage is not refused for being slow.
"""
from __future__ import annotations

import json

from engine import ledger as L, pipeline as P, pipeline_stub as S, preflight
from fixtures import new_run, preflight_doc


def _fresh(tmp_path, n=6):
    run = new_run(tmp_path, n=n)
    preflight.record(run, preflight_doc())
    return run


def _opts(tmp_path, dispatcher, **over):
    kw = dict(dispatcher=dispatcher, reads=S.StubReads(), shipper=S.StubShipper(), push=False,
              folder_root=tmp_path / "client_out", ingest_poll_s=0, sleep=lambda s: None,
              log=lambda s: None, until="RESEARCH")
    kw.update(over)
    return P.Options(**kw)


def test_the_default_ceiling_is_ten_and_the_stall_window_two():
    assert P.Options.max_rounds == 10
    assert P.Options.stall_rounds == 2
    assert P.Options.enrichment_heals == 1 and P.Options.relay is True


def test_the_cli_defaults_match_the_options():
    """`main` would drive a run, so the parser is read rather than invoked:
    each flag takes its default FROM the Options field, never a second copy."""
    import inspect
    text = inspect.getsource(P.main)
    assert '"--max-rounds", type=int, default=Options.max_rounds' in text
    assert '"--stall-rounds", type=int, default=Options.stall_rounds' in text
    assert '"--enrichment-heals", type=int, default=Options.enrichment_heals' in text
    assert '"--no-relay"' in text


def _incremental_lane(exa_once: bool = True):
    """A research lane that closes ONE cell per dispatch — the shape the old
    three-round ceiling refused while it was still making progress."""
    def lane(agent, prompt_file, ctx):
        F = S.fixtures()
        cat = agent.split("-")[1].upper()
        wb = ctx.run.open()
        cells = [c for c in wb.selected_subcaps() if c.startswith(cat)]
        for c in cells:
            row = wb.scoring_row(c) or {}
            if str(row.get("Dominant_Claim") or "").strip():
                continue
            eids = F.bank_evidence(wb, c, n=5)
            if exa_once and not L.enrichment_status(wb, cat)["enrichment_searches"]:
                L.append_search(wb, subcap=c, facet="works", query='"Acme Credit Union" vendor',
                                tool="exa", hits=2, kept=1)
            F.synthesise(wb, c, F.good_synthesis(c, eids), author=agent)
            break                                    # one cell, then hand back
        F.client_facts(wb, wb.selected_subcaps(), S._evidence_by_cell(wb))
    return lane


def test_a_category_still_gaining_ground_is_not_refused_at_three_rounds(tmp_path):
    run = _fresh(tmp_path, n=6)
    disp = S.StubDispatcher({"research-p": _incremental_lane(), "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp)).run_all()
    assert out["outcome"] == "STOPPED_AT_UNTIL", out
    research = [c for c in disp.calls if c["stage"] == "RESEARCH"]
    assert len(research) == 6, "six cells, one per round, none refused"
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())["stages"]["RESEARCH"]
    assert st["verdict"] == "PASS" and st["rounds"] == 6


def test_the_old_ceiling_would_have_refused_that_same_run(tmp_path):
    """The reproduction: the exact shape the owner saw. Kept so the number
    the fix changed stays tied to the failure it caused."""
    run = _fresh(tmp_path, n=6)
    disp = S.StubDispatcher({"research-p": _incremental_lane(), "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, max_rounds=3)).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "RESEARCH"
    assert "after 3 round(s)" in out["reason"] and "floors gate" in out["reason"]
    assert "advanced nothing" not in out["reason"], "it was moving; the ceiling, not a stall, stopped it"


def test_a_stalled_stage_stops_after_the_window_not_the_ceiling(tmp_path):
    run = _fresh(tmp_path, n=4)
    disp = S.StubDispatcher({"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, max_rounds=10, stall_rounds=2)).run_all()
    assert out["outcome"] == "FAILED" and out["stage"] == "RESEARCH"
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 2, "not ten"
    assert "floors gate" in out["reason"] and "advanced nothing" in out["reason"]
    assert "stopped at round 2" in out["reason"]
    st = json.loads((run.qa_dir / P.STATE_NAME).read_text())["stages"]["RESEARCH"]
    assert st["verdict"] == "FAIL" and st["rounds"] == 2


def test_stall_detection_can_be_switched_off(tmp_path):
    run = _fresh(tmp_path, n=4)
    disp = S.StubDispatcher({"research-p": S.lane_noop, "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, max_rounds=4, stall_rounds=0)).run_all()
    assert out["outcome"] == "FAILED"
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 4
    assert "advanced nothing" not in out["reason"]


def test_progress_resets_the_stall_count(tmp_path):
    """Two idle rounds, one productive one, two idle: the window counts
    CONSECUTIVE idle rounds, so the productive round buys two more."""
    run = _fresh(tmp_path, n=4)
    calls = {"n": 0}
    real = _incremental_lane()

    def sometimes(agent, prompt_file, ctx):
        calls["n"] += 1
        if calls["n"] in (2, 5):
            real(agent, prompt_file, ctx)
    disp = S.StubDispatcher({"research-p": sometimes, "finding-challenger": S.lane_noop})
    out = P.Pipeline(run, _opts(tmp_path, disp, max_rounds=10, stall_rounds=2)).run_all()
    assert out["outcome"] == "FAILED"
    # rounds: 1 idle, 2 progress, 3 idle, 4 idle → stop at 4 (window 2 after the reset)
    assert len([c for c in disp.calls if c["stage"] == "RESEARCH"]) == 4


def test_the_research_signature_measures_the_substrate(tmp_path):
    run = _fresh(tmp_path, n=4)
    p = P.Pipeline(run, _opts(tmp_path, S.StubDispatcher({})))
    before = p._progress("RESEARCH")
    assert len(before) == 6
    wb = run.open()
    cell = wb.selected_subcaps()[0]
    L.append_search(wb, subcap=cell, facet="works", query='"Acme Credit Union" vendor',
                    tool="exa", hits=1, kept=1)
    p.reopen()
    after = p._progress("RESEARCH")
    assert after[2] == before[2] + 1, "one more search"
    assert after[5] == before[5] + 1, "one more connector search"
    assert after[:2] == before[:2] and after[3:5] == before[3:5]


def test_every_looping_stage_checks_for_a_stall():
    import inspect
    for stage in ("_stage_prelim", "_stage_research", "_stage_scoring", "_stage_reports"):
        src = inspect.getsource(getattr(P.Pipeline, stage))
        assert "self._stalled(" in src, stage
        assert "self._stall_note()" in src, stage
