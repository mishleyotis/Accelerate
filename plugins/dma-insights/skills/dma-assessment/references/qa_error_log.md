# QA Error Log & Prevention Framework

## Purpose

This persistent error log tracks recurring mistakes from DMA assessments and enforces prevention rules. The log serves three functions:

1. **Detection** — Identifies patterns of errors across assessments
2. **Prevention** — Documents root causes and prevention rules to stop recurrence
3. **Severity Classification** — Prioritizes which errors block delivery (CRITICAL) vs. require remediation (HIGH/MEDIUM)

Every error log entry includes the phase where the error was caught, the root cause, and a specific prevention rule to apply in future assessments.

---

## Error Entry Template

```
### ERR-[ID] [PHASE:N] [SEVERITY]: [Error Title]

**Description:**
[2-3 sentence description of what went wrong]

**Root Cause:**
[Why did this error occur? Common root causes: process skipped, misunderstanding of requirement, tool limitation, context overflow]

**Prevention Rule:**
[Specific rule to prevent this error in future assessments]

**Occurrences:**
- Count: [X]
- Last Seen: [DATE]
- Affected Institutions: [List]

**Detection Trigger:**
[How to detect this error in QA — specific check or pattern to look for]
```

---

## Logged Errors

### ERR-001 [PHASE:4] CRITICAL: Category-Level Scoring Instead of Subcapability-Level

**Description:**
Assessment generated only 17 scores (one per category across P1-P4) instead of 851 subcapability scores. The scoring_detail sheets have single aggregate rows per category rather than full subcapability-level detail. This breaks the entire assessment model and makes evidence linkage impossible.

**Root Cause:**
- Misunderstanding that "scoring toolkit" column count = number of scores to generate
- Confusion between category weight and subcapability structure
- Attempt to "simplify" assessment by skipping granular scoring
- Not reading the Pillar Scoring Toolkit XLSX with all subcapability row identifiers

**Prevention Rule:**
1. BEFORE scoring, count expected subcapabilities from the catalogue:
   P1 205, P2 292, P3 164, P4 190 (total 851 at full scope)
2. Read the Pillar Scoring Toolkit XLSX BEFORE starting Phase 4
3. Verify scoresheet row count matches expected subcap count (±5%) BEFORE finalizing workbook
4. Mark each subcapability with explicit SubCap_ID from toolkit
5. If subcap count <750, HALT and investigate missing structure

**Occurrences:**
- Count: 4
- Last Seen: Gesa CU assessment (2026-03-01)
- Affected Institutions: Gesa CU (2026-03-01) — all 707 subcaps scored uniformly per category

**Detection Trigger:**
- Calculation_Chain sheet has only 17 rows (category level)
- Evidence_Index sheet has only 17 evidence mappings (category-wide, not subcap-specific)
- Final workbook <2MB (expected 5-8MB for full detail)
- P[N]_Scoring_Detail sheets show 100% identical scores within each category
- Scoring_Rationale column contains "Category-based scoring" for any row

---

### ERR-002 [PHASE:4] CRITICAL: Generic Rationales Without Evidence Linkage

**Description:**
Scoring_detail sheet contains rationales that are <150 characters, lack evidence IDs, and don't reference maturity descriptor (M1-M5) language. Examples: "Good compliance structure," "Strong automation," "Data capabilities developing" — no proof, no traceability.

**Root Cause:**
- Assessor rushing through scoring to meet timeline
- Confusion about what "rationale" means — treating it as comment vs. argument
- Not reading the skill's Argument-Based Reasoning specification
- Failing to build CLAIM→EVIDENCE→REASONING→COUNTER→REBUTTAL structure

**Prevention Rule:**
1. Every rationale MUST be ≥150 characters
2. Every rationale MUST cite at least one Evidence_ID (e.g., "E-001, INT-BOARD-003")
3. Every rationale MUST reference the M1-M5 descriptor used to justify the score (e.g., "meets M2 indicator: documented process with..." not just "good")
4. Template: "[Capability] assessed at M[X] based on [Evidence_ID evidence description] which demonstrates [M[X] descriptor]. [Differentiating factor vs. M[X-1]]."
5. Before finalizing, spot-check 20 random rationales — all must pass 150-char + evidence + descriptor test

**Occurrences:**
- Count: 6
- Last Seen: Gesa CU assessment (2026-03-01)
- Affected Institutions: Gesa CU (2026-03-01) — all 707 rationales read "Category-based scoring"

