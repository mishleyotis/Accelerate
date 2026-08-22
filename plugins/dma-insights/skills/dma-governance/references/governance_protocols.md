# Governance Protocols

This file defines how the DMA program evolves over time: how changes are proposed,
reviewed, tested, and released without breaking comparability or defensibility.

---

## 1. Version Control

### 1.1 Versioned Artifacts

| Artifact | Current Version | What Changes Require Bump |
|----------|----------------|--------------------------|
| Rubric (scoring rules, ceilings, caps, adjustments) | 5.0 | Any scoring logic change |
| Taxonomy (subcaps, capabilities, categories, pillars) | 5.0 | Any structural change to what is scored |
| Templates (report structure, workbook layout) | 5.0 | Any output format change |
| Peer Methodology (how peers are scored/proxied) | 5.0 | Any benchmarking methodology change |
| Governance Skill | 1.0 | Any audit check, calibration metric, or golden case change |

### 1.2 Version Numbering

`MAJOR.MINOR` where:
- **MAJOR**: Breaking change that affects score comparability across versions. Requires
  bridge mapping and CCB approval.
- **MINOR**: Non-breaking change (clarifications, editorial, additive checks). Backward
  compatible. Still requires regression pass.

Examples:
- Adding a new subcapability to taxonomy → MAJOR (5.0 → 6.0)
- Changing a ceiling value → MAJOR
- Clarifying an ambiguous rubric rule without changing scoring outcomes → MINOR (5.0 → 5.1)
- Adding a new QA check → MINOR
- Fixing a typo in report template → MINOR

### 1.3 Version Tracking

Every assessment's `run_manifest.json` records all artifact versions. The Program Repository
stores the mapping: `assessment_id → {rubric_version, taxonomy_version, ...}`.

---

## 2. Change Classification

### Class 0: Editorial

**Definition**: Changes that affect wording, formatting, or presentation but have ZERO
impact on scoring logic or output structure.

**Examples**: Fixing typos, improving rubric clarity without changing meaning, reformatting
tables, updating branding colors.

**Process**:
1. Propose change
2. Peer review (another team member confirms no scoring impact)
3. Apply directly (no regression required)
4. MINOR version bump

### Class 1: Interpretation Clarification

**Definition**: Changes that clarify ambiguous rules. Intended scoring impact is minimal
but non-zero (edge cases may shift by ±0.25 at subcap level).

**Examples**: Specifying what "recent" means in a staleness rule, clarifying which evidence
types count as "T2 vs T3" for a specific source, tightening a confidence rubric threshold.

**Process**:
1. Propose change with rationale
2. Impact assessment: estimate which subcaps/categories could shift
3. Run regression suite (PARTIAL PASS acceptable)
4. CCB approval (lightweight — program lead + 1 SME)
5. Apply and bump MINOR version
6. Document in release notes

### Class 2: Scoring Logic Change

**Definition**: Changes that intentionally alter scoring outcomes. Score comparability
across versions may be affected.

**Examples**: Changing a ceiling value, adding/removing a cap rule, changing the ERS
formula weights, adding a new dependency cap, modifying tier definitions.

**Process**:
1. Propose change with full rationale and expected impact
2. Impact assessment: back-test on ≥2 prior assessments to quantify shifts
3. Run full regression suite (PASS required — PARTIAL PASS not acceptable)
4. Run anchor case calibration
5. CCB approval (full board: program lead + domain SME + QA lead + delivery lead)
6. Produce comparability plan:
   - Bridge mapping (expected category-level shifts)
   - Benchmark adjustment factors (if needed)
   - Disclosure language for cross-version comparisons
7. Apply and bump MAJOR version
8. Full release notes + comparability statement

---

## 3. Change Control Board (CCB)

### 3.1 Composition

| Role | Responsibility | Required For |
|------|---------------|-------------|
| Program Lead | Final approval, priority decisions | All Class 1/2 |
| Domain SME | Subject matter validity | Class 1/2 |
| QA Lead | Regression pass verification | Class 1/2 |
| Delivery Lead | Practical implementation impact | Class 2 only |

### 3.2 CCB Decision Record

Every CCB decision is documented:

```markdown
=== CCB DECISION — [Change ID] [Date] ===
Change Class: [0/1/2]
Proposer: [Name]
Description: [What's changing]
Rationale: [Why]
Impact Assessment: [Expected scoring shifts]
Regression Result: [PASS/PARTIAL/FAIL]
Calibration Impact: [None/Minimal/Significant]
Decision: APPROVED / REJECTED / DEFERRED
Conditions: [Any conditions on approval]
Effective Date: [When the change takes effect]
Version Bump: [X.Y → X.Z]
=== END DECISION ===
```

