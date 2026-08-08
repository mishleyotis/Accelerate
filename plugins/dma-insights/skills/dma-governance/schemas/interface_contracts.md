# Interface Contracts: Layer 1 → Layer 2

These schemas define the machine-readable formats that the DMA Assessment Skill (Layer 1)
outputs and the DMA Governance Skill (Layer 2) consumes. Both skills must keep these
contracts in sync. If a contract changes, both skills must be updated.

**Version**: 2.0
**Effective Date**: 2026-03-01
**Change Log**: v2.0 — Unified hybrid run_manifest schema (nested structure + audit fields),
added CRITIC_CHALLENGE cap type, added contradiction_type column, added Contract 8
(reasoning_chain_log.json). Aligned all enums and pillar names with assessment skill v5.0.

---

## Contract 1: Run Manifest (`run_manifest.json`)

Every completed assessment produces exactly one run manifest. It is the identity document
for the assessment and the primary key for the Program Repository.

**Schema file**: `schemas/run_manifest.schema.json` (HYBRID v2.0 — authoritative source)

The run manifest uses a **nested structure** matching the assessment skill's output format,
enriched with audit-specific fields (`run_id`, `skill_references_read`, `files_generated`,
`assessment.status`, `evidence_metrics.document_count`, `scoring_metrics.peer_count`).

```json
{
  "$schema": "run_manifest_v2",
  "run_id": "DMA-OZK-20250115-0001",
  "institution": {
    "name": "string — full legal name",
    "id": "string — unique identifier (NCUA charter#, OCC charter#, or assigned)",
    "sub_vertical": "enum: Credit Unions|Regional Banks|Commercial Lending|CIB|Insurance Carriers|Insurance Brokerages|Wealth Managers / RIAs|Asset Management",
    "size_tier": "enum: Mega|Large|Medium|Small|Micro|Nano",
    "primary_regulator": "string — e.g., NCUA, OCC, FDIC, Federal Reserve",
    "geography": "string — HQ state/region"
  },
  "assessment": {
    "date": "ISO-8601 date (YYYY-MM-DD)",
    "evidence_mode": "enum: PUBLIC|INTERNAL|HYBRID",
    "assessor": "string — name or ID of the person/agent that ran the assessment",
    "tool_version": "string — Claude model + skill version (e.g., 'claude-opus-4-20250514 + DMA v5.0')",
    "status": "enum: IN_PROGRESS|SCORING_COMPLETE|REPORT_DRAFT|AWAITING_REVIEW|DELIVERED"
  },
  "versions": {
    "rubric": "string — scoring methodology version (e.g., '5.0')",
    "taxonomy": "string — capability taxonomy version (e.g., '5.0')",
    "template": "string — report template version (e.g., '5.0')",
    "peer_methodology": "string — peer benchmarking methodology version (e.g., '5.0')",
    "governance_skill": "string — governance skill version (e.g., '2.1') or null if not yet audited"
  },
  "scores": {
    "overall": "number (2 decimal places)",
    "pillars": {
      "P1": "number — Strategy, Governance & Culture",
      "P2": "number — Member/Customer Experience",
      "P3": "number — Operations, Risk & Compliance",
      "P4": "number — Data, Analytics & Technology"
    },
    "categories": {
      "P1C1": "number", "P1C2": "number", "...all 17...": "..."
    }
  },
  "evidence_metrics": {
    "total_items": "integer",
    "tier_distribution": {"T1": 0, "T2": 0, "T3": 0, "T4": 0, "T5": 0},
    "avg_ers": "number (2 decimal places)",
    "median_ers": "number",
    "sources_per_subcap_avg": "number",
    "single_source_subcap_count": "integer",
    "no_evidence_subcap_count": "integer",
    "document_count": "integer — number of unique documents processed"
  },
  "scoring_metrics": {
    "caps_applied_count": "integer",
    "adjustments_applied_count": "integer",
    "dependency_caps_triggered": "integer",
    "contradictions_found": "integer",
    "contradictions_unresolved": "integer",
    "na_capabilities": ["list of capability IDs marked N/A"],
    "peer_count": "integer — number of peer institutions used"
  },
  "confidence_distribution": {
    "HIGH": "integer (count of subcaps)",
    "MEDIUM": "integer",
    "LOW": "integer"
  },
  "qa": {
    "verdict": "enum: PASS|PASS_WITH_NOTES|FAIL",
    "regression_tests": "string — e.g., '8/8 PASS'",
    "issues_found": {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0},
    "critical_issues": "integer — shortcut, must equal issues_found.CRITICAL"
  },
  "skill_references_read": ["analytical_framework.md", "scoring_methodology.md", "..."],
  "files_generated": [
    {"filename": "string", "file_type": "enum: xlsx|docx|csv|json|png|md", "path": "string"}
  ],
  "assessment_notes": "optional string"
}
```

