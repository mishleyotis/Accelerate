---
name: dma-assessment
description: >
  Conducts Digital Maturity Assessments (DMA) for financial services institutions using
  argument-based reasoning. Covers 8 sub-verticals across 4 pillars, 17 categories, 144
  capabilities, ~836 subcapabilities scored M1-M5. Works best when preceded by dma-research
  skill (research_handoff.json with claim-labeled evidence, tech utilization, uncertainty
  bands). ALWAYS use this skill when the user mentions: DMA, digital maturity, scoring
  subcapabilities, maturity rubric, pillar scoring, scoring workbook, cap enforcement, peer
  benchmarking, Zennify DMA, pillar/capability IDs like P1C1, P2C3, maturity levels M1-M5,
  or uploaded internal documents in assessment context. Also trigger when asked to assess,
  score, or benchmark any financial services institution's digital capabilities.
---

# DMA Assessment Skill v5.5

**v5.5 Changes:** 11-column workbook structure (matching CFC workbook: SubCap_ID, SubCap_Name,
Category, Score, Confidence, Evidence_IDs, Source_URLs, Evidence_Ceiling, Caps_Applied,
Rationale, Proxy_Searched). Subcap-level scoring reinforced with row count checks. Explicit
calculation chain rollup instructions. Taxonomy vs workbook row count clarified. QA checks
aligned with 11-column format. URL enforcement. Cross-skill consistency (3-5 queries/subcap).

## ⛔ NON-NEGOTIABLE RULES

| # | Rule | Failure It Prevents |
|---|------|---------------------|
| 1 | **Score at SUBCAPABILITY level** — one row per subcap ID (e.g., P1C1.1.1, P1C1.1.2). Each P#_Subcap_Scoring sheet must have ≥50 rows. P1≈186, P2≈232, P3≈118, P4≈172. If your sheet has <50 rows, you are scoring at CATEGORY level — STOP and redo. | Category-level scoring (17-28 rows instead of 700+) |
| 2 | **Differentiate scores** — ≥2 unique scores per capability. Each subcap's diagnostic question asks something DIFFERENT — scores should reflect that. | Identical scores (2.5, 2.5, 2.5...) across all subcaps |
| 3 | **Map evidence to INDIVIDUAL subcaps** — cite E-xxx:Fy fact-level refs. Different subcaps within the same capability must cite DIFFERENT evidence facts. | Same evidence cited for every subcap |
| 4 | **≥150-char rationales per subcap** — institution-specific, cite E-IDs, reference M-level descriptor, explain gap to next level. | Generic "demonstrates capability" text |
| 5 | **Use 11-column workbook structure** — SubCap_ID, SubCap_Name, Category, Score, Confidence, Evidence_IDs, Source_URLs, Evidence_Ceiling, Caps_Applied, Rationale, Proxy_Searched. See "Workbook Column Structure" below. | Wrong column layout, confusion with 22-column spec |
| 6 | **Cite evidence inline in report** — (E-xxx, Source, Tier, Date) | Generic consulting prose |
| 7 | **Run `scripts/validate_scoring_quality.py` after Phase 4** | Undetected quality failures |
| 8 | **Web searches at SUBCAPABILITY level** — 3-5 per subcap via `web_search`. Each subcap's diagnostic question drives DIFFERENT queries. | Thin single-source assessments |

**If output matches any "Failure" pattern, STOP and redo that step.**

---

## Workbook Column Structure (CANONICAL — 11 columns per P#_Subcap_Scoring sheet)

This is the ONLY acceptable column layout. It matches the proven CFC workbook format.
**Do NOT use the legacy 22-column (A-V) layout. Do NOT invent additional columns.**

| Col | Header | Description |
|-----|--------|-------------|
| A | SubCap_ID | Unique subcap identifier (e.g., P1C1.1.1, P2C3.2.4). One row per subcap. |
| B | SubCap_Name | Subcapability name from Pillar XLSX toolkit |
| C | Category | Parent category ID (e.g., P1C1, P2C3) |
| D | Score | Final maturity score (1.0-5.0, default 0.5 precision) |
| E | Confidence | HIGH / MEDIUM / LOW based on evidence coverage and tier diversity |
| F | Evidence_IDs | Comma-separated evidence IDs (E-001, E-015, INT-BOARD-003) or NO_EVIDENCE |
| G | Source_URLs | Hyperlinks to evidence sources (specific URLs, not "multiple searches") |
| H | Evidence_Ceiling | Maximum score supported by evidence tier (e.g., T5-only → 2.0) |
| I | Caps_Applied | Cap description if applied (e.g., "T5-only cap 2.0") or empty if none |
| J | Rationale | ≥150 chars. Must cite E-IDs, reference M-level descriptor, explain gap, institution-specific "so what" |
| K | Proxy_Searched | "Yes" or "No" — whether proxy searches (Tiers 7-10) were attempted |

**Expected row counts per sheet:**
- P1_Subcap_Scoring: ~186 rows (range 170-200)
- P2_Subcap_Scoring: ~232 rows (range 210-250)
- P3_Subcap_Scoring: ~118 rows (range 105-135)
- P4_Subcap_Scoring: ~172 rows (range 155-190)
- **TOTAL: ~708 subcap rows across all 4 pillar sheets**

**Additional sheets (same as CFC workbook):**
- Executive_Summary — Overall maturity snapshot
- Pillar_Summary — 4 pillar rows + Overall, with weights, scores, peer medians, gaps
- Category_Detail — 17 category rows with scores, weights, peer medians, priorities
- Evidence_Master — All evidence items with ID, Source, URL, Tier, Recency, Claim_Type, Finding
- Peer_Benchmarks — Peer scores per category
- Recommendations — Top recommendations with evidence linkage
- Run_Metadata — Assessment ID, evidence mode, parameters

**Self-check:** If any P#_Subcap_Scoring sheet has <50 rows → you scored at CATEGORY level.
STOP. Delete the sheet. Redo with one row per subcap ID.

---

## Context Window Management (CRITICAL)

