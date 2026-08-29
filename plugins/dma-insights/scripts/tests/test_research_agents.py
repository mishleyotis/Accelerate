"""The research tier is generated, and three authorities must agree on it.

The sixteen category researchers are emitted by gen_research_agents.py from
one template plus a name table. That table has two independent counterparts
that predate it — the engine contract's catalogue-derived category list, and
dma-assessment/references/capability_criteria.md's headings — and the whole
point of clustering research BY CATEGORY is that all three mean the same
sixteen grains. A disagreement here is taxonomy drift (the defect class the
v5→v7 17-category incident is pinned under), never something a generator
should paper over.
"""
import json
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
PLUGIN = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(PLUGIN / "skills" / "dma-research"))

import gen_research_agents as gen  # noqa: E402

CRITERIA = (PLUGIN / "skills" / "dma-assessment" / "references" /
            "capability_criteria.md")
PROTOCOL = (PLUGIN / "skills" / "dma-research" / "references" /
            "RESEARCH-PROTOCOL.md")
CATEGORIES_DIR = PLUGIN / "agents" / "research" / "categories"
CONDUCTOR = PLUGIN / "agents" / "research" / "research-conductor.md"
PLUGIN_JSON = PLUGIN / ".claude-plugin" / "plugin.json"


def test_the_manifests_on_disk_are_what_the_template_produces():
    """The freshness gate itself — the same discipline as gen_gates_md.py.
    A hand-edited manifest is sixteen-way drift waiting to happen."""
    assert gen.main(["--check"]) == 0


def test_the_name_table_agrees_with_the_capability_criteria():
    """capability_criteria.md is the assessment skill's own statement of the
    sixteen categories. The generator declares the same names rather than
    scraping them, so this test is the coupling."""
    text = CRITERIA.read_text()
    headings = dict(re.findall(r"^### (P\dC\d): (.+?)\s*$", text, re.M))
    assert headings == gen.CATEGORY_NAMES, (
        f"only in criteria doc: {sorted(headings.items() - gen.CATEGORY_NAMES.items())}; "
        f"only in generator: {sorted(gen.CATEGORY_NAMES.items() - headings.items())}")


def test_the_name_table_agrees_with_the_engine_catalogue():
    """The engine's taxonomy is derived from the pinned v7.0 catalogue —
    sixteen categories, P1C5 retired. A researcher for a category the
    catalogue does not carry researches nothing; a category with no
    researcher is an unworked sixteenth of every run."""
    from engine import contract
    assert list(contract.taxonomy().categories) == sorted(gen.CATEGORY_NAMES)


def test_every_category_has_exactly_one_manifest_and_no_strays():
    on_disk = sorted(p.name for p in CATEGORIES_DIR.glob("*.md"))
    expected = sorted(f"research-{c.lower()}-producer.md"
                      for c in gen.CATEGORY_NAMES)
    assert on_disk == expected


def test_plugin_json_lists_the_conductor_and_all_sixteen():
    declared = set(json.loads(PLUGIN_JSON.read_text())["agents"])
    missing = [p for p in gen.agent_paths() if p not in declared]
    assert not missing, missing
    assert "./agents/research/research-conductor.md" in declared


def test_the_shared_protocol_exists_where_the_manifests_point():
    """Every manifest defers its method to one protocol file. The file lives
    in the dma-research skill (NOT under agents/, where packaging would
    flatten it into the claude.ai roster as a nameless agent)."""
    assert PROTOCOL.is_file()
    rel = "skills/dma-research/references/RESEARCH-PROTOCOL.md"
    for p in [CONDUCTOR, *CATEGORIES_DIR.glob("*.md")]:
        assert rel in p.read_text(), f"{p.name} does not point at {rel}"
    strays = [p for p in (PLUGIN / "agents").rglob("*.md")
              if p.name not in ("README.md",)
              and "name:" not in p.read_text()[:2000]]
    assert not strays, (
        f"non-agent .md under agents/: {[p.name for p in strays]} — "
        f"packaging flattens everything there into the roster")


@pytest.mark.parametrize("cat", sorted(gen.CATEGORY_NAMES))
def test_researchers_cannot_write_score_or_promote(cat):
    """The independence the challenge relies on: a researcher writes through
    the engine CLI (Bash) only — no Write/Edit — and its manifest binds it
    to one category, never to scoring or submission."""
    body = (CATEGORIES_DIR / f"research-{cat.lower()}-producer.md").read_text()
    head = body.split("---")[1]
    m = re.search(r"^disallowedTools:\s*(.+)$", head, re.M)
    assert m, "no disallowedTools line"
    banned = {t.strip() for t in m.group(1).split(",")}
    assert {"Write", "Edit", "NotebookEdit"} <= banned
    assert "never scores" in body and "never promotes" in body
    assert f"--category {cat}" in body, "the binding is the manifest's job"


def test_research_subagents_get_the_research_brief_not_the_production_one():
    """The SubagentStart hook briefs every dispatched child. A category
    researcher told 'produce only the surface you were dispatched for'
    has been handed a rule from the wrong pipeline — after a compaction
    that half-applicable sentence is all it has. The hook routes research
    children to their own brief."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "session_brief", HERE / "hooks" / "session_brief.py")
    sb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sb)
    research = sb.brief({"hook_event_name": "SubagentStart",
                         "agent_type": "dma-insights:research-p1c1-producer"})
    assert "five volleys" in research and "orient" in research
    assert "surface-producer" not in research, (
        "the production submit boundary is meaningless to a researcher and "
        "reads as an instruction anyway")
    producer = sb.brief({"hook_event_name": "SubagentStart",
                         "agent_type": "dma-insights:overview-hero-producer"})
    assert "SUBAGENT" in producer and "surface" in producer
    top = sb.brief({"source": "startup"})
    assert "research-conductor" in top, (
        "the top-session brief must carry the entry fork, or a research "
        "ask gets answered by re-scanning the intake Drive")


def test_the_conductor_is_the_only_research_agent_allowed_to_assemble():
    """The conductor dispatches, gates, renders and assembles; the sixteen
    only research. If a category manifest ever mentions assemble/push the
    split has been violated."""
    for p in CATEGORIES_DIR.glob("*.md"):
        body = p.read_text()
        assert "assemble" not in body.lower(), p.name
        assert "push-package" not in body, p.name
    assert "assemble" in CONDUCTOR.read_text().lower()


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
