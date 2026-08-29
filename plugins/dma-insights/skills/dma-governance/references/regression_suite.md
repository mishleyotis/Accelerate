# Regression Suite

This file defines the golden test cases and structural invariants used to verify that
rubric, template, or taxonomy changes don't break scoring consistency.

---

## 1. Structural Invariants

These must hold for ANY assessment, regardless of institution or rubric version.

### 1.1 Mathematical Invariants

| ID | Invariant | Tolerance |
|----|-----------|-----------|
| MI-01 | subcap scores ∈ [1.0, 5.0] | Exact |
| MI-02 | subcap scores have ≤1 decimal place | Exact |
| MI-03 | Final_Score ≤ Raw_Score always | Exact |
| MI-04 | Final_Score ≤ Evidence_Ceiling always | Exact |
| MI-05 | Final_Score = min(Raw, Ceiling, all Caps, all Adj_Ceilings) | ±0.01 |
| MI-06 | Weighted contributions sum to parent Raw_Score | ±0.01 per level |
| MI-07 | Weight sums = 1.0 at every aggregation level | ±0.01 |
| MI-08 | Overall = weighted average of pillars | ±0.02 |
| MI-09 | ADJ_STALENESS ceiling = min(raw, others) − 0.3 | ±0.01 |
| MI-10 | ADJ_INCIDENT_MAJOR ceiling = min(raw, others) − 0.5 | ±0.01 |
| MI-11 | ADJ_COMPLAINT ceiling = min(raw, others) − 0.3 | ±0.01 |
| MI-12 | N/A capability Effective_Weight = 0 | Exact |
| MI-13 | Non-N/A Effective_Weights within category sum to 1.0 | ±0.01 |

### 1.2 Policy Invariants

| ID | Invariant |
|----|-----------|
| PI-01 | Every Final ≠ Raw has a Caps_Applied_Log row |
| PI-02 | Every UNRESOLVED contradiction is flagged in Section 11 |
| PI-03 | Peer proxy disclosure present in Section 2 |
| PI-04 | No "identical methodology" language in report |
| PI-05 | No fixed month ranges (Months 0-6, etc.) in roadmap |
| PI-06 | No "Critical Gaps" heading in report |
| PI-07 | Every rationale ≥150 characters |
| PI-08 | Every rationale has ≥1 evidence-backed fact citation |
| PI-09 | HIGH confidence requires ERS ≥ 2.5 |
| PI-10 | Single-source subcap confidence ≤ MEDIUM |
| PI-11 | N/A capabilities documented in Section 11 |
| PI-12 | Run manifest present with all required fields |

### 1.3 Relational Invariants

| ID | Invariant |
|----|-----------|
| RI-01 | Evidence_Index IDs ⊇ all evidence IDs cited in scoring |
| RI-02 | Caps_Applied_Log IDs ⊇ all cap IDs cited in Caps_Applied columns |
| RI-03 | Contradiction_Log subcap_ids ⊆ scored subcap IDs |
| RI-04 | Absent_Evidence_Log subcap_ids ⊆ taxonomy subcap IDs |
| RI-05 | Run manifest scores match workbook Summary sheet |
| RI-06 | Report scores match workbook scores (all 16 categories + 4 pillars + overall) |

---

## 2. Golden Test Cases

### Case A: Sparse Evidence (PUBLIC mode, Small CU)

**Profile**: $800M credit union, public evidence only, 15 evidence items

**Expected behaviors**:
- Most subcaps scored 1.0-2.5 (low evidence depth)
- Evidence ceilings binding on most subcaps (T3-T5 dominant)
- ≥5 capabilities marked N/A (>30% subcaps with NO_EVIDENCE)
- LOW confidence on >40% of subcaps
- No dependency caps triggered (base scores too low)
- Single-source cap (3.0) binding on >30% of scored subcaps

**Key score expectations** (tolerance: ±0.5 at subcap, ±0.25 at category):
- Overall: 1.8-2.4
- P1 (Strategy): 1.5-2.5
- P4 (Technology): 1.5-2.0

**Caps that MUST trigger**:
- Evidence ceiling caps on every subcap with T4/T5-only evidence
- Single-source caps on subcaps with only 1 evidence item

**Evidence pack**: [To be curated — 15 items: 2×T2 (annual report, 10-K), 5×T3 (ratings,
analyst), 3×T4 (leaked internal), 5×T5 (website, press releases)]

---

### Case B: Contradictory Evidence (PUBLIC mode, Medium Bank)

**Profile**: $5B community bank, public evidence, 45 evidence items, known mixed signals

**Expected behaviors**:
- T1 source (OCC exam from 18 months ago) contradicts T3 analyst report (6 months old)
- ERS-first resolution should prefer the T3 in cases where T1 is stale (>24mo) — but the
  T1 here is 18 months, so T1/T2 override applies
- ≥8 contradictions logged in Contradiction_Log
- MEDIUM confidence on most contradicted subcaps
- Moderate cap activity (regulatory caps on 2-3 capabilities from MRA)

