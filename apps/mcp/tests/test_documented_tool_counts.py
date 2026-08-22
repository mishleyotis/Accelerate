"""A count written in prose drifts; a count nothing checks drifts silently.

`apps/mcp/README.md` opened with "15 production tools per TRD" while the
server exposed 22 of them, and CLAUDE.md said 12 while the server exposed 33.
Both numbers were right when written. Neither had anything holding it to the
code, so every tool added since made them a little more wrong, and a reader
budgeting work against "15 tools" was reading a figure from a different year.

The counts are cheap to hold: the decorator is the source of truth, the split
between the two families is the module each tool delegates to, and both are
readable from the file without importing it (importing `server` wants a
database and an embedding model).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SERVER = ROOT / "apps" / "mcp" / "server.py"
README = ROOT / "apps" / "mcp" / "README.md"
CHARTER = ROOT / "CLAUDE.md"

# memory.py and feedback.py hold the findings store — the "further tools"
# the README counts separately.
MEMORY_MODULES = ("memory_mod", "feedback_mod")


def tools():
    """(production, memory) tool names, by decorator and delegated module."""
    src = SERVER.read_text()
    production, memory = [], []
    for body in src.split("@mcp.tool()")[1:]:
        m = re.search(r"\bdef\s+(\w+)", body)
        assert m, "an @mcp.tool() with no def after it"
        mods = set(re.findall(r"\b(\w+_mod)\.", body))
        (memory if mods & set(MEMORY_MODULES) else production).append(m.group(1))
    return production, memory


def test_the_server_exposes_the_tools_the_readme_counts():
    production, memory = tools()
    head = README.read_text()[:900]
    assert f"{len(production)} production tools" in head, (
        f"README does not say '{len(production)} production tools' — the "
        f"server exposes {len(production)}")
    assert f"{len(memory)} memory" in head or \
           f"({len(memory)} further tools)" in README.read_text(), (
        f"README does not count the {len(memory)} memory/feedback tools")
    assert f"{len(production) + len(memory)} in all" in head


def test_the_charter_names_the_same_total():
    total = sum(len(x) for x in tools())
    assert f"{total} tools" in CHARTER.read_text(), (
        f"CLAUDE.md does not say '{total} tools'")


def test_the_two_families_partition_every_tool():
    """The control: if the module heuristic stopped classifying, both counts
    could still match a README that had been edited to fit."""
    production, memory = tools()
    src = SERVER.read_text()
    decorated = src.count("@mcp.tool()")
    assert len(production) + len(memory) == decorated, (
        f"{decorated} decorated tools, {len(production)}+{len(memory)} "
        f"classified")
    assert set(production).isdisjoint(memory)
    assert len(memory) > 0 and len(production) > 0


def test_a_named_tool_from_each_family_lands_where_it_belongs():
    """A partition test passes trivially if everything lands in one bucket."""
    production, memory = tools()
    assert "promote_run" in production
    assert "submit_page_payload" in production
    assert "record_finding" in memory
    assert "ingest_reviewer_feedback" in memory
