---
name: dma-research
description: >
  Conducts subcapability-level public evidence research for Digital Maturity Assessments
  of financial services institutions. Reads diagnostic questions from Pillar XLSX toolkits,
  generates targeted search queries for each of 851 subcapabilities, executes web searches,
  maps evidence to specific subcap rows, and populates the scoring workbook with evidence
  (leaving score columns empty for dma-assessment). NO scoring, NO maturity levels — ceiling
  estimates with uncertainty bands ONLY. ALWAYS use when the user mentions: DMA research,
  evidence collection, pre-assessment research, tech stack discovery, entity profiling,
  subvertical classification, or any request to gather evidence before DMA scoring.
  Also covers what the retired dma-p1, dma-orchestrator and dma-core skills did: P1 or
  Pillar 1 research, research handoff, CCG/RSG inspection, SIB assembly, ESG research
  (P1C5 lineage), public-only, internal-only or hybrid DMA research engagements.
---

# DMA Research Skill v2.5

This skill produces the **evidence foundation** for a Digital Maturity Assessment. It does
NOT score — it researches. Output: a partially-filled scoring workbook with evidence columns
populated and scoring columns empty for `dma-assessment`.

Version history: `references/CHANGELOG.md`.

## Reading manifest — by phase

The engine (`engine.cli`, `engine.brief`, `engine.pipeline`) is the run's authority; the
prose below is what a person or a lane reads to work it. By phase:

| Phase | Read | Why |
|---|---|---|
| Session start | this file's ABSOLUTE RULES, `references/context_window.md`, `references/RESEARCH-PROTOCOL.md` | the rules and the protocol |
| PRELIM | `references/subvertical_profiles.md`, `references/tech_discovery.md` | the binding and the estate |
| A category lane | `engine.brief dispatch` (the card), `references/core_engine.md`, `references/deep_search_protocol.md`, `references/evidence_methodology.md` | the loop, the search ladder, the tiers |
| Declaring an absence | `references/org_capability_proxies.md`, `references/uncertainty_framework.md` | the ladder and the ceiling estimate |
| A batch boundary | `references/batch_execution_protocol.md` § the batch you are in | its checks |
| Handoff | `references/deliverables_spec.md`, `references/research_workbook_spec.md` | what ships |

## ⛔ ABSOLUTE RULES

