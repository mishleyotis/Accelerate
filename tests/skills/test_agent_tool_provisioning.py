"""Every agent is provisioned by role, and the roles are the invariants.

Measured 2026-08-22, before this existed. All 47 agents carried a
`disallowedTools` deny-list and none carried an allow-list, so the default was
GRANT — and the default had already produced a real gap:

    only  4 of 47 denied all 13 connector write tools
         33 of 47 denied 7 of them

Every one of those 33 is a per-surface producer whose own description ends
"it returns section JSON and never submits", and every one of them could call
`open_payload` and `append_payload_part` — which is how a page too large to
send inline IS submitted. They could not call `submit_page_payload`, so they
could not finish; they could open the door and fill the doorway.

Worse and quieter: all 33 could write the findings memory, `resolve_finding`
included. That is exactly the move the qa-overseer's own charter forbids —
"soften a finding because the run shipped" — available to the agent whose work
the finding is about.

The deny-list could not fix this by being longer, because the failure is its
DIRECTION: a tool added to the connector tomorrow is granted to all 47 until
someone edits 47 files. So both lists are now generated from one role table
(`scripts/provision_agent_tools.py`) and this suite asserts the boundaries
that table exists to hold.
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "plugins" / "dma-insights" / "agents"
SCRIPT = ROOT / "scripts" / "provision_agent_tools.py"

sys.path.insert(0, str(ROOT / "scripts"))
import provision_agent_tools as prov                                # noqa: E402

P = prov.PREFIX
FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
AGENT_FILES = sorted(AGENTS.rglob("*.md"))


def front(path: Path) -> dict:
    m = FM.match(path.read_text(encoding="utf-8"))
    assert m, f"{path.name} has no frontmatter"
    out = {}
    for line in m.group(1).split("\n"):
        if ":" in line and not line.startswith((" ", "-")):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def tools_of(path: Path) -> set:
    return {t.strip() for t in front(path).get("tools", "").split(",") if t.strip()}


def denied_of(path: Path) -> set:
    return {t.strip() for t in front(path).get("disallowedTools", "").split(",")
            if t.strip()}


def rel(path: Path) -> str:
    return str(path.relative_to(AGENTS))


def test_there_are_agents_to_check():
    assert len(AGENT_FILES) >= 40


@pytest.mark.parametrize("path", AGENT_FILES, ids=rel)
def test_every_agent_declares_an_allow_list(path):
    assert tools_of(path), f"{rel(path)} has no tools: line — its default is grant"


@pytest.mark.parametrize("path", AGENT_FILES, ids=rel)
def test_the_two_lists_never_contradict_each_other(path):
    """They are generated together, so an overlap means someone hand-edited
    one of them and a runtime honouring only one would disagree with a
    runtime honouring the other."""
    assert tools_of(path) & denied_of(path) == set(), rel(path)


# ── the boundaries the role table exists to hold ──


CONTENT = [P + t for t in prov.CONTENT_TOOLS]
MEMORY = [P + t for t in prov.MEMORY_TOOLS]


@pytest.mark.parametrize("tool", CONTENT)
def test_exactly_one_agent_may_put_content_into_the_product(tool):
    """Invariant 2 — content enters only through the connector — is only as
    true as the list of agents that can reach the connector's write tools."""
    holders = {rel(p) for p in AGENT_FILES if tool in tools_of(p)}
    assert holders == {"orchestration/surface-producer.md"}, (
        f"{tool} is reachable by {sorted(holders)}")


@pytest.mark.parametrize("tool", MEMORY)
def test_only_the_learning_agents_may_write_the_findings_memory(tool):
    holders = {rel(p) for p in AGENT_FILES if tool in tools_of(p)}
    assert holders <= {"qa/qa-overseer.md", "learning/rectifier.md",
                       "learning/learning-grader.md",
                       "orchestration/surface-producer.md"}, (
        f"{tool} is reachable by {sorted(holders)}")


def test_no_producer_can_open_or_fill_a_chunked_upload():
    """The half-door. `open_payload` + `append_payload_part` is how a large
    page is submitted; denying only `submit_page_payload` leaves a producer
    able to stage one."""
    for p in AGENT_FILES:
        if not rel(p).startswith("production/"):
            continue
        for tool in ("open_payload", "append_payload_part"):
            assert P + tool not in tools_of(p), f"{rel(p)} can {tool}"


def test_an_adversary_cannot_repair_what_it_finds():
    """checkers/ and qa/ exist to disbelieve a result. One that can edit
    files or write content is not an adversary."""
    for p in AGENT_FILES:
        if not rel(p).startswith(("checkers/", "qa/")):
            continue
        assert "Write" not in tools_of(p), rel(p)
        assert "Edit" not in tools_of(p), rel(p)
        for tool in prov.CONTENT_TOOLS:
            assert P + tool not in tools_of(p), f"{rel(p)} can {tool}"


def test_every_agent_can_still_read_the_contract_and_the_catalogue():
    """An allow-list that is too tight is a broken agent, which is worse than
    a permissive deny-list. These two are what every agent needs to do
    anything at all."""
    for p in AGENT_FILES:
        for tool in ("get_page_contract", "get_staged_payload"):
            assert P + tool in tools_of(p), f"{rel(p)} cannot {tool}"


def test_producers_keep_the_research_tools_they_are_told_to_use():
    for p in AGENT_FILES:
        if not rel(p).startswith("production/"):
            continue
        t = tools_of(p)
        assert "WebSearch" in t and "WebFetch" in t, rel(p)
        assert "mcp__Exa__web_search_exa" in t, rel(p)


def test_the_people_producer_can_still_reach_clay():
    """The Clay handoff that dropped 20 contacts is a live concern; an
    allow-list that quietly removed the tool would look like the same defect
    and be much harder to see."""
    t = tools_of(AGENTS / "production" / "overview" / "overview-people-producer.md")
    assert "mcp__Clay__find-and-enrich-contacts-at-company" in t
    assert "mcp__Clay__get-task-context" in t, (
        "polling is the half that was skipped; without the tool it cannot be done")


# ── a new connector tool must not be granted by silence ──


def test_the_write_tool_list_covers_every_mutating_connector_tool():
    """The guard on the guard. If a tool is added to server.py and not
    classified here, it falls through to the read set and is granted to all
    47 agents — the exact default this work removed."""
    known = set(prov.WRITE_TOOLS)
    conn = set(prov.connector_tools())
    unclassified = {t for t in conn - known
                    if t.split("_")[0] in ("submit", "promote", "record",
                                           "resolve", "report", "claim",
                                           "withdraw", "register", "open",
                                           "append", "ingest")}
    assert unclassified == set(), (
        f"mutating-looking connector tools not in WRITE_TOOLS: "
        f"{sorted(unclassified)}")


def test_the_files_match_the_role_table():
    """Run the provisioner in check mode: exit 1 means a frontmatter was
    hand-edited away from its role, which is how 47 lists drifted apart the
    first time."""
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True,
                       text=True, cwd=str(ROOT))
    assert r.returncode == 0, (
        f"agent frontmatter has drifted from the role table:\n{r.stdout}\n"
        f"run: python3 scripts/provision_agent_tools.py --write")
