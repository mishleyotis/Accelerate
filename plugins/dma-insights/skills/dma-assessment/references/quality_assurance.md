# Quality Assurance Protocol

Read this file during Phase 8, before any deliverable is shared. Run EVERY check.

---

## Pre-Delivery Validation Checklist

### Section A: Score Integrity

- [ ] All 17 category Final Scores populated in workbook
- [ ] Final Score = min(Raw, Evidence Ceiling, All Applicable Caps) verified for each
- [ ] Workbook Final Score matches EXACTLY in:
  - [ ] Narrative text mentions
  - [ ] Capability scorecard table
  - [ ] Pillar scorecard table
  - [ ] Benchmark comparison table
  - [ ] Chart data points
- [ ] Pillar scores = weighted sum of category scores (verify formula, show work)
- [ ] Overall score = weighted sum of pillar scores using correct sub-vertical weights
- [ ] All weights at each aggregation level sum to 100% (no rounding errors)
- [ ] All scores rounded to 2 decimal places

### Section B: Peer Benchmark Integrity

- [ ] 3-5 peer institutions identified with documented selection rationale
- [ ] Peer scores CALCULATED (not hardcoded) with evidence basis for each
- [ ] Median, P25, P75 calculated from peer scores (verify formula, show work)
- [ ] Same peer median value used consistently across ALL artifacts
- [ ] No peer score is an unexamined outlier (>1.5 from others)
- [ ] Peer Benchmark Calculations appendix complete with full calculation traces

### Section C: Evidence Traceability

- [ ] Every category score has Evidence IDs listed in workbook
- [ ] Every Evidence ID cited exists in the Evidence Index
- [ ] Every quantified claim (%, $, metric) has inline citation (Source, Tier, Date)
- [ ] All T1 sources verified with URL or document reference
- [ ] Absence signals documented where expected evidence was not found
- [ ] Contradictions documented with resolution rationale

### Section D: Caps and Adjustments

- [ ] All severity caps from Issue Register applied
- [ ] All evidence tier caps applied where triggered
- [ ] All cross-pillar dependency caps checked and applied
- [ ] All sentiment caps applied to P2 categories
- [ ] Caps Applied Log complete showing: Raw → Cap → Final for every capped score
- [ ] No score exceeds its evidence ceiling

### Section E: Reasoning Quality

- [ ] Scoring rationale documented for EVERY category (not just low scores)
- [ ] Alternative interpretations considered and documented
- [ ] Counter-arguments addressed for each recommendation
- [ ] Recommendations tied to specific root causes (not generic)
- [ ] Expected outcomes have evidence basis (not just assertion)

### Section E.1: Evidence Ranking Integrity

- [ ] Every evidence item in the evidence index has an ERS score calculated
- [ ] ERS formula applied consistently: (0.35×Tier) + (0.25×Recency) + (0.20×Specificity) + (0.20×Corroboration)
- [ ] Capability narratives cite evidence in descending ERS order
- [ ] Executive summary cites only evidence with ERS ≥ 3.5
- [ ] No recommendation root cause relies solely on evidence with ERS < 2.5
- [ ] Section 12 Evidence Sources sorted by ERS within each tier
- [ ] Corroboration scores reflect genuinely INDEPENDENT sources (not same-author sources)

### Section E.2: Checkpoint Integrity

- [ ] All checkpoint files present in `/home/claude/dma_checkpoints/`
- [ ] Scores in `04_scores.json` match workbook scores
- [ ] Peer benchmarks in `02_peer_benchmarks.json` match all benchmark references
- [ ] Priority scores in `05_priorities.json` match Section 8 of report
- [ ] No stale checkpoint data carried forward after a score revision

### Section F: Narrative Quality

- [ ] No generic statements survive the specificity test
- [ ] No deficit language (gap → area for improvement)
- [ ] Timelines tied to institutional anchors (no "0-6 months")
- [ ] All recommendations include "why THIS solution for THIS institution"
- [ ] Inline citations embedded throughout (not end-listed)
- [ ] SO WHAT analysis present for every major finding

### Section G: Cross-Document Consistency

- [ ] Same score for each category appears in workbook, report, and all tables/charts
- [ ] Same peer median values appear in all artifacts
- [ ] Same trend direction in tables matches chart directions
- [ ] No contradiction between "improving" narrative and "↓" arrow
- [ ] Overall score in executive summary matches calculated overall score
- [ ] Pillar scores in executive summary match workbook pillar scores
- [ ] Institution name spelled identically in all artifacts

### Section G.7: Subcapability Score Differentiation

For each capability across all 4 pillar scoring sheets, count unique scores among subcaps:

- [ ] No capability has 100% identical subcap scores (unless all NO_EVIDENCE → 1.0)
- [ ] No capability has >60% of subcaps sharing the same score (WARN if found)
- [ ] Variation ratio (unique scores / total subcaps) ≥ 0.3 for each capability
- [ ] Differentiation log present showing PASS/WARN/CRITICAL per capability
- [ ] Any capability flagged WARN or CRITICAL has documented justification or was rescored

**Detection script (run on completed workbook):**
```
For each capability in P[N]_Scoring_Detail:
  scores = all Score_1_to_5 values for subcaps in this capability
  unique_count = count of distinct values in scores
  total_count = count of all scores
  mode_pct = count of most common score / total_count
  IF mode_pct > 0.6: FLAG as DIFFERENTIATION_WARNING
  IF unique_count == 1 AND not all NO_EVIDENCE: FLAG as CRITICAL_BLOCK
```

### Section G.8: Evidence Excerpt Completeness

