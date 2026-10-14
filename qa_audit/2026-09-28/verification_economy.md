# VERIFICATION ECONOMY — Axis D — 28-09-2026 · dma-insights 1.20.0

| id | measure | result | pass |
|---|---|---|---|
| D-01 | search/fetch calls by synthesis and verification agents | no run transcripts on disk; allow-lists permit it (D-02); server evidence rows are all `discovered_by: package` (368/368), i.e. none minted at synthesis for this run | UNKNOWN (allow-list says possible) |
| D-02 | synthesis/verifier allow-lists exclude search/fetch | 31 of 74 agents carry WebSearch+WebFetch: finding-challenger, adversarial-verifier, deployed-app-auditor, 3 checkers, enrichment-ledger-auditor, 24 per-surface producers, 6 page producers. research-challenger, scoring-*, report-* correctly carry none | FAIL |
| D-03 | VERIFY_REQUEST path end to end | equivalent exists and is code: lane emits `search_requests` (query + falsifier + facet) → PostToolUse `harvest_on_return.py` → `engine.relay harvest` (queued once per id in 07_qa/search_relay.jsonl) → `engine.relay batch` (dedup by normalised query, grouped by capability, connector proposed, prompt per group under briefs/relay_r<N>/) → top session spawns enrichment-web/connector-specialist → `engine.cli search/evidence` + `engine.relay record` → `engine.relay reconcile` closes from the Search_Log → `scripts/source_yield.py` ledger. Traced in code (relay.py:210-949, hooks/harvest_on_return.py:169-315, routing.md:95-130); not exercised live | PASS (traced) |
| D-04 | excerpt sufficiency, 30 cells | 20/30 verifiable = 67%; claims 67: entailed 35, partial 20, not supported 12 (18%). Median stored excerpt 151 chars (min 50) — search-snippet length. Unsupported claims include a named CEO attribution, a committee structure, and an after-state ("hours to minutes") | FAIL (<90%) — the fix belongs in research capture |
| D-05 | duplicate queries in one run | `engine.cli search` accepted the same query twice (Search_Log rows 1-2 identical); relay dedups only relay requests | FAIL (mechanism absent; rate not measurable) |
| D-06 | URL re-fetch | `07_qa/fetch_cache/<sha>.json` caches extracted pages per run (engine.cli fetch); rate not measurable | UNKNOWN |
| D-07 | verifier independence | `brief.challenge_batch` → `_abridge` hands the challenger synthesis + registered evidence, not the lane's reasoning; research-challenger reads "nothing but its brief packet" | PASS |
| D-08 | self-grading | research-challenger refuses a cell it authored (scope.py _CHALLENGERS); scoring-critic refuses a pillar's own scorer; BUT page-consolidator "synthesizes the storyline and then challenges it once more" and heatmap producers grade their own thin cells | PARTIAL |
| D-09 | evidence by reference | packets carry E-ids and `leads_in[]` rows; a `correlate` prompt is capped at 2,000 chars | PASS |
| D-10 | snippet-only conclusions | register refuses an excerpt the run never fetched (excerpt_unverified) — C-8a; live rows: 0 URL-as-excerpt, 0 <50 chars | PASS |
| D-11 | escalation criteria | present (declared absence with ladder; search_requests to relay; deferred questions) but stated differently in RESEARCH-PROTOCOL.md, SKILL.md and brief.py (see L-11) | PARTIAL |

## Evidence Gap Dossier (D-12..D-20)
The engine's declared absence (`engine.cli absence --subcap --ladder --proxy-log --hunted --enrichment-unavailable`) is the dossier's nearest artefact. Field coverage against the brief's dossier:

| dossier field | engine equivalent | present |
|---|---|---|
| subcap_id, descriptor, sub_vertical, depth_tier | subcap + catalogue names | yes |
| facets_status per facet | floors gate counts volleys per cell (works/fails/value/contradicts/corroborates), not per-facet ANSWERED/THIN/ABSENT | partial |
| searches_run (tool, query, date, count, log row) | Search_Log rows keyed by subcap+facet | yes (reconciles by construction: the log IS the record — D-13 100%) |
| sources_reviewed with rejection reason | fetch_cache + `--hunted` free text | partial |
| evidence_held | Evidence_Detail rows for the subcap | yes |
| inferable (labelled INFERENCE + validation question) | Claim_Label INFERENCE on synthesis; no validation question field | partial |
| not_determinable + reason | `--ladder` prose; `--enrichment-unavailable` flag | partial |
| proxy_rungs_tried / proxy_candidates | `--proxy-log`; catalogue `proxy_class_if_absent` | partial |
| internal_only_flag → discovery question | deferred questions ride as discovery (research lanes) | yes |
| est_cost | none | no |
| coordinator triage disposition (4 kinds) | `engine.brief gaps` lists open/undeclared/unserviced/stalled; no per-gap disposition record | no (D-14 FAIL) |
| proxy brief from template | relay batch prompts are template-generated and self-contained (queries, cells, connector, commands) | yes (D-15 PASS for relay batches) |
| prior-query exclusion list in the brief | relay batch dedups by normalised query; exclusion list not stated to the specialist | partial (D-16 not enforced) |
| one proxy round per subcap | `--stall-rounds 2`, `--enrichment-heals 1` | yes (D-17) |
| proxy hits labelled INFERENCE | ledger requires Claim_Label; no rule forcing INFERENCE on proxy rows; `quality.proxy_only` flags FACT on proxy | partial (D-18) |
| batching per proxy class | relay batches per capability+connector, not per subcap (ratio ≈ requests per batch, not measurable here) | yes (D-20) |

Verdict: the research tier has a real, code-enforced relay for new retrieval and a declared-absence record with a ladder; what is missing is the coordinator's written disposition per gap, the exclusion list handed to proxy searchers, and a validation question on every inference. Regression seed 14 (proxy re-running failed queries) is not prevented at the write (F-D05-033).
