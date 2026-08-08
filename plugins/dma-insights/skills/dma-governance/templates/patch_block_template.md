# Patch Block: [Institution Name] Assessment [Date]

**Run ID:** DMA-XXXX-00000000-0000
**Assessment Skill Version:** 3.0
**Governance Audit Date:** 2024-01-16
**Patch Block Version:** 1.0

---

## Executive Summary

This patch block documents issues discovered during governance audit (Workflow A) and proposes program-level learning improvements based on findings. All proposed changes are optional enhancements to the DMA assessment methodology.

**Audit Verdict:** PASS_WITH_NOTES
**Issues Found:** 5 total (0 CRITICAL, 0 HIGH, 2 MEDIUM, 3 LOW)
**Actionable Patches:** 3

---

## Section 1: Structural Issues & Fixes

### Issue 1.1: [Issue Category] - [Brief Title]

**Original Issue:**
[Description of what was found, with example or specific reference]

**Root Cause Analysis:**
[Why did this issue occur? What gap in methodology or rubric allowed it?]

**Proposed Fix:**
[Specific action to prevent recurrence]

**Implementation Location:**
- File: `references/[reference_file].md` or `capability_criteria.md` (for rubric clarification)
- Section/Line: [Specific location in skill documentation]

**Impact:** Affects ~2-5% of assessments (similar institutions/sub-verticals)

**Priority:** MEDIUM

---

## Section 2: Rubric Clarification Proposals

### Proposal 2.1: Evidence Linking Standard — Add Proof-Carrying Requirement

**Current State:**
Evidence linkage is documented in communication_standards.md, but proof structure (Claims-Evidence-Rules-Counterclaim) is not formalized in scoring_methodology.md.

**Problem:**
Scorer [Name] omitted rule links in P1C2 rationale due to unclear requirement. This increases variation across assessments.

**Proposed Wording:**
Add to `references/scoring_methodology.md`, Section "Rationale Structure":

