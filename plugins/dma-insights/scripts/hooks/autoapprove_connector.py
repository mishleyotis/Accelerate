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
import re
import sys

PREFIX = "mcp__plugin_dma-insights_connector__"

# Tools whose own PreToolUse hook owns the decision. Listed here rather than
# excluded by the matcher regex, because a matcher that has to express "all of
# these except two" is a matcher nobody will read correctly later.
GUARDED_SUFFIXES = {
    "submit_page_payload",            # precheck_submit.py
    "promote_run",                    # precheck_promote.py
}
GUARDED = {PREFIX + t for t in GUARDED_SUFFIXES}

# ── THE SAME CONNECTOR UNDER A DIFFERENT NAME ────────────────────────────
#
# MEASURED 2026-08-31, from the owner: "I keep on getting requests to
# approve the get client state tool." The plugin installs the DMA connector
# as `mcp__plugin_dma-insights_connector__*`, which the PREFIX rule above
# allows. But a Routine attaches the SAME server as a claude.ai connector,
# and the trigger record names it `DMA-Insights` — so in a trigger-fired
# session the very same tool arrives as
# `mcp__DMA-Insights__get_client_state`, matches no rule here, and prompts.
# A scheduled container has nobody to answer, so the firing hangs or dies on
# the one connector the whole pipeline is built around.
#
# `audit_autoapprove.py --strict` passed through all of this, because it
# audits the names this file already knows. That is the same shape as the
# routines canon measuring itself: a check that reads the config it is
# checking can only ever confirm it.
#
# So the DMA connector is matched under a SECOND, exactly-named server
# identity — never by tool name alone under any server. That distinction is
# the whole safety of this rule and an earlier draft of it got this wrong:
# matching `claim_run` under any segment also matched
# `mcp__notplugin_dma-insights_connector__claim_run`, which the lookalike
# test has guarded against since this hook was written. A server whose name
# merely CONTAINS ours is not ours. So the segment is normalised (lowercased,
# separators dropped) and compared for EQUALITY against the identities the
# DMA connector actually attaches under.
#
# `test_autoapprove_connector.py` reconciles the tool set below against
# `apps/mcp/server.py`, so it cannot drift from the 33 the connector serves.
SERVER_IDS = {
    "dmainsights",                    # the claude.ai connector, per trigger
    "plugindmainsightsconnector",     # the plugin install (PREFIX handles it)
}


def _is_ours(server: str) -> bool:
    """Equality on a normalised segment, never a substring."""
    return "".join(ch for ch in server.lower() if ch.isalnum()) in SERVER_IDS


DMA_TOOLS = {
    "get_report_bundle", "get_capability_catalogue", "get_platform_fit",
    "get_page_contract", "get_evidence", "get_run_progress",
    "get_staged_payload", "get_client_state", "list_open_rejections",
    # Read-only: what a chunked upload has already received. Added with the
    # tool itself — a connector tool missing from this set does not fail
    # closed, it PROMPTS, and a scheduled session has nobody to answer.
    "get_upload_status",
    "list_pending_runs", "claim_run", "register_evidence", "open_payload",
    "append_payload_part", "submit_page_payload", "promote_run",
    "withdraw_run", "list_withdrawn_runs", "get_validation_verdict",
    "explain_gate", "record_enrichment", "record_finding", "search_findings",
    "list_open_findings", "list_enrichment_gaps", "get_finding",
    "list_defect_classes", "record_refinement", "resolve_finding",
    "report_recurrence", "get_memory_digest", "list_reviewer_feedback",
    "ingest_reviewer_feedback",
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
    #
    # `mcp__Quartr__search` IS required — the enrichment specialist's own
    # frontmatter grants it — and it is allowed through QUALIFIED_TOOLS
    # below, by its full name, precisely because the suffix alone is unsafe.
})

