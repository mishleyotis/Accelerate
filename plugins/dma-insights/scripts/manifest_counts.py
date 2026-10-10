#!/usr/bin/env python3
"""The counts the install ads state, derived from what they count.

WHY THIS EXISTS (Interac, 2026-10-10 — and every DMA session before it).
`plugin.json` said "(35 tools)" while `apps/mcp/server.py` registered 36, and
`marketplace.json` said "(34 tools)" and "74 DMA agents" while the manifest
listed 76. Each was a number somebody typed when a tool or an agent landed,
so each drifted the next time one landed without the typing. The doctor's
roster row then failed at the start of every DMA session, the run-assessment
command told the session to "report the row and stop", and the owner was
asked about a cosmetic string instead of the client.

A typed copy of a count is the defect; a test that the copy matches is only
the alarm. So the numbers are DERIVED here from their sources, and
`--write` rewrites both manifests from them:

  tools   the `@mcp.tool()` functions in apps/mcp/server.py — the connector
          this checkout deploys (deploy.sh builds dmai-mcp from it)
  agents  the `agents` list in plugin.json — which `doctor.expected_agents`
          already reads, so the count and the roster cannot disagree

and `marketplace.json`'s plugin entry carries plugin.json's description
VERBATIM, so there is one ad, not two. Adding a tool or an agent is then one
command (`manifest_counts.py --write`), and `--check` (CI, and the test
beside this file) fails a PR that forgets it — at review time, never at the
start of a client's run.

    manifest_counts.py --check        # exit 1 on drift, names each field
    manifest_counts.py --write        # rewrite both manifests in place
    manifest_counts.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
REPO = PLUGIN.parent.parent

TOOLS_RE = re.compile(r"\((\d+) tools\)")
AGENTS_RE = re.compile(r"\b(\d+) DMA agents\b")
#: A decorated function: `@mcp.tool(...)`, any further decorators, then def.
_TOOL_DEF = re.compile(
    r"^@mcp\.tool\([^)]*\)\s*\n(?:@[^\n]*\n)*\s*(?:async\s+)?def\s+(\w+)",
    re.MULTILINE)


def server_tools(repo_root: Path | None = None) -> list[str] | None:
    """The tool names the checkout's connector registers, or None when this
    tree carries no connector source (an installed plugin cache, a zip)."""
    src = Path(repo_root or REPO) / "apps" / "mcp" / "server.py"
    try:
        return _TOOL_DEF.findall(src.read_text())
    except OSError:
        return None


def _paths(repo_root: Path | None):
    root = Path(repo_root or REPO)
    return (root / "plugins" / "dma-insights" / ".claude-plugin" / "plugin.json",
            root / ".claude-plugin" / "marketplace.json")


def _entry(market: dict) -> dict | None:
    return next((p for p in market.get("plugins") or []
                 if p.get("name") == "dma-insights"), None)


def _count(regex, text: str | None) -> int | None:
    m = regex.search(text or "")
    return int(m.group(1)) if m else None


def drift(repo_root: Path | None = None) -> dict:
    """Every stated count against its source. `problems` empty == in sync."""
    plugin_p, market_p = _paths(repo_root)
    manifest = json.loads(plugin_p.read_text())
    market = json.loads(market_p.read_text()) if market_p.is_file() else {}
    tools = server_tools(repo_root)
    want = {"tools": len(tools) if tools is not None else None,
            "agents": len(manifest.get("agents") or [])}
    desc = manifest.get("description") or ""
    have = {"tools": _count(TOOLS_RE, desc), "agents": _count(AGENTS_RE, desc)}
    problems = []
    for key in ("tools", "agents"):
        if want[key] is None:
            continue                      # no source in this tree to compare
        if have[key] is None:
            problems.append(f"plugin.json description states no {key} count")
        elif have[key] != want[key]:
            problems.append(f"plugin.json says {have[key]} {key}; the source "
                            f"has {want[key]}")
    entry = _entry(market)
    if market and entry is None:
        problems.append("marketplace.json lists no dma-insights entry")
    elif entry is not None and (entry.get("description") or "") != desc:
        problems.append("marketplace.json's dma-insights description is not "
                        "plugin.json's (it says "
                        f"{_count(TOOLS_RE, entry.get('description'))} tools, "
                        f"{_count(AGENTS_RE, entry.get('description'))} agents)")
    return {"want": want, "have": have, "problems": problems,
            "tools": tools or []}


def write(repo_root: Path | None = None) -> dict:
    plugin_p, market_p = _paths(repo_root)
    d = drift(repo_root)
    raw = plugin_p.read_text()
    manifest = json.loads(raw)
    desc = manifest.get("description") or ""
    if d["want"]["tools"] is not None:
        desc = (TOOLS_RE.sub(f"({d['want']['tools']} tools)", desc)
                if TOOLS_RE.search(desc) else
                desc.rstrip(".") + f" (the connector: {d['want']['tools']} tools).")
    desc = AGENTS_RE.sub(f"{d['want']['agents']} DMA agents", desc)
    if desc != manifest.get("description"):
        manifest["description"] = desc
        plugin_p.write_text(json.dumps(manifest, indent=2) + "\n")
    if market_p.is_file():
        market = json.loads(market_p.read_text())
        entry = _entry(market)
        if entry is not None and entry.get("description") != desc:
            entry["description"] = desc
            market_p.write_text(json.dumps(market, indent=2) + "\n")
    return drift(repo_root)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--check", action="store_true")
    g.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--repo", default=None)
    a = ap.parse_args(argv)
    out = write(a.repo) if a.write else drift(a.repo)
    if a.json:
        print(json.dumps({k: v for k, v in out.items() if k != "tools"},
                         indent=1))
    else:
        print(f"source: {out['want']['tools']} tools, "
              f"{out['want']['agents']} agents; plugin.json states "
              f"{out['have']['tools']} tools, {out['have']['agents']} agents")
        for p in out["problems"]:
            print(f"  DRIFT {p}")
        if out["problems"]:
            print("  -> python3 plugins/dma-insights/scripts/manifest_counts.py "
                  "--write")
    return 1 if out["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
