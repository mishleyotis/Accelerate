#!/usr/bin/env python3
"""PreToolUse on the connector — approve this plugin's own tools, nothing else.

WHY THIS EXISTS (measured 2026-08-21, and it is what had stopped every
scheduled firing of the synthesis routine).

A trigger-fired session bound the connector correctly and then stopped on:

    Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress

There is nobody in a scheduled container to answer that, and the owner has
confirmed the prompt is never surfaced to them either — it is not that the
approval was slow, it is that no human can ever see it. So the firing burns
its twelve-hour slot, stages nothing and records nothing. 178 clients sat
INGESTED behind this (MEM-0118).

Every earlier diagnosis reached for the binding defect (MEM-0112) because
from outside the two are indistinguishable: a session that CANNOT call a tool
and one that is NOT ALLOWED to both simply stop, with the plugin enabled and
the doctor green.

WHY A HOOK RATHER THAN A SETTINGS GRANT. A user-scope `permissions.allow`
entry also works, but only if something writes it BEFORE session start —
which means the environment setup script, wired by hand, per environment,
and silently absent the moment anyone stands up a new one. Project-scope
settings do not work at all: their permission rules are skipped in a
non-interactive session. A hook ships INSIDE the plugin, travels with it, and
needs no environment wiring, so a fresh environment is correct by default.
Both are in place; this is the one that cannot be forgotten.

SCOPE, deliberately narrow. This approves ONLY tools whose name begins with
this plugin's own connector prefix. It cannot approve Bash, a file write, a
web fetch, another MCP server, or anything else — a hook that auto-approved
broadly would be a far worse bug than the one it fixes, and it would be
invisible until it mattered.

It also STANDS ASIDE for the two tools that carry their own PreToolUse
guards. `submit_page_payload` and `promote_run` emit their own decision from
precheck_submit.py / precheck_promote.py, which can still refuse. Approving
them from here as well would put two hooks on one tool with opposite
opinions, and the resolution order is not something to bet a promote on.
"""
import json
import sys

PREFIX = "mcp__plugin_dma-insights_connector__"

# Tools whose own PreToolUse hook owns the decision. Listed here rather than
# excluded by the matcher regex, because a matcher that has to express "all of
# these except two" is a matcher nobody will read correctly later.
GUARDED = {
    PREFIX + "submit_page_payload",   # precheck_submit.py
    PREFIX + "promote_run",           # precheck_promote.py
}

REASON = (
    "dma-insights connector tool, auto-approved by the plugin's own hook: a "
    "scheduled session has nobody to answer a permission prompt. Writes still "
    "pass the connector's server-side validation, gate families and atomic "
    "promote; submit_page_payload and promote_run keep their own precheck "
    "hooks, which this hook does not touch."
)