| # | Rule | Prevents |
|---|------|----------|
| 1 | **NO SCORING** — Ceiling estimates with uncertainty bands ONLY. Never assign M1-M5. | Premature scoring |
| 2 | **EVERY claim labeled** — FACT / INFERENCE / HYPOTHESIS / CEILING_ESTIMATE. | Unlabeled assertions |
| 3 | **EVERY claim cited** — Evidence ID `[E-xxx]` + KB Source ID `[KB-XX-xxx]`. | Ungrounded prose |
| 4 | **Compact output** — One line per finding. No narrating, no previewing. | Token waste |
| 5 | **Presence ≠ Utilization** — Tech findings are ceiling estimates. Flag utilization uncertainty. | Over-estimation |
| 6 | **`web_search` at SUBCAPABILITY level** — 3-5 queries per subcap via `references/deep_search_protocol.md`. Execute Tiers 1-6. If signals remain unknown or <3 evidence items after Tiers 1-6, proxy searches (Tiers 7-10) are MANDATORY — do not skip. This is the PRIMARY research mechanism — no shortcuts. | Thin evidence, shallow single-search-per-category |
| 6b | **Dual-source: `web_search` FIRST, then Moody's connector** — web_search is PRIMARY (≥70% of queries). Moody's SUPPLEMENTS with structured credit/financial data. web_search MUST precede Moody's in every batch. Moody's does NOT replace subcap-level web searches. | Single-source dependency |
| 7 | **Batch execution** — 6 batches. Stop after each. Wait for "continue". Checkpoint after each batch. | Context overflow |
| 8 | **Fill the workbook** — Columns A-I, K, L, M, U, V. Leave J, N-T EMPTY. Every row: specific URL in L, ERS in M, excerpt ≥50 chars in U. | Evidence trapped in chat / truncated evidence |
| 9 | **Read diagnostic Qs FIRST** — Column H drives the search. | Generic searches |
| 10 | **Calculate ERS** — 0.35×Tier + 0.25×Recency + 0.20×Specificity + 0.20×Corroboration. | Undifferentiated evidence |
| 11 | **Extract at FACT level** — `[E-xxx:Fy]` notation. One `web_fetch` → 20+ subcap facts. | Single-fact extraction |
| 12 | **5-Layer Analysis** (HYBRID/INTERNAL) — Explicit → Implicit → Absence → Contradiction → Strategic. | Surface-level extraction |
| 13 | **Use project knowledge base templates** — Client Profile report MUST use the `DMA_Client_Profile_Research_Template.docx` from the project knowledge base. Retrieve it, fill it. NO deviation, NO ad hoc structures. | Inconsistent report formats |
| 14 | **Peer set locked in Batch 1** — Select 3-5 peers during entity profiling. Peers are IMMUTABLE after Batch 1. Saved to peer_set.json and carried into handoff. | Assessment delays from deferred peer selection |
| 15 | **Canonical evidence schema** — Every evidence item uses identical field names across all batches. See Evidence Item Schema below. | Schema inconsistency across batches (QA-010) |
| 16 | **70% evidence-coverage floor PER CATEGORY** — at least 70% of a category's subcaps must carry ≥1 resolvable evidence item. The floors gate BLOCKS on `coverage_below_floor` (AUD-0115). Work the long tail with the DQ facets as discovery probes + the negative ladder; declare honest absences only AFTER a deep search. | Shallow categories where most subcaps are marked no-evidence without deep/proxy searches |
| 17 | **Synthesise + INDEPENDENTLY challenge every evidenced subcap BEFORE scoring** — a subcap with evidence is not done until it carries a synthesis AND a challenge recorded by a *different agent run* (distinct session; a relabel of the same run is refused). The research → **synthesis → independent challenge** → handoff → scoring order is enforced: `handoff.build` REFUSES any category that did not clear the floors gate with `--require-synthesis` (AUD-0116), so a coverage-only pass can never reach the scoring stage. The score must reflect a challenged claim, never raw evidence. | Volleyed subcaps scored on unchallenged evidence; challenge treated as an optional afterthought |

---

## Context Window Management (CRITICAL)

Read `references/context_window.md` — the context-window rules for a research session. Read at session start and after a compaction.

## Output Directory Taxonomy (MANDATORY)

```
/home/claude/dma_output/{RUN_ID}/
├── run_manifest.json
├── 00_entity_profile/         # Batch 1
│   ├── entity_profile.json
│   ├── subvertical_classification.json
│   ├── financial_baseline.json
│   └── peer_set.json          # LOCKED peer set (3-5 peers, immutable after Batch 1)
├── 01_evidence/               # Batches 2-3
│   ├── evidence_index.json
│   ├── evidence_index.csv
│   ├── search_log.json
│   └── rich_documents/
├── 02_workbook/               # Batch 4
│   ├── DMA_Research_Workbook_{INST}_{DATE}.xlsx
│   └── workbook_validation.json
├── 03_appendices/             # Batches 4+6 (A1-A9 CSVs)
├── 04_visualizations/         # Batch 6 (VIZ-01 to VIZ-05 PNGs)
├── 05_report/                 # Batch 5
├── 06_handoff/                # Batch 6 (research_handoff.json)
├── 07_qa/                     # QA artifacts
└── checkpoints/               # Batch checkpoints
```

**Run ID:** `DMA-RES-{INST_CODE}-{YYYYMMDD}-{SEQ}` (e.g., DMA-RES-GESA-20260304-0001)

**At Batch 1 start:** Generate RUN_ID → create full tree → create `run_manifest.json` →
all subsequent file writes use these paths — no exceptions.

**Provenance:** Every file references `run_id`. CSVs: header comment `# run_id: {RUN_ID}`.
Workbook: `Run_Metadata` sheet. VIZ: footer text. Hard gate: mismatched `run_id` = build fails.

**Clean build:** Never reuse artifacts from different RUN_ID. Final package = manifest list only.

---

## Evidence Tier System

