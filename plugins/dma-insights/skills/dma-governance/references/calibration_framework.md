# Calibration Framework

This file defines the methodology for measuring cross-assessment consistency, detecting
drift, and maintaining scoring reliability across multiple assessments.

**Minimum requirement**: ≥2 completed assessments with run manifests to run calibration.
Full calibration power requires ≥5 assessments within the same sub-vertical.

---

## 1. Calibration Metrics

### 1.1 Score Distribution Metrics

Computed at category level (16 categories) across all assessments in the comparison set.

| Metric | Formula | Purpose |
|--------|---------|---------|
| Mean category score | `avg(category_score)` across assessments | Central tendency baseline |
| Median category score | `median(category_score)` | Robust central tendency |
| Standard deviation | `stdev(category_score)` | Expected variance |
| Interquartile range | `Q3 - Q1` | Spread measure robust to outliers |
| Skewness | `3(mean - median) / stdev` | Direction of score bias |

**Baselines**: After ≥5 assessments, compute baselines per sub-vertical + size tier
combination. Store in Program Repository for ongoing comparison.

### 1.2 Evidence Discipline Metrics

| Metric | Formula | What It Measures |
|--------|---------|-----------------|
| Average ERS | `avg(ers)` across all evidence items | Overall evidence quality |
| Tier diversity index | `1 - sum(tier_pct²)` (Herfindahl) | Evidence triangulation quality |
| Sources per subcap | `total_evidence / total_subcaps` | Evidence depth |
| Single-source rate | `single_source_subcaps / total_subcaps` | Evidence thinness |
| Staleness rate | `stale_evidence_items / total_evidence` | Evidence recency |

### 1.3 Scoring Behavior Metrics

| Metric | Formula | What It Measures |
|--------|---------|-----------------|
| Cap rate | `capped_subcaps / total_subcaps` | How often evidence caps bind |
| Adjustment rate | `adjusted_subcaps / total_subcaps` | How often adjustments fire |
| Contradiction rate | `contradictions / total_subcaps` | Evidence conflict frequency |
| Resolution consistency | `% using ERS_RANKING vs T1T2_OVERRIDE` | Whether resolution rules are applied uniformly |
| Confidence distribution | `{HIGH: %, MEDIUM: %, LOW: %}` | Confidence calibration |

### 1.4 Assessor-Specific Metrics (when multiple assessors exist)

| Metric | Computation | Threshold |
|--------|-------------|-----------|
| Harshness index | `assessor_mean - program_mean` | FLAG if \|index\| > 0.5 |
| Category bias | `assessor_cat_mean - program_cat_mean` per category | FLAG if \|bias\| > 0.75 on ≥3 categories |
| Confidence tendency | `assessor_HIGH% - program_HIGH%` | FLAG if delta > 20pp |
| Evidence effort | `assessor_sources_per_subcap - program_avg` | FLAG if < 50% of program avg |

---

## 2. Drift Detection

Drift is a systematic change in scoring behavior over time, often invisible to individual
assessors.

### 2.1 Types of Drift

| Type | What It Looks Like | Detection Method |
|------|-------------------|-----------------|
| Score inflation | Mean scores trend upward over time | Linear regression on mean score vs. assessment date |
| Score compression | Scores cluster around 2.5-3.0 over time | Standard deviation decreasing over time |
| Evidence laziness | Sources per subcap declining | Trend analysis on evidence depth |
| Confidence inflation | HIGH confidence increasing without ERS improvement | Compare confidence distribution vs ERS over time |
| Cap avoidance | Cap rate declining without evidence improvement | Compare cap rate vs tier distribution over time |

### 2.2 Drift Detection Algorithm

For each metric in Section 1:

1. Compute the metric for each assessment, ordered by date
2. Fit a simple linear trend (OLS regression on metric vs. assessment ordinal)
3. Flag if:
   - Slope is statistically significant (p < 0.10) AND
   - Magnitude exceeds the "concern threshold" for that metric

**Concern thresholds** (tuned after ≥10 assessments):

| Metric | Concern Threshold |
|--------|------------------|
| Mean category score | >0.15 per assessment |
| Standard deviation | Decrease >0.1 per assessment |
| Sources per subcap | Decrease >0.3 per assessment |
| HIGH confidence % | Increase >5pp per assessment |
| Cap rate | Change >5pp per assessment |

### 2.3 Drift Response

| Drift Type | Immediate Action | Program Action |
|------------|-----------------|----------------|
| Score inflation | Flag in calibration report | Review anchor cases, retrain |
| Score compression | Flag in calibration report | Review rubric clarity |
| Evidence laziness | Flag as HIGH | Add evidence depth to QA checks |
| Confidence inflation | Flag as MEDIUM | Enforce ERS-confidence cross-checks |
| Cap avoidance | Flag as HIGH | Review cap rule clarity |

---

## 3. Anchor Case Calibration

Anchor cases are curated assessment scenarios used to test assessor consistency.

### 3.1 Anchor Case Requirements

Each anchor case must include:
- A curated evidence pack (10-30 evidence items across T1-T5)
- Expected subcap scores with tolerance ranges
- Expected caps that should trigger
- Expected contradictions and their resolutions
- Canonical rationale examples

### 3.2 Anchor Case Coverage

Maintain ≥3 anchor cases covering:

| Case | Profile | Key Testing Focus |
|------|---------|------------------|
| Case A: Sparse Evidence | Small institution, public-only | Evidence ceilings, NO_EVIDENCE handling, N/A logic |
| Case B: Contradictory Evidence | Medium institution with mixed signals | T1/T2 vs T3 conflicts, contradiction resolution, confidence |
| Case C: Dependency Cascade | Large institution with governance gaps | Cross-pillar caps, two-pass algorithm, cascading |
| Case D: High Maturity | Mega institution with strong evidence | Score precision (0.1 rules), ceiling non-binding, HIGH confidence |

### 3.3 Anchor Scoring Protocol

1. Assessor scores the anchor case independently (no reference to expected scores)
2. Governance skill compares results against expected values
3. Flag any subcap outside tolerance (±0.5 at subcap, ±0.25 at category)
4. Generate assessor-specific calibration report

---

## 4. Calibration Report Output

```markdown
=== CALIBRATION REPORT — [Date] ===
Assessments compared: [N]
Sub-vertical: [X] | Size tier: [X]

## Score Distribution
[Table: category × assessment, with mean/median/stdev row]

## Evidence Discipline
[Table: metric × assessment]

## Scoring Behavior
[Table: metric × assessment]

## Drift Flags
[List of any metric trends exceeding concern thresholds]

## Assessor-Specific Flags (if applicable)
[Per-assessor harshness index, category bias, confidence tendency]

## Recommendations
[Targeted actions: rubric clarifications, retraining needs, evidence collection guidance]
=== END CALIBRATION REPORT ===
```

---

## 5. Comparability Across Rubric Versions

When rubric version changes, the calibration framework must track:

1. **Version boundary markers**: Which assessments used which rubric version
2. **Bridge mapping**: Back-test ≥2 prior assessments under the new rubric to quantify
   expected score shifts per category
3. **Adjustment factors**: If systematic shifts are found, document them as "comparability
   notes" attached to the peer benchmark dataset
4. **Policy**: Never silently compare assessments across major version changes without
   disclosing the version difference and any known systematic shifts
