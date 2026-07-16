# v2 QA — Under-Leveraged Information Per Client Folder

Scope: the 5 real-sample DMA packages in
`backend/tests/fixtures/dma_packages_real_samples/`. Baseline:
`HEAD = 2c20f26` (Batch 9 ship-clean). Parser surface: docstring at
`backend/app/services/parsers/dma_package.py:11-40` declares the
ingested files; this artifact catalogs files PRESENT in each folder
but NOT named in that docstring (= under-leveraged) and maps each
to the frontend page where the AE / customer / admin would see the
gap.

Folders audited:
- `Alma_Bank__DMA/` (M&T-style bot output; ~$1.5B subvertical)
- `Calprivate_Bank__DMA/` (independent research output; pre-rendered VIZ pngs)
- `Nicola_Wealth__DMA/` (Wealth subvertical; per-pillar split XLSX + L2 governance)
- `Odlum_BROWN__DMA/` (Wealth subvertical; phase-5 priority analysis; L1+L2 verdicts)
- `WSFS_Bank__DMA/` (bot canonical; A1-A9 appendix CSV variant; check_results_pass1/2)

---

## Section A — Parser surface (`dma_package.py:11-40` docstring)

The docstring explicitly names these files. Anything else in the
folder is potentially under-leveraged.

| Subdir | Files parser DOES read |
|--|--|
| `01_evidence/` | `evidence_index.csv` ∨ `evidence_index.json` |
| `02_research_workbook/` | `research_handoff.json`, `*.xlsx` (raw Layer-0) |
| `03_scoring_workbook/` | `export_scoring_detail.csv`, `export_pillar_summary.csv`, `export_category_summary.csv`, `final_scores.json`, `*.xlsx` (raw Layer-1) |
| `04_reports/` | `*_Assessment_Report.docx`, `*_Client_Profile_Research_Report.docx` |
| `05_narrative_deck/` | (often empty; not parsed) |
| `06_peers/` | `peer_scores_*.json`, `peer_comparison_table.csv`, `peer_synthesis.md` (only if peer_scores parsed — `peer_synthesis.md` is read line 30 docstring only; verify usage in code) |
| `07_governance/` | `run_manifest.json`, `qa_verdict.json`, `audit_summary.json`, `layer1_issue_register.json`, `assessment_issue_register.json`, `issue_register.csv` |
| `08_appendices/` | `recommendations_detail.json`, `assessment_analysis.json`, `*_Explorium_Tech_Stack.xlsx`, `report_synthesis.md`, `run_manifest.json` (WSFS variant) |

**Parser fallback chain** (dma_package.py:880-896): run_manifest.json
searched at `07_governance/run_manifest.json` (Alma), then
`08_appendices/run_manifest.json` (WSFS), then
`03_scoring_workbook/run_manifest.json` (AmeriCU). Other paths
NOT searched.

---

## Section B — Per-folder under-leveraged inventory

For every file in each folder NOT named in §A, we capture:
- **size** (rough information density signal)
- **what it appears to contain** (file-name inference, validated by sampling)
- **frontend page** that would surface this if leveraged
- **end-user impact** (what an AE / customer / admin loses today)

### B.1 — Alma_Bank__DMA (under-leveraged: 6 files, ~841 KB)

| File | Size | Apparent content | Where it'd surface | End-user impact today |
|--|--|--|--|--|
| `01_evidence/scoring_scratchpad.json` | **788 KB** | Per-subcap reasoning trace (likely raw LLM scoring rationale) | HeatmapPage SynthesisDrawer (`backend/app/routers/heatmap.py:324` subcap endpoint) | AE clicks a cell, sees Vertex-generated synthesis instead of the actual scoring rationale that produced the score — disconnect between "why this score" (in scratchpad) and "what we synthesize now" |
| `07_governance/caps_applied_log.csv` | 917 B | Score-cap audit (subcaps where ceiling enforced) | HealthPage Gates tab (`HealthPage.tsx:485` Gates tab) | ANALYST cannot see WHY a score was capped (e.g. evidence_ceiling=2 limited subcap to score ≤ 2) — defensible-rationale story missing |
| `07_governance/patch_block.md` | 7.2 KB | Layer-1 review patch suggestions in markdown | HealthPage Patterns tab OR Admin pending-review (`admin.py:1080`) | Reviewer cannot see what an L1 critic ASKED to change — review/audit story incomplete |
| `08_appendices/assessment_analysis.json` | 6.6 KB | Cross-cutting strategic analysis | ClientOverviewPage why_now IntelligencePanel (`ClientOverviewPage.tsx:202`) | Meeting-prep talking points are LLM-synthesized when ground-truth analysis already shipped in the package |
| `08_appendices/report_synthesis.md` | 11 KB | Final report executive summary in markdown | ClientOverviewPage SCQA block (`ClientOverviewPage.tsx` line-of-Batch-9 M-1 chain) | The package SHIPPED a polished narrative; ClientOverview shows a per-pillar reconstructed one |
| `01_evidence/evidence_index.json` (parsed, but JSON-side fields not fully extracted) | 237 KB | Richer fields than CSV: source URLs, tier rationale, recency_months, ers (effective relevance score) | EvidenceDrawer (`evidence.py:168`) | UI shows excerpt + URL + tier but not the ERS or the tier-assignment rationale |

