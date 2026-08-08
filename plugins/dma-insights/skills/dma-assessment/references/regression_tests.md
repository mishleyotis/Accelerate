# Regression Test Suite — Phase 8 QA Validation

## Overview

This test suite contains 8 golden regression tests that validate the assessment workbook and narrative against the DMA skill's core requirements. Each test is executed during Phase 8 QA (Final Quality Assurance) before the assessment is delivered to the client.

**Test Execution Rule:** All tests run in sequence. A CRITICAL failure stops the assessment; a WARNING allows conditional delivery with documented caveat.

---

## TEST 1: Row Count Validation

**Test ID:** REG-001
**Name:** Subcapability Row Count Audit
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that the scoring_detail sheets (P1, P2, P3, P4) contain the correct number of subcapability rows. The DMA model defines a fixed subcapability taxonomy:

- **P1_Scoring_Detail sheet:** ~199 rows (±5%, range 189-209)
- **P2_Scoring_Detail sheet:** ~288 rows (±5%, range 273-303)
- **P3_Scoring_Detail sheet:** ~162 rows (±5%, range 154-170)
- **P4_Scoring_Detail sheet:** ~187 rows (±5%, range 178-196)
- **Total across all pillars:** ~836 rows

### Pass/Fail Criteria

**PASS:** All four sheets have row counts within ±5% of target.

```
✓ P1 rows: [actual_count] (target 199 ± 5%)
✓ P2 rows: [actual_count] (target 288 ± 5%)
✓ P3 rows: [actual_count] (target 162 ± 5%)
✓ P4 rows: [actual_count] (target 187 ± 5%)
✓ Total: [actual_total] (target 836 ± 5%)
```

**WARNING:** One sheet is within ±7.5% (e.g., P2 has 310 rows = 7.6% over).

**CRITICAL FAIL:** Any sheet is outside ±7.5% or has <750 total rows across all pillars.

### Failure Recovery

If CRITICAL FAIL:
1. Load the Pillar Scoring Toolkit XLSX
2. Manually count subcapabilities per pillar from the toolkit
3. Identify missing or duplicate SubCap_ID rows in scoring_detail sheets
4. Re-map evidence and re-score missing subcaps
5. Re-run test

### Test Example Output

```
REG-001: Row Count Validation
[PASS] P1_Scoring_Detail: 203 rows (target 199 ± 10)
[PASS] P2_Scoring_Detail: 291 rows (target 288 ± 14)
[PASS] P3_Scoring_Detail: 164 rows (target 162 ± 8)
[PASS] P4_Scoring_Detail: 189 rows (target 187 ± 9)
[PASS] Total: 847 rows (target 836 ± 42)
RESULT: PASS
```

---

## TEST 2: Rationale Quality Audit

**Test ID:** REG-002
**Name:** Scoring Rationale Quality Validation
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that every subcapability score in the scoring_detail sheets has a high-quality rationale meeting four criteria:

1. **Length:** ≥150 characters (substantial reasoning, not comments)
2. **Evidence Citation:** Contains at least one Evidence_ID reference (E-XXX or INT-XXX-NNN)
3. **Maturity Descriptor:** References the M1-M5 level used to justify the score (e.g., "meets M2 indicator" not just "good")
4. **No Forbidden Patterns:** Does not contain generic phrases from communication_standards.md forbidden list

### Pass/Fail Criteria

**PASS:** All scored rows (excluding NO_EVIDENCE) meet all 4 criteria. Spot-check minimum 20 rows per pillar (80 total across all pillars).

**CRITICAL FAIL:** >10% of rationales fail any criterion.

**WARNING:** 5-10% of rationales fail one criterion.

### Validation Rules

- **Minimum character count:** Count actual rationale_text length (excluding citations in parentheses)
- **Evidence citation format:** Match pattern `[E-\d+|INT-[A-Z]+-\d+]` — at least one match required
- **Maturity descriptor:** Match M1, M2, M3, M4, or M5 (e.g., "M2 indicator", "meets M3", "M4-level", "approaching M2")
- **Forbidden phrase check:** Grep against all phrases in FORBIDDEN list from communication_standards.md

### Spot-Check Sampling Logic

