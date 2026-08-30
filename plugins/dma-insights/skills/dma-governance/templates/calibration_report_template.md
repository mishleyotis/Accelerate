# Cross-Assessment Calibration Report

**Report ID:** CALIB-[YYYYMMDD]-[SEQ]
**Workflow:** Governance Skill v2.0 — Workflow B
**Report Generated:** [Date and Time]
**Assessment Period:** [Date Range]

---

## Executive Summary

This report compares maturity assessments across [N] institutions to detect drift, bias, and calibration issues. All findings are statistical patterns that may indicate methodology refinement opportunities.

### Key Findings

| Metric | Value | Interpretation |
|--------|-------|-----------------|
| **Assessments Compared** | [N] | All same sub-vertical: [Sub-Vertical] |
| **Score Distribution Variance** | [X] std dev | Within/Outside expected range |
| **Harshness Index** | [+X% / -X%] | Deviation from baseline |
| **Drift Flags** | [N critical, N caution] | Items requiring attention |

---

## Section 1: Assessment Cohort Profile

### 1.1 Cohort Composition

| Metric | Value |
|--------|-------|
| **Total Assessments** | [N] |
| **Sub-Vertical** | [Sub-Vertical] |
| **Size Tiers Represented** | [List tiers] |
| **Evidence Modes** | PUBLIC: [N], INTERNAL: [N], HYBRID: [N] |
| **Assessment Skill Versions** | [List versions] |
| **Assessment Period** | [Months covered] |
| **Governance Audit Verdicts** | PASS: [N], PASS_WITH_NOTES: [N], FAIL: [N] |

### 1.2 Comparable Assessment Selection

**Comparability Criteria Applied:**
- Same sub-vertical: [Sub-Vertical]
- Same size tier (or adjusted per schema): [Tier]
- Same major governance skill version: 2.0
- Same assessment skill version (or documented compatibility): v3.0+

**Assessments Included:** [List institution names, run IDs, dates]

**Assessments Excluded:** [Reasons: version mismatch, different sub-vertical, insufficient data, etc.]

---

## Section 2: Calibration Metrics

### 2.1 Score Distribution Comparison

**Metric:** Overall score across all assessments (target: 2.5–3.5 range typical)

```
Institution          | Overall | P1    | P2    | P3    | P4
---------------------|---------|-------|-------|-------|-------
[Institution A]      | 2.8     | 3.1   | 2.9   | 2.4   | 2.9
[Institution B]      | 3.2     | 3.4   | 3.5   | 3.0   | 3.0
[Institution C]      | 2.5     | 2.6   | 2.8   | 2.2   | 2.5
---------------------|---------|-------|-------|-------|-------
Mean                 | 2.83    | 3.03  | 3.07  | 2.53  | 2.80
Median               | 2.80    | 3.10  | 2.90  | 2.40  | 2.90
Std Dev              | 0.35    | 0.40  | 0.35  | 0.40  | 0.25
Min                  | 2.50    | 2.60  | 2.80  | 2.20  | 2.50
Max                  | 3.20    | 3.40  | 3.50  | 3.00  | 3.00
```

**Interpretation:**
- Mean overall score of 2.83 is consistent with [historical baseline / peer group baseline]
- P2 (Customer Experience) shows highest average (3.07), suggesting consistent strength in this pillar across cohort
- P3 (Operations) shows lowest average (2.53) and highest variance (0.40 std dev), suggesting less consistency in evaluation or actual material differences

---

### 2.2 Evidence Discipline Metrics

**Average Evidence per Subcapability:**

| Metric | Value | Range | Assessment |
|--------|-------|-------|------------|
| **Avg ERS Score** | 3.2 | 2.8–3.6 | Within expected; quality consistent |
| **Avg Evidence Items per Subcap** | 2.4 | 1.8–3.2 | Slightly below target (2.5); suggests saturation or evidence scarcity |
| **Evidence Tier Distribution (Avg)** | T1: 18%, T2: 28%, T3: 35%, T4: 15%, T5: 4% | — | Healthy mix; T3 dominant (reasonable for prospecting context) |
| **Sources per Evidence Item** | 1.3 | 1.1–1.8 | Mostly single-source; limited cross-corroboration |
| **Recency (% within 12 mo)** | 72% | 65–85% | Acceptable; 28% historical evidence acceptable for stable metrics |

**Flags:**
- **Sources per Evidence Item = 1.3:** Most evidence is single-source. While acceptable, consider whether 2+ independent sources on key metrics would improve confidence
- **Evidence Items per Subcap = 2.4:** Approach target but on lower end; may indicate assessor time constraints or genuine evidence scarcity in prospecting context

---

### 2.3 Cap Application Frequency

**How Often Each Cap Type Fires (Across Cohort):**

