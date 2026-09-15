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

THE SECOND MEASUREMENT (2026-09-14). The allow-lists had grown by default in
the other direction. Every research lane held Exa, Tavily and Drive and all
21 connector reads (39 tools); every section producer held five connector
families (50-53); the fleet carried ~3,314 grants, ~1,000 of them external
connectors — and the harness binds none of those into a headless child, so
a lane holding Exa held a refusal and spent turns on it. Owner decision:
connectors are HELD AND CALLED by the orchestrator tier, which batches
queries by capability and assigns the connector per batch; lanes and
producers emit `search_requests`. Drive is granted to no agent (the client
folder lands through `drive_fetch.py` over Bash); Quartr is granted to no
agent (declared, not wired); Indeed only on the technographic scanner.

COUNTING RULE. `CORE` (Read/Grep/Glob/Bash/Skill) is how an agent reads its
run and drives the engine — not counted. K = capability tools: WebSearch,
WebFetch, Write, Edit, Agent, AskUserQuestion and every external connector
tool. K <= 5 for every lane, producer and checker; the five agents in
`CONNECTOR_TIER` exceed it by design, each with its own pinned ceiling. The
plugin's own connector reads are trimmed per role bundle (`READS`) and not
counted — they are the API of the run being produced.

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


#: How an agent reads its run and drives the engine over Bash. Not counted
#: as capability. `TodoWrite` left 2026-09-14: no body names it.
CORE = ["Read", "Grep", "Glob", "Bash", "Skill"]
#: The web pair. Search is a capability; so is fetching a page.
WEB = ["WebSearch", "WebFetch"]
FETCH_ONLY = ["WebFetch"]