# ── tools allowed by their FULL name ─────────────────────────────────────
#
# The suffix list above exists because a claude.ai connector's server segment
# is an opaque per-attachment UUID. Not every connector is like that: some
# attach under a stable, human-named segment, and for those the full tool
# name can be written down exactly.
#
# That distinction is what lets a common-word tool be allowed safely. Added
# 2026-08-23 after diffing the allowlist against every MCP tool the plugin's
# own agents and skills name: `mcp__Quartr__search` was the one required call
# the suffix rule could not express, because allowing the bare suffix
# `search` would have allowed `search` on every connector this session ever
# attaches — LunarCrush's included.
#
# Anything added here must be READ-ONLY, like the list above, and must name a
# server segment that is stable rather than a per-attachment UUID.
#
# ── the stable-segment servers, split read from write ────────────────────
#
# Measured 2026-08-30, owner: "check that all MCP connector tools are usually
# autoapproved for all runs; I do not constantly have to approve tool calls."
# Running THIS hook against the 86 MCP tools actually attached to a session
# found 16 approved and 70 prompting. The list above had only ever learned the
# ENRICHMENT connectors, because those are what stopped a scheduled firing;
# every other attached server — Slack, Salesforce, Google Admin, Auctor,
# GitHub, Grace — had never been looked at, and each prompts on every call.
#
# These servers attach under a STABLE, human-named segment, so the full tool
# name can be written down exactly and the suffix rule's hazard (a common word
# allowed on every connector ever attached) does not apply.
#
# `read` is auto-approved. `withheld` is NOT, and is LISTED rather than
# omitted: a tool that is simply absent is indistinguishable from one nobody
# thought about, and that difference is this file's whole subject. Everything
# withheld writes, publishes, deletes, spends, or runs code somebody else
# authored. Nothing is withheld for being merely sensitive to READ — a read is
# a read, and the owner asked not to be prompted for them.
#
# A tool on one of these servers that is in NEITHER set fails the roster
# check, which is how a newly attached tool becomes visible instead of
# silently prompting forever.
SERVER_SURFACES = {
    "Quartr": {
        # Transcripts and filings. `search` is here rather than in the suffix
        # list because the bare word would allow `search` on every connector.
        "read": {"search", "list_conferences", "get_conference",
                 "read_transcript", "list_saved_items"},
        "withheld": {"save_item", "write_workspace", "move_saved_items",
                     "remove_saved_item"},
    },
    "Google_Drive": {
        # The routine's own writes go through drive_fetch.py on the service
        # account, never through this connector. `get_file_permissions` was
        # excluded while this list meant "enrichment"; it is a READ, and the
        # owner's ask is broader than enrichment now.
        "read": {"search_files", "read_file_content", "download_file_content",
                 "get_file_metadata", "list_recent_files",
                 "get_file_permissions"},
        "withheld": {"create_file", "update_file", "share_file", "trash_file",
                     "copy_file"},
    },
    "Slack": {
        # Reading a channel is research. SENDING is publication: it reaches
        # people and it is not retractable, which is why the reply path
        # specified in docs/CLIENT-SELECTION.md §3.5 must be approved by
        # whoever builds the sender, in that same change.
        "read": {"slack_read_canvas", "slack_read_channel",
                 "slack_read_thread", "slack_read_user_profile",
                 "slack_search_channels", "slack_search_public",
                 "slack_search_public_and_private", "slack_search_users"},
        # `slack_send_message` is NOT here: it is CONDITIONAL — allowed
        # into #deal-desk and nowhere else — and a tool cannot be both
        # withheld and conditionally allowed without one of the two records
        # being a lie. See CONDITIONAL_TOOLS.
        "withheld": {"slack_send_message_draft",
                     "slack_schedule_message", "slack_create_canvas",
                     "slack_update_canvas"},
    },
    "Salesforce_Prod": {
        # Reads against the production CRM. Every mutation stays prompting —
        # a create, an update or a delete in production is exactly the class
        # of call a person should still be asked about.
        "read": {"find", "getObjectSchema", "getRelatedRecords",
                 "getUserInfo", "listRecentSobjectRecords", "soqlQuery"},
        "withheld": {"createSobjectRecord", "updateSobjectRecord",
                     "deleteSobjectRecord", "updateRelatedRecord",
                     "deleteRelatedRecord"},
    },
    "Salesforce_Docs": {
        "read": {"salesforce_docs_fetch", "salesforce_docs_search"},
        "withheld": set(),
    },
    "GAdmin_MCP": {
        # The directory is readable; the directory is not editable. Every
        # withheld entry changes a real person's access.
        "read": {"get_user", "list_users", "list_group_members",
                 "list_groups_for_user", "list_license_assignments",
                 "list_org_units"},
        "withheld": {"add_user_to_group", "remove_user_from_group",
                     "remove_user_from_all_groups", "suspend_user",
                     "archive_user", "move_user_to_org_unit",
                     "bulk_offboard_users", "licensing_bulk_swap"},
    },
    "Auctor_MCP": {
        "read": {"auctor_get_artifact", "auctor_get_plan_item",
                 "auctor_get_plan_item_by_key", "auctor_get_space",
                 "auctor_get_user", "auctor_list_artifacts",
                 "auctor_list_plan_items", "auctor_list_plan_types",
                 "auctor_list_spaces", "auctor_list_statuses",
                 "auctor_list_templates", "auctor_list_users"},
        "withheld": {"auctor_create_artifact", "auctor_create_plan_item",
                     "auctor_create_space", "auctor_update_artifact",
                     "auctor_update_plan_item", "auctor_update_space"},
    },
    "Grace_PMO": {
        "read": {"pmo_retrieve_grounding_bundle"},
        "withheld": set(),
    },
    "Indeed": {
        # The other three are already allowed by suffix; get_resume was not,
        # and it is a read like the rest.
        "read": {"search_jobs", "get_job_details", "get_company_data",
                 "get_resume"},
        "withheld": set(),
    },
    "github": {
        # Reading a repository, a PR, a check run or a log is how any review
        # or CI diagnosis starts. Everything that changes the repository or
        # the conversation on it stays prompting, `merge_pull_request` most
        # of all.
        "read": {"get_me", "get_file_contents", "get_commit", "get_tag",
                 "get_label", "get_latest_release", "get_release_by_tag",
                 "get_check_run", "get_job_logs", "get_team_members",
                 "get_teams", "list_branches", "list_commits", "list_issues",
                 "list_issue_fields", "list_issue_types",
                 "list_pull_requests", "list_releases", "list_tags",
                 "list_repository_collaborators", "issue_read",
                 "pull_request_read", "actions_list", "actions_get",
                 "search_code", "search_commits", "search_issues",
                 "search_pull_requests", "search_repositories",
                 "search_users"},
        "withheld": {"create_branch", "create_or_update_file", "delete_file",
                     "push_files", "create_pull_request", "create_repository",
                     "fork_repository", "merge_pull_request",
                     "update_pull_request", "update_pull_request_branch",
                     "enable_pr_auto_merge", "disable_pr_auto_merge",
                     "issue_write", "sub_issue_write", "add_issue_comment",
                     "add_comment_to_pending_review",
                     "add_reply_to_pull_request_comment",
                     "pull_request_review_write", "request_copilot_review",
                     "resolve_review_thread", "unresolve_review_thread",
                     "actions_run_trigger", "run_secret_scanning",
                     "subscribe_pr_activity", "unsubscribe_pr_activity"},
    },
}

