# LLM Reasoning Prompts — Pass 2 Deep Analysis

This file contains structured evaluation rubrics, chain-of-thought scaffolds, and
few-shot examples for the judgment-dependent checks that require LLM reasoning.
These checks CANNOT be automated — they require semantic understanding.

**When to read**: After running `gov_auditor.py` (Pass 1), before performing Pass 2.

---

## PV-01: Proof Structure Completeness

### Purpose
Verify every subcap rationale contains all 5 proof elements.

### Step 0 — do the inputs exist at all?

Count the rows carrying a non-empty Column S or T, and check whether
`reasoning_chain_log.json` exists. **If the answer is zero rows and no
file, stop: do not report PV-01 as 0%.**

Zero is not a measurement of proof quality — it is a measurement of a
FORMAT CONTRADICTION between two skills in this plugin. `dma-assessment`
declares the 11-column layout canonical and states "Do NOT use the legacy
22-column (A-V) layout"; this check audits columns R, S and T, which
exist only in that layout. Emit `GOV-FORMAT-01` at CRITICAL, name both
skills and the columns, and set the verdict to FAIL.

This happened, and the cost is the reason for this step: one promoted
assessment scored 0 of 709 rows, the verdict recorded it under
`schema_drift_accepted`, returned PASS_WITH_NOTES, and the run reached a
regulated dealer's dashboard telling it that its trade surveillance was
Differentiating on the strength of a subsidiary's officer list.

Where the columns ARE present, continue below.

### Evaluation Procedure

For each subcap rationale, check across THREE data sources:
- **Column R** (Scoring_Rationale): Human-readable narrative
- **Column S** (Proof_Claims): Structured claim set (C1/C2/C3 format)
- **Column T** (Proof_Links): JSON proof structure for programmatic validation
- **reasoning_chain_log.json**: Machine-readable decision trail (Contract 8)

Check for these 5 elements:

| Element | Detection Strategy — Column R | Cross-Validation — Columns S/T + Reasoning Chain |
|---------|-------------------------------|---------------------------------------------------|
| Claims (C1–C3) | Look for "C1:", "C2:", "C3:" tags or 3+ distinct factual assertions | Column S must have structured C1/C2/C3 entries. Column T JSON `claims[]` array length must match. |
| Evidence Links | Look for "E-NNN" or "E-NNN:FN" patterns | Column T JSON `claims[].evidence` arrays populated. All IDs must exist in evidence_index.csv. |
| Rule Links | Look for "RULE_" prefix or rule name citations | Column T JSON `claims[].rule` populated. reasoning_chain `m_level_match.descriptor` populated. |
| Counterclaim | Look for "counterargument", "however", "opposing", "rebuttal" | Column T JSON `counterclaim.text` populated (not generic filler). reasoning_chain `contradictions` array present. |
| Constraints | Look for "ceiling", "cap", "dependency", "tier", "verified" | Column T JSON `constraints[]` array populated. reasoning_chain `ceiling_calc` and `caps_applied` populated. |

**Cross-validation rule**: If Column R claims PASS but Column T JSON is missing or
inconsistent, log as MEDIUM issue — the narrative looks right but the machine-readable
proof is incomplete, reducing auditability.

### Chain-of-Thought Template

