> **AUTHORITY NOTE (added by rectification, MEM-0054 + MEM-0055).**
> `SKILL.md` is the authority on workbook shape and it declares the
> **11-column `P#_Subcap_Scoring`** layout CANONICAL, in these words: *"This is
> the ONLY acceptable column layout. Do NOT use the legacy 22-column (A-V)
> layout."* Where this file still describes columns R/S/T/U/V or sheets named
> `P#_Scoring_Detail`, it is describing the LEGACY form and SKILL.md wins.
>
> That disagreement was not academic. `scripts/validate_scoring_quality.py` —
> declared MANDATORY after Phase 4 — checked the layout described here, found
> none of its sheets in a canonical workbook, and then five of its seven checks
> iterated the absent sheets, examined zero rows and printed PASS. A real
> assessment went through it with five green ticks and not one score examined,
> and reached a regulated client. The validator now checks the canonical form
> and refuses to print PASS for a check that examined nothing.
>
> Proof in the canonical form is carried by **J (Rationale, >=150 chars,
> citing E-ids), F (Evidence_IDs), H (Evidence_Ceiling) and I (Caps_Applied)**
> — see SKILL.md "Proof-Carrying Scoring". Do not add R/S/T columns to satisfy
> a check; fix the check.

# DMA Scoring Workbook Specification

## Overview

The DMA Assessment Scoring Workbook is the **single source of truth** for all assessment results. It contains 10 mandatory sheets with complete audit trail, evidence linkage, cap documentation, and reconciliation formulas. The workbook is generated BEFORE the narrative report and supersedes any conflicting report statements.

**File Naming:** `DMA_Scoring_Workbook_[INSTITUTION_NAME]_[DATE].xlsx`

**File Size Target:** 5-8 MB (indicative of full detail; <2 MB indicates missing sheets)

---

## Mandatory Sheets (11)

Sheets match the proven CFC workbook structure:
1. Executive_Summary — Overall assessment snapshot
2. Pillar_Summary — 4 pillars + Overall with weights, scores, peer medians, gaps
3. Category_Detail — 16 categories with scores, weights, peer medians, priorities
4. P1_Subcap_Scoring — ~186 subcap rows (11 columns A-K)
5. P2_Subcap_Scoring — ~232 subcap rows (11 columns A-K)
6. P3_Subcap_Scoring — ~118 subcap rows (11 columns A-K)
7. P4_Subcap_Scoring — ~172 subcap rows (11 columns A-K)
8. Evidence_Master — All evidence items with ID, Source, URL, Tier, Recency, Claim_Type, Finding
9. Peer_Benchmarks — Peer scores per category
10. Recommendations — Top recommendations with evidence linkage
11. Run_Metadata — Assessment ID, evidence mode, parameters

### Sheet 1: Summary

**Purpose:** Executive pillar-level scorecard with peer comparison

**Structure:**

| Pillar | Score | Level | Peer_Median | vs_Median | vs_P25 | vs_P75 | Trend | Evidence_Coverage_Pct | Confidence | Key_Findings |
|--------|-------|-------|-------------|-----------|--------|--------|-------|----------------------|------------|--------------|
| P1 | 3.4 | M3.4 | 3.2 | +0.2 | +0.6 | -0.2 | ↑ | 96% | HIGH | 2 strengths, 1 gap |
| P2 | 3.1 | M3.1 | 3.3 | -0.2 | +0.2 | -0.5 | → | 95% | HIGH | Onboarding ahead; engagement gap |
| P3 | 2.8 | M2.8 | 3.2 | -0.4 | -0.4 | -0.8 | ↓ | 95% | MEDIUM | Compliance gap S2 active |
| P4 | 3.3 | M3.3 | 3.0 | +0.3 | +0.7 | -0.2 | ↑ | 96% | HIGH | Data governance strong |
| **Overall** | **3.15** | **M3.15** | **3.17** | **-0.02** | **+0.33** | **-0.45** | **→** | **96%** | **HIGH** | [2-3 word summary] |

**Rows:** 5 (fixed: P1, P2, P3, P4, Overall)