**Validation rules**:
- `scores.overall` must equal weighted average of `scores.pillars` (±0.02)
- `evidence_metrics.total_items` must equal sum of `tier_distribution` values
- `confidence_distribution` sum must equal total subcapability count
- `qa.verdict` must be PASS or PASS_WITH_NOTES for delivery-ready assessments
- `qa.critical_issues` must equal `qa.issues_found.CRITICAL`
- `$schema` must be `"run_manifest_v2"`

**Migration from v1**: If a v1 manifest (flat structure) is encountered, the governance
auditor should log IV-02 as HIGH (not CRITICAL) and attempt best-effort field mapping.

---

## Contract 2: Caps Applied Log (`caps_applied_log.csv`)

Exported from the workbook's `Caps_Applied_Log` sheet. One row per cap/adjustment applied.

| Column | Type | Description |
|--------|------|-------------|
| cap_id | string | Unique ID (CAP-001, CAP-002...) |
| cap_type | enum | EVIDENCE_CEILING / SENTIMENT / REGULATORY / CROSS_PILLAR / ADJ_STALENESS / ADJ_COMPLAINT / ADJ_INCIDENT_MAJOR / ADJ_INCIDENT_PATTERN / CRITIC_CHALLENGE |
| trigger_reason | string | Condition that triggered the cap |
| trigger_evidence | string | Evidence ID(s) substantiating the trigger |
| affected_id | string | SubCap/Capability/Category ID |
| raw_score | number | Score before this cap |
| cap_ceiling | number | Maximum allowed by this cap |
| final_score | number | Score after all caps applied |
| score_delta | number | raw_score - final_score |

**cap_type enum values**:
- `EVIDENCE_CEILING`: Evidence tier limits score (T5-only → 2.0, T4/T5 → 2.5, etc.)
- `SENTIMENT`: App rating or complaint trend cap (P2 capabilities only)
- `REGULATORY`: Severity cap from enforcement actions (S2, S3)
- `CROSS_PILLAR`: Dependency cap triggered by low category score in another pillar
- `ADJ_STALENESS`: Adjustment-ceiling for evidence >24 months old (−0.3)
- `ADJ_COMPLAINT`: Adjustment-ceiling for complaint trend increase >20% YoY (−0.3)
- `ADJ_INCIDENT_MAJOR`: Adjustment-ceiling for major incident (−0.5)
- `ADJ_INCIDENT_PATTERN`: Adjustment-ceiling for pattern of incidents (−0.3)
- `CRITIC_CHALLENGE`: Score downgrade from Phase 4.5 Adversarial Critic Pass

**Validation rules**:
- Every row must have `cap_type` in the allowed enum (including CRITIC_CHALLENGE)
- `score_delta` must equal `raw_score - final_score` (±0.01)
- `final_score ≤ cap_ceiling` always
- ADJ_ types and CRITIC_CHALLENGE must have `trigger_evidence` populated

---

## Contract 3: Contradiction Log (`contradiction_log.csv`)

Exported from the workbook's `Contradiction_Log` sheet. One row per contradiction found.