#: Read-only tools allowed by their FULL name, derived from the table above so
#: the allowlist and the read/write split cannot drift apart.
QUALIFIED_TOOLS = frozenset(
    f"mcp__{server}__{tool}"
    for server, surface in SERVER_SURFACES.items()
    for tool in surface["read"])

#: The other half, kept so "not approved" is a decision on the record rather
#: than an absence. Nothing reads this at runtime; the roster check does.
WITHHELD_TOOLS = frozenset(
    f"mcp__{server}__{tool}"
    for server, surface in SERVER_SURFACES.items()
    for tool in surface["withheld"])

#: A THIRD disposition: allowed only when an ARGUMENT says so.
#:
#: Added 2026-08-30, when the owner moved the assessment intake onto Slack:
#: the routine reads #deal-desk for requests and, at completion, replies in
#: the request's own thread with the folder link. That last step is a SEND,
#: and a scheduled session has nobody to answer its prompt — the failure that
#: made this hook exist (MEM-0118).
#:
#: Blanket-approving `slack_send_message` would hand every agent in every
#: firing the ability to post anywhere in the workspace. So the decision reads
#: the ARGUMENT: this one channel, and nothing else. The event carries it —
#: `precheck_submit.py` and `deny_credential_ops.py` both read `tool_input`
#: already; this hook simply had never looked.
#:
#: A conditional tool must NOT be listed in any server's `read` set, and the
#: reason is load-bearing: `bootstrap_session.sh` derives user-scope
#: `permissions.allow` entries from those read sets, and a settings grant is
#: honoured WITHOUT the hook being consulted. A read-set entry would therefore
#: approve the send everywhere and the channel check would exist and never
#: run.
#:
#: The predicate returns True to allow. Anything else — a different channel, a
#: missing argument, a malformed event — returns False, which prints NOTHING.
#: Not a deny: a person driving an interactive session must still be able to
#: send, and this hook exists to spare an unattended one a prompt, not to take
#: a decision away from someone who is there to make it.
#: #deal-desk. Declared here because a hook cannot import from `scripts/`
#: (it runs standalone from the installed plugin), and pinned to
#: `slack_intake.DEAL_DESK_CHANNEL_ID` by a test so the two cannot drift.
DEAL_DESK_CHANNEL_ID = "C0AD83KJ4DU"