### B.2 — Calprivate_Bank__DMA (under-leveraged: 17 files including 5 PNGs)

| File | Size | Apparent content | Where it'd surface | End-user impact today |
|--|--|--|--|--|
| `01_evidence/search_log.json` | 4.6 KB | Per-query search trace (which queries the bot ran) | HealthPage Patterns OR Admin diagnostics | Cannot verify "did we look for X?" auditability story; reviewer must trust unverifiable absence-of-evidence claims |
| `03_scoring_workbook/calculation_chain.json` | 1.5 KB | Chain-of-thought score derivation | HeatmapPage SynthesisDrawer (`heatmap.py:324`) | Vertex re-synthesizes the rationale when it's already in the package |
| `06_peers/peer_benchmarks.json` | 2.6 KB | Aggregated peer subcap scores w/ percentile data | HeatmapPage peer overlay (`HeatmapPage.tsx:145` peer switch) | Peer-band shown is computed from peer_scores_*.json individually; pre-aggregated benchmarks IGNORED |
| `06_peers/peer_set.json` | 6.8 KB | Documented peer-set rationale (why these 5 peers) | ClientOverviewPage peer comparison strip | AE cannot answer "why these peers?" — credibility gap in customer-facing comparison |
| `07_governance/Layer1_qa_verdict.json` | 1.2 KB | L1 (first-pass) verdict separate from L2 | HealthPage Gates tab | Cannot see L1→L2 escalation; only the final verdict is surfaced |
| `07_governance/GOV_issue_register.csv` | 3.1 KB | Governance issues (distinct from L2 issues) | HealthPage Alerts tab (`HealthPage.tsx:208` Review/Waive) | Issues exist in 2 distinct lists; UI shows only one |
| `07_governance/GOV_patch_block.md` | 4.1 KB | Governance patch suggestions | Admin pending-review | Same as Alma `patch_block.md` |
| `07_governance/GOV_qa_verdict.json` | 2.0 KB | Governance verdict (distinct from L1+L2) | HealthPage Gates tab | 3-level verdict (L1, L2, GOV) collapsed into one shown |
| `07_governance/research_handoff.json` | 12 KB | **In 07_governance, not 02_research_workbook** — parser's `02_research_workbook` search misses it | EvidenceDrawer | Workbook↔handoff E-ID reconcile NEVER fires for Calprivate — E-IDs may be miscategorized by tier |
| `08_appendices/A1_Evidence_Index.csv` | 23.6 KB | Duplicate of `01_evidence/evidence_index.csv` but Calprivate ships JSON only in 01_evidence/ — A1 is the CSV form | Same as 01_evidence/evidence_index | Without the CSV in 01_evidence/, parser falls back to JSON; if JSON parse fails, A1 in 08 is the safety net but unused |
| `08_appendices/A3_Coverage_Map.csv` | 55.7 KB | Subcap → evidence coverage matrix | HeatmapPage cell hover ("3 of 5 evidence cited") | AE has no quick view of evidence density per subcap |
| `08_appendices/A4_Safeguard_Gates.csv` | 483 B | Gate-by-gate pass/fail | HealthPage Gates tab (currently hard-coded gate display) | Gate UI is decorative; real gates ARE in the package |
| `08_appendices/A5_Tier_Distribution.csv` | 224 B | Evidence tier distribution | HealthPage Age tab | T1/T2/T3/T4/T5 distribution not shown today |
| `08_appendices/A6_Tech_Stack_Summary.csv` | 2.3 KB | Tech stack summary | TechStackPage (`TechStackPage.tsx:195`) | Tech-stack page reads Explorium XLSX only; CSV summary IGNORED |
| `08_appendices/A7_Leadership_Summary.csv` | 2.0 KB | Leadership table (CSV form) | ClientOverviewPage leadership grid (`ClientOverviewPage.tsx:670-745`) | If DOCX parse fails to find leadership, A7 CSV is the safety net but unused |
| `08_appendices/A8_Issue_Register.csv` | 2.0 KB | Issue register (duplicate of 07 GOV_issue_register) | HealthPage Alerts tab | Same as above |
| `08_appendices/A9_Search_Log.csv` | 2.1 KB | CSV form of search_log.json | (same as B2 row 1) | (same) |
| `08_appendices/VIZ-01_evidence_quality.png` | 98 KB | **Pre-rendered chart** of evidence quality | ANY page could embed | UI renders its own charts; pre-rendered ones never used (consistency risk; could be the "official" version for export) |
| `08_appendices/VIZ-02_coverage_map.png` | 69.9 KB | Pre-rendered coverage map | HeatmapPage / Admin export | Same |
| `08_appendices/VIZ-03_opportunity_map.png` | 144.7 KB | Pre-rendered opportunity map | PlatformPage opportunity grid (`PlatformPage.tsx:104`) | Same |
| `08_appendices/VIZ-04_financial_trajectory.png` | 87.8 KB | Pre-rendered financial trajectory | ContextPage financials block | Same |
| `08_appendices/VIZ-05_tech_stack.png` | 105.2 KB | Pre-rendered tech stack visualization | TechStackPage | Same |
| `08_appendices/assumptions_register.json` | 5.0 KB | Documented analytical assumptions | HealthPage Patterns tab OR Admin diagnostics | Assumptions IS what makes a DMA defensible; not shown anywhere |
| `08_appendices/entity_profile.json` | 12.2 KB | Structured entity profile (firmographics + leadership + financials) | ClientOverviewPage header + ContextPage firmographics | Currently extracted via regex from DOCX (Batch 4.2); a STRUCTURED entity_profile.json would be far more reliable |
| `README.txt` (root) | 2.0 KB | Package documentation | nowhere (operator-only) | Lost context — what version of the bot generated this? |