| Tier | Type | Weight | Max Ceiling | Examples |
|------|------|--------|-------------|---------|
| T1 | Regulatory/Audited + Verified Tech Scans | 1.0 | L5 | Call reports, enforcement orders, **Hubbl scans**, BuiltWith, Wappalyzer |
| T2 | Official Disclosures + Structured Internal | 0.85 | L5 | Annual reports, 10-K, investor decks, **discovery notes** with specific tech/metrics |
| T3 | Third-Party Analysis | 0.7 | L4 | J.D. Power, Forrester, app ratings |
| T4 | Internal (Unvalidated Narrative) | 0.55 | L2.5 | Unstructured memos, anecdotal claims |
| T5 | Marketing/Claims | 0.3 | L2 | Website claims, brochures — REQUIRES corroboration |

### ⚠️ Hubbl & Discovery Notes — CRITICAL Tier Rules

**Hubbl scans = T1.** Machine-generated, timestamped, objective deployment data.
**Structured discovery notes = T2.** Formal engagement outputs with specific tech/metrics.
**NEVER classify Hubbl as T4.** Most common misclassification — suppresses scores via T4 ceilings.

```
Classification decision tree:
  Machine-generated scan (Hubbl, BuiltWith)? → T1
  Structured engagement notes with metrics?  → T2
  Formal internal doc (policy, board deck)?  → T3 (use with corroboration)
  Informal memo, email, anecdotal claim?     → T4
```

**Recency tags:** CURRENT (<18mo), RECENT (18-36mo), LEGACY (>36mo), UNVERIFIED (undated)

---

## Canonical Evidence Item Schema (MANDATORY — all batches)

Every evidence item across ALL batches MUST use this exact schema. No field name variations.
This prevents the schema inconsistencies documented in QA-010.

```json
{
  "evidence_id": "E-xxx",
  "source_name": "string",
  "url": "string (specific URL — NEVER 'multiple searches' or blank)",
  "tier": "T1|T2|T3|T4|T5",
  "ers_score": 0.0,
  "recency_tag": "CURRENT|RECENT|LEGACY|UNVERIFIED",
  "subcap_mappings": ["P1C1.1.1", "P1C1.1.2"],
  "facts": [{"fact_id": "F1", "text": "string", "claim_label": "FACT|INFERENCE|HYPOTHESIS|CEILING_ESTIMATE"}],
  "publish_date": "YYYY-MM",
  "signal_direction": "POSITIVE|NEGATIVE|NEUTRAL|CONTRADICTORY"
}
```

**Hard enforcement:** `engine.cli evidence` refuses an item not conforming to this
schema (an excerpt outside 50–500 verbatim characters, an off-vocabulary tier, a cell the run
did not select), and `engine.cli validate` fails the workbook on any row that got in around it.
Field aliases (e.g., `id` instead of `evidence_id`, `finding` instead of `facts`) are NOT
accepted. (`scripts/validate_workbook.py` is retired — it validated the 22-column layout the
engine replaced, and it refuses, naming `engine.cli validate`.)

---

## Dual-Source Research Protocol (web_search + Moody's Connector)

**web_search is the PRIMARY evidence tool.** Moody's connectors SUPPLEMENT but never replace
targeted web searches. This is enforced per-batch.

### Invocation Order (MANDATORY per batch)

```
STEP 1: Targeted web searches (≥10 per batch, ≥70% of total queries)
  → web_search for institution-specific evidence
  → web_fetch on discovered pages (vendor case studies, press releases, tech blogs)
  → Fetch institution's primary website for first-party source data

STEP 2: Moody's connector calls (structured credit/financial data)
  → Moody's scorecard data (financial ratios, credit metrics)
  → Moody's sector outlook (industry context)
  → Moody's document search (analyst reports, research notes)

STEP 3: Regulatory database deep dive
  → Regulator-specific searches (FDIC, NCUA, OCC, FCA, state regulators)
  → Enforcement action searches
  → Call report / financial filing retrieval

STEP 4: Proxy signal searches (Tiers 7-10)
  → Industry associations mentioning entity
  → Vendor case studies, partner press releases
  → Job postings (LinkedIn, Indeed) for capability indicators
  → Glassdoor reviews, community forums
```