#: THE CONNECTOR REGISTRY. One table: `connector_contract.families()` reads
#: this literal out of the file (brace-matched on the assignment), so the
#: doctor, the bootstrap and the Routine prompts all answer from it. Listed
#: by server so a rename is one edit. A family in the registry is not a
#: grant — the role rows below grant, and `drive` and `quartr` are granted
#: to no role at all: Drive reads go through `drive_fetch.py` over Bash and
#: every body that names Quartr says "declared, not wired".
EXTERNAL = {
    "exa":     ["mcp__Exa__web_search_exa", "mcp__Exa__web_fetch_exa"],
    # search + extract only. `crawl`/`map` are whole-site operations no
    # body asks for; a lane holding them had a page-sized context sink.
    "tavily":  ["mcp__Tavily__tavily_search", "mcp__Tavily__tavily_extract"],
    # `find-and-enrich-list-of-contacts` dropped: no body names it, and the
    # contacts pass is one company at a time by design (the poll is the
    # half that was skipped — `get-task-context` is not optional).
    "clay":    ["mcp__Clay__find-and-enrich-contacts-at-company",
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
    # it could reach. A session that has not attached the connector finds
    # the tool absent and says NOT_RUN with that reason.
    "explorium": ["mcp__Vibe_Prospecting__match-business",
                  "mcp__Vibe_Prospecting__enrich-business",
                  "mcp__Vibe_Prospecting__fetch-entities"],
    # Job postings are the highest-yield public signal for the DATA and
    # INFRA layers — a stack a client never announces is still named in the
    # roles it hires for. `search_jobs` is the signal; `get_job_details` and
    # `get_company_data` were never named by a body and are gone.
    # `get_resume` is deliberately absent: a named person's resume is not
    # estate evidence and is not ours to read.
    "indeed":  ["mcp__Indeed__search_jobs"],
    "quartr":  ["mcp__Quartr__search", "mcp__Quartr__read_transcript",
                "mcp__Quartr__list_conferences", "mcp__Quartr__get_conference"],
    "drive":   ["mcp__Google_Drive__search_files",
                "mcp__Google_Drive__read_file_content",
                "mcp__Google_Drive__download_file_content",
                "mcp__Google_Drive__get_file_metadata"],
}

#: Slices of a family, for a role that needs one half of it. `clay/people`
#: is the contacts pass (find, poll, attach); `clay/company` the
#: firmographic-and-technographic pass. Both carry `get-task-context`
#: because polling is the step that was skipped in the 20-contact loss.
SLICES = {
    "clay/people":  ["mcp__Clay__find-and-enrich-contacts-at-company",
                     "mcp__Clay__get-task-context",
                     "mcp__Clay__add-contact-data-points"],
    "clay/company": ["mcp__Clay__find-and-enrich-company",
                     "mcp__Clay__get-task-context",
                     "mcp__Clay__add-company-data-points"],
}


def family_of(name: str) -> str:
    """`clay/people` -> `clay`; `exa` -> `exa`."""
    return name.split("/", 1)[0]


def external_tools(name: str) -> list[str]:
    if name in SLICES:
        return SLICES[name]
    return EXTERNAL[name]


#: CONNECTOR READ BUNDLES. `floor` is what every agent needs to do anything
#: at all (the page contract and the staged payload). Each bundle is what
#: a ROLE reads; a read outside the bundle is granted per agent as
#: `reads_extra` and must be named by that agent's body (tests pin both).
FLOOR = ["get_page_contract", "get_staged_payload"]
READS = {
    "floor": FLOOR,
    # A section producer: the catalogue it maps to, the evidence it cites,
    # the run's memory and report bundle, its progress and rejections, the
    # gate registry and the findings it must not repeat.
    "producer": FLOOR + ["get_capability_catalogue", "get_evidence",
                         "get_memory_digest", "get_report_bundle",
                         "get_run_progress", "list_open_rejections",
                         "explain_gate", "search_findings"],
    # A page router: the digest, the run's progress and the findings memory.
    # It reads its producers' fragments from disk, not from the connector.
    "assembler": FLOOR + ["get_memory_digest", "get_run_progress",
                          "search_findings"],
    # A checker or verifier: everything it re-derives a verdict from, and
    # nothing that would let it reach outside the run it judges.
    "checker": FLOOR + ["get_evidence", "get_capability_catalogue",
                        "get_run_progress", "get_platform_fit",
                        "get_validation_verdict", "explain_gate",
                        "search_findings", "get_client_state"],
    # An enrichment specialist: the client's state and its gaps, the
    # evidence it corroborates, the run it is servicing.
    "enrichment": FLOOR + ["get_client_state", "list_enrichment_gaps",
                           "search_findings", "get_evidence",
                           "get_capability_catalogue", "get_run_progress",
                           "get_memory_digest", "explain_gate"],
    # The learning loop: the findings memory, both directions.
    "memory": FLOOR + ["search_findings", "get_finding", "list_defect_classes",
                       "get_memory_digest", "list_open_findings",
                       "list_open_rejections", "list_reviewer_feedback",
                       "get_validation_verdict"],
    # The one agent that claims, submits and promotes: the queue, the
    # upload state, the verdicts, and the evidence it reconciles across pages.
    "orchestrator": FLOOR + ["get_client_state", "get_evidence",
                             "get_report_bundle", "get_run_progress",
                             "get_validation_verdict", "list_pending_runs",
                             "get_upload_status", "list_withdrawn_runs",
                             "list_open_rejections", "get_memory_digest"],
}


def row(*, web=(), external=(), reads="floor", reads_extra=(), writes=(),
        extra=(), why, core=None) -> dict:
    """One role row. `why` is mandatory: a grant nobody can explain is the
    default this table exists to remove, and the reverse test reads it
    when a body does not name the family itself."""
    return dict(web=list(web), external=list(external), reads=reads,
                reads_extra=list(reads_extra), writes=tuple(writes),
                extra=list(extra), why=why, core=list(core or CORE))


# ── the fourteen role classes ─────────────────────────────────────────────

#: The sixteen category researchers (generated — gen_research_agents.py
#: derives its tools line from THIS row). They write only through the
#: engine CLI over Bash: the workbook refusals are the write control, so
#: Write/Edit stay denied and no connector write is reachable. They hold
#: NO connector: a lane emits `search_requests` and the conductor services
#: them per capability batch. Internal artefacts reach them through the
#: conductor's `drive_fetch.py pull`, on disk under the run root.
RESEARCH_LANE = row(
    web=WEB, reads="floor",
    why="a lane searches the open web and emits every connector query as a "
        "search_requests entry; the orchestrator tier holds the connectors")

#: A per-surface producer: researches on the web, reads the run, records
#: that an enrichment ran, and touches nothing else. Connector corroboration
#: for its surface is serviced by the enrichment specialists.
SECTION_PRODUCER = row(
    web=WEB, reads="producer", writes=LEDGER_TOOLS,
    why="writes one surface from the run and the open web; connector "
        "corroboration is emitted as search_requests and serviced")

#: overview.leadership is WRITTEN from Clay's contacts answer (CONNECTORS.md
#: marks the row ‡): find the contacts, poll the task, attach the data
#: points. The 20-contact loss was the poll being skipped.
PEOPLE_PRODUCER = row(
    web=WEB, external=["clay/people"], reads="producer",
    reads_extra=["list_enrichment_gaps"], writes=LEDGER_TOOLS,
    why="overview.leadership is written from Clay's contacts pass, which "
        "the producer must run and poll itself")

#: techstack.techstack and insights.landscape are WRITTEN from the Explorium
#: register (‡): the app's techstack facet names its sources as exactly
#: {explorium, clay} (apps/api computed.py), so an estate assembled from web
#: search cannot be reconciled against the app's own contract.
TECHNOGRAPHIC_PRODUCER = row(
    web=WEB, external=["explorium"], reads="producer", writes=LEDGER_TOOLS,
    why="the technographic register and its landscape rollup are written "
        "from Explorium's answer, which this producer must call itself")

#: The six page routers. They assemble their producers' fragments and hand
#: the page back; explicitly not a door.
PAGE_ASSEMBLER = row(
    web=WEB, reads="assembler",
    why="routes one page: reads its producers' fragments from disk, the "
        "digest and the run's progress; searches only to settle a conflict")

#: Owns the technographic scan as a deliverable. Writes only Tech_Register,
#: through the engine CLI. It carries EXPLORIUM, CLAY (company slice) and
#: INDEED, and that is the point: the deployed app's techstack facet names
#: its sources as exactly {explorium, clay}. Explorium has three doors and
#: only one needs a key — the Vibe Prospecting connector is authenticated at
#: the session (measured 2026-08-23 at 392 / 357 / 147 named technologies);
#: the INGEST scan is a different path (apps/worker enrichment.py) and its
#: darkness says nothing about the connector. Exa/Tavily corroboration is
#: emitted as search_requests; the conductor services it.
TECHNOGRAPHIC_SCANNER = row(
    web=WEB, external=["explorium", "clay/company", "indeed"], reads="floor",
    why="the scan's spine is Explorium and Clay's company pass; Indeed job "
        "postings are the DATA/INFRA demand signal only this agent reads")

#: The research orchestrator. Dispatches the sixteen lanes, gates, services
#: their `search_requests` per capability batch through the connectors IT
#: holds (Exa search, Tavily fallback/extract, Clay people for the
#: leadership pass), renders and ships. Everything it writes goes through
#: the engine CLI (Bash) — no Write/Edit, no connector writes.
#: AskUserQuestion is load-bearing: the binding preflight REFUSES a run
#: whose sub-vertical and evidence mode were not confirmed by a person.
RESEARCH_CONDUCTOR = row(
    web=WEB, external=["exa", "tavily", "clay/people"], reads="floor",
    extra=["Agent", "AskUserQuestion"],
    why="holds Exa, Tavily and Clay because it services every lane's "
        "search_requests per capability batch; its preflight is the "
        "connector contract's caller")

#: The only agent that puts content into the product. Invariant 2 in one row.
#: No web and no connector: it assembles, reconciles and submits what its
#: producers wrote; a question about the world goes to a producer.
SURFACE_PRODUCER = row(
    reads="orchestrator", writes=CONTENT_TOOLS + LEDGER_TOOLS + MEMORY_TOOLS,
    extra=["Agent", "Write", "Edit"],
    why="claims, assembles, submits and promotes; dispatches producers and "
        "writes their fragments to disk")

#: Services Clay and Explorium `search_requests` and records what each
#: returned. No web: a connector specialist that could fall back to
#: WebSearch would log a connector search it did not run.
CONNECTOR_SPECIALIST = row(
    external=["clay", "explorium"], reads="enrichment", writes=LEDGER_TOOLS,
    why="services the Clay and Explorium batches the orchestrator hands it "
        "and records every result with the tool that produced it")

#: Services Exa/Tavily batches (the relay drain). Exa is the search; Tavily
#: is the fallback and the verbatim-extract path.
WEB_SPECIALIST = row(
    web=WEB, external=["exa", "tavily"], reads="enrichment",
    writes=LEDGER_TOOLS,
    why="services the Exa and Tavily batches the orchestrator hands it; "
        "Tavily extract is its verbatim-excerpt read")

#: Read-only auditors. They exist to disbelieve a result, and an adversary
#: that can repair what it found is not an adversary. WebFetch only: a
#: checker asked whether an evidence row's URL is real may open it; it may
#: not go looking for new evidence.
AUDITOR = row(
    web=FETCH_ONLY, reads="checker",
    why="re-derives a verdict from the run and may open a cited URL to "
        "confirm it; searches for nothing")

#: Verifiers attack a passing result and may search for the falsifier.
VERIFIER = row(
    web=WEB, reads="checker",
    why="attacks a result that already passed and may search the open web "
        "for the falsifier; repairs nothing")

#: Engine-only agents: every write goes through the engine CLI over Bash
#: and the ledger's refusals are the write control. No web: the research
#: stage is closed by the time they run, and what they need is in the
#: workbook.
ENGINE_ONLY = row(
    reads="floor",
    why="works the workbook through the engine CLI; the research stage is "
        "closed and nothing outside the run root is an input")

#: The learning loop: writes what was learned, never content.
MEMORY_WRITER = row(
    reads="memory", writes=MEMORY_TOOLS + LEDGER_TOOLS,
    why="owns the findings memory; touches memory, never content")


#: ROLE TABLE. Keyed by the manifest's path under agents/ (without .md), or
#: by its top-level folder as the default for that folder. `writes` names the
#: connector write tools this role may call; everything else the connector
#: exposes is denied. `extra` is built-ins beyond CORE and the web pair.
ROLES = {
    "orchestration/surface-producer": SURFACE_PRODUCER,
    "orchestration/page-consolidator": ENGINE_ONLY,
    "orchestration/package-vetter": dict(ENGINE_ONLY, extra=["Write"],
                                         why=ENGINE_ONLY["why"] +
                                         "; writes its vetting report as a file"),
    "research/research-conductor": RESEARCH_CONDUCTOR,
    "research/technographic-scanner": TECHNOGRAPHIC_SCANNER,
    # C3-1: the Sonnet challenge pass over research syntheses. It reads
    # nothing but its brief; `engine.cli fetch` over Bash is its only
    # look-up. Read/Bash/Skill only — it greps nothing and globs nothing.
    "research/research-challenger": dict(ENGINE_ONLY, core=["Read", "Bash", "Skill"],
                                         why="challenges a synthesis from its "
                                             "brief alone and records the "
                                             "verdict through engine.cli"),
    "production/overview/overview-people-producer": PEOPLE_PRODUCER,
    "production/techstack/techstack-register-producer": TECHNOGRAPHIC_PRODUCER,
    "production/techstack/techstack-layers-producer": TECHNOGRAPHIC_PRODUCER,
    "production/insights/insights-landscape-producer": TECHNOGRAPHIC_PRODUCER,
    # body-named reads outside the producer bundle
    "production/heatmap/heatmap-focus-producer": dict(
        SECTION_PRODUCER, reads_extra=["list_reviewer_feedback"]),
    "production/insights/insights-cards-producer": dict(
        SECTION_PRODUCER, reads_extra=["list_reviewer_feedback"]),
    "production/heatmap/heatmap-signals-producer": dict(
        SECTION_PRODUCER, reads_extra=["get_client_state"]),
    "production/heatmap/heatmap-valuechain-producer": dict(
        SECTION_PRODUCER, reads_extra=["get_client_state", "list_enrichment_gaps"]),
    "production/overview/overview-opportunity-producer": dict(
        SECTION_PRODUCER, reads_extra=["get_platform_fit"]),
    "production/platform/platform-fit-producer": dict(
        SECTION_PRODUCER, reads_extra=["get_platform_fit"]),
    # the six page routers
    "production/overview/overview-surface-producer": PAGE_ASSEMBLER,
    "production/insights/insights-surface-producer": PAGE_ASSEMBLER,
    "production/context/context-surface-producer": PAGE_ASSEMBLER,
    "production/platform/platform-surface-producer": dict(
        PAGE_ASSEMBLER, reads_extra=["get_platform_fit"]),
    "production/heatmap/heatmap-surface-producer": dict(
        PAGE_ASSEMBLER, reads_extra=["get_evidence"]),
    "production/techstack/techstack-surface-producer": dict(
        PAGE_ASSEMBLER, reads_extra=["get_evidence"]),
    # enrichment
    "enrichment/enrichment-connector-specialist": CONNECTOR_SPECIALIST,
    "enrichment/enrichment-web-specialist": WEB_SPECIALIST,
    "enrichment/enrichment-ledger-auditor": dict(
        AUDITOR, reads_extra=["list_enrichment_gaps"]),
    "enrichment/enrichment-planner": dict(
        AUDITOR, reads_extra=["get_memory_digest", "list_enrichment_gaps",
                              "list_open_findings", "list_open_rejections"]),
    # verifiers
    "qa/adversarial-verifier": VERIFIER,
    "checkers/finding-challenger": VERIFIER,
    # the learning loop
    "qa/qa-overseer": MEMORY_WRITER,
    # No Agent: its body never instructs a dispatch (the grader and testgen
    # are invoked by the dma-rectifier skill's flow, not by this manifest),
    # and a capability nobody is told to use is a grant by habit. Re-grant
    # it the day the body says "dispatch learning-grader via the Agent tool".
    "learning/rectifier": dict(MEMORY_WRITER, writes=MEMORY_TOOLS,
                               extra=["Write", "Edit"],
                               why="edits the toolchain — skills, agents, "
                                   "gates — and records the refinement; "
                                   "produces no client content"),
    "learning/learning-grader": dict(MEMORY_WRITER, writes=MEMORY_TOOLS),
    "learning/learning-testgen": dict(MEMORY_WRITER, writes=(),
                                      extra=["Write", "Edit"],
                                      why="writes test cases as files; "
                                          "records nothing"),
}
#: Directory defaults for the roles not named above.
DEFAULTS = {
    "production": SECTION_PRODUCER,
    "research": RESEARCH_LANE,        # research/categories/*
    "checkers": AUDITOR,
    "qa": AUDITOR,
    "reports": ENGINE_ONLY,           # gen_report_agents.py derives from this
    "scoring": ENGINE_ONLY,           # gen_scoring_agents.py derives from this
    "orchestration": ENGINE_ONLY,
    "learning": MEMORY_WRITER,
    "enrichment": AUDITOR,
}

#: The agents allowed past K = 5, each with its own ceiling. The test suite
#: pins this dict against its own copy, so a new entry is a visible decision.
CONNECTOR_TIER = {
    "research-conductor": 11,
    "surface-producer": 3,
    "technographic-scanner": 9,
    "enrichment-connector-specialist": 8,
    "enrichment-web-specialist": 6,
}


def role_for(rel: str) -> dict:
    key = rel[:-3] if rel.endswith(".md") else rel
    if key in ROLES:
        return ROLES[key]
    return DEFAULTS[key.split("/", 1)[0]]


def lists_for(rel: str, conn: list[str]) -> tuple[list[str], list[str]]:
    """(allowed, denied) for one manifest. `conn` is the connector's tool
    list, read from the server, so a read the bundle names but the server
    no longer exposes is dropped rather than granted into the void."""
    role = role_for(rel)
    allowed = list(role["core"]) + list(role["web"]) + list(role["extra"])
    for name in role["external"]:
        for t in external_tools(name):
            if t not in allowed:
                allowed.append(t)
    reads = list(READS[role["reads"]]) + [r for r in role["reads_extra"]
                                          if r not in READS[role["reads"]]]
    for r in reads:
        if r in WRITE_TOOLS:
            raise SystemExit(f"{rel}: {r} is a write tool, not a read")
        if r not in conn:
            raise SystemExit(f"{rel}: {r} is not a connector tool")
    allowed += [PREFIX + t for t in conn if t in reads]
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
    for p in drifted[:80]:
        print("   ", p.relative_to(AGENTS))
    return 0 if (args.write or not drifted) else 1


if __name__ == "__main__":
    sys.exit(main())