| Phase | Max Tokens | Focus |
|-------|-----------|-------|
| 0 | ~2,000 | Setup, parameter lock |
| 1 | ~20,000 | Evidence collection |
| 2 | ~8,000 | Peer scoring — batch by peer |
| 3 | ~3,000 | Issue register |
| 4 | ~25,000 | Scoring — code-heavy |
| 4.5 | ~8,000 | Critic pass — table format |
| 5 | ~4,000 | Analysis — computed output |
| 6 | ~6,000 | Recommendations — structured |
| 7 | ~15,000 | Deliverables — code-heavy |
| 8 | ~4,000 | QA — script + computed verdict |

**Anti-Bloat Rules:**
1. Go straight to code/action — no "Let me now..." or "I'll proceed to..."
2. Phase gate acknowledgments: MAX 5 lines
3. Scoring rationales go in workbook, NOT in chat — chat gets summary stats only
4. Workbook/report generation: output code blocks only — no explanatory prose
5. Checkpoint BEFORE context limit — don't try to squeeze more in

**Scratchpad-First Scoring (CRITICAL for Phase 4):**
Do NOT score subcaps in chat prose. Instead:
1. Load evidence for ONE capability at a time (see Evidence Loading below)
2. Score all subcaps in that capability → write rows directly to a JSON scratchpad file
   on disk: `$DMA_ROOT/checkpoints/scoring_scratchpad.json`
3. Chat output: ONLY print capability summary (e.g., "P1C1: 8 subcaps scored, range 1.5-3.0, 3 caps applied")
4. After each PILLAR: save checkpoint, print pillar stats (5 lines max)
5. After ALL pillars: run a Python script to convert scratchpad JSON → XLSX workbook with
   ALL 11 sheets (P1-P4_Subcap_Scoring, Executive_Summary, Pillar_Summary, Category_Detail,
   Evidence_Master, Peer_Benchmarks, Recommendations, Run_Metadata)

**Why this matters:** If you try to score 700+ subcaps in chat, you WILL exhaust context.
The scratchpad pattern keeps context for the CURRENT capability only (~5-12 subcaps), while
all previous scores are safely on disk. The final workbook is built from the scratchpad
in one code block — guaranteeing all tabs exist and all data is included.

**If chat stalls or requires "continue":** You are printing too much in chat. Write to disk,
summarize in chat. The user should not need to press "continue" during normal scoring.

### Cross-Conversation Execution (SUPPORTED)

Each phase can run in a separate conversation. All state lives in checkpoint files — prior
conversation context is NOT required. On new conversation start:

1. Read this SKILL.md
2. Load the most recent checkpoint from `$DMA_ROOT/checkpoints/`
3. Confirm parameters and current phase with user
4. Proceed from the checkpoint — do NOT re-derive prior phases' output from conversation

This is the primary mechanism for managing long assessments without context overflow. When
approaching context limits mid-phase, save a checkpoint at the nearest category boundary
and instruct the user to continue in a new conversation.

---

## Core Analytical Principles

**1. Specificity:** Before writing ANY sentence, test: "Could this appear unchanged for a different institution?" If YES → rewrite with institution-specific data. FORBIDDEN: "The institution should improve its digital capabilities" and similar generic prose.

**2. Argument-Based Reasoning:** Every conclusion requires: CLAIM → EVIDENCE → REASONING → COUNTER-ARGUMENTS → REBUTTAL → QUALIFICATION. See `references/analytical_framework.md`.

**3. Evidence Triangulation:** No MEDIUM+ confidence conclusion rests on single-source evidence. Minimum 2 tier types for M3+. Hard cap: single tier-type only → max 2.5 (unless T1/T2). See `references/scoring_methodology.md` Step 3.

**4. Single Source of Truth:** The Scoring Workbook is canonical. All other artifacts derive FROM it. Numbers never diverge. Workbook wins.

---

## Taxonomy & Maturity Scale

```
Pillar (4) → Category (17) → Capability (144) → Subcapability (~836)
```

| Pillar | Name | Subcaps |
|--------|------|---------|
| P1 | Strategy, Governance & Culture | ~199 |
| P2 | Member/Customer Experience | ~288 |
| P3 | Operations, Risk & Compliance | ~162 |
| P4 | Data, Analytics & Technology | ~187 |

**Note:** Taxonomy counts (~836) are the theoretical maximum from the Pillar XLSX toolkits.
Actual workbook rows vary by sub-vertical (some subcaps are N/A). Typical observed ranges:
P1≈186, P2≈232, P3≈118, P4≈172 (~708 total). Both are valid — the workbook contains
all applicable subcaps for the specific institution's sub-vertical.

| Level | Name | Range | Meaning |
|-------|------|-------|---------|
| M1 | Foundational | 1.0–1.4 | Absent/ad-hoc |
| M2 | Developing | 1.5–2.4 | Basic, inconsistent |
| M3 | Established | 2.5–3.4 | Standardized, documented |
| M4 | Advanced | 3.5–4.4 | Optimized, data-driven |
| M5 | Transformational | 4.5–5.0 | Industry-leading |

Maturity descriptors: Pillar XLSX files → Maturity Descriptors sheet.

---

## Evidence Tier System

| Tier | Type | ERS Score | Max Alone |
|------|------|-----------|-----------|
| T1 | Regulatory/Audited + Verified Tech Scans | 5.0 | M5 |
| T2 | Official Disclosures + Structured Internal | 4.0 | M5 |
| T3 | Third-Party Analysis | 3.0 | M4 |
| T4 | Internal (Unvalidated Narrative) | 2.0 | M2.5 |
| T5 | Marketing/Claims | 1.0 | M2 |

**Hubbl scans = T1** (machine-verified). **Discovery notes = T2** (structured engagement).
**NEVER classify Hubbl as T4.** See dma-research SKILL.md for decision tree.

**ERS Formula:** `(0.35×Tier) + (0.25×Recency) + (0.20×Specificity) + (0.20×Corroboration)`.
Factor scores 1.0-5.0. See `references/evidence_ranking.md`.

**Inline Citations (MANDATORY in workbook AND report):**
- Workbook: `[Claim] (E-xxx:Fy, Source, Tier)`
- Report: `[Claim] (E-xxx, Source, Tier, Date)`
- Every claim → citation. No exceptions.

---

## Cap System

```
final_score = min(raw_score, evidence_ceiling, all_caps, all_adjustment_ceilings)
```

Adjustments computed as `adjustment_ceiling = min(raw, other_ceilings) − X`, logged with `ADJ_` prefix.