| Cap Type | Frequency | Avg Severity | Interpretation |
|----------|-----------|--------------|---|
| **Severity Caps (S1/S2/S3)** | 18% of subcaps | S2 (material) | Reasonable; reflects mixed regulatory landscape |
| **Evidence Caps (T5-only, single-source)** | 24% of subcaps | Moderate | Suggests evidence gathering strategy may need refinement for future assessments |
| **Sentiment Caps (P2 only)** | 12% of P2 subcaps | Low impact | App ratings generally >3.5; caps applied sparingly |
| **Cross-Pillar Dependency Caps** | 8% of subcaps | Moderate | Governance gaps do constrain downstream; expected pattern |

**Drift Threshold:** Severity cap frequency should stay within 10–25%. Current cohort = 18% ✓ PASS

**Alert:** Evidence cap frequency = 24%, approaching upper threshold (25%). If increases to ≥30% in next assessment cycle, escalate evidence gathering guidance.

---

### 2.4 Confidence Calibration

**Confidence Distribution Across Assessments:**

| Confidence Level | % of Subcaps | Expected % | Assessment |
|------------------|-------------|-----------|---|
| **HIGH** | 62% | 50–65% | Within expected (not overconfident) |
| **MEDIUM** | 28% | 25–40% | Within expected |
| **LOW** | 10% | 5–15% | Within expected; appropriate for sparse evidence |

**Cross-Check:** Avg ERS score = 3.2. Avg confidence = HIGH for 62% of subcaps.
- Confidence level HIGH (>3.0 ERS) = 62% of subcaps ✓ Alignment good

**Observation:** No overconfidence pattern detected. Governance verdict stands as PASS for confidence calibration.

---

### 2.5 Contradiction Rate

**Contradictions per Assessed Capability (Avg Across Cohort):**

| Pillar | Avg Contradictions | Avg Evidence Items | Contradiction Rate |
|--------|-------------------|-------------------|---|
| **P1** | 0.8 | 2.1 | 38% |
| **P2** | 1.2 | 2.6 | 46% |
| **P3** | 1.5 | 3.0 | 50% |
| **P4** | 0.6 | 2.2 | 27% |
| **Overall** | 1.0 | 2.5 | 40% |

**Interpretation:**
- Contradiction rate 40% is **NORMAL** for prospecting context with mixed evidence sources
- P3 shows highest contradiction rate (50%), reflecting regulatory complexity and evolving compliance landscape
- All contradictions documented with resolution rationale per skill requirement

**Assessment:** No anomalies. Contradiction rates consistent with evidence strategy.

---

## Section 3: Drift Detection

### 3.1 Harshness Index

**Harshness Index:** Deviation of current cohort mean from historical baseline

```
Metric                      | Current Cohort | Historical Baseline | Delta  | Status
---------------------------|----------------|-------------------|--------|--------
Overall Score Mean          | 2.83           | 2.85               | -0.02  | ✓ No drift
P1 Mean                     | 3.03           | 3.05               | -0.02  | ✓ No drift
P2 Mean                     | 3.07           | 3.08               | -0.01  | ✓ No drift
P3 Mean                     | 2.53           | 2.54               | -0.01  | ✓ No drift
P4 Mean                     | 2.80           | 2.82               | -0.02  | ✓ No drift
```

**Drift Threshold:** ±0.15 at overall level; ±0.20 at pillar level
**Result:** All metrics within tolerance. NO HARSHNESS DRIFT detected.

**Interpretation:** Assessments are calibrated consistently; no evidence of assessor group becoming systematically harsher or more lenient over time.

---

### 3.2 Category-Level Bias Detection

**Are scores consistently higher/lower on specific categories vs. program mean?**

```
Category           | Current Cohort Mean | Program Baseline | Delta  | Std Deviations | Drift Status
-------------------|-------------------|-----------------|--------|---|---
P1C1 (Strategy)    | 3.1                | 3.12            | -0.02  | 0.1 | ✓ No drift
P1C2 (Governance)  | 3.2                | 3.14            | +0.06  | 0.3 | ✓ No drift
P2C1 (Marketing)   | 3.2                | 3.15            | +0.05  | 0.2 | ✓ No drift
P2C2 (Onboarding)  | 3.4                | 3.35            | +0.05  | 0.2 | ✓ No drift
P3C3 (Compliance)  | 2.8                | 2.75            | +0.05  | 0.2 | ✓ No drift
P4C1 (Data Mgmt)   | 2.7                | 2.68            | +0.02  | 0.1 | ✓ No drift
```

**Drift Threshold:** ±1.5 std dev (±1.5σ)
**Result:** All deltas <0.5σ. NO SYSTEMATIC BIAS detected.

**Interpretation:** Assessments are balanced; no specific category is consistently overscored or underscored.

---

