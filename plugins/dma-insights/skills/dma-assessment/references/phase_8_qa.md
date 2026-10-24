# Phase 8: Quality Assurance (14-Check Suite)

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Phase 8: Quality Assurance (14-Check Suite)

Execute Phase Gate Protocol.

Run full validation per `references/quality_assurance.md`. Workbook wins on mismatch.

**`scripts/qa_auditor.py` now runs 14 checks (expanded from 6). ALL must pass.**

| # | Check | Severity | What It Catches |
|---|-------|----------|----------------|
| 1 | Row counts per pillar (≥50 rows) | CRITICAL | Category-level scoring |
| 2 | Score bounds (1.0-5.0, max 1 decimal) | CRITICAL | Out-of-range scores |
| 3 | Evidence linkage (score → evidence exists) | HIGH | Ungrounded scores |
| 4 | Caps log consistency (Caps_Applied non-empty → Score ≤ Evidence_Ceiling) | MEDIUM | Undocumented caps |
| 5 | Rationale quality (≥150 chars, E-ID cited) | MEDIUM | Generic rationales |
| 6 | Weight sums (~1.0 per capability) | MEDIUM | Broken aggregation |
| 7 | **Evidence field completeness** | **CRITICAL** | Truncated evidence: missing URLs, no ERS, no excerpts |
| 8 | **Report citation density** (≥30 unique E-IDs, ≥5 in exec summary) | **CRITICAL** | Reports with zero or thin citations |
| 9 | **Output artifact existence** (all mandatory files present) | **CRITICAL** | Missing deliverables (peer files, exports, report) |
| 10 | **Assessment ID consistency** (same RUN_ID across all artifacts) | **CRITICAL** | Mixed-run output |
| 11 | **Evidence mode consistency** (same mode across all artifacts) | **HIGH** | Conflicting evidence mode claims |
| 12 | **Peer data in report** (≥10 peer references, ≥1 per pillar) | **HIGH** | Peer data not flowing into report |
| 13 | **Anti-generic rationale check** (scan for forbidden patterns) | **HIGH** | Generic consulting prose |
| 14 | **Score differentiation + distribution** (no pillar >70% same score) | **MEDIUM** | Uniform scoring |

**Checks 7-14 are NEW. They catch the real issues that the previous 6-check suite missed.**

**Run:** `python scripts/qa_auditor.py --workbook <path> --report <path> --assessment-dir <path>`
Exit code 1 = FAIL. Do NOT manually override verdicts. Fix issues and re-run.

### Computed QA Verdict (`$DMA_ROOT/08_qa/qa_verdict.json`)

Generated programmatically — never from manual/stale templates:
```python
qa_verdict = {
    "run_id": RUN_ID,
    "generated_at": ISO_TIMESTAMP,
    "verdict": "PASS|PASS_WITH_NOTES|FAIL",
    "checks_executed": {"total": N, "passed": P, "failed": F, "warnings": W},
    "reconciliation": {
        "subcap_count_match": bool, "pillar_rollup_reconciled": bool,
        "evidence_ids_all_valid": bool, "broken_evidence_refs": 0
    },
    "score_state_propagation": {
        "raw_to_final_consistent": bool, "category_uses_final_score": bool,
        "pillar_uses_final_score": bool
    },
    "artifact_provenance": {"run_id_consistent_across_all": bool, "mismatched_artifacts": []},
    "regression_tests": "8/8 PASS",
    "blocker_issues": [],
    "timestamp_validation": {"all_artifacts_after_run_start": bool, "stale_artifacts_found": []}
}
```

**Verdict:** FAIL = any blocker/reconciliation failure/regression fail. PASS_WITH_NOTES = warnings only. PASS = all green. Timestamp MUST be newer than all other artifacts.

**Regression Tests:** Run all 8 suites per `references/regression_tests.md`. X/8 PASS. CRITICAL fail = fix before delivery.

**Error Log Patch:** Output in chat for human to append to master qa_error_log.md.

---
