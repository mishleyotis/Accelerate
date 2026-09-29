---
name: dma-assessment
description: >
  Conducts Digital Maturity Assessments (DMA) for financial services institutions using
  argument-based reasoning. Covers 9 sub-verticals across 4 pillars, 16 categories, 136
  capabilities, 851 subcapabilities (686 universal + 165 sub-vertical
  variants) scored 1-5 and rendered in four bands. Works best when preceded by dma-research
  skill (research_handoff.json with claim-labeled evidence, tech utilization, uncertainty
  bands). ALWAYS use this skill when the user mentions: DMA, digital maturity, scoring
  subcapabilities, maturity rubric, pillar scoring, scoring workbook, cap enforcement, peer
  benchmarking, Zennify DMA, pillar/capability IDs like P1C1, P2C3, maturity levels M1-M5,
  or uploaded internal documents in assessment context. Also trigger when asked to assess,
  score, or benchmark any financial services institution's digital capabilities.
---

# DMA Assessment Skill v5.6

**v5.6 Changes (2026-09-03):** the workbook is `${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/contract.py`'s and this skill
BUILDS NO WORKBOOK. The scoring stage writes column D of the run's existing workbook through
`engine.assessment open / score / critique / rollup / gate`. The retired `scripts/assessment_runner.py`
(it built a fresh 11-sheet openpyxl workbook) refuses and names those commands. The eleven app-facing
columns A–K below are unchanged — they are the first eleven of the contract's 33 (L–AG are the
research working area, stripped after the handoff). Category count is 16 (v7.0), not 17.

**v5.5 Changes:** 11-column app-facing layout (matching CFC workbook: SubCap_ID, SubCap_Name,
Category, Score, Confidence, Evidence_IDs, Source_URLs, Evidence_Ceiling, Caps_Applied,
Rationale, Proxy_Searched). Subcap-level scoring reinforced with row count checks. Explicit
calculation chain rollup instructions. Taxonomy vs workbook row count clarified. QA checks
aligned with the A–K columns. URL enforcement. Cross-skill consistency (3-5 queries/subcap).

## Reading manifest — by phase

| Phase | Read | Why |
|---|---|---|
| Phase 0 (setup) | this file's rules, `references/workbook_columns.md`, `references/operating_procedure.md` | the contract and the working rules |
| Phases 1–3 | `references/evidence_ranking.md`, `references/peer_benchmarking.md`, this file's Cap System | tiers, peers, caps |
| Phase 4 (scoring) | `references/scoring_methodology.md`, `references/score_states.md`, `references/phase_4_scoring.md` | the eight steps, the arithmetic (`engine.assessment apply`), the loop |
| Phases 5–6 | `references/analytical_framework.md`, `references/priority_framework.md`, `references/zennify_solutions.md` | synthesis and recommendations |
| Phase 7 | `references/phase_7_deliverables.md`, `references/report_template.md`, `references/communication_standards.md` | the deliverables |
| Phase 8 | `references/phase_8_qa.md`, `references/quality_assurance.md`, `references/regression_tests.md` | QA |

## ⛔ NON-NEGOTIABLE RULES

| # | Rule | Failure It Prevents |
|---|------|---------------------|
| 1 | **Score at SUBCAPABILITY level** — one row per subcap ID (e.g., P1C1.1.1, P1C1.1.2). Each P#_Subcap_Scoring sheet must have ≥50 rows. P1≈186, P2≈232, P3≈118, P4≈172. If your sheet has <50 rows, you are scoring at CATEGORY level — STOP and redo. | Category-level scoring (17-28 rows instead of 700+) |
| 2 | **Differentiate scores** — ≥2 unique scores per capability. Each subcap's diagnostic question asks something DIFFERENT — scores should reflect that. | Identical scores (2.5, 2.5, 2.5...) across all subcaps |
| 3 | **Map evidence to INDIVIDUAL subcaps** — cite E-xxx:Fy fact-level refs. Different subcaps within the same capability must cite DIFFERENT evidence facts. | Same evidence cited for every subcap |
| 4 | **≥150-char rationales per subcap** — institution-specific, cite E-IDs, reference M-level descriptor, explain gap to next level. | Generic "demonstrates capability" text |
| 5 | **Never build a workbook** — the run's ONE workbook already exists (`engine.cli start` created it from `${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/contract.py`: 41 sheets, P#_Subcap_Scoring seeded with every selected subcap and its `SubCap_Name`). Scores go into ITS column D through `engine.assessment score`; a fresh `openpyxl.Workbook()`, a "single Python script that generates the XLSX" or the retired `scripts/assessment_runner.py` is REFUSED by the PreToolUse hook. See "Workbook Column Structure" below for the A–K columns you write. | A second workbook with the wrong shape, missing fields, formatting and subcap names — the "workbook defaults to the wrong structure every run" defect |
| 6 | **Cite evidence inline in report** — (E-xxx, Source, Tier, Date) | Generic consulting prose |
| 7 | **Run `scripts/validate_scoring_quality.py` after Phase 4** | Undetected quality failures |
| 8 | **Web searches at SUBCAPABILITY level** — 3-5 per subcap via `web_search`. Each subcap's diagnostic question drives DIFFERENT queries. | Thin single-source assessments |