> **Required Proof Elements for Every Subcapability Score:**
>
> 1. **Claims (C1–C3):** Explicit factual assertions (min. 3 distinct claims supporting the score)
> 2. **Evidence Links:** Inline citations to Evidence_Index (format: E#:F#)
> 3. **Rule Links:** Reference to applicable scoring rule (format: RuleID from capability_criteria.md)
> 4. **Counterclaim Check:** Documented anticipation of opposing interpretation
> 5. **Constraint Verification:** Note any caps applied or dependencies respected
>
> All rationales must pass the following validation:
> - Are Claims grounded in specific, cited Evidence?
> - Do Claims align with the referenced Rule?
> - Has a reasonable counterargument been addressed?

**Golden Cases to Test:**
- Case A (Sparse evidence) should still score M1-M2 with valid proof structure
- Case E (Proof-carrying compliance) should PASS all proof checks

**Impact:** Increases consistency; raises bar for rationale quality; ~10% of assessments will require re-scoring

**Timeline:** Implement in next assessment skill version (v3.1)

---

### Proposal 2.2: Distributional Check Sensitivity — Cap Distribution Threshold

**Current State:**
DIST-004 flagged cap application rate of 28% as suspicious.

**Problem:**
28% cap rate may be legitimate for early-stage institutions with limited evidence (PUBLIC mode), but current threshold (30%) doesn't differentiate by evidence_mode or size_tier.

**Proposed Wording:**
Update `references/distributional_checks.md` with sensitivity by context:

> **Cap Distribution Thresholds:**
> - PUBLIC mode: Threshold = 35% (acceptable given source limitations)
> - INTERNAL mode: Threshold = 25% (full evidence available; high caps suggest methodology issue)
> - HYBRID mode: Threshold = 30%
>
> Also threshold by size tier: Smaller institutions (<$500M) may have fewer measured KPIs → adjust threshold +5%

**Implementation:**
Modify `qa_auditor.py` (if used) or governance audit Step 5 logic to apply context-aware thresholds.

**Impact:** Reduces false-positive DIST flags; improves calibration reliability

**Timeline:** Implement in governance skill v2.1

---

## Section 3: Regression Test Enhancements

### Regression Test 3.1: Golden Case F — Critic Pass Effectiveness

**Current Status:** Not yet formalized

**Proposal:**
Add Case F to golden test cases (reference `templates/golden_cases/case_f_critic_pass.json`):

- **Purpose:** Verify Critic_Log consumption and CR-01 checks work correctly
- **Test Data:** Includes 8 sample critic findings (mix of: valid concerns, edge-case concerns, invalid concerns)
- **Expected Behavior:**
  - All valid findings → must be addressed or accepted with documented rationale
  - Edge-case findings → may be deferred with explanation
  - Invalid findings → marked INVALID with justification
- **Pass Criteria:** ≥95% of critic findings have status ADDRESSED, ACCEPTED_WITH_RATIONALE, or INVALID

**Implementation Location:**
- Golden case JSON: `templates/golden_cases/case_f_critic_pass.json`
- Test runner: `references/regression_suite.md`, Golden Cases section

**Impact:** Ensures Critic_Log integration is working as designed

**Timeline:** Implement in governance skill v2.0 (current)

---

### Regression Test 3.2: Golden Case E — Proof-Carrying Compliance

**Current Status:** Not yet formalized

**Proposal:**
Add Case E to golden test cases (reference `templates/golden_cases/case_e_proof_carrying.json`):

- **Purpose:** Verify proof structure validation (PV-01, PV-02, PV-03 checks)
- **Test Data:** Includes 5 sample subcap rationales:
  - 3 with complete proof structures (PASS examples)
  - 2 with missing elements (intentional failures: missing Rule links, missing Counterclaim)
- **Expected Behavior:** Checks correctly identify and categorize proof deficiencies
- **Pass Criteria:** All PASS examples score ≥3.5 without proof issues; all FAIL examples flagged with specific missing element

**Implementation Location:**
- Golden case JSON: `templates/golden_cases/case_e_proof_carrying.json`
- Test runner: `references/regression_suite.md`, Golden Cases section

**Impact:** Ensures proof-carrying structure checks are robust and prevent partial structures

**Timeline:** Implement in governance skill v2.0 (current)

---

## Section 4: Error Log Entries

### Error Log Entry 4.1: "Proof Structure Incomplete" Pattern

**Pattern ID:** ERR-PROOF-001
**Severity:** MEDIUM
**Frequency in this assessment:** 1 occurrence (P1C5)

**Pattern Description:**
Rationale lacks explicit Claims (C1-C3) structure, replacing with narrative prose. Evidence links and Rule links present but claim structure unclear.

**Trigger Condition:**
Post-hoc rationale analysis shows: narrative format, <3 explicit claims, evidence citations sparse but valid, rule references present.

**Remediation:**
Re-structure rationale using Claims-Evidence-Rules framework before re-audit.

**Learning Implication:**
Governance team should emphasize proof template clarity in pre-assessment guidance. Consider providing annotated proof examples to scorers.

---

### Error Log Entry 4.2: "Distribution Anomaly — Platform Effect" Pattern

**Pattern ID:** ERR-DIST-PLATFORM-001
**Severity:** INFO
**Frequency in this assessment:** 1 occurrence (P2, 62% on score 3.0)

**Pattern Description:**
Score clustering on a specific value (3.0) suggests possible implicit "default score" bias, particularly in P2 where many capabilities are present in the platform but maturity varies.

**Trigger Condition:**
>60% of subcaps in a pillar score exactly 3.0; no clear operational reason (e.g., no pervasive cap).

**Remediation:**
During next similar assessment, ask scorer to justify each score >M2 with specific evidence differentiator. If still clustering, consider whether capability definitions are too broad or whether evidence types make fine-grained differentiation difficult.

**Learning Implication:**
P2 capability definitions may need refinement to better distinguish M2 (some platform features) from M3 (measurable adoption/integration).

---

## Section 5: Recommended Program Actions

### Action 5.1: Update Proof-Carrying Framework (PRIORITY: HIGH)

**Owner:** Skill Development Team
**Timeline:** Before next v3.1 release
**Files to Update:**
- `references/scoring_methodology.md` — Add explicit proof structure requirements
- `communication_standards.md` — Add proof template examples
- `capability_criteria.md` — Add proof-carrying examples for 2-3 sample capabilities

**Success Criterion:**
Next 2 assessments using updated skill show ≤1 proof structure issue per assessment (vs. current 1 per assessment).

---

### Action 5.2: Refine P2 Capability Definitions (PRIORITY: MEDIUM)

**Owner:** Rubric Development Team
**Timeline:** Next rubric revision cycle (Q2 2024)
**Files to Update:**
- `scoring_toolkit_P2.xlsx` — Add maturity level anchor examples distinguishing M2 vs. M3
- `evidence_map.md` — Flag P2 categories requiring specific quantitative evidence (e.g., adoption %, feature usage rates)

**Success Criterion:**
Score distribution in P2 across 3+ assessments shows <55% clustering on any single value.

---

### Action 5.3: Formalize Golden Cases E & F (PRIORITY: HIGH)

**Owner:** Governance & QA Team
**Timeline:** Before governance skill v2.0 final release
**Deliverables:**
- `templates/golden_cases/case_e_proof_carrying.json` — Complete test case with 5 sample rationales
- `templates/golden_cases/case_f_critic_pass.json` — Complete test case with 8 critic findings
- Updated `references/regression_suite.md` to include both cases

**Success Criterion:**
Both golden cases execute successfully in test runner; tolerance checks pass within ±0.25 at category level.

---

## Section 6: Deferred Items

### Deferred Item 6.1: Cross-Assessment Calibration Baseline

**Issue:** DIST-001 flagged score clustering, but only 1 comparable assessment available. Cannot determine if pattern is normal variation or systematic bias.

**Decision:** Defer to Workflow B (Cross-Assessment Calibration) once ≥3 similar-institution assessments complete.

**Deferral Reason:** Need statistically significant sample to establish program baseline.

**Expected Resolution:** Q2 2024 after 3+ regional bank assessments

---

## Section 7: Patch Block Metadata

| Field | Value |
|-------|-------|
| **Patch Block ID** | PATCH-DMA-XXXX-00000000 |
| **Assessment Run ID** | DMA-XXXX-00000000-0000 |
| **Institution** | [Institution Name] |
| **Sub-vertical** | [Sub-vertical] |
| **Governance Auditor** | [Auditor Name], Skill v2.0 |
| **Issues Addressed** | 5 total (3 actionable) |
| **Golden Cases Proposed** | Case E, Case F |
| **Error Log Entries** | 2 new patterns (ERR-PROOF-001, ERR-DIST-PLATFORM-001) |
| **Rubric Changes Proposed** | 2 (proof structure, dist thresholds) |
| **Program Actions** | 3 (high, medium, high priorities) |
| **Generated** | 2024-01-16T14:32:00Z |

---

## Appendix: Technical Details

### Test Case Execution (if Workflow C applies)

If this assessment triggers a rubric version change, run golden cases with updated rubric:

```
Golden Case A (Sparse Evidence):
  Input: 15 evidence items, PUBLIC mode, small CU
  Expected Overall: 2.2 ± 0.5
  Actual Overall: [populated after re-run]
  Status: [PASS/FAIL]

Golden Case B (Contradictory Evidence):
  Input: 20 evidence items with 4 contradictions (T1 vs T3)
  Expected Overall: 2.8 ± 0.5
  Actual Overall: [populated after re-run]
  Status: [PASS/FAIL]

Golden Case E (Proof-Carrying):
  Input: 5 sample rationales (3 complete, 2 incomplete)
  Expected: PV-01 PASS, PV-02 PASS, PV-03 warnings only
  Actual: [populated after re-run]
  Status: [PASS/FAIL]
```

---

## Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Governance Auditor | [Auditor Name] | ________________ | 2024-01-16 |
| Skill Owner (Assessment) | [Skill Owner] | ________________ | [Date] |
| Program Manager | [PM Name] | ________________ | [Date] |

---

**Document Classification:** Internal — Governance
**Retention:** Permanent (learning archive)
**Distribution:** Skill development team, program leadership, historical repository