**Column Definitions:**
- **Pillar:** P1, P2, P3, P4, or Overall
- **Score:** Final pillar score (0.5 precision default, 0.1 with justification)
- **Level:** Maturity level text (M1.0-M5.0)
- **Peer_Median:** Median score from user-selected peers for this pillar
- **vs_Median:** Score - Peer_Median (+ above, - below)
- **vs_P25:** Score - 25th percentile peer score
- **vs_P75:** Score - 75th percentile peer score
- **Trend:** ↑ improving, → stable, ↓ declining (vs. prior assessment if reassessment; vs. historical if available)
- **Evidence_Coverage_Pct:** Percentage of subcapabilities with non-NO_EVIDENCE scores
- **Confidence:** HIGH (≥70% coverage, ≥2 evidence tiers), MEDIUM (50-69% or single tier), LOW (<50% or only T4/T5)
- **Key_Findings:** 1-2 line summary of pillar story (not generic)

---

### Sheet 2: Calculation_Chain

**Purpose:** Complete aggregation audit trail from subcapability through overall score

**Structure (in row order):**

**Section A: Subcapability Level (851 rows at full scope)**

| SubCap_ID | SubCapability | Raw_Score | SubCap_Weight | Weighted_Value |
|-----------|---------------|-----------|---------------|-----------------|
| P1C1.1 | [Name] | 3.4 | 0.14 | 0.476 |
| P1C1.2 | [Name] | 3.5 | 0.11 | 0.385 |
| ... | ... | ... | ... | ... |

- Includes ALL subcapabilities, even those with NO_EVIDENCE (score = 1.0)
- Weight_Pct values sum to 100% for parent capability
- Weighted_Value = Raw_Score × (SubCap_Weight / 100)

**Section B: Capability Level (72 rows = 17 per pillar)**

| Cap_ID | Capability | Sum_Weighted_SubCap_Values | Cap_Weight | Capability_Score |
|--------|------------|---------------------------|------------|-----------------|
| P1C1 | Digital Strategy & Vision | 0.476 + 0.385 + ... | 0.20 | 3.42 |
| ... | ... | ... | ... | ... |

- Capability_Score = Sum_Weighted_SubCap_Values (can exceed 5.0 before capping)
- Then apply caps in separate column (see Caps_Applied_Log)

**Section C: Category Level (16 rows)**

| Category | Capabilities_in_Category | Sum_Capability_Weighted_Values | Category_Score |
|----------|-------------------------|-------------------------------|-----------------|
| P1 | C1 + C2 + C3 + C4 + C5 | Sum of weighted capability values | [Score] |
| P2 | C1 + C2 + C3 + C4 | Sum | [Score] |
| ... | ... | ... | ... |

**Section D: Pillar Level (4 rows)**

| Pillar | Categories | Sum_Category_Weighted_Values | Pillar_Weight | Pillar_Score |
|--------|-----------|------------------------------|---------------|--------------|
| P1 | P1C1...P1C5 | [Sum] | 0.25 | 3.40 |
| P2 | P2C1...P2C4 | [Sum] | 0.30 | 3.10 |
| P3 | P3C1...P3C4 | [Sum] | 0.20 | 2.80 |
| P4 | P4C1...P4C4 | [Sum] | 0.25 | 3.30 |

**Section E: Overall Score (1 row)**

| Overall | All_Pillars | Sum_Pillar_Weighted_Values | Overall_Score |
|---------|------------|---------------------------|--------------|
| Overall | P1+P2+P3+P4 | [Sum] | 3.15 |

**Formulas:**
- All calculations use SUM() and multiplication formulas (not hardcoded values)
- Weighted values calculated as: Score × (Weight / 100)
- Rows are locked in sequence: subcap → cap → cat → pillar → overall

---

### Sheet 3: P1_Subcap_Scoring

**Purpose:** Complete P1 (Strategy, Governance, Culture) subcapability scores with evidence linkage

**Row Count:** ~186 rows (range 170-200)

**Columns (A-K) — 11-column canonical format:**

| A | B | C | D | E | F | G | H | I | J | K |
|---|---|---|---|---|---|---|---|---|---|---|
| SubCap_ID | SubCap_Name | Category | Score | Confidence | Evidence_IDs | Source_URLs | Evidence_Ceiling | Caps_Applied | Rationale | Proxy_Searched |

**Column Definitions:**