- [ ] Column U (Evidence_Excerpt) populated for every row in all P[N]_Scoring_Detail sheets
- [ ] No Evidence_Excerpt cell is blank or contains only whitespace
- [ ] No Evidence_Excerpt cell is shorter than 30 characters
- [ ] NO_EVIDENCE rows have absence explanation (what was searched, what was not found)
- [ ] Evidence_Excerpt does NOT match these forbidden generic patterns:
  - "Based on available evidence"
  - "Public sources suggest"
  - "Evidence indicates"
  - "Analysis shows"
  (These are summaries, not excerpts — the cell must contain the actual data point)
- [ ] Column V (Source_Document) populated for every row that has evidence
- [ ] Source_Document references specific documents (not "public sources" or "various")

### Section G.9: Forbidden Rationale Pattern Scan

Scan ALL Column R (Scoring_Rationale) cells across all P[N]_Scoring_Detail sheets:

- [ ] ZERO cells contain "Category-based scoring" (CRITICAL — rescore entire capability)
- [ ] ZERO cells contain "Based on public evidence analysis" (CRITICAL)
- [ ] ZERO cells contain "Based on T[N] evidence" without additional specifics (CRITICAL)
- [ ] ZERO cells contain "Evidence suggests M[N] level" without evidence ID (CRITICAL)
- [ ] ZERO cells contain "Score assigned based on available data" (CRITICAL)
- [ ] ZERO cells are shorter than 150 characters (CRITICAL)
- [ ] ZERO cells lack an Evidence_ID reference (E-NNN or INT-XXX-NNN)
- [ ] ZERO cells lack an M-level descriptor reference
- [ ] Spot-check 20 random rationales — all pass institution-specificity test (would this
  text make sense if the institution name were changed? If yes → it's too generic)

### Section G.10: Recommendation Scope Compliance

- [ ] Every recommendation action item tagged as [ZENNIFY] or [CLIENT]
- [ ] No [ZENNIFY]-tagged action falls outside Zennify's 12 solutions
- [ ] No recommendation positions hiring decisions as Zennify deliverables
- [ ] No recommendation positions organizational restructuring as Zennify deliverables
- [ ] No recommendation positions certification/compliance programs as Zennify deliverables
- [ ] Out-of-scope dependencies correctly framed as "[CLIENT] — prerequisite for..." not as
  primary recommendations
- [ ] Each [ZENNIFY] action names a specific solution from the catalog

### Section H: File Completeness

- [ ] Scoring Workbook (.xlsx) complete with all tabs
- [ ] Assessment Report (.docx) complete with all 12 sections + 3 appendices
  - [ ] Section 1: Executive Summary (with Bottom Line, Strengths, Gaps, Recommendation)
  - [ ] Section 2: Assessment Context (Profile, Methodology, Sources, Limitations)
  - [ ] Section 3: Trend Analysis (Financial, Digital Evolution, Sentiment + Chart)
  - [ ] Section 4: Issue Register (Issue Time Map table, Severity Cap Impact)
  - [ ] Section 5: Assessment Results (Pillar Scorecard table, Radar Chart, Heatmap)
  - [ ] Section 6: Pillar Deep Dives (6.1-6.4, each with Scorecard, Calculation, What We See, Why It Matters)
  - [ ] Section 7: Benchmark Comparison (Strategic Pattern, Strengths, Improvement Areas)
  - [ ] Section 8: Gap Prioritization (Gap-to-Solution Mapping table, Priority Methodology, Critical Gaps)
  - [ ] Section 9: Recommendations (each with Root Cause, Solution, Why This, Outcomes, Risk of Inaction)
  - [ ] Section 10: Transformation Roadmap (Phases 1-3, Trajectory table, Investment Summary)
  - [ ] Section 11: Data Gaps & Confidence (What We Couldn't Assess, N/A Capabilities, Next Steps)
  - [ ] Section 12: Evidence Sources (grouped by tier, sorted by ERS within tier)
  - [ ] Appendix A: Capability Definitions (all 17)
  - [ ] Appendix B: Maturity Level Definitions (M1-M5)
  - [ ] Appendix C: Sub-Vertical Pillar Weights table
- [ ] Charts generated from workbook data (not independently created)
- [ ] Files saved to appropriate output directory
- [ ] File naming follows convention: `[Institution]_DMA_[Artifact]_[YYYYMMDD].[ext]`

---

## Reconciliation Procedure

If ANY mismatch is detected during validation:

### 1. Identify the Source of Truth
The **Scoring Workbook Final Score column** is ALWAYS the authoritative source.
No exceptions. No overrides.

### 2. Trace the Error
- Where did the incorrect number appear?
- Was it a formula error, copy error, manual entry, or rounding issue?
- Did it propagate to other calculations?

### 3. Correct ALL Artifacts
- Update narrative to match workbook
- Update tables to match workbook
- Regenerate charts from workbook data
- Update any derived calculations (pillar scores, overall, gaps)

### 4. Revalidate
- Run the full validation checklist again
- Confirm all artifacts now consistent
- Pay special attention to any numbers that were derived from the corrected value

### 5. Document the Correction
- Note what was wrong, what was fixed, and where
- This prevents the same error pattern in future assessments

**RULE: NEVER DELIVER WITH KNOWN MISMATCHES**

---

## Common Error Patterns

These are the most frequent errors found in assessments. Check for each specifically:

1. **Peer median calculated differently in different places** — Always use the same formula and the same peer scores everywhere
2. **Pillar score doesn't match weighted sum of categories** — Usually a weight that doesn't sum to 100%
3. **Cap applied in narrative but not in workbook (or vice versa)** — Check caps log against all artifacts
4. **Score changed during analysis but not updated everywhere** — After any score change, trace through ALL downstream effects
5. **Different rounding in different artifacts** — Always round to 2 decimal places, always round at the same step
6. **Peer scores from different time periods mixed** — All peer evidence should be from the same assessment window
