# Workbook Column Structure (the contract's P#_Subcap_Scoring sheet — columns A–K are yours)

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Workbook Column Structure (the contract's P#_Subcap_Scoring sheet — columns A–K are yours)

The layout is `${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/contract.py: PILLAR_COLUMNS` (33 columns) and nothing else — not this
table, not a template recalled from memory, not the CFC workbook it descends from. Columns
A–K below are the eleven the app ingests and the ones the scoring stage writes (D, E, H, I, J
through `engine.assessment score`; A, B, C, F, G, K were filled at the research stage).
Columns L–AG are the research working area (synthesis, volleys, triangulation, absence proof);
`engine.cli strip` removes them AFTER the handoff carries them, so the shipped workbook reads
as A–K. **Do NOT create a sheet, add a column, or rename a header; `engine.cli validate`
fails the workbook on any deviation and the app's parser will not read it.**

| Col | Header | Description |
|-----|--------|-------------|
| A | SubCap_ID | Unique subcap identifier (e.g., P1C1.1.1, P2C3.2.4). One row per subcap. |
| B | SubCap_Name | Subcapability name from Pillar XLSX toolkit |
| C | Category | Parent category ID (e.g., P1C1, P2C3) |
| D | Score | Final maturity score (1.0-5.0, quarter points x.00/x.25/x.50/x.75 — `engine.assessment` refuses any other) |
| E | Confidence | HIGH / MEDIUM / LOW based on evidence coverage and tier diversity |
| F | Evidence_IDs | Comma-separated evidence IDs (E-001, E-015, INT-BOARD-003) or NO_EVIDENCE |
| G | Source_URLs | Hyperlinks to evidence sources (specific URLs, not "multiple searches") |
| H | Evidence_Ceiling | Maximum score supported by evidence tier (e.g., T5-only → 2.0) |
| I | Caps_Applied | Cap description if applied (e.g., "T5-only cap 2.0") or empty if none |
| J | Rationale | ≥150 chars. Must cite E-IDs, reference M-level descriptor, explain gap, institution-specific "so what" |
| K | Proxy_Searched | "Yes" or "No" — whether proxy searches (Tiers 7-10) were attempted |

**Expected row counts per sheet:**
- P1_Subcap_Scoring: ~186 rows (range 170-200)
- P2_Subcap_Scoring: ~232 rows (range 210-250)
- P3_Subcap_Scoring: ~118 rows (range 105-135)
- P4_Subcap_Scoring: ~172 rows (range 155-190)
- **TOTAL: ~708 subcap rows across all 4 pillar sheets**

**The other sheets** are the contract's (`${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/contract.py: SHEETS`, 41 in all — among them
Executive_Summary, Pillar_Summary, Category_Detail (16 rows), Evidence_Detail, Peer_Benchmarks,
Recommendations, Run_Metadata, and the scoring-stage tabs Subcap_Scores, Pillar_Rollup,
Category_Rollup, Pillar_Weights, Maturity_Rubric, Cap_Triggers, Caps_Applied_Log, Coverage_Map).
They exist from `engine.cli start`; `engine.assessment rollup` and `engine.grains recompute`
fill the rollups; `engine.cli complete check` refuses an empty tab with no reason recorded.

**Self-check:** If any P#_Subcap_Scoring sheet has <50 rows → you scored at CATEGORY level.
STOP. Delete the sheet. Redo with one row per subcap ID.

---