**Severity:** S3 (active enforcement <12mo)→1.5 | S2 (terminated <24mo)→3.0
**Evidence:** T5-only→2.0 | T4/T5-only→2.5 | Single source→3.0 | Single tier-type→2.5 (EXCEPTION: internal T1/T2 + public T3 = two tier types, ceiling removed) | >24mo→ADJ −0.3
**Internal Evidence Override:** Internal T1/T2 evidence removes the single-tier-type cap (2.5). A subcap supported by both internal T2 and public T3 has effective ceiling M5, not M2.5.
**Sentiment (P2):** Rating <3.0→2.0 | 3.0-3.5→2.5 | 3.5-4.0→3.5 | Complaints +20% YoY→ADJ −0.3

**Cross-Pillar (applied Pass 2 AFTER all pillars scored):**
P1C2<2.5→P3 cap 3.0 | P4C4<2.5→P4C1 cap 3.0 | P3C3<2.5→P2C2 cap 3.0 |
P4C1<2.5→P2C4 cap 3.0 | P4C3<2.5→P3C1 cap 3.0 | Breach <12mo→P4C4 cap 2.0

Authoritative: `references/scoring_methodology.md` Step 3, Step 7.

---

## Deterministic Score States (MANDATORY)

In the 11-column workbook, scoring flows through these states:

| State | Where | Description |
|-------|-------|-------------|
| `raw_score` | Internal (not in workbook) | From M-level matching (before caps) |
| `evidence_ceiling` | Column H | Maximum score supported by evidence tier |
| `caps_applied` | Column I | Description of any caps that reduced the score |
| `final_score` | **Column D (Score)** | min(raw, evidence_ceiling, severity_caps, cross_pillar) — **ONLY value in rollups** |

**Column D is the FINAL score** — it already incorporates all caps. There is no separate
raw_score column in the workbook. The raw-to-final pathway is documented in the Rationale
(Column J) and Caps_Applied (Column I).

**Rollup:** subcap final_score (Col D) → capability → category → pillar → overall (weighted avg)
**Reconciliation:** Recompute pillar from categories — must match ±0.01. Fix before proceeding.

### Canonical Export Layer (MANDATORY after Phase 4)

```
$DMA_ROOT/04_scoring/exports/
├── export_scoring_detail.csv      # All subcaps: ID, Score, Evidence_Ceiling, Caps_Applied, Confidence
├── export_category_summary.csv    # 17 rollups with weighted scores
├── export_pillar_summary.csv      # 4 rollups with weighted scores
├── export_evidence_inventory.csv  # All evidence with ERS
├── export_issue_register.csv      # Issues with dates
└── export_coverage_stats.csv      # Subcap counts, coverage %
```

**Phase 7 report reads ONLY from exports. No ad hoc data.**

### Sub-Vertical Pillar Weights

| Sub-Vertical | P1 | P2 | P3 | P4 |
|-------------|----|----|----|----|
| Credit Unions | 25 | 30 | 20 | 25 |
| Regional Banks | 25 | 30 | 20 | 25 |
| Commercial Lending | 20 | 20 | 35 | 25 |
| CIB | 20 | 20 | 35 | 25 |
| Insurance Carriers | 20 | 20 | 30 | 30 |
| Insurance Brokerages | 20 | 35 | 20 | 25 |
| Wealth / RIAs | 25 | 30 | 20 | 25 |
| Asset Management | 20 | 30 | 25 | 25 |

---

## Persistent QA Memory System

Maintains a living error log across assessments. See `references/qa_error_log.md` (master template).

**Phase 0:** Copy to `$DMA_ROOT/checkpoints/qa_error_log.md` (writable). If already exists (session resume), load without overwriting.

**Phase Gate Protocol (EVERY phase, no exceptions):**
1. LOAD `$DMA_ROOT/checkpoints/qa_error_log.md`
2. FILTER to current phase tag `[PHASE:N]`
3. ACKNOWLEDGE: `⚠️ PHASE GATE [N] — [X] prevention rules: [list]. Proceeding.`
4. APPLY each as hard constraint

**Post-Phase QA:** Log issues → compare to error log → create/increment entries → write to writable copy → confirm in chat.

**End-of-Assessment:** Output patch block in chat for human to append to master template:
```
=== DMA ERROR LOG PATCH — [Institution] [Date] ===
[New/updated ERR entries]
=== END PATCH ===
```

---

## Inline Prevention Rules (consolidated)

These fire at their tagged phase. All are hard constraints.

| ID | Phase | Severity | Rule |
|----|-------|----------|------|
| ERR-001 | 4 | CRITICAL | Score at SUBCAP level. <50 rows per pillar = wrong granularity. |
| ERR-002 | 4 | CRITICAL | Rationale ≥150 chars, cite E-ID, reference descriptor, explain gap. Forbidden: "Based on public evidence analysis" and similar. |
| ERR-003 | 1,4 | HIGH | Evidence:fact pairs (E-xxx:Fy). 3+ consecutive subcaps with identical evidence = STOP. |
| ERR-004 | 4 | HIGH | Default 0.5 increments. 0.1 only when: quantitative evidence + explicit mapping + 1 decimal max. |
| ERR-005 | 4 | HIGH | Category_Detail + Pillar_Summary must show complete rollup: subcap→capability→category→pillar→overall. Reconcile ±0.01. |
| ERR-006 | 7 | HIGH | Pillar narratives synthesized from workbook rationales. No evidence not in workbook. |
| ERR-008 | 1,4 | CRITICAL | ≥3 evidence items per subcap. <3 = BLOCKED. >30% blocked in capability = N/A. |
| ERR-009 | 1,4 | CRITICAL | Internal evidence misclassification. If HYBRID/INTERNAL mode: any Hubbl scan classified as T4+ or any structured discovery note classified as T4+ → STOP and reclassify using decision tree. |

---

## Memory, Batching & Caching

**Checkpoint files** saved to `$DMA_ROOT/checkpoints/` after each phase:

| Phase | File | Contents |
|-------|------|----------|
| 0 | `00_parameters.json` | Institution, SV, size, mode, docs |
| 1 | `01_evidence_index.json` | All evidence with IDs, tiers, facts |
| 2 | `02_peer_benchmarks.json` | Peers, scores, benchmarks |
| 3 | `03_issue_register.json` | Issues, severity, caps |
| 4 | `04_scores.json` + Workbook XLSX | All subcap scores + rationales |
| 5 | `05_priorities.json` | Priority scores, ranked |
| 6 | `06_recommendations.json` | Full argument structures |