def _to_deal_desk(args: dict) -> bool:
    """True only for a send into #deal-desk. `channel_id` is the argument the
    tool actually takes; `channel` is accepted because a caller who used the
    other spelling should be refused a silent allow, not handed one."""
    return (args.get("channel_id") or args.get("channel")) == \
        DEAL_DESK_CHANNEL_ID


CONDITIONAL_TOOLS = {
    "mcp__Slack__slack_send_message": {
        "why": ("the DMA intake replies in the request's own thread in "
                "#deal-desk when the assessment is delivered; every other "
                "destination still asks"),
        "scope": f"channel_id == {DEAL_DESK_CHANNEL_ID} (#deal-desk)",
        "test": _to_deal_desk,
    },
}

#: The same record for the connectors matched BY SUFFIX, whose server segment
#: is a per-attachment UUID that no full name can pin. `ENRICHMENT_TOOLS` says
#: what is approved on them; without this, everything else on those servers was
#: merely absent, and absent does not distinguish "we decided against it" from
#: "nobody looked". Each of these was already argued for in the comments above
#: — this is where the argument becomes checkable.
WITHHELD_SUFFIXES = frozenset({
    # Clay — writes into the user's own workspace.
    "add-company-data-points", "add-contact-data-points",
    # Clay — a workspace subroutine is user-authored and can do anything.
    "run_subroutine", "run_subroutine_direct",
    # Vibe Prospecting / Explorium — sends data outward.
    "export-to-csv",
    # Quartr, under an opaque segment: the writes its named entry withholds.
    "save_item", "write_workspace", "move_saved_items", "remove_saved_item",
})

ENRICHMENT_REASON = (
    "read-only enrichment lookup, auto-approved by the dma-insights hook: the "
    "synthesis routine requires these connectors and a scheduled session has "
    "nobody to answer a prompt. Allowlisted by tool name because a claude.ai "
    "connector's server segment is a per-attachment UUID that no rule can "
    "name; every tool on the list fetches and returns, and none writes, "
    "spends or sends."
)


def _canonical(tool: str) -> str:
    """The same tool with its SERVER segment's hyphens turned to underscores.

    A classified server may attach under either spelling — the Routine record
    and this file's tables use `Google_Drive`, the live connector attaches as
    `Google-Drive` — and a full-name rule written one way misses the other.
    Only the server segment (index 1) is touched; the tool id keeps its own
    hyphens (`enrich-business` stays `enrich-business`)."""
    parts = tool.split("__")
    if len(parts) >= 3 and parts[0] == "mcp":
        server = parts[1].replace("-", "_")
        # A connector Claude Code fetches from claude.ai ITSELF attaches as
        # `mcp__claude_ai_<server>__<tool>` (permissions reference, measured
        # 2026-09-04 while chasing Tavily/Exa prompts the owner still saw on
        # every surface). Same server, third spelling; the classified tables
        # and the withheld lists must see through it or a write on Google
        # Drive under this prefix is judged by the verb heuristic alone.
        if server.startswith("claude_ai_"):
            server = server[len("claude_ai_"):]
        parts[1] = server
        return "__".join(parts)
    return tool