- **A - SubCap_ID:** Unique subcap identifier (e.g., P1C1.1.1, P1C1.1.2). One row per subcap.
- **B - SubCap_Name:** Subcapability name from Pillar XLSX toolkit (e.g., "Digital Strategy Document", "Business Alignment")
- **C - Category:** Parent category ID (e.g., P1C1, P1C2)
- **D - Score:** Final maturity score after all caps applied (1.0-5.0, default 0.5 precision)
- **E - Confidence:** HIGH / MEDIUM / LOW based on evidence coverage and tier diversity
- **F - Evidence_IDs:** Comma-separated list (E-001, E-015, INT-BOARD-003) or NO_EVIDENCE
- **G - Source_URLs:** Hyperlinks to evidence sources (specific URLs, not "multiple searches")
- **H - Evidence_Ceiling:** Maximum score the evidence tier supports (e.g., T5-only → 2.0, T3 → 4.0)
- **I - Caps_Applied:** Description of any caps (e.g., "T5-only cap 2.0", "Severity S2 cap 3.0") or empty if none
- **J - Rationale:** ≥150 characters. Must cite E-IDs, reference M-level descriptor, explain gap to next level, institution-specific "so what"
- **K - Proxy_Searched:** "Yes" or "No" — whether proxy searches (Tiers 7-10) were attempted for this subcap

**Data Entry Rules:**

1. **Evidence_IDs (Column F):** Must follow format: `E-\d{3}` (public) or `INT-[DOC_ABBREV]-\d{3}` (internal)
   - Example: `E-001, INT-BOARD-002, E-015`
   - If NO_EVIDENCE, type "NO_EVIDENCE" (triggers conservative baseline score)

2. **Rationale (Column J) Template:**
   ```
   "[SubCapability] assessed at M[X] based on [Evidence_ID] evidence showing
   [specific finding]. Meets M[X] indicator: [M[X] descriptor from toolkit].
   Differs from M[X+1] by [gap]. For [INSTITUTION], this means [so what]."

   Examples:

   GOOD:
   "P1C1.1.1 Digital Strategy Document assessed at M2.5 based on E-020, E-021
   showing CDO Joseph Paulraj appointed Dec 2024 with 3-year digital roadmap
   including cloud migration, AI integration, and low-code platform development.
   Meets M2 indicator: 'documented strategy with executive accountability.'
   Exceeds M2 toward M3 with named initiatives. Differs from M3 by lacking
   defined KPIs with quarterly tracking cadence. For Capital Farm Credit, this
   means strategic direction exists but execution measurement is unproven.
   [287 chars, E-IDs cited, M-level referenced, institution-specific so what]"

   BAD:
   "Good strategy in place, board approved, looks solid. [50 chars, no evidence,
   no M-level, no so what]"
   ```

