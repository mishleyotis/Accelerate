# Connectors — what each surface uses, and how access actually works

Owner decisions, 2026-08-20: enrichment runs through the ALREADY
AUTHENTICATED claude.ai connectors — no API keys; and Google Drive runs by
service account (the owner shared the intake folder with the routine
identity, verified: 178 client folders visible). The use case per surface
is recorded below.

## The two access paths

| What | How | One-time setup (done once, works forever) |
|---|---|---|
| **Google Drive** (packages in, memory round-trip) | `scripts/drive_fetch.py` — the dmai-routine service account the container already holds | share the intake folder with `dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com` as Editor — **DONE 2026-08-20** |
| **Enrichment** (Clay · Exa · Tavily · Vibe-Prospecting/Explorium · Indeed) | the claude.ai connectors' own tools (`mcp__<Name>__…`), with the owner's existing authentication | attach the connectors to each Routine in the claude.ai routines UI — already done for drift and rectification; the same edit on **dma-synthesis-sequence** completes it |
| **The dma-insights connector** (the parsed package, submit, promote, memory) | plugin MCP server, auto-connecting (static /mcp + header token) | none |

Rules: the synthesis routine REFUSES to produce without its enrichment
connectors (owner: never degrade mode) — a stopped firing names exactly
what it carried; and nothing is ever fabricated to cover an unattached
connector (MEM-0082). Optional extras (Indeed, LunarCrush, PDF-Viewer)
degrade per facet when absent. API keys
are deliberately NOT used for enrichment (owner, 2026-08-20); the
Secret Manager slots briefly created for them were deleted the same day.
Trigger-fired sessions receive exactly the connectors attached to their
Routine in the UI — attachment is per-Routine and one-time, never
per-session (the org's API cannot attach them; the UI can).

## Approval — reads go through, writes still ask

**Attached is not the same as callable.** A tool a session carries and is not
allowed to call fails exactly like one it never bound: the session stops on
*"Waiting on permission: …"*, and a scheduled container has nobody to answer.
Two mechanisms decide, and they must agree.

| mechanism | where | what it covers |
|---|---|---|
| `hooks/autoapprove_connector.py` | inside the plugin, so it travels with it and needs no environment wiring | the decision of record, per tool |
| `permissions.allow` in **user** settings | written by `bootstrap_session.sh` before session start | the same decision, restated so it survives a session whose hooks bound from a stale install |

The rule is one line: **a read is auto-approved; a write, a publication, a
deletion, a spend, or code somebody else authored still asks.**

- Servers with a **stable segment** (Slack, Salesforce, Google Admin, Auctor,
  GitHub, Google Drive, Quartr, Indeed, Grace) are split tool by tool in
  `SERVER_SURFACES` — `read` is approved, `withheld` is refused **on the
  record**. Listed, not omitted: a tool that is simply absent cannot be told
  apart from one nobody thought about.
- Servers whose segment is a **per-attachment UUID** (the claude.ai enrichment
  connectors) cannot be named exactly, so they are matched by tool-name suffix
  — `ENRICHMENT_TOOLS` approved, `WITHHELD_SUFFIXES` refused.
- The DMA connector's own 33 tools are approved by prefix, except
  `submit_page_payload` and `promote_run`, which stand aside for their own
  precheck hooks.

**A server wildcard in settings is coarser than the hook and overrules it.**
`mcp__<Server>__*` approves the writes too, silently, without the hook being
consulted. So the grant is derived from the hook's own table: a classified
server is granted by **exact read tool name**, and only an unclassified one
gets a wildcard. This was a live defect until 2026-08-30 — Google Drive's
`trash_file` and `share_file` were granted by a wildcard the hook refuses.

Ask the question rather than trusting this table:

```
python3 plugins/dma-insights/scripts/audit_autoapprove.py --strict
```

It runs the **real hook** against `scripts/tests/mcp_roster.txt`, one
subprocess per tool, and reports `ALLOWED · WITHHELD · GUARDED ·
UNCLASSIFIED`. `UNCLASSIFIED` is the finding: a tool on a server the hook
already knows that nobody ever ruled on, prompting on every call forever.
Measured 2026-08-30 before the split existed: **16 of 86 approved.** After:
124 of 184, 58 refused on the record, 2 guarded, **0 unclassified**.

## Slack — a bot token, not a connector (PORTABLE, 2026-08-30)

**Status: code LIVE; the secret is the owner's to provision.**

Until 2026-08-30 the only route to `#deal-desk` was the claude.ai Slack
**connector**, attached per Routine on its own edit screen. That is not
portable in three measured ways:

1. `dma-assessment-intake` carries no connector of any kind, so the queue
   that decides which client to assess could not read its own channel
   (AUD-0190). `update_trigger` cannot attach one; only a human can.
2. **A script can never call a connector tool.** So the triage rule could be
   tested over recorded fixtures and never over the live channel — the read
   half and the decide half could drift with nothing to catch it.
3. Every new Routine, every fresh container, every teammate's session starts
   with no Slack until somebody clicks through a UI.

A bot token in Secret Manager has none of those properties.
`scripts/slack_client.py` reads it by the same three-rung ladder as the
connector path token, works in any process carrying the service-account key,
and is rotated without touching code.

### There is no redirect URL, and that is a design decision

The intake **polls**. It calls `conversations.history`, `conversations.replies`
and `chat.postMessage` outbound, on a schedule. It subscribes to no Slack
events, so there is:

- no request URL for Slack to call,
- no **OAuth redirect URL** — the app is installed once, to one workspace,
  from its own **Install to Workspace** button, which uses Slack's own
  `https://slack.com/oauth/v2/authorize` flow and hands back a bot token;
- no **signing secret** to store, because nothing inbound needs verifying.

If Slack's app-config screen insists on a redirect URL before it will let you
install (it does on some workspace policies), use

```
https://slack.com/oauth/v2/authorize
```

as the OAuth entry and leave **Redirect URLs empty**; only a *distributed*
app (one installable by other workspaces) needs its own callback endpoint,
and this app is internal to one workspace. Do not invent a callback on the
MCP service: there is no handler there, so a redirect pointed at it would
fail closed at install time and read as a Slack problem.

### Scopes the bot needs

| scope | what stops working without it |
|---|---|
| `channels:history` | `conversations.history` — the queue cannot be read |
| `channels:read` | `conversations.info` — the channel name in the transcript |
| `chat:write` | the completion reply |
| `users:read` | display names on replies (degrades to bare ids, not fatal) |

Private channel instead of public → `groups:history` + `groups:read`.
**The bot must also be in the channel**: `/invite @<app>` in `#deal-desk`.
`not_in_channel` is the error that says you skipped this, and
`slack_client.py` names the remedy in the message.

### Provisioning (owner, once)

```bash
printf %s "$SLACK_BOT_TOKEN" | gcloud secrets create dmai-slack-bot-token \
    --project=digital-maturity-assessor --data-file=- --replication-policy=automatic
gcloud secrets add-iam-policy-binding dmai-slack-bot-token \
    --project=digital-maturity-assessor \
    --member="serviceAccount:<the routine service account>" \
    --role=roles/secretmanager.secretAccessor
```

Rotation is `gcloud secrets versions add dmai-slack-bot-token --data-file=-`
and nothing else — the ladder always reads `latest`.

Verify without printing the secret:

```bash
python3 plugins/dma-insights/scripts/slack_client.py whoami
python3 plugins/dma-insights/scripts/slack_intake.py fetch      # channel + threads
python3 plugins/dma-insights/scripts/slack_intake.py triage --transcript /tmp/deal_desk.txt --threads /tmp/threads
```

`whoami` prints team, user and bot id — never the token. No code path in this
repository prints it, and `test_no_source_file_carries_a_literal_bot_token`
fails the build if one is ever committed.

### The connector route still works

Nothing was removed. A session that HAS the Slack connector may still read
the channel with it and save the transcript; `slack_client.py` renders the
API's JSON into that same text shape, so one parser and one set of fixtures
serve both. `test_slack_client.py` proves it by running the real parser over
rendered output and asserting the same verdicts the recordings assert.

## Preflight (STEP 0 of every synthesis firing)

1. `drive_fetch.py check` — REQUIRED: the intake folder answers the SA.
2. Connector-tool presence — REQUIRED (owner: the routine never runs in
   degrade mode): Exa, Tavily and at least one of Clay/Vibe-Prospecting
   present, or the firing STOPS naming exactly what it carries. Attachment
   happens on the Routine's own EDIT screen in the routines UI — the
   connector browse list's Use buttons enable a connector for the org,
   not for a Routine (measured 2026-08-20).
3. The connector roster (33 tools) via the doctor — REQUIRED.

## Per-surface connector use cases

The DMA package itself reaches every surface through the **dma-insights
connector** (the app's package scan ingested it server-side; `drive_fetch.py
pull` additionally lands the raw client folder locally for consultation).
The table lists what each surface uses BEYOND the package, and why.

| Surface (payload section) | Services | Use case |
|---|---|---|
| overview.scores | — | package only: engine scores, peer medians |
| overview.firmographics | Explorium · Tavily | firmographic verification (size, charter, footprint); regulator filings (NCUA/SEC) via web search |
| overview.exec_summary | — | synthesis over other surfaces; no direct enrichment |
| overview.why_now | Exa · Tavily | dated external signals: announcements, filings, leadership statements — each registered with excerpt + URL |
| overview.thought_leadership | Exa | the entity's own publications, talks, bylines |
| overview.leadership | Explorium · Tavily · (Clay) | roster verification, arrivals/departures, profile facts; Clay contact enrichment via its connector |
| overview.financial_series | Tavily | regulator series (call reports, 10-K figures) corroboration |
| overview.sentiment | Tavily | app-store / review aggregate figures with n, scale, as_of |
| overview.findings | — | package + cross-surface reconciliation |
| overview.opportunity | (engine) + the platform set below | tiles mirror platform.platform_story — same factors, same validations |
| heatmap.workbook_scores | — | package only — scores are never enriched (invariant: no fabricated scores) |
| heatmap.focus_areas | Exa · Tavily | corroborate/falsify the named gap per the H3 ladder |
| heatmap.cell_evidence | Exa · Tavily · Indeed* | subcap-specific evidence: artefact vocabulary searches, job postings as demand signals |
| heatmap.evidence | — | the register itself; new rows only via register_evidence |
| heatmap.evidence_age | — | computed from the register |
| heatmap.alerts | — | the ladder's honest residue; queries logged, no new sources |
| heatmap.safeguard_gates | — | server verdicts |
| heatmap.cohort_patterns | — | cross-entity, server-side |
| heatmap.value_chain | — | server-derived (H9 envelope) |
| insights.insights | Exa · Tavily | each card's external claims verified corroborate+falsify before challenge |
| insights.landscape | Explorium · Tavily | peer set facts; T2 recomputes from T1 register |
| platform.platform_story | Clay† · Explorium · Exa · Tavily · Indeed* | greenfield deep-search ladder (family truly absent?); peer deployments; demand signals; alignment quotes from the entity's own words |
| platform.recommendations | Exa · Tavily | feasibility corroboration for each recommendation's premise |
| platform.roadmap | — | sequenced from fit engine + register |
| platform.stairstep | — | engine + package |
| platform.starters | Exa · Tavily | each starter's named gap re-verified before it ships |
| techstack.techstack | Clay† · Explorium | technographic register verification: CONFIRMED needs a source row; ABSENT needs the absence ladder |
| context.timeline | Exa · Tavily | dated events with verbatim excerpts |
| context.issue_register | Tavily | regulator/issue corroboration |
| context.regulatory_standing | Tavily | regulator records (NCUA, SEC, FINRA) |
| context.context_sentiment | Tavily | rated-source aggregates |
| context.acquisitions | Exa · Tavily | deal records, integration statements |

\* Indeed via its claude.ai connector where attached; job-posting demand
signals fall back to Tavily/Exa site-scoped searches where it is not.
† Clay via its claude.ai connector in the correct workspace; a refused
grant records as not-run — never invented technographics (MEM-0082).

## Dispatch mode and where the connectors actually live

The claude.ai connector tools exist ONLY in the top trigger-fired session —
headless children dispatched via `scripts/agent_run.py` (the fallback for
sessions without an Agent tool) do not inherit them. The rule that keeps
enrichment honest across that boundary lives in
`skills/dma-surface-production/05-lifecycle/routing.md` § Dispatch mode:
children emit `search_requests`, the top session runs them through the real
connectors and re-invokes. The dma-insights connector itself reaches every
layer (static /mcp + header token), children included.

Per-facet source detail (tiers, ceilings, query shapes) stays where it
lives: `02-inputs/enrichment_sources.json` and each page rulebook's
"Enrichment pathways" section. This file maps surfaces to services; those
map services to evidence discipline.


## The DMA connector itself in claude.ai — install name: **DMA Insights**

The connector's display name is **DMA Insights** everywhere: its own MCP
initialize response says so, and it is the name to type in claude.ai's
"Add custom connector" dialog. (Inside Claude Code the plugin binds it as
the plugin server `connector`; those tool ids are load-bearing across
agents and hooks and deliberately unchanged.)

Access contract (docs/DECISIONS.md D8): any verified **@zennify.com**
Google account is authorized — humans through the OAuth flow below, the
routine service account through its audience-bound ID token, exactly as
the plugin has always sent it.

### What to type in the dialog

| Field | Value |
|---|---|
| Name | `DMA Insights` |
| URL | `https://dmai-mcp-dukrne5v4a-uc.a.run.app/mcp` — bare, no token segment |
| OAuth Client ID | **leave blank** |
| OAuth Client Secret | **leave blank** |

The Advanced fields stay EMPTY, and that is the correction: this document
used to tell you to paste a Google OAuth client id and secret there. That
never worked and could not — Google publishes no registration endpoint and
issues no refresh token to a standard OAuth client, so the connection
failed to authorize and, when it did connect, expired within the hour.
The connector now runs its own OAuth 2.1 authorization server
(`apps/mcp/dma_mcp/oauth_as.py`) which registers Claude dynamically, so
there is nothing for a human to paste. Google is the identity provider
behind it and still decides who you are.

### The one thing that must be configured, once

The Google OAuth client the server logs people in with needs OUR callback
on its authorized list — not claude.ai's:

```
https://dmai-mcp-dukrne5v4a-uc.a.run.app/oauth/callback
```

Add it at console.cloud.google.com/apis/credentials → the OAuth client →
Authorized redirect URIs. The consent screen should be **Internal**, which
is the Workspace half of the @zennify.com restriction; the gate enforces
the domain server-side regardless.

Then store the client's id and secret, and prove the three of them work
together:

```bash
bash scripts/set_oauth_secret.sh        # reads the secret with echo off
python3 scripts/verify_oauth_client.py  # PASS means Google accepts all three
```

`verify_oauth_client.py` is the check that matters, because every failure
in this chain reaches the dialog as the same sentence — "Authorization
with DMA Insights failed". It distinguishes them: `invalid_client` is a
wrong id/secret pair (measured 2026-08-20: the stored secret was a
24-character placeholder beginning "YOU"), `redirect_uri_mismatch` is the
callback above missing from the client, and `invalid_grant` is the PASS —
the deliberately invalid probe code was the only thing wrong.

### Reading the server's own answer

Every layer states itself, so a failure names its cause:

```bash
M=https://dmai-mcp-dukrne5v4a-uc.a.run.app
curl -s $M/.well-known/oauth-protected-resource      # 200: names the AS
curl -s $M/.well-known/oauth-authorization-server    # 200: registration_endpoint, S256, offline_access
curl -sD- -o /dev/null -X POST $M/mcp                # 401 + WWW-Authenticate: resource_metadata=...
```

A 401 on the two well-known paths means the identity gate is standing
where discovery must be public — the defect fixed on 2026-08-20.