```
Sample size = ceiling(total_rows * 0.02) with minimum 20 per pillar
Sampling method = stratified: select every Nth row where N = total_rows / sample_size
Example: P2 has 291 rows → sample 6 rows → select rows 5, 54, 103, 152, 201, 250
```

### Good Rationale Example (PASS)

```
"P2C3 assessed at M3 based on omnichannel servicing evidence (E-001: digital
channels operational, E-009: omnichannel oversight documented) demonstrating
documented cross-channel coordination with measured performance KPIs. Differs
from M4 by lacking proactive member experience design and predictive routing
across channels. [179 chars, 2 evidence IDs, M3 descriptor, no forbidden phrases]"
```

### Bad Rationale Example (FAIL)

```
"Strong omnichannel support in place. App integration good. Member feedback
positive overall. [65 chars, 0 evidence IDs, no M-level, 'strong' is generic]"
```

### Test Example Output

```
REG-002: Rationale Quality Audit
Spot-check sample: 80 rows (20 per pillar)
[PASS] Length ≥150 chars: 79/80 (98.75%)
[PASS] Evidence_ID cited: 80/80 (100%)
[PASS] M[X] descriptor: 80/80 (100%)
[PASS] No forbidden patterns: 80/80 (100%)
RESULT: PASS
```

---

## TEST 3: Evidence Coverage Audit

**Test ID:** REG-003
**Name:** Evidence Coverage & Linkage Validation
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that scored subcapabilities have evidence linkage and that coverage is sufficient across the assessment. Tests two aspects:

1. **Individual Subcap Coverage:** Each non-NO_EVIDENCE score has at least one evidence_ID reference
2. **Pillar-Level Coverage:** ≥70% of subcapabilities per pillar have non-NO_EVIDENCE evidence

### Pass/Fail Criteria

**PASS:**
- 100% of scored rows (excluding NO_EVIDENCE rows) have evidence_ID references
- ≥70% of total rows per pillar have non-NO_EVIDENCE scores
- Evidence_Linkage_Matrix sheet references all evidence_IDs used in scoring

**WARNING:**
- 65-69% coverage on any pillar

**CRITICAL FAIL:**
- <65% coverage on any pillar
- Any non-NO_EVIDENCE score lacks evidence_ID reference

### Calculation Logic

```
Coverage_Pct = (non_NO_EVIDENCE_rows / total_rows) × 100%

P1 coverage = X / 203
P2 coverage = Y / 291
P3 coverage = Z / 164
P4 coverage = W / 189
```

### Test Example Output

```
REG-003: Evidence Coverage Audit
[PASS] P1 coverage: 195/203 (96%)
[PASS] P2 coverage: 275/291 (95%)
[PASS] P3 coverage: 155/164 (95%)
[PASS] P4 coverage: 182/189 (96%)
[PASS] All non-NO_EVIDENCE rows have evidence_ID
RESULT: PASS
```

---

## TEST 4: Aggregation Reconciliation

**Test ID:** REG-004
**Name:** Calculation Chain Integrity & Reconciliation
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that the aggregation chain (Subcap → Capability → Category → Pillar → Overall) is mathematically correct and fully traceable. Tests three aspects:

1. **Formula Correctness:** Subcap weighted averages = capability scores (±0.01 tolerance)
2. **Multi-Level Consistency:** Capability aggregation, category aggregation, pillar aggregation all correct
3. **Sheet Alignment:** Summary sheet scores match Calculation_Chain derived scores

### Pass/Fail Criteria

**PASS:**
- All capability scores = sum(subcap_score × subcap_weight) with ±0.01 tolerance
- All category scores = sum(capability_score × capability_weight) with ±0.01 tolerance
- All pillar scores = sum(category_score × category_weight) with ±0.01 tolerance
- Overall score = sum(pillar_score × pillar_weight) with ±0.01 tolerance
- Summary sheet scores match Calculation_Chain sheet derived scores exactly
- Calculation_Chain sheet has full row documentation (subcap → capability → category → pillar → overall)

**WARNING:**
- One or two calculations out of tolerance by 0.02-0.05 (likely rounding artifact)