```
SUBCAP: [P1C1S01]
Score: [3.5]

CLAIMS CHECK:
  C1 found (Col R): [yes/no] — "[claim text or 'missing']"
  C2 found (Col R): [yes/no] — "[claim text or 'missing']"
  C3 found (Col R): [yes/no] — "[claim text or 'missing']"
  Col S structured claims match: [yes/no/missing]
  Col T JSON claims[] count: [N] — matches Col R: [yes/no]
  Verdict: [PASS/FAIL]

EVIDENCE LINKS CHECK:
  Links found (Col R): [E-001:F2, E-015:F1, ...]
  All claims linked: [yes/no]
  Col T JSON evidence arrays populated: [yes/no]
  Links exist in evidence_index: [yes/no — cross-reference]
  reasoning_chain evidence_considered matches: [yes/no]
  Verdict: [PASS/FAIL]

RULE LINKS CHECK:
  Rules cited (Col R): [RULE_M3_CAPABILITY_ADVANCEMENT, ...]
  Rules exist in framework: [yes/no]
  Col T JSON claims[].rule populated: [yes/no]
  reasoning_chain m_level_match present: [yes/no]
  Rules correctly applied: [yes/no — explain]
  Verdict: [PASS/FAIL]

COUNTERCLAIM CHECK:
  Counter identified (Col R): [yes/no] — "[counter text or 'missing']"
  Counter is specific (not generic): [yes/no]
  Col T JSON counterclaim.text populated: [yes/no]
  Rebuttal provided: [yes/no] — "[rebuttal text or 'missing']"
  Rebuttal cites evidence: [yes/no]
  Verdict: [PASS/FAIL]

CONSTRAINTS CHECK:
  Applicable caps/dependencies: [list from Pass 1 results]
  Acknowledged in rationale: [yes/no]
  Verdict: [PASS/FAIL]

OVERALL: [PASS / PARTIAL (N of 5) / FAIL]
Missing elements: [list]
```

### Few-Shot Examples

**PASS example** (all 5 elements present):
```
P2C3S04 — Digital Account Opening: Score 3.5

C1: Institution launched digital account opening in Q2 2023 with 68% completion rate (E-045:F3).
C2: Mobile app rating improved from 3.2 to 4.1 over 18 months (E-012:F1, E-067:F2).
C3: Digital channel now handles 42% of new account applications vs. 15% two years prior (E-045:F7).

Applied RULE_M3_CAPABILITY_ADVANCEMENT: Score of M3.5 reflects measurable adoption
beyond initial deployment (>30% channel share) with sustained quality improvement.

Counterargument: Completion rate of 68% suggests 32% abandonment, possibly indicating
UX friction that limits true maturity. However, industry average completion rate for
comparable institutions is 55% (E-089:F2), placing this institution above median.

Constraints: Evidence ceiling T3→4.0 (not binding at 3.5). No cross-pillar dependency
triggered (P1C2 = 3.4 > 2.5 threshold). Single-source limitation does not apply (3 sources).
```

**FAIL example** (missing Rule Links + weak Counterclaim):
```
P3C1S02 — Data Governance Framework: Score 3.0

The institution has a documented data governance framework that covers key data domains.
Evidence shows policy documents are in place (E-033) and a data steward network exists
(E-034). The framework appears to be at a developing-to-defined stage.

No significant counterarguments identified.

ANALYSIS:
- Claims: PARTIAL — assertions present but not tagged C1/C2/C3
- Evidence Links: PASS — E-033, E-034 cited
- Rule Links: FAIL — no RULE_ reference
- Counterclaim: FAIL — generic dismissal, no specific counter or rebuttal
- Constraints: FAIL — no cap/dependency acknowledgment
VERDICT: FAIL (2 of 5 elements complete)
```

### Scoring Rubric

| % Subcaps with Complete Proof | PV-01 Verdict |
|-------------------------------|---------------|
| ≥ 95% | PASS |
| 80–94% | PASS_WITH_WARNINGS |
| < 80% | FAIL |

---

## PV-02: Rule Link Validity

### Purpose
Verify all cited RuleIDs exist and are correctly applied.

### Evaluation Procedure

1. Extract all RULE_ references from all rationales
2. For each unique RuleID:
   a. Verify it exists in the scoring framework (capability_criteria.md, scoring_methodology.md)
   b. Check that the rule's conditions match the evidence cited
   c. Verify the score aligns with what the rule would produce

### Chain-of-Thought Template

```
RULE: [RULE_M3_CAPABILITY_ADVANCEMENT]
Cited in: [P2C3S04]
Score assigned: [3.5]

EXISTENCE CHECK:
  Found in framework: [yes/no]
  Source document: [capability_criteria.md, Section X]
  Rule definition: "[summary of rule conditions]"

APPLICATION CHECK:
  Rule requires: [list conditions from rule definition]
  Evidence shows: [what the evidence actually demonstrates]
  Conditions met: [yes/partially/no — explain each]

SCORE ALIGNMENT:
  Rule predicts score range: [e.g., M3 = 3.0, M3.5 if quantitative metrics exceed threshold]
  Actual score: [3.5]
  Alignment: [consistent/inconsistent — explain]

VERDICT: [PASS/FAIL]
If FAIL, reason: [INVALID_RULE_ID / RULE_MISAPPLIED / SCORE_INCONSISTENT]
```

