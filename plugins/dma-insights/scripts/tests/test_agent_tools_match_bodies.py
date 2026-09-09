"""An agent may only be TOLD to call a tool it is GRANTED.

Owner, 2026-09-03: "ensure the agents assign the correct tools to the
subagents such that they use it as they go through it." The Agent tool
hands a subagent exactly its front-matter `tools:` line and nothing the
orchestrator wishes it had — so a manifest whose BODY says "call
`mcp__Clay__get-task-context`" while its `tools:` line omits it describes a
step the agent cannot take, and the agent either skips it silently or
reports a permission fault as its own missing parameter (CG-32 was born of
exactly that shape).

`scripts/provision_agent_tools.py` generates every `tools:` line from one
role table, so the GRANTS cannot drift from each other. Nothing checked that
the PROSE agrees with the grants. This does, for all 73 manifests, and it
also pins the headless dispatch path: every built-in an agent's grants name
is in `agent_run.ALLOWED`, because `--permission-mode dontAsk` DENIES what is
not pre-approved rather than asking (MEM-0111).
"""
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parents[1]
AGENTS = PLUGIN / "agents"
sys.path.insert(0, str(HERE.parent))
import agent_run  # noqa: E402

FM = re.compile(r"^---\n(.*?)\n---\n", re.S)
MCP_NAME = re.compile(r"mcp__[A-Za-z0-9_-]+__[A-Za-z0-9_-]+")
#: Built-ins whose mention in prose is an INSTRUCTION to use them, as opposed
#: to the verbs "write" and "edit" which appear in every manifest as English.
BUILTIN_INSTRUCTION = {
    "AskUserQuestion": re.compile(r"\bAskUserQuestion\b"),
    "Agent": re.compile(r"\bAgent tool\b|\bvia the Agent\b|\bDispatch .{0,40}\bAgent\b"),
}


def manifests():
    for p in sorted(AGENTS.rglob("*.md")):
        if p.name == "README.md":
            continue
        text = p.read_text(encoding="utf-8")
        m = FM.match(text)
        assert m, f"{p}: no frontmatter"
        fm, body = m.group(1), text[m.end():]
        tools = {t.strip() for t in
                 re.search(r"^tools:\s*(.*)$", fm, re.M).group(1).split(",")}
        dis = re.search(r"^disallowedTools:\s*(.*)$", fm, re.M)
        dis = {t.strip() for t in dis.group(1).split(",")} if dis else set()
        yield p, tools, dis, body


ALL = list(manifests())


def test_the_roster_is_the_size_the_manifest_promises():
    assert len(ALL) == 73


@pytest.mark.parametrize("path,tools,dis,body", ALL,
                         ids=[str(m[0].relative_to(AGENTS)) for m in ALL])
def test_every_mcp_tool_a_body_names_is_granted(path, tools, dis, body):
    named = set(MCP_NAME.findall(body))
    # `mcp__Server__*` in prose names a family; the family must be granted.
    families = set(re.findall(r"mcp__([A-Za-z0-9_-]+)__\*", body))
    granted_families = {t.split("__")[1] for t in tools if t.startswith("mcp__")}
    missing = sorted(n for n in named if n not in tools and not n.endswith("__*"))
    assert not missing, (
        f"{path.name} tells the agent to call {missing} and does not grant it — "
        f"the Agent tool hands a subagent only its tools: line")
    assert families <= granted_families, (
        f"{path.name} names family {sorted(families - granted_families)} it is "
        f"not granted")


@pytest.mark.parametrize("path,tools,dis,body", ALL,
                         ids=[str(m[0].relative_to(AGENTS)) for m in ALL])
def test_no_body_instructs_a_call_its_deny_list_forbids(path, tools, dis, body):
    named = set(MCP_NAME.findall(body))
    # A manifest may NAME a denied tool to say "never call X"; it may not
    # instruct it. Instruction shapes: "call X", "run X", "use X", "X(" .
    instructed = set()
    for n in named & dis:
        if re.search(rf"(call|run|use|invoke|through)\s+`?{re.escape(n)}", body) \
                or f"{n}(" in body:
            instructed.add(n)
    assert not instructed, f"{path.name} instructs a denied tool: {sorted(instructed)}"


@pytest.mark.parametrize("path,tools,dis,body", ALL,
                         ids=[str(m[0].relative_to(AGENTS)) for m in ALL])
def test_a_builtin_a_body_instructs_is_granted(path, tools, dis, body):
    for tool, rx in BUILTIN_INSTRUCTION.items():
        if rx.search(body) and tool not in tools:
            # `AskUserQuestion` is discussed by the intake-facing agents as
            # something they DO NOT have; that is a statement, not an
            # instruction. Only an imperative counts.
            if tool == "AskUserQuestion" and not re.search(
                    r"(with|use|call)\s+\*{0,2}AskUserQuestion", body):
                continue
            pytest.fail(f"{path.name} instructs {tool} and does not grant it")


def test_the_headless_dispatch_pre_approves_every_builtin_the_roster_grants():
    """`claude -p … --permission-mode dontAsk --allowedTools=…` DENIES any tool
    not listed. So every built-in that appears on ANY agent's tools: line must
    be in agent_run.ALLOWED, or that agent starves silently under dispatch."""
    builtins = set()
    for _, tools, _, _ in ALL:
        builtins |= {t for t in tools if not t.startswith("mcp__")}
    allowed = set(agent_run.ALLOWED.split(","))
    # AskUserQuestion is deliberately NOT pre-approved: nobody can answer it
    # in a headless child, and its denial is what sends the conductor to
    # `engine.preflight autobind` instead of hanging.
    missing = sorted(builtins - allowed - {"AskUserQuestion"})
    assert not missing, f"agent_run.ALLOWED lacks {missing}"


def test_the_headless_dispatch_pre_approves_every_connector_family_the_roster_grants():
    families = set()
    for _, tools, _, _ in ALL:
        families |= {"__".join(t.split("__")[:2]) for t in tools if t.startswith("mcp__")}
    allowed = set(agent_run.ALLOWED.split(","))
    missing = sorted(f for f in families if f not in allowed)
    assert not missing, f"agent_run.ALLOWED lacks connector families {missing}"
