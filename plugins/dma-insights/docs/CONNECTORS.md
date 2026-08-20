# Connectors — what each surface uses, and how access actually works

Owner instruction, 2026-08-20: connectors must avail their tools without
per-session intervention, and the use case per surface must be written
down. This file is that record.

## The two access paths

| Path | How it authenticates | Where it works |
|---|---|---|
| **Service-account APIs** (the floor) | the dmai-routine key the container holds mints tokens; API keys live in Secret Manager | **every** session, including trigger-fired — `scripts/drive_fetch.py` (Google Drive), `scripts/enrich_api.py` (Exa · Tavily · Clay · Explorium), `scripts/mcp_auth_headers.sh` (the dma-insights connector) |
| **claude.ai connectors** (a bonus) | interactive OAuth in the user's claude.ai account | interactive sessions only — measured repeatedly: they do NOT load in trigger-fired sessions, and this organisation cannot attach them to triggers via API |

Rule: a routine plans around the floor and treats a loaded claude.ai
connector as a faster substitute, never a dependency. A facet whose service
has no stored key records as not-run (MEM-0082) — named, never fabricated.

One-time setup (each already named by the preflights when missing):
Drive — share the intake folder with
`dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com` as Editor;
per service — `printf '%s' 'THE-API-KEY' | gcloud secrets versions add
dmai-<service>-api-key --project=digital-maturity-assessor --data-file=-`.

## Preflight (STEP 0 of every synthesis firing)

1. `drive_fetch.py check` — REQUIRED: the intake folder answers the SA.
2. `enrich_api.py check` — reported: which services are configured; missing
   ones degrade their facets honestly, they do not block production.
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
| overview.leadership | Explorium · Tavily · (Clay) | roster verification, arrivals/departures, profile facts; Clay contact enrichment where its API plan allows |
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

\* Indeed has no key-API floor yet — job-posting demand signals fall back to
Tavily/Exa site-scoped searches in fired sessions; the claude.ai Indeed
connector serves interactive sessions.
† Clay's API surface depends on the workspace plan; `enrich_api.py call`
speaks it where enabled, and a refusal records as not-run — never invented
technographics (MEM-0082).

Per-facet source detail (tiers, ceilings, query shapes) stays where it
lives: `02-inputs/enrichment_sources.json` and each page rulebook's
"Enrichment pathways" section. This file maps surfaces to services; those
map services to evidence discipline.