**On resume:** Check checkpoints/ first. Confirm resume vs. fresh start.

**Batching:** Evidence by pillar→save. Peers one at a time→save. Scoring by pillar (Pass 1)→save→Pass 2 cross-pillar. Report section by section.

**Caching:** Evidence=immutable once collected. Peers=immutable. Scores=mutable (cap changes invalidate downstream). Internal docs=read-once→index. Calculation traces=cacheable, trace forward on change.

**Evidence Loading During Scoring (CRITICAL for context management):**

During Phase 4, NEVER load the full evidence index into context. Instead, load evidence
one CAPABILITY at a time using a targeted extraction:

```python
import json
data = json.load(open(f'{DMA_ROOT}/checkpoints/01_evidence_index.json'))
cap_evidence = [e for e in data['items'] if any(
    s.startswith('P1C1.1') for s in e.get('subcap_mappings', [])
)]
```

Score all subcaps in that capability, write results to the workbook, then discard the
evidence slice and load the next capability. A capability typically contains 5-12 subcaps
worth of evidence (~2-5K tokens), which is manageable. This preserves the ability to see
all evidence for related subcaps together while keeping the context footprint bounded.

---

## Proof-Carrying Scoring

In the 11-column workbook, proof is carried in these columns:

**Column J (Rationale):** ≥150 chars, human narrative with evidence citations, M-level match,
gap analysis, and institution-specific "so what". This is the primary audit trail.
**Column F (Evidence_IDs):** Comma-separated evidence references (E-xxx, INT-xxx).
**Column H (Evidence_Ceiling):** Maximum score the evidence tier supports.
**Column I (Caps_Applied):** Description of any caps that reduced the score from raw to final.

**Quality gate:** Every subcap has Rationale (Col J) ≥150 chars with E-ID citations.
M3+ scores cite 2+ sources. Evidence_Ceiling (Col H) and Caps_Applied (Col I) documented
for any capped score. Confidence (Col E) reflects evidence depth.

---

## Output Directory Taxonomy (MANDATORY)

```
{DMA_ROOT}/                         # DMA-ASM-{INST}-{DATE}-{SEQ}
├── run_manifest.json
├── 00_setup/
├── 01_evidence/
├── 02_peers/
├── 03_issues/
├── 04_scoring/
│   ├── Workbook.xlsx
│   ├── caps_applied_log.csv
│   ├── contradiction_log.csv
│   ├── reasoning_chain_log.json
│   └── exports/                    # Canonical export layer
├── 05_analysis/
├── 06_recommendations/
├── 07_deliverables/
│   ├── Report.docx
│   └── charts/
├── 08_qa/
│   ├── qa_verdict.json
│   └── qa_findings_register.csv
├── governance/                     # Layer 2 handoff
└── checkpoints/
```

**Run ID:** `DMA-ASM-{INST_CODE}-{YYYYMMDD}-{SEQ}`
**Provenance:** Every artifact references run_id. CSVs: header comment. Workbook: Run_Metadata sheet. Charts: footer. Mismatch = build fails.
**Clean build:** Never reuse from different RUN_ID.

---

## Phase 0: Engagement Setup

1. **Research Handoff Check:** Look for `research_handoff.json`. IF FOUND → set RESEARCH_HANDOFF mode, skip Phase 1. IF `locked_peer_set[]` present in handoff → import peer set, skip peer selection below.

2. **Evidence Mode:** PUBLIC / INTERNAL / HYBRID / RESEARCH_HANDOFF
   - RESEARCH_HANDOFF: Phase 1 skipped. Handoff includes claim-labeled evidence, tech utilization, uncertainty bands.
   - PUBLIC: ~2,500-4,200 web searches + Moody's connector enrichment. HYBRID: internal docs + full web search + Moody's (highest quality).
   - **Dual-Source Mandate:** web_search is PRIMARY (≥70% of queries). Moody's connectors SUPPLEMENT with structured credit/financial data. web_search MUST precede Moody's in every phase.

3. **Parameter Lock:** Institution, sub-vertical, size tier, regulator, geography
   Size: Mega(>$50B) | Large($10-50B) | Medium($2-10B) | Small($500M-2B) | Micro($100-500M) | Nano(<$100M)

4. **Toolkit Binding:** Verify ALL 4 Pillar XLSX files accessible. HARD STOP if any missing.

5. **Workspace:** Generate RUN_ID → create full directory tree → create run_manifest.json → copy qa_error_log.md to checkpoints/
   **Write RUN_ID and EVIDENCE_MODE to `00_parameters.json`. These are IMMUTABLE for the entire assessment. Every artifact must reference them. Mismatch = build fails.**

6. **Peer Set Selection & Lock** (SKIP if imported from research handoff):
   - Select 3-5 peers: sub-vertical match, size tier proximity, geographic overlap, competitive relevance
   - Document per peer: name, size_tier, key_metric, geography, overlap_pct, selection_rationale
   - Save to `00_setup/peer_set.json`
   - **Peer set is IMMUTABLE after Phase 0.** Phase 2 scores them; it does NOT re-select them.

---

## Phase 1: Evidence Collection

> **SKIP** if RESEARCH_HANDOFF mode. Print count and proceed to Phase 2.

Execute Phase Gate Protocol. Apply ERR-003, ERR-008, ERR-009.

**Dual-Source Mandate:** web_search is PRIMARY (≥70% of queries). Moody's connectors supplement
with structured credit/financial data. web_search MUST precede Moody's for each capability.

**For every subcap (~836):** 3-5 `web_search` queries → Moody's enrichment → `web_fetch` rich docs → fact-level extraction [E-xxx:Fy] → tier classify → map to specific subcap IDs.

**For HYBRID/INTERNAL mode:** Load internal evidence FIRST per Internal Evidence Integration Protocol (see below). Internal T1/T2 evidence takes priority over public T3-T5.

**Query Construction (4 signals):** Diagnostic Q decomposition → Subcap keywords → Tier-aware source targeting → Proxy signals. See research skill for full 10-tier system.