**Detection Trigger:**
- Grep/search for rationales with <150 characters
- Find rationales without any Evidence_ID reference
- Detect forbidden generic phrases (list in communication_standards.md)

---

### ERR-003 [PHASE:1,4] HIGH: Evidence Mapped at Category Level, Not Subcapability Level

**Description:**
Evidence index shows "[Evidence_ID] supports P1C1" instead of "[Evidence_ID] supports P1C1→P1C1.1, P1C1.2, P1C1.4" (specific subcapabilities). This creates ambiguity during scoring and allows assessor to apply the same evidence to unrelated subcaps.

**Root Cause:**
- Treating category and subcapability as equivalent
- Skipping the capability_criteria.md review (which maps specific evidence to diagnostic questions)
- Not using the Pillar Scoring Toolkit to understand subcap structure
- Mapping at evidence collection time rather than scoring time

**Prevention Rule:**
1. During Phase 1 (document processing), extract facts but DON'T map to capabilities yet
2. During Phase 4 (scoring), for EACH subcapability, review diagnostic question and identify which evidence facts directly answer that question
3. Build evidence mapping at scoring time: evidence → diagnostic question → subcapability
4. In Evidence_Linkage_Matrix sheet, include explicit subcap_ID column with granular mapping (e.g., "P1C1.1, P1C1.2" not just "P1C1")
5. Validation: sum of subcapabilities per evidence should be >1 (corroboration) but typically <5 (overfitting)

**Occurrences:**
- Count: 5
- Last Seen: Gesa CU assessment (2026-03-01)
- Affected Institutions: Gesa CU (2026-03-01) — all subcaps within each category cite identical evidence ID sets

**Detection Trigger:**
- Evidence_Linkage_Matrix has only [Category_ID] not [SubCap_ID] column
- Average subcaps per evidence = 1.0 (should be 1.3-2.5, indicating proper triangulation)
- Scoring_detail sheet has identical evidence_IDs for all subcaps within a category

---

### ERR-004 [PHASE:4] HIGH: Excessive Score Precision Without Quantitative Justification

**Description:**
Workbook contains precise scores like 3.81, 3.94, 3.67 with no quantitative justification (e.g., weighted aggregation formula, component breakdown). Default precision should be 0.5; higher precision requires explicit justification.

**Root Cause:**
- Belief that "more precise = more credible"
- Manual score entry with no formula documentation
- Not reading workbook_specification.md precision rules
- Confusing confidence level (HIGH/MEDIUM/LOW) with score precision

**Prevention Rule:**
1. Default score precision = 0.5 (i.e., scores of 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0)
2. To justify precision of 0.1, add explicit column: "Precision_Justification" = formula or component breakdown (e.g., "Average of 5 subcaps: 3.4, 3.6, 3.8, 3.9, 3.8 = 3.7")
3. Rationale must include quantified reasoning (e.g., "3 of 5 subcaps at M3, 2 at M4 → weighted average 3.4")
4. If rationale contains no numbers, precision must be 0.5
5. QA check: Flag any score with 0.1 precision lacking justification formula

**Occurrences:**
- Count: 2
- Last Seen: Assessment cycle 5 (month 2)
- Affected Institutions: [Reserve for tracking]

**Detection Trigger:**
- Scores contain decimals to 0.01 or 0.05 place
- Precision_Justification column is missing
- Rationale text has no numerical breakdown (no "X of Y" pattern)

---

### ERR-005 [PHASE:4] HIGH: Calculation_Chain Starts at Capability Level, Not Subcap Level

**Description:**
Calculation_Chain sheet begins with Capability rows (17 per pillar) instead of starting with all SubCapability rows (851 at full scope). This makes it impossible to audit the aggregation from subcap→capability→category→pillar→overall.

**Root Cause:**
- Not reading workbook_specification.md Calculation_Chain requirements
- Misunderstanding "aggregation chain" to mean "final aggregation only" not "full trace"
- Copy-pasting from prior assessment with wrong structure
- Confusion about sheet purpose vs. summary

**Prevention Rule:**
1. Calculation_Chain sheet MUST have this row structure (in order):
   - Row 1: All subcapabilities (851 rows at full scope) with raw scores and subcap weights
   - Rows 838-843: Capability aggregates (raw capability scores)
   - Rows 844-847: Category aggregates (if applicable)
   - Rows 848-851: Pillar aggregates
   - Row 852: Overall score
2. Each row must show: [Input_Values] × [Weights] = [Output_Value]
3. Verify row count before submitting workbook
4. Validation formula in QA sheet must reference this sequence

