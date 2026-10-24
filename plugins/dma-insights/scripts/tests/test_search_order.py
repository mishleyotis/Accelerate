"""The free chain is an order the hook enforces (owner, 2026-10-11): a
research actor batches its questions into ONE research_brief before any
general WebSearch, and never fires general searches severally against it.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "hooks"
sys.path.insert(0, str(HOOKS))
import search_order as so  # noqa: E402


class _Scope:
    def classify(self, name):
        if name.endswith("-collector"):
            return {"class": "category-collector"}
        if name.startswith("research-p"):
            return {"class": "category-researcher"}
        if name == "overview-hero-producer":
            return {"class": "surface-producer"}
        return {"class": ""}


def _marker(tmp_path, available=True, age=0.0):
    d = tmp_path / "layer"
    d.mkdir(parents=True, exist_ok=True)
    (d / "evidence.json").write_text(json.dumps({"service": "evidence", "available": available,
                                                 "ts": time.time() - age}))
    return d


def _p(tool, agent="dma-insights:research-evidence-collector", sid="S1", agent_id="A1", resp=None):
    out = {"tool_name": tool, "agent_type": agent, "session_id": sid, "agent_id": agent_id}
    if resp is not None:
        out["tool_response"] = resp
    return out


def test_a_collector_is_sent_to_the_brief_before_its_first_websearch(tmp_path):
    layer = _marker(tmp_path)
    st = tmp_path / "state"
    why = so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope())
    assert "ONE mcp__plugin_dma-insights_evidence__find_evidence_all_sources" in why and "subcap_ids" in why
    # one brief fired and answered: the general searches are allowed, up to the ceiling
    so.record(_p(so.BRIEF, resp={"cards": [{"card_id": "EV-1"}]}), state_dir=st)
    for _ in range(so.WEB_PER_BRIEF):
        assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
        so.record(_p("WebSearch"), state_dir=st)
    why = so.decide(_p("mcp__Exa__web_search_exa"), state_dir=st, layer_dir=layer, scope=_Scope())
    assert "3 general searches against 1 evidence-engine brief" in why and "keyword_search_web_pages" in why
    # a second brief lifts the ceiling in proportion
    so.record(_p(so.BRIEF, resp={"cards": []}), state_dir=st)
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""


def test_an_engine_error_moves_the_chain_on(tmp_path):
    layer = _marker(tmp_path)
    st = tmp_path / "state"
    so.record(_p(so.BRIEF, resp={"isError": True, "content": [{"type": "text", "text": "service unavailable"}]}),
              state_dir=st)
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
    so.record(_p(so.BRIEF, resp={"needs_spend_approval": True, "cards": []}), state_dir=st)
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""


def test_the_hook_steps_aside_when_the_layer_is_down_or_unknown(tmp_path):
    st = tmp_path / "state"
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=tmp_path / "none", scope=_Scope()) == ""
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=_marker(tmp_path, available=False), scope=_Scope()) == ""
    stale = _marker(tmp_path, available=True, age=so.MARKER_MAX_AGE_S + 60)
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=stale, scope=_Scope()) == ""


def test_only_research_actors_are_ordered_and_counts_are_per_agent(tmp_path):
    layer = _marker(tmp_path)
    st = tmp_path / "state"
    assert so.decide(_p("WebSearch", agent="dma-insights:overview-hero-producer"), state_dir=st,
                     layer_dir=layer, scope=_Scope()) == ""
    assert so.decide(_p("WebSearch", agent=""), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
    assert so.decide(_p("WebFetch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
    so.record(_p(so.BRIEF, agent_id="A1", resp={"cards": []}), state_dir=st)
    assert so.decide(_p("WebSearch", agent_id="A1"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
    assert "no evidence-engine brief yet" in so.decide(_p("WebSearch", agent_id="A2"), state_dir=st,
                                                layer_dir=layer, scope=_Scope())
    assert "no evidence-engine brief yet" in so.decide(_p("WebSearch", agent="dma-insights:research-p1c1-producer",
                                                   agent_id="A3"), state_dir=st, layer_dir=layer, scope=_Scope())


def test_a_corrupt_state_or_marker_fails_open(tmp_path):
    layer = tmp_path / "layer"; layer.mkdir(); (layer / "evidence.json").write_text("{not json")
    st = tmp_path / "state"; st.mkdir(); (st / "S1.json").write_text("{not json")
    assert so.decide(_p("WebSearch"), state_dir=st, layer_dir=layer, scope=_Scope()) == ""
    good = _marker(tmp_path / "ok")
    assert "no evidence-engine brief yet" in so.decide(_p("WebSearch"), state_dir=st, layer_dir=good, scope=_Scope())


def test_the_proxy_writes_the_marker_the_hook_reads(tmp_path, monkeypatch):
    sys.path.insert(0, str(HOOKS.parent))
    import evidence_proxy as ep  # noqa: E402
    monkeypatch.setattr(ep, "LAYER_STATE_DIR", tmp_path / "layer")
    monkeypatch.setitem(ep._cfg, "secret", "dmai-evidence-path-token")
    ep.mark_available(True, None)
    assert so.layer_available(tmp_path / "layer") is True
    ep.mark_available(False, "HTTP 404")
    assert so.layer_available(tmp_path / "layer") is False
    d = json.loads((tmp_path / "layer" / "evidence.json").read_text())
    assert d["reason"] == "HTTP 404" and "token" not in json.dumps(d).lower().replace("path-token", "")


def test_every_per_class_brief_counts_and_the_upstream_name_still_does(tmp_path):
    """Owner, 2026-10-11: the per-class find_* tools are briefs too — a
    collector that chased its unanswered cells with find_regulator_evidence
    earns its WebSearch allowance exactly as the all-sources call does; a
    session bound before the surface shipped still counts research_brief."""
    st = tmp_path / "state"
    for i, tool in enumerate(("mcp__plugin_dma-insights_evidence__find_regulator_evidence",
                              "mcp__plugin_dma-insights_evidence__find_job_posting_evidence",
                              "mcp__plugin_dma-insights_evidence__research_brief")):
        row = so.record(_p(tool, resp={"cards": []}), state_dir=st)
        assert row["briefs"] == i + 1