### B.3 — Nicola_Wealth__DMA (under-leveraged: 27 files including 4 PNGs)

| File | Size | Apparent content | Where it'd surface | End-user impact today |
|--|--|--|--|--|
| `01_evidence/A1_Evidence_Master.csv` | 38.5 KB | Master evidence index (large) | EvidenceDrawer | Same as Calprivate A1 pattern |
| `01_evidence/A2_Search_Log.csv` | 4.7 KB | Search log | Admin diagnostics | Auditability gap |
| `01_evidence/A3_Subcap_Coverage_Map.csv` | 93.9 KB | **Massive** subcap × evidence map | HeatmapPage cell hover | Same as Calprivate A3 |
| `02_research_workbook/Nicola_Wealth_P1_Research.xlsx` | 281 KB | **Per-pillar XLSX (1 of 4)** | research_workbook.py expects 16 sheets in ONE file | Parser at `research_workbook.py` (per CLAUDE.md, looks for P1C1..P4C4 sheets in one XLSX); Nicola SPLIT them across 4 files — likely the parser only loads 1 of 4 (whichever it finds first) → 75% of research evidence lost |
| `02_research_workbook/Nicola_Wealth_P2_Research.xlsx` | 329 KB | P2 evidence | same | same |
| `02_research_workbook/Nicola_Wealth_P3_Research.xlsx` | 187 KB | P3 evidence | same | same |
| `02_research_workbook/Nicola_Wealth_P4_Research.xlsx` | 261 KB | P4 evidence | same | same |
| `02_research_workbook/NicolaWealth_research_handoff.json` | 85 KB | Massive handoff (compared to Alma's tiny one) | EvidenceDrawer tier rationale | Probably the richest handoff in the dataset; reconcile-with-workbook misses it |
| `03_scoring_workbook/NicolaWealth_Category_Summary.csv` | 1.0 KB | Custom-named category summary | (parsed via export_category_summary.csv) | Parser looks for `export_category_summary.csv`; `NicolaWealth_Category_Summary.csv` IS NOT detected → category breakdown empty for Nicola |
| `03_scoring_workbook/NicolaWealth_Pillar_Summary.csv` | 257 B | Custom-named pillar summary | (parsed via export_pillar_summary.csv) | Same — pillar summary empty |
| `03_scoring_workbook/NicolaWealth_Scoring_Detail.csv` | 59.3 KB | Custom-named scoring detail | (parsed via export_scoring_detail.csv) | Same — subcap_scores empty unless XLSX fallback kicks in |
| `03_scoring_workbook/export_coverage_stats.csv` | 276 B | Coverage stats | HealthPage Age tab | Not surfaced |
| `03_scoring_workbook/export_evidence_inventory.csv` | 11.7 KB | Evidence inventory | EvidenceDrawer | Not surfaced |
| `03_scoring_workbook/export_issue_register.csv` | 613 B | Issue register in 03 (not 07) | HealthPage Alerts tab | Parser only checks 07_governance — this is missed |
| `06_peers/02_peer_benchmarks.json` | 8.7 KB | Peer benchmarks (NUMERIC prefix variant) | HeatmapPage peer overlay | Same as Calprivate; numeric prefix variant prevents match |
| `06_peers/A6_Peer_Set_Locked.csv` | 1.7 KB | "Locked" peer set | ClientOverviewPage peer strip | Reviewer-locked peer set not shown |
| `07_governance/A5_Safeguard_Gates.csv` | 1.9 KB | Safeguard gates | HealthPage Gates tab | Same as Calprivate A4 |
| `07_governance/A7_Issue_Register.csv` | 2.5 KB | Issue register | HealthPage Alerts tab | Parser misses A-prefixed variant |
| `07_governance/A9_Assumptions_Register.csv` | 2.5 KB | Assumptions register | HealthPage Patterns OR Admin | Same as Calprivate assumptions_register.json |
| `07_governance/NicolaWealth_L2_IssueRegister.csv` | 3.0 KB | **L2 (second-pass)** issue register | HealthPage Alerts tab | L1 vs L2 distinction lost |
| `07_governance/NicolaWealth_L2_PatchBlock.md` | 6.3 KB | L2 patch block | Admin pending-review | Same as Alma patch_block.md |
| `07_governance/NicolaWealth_L2_QAVerdict.json` | 2.1 KB | L2 verdict | HealthPage Gates tab | Same |
| `07_governance/contradiction_log.csv` | 1.7 KB | **Contradictions found across sources** | HealthPage Patterns tab OR Admin | This is the "honest discomfort" signal — entirely missing from UI |
| `07_governance/reasoning_chain_log.json` | 9.9 KB | **Chain-of-thought audit log** | Admin diagnostics tab OR HeatmapPage SynthesisDrawer | The bot's REASONING is in the package; the UI re-runs Vertex to produce a different reasoning |
| `08_appendices/A8_Opportunities_Map.csv` | 3.1 KB | Opportunities map | PlatformPage opportunities grid | Not surfaced |
| `08_appendices/NicolaWealth_Chart1_Radar.png` | 178 KB | Pre-rendered radar chart | ClientOverviewPage scorecard preview | Same as Calprivate VIZ |
| `08_appendices/NicolaWealth_Chart2_Heatmap.png` | 132 KB | Pre-rendered heatmap | HeatmapPage | Same |
| `08_appendices/NicolaWealth_Chart3_Trajectory.png` | 138 KB | Pre-rendered trajectory | ContextPage trajectory block | Same |
| `08_appendices/NicolaWealth_Chart4_MaturityTrajectory.png` | 161 KB | Pre-rendered maturity trajectory | ClientOverviewPage history | Same |

### B.4 — Odlum_BROWN__DMA (under-leveraged: 9 files)

| File | Size | Apparent content | Where it'd surface | End-user impact today |
|--|--|--|--|--|
| `01_evidence/search_log.json` | 2.1 KB | Search log | Admin diagnostics | Auditability gap |
| `06_peers/benchmarks.json` | 6.7 KB | Peer benchmarks (no `peer_` prefix; parser-glob misses it) | HeatmapPage peer overlay | Same as Calprivate/Nicola pattern; differently named again |
| `07_governance/L1_qa_verdict.json` | 803 B | L1 verdict | HealthPage Gates tab | L1↔L2 distinction lost |
| `07_governance/L2_issue_register.csv` | 870 B | L2 issue register | HealthPage Alerts tab | L1↔L2 distinction lost |
| `07_governance/L2_patch_block.md` | 3.8 KB | L2 patch block | Admin pending-review | Same |
| `07_governance/L2_qa_verdict.json` | 3.2 KB | L2 verdict | HealthPage Gates tab | Same |
| `07_governance/contradiction_log.csv` | 1.3 KB | Contradiction log | HealthPage Patterns tab | Same as Nicola |
| `07_governance/critic_log.json` | 1.8 KB | LLM critic responses | Admin diagnostics | Critic critique invisible to reviewer |
| `07_governance/recommendations_register.json` | **41.8 KB** | **Recommendations register IN 07_governance** | Parser looks for `08_appendices/recommendations_detail.json`; this is in 07 with a different name | 41.8 KB of recommendations + linked subcaps + evidence — entirely MISSED for Odlum; ClientOverviewPage recs grid will be EMPTY |
| `07_governance/scoring_exports/export_*.csv` (3 files) | 63 KB | **Nested scoring exports** in 07_governance/scoring_exports/ | Parser looks for `03_scoring_workbook/export_*.csv` | If parser doesn't recurse into 07/scoring_exports, the FINAL scoring exports are missed — Odlum's scoring may come from raw XLSX only |
| `08_appendices/calculation_chain.json` | 652 B | Calculation chain | HeatmapPage SynthesisDrawer | Same as Calprivate (different folder) |
| `08_appendices/phase5_priority_analysis.json` | 1.6 KB | Phase-5 priority analysis | ClientOverviewPage top findings (`ClientOverviewPage.tsx:597` Finding accordion) | Final-phase priorities directly from bot; not surfaced |

### B.5 — WSFS_Bank__DMA (under-leveraged: 15 files)

| File | Size | Apparent content | Where it'd surface | End-user impact today |
|--|--|--|--|--|
| `01_evidence/A1_evidence_index_full.csv` | 39 KB | **Full evidence index (distinct from `evidence_index.csv`)** | EvidenceDrawer | Likely a SUPERSET of the parsed CSV; richer fields missed |
| `01_evidence/A4_source_url_index.csv` | 16 KB | Source URL index | EvidenceDrawer URL chip | URL deduping data ignored |
| `01_evidence/A5_ers_distribution.csv` | 368 B | ERS (effective relevance score) distribution | HealthPage Age tab | Not surfaced |
| `01_evidence/A6_proxy_search_log.csv` | 1.5 KB | Proxy search log | Admin diagnostics | Auditability gap |
| `02_research_workbook/A2_peer_comparison.csv` | 2.9 KB | **Peer comparison in research folder** | Parser looks for `06_peers/peer_comparison_table.csv` | Peer data in 02; not 06; missed if parser strict on path |
| `02_research_workbook/A3_subcap_coverage.csv` | 1.2 KB | Subcap coverage in research folder | HeatmapPage cell hover | Not surfaced |
| `02_research_workbook/A7_leadership_map.csv` | 2.9 KB | Leadership map in research folder | ClientOverviewPage leadership grid | Parser only reads DOCX for leadership |
| `02_research_workbook/A8_research_issue_register.csv` | 3.8 KB | Issues from research phase | HealthPage Alerts tab | Distinct from 07_governance issues |
| `03_scoring_workbook/export_coverage_stats.csv` | 69 B | Coverage stats | HealthPage Age tab | Same as Nicola |
| `03_scoring_workbook/rollup_data.json` | 5.4 KB | Rollup data (likely pillar+category aggregations) | ClientOverviewPage pillar bars | Pillar bars computed from subcap_scores; pre-aggregated rollups ignored |
| `07_governance/assessment_issue_register.json` | 7.9 KB | (parsed per docstring line 33) | HealthPage Alerts tab | Parser does read; verify field-level extraction |
| `07_governance/check_results_pass1.json` | 11.5 KB | **L1 check results** (large) | HealthPage Gates tab | L1 detailed check results lost |
| `07_governance/check_results_pass2.json` | 1.9 KB | L2 check results | HealthPage Gates tab | L2 detailed check results lost |
| `07_governance/patch_block.md` | 6.1 KB | Patch block | Admin pending-review | Same as Alma |
| `08_appendices/A9_tech_stack_raw_or_issue_register.csv` | 2.1 KB | Either tech stack raw OR an issue register (naming ambiguous) | TechStackPage OR HealthPage | Ambiguity itself a parser problem — filename suggests bot uncertainty |

---

## Section C — Cross-folder gap classes (the real improvement opportunities)

### C1 — Per-pillar XLSX split (Nicola_Wealth only) — **RECLASSIFIED** (2026-06-07)

**Original finding (incorrect):** Nicola ships 4 XLSX files
(`Nicola_Wealth_P1_Research.xlsx` … P4) and the parser only loads
the first; assumed to be a P1C1..P4C4 sheet-split losing P2/P3/P4
evidence rows.

**Reality (verified 2026-06-07):** Nicola's per-pillar XLSX files
are **scoring toolkits organized by subvertical**, NOT evidence
workbooks. Each file's sheets are:

```
Weight Summary
Credit Unions
Regional Banks
Lending
CIB
RIAs & Broker-Dealers
Asset Management
Insurance Carriers
Insurance Brokers
Research_Metadata
```

Each sheet contains a 12-column **capability-mapping rubric** —
`Category ID | Category Name | Cap ID | Capability | Sub-Cap ID |
Sub-Capability | Tier | Diagnostic Question | Internal Evidence
Sources | Public/External Evidence Sources | Source Type | Weight %`.
These are reference toolkits the assessor consulted, not
assessment-specific evidence about Nicola Wealth Management.

Running `parse_per_pillar_sheets` against any of the 4 files yields
**0 rows / 0 warnings / 0 observations** — the parser correctly
recognizes the format mismatch and skips. No data is lost.

- **End-user impact:** **None.** Nicola's evidence (149 rows) comes
  entirely from `01_evidence/evidence_index.csv`; the XLSX
  enrichment step is a no-op for Nicola but adds nothing the
  evidence index doesn't already have.
- **Action:** none in parser. The under-leveraged matrix's original
  C1 hypothesis was wrong about the file shape. Closed.
- **Cascade-guard test:** pinned in
  `test_qa_v2_5folder_ingestion.py::test_c1_nicola_per_pillar_xlsx_is_subvertical_toolkit_not_evidence`
  so a future contributor doesn't reopen this with the same
  mis-diagnosis.

### C2 — Non-canonical scoring CSV names (Nicola_Wealth, likely WSFS variant)
- **Symptom:** Nicola ships `NicolaWealth_Scoring_Detail.csv` instead
  of `export_scoring_detail.csv` (both at
  `03_scoring_workbook/`).
- **Risk:** parser at `package_csvs.py` (the CSV leaf) globs for
  `export_*.csv`; non-conforming names skipped → `subcap_scores`
  table empty unless XLSX-fallback fires.
- **Files affected:** `package_csvs.py`,
  `package_persist.py:811-921` subcap_scores UPSERT.
- **End-user impact:** Nicola's heatmap shows ALL subcaps as "no
  data" — entire assessment effectively missing from UI.
- **Fix scope:** add glob `(export_|*_)scoring_detail.csv`,
  `(export_|*_)pillar_summary.csv`, `(export_|*_)category_summary.csv`.
- **Verification:** ingest Nicola, count `subcap_scores WHERE run_id=…`;
  must equal NicolaWealth_Scoring_Detail.csv row count.

### C3 — Recommendations register location drift (Odlum_BROWN)
- **Symptom:** Odlum ships
  `07_governance/recommendations_register.json` (42 KB) instead of
  `08_appendices/recommendations_detail.json`.
- **Risk:** parser at `dma_package.py:_load_recommendations` (line
  ranges per docstring §A) globs strict path → recommendations
  empty for Odlum.
- **Files affected:** parser load fn (find via grep), persist at
  `package_persist.py:1009-1039` recommendations UPSERT.
- **End-user impact:** ClientOverviewPage recommendations strip and
  RecommendationsPage detail are EMPTY for Odlum despite 42 KB of
  detailed recs in the package.
- **Fix scope:** check both `08_appendices/recommendations_detail.json`
  AND `07_governance/recommendations*.json`.

### C4 — Nested scoring_exports dir (Odlum_BROWN)
- **Symptom:** Odlum has `07_governance/scoring_exports/export_*.csv`
  (~63 KB final scoring) instead of `03_scoring_workbook/export_*.csv`.
- **Risk:** parser does not recurse beyond direct children of 03.
- **Files affected:** `dma_package.py:730-744` scoring CSV scan.
- **End-user impact:** Odlum's final scoring uses RAW XLSX (Layer-1
  scoring) instead of the post-cap exports → cap-applied scores not
  shown.