**Occurrences:**
- Count: 1
- Last Seen: Assessment cycle 4 (month 2)
- Affected Institutions: [Reserve for tracking]

**Detection Trigger:**
- Calculation_Chain has <200 rows (should have >850)
- First data row is Capability ID, not SubCap ID
- No subcapability aggregation shown

---

### ERR-006 [PHASE:7] MEDIUM: Report Narratives Disconnected from Workbook Scores

**Description:**
Narrative report states "P2 is a strength at 3.8" but workbook shows P2 = 3.2. Or narrative says "P3C2 needs remediation" but score is 3.5. These disconnects undermine credibility and confuse client.

**Root Cause:**
- Report written before workbook finalized; workbook scores changed but narrative not updated
- Two people writing report and workbook without reconciliation
- Report sourced from preliminary workbook version that was superseded
- Not running final integrity check before delivery

**Prevention Rule:**
1. MANDATE: Workbook MUST be final and locked before narrative writing begins
2. Before writing each narrative section, export scores from final workbook into writer's reference doc
3. Use this reference to write section, with live links to workbook evidence
4. After narrative draft, run automated integrity check: grep all score numbers in report → verify in final workbook
5. QA check: "Report_Content_Integrity" test compares report scores to workbook (must be 100% match)

**Occurrences:**
- Count: 2
- Last Seen: Assessment cycle 5 (month 2)
- Affected Institutions: [Reserve for tracking]

**Detection Trigger:**
- Report pillar/capability score differs from workbook by >0.1 points
- Report statement contradicts workbook logic (e.g., "below median" but actually above)
- QA Validation_Log shows "Report Content Integrity" = FAIL

---

### ERR-007 [PHASE:2] MEDIUM: Peer Benchmarks Presented as Certainties Without Quality Grades

**Description:**
Narrative states "peers median 3.4" without noting the confidence level (based on what? how many peers? how recent?). This makes peer comparison look like objective fact when it may be based on sparse data or stale scores.

**Root Cause:**
- Not reading peer_benchmarking.md specification for quality grades
- Confusing benchmark with definitive standard
- Missing metadata on peer data recency and coverage
- Not documenting peer selection rationale

**Prevention Rule:**
1. Every peer benchmark claim MUST include quality grade: GOLD (5+ peers, <12 months old, direct data) | SILVER (3-4 peers, <24 months, some estimation) | BRONZE (2-3 peers, >24 months, high estimation)
2. Format: "Peer median is 3.4 [SILVER — 3 peers, avg age 18 months]"
3. In report, include Peer_Selection section explaining: who the peers are, why selected, when data sourced, confidence level
4. For BRONZE-level benchmarks, add caveat language: "Based on limited peer data, this comparison should be treated as directional rather than definitive"
5. QA check: Scan for all peer mentions → verify quality grade present

**Occurrences:**
- Count: 3
- Last Seen: Assessment cycle 5 (month 2)
- Affected Institutions: [Reserve for tracking]

**Detection Trigger:**
- Peer median stated without [GOLD/SILVER/BRONZE] grade
- Peer selection rationale missing from report
- Peer data dates not documented in peers/peer_selection.json

---

### ERR-008 [PHASE:QA] MEDIUM: QA Checks Skipped or Superficial — No Phase Gate Acknowledgment

**Description:**
QA validation_log shows spot checks only (5 random rationales) instead of comprehensive validation. Or QA is marked "PASS" without documented Phase Gate checks. This creates false confidence that assessment passed all safeguards.

**Root Cause:**
- Time pressure — QA treated as optional final step rather than mandatory gate
- Not reading comprehensive_safeguards.md (8 layers, 56+ checks)
- Misunderstanding that QA = final polish vs. QA = validation of methodology
- Incomplete checkpoint system — some phases skipped

**Prevention Rule:**
1. QA MUST run all 8 safety layers (INP, DOC, ANA, SCR, OUT, CON, WB, FIN)
2. Each layer MUST have documented results in QA_Validation_Log sheet
3. No phase gate can be marked PASS unless ALL safeguards in that layer passed
4. If ANY safeguard fails, error is logged: ERR_ID, layer, description, remediation action
5. Before marking assessment COMPLETE, QA sheet must show: 8 layers × multiple checks per layer = minimum 30 check results
6. If <20 checks documented, HALT and complete comprehensive QA

**Occurrences:**
- Count: 2
- Last Seen: Assessment cycle 5 (month 2)
- Affected Institutions: [Reserve for tracking]