**Fact extraction — THIS IS THE CRITICAL STEP:**
```
GOOD: E-011 → F1:P1C1.1.1, F2:P1C1.2.1, F3:P1C1.1.3[ABSENCE], F4:P1C1.1.4
BAD:  E-011 → F1:P1C1 [category-level = FAILS scoring]
```
Each evidence item MUST produce ≥2 facts to DIFFERENT subcap IDs.

**5-Layer Analysis (internal docs):** Explicit → Implicit → Absence → Contradiction → Strategic

**Quality Gates (block Phase 2):**
- Facts/item avg ≥2.0. Subcap-level mapping (not category). ≥3 evidence items/subcap.
- Web search coverage ≥80% of target. >20% blocked subcaps = STOP.

---

## Phase 2: Peer Scoring & Benchmarking

Execute Phase Gate Protocol.

**Peer set is already locked** (from Phase 0 or research handoff). This phase SCORES them; it does NOT re-select them.

Score each peer at category level → calculate benchmarks. Generate evidence coverage and quality grades (A/B/C) per category. See `references/peer_benchmarking.md`.

**MANDATORY output files — ALL must exist before Phase 3:**
- `02_peers/peer_scores_{PeerName}.json` — per-peer category scores
- `02_peers/peer_synthesis.md` — narrative synthesis of peer landscape
- `02_peers/peer_comparison_table.csv` — entity vs peers, category-by-category, with median/P25/P75 and deltas
- Verify: `ls 02_peers/` must contain ≥(N_peers + 2) files.

**HARD GATE:** If `02_peers/` does not contain all required files → BLOCK Phase 3.

---

## Phase 3: Issue Register & Cap Determination

Execute Phase Gate Protocol.

Search enforcement databases → Issue Time Map → severity S1/S2/S3 → determine all caps before scoring.

---

## Phase 4: Scoring & Workbook Production

Execute Phase Gate Protocol. Apply ERR-001, ERR-002, ERR-003, ERR-004, ERR-005, ERR-008, ERR-009.

**Read first:** `references/scoring_methodology.md`, `references/workbook_specification.md`.

**Load evidence per-capability** (see "Evidence Loading During Scoring" in Memory section).

**OUTPUT FORMAT: 11-column P#_Subcap_Scoring sheets (see "Workbook Column Structure" above).**
Each row = one subcap ID (e.g., P1C1.1.1). Column D = final score. Column J = rationale.
If your sheet has <50 rows, you are scoring at the WRONG LEVEL — STOP.

### Capability Micro-Loop (repeat for each ~72 capabilities)

**3a. RETRIEVE** subcap list + diagnostic Qs from Pillar XLSX Column H.
List every subcap ID under this capability (e.g., P1C1.1.1, P1C1.1.2, P1C1.1.3...).
Each subcap becomes ONE ROW in the workbook.

**3b. MAP EVIDENCE** to each subcap individually. Different diagnostic Qs → different facts from same source. Evidence minimum check: ≥3 items or BLOCKED.

**INTERNAL EVIDENCE PRIORITY CHECK (HYBRID/INTERNAL mode — fires before public evidence mapping):**
1. Check: does internal evidence exist for this subcap? (Hubbl scans, discovery notes, client docs)
2. If YES: classify using decision tree — NEVER default to T4:
   - Hubbl/BuiltWith/Wappalyzer scan → T1 (machine-verified)
   - Structured discovery notes with specific tech/metrics → T2
   - Client-provided policy docs, board decks, roadmaps → T2
   - General internal doc without specific metrics → T3
   - Informal memo, anecdotal claim → T4
3. Internal T1/T2 evidence RAISES the evidence ceiling (not constrained by public T3-T5 caps)
4. When internal contradicts public: internal T1/T2 wins unless public T1 disagrees
5. Log in rationale: "Internal evidence [INT-xxx] classified as T2, overrides public T5 ceiling"

**3c. SCORE EACH SUBCAP** using 8-step decision tree: Collect evidence → Tier classify → Evidence ceiling (Col H) → M-level match → Negative adjustments → Resolve contradictions → Apply caps (Col I) → Final score (Col D) + rationale (Col J).

**3d. WRITE RATIONALE (Column J)** — ≥150 chars, using this template:
```
[EVIDENCE]: [E-xxx:Fy] shows [fact]. [SECOND SOURCE]: [E-yyy:Fz] confirms/contradicts.
[MATURITY MATCH]: Maps to M[N] "[descriptor]" because [why]. [GAP TO NEXT]: Missing [element].
[COUNTER]: [opposing evidence or "None identified"]. [CEILING]: [cap check].
[SO WHAT]: For [Institution], this means [specific impact].
```
FORBIDDEN: "Category-based scoring", "Based on public evidence analysis", anything generic.

**3e. DIFFERENTIATION CHECK:** >60% same score within a capability = STOP. 100% identical = HARD BLOCK.

**3f. CONFIDENCE-ERS CROSS-VALIDATION:** HIGH requires ERS≥2.5. Single-source caps at MEDIUM.

**3g. LOG REASONING CHAIN** to `reasoning_chain_log.json`.

### Post-Scoring Steps

5. **GENERATE WORKBOOK FROM SCRATCHPAD (single Python script):**
   Read `scoring_scratchpad.json` → generate XLSX with ALL 11 sheets:
   ```
   Sheet order (must match CFC workbook):
   1. Executive_Summary   — Populate AFTER Pillar_Summary is computed
   2. Pillar_Summary      — 5 rows (P1-P4 + Overall) with weights, scores, peer medians, gaps
   3. Category_Detail     — 17 rows with rollup scores
   4. P1_Subcap_Scoring   — ~186 rows, 11 columns A-K
   5. P2_Subcap_Scoring   — ~232 rows, 11 columns A-K
   6. P3_Subcap_Scoring   — ~118 rows, 11 columns A-K
   7. P4_Subcap_Scoring   — ~172 rows, 11 columns A-K
   8. Evidence_Master     — All evidence items
   9. Peer_Benchmarks     — Peer scores per category
   10. Recommendations    — Top recommendations
   11. Run_Metadata       — Assessment ID, evidence mode, parameters
   ```
   **Every sheet must exist. Missing sheets = QA failure.**
   **Read the xlsx skill (`/mnt/skills/public/xlsx/SKILL.md`) before generating.**