- **Fix scope:** include `**/scoring_exports/export_*.csv` in scan.

### C5 — L1 / L2 governance distinction lost (Alma_Bank, Calprivate, Nicola, Odlum, WSFS — ALL 5)
- **Symptom:** every folder distinguishes L1 (first-pass) and L2
  (second-pass) governance verdicts via separate files (e.g.
  `L1_qa_verdict.json` + `L2_qa_verdict.json`), but the parser
  + `health.py` router collapse them into one `qa_verdict.json`.
- **Risk:** "did the L1 pass and then L2 found new issues?"
  invisible to reviewer.
- **Files affected:** parser load fn (find via grep); `health.py`
  Gates tab response.
- **End-user impact:** ANALYST cannot see escalation; reviewer
  cannot validate the 2-stage QA chain that was actually performed.
- **Fix scope:** add `qa_verdict_l1` + `qa_verdict_l2` fields to
  HealthResponse; surface both in HealthPage Gates tab tile rows.

### C6 — Pre-rendered VIZ PNGs (Calprivate, Nicola_Wealth)
- **Symptom:** Calprivate ships 5 PNGs (VIZ-01…05); Nicola ships
  4 PNGs (Chart1…4).
- **Risk:** UI renders its own visualizations; pre-rendered ones
  IGNORED. Export endpoints (scorecard HTML/PDF) may show DIFFERENT
  charts than what the analyst signed off on.