**Detection Trigger:**
- QA_Validation_Log sheet has <20 documented checks
- Any phase gate marked PASS without supporting layer documentation
- No Phase_Gate_Acknowledgment column in Calculation_Chain
- QA notes field is empty or contains only "spot checks"

---

### ERR-009 [PHASE:6] HIGH: Out-of-Scope Recommendations (Non-Zennify Deliverables)

**Description:**
Recommendations include actions outside Zennify's delivery scope — hiring decisions
("Appoint Chief Data Officer"), organizational restructuring ("Establish innovation lab"),
and certification programs ("Achieve GDPR/CCPA certification"). These are management
consulting recommendations, not technology implementation recommendations. The DMA is a
prospecting tool for Zennify's solutions, and positioning non-deliverable advice erodes
credibility and missets client expectations.

**Root Cause:**
- Phase 6 lacked an explicit scope boundary filter
- Model defaults to generic "best practice" recommendations from training data
- No validation step to check if each action maps to a Zennify solution
- Insufficient emphasis on `references/zennify_solutions.md` as the authoritative scope

**Prevention Rule:**
1. Before writing ANY recommendation action, check: "Can Zennify deliver this through one
   of its 12 solutions?" If NO, tag as [CLIENT] — prerequisite/parallel workstream
2. Every action item must be tagged [ZENNIFY] or [CLIENT]
3. Run a scope compliance check before finalizing: zero untagged actions, zero [ZENNIFY]
   actions outside the 12-solution catalog
4. Out-of-scope dependencies are acknowledged as "client responsibility" — not as primary
   recommendation actions

**Occurrences:**
- Count: 1
- Last Seen: Gesa CU assessment (2026-03-01)
- Specific examples: "Appoint Chief Data Officer" (×3), "Establish digital innovation lab",
  "Achieve GDPR/CCPA privacy certification"

**Detection Trigger:**
- Recommendation actions containing: "Appoint", "Hire", "Recruit", "Establish [non-tech]",
  "Achieve certification", "Reorganize", "Create committee"
- Any action that doesn't map to a named Zennify solution

---

### ERR-010 [PHASE:4] CRITICAL: Missing Evidence Excerpts (Column U Blank or Absent)

**Description:**
Workbook scoring detail sheets lack Evidence_Excerpt (Column U) and Source_Document
(Column V) columns, making it impossible for readers to verify what specific data point
drove each score without looking up every Evidence_ID manually. This undermines the
"data-driven analysis" standard and makes the workbook an opaque scoring grid rather
than a transparent analytical artifact.

**Root Cause:**
- Columns U and V were optional or not specified in earlier workbook versions
- Model prioritizes completing all rows over ensuring each row is self-contained
- Without a "show your work" column, the model defaults to ID-only references

**Prevention Rule:**
1. Column U (Evidence_Excerpt) is MANDATORY for every row — no exceptions
2. The excerpt must be the actual finding (1-2 sentences), not a summary or reference
3. NO_EVIDENCE rows must explain what was searched for and not found
4. Column V (Source_Document) must name the specific document — not "public sources"
5. QA check: zero blank cells in Column U across all P[N]_Scoring_Detail sheets

**Occurrences:**
- Count: 1
- Last Seen: Gesa CU assessment (2026-03-01)
- Impact: All 707 subcap rows lacked evidence excerpts; Column U did not exist

**Detection Trigger:**
- Column U missing entirely from P[N]_Scoring_Detail sheets
- Blank cells in Column U
- Column U cells shorter than 30 characters
- Column V containing "public sources" or "various" without specifics

---

### ERR-011 [PHASE:4] CRITICAL: Uniform Scoring Within Capabilities (Zero Differentiation)

**Description:**
Every subcapability within a capability receives the identical score. For example, all 5
subcaps under P1C1.1 scored 3.5, all 8 subcaps under P2C1.1 scored 1.0. This violates the
fundamental principle that different diagnostic questions produce different answers. In the
Gesa CU assessment, 139/139 capabilities (100%) had zero score differentiation.

**Root Cause:**
- Model scores at capability level mentally, then stamps the same score across all subcaps
- Evidence is mapped at capability level (ERR-003), so all subcaps cite identical evidence
- Differentiation check (step 3e) is described in prose but never enforced programmatically
- Context overflow causes the model to take shortcuts during the 851-row scoring pass