**Research batch checks (verified after each batch).** These are checks on
THIS SKILL's own search behaviour. They are not connector gates, they never
appear in a payload, and `explain_gate` does not know them — which is why they
carry the `RS-` prefix and not `SG-`. They were `SG-01…SG-06` until
2026-08-23, and the collision cost a production session a contradiction it
could not settle: one challenger called `explain_gate` on a payload's `SG-01`,
got `unknown_gate`, and reported the id fabricated (correctly — CG-22 refuses
exactly that); a second challenger found these definitions and argued the same
ids were legitimate disclosures to preserve. Both read a real document. The
`SG-` namespace belongs to `apps/mcp/dma_mcp/gates.py` alone.
- RS-01: web_search invoked BEFORE Moody's in this batch
- RS-02: ≥10 targeted web searches executed this batch
- RS-03: Entity primary website fetched for first-party data
- RS-04: Moody's data layered on top of (not replacing) web search results
- RS-05: Negative results documented (absence = evidence)
- RS-06: Financial data covers ≥3 years for trend analysis

**Search log (A2 CSV) must show web_search as dominant query type (≥70% of total).**

---

## Internal Evidence Integration Protocol (HYBRID/INTERNAL mode)

**MANDATORY for every capability when internal evidence exists.**

1. **LOAD internal evidence FIRST** — before web search. Read all uploaded client documents,
   discovery notes, Hubbl scans, and internal files at batch start.
2. **CLASSIFY using decision tree** — NEVER default internal evidence to T4:
   ```
   Machine-generated scan (Hubbl, BuiltWith, Wappalyzer)?  → T1
   Structured engagement notes with specific tech/metrics?  → T2
   Client-provided policy docs, board decks, roadmaps?      → T2
   Formal internal doc (general, no specific metrics)?       → T3
   Informal memo, email, anecdotal claim?                    → T4
   ```
3. **CROSS-REFERENCE** against public evidence — note agreements and contradictions
4. **WEIGHT CORRECTLY:** Internal T2 evidence OUTWEIGHS public T3-T5 evidence for the same subcap
5. **Flag in workbook Column U** when internal evidence contradicts public evidence
6. **HARD GATE:** If HYBRID/INTERNAL mode and >50% of subcaps have zero internal evidence
   cited → STOP and verify internal docs were actually loaded and analyzed

---

## Claim Labels (MANDATORY — every finding)

| Label | Citation Rule | Format |
|-------|--------------|--------|
| FACT | E-ID + KB-ID | `[E-003] NCUA Q4 2024 (T1, CURRENT): Assets $4.2B. [KB-US-001] (FACT)` |
| INFERENCE | 2+ E-IDs + logic | `[E-012, E-015] AppExchange listing + job posting for "Salesforce Admin": Likely uses FSC. (INFERENCE)` |
| HYPOTHESIS | E-IDs + proxy attempts | `[E-030] LinkedIn shows no digital officer titles in leadership. Proxy: board bios searched, no tech background found [E-031]. Org chart suggests digital reports to CIO. (HYPOTHESIS — validate via internal org chart)` |
| CEILING_ESTIMATE | E-IDs + uncertainty | `P4C3 ceiling: L3.5 (±0.5). Tech presence confirmed [E-018] but utilization unknown. (CEILING_ESTIMATE)` |

**FORBIDDEN HYPOTHESIS PATTERNS (these indicate skipped proxy searches):**
- "No CDO found" — Did you search board bios, LinkedIn, press releases, job postings?
- "No governance strategy" — Did you search annual reports, investor decks, proxy statements?
- "No digital strategy" — Did you search strategic plan filings, CDO/CTO appointments, conference talks?
If your hypothesis is "not found", you MUST list the proxy searches attempted and their results.

---

## Core Engine: Diagnostic Q → Search → Evidence → Subcap Row

Read `references/core_engine.md` — diagnostic question → search → evidence → subcap row, in full. Read before the first batch.

## Diagnostic Question Patterns