# ── verb vocabulary for the resilient default ────────────────────────────
#
# A tool id is a run of words; the WORD is what says read from write. These
# sets are deliberately asymmetric: WRITE is broad (anything that could change,
# send, spend or run something the routine did not author prompts), READ is the
# narrow set of words that only ever fetch and return. WRITE is tested first so
# a compound like `get_and_delete` prompts.
_WRITE_VERBS = frozenset({
    "create", "update", "delete", "remove", "send", "write", "post", "add",
    "set", "merge", "trash", "share", "move", "copy", "upload", "export",
    "run", "exec", "execute", "schedule", "submit", "promote", "save",
    "archive", "suspend", "offboard", "swap", "invite", "revoke", "install",
    "deploy", "publish", "reply", "trigger", "bulk", "draft", "cancel",
    "approve", "reject", "put", "patch", "insert", "drop", "enable", "disable",
    "subscribe", "unsubscribe", "withdraw", "claim", "append", "register",
    "ingest", "resolve", "unresolve", "clear", "edit", "rename", "star",
    "fork", "dispatch", "comment", "assign", "close", "reopen", "sync"})
_READ_VERBS = frozenset({
    "get", "list", "search", "read", "fetch", "find", "download", "query",
    "describe", "show", "view", "lookup", "count", "check", "status",
    "enrich", "match", "autocomplete", "map", "crawl", "extract", "inspect",
    "related", "estimate", "sample", "retrieve", "soql", "display", "explain"})


def _verb_disposition(suffix: str) -> str:
    """'write', 'read', or 'unknown' from the words in a tool id. WRITE wins."""
    words = {w for w in re.split(r"[^a-z0-9]+", str(suffix).lower()) if w}
    if words & _WRITE_VERBS:
        return "write"
    if words & _READ_VERBS:
        return "read"
    return "unknown"


VERB_READ_REASON = (
    "read-only connector tool, auto-approved by the dma-insights hook's "
    "resilient default: the tool id carries a read verb and no write/send "
    "verb, so it fetches and returns. New or renamed read tools are covered "
    "with no rule change; a write, send, or unrecognised verb still prompts, "
    "and the explicit withheld lists win over this classification."
)


