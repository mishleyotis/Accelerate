"""The documented dispatch topology is the actual one, and there is one
submitter per mode.

Measured 28-09-2026 (QA audit F-C01-021, F-L11-042 pairs 22-23): routing.md
said the page producer "fans the page out" while no page producer held the
Agent tool and the same file said the top session dispatches every stage;
surface-producer.md called itself "the only agent permitted to submit or
promote" and, a hundred lines later, said the driver ships; the session
brief told the surface-producer itself not to submit; and step 4 ordered a
Clay pass from an agent with no Clay tool.
"""
import importlib.util
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[2]
AGENTS = PLUGIN / "agents"
ROUTING = PLUGIN / "skills/dma-surface-production/05-lifecycle/routing.md"
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def _agents():
    for p in sorted(AGENTS.rglob("*.md")):
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = FM.match(text)
        fm, body = m.group(1), text[m.end():]
        tools = {t.strip() for t in re.search(r"^tools:\s*(.*)$", fm, re.M).group(1).split(",")}
        desc = re.search(r"^description:\s*(.*)$", fm, re.M).group(1)
        yield str(p.relative_to(AGENTS)), tools, desc, body


def test_only_the_two_orchestrators_hold_the_agent_tool():
    holders = {rel for rel, tools, _, _ in _agents() if "Agent" in tools}
    assert holders == {"orchestration/surface-producer.md", "research/research-conductor.md"}, holders


def test_no_page_producer_claims_to_dispatch():
    for rel, tools, desc, body in _agents():
        if not rel.endswith("-surface-producer.md") or rel.startswith("orchestration/"):
            continue
        assert "Agent" not in tools, rel
        assert "dispatches nothing" in desc, f"{rel}: the description must say it dispatches nothing"
        low = (desc + body).lower()
        for phrase in ("fanning", "fans the page out", "fan out to", "invoke them in parallel",
                       "the page producer invokes"):
            assert phrase not in low, f"{rel} still claims to {phrase!r}"
        assert "you dispatch nothing" in low or "dispatches nothing" in low, rel


def test_routing_states_one_topology_and_names_both_submitters():
    text = ROUTING.read_text(encoding="utf-8")
    assert "DISPATCHES NOTHING" in text and "ASSEMBLER" in text
    assert "The TOP session runs the\n  page's per-surface producers first" in text.replace("  \n", "\n") \
        or "The TOP session runs the" in text
    assert "fans the page out" not in text and "a page fans out" not in text
    assert "which producers a page assembles" in text
    assert "`surface-producer` on a hand-driven run; on a research-engine run the driver" in text
    assert "F-C01-021" in text


def test_the_surface_producer_is_one_submitter_per_mode_and_holds_what_it_orders():
    rel, tools, desc, body = next(a for a in _agents() if a[0] == "orchestration/surface-producer.md")
    assert "only agent permitted to submit" not in desc
    assert "hand-driven run this is the one agent that submits" in desc
    assert "the driver (engine.pipeline, through ship_page.py --claim) submits" in desc
    assert not any(t.startswith("mcp__Clay__") for t in tools)
    assert "Start Clay enrichment" not in body
    assert "you hold no Clay, Explorium or search\n   tool" in body or "you hold no Clay" in body
    assert "the DRIVER ships" in body, "the driver paragraph stays: it is the rule for engine runs"


def test_the_session_brief_names_both_submitters_and_spares_the_submitter():
    spec = importlib.util.spec_from_file_location(
        "session_brief", PLUGIN / "scripts/hooks/session_brief.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    assert "only the surface-producer" not in sb.CORE
    assert "surface-producer on a hand-driven run" in sb.CORE and "engine.pipeline" in sb.CORE
    top = sb.brief({"hook_event_name": "SubagentStart", "agent_type": "dma-insights:surface-producer"})
    assert "do not submit or promote" not in top
    child = sb.brief({"hook_event_name": "SubagentStart", "agent_type": "dma-insights:overview-hero-producer"})
    assert "do not submit or promote" in child


def test_the_agents_doc_agrees():
    text = (PLUGIN / "docs/AGENTS.md").read_text(encoding="utf-8")
    assert "The only agent permitted to submit or promote" not in text
    assert "Submits and promotes on a hand-driven run" in text
