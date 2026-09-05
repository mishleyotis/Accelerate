"""Every agent tier gets ITS brief — and a stale install refuses the work.

Measured 2026-09-03: `session_brief.brief()` routed by the substring
"research-", so `report-research-producer` received the category
researcher's brief ("fire five volleys, engine.brief dispatch --category
<YOURS>") and `report-assessment-producer`, `report-validator` and the four
scoring producers received the production submit-boundary rule and no word
about templates, preconditions or the scoring stage. The install check
warned and repaired nothing.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "dma-insights"


def _sb():
    spec = importlib.util.spec_from_file_location(
        "session_brief", PLUGIN / "scripts" / "hooks" / "session_brief.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _brief(agent: str) -> str:
    return _sb().brief({"hook_event_name": "SubagentStart",
                        "agent_type": f"dma-insights:{agent}"})


def test_report_producers_get_the_report_brief_not_the_research_one():
    for agent in ("report-research-producer", "report-assessment-producer",
                  "report-validator"):
        t = _brief(agent)
        assert "narrative preconditions" in t, agent
        assert "references/templates/" in t and "gold_reference.json" in t, agent
        assert "engine.gold_standard report" in t, agent
        assert "engine.brief dispatch" not in t, agent
        assert "five volleys" not in t, agent
        assert "produce only the surface" not in t, agent


def test_the_scoring_tier_is_told_open_has_no_force():
    for agent in ("scoring-p1-producer", "scoring-p4-producer", "scoring-critic"):
        t = _brief(agent)
        assert "engine.assessment state" in t, agent
        assert "NO --force" in t, agent
        assert "engine.assessment gate" in t and "gold_reference.json" in t, agent
        assert "engine.brief dispatch" not in t, agent


def test_category_researchers_still_get_the_research_brief():
    for agent in ("research-p1c1-producer", "research-p4c4-producer",
                  "technographic-scanner"):
        t = _brief(agent)
        assert "five volleys" in t and "engine.brief dispatch" in t, agent
        assert "surface-producer" not in t, agent


def test_production_subagents_keep_the_production_brief():
    t = _brief("overview-hero-producer")
    assert "SUBAGENT" in t and "surface" in t
    assert "narrative preconditions" not in t


def test_a_stale_install_refuses_research_work(monkeypatch):
    sb = _sb()
    import sys
    import types
    fake = types.SimpleNamespace(
        compare=lambda: {"ok": False, "status": "STALE"},
        summary=lambda v: "STALE: installed 0.9.12 (47 agents) vs published 1.17.0 (74 agents)")
    monkeypatch.setitem(sys.modules, "plugin_version", fake)
    text = sb.install_warning()
    assert "RESEARCH, SCORING AND REPORT WORK IS REFUSED" in text
    assert "doctor.py --heal" in text
    assert "engine.pipeline run" in text
    # the healed-mid-session state is NOT a refusal
    fake.compare = lambda: {"ok": False, "status": "UPDATED_MID_SESSION"}
    text = sb.install_warning()
    assert "IS REFUSED" not in text and "doctor.py --heal" in text
    # an OK install says nothing
    fake.compare = lambda: {"ok": True, "status": "OK"}
    assert sb.install_warning() == ""


def test_the_top_session_brief_carries_the_install_verdict():
    sb = _sb()
    top = sb.brief({"source": "startup"})
    assert "research-conductor" in top