# ── the enrichment connectors ────────────────────────────────────────────
#
# Measured 2026-08-21T03:09Z: with the connector above approved, the routine
# got through its preflight and the Drive pull, then stopped on
# `mcp__5e0fe4f4-…__search_jobs` — an enrichment connector, same failure
# class, different owner. STEP 0(b) makes these REQUIRED (the routine never
# runs in degrade mode), so a prompt on one of them stops a firing exactly as
# dead as a prompt on ours.
#
# THESE CANNOT BE MATCHED BY SERVER, which is why this list is by tool name.
# A claude.ai connector's server segment is an opaque per-attachment UUID —
# `5e0fe4f4-8fd9-448d-a1b5-fafc63f9aa67` here, and not the connector_uuid the
# Routine record carries — so it is neither stable nor predictable, and a
# server-shaped rule cannot be written for it at all.
#
# The list is therefore an exact allowlist of READ-ONLY research calls: search
# the web, read a page, look up a company or a role. Every one of them fetches
# and returns; none writes anywhere, spends anything, or sends a message. A
# tool whose suffix is not listed draws no decision, so the blast radius of
# this being wrong is "the routine stops and asks", never "the routine did
# something nobody sanctioned".
ENRICHMENT_TOOLS = frozenset({
    # Exa
    "web_search_exa", "web_fetch_exa",
    # Tavily
    "tavily_search", "tavily_extract", "tavily_crawl", "tavily_map",
    "tavily_research",
    # Firecrawl
    "firecrawl_search",
    # Indeed — the one that stopped the run
    "search_jobs", "get_job_details", "get_company_data",
    # Clay
    "find-and-enrich-company", "find-and-enrich-contacts-at-company",
    "find-and-enrich-list-of-contacts", "ask-question-about-accounts",
    "query-objects", "get-current-workspace",
    # Vibe Prospecting / Explorium
    "enrich-business", "match-business", "fetch-entities",
    "fetch-businesses-events", "enrich-prospects", "match-prospects",
    "autocomplete", "show-sample",

    # ── added 2026-08-23, owner: "each time I have to approve MCP tool calls
    # in the routine eg Tavily, Clay etc. Ensure this runs headless." Every
    # one below is a call the routine's own rulebooks REQUIRE, so a prompt on
    # it stops a firing as dead as a prompt on the connector.

    # Clay. get-task-context is the one that mattered most: CG-32 makes it
    # MANDATORY — Clay returns a task HANDLE and the rows arrive only from
    # this call, so a producer that cannot make it reads an acknowledgement
    # as a result. That is the defect CG-32 exists to refuse, and the gap in
    # this list was making it unavoidable. `run_subroutine` and
    # `run_subroutine_direct` are deliberately NOT here: a workspace
    # subroutine is user-authored and can do anything, so it keeps its prompt.
    "get-task-context", "list_subroutines",

    # Vibe Prospecting / Explorium — the rest of the read surface.
    # `export-to-csv` is deliberately absent: it sends data outward.
    "fetch-entities-statistics", "fetch-prospects-events", "get-dataset",
    "estimate-cost", "show-pricing-plans",

    # Firecrawl research — reads papers and public repositories.
    "firecrawl_research_search_papers", "firecrawl_research_read_paper",
    "firecrawl_research_inspect_paper", "firecrawl_research_related_papers",
    "firecrawl_research_search_github",

    # Google Drive, READS ONLY. The routine reads the client's own intake
    # folder through these. Every WRITE — create_file, update_file,
    # share_file, trash_file, copy_file — is absent on purpose: the routine's
    # own writes go through drive_fetch.py on the service account, never
    # through this connector, so there is nothing to allow. get_file_
    # permissions is also absent: it reads, but it reads who can see a
    # document, and that is not enrichment.
    "search_files", "read_file_content", "download_file_content",
    "get_file_metadata", "list_recent_files",

    # Quartr — transcripts and filings for the trajectory and thought-
    # leadership surfaces. Reads only; save_item, write_workspace,
    # move_saved_items and remove_saved_item keep their prompts.
    "list_conferences", "get_conference", "read_transcript",
    "list_saved_items",

    # Context7 and the PDF viewer.
    "resolve-library-id", "query-docs", "list_pdfs", "display_pdf",

    # Dice, beside Indeed's three above.
    "get_company",

    # NOT ADDED, and the reason is the matching rule rather than the tool:
    # this list matches the SUFFIX after the server segment, so a name that
    # is a common English word would allow that word on ANY connector this
    # session ever attaches. LunarCrush's `search`, `list`, `post`, `fetch`,
    # `topic` and `creator` are all in that class. They are not in the
    # routine's required set, so the safe reading is the narrow one.
})

ENRICHMENT_REASON = (
    "read-only enrichment lookup, auto-approved by the dma-insights hook: the "
    "synthesis routine requires these connectors and a scheduled session has "
    "nobody to answer a prompt. Allowlisted by tool name because a claude.ai "
    "connector's server segment is a per-attachment UUID that no rule can "
    "name; every tool on the list fetches and returns, and none writes, "
    "spends or sends."
)


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except Exception:                                        # noqa: BLE001
        # Say nothing rather than guess. No output means no decision, which
        # leaves the tool exactly as it would have been without this hook.
        return 0

    tool = event.get("tool_name")
    if not isinstance(tool, str):
        return 0
    # startswith on the full prefix — never a substring match, never a regex.
    # `mcp__plugin_dma-insights_connector__x` is ours; anything else is not,
    # including a server that merely contains this name inside a longer one.
    if tool.startswith(PREFIX):
        if tool in GUARDED:
            return 0
        return _allow(REASON)

    # An enrichment connector, matched by TOOL NAME because its server segment
    # is an opaque per-attachment UUID. Only ever an MCP tool, and only ever
    # one on the read-only allowlist.
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        suffix = tool.rsplit("__", 1)[1]
        if suffix in ENRICHMENT_TOOLS:
            return _allow(ENRICHMENT_REASON)

    return 0


def _allow(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
