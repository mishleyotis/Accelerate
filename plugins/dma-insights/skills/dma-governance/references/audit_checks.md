# Audit Check Catalog

This file contains every check that the Governance Skill runs during a Workflow A
single-assessment audit. Checks are grouped by category and mapped to the DMA Assessment
Skill's QA system for traceability.

**Severity definitions**:
- **CRITICAL**: Blocks delivery. Score is mathematically wrong, evidence is missing, or
  a mandatory disclosure is absent. Must be fixed.
- **HIGH**: Should block delivery unless accepted by program lead. Systematic issue that
  affects reliability or defensibility.
- **MEDIUM**: Should be noted but doesn't block delivery. May indicate an evidence gap
  or a minor inconsistency.
- **LOW**: Informational. Polish item or style preference.

---

## Category 1: Input Validation

Run these before any scoring checks.

| Check ID | Description | Pass Criteria | Severity |
|----------|-------------|---------------|----------|
| IV-01 | run_manifest.json present | File exists and parses as valid JSON | CRITICAL |
| IV-02 | run_manifest.json schema valid | All required fields populated, enums valid | CRITICAL |
| IV-03 | run_manifest overall score matches pillar weighted average | ±0.02 | CRITICAL |
| IV-04 | run_manifest evidence total = sum of tier distribution | Exact match | HIGH |
| IV-05 | caps_applied_log, WHEREVER it lives, is parseable when it exists | Sheet, column, CSV or JSON — parseable if present. **ABSENT IS A PASS**: if no caps were applied there were no issues (owner, 2026-08-23), and a clean assessment writes no cap log | HIGH |
| IV-06 | contradiction_log.csv present and parseable | File exists, correct column count | CRITICAL |
| IV-07 | evidence_index.csv present and parseable | File exists, correct column count | CRITICAL |
| IV-08 | Workbook (.xlsx) present with the tabs that carry data | Summary, Calculation_Chain, P1-P4_Scoring_Detail, Evidence_Index. Caps_Applied_Log, Contradiction_Log and Absent_Evidence_Log are CONDITIONAL — required only when the assessment has caps, contradictions or absences to log; an empty finding set writes no sheet, and their absence is never CRITICAL | CRITICAL for the data tabs |
| IV-09 | Report (.docx) present | File exists | CRITICAL |
| IV-10 | Rubric version in manifest matches skill version in workbook | Exact match | HIGH |
| IV-11 | reasoning_chain_log.json present and parseable | File exists, valid JSON, `summary.total_subcaps` matches workbook row count | HIGH |
| IV-12 | Manifest uses `run_manifest_v2` schema | `$schema` field equals `"run_manifest_v2"` | HIGH |

---

