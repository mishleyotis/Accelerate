# Evidence Ranking System

Read this file during Phase 1 (when building the evidence index) and Phase 7 (when writing
the report and deciding citation order).

---

## Evidence Rank Score (ERS)

Every evidence item receives a composite score that determines its citation priority,
weight in scoring decisions, and prominence in the final report.

```
ERS = (0.35 × Tier_Score) + (0.25 × Recency_Score) + (0.20 × Specificity_Score) + (0.20 × Corroboration_Score)
```

ERS ranges from 1.0 (lowest quality) to 5.0 (highest quality).

---

## Factor Scoring Details

### Tier Score (Weight: 35%)

| Tier | Score | Rationale |
|------|-------|-----------|
| T1 — Regulatory/Audited | 5.0 | Independently verified, legally authoritative |
| T2 — Official Disclosures | 4.0 | Publicly filed, liability for misstatement |
| T3 — Third-Party Analysis | 3.0 | Independent perspective, professional standards |
| T4 — Internal (Unvalidated) | 2.0 | Potentially biased, no external verification |
| T5 — Marketing/Claims | 1.0 | Explicitly promotional, no accountability |

### Recency Score (Weight: 25%)

| Age | Score | Label |
|-----|-------|-------|
| Current year (trailing 12 months) | 5.0 | CURRENT |
| Prior year (12-24 months) | 4.0 | RECENT |
| 2 years ago (24-36 months) | 3.0 | DATED |
| 3 years ago (36-48 months) | 2.0 | STALE |
| 4+ years ago | 1.0 | ARCHIVAL |

Note: For trend analysis, archival evidence is valuable for trajectory, but should not
drive current-state scoring. Apply recency score to scoring decisions only.

### Specificity Score (Weight: 20%)

| Specificity Level | Score | Example |
|------------------|-------|---------|
| Quantified metric with methodology | 5.0 | "STP rate: 72.3%, measured monthly across all loan products" |
| Quantified metric without methodology | 4.0 | "STP rate: approximately 72%" |
| Specific qualitative with examples | 3.0 | "Implemented RPA for 3 lending processes: origination, servicing, collections" |
| General qualitative claim | 2.0 | "Pursuing automation across lending operations" |
| Vague or aspirational | 1.0 | "Committed to operational excellence through digital transformation" |

### Corroboration Score (Weight: 20%)

| Corroboration Level | Score | Description |
|--------------------|-------|-------------|
| 3+ independent sources agree | 5.0 | Multiple unrelated sources confirm the same fact |
| 2 independent sources agree | 4.0 | Two unrelated sources confirm |
| Single source, T1-T2 | 3.0 | Only one source, but high-authority |
| Single source, T3 | 2.0 | Only one source, moderate authority |
| Single source, T4-T5 | 1.0 | Only one source, low authority |

"Independent" means the sources have different origins — e.g., CFPB data + Annual Report
are independent. Annual Report + Investor Presentation from the same institution are NOT
independent (same author, same incentives).

---

## Worked Examples

### Example 1: High-ERS Evidence

```
Evidence: "App rating of 4.2 stars based on 12,450 reviews"
Source: iOS App Store (T3, current)
Corroborated by: CFPB complaints declining 18% YoY (T1, current) + Glassdoor reviews
  mention "improved mobile platform" (T3, current)

Tier Score: 3.0 (T3)
Recency Score: 5.0 (current)
Specificity Score: 5.0 (exact metric with volume)
Corroboration Score: 5.0 (3 independent sources)

ERS = (0.35 × 3.0) + (0.25 × 5.0) + (0.20 × 5.0) + (0.20 × 5.0)
    = 1.05 + 1.25 + 1.00 + 1.00 = 4.30

Interpretation: HIGH-quality evidence. Lead with this in the P2C3 narrative.
```

### Example 2: Low-ERS Evidence