| Pattern | Evidence Needed | Query Strategy |
|---------|----------------|----------------|
| "Does [entity] have..." | Existence proof | Search for the thing |
| "Is [thing] documented..." | T2+ documentation | Annual reports, filings |
| "Is there a defined process..." | Process maturity T2/T3 | Process descriptions, job posts |
| "Are metrics tracked..." | Measurement T1/T2 | Reported metrics, KPIs |
| "Is [thing] automated..." | Technology T3/T4 | Platform, vendor, case study |
| "Is there board oversight..." | Governance T1/T2 | Proxy statements, charters |
| "Are results used to improve..." | Optimization T2/T3 | Iteration evidence, A/B testing, CI |
| "Is [capability] integrated across..." | Enterprise adoption T2/T3 | Cross-dept mentions, unified platform |

### Evidence Sufficiency by Question Type

| Question Type | Minimum Evidence | Below Minimum Action |
|---------------|-----------------|---------------------|
| Existence | 1 confirming OR 3 non-findings + proxy attempts | NO_EVIDENCE only after proxy searches (Tiers 7-10) also fail |
| Process maturity | 2 sources | EVIDENCE_THIN, flag for internal validation |
| Measurement | 1 T1/T2 with actual values | T3+ only → label INFERRED, note no hard data |
| Technology | 1 tech evidence + 1 utilization | Presence alone → CEILING_ESTIMATE |
| Governance | 1 T1/T2 governance evidence + proxy search | Proxy/board composition only → HYPOTHESIS with proxy log |
| Optimization | 2 improvement cycle references | Single mention → HYPOTHESIS, low confidence |
| Enterprise adoption | 2+ cross-department references | Single dept → cap at L3.0 |

**MANDATORY PROXY RULE for Governance & Strategy subcaps (P1C1-P1C5):**
These subcaps are the most likely to produce false "not found" conclusions because
governance evidence is often indirect. For EVERY governance/strategy subcap:
1. Search board bios for tech/digital background (Tier 7)
2. Search for C-suite digital hires — CDO, CTO, CIO appointments (Tier 7)
3. Search LinkedIn for leadership with digital titles (Tier 7)
4. Search conference presentations by entity leadership (Tier 8)
5. Search for strategic plan filings or investor deck mentions (Tier 2)
These five are the `proxy` rung of the absence ladder for P1: log each as an
`engine.cli search --subcap <cell> --facet <f> --tool <connector>` and name
them in `--ladder` / `--proxy-log` when you declare. "No CDO found" without
them is a research failure, not a finding — and `engine.cli absence` refuses
it, because the Search_Log will not show the searches.

---

## Batch Execution Protocol

Read `references/batch_execution_protocol.md` — the six batches, B1–B6, and their checks. Read the batch you are in.

## Workbook Columns (Research Responsibility)

| Cols | Research Fills | Cols | Assessment Fills |
|------|---------------|------|-----------------|
| A-I | Taxonomy + diagnostic Q + weights | J | Score |
| K,L,M | Evidence IDs, URLs, Tier | N-T | Confidence, caps, rationale, proof |
| U,V | Evidence excerpt + source doc | — | May enrich U,V |

---

## Reference Files

| File | Read When | Key Contents |
|------|-----------|-------------|
| `references/evidence_methodology.md` | Batch 1 start | ERS formula, fact-level extraction, 5-Layer analysis, red flags |
| `references/deep_search_protocol.md` | Batch 2 start | 10-tier query system, proxy signals, smart batching |
| `references/research_workbook_spec.md` | Batch 4 | Column specs, Column U protocol, sheet structure |
| `references/source_catalogue.md` | Batch 1 | KB Source IDs, URLs, query templates |
| `references/subvertical_profiles.md` | Batch 1 | Decision tree, T1 sources, financial metrics |
| `references/tech_discovery.md` | Batch 3 | Tech categories, utilization, URF-01-06, vendor tenure |
| `references/org_capability_proxies.md` | Batch 3 | LinkedIn density, job seniority, Glassdoor |
| `references/uncertainty_framework.md` | Batch 4 | Base uncertainty, red flag modifiers, ±0.8 cap |
| `references/safeguard_gates.md` | Batch 4 | 16 safeguard gates |
| `references/deliverables_spec.md` | Batch 5 | D0-D6 structure, appendix specs |
| `references/document_formatting.md` | Batch 5 | Zennify branding, DM Sans, python-docx |
| `references/context_window.md` | Session start | Context-window rules (moved from this file, F-B04-027) |
| `references/core_engine.md` | Before the first batch | Diagnostic Q → search → evidence → subcap row |
| `references/batch_execution_protocol.md` | Each batch boundary | The six batches and their checks |
| `references/CHANGELOG.md` | Never in a run | Version history |
| `references/diagnostic_questions.md` | Fallback | ONE question per category, not per subcapability — 71 in all. It is NOT a substitute for the toolkits; a run that falls back to it is running on 8% of the coverage the name implies, and must say so. |