## Category 2: Score Integrity (maps to Layer 1 QA G.1–G.4)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| SI-01 | G.1.1 | Subcap count per pillar matches taxonomy | Exact count | CRITICAL |
| SI-02 | G.1.2 | No empty rows in scoring detail | 0 empty | CRITICAL |
| SI-03 | G.1.3 | No duplicate subcap IDs | 0 duplicates | CRITICAL |
| SI-04 | G.2.1 | All rationale cells populated | 0 empty | CRITICAL |
| SI-05 | G.2.2 | All rationales ≥150 characters | 100% | HIGH |
| SI-06 | G.2.3 | No forbidden rationale patterns | 0 matches | HIGH |
| SI-07 | G.2.4 | Every rationale has ≥1 evidence ID + quoted fact | 100% | HIGH |
| SI-08 | G.2.5 | Every rationale references a maturity descriptor | 100% | MEDIUM |
| SI-09 | G.2.6 | Non-.5 Raw_Scores have quantitative justification | 100% | HIGH |
| SI-10 | G.2.7 | Ceiling and cap checks documented in rationale | 100% | HIGH |
| SI-11 | G.2.8 | Counter-evidence addressed in rationale | 100% | MEDIUM |
| SI-12 | G.2.9 | No duplicate rationale text across subcaps | 0 exact matches | HIGH |
| SI-13 | G.2.10 | Contradictions cite resolution rule | 100% | HIGH |
| SI-14 | G.2.11 | Adjustment-ceilings have ADJUSTMENTS line in rationale | 100% | HIGH |
| SI-15 | G.4.1 | All scores between 1.0 and 5.0 | 100% | CRITICAL |
| SI-16 | G.4.2 | Scores in 0.5 increments unless justified | Justified exceptions only | MEDIUM |
| SI-17 | G.4.3 | Final_Score ≤ Evidence_Ceiling | 100% | CRITICAL |
| SI-18 | G.4.4 | Final_Score ≤ all applicable cap/adjustment ceilings | 100% | CRITICAL |
| SI-19 | G.4.5 | Final = Raw when Caps_Applied = "None" | 100% | CRITICAL |
| SI-20 | G.4.7 | Final ≠ Raw → Caps_Applied ≠ "None" + log row exists | 100% | CRITICAL |
| SI-21 | G.4.8 | ADJ_ entries have Trigger_Evidence | 100% | HIGH |
| SI-22 | — | Column S (Proof_Claims) populated for all scored subcaps | 100% non-empty | HIGH |
| SI-23 | — | Column T (Proof_Links) contains valid JSON for all scored subcaps | 100% parseable | HIGH |

---

## Category 3: Evidence Traceability (maps to Layer 1 QA G.3)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| ET-01 | G.3.1 | Every Evidence_ID cited in scoring exists in Evidence_Index | 100% | CRITICAL |
| ET-02 | G.3.2 | Every Evidence_ID uses correct format (E-NNN:FN) | 100% | MEDIUM |
| ET-03 | G.3.3 | Every subcap cites ≥1 evidence item | 100% | HIGH |
| ET-04 | G.3.4 | Every evidence item in Evidence_Index is cited ≥1 time | 100% | MEDIUM |
| ET-05 | G.3.5 | Evidence_Tier in scoring matches Evidence_Index tier | 100% | CRITICAL |
| ET-06 | — | Evidence_Index ERS values are arithmetically valid | Recalculate from components (±0.01) | HIGH |

---

## Category 4: Aggregation (maps to Layer 1 QA G.5)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| AG-01 | G.5.1 | Subcap weights sum to 1.0 per capability | ±0.01 | CRITICAL |
| AG-02 | G.5.2 | Capability Effective_Weights sum to 1.0 per category | ±0.01 (excl. N/A) | CRITICAL |
| AG-03 | G.5.3 | Category weights sum to 1.0 per pillar | ±0.01 | CRITICAL |
| AG-04 | G.5.4 | Pillar weights sum to 1.0 | ±0.01 | CRITICAL |
| AG-05 | G.5.5 | Capability scores match subcap aggregation | ±0.02 | CRITICAL |
| AG-06 | G.5.6 | Category scores match capability aggregation | ±0.02 | CRITICAL |
| AG-07 | G.5.7 | Pillar scores match category aggregation | ±0.02 | CRITICAL |
| AG-08 | G.5.8 | Overall score matches pillar aggregation | ±0.02 | CRITICAL |
| AG-09 | G.5.9 | Calculation_Chain parent = sum of children weighted contributions | ±0.01 | CRITICAL |
| AG-10 | G.5.10 | N/A capabilities: >30% subcaps have NO_EVIDENCE + Absent_Evidence_Log | 100% | HIGH |
| AG-11 | G.5.11 | N/A capabilities: Effective_Weight = 0, Weighted_Contribution = 0 | 100% | CRITICAL |
| AG-12 | G.5.12 | N/A capabilities documented in report Section 11 | 100% | HIGH |

---