5.5. **EVIDENCE COMPLETENESS GATE (blocks Phase 5):**
   For every scored subcap row, verify: F (Evidence_IDs) non-empty, G (Source_URLs)
   contains specific URL (not blank, not "multiple searches"), H (Evidence_Ceiling)
   contains valid tier ceiling, J (Rationale) ≥150 characters.
   Rows with score but empty/invalid evidence fields = BLOCKED. Fix before proceeding.
6. **Build Calculation Chain (MANDATORY — populates Category_Detail + Pillar_Summary sheets):**
   The calculation chain is the auditable rollup from subcap to overall score:
   ```
   a. CAPABILITY score = weighted average of subcap Score (Col D) values within that capability
      (weights from Pillar XLSX → Capability Map → Weight column)
   b. CATEGORY score = weighted average of capability scores within that category
   c. PILLAR score = weighted average of category scores within that pillar
   d. OVERALL score = weighted average of pillar scores using Sub-Vertical Pillar Weights
   ```
   Write results to Category_Detail sheet (17 rows: Category_ID, Category_Name, Pillar,
   Score, Weight, Peer_Median, Gap, Priority) and Pillar_Summary sheet (5 rows: P1-P4 + Overall).
   **Reconciliation:** Recompute pillar from categories — must match ±0.01. Fix before proceeding.
7. Run Workbook QA (G.1-G.9 from `references/quality_assurance.md`).
8. **RUN `scripts/validate_scoring_quality.py`** — exit code 1 = BLOCK Phase 5.
9. Generate canonical export CSVs to `$DMA_ROOT/04_scoring/exports/`.

---

## Phase 4.5: Adversarial Critic Pass

Execute Phase Gate Protocol.

**For each subcap:** Challenge evidence sufficiency → generate 1-3 downgrade arguments → adjudicate (DEFEND or DOWNGRADE) → log to Critic_Log sheet.

**Tie-break:** T1/T2 > ERS attacks > Quantified > Corroborated > Conservative default.
**Cap changes:** Log as CRITIC_CHALLENGE in Caps_Applied_Log. Recalculate aggregations.
**Metrics:** Coverage target 100% for ≥2.5 scores. If 100% DEFEND, re-examine top 5.

**Distributional Self-Checks (DC-01 through DC-08):**
Score clustering, confidence inflation, tier concentration, cap saturation, rationale homogeneity, evidence reuse, score-confidence alignment, peer benchmark plausibility. Fix or document.

---

## Phase 5: Analysis & Synthesis

Execute Phase Gate Protocol.

Compare to peer benchmarks. Calculate priority scores (6-factor: Business Impact, Risk, Competitive Gap, Effort Inverse, Quick Win, Trend). See `references/priority_framework.md`.

---

## Phase 6: Recommendation Development

Execute Phase Gate Protocol.

**Zennify Scope Boundary:** Zennify = technology implementation partner. IN-SCOPE: 12 Zennify solutions (Service Cloud, FSC, Marketing Cloud, Data Cloud, MuleSoft, CRM Analytics, Shield, Slack, Agentforce, Experience Cloud, GRC, Digital Strategy Workshop). OUT-OF-SCOPE: hiring, reorgs, certifications, board changes, non-Zennify vendors → tag as [CLIENT] responsibility.

**Per recommendation:** Evidence-grounded root cause → Peer-led gap assessment (live research) → Zennify offering alignment (see `references/zennify_solutions.md`) → Impact prioritization with cross-pillar unlocks → Counter-argument & alternative analysis.

---

## Phase 7: Deliverable Generation

Execute Phase Gate Protocol. Apply ERR-006.

Generate in order: **1. Workbook** → **2. Report** (.docx) → **3. Charts** → **4. Peer Analysis** → **5. Run Manifest** → **6. Governance Logs** → **7. Validate** → **8. Citation validation**

### Report Generation Protocol (MANDATORY)

**Template is MANDATORY — NO deviation.**

**STEP 0:** Retrieve `DMA_Assessment_Report_Template.docx` from the project knowledge base.
This is the ONLY acceptable report structure. Do NOT create ad hoc layouts. Do NOT invent
sections. Fill the template exactly as structured.

**STEP 1 — ANALYZE (before writing ANYTHING — save analysis to disk):**
  Create `$DMA_ROOT/07_deliverables/report_analysis.json` containing:
  ```python
  analysis = {
    "total_evidence_items": N,
    "unique_e_ids": [list],
    "items_per_pillar": {"P1": N, "P2": N, "P3": N, "P4": N},
    "top_5_strongest": [{"subcap_id": "P1C1.1.1", "score": 3.5, "evidence": "E-xxx", "why": "..."}],
    "top_5_weakest": [{"subcap_id": "P2C3.2.1", "score": 1.5, "evidence": "none", "why": "..."}],
    "top_3_patterns": ["pattern description with E-IDs"],
    "cross_pillar_links": ["P4C1 low → caps P2C4 because..."],
    "peer_gaps": [{"category": "P2C1", "entity_score": 2.5, "peer_median": 3.2, "gap": -0.7}]
  }
  ```
  **This file is the ONLY input to Step 2. If it doesn't exist, Steps 2-3 cannot proceed.**

**STEP 2 — SYNTHESIZE (write synthesis to disk — do NOT skip):**
  Create `$DMA_ROOT/07_deliverables/report_synthesis.md` answering:
  a. What story does the DATA tell? (cite specific E-IDs and scores)
  b. Where vs peers — and WHY? (cite peer_gaps from analysis)
  c. What should Zennify prioritize? (map to specific Zennify solutions with evidence)
  d. Cross-pillar unlocks? (cite cross_pillar_links from analysis)
  **Each answer must reference specific E-IDs, scores, and peer data. Generic answers = redo.**

**STEP 3 — WRITE (following template structure, reading from synthesis):**
  Read `report_synthesis.md` → write each report section using ONLY data from synthesis.
  a. SCQA Executive Summary with ≥7 unique E-ID citations
  b. Pillar Deep Dives using "What We See / Why It Matters" structure per pillar
  c. Recommendations with ROOT CAUSE (E-IDs) + SOLUTION (Zennify offering) + EXPECTED OUTCOMES
  d. NO investment amounts, cost estimates, or ROI projections anywhere in the report