### 3.3 Evidence Tier Preference

**Do assessments over-rely on specific evidence tier types?**

```
Evidence Tier | Current Cohort Avg | Program Baseline | Delta    | Drift Status
--------------|-------------------|-----------------|----------|---
T1 (Reg/Audit) | 18%               | 19%             | -1%      | ✓ No drift
T2 (Official)  | 28%               | 27%             | +1%      | ✓ No drift
T3 (3P Anal)   | 35%               | 36%             | -1%      | ✓ No drift
T4 (Internal)  | 15%               | 15%             | 0%       | ✓ No drift
T5 (Marketing) | 4%                | 3%              | +1%      | ✓ No drift
```

**Drift Threshold:** Any tier >±5% variation
**Result:** All tiers within ±1%. NO TIER PREFERENCE DRIFT detected.

**Interpretation:** Evidence sourcing is consistent; assessments are not favoring or avoiding specific evidence types.

---

## Section 4: Flags & Recommendations

### 4.1 Critical Drift Flags

**NONE.** No assessments in cohort exceeded drift thresholds.

---

### 4.2 Caution Flags

#### Flag 4.2.1: Evidence Cap Frequency Trending Upward (CAUTION)

**Finding:** Evidence cap application = 24% (vs. baseline 20%)

**Trend:** Last assessment 19%, current cohort 24% (↑5% over [N] assessments)

**Root Cause:** All assessments in cohort used PUBLIC evidence mode (no internal documents). Evidence scarcity is expected.

**Recommendation:**
- For next similar cohort, encourage assessments to source INTERNAL evidence where available
- If PUBLIC-only constraint persists, update governance baselines to accept 25–30% evidence cap rate as normal for prospecting context
- No action required on current assessments (verdict stands PASS)

---

#### Flag 4.2.2: P3 Contradiction Rate Higher Than Other Pillars (CAUTION)

**Finding:** P3 contradiction rate = 50% vs. P4 = 27% (23-point gap)

**Root Cause:** P3 (Operations & Compliance) inherently more complex; regulatory guidance evolves; audit findings often contradict compliance claims.

**Recommendation:**
- This is NORMAL pattern for Operations pillar
- Document in program baseline: P3 expected contradiction rate = 45–55%
- No action required (expected variation)

---

### 4.3 Informational Notes

#### Note 4.3.1: P2 Emerges as Strongest Pillar Across Cohort

**Finding:** P2 mean = 3.07 (highest); P3 mean = 2.53 (lowest)

**Observation:** Consistent pattern across [N] institutions suggests:
- Digital customer experience capabilities are more mature than operations/tech in this cohort
- Possible strategic focus on CX/digital banking by these institutions

**Implication:** In future assessments, focus evidence gathering on P3 and P4 to reduce evidence caps (currently 24%).

---

## Section 5: Calibration Assessment

### 5.1 Verdict Summary

| Dimension | Status | Notes |
|-----------|--------|-------|
| **Harshness Consistency** | ✓ PASS | No drift detected; assessments consistent |
| **Category Balance** | ✓ PASS | No systematic bias; categories balanced |
| **Evidence Discipline** | ✓ PASS | 2.4 items/subcap reasonable; ERS 3.2 acceptable |
| **Confidence Alignment** | ✓ PASS | No overconfidence; 62% HIGH confidence appropriate |
| **Contradiction Management** | ✓ PASS | 40% rate normal; all resolutions documented |
| **Cap Application** | ⚠ CAUTION | 24% evidence caps trending up; monitor |
| **Tier Preference** | ✓ PASS | No tier bias detected |

**Overall Calibration Status:** PASS_WITH_CAUTION

---

### 5.2 Program-Level Recommendations

#### Recommendation 5.2.1: Establish Prospecting-Context Baselines

**Action:** Create sub-vertical-specific baseline ranges for:
- Score distributions (mean, std dev)
- Evidence caps (expected %, adjusted for PUBLIC/INTERNAL/HYBRID)
- Confidence calibration (% HIGH acceptable per mode)
- Contradiction rates (by pillar)

**Rationale:** Current baselines are generic; prospecting context warrants context-specific thresholds.

**Owner:** Program Leadership
**Timeline:** Implement by next calibration cycle (Q2 2024)

---

#### Recommendation 5.2.2: Enhance Evidence Sourcing Guidance for Public Mode

**Action:** Update evidence_map.md and operating guides with:
- Tier-weighted sourcing targets for PUBLIC mode (e.g., "Aim for T1/T2 ≥40%, T3 ≥35%")
- Public-source inventory by sub-vertical (regulatory databases, published research, third-party ratings)
- Fallback rules when evidence gaps occur

**Rationale:** 24% evidence cap rate suggests assessors may be missing available public sources or hitting natural scarcity. Guidance could reduce caps to 20%.

