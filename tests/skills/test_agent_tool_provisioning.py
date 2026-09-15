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

2026-09-14, the second measurement. The table had grown by default in the
other direction: every research lane held Exa, Tavily and Drive (39 tools),
every section producer held five connector families (50-53), and the fleet
carried ~3,300 grants of which ~1,000 were external connectors — while the
harness bound none of them into a headless child, so the lanes spent their
turns on refusals. The owner's decision: connectors are held and CALLED by
the orchestrator tier, which batches queries by capability and assigns the
connector per batch; lanes and producers emit `search_requests`. The tests
below pin the holder set per family, a capability ceiling per role, and the
reverse direction — nothing is granted that neither the body nor the role
justifies.
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


#: The four section producers whose SURFACE is sourced from a connector the
#: producer must hold itself (CONNECTORS.md marks those rows with ‡).
PRODUCERS_WITH_A_CONNECTOR = {
    "production/overview/overview-people-producer.md",       # leadership: Clay
    "production/techstack/techstack-register-producer.md",   # techstack: Explorium
    "production/techstack/techstack-layers-producer.md",     # techstack: Explorium
    "production/insights/insights-landscape-producer.md",    # landscape: Explorium
}
CONNECTOR_PREFIXES = ("mcp__Exa__", "mcp__Tavily__", "mcp__Clay__",
                      "mcp__Vibe_Prospecting__", "mcp__Indeed__",
                      "mcp__Quartr__", "mcp__Google_Drive__")


def _connector_tools(t: set) -> set:
    return {x for x in t if x.startswith(CONNECTOR_PREFIXES)}


def test_producers_keep_the_research_tools_they_are_told_to_use():
    """The web pair stays on every producer; the CONNECTORS leave all but the
    four whose surface names one with ‡. A producer that needs Exa emits a
    `search_requests` entry and the orchestrator tier services it."""
    for p in AGENT_FILES:
        if not rel(p).startswith("production/"):
            continue
        t = tools_of(p)
        assert "WebSearch" in t and "WebFetch" in t, rel(p)
        if rel(p) not in PRODUCERS_WITH_A_CONNECTOR:
            assert _connector_tools(t) == set(), (
                f"{rel(p)} holds {sorted(_connector_tools(t))}; connectors "
                f"are the orchestrator tier's — a producer emits search_requests")


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


# ── 2026-09-14: connectors live on the orchestrator tier ──


def _holders(prefix: str) -> set:
    return {Path(rel(p)).stem for p in AGENT_FILES
            if any(t.startswith(prefix) for t in tools_of(p))}


@pytest.mark.parametrize("prefix,expected", [
    ("mcp__Exa__", {"research-conductor", "enrichment-web-specialist"}),
    ("mcp__Tavily__", {"research-conductor", "enrichment-web-specialist"}),
    ("mcp__Clay__", {"research-conductor", "enrichment-connector-specialist",
                     "technographic-scanner", "overview-people-producer"}),
    ("mcp__Vibe_Prospecting__", {"technographic-scanner",
                                 "techstack-register-producer",
                                 "techstack-layers-producer",
                                 "insights-landscape-producer",
                                 "enrichment-connector-specialist"}),
    ("mcp__Indeed__", {"technographic-scanner"}),
    ("mcp__Quartr__", set()),
    ("mcp__Google_Drive__", set()),
])
def test_only_the_connector_tier_holds_a_connector(prefix, expected):
    """Exact holder sets, by family. Quartr is declared and not wired (every
    body that names it says so); Drive reads go through `drive_fetch.py`
    over Bash, so no agent needs the tool and none holds it."""
    assert _holders(prefix) == expected, (
        f"{prefix} holders drifted: {sorted(_holders(prefix))}")


#: The capability tools — what "4-5 tools per agent" counts. CORE
#: (Read/Grep/Glob/Bash/Skill) and the plugin's own connector reads are
#: not capabilities; they are how an agent reads its run.
CAPABILITY_BUILTINS = {"WebSearch", "WebFetch", "Write", "Edit", "Agent",
                       "AskUserQuestion"}


def K(t: set) -> int:
    return len((t & CAPABILITY_BUILTINS) | _connector_tools(t))


#: The five agents that exceed the ceiling, by design, each with its own.
CONNECTOR_TIER = {
    "research-conductor": 11,                # web 2 + Agent/Ask 2 + exa 2 + tavily 2 + clay/people 3
    "surface-producer": 3,                   # Agent, Write, Edit — no web, no connector
    "technographic-scanner": 9,              # web 2 + explorium 3 + clay/company 3 + indeed 1
    "enrichment-connector-specialist": 8,    # clay 5 + explorium 3
    "enrichment-web-specialist": 6,          # web 2 + exa 2 + tavily 2
}


@pytest.mark.parametrize("path", AGENT_FILES, ids=rel)
def test_no_lane_producer_or_checker_exceeds_five_capability_tools(path):
    name = Path(rel(path)).stem
    k = K(tools_of(path))
    ceiling = CONNECTOR_TIER.get(name, 5)
    assert k <= ceiling, (
        f"{rel(path)} holds {k} capability tools (ceiling {ceiling}): "
        f"{sorted((tools_of(path) & CAPABILITY_BUILTINS) | _connector_tools(tools_of(path)))}")