**STEP 4 — VALIDATE (before declaring Phase 7 complete):**
  a. Count E-xxx citations in report. <30 = FAIL, rewrite.
  b. Specificity test: could any paragraph apply to a different institution? If YES = rewrite.
  c. Verify Assessment ID and Evidence Mode on cover page, header, Appendix C match run_manifest.json.
  d. Verify every recommendation cites specific E-IDs and maps to a named Zennify solution.
  e. Verify peer data appears ≥10 times with specific peer names and scores.

**ANTI-GENERIC CHECK (fires before EVERY section):**
FORBIDDEN without proxy evidence confirming the gap exists: "Appoint a CDO", "No CDO found",
"no digital strategy", "Create a Center of Excellence", "Establish a data governance committee",
"Hire a CISO", "Form an innovation lab". Before concluding "no evidence" for any capability →
exhaust proxy searches (Tiers 7-10: industry associations, vendor case studies, job postings,
Glassdoor, community forums).

### Data Borrowing from Research Report (MANDATORY)

The following sections are COPY operations from the Client Profile / Research Report.
Do NOT rewrite them. Load the research report, extract relevant sections, and transplant
with assessment-layer annotations:

1. Section 3 (Trend Analysis & Digital Evolution Timeline) ← Research Report Section 3.3
2. Section 4 (Issue Register & Issue Timeline) ← Research Report Section 5.1
3. Section 2 (Assessment Methodology, entity context) ← Research Report Section 2

For sections requiring NEW analysis (Pillar Deep Dives, Recommendations, Gap Prioritization),
follow the Analyze→Synthesize→Write protocol above.

### Report Rules
- **Scoring-related claims** (pillar deep dives, capability analysis, recommendations): Synthesize FROM workbook rationales ONLY. No scoring facts not in workbook.
- **Contextual sections** (trend analysis, issue timeline, entity profile): BORROW from research report per Data Borrowing protocol above. These sections provide context, not scoring assertions.
- Read scoring data ONLY from canonical export CSVs in `$DMA_ROOT/04_scoring/exports/`. No ad hoc data sources.
- Inline citations: ≥5 in Executive Summary, ≥2/capability in Pillar Deep Dives, ≥1/recommendation. Total ≥30.
- Post-generation: count E-xxx citations. <10 = FAIL, rewrite.
- Structure: per `DMA_Assessment_Report_Template.docx` from project knowledge base.

### Run Manifest (`run_manifest.json`)
Schema: `run_manifest_v2`. See `references/workbook_specification.md` for full spec.
**Key validation rules:** $schema="run_manifest_v2" | overall=weighted avg pillars ±0.02 | total_items=sum tier_distribution | confidence sum=subcap count | verdict ∈ {PASS,PASS_WITH_NOTES} for delivery.

### Governance Logs (CSV exports for Layer 2)

**`caps_applied_log.csv`** — Contract 2. Columns: cap_id, cap_type (EVIDENCE_CEILING/SENTIMENT/REGULATORY/CROSS_PILLAR/ADJ_*/CRITIC_CHALLENGE), trigger_reason, trigger_evidence, affected_id, raw_score, cap_ceiling, final_score, score_delta.

**`contradiction_log.csv`** — Contract 3. Columns: contradiction_id, subcap_id, evidence_a_id, evidence_a_ers, evidence_a_claim, evidence_b_id, evidence_b_ers, evidence_b_claim, resolution_rule, winner, justification, confidence_impact, flagged_in_report, contradiction_type (HARD/SOFT).

**`evidence_index.csv`** — Contract 4. Columns: evidence_id, source_name, url, tier, ers_score, publish_date, subcaps_supported, key_facts_count.

**`reasoning_chain_log.json`** — Contract 8. Per-subcap: decision_path, evidence_considered, ceiling_calc, m_level_match, caps_applied, contradictions, confidence, critic_result, final_score. See `references/reasoning_chain_schema.md`.

### Post-Delivery Evidence Validation
Before declaring Phase 7 complete, verify all evidence IDs referenced in the workbook and report exist in `evidence_index.csv`. Any broken reference = fix before proceeding to Phase 8.

---

## Phase 8: Quality Assurance (14-Check Suite)

Execute Phase Gate Protocol.

Run full validation per `references/quality_assurance.md`. Workbook wins on mismatch.

**`scripts/qa_auditor.py` now runs 14 checks (expanded from 6). ALL must pass.**

| # | Check | Severity | What It Catches |
|---|-------|----------|----------------|
| 1 | Row counts per pillar (≥50 rows) | CRITICAL | Category-level scoring |
| 2 | Score bounds (1.0-5.0, max 1 decimal) | CRITICAL | Out-of-range scores |
| 3 | Evidence linkage (score → evidence exists) | HIGH | Ungrounded scores |
| 4 | Caps log consistency (Caps_Applied non-empty → Score ≤ Evidence_Ceiling) | MEDIUM | Undocumented caps |
| 5 | Rationale quality (≥150 chars, E-ID cited) | MEDIUM | Generic rationales |
| 6 | Weight sums (~1.0 per capability) | MEDIUM | Broken aggregation |
| 7 | **Evidence field completeness** | **CRITICAL** | Truncated evidence: missing URLs, no ERS, no excerpts |
| 8 | **Report citation density** (≥30 unique E-IDs, ≥5 in exec summary) | **CRITICAL** | Reports with zero or thin citations |
| 9 | **Output artifact existence** (all mandatory files present) | **CRITICAL** | Missing deliverables (peer files, exports, report) |
| 10 | **Assessment ID consistency** (same RUN_ID across all artifacts) | **CRITICAL** | Mixed-run output |
| 11 | **Evidence mode consistency** (same mode across all artifacts) | **HIGH** | Conflicting evidence mode claims |
| 12 | **Peer data in report** (≥10 peer references, ≥1 per pillar) | **HIGH** | Peer data not flowing into report |
| 13 | **Anti-generic rationale check** (scan for forbidden patterns) | **HIGH** | Generic consulting prose |
| 14 | **Score differentiation + distribution** (no pillar >70% same score) | **MEDIUM** | Uniform scoring |

**Checks 7-14 are NEW. They catch the real issues that the previous 6-check suite missed.**

