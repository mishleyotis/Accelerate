"""The diagnostic that names which layer let a prompt through.

Owner, 2026-09-04: Tavily and Exa prompt on every surface and "allow for all
sessions" prompts again. Four layers can remove a prompt and one org control
can put it back over all of them; from the outside they look identical. This
pins the rule matching (Claude Code's documented forms) and that the
diagnostic names the org `ask` layer exactly when every layer here approves.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import why_did_it_prompt as W  # noqa: E402


def test_rule_matching_follows_the_documented_forms():
    t = "mcp__Tavily__tavily_search"
    assert W.rule_matches("mcp__Tavily", t)                 # bare server
    assert W.rule_matches("mcp__Tavily__*", t)              # server wildcard
    assert W.rule_matches("mcp__Tavily__tavily_*", t)       # tool prefix glob
    assert W.rule_matches("mcp__Tavily__tavily_search", t)  # exact
    assert not W.rule_matches("mcp__Tavily", "mcp__claude_ai_Tavily__tavily_search"), (
        "a grant for one spelling must not read as covering the other — that "
        "is the gap this tool exists to show")
    assert not W.rule_matches("mcp__Exa", t)
    assert not W.rule_matches("mcp__*", t), "an unanchored glob approves nothing"
    assert W.rule_matches("WebSearch", "WebSearch")
    assert not W.rule_matches("Bash(python3 -m engine.*)", "Bash")


def test_a_fully_approved_tool_points_at_the_org_control():
    out = W.diagnose("mcp__Tavily__tavily_search")
    assert out["hooks"]["autoapprove_connector.py"] == "allow"
    assert any(out["allow_rules_matching"].values()), out["allow_rules_matching"]
    text = " ".join(out["findings"])
    assert W.ORG_ASK_REASON in text
    assert "/mcp" in text
    assert any("admin" in o for o in out["who_closes_it"])


def test_an_unruled_tool_points_at_the_hook():
    out = W.diagnose("mcp__Exa__deep_researcher_start")
    assert out["hooks"]["autoapprove_connector.py"] is None
    assert any("hook" in f and "no decision" in f for f in out["findings"])


def test_the_cowork_workspace_tool_is_explained():
    out = W.diagnose("mcp__workspace__bash", {"command": "git push"})
    assert any("Cowork" in f for f in out["findings"])


def test_the_surfaces_are_all_named():
    out = W.diagnose("mcp__Tavily__tavily_search")
    for s in ("claude.ai/code web", "Claude Code CLI", "Cowork desktop", "claude.ai chat"):
        assert s in out["surfaces"]