- **Files affected:** `prospecting.py:262` scorecard export;
  `app/services/scorecard_renderer.py` (if exists).
- **End-user impact:** Customer-facing scorecard shows
  React-generated charts that differ visually from the bot's
  signed-off output; trust gap.
- **Fix scope:** if `08_appendices/VIZ-*.png` or
  `08_appendices/*_Chart*.png` exist, embed those into export
  instead of re-rendering.

### C7 — Reasoning chain + contradiction logs (Nicola, Odlum)
- **Symptom:** `07_governance/reasoning_chain_log.json` (9.9 KB,
  Nicola), `07_governance/contradiction_log.csv` (Nicola, Odlum),
  `07_governance/critic_log.json` (Odlum).
- **Risk:** the bot's actual reasoning chain (CoT) is in the
  package, but the UI re-runs Vertex to synthesize a different
  rationale.
- **Files affected:** synthesis_orchestrator.py 8-gate decision;
  HeatmapPage SynthesisDrawer.
- **End-user impact:** AE sees Vertex-fresh synthesis; ANALYST
  cannot audit the bot's original reasoning; reviewer trust gap.
- **Fix scope:** when reasoning_chain_log.json is present, prefer
  it as the primary subcap-detail narrative; only fall back to
  Vertex when missing.

### C8 — Scoring scratchpad (Alma_Bank only, 788 KB) — **RECLASSIFIED** (2026-06-07)