**Run:** `python scripts/qa_auditor.py --workbook <path> --report <path> --assessment-dir <path>`
Exit code 1 = FAIL. Do NOT manually override verdicts. Fix issues and re-run.

### Computed QA Verdict (`$DMA_ROOT/08_qa/qa_verdict.json`)

Generated programmatically — never from manual/stale templates:
```python
qa_verdict = {
    "run_id": RUN_ID,
    "generated_at": ISO_TIMESTAMP,
    "verdict": "PASS|PASS_WITH_NOTES|FAIL",
    "checks_executed": {"total": N, "passed": P, "failed": F, "warnings": W},
    "reconciliation": {
        "subcap_count_match": bool, "pillar_rollup_reconciled": bool,
        "evidence_ids_all_valid": bool, "broken_evidence_refs": 0
    },
    "score_state_propagation": {
        "raw_to_final_consistent": bool, "category_uses_final_score": bool,
        "pillar_uses_final_score": bool
    },
    "artifact_provenance": {"run_id_consistent_across_all": bool, "mismatched_artifacts": []},
    "regression_tests": "8/8 PASS",
    "blocker_issues": [],
    "timestamp_validation": {"all_artifacts_after_run_start": bool, "stale_artifacts_found": []}
}
```

**Verdict:** FAIL = any blocker/reconciliation failure/regression fail. PASS_WITH_NOTES = warnings only. PASS = all green. Timestamp MUST be newer than all other artifacts.

**Regression Tests:** Run all 8 suites per `references/regression_tests.md`. X/8 PASS. CRITICAL fail = fix before delivery.

**Error Log Patch:** Output in chat for human to append to master qa_error_log.md.

---

## Report Formatting & Branding

**Font:** DM Sans (Google Font). Fallback: Calibri. Bold headings, Regular body, Medium tables.
**Colors:**
- Heading text: Dark Teal `#1F9A90`
- Table header bg: Primary Teal `#27BBAF` (white text)
- Body: Charcoal `#333333` | Alt rows: Light Teal `#E8F8F6`
- Maturity: M1=`#D32F2F` M2=`#F57C00` M3=`#FBC02D` M4=`#388E3C` M5=`#1565C0`

**Layout:** Letter, 1" margins, 11pt body, 1.15 spacing. Cover page: teal bg, white text. See `references/report_template.md`.

---

## Language Standards

**Substitutions:** "gap"→"opportunity" | "weakness"→"development area" | "critical gap"→"priority improvement area" | Fixed timelines→milestone-anchored
**SO WHAT Test:** FINDING → SO WHAT (for THIS institution) → NOW WHAT (specific action)

---

## Ontology (Strict Definitions)

**Evidence Item:** Single time-bound fact from a source, with Tier, Date, Source, Fact ID.
**Unique Source:** A document/database producing evidence. Multiple facts from same source = 1 source for corroboration.
**Corroboration:** 2+ different sources AND 2+ different tier types. Exception: single T1 ≤24mo = HIGH alone.
**Hard Contradiction:** Direct factual conflict (can't both be true) → resolution protocol → Contradiction_Log. **Soft:** Interpretive divergence → prefer authoritative, no forced resolution.
**Trend:** ≥2 dated points, ≥6 months apart. Single snapshot ≠ trend.
**Score Precision:** Default 0.5 grid. 0.1 only with quantitative evidence + explicit mapping + max 1 decimal. 2+ decimals = QA failure.

---

## Unknown as First-Class Outcome

Insufficient evidence → LOW confidence, score ceiling, transparent gap documentation.
>30% subcaps NO_EVIDENCE → capability N/A (exclude from aggregation, redistribute weight).
Never fabricate. "I don't know" builds credibility. Feed gaps into Missing Evidence Impact Plan (report Section 11).

---

## Reference Files

| File | Phase | Contents |
|------|-------|----------|
| `references/analytical_framework.md` | All | Argument construction, triangulation, red flags |
| `references/scoring_methodology.md` | 4 | 8-step decision tree, caps, dependencies |
| `references/sub_verticals.md` | 0 | Regulatory/competitive context per SV |
| `references/capability_criteria.md` | 4 | Diagnostic Qs, M1-M5 indicators |
| `references/peer_benchmarking.md` | 2 | Scoring methodology, benchmarks (peer selection now in Phase 0) |
| `references/evidence_ranking.md` | 1,7 | ERS calculation, citation priority |
| `references/quality_assurance.md` | 8 | Full validation checklist |
| `references/regression_tests.md` | 8 | 8 golden test suites |
| `references/communication_standards.md` | 7 | Citation patterns, language |
| `references/report_template.md` | 7 | Section structure, tables |
| `references/priority_framework.md` | 5 | 6-factor formula |
| `references/zennify_solutions.md` | 6,7 | 12 offerings, mapping, investment |
| `references/workbook_specification.md` | 4,7 | Sheet specs, column defs, rationale template |
| `references/qa_error_log.md` | 0 | Master error log (copy to writable) |
| `references/reasoning_chain_schema.md` | 4,7 | reasoning_chain_log.json schema |

## Scripts

| Script | Phase | Purpose |
|--------|-------|---------|
| `scripts/ingest_evidence.py` | 1 | Pre-process documents |
| `scripts/build_index.py` | 1 | BM25 retrieval index |
| `scripts/retrieve.py` | 1 | Evidence retrieval per subcap |
| `scripts/assessment_runner.py` | 0-4 | Batch scoring orchestrator |
| `scripts/validate_scoring_quality.py` | 4 | **MANDATORY** 8-gate validator |
| `scripts/qa_auditor.py` | 8 | Automated QA checks |
| `scripts/generate_governance_outputs.py` | 7 | CSVs + manifest from workbook |
| `scripts/validate_contracts.py` | 7 | Layer 2 contract validation |

## Pillar XLSX Files

Search `/mnt/user-data/uploads/` and `/mnt/project/` for:
Pillar 1-4 Scoring Toolkit (or v5.0 equivalent). Key sheets: Capability Map, Maturity Descriptors, Sub-Vertical Matrix.

---

## Error Handling

- Document unreadable → UNAVAILABLE, continue
- Context overflow → checkpoint, batch, resume (new conversation if needed)
- Contradiction unresolvable → conservative, LOW confidence
- >30% no evidence → capability N/A, exclude from weighted avg
- Score >1.5 from peers → investigate evidence quality