### Scoring Rubric

| Condition | PV-02 Verdict |
|-----------|---------------|
| All RuleIDs valid AND correctly applied | PASS |
| Any invalid RuleID OR demonstrable misapplication | FAIL |

---

## PV-03: Counterclaim Quality

### Purpose
Assess whether counterclaims are substantive (not boilerplate).

### Quality Criteria

**Substantive (PASS):**
- Identifies a *specific* opposing interpretation (not "there could be counterarguments")
- The counter is *plausible* — someone could reasonably hold this view
- Rebuttal addresses the specific counter with *evidence* (not just assertion)
- Counter relates to the *score-relevant* aspect of the capability

**Non-substantive (FAIL):**
- Generic: "No significant counterarguments exist"
- Strawman: Counter is too weak to be meaningful
- Unaddressed: Counter raised but no rebuttal provided
- Assertion-only: Rebuttal doesn't cite evidence

### Chain-of-Thought Template

```
SUBCAP: [ID]
Counterclaim text: "[full text]"

SPECIFICITY: [1-5]
  1 = completely generic / absent
  3 = identifies a direction but vague
  5 = names a specific alternative interpretation with reasoning

PLAUSIBILITY: [1-5]
  1 = strawman / no reasonable person would hold this view
  3 = somewhat plausible but unlikely
  5 = a legitimate concern that a reviewer might raise

REBUTTAL QUALITY: [1-5]
  1 = absent or pure assertion
  3 = logical argument but no evidence
  5 = cites specific evidence that directly addresses the counter

VERDICT: [PASS if avg ≥ 3.0, FAIL if avg < 3.0]
```

### Scoring Rubric

| % Subcaps with Substantive Counterclaims | PV-03 Verdict |
|------------------------------------------|---------------|
| ≥ 90% | PASS |
| 75–89% | PASS_WITH_WARNINGS |
| < 75% | FAIL |

---

## CR-01: Critic Log Resolution

### Purpose
Verify all adversarial findings from the Critic_Log have been addressed.

### Evaluation Procedure

1. Read each row in the Critic_Log worksheet
2. Classify resolution status: ADDRESSED / ACCEPTED_WITH_RATIONALE / INVALID / UNADDRESSED
3. For non-UNADDRESSED entries, evaluate resolution quality

### Chain-of-Thought Template

```
CRITIC FINDING: [CRI-P2C1-001]
Finding text: "[what the critic flagged]"
Severity: [HIGH/MEDIUM/LOW]

RESOLUTION STATUS: [ADDRESSED / ACCEPTED_WITH_RATIONALE / INVALID / UNADDRESSED]

RESOLUTION QUALITY (if not UNADDRESSED):
  Response text: "[assessor's response]"
  Is response specific (not generic)?: [yes/no]
  Does response cite evidence or scoring logic?: [yes/no]
  Would a skeptical reviewer accept this?: [yes/no]
  If ADDRESSED: was the score/rationale actually updated? [yes/no]
  If ACCEPTED: does rationale explain WHY no change needed? [yes/no]
  If INVALID: does explanation identify why concern doesn't apply? [yes/no]

VERDICT: [PASS/FAIL for this finding]
Reason: [brief explanation]
```

### Resolution Quality Standards

| Resolution Type | Required Elements | PASS Criteria |
|----------------|-------------------|---------------|
| ADDRESSED | Evidence of change + citation | Score or rationale was modified, change documented |
| ACCEPTED_WITH_RATIONALE | Explanation + evidence | Clear reasoning why finding doesn't require score change |
| INVALID | Explanation + framework reference | Identifies why the concern is based on incorrect premises |
| UNADDRESSED | — | Always FAIL |

### Scoring Rubric