**CRITICAL FAIL:**
- >2 calculations out of tolerance
- Calculation_Chain sheet is missing intermediate rows (e.g., jumps from subcap to pillar, skipping capability)
- Summary scores differ from derived scores by >0.1

### Verification Method

For each capability C in P1:
```
expected_score = sum(subcap_score × subcap_weight for all subcaps in C)
actual_score = capability_score in Calculation_Chain
tolerance = 0.01
pass = abs(expected_score - actual_score) <= tolerance
```

Repeat for capability→category, category→pillar, pillar→overall.

### Test Example Output

```
REG-004: Aggregation Reconciliation
Subcap→Capability verification: 72 capabilities tested, 72 within ±0.01
[PASS] Capability level aggregation correct
Category→Pillar verification: 16 category sums tested, 16 within ±0.01
[PASS] Category level aggregation correct
Pillar→Overall verification: 4 pillar sums tested, 4 within ±0.01
[PASS] Pillar level aggregation correct
Summary sheet scores match Calculation_Chain: [PASS]
RESULT: PASS
```

---

## TEST 5: Cap Enforcement & Logging

**Test ID:** REG-005
**Name:** Caps Applied Log Completeness & Accuracy
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that every cap applied during scoring is:
1. Documented in the Caps_Applied_Log sheet
2. Correctly applied (raw_score reduced to cap_ceiling or lower)
3. Not over-applied (cap_ceiling is at or above highest evidence tier available)

Tests two aspects:

1. **Completeness:** All caps used in scoring are logged
2. **Accuracy:** Each capped score shows raw_score > cap_ceiling, proving the cap was needed

### Pass/Fail Criteria

**PASS:**
- Every row in scoring_detail sheets with Caps_Applied field "YES" is documented in Caps_Applied_Log sheet
- Every logged cap shows: raw_score > cap_ceiling (proving cap was enforced)
- No duplicate cap entries (same subcap capped twice)
- All cap types (SEVERITY, EVIDENCE, SENTIMENT, CROSS_PILLAR) are represented

**WARNING:**
- One or two caps are missing from log (but still applied correctly in scores)

**CRITICAL FAIL:**
- >2 caps missing from log
- Caps_Applied_Log shows cap applied but actual score doesn't reflect it (e.g., raw_score 4.0, cap_ceiling 2.0, but final_score is 4.0)
- Caps_Applied field left blank for rows that should be capped

### Cap Type Verification

For each logged cap, validate the trigger:

```
SEVERITY cap (S3/S2/S1): Verify issue exists in Issue_Register
EVIDENCE cap (T5, single_source, etc.): Verify evidence_tier in scored row matches cap trigger
SENTIMENT cap (P2 only): Verify app_rating in Evidence_Index is below threshold
CROSS_PILLAR cap: Verify dependency basis exists (e.g., "P1C2 < 2.5" → check P1C2 score)
```

### Test Example Output

```
REG-005: Cap Enforcement & Logging
Total capped subcaps: 23
Documented in Caps_Applied_Log: 23 [PASS]
Raw score > cap ceiling (proof of enforcement): 23/23 [PASS]
No duplicate caps: [PASS]
Cap types represented:
  - SEVERITY: 5 caps (3 S2, 2 S1) [PASS]
  - EVIDENCE: 12 caps (8 T5_only, 4 single_source) [PASS]
  - SENTIMENT: 4 caps (P2C2, P2C3, P2C4, P2C1) [PASS]
  - CROSS_PILLAR: 2 caps [PASS]
RESULT: PASS
```

---

## TEST 6: Adjustment-Ceiling Traceability

**Test ID:** REG-006
**Name:** ADJ_ Prefixed Entries & Proof Formulas
**Phase:** Phase 8 (Final)
**Severity:** MEDIUM
**Run Frequency:** Every assessment with adjustments

### What It Checks

Validates that any adjusted scores (prefixed with ADJ_ in Scoring_Rationale or Proof_Claims) have documented formulas showing how the adjustment was derived. This prevents "magic number" scores.

### Pass/Fail Criteria

**PASS:**
- All rows with "ADJ_" prefix in Scoring_Rationale have formula in Proof_Claims column
- Formula is quantitative (not "professional judgment")
- Formula is verifiable by cross-referencing to other evidence