**If output matches any "Failure" pattern, STOP and redo that step.**

---

## Workbook Column Structure (the contract's P#_Subcap_Scoring sheet — columns A–K are yours)

Read `references/workbook_columns.md` — the eleven app-facing columns A–K and what each holds. Read once, in Phase 0.

## Context Window Management (CRITICAL)

Read `references/operating_procedure.md` — context-window, memory/batching and output-directory rules. Read in Phase 0 and again when a batch closes.

## Core Analytical Principles

**1. Specificity:** Before writing ANY sentence, test: "Could this appear unchanged for a different institution?" If YES → rewrite with institution-specific data. FORBIDDEN: "The institution should improve its digital capabilities" and similar generic prose.

**2. Argument-Based Reasoning:** Every conclusion requires: CLAIM → EVIDENCE → REASONING → COUNTER-ARGUMENTS → REBUTTAL → QUALIFICATION. See `references/analytical_framework.md`.

**3. Evidence Triangulation:** No MEDIUM+ confidence conclusion rests on single-source evidence. Minimum 2 tier types for M3+. Hard cap: single tier-type only → max 2.5 (unless T1/T2). See `references/scoring_methodology.md` Step 3.

**4. Single Source of Truth:** The Scoring Workbook is canonical. All other artifacts derive FROM it. Numbers never diverge. Workbook wins.

---

## Taxonomy & Maturity Scale

```
Pillar (4) → Category (16) → Capability (136) → Subcapability (851)
```

| Pillar | Name | Subcaps |
|--------|------|---------|
| P1 | Strategy, Governance & Culture | 205 |
| P2 | Member/Customer Experience | 292 |
| P3 | Operations, Risk & Compliance | 164 |
| P4 | Data, Analytics & Technology | 190 |

**Note:** Taxonomy counts (851 = 205 P1 + 292 P2 + 164 P3 + 190 P4) are
COUNTED FROM THE CATALOGUE, never asserted: run
`python3 plugins/dma-insights/skills/dma-research/engine/contract.py`.
They are the theoretical maximum from the Pillar XLSX toolkits.
Actual workbook rows vary by sub-vertical (some subcaps are N/A). Typical observed ranges:
P1≈186, P2≈232, P3≈118, P4≈172 (~708 total). Both are valid — the workbook contains
all applicable subcaps for the specific institution's sub-vertical.

| Level | Name | Range | Meaning |
|-------|------|-------|---------|
| M1 | Foundational | 1.0–1.4 | Absent/ad-hoc |
| M2 | Developing | 1.5–2.4 | Basic, inconsistent |
| M3 | Established | 2.5–3.4 | Standardized, documented |
| M4 | Advanced | 3.5–4.4 | Optimized, data-driven |
| M5 | Leading | 4.5–5.0 | Industry-leading |

This is the 1–5 **score** scale (`skills/dma-research/engine/rubric.py`, the one owner of
these rows). It is not the four display **bands** the app renders — `<2 Activating · <3
Building · <4 Competing · ≥4 Differentiating`, strict less-than on the raw score
(`engine.contract.band_of`, `apps/web/lib/bands.js`). A fifth band word appears nowhere.

Maturity descriptors: Pillar XLSX files → Maturity Descriptors sheet.

---

## Evidence Tier System

| Tier | Type | ERS Score | Max Alone |
|------|------|-----------|-----------|
| T1 | Regulatory/Audited + Verified Tech Scans | 5.0 | none (5.0) |
| T2 | Official Disclosures + Structured Internal | 4.0 | none (5.0) |
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

