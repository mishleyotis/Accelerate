# Reasoning Chain Log Schema

This file defines the schema for `reasoning_chain_log.json`, a machine-readable audit trail
of every scoring decision made during Phase 4. This log enables Layer 2 governance to audit
reasoning quality programmatically, not just score integrity.

**Version**: 1.0
**Generated during**: Phase 4 (scoring) and Phase 4.5 (adversarial critic)
**Consumed by**: Layer 2 Governance Skill (Workflow A audit checks, calibration metrics)

---

## Why This Exists

Traditional QA checks verify that scores are mathematically correct and evidence is cited.
But they cannot verify that the *reasoning* was sound — that the assessor considered all
relevant evidence, applied the right rules, and reached a defensible conclusion. The reasoning
chain log captures the decision path for every subcapability, making reasoning auditable.

---

## Full Schema

```json
{
  "$schema": "reasoning_chain_v1",
  "assessment_id": "string — matches run_manifest institution.id + assessment.date",
  "generated_at": "ISO-8601 datetime",
  "subcaps": [
    {
      "id": "string — subcapability ID (e.g., P1C1.1.1)",
      "capability_id": "string — parent capability (e.g., P1C1.1)",
      "category_id": "string — parent category (e.g., P1C1)",

      "decision_path": {
        "steps_applied": ["string — ordered list of decision tree steps that fired"],
        "steps_skipped": ["string — steps that were evaluated but not applicable"],
        "notes": "string — any deviations from standard path"
      },

      "evidence_considered": [
        {
          "evidence_id": "string — e.g., E-001:F1",
          "tier": "string — T1/T2/T3/T4/T5",
          "ers": "number",
          "role": "string — SUPPORTING / OPPOSING / NEUTRAL",
          "key_fact": "string — the specific fact used from this evidence"
        }
      ],

      "ceiling_calc": {
        "best_tier": "string — highest tier of evidence available",
        "ceiling_value": "number — evidence ceiling applied",
        "binding": "boolean — whether the ceiling constrained the score",
        "single_source": "boolean — whether only 1 source supports this subcap"
      },

      "m_level_match": {
        "descriptor_id": "string — e.g., M3",
        "descriptor_range": "string — e.g., 3.0-3.5",
        "selected_score": "number — raw score before caps",
        "precision": "string — 0.5 (default) or 0.1 (with justification)",
        "precision_justification": "string — required if 0.1 precision used"
      },

      "caps_applied": [
        {
          "cap_id": "string — matches caps_applied_log.csv cap_id",
          "cap_type": "string — matches enum in caps_applied_log",
          "ceiling": "number",
          "score_before": "number",
          "score_after": "number"
        }
      ],

      "adjustments_applied": [
        {
          "adj_type": "string — ADJ_STALENESS / ADJ_COMPLAINT / ADJ_INCIDENT_MAJOR / ADJ_INCIDENT_PATTERN",
          "trigger_evidence": "string — evidence ID that triggered",
          "ceiling": "number",
          "formula": "string — e.g., min(raw, others) - 0.3"
        }
      ],

      "contradictions": [
        {
          "contradiction_id": "string — matches contradiction_log.csv contradiction_id",
          "evidence_a": "string",
          "evidence_b": "string",
          "resolution_rule": "string — which rule was applied",
          "impact_on_score": "string — how the resolution affected this subcap's score"
        }
      ],

      "confidence": {
        "level": "string — HIGH / MEDIUM / LOW",
        "ers_of_best_evidence": "number",
        "source_count": "integer",
        "tier_count": "integer",
        "cross_validation": {
          "ce01_check": "string — PASS / FAIL (HIGH requires ERS ≥ 2.5)",
          "ce02_check": "string — PASS / FLAG (LOW with ERS ≥ 3.5 + ≥3 sources)",
          "ce03_check": "string — PASS / FAIL (single-source ≤ MEDIUM)",
          "ce04_check": "string — PASS / N/A (single-source T1/T2 limitation statement)"
        },
        "rationale": "string — brief explanation of confidence assignment"
      },

      "critic_result": {
        "attacked": "boolean — whether the adversarial critic challenged this subcap",
        "attack_arguments": [
          {
            "argument": "string — the attack argument text",
            "evidence_gap_identified": "string — what evidence would change the score",
            "defense": "string — how the current evidence defends the score"
          }
        ],
        "adjudication": "string — DEFEND / DOWNGRADE / NOT_ATTACKED",
        "score_delta": "number — 0 if defended, negative if downgraded"
      },

      "final_score": "number — the score after all caps, adjustments, and critic pass",
      "raw_score": "number — score before any caps or adjustments"
    }
  ],

  "summary": {
    "total_subcaps": "integer",
    "decision_paths_logged": "integer — should equal total_subcaps",
    "avg_evidence_per_subcap": "number",
    "ceiling_binding_count": "integer — how many subcaps were constrained by evidence ceiling",
    "single_source_count": "integer",
    "caps_applied_total": "integer",
    "contradictions_total": "integer",
    "confidence_distribution": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
    "confidence_overrides": "integer — how many confidence levels were changed by cross-validation",
    "critic_attacks_total": "integer",
    "critic_downgrades_total": "integer",
    "critic_coverage_pct": "number — % of subcaps attacked",
    "critic_defend_pct": "number — % of attacked subcaps that were defended"
  },

  "distributional_self_checks": {
    "dc01_score_clustering": {"fired": false, "details": ""},
    "dc02_confidence_inflation": {"fired": false, "details": ""},
    "dc03_tier_concentration": {"fired": false, "details": ""},
    "dc04_cap_saturation": {"fired": false, "details": ""},
    "dc05_rationale_homogeneity": {"fired": false, "details": ""},
    "dc06_evidence_reuse": {"fired": false, "details": ""},
    "dc07_score_confidence_alignment": {"fired": false, "details": ""},
    "dc08_peer_benchmark_plausibility": {"fired": false, "details": ""}
  }
}
```

---

## Cross-References

| Field in reasoning_chain_log | Must match field in... |
|-----|-----|
| `subcaps[].id` | Workbook P[N]_Scoring_Detail SubCap_ID |
| `subcaps[].evidence_considered[].evidence_id` | `evidence_index.csv` evidence_id |
| `subcaps[].caps_applied[].cap_id` | `caps_applied_log.csv` cap_id |
| `subcaps[].contradictions[].contradiction_id` | `contradiction_log.csv` contradiction_id |
| `subcaps[].final_score` | Workbook P[N]_Scoring_Detail Final_Score |
| `summary.confidence_distribution` | `run_manifest.json` confidence_distribution |
| `summary.critic_attacks_total` | Workbook Critic_Log row count |

---

## Layer 2 Governance Checks Enabled

With this log, Layer 2 can add programmatic reasoning checks:

1. **Decision completeness**: Every subcap has all 8 decision tree steps evaluated
2. **Evidence utilization**: No evidence items in the index are completely unused
3. **Ceiling consistency**: Ceiling calculations match tier→ceiling mapping rules
4. **Confidence integrity**: All CE-01 through CE-04 checks pass in the log
5. **Critic thoroughness**: Coverage ≥ 80%, intensity ≥ 1.5 for M4+ scores
6. **Reasoning uniqueness**: No two subcaps have identical decision paths + evidence sets
7. **Cross-reference integrity**: All IDs in the log exist in the corresponding CSV/workbook
