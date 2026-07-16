# 95-client corpus stress-test — empty-surface classification (2026-07-09)

Purpose: for every DMA surface, sweep all 95 active clients, find where a
surface is empty, and **dig into each empty to decide whether it is an
extraction/wiring bug (fixable in the scripts) or genuine information
unavailability (an enrichment candidate — never fabricate).** Findings drive
the script fixes; the honest-null cases are queued for Clay/Explorium/Gemini
enrichment rather than papered over.

Method: run against the full PG15 corpus (95 entities / 95 active runs, 15,230
`evidence_index` rows, 873 insight cards). `scratchpad/stress_audit.py` +
targeted per-field probes. Every "fix" is verified by re-measuring the live
corpus, not by assuming non-empty == correct.

## Surface coverage (before → after this pass)

| Surface / field | Empty (of 95) | Verdict | Action |
|---|---|---|---|
| `runs.scqa` | 95 | **WIRING** — analyst SCQA prose is persisted as a `document_sections` row (`executive_summary_scqa`, 95/95 present) and served on D1 via `section_routing`; `package_persist` intentionally stores `runs.scqa=None`. The NLP layer reads `runs.scqa`, so the L4 storyline spine never sees it. | Pending — wire `load_entity_state` to read the section body when `runs.scqa` is empty; thread the thesis into persisted `top_findings`. (Rendered impact is gated on threading the thesis into `derive_insights`, which today calls `compose_findings` without a thesis.) |
| `firmographics.hq_address` | 50 → **34** | **EXTRACTION** (44/50 had a location in `parsed_facts`). | **FIXED** — `derive_hq_address` lifts the HQ city from structured `hq`/`hq_city`/footprint/geography; +18 clean fills, 2 garbage stubs cleared, 0 false positives. Remaining 34 = non-US HQs / regional-only / thin-ingest → unavailability. |
| evidence drawer chips | ~every client | **EXTRACTION** (ingest artifacts: 4,925 column-cut `E-6:F1, E-7:` cells + 5,390 `[CEILING…]` excerpts + `(no excerpt)`/`NEGATIVE PROXY:` stubs, all carrying `linked_subcap_ids` so they reached the drawer). | **FIXED** — `clean_and_dedupe_evidence` at read time; swept all 43,771 (run,subcap) drawers, 0 quotable-row losses. |
| `firmographics.revenue_usd` | 59 | **UNAVAILABILITY (by design)** — banks/CUs report *assets* (`aum_usd` 98% covered) + net income, not "revenue"; `derive_financials` already keeps them honest-null (`REVENUE_SUBVERTICALS` gate). Forcing net-income → revenue would be semantically wrong. | None (correct as-is). Revenue-basis LOBs (IB/RIA/AM…) already extract it. |
| `firmographics.headcount` | 9 | **UNAVAILABILITY** — the 9 nulls carry no headcount signal in `parsed_facts` or narrative. | Enrichment candidate (Clay/Explorium). |
| `firmographics.aum_usd` | 2 | UNAVAILABILITY — 2 non-asset-basis entities. | Enrichment candidate. |
| `recommendations` / `issue_register` / `timeline_events` / `evidence_index` / `firmographics.*` | 1 each | **UNAVAILABILITY** — all are the single client `atb-a8f3`, a thin ingest (5 empty surfaces). | Re-ingest / enrichment candidate; not an extraction bug. |

Everything else (insight_cards, focus_areas, platform_scores, subcap_scores,
subcap_narratives, document_sections, tech_stack_entries, top_findings,
why_now_signals, leadership, sentiment, financial narrative) is ≥ 99% covered.

## Extraction vs unavailability — the rule applied

- **Extraction/wiring** = the fact exists in the client's own corpus (a parsed
  fact, a section body, an evidence row) but a script fails to surface it. These
  are fixed in code and re-verified against the live corpus.
- **Unavailability** = the client's corpus genuinely carries no signal (revenue
  for a CU, headcount for 9 clients, the thin `atb-a8f3` package). These are
  left honest-null and queued for enrichment; fabricating them would violate the
  "clear, traceable quotation" contract.

## Landed this pass

1. `entity_healing.derive_hq_address` + `hq_is_plausible` and the
   `derive_financials` backfill (structured-only; free-prose mining rejected
   after it bound Transamerica's HQ to VFP). 20 client-level firmographics
   improvements.
2. `evidence_hygiene.clean_and_dedupe_evidence` + the heatmap drawer wiring.
   Cleans thousands of chips corpus-wide; 0 drawer regressions.

## Queued (follow-up)

- SCQA→state wiring + thesis threading into persisted `top_findings`.
- `ai_enrichments` is 0 rows — the Gemini evidence-acquisition loop that would
  fill the unavailability cases (headcount, thin `atb-a8f3`) is not yet firing
  on the corpus.
- Apply the same excerpt hygiene to the regulatory-standing miner
  (`context.py`) and platform starter-fact miner (`platforms.py`) — they mine
  excerpts internally (not rendered raw), so lower priority.