def test_the_connector_tier_is_exactly_the_agents_the_table_names():
    """An agent over 5 that is not in CONNECTOR_TIER is a drift; an agent in
    CONNECTOR_TIER that no longer needs its ceiling should lose the entry."""
    over = {Path(rel(p)).stem for p in AGENT_FILES if K(tools_of(p)) > 5}
    assert over <= set(CONNECTOR_TIER), f"over the ceiling and not in the tier: {sorted(over - set(CONNECTOR_TIER))}"
    assert prov.CONNECTOR_TIER == CONNECTOR_TIER, (
        "the ceilings live in the provisioner and here; they must agree")


def test_the_fleet_tripwire():
    """Measured 2026-09-14 before the change: ~3,314 grants. The role table
    should land near 1,100; anything past 1,300 means a default grew again."""
    total = sum(len(tools_of(p)) for p in AGENT_FILES)
    assert total <= 1300, f"{total} grants across the fleet"


def test_exactly_one_search_connector_per_batch_role():
    """Tavily is the fallback and the extract path; Exa is the search. A
    role holding Tavily search without Exa search would search on the
    fallback, and a role holding either without the other cannot fall back."""
    for p in AGENT_FILES:
        t = tools_of(p)
        if "mcp__Tavily__tavily_search" in t:
            assert "mcp__Exa__web_search_exa" in t, rel(p)
        if "mcp__Exa__web_search_exa" in t:
            assert "mcp__Tavily__tavily_search" in t, rel(p)


# ── the reverse direction: nothing granted without a reason ──


def _body(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    return text[m.end():]


FAMILY_WORD = {
    "exa": r"\bExa\b", "tavily": r"\bTavily\b", "clay": r"\bClay\b",
    "explorium": r"\bExplorium\b|Vibe.Prospecting", "indeed": r"\bIndeed\b",
    "quartr": r"\bQuartr\b", "drive": r"\bDrive\b",
}
INSTRUCTED = {
    "Agent": re.compile(r"\bAgent tool\b|\bvia the Agent\b|\bsubagent|\bdispatch", re.I),
    "AskUserQuestion": re.compile(r"AskUserQuestion"),
}


@pytest.mark.parametrize("path", AGENT_FILES, ids=rel)
def test_no_agent_holds_what_neither_its_body_nor_its_role_floor_justifies(path):
    """The reverse of the body-names-it test. Every granted external family
    must be in the role row AND be named by the body or by the row's
    mandatory `why`; every connector read outside the role's bundle must be
    named by the body; Agent/AskUserQuestion must be instructed, not just
    held."""
    row = prov.role_for(rel(path))
    t = tools_of(path)
    body = _body(path)
    assert row.get("why"), f"{rel(path)}: the role row has no `why`"
    granted_families = {fam for fam, tools in prov.EXTERNAL.items()
                        if any(x in t for x in tools)}
    row_families = {prov.family_of(x) for x in row["external"]}
    assert granted_families <= row_families, (
        f"{rel(path)} holds {sorted(granted_families - row_families)} "
        f"outside its role row")
    for fam in granted_families:
        rx = FAMILY_WORD[fam]
        assert re.search(rx, body) or re.search(rx, row["why"]), (
            f"{rel(path)} holds {fam}; neither its body nor the row's why names it")
    bundle = set(prov.READS[row["reads"]])
    extra_reads = {x[len(P):] for x in t if x.startswith(P)} - bundle \
        - set(prov.WRITE_TOOLS)
    for name in extra_reads:
        assert re.search(rf"\b{name}\b", body), (
            f"{rel(path)} is granted {name} outside the {row['reads']!r} "
            f"bundle and its body never names it")
    for tool, rx in INSTRUCTED.items():
        if tool in t:
            assert rx.search(body), f"{rel(path)} holds {tool} and never instructs it"


def test_the_core_is_the_five_and_todowrite_is_gone():
    """No body names TodoWrite; a tool nobody is told to use is a grant by
    habit. The five core tools are how an agent reads its run and drives
    the engine over Bash."""
    assert prov.CORE == ["Read", "Grep", "Glob", "Bash", "Skill"]
    for p in AGENT_FILES:
        assert "TodoWrite" not in tools_of(p), rel(p)


def test_the_research_challenger_is_engine_only():
    """C3-1: sonnet, medium, Read/Bash/Skill + the two floor reads, no web,
    no connector, no `get_evidence` — it reads nothing but its brief."""
    path = AGENTS / "research" / "research-challenger.md"
    fm = front(path)
    assert fm["model"] == "sonnet" and fm["effort"] == "medium"
    assert fm["maxTurns"] == "60"
    t = tools_of(path)
    assert t == {"Read", "Bash", "Skill", P + "get_page_contract",
                 P + "get_staged_payload"}, sorted(t)
    body = _body(path)
    for dim in ("evidence_sufficiency", "claim_label_fit", "facet_coverage",
                "contradiction_handling", "ceiling_reasoning", "recency",
                "synthesis_quality"):
        assert dim in body, f"the body does not name dimension {dim}"
    assert "engine.cli challenge" in body and "--actor research-challenger" in body
    assert "engine.cli fetch" in body
    assert "NOT FOUND IS NOT DISPROVED" in body