| Column | Type | Description |
|--------|------|-------------|
| contradiction_id | string | CTR-001, CTR-002... |
| subcap_id | string | Affected subcapability |
| evidence_a_id | string | First conflicting evidence |
| evidence_a_ers | number | ERS of Evidence A |
| evidence_a_claim | string | What A asserts |
| evidence_b_id | string | Second conflicting evidence |
| evidence_b_ers | number | ERS of Evidence B |
| evidence_b_claim | string | What B asserts |
| resolution_rule | enum | ERS_RANKING / T1T2_OVERRIDE / TIEBREAKER / CONSERVATIVE_DEFAULT / UNRESOLVED |
| winner | string | Evidence ID that was preferred |
| justification | string | Brief reason |
| confidence_impact | string | How resolution affected confidence |
| flagged_in_report | boolean | Whether noted in Section 11 |
| contradiction_type | enum | HARD / SOFT |

**Column notes**:
- `contradiction_type` classifies the nature of the conflict:
  - `HARD`: Direct numeric or factual conflict that cannot both be true
  - `SOFT`: Interpretive disagreement where both could be true under different assumptions
- Only HARD contradictions trigger the formal contradiction resolution protocol. SOFT
  contradictions are documented for transparency but don't require forced resolution.

**Validation rules**:
- Every UNRESOLVED row must have `flagged_in_report = true`
- `winner` must be either `evidence_a_id` or `evidence_b_id` (or "NONE" if unresolved)
- `resolution_rule` must be in the allowed enum
- `contradiction_type` must be HARD or SOFT

---

## Contract 4: Evidence Index (`evidence_index.csv`)

Exported from the workbook's `Evidence_Index` sheet.

| Column | Type | Description |
|--------|------|-------------|
| evidence_id | string | E-001, E-002... |
| source_name | string | Human-readable source name |
| url | string | Source URL (or "INTERNAL" for non-public) |
| tier | enum | T1/T2/T3/T4/T5 |
| ers_score | number | Calculated ERS |
| publish_date | date | Publication date |
| subcaps_supported | string | Comma-separated subcap IDs |
| key_facts_count | integer | Number of facts extracted |

---

## Contract 5: Issue Register (`issue_register.csv`)

OUTPUT of Layer 2 — the structured list of issues found during governance audit.

| Column | Type | Description |
|--------|------|-------------|
| issue_id | string | ISS-001, ISS-002... |
| severity | enum | CRITICAL / HIGH / MEDIUM / LOW |
| category | enum | SCORE_INTEGRITY / EVIDENCE_QUALITY / CAP_LOGIC / AGGREGATION / NARRATIVE / FORMATTING / COMPLIANCE / CALIBRATION / DISTRIBUTIONAL / PROOF_VERIFICATION / CRITIC_RESOLUTION |
| subcategory | string | Specific check that failed (e.g., "G.4.7 — Final≠Raw without cap log") |
| affected_id | string | SubCap/Capability/Category/Section affected |
| description | string | What's wrong |
| detection_evidence | string | How the issue was found (calculation, comparison, rule check) |
| fix_instruction | string | Specific action to resolve |
| auto_fixable | boolean | Whether Layer 2 can propose an automated fix |
| status | enum | OPEN / FIXED / ACCEPTED_RISK |

---

## Contract 6: QA Verdict (`qa_verdict.json`)

OUTPUT of Layer 2 — the formal audit conclusion.

```json
{
  "$schema": "qa_verdict_v1",
  "institution_name": "string",
  "assessment_date": "ISO-8601 date",
  "rubric_version": "string",
  "governance_skill_version": "string",
  "audit_date": "ISO-8601 date",
  "verdict": "enum: PASS|PASS_WITH_NOTES|FAIL",
  "verdict_rationale": "string — 1-3 sentence summary of why this verdict",
  "issue_summary": {
    "total": "integer",
    "critical": "integer",
    "high": "integer",
    "medium": "integer",
    "low": "integer"
  },
  "blocking_issues": ["list of issue_ids that caused FAIL verdict"],
  "notes": ["list of issue_ids that caused PASS_WITH_NOTES"],
  "regression_results": "string — e.g., '8/8 PASS'",
  "calibration_flags": ["list of calibration concerns if any"],
  "recommendation": "string — DELIVER / FIX_AND_REAUDIT / MAJOR_REWORK"
}
```