| Condition | CR-01 Verdict |
|-----------|---------------|
| 100% findings resolved (ADDRESSED/ACCEPTED/INVALID) | PASS |
| ≥90% resolved, unresolved are LOW-severity only | PASS_WITH_WARNINGS |
| Any HIGH-severity UNADDRESSED, OR >10% UNADDRESSED | FAIL |

---

## Root Cause Analysis

### Purpose
For each CRITICAL or HIGH issue from Pass 1, trace the causal chain to identify systemic risks.

### Chain-of-Thought Template

```
ISSUE: [ISS-XXX] — [brief description]
Check: [check_id]
Severity: [CRITICAL/HIGH]

1. SURFACE FINDING:
   What the automated check detected: [exact failure description from check_results.json]

2. PROXIMATE CAUSE:
   Immediate reason: [e.g., "Score 4.0 assigned but Evidence_Ceiling = 3.5"]
   How did this value get here: [e.g., "Assessor scored based on self-reported metric
   without checking ceiling constraint"]

3. ROOT CAUSE:
   Process gap: [e.g., "No pre-scoring ceiling check in Layer 1 workflow"]
   Knowledge gap: [e.g., "Assessor unaware that T3 evidence caps at 3.5"]
   Tool gap: [e.g., "Workbook doesn't auto-flag ceiling violations"]

4. SYSTEMIC RISK:
   Could this affect other assessments? [yes/no]
   Scope: [e.g., "Any assessment using T3-only evidence for M4+ capabilities"]
   Frequency estimate: [e.g., "~15% of PUBLIC-mode assessments"]

5. PREVENTION:
   Immediate fix: [for this assessment]
   Process fix: [prevent recurrence in future assessments]
   Tool fix: [automation or guardrail to add]
```

---

## Patch Block Generation

### Purpose
Synthesize all findings into a structured program learning document.

### Required Sections

After completing PV, CR, root cause analysis, and reviewing all Pass 1 issues,
generate the patch block using `templates/patch_block_template.md` as the format.

### Content Generation Guidelines

**Section 1 (Structural Issues):**
- Start with Pass 1 issues grouped by category
- Add root cause analysis for each CRITICAL/HIGH issue
- Propose specific file + line changes

**Section 2 (Rubric Clarifications):**
- Trigger: systematic PV failures suggest ambiguous rules
- Trigger: CR findings reveal rule interpretation disagreements
- Propose exact wording changes with before/after

**Section 3 (Regression Test Enhancements):**
- Any novel failure pattern → propose a golden case addition
- Any check that caught an issue for the first time → propose regression test

**Section 4 (Error Log Entries):**
- New pattern ID for each novel failure type
- Include trigger condition, remediation, learning implication

**Section 5 (Program Actions):**
- Prioritize by impact × frequency
- Assign to specific teams/owners
- Include success criteria and timeline

---

## Output Format Mapping

After completing all Pass 2 checks, update `qa_verdict.json` with:

```json
{
  "proof_verification": {
    "PV01_structure_complete": "[PASS/PASS_WITH_WARNINGS/FAIL]",
    "PV02_rule_links_valid": "[PASS/FAIL]",
    "PV03_counterclaim_documented": "[PASS/PASS_WITH_WARNINGS/FAIL]",
    "proof_issues": [
      {
        "subcap_id": "P2C3",
        "issue_type": "MISSING_RULE_LINKS",
        "description": "Rationale lacks RULE_ reference"
      }
    ]
  },
  "critic_resolution": {
    "CR01_findings_addressed": "[PASS/PASS_WITH_WARNINGS/FAIL]",
    "critic_issues": [
      {
        "critic_finding_id": "CRI-P2C1-001",
        "finding_text": "...",
        "status": "UNADDRESSED",
        "resolution": ""
      }
    ]
  },
  "sign_off": {
    "auditor_id": "[update with actual auditor]",
    "auditor_name": "[update]",
    "organization": "[update]",
    "verdict_date": "[update to Pass 2 completion time]",
    "is_approved": true,
    "sign_off_notes": "[any notes from human reviewer]"
  }
}
```

Replace the `PENDING_LLM_PASS2` placeholders with actual results.