**Key score expectations**:
- Overall: 2.5-3.2
- Categories with contradictions: wider tolerance (±0.75)
- P3 (Risk): 2.0-2.8 (MRA impact)

**Contradictions that MUST be found and resolved**:
1. OCC exam (T1, 18mo) rates risk management "satisfactory" vs analyst report (T3, 6mo)
   citing "inadequate BSA/AML controls" → T1/T2 override applies (≤24mo + directly relevant)
2. Annual report (T2) claims "AI-powered lending" vs app store reviews (T3) showing basic
   digital experience → ERS ranking (T3 higher if more specific)

**Evidence pack**: [To be curated — 45 items across all tiers]

---

### Case C: Dependency Cascade (HYBRID mode, Large Bank)

**Profile**: $25B regional bank, hybrid evidence, 80 evidence items, governance weakness

**Expected behaviors**:
- P1C2 (Governance) scores <2.5, triggering cap on ALL P3 subcaps at 3.0
- P4C4 (Cybersecurity) scores <2.5 (disclosed breach 15mo ago), triggering:
  - Breach <24mo cap on P4C4 at 3.0
  - P4C4 <2.5 triggering cap on P4C1 (Data Governance) at 3.0
- Cascading: P4C1 cap may push P4C1 <2.5, triggering cap on P2C4 (Personalization)
- Two-pass algorithm fully exercised
- ≥15 CROSS_PILLAR cap log entries

**Key score expectations**:
- Overall: 2.2-2.8
- P3 categories: all ≤3.0 (governance cap)
- P4C4: ≤3.0 (breach cap)
- P4C1: ≤3.0 (cybersecurity dependency)
- P2C4: ≤3.0 if P4C1 cascade fires

**Dependency caps that MUST trigger**:
1. P1C2 < 2.5 → P3 all subcaps ≤ 3.0
2. Breach <24mo → P4C4 subcaps ≤ 3.0
3. P4C4 < 2.5 → P4C1 subcaps ≤ 3.0
4. If P4C1 < 2.5 after cap → P2C4 subcaps ≤ 3.0 (cascade)

**Evidence pack**: [To be curated — 80 items, heavy T1/T2 from regulatory actions]

---

### Case D: High Maturity (PUBLIC mode, Mega Bank)

**Profile**: $100B institution, public evidence, 120+ evidence items, strong digital

**Expected behaviors**:
- Most subcaps scored 3.5-4.5
- Evidence ceilings rarely binding (strong T1/T2 evidence available)
- HIGH confidence on >50% of subcaps
- Score precision: 0.1 increments used where quantitative metrics justify
- Few caps triggered (strong evidence base)
- Staleness check: some T1 evidence >24mo triggers ADJ_STALENESS on specific subcaps

**Key score expectations**:
- Overall: 3.5-4.2
- P2 (Customer): 3.8-4.5 (strong digital presence)
- P1 (Strategy): 3.5-4.0

**Precision tests**:
- At least 3 subcaps should use 0.1 scoring (e.g., 3.7, 4.3) justified by quantitative
  metrics from evidence
- At least 1 subcap should have ADJ_STALENESS applied (T1 exam from >24 months ago)

---

## 3. Regression Execution Protocol

### When to Run

- Before ANY rubric version release (change Class 1 or 2)
- Before ANY taxonomy version release
- Quarterly (even without changes, to validate tooling stability)

### How to Run

1. Load the golden case evidence pack
2. Run Layer 1 (DMA Assessment Skill) with the proposed rubric version
3. Collect all outputs (workbook, report, manifest, CSVs)
4. Run Layer 2 (this Governance Skill) Workflow A on each output
5. Compare results against expected behaviors and score tolerances

### Pass/Fail Criteria

- **PASS**: All golden cases within tolerance on all metrics, all invariants hold
- **PARTIAL PASS**: Minor deviations (1-2 subcaps outside tolerance by <0.25), all
  structural/relational invariants hold. Acceptable for Class 0/1 changes.
- **FAIL**: Any category-level score outside tolerance, OR any structural invariant violated.
  Block the release.

### Regression Report Format

```markdown
=== REGRESSION REPORT — [Proposed Version] [Date] ===

## Test Results
| Case | Overall Expected | Overall Actual | Delta | Verdict |
|------|-----------------|---------------|-------|---------|
| A (Sparse) | 1.8-2.4 | [X.XX] | [±X.XX] | PASS/FAIL |
| B (Contradictions) | 2.5-3.2 | [X.XX] | [±X.XX] | PASS/FAIL |
| C (Dependencies) | 2.2-2.8 | [X.XX] | [±X.XX] | PASS/FAIL |
| D (High Maturity) | 3.5-4.2 | [X.XX] | [±X.XX] | PASS/FAIL |

## Invariant Checks
[All MI/PI/RI checks: PASS/FAIL count]

## Behavioral Checks
[Did expected caps trigger? Did contradictions resolve correctly?]

## Comparability Assessment
[How does this change affect cross-version benchmarking?]

## Verdict: PASS / PARTIAL PASS / FAIL
=== END REGRESSION REPORT ===
```