3. **Score (Column D) Precision Rules:**
   - **Default:** 0.5 precision (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
   - **If 0.1 precision used:** Rationale MUST contain quantified breakdown

4. **Confidence (Column E) Logic:**
   - **HIGH:** ≥2 evidence tiers AND ≥70% subcaps in capability have evidence
   - **MEDIUM:** 1-2 tiers OR 50-69% coverage
   - **LOW:** Single tier only (T5, T4) OR <50% coverage

---

### Sheet 4: P2_Subcap_Scoring

**Purpose:** Complete P2 (Member/Customer Experience) subcapability scores

**Row Count:** ~232 rows (range 210-250)

**Columns:** Same 11 columns (A-K) as P1_Subcap_Scoring

**Special Rules for P2:**

- **Sentiment Caps Apply:** If app_rating (from Evidence_Master) is <3.0, cap entire P2 at 2.0; if 3.0-3.5, cap at 2.5, etc. (see cap matrix in SKILL.md)
- **Complaint Trend:** Document complaint trajectory (increasing >20% YoY = -0.3 additional discount)
- **Diagnostic Questions:** Focused on member journey (acquisition, onboarding, servicing, engagement, personalization)

---

### Sheet 5: P3_Subcap_Scoring

**Purpose:** Complete P3 (Operations, Risk, Compliance) subcapability scores

**Row Count:** ~118 rows (range 105-135)

**Columns:** Same 11 columns (A-K) as P1_Subcap_Scoring

**Special Rules for P3:**

- **Compliance & Enforcement:** Issue_Register mapped to affected P3 subcaps with severity caps (S3/S2/S1)
- **Complaint Management:** P3C2 (Operational Risk & Fraud) links to complaint trends from P2 evidence
- **Regulatory History:** Document outstanding MRAs, enforcement actions, remediation status

---

### Sheet 6: P4_Subcap_Scoring

**Purpose:** Complete P4 (Data, Analytics, Technology) subcapability scores

**Row Count:** ~172 rows (range 155-190)

**Columns:** Same 11 columns (A-K) as P1_Subcap_Scoring

**Special Rules for P4:**

- **Cybersecurity & Breach History:** P4C4 (Information Security) capped at 2.0 if breach <12 months, 3.0 if <24 months (per cap matrix)
- **Architecture & Integration:** P4C3 evidence from vendor assessments, RFP responses, technical audits
- **Data Quality:** KPIs from data management tools, data lineage documentation

---

### Sheet 7: Evidence_Master

**Purpose:** All evidence items used in the assessment with tier, recency, and subcap mappings

**Row Count:** Varies (number of unique evidence items)

**Columns:**

| Evidence_ID | Source_Name | URL_or_Citation | Tier | ERS_Score | Date_Published | Date_Accessed | Recency_Weight | Subcaps_Supported | Fact_Summary | Contradiction_Flags |
|-------------|------------|-----------------|------|-----------|-----------------|----------------|-----------------|-------------------|--------------|-------------------|
| E-001 | CFPB Complaint Database | [URL] | T1 | 4.2 | trailing 24mo | [DATE] | 5.0 | P3C2.1, P3C2.3, P2C3.2 | High complaint volume in deposit services (120 complaints, YoY increase 15%) | Contradicts internal NPS at +42 |
| INT-BOARD-001 | Board Minutes, Digital Strategy Session | internal | T2 | 4.5 | [DATE 6mo ago] | [DATE] | 4.0 | P1C1.1, P1C1.2, P1C3.2 | Board approved 3-year digital roadmap w/ $500M funding and quarterly accountability | None |
| E-007 | J.D. Power Digital Banking Study | [URL] | T3 | 3.1 | annual 2026 | [DATE] | 4.5 | P2C1.3, P2C2.1 | Ranked 4th in digital onboarding speed (22 min vs. 28 min industry avg) | None |

**Column Definitions:**

- **Evidence_ID:** Unique identifier (E-XXX for external, INT-[ABBREV]-XXX for internal)
- **Source_Name:** Human-readable source name
- **URL_or_Citation:** Hyperlink (if public) or "internal: [document name]"
- **Tier:** T1/T2/T3/T4/T5 per evidence tier system
- **ERS_Score:** Evidence Ranking System score (1.0-5.0, from skill's ERS formula)
- **Date_Published:** When source was published
- **Date_Accessed:** When assessor accessed/extracted evidence
- **Recency_Weight:** ERS recency component (5.0=current year, 4.0=prior year, 3.0=2yr ago, 2.0=3yr, 1.0=4+yr)
- **Subcaps_Supported:** Comma-separated subcap IDs (e.g., "P1C1.1, P1C1.2")
- **Fact_Summary:** 1-2 line summary of key finding from source
- **Contradiction_Flags:** References to Contradiction_Log entries (if evidence contradicts other sources)

---

### Sheet 8: Caps_Applied_Log

**Purpose:** Audit trail of every cap applied during scoring with justification

**Row Count:** Varies (number of caps applied)

**Columns:**

| Cap_ID | Cap_Type | Trigger_Reason | Affected_SubCap_ID | Affected_Capability | Raw_Score | Cap_Ceiling | Final_Score | Score_Delta | Severity_Classification | Evidence_of_Trigger | Applied_Phase |
|--------|----------|-----------------|-------------------|-------------------|-----------|------------|------------|------------|----------------------|-------------------|--------------|
| CAP-001 | SEVERITY_S2 | Consent order, CFPB, 2024 | P3C3.1, P3C3.2, P3C3.3 | P3C3 Compliance | 3.8 | 3.0 | 3.0 | -0.8 | Material | E-001 (CFPB Orders) | Phase 4 Step 7 |
| CAP-002 | EVIDENCE_T5_ONLY | Marketing claims only, no T1-T3 corroboration | P2C4.1 | P2C4 Personalization | 2.8 | 2.0 | 2.0 | -0.8 | High | E-005 (website claim) | Phase 4 Step 7 |
| CAP-003 | SENTIMENT_P2 | App rating 2.8 | P2C1, P2C2, P2C3 | P2 all | 3.2 | 2.5 | 2.5 | -0.7 | High | E-007 (app store rating) | Phase 4 Step 7 |
| CAP-004 | CROSS_PILLAR_DEP | P3C3 < 2.5 triggers P2C2 cap | P2C2.1, P2C2.2 | P2C2 Onboarding | 3.4 | 3.0 | 3.0 | -0.4 | Dependency | P3C3 score: 2.3 | Phase 4 Step 8 |

**Column Definitions:**

- **Cap_ID:** Unique cap identifier (CAP-001, CAP-002, etc.)
- **Cap_Type:** SEVERITY_S3 / SEVERITY_S2 / SEVERITY_S1 / EVIDENCE_T5_ONLY / EVIDENCE_SINGLE_SOURCE / SENTIMENT_P2 / CROSS_PILLAR_DEP / STALE_DATA
- **Trigger_Reason:** Specific reason for cap (e.g., "Active enforcement order <12 months", "T5 marketing claims only")
- **Affected_SubCap_ID:** Which subcapability(ies) capped (comma-separated)
- **Affected_Capability:** Parent capability
- **Raw_Score:** Score before cap
- **Cap_Ceiling:** Maximum allowed score
- **Final_Score:** Score after cap (must be ≤ cap_ceiling)
- **Score_Delta:** Raw - Final (negative number)
- **Severity_Classification:** CRITICAL / MATERIAL / MINOR (from issue register if applicable)
- **Evidence_of_Trigger:** Reference to evidence (E-XXX or capability ID) that triggered cap
- **Applied_Phase:** When cap was applied (Phase 4 Step 7 for severity/evidence/sentiment; Phase 4 Step 8 for cross-pillar)

**Validation Rule:** For every row, verify: Raw_Score > Cap_Ceiling (if cap was applied, raw score should have exceeded ceiling)

---

### Sheet 9: Absent_Evidence_Log

**Purpose:** Document all subcapabilities where evidence is missing or insufficient, and impact on scoring

**Row Count:** Varies (number of NO_EVIDENCE or LOW-confidence scores)

**Columns:**

| SubCap_ID | Subcapability | Search_Attempts | Evidence_Search_Strategy | Why_No_Evidence | Impact_on_Capability_Score | Score_Applied | Confidence_Level | Next_Steps |
|-----------|---------------|-----------------|-------------------------|-----------------|----------------------------|-----------------|-----------------|-----------|
| P4C2.3 | Predictive Analytics Deployment | A1, A5, web search, vendor assessment | Searched: job postings, press releases, board presentations, vendor tool websites | No public evidence of predictive models; internal docs not available; vendor assessment pending | P4C2 could not be evaluated if >30% subcaps NO_EVIDENCE; 4/8 subcaps have evidence → capability evaluated | 1.0 (NO_EVIDENCE) | LOW | Request internal data governance roadmap in Phase 2 conversation |
| P1C3.4 | Venture Capital / Fintech Partnerships | A1, A7, web search | Searched: press releases, investor relations, fintech partnerships announcements | No active partnerships disclosed; assessment is >18 months old | P1C3 aggregate reduced by ~0.3; partnership gap vs. peers | 1.5 (inferred dormancy) | LOW | Recommend direct question to institution about innovation strategy |

**Column Definitions:**

- **SubCap_ID:** Subcapability with missing evidence
- **Subcapability:** Full name
- **Search_Attempts:** Where assessor looked (A1=research package, A5=issue register, web, vendor, internal, etc.)
- **Evidence_Search_Strategy:** Specific search terms, databases, or contacts used
- **Why_No_Evidence:** Root cause (not publicly disclosed, too confidential, no vendor data available, assessment too old, institution too small for coverage, etc.)
- **Impact_on_Capability_Score:** How missing evidence affected parent capability (e.g., "reduced median by 0.3 points")
- **Score_Applied:** What score was used (1.0 for NO_EVIDENCE, or 1.5+ for inferred scores with heavy caveats)
- **Confidence_Level:** HIGH / MEDIUM / LOW
- **Next_Steps:** Recommended action to fill gap in reassessment (direct question, vendor RFP, etc.)

---

### Sheet 10: QA_Validation_Log

**Purpose:** Document Phase 8 QA testing results for all regression tests and safeguard layers

**Row Count:** Varies (number of QA checks)

**Columns:**

| Check_ID | Check_Name | Phase_Applicable | Check_Type | Status | Details | Failure_Actions_Taken | Result_Summary |
|----------|-----------|-----------------|-----------|--------|---------|----------------------|-----------------|
| REG-001 | Row Count Validation | Phase 8 | Regression | PASS | P1: 203 (target ±5%), P2: 291, P3: 164, P4: 189, Total: 847 | N/A | All sheets within tolerance |
| REG-002 | Rationale Quality | Phase 8 | Regression | PASS | 80/80 spot-check pass (20 per pillar): all ≥150 chars, evidence cited, M[X] descriptor present | N/A | Spot-check passed |
| INP_01 | Document Inventory Complete | Phase 1 | Input Validation | PASS | All 18 documents in /mnt/user-data/uploads/ inventoried and readable | N/A | Inventory complete |
| INP_05 | Toolkit Binding Verified | Phase 1 | Input Validation | PASS | Zennify Credit Union Maturity Model v4.0 bound, Pillar scoring toolkits loaded | N/A | Correct toolkit verified |
| SCR_01 | Subcap Count Validation | Phase 4 | Scoring | PASS | 847 subcaps scored (target 851 ±5%) | N/A | Row count within tolerance |
| SCR_05 | Caps Applied Correctly | Phase 4 | Scoring | PASS | 23 caps applied, all documented in Caps_Applied_Log, raw_score > cap_ceiling verified | N/A | All caps verified |
| OUT_05 | No Generic Statements | Phase 7 | Output | WARNING | One instance: "Strong governance structure" in P1C2 narrative (should be "governance structure demonstrating documented risk oversight per [evidence]") | Corrected narrative | 1 generic phrase rewritten |
| WB_07 | Entity Folder Saved | Phase 8 | Workbook | PASS | Workbook saved to /home/claude/dma_assessments/[ENTITY]_DMA/outputs/ and /mnt/user-data/outputs/ | N/A | Both locations verified |

**Column Definitions:**

- **Check_ID:** Unique check identifier (REG-001, INP_01, SCR_05, OUT_05, etc.)
- **Check_Name:** Human-readable name
- **Phase_Applicable:** Which phase this check runs in
- **Check_Type:** Regression / Input_Validation / Document_Processing / Analytical / Scoring / Output / Consistency / Workbook / Final_Quality
- **Status:** PASS / WARNING / CRITICAL_FAIL
- **Details:** Specific findings from the check
- **Failure_Actions_Taken:** If warning/fail, what was done to remediate
- **Result_Summary:** 1-line summary of overall check result

**Final Gate:** Assessment is marked COMPLETE only when all checks show PASS status (or WARNING with documented caveat and remediation).

---

## Workbook Generation Workflow

1. **After Phase 4 Scoring Complete:**
   - Extract all subcapability scores from scoring decisions
   - Populate P1-P4_Scoring_Detail sheets (rows in order, no sorting)
   - Build Calculation_Chain with full aggregation formulas
   - Generate Summary sheet from Calculation_Chain
   - Create Caps_Applied_Log and Absent_Evidence_Log

2. **After Phase 2 Peer Analysis:**
   - Populate Summary sheet peer comparison columns (Peer_Median, vs_Median, etc.)
   - Update Confidence levels based on evidence coverage

3. **Before Phase 8 QA:**
   - Finalize all sheets
   - Run automated validation (row count, formula checks, etc.)
   - Lock workbook structure (no further additions to subcapability rows)

4. **During Phase 8 QA:**
   - Run all 8 regression tests
   - Document results in QA_Validation_Log
   - Remediate any failures
   - Save final workbook to entity folder AND /mnt/user-data/outputs/

---

## Formatting & Presentation Rules

### Column Widths & Alignment

- **Column A-B:** 12 characters (Category_ID, Category_Name)
- **Column C-F:** 15 characters (Cap_ID, Capability, SubCap_ID, SubCapability)
- **Column G-H:** 30 characters (Tier, Diagnostic_Question) — wrap text enabled
- **Column I-J:** 12 characters (Weight_Pct, Score)
- **Column K-L:** 25 characters (Evidence_IDs, Evidence_URLs)
- **Column R:** 50+ characters (Scoring_Rationale) — wrap text enabled
- **Column U:** 60+ characters (Evidence_Excerpt) — wrap text enabled. This is the "show your work" column.
- **Column V:** 30+ characters (Source_Document) — wrap text enabled
- **Number Format:** Scores with 0.0 decimal places; weights with 0.0% format; ERS scores with 0.1 decimal

### Conditional Formatting

- **Score Column (J):** Green if 3.0+, yellow if 2.0-2.9, red if <2.0
- **Final_Score Column (P):** Gray background if caps applied (Caps_Applied = YES)
- **Confidence Column (N):** Green = HIGH, yellow = MEDIUM, red = LOW
- **Score_Delta (Cap Sheet):** Red text for any delta

### Freeze Panes

- **P1-P4_Scoring_Detail sheets:** Freeze row 1 (headers) and columns A-F (subcap IDs)
- **Calculation_Chain:** Freeze row 1 and columns A-C
- **Evidence_Linkage_Matrix:** Freeze row 1

### Data Validation

- **Score columns:** Allow only values 1.0-5.0 in 0.1 increments
- **Confidence:** Dropdown list (HIGH / MEDIUM / LOW)
- **Cap_Type:** Dropdown list (values from cap taxonomy)
- **Evidence_Tier:** Dropdown (T1 / T2 / T3 / T4 / T5 / NO_EVIDENCE)

---

## Formula Examples

### Capability Score Aggregation (Calculation_Chain Sheet)

```
Capability_Score = SUMPRODUCT(subcap_scores_array, subcap_weights_array) / SUM(subcap_weights_array)

Example (P1C1 with 5 subcaps):
= (3.4×14% + 3.5×11% + 3.0×12% + 3.2×15% + 3.1×14%) / 100%
= (0.476 + 0.385 + 0.360 + 0.480 + 0.434) / 1.0
= 2.135 / 1.0
= 2.135 → rounded to 3.2 (0.5 precision)
```

### Pillar Score Aggregation

```
Pillar_Score = SUMPRODUCT(capability_scores_array, capability_weights_array)

Example (P1 with 5 capabilities):
= 3.2×20% + 3.5×20% + 3.1×20% + 3.4×20% + 2.9×20%
= 0.64 + 0.70 + 0.62 + 0.68 + 0.58
= 3.22 → rounded to 3.2
```

### Overall Score Aggregation

```
Overall_Score = SUMPRODUCT(pillar_scores_array, pillar_weights_array)

Example (4 pillars with sub-vertical weights):
= P1_score × 0.25 + P2_score × 0.30 + P3_score × 0.20 + P4_score × 0.25
= 3.4×0.25 + 3.1×0.30 + 2.8×0.20 + 3.3×0.25
= 0.85 + 0.93 + 0.56 + 0.825
= 3.155 → rounded to 3.2
```

---

## Error Prevention Checklist

Before finalizing workbook:

- [ ] All P1-P4_Scoring_Detail sheets have row counts within ±5% of targets
- [ ] No blank Score_1_to_5 cells (use 1.0 for NO_EVIDENCE)
- [ ] All scores ≤ 5.0 (before capping)
- [ ] All weight percentages sum to 100% per capability
- [ ] Calculation_Chain has full aggregation trail (subcap → cap → cat → pillar → overall)
- [ ] Summary sheet scores match Calculation_Chain derived scores (±0.01 tolerance)
- [ ] Caps_Applied_Log has entry for every YES in Caps_Applied column
- [ ] Evidence_IDs in P1-P4 sheets exist in Evidence_Linkage_Matrix
- [ ] All rationales ≥150 characters with evidence ID and M[X] descriptor
- [ ] QA_Validation_Log documented with all regression test results
- [ ] File saved to both entity folder AND /mnt/user-data/outputs/