---

## 4. Program Learning Loop

### 4.1 How Issues Become Improvements

```
Assessment complete
    ↓
Layer 2 audit → Issue Register + Patch Block
    ↓
Patch Block contains:
    ├── Error log additions (apply immediately after review)
    ├── Regression test proposals (apply after CCB lightweight review)
    └── Rubric tweak proposals (apply after full CCB process)
    ↓
CCB reviews rubric tweaks → classifies as Class 0/1/2
    ↓
Appropriate process executed → version bumped → regression passed
    ↓
New version deployed for next assessment
```

### 4.2 Error Log Pipeline

1. Layer 2 detects novel issue pattern during audit
2. Patch block includes proposed ERR entry (with prevention rule, phase tag, severity)
3. Human operator reviews the ERR entry:
   - Confirms it's a genuine pattern (not a one-off data quirk)
   - Validates the prevention rule is actionable
4. Approved entries are appended to `${CLAUDE_PLUGIN_ROOT}/skills/dma-assessment/references/qa_error_log.md` (the Layer 1 skill)
5. Future assessments automatically load these prevention rules at phase gates

### 4.3 Regression Test Pipeline

1. Layer 2 identifies a check that revealed an issue not caught by existing tests
2. Patch block includes proposed test addition (invariant, golden case, or behavioral check)
3. QA lead reviews:
   - Is the test deterministic? (Same inputs → same pass/fail)
   - Is the tolerance appropriate?
   - Does it conflict with existing tests?
4. Approved tests are added to `${CLAUDE_PLUGIN_ROOT}/skills/dma-assessment/references/regression_tests.md` (Layer 1) and
   `references/regression_suite.md` in Layer 2

### 4.4 Rubric Tweak Pipeline

1. Layer 2 identifies systematic issue suggesting rule ambiguity or gap
2. Patch block includes proposed change with:
   - Change description
   - Affected files/sections
   - Expected scoring impact
   - Suggested change class
3. CCB evaluates using the Class 0/1/2 process
4. If approved: implement, regression test, version bump, release

---

## 5. Benchmark Defensibility

### 5.1 What Makes Benchmarks Defensible

A benchmark is defensible when a reasonable third party could:
1. Understand the methodology (transparency)
2. Verify the scoring of individual institutions (traceability)
3. Confirm that comparisons are valid (comparability)
4. Trust that the process is consistent (calibration)

### 5.2 Defensibility Checklist

| Requirement | How We Ensure It |
|-------------|-----------------|
| Methodology transparency | Published rubric + peer methodology + scoring decision tree |
| Scoring traceability | Workbook + evidence index + rationale + caps log |
| Comparison validity | Peer proxy disclosure + version-consistent benchmarking |
| Process consistency | Calibration framework + regression suite + error log |
| Version awareness | Run manifest tracks all versions; cross-version comparisons disclosed |
| Audit trail | Governance skill produces issue register + QA verdict for every assessment |

### 5.3 Cross-Version Comparability Policy

**Default**: Only compare assessments scored under the same MAJOR rubric version.

**Exception (bridged comparison)**: Cross-version comparison is permitted when:
1. A bridge mapping has been produced (back-test ≥2 assessments under both versions)
2. Category-level shift estimates are documented
3. The comparison includes a disclosure: "Institution A was scored under Rubric v[X],
   Institution B under v[Y]. Estimated scoring differential: [details]."

**Never**: Compare assessments across MAJOR taxonomy versions without explicit restructuring
mapping.

---

## 6. Release Notes Template

```markdown
=== RELEASE NOTES — [Artifact] v[X.Y] — [Date] ===

## Summary
[1-2 sentence description of what changed]

## Change Class: [0/1/2]

## Changes
[Numbered list of specific changes]

## Files Modified
[List of files and sections changed]

## Scoring Impact
[Expected impact on scores: None / Minimal / Significant]
[Categories most likely affected]

## Regression Result
[PASS / PARTIAL PASS — with details]

## Comparability Statement
[For Class 2: How this affects cross-version benchmarking]
[For Class 0/1: "No comparability impact expected"]

## CCB Decision Reference
[Link or ID to CCB decision record]
=== END RELEASE NOTES ===
```