#: Built-in (non-MCP) tools this routine runs headless. MEASURED 2026-09-01,
#: owner: "still getting approval prompts" while sixteen research producers ran.
#: Root cause: this hook was wired ONLY to `mcp__.*`, and the enrichment
#: connectors it covers are not the whole story — the producers' PRIMARY
#: retrieval is the BUILT-IN `WebSearch` and `WebFetch`, which no auto-approve
#: hook matched and `permissions.allow` did not list, so every one fell through
#: to a prompt. They are READ-ONLY web reads (no state written anywhere), the
#: exact tools a headless research routine must run without a human. `Bash` is
#: deliberately NOT here — it has its own deny hooks and auto-approving every
#: shell call from this hook would wave through far more than web reads.
#: hooks.json registers this hook against the `WebSearch` and `WebFetch`
#: matchers as well as `mcp__.*`, so this branch actually fires.
READ_ONLY_BUILTINS = frozenset({"WebSearch", "WebFetch"})
BUILTIN_WEB_REASON = (
    "read-only web retrieval (WebSearch/WebFetch) — the research routine's "
    "primary evidence-gathering tools, auto-approved so it runs headless")


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
    # Built-in read-only web tools first: they carry no `mcp__` prefix, so none
    # of the connector logic below would ever reach them.
    if tool in READ_ONLY_BUILTINS:
        return _allow(BUILTIN_WEB_REASON)
    # startswith on the full prefix — never a substring match, never a regex.
    # `mcp__plugin_dma-insights_connector__x` is ours; anything else is not,
    # including a server that merely contains this name inside a longer one.
    if tool.startswith(PREFIX):
        if tool in GUARDED:
            return 0
        return _allow(REASON)

    # The same connector attached under a claude.ai server name. Everything
    # the PREFIX branch allows, allowed here too — EXCEPT the guarded pair,
    # and that exception is not symmetry for its own sake. The precheck
    # hooks are registered in hooks.json against tool-name matchers; if a
    # matcher does not fire for this server segment, auto-approving here
    # would wave a submit or a promote through with NO precheck at all.
    # Leaving them to prompt fails closed: a prompt in a scheduled session
    # stops the firing, which is the safe direction for the two calls that
    # write serving content.
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        parts = tool.split("__")
        server, suffix = parts[1], parts[-1]
        if (_is_ours(server) and suffix in DMA_TOOLS
                and suffix not in GUARDED_SUFFIXES):
            return _allow(REASON)

    # Allowed only when an ARGUMENT says so. Checked before the name rules
    # because it is the strictest of the three: it is the only one that can
    # say "this destination and no other".
    cond = CONDITIONAL_TOOLS.get(tool)
    if cond:
        args = event.get("tool_input")
        try:
            ok = bool(cond["test"](args if isinstance(args, dict) else {}))
        except Exception:                                    # noqa: BLE001
            ok = False
        if ok:
            return _allow(f"{cond['why']}. Scoped: {cond['scope']}.")
        # NOT a deny. No output leaves the call exactly as it would be
        # without this hook, so a person in an interactive session can still
        # send wherever they meant to.
        return 0

    # A connector that attaches under a stable, nameable server segment, so
    # its full tool name can be written down exactly. This is checked BEFORE
    # the suffix rule because it is the stricter of the two.
    #
    # MEASURED 2026-09-01, owner: still prompting on Google-Drive / Vibe-
    # Prospecting. The SERVER_SURFACES keys are written with underscores
    # (Google_Drive), but the connector attaches under a HYPHEN segment
    # (Google-Drive) in this environment — so the exact full name missed and
    # the read fell through to a prompt. The tool SUFFIX never carries this
    # ambiguity (it is the connector's own tool id), so only the SERVER
    # segment is canonicalised, hyphen to underscore, before the lookup.
    if tool in QUALIFIED_TOOLS or _canonical(tool) in QUALIFIED_TOOLS:
        return _allow(ENRICHMENT_REASON)

    # An enrichment connector, matched by TOOL NAME because its server segment
    # is an opaque per-attachment UUID. Only ever an MCP tool, and only ever
    # one on the read-only allowlist.
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        suffix = tool.rsplit("__", 1)[1]
        if suffix in ENRICHMENT_TOOLS:
            return _allow(ENRICHMENT_REASON)

    # ── the resilient default: classify by VERB, so a tool nobody listed is
    # still handled the moment it appears (owner 2026-09-01: "even when new
    # tools surface or tool names change, everything is already factored in").
    #
    # The explicit tables above are the RECORD of specific decisions; this is
    # the rule that does not need editing when a connector adds `get_widgets`
    # or renames `search` to `search_v2`. A READ verb in the tool id approves;
    # a WRITE/SEND verb prompts; a name that carries neither prompts, because a
    # tool this rule cannot read is exactly the one a person should still see.
    # WRITE wins over READ (a `get_and_delete` is a delete), and the explicit
    # WITHHELD lists win over both, so a known write named with a read verb
    # (github `resolve_review_thread`) still prompts.
    if tool.startswith("mcp__") and tool.count("__") >= 2:
        suffix = tool.rsplit("__", 1)[1]
        if (tool in WITHHELD_TOOLS or _canonical(tool) in WITHHELD_TOOLS
                or suffix in WITHHELD_SUFFIXES):
            return 0
        disp = _verb_disposition(suffix)
        if disp == "read":
            return _allow(VERB_READ_REASON)
        # "write" and "unknown" both fall through to a prompt.

    return 0


def _allow(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": reason,
    }}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                                        # noqa: BLE001
        # A hook must NEVER crash: a non-zero exit is an error the harness can
        # act on, and no output is no decision (the tool prompts) — the safe
        # direction. An internal bug must degrade to a prompt, never to a
        # broken session. This is the resilience floor beneath every rule above.
        sys.exit(0)