```
Evidence: "Industry-leading digital capabilities"
Source: Institution website About page (T5, current)
Corroborated by: Nothing

Tier Score: 1.0 (T5)
Recency Score: 5.0 (current)
Specificity Score: 1.0 (vague, aspirational)
Corroboration Score: 1.0 (single source, T5)

ERS = (0.35 × 1.0) + (0.25 × 5.0) + (0.20 × 1.0) + (0.20 × 1.0)
    = 0.35 + 1.25 + 0.20 + 0.20 = 2.00

Interpretation: LOW-quality evidence. Do not cite as supporting evidence for any
M3+ score. May mention only as contrast with higher-ERS contradicting evidence.
```

### Example 3: Stale but Authoritative Evidence

```
Evidence: "NCUA examination rated 2 (satisfactory) with no MRAs"
Source: NCUA exam results (T1, 3 years ago)
Corroborated by: No newer exam data available

Tier Score: 5.0 (T1)
Recency Score: 2.0 (3 years ago)
Specificity Score: 4.0 (specific rating, but no detail on sub-areas)
Corroboration Score: 3.0 (single source, T1)

ERS = (0.35 × 5.0) + (0.25 × 2.0) + (0.20 × 4.0) + (0.20 × 3.0)
    = 1.75 + 0.50 + 0.80 + 0.60 = 3.65

Interpretation: MEDIUM-HIGH quality — authoritative but dated. Use with recency
caveat: "As of the most recent available examination (3 years prior)..." and
flag that current status may differ.
```

---

## Citation Priority Rules

### In Capability Narratives
1. Open with the highest-ERS evidence (leads the analysis)
2. Cite supporting evidence in descending ERS order
3. Cite constraining/negative evidence in descending ERS order
4. In reconciliation sections, the higher-ERS evidence wins unless tier hierarchy overrides

### In Executive Summary
- Cite only evidence with ERS ≥ 3.5 (high-quality only)
- If no evidence meets threshold for a finding, add confidence qualifier

### In Recommendations
- Root cause analysis: Cite evidence with ERS ≥ 3.0
- Expected outcomes: Cite peer evidence or benchmarks (typically T3, ERS ≥ 3.0)
- Never base a recommendation solely on evidence with ERS < 2.5

### In Evidence Sources Section (Section 12)
- Group by tier (T1 first, T5 last)
- Within each tier, sort by ERS descending
- Include ERS score parenthetically: "(ERS: 4.30)"

---

## Edge Cases

### ERS Tie-Breaking
When two evidence items have the same ERS:
1. Higher tier wins
2. If same tier: more recent wins
3. If same recency: more specific wins
4. If still tied: the one with more corroboration wins

### Contradictory Evidence of Similar ERS
When conflicting evidence items have ERS within 0.5 of each other, the contradiction is
"legitimate" — neither clearly outweighs the other. In this case:
1. Document both in the narrative with full citations
2. Apply the resolution hierarchy (T1 > T2 > T3, etc.)
3. Reduce confidence to MEDIUM or LOW
4. Default to the conservative (lower) score interpretation
5. Flag in Section 11 (Data Gaps & Confidence) as an unresolved tension

### Absence as Evidence
When evidence is expected but absent (e.g., no CDO listed for an M3+ data governance claim),
the absence itself receives an ERS:
- Tier: Same as the source that was checked (e.g., T3 if LinkedIn was searched)
- Recency: Current (the search was performed now)
- Specificity: 4.0 (specific absence — "no CDO found on LinkedIn or leadership page")
- Corroboration: Checked 2+ sources = 4.0; checked 1 source = 2.0

---

## Evidence Index Extension

When building the evidence index (Phase 1), add these columns for ERS:

| Column | Values |
|--------|--------|
| tier_score | 1.0-5.0 |
| recency_score | 1.0-5.0 |
| specificity_score | 1.0-5.0 |
| corroboration_score | 1.0-5.0 |
| ers_total | Calculated composite |
| corroborating_ids | List of other evidence IDs that confirm this item |

Save ERS scores in the `01_evidence_index.json` checkpoint. They are used throughout
scoring, narrative writing, and report generation.
