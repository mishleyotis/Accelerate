#!/usr/bin/env python3
"""Give every DMA agent an explicit tool allow-list, and make its deny-list complete.

WHY BOTH. `disallowedTools` is a deny-list, so its default is GRANT: a tool
added to the connector tomorrow is available to all 47 agents until someone
remembers 47 files. Measured 2026-08-22, that default had already produced a
real gap —

    only  4 of 47 agents denied all 13 connector write tools
         33 of 47 denied 7 of them, leaving open_payload, append_payload_part
            and the whole findings-memory surface reachable

`open_payload` + `append_payload_part` is how a large page is submitted. Every
one of those 33 agents' descriptions ends "it returns section JSON and never
submits", and every one of them could open an upload and fill it. Separately,
all 33 could write the findings memory the qa-overseer is supposed to own —
including `resolve_finding`, which is precisely the "soften a finding because
the run shipped" move that agent's own charter forbids.

So each agent gets `tools:` (allow, default-deny) AND a `disallowedTools`
completed from the same role definition. They are generated together from one
table, so they cannot disagree; the allow-list is the intent and the deny-list
is the belt to its braces if a runtime honours only one of them.

    python3 scripts/provision_agent_tools.py            # check, exit 1 on drift
    python3 scripts/provision_agent_tools.py --write    # rewrite the frontmatter
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "plugins" / "dma-insights" / "agents"
SERVER = ROOT / "apps" / "mcp" / "server.py"
PREFIX = "mcp__plugin_dma-insights_connector__"

#: Connector tools that MUTATE — serving content, a claim, or the findings
#: memory. Everything else the connector exposes is a read.
WRITE_TOOLS = (
    "claim_run", "register_evidence", "open_payload", "append_payload_part",
    "submit_page_payload", "promote_run", "withdraw_run",
    "record_enrichment", "record_finding", "record_refinement",
    "resolve_finding", "report_recurrence", "ingest_reviewer_feedback",
)
#: The subset that puts CONTENT into the product (invariant 2's door).
CONTENT_TOOLS = ("claim_run", "register_evidence", "open_payload",
                 "append_payload_part", "submit_page_payload", "promote_run",
                 "withdraw_run")
#: The subset that writes what the system has LEARNED.
MEMORY_TOOLS = ("record_finding", "record_refinement", "resolve_finding",
                "report_recurrence", "ingest_reviewer_feedback")
#: Records that an enrichment happened. Producers legitimately need it —
#: the ledger exists to catch "the work was done but it is not showing".
LEDGER_TOOLS = ("record_enrichment",)


def connector_tools() -> list[str]:
    """Read from the server, so a new tool appears here the day it is added."""
    src = SERVER.read_text(encoding="utf-8")
    return re.findall(r"@mcp\.tool\(\)\s*\n(?:@\w+\s*\n)*def (\w+)", src)


BASE = ["Read", "Grep", "Glob", "Bash", "TodoWrite", "Skill"]
RESEARCH = ["WebFetch", "WebSearch"]
#: External research servers these agents actually name in their own text.
#: Listed by server so a rename is one edit, and so an allow-list does not
#: silently drop a capability an agent depends on.
EXTERNAL = {
    "exa":     ["mcp__Exa__web_search_exa", "mcp__Exa__web_fetch_exa"],
    "tavily":  ["mcp__Tavily__tavily_search", "mcp__Tavily__tavily_extract",
                "mcp__Tavily__tavily_crawl", "mcp__Tavily__tavily_map"],
    "clay":    ["mcp__Clay__find-and-enrich-contacts-at-company",
                "mcp__Clay__find-and-enrich-list-of-contacts",
                "mcp__Clay__find-and-enrich-company",
                "mcp__Clay__get-task-context",
                "mcp__Clay__add-contact-data-points",
                "mcp__Clay__add-company-data-points"],
    "quartr":  ["mcp__Quartr__search", "mcp__Quartr__read_transcript",
                "mcp__Quartr__list_conferences", "mcp__Quartr__get_conference"],
    "drive":   ["mcp__Google_Drive__search_files",
                "mcp__Google_Drive__read_file_content",
                "mcp__Google_Drive__download_file_content",
                "mcp__Google_Drive__get_file_metadata"],
}

#: ROLE TABLE. `writes` names the connector write tools this role may call;
#: everything else the connector exposes is denied. `extra` is built-ins.
#:
#: The whole point is that these are role decisions, made once and visible in
#: one place, rather than 47 hand-maintained lists that drift.
ROLES = {
    # The only agent that puts content into the product. Invariant 2 in one row.
    "orchestration/surface-producer": dict(
        writes=CONTENT_TOOLS + LEDGER_TOOLS + MEMORY_TOOLS,
        extra=["Agent", "Write", "Edit"], external=list(EXTERNAL), research=True),
    # Assembles a page and hands it back. Explicitly not a door.
    "orchestration/page-consolidator": dict(
        writes=(), extra=[], external=["exa"], research=True),
    "orchestration/package-vetter": dict(
        writes=(), extra=["Write"], external=["drive"], research=True),
    # Writes what was learned; touches memory, never content.
    "qa/qa-overseer": dict(
        writes=MEMORY_TOOLS + LEDGER_TOOLS, extra=[], external=[], research=False),
    # Edits the toolchain; produces no client content.
    "learning/rectifier": dict(
        writes=MEMORY_TOOLS, extra=["Write", "Edit", "Agent"],
        external=[], research=True),
    "learning/learning-testgen": dict(
        writes=(), extra=["Write", "Edit"], external=[], research=False),
    "learning/learning-grader": dict(
        writes=MEMORY_TOOLS, extra=[], external=[], research=False),
}
#: Directory defaults for the roles not named above.
DEFAULTS = {
    # Per-surface producers: research and read freely, record that an
    # enrichment ran, and touch nothing else.
    "production": dict(writes=LEDGER_TOOLS, extra=[],
                       external=["exa", "tavily", "clay", "quartr", "drive"],
                       research=True),
    "enrichment": dict(writes=LEDGER_TOOLS, extra=[],
                       external=list(EXTERNAL), research=True),
    # Adversaries and auditors: read-only by construction. They exist to
    # disbelieve a result, and an adversary that can repair what it found is
    # not an adversary.
    #
    # They DO get Drive and Tavily reads, added 2026-08-23. A checker asked
    # whether an evidence row's URL is real has two honest answers and one
    # dishonest one: confirm it, refuse it, or — with no way to look — call
    # a row unciteable because it could not see the package that states it.
    # 757 of T. Rowe's 894 items were served without a URL while the package
    # held 748 of them, and nothing in the pipeline could look. Reading is
    # not repairing; these stay writes=() .
    "checkers": dict(writes=(), extra=[],
                     external=["exa", "tavily", "drive"], research=True),
    "qa": dict(writes=(), extra=[],
               external=["exa", "tavily", "drive"], research=True),
    "orchestration": dict(writes=(), extra=[], external=["exa"], research=True),
    "learning": dict(writes=(), extra=[], external=[], research=False),
}


def role_for(rel: str) -> dict:
    key = rel[:-3] if rel.endswith(".md") else rel
    if key in ROLES:
        return ROLES[key]
    return DEFAULTS[key.split("/", 1)[0]]


def lists_for(rel: str, conn: list[str]) -> tuple[list[str], list[str]]:
    role = role_for(rel)
    allowed = list(BASE)
    if role["research"]:
        allowed += RESEARCH
    allowed += role["extra"]
    for name in role["external"]:
        allowed += EXTERNAL[name]
    reads = [t for t in conn if t not in WRITE_TOOLS]
    allowed += [PREFIX + t for t in reads]
    allowed += [PREFIX + t for t in role["writes"]]
    denied = [PREFIX + t for t in conn if t not in role["writes"]
              and t in WRITE_TOOLS]
    if "Write" not in allowed:
        denied = ["Write", "Edit", "NotebookEdit"] + denied
    return allowed, denied


FM = re.compile(r"^---\n(.*?)\n---\n", re.S)


def apply(path: Path, conn: list[str], write: bool) -> bool:
    rel = str(path.relative_to(AGENTS))
    text = path.read_text(encoding="utf-8")
    m = FM.match(text)
    if not m:
        raise SystemExit(f"{rel}: no frontmatter")
    allowed, denied = lists_for(rel, conn)
    body = m.group(1)
    body = "\n".join(l for l in body.split("\n")
                     if not l.startswith(("tools:", "disallowedTools:")))
    body = body.rstrip() + f"\ntools: {', '.join(allowed)}"
    if denied:
        body += f"\ndisallowedTools: {', '.join(denied)}"
    new = f"---\n{body}\n---\n" + text[m.end():]
    if new == text:
        return False
    if write:
        path.write_text(new, encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    conn = connector_tools()
    if not conn:
        raise SystemExit("no connector tools found in server.py")
    drifted = [p for p in sorted(AGENTS.rglob("*.md"))
               if apply(p, conn, args.write)]
    verb = "rewritten" if args.write else "would change"
    print(f"{len(conn)} connector tools · {len(list(AGENTS.rglob('*.md')))} "
          f"agents · {len(drifted)} {verb}")
    for p in drifted[:60]:
        print("   ", p.relative_to(AGENTS))
    return 0 if (args.write or not drifted) else 1


if __name__ == "__main__":
    sys.exit(main())