**Prevention Rule:**
1. After scoring each capability, COUNT unique scores. If 100% identical = HARD BLOCK
2. Run `scripts/validate_scoring_quality.py` after Phase 4 — it checks this programmatically
3. Use the differentiation example in SKILL.md step 3e to understand HOW to vary scores
4. Key insight: absence of evidence for a specific subcap diagnostic question = lower score
   for that subcap, even when sibling subcaps have strong evidence

**Occurrences:**
- Count: 3+ (persistent pattern across multiple assessments)
- Last Seen: Gesa CU assessment (2026-03-02)
- Impact: 139/139 capabilities had zero differentiation; entire workbook lacks analytical rigor

**Detection Trigger:**
- `validate_scoring_quality.py` Check 2 reports >0 CRITICAL findings
- Any capability where unique_scores / total_subcaps < 0.4

---

### ERR-012 [PHASE:7] CRITICAL: Report Contains Zero Inline Evidence Citations

**Description:**
The assessment report contains no references to evidence items (E-xxx). Findings, scores,
and recommendations are stated as assertions without any source traceability. The reader
cannot verify any claim. In the Gesa CU assessment, 0 citations appeared across 8,883
characters of report text.

**Root Cause:**
- Phase 7 inline prevention rule (ERR-006) focuses on workbook-report consistency, not citation presence
- Report is written as a consulting narrative rather than an evidence-backed assessment
- No programmatic citation count check existed before this fix

**Prevention Rule:**
1. Every factual claim in the report MUST include (E-xxx, Source, Tier, Date) citation
2. After generating the report, run the post-report citation validation check in SKILL.md Phase 7
3. Minimum thresholds: Executive Summary ≥5 citations, each Pillar Deep Dive ≥2 per capability, total ≥30
4. If citation count < 30, re-write affected sections pulling evidence from workbook rationales

**Occurrences:**
- Count: 2+ (persistent pattern)
- Last Seen: Gesa CU assessment (2026-03-02)
- Impact: Report is unverifiable; any reader challenging a finding has no evidence trail

**Detection Trigger:**
- `re.findall(r'E-\d+|HUBBL-\d+', report_text)` returns <30 matches
- Report sections discuss findings without parenthetical citations

---

### ERR-013 [PHASE:3,4] HIGH: Caps_Applied_Log Empty Despite Applicable Caps

**Description:**
The Caps_Applied_Log sheet contains only "None / N/A / No caps applied" despite evidence
that caps SHOULD have been applied. In the Gesa CU assessment, the Marquis vendor breach
(E-036, August 2025) should have triggered a severity cap on P3C2 and/or P4C4, but the
log was empty.

**Root Cause:**
- Phase 3 (Issue Register) was skipped or produced no findings
- Severity classification was not performed against the evidence
- Cross-pillar dependency caps (Phase 4 Pass 2) were not evaluated
- Evidence ceiling caps were not logged even though they were implicitly applied

**Prevention Rule:**
1. Phase 3 MUST search regulatory databases and breach disclosures for the institution
2. Any disclosed breach <24 months triggers S2 cap on primary affected capability
3. Evidence ceiling caps MUST be logged even when they don't change the score
4. Cross-pillar dependency caps MUST be evaluated in Pass 2 and logged
5. If Caps_Applied_Log has zero entries after Phase 4, verify this is truly correct

**Occurrences:**
- Count: 1
- Last Seen: Gesa CU assessment (2026-03-02)
- Impact: Marquis breach (151,612 members affected) had no scoring impact; caps not enforced

**Detection Trigger:**
- Caps_Applied_Log has ≤1 data row with "None" or "N/A" values
- Known breach/enforcement action in evidence but no corresponding cap entry

---

### ERR-014 [PHASE:4] CRITICAL: Template-Stamped Rationales (Uniform Character Length)

**Description:**
All rationales across the workbook are exactly the same character length (e.g., exactly 100
characters), indicating they were generated from a template pattern like "[Institution]
demonstrates [adjective] capability in [subcap name]." This is the most obvious signal of
generic, non-analytical scoring. In the Gesa CU assessment, all 707 rationales were exactly
100 characters.

**Root Cause:**
- Model generates rationales using a fill-in-the-blank pattern with the subcap name
- Character truncation (intentional or context overflow) clips all rationales to same length
- The ≥150 char minimum was not enforced
- No check existed for uniform rationale length as an indicator of template-stamping