**Original finding (incorrect):** Alma's
`01_evidence/scoring_scratchpad.json` (788 KB) was presumed to carry
analyst rationale that the parser ignored, forcing SynthesisDrawer
to re-run Vertex at runtime.

**Reality (verified 2026-06-07):** the scratchpad's per-subcap
`Rationale` field IS reaching `SubcapScoreRow.rationale` via the XLSX-
enrichment path (`dma_package.py:1230` rationale_lookup). Direct
comparison across Alma's 698 subcaps:

```
Scratchpad rationale chars: 703
Parsed rationale chars:     703
EQUAL? True
```

100% of Alma's 698 subcaps already carry the full 700+ char analyst
rationale on `pkg.subcap_scores[*].rationale`. The scratchpad is a
redundant copy of data already extracted via the XLSX path; no
SynthesisDrawer Vertex waste.

- **End-user impact:** **None.** The Vertex re-synthesis concern was
  hypothetical — the analyst rationale is already persisted on
  `subcap_scores.rationale` (column populated since the initial
  schema) and surfaced via the heatmap subcap-detail endpoint.
- **Action:** none in parser. The under-leveraged matrix's original
  C8 hypothesis was based on an incomplete inventory of XLSX
  enrichment paths. Closed.
- **Cascade-guard test:** pinned in
  `test_qa_v2_5folder_ingestion.py::test_c8_alma_subcap_rationale_already_100pct_populated`
  so a future contributor doesn't reopen the same mis-diagnosis.