**Owner:** Evidence Development Team
**Timeline:** Within 30 days

---

#### Recommendation 5.2.3: Refine P3 Contradiction Protocol

**Action:** Document that P3 contradiction rates of 45–55% are NORMAL and expected. Establish resolution quality standards:
- T1 vs. T3 contradiction: T1 wins (always)
- T2 vs. T3 contradiction: Use ERS; if tied, prefer more recent
- Multiple contradictions on same metric: Flag in narrative as "area of interpretation divergence"

**Rationale:** P3 operates in regulatory uncertainty; contradictions are not errors but reflect real divergence in guidance/practices.

**Owner:** Capability Development Team
**Timeline:** Update capability_criteria.md within 30 days

---

## Section 6: Comparability Assessment

### 6.1 Cross-Version Benchmarking

**Assessment Skill Versions in Cohort:** [List versions]

**Compatibility:** All assessments using v3.0+; rubric changes between v2.9 and v3.0 were backward-compatible (no retesting required for scoring).

**Limitation:** Cannot benchmark against v2.x assessments without recalculation; recommend archiving v2.x as "legacy baseline" and comparing forward only to v3.0+.

**Recommendation:** Future calibration reports should isolate v3.0 and v3.1 assessments separately until v3.1 stabilizes.

---

### 6.2 Sub-Vertical Variation

**Cohort Homogeneity:** All assessments are [Sub-Vertical].

**Status:** Single sub-vertical → Baseline established for this sub-vertical only. Cannot extrapolate to other sub-verticals (e.g., Regional Banks, Insurance).

**Next Step:** Once ≥3 assessments available in each sub-vertical, produce sub-vertical-specific calibration reports.

---

## Section 7: Historical Comparison (If Available)

### 7.1 Year-over-Year Trend

| Metric | [Prior Year] | Current Year | Trend |
|--------|---|---|---|
| Avg Overall Score | 2.85 | 2.83 | Stable |
| Avg P2 Score | 3.08 | 3.07 | Stable |
| Evidence Cap Rate | 20% | 24% | ↑ (4 pct point rise) |
| Avg ERS | 3.1 | 3.2 | ↑ (slight improvement) |

**Interpretation:**
- Overall calibration stable year-over-year
- ERS improving (better evidence sourcing or skill version improvement)
- Evidence cap rate trending up (see recommendations above)

---

## Section 8: Data Quality & Limitations

### 8.1 Data Limitations

- **Sample Size:** N=[count] assessments (small cohort; recommend ≥5 per sub-vertical for robust baselines)
- **Time Period:** [Months covered] (short window; seasonal or cycle effects not yet visible)
- **Evidence Mode Mix:** [N PUBLIC, N INTERNAL, N HYBRID] (skewed toward PUBLIC; may inflate evidence cap rates)
- **Assessor Pool:** [N assessors] (small pool; individual style may influence baseline estimates)

### 8.2 Caveats

- Recommendations should be treated as **hypotheses** to monitor, not confirmed insights
- Once ≥5 assessments of same sub-vertical and evidence mode available, recalibrate baselines
- Drift detection assumes stable institution population; changes in prospecting targets (e.g., shift from Large→Small tiers) invalidate baseline comparisons

---

## Section 9: Appendices

### Appendix A: Statistical Methods

**Drift Detection:** All metrics compared to historical baseline using parametric z-test (±1.5 std dev threshold). Drift threshold chosen to flag systematic bias while tolerating normal variation.

**Confidence Calibration:** ERS score vs. assigned Confidence level cross-tabulated; misalignment flagged if >20% of scores have confidence ≠ ERS quartile.

**Tier Distribution:** Chi-squared test (expected = baseline distribution, observed = current cohort). Flag if p < 0.05.

---

### Appendix B: Baseline Data Reference

```
Historical Program Baseline (Updated [Date]):
- Mean Overall Score: 2.85 ± 0.30
- P1 Mean: 3.05 ± 0.35
- P2 Mean: 3.08 ± 0.30
- P3 Mean: 2.54 ± 0.40
- P4 Mean: 2.82 ± 0.35
- Severity Cap Rate: 15–20%
- Evidence Cap Rate: 18–22%
- Avg ERS: 3.0–3.2
- Contradiction Rate: 35–45% (overall), P3 45–55%
```

---

## Sign-Off

| Role | Name | Signature | Date |
|------|------|-----------|------|
| Calibration Analyst | [Name] | ________________ | [Date] |
| Program Manager | [Name] | ________________ | [Date] |
| Governance Lead | [Name] | ________________ | [Date] |

---

**Report Classification:** Internal — Governance & Program Learning
**Distribution:** Program leadership, skill development team, historical archive
**Retention:** Permanent
**Next Review:** [Date or trigger condition]