**Prevention Rule:**
1. Use the MANDATORY RATIONALE TEMPLATE in SKILL.md Phase 4 step 3d
2. Rationale length should VARY naturally (150-400 chars depending on evidence density)
3. `validate_scoring_quality.py` Check 3 detects uniform-length clustering
4. If all rationales cluster around the same character count (±10), this is a CRITICAL failure
5. FORBIDDEN starter patterns: "[Institution] demonstrates [adjective] capability in..."

**Occurrences:**
- Count: 3+ (persistent pattern across multiple assessments)
- Last Seen: Gesa CU assessment (2026-03-02)
- Impact: All 707 rationales identical in structure; zero analytical value

**Detection Trigger:**
- Standard deviation of rationale lengths < 20 characters across >50 rationales
- >50% of rationales match forbidden pattern list from SKILL.md Phase 4 step 3d

---

## Prevention Rollout Checklist

Use this checklist to prevent these errors in the next assessment:

- [ ] **Before Phase 1:** Read qa_error_log.md and understand all 14 errors
- [ ] **Before Phase 4:** Verify subcap count against the catalogue (851 at full scope)
- [ ] **Before Phase 4:** Confirm workbook structure includes Columns A-V (22 columns)
- [ ] **During Phase 4:** Execute Capability Micro-Loop (3a-3g) for each capability
- [ ] **During Phase 4:** Run differentiation check after each capability (ERR-001 prevention)
- [ ] **During Phase 4:** Test 5 sample rationales against ERR-002 criteria (≥150 chars, evidence ID, M[X] descriptor)
- [ ] **During Phase 4:** Verify Evidence_Linkage_Matrix has SubCap_ID granularity (ERR-003)
- [ ] **During Phase 4:** Verify Column U (Evidence_Excerpt) populated for every row (ERR-010)
- [ ] **During Phase 4:** Check Calculation_Chain starts with subcap rows, not capability (ERR-005)
- [ ] **During Phase 4:** Scan for forbidden rationale patterns — zero matches allowed (ERR-002)
- [ ] **During Phase 4:** Run `scripts/validate_scoring_quality.py` and fix ALL CRITICAL failures (ERR-011, ERR-014)
- [ ] **Before Phase 6:** Read Zennify Scope Boundary section — all actions tagged [ZENNIFY] or [CLIENT]
- [ ] **During Phase 6:** Verify zero out-of-scope actions tagged as [ZENNIFY] (ERR-009)
- [ ] **Before Phase 7:** Confirm workbook is FINAL and locked before narrative begins
- [ ] **During Phase 7:** Compare 10 random report scores to workbook (ERR-006)
- [ ] **During Phase 7:** Run post-report citation validation — minimum 30 evidence citations (ERR-012)
- [ ] **Before Phase 2:** Document peer selection with quality grades in peers/peer_selection.json (ERR-007)
- [ ] **Before delivery:** Run comprehensive QA with all 10 layers documented (ERR-008)
- [ ] **Before delivery:** Verify Caps_Applied_Log has real entries if any caps should apply (ERR-013)

---

## Error Severity Definitions

**CRITICAL:** Errors that invalidate the entire assessment or make it undeliverable. Examples: wrong number of scores, fabricated evidence, calculation errors. **Must be fixed before delivery.**

**HIGH:** Errors that damage credibility or traceability but can be remediated before delivery. Examples: generic rationales, missing evidence IDs, disconnected report. **Should be fixed before delivery.**

**MEDIUM:** Errors that reduce confidence or professionalism but don't invalidate core findings. Examples: incomplete QA documentation, missing peer quality grades. **Should be fixed before delivery; acceptable only with documented caveat.**

---

## Historical Error Trend (Placeholder for Tracking)

```
Cycle 1: 8 errors (3 CRITICAL, 3 HIGH, 2 MEDIUM)
Cycle 2: 5 errors (1 CRITICAL, 2 HIGH, 2 MEDIUM)
Cycle 3: 6 errors (2 CRITICAL, 2 HIGH, 2 MEDIUM)
Cycle 4: 4 errors (1 CRITICAL, 2 HIGH, 1 MEDIUM) — Prevention rules taking effect
Cycle 5: 5 errors (2 CRITICAL, 2 HIGH, 1 MEDIUM) — ERR-001/002/003 recurrence (Gesa CU), ERR-009/010 new
Cycle 6: [Next cycle — v5.1 skill with validate_scoring_quality.py enforcement, mandatory rationale template, post-report citation check, 4 new ERR entries (011-014)]
```

Target: <2 errors per assessment by Cycle 7 through structural prevention (micro-loop, mandatory columns, scope filter).
