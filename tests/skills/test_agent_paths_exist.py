"""Every rooted path an agent is told to read resolves — RC-01, 2026-10-04.

Producers were told to "read `docs/GOLD-STANDARD.md`" before authoring. From
the repository root — where every producer session starts — `docs/` is the
read-only design-docs folder, and no GOLD-STANDARD.md is in it. The file is
`plugins/dma-insights/docs/GOLD-STANDARD.md`. So the one instruction meant to
show a producer the standard before it started pointed at nothing, and
"in line with gold" became a phrase nobody could act on (SWBC gold audit:
slices OH-13, S-11, HM-13, CTX-12, XC-06).

THE RESOLUTION RULE this test fixes, by prefix of the backticked path:

  ${CLAUDE_PLUGIN_ROOT}/…   the plugin's own tree, wherever it is installed
  plugins/dma-insights/…    the repository root
  docs/…                    the repository root — i.e. the design docs. A
                            plugin doc must be named through one of the two
                            rooted forms above, never as a bare `docs/` path

Paths with any other prefix are run-directory or skill-relative and are not
judged here: they have no single root to resolve against.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugins" / "dma-insights"
AGENTS = PLUGIN / "agents"

_TICKED = re.compile(r"`([^`\s]+)`")
_FILE = re.compile(r"\.(md|py|json|txt|ya?ml|sh|html)$")


def _resolve(token: str) -> Path | None:
    if token.startswith("${CLAUDE_PLUGIN_ROOT}/"):
        return PLUGIN / token[len("${CLAUDE_PLUGIN_ROOT}/"):]
    if token.startswith("plugins/dma-insights/"):
        return ROOT / token
    if token.startswith("docs/"):
        return ROOT / token
    return None


def _rooted_paths():
    for md in sorted(AGENTS.rglob("*.md")):
        for n, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
            for token in _TICKED.findall(line):
                token = token.rstrip(".,;:)")
                if "*" in token or "<" in token or "{" in token.replace(
                        "${CLAUDE_PLUGIN_ROOT}", ""):
                    continue                     # a pattern, not a path
                if not _FILE.search(token):
                    continue
                target = _resolve(token)
                if target is not None:
                    yield md.relative_to(ROOT), n, token, target


def test_the_walk_finds_paths_to_judge():
    """Floor: a regex that matched nothing would pass vacuously."""
    assert sum(1 for _ in _rooted_paths()) > 50


def test_every_rooted_agent_path_resolves():
    missing = [f"{md}:{n}: `{token}`" for md, n, token, target
               in _rooted_paths() if not target.exists()]
    assert not missing, (
        "agent files point at paths that do not exist under the root their "
        "prefix names (see this module's docstring for the rule):\n  "
        + "\n  ".join(missing))


def test_the_gold_doc_is_named_where_it_is():
    """The specific instruction RC-01 found broken, pinned by name."""
    for rel in ("orchestration/surface-producer.md",
                "research/research-conductor.md",
                "reports/report-research-producer.md",
                "reports/report-assessment-producer.md"):
        text = (AGENTS / rel).read_text(encoding="utf-8")
        assert "`docs/GOLD-STANDARD.md`" not in text, rel
        assert "plugins/dma-insights/docs/GOLD-STANDARD.md" in text, rel
