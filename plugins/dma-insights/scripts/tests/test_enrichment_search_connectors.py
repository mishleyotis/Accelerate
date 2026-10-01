"""The enrichment inventory names the two search connectors the research tier
runs on, and says who holds them (QA audit F-L11-042 pair 4, 29-09-2026: the
file that answered "which connector serves which facet" did not know Exa or
Tavily, the two the tier uses most)."""
import importlib.util
import json
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
ES = PLUGIN / "skills" / "dma-surface-production" / "02-inputs" / "enrichment_sources.json"


def _provisioner():
    spec = importlib.util.spec_from_file_location(
        "provision_agent_tools", PLUGIN.parents[1] / "scripts" / "provision_agent_tools.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exa_and_tavily_are_named_with_their_holders():
    d = json.loads(ES.read_text(encoding="utf-8"))
    sc = d["search_connectors"]
    prov = _provisioner()
    for name in ("exa", "tavily"):
        assert sc[name]["status"] == "wired"
        assert name in prov.EXTERNAL, name
        assert set(sc[name]["held_by"]) == {"research-conductor", "enrichment-web-specialist"}
    assert "EMITS" in sc["_rule"] and "RESEARCH-PROTOCOL.md" in sc["_rule"]


def test_the_holders_are_the_roles_that_actually_hold_them():
    prov = _provisioner()
    assert "exa" in prov.RESEARCH_CONDUCTOR["external"] and "tavily" in prov.RESEARCH_CONDUCTOR["external"]
    assert "exa" in prov.WEB_SPECIALIST["external"] and "tavily" in prov.WEB_SPECIALIST["external"]
    assert prov.RESEARCH_LANE["external"] == [] and prov.RESEARCH_LANE["web"] == ["WebSearch"]