**Verdict rules**:
- FAIL: Any CRITICAL issue with status OPEN
- PASS_WITH_NOTES: No CRITICAL issues, but ≥1 HIGH or MEDIUM issues with status OPEN
- PASS: No CRITICAL or HIGH issues; all MEDIUM issues either FIXED or ACCEPTED_RISK

---

## Contract 7: Patch Block (`patch_block.md`)

OUTPUT of Layer 2 — append-only proposals for program learning.

Structure:
```markdown
=== GOVERNANCE PATCH BLOCK — [Institution] [Date] ===
Governance Skill Version: [X.X]
Assessment Rubric Version: [X.X]

## Error Log Additions
[New ERR entries in qa_error_log.md template format]

## Regression Test Proposals
[New test cases or modifications to existing tests]

## Rubric Tweak Proposals (REQUIRES CCB APPROVAL)
[Proposed changes to scoring rules, ceilings, caps, or templates]
[Each proposal: Change ID, Description, Rationale, Impact Assessment, Class (0/1/2)]

## Calibration Observations
[Score distribution notes, evidence discipline metrics, drift indicators]
=== END PATCH BLOCK ===
```

**Rules**:
- Patch blocks are PROPOSALS, never auto-applied
- Class 2 rubric tweaks require regression test + calibration check before approval
- Error log additions can be applied immediately after human review

---

## Contract 8: Reasoning Chain Log (`reasoning_chain_log.json`)

Machine-readable audit trail of every scoring decision made during Phase 4. Produced by
Layer 1 alongside the scoring workbook — NOT reconstructed afterwards. Enables Layer 2 to
programmatically audit reasoning quality, decision path consistency, and evidence linkage.

**Schema file**: See assessment skill `references/reasoning_chain_schema.md` for the full
schema definition.

```json
{
  "subcaps": [
    {
      "id": "P1C1.1.1",
      "decision_path": ["evidence_collected", "tier_classified", "ceiling_applied", "m_level_matched", "no_adjustments", "no_contradictions", "no_dependencies", "final_calculated"],
      "evidence_considered": ["E-001:F1", "E-005:F2"],
      "ceiling_calc": {"tier": "T3", "ceiling": 3.5, "binding": false},
      "m_level_match": {"descriptor": "M3", "range": "3.0-3.5", "selected": 3.0},
      "caps_applied": [],
      "contradictions": [],
      "confidence": {"level": "MEDIUM", "ers": 2.8, "sources": 2, "tiers": 1, "rationale": "Two sources but same tier"},
      "critic_result": {"attacked": true, "arguments": 1, "adjudication": "DEFEND", "delta": 0.0},
      "final_score": 3.0
    }
  ],
  "summary": {
    "total_subcaps": 836,
    "decision_paths_logged": 836,
    "critic_attacks": 400,
    "critic_downgrades": 25,
    "confidence_overrides": 3
  }
}
```

**Validation rules**:
- `summary.decision_paths_logged` must equal number of entries in `subcaps` array
- `summary.total_subcaps` must match total subcap count from workbook
- Every `subcaps[].id` must correspond to a row in the scoring workbook
- Every evidence ID in `evidence_considered` must exist in `evidence_index.csv`
- Every cap ID referenced in `caps_applied` must exist in `caps_applied_log.csv`

**Governance usage**:
- PV-01 (Proof Structure Completeness): Cross-validate reasoning chain entries against
  workbook Columns R (Scoring_Rationale), S (Proof_Claims), and T (Proof_Links)
- PV-02 (Rule Link Validity): Verify `m_level_match.descriptor` against capability_criteria.md
- Calibration (Workflow B): Analyze `decision_path` distribution across assessments for
  scoring behavior consistency