### C9 — Entity profile JSON (Calprivate)
- **Symptom:** `08_appendices/entity_profile.json` (12.2 KB) ships
  a STRUCTURED entity profile; parser uses regex on DOCX
  (`client_profile.py` Batch 4.2 fix) for the same fields.
- **Risk:** regex fragility vs. JSON structured data.
- **Files affected:** `client_profile.py` firmographics regex;
  `package_persist.py:614-668` firmographics UPSERT.
- **End-user impact:** when regex fails (any future DOCX format
  variant), firmographics blank — but JSON would have given perfect
  fidelity.
- **Fix scope:** prefer `entity_profile.json` when present;
  fallback to regex when absent.

### C10 — Caps applied log (all 5)
- **Symptom:** `07_governance/caps_applied_log.csv` in every
  folder; never parsed.
- **Risk:** capped scores look like "the assessment scored low"
  rather than "evidence ceiling prevented a higher score".
- **Files affected:** HealthPage Gates tab.
- **End-user impact:** Defensible-rationale story lost; AE cannot
  explain "score is 2 because evidence_ceiling capped it" — they
  see only "score is 2".
- **Fix scope:** persist caps_applied_log per run; surface in
  HealthPage Gates as a sortable table.

### C11 — Assumptions register (Calprivate, Nicola)
- **Symptom:** `08_appendices/assumptions_register.json` (5.0 KB,
  Calprivate); `07_governance/A9_Assumptions_Register.csv` (2.5 KB,
  Nicola).
