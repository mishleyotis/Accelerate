"""The run path refuses a container that cannot finish the run.

THE MEASURED DEADLOCK, 2026-09-12: a run began with no enrichment connector
bound. `declare_absence` refuses a cell whose searches all ran through the
built-in web tools, so no empty cell could close; no floors gate could pass;
the driver re-dispatched sixteen categories ~18 times and spent $96.65
against a $20 budget, closing nothing.

The 2026-09-13 work built the degraded path that makes such a container
honest — `--enrichment-unavailable` writes the absence at REDUCED rigour —
but it lifts ONLY on the run's own recorded connector baseline, and nothing
on the run path wrote or checked one. `Pipeline.run_all` called
`refuse_on_stale_install` and nothing else; `env_check`, which carries the
connector row as a hard failure, was wired to the `env` subcommand alone.
A test asserted that two markdown files MENTION the preflight.

So the deadlock was reachable exactly as before: no baseline means
`enrichment_binding` answers `known=False`, the gate keeps blocking, the
absence keeps being refused, and `heal_plan` falls through to "you never
attempted a connector, fire one" — at a lane that has none.

These pin the gate on the run path: it blocks before a single lane is
dispatched, it degrades where the baseline PROVES the connector missing,
and an unverified container is refused rather than degraded, because
unverified is not a diagnosis.
"""
from __future__ import annotations

import json

import pytest

from engine import pipeline as P, pipeline_stub as S, preflight
from fixtures import new_run, preflight_doc


def _baseline(run, tools):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(P.__file__).resolve().parents[3] / "scripts"))
    import connector_contract as cc                            # noqa: PLC0415
    return cc.write_baseline(tools, str(run.root))


BOUND = ["mcp__Exa__web_search_exa", "mcp__Tavily__tavily_search",
         "mcp__Clay__find-and-enrich-company"]
SHORT = ["mcp__Clay__find-and-enrich-company"]


def _drive(tmp_path, *, baseline, **over):
    run = new_run(tmp_path, n=6, baseline=None)
    preflight.record(run, preflight_doc())
    if baseline is not None:
        _baseline(run, baseline)
    disp = S.StubDispatcher(S.default_handlers())
    kw = dict(dispatcher=disp, reads=S.StubReads(), shipper=S.StubShipper(),
              push=False, folder_root=tmp_path / "client_out", ingest_poll_s=0,
              sleep=lambda s: None, log=lambda s: None, until="RESEARCH",
              max_rounds=1, stall_rounds=0)
    kw.update(over)
    p = P.Pipeline(run, P.Options(**kw))
    return p, disp, p.run_all()


def test_no_baseline_blocks_before_any_lane_is_dispatched(tmp_path):
    p, disp, out = _drive(tmp_path, baseline=None)
    assert out["outcome"] == "BLOCKED", out
    assert out["stage"] == "PREFLIGHT"
    assert "baseline" in out["reason"] and str(p.run.root) in out["reason"]
    assert disp.calls == [], "a lane was dispatched before the gate refused"
    assert not (p.run.root / "briefs").exists()


def test_a_short_baseline_degrades_and_records_why(tmp_path):
    """A container that PROVABLY never had one is honest, not refused: it
    declares its absences at reduced rigour and says so."""
    p, disp, out = _drive(tmp_path, baseline=SHORT)
    assert out["outcome"] != "BLOCKED", out
    deg = p.state.get("enrichment_degraded")
    assert deg and "exa" in " ".join(deg["missing"]).lower()
    assert deg["reason"]


def test_a_bound_baseline_says_nothing_and_proceeds(tmp_path):
    p, disp, out = _drive(tmp_path, baseline=BOUND)
    assert out["outcome"] != "BLOCKED", out
    assert not p.state.get("enrichment_degraded")


def test_the_waiver_is_recorded_rather_than_silent(tmp_path):
    """An operator may override it; the run must carry the fact."""
    p, disp, out = _drive(tmp_path, baseline=None,
                          allow_unverified_connectors=True)
    assert out["outcome"] != "BLOCKED", out
    assert any("unverified_connectors" in w for w in p.state.get("waivers") or [])


def test_a_resume_past_research_needs_no_baseline(tmp_path):
    """The gate guards the stage that spends the money. A run already past
    it is not re-refused over a file nobody will read again."""
    run = new_run(tmp_path, n=6, baseline=None)
    preflight.record(run, preflight_doc())
    p = P.Pipeline(run, P.Options(
        dispatcher=S.StubDispatcher(S.default_handlers()), reads=S.StubReads(),
        shipper=S.StubShipper(), push=False, folder_root=tmp_path / "out",
        ingest_poll_s=0, sleep=lambda s: None, log=lambda s: None))
    assert p._connector_gate("PROMOTE") is None


def test_env_check_reads_the_run_root_it_is_given(tmp_path):
    """It read $DMA_RUN_ROOT or the cwd, so the answer depended on where the
    process happened to be standing."""
    run = new_run(tmp_path, n=6, baseline=None)
    _baseline(run, BOUND)
    row = P._connector_row(str(run.root))
    assert row[1] is True, row
    assert P._connector_row(str(tmp_path / "nowhere"))[1] is False


def test_the_run_path_calls_the_gate(tmp_path):
    """The old test asserted that two markdown files MENTION the preflight."""
    import inspect
    src = (inspect.getsource(P.Pipeline.run_all)
           + inspect.getsource(P.Pipeline._run_all))
    assert "_connector_gate" in src


def test_an_unverified_container_is_refused_not_degraded(tmp_path):
    """THE ANTI-HOLLOWING PROPERTY, and the reason the gate refuses rather
    than assuming the kinder answer. If an absent baseline were treated as
    proof that no connector exists, every run that skipped its preflight
    would inherit the degraded path — absences at REDUCED rigour, bought by
    never having measured. The degradation must be EARNED by a baseline
    that shows the families missing."""
    p, disp, out = _drive(tmp_path, baseline=None)
    assert out["outcome"] == "BLOCKED"
    assert not p.state.get("enrichment_degraded"), (
        "an unverified container was quietly given the degraded path")
    short_p, _, short_out = _drive(tmp_path / "b", baseline=SHORT)
    assert short_out["outcome"] != "BLOCKED"
    assert short_p.state["enrichment_degraded"], (
        "a container that PROVED the connector missing was not degraded")