## Scripts

| Script | Batch | Purpose |
|--------|-------|---------|
| `scripts/extract_diagnostic_questions.py` | 2 | Parse Pillar XLSX → subcap IDs, names, diagnostic Qs |
| `scripts/generate_query_plan.py` | — | **RETIRED** (refuses): the work card from `engine.cli orient` is the query plan; a JSON plan beside the run had no reader (F-J02-011) |
| `scripts/calculate_ers.py` | All | Calculate ERS scores, optionally write back |
| `scripts/merge_evidence.py` | 4 | Deduplicate, link corroborations, coverage stats |
| `scripts/populate_workbook.py` | — | **RETIRED** (refuses): it built a second, 10-sheet workbook beside the run. The run's one workbook is created by `engine.cli start` and written only through `engine.cli evidence / search / synthesise / absence` |
| `scripts/validate_coverage.py` | 4 | Coverage thresholds, tier distribution, hard gates |
| `scripts/validate_workbook.py` | — | **RETIRED** (refuses): it validated the 22-column layout the engine replaced. Use `engine.cli validate` |

---

## Domain-Specific Rules

**P4 Stricter Thresholds:** HIGH=T1/T2+corroboration+UTILIZATION. MEDIUM=T3+stack confirmed.
LOW=T4-T5 or any red flag. Inferred tech→cap L3.0. Tenure >10yr basic→internal validation.

**Minimum Coverage (HARD GATE — blocks Batch 4):**
1+ T1 regulatory anchor | 2+ T1/T2 financials | 2+ operating model sources |
5-year trend data | Issue search all regulators | Sentiment attempted |
Tech stack all categories | Org proxies | Diagnostic Qs loaded | ≥80% subcaps with evidence

**Tech Utilization:** See `references/tech_discovery.md` (evidence levels 1-4, utilization
levels, URF-01-06 red flags, vendor tenure, Zennify-priority, recency protocol).

**Uncertainty:** See `references/uncertainty_framework.md` (base ±0.3-0.5, red flags +0.1-0.2,
evidence gaps +0.1-0.2, formula capped ±0.8).

**Org Proxies:** See `references/org_capability_proxies.md` (LinkedIn density, job seniority,
Glassdoor culture, impact on P1C4/P4 ceilings).

---

## PARAMETER LOCK Block (Final Output)

```
════════════════════════════════════════════════════════
ASSESSMENT ID: [RUN_ID]
EVIDENCE MODE: [PUBLIC/INTERNAL/HYBRID]
PARAMETER LOCK: [Subvertical] toolkit bound
SUBCAPS: [N]/[SELECTED] ([X]%) | COVERAGE: [N]≥3, [M] thin, [P] none
CEILINGS: [X] caps, avg ±[Y] | TECH: [N] total, [M] Zennify-priority
CLAIMS: [F/I/H/CE] | GATES: [N] PASS, [M] FAIL
PEERS (LOCKED): [Peer1 (SizeTier), Peer2 (SizeTier), ...]
WORKBOOK: Evidence populated, scores empty
REPORT: Client Profile generated from project KB template
STOP: NO SCORING. Run dma-assessment.
════════════════════════════════════════════════════════
```

**research_handoff.json must include:**
- `assessment_id`: RUN_ID (top-level, IMMUTABLE)
- `evidence_mode`: PUBLIC/INTERNAL/HYBRID (top-level, IMMUTABLE)
- `locked_peer_set[]`: Array of {peer_name, size_tier, key_metric, geography, overlap_pct, selection_rationale}
- All other existing handoff fields