**WARNING:**
- One or two ADJ_ entries lack complete formula documentation

**CRITICAL FAIL:**
- Multiple ADJ_ entries without formulas
- Formula is circular or non-verifiable

### Formula Documentation Template

```
ADJ_[REASON]_[FORMULA]

Examples:
"ADJ_Sentiment_Upweight: (M2_base_score 2.4 + sentiment_lift 0.3 = 2.7, capped at evidence ceiling 3.0 = 3.0)"
"ADJ_Prior_Reassessment: (prior_score 2.8 + new_evidence_impact +0.5 = 3.3, verified against baseline)"
"ADJ_Exception_Override: (standard_evidence_would_suggest 2.5, but regulatory_mandate_forces M3 minimum = 3.0, CEO governance review required per P1C2)"
```

### Test Example Output

```
REG-006: Adjustment-Ceiling Traceability
ADJ_ entries found: 3
  Entry 1: "ADJ_Sentiment_Upweight" → Formula present [PASS]
  Entry 2: "ADJ_Prior_Upweight" → Formula present [PASS]
  Entry 3: "ADJ_Exception_P1C2" → Formula present [PASS]
All formulas verifiable: [PASS]
RESULT: PASS
```

---

## TEST 7: Dependency Cap Propagation

**Test ID:** REG-007
**Name:** Cross-Pillar Dependency Caps Applied in Pass 2
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that cross-pillar dependency caps (e.g., "if P1C2 < 2.5, cap all P3 capabilities at 3.0") are:
1. Only applied AFTER all pillars are initially scored (Pass 2 of scoring)
2. Correctly cascade to affected subcapabilities
3. Documented with dependency reason (not standalone severity)

### Pass/Fail Criteria

**PASS:**
- All cross-pillar dependency caps are logged with "dependency" type and basis (e.g., "P1C2 < 2.5 triggers P3 cap")
- Every affected subcapability in P3 (when P1C2 < 2.5) is capped or already below cap
- Caps Applied Log shows date/phase = Phase 4 Step 8 (after pillar aggregation)

**WARNING:**
- One dependency cap applied at wrong phase but final scores are correct

**CRITICAL FAIL:**
- Dependency cap applied in Phase 4 Step 7 (before all pillars scored) → inconsistent application
- Dependency cap triggered but not applied to all affected subcaps
- Dependency logic is circular (A caps B, B caps A)

### Dependency Rules (from skill specification)

```
IF P1C2 Governance < 2.5   THEN cap all P3 capabilities at 3.0
IF P4C4 Cybersecurity < 2.5 THEN cap P4C1 Data Governance at 3.0
IF P3C3 Compliance < 2.5   THEN cap P2C2 Onboarding at 3.0
IF P4C1 Data Governance < 2.5 THEN cap P2C4 Personalization at 3.0
IF P4C3 Architecture < 2.5 THEN cap P3C1 Automation at 3.0
IF Disclosed Breach <12mo  THEN cap P4C4 at 2.0
IF Disclosed Breach <24mo  THEN cap P4C4 at 3.0
```

### Test Example Output

```
REG-007: Dependency Cap Propagation
Dependency checks:
  [PASS] P1C2 score: 3.2 (not < 2.5, no P3 cap triggered)
  [PASS] P4C4 score: 3.0 (not < 2.5, no P4C1 cap triggered)
  [PASS] P3C3 score: 2.3 (< 2.5, triggers P2C2 cap) → P2C2 score: 2.8 (capped at 3.0) [PASS]
  [PASS] P4C1 score: 2.6 (not < 2.5, no P2C4 cap triggered)
  [PASS] Breach history: none active, no P4C4 cap triggered
All caps applied in Pass 2 (Phase 4 Step 8): [PASS]
RESULT: PASS
```

---

## TEST 8: Report Content Integrity

**Test ID:** REG-008
**Name:** Narrative Report Score Alignment with Workbook
**Phase:** Phase 8 (Final)
**Severity:** CRITICAL
**Run Frequency:** Every assessment

### What It Checks

Validates that every quantified score statement in the narrative report matches the final workbook exactly. This prevents "narrative drift" where report says one thing and workbook another.

### Pass/Fail Criteria

