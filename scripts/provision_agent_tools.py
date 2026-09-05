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
    # Explorium, through the Vibe Prospecting connector. It is authenticated
    # AT THE SESSION — no key, no Secret Manager — and the plugin's own
    # auto-approve hook already allowlists exactly these three tool names
    # (scripts/hooks/autoapprove_connector.py). Measured 2026-08-23 on three
    # promoted clients it returned 392 / 357 / 147 named technologies, so a
    # producer recording NOT_RUN for this facet was recording it for a source
    # it could reach. Grant it; a session that has not attached the connector
    # finds the tool absent and says NOT_RUN with that reason, which is the
    # honest failure rather than a silent web fallback.
    "explorium": ["mcp__Vibe_Prospecting__match-business",
                  "mcp__Vibe_Prospecting__enrich-business",
                  "mcp__Vibe_Prospecting__fetch-entities"],
    # Job postings are the highest-yield public signal for the DATA and
    # INFRA layers — a stack a client never announces is still named in the
    # roles it hires for. `get_resume` is deliberately absent: a named
    # person's resume is not estate evidence and is not ours to read.
    "indeed":  ["mcp__Indeed__search_jobs", "mcp__Indeed__get_job_details",
                "mcp__Indeed__get_company_data"],
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
    # Orchestrates the research run: dispatches the sixteen category
    # researchers, gates, renders and ships. Everything it writes goes
    # through the engine CLI (Bash) — no Write/Edit, no connector writes.
    # AskUserQuestion is load-bearing, not a convenience: the binding
    # preflight REFUSES a run whose sub-vertical and evidence mode were not
    # confirmed by a person, and an agent that cannot ask cannot start one.
    # Owns the technographic scan as a deliverable rather than as a side
    # effect. Writes only Tech_Register, through the engine CLI.
    #
    # It carries EXPLORIUM, CLAY and INDEED, and that is the point rather
    # than a convenience. The deployed app's techstack facet names its
    # sources as exactly {explorium, clay} (apps/api computed.py; the mcp
    # server's `record_enrichment` source vocabulary), so a scan assembled
    # from whatever a web search happened to surface produces an estate the
    # app cannot reconcile against its own contract.
    #
    # Explorium has THREE doors and only one needs a key. The Vibe
    # Prospecting MCP connector is authenticated AT THE SESSION and answers —
    # measured 2026-08-23 at 392 / 357 / 147 named technologies across three
    # promoted clients — which is why it is granted here. The INGEST scan is
    # a DIFFERENT path and does need a Secret Manager key it does not have
    # (apps/worker/dma_worker/enrichment.py); its darkness says nothing about
    # the connector, and conflating the two cost every run its technographics
    # once already. Where the connector is not attached, an export the owner
    # drops in the client folder is the third door and
    # `engine.techscan import-explorium` parses it. Every row is recorded
    # with the provider that produced it; none of them can be implied.
    "research/technographic-scanner": dict(
        writes=(), extra=[],
        external=["explorium", "clay", "indeed", "exa", "tavily", "drive"],
        research=True),
    "research/research-conductor": dict(
        writes=(), extra=["Agent", "AskUserQuestion"], external=["drive"],
        research=True),
    # The report tier. Producers write sections through the engine CLI
    # (Bash) and read the finished run; the validator writes nothing at all,
    # because `engine.narrative review` refuses a verdict from a section's
    # own author and an agent that could edit what it judges would be
    # working around that rule rather than under it.
    "reports/report-research-producer": dict(
        writes=(), extra=[], external=["drive"], research=True),
    "reports/report-assessment-producer": dict(
        writes=(), extra=[], external=["drive"], research=True),
    "reports/report-validator": dict(
        writes=(), extra=[], external=["exa", "tavily", "drive"],
        research=True),
    # THE SEVEN SURFACES CONNECTORS.md SOURCES FROM EXPLORIUM OR INDEED.
    # The `production` default below gives every surface producer exa,
    # tavily, clay, quartr and drive. Five surfaces need more, and the
    # per-surface table in docs/CONNECTORS.md has said so all along while
    # nothing joined the two: measured 2026-08-30, the table assigned
    # Explorium to overview.firmographics, overview.leadership,
    # insights.landscape, platform.platform_story and techstack.techstack,
    # and not one web-app surface producer declared it. An agent that does
    # not DECLARE a tool cannot call it, so the doc said Explorium verifies
    # the technographic register while the agent writing that register had
    # no way to ask Explorium anything.
    #
    # These are per-agent rather than a wider default because the table is
    # per-surface: granting all thirty producers a contact-and-firmographic
    # connector to serve five of them widens the surface for the other
    # twenty-five with nothing asking for it.
    # `scripts/tests/test_connector_provisioning.py` re-derives the join
    # from the doc on every run, so a section that moves between producers
    # fails there rather than drifting quietly.
    "production/overview/overview-hero-producer": dict(          # firmographics
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "explorium"],
        research=True),
    "production/overview/overview-people-producer": dict(        # leadership
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "explorium"],
        research=True),
    "production/insights/insights-landscape-producer": dict(     # landscape
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "explorium"],
        research=True),
    "production/techstack/techstack-register-producer": dict(    # T1 register
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "explorium"],
        research=True),
    "production/techstack/techstack-layers-producer": dict(      # T2 rollup
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "explorium"],
        research=True),
    # Job postings are a demand signal: platform_story argues greenfield and
    # cell_evidence reads hiring as artefact vocabulary.
    "production/platform/platform-fit-producer": dict(           # platform_story
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive",
                  "explorium", "indeed"],
        research=True),
    "production/heatmap/heatmap-evidence-producer": dict(        # cell_evidence
        writes=LEDGER_TOOLS, extra=[],
        external=["exa", "tavily", "clay", "quartr", "drive", "indeed"],
        research=True),
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
    # The sixteen category researchers (generated — gen_research_agents.py
    # derives its tools line from THIS table). They write only through the
    # engine CLI over Bash: the workbook refusals are the write control, so
    # Write/Edit stay denied and no connector write is reachable. Drive
    # reads are for INTERNAL/HYBRID evidence in the client folder; the
    # toolkits come via drive_fetch.py under Bash.
    "research": dict(writes=(), extra=[],
                     external=["exa", "tavily", "drive"], research=True),
    # The SCORING stage (generated — gen_scoring_agents.py derives its tools
    # line from THIS table): four pillar scorers and one critic. They write
    # only through `engine.assessment` over Bash — the ledger's refusals are
    # the write control — so Write/Edit stay denied and no connector write is
    # reachable. Drive reads are for the internal artefacts a HYBRID score
    # rests on; exa/tavily let a scorer re-open a cited source, never search
    # for new evidence (the research stage is closed by the time they run).
    "scoring": dict(writes=(), extra=[],
                    external=["exa", "tavily", "drive"], research=True),
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
