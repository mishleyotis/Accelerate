# LLM Reasoning Prompts — Pass 2 Deep Analysis

This file contains structured evaluation rubrics, chain-of-thought scaffolds, and
few-shot examples for the judgment-dependent checks that require LLM reasoning.
These checks CANNOT be automated — they require semantic understanding.

**When to read**: After running `gov_auditor.py` (Pass 1), before performing Pass 2.

---

## PV-01: Proof Structure Completeness

### Purpose
Verify every scored subcap's proof is complete, in the columns the engine's contract
holds (rewritten 29-09-2026, QA audit F-L11-042 pair 35: this check used to read
columns R, S and T of a 22-column layout the engine replaced, and `GOV-FORMAT-01`
recorded the contradiction; the contract's columns are canonical and the contradiction
is retired).

### Step 0 — do the inputs exist at all?

Count the scored rows whose `Rationale` is non-empty, and check whether
`07_qa/scoring.json` (the scoring packet `engine.assessment gate` writes) exists. **If
the answer is zero rows or no packet, stop: do not report PV-01 as 0%.** The scoring
stage did not run through the engine; the verdict is FAIL naming the missing input.

This step exists because of what happened without it: one promoted assessment scored
0 of 709 rows against a layout that no longer existed, the verdict recorded it under
`schema_drift_accepted`, returned PASS_WITH_NOTES, and the run reached a regulated
dealer's dashboard telling it that its trade surveillance was Differentiating on the
strength of a subsidiary's officer list.

Where the inputs ARE present, continue below.

### Evaluation Procedure

For each scored subcap, check across the contract's columns and the packet:
- **`Rationale`**: the scorer's six-heading argument — `[EVIDENCE]`, `[MATURITY MATCH]`,
  `[GAP TO NEXT]`, `[COUNTER]`, `[CEILING]`, `[SO WHAT]`
- **`Evidence_IDs`**: the rows the argument cites
- **`Challenge_Verdict`**: the independent challenge recorded before scoring
- **`Caps_Applied`**: the arithmetic string `engine.assessment score` wrote
  (raw, adjustments, ceiling, caps, quarter-point, final)
- **`07_qa/scoring.json`**: the same row, machine-readable

Check for these 5 elements:

| Element | Detection — `Rationale` | Cross-validation |
|---------|-------------------------|------------------|
| Claims | `[EVIDENCE]` states 3+ distinct factual assertions, each with an `E-xxx` | every cited id is in `Evidence_IDs` and resolves in `Evidence_Detail` |
| Evidence links | `E-xxx` / `E-xxx:Fy` patterns | `Evidence_IDs` non-empty; the packet's row cites the same ids |
| Rule link | `[MATURITY MATCH]` names the rubric descriptor the score matches | the level named is the rubric's for that score (`${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/rubric.py`) |
| Counterclaim | `[COUNTER]` states a specific opposing reading and its rebuttal | `Challenge_Verdict` present; a generic dismissal is a FAIL |
| Constraints | `[CEILING]` names the evidence ceiling and the caps | `Caps_Applied` carries the arithmetic; the packet's final equals the workbook's |

**Cross-validation rule**: if `Rationale` reads complete but `Caps_Applied` or the packet
disagrees with the workbook's score, log as MEDIUM — the narrative looks right but the
machine-readable proof is inconsistent, reducing auditability.

### Chain-of-Thought Template

```
SUBCAP: [P1C1.1.1]
Score: [3.5]

CLAIMS CHECK ([EVIDENCE]):
  distinct claims found: [N] — each with an E-id: [yes/no]
  every cited id in Evidence_IDs and resolving: [yes/no]
  Verdict: [PASS/FAIL]

RULE LINK CHECK ([MATURITY MATCH]):
  descriptor named: [yes/no] — "[text or 'missing']"
  matches the rubric level for the score: [yes/no]
  Verdict: [PASS/FAIL]

COUNTERCLAIM CHECK ([COUNTER]):
  specific opposing reading: [yes/no] — "[text or 'missing']"
  rebuttal cites evidence: [yes/no]
  Challenge_Verdict present: [yes/no]
  Verdict: [PASS/FAIL]

CONSTRAINTS CHECK ([CEILING] / Caps_Applied):
  ceiling and caps named: [yes/no]
  Caps_Applied arithmetic ends at the workbook's score: [yes/no]
  packet row agrees: [yes/no]
  Verdict: [PASS/FAIL]

OVERALL: [PASS / PARTIAL (N of 5) / FAIL]
Missing elements: [list]
```

### Few-Shot Examples

**PASS example** (all elements present):
```
P2C2.1.1 — Digital account opening: score 3.5

[EVIDENCE] E-045 (T2, annual report 2024): digital account opening launched Q2 2023, 68 %
completion. E-012, E-067 (T3, app stores): rating 3.2 → 4.1 over 18 months. E-045: the
digital channel handles 42 % of new applications vs 15 % two years prior.
[MATURITY MATCH] M3 "measurable adoption beyond deployment (>30 % channel share) with
sustained quality improvement".
[GAP TO NEXT] M4 needs a stated funnel target and a closed-loop fix cycle; neither is
evidenced.
[COUNTER] 68 % completion means 32 % abandonment — possible UX friction. Peer completion
for comparable institutions is 55 % (E-089), so above median; the counter lowers
confidence, not the level.
[CEILING] T2/T3 evidence: ceiling 4.0, not binding; no cap; raw 3.5 − 0 = 3.5.
[SO WHAT] For <entity>, the next quarter's decision is the funnel target, not the channel.
Caps_Applied: raw 3.5; adjusted 3.5; ceiling 4.0; final 3.5 (Competing)
```

**FAIL example** (missing rule link, generic counter):
```
P4C1.1.2 — Data governance framework: score 3.0

The institution has a documented data governance framework covering key domains.
Policy documents are in place (E-033) and a data steward network exists (E-034). The
framework appears developing-to-defined. No significant counterarguments identified.

ANALYSIS:
- Claims: PARTIAL — assertions present, one without an id
- Evidence links: PASS — E-033, E-034 cited and resolving
- Rule link: FAIL — no [MATURITY MATCH]; no rubric descriptor
- Counterclaim: FAIL — generic dismissal, no specific counter or rebuttal
- Constraints: FAIL — no [CEILING]; Caps_Applied blank
VERDICT: FAIL (1 of 5 elements complete)
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

Replace the `NOT_RUN` placeholders with actual results.