## Category 5: Caps & Dependencies (maps to Layer 1 QA G.6)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| CD-01 | G.6.1 | All 7 dependency rules evaluated against category scores | All checked | CRITICAL |
| CD-02 | G.6.2 | Triggered deps logged as CROSS_PILLAR in Caps_Applied_Log | 100% | CRITICAL |
| CD-03 | G.6.3 | Affected subcaps ≤ dependency cap value | 100% | CRITICAL |
| CD-04 | G.6.4 | Post-Pass 2 aggregation recalculated correctly | ±0.02 | CRITICAL |
| CD-05 | G.6.5 | Cascading dependencies converged | No further changes possible | HIGH |
| CD-06 | — | ADJ_STALENESS ceiling = min(raw, others) − 0.3 | ±0.01 | CRITICAL |
| CD-07 | — | ADJ_INCIDENT_MAJOR ceiling = min(raw, others) − 0.5 | ±0.01 | CRITICAL |
| CD-08 | — | ADJ_COMPLAINT ceiling = min(raw, others) − 0.3 | ±0.01 | CRITICAL |

---

## Category 6: Confidence-ERS Validation (maps to Layer 1 QA G.7)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| CE-01 | G.7.1 | No HIGH confidence with best-evidence ERS < 2.5 | 0 violations | CRITICAL |
| CE-02 | G.7.2 | No LOW confidence with ERS ≥ 3.5 + ≥3 sources (flag for review) | 0 violations | MEDIUM |
| CE-03 | G.7.3 | Single-source subcaps have confidence ≤ MEDIUM | 100% | HIGH |
| CE-04 | G.7.4 | Single-source T1/T2 subcaps have limitation statement | 100% | MEDIUM |

---

## Category 7: Contradiction Log (maps to Layer 1 QA G.8)

| Check ID | L1 QA Ref | Description | Pass Criteria | Severity |
|----------|-----------|-------------|---------------|----------|
| CL-01 | G.8.1 | Rationale counter-evidence → Contradiction_Log row exists | 100% | HIGH |
| CL-02 | G.8.2 | Resolution_Rule populated with valid enum | 100% | HIGH |
| CL-03 | G.8.3 | UNRESOLVED contradictions flagged in Section 11 | 100% | HIGH |
| CL-04 | G.8.4 | Winner matches evidence used for scoring | 100% | HIGH |

---

## Category 8: Report Content

| Check ID | Description | Pass Criteria | Severity |
|----------|-------------|---------------|----------|
| RC-01 | All 12 sections + 3 appendices present | 100% | CRITICAL |
| RC-02 | Peer proxy disclosure in Section 2 | Present with required phrases | CRITICAL |
| RC-03 | No "identical methodology" language | 0 occurrences | HIGH |
| RC-04 | No fixed month ranges in roadmap | 0 occurrences of "Months 0-6" etc. | HIGH |
| RC-05 | Roadmap phases anchor to institutional milestones | Each phase has Target | MEDIUM |
| RC-06 | No "Critical Gaps" heading | 0 occurrences | MEDIUM |
| RC-07 | All workbook scores match report scores | 100% exact match | CRITICAL |
| RC-08 | All peer medians match across artifacts | 100% exact match | HIGH |
| RC-09 | Trend arrows consistent with narrative | No "improving" + "↓" contradiction | HIGH |
| RC-10 | N/A capabilities in Section 11 | 100% documented | HIGH |
| RC-11 | Single-source capabilities have limitation statements | 100% | MEDIUM |
| RC-12 | Banned language check (per communication_standards.md) | 0 violations | MEDIUM |

---

## Execution Order

1. Input Validation (IV-01 to IV-10) — STOP if any CRITICAL fails
2. Score Integrity (SI-01 to SI-21)
3. Evidence Traceability (ET-01 to ET-06)
4. Aggregation (AG-01 to AG-12)
5. Caps & Dependencies (CD-01 to CD-08)
6. Confidence-ERS (CE-01 to CE-04)
7. Contradiction Log (CL-01 to CL-04)
8. Report Content (RC-01 to RC-12)
9. Distributional Checks (see distributional_checks.md)

Total: 79 checks across 9 categories.
