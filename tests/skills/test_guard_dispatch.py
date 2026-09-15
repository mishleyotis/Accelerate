"""A dispatch is the most expensive call this system makes.

The engine refuses each of these states at the write path — but a refusal
that arrives after the lane has run has already spent the lane, and a lane
that has spent its turns is re-dispatched, which is the shape that turned a
$20 budget into $96.65. These pin the belt at the seam: one deny per rule,
the allow for a call the table does not govern, and the fail-open that keeps
a guard from refusing on its own bug.

THE INSTALL CHECK IS PATCHED OUT of the per-rule tests on purpose. It is the
FIRST refusal — a lane dispatched on a stale install runs gates the checkout
no longer publishes — so on any container whose plugin cache is behind the
checkout (this one, today: installed 1.19.0 vs published 1.20.0) it would
mask every other rule. It has its own test, where it is the subject.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PLUGIN = REPO / "plugins" / "dma-insights"
HOOK = PLUGIN / "scripts" / "hooks" / "guard_dispatch.py"


def _mod():
    spec = importlib.util.spec_from_file_location("guard_dispatch", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture()
def run(tmp_path: Path) -> Path:
    """A run tree shaped enough for `runstate.locate` to find it."""
    d = tmp_path / "run-guard-dispatch"
    (d / "07_qa").mkdir(parents=True)
    (d / f"DMA_Scoring_Workbook_{d.name}.xlsx").write_bytes(b"not a workbook")
    (d / "connectors_baseline.json").write_text(
        json.dumps({"recorded_at": "2026-09-14T00:00:00Z", "present": ["web"]}))
    (d / "07_qa" / "pipeline_state.json").write_text(
        json.dumps({"spent_usd": 3.0, "budget_usd": 20.0,
                    "stages": {"RESEARCH": {"rounds": 1}}}))
    return d


@pytest.fixture()
def guard(run, monkeypatch):
    """The hook, pointed at this run, with the install check satisfied."""
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    monkeypatch.delenv("DMA_ACTOR", raising=False)
    m = _mod()
    monkeypatch.setattr(m, "install_refusal", lambda: "")
    # `brief correlate` opens the workbook; this fixture's is a stub, so the
    # subprocess exits non-zero and the hook treats it as nothing to append —
    # which is the documented behaviour and what the empty-correlate test pins.
    monkeypatch.setattr(m, "correlation", lambda *a, **k: "")
    return m


def _dispatch(agent="research-p1c1-producer", prompt="Work your category."):
    return {"tool_name": "Agent",
            "tool_input": {"subagent_type": f"dma-insights:{agent}",
                           "prompt": prompt}}


def _decision(out) -> str:
    return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecision", "")


def _why(out) -> str:
    return ((out or {}).get("hookSpecificOutput") or {}).get("permissionDecisionReason", "")


# ── the refusals ─────────────────────────────────────────────────────────

def test_no_connector_baseline_denies_the_dispatch(guard, run):
    (run / "connectors_baseline.json").unlink()
    out = guard.decide(_dispatch())
    assert _decision(out) == "deny"
    assert "connectors_baseline.json" in _why(out)
    assert "LOST" in _why(out)         # it says WHY the absence matters


def test_a_refusing_install_denies_the_dispatch(run, monkeypatch):
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    m = _mod()
    monkeypatch.setattr(m, "install_refusal",
                        lambda: "this container's plugin is STALE: 0.9.12")
    out = m.decide(_dispatch())
    assert _decision(out) == "deny"
    assert "STALE" in _why(out)


def test_an_install_that_cannot_be_measured_does_not_refuse(monkeypatch):
    """Fail OPEN: a version check that cannot run must not stop the work."""
    m = _mod()
    stub = types.ModuleType("plugin_version")

    def boom(*a, **k):
        raise RuntimeError("no checkout in this container")
    stub.compare = boom
    monkeypatch.setitem(sys.modules, "plugin_version", stub)
    assert m.install_refusal() == ""


def test_a_non_refusing_install_status_does_not_refuse(monkeypatch):
    """UPDATED_MID_SESSION is not a refusing state: the disk is fixed and
    child processes bind the healed install."""
    m = _mod()
    stub = types.ModuleType("plugin_version")
    stub.compare = lambda *a, **k: {"ok": False, "status": "UPDATED_MID_SESSION"}
    stub.summary = lambda v: "UPDATED_MID_SESSION"
    monkeypatch.setitem(sys.modules, "plugin_version", stub)
    assert m.install_refusal() == ""
    stub.compare = lambda *a, **k: {"ok": False, "status": "STALE"}
    assert "STALE" in m.install_refusal()


def test_an_exhausted_budget_denies_the_dispatch(guard, run):
    (run / "07_qa" / "pipeline_state.json").write_text(
        json.dumps({"spent_usd": 20.5, "budget_usd": 20.0,
                    "stages": {"RESEARCH": {"rounds": 1}}}))
    out = guard.decide(_dispatch())
    assert _decision(out) == "deny"
    assert "ceiling" in _why(out) and "AT_USD_CEILING" in _why(out)


def test_exhausted_rounds_deny_the_dispatch(guard, run):
    (run / "07_qa" / "pipeline_state.json").write_text(
        json.dumps({"spent_usd": 1.0, "budget_usd": 20.0,
                    "stages": {"RESEARCH": {"rounds": 99}}}))
    out = guard.decide(_dispatch())
    assert _decision(out) == "deny"
    assert "rounds" in _why(out)


def test_an_unknown_ceiling_is_not_an_exhausted_one(guard, run):
    (run / "07_qa" / "pipeline_state.json").write_text(
        json.dumps({"stages": {"RESEARCH": {"rounds": 1}}}))
    assert _decision(guard.decide(_dispatch())) != "deny"


def test_another_categorys_cell_in_the_prompt_denies_the_dispatch(guard):
    out = guard.decide(_dispatch(
        prompt="Close P1C1.3, and also handle P3C2.7 while you are in there."))
    assert _decision(out) == "deny"
    assert "P3C2.7" in _why(out) and "leads_in" in _why(out)


def test_a_cell_inside_a_leads_in_block_is_not_contamination(guard):
    prompt = ('Work P1C1.\n\n"leads_in": [{"subcap": "P3C2.7", "e_id": "E-9"}]\n\n'
              "Close your own cells.")
    assert _decision(guard.decide(_dispatch(prompt=prompt))) != "deny"


def test_a_cell_under_an_also_names_heading_is_not_contamination(guard):
    prompt = ("Work P1C1.\n\n### also_names\n- P2C4.11 (the same source)\n"
              "- P4C1.2\n\nNow close your own cells.")
    assert _decision(guard.decide(_dispatch(prompt=prompt))) != "deny"


def test_a_cell_after_the_carve_out_block_has_closed_is_contamination(guard):
    """The carve-out is a block, not a licence for the rest of the prompt."""
    prompt = ('Work P1C1.\n\n"leads_in": [{"subcap": "P3C2.7"}]\n\n'
              "Then go and close P4C3.9 as well.")
    out = guard.decide(_dispatch(prompt=prompt))
    assert _decision(out) == "deny"
    assert "P4C3.9" in _why(out)
    assert "P3C2.7" not in _why(out)


def test_the_lanes_own_cells_are_never_contamination(guard):
    out = guard.decide(_dispatch(prompt="Close P1C1.3, P1C1.4 and P1C1.12."))
    assert _decision(out) != "deny", _why(out)


def test_only_a_category_lane_can_contaminate(guard):
    """A conductor or a specialist names every category by design."""
    for agent in ("research-conductor", "enrichment-web-specialist"):
        out = guard.decide(_dispatch(agent=agent,
                                     prompt="Service P1C1.3 and P3C2.7."))
        assert _decision(out) != "deny", agent


# ── what it leaves alone ─────────────────────────────────────────────────

def test_a_non_dma_agent_call_is_untouched(guard):
    ev = {"tool_name": "Agent",
          "tool_input": {"subagent_type": "general-purpose",
                         "prompt": "Anything at all, including P3C2.7."}}
    assert guard.decide(ev) is None


def test_a_dispatch_with_no_run_to_read_is_allowed(tmp_path, monkeypatch):
    """Fail OPEN: a guard that cannot see the run must not refuse it."""
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.delenv("DMA_RUN_ID", raising=False)
    monkeypatch.setenv("DMA_RUN_ROOT", str(empty))
    m = _mod()
    monkeypatch.setattr(m, "install_refusal", lambda: "")
    assert _decision(m.decide(_dispatch())) != "deny"


# ── the correlation the dispatch carries ─────────────────────────────────

def test_a_correlation_block_is_appended_to_the_prompt(guard, monkeypatch):
    monkeypatch.setattr(guard, "correlation",
                        lambda run, cat: f"# {cat} — evidence another lane registered")
    out = guard.decide(_dispatch(prompt="Work your category."))
    assert _decision(out) == "allow"
    updated = out["hookSpecificOutput"]["updatedInput"]["prompt"]
    assert updated.startswith("Work your category.")
    assert "P1C1 — evidence another lane registered" in updated


def test_an_empty_correlation_changes_nothing(guard, monkeypatch):
    """`{}` means dispatch nothing: a lane handed 'nothing to correlate' has
    paid to read it."""
    monkeypatch.setattr(guard, "correlation", lambda run, cat: "")
    assert guard.decide(_dispatch()) is None


def _stub_cli(m, monkeypatch, *, returncode=0, stdout=""):
    monkeypatch.setattr(m.subprocess, "run",
                        lambda *a, **k: type("R", (), {
                            "returncode": returncode, "stdout": stdout,
                            "stderr": ""})())


def test_the_correlation_block_is_capped(run, monkeypatch):
    """A prompt is a budget. `brief correlate` has its own, larger ceiling;
    the dispatch seam has this one."""
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    m = _mod()                          # the REAL `correlation`, stub CLI
    long = "\n".join(f"line {i} " + "x" * 80 for i in range(200))
    _stub_cli(m, monkeypatch, stdout=json.dumps({"prompt": long}))
    got = m.correlation(m.ctx.locate(), "P1C1")
    assert 0 < len(got) <= m.CORRELATE_CAP + 20
    assert got.endswith("(truncated)")


def test_a_failing_correlate_is_nothing_to_append_never_a_refusal(run, monkeypatch):
    """`brief correlate` is being built by another stream. A non-zero exit, a
    missing subcommand or unreadable output all mean nothing to append — they
    never fail a dispatch."""
    monkeypatch.setenv("DMA_RUN_ID", run.name)
    monkeypatch.setenv("DMA_RUN_ROOT", str(run))
    m = _mod()
    _stub_cli(m, monkeypatch, returncode=2, stdout="")
    assert m.correlation(m.ctx.locate(), "P1C1") == ""
    _stub_cli(m, monkeypatch, returncode=0, stdout="usage: engine.brief ...")
    assert m.correlation(m.ctx.locate(), "P1C1") == ""
    _stub_cli(m, monkeypatch, returncode=0, stdout="{}")
    assert m.correlation(m.ctx.locate(), "P1C1") == ""


# ── the dispatch fingerprint the return reads ────────────────────────────

def test_an_allowed_dispatch_records_what_the_substrate_looked_like(guard, run):
    guard.decide(_dispatch())
    marker = run / "07_qa" / "dispatch" / "research-p1c1-producer.json"
    assert marker.is_file(), "the return cannot say whether the lane wrote"
    doc = json.loads(marker.read_text())
    assert "fingerprint" in doc and doc["fingerprint"].get("wb")


# ── the process contract ─────────────────────────────────────────────────

def _cli(payload: str, env=None) -> subprocess.CompletedProcess:
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run([sys.executable, str(HOOK)], input=payload,
                          capture_output=True, text=True, timeout=180, env=e)


def test_it_fails_open_on_input_it_did_not_parse():
    for payload in ("not json", "", "[1,2,3]"):
        p = _cli(payload)
        assert p.returncode == 0, p.stderr
        assert not p.stdout.strip()


def test_the_guard_can_be_switched_off_without_editing_it(run):
    p = _cli(json.dumps(_dispatch()),
             env={"DMA_RUN_ID": run.name, "DMA_RUN_ROOT": str(run),
                  "DMA_DISPATCH_GUARD": "off"})
    assert p.returncode == 0
    assert not p.stdout.strip()


def test_only_a_searching_lane_is_refused_for_a_missing_baseline(guard, run):
    """A scorer and a report writer read a finished workbook and call no
    connector: the baseline says nothing about whether their work is sound."""
    (run / "connectors_baseline.json").unlink()
    assert _decision(guard.decide(_dispatch("research-p1c1-producer"))) == "deny"
    assert _decision(guard.decide(_dispatch("enrichment-web-specialist"))) == "deny"
    assert _decision(guard.decide(_dispatch("research-challenger"))) == "deny"
    for agent in ("scoring-p1-producer", "report-validator"):
        assert _decision(guard.decide(_dispatch(agent))) != "deny", agent


def test_the_budget_ceiling_stops_every_governed_lane(guard, run):
    """Budget and rounds are about the RUN, not about the tool."""
    (run / "07_qa" / "pipeline_state.json").write_text(
        json.dumps({"spent_usd": 20.5, "budget_usd": 20.0}))
    for agent in ("research-p1c1-producer", "scoring-p1-producer",
                  "report-validator", "enrichment-web-specialist"):
        assert _decision(guard.decide(_dispatch(agent))) == "deny", agent