Adjustments are `ADJ_` deltas that lower the raw score. **The arithmetic has one owner:** `python3 -m engine.assessment apply --run <R> --subcap <cell> --raw <M> --adj ADJ_…:-0.3 --cap CAP_…:3.0` computes `min(raw + Σadj, evidence ceiling, caps)`, takes it to the quarter-point (down, never up) and returns the final, the band and the arithmetic string; `score --raw --adj --cap` does the same and records the working in `Caps_Applied`. A scorer supplies inputs, never the result (QA audit F-F14-029: three scorers, one cell, 2.5 / 2.7 / 2.7).

**Severity:** S3 (active enforcement <12mo)→2.0 | S2 (terminated <24mo)→3.0 (`contract.CAP_TRIGGERS`)
**Evidence:** T5-only→2.0 | T4/T5-only→2.5 | Single source→3.0 | Single tier-type→2.5 (EXCEPTION: internal T1/T2 + public T3 = two tier types, ceiling removed) | >24mo→ADJ −0.3
**Internal Evidence Override:** Internal T1/T2 evidence removes the single-tier-type cap (2.5). A subcap supported by both internal T2 and public T3 has no ceiling (5.0), not M2.5.
**Sentiment (P2):** Rating <3.0→2.0 | 3.0-3.5→2.5 | 3.5-4.0→3.5 | Complaints +20% YoY→ADJ −0.3

**Cross-Pillar (applied Pass 2 AFTER all pillars scored):**
P1C2<2.5→P3 cap 3.0 | P4C4<2.5→P4C1 cap 3.0 | P3C3<2.5→P2C2 cap 3.0 |
P4C1<2.5→P2C4 cap 3.0 | P4C3<2.5→P3C1 cap 3.0 | Breach <12mo→P4C4 cap 2.0

Authoritative: `references/scoring_methodology.md` Step 3, Step 7.

---

## Deterministic Score States (MANDATORY)

Read `references/score_states.md` — the score states and the raw-to-final pathway. Read before Phase 4; `engine.assessment apply` does the arithmetic.

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

Read `references/operating_procedure.md` — memory, batching and caching (same file as the context-window rules).

## Proof-Carrying Scoring

In the P#_Subcap_Scoring sheet, proof is carried in these columns:

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

Read `references/operating_procedure.md` — the output directory taxonomy (same file).

## Phase 0: Engagement Setup

1. **Research Handoff Check — THE WORKBOOK, not the JSON.**

   Look for the **scoring workbook** (`DMA_Scoring_Workbook_*.xlsx`, contract
   v3). It is the handoff. Open it and read `Handoff_Lock`:

   ```
   python3 ${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/validator.py \
       --workbook <WORKBOOK> --json
   ```

   * **FAILS=0** → set `RESEARCH_HANDOFF` mode and skip Phase 1. The
     engagement set is the seeded rows; `Run_Metadata.subcaps_selected` is
     the denominator for every coverage figure you report.
   * **`Handoff_Lock.catalogue_hash` ≠ the catalogue you are about to score
     against → HARD STOP.** The catalogue moved between research and
     assessment and the scores would be against a different taxonomy. This
     is the refusal the Client Profile template asserts and that nothing
     implemented.
   * **`locked_peer_set` in `Handoff_Lock`** → import the peer set and skip
     peer selection below.
   * **Any FAIL** → the workbook does not satisfy its own contract. Repair
     the research run; do not score around it.

   `research_handoff.json`, where present, is a **read-only index over those
   same sheets** and says so in its own `_contract` block. It is not the
   interface. Two skills once agreed on that JSON file as a private contract
   the owner never designated, so the artefact the owner audits (the
   workbook) and the artefact the pipeline trusted (the handoff) could
   diverge with no gate noticing — and three gate-required analysis fields
   died in the gap. **If the two ever disagree, the workbook is right.**

2. **Evidence Mode:** PUBLIC / INTERNAL / HYBRID / RESEARCH_HANDOFF
   - RESEARCH_HANDOFF: Phase 1 skipped. The WORKBOOK carries claim-labelled
     evidence (`Evidence_Detail`), the per-subcap synthesis and its ceiling
     reasoning (columns L..AG), the search log, the gate log and the
     uncertainty band — all of it beside the rows it bears on. Read the
     sheets; do not re-derive from a JSON copy of them.
   - PUBLIC: the research tier's public evidence, five volleys per cell. HYBRID: internal
     documents beside it (highest quality). Which tool, in which order, is the research
     tier's rule, stated once (`${CLAUDE_PLUGIN_ROOT}/skills/dma-research/references/RESEARCH-PROTOCOL.md`
     § *Tools*); this skill restates none of it.

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

