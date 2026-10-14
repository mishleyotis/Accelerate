# Deterministic Score States (MANDATORY)

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Deterministic Score States (MANDATORY)

In the P#_Subcap_Scoring sheet (columns A–K), scoring flows through these states:

| State | Where | Description |
|-------|-------|-------------|
| `raw_score` | Internal (not in workbook) | From M-level matching (before caps) |
| `evidence_ceiling` | Column H | Maximum score supported by evidence tier |
| `caps_applied` | Column I | Description of any caps that reduced the score |
| `final_score` | **Column D (Score)** | min(raw, evidence_ceiling, severity_caps, cross_pillar) — **ONLY value in rollups** |

**Column D is the FINAL score** — it already incorporates all caps. There is no separate
raw_score column in the workbook. The raw-to-final pathway is documented in the Rationale
(Column J) and Caps_Applied (Column I).

**Rollup:** subcap final_score (Col D) → capability → category → pillar → overall (weighted avg)
**Reconciliation:** Recompute pillar from categories — must match ±0.01. Fix before proceeding.

### Canonical Export Layer (MANDATORY after Phase 4)

```
$DMA_ROOT/04_scoring/exports/
├── export_scoring_detail.csv      # All subcaps: ID, Score, Evidence_Ceiling, Caps_Applied, Confidence
├── export_category_summary.csv    # one rollup per catalogue category (16 in v7.0 — contract.counts())
├── export_pillar_summary.csv      # 4 rollups with weighted scores
├── export_evidence_inventory.csv  # All evidence with ERS
├── export_issue_register.csv      # Issues with dates
└── export_coverage_stats.csv      # Subcap counts, coverage %
```

**Phase 7 report reads ONLY from exports. No ad hoc data.**

### Sub-Vertical Pillar Weights

| Sub-Vertical | P1 | P2 | P3 | P4 |
|-------------|----|----|----|----|
| Credit Unions | 25 | 30 | 20 | 25 |
| Regional Banks | 25 | 30 | 20 | 25 |
| Commercial Lending | 20 | 20 | 35 | 25 |
| CIB | 20 | 20 | 35 | 25 |
| Insurance Carriers | 20 | 20 | 30 | 30 |
| Insurance Brokerages | 20 | 35 | 20 | 25 |
| Wealth / RIAs | 25 | 30 | 20 | 25 |
| Asset Management | 20 | 30 | 25 | 25 |

---