- **End-user impact:** Customer sees a "facts" presentation; AE
  cannot explain "we assumed X because no public data on Y" — looks
  weaker than it should.
- **Fix scope:** persist assumptions; surface in ClientOverviewPage
  data-source footer.

### C12 — Search logs + critic logs + check_results (auditability)
- **Symptom:** various per-folder audit logs:
  - `01_evidence/search_log.json` (Calprivate, Odlum)
  - `01_evidence/A2_Search_Log.csv` (Nicola)
  - `01_evidence/A6_proxy_search_log.csv` (WSFS)
  - `07_governance/check_results_pass1.json` + `_pass2.json` (WSFS)
  - `07_governance/critic_log.json` (Odlum)
- **End-user impact:** ADMIN cannot answer "what did the bot
  actually search for?" — audit story broken.
- **Fix scope:** admin diagnostics tile listing each log type;
  ADMIN can drill in.

---

## Section D — Severity ranking + fix order

| Class | Severity | Affected folders | Frontend pages affected | Fix LOC est. | Cascade risk |
|--|--|--|--|--|--|
| **C2** non-canonical scoring CSV names | **P0** | Nicola_Wealth | HeatmapPage, ClientOverviewPage, all subcap consumers | parser:~30 LOC | Low — additive glob |
| **C3** recommendations register location drift | **P0** | Odlum_BROWN | ClientOverviewPage, RecommendationsPage | parser:~20 LOC | Low — additive path |
| **C4** nested scoring_exports dir | **P0** | Odlum_BROWN | HeatmapPage, HealthPage | parser:~20 LOC | Low — additive recurse |
| **C1** per-pillar XLSX split | **P1** | Nicola_Wealth | HeatmapPage evidence chips, EvidenceDrawer | parser:~40 LOC | Medium — research_workbook iteration semantics change |
| **C8** scoring_scratchpad (Alma) | **P1** | Alma_Bank | HeatmapPage SynthesisDrawer | parser:~40 LOC + new table | Medium — new persistence target |
| **C9** entity_profile.json (Calprivate) | **P1** | Calprivate_Bank | ClientOverviewPage header, ContextPage firmographics | parser:~30 LOC | Low — fallback chain |
| **C5** L1/L2 verdict distinction | **P2** | ALL 5 | HealthPage Gates tab | parser + schema:~50 LOC | Medium — schema additions |
| **C7** reasoning chain + contradiction logs | **P2** | Nicola, Odlum | HeatmapPage SynthesisDrawer | parser + synthesis flow:~80 LOC | High — touches Vertex 8-gate |
| **C10** caps applied log | **P2** | ALL 5 | HealthPage Gates tab | parser + new schema field | Low — additive |
| **C11** assumptions register | **P3** | Calprivate, Nicola | ClientOverviewPage footer | parser + new schema field | Low |
| **C12** search/critic logs (auditability) | **P3** | Cal, Odlum, Nicola, WSFS | AdminPage diagnostics | parser + admin route | Low |
| **C6** pre-rendered VIZ PNGs | **P3** | Cal, Nicola | ProspectingPage export | export pipeline change | Medium — export contract |

---

## Section E — Cascade-gate considerations for these fixes

Each fix above will go through cascade gates per the v2 plan:

- **Gate 2 (post-Phase-2):** for each parser change, re-run all 8
  fixtures + verify Batch 6 baselines unchanged for the others
  (e.g. richbank/regions/etc.) — additive globs MUST NOT pick up
  unintended files in other folders.
- **Gate 3:** verify no frontend page state changes (these are
  data-additive fixes; UI components should fall through to the
  new data without re-rendering errors).
- **Gate 5:** TDD-by-revert per Batches 7-9 — every parser fix
  has a contract test that fails on the broken path AND passes
  after fix.

---

## Section F — Next steps

1. Spin up local PG + Redis + uvicorn (Phase 1 Step 1.1).
2. Run `parse_package` against each of the 5 folders, capture
   per-folder `IngestedPackage` shape: subcap_count, evidence_count,
   recommendations_count, peer_count, focus_area_count,
   parser_warnings, leadership_count, firmographics fields.
3. Compare against folder content (count cells in scoring_detail
   CSV, count rows in evidence index, etc.) → quantify the
   under-leveraged information per folder.
4. Per-class fix proposals enter `qa_patch_backlog.md` (Phase 5
   artifact) with TDD-by-revert validation block.
5. Cascade gates 1-5 + Production-Ready Gate gate the merge.

This artifact is the first concrete evidence row for Phase 2B of
the v2 QA plan, scoped to the user's explicit directive: **use the
5 client folders to find under-leveraged information**.