**Which tools the evidence came through** is
the research tier's rule, stated once in `${CLAUDE_PLUGIN_ROOT}/skills/dma-research/references/RESEARCH-PROTOCOL.md`
§ *Tools: first choice, fallback, and what you emit* — this skill restates none of it.

**For every subcap (851 at full scope):** the research lane fired the five volleys and the
primary question, read rich documents as windows through `engine.cli fetch`, extracted at
fact level `[E-xxx:Fy]`, tiered and mapped each fact to the cells it bears on — and the
floors gate holds the category to it before this skill opens.

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

Read `references/phase_4_scoring.md` — the scoring loop, the capability micro-loop and the post-scoring steps. Read when Phase 4 opens.

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

Read `references/phase_7_deliverables.md` — the report generation protocol. Read when Phase 7 opens.

## Phase 8: Quality Assurance (14-Check Suite)

Read `references/phase_8_qa.md` — the 14-check suite. Read when Phase 8 opens.

## Report Formatting & Branding

**Font:** DM Sans (Google Font). Fallback: Calibri. Bold headings, Regular body, Medium tables.
**Colors:**
- Heading text: Dark Teal `#1F9A90`
- Table header bg: Primary Teal `#27BBAF` (white text)
- Body: Charcoal `#333333` | Alt rows: Light Teal `#E8F8F6`
- Maturity BANDS (four, and only four — charter invariant 6):
  Activating=`#D32F2F` Building=`#62D7B8` Competing=`#FBC02D`
  Differentiating=`#388E3C`. A null score gets NO swatch. There is no
  fifth band and no hex for one; the score levels 1-5 are a different
  scale from the four display bands and never carry a colour.

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
| `references/workbook_columns.md` | 0 | Columns A–K of P#_Subcap_Scoring (moved from this file, F-B04-027) |
| `references/operating_procedure.md` | 0 | Context window, memory/batching/caching, output directory taxonomy |
| `references/score_states.md` | 4 | Deterministic score states; `engine.assessment apply` does the arithmetic |
| `references/phase_4_scoring.md` | 4 | The scoring loop and the capability micro-loop |
| `references/phase_7_deliverables.md` | 7 | Report generation protocol |
| `references/phase_8_qa.md` | 8 | The 14-check suite |

## Scripts

| Script | Phase | Purpose |
|--------|-------|---------|
| `scripts/ingest_evidence.py` | 1 | Pre-process documents |
| `scripts/build_index.py` | 1 | BM25 retrieval index |
| `scripts/retrieve.py` | 1 | Evidence retrieval per subcap |
| `scripts/assessment_runner.py` | — | **RETIRED** (refuses): it built a fresh 11-sheet workbook. Scoring runs through `engine.assessment open / score / critique / rollup / gate` on the run's one workbook |
| `scripts/validate_scoring_quality.py` | 4 | **MANDATORY** 8-gate validator |
| `scripts/qa_auditor.py` | 8 | Automated QA checks |
| `scripts/generate_governance_outputs.py` | 7 | CSVs + manifest from workbook |
| `scripts/validate_contracts.py` | 7 | Layer 2 contract validation |

## Pillar XLSX Files

The engine reads the catalogue, never the XLSX: `packages/shared/catalogue_v70_tier.json`
(+ `catalogue_v70_names.json`) resolved by `engine.contract.catalogue_path()` (env
`DMA_CATALOGUE` → the checkout → the packaged copy). The Pillar 1-4 Scoring Toolkit XLSX
files are the v7.0 source of record at `gs://digital-maturity-assessor-catalogue-staging/v7.0/`
and are pulled by the research-conductor at run start. Key sheets: Capability Map, Maturity
Descriptors, Sub-Vertical Matrix. Nothing is searched for under `/mnt/`.

---

## Error Handling

- Document unreadable → UNAVAILABLE, continue
- Context overflow → checkpoint, batch, resume (new conversation if needed)
- Contradiction unresolvable → conservative, LOW confidence
- >30% no evidence → capability N/A, exclude from weighted avg
- Score >1.5 from peers → investigate evidence quality