**PASS:**
- All pillar scores in narrative match Summary sheet pillar scores exactly
- All capability scores in narrative match Calculation_Chain capability scores exactly
- All references to "above/below median" match peer comparison logic
- No score statements appear in narrative that don't exist in workbook

**WARNING:**
- One narrative statement refers to a score rounded to nearest 0.5 (e.g., narrative says "3.0" for workbook score 3.04) — acceptable if consistent

**CRITICAL FAIL:**
- Narrative score differs from workbook by >0.1 (indicates report written from outdated workbook)
- Narrative contains score statement with no corresponding workbook entry
- Narrative contradicts workbook logic (e.g., "low score of 3.8" when 3.8 is above median)

### Verification Method

For each numeric statement in report:

```
1. Extract score number (e.g., "P2 scored 3.5")
2. Cross-reference to workbook:
   - Pillar score: check Summary sheet
   - Capability score: check Calculation_Chain
   - Category score: check Calculation_Chain or P[X]_Scoring_Detail aggregate row
3. Verify match: workbook_score = narrative_score (±0.05 rounding tolerance)
4. If reference is "above/below median", verify vs. peer data in peers/peer_selection.json
```

### Test Example Output

```
REG-008: Report Content Integrity
Score statements found in narrative: 47
[PASS] P1 = 3.4 (Summary: 3.4) [exact match]
[PASS] P2 = 3.1 (Summary: 3.1) [exact match]
[PASS] P3 = 2.8 (Summary: 2.8) [exact match]
[PASS] P4 = 3.3 (Summary: 3.3) [exact match]
[PASS] Overall = 3.15 (Summary: 3.15) [exact match]
[PASS] "P3 below peer median" (Median: 3.2, Score: 2.8) [logic correct]
[PASS] Capability scores: 42/42 match (±0.05 tolerance)
RESULT: PASS
```

---

## Regression Test Execution Checklist

Use this checklist during Phase 8 QA:

- [ ] **REG-001:** Run row count validation (expected ±5%)
- [ ] **REG-002:** Spot-check 80 rationales (20 per pillar) for quality criteria
- [ ] **REG-003:** Calculate pillar-level coverage % (expect ≥70% per pillar)
- [ ] **REG-004:** Verify aggregation math (subcap→cap→cat→pillar→overall)
- [ ] **REG-005:** Cross-reference Caps_Applied_Log completeness vs. scoring_detail sheets
- [ ] **REG-006:** Verify ADJ_ entries have formulas documented
- [ ] **REG-007:** Check cross-pillar dependency caps applied in Pass 2
- [ ] **REG-008:** Grep narrative scores against workbook (exact match required)

---

## Test Failure Recovery Workflow

| Test | CRITICAL Failure | Recovery |
|------|-----------------|----------|
| REG-001 | Row count <750 | Reload Pillar Toolkit, identify missing subcaps, re-score |
| REG-002 | >10% rationale failures | Re-write failed rationales, re-test |
| REG-003 | Coverage <65% any pillar | Identify gaps, search for additional evidence, re-score |
| REG-004 | Aggregation errors >0.05 | Recalculate formulas, verify weights sum to 100%, re-derive |
| REG-005 | Caps not logged | Audit caps_applied_log, add missing entries with formulas |
| REG-006 | ADJ_ entries lack formula | Document formula for each ADJ_ entry |
| REG-007 | Dependency caps in Pass 1 | Re-apply all caps in Pass 2 (after pillar aggregation), re-run |
| REG-008 | Score mismatch >0.1 | Reload final workbook, re-write narrative from workbook |

---

## Test Result Documentation

All test results must be documented in the **QA_Validation_Log sheet** of the workbook with this structure:

```
| Test_ID | Test_Name | Status | Result_Summary | Failure_Details | Recovery_Action |
|---------|-----------|--------|-----------------|-----------------|-----------------|
| REG-001 | Row Count Validation | PASS | P1:203, P2:291, P3:164, P4:189 | N/A | N/A |
| REG-002 | Rationale Quality | PASS | 80/80 spot-check pass | N/A | N/A |
| ... | ... | ... | ... | ... | ... |
```

**Final Gate:** Assessment can only be marked COMPLETE when all 8 regression tests return PASS status.
