# DMA run snapshot telemetry — quantitative extract

Generated 2026-10-09 from the run-tree snapshots in the owner's Drive. Scripts: `scratchpad/snap_tools/{unpack,extract,report}.py`; per-run raw extracts: `scratchpad/snapshot_telemetry/<run>.json`.

## Coverage and caveats

- **Downloaded and analysed (3 of 5):** Arbor Bank (4.9 MB), Susser Bank (5.9 MB), Cross Insurance Agency (4.1 MB).
- **Could not be downloaded (2 of 5):** B1 Bank (`1SrMcxXoBEqfq9iCXCXse6r9ndsGWO_vR`, 8.7 MB) and First Tech FCU (`1aIVkqonSJWhsppZ9WthmsZwlv7vfTJbc`, 7.2 MB). Each was tried twice; both times the Google Drive MCP connection closed with "message from the server was too large or could not be parsed" (base64 payload ≈ 11.6 M and 9.6 M chars; the largest payload that came through was Susser at 7.8 M chars). No partial result was saved. They need a smaller export (split tar, or share via GCS) before this telemetry can be produced for them.
- `agent_logs/` is absent from all three snapshots (as expected). `scoring_workflow.json`, `reports_workflow.json`, `pages_workflow.json`, `enforcement_rungs.json` and `run_manifest.json` are **absent in all three** 07_qa trees; only `research_workflow.json` is present (and it holds the *last* handoff, not the first). Estimates for scoring/reports/pages are therefore "not recorded" except where a Gate_Log row carries them.
- Search_Log has no Actor column in any run (columns: Seq, Timestamp, SubCap_ID, Facet, Query, Tool, Hits, Kept, Outcome), so per-actor search counts are not recorded; `report_reviews.jsonl` has no `upstream` field (upstream routing is only mentioned inside `note`).
- USD and token figures come from `07_qa/cost_ledger.jsonl` (`agent_run` batch rows and `workflow agents: N charged` rows). Pipeline-only stages (KG, HANDOFF, INGEST_*, PACKAGE, PROMOTE) record elapsed time but no USD — reported as "not recorded". RESEARCH USD is the connector/workflow charge captured as deltas; its tokens are the workflow agents' tokens.
- 'Wall' per stage = first ledger timestamp of the stage → last ledger timestamp of the stage (includes idle/human gaps between resumes). 'Agent elapsed' = sum of agent_run batch elapsed_s.


---

# Arbor Bank (2026-10-05→07) — `arbor-bank-2026-10-05`

Sub-vertical **CL**, evidence mode PUBLIC, **708 subcaps** selected of 851; overall 1.08; promoted at **2026-10-07T07:22:45.544420+00:00**. Ledger span 2026-10-05T03:15Z → 2026-10-07T07:22Z = **52.1 h wall clock**; Run_Metadata.cost_summary: {'stages': 12, 'total_elapsed_s': 60384.8, 'total_usd': 409.0977, 'turns': 11076}; pipeline_state spent/budget: 409.0977/475.0; pipeline invocations recorded: 41.

## 1. Stage table (cost_ledger.jsonl + Gate_Log STAGE_* rows)

| stage | started | ended | wall min | agent elapsed min | pipeline rounds (sum of 'after N round/attempt') | batches / lanes / attempts | USD | tokens (cache_read / cache_write / uncached / output) | STAGE_* verdicts → final |
|---|---|---|---|---|---|---|---|---|---|
| PRELIM | 2026-10-05T03:07Z | 2026-10-06T07:59Z | 1731.6 | 11.6 | 2 | 2 / 4 / 4 | $5.66 | cr 8,212,291 / cw 359,587 / unc 176 / out 50,003 | {'PASS': 2} → PASS |
| KG | 2026-10-05T03:15Z | 2026-10-05T03:15Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| RESEARCH | 2026-10-05T03:15Z | 2026-10-06T07:59Z | 1724.0 | 0.0 | 0 | 0 / 0 / 0; 412 workflow agents charged | $254.15 | cr 557,053,527 / cw 55,735,089 / unc 15,146 / out 337,424 | {'PENDING_ORCHESTRATOR': 15} → PENDING_ORCHESTRATOR |
| HANDOFF | 2026-10-05T09:11Z | 2026-10-05T09:16Z | 5.6 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'FAIL': 1, 'PASS': 1} → PASS |
| SCORING | 2026-10-05T09:17Z | 2026-10-06T04:14Z | 1137.1 | 158.9 | 19 | 41 / 98 / 98 | $40.69 | cr 47,347,513 / cw 4,217,496 / unc 2,294 / out 678,259 | {'FAIL': 3, 'PASS': 1} → PASS |
| INGEST_A | 2026-10-06T04:43Z | 2026-10-06T04:43Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| REPORTS | 2026-10-06T08:04Z | 2026-10-06T12:34Z | 269.6 | 211.0 | 19 | 39 / 59 / 60 | $73.57 | cr 110,805,434 / cw 5,372,343 / unc 2,480 / out 1,076,980 | {'FAIL': 3, 'PASS': 1} → PASS |
| PAGES_A | 2026-10-06T15:00Z | 2026-10-06T16:38Z | 98.1 | 24.5 | 13 | 12 / 24 / 24 | $12.92 | cr 16,982,307 / cw 1,519,992 / unc 584 / out 215,997 | {'FAIL': 5, 'PASS': 1} → PASS |
| PACKAGE | 2026-10-06T16:39Z | 2026-10-06T16:39Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| INGEST_B | 2026-10-06T17:15Z | 2026-10-06T17:15Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| PAGES_B | 2026-10-06T17:17Z | 2026-10-07T07:21Z | 844.8 | 36.5 | 11 | 11 / 26 / 31 | $22.10 | cr 31,409,707 / cw 2,390,598 / unc 844 / out 430,505 | {'FAIL': 7, 'PASS': 2} → PASS |
| PROMOTE | 2026-10-07T02:22Z | 2026-10-07T07:22Z | 300.6 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'FAIL': 2, 'PASS': 1} → PASS |

**Total:** wall clock 52.1 h (first→last ledger row); **USD 409.10** (ledger) vs Run_Metadata.cost_summary.total_usd 409.0977; tokens cr 771,810,779 / cw 69,595,105 / unc 21,524 / out 2,789,168; turns 11076.

STAGE_* FAIL rows (21):
  - HANDOFF: REFUSED: 4 tab(s) are empty with no reason recorded. A workbook that validates and carries nothing is the Golden 1 shape: shape-correct, content-empty.
  - Tech_Peer_Deployments: empty, and no reason 
  - SCORING: terminated by signal 15: the running batch was told to stop its lanes; resume with `engine.pipeline run` [elapsed 766.6s; rounds 3]
  - SCORING: SCORING gate FAIL after 6 round(s): critic_failed, critic_missing, dashboard_incomplete, rollup_missing, unscored; the rollup has no headline — the scoring-critic lane records it (`engine.assessment r
  - SCORING: SCORING gate FAIL after 4 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - REPORTS: reports not READY after 5 round(s): client_research, assessment; blocking: client_research: §1, §3, §4, §5, §6 not READY; assessment: §6 not READY — stopped at round 5: the last 2 round(s) advanced no
  - REPORTS: terminated by signal 15: the running batch was told to stop its lanes; resume with `engine.pipeline run` [elapsed 980.4s; rounds 3]
  - REPORTS: reports not READY after 10 round(s): assessment; blocking: assessment: §8 not READY [elapsed 6846.3s; rounds 10]
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-14', 'section': 'techstack', 'path': 'techstack.items[5].linked_subcap_ids[1]', 'mes; heatmap: {'gate_id': 'CG-15', 'sec
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x38 over budget 8 — find grounding or drop the claim, techstack.items[0].detection_basis (sim 0.45 < 0.55); heatmap
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'coh
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'coh
  - PAGES_A: page(s) not passing on version A after 1 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'coh
  - PAGES_B: page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-18', 'section': 'firmographics', 'path': 'firmographics.fields', 'message': "must-pr, {'gate_id': 'CG-18', 'section': 'fi
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-005 reso, {'gate_id': 'ET-07', 'section': 'ex
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'CG-31', 'section': 'opportunity', 'path': 'overview.opportunity.tiles[1].composite', 'm; insights: SG-V4 grounding FAIL x112
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: SG-V4 grounding FAIL x167 over budget 8 — find grounding or drop the claim, ceilings.narrative_thread (sim 0.397 < 0.5); insights: SG-V4 
  - PAGES_B: page(s) not passing on version B after 3 attempt(s): context: {'gate_id': 'ET-07', 'section': 'issue_register', 'path': 'issue_register.e_ids', 'message': "E-006 , {'gate_id': 'ET-07', 'section': 'tim
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-46', 'section': 'issue_register', 'path': 'context.issue_register.empty_state', 'mes, {'gate_id': 'AG-03', 'section': 'con
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'ET-07', 'section': 'issue_register', 'path': 'issue_register.e_ids', 'message': "E-006 , {'gate_id': 'AG-03', 'section': 'con
  - PROMOTE: promote_run refused: {"promoted": false, "error": "retained_pages_fail_current_gates", "pages": ["overview", "platform"], "reasons": {"overview": [{"gate_id": "CG-PAR", "section": "sentiment", "path":
  - PROMOTE: promote_run refused: {"promoted": false, "error": "retained_pages_fail_current_gates", "pages": ["overview", "platform"], "reasons": {"overview": [{"gate_id": "CG-PAR", "section": "sentiment", "path":

## 2. Workflow estimates

- **Research** (STAGE_RESEARCH PENDING_ORCHESTRATOR rows = handoffs to the conducting session): **15 handoffs**. First: 16 categories × 81 batches for 708 open cells, est **$141.56** (basis `pilot $0.19/cell + $0.44/category challenge`). Sum of all handoff estimates $302.25; sum of open cells re-handed 1252 (+3 repair cells). Actual research charge (ledger) **$254.15** over 412 workflow agents; workflow_costs_recorded.json: {'agents': 412, 'usd': 254.15, 'turns': 7602}.
  - Handoff sequence (at | cats | batches | open+repair cells | est $): 10-05T03:15 | 16 | 81 | 708+0 | 141.56; 10-05T04:51 | 13 | 8 | 67+0 | 18.45; 10-05T05:12 | 13 | 8 | 67+0 | 18.45; 10-05T08:19 | 11 | 13 | 73+0 | 18.71; 10-05T10:38 | 16 | 18 | 102+0 | 26.42; 10-05T13:03 | 15 | 12 | 61+0 | 18.19; 10-05T14:02 | 15 | 12 | 61+0 | 18.19; 10-05T16:02 | 15 | 12 | 61+0 | 18.19; 10-05T16:30 | 8 | 8 | 12+0 | 5.8; 10-05T17:04 | 3 | 3 | 6+0 | 2.46; 10-05T18:58 | 8 | 8 | 23+0 | 7.89; 10-05T23:18 | 5 | 5 | 7+0 | 3.53; 10-05T23:26 | 3 | 3 | 3+0 | 1.89; 10-05T23:33 | 1 | 1 | 1+0 | 0.63; 10-06T07:59 | 3 | 3 | 0+3 | 1.89
  - Last research_workflow.json: estimate {'open_cells': 0, 'repair_cells': 3, 'batches': 3, 'categories': 3, 'usd': 1.89, 'basis': 'pilot $0.19/cell + $0.44/category challenge', 'spent_at_handoff': 300.5, 'research_at_handoff': 254.15, 'spent_usd': 300.5, 'budget_usd': 400.0, 'fits_budget': True}; invocations: P1 cats=['P1C2'] batches={'P1C2': 0} batch_cells={'P1C2': 0} repair_cells={'P1C2': 1} rounds=2; P4 cats=['P4C3'] batches={'P4C3': 0} batch_cells={'P4C3': 0} repair_cells={'P4C3': 1} rounds=2; P4 cats=['P4C4'] batches={'P4C4': 0} batch_cells={'P4C4': 0} repair_cells={'P4C4': 1} rounds=2
- **Scoring**: scoring_workflow.json not recorded. Observed: 41 lane batches, 98 lanes dispatched (0 failed), agents {'scoring-p1-producer': 19, 'scoring-p2-producer': 19, 'scoring-p3-producer': 19, 'scoring-p4-producer': 19, 'technographic-scanner': 4, 'scoring-critic': 18}; briefs dirs scoring_r*/scoring_critic_r*: 39; Subcap_Scoring rows per pillar: not in workflow file — see §4 Provenance counts.
- **Reports**: reports_workflow.json not recorded. Observed: 39 lane batches, 59 lanes, agents {'enrichment-web-specialist': 8, 'report-assessment-producer': 19, 'report-research-producer': 14, 'report-validator': 18}; briefs reports_r* dirs = **19 rounds**; Report_Narrative sections = 31.
- **Pages**: pages_workflow.json not recorded. Observed: briefs dirs ['pages_A_0_assemble', 'pages_A_0_challenge', 'pages_A_0_consolidate', 'pages_A_0_fragments', 'pages_A_1_assemble', 'pages_A_2_assemble', 'pages_B_0_assemble', 'pages_B_0_challenge', 'pages_B_0_consolidate', 'pages_B_0_fragments', 'pages_B_1_assemble', 'pages_B_2_assemble'] (files per dir: {'pages_A_0_assemble': 5, 'pages_A_0_challenge': 3, 'pages_A_0_consolidate': 3, 'pages_A_0_fragments': 17, 'pages_A_1_assemble': 5, 'pages_A_2_assemble': 5, 'pages_B_0_assemble': 9, 'pages_B_0_challenge': 3, 'pages_B_0_consolidate': 3, 'pages_B_0_fragments': 33, 'pages_B_1_assemble': 9, 'pages_B_2_assemble': 9}); PAGES_A lanes 24 ({'heatmap-evidence-producer': 1, 'heatmap-focus-producer': 1, 'heatmap-freshness-producer': 1, 'heatmap-grid-producer': 1, 'heatmap-signals-producer': 1, 'heatmap-valuechain-producer': 1, 'techstack-layers-producer': 1, 'techstack-register-producer': 1, 'finding-challenger': 1, 'page-consolidator': 1, 'heatmap-surface-producer': 9, 'techstack-surface-producer': 5}); PAGES_B lanes 31 ({'insights-cards-producer': 1, 'insights-landscape-producer': 1, 'overview-findings-producer': 1, 'overview-governance-producer': 1, 'overview-hero-producer': 1, 'overview-market-producer': 1, 'overview-narrative-producer': 1, 'overview-opportunity-producer': 1, 'overview-people-producer': 1, 'overview-whynow-producer': 1, 'platform-conversation-producer': 1, 'platform-fit-producer': 1, 'platform-roadmap-producer': 1, 'finding-challenger': 1, 'page-consolidator': 1, 'insights-surface-producer': 3, 'overview-surface-producer': 4, 'platform-surface-producer': 3, 'context-risk-producer': 1, 'context-sentiment-producer': 1, 'context-timeline-producer': 1, 'context-surface-producer': 3}); 08_sections files 34, backup dirs ['_bak_pre_B_repair', '_bak_pre_assemble', '_bak_pre_context', '_bak_pre_peers', '_bak_pre_promote', '_bak_pre_rbdrop', '_bak_pre_realign', '_bak_pre_rerank', '_bak_pre_v4repair'].
- **PRELIM**: lanes {'files': 2, 'dispatched': 4, 'ok': 4, 'failed': 0, 'usd': 5.66, 'agents': {'research-conductor': 2, 'technographic-scanner': 2}, 'retries': 0, 'lane_attempts_gt1': 0}.

## 3. RESEARCH

FLOORS gate rows total **212** (164 FAIL, 48 PASS) over 16 categories; blocking-term frequency across failing rounds: {'challenge_failed': 68, 'absence_undeclared_empty': 62, 'single_source_fact': 60, 'primary_unfired': 55, 'volleys_incomplete': 47, 'challenge_missing': 37, 'absence_unsearched': 28, 'claim_unsupported': 18, 'synthesis_missing': 9, 'boilerplate': 2}. FLOORS_WAIVER rows: 4 (P1C2: "P1C2.3.2", "P1C2.6.2", "P1C2.6.4", "P1C2.7.3"; P4C3: "P4C3.4.1"; P4C4: "P4C4.1.1", "P4C4.3.1"; P3C1: "P3C1.3.RB1"). Challenge_Log: {'FAIL': 205, 'PASS': 182}. Provenance steps: {'absence': 693, 'attach': 121, 'synthesis': 642, 'challenge': 385, 'score': 860, 'tech_register_restrike:TS-001': 1, 'tech_register_restrike:TS-002': 1, 'tech_register_restrike:TS-003': 1, 'tech_register_vendor:TS-001': 1, 'tech_register_cells:TS-008': 1}.

| cat | FLOORS rows (=rounds) | verdict sequence | blocking terms across failing rounds | search ops (floors json) | cells selected | researched (Coverage) | synthesised (Provenance distinct) | declared absent (Provenance distinct) | final floors gate / blocking |
|---|---|---|---|---|---|---|---|---|---|
| P1C1 | 18 | `FFFFFPPFFFFFFFPFFP` | {'challenge_failed': 8, 'primary_unfired': 5, 'single_source_fact': 5, 'volleys_incomplete': 5, 'challenge_missing': 3, 'absence_undeclared_empty': 2, 'absence_unsearched': 2, 'claim_unsupported': 2} | 432 | 47 | 15 | 16 | 32 | PASS / [] |
| P1C2 | 15 | `FFFFFFPFFFFFFFP` | {'single_source_fact': 7, 'primary_unfired': 6, 'volleys_incomplete': 6, 'absence_undeclared_empty': 4, 'challenge_failed': 4, 'absence_unsearched': 3, 'challenge_missing': 3, 'synthesis_missing': 2, 'claim_unsupported': 1} | 526 | 58 | 8 | 8 | 50 | PASS / [] |
| P1C3 | 11 | `FFFFPPFFFFP` | {'primary_unfired': 4, 'challenge_failed': 3, 'absence_undeclared_empty': 2, 'absence_unsearched': 2, 'challenge_missing': 2, 'volleys_incomplete': 2, 'claim_unsupported': 1, 'single_source_fact': 1} | 324 | 38 | 4 | 4 | 34 | PASS / [] |
| P1C4 | 7 | `FPFFFPP` | {'challenge_failed': 3, 'absence_undeclared_empty': 1} | 354 | 42 | 3 | 6 | 39 | PASS / [] |
| P2C1 | 16 | `FFFFFFPFFPPFFFFP` | {'single_source_fact': 7, 'primary_unfired': 5, 'volleys_incomplete': 5, 'challenge_failed': 5, 'absence_undeclared_empty': 4, 'absence_unsearched': 2, 'claim_unsupported': 2, 'challenge_missing': 1} | 528 | 59 | 27 | 27 | 32 | PASS / [] |
| P2C2 | 12 | `FFFFFFPFFPFP` | {'absence_undeclared_empty': 6, 'primary_unfired': 6, 'single_source_fact': 6, 'volleys_incomplete': 6, 'absence_unsearched': 3, 'synthesis_missing': 3, 'challenge_failed': 3, 'challenge_missing': 2, 'claim_unsupported': 1} | 522 | 59 | 18 | 19 | 41 | PASS / [] |
| P2C3 | 11 | `FFFFFPFFFPP` | {'absence_undeclared_empty': 5, 'primary_unfired': 5, 'volleys_incomplete': 4, 'challenge_failed': 3, 'absence_unsearched': 2, 'challenge_missing': 1, 'claim_unsupported': 1, 'single_source_fact': 1} | 508 | 60 | 15 | 15 | 45 | PASS / [] |
| P2C4 | 15 | `FFFFFFPFFFFFFFP` | {'challenge_failed': 5, 'absence_undeclared_empty': 4, 'challenge_missing': 3, 'synthesis_missing': 3, 'single_source_fact': 3, 'boilerplate': 2, 'absence_unsearched': 1, 'primary_unfired': 1, 'volleys_incomplete': 1, 'claim_unsupported': 1} | 504 | 51 | 12 | 12 | 39 | PASS / [] |
| P3C1 | 19 | `FFFFFFPFFFFFFFFFFFP` | {'single_source_fact': 9, 'challenge_failed': 9, 'absence_undeclared_empty': 6, 'absence_unsearched': 4, 'challenge_missing': 4, 'volleys_incomplete': 4, 'primary_unfired': 2, 'claim_unsupported': 1} | 374 | 38 | 9 | 10 | 29 | PASS / [] |
| P3C2 | 20 | `FFFFFFFFFFFPPFFFFFFP` | {'primary_unfired': 11, 'single_source_fact': 11, 'absence_undeclared_empty': 9, 'volleys_incomplete': 8, 'challenge_failed': 6, 'absence_unsearched': 3, 'challenge_missing': 3, 'claim_unsupported': 1} | 184 | 26 | 8 | 9 | 18 | PASS / [] |
| P3C3 | 15 | `FFFFFPFFFPFPFFP` | {'absence_undeclared_empty': 5, 'challenge_failed': 4, 'claim_unsupported': 3, 'challenge_missing': 2, 'absence_unsearched': 1, 'synthesis_missing': 1, 'volleys_incomplete': 1, 'single_source_fact': 1} | 225 | 29 | 6 | 6 | 23 | PASS / [] |
| P3C4 | 4 | `PFFP` | {'challenge_failed': 1, 'claim_unsupported': 1, 'challenge_missing': 1, 'single_source_fact': 1} | 262 | 29 | 1 | 1 | 28 | PASS / [] |
| P4C1 | 13 | `FFFFFPPFFFFPP` | {'absence_undeclared_empty': 5, 'single_source_fact': 4, 'challenge_missing': 3, 'challenge_failed': 3, 'claim_unsupported': 1} | 383 | 40 | 4 | 5 | 36 | PASS / [] |
| P4C2 | 6 | `FFPFFP` | {'absence_undeclared_empty': 2, 'challenge_missing': 2, 'primary_unfired': 2, 'challenge_failed': 1, 'claim_unsupported': 1, 'single_source_fact': 1} | 437 | 55 | 2 | 2 | 53 | PASS / [] |
| P4C3 | 15 | `FFFPPPPFFFFFFFP` | {'challenge_failed': 5, 'absence_undeclared_empty': 3, 'challenge_missing': 3, 'absence_unsearched': 1, 'primary_unfired': 1, 'volleys_incomplete': 1, 'claim_unsupported': 1, 'single_source_fact': 1} | 432 | 47 | 3 | 3 | 44 | PASS / [] |
| P4C4 | 15 | `FFFFFFFPFFFFFFP` | {'primary_unfired': 7, 'challenge_failed': 5, 'absence_undeclared_empty': 4, 'absence_unsearched': 4, 'challenge_missing': 4, 'volleys_incomplete': 4, 'single_source_fact': 2} | 216 | 30 | 5 | 5 | 25 | PASS / [] |

Note: Coverage.Synthesised equals Selected in every category (the sheet counts rows written, not evidenced cells); Provenance 'synthesis' vs 'absence' distinct subcaps is the evidenced/absent split. floors_<cat>.json `blocking` is empty for every category at snapshot time (all closed PASS); the per-round blocking terms above come from the Gate_Log FLOORS Detail of each failing round (the json holds only final state).

**Search_Log**: **6332 rows**; per Tool {'web_fetch': 33, 'clay': 10, 'web_search': 2130, 'exa': 2005, 'tavily': 2148, 'vibe': 3, 'indeed': 2, 'explorium': 1}; PRELIM rows (SubCap_ID blank) **74**; facets {'null': 19, 'primary': 1170, 'works': 1536, 'fails': 843, 'contradicts': 833, 'corroborates': 1029, 'value': 847, 'focus_areas': 25, 'issues': 14, 'peer_deployments': 16}; rows per actor: not recorded (no Actor column). Duplicates (normalised query, lower/alnum): **805 duplicate groups, 5169 repeated rows** (81% of rows); of these 786 groups span ≥2 SubCap_IDs (5141 rows) and 19 repeat within one SubCap_ID (28 rows). Max rows per category: **['P2C1', 533]**; per category {'P1C1': 432, 'P1C2': 526, 'P1C3': 324, 'P1C4': 354, 'P2C1': 533, 'P2C2': 526, 'P2C3': 515, 'P2C4': 504, 'P3C1': 381, 'P3C2': 184, 'P3C3': 225, 'P3C4': 262, 'P4C1': 396, 'P4C2': 437, 'P4C3': 443, 'P4C4': 216}; most-searched subcaps [['P4C1.1.1', 21], ['P4C3.1.1', 19], ['P2C3.6.5', 17]]; rows with Hits=0: 65, Kept=0: 4928. Top repeated queries (query, rows, distinct subcaps): [['arbor bank omaha lead routing speed to lead crm marketing automation', 54, 9], ['arbor bank text messaging terms consent unsubscribe email marketing fair lending privacy c', 42, 7], ['arbor bank omaha digital account opening experience customer reviews app', 36, 12], ['arbor bank omaha welcome email new account abandoned application online account opening', 35, 7], ['arbor bank nebraska marketing compliance review fair lending tcpa email consent brand guid', 35, 7]]. **Fan-out vs re-run:** 4824 of the repeated rows share an identical query *and* timestamp (one search written once per facet and once per cell in the batch), only **345 are the same query issued again at a new timestamp** (581 same subcap+query re-runs); distinct (query, timestamp) pairs = **1508**, i.e. the row count overstates searches ~4.2×, and floors_<cat>.json `search_ops` equals the row count per category.

**Evidence_Detail**: **252 rows**; per Tier {'T1': 68, 'T2': 99, 'T3': 63, 'T4': 22}; per Origin {'public': 245, 'client': 1, 'connector': 6}; no URL **0**; attached to >1 subcap (SubCap_IDs list) **69**, unattached 41, attach-count distribution {'0': 41, '3': 8, '1': 142, '2': 48, '5': 5, '6': 3, '4': 5}; cited by ≥1 Subcap_Scoring row **211** of 252; recency {'CURRENT': 39, 'ARCHIVAL': 21, 'DATED': 5, 'STALE': 8, 'UNVERIFIED': 177, 'RECENT': 2}; claim type {'FACT': 160, 'INFERENCE': 92}; Access_Status≠OK 2.

## 4. SCORING

SCORING_OPENED: weight set CL_v1; research gates held; THIN: 140/708 subcaps carry bidirectional evidence and 211 rows over 708 subcaps — below the Golden 1 reference. Disclosed, not blocking: scores are capped by th.

| pillar | SCORING_CRITIC rows (critic rounds) | verdicts in order (F=FAIL, P=PASS) | score moves named in critic text (`x.x->y.y`) | first critic row | last critic row | Provenance `score` rows by producer |
|---|---|---|---|---|---|---|
| P1 | 11 | `FFFFFFFFPFP` | 23 | 2026-10-06T01:25:59Z | 2026-10-06T10:54:59Z | 231 |
| P2 | 13 | `FFFFFFFFFPFFP` | 35 | 2026-10-06T00:55:43Z | 2026-10-06T04:13:50Z | 285 |
| P3 | 11 | `FFFFFFPPPFP` | 24 | 2026-10-06T00:21:42Z | 2026-10-06T04:06:59Z | 155 |
| P4 | 11 | `FFFFPPPPFFP` | 6 | 2026-10-06T01:26:16Z | 2026-10-06T10:59:17Z | 189 |

Total critic rows 46; **--move rows: Gate_Log has no MOVE gate, scoring.json `critic_moves_pending`=0 and Run_Metadata `critic_moves`={}** — the only move record is the critic prose (88 `a->b` moves named). SCORING gate rows (pipeline gate, not STAGE): 23, verdicts {'FAIL': 21, 'PASS': 2}; blocker trajectory: critic_missing=4; dashboard_incomplete=13; no_differentiatio → critic_missing=4; dashboard_incomplete=13; rollup_missing=2; → critic_failed=2; critic_missing=2; dashboard_incomplete=13;  → critic_failed=2; critic_missing=2; dashboard_incomplete=13;  → critic_failed=3; dashboard_incomplete=13; rollup_missing=2 → critic_failed=3; dashboard_incomplete=13; rollup_missing=2 → critic_failed=1; dashboard_incomplete=13; rollup_missing=2 → all terms met; 705 scored, overall 1.08. STAGE_SCORING rows {'FAIL': 3, 'PASS': 1} with round sum 19; pipeline_state.SCORING rounds 6 / runs 4.

Provenance `score` rows **860** for 708 subcaps → 100 subcaps scored more than once (max [['P1C1.4.2', 5], ['P1C1.4.3', 5], ['P1C1.7.1', 5]]). Score rows per SCORING agent batch (batch start → rows written): 10-05T09:17→10, 10-05T09:23→8, 10-05T09:27→8, 10-05T23:37→198, 10-05T23:55→255, 10-06T00:22→187, 10-06T00:45→58, 10-06T01:10→21, 10-06T01:20→13, 10-06T01:27→10, 10-06T01:33→21, 10-06T03:34→10, 10-06T03:41→16, 10-06T03:48→7, 10-06T03:54→8, 10-06T04:01→13, 10-06T04:08→12 (855 of 860 fall inside a batch window). Wall clock first `score` row (2026-10-05T09:18Z) → STAGE_SCORING PASS (2026-10-06T04:14Z) = **18.94 h**; scoring.json: {'gate': 'PASS', 'subcaps': 708, 'scored': 708, 'overall': 1.08, 'blocking': 0, 'advisory': 1, 'unscored': 0, 'critic_missing': 0, 'critic_failed': 0, 'rollup_missing': 0, 'dashboard_incomplete': 0, 'no_differentiation': 0, 'critic_moves_pending': 0}.

## 5. REPORTS

Sources: `report_reviews.jsonl` present, 137 rows; Provenance `report_review:*` rows **137** (2026-10-06T08:41:23Z → 2026-10-06T12:31:04Z). 
- Reviews per report: {'client_research': 63, 'assessment': 74}; verdict distribution **{'REVISE': 94, 'FAIL': 5, 'PASS': 38}**; jsonl dimension FAIL/REVISE counts: {'evidence_support': 81, 'inference_honesty': 16, 'absence_rigour': 29, 'weighing_balance': 17, 'bias_disclosure': 4, 'tone': 5}; notes mentioning 'upstream' 46 (no `upstream` field; phrases: ['upstream for the conductor', 'upstream)', 'upstream for the conductor via engine', 'upstream only and unchanged since round 2']).
- Reviews per report:section (count / of which REVISE+FAIL): client_research:1 10/8, client_research:2 11/8, client_research:3 9/7, client_research:4 7/6, client_research:5 9/8, client_research:6 7/6, client_research:7 4/2, client_research:8 6/3, assessment:1 9/7, assessment:2 10/8, assessment:3 1/0, assessment:4 5/3, assessment:5 10/7, assessment:6 8/7, assessment:7 11/7, assessment:8 9/6, assessment:9 2/1, assessment:10 7/4, assessment:11 2/1
- Rounds until READY: briefs reports_r* = **19**; STAGE_REPORTS rows {'FAIL': 3, 'PASS': 1} (round sum 19); FAILs: reports not READY after 5 round(s): client_research, assessment; blocking: client_research: §1, §3, §4, §5, §6 not READY; assessment: §6 not READY — s | terminated by signal 15: the running batch was told to stop its lanes; resume with `engine.pipeline run` [elapsed 980.4s; rounds 3] | reports not READY after 10 round(s): assessment; blocking: assessment: §8 not READY [elapsed 6846.3s; rounds 10]
- Review dimensions marked REVISE/FAIL (parsed from every non-PASS Provenance review row, 99 rows): {'evidence_support': 81, 'absence_rigour': 29, 'weighing_balance': 17, 'inference_honesty': 16, 'tone': 5, 'bias_disclosure': 4}.
- Recurring REVISE/FAIL reasons (keyword classes over the free-text part of those 99 notes, dimensions dict removed; a note can hit several): **citation form / E-id cited wrongly** 57; **round fixes landed / unchanged since round** 52; **dates / currency / stale** 31; **peer set / benchmark basis** 29; **figure/count does not reconcile** 22; **CAGR / financial series** 20; **weighing balance / one-sided** 13; **tech register / Clay scan rows** 11; **template / word count / length** 11; **upstream (routed out of loop)** 5
- Report_Narrative: **31 sections, 33,508 words** ({'client_research': 13051, 'assessment': 20457}). Per section (report §: words | reviews in Provenance | REVISE/FAIL = rewrites):
  - client_research §PRELIM-FIN Financial profile and lines of business (section): 251 w | 0 reviews | 0 rewrites | written 2026-10-05T03:07
  - client_research §PRELIM-FIRM Institution profile (section): 135 w | 0 reviews | 0 rewrites | written 2026-10-05T03:13
  - client_research §PRELIM-LEAD Leadership and digital ownership (section): 184 w | 0 reviews | 0 rewrites | written 2026-10-05T03:13
  - client_research §PRELIM-THOUGHT Thought leadership and stated direction (section): 260 w | 0 reviews | 0 rewrites | written 2026-10-05T03:14
  - client_research §PRELIM-ISSUES Open matters (section): 316 w | 0 reviews | 0 rewrites | written 2026-10-06T08:11
  - client_research §1 Firmographics (section): 1019 w | 10 reviews | 8 rewrites | written 2026-10-06T10:54
  - assessment §1 Executive Summary (section): 1507 w | 9 reviews | 7 rewrites | written 2026-10-06T11:49
  - client_research §2 Executive Summary (section): 1599 w | 11 reviews | 8 rewrites | written 2026-10-06T12:07
  - client_research §3 Entity Profile (section): 1382 w | 9 reviews | 7 rewrites | written 2026-10-06T10:32
  - assessment §3 Issue Impact and Cap Analysis (section): 639 w | 1 reviews | 0 rewrites | written 2026-10-06T08:19
  - assessment §4 Assessment Results (section): 748 w | 5 reviews | 3 rewrites | written 2026-10-06T11:38
  - client_research §4 Market Position and Trends (section): 1815 w | 7 reviews | 6 rewrites | written 2026-10-06T10:32
  - assessment §2 Assessment Methodology (section): 1032 w | 10 reviews | 8 rewrites | written 2026-10-06T11:48
  - assessment §5 Pillar Deep Dives (pillar): 1149 w | 10 reviews | 7 rewrites | written 2026-10-06T11:49
  - client_research §5 Strategic Intelligence (section): 3193 w | 9 reviews | 8 rewrites | written 2026-10-06T10:33
  - assessment §5 Pillar Deep Dives (pillar): 1327 w | 10 reviews | 7 rewrites | written 2026-10-06T11:49
  - client_research §6 Client Priorities (section): 1513 w | 7 reviews | 6 rewrites | written 2026-10-06T10:22
  - client_research §7 Risk and Issues (section): 1127 w | 4 reviews | 2 rewrites | written 2026-10-06T10:33
  - client_research §8 Workbook References (section): 257 w | 6 reviews | 3 rewrites | written 2026-10-06T11:08
  - assessment §5 Pillar Deep Dives (pillar): 1146 w | 10 reviews | 7 rewrites | written 2026-10-06T11:50
  - assessment §5 Pillar Deep Dives (pillar): 1252 w | 10 reviews | 7 rewrites | written 2026-10-06T11:50
  - assessment §6 Benchmark and Technology Estate (section): 2291 w | 8 reviews | 7 rewrites | written 2026-10-06T11:38
  - assessment §7 Gap Prioritisation (section): 1693 w | 11 reviews | 7 rewrites | written 2026-10-06T12:01
  - assessment §8 Recommendations (recommendation): 1258 w | 9 reviews | 6 rewrites | written 2026-10-06T08:49
  - assessment §8 Recommendations (recommendation): 1157 w | 9 reviews | 6 rewrites | written 2026-10-06T12:07
  - assessment §8 Recommendations (recommendation): 1132 w | 9 reviews | 6 rewrites | written 2026-10-06T10:32
  - assessment §8 Recommendations (recommendation): 1204 w | 9 reviews | 6 rewrites | written 2026-10-06T12:28
  - assessment §8 Recommendations (recommendation): 1084 w | 9 reviews | 6 rewrites | written 2026-10-06T12:28
  - assessment §9 Transformation Roadmap (section): 855 w | 2 reviews | 1 rewrites | written 2026-10-06T08:48
  - assessment §10 Data Gaps and Confidence (section): 795 w | 7 reviews | 4 rewrites | written 2026-10-06T11:09
  - assessment §11 Workbook Traceability (section): 188 w | 2 reviews | 1 rewrites | written 2026-10-06T08:49
- Other report-stage gates: TECH_REGISTER_RECONCILE ['PASS', 'PASS', 'PASS', 'PASS']; GS/TEMPLATE {'GS': {'FAIL': 9, 'PASS': 19}, 'TEMPLATE': {'PASS': 20}}; PRELIM_AMEND none.

## 6. PAGES / PROMOTE

pages_workflow.json: not recorded. pipeline_state.pages:

| page | final version/status | attempts (pipeline_state) | sg_v4_fails (final) | versions | STAGE_PAGES gate ids named for this page |
|---|---|---|---|---|---|
| techstack | B/pass | 8 | 0 | {'A': 'pass', 'B': 'pass'} | {'CG-15': 1, 'CG-14': 1, 'SG-V4': 1, 'ET-07': 1} |
| heatmap | B/pass | 15 | 0 | {'A': 'pass', 'B': 'pass'} | {'AG-01': 3} |
| overview | B/pass | 9 | 173 | {'B': 'pass'} | {'CG-18': 1, 'CG-12': 1, 'AG-01': 1, 'SG-V4': 3, 'ET-07': 1, 'CG-31': 1} |
| insights | B/pass | 8 | 112 | {'B': 'pass'} | {} |
| platform | B/pass | 8 | 204 | {'B': 'pass'} | {} |
| context | B/pass | 7 | 39 | {'B': 'pass'} | {'ET-07': 2, 'AG-03': 2, 'CG-46': 1} |

Total page attempts (pipeline_state) **55**; STAGE_PAGES_A rows {'FAIL': 5, 'PASS': 1} (attempt sum 13), STAGE_PAGES_B rows {'FAIL': 7, 'PASS': 2} (attempt sum 11); STAGE_PROMOTE rows {'FAIL': 2, 'PASS': 1}. Gate ids across all STAGE_PAGES FAIL rows: {'CG-15': 1, 'CG-14': 1, 'SG-V4': 4, 'ET-07': 4, 'AG-01': 4, 'CG-18': 1, 'CG-12': 1, 'CG-31': 1, 'AG-03': 2, 'CG-46': 1}. Special rows: {'PAGE_PREFLIGHT': 0, 'CONNECTOR_DRIFT': 0, 'SG_V4_BUDGET_RAISED': 8, 'SG_V4_BUDGET_OVERRIDE': 0, 'ENRICHMENT': 0, 'PRELIM_AMEND': 0, 'INGEST_A_REPOINT': 0, 'OWNER_DECISION': 1, 'REPORT_PROBES': 0, 'FLOORS_WAIVER': 4} (PAGE_PREFLIGHT and CONNECTOR_DRIFT: none recorded in any run; CG-*/ET-*/SG-* never appear as their own Gate_Log rows — only inside STAGE_PAGES detail and verdict files).
- SG-V4 budget rows (SG_V4_BUDGET_RAISED) ×8: insights: 112 prose fails; platform: 204 prose fails; overview: 168 prose fails; context: 39 prose fails; overview: 173 prose fails; insights: 112 prose fails; platform: 204 prose fails; context: 39 prose fails; pipeline_state.waivers: 8.
- Verdict files (07_qa/verdict*.json): `verdict_context_B.json` → context: pass reasons=0 gate_ids={} sg_v4=49; `verdict_heatmap_A.json` → heatmap: pass reasons=0 gate_ids={} sg_v4=638; `verdict_heatmap_B.json` → heatmap: pass reasons=0 gate_ids={} sg_v4=997; `verdict_insights_B.json` → insights: pass reasons=0 gate_ids={} sg_v4=119; `verdict_overview_B.json` → overview: pass reasons=0 gate_ids={} sg_v4=188; `verdict_platform_B.json` → platform: pass reasons=0 gate_ids={} sg_v4=208; `verdict_techstack_A.json` → techstack: pass reasons=0 gate_ids={} sg_v4=4; `verdict_techstack_B.json` → techstack: pass reasons=0 gate_ids={} sg_v4=0; `verdicts_A.json` → techstack:  reasons=7 gate_ids={} sg_v4=7, heatmap:  reasons=12 gate_ids={'AG-01': 12} sg_v4=0; `verdicts_B.json` → overview:  reasons=2 gate_ids={'CG-31': 2} sg_v4=0, insights:  reasons=7 gate_ids={} sg_v4=7, platform:  reasons=7 gate_ids={} sg_v4=7, context:  reasons=2 gate_ids={'ET-07': 1, 'AG-03': 1} sg_v4=0
- PAGES lanes: A 24 lanes / $12.92, B 31 lanes / $22.1; 0 lane failures in either.
- PAGES_A FAIL rows:
  - page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-14', 'section': 'techstack', 'path': 'techstack.items[5].linked_subcap_ids[1]', 'mes; heatmap: {'gate_id': 'CG-15', 'section': 'cell_evidence', 'path'
  - page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x38 over budget 8 — find grounding or drop the claim, techstack.items[0].detection_basis (sim 0.45 < 0.55); heatmap: {'gate_id': 'ET-07', 'sectio
  - page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort
  - page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort
  - page(s) not passing on version A after 1 attempt(s): heatmap: {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort_patterns.insufficient_cohorts[0]., {'gate_id': 'AG-01', 'section': 'cohort_patterns', 'path': 'cohort
- PAGES_B FAIL rows:
  - page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-18', 'section': 'firmographics', 'path': 'firmographics.fields', 'message': "must-pr, {'gate_id': 'CG-18', 'section': 'firmographics', 'path': 'firmogr
  - page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-005 reso, {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_sum
  - page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'CG-31', 'section': 'opportunity', 'path': 'overview.opportunity.tiles[1].composite', 'm; insights: SG-V4 grounding FAIL x112 over budget 8 — find groundin
  - page(s) not passing on version B after 1 attempt(s): overview: SG-V4 grounding FAIL x167 over budget 8 — find grounding or drop the claim, ceilings.narrative_thread (sim 0.397 < 0.5); insights: SG-V4 grounding FAIL x112 over budge
  - page(s) not passing on version B after 3 attempt(s): context: {'gate_id': 'ET-07', 'section': 'issue_register', 'path': 'issue_register.e_ids', 'message': "E-006 , {'gate_id': 'ET-07', 'section': 'timeline', 'path': 'timeline.e_id
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-46', 'section': 'issue_register', 'path': 'context.issue_register.empty_state', 'mes, {'gate_id': 'AG-03', 'section': 'context_sentiment', 'path': 'cont
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'ET-07', 'section': 'issue_register', 'path': 'issue_register.e_ids', 'message': "E-006 , {'gate_id': 'AG-03', 'section': 'context_sentiment', 'path': 'cont
- PROMOTE FAIL rows:
  - promote_run refused: {"promoted": false, "error": "retained_pages_fail_current_gates", "pages": ["overview", "platform"], "reasons": {"overview": [{"gate_id": "CG-PAR", "section": "sentiment", "path": "overview.sentiment.gap_analy
  - promote_run refused: {"promoted": false, "error": "retained_pages_fail_current_gates", "pages": ["overview", "platform"], "reasons": {"overview": [{"gate_id": "CG-PAR", "section": "sentiment", "path": "overview.sentiment.gap_analy

## 7. ENRICHMENT / PRELIM

- Gate_Log ENRICHMENT rows: **none** (gates present: ['STAGE_PRELIM']); STAGE_PRELIM: {'n': 2, 'verdicts': {'PASS': 2}, 'final': 'PASS', 'fail_details': []}. PRELIM ledger: [('2026-10-05T03:07Z', 5.66, 4, 11.6)].
- search_relay.jsonl: **94 rows**; events {'open': 47, 'empty': 43, 'served': 4} (no `status` field — OPEN/SERVED/EMPTY/BLOCKED live in `event`); lanes {'report-probes': 47, 'null': 47}; categories {'P4C1': 13, 'P2C1': 5, 'P4C3': 11, 'P2C2': 4, 'P3C1': 7, 'P2C3': 7, 'null': 47}; tools {'exa': 47, 'null': 47}.
- Run_Metadata enrichment facets: only ['prelim_status', 'prelim_completed_at', 'connector_run_id', 'connector_run_id_prev', 'connector_ingest_after_seq'] — no enrichment facet counts recorded. Enrichment_Needed sheet rows: 5; Firmographics rows 10 states {'STATED': 10}.
- PRELIM rows in Search_Log (blank SubCap_ID): **74**; tools {'web_fetch': 33, 'clay': 10, 'web_search': 20, 'vibe': 3, 'indeed': 2, 'explorium': 1, 'exa': 5}.
- PRELIM evidence (E-ids with Retrieved_At before the first category search at 2026-10-05T03:20Z): **26** (E-001…E-026); cited by Subcap_Scoring rows **2**; carrying SubCap_IDs 2; **orphaned (neither) 24**.
- Dispatch files: ['enrichment-connector-specialist.json', 'enrichment-web-specialist.json', 'research-challenger.json', 'scoring-critic.json', 'scoring-p1-producer.json', 'scoring-p4-producer.json']; handbacks: {'research-challenger': 115}.

## 8. Lock contention signals

- Gate_Log OWNER_DECISION @ 2026-10-06T09:59:36Z: Owner (dma@zennify.com, 2026-10-06) cut the named peer set from 6 to 5 to meet the report template limit (>5 fails client_research s4 / assessment s6): RVR Bank removed (site refused automated reads; 
- pipeline_state.json matches: none; driver/pipeline logs scanned 28 files, hits none; agent_logs present: False (excluded from snapshots — nothing to read).

---

# Susser Bank (2026-10-05→06) — `susser-bank-2026-10-05`

Sub-vertical **CL**, evidence mode PUBLIC, **708 subcaps** selected of 851; overall 1.17; promoted at **2026-10-06T06:22:42.537299+00:00**. Ledger span 2026-10-05T03:17Z → 2026-10-06T06:22Z = **27.1 h wall clock**; Run_Metadata.cost_summary: {'stages': 12, 'total_elapsed_s': 72757.4, 'total_usd': 450.0197, 'turns': 11539}; pipeline_state spent/budget: 450.0197/500.0; pipeline invocations recorded: 46.

## 1. Stage table (cost_ledger.jsonl + Gate_Log STAGE_* rows)

| stage | started | ended | wall min | agent elapsed min | pipeline rounds (sum of 'after N round/attempt') | batches / lanes / attempts | USD | tokens (cache_read / cache_write / uncached / output) | STAGE_* verdicts → final |
|---|---|---|---|---|---|---|---|---|---|
| PRELIM | 2026-10-05T03:10Z | 2026-10-05T03:17Z | 7.1 | 7.1 | 1 | 1 / 2 / 2 | $3.24 | cr 5,778,595 / cw 168,312 / unc 120 / out 34,430 | {'PASS': 1} → PASS |
| KG | 2026-10-05T03:17Z | 2026-10-05T03:17Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| RESEARCH | 2026-10-05T03:17Z | 2026-10-05T12:55Z | 577.1 | 0.0 | 0 | 0 / 0 / 0; 353 workflow agents charged | $249.41 | cr 563,810,864 / cw 53,679,247 / unc 14,458 / out 242,504 | {'PENDING_ORCHESTRATOR': 8} → PENDING_ORCHESTRATOR |
| HANDOFF | 2026-10-05T08:51Z | 2026-10-05T09:07Z | 16.4 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'FAIL': 1, 'PASS': 1} → PASS |
| SCORING | 2026-10-05T09:08Z | 2026-10-05T19:11Z | 603.2 | 214.0 | 29 | 49 / 81 / 91 | $49.03 | cr 53,480,471 / cw 4,394,272 / unc 2,164 / out 732,301 | {'FAIL': 9, 'PASS': 1} → PASS |
| INGEST_A | 2026-10-05T19:44Z | 2026-10-05T19:44Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| REPORTS | 2026-10-05T19:44Z | 2026-10-06T01:26Z | 342.2 | 278.9 | 26 | 57 / 104 / 105 | $109.85 | cr 167,175,578 / cw 8,380,637 / unc 3,878 / out 1,552,370 | {'FAIL': 9, 'PASS': 1} → PASS |
| PAGES_A | 2026-10-06T01:27Z | 2026-10-06T03:52Z | 145.3 | 25.1 | 18 | 17 / 34 / 34 | $14.53 | cr 18,584,036 / cw 1,796,940 / unc 674 / out 251,694 | {'FAIL': 6, 'PASS': 1} → PASS |
| PACKAGE | 2026-10-06T03:53Z | 2026-10-06T03:53Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| INGEST_B | 2026-10-06T04:15Z | 2026-10-06T04:15Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| PAGES_B | 2026-10-06T04:15Z | 2026-10-06T06:22Z | 126.7 | 32.5 | 15 | 11 / 30 / 35 | $23.96 | cr 38,005,913 / cw 2,542,932 / unc 930 / out 429,900 | {'FAIL': 11, 'PASS': 2} → PASS |
| PROMOTE | 2026-10-06T06:15Z | 2026-10-06T06:22Z | 7.8 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'FAIL': 1, 'PASS': 1} → PASS |

**Total:** wall clock 27.1 h (first→last ledger row); **USD 450.02** (ledger) vs Run_Metadata.cost_summary.total_usd 450.0197; tokens cr 846,835,457 / cw 70,962,340 / unc 22,224 / out 3,243,199; turns 11539.

STAGE_* FAIL rows (37):
  - HANDOFF: REFUSED: 3 tab(s) are empty with no reason recorded. A workbook that validates and carries nothing is the Golden 1 shape: shape-correct, content-empty.
  - Tech_Peer_Deployments: empty, and no reason 
  - SCORING: terminated by signal 15: the running batch was told to stop its lanes; resume with `engine.pipeline run` [elapsed 1923.5s; rounds 8]
  - SCORING: SCORING gate FAIL after 4 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 3 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 3 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - REPORTS: reports not READY after 7 round(s): client_research, assessment; blocking: client_research: §2, §5, §6 not READY; assessment: §5, §6, §7, §8, §10 not READY — stopped at round 7: the last 2 round(s) ad
  - REPORTS: reports not READY after 4 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §6, §8, §9 not READY — stopped at round 4: the last 2 round(s) advanced nothing th
  - REPORTS: Tech_Register contradicts the run's own evidence: TS-002 MuleSoft Anypoint Platform CLAIMED, named by E-411. Re-strike each row from the cited excerpts before any section is written: `python3 -m engin
  - REPORTS: reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §1, §6, §7, §8 not READY — stopped at round 2: the last 2 round(s) advanced nothin
  - REPORTS: reports not READY after 3 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §6, §7, §8 not READY — stopped at round 3: the last 2 round(s) advanced nothing th
  - REPORTS: reports not READY after 3 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §8 not READY — stopped at round 3: the last 2 round(s) advanced nothing the stage 
  - REPORTS: reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §8 not READY — stopped at round 2: the last 2 round(s) advanced nothing the stage 
  - REPORTS: reports not READY after 3 round(s): assessment; blocking: assessment: §8 not READY — stopped at round 3: the last 2 round(s) advanced nothing the stage measures, so more rounds would not have helped [
  - REPORTS: reports not READY after 2 round(s): assessment; blocking: assessment: §1, §3, §4, §5, §6, §7, §8, §9, §10, §11 not READY — stopped at round 2: the last 2 round(s) advanced nothing the stage measures, 
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: no section files for techstack in /home/user/dma-runs/susser-bank/08_sections: the page lane produce; heatmap: no section files for heat
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-20', 'section': 'techstack', 'path': 'techstack.items[3].product', 'message': "produ, {'gate_id': 'CG-20', 'section': 't
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-50', 'section': 'techstack', 'path': 'techstack.techstack.items[4]', 'message': "'Q2, {'gate_id': 'ET-12', 'section': 't
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x48 over budget 8 — find grounding or drop the claim, techstack.items[0].peer_deployments[1].basis (sim 0.41 < 0.5)
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'CG-10', 'section': 'evidence_age', 'path': 'evidence_age.rows[100].published_or_asof', , {'gate_id': 'CG-10', 'section': 'evi
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): heatmap: SG-V4 grounding FAIL x867 over budget 8 — find grounding or drop the claim, alerts.narrative_thread (sim 0.459 < 0.5) [elapsed 327.7s; rou
  - PAGES_B: page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportunity.tiles[0].addressable_cells[0].fe, {'gate_id': 'CG-12', 'section': 'op
  - PAGES_B: page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportunity.tiles[0].addressable_cells[1].fe, {'gate_id': 'CG-12', 'section': 'op
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-006 reso, {'gate_id': 'ET-07', 'section': 'ex
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: SG-V4 grounding FAIL x138 over budget 8 — find grounding or drop the claim, ceilings.rows[0].rationale (sim 0.354 < 0.58); insights: SG-V
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-23', 'section': 'acquisitions', 'path': 'acquisitions.narrative_thread', 'message': [elapsed 263.0s; rounds 0]
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'ET-07', 'section': 'acquisitions', 'path': 'acquisitions.e_ids', 'message': "E-012 reso, {'gate_id': 'ET-07', 'section': 'tim
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-03b', 'section': 'context_sentiment', 'path': 'context_sentiment.context_tiles', 'me [elapsed 1.0s; rounds 0]
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-46', 'section': 'issue_register', 'path': 'context.issue_register.empty_state', 'mes, {'gate_id': 'AG-03', 'section': 'con
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): techstack: {'gate_id': 'ET-07', 'section': 'techstack', 'path': 'techstack.e_ids', 'message': "E-SUSSERBA-004 r, {'gate_id': 'ET-07', 'section': 't
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-SUSSERBA, {'gate_id': 'ET-07', 'section': 'ex
  - PAGES_B: page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'ceilings', 'path': 'ceilings.e_ids', 'message': "E-SUSSERBA-144 res [elapsed 39.3s; rounds 0]
  - PROMOTE: promote_run refused: {"_error": "tmap_evidence_age\" violates foreign key constraint \"heatmap_evidence_age_e_id_fkey\"', 'D': 'Key (e_id)=(E-025) is not present in table \"evidence_index\".', 's': 'p

## 2. Workflow estimates

- **Research** (STAGE_RESEARCH PENDING_ORCHESTRATOR rows = handoffs to the conducting session): **8 handoffs**. First: 16 categories × 81 batches for 708 open cells, est **$141.56** (basis `pilot $0.19/cell + $0.44/category challenge, calibrated by this run's last round ($3.73 measured: x1.0, floor $0.746/category)`). Sum of all handoff estimates $276.09; sum of open cells re-handed 834 (+241 repair cells). Actual research charge (ledger) **$249.41** over 353 workflow agents; workflow_costs_recorded.json: {'agents': 353, 'usd': 249.41, 'turns': 7286}.
  - Handoff sequence (at | cats | batches | open+repair cells | est $): 10-05T03:17 | 16 | 81 | 708+0 | 141.56; 10-05T04:42 | 15 | 9 | 63+0 | 18.57; 10-05T05:12 | 15 | 9 | 63+0 | 18.57; 10-05T05:30 | 14 | 0 | 0+0 | 6.16; 10-05T08:19 | 14 | 19 | 0+131 | 31.05; 10-05T09:59 | 15 | 16 | 0+104 | 47.64; 10-05T10:53 | 5 | 5 | 0+5 | 11.79; 10-05T12:55 | 1 | 1 | 0+1 | 0.75
  - Last research_workflow.json: estimate {'open_cells': 0, 'repair_cells': 1, 'batches': 1, 'categories': 1, 'usd': 0.75, 'basis': "pilot $0.19/cell + $0.44/category challenge, calibrated by this run's last round ($3.73 measured: x1.0, floor $0.746/category)", 'spent_at_handoff': 264.48, 'research_at_handoff': 249.41, 'spent_usd': 264.48, 'budget_usd': 450.0, 'fits_budget': True}; invocations: P3 cats=['P3C1'] batches={'P3C1': 0} batch_cells={'P3C1': 0} repair_cells={'P3C1': 1} rounds=2
- **Scoring**: scoring_workflow.json not recorded. Observed: 47 lane batches, 79 lanes dispatched (1 failed), agents {'scoring-p1-producer': 11, 'scoring-p2-producer': 10, 'scoring-p3-producer': 10, 'scoring-p4-producer': 10, 'technographic-scanner': 10, 'scoring-critic': 28}; briefs dirs scoring_r*/scoring_critic_r*: 58; Subcap_Scoring rows per pillar: not in workflow file — see §4 Provenance counts.
- **Reports**: reports_workflow.json not recorded. Observed: 54 lane batches, 88 lanes, agents {'report-assessment-producer': 26, 'report-research-producer': 22, 'report-validator': 26, 'enrichment-web-specialist': 14}; briefs reports_r* dirs = **26 rounds**; Report_Narrative sections = 31.
- **Pages**: pages_workflow.json not recorded. Observed: briefs dirs ['pages_A_0', 'pages_A_0_assemble', 'pages_A_0_challenge', 'pages_A_0_consolidate', 'pages_A_0_fragments', 'pages_A_1', 'pages_A_1_assemble', 'pages_A_2', 'pages_A_2_assemble', 'pages_B_0_assemble', 'pages_B_0_challenge', 'pages_B_0_consolidate', 'pages_B_0_fragments', 'pages_B_1_assemble', 'pages_B_2_assemble'] (files per dir: {'pages_A_0': 5, 'pages_A_0_assemble': 5, 'pages_A_0_challenge': 3, 'pages_A_0_consolidate': 3, 'pages_A_0_fragments': 17, 'pages_A_1': 5, 'pages_A_1_assemble': 5, 'pages_A_2': 5, 'pages_A_2_assemble': 5, 'pages_B_0_assemble': 9, 'pages_B_0_challenge': 3, 'pages_B_0_consolidate': 3, 'pages_B_0_fragments': 33, 'pages_B_1_assemble': 7, 'pages_B_2_assemble': 7}); PAGES_A lanes 34 ({'heatmap-surface-producer': 14, 'techstack-surface-producer': 10, 'heatmap-evidence-producer': 1, 'heatmap-focus-producer': 1, 'heatmap-freshness-producer': 1, 'heatmap-grid-producer': 1, 'heatmap-signals-producer': 1, 'heatmap-valuechain-producer': 1, 'techstack-layers-producer': 1, 'techstack-register-producer': 1, 'finding-challenger': 1, 'page-consolidator': 1}); PAGES_B lanes 34 ({'insights-cards-producer': 1, 'insights-landscape-producer': 1, 'overview-findings-producer': 1, 'overview-governance-producer': 1, 'overview-hero-producer': 1, 'overview-market-producer': 1, 'overview-narrative-producer': 1, 'overview-opportunity-producer': 1, 'overview-people-producer': 1, 'overview-whynow-producer': 1, 'platform-conversation-producer': 1, 'platform-fit-producer': 1, 'platform-roadmap-producer': 1, 'finding-challenger': 1, 'page-consolidator': 1, 'insights-surface-producer': 5, 'overview-surface-producer': 5, 'platform-surface-producer': 5, 'context-risk-producer': 1, 'context-sentiment-producer': 1, 'context-timeline-producer': 1, 'context-surface-producer': 1}); 08_sections files 34, backup dirs none.
- **PRELIM**: lanes {'files': 1, 'dispatched': 2, 'ok': 2, 'failed': 0, 'usd': 3.24, 'agents': {'research-conductor': 1, 'technographic-scanner': 1}, 'retries': 0, 'lane_attempts_gt1': 0}.

## 3. RESEARCH

FLOORS gate rows total **141** (108 FAIL, 33 PASS) over 16 categories; blocking-term frequency across failing rounds: {'volleys_incomplete': 73, 'primary_unfired': 57, 'absence_undeclared_empty': 52, 'single_source_fact': 50, 'challenge_failed': 30, 'absence_unsearched': 16, 'challenge_missing': 16, 'boilerplate': 13, 'synthesis_missing': 8, 'evidence_smear': 6}. FLOORS_WAIVER rows: 0. Challenge_Log: {'FAIL': 135, 'PASS': 228}. Provenance steps: {'absence': 600, 'synthesis': 561, 'attach': 137, 'challenge': 362, 'score': 972, 'tech_register_correction:TS-018': 1, 'tech_register_correction:TS-019': 1, 'tech_register_correction:TS-020': 1, 'tech_register_correction:TS-016': 1, 'tech_register_correction:TS-007': 1, 'focus_area_locator:FA-01': 1, 'focus_area_locator:FA-02': 1, 'focus_area_locator:FA-03': 1, 'report_citation_form:assessment': 1, 'tech_register_product:TS-005': 1, 'tech_register_product:TS-010': 1, 'tech_register_product:TS-012': 1, 'tech_register_product:TS-013': 1, 'tech_register_product:TS-015': 1, 'tech_register_product:TS-008': 1}.

| cat | FLOORS rows (=rounds) | verdict sequence | blocking terms across failing rounds | search ops (floors json) | cells selected | researched (Coverage) | synthesised (Provenance distinct) | declared absent (Provenance distinct) | final floors gate / blocking |
|---|---|---|---|---|---|---|---|---|---|
| P1C1 | 10 | `FFFFFPFFFP` | {'boilerplate': 5, 'evidence_smear': 5, 'single_source_fact': 5, 'volleys_incomplete': 5, 'absence_undeclared_empty': 3, 'absence_unsearched': 3, 'challenge_failed': 3, 'challenge_missing': 2} | 350 | 47 | 22 | 22 | 28 | PASS / [] |
| P1C2 | 11 | `FFFFFFFFPFP` | {'absence_undeclared_empty': 8, 'boilerplate': 8, 'primary_unfired': 8, 'single_source_fact': 8, 'volleys_incomplete': 8, 'absence_unsearched': 3, 'challenge_missing': 3, 'challenge_failed': 1} | 568 | 58 | 12 | 14 | 46 | PASS / [] |
| P1C3 | 8 | `FFFFFPFP` | {'primary_unfired': 5, 'volleys_incomplete': 5, 'absence_undeclared_empty': 4, 'challenge_missing': 1, 'challenge_failed': 1} | 328 | 38 | 15 | 17 | 24 | PASS / [] |
| P1C4 | 7 | `FFFFPFP` | {'primary_unfired': 4, 'volleys_incomplete': 4, 'single_source_fact': 3, 'synthesis_missing': 2, 'absence_undeclared_empty': 1, 'challenge_failed': 1} | 320 | 42 | 21 | 21 | 21 | PASS / [] |
| P2C1 | 10 | `FFFFFFFPFP` | {'primary_unfired': 7, 'volleys_incomplete': 7, 'single_source_fact': 6, 'absence_undeclared_empty': 5, 'challenge_missing': 2, 'absence_unsearched': 1, 'challenge_failed': 1} | 462 | 59 | 25 | 25 | 34 | PASS / [] |
| P2C2 | 11 | `FFFFFFPFFFP` | {'absence_undeclared_empty': 6, 'primary_unfired': 6, 'single_source_fact': 6, 'volleys_incomplete': 6, 'absence_unsearched': 4, 'challenge_missing': 2, 'challenge_failed': 2, 'evidence_smear': 1} | 465 | 59 | 17 | 18 | 42 | PASS / [] |
| P2C3 | 10 | `FFFFFFPFFP` | {'single_source_fact': 6, 'volleys_incomplete': 6, 'primary_unfired': 5, 'absence_undeclared_empty': 3, 'challenge_failed': 2} | 728 | 60 | 31 | 31 | 33 | PASS / [] |
| P2C4 | 8 | `FFFFPFFP` | {'single_source_fact': 3, 'challenge_failed': 2, 'absence_undeclared_empty': 1, 'absence_unsearched': 1, 'primary_unfired': 1, 'synthesis_missing': 1, 'volleys_incomplete': 1} | 514 | 51 | 6 | 6 | 45 | PASS / [] |
| P3C1 | 10 | `FFFFPFFFFP` | {'absence_undeclared_empty': 4, 'primary_unfired': 4, 'single_source_fact': 4, 'volleys_incomplete': 4, 'challenge_failed': 4, 'challenge_missing': 1} | 274 | 38 | 12 | 12 | 26 | PASS / [] |
| P3C2 | 8 | `FFFFFPFP` | {'primary_unfired': 5, 'volleys_incomplete': 5, 'absence_undeclared_empty': 2, 'challenge_failed': 1} | 207 | 26 | 14 | 14 | 12 | PASS / [] |
| P3C3 | 9 | `FFFFFPFFP` | {'single_source_fact': 5, 'volleys_incomplete': 5, 'absence_undeclared_empty': 2, 'challenge_failed': 2, 'challenge_missing': 1} | 226 | 29 | 14 | 14 | 15 | PASS / [] |
| P3C4 | 3 | `FPP` | {'absence_undeclared_empty': 1} | 208 | 29 | 1 | 0 | 29 | PASS / [] |
| P4C1 | 9 | `FFFFPFFFP` | {'absence_undeclared_empty': 4, 'primary_unfired': 4, 'volleys_incomplete': 4, 'challenge_failed': 3, 'challenge_missing': 1} | 367 | 40 | 11 | 13 | 30 | PASS / [] |
| P4C2 | 8 | `FFFFPFPP` | {'primary_unfired': 4, 'volleys_incomplete': 4, 'absence_undeclared_empty': 2, 'synthesis_missing': 2, 'challenge_failed': 1} | 567 | 55 | 6 | 6 | 49 | PASS / [] |
| P4C3 | 8 | `FFFFPFFP` | {'primary_unfired': 4, 'single_source_fact': 4, 'volleys_incomplete': 4, 'absence_undeclared_empty': 3, 'synthesis_missing': 3, 'challenge_failed': 2, 'absence_unsearched': 1, 'challenge_missing': 1} | 389 | 47 | 14 | 15 | 33 | PASS / [] |
| P4C4 | 11 | `FFFFFPFFFFP` | {'volleys_incomplete': 5, 'challenge_failed': 4, 'absence_undeclared_empty': 3, 'absence_unsearched': 3, 'challenge_missing': 2} | 224 | 30 | 3 | 3 | 27 | PASS / [] |

Note: Coverage.Synthesised equals Selected in every category (the sheet counts rows written, not evidenced cells); Provenance 'synthesis' vs 'absence' distinct subcaps is the evidenced/absent split. floors_<cat>.json `blocking` is empty for every category at snapshot time (all closed PASS); the per-round blocking terms above come from the Gate_Log FLOORS Detail of each failing round (the json holds only final state).

**Search_Log**: **6319 rows**; per Tool {'web_fetch': 4, 'web_search': 1969, 'tavily': 2391, 'exa': 1955}; PRELIM rows (SubCap_ID blank) **27**; facets {'null': 10, 'primary': 1335, 'works': 1446, 'corroborates': 984, 'contradicts': 866, 'fails': 828, 'value': 831, 'ai_deployment': 2, 'issues': 17}; rows per actor: not recorded (no Actor column). Duplicates (normalised query, lower/alnum): **893 duplicate groups, 5008 repeated rows** (79% of rows); of these 858 groups span ≥2 SubCap_IDs (4954 rows) and 35 repeat within one SubCap_ID (54 rows). Max rows per category: **['P2C3', 758]**; per category {'P1C1': 354, 'P1C2': 568, 'P1C3': 328, 'P1C4': 320, 'P2C1': 463, 'P2C2': 478, 'P2C3': 758, 'P2C4': 514, 'P3C1': 287, 'P3C2': 207, 'P3C3': 226, 'P3C4': 213, 'P4C1': 379, 'P4C2': 567, 'P4C3': 405, 'P4C4': 225}; most-searched subcaps [['P2C3.1.1', 27], ['P2C3.5.2', 26], ['P2C3.5.3', 26]]; rows with Hits=0: 57, Kept=0: 4870. Top repeated queries (query, rows, distinct subcaps): [['susser bank dispute error resolution customer service sla complaints', 54, 9], ['susser bank customer service technology case management proactive service recovery', 54, 9], ['susser bank loan servicing collections annual review commercial loan officer workflow', 54, 9], ['susser bank salesforce zoom contact center jack henry xperience job posting case managemen', 36, 9], ['susser bank collections specialist or loan servicing or loan administration job posting', 36, 9]]. **Fan-out vs re-run:** 4833 of the repeated rows share an identical query *and* timestamp (one search written once per facet and once per cell in the batch), only **175 are the same query issued again at a new timestamp** (364 same subcap+query re-runs); distinct (query, timestamp) pairs = **1486**, i.e. the row count overstates searches ~4.3×, and floors_<cat>.json `search_ops` equals the row count per category.

**Evidence_Detail**: **428 rows**; per Tier {'T1': 123, 'T2': 98, 'T3': 161, 'T4': 46}; per Origin {'public': 407, 'web': 2, 'connector': 19}; no URL **5**; attached to >1 subcap (SubCap_IDs list) **83**, unattached 43, attach-count distribution {'0': 43, '3': 14, '4': 9, '1': 302, '2': 54, '6': 4, '5': 2}; cited by ≥1 Subcap_Scoring row **385** of 428; recency {'CURRENT': 71, 'ARCHIVAL': 15, 'STALE': 8, 'DATED': 17, 'RECENT': 21, 'UNVERIFIED': 296}; claim type {'FACT': 194, 'INFERENCE': 234}; Access_Status≠OK 18.

## 4. SCORING

SCORING_OPENED: weight set CL_v1; research gates held; THIN: 222/708 subcaps carry bidirectional evidence and 359 rows over 708 subcaps — below the Golden 1 reference. Disclosed, not blocking: scores are capped by th.

| pillar | SCORING_CRITIC rows (critic rounds) | verdicts in order (F=FAIL, P=PASS) | score moves named in critic text (`x.x->y.y`) | first critic row | last critic row | Provenance `score` rows by producer |
|---|---|---|---|---|---|---|
| P1 | 19 | `PFFFFFFFPPFFFFFPPFP` | 28 | 2026-10-05T14:42:04Z | 2026-10-05T19:10:50Z | 244 |
| P2 | 21 | `FFFFFFFFFFFFFFFFFPPPP` | 40 | 2026-10-05T14:28:44Z | 2026-10-05T19:11:03Z | 399 |
| P3 | 19 | `FFFFFFFFFFPPFFFFFFP` | 25 | 2026-10-05T14:42:17Z | 2026-10-05T19:10:56Z | 154 |
| P4 | 17 | `PPPPPPPPFPPFFPPPP` | 14 | 2026-10-05T14:42:24Z | 2026-10-05T19:11:10Z | 175 |

Total critic rows 76; **--move rows: Gate_Log has no MOVE gate, scoring.json `critic_moves_pending`=not recorded and Run_Metadata `critic_moves`=None** — the only move record is the critic prose (107 `a->b` moves named). SCORING gate rows (pipeline gate, not STAGE): 37, verdicts {'FAIL': 36, 'PASS': 1}; blocker trajectory: critic_missing=4; dashboard_incomplete=13; rollup_missing=2; → critic_missing=4; dashboard_incomplete=13; no_differentiatio → critic_failed=3; dashboard_incomplete=13; rollup_missing=2 → critic_failed=3; dashboard_incomplete=13; rollup_missing=2 → critic_failed=2; dashboard_incomplete=13; rollup_missing=2 → critic_failed=4; dashboard_incomplete=13; rollup_missing=2 → all terms met; 708 scored, overall 1.17. STAGE_SCORING rows {'FAIL': 9, 'PASS': 1} with round sum 29; pipeline_state.SCORING rounds 1 / runs 10.

Provenance `score` rows **972** for 708 subcaps → 165 subcaps scored more than once (max [['P2C2.4.9', 7], ['P2C3.2.3', 6], ['P2C3.3.2', 5]]). Score rows per SCORING agent batch (batch start → rows written): 10-05T09:08→11, 10-05T09:14→9, 10-05T09:18→8, 10-05T09:22→9, 10-05T09:26→7, 10-05T09:29→6, 10-05T09:33→7, 10-05T12:58→708, 10-05T14:22→14, 10-05T14:29→70, 10-05T15:01→11, 10-05T17:17→15, 10-05T17:28→2, 10-05T17:33→3, 10-05T17:44→5, 10-05T18:42→17, 10-05T19:02→4 (906 of 972 fall inside a batch window). Wall clock first `score` row (2026-10-05T09:09Z) → STAGE_SCORING PASS (2026-10-05T19:11Z) = **10.04 h**; scoring.json: {'gate': 'PASS', 'subcaps': 708, 'scored': 708, 'overall': 1.17, 'blocking': 0, 'advisory': 1, 'unscored': 0, 'critic_missing': 0, 'critic_failed': 0, 'rollup_missing': 0, 'dashboard_incomplete': 0, 'no_differentiation': 0}.

## 5. REPORTS

Sources: `report_reviews.jsonl` present, 28 rows; Provenance `report_review:*` rows **154** (2026-10-05T20:05:32Z → 2026-10-06T01:24:38Z). The jsonl is shorter than the Provenance trail, so counts below use Provenance; the jsonl dimension breakdown is given where it exists. 
- Reviews per report: {'client_research': 49, 'assessment': 105}; verdict distribution **{'REVISE': 113, 'FAIL': 5, 'PASS': 36}**; jsonl dimension FAIL/REVISE counts: {'evidence_support': 12, 'inference_honesty': 11, 'weighing_balance': 11, 'absence_rigour': 12, 'bias_disclosure': 10, 'tone': 10}; notes mentioning 'upstream' 3 (no `upstream` field; phrases: ['upstream: focus_areas fa-03 still unconfirmed', 'upstream: the focus_areas sheet still reads fa-03 unconfirmed and cu', 'upstream: focus_areas fa-03 still reads unconfirmed while both repor']).
- Reviews per report:section (count / of which REVISE+FAIL): client_research:1 3/2, client_research:2 9/8, client_research:3 4/3, client_research:4 5/4, client_research:5 10/9, client_research:6 13/12, client_research:7 3/2, client_research:8 2/1, assessment:1 11/7, assessment:2 2/1, assessment:3 4/2, assessment:4 4/2, assessment:5 12/10, assessment:6 19/17, assessment:7 12/8, assessment:8 25/22, assessment:9 6/3, assessment:10 7/4, assessment:11 3/1
- Rounds until READY: briefs reports_r* = **26**; STAGE_REPORTS rows {'FAIL': 9, 'PASS': 1} (round sum 26); FAILs: reports not READY after 7 round(s): client_research, assessment; blocking: client_research: §2, §5, §6 not READY; assessment: §5, §6, §7, §8, §10 not  | reports not READY after 4 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §6, §8, §9 not READY — stopped a | Tech_Register contradicts the run's own evidence: TS-002 MuleSoft Anypoint Platform CLAIMED, named by E-411. Re-strike each row from the cited excerpt | reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §1, §6, §7, §8 not READY — stopp | reports not READY after 3 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §6, §7, §8 not READY — stopped a | reports not READY after 3 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §8 not READY — stopped at round  | reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §6 not READY; assessment: §8 not READY — stopped at round  | reports not READY after 3 round(s): assessment; blocking: assessment: §8 not READY — stopped at round 3: the last 2 round(s) advanced nothing the stag | reports not READY after 2 round(s): assessment; blocking: assessment: §1, §3, §4, §5, §6, §7, §8, §9, §10, §11 not READY — stopped at round 2: the las
- Review dimensions marked REVISE/FAIL (parsed from every non-PASS Provenance review row, 118 rows): {'evidence_support': 106, 'inference_honesty': 52, 'absence_rigour': 44, 'weighing_balance': 27, 'tone': 18, 'bias_disclosure': 16}.
- Recurring REVISE/FAIL reasons (keyword classes over the free-text part of those 118 notes, dimensions dict removed; a note can hit several): **citation form / E-id cited wrongly** 75; **figure/count does not reconcile** 53; **dates / currency / stale** 37; **tech register / Clay scan rows** 29; **round fixes landed / unchanged since round** 24; **CAGR / financial series** 20; **peer set / benchmark basis** 20; **template / word count / length** 12; **inference presented as fact** 10; **weighing balance / one-sided** 10
- Report_Narrative: **31 sections, 37,317 words** ({'client_research': 13429, 'assessment': 23888}). Per section (report §: words | reviews in Provenance | REVISE/FAIL = rewrites):
  - client_research §PRELIM-FIN Financial profile and lines of business (section): 311 w | 0 reviews | 0 rewrites | written 2026-10-05T03:10
  - client_research §PRELIM-FIRM Institution profile (section): 424 w | 0 reviews | 0 rewrites | written 2026-10-05T03:50
  - client_research §PRELIM-LEAD Leadership and digital ownership (section): 554 w | 0 reviews | 0 rewrites | written 2026-10-05T03:43
  - client_research §PRELIM-THOUGHT Thought leadership and stated direction (section): 284 w | 0 reviews | 0 rewrites | written 2026-10-05T03:15
  - client_research §1 Firmographics (section): 854 w | 3 reviews | 2 rewrites | written 2026-10-05T20:30
  - client_research §2 Executive Summary (section): 1846 w | 9 reviews | 8 rewrites | written 2026-10-05T21:45
  - client_research §3 Entity Profile (section): 1148 w | 4 reviews | 3 rewrites | written 2026-10-05T20:42
  - assessment §5 Pillar Deep Dives (pillar): 1588 w | 12 reviews | 10 rewrites | written 2026-10-05T22:11
  - client_research §4 Market Position and Trends (section): 1374 w | 5 reviews | 4 rewrites | written 2026-10-05T20:58
  - assessment §5 Pillar Deep Dives (pillar): 1561 w | 12 reviews | 10 rewrites | written 2026-10-05T22:10
  - assessment §5 Pillar Deep Dives (pillar): 1439 w | 12 reviews | 10 rewrites | written 2026-10-05T22:10
  - assessment §5 Pillar Deep Dives (pillar): 1647 w | 12 reviews | 10 rewrites | written 2026-10-05T22:10
  - client_research §5 Strategic Intelligence (section): 3816 w | 10 reviews | 9 rewrites | written 2026-10-05T21:46
  - assessment §1 Executive Summary (section): 1388 w | 11 reviews | 7 rewrites | written 2026-10-05T23:43
  - client_research §6 Client Priorities (section): 986 w | 13 reviews | 12 rewrites | written 2026-10-06T00:56
  - assessment §2 Assessment Methodology (section): 583 w | 2 reviews | 1 rewrites | written 2026-10-05T20:12
  - client_research §7 Risk and Issues (section): 1319 w | 3 reviews | 2 rewrites | written 2026-10-05T20:33
  - assessment §3 Issue Impact and Cap Analysis (section): 1126 w | 4 reviews | 2 rewrites | written 2026-10-05T20:12
  - client_research §8 Workbook References (section): 513 w | 2 reviews | 1 rewrites | written 2026-10-05T20:12
  - assessment §4 Assessment Results (section): 854 w | 4 reviews | 2 rewrites | written 2026-10-05T20:13
  - assessment §6 Benchmark and Technology Estate (section): 3655 w | 19 reviews | 17 rewrites | written 2026-10-06T00:13
  - assessment §7 Gap Prioritisation (section): 1834 w | 12 reviews | 8 rewrites | written 2026-10-06T00:13
  - assessment §8 Recommendations (recommendation): 1029 w | 25 reviews | 22 rewrites | written 2026-10-06T00:48
  - assessment §8 Recommendations (recommendation): 1050 w | 25 reviews | 22 rewrites | written 2026-10-06T00:48
  - assessment §8 Recommendations (recommendation): 1039 w | 25 reviews | 22 rewrites | written 2026-10-06T00:48
  - assessment §8 Recommendations (recommendation): 1072 w | 25 reviews | 22 rewrites | written 2026-10-06T00:48
  - assessment §8 Recommendations (recommendation): 1100 w | 25 reviews | 22 rewrites | written 2026-10-06T00:49
  - assessment §9 Transformation Roadmap (section): 792 w | 6 reviews | 3 rewrites | written 2026-10-05T23:26
  - assessment §10 Data Gaps and Confidence (section): 874 w | 7 reviews | 4 rewrites | written 2026-10-05T21:48
  - assessment §11 Workbook Traceability (section): 118 w | 3 reviews | 1 rewrites | written 2026-10-05T19:57
  - assessment §8 Recommendations (recommendation): 1139 w | 25 reviews | 22 rewrites | written 2026-10-06T01:12
- Other report-stage gates: TECH_REGISTER_RECONCILE ['FAIL', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS', 'PASS']; GS/TEMPLATE {'GS': {'PASS': 22}, 'TEMPLATE': {'PASS': 8}}; PRELIM_AMEND none.

## 6. PAGES / PROMOTE

pages_workflow.json: not recorded. pipeline_state.pages:

| page | final version/status | attempts (pipeline_state) | sg_v4_fails (final) | versions | STAGE_PAGES gate ids named for this page |
|---|---|---|---|---|---|
| techstack | B/pass | 16 | 56 | {'A': 'pass', 'B': 'pass'} | {'CG-20': 1, 'CG-27': 1, 'CG-50': 1, 'CG-11': 1, 'CG-04': 1, 'ET-12': 1, 'SG-V4': 1, 'CG-15': 1, 'ET-07': 1} |
| heatmap | B/pass | 21 | 1517 | {'A': 'pass', 'B': 'pass'} | {'CG-10': 1, 'SG-V4': 1} |
| overview | B/pass | 12 | 213 | {'B': 'pass'} | {'ET-07': 5, 'CG-12': 2, 'CG-04': 1, 'SG-V4': 1} |
| insights | B/pass | 10 | 98 | {'B': 'pass'} | {} |
| platform | B/pass | 11 | 289 | {'B': 'pass'} | {} |
| context | B/pass | 6 | 76 | {'B': 'pass'} | {'CG-23': 1, 'ET-07': 1, 'CG-03b': 1, 'AG-03': 1, 'CG-46': 1} |

Total page attempts (pipeline_state) **76**; STAGE_PAGES_A rows {'FAIL': 6, 'PASS': 1} (attempt sum 18), STAGE_PAGES_B rows {'FAIL': 11, 'PASS': 2} (attempt sum 15); STAGE_PROMOTE rows {'FAIL': 1, 'PASS': 1}. Gate ids across all STAGE_PAGES FAIL rows: {'CG-20': 1, 'CG-27': 1, 'CG-50': 1, 'CG-11': 1, 'CG-04': 2, 'ET-12': 1, 'SG-V4': 3, 'CG-15': 1, 'CG-10': 1, 'ET-07': 7, 'CG-12': 2, 'CG-23': 1, 'CG-03b': 1, 'AG-03': 1, 'CG-46': 1}. Special rows: {'PAGE_PREFLIGHT': 0, 'CONNECTOR_DRIFT': 0, 'SG_V4_BUDGET_RAISED': 0, 'SG_V4_BUDGET_OVERRIDE': 8, 'ENRICHMENT': 0, 'PRELIM_AMEND': 0, 'INGEST_A_REPOINT': 0, 'OWNER_DECISION': 0, 'REPORT_PROBES': 1, 'FLOORS_WAIVER': 0} (PAGE_PREFLIGHT and CONNECTOR_DRIFT: none recorded in any run; CG-*/ET-*/SG-* never appear as their own Gate_Log rows — only inside STAGE_PAGES detail and verdict files).
- SG-V4 budget rows (SG_V4_BUDGET_OVERRIDE) ×8: overview: 138 prose fails; insights: 66 prose fails; platform: 193 prose fails; context: 29 prose fails; insights: 66 prose fails; platform: 193 prose fails; overview: 138 prose fails; context: 29 prose fails; pipeline_state.waivers: none.
- Verdict files (07_qa/verdict*.json): `verdict_context_B.json` → context: pass reasons=0 gate_ids={} sg_v4=76; `verdict_heatmap_A.json` → heatmap: pass reasons=0 gate_ids={} sg_v4=921; `verdict_heatmap_B.json` → heatmap: pass reasons=0 gate_ids={} sg_v4=1517; `verdict_insights_B.json` → insights: pass reasons=0 gate_ids={} sg_v4=98; `verdict_overview_B.json` → overview: pass reasons=0 gate_ids={} sg_v4=213; `verdict_platform.json` → _claim: claim_refused reasons=0 gate_ids={} sg_v4=0; `verdict_platform_B.json` → platform: pass reasons=0 gate_ids={} sg_v4=289; `verdict_techstack_A.json` → techstack: pass reasons=0 gate_ids={} sg_v4=48; `verdict_techstack_B.json` → techstack: pass reasons=0 gate_ids={} sg_v4=56; `verdicts_A.json` → techstack:  reasons=7 gate_ids={} sg_v4=7, heatmap:  reasons=7 gate_ids={} sg_v4=7; `verdicts_B.json` → overview:  reasons=1 gate_ids={'ET-07': 1} sg_v4=0, insights:  reasons=7 gate_ids={} sg_v4=7, platform:  reasons=9 gate_ids={'ET-07': 9} sg_v4=0, context:  reasons=2 gate_ids={'CG-46': 1, 'AG-03': 1} sg_v4=0, techstack:  reasons=4 gate_ids={'ET-07': 4} sg_v4=0
- PAGES lanes: A 34 lanes / $14.53, B 34 lanes / $23.96; 0 lane failures in either.
- PAGES_A FAIL rows:
  - page(s) not passing on version A after 3 attempt(s): techstack: no section files for techstack in /home/user/dma-runs/susser-bank/08_sections: the page lane produce; heatmap: no section files for heatmap in /home/user/dma-runs/sus
  - page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-20', 'section': 'techstack', 'path': 'techstack.items[3].product', 'message': "produ, {'gate_id': 'CG-20', 'section': 'techstack', 'path': 'techstack.
  - page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-50', 'section': 'techstack', 'path': 'techstack.techstack.items[4]', 'message': "'Q2, {'gate_id': 'ET-12', 'section': 'techstack', 'path': 'techstack.
  - page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x48 over budget 8 — find grounding or drop the claim, techstack.items[0].peer_deployments[1].basis (sim 0.41 < 0.5); heatmap: {'gate_id': 'CG-15'
  - page(s) not passing on version A after 3 attempt(s): heatmap: {'gate_id': 'CG-10', 'section': 'evidence_age', 'path': 'evidence_age.rows[100].published_or_asof', , {'gate_id': 'CG-10', 'section': 'evidence_age', 'path': 'evidence_
  - page(s) not passing on version A after 3 attempt(s): heatmap: SG-V4 grounding FAIL x867 over budget 8 — find grounding or drop the claim, alerts.narrative_thread (sim 0.459 < 0.5) [elapsed 327.7s; rounds 0]
- PAGES_B FAIL rows:
  - page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportunity.tiles[0].addressable_cells[0].fe, {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportuni
  - page(s) not passing on version B after 3 attempt(s): overview: {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportunity.tiles[0].addressable_cells[1].fe, {'gate_id': 'CG-12', 'section': 'opportunity', 'path': 'opportuni
  - page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-006 reso, {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_sum
  - page(s) not passing on version B after 1 attempt(s): overview: SG-V4 grounding FAIL x138 over budget 8 — find grounding or drop the claim, ceilings.rows[0].rationale (sim 0.354 < 0.58); insights: SG-V4 grounding FAIL x66 over budg
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-23', 'section': 'acquisitions', 'path': 'acquisitions.narrative_thread', 'message': [elapsed 263.0s; rounds 0]
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'ET-07', 'section': 'acquisitions', 'path': 'acquisitions.e_ids', 'message': "E-012 reso, {'gate_id': 'ET-07', 'section': 'timeline', 'path': 'timeline.e_id
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-03b', 'section': 'context_sentiment', 'path': 'context_sentiment.context_tiles', 'me [elapsed 1.0s; rounds 0]
  - page(s) not passing on version B after 1 attempt(s): context: {'gate_id': 'CG-46', 'section': 'issue_register', 'path': 'context.issue_register.empty_state', 'mes, {'gate_id': 'AG-03', 'section': 'context_sentiment', 'path': 'cont
  - page(s) not passing on version B after 1 attempt(s): techstack: {'gate_id': 'ET-07', 'section': 'techstack', 'path': 'techstack.e_ids', 'message': "E-SUSSERBA-004 r, {'gate_id': 'ET-07', 'section': 'techstack', 'path': 'techstack.
  - page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_summary.e_ids', 'message': "E-SUSSERBA, {'gate_id': 'ET-07', 'section': 'exec_summary', 'path': 'exec_sum
  - page(s) not passing on version B after 1 attempt(s): overview: {'gate_id': 'ET-07', 'section': 'ceilings', 'path': 'ceilings.e_ids', 'message': "E-SUSSERBA-144 res [elapsed 39.3s; rounds 0]
- PROMOTE FAIL rows:
  - promote_run refused: {"_error": "tmap_evidence_age\" violates foreign key constraint \"heatmap_evidence_age_e_id_fkey\"', 'D': 'Key (e_id)=(E-025) is not present in table \"evidence_index\".', 's': 'public', 't': 'heatmap_evidence

## 7. ENRICHMENT / PRELIM

- Gate_Log ENRICHMENT rows: **none** (gates present: ['STAGE_PRELIM']); STAGE_PRELIM: {'n': 1, 'verdicts': {'PASS': 1}, 'final': 'PASS', 'fail_details': []}. PRELIM ledger: [('2026-10-05T03:10Z', 3.24, 2, 7.1)].
- search_relay.jsonl: **240 rows**; events {'open': 92, 'blocked': 27, 'empty': 71, 'reopen': 27, 'served': 23} (no `status` field — OPEN/SERVED/EMPTY/BLOCKED live in `event`); lanes {'report-probes': 92, 'null': 148}; categories {'P3C1': 13, 'P2C3': 29, 'P2C2': 12, 'P4C3': 16, 'P4C1': 12, 'P4C4': 1, 'P3C4': 5, 'P1C1': 4, 'null': 148}; tools {'exa': 92, 'null': 148}.
- Run_Metadata enrichment facets: only ['prelim_status', 'prelim_completed_at', 'connector_run_id', 'connector_run_id_prev', 'connector_ingest_after_seq'] — no enrichment facet counts recorded. Enrichment_Needed sheet rows: 9; Firmographics rows 10 states {'STATED': 10}.
- PRELIM rows in Search_Log (blank SubCap_ID): **27**; tools {'web_fetch': 3, 'web_search': 8, 'exa': 9, 'tavily': 7}.
- PRELIM evidence (E-ids with Retrieved_At before the first category search at 2026-10-05T03:20Z): **26** (E-001…E-026); cited by Subcap_Scoring rows **1**; carrying SubCap_IDs 1; **orphaned (neither) 25**.
- Dispatch files: none; handbacks: none.

## 8. Lock contention signals

- Gate_Log / cost_ledger: no 'lock', 'waited', 'timed out', 'lease' or 'deadlock' text (matches excluding Handoff_Lock/locked_peer_set).
- pipeline_state.json matches: none; driver/pipeline logs scanned 47 files, hits none; agent_logs present: False (excluded from snapshots — nothing to read).

---

# Cross Insurance Agency (2026-10-01) — `cross-insurance-agency-20261001`

**Cross caveats:** the ledger holds no `workflow agents … charged` rows, so the research stage's USD is **not recorded** and the run total below excludes it; Search_Log shows 4,994 of 4,999 category rows on `web_search` with Provenance absence rows marked `REDUCED RIGOUR — this run's connector baseline is short of exa, tavily`; there is no STAGE_PROMOTE row and `promoted_at` is None (pipeline_state.last_outcome FAILED; final stage row is PAGES_B PASS at 20:44Z), so this run was shipped to version B but not promoted in the snapshot.

Sub-vertical **IB**, evidence mode PUBLIC, **694 subcaps** selected of 851; overall 1.01; promoted at **not recorded (pipeline_state.PAGES_B PASS; no STAGE_PROMOTE row)**. Ledger span 2026-10-01T11:43Z → 2026-10-01T20:44Z = **9.0 h wall clock**; Run_Metadata.cost_summary: {'stages': 11, 'total_elapsed_s': 30701.5, 'total_usd': 82.7062, 'turns': 1782}; pipeline_state spent/budget: 81.396/150.0; pipeline invocations recorded: 14.

## 1. Stage table (cost_ledger.jsonl + Gate_Log STAGE_* rows)

| stage | started | ended | wall min | agent elapsed min | pipeline rounds (sum of 'after N round/attempt') | batches / lanes / attempts | USD | tokens (cache_read / cache_write / uncached / output) | STAGE_* verdicts → final |
|---|---|---|---|---|---|---|---|---|---|
| PRELIM | 2026-10-01T11:35Z | 2026-10-01T11:43Z | 7.5 | 7.5 | 1 | 1 / 2 / 2 | $4.30 | cr 7,545,586 / cw 242,009 / unc 132 / out 37,454 | {'PASS': 1} → PASS |
| KG | 2026-10-01T11:43Z | 2026-10-01T11:43Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| RESEARCH | 2026-10-01T11:43Z | 2026-10-01T12:47Z | 63.4 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PENDING_ORCHESTRATOR': 2} → PENDING_ORCHESTRATOR |
| HANDOFF | 2026-10-01T14:07Z | 2026-10-01T14:13Z | 5.9 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'FAIL': 1, 'PASS': 1} → PASS |
| SCORING | 2026-10-01T14:14Z | 2026-10-01T17:23Z | 189.2 | 138.6 | 21 | 47 / 110 / 110 | $41.77 | cr 34,592,727 / cw 5,524,413 / unc 2,010 / out 482,661 | {'FAIL': 4, 'PASS': 1} → PASS |
| INGEST_A | 2026-10-01T17:23Z | 2026-10-01T17:23Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| REPORTS | 2026-10-01T17:23Z | 2026-10-01T19:26Z | 122.5 | 78.5 | 6 | 12 / 18 / 18 | $32.23 | cr 49,269,682 / cw 2,533,270 / unc 1,088 / out 494,734 | {'FAIL': 2, 'PASS': 1} → PASS |
| PAGES_A | 2026-10-01T19:26Z | 2026-10-01T20:13Z | 47.4 | 5.6 | 6 | 9 / 12 / 12 | $3.36 | cr 2,311,337 / cw 624,706 / unc 126 / out 36,725 | {'FAIL': 4, 'PASS': 1} → PASS |
| PACKAGE | 2026-10-01T20:14Z | 2026-10-01T20:14Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| INGEST_B | 2026-10-01T20:43Z | 2026-10-01T20:43Z | 0.0 | 0.0 | 0 | 0 / 0 / 0 | not recorded | not recorded | {'PASS': 1} → PASS |
| PAGES_B | 2026-10-01T20:43Z | 2026-10-01T20:44Z | 1.0 | 0.7 | 0 | 2 / 4 / 4 | $1.05 | cr 119,492 / cw 240,272 / unc 20 / out 5,137 | {'PASS': 1} → PASS |

**Total:** wall clock 9.0 h (first→last ledger row); **USD 82.71** (ledger) vs Run_Metadata.cost_summary.total_usd 82.7062; tokens cr 93,838,824 / cw 9,164,670 / unc 3,376 / out 1,056,711; turns 1782.

STAGE_* FAIL rows (11):
  - HANDOFF: REFUSED: 4 tab(s) are empty with no reason recorded. A workbook that validates and carries nothing is the Golden 1 shape: shape-correct, content-empty.
  - Tech_Peer_Deployments: empty, and no reason 
  - SCORING: SCORING gate FAIL after 10 round(s): critic_failed, dashboard_incomplete, no_differentiation, rollup_missing, unscored; the rollup has no headline — the scoring-critic lane records it (`engine.assessm
  - SCORING: SCORING gate FAIL after 5 round(s): critic_failed, dashboard_incomplete, no_differentiation, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup 
  - SCORING: SCORING gate FAIL after 3 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - SCORING: SCORING gate FAIL after 2 round(s): critic_failed, dashboard_incomplete, rollup_missing; the rollup has no headline — the scoring-critic lane records it (`engine.assessment rollup --headline '<one ins
  - REPORTS: reports not READY after 4 round(s): client_research, assessment; blocking: client_research: §1, §2, §3, §4, §5 not READY; assessment: §1, §5, §6, §8, §10 not READY — stopped at round 4: the last 2 rou
  - REPORTS: reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §5, §8 not READY; assessment: §5, §7, §8, §9 not READY — stopped at round 2: the last 2 round(s) advanced no
  - PAGES_A: claim on d5aed033-718d-4923-901f-2f761c489e0b refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 77.8s; rounds 0]
  - PAGES_A: claim on a1550631-23a2-426f-9172-b2631605b308 refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 46.1s; rounds 0]
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-23', 'section': 'techstack', 'path': 'techstack.narrative_thread', 'message': "this , {'gate_id': 'CG-27', 'section': 't
  - PAGES_A: page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x60 over budget 8 — find grounding or drop the claim, techstack.narrative_thread (sim 0.438 < 0.5) [elapsed 172.3s;

## 2. Workflow estimates

- **Research** (STAGE_RESEARCH PENDING_ORCHESTRATOR rows = handoffs to the conducting session): **2 handoffs**. First: 16 categories × 79 batches for 694 open cells, est **$138.9** (basis `measured pilot: $0.19/cell + $0.44/category challenge`). Sum of all handoff estimates $277.80; sum of open cells re-handed 1388 (+0 repair cells). Actual research charge (ledger) **$0.00** over 0 workflow agents; workflow_costs_recorded.json absent.
  - Handoff sequence (at | cats | batches | open+repair cells | est $): 10-01T11:43 | 16 | 79 | 694+0 | 138.9; 10-01T12:47 | 16 | 79 | 694+0 | 138.9
  - Last research_workflow.json: estimate {'open_cells': 694, 'batches': 79, 'usd': 138.9, 'basis': 'measured pilot: $0.19/cell + $0.44/category challenge', 'spent_usd': 4.3, 'budget_usd': 150.0, 'fits_budget': True}; invocations: P1 cats=['P1C1'] batches={'P1C1': 6} batch_cells={'P1C1': 8} repair_cells={} rounds=2; P1 cats=['P1C2'] batches={'P1C2': 6} batch_cells={'P1C2': 9} repair_cells={} rounds=2; P1 cats=['P1C3'] batches={'P1C3': 4} batch_cells={'P1C3': 9} repair_cells={} rounds=2; P1 cats=['P1C4'] batches={'P1C4': 5} batch_cells={'P1C4': 10} repair_cells={} rounds=2; P2 cats=['P2C1'] batches={'P2C1': 8} batch_cells={'P2C1': 8} repair_cells={} rounds=2; P2 cats=['P2C2'] batches={'P2C2': 7} batch_cells={'P2C2': 9} repair_cells={} rounds=2; P2 cats=['P2C3'] batches={'P2C3': 7} batch_cells={'P2C3': 9} repair_cells={} rounds=2; P2 cats=['P2C4'] batches={'P2C4': 6} batch_cells={'P2C4': 8} repair_cells={} rounds=2; P3 cats=['P3C1'] batches={'P3C1': 3} batch_cells={'P3C1': 8} repair_cells={} rounds=2; P3 cats=['P3C2'] batches={'P3C2': 3} batch_cells={'P3C2': 8} repair_cells={} rounds=2; P3 cats=['P3C3'] batches={'P3C3': 3} batch_cells={'P3C3': 7} repair_cells={} rounds=2; P3 cats=['P3C4'] batches={'P3C4': 3} batch_cells={'P3C4': 8} repair_cells={} rounds=2; P4 cats=['P4C1'] batches={'P4C1': 4} batch_cells={'P4C1': 9} repair_cells={} rounds=2; P4 cats=['P4C2'] batches={'P4C2': 6} batch_cells={'P4C2': 8} repair_cells={} rounds=2; P4 cats=['P4C3'] batches={'P4C3': 5} batch_cells={'P4C3': 8} repair_cells={} rounds=2; P4 cats=['P4C4'] batches={'P4C4': 3} batch_cells={'P4C4': 8} repair_cells={} rounds=2
- **Scoring**: scoring_workflow.json not recorded. Observed: 47 lane batches, 110 lanes dispatched (0 failed), agents {'scoring-p1-producer': 21, 'scoring-p2-producer': 21, 'scoring-p3-producer': 21, 'scoring-p4-producer': 21, 'technographic-scanner': 5, 'scoring-critic': 21}; briefs dirs scoring_r*/scoring_critic_r*: 43; Subcap_Scoring rows per pillar: not in workflow file — see §4 Provenance counts.
- **Reports**: reports_workflow.json not recorded. Observed: 12 lane batches, 18 lanes, agents {'report-assessment-producer': 6, 'report-research-producer': 6, 'report-validator': 6}; briefs reports_r* dirs = **6 rounds**; Report_Narrative sections = 30.
- **Pages**: pages_workflow.json not recorded. Observed: briefs dirs ['pages_A_0', 'pages_A_1', 'pages_A_2', 'pages_B_0'] (files per dir: {'pages_A_0': 5, 'pages_A_1': 3, 'pages_A_2': 3, 'pages_B_0': 9}); PAGES_A lanes 12 ({'heatmap-surface-producer': 3, 'techstack-surface-producer': 9}); PAGES_B lanes 4 ({'insights-surface-producer': 1, 'overview-surface-producer': 1, 'platform-surface-producer': 1, 'context-surface-producer': 1}); 08_sections files 1, backup dirs none.
- **PRELIM**: lanes {'files': 1, 'dispatched': 2, 'ok': 2, 'failed': 0, 'usd': 4.3, 'agents': {'research-conductor': 1, 'technographic-scanner': 1}, 'retries': 0, 'lane_attempts_gt1': 0}.

## 3. RESEARCH

FLOORS gate rows total **75** (23 FAIL, 52 PASS) over 16 categories; blocking-term frequency across failing rounds: {'volleys_incomplete': 11, 'single_source_fact': 10, 'primary_unfired': 9, 'challenge_missing': 7, 'absence_undeclared_empty': 6, 'boilerplate': 5, 'absence_unsearched': 4}. FLOORS_WAIVER rows: 0. Challenge_Log: {'PASS': 41, 'FAIL': 26}. Provenance steps: {'absence': 822, 'synthesis': 79, 'attach': 18, 'challenge': 67, 'score': 744}.

| cat | FLOORS rows (=rounds) | verdict sequence | blocking terms across failing rounds | search ops (floors json) | cells selected | researched (Coverage) | synthesised (Provenance distinct) | declared absent (Provenance distinct) | final floors gate / blocking |
|---|---|---|---|---|---|---|---|---|---|
| P1C1 | 13 | `FFPPPPPPPPPPP` | {'absence_undeclared_empty': 2, 'absence_unsearched': 2, 'volleys_incomplete': 2} | 296 | 47 | 2 | 2 | 45 | PASS / [] |
| P1C2 | 9 | `FFFFFFPPP` | {'primary_unfired': 5, 'single_source_fact': 4, 'challenge_missing': 2, 'absence_undeclared_empty': 1, 'absence_unsearched': 1, 'volleys_incomplete': 1} | 434 | 57 | 6 | 6 | 51 | PASS / [] |
| P1C3 | 10 | `FPPPPPPPPP` | {'challenge_missing': 1} | 263 | 38 | 5 | 5 | 34 | PASS / [] |
| P1C4 | 7 | `FFFPPPP` | {'single_source_fact': 3} | 263 | 42 | 1 | 1 | 41 | PASS / [] |
| P2C1 | 9 | `FFFFFPPPP` | {'boilerplate': 5, 'volleys_incomplete': 5} | 385 | 57 | 3 | 3 | 54 | PASS / [] |
| P2C2 | 1 | `P` | — | 383 | 57 | 0 | 0 | 57 | PASS / [] |
| P2C3 | 10 | `FFFFFPPPPP` | {'primary_unfired': 4, 'absence_undeclared_empty': 3, 'challenge_missing': 3, 'single_source_fact': 3, 'volleys_incomplete': 3, 'absence_unsearched': 1} | 358 | 56 | 9 | 11 | 47 | PASS / [] |
| P2C4 | 1 | `P` | — | 366 | 51 | 2 | 2 | 49 | PASS / [] |
| P3C1 | 2 | `FP` | {'challenge_missing': 1} | 208 | 31 | 6 | 6 | 25 | PASS / [] |
| P3C2 | 1 | `P` | — | 187 | 28 | 0 | 0 | 28 | PASS / [] |
| P3C3 | 1 | `P` | — | 182 | 28 | 2 | 2 | 26 | PASS / [] |
| P3C4 | 1 | `P` | — | 301 | 29 | 0 | 0 | 29 | PASS / [] |
| P4C1 | 1 | `P` | — | 310 | 41 | 0 | 0 | 41 | PASS / [] |
| P4C2 | 5 | `PPPPP` | — | 473 | 54 | 1 | 1 | 53 | PASS / [] |
| P4C3 | 3 | `PPP` | — | 300 | 48 | 0 | 0 | 48 | PASS / [] |
| P4C4 | 1 | `P` | — | 274 | 30 | 1 | 1 | 29 | PASS / [] |

Note: Coverage.Synthesised equals Selected in every category (the sheet counts rows written, not evidenced cells); Provenance 'synthesis' vs 'absence' distinct subcaps is the evidenced/absent split. floors_<cat>.json `blocking` is empty for every category at snapshot time (all closed PASS); the per-round blocking terms above come from the Gate_Log FLOORS Detail of each failing round (the json holds only final state).

**Search_Log**: **4999 rows**; per Tool {'clay': 2, 'explorium': 2, 'indeed': 1, 'web_search': 4994}; PRELIM rows (SubCap_ID blank) **16**; facets {'null': 16, 'primary': 869, 'value': 762, 'contradicts': 783, 'corroborates': 779, 'works': 1045, 'fails': 745}; rows per actor: not recorded (no Actor column). Duplicates (normalised query, lower/alnum): **699 duplicate groups, 4126 repeated rows** (82% of rows); of these 656 groups span ≥2 SubCap_IDs (4078 rows) and 43 repeat within one SubCap_ID (48 rows). Max rows per category: **['P4C2', 473]**; per category {'P1C1': 296, 'P1C2': 434, 'P1C3': 263, 'P1C4': 263, 'P2C1': 385, 'P2C2': 383, 'P2C3': 358, 'P2C4': 366, 'P3C1': 208, 'P3C2': 187, 'P3C3': 182, 'P3C4': 301, 'P4C1': 310, 'P4C2': 473, 'P4C3': 300, 'P4C4': 274}; most-searched subcaps [['P4C2.1.2', 15], ['P4C2.1.1', 14], ['P3C4.4.1', 13]]; rows with Hits=0: 1, Kept=0: 4838. Top repeated queries (query, rows, distinct subcaps): [['cross insurance agency operational resilience business continuity disaster recovery', 24, 12], ['cross insurance agency risk management enterprise risk coo information security officer hi', 24, 12], ['cross insurance agency applied epic outage or downtime or business impact analysis or tabl', 24, 12], ['cross insurance agency proactive client outreach renewal review digital personalized', 24, 12], ['cross insurance agency retention churn analytics customer data platform applied epic autom', 24, 12]]. **Fan-out vs re-run:** 3683 of the repeated rows share an identical query *and* timestamp (one search written once per facet and once per cell in the batch), only **443 are the same query issued again at a new timestamp** (273 same subcap+query re-runs); distinct (query, timestamp) pairs = **1316**, i.e. the row count overstates searches ~3.8×, and floors_<cat>.json `search_ops` equals the row count per category.

**Evidence_Detail**: **70 rows**; per Tier {'T3': 47, 'T2': 16, 'T1': 5, 'T4': 2}; per Origin {'clay': 5, 'business directory match 2026-10-01': 1, 'public': 58, 'vendor_case_study': 4, 'trade_association_listing': 2}; no URL **1**; attached to >1 subcap (SubCap_IDs list) **14**, unattached 31, attach-count distribution {'0': 31, '1': 25, '2': 11, '3': 3}; cited by ≥1 Subcap_Scoring row **39** of 70; recency {'CURRENT': 5, 'ARCHIVAL': 20, 'UNVERIFIED': 31, 'RECENT': 7, 'DATED': 2, 'STALE': 5}; claim type {'INFERENCE': 51, 'FACT': 19}; Access_Status≠OK 5.

## 4. SCORING

SCORING_OPENED: weight set IB_v1; research gates held; THIN: 38/694 subcaps carry bidirectional evidence and 69 rows over 694 subcaps — below the Golden 1 reference. Disclosed, not blocking: scores are capped by the .

| pillar | SCORING_CRITIC rows (critic rounds) | verdicts in order (F=FAIL, P=PASS) | score moves named in critic text (`x.x->y.y`) | first critic row | last critic row | Provenance `score` rows by producer |
|---|---|---|---|---|---|---|
| P1 | 14 | `FFFFFFFFPPPFFP` | 10 | 2026-10-01T14:52:13Z | 2026-10-01T17:22:23Z | 204 |
| P2 | 13 | `FFFFFFFFFFFPP` | 16 | 2026-10-01T14:52:18Z | 2026-10-01T17:11:34Z | 231 |
| P3 | 21 | `FFFFFFFFFFFFFFFPPPPPP` | 22 | 2026-10-01T14:41:14Z | 2026-10-01T17:22:29Z | 130 |
| P4 | 13 | `FFFFFFFFPPPPP` | 8 | 2026-10-01T14:52:22Z | 2026-10-01T17:11:46Z | 179 |

Total critic rows 61; **--move rows: Gate_Log has no MOVE gate, scoring.json `critic_moves_pending`=not recorded and Run_Metadata `critic_moves`=None** — the only move record is the critic prose (56 `a->b` moves named). SCORING gate rows (pipeline gate, not STAGE): 30, verdicts {'FAIL': 29, 'PASS': 1}; blocker trajectory: critic_failed=1; critic_missing=3; dashboard_incomplete=13;  → critic_failed=4; dashboard_incomplete=13; no_differentiation → critic_failed=4; dashboard_incomplete=13; no_differentiation → critic_failed=4; dashboard_incomplete=13; no_differentiation → critic_failed=4; dashboard_incomplete=13; no_differentiation → critic_failed=1; dashboard_incomplete=13; rollup_missing=2. STAGE_SCORING rows {'FAIL': 4, 'PASS': 1} with round sum 21; pipeline_state.SCORING rounds 1 / runs 5.

Provenance `score` rows **744** for 694 subcaps → 40 subcaps scored more than once (max [['P3C1.4.2', 3], ['P3C1.4.3', 3], ['P3C1.1.4', 3]]). Score rows per SCORING agent batch (batch start → rows written): 10-01T14:14→125, 10-01T14:42→9, 10-01T14:45→9, 10-01T14:49→9, 10-01T14:53→9, 10-01T14:57→9, 10-01T15:01→9, 10-01T15:05→9, 10-01T15:09→9, 10-01T15:13→9, 10-01T15:33→120, 10-01T15:50→184, 10-01T16:08→184 (694 of 744 fall inside a batch window). Wall clock first `score` row (2026-10-01T14:14Z) → STAGE_SCORING PASS (2026-10-01T17:23Z) = **3.14 h**; scoring.json: {'gate': 'PASS', 'subcaps': 694, 'scored': 694, 'overall': 1.01, 'blocking': 0, 'advisory': 1, 'unscored': 0, 'critic_missing': 0, 'critic_failed': 0, 'rollup_missing': 0, 'dashboard_incomplete': 0, 'no_differentiation': 0}.

## 5. REPORTS

Sources: `report_reviews.jsonl` ABSENT; Provenance `report_review:*` rows **95** (2026-10-01T17:45:31Z → 2026-10-01T19:18:27Z). 
- Reviews per report: {'client_research': 41, 'assessment': 54}; verdict distribution **{'REVISE': 56, 'PASS': 39}**; notes mentioning 'upstream' 0 (no `upstream` field; phrases: []).
- Reviews per report:section (count / of which REVISE+FAIL): client_research:1 6/4, client_research:2 7/5, client_research:3 6/4, client_research:4 6/5, client_research:5 9/7, client_research:6 1/0, client_research:7 2/1, client_research:8 4/2, assessment:1 7/4, assessment:2 3/1, assessment:3 2/0, assessment:4 3/1, assessment:5 7/5, assessment:6 7/4, assessment:7 6/3, assessment:8 7/5, assessment:9 4/1, assessment:10 6/4, assessment:11 2/0
- Rounds until READY: briefs reports_r* = **6**; STAGE_REPORTS rows {'FAIL': 2, 'PASS': 1} (round sum 6); FAILs: reports not READY after 4 round(s): client_research, assessment; blocking: client_research: §1, §2, §3, §4, §5 not READY; assessment: §1, §5, §6, §8,  | reports not READY after 2 round(s): client_research, assessment; blocking: client_research: §5, §8 not READY; assessment: §5, §7, §8, §9 not READY — s
- Review dimensions marked REVISE/FAIL (parsed from every non-PASS Provenance review row, 56 rows): {'evidence_support': 45, 'inference_honesty': 19, 'absence_rigour': 12, 'weighing_balance': 7, 'bias_disclosure': 6, 'tone': 1}.
- Recurring REVISE/FAIL reasons (keyword classes over the free-text part of those 56 notes, dimensions dict removed; a note can hit several): **citation form / E-id cited wrongly** 29; **figure/count does not reconcile** 25; **dates / currency / stale** 15; **CAGR / financial series** 10; **tech register / Clay scan rows** 9; **peer set / benchmark basis** 7; **weighing balance / one-sided** 7; **template / word count / length** 6; **round fixes landed / unchanged since round** 6; **unsourced/unsupported figure** 4
- Report_Narrative: **30 sections, 30,215 words** ({'client_research': 11705, 'assessment': 18510}). Per section (report §: words | reviews in Provenance | REVISE/FAIL = rewrites):
  - client_research §PRELIM-FIN Financial profile and lines of business (section): 171 w | 0 reviews | 0 rewrites | written 2026-10-01T11:35
  - client_research §PRELIM-LEAD Leadership and digital ownership (section): 225 w | 0 reviews | 0 rewrites | written 2026-10-01T11:42
  - client_research §PRELIM-FIRM Institution profile (section): 217 w | 0 reviews | 0 rewrites | written 2026-10-01T11:41
  - client_research §PRELIM-THOUGHT Thought leadership and stated direction (section): 244 w | 0 reviews | 0 rewrites | written 2026-10-01T11:42
  - client_research §1 Firmographics (section): 1234 w | 6 reviews | 4 rewrites | written 2026-10-01T18:40
  - client_research §2 Executive Summary (section): 1531 w | 7 reviews | 5 rewrites | written 2026-10-01T18:54
  - assessment §2 Assessment Methodology (section): 593 w | 3 reviews | 1 rewrites | written 2026-10-01T18:40
  - client_research §3 Entity Profile (section): 1218 w | 6 reviews | 4 rewrites | written 2026-10-01T18:40
  - assessment §3 Issue Impact and Cap Analysis (section): 715 w | 2 reviews | 0 rewrites | written 2026-10-01T18:40
  - assessment §4 Assessment Results (section): 667 w | 3 reviews | 1 rewrites | written 2026-10-01T18:40
  - client_research §4 Market Position and Trends (section): 1260 w | 6 reviews | 5 rewrites | written 2026-10-01T18:40
  - assessment §5 Pillar Deep Dives (pillar): 1385 w | 7 reviews | 5 rewrites | written 2026-10-01T18:31
  - assessment §5 Pillar Deep Dives (pillar): 1212 w | 7 reviews | 5 rewrites | written 2026-10-01T18:40
  - client_research §5 Strategic Intelligence (section): 3099 w | 9 reviews | 7 rewrites | written 2026-10-01T19:13
  - assessment §5 Pillar Deep Dives (pillar): 1130 w | 7 reviews | 5 rewrites | written 2026-10-01T19:13
  - client_research §6 Client Priorities (section): 797 w | 1 reviews | 0 rewrites | written 2026-10-01T17:31
  - assessment §5 Pillar Deep Dives (pillar): 1170 w | 7 reviews | 5 rewrites | written 2026-10-01T19:13
  - client_research §7 Risk and Issues (section): 1144 w | 2 reviews | 1 rewrites | written 2026-10-01T17:51
  - assessment §6 Benchmark and Technology Estate (section): 1847 w | 7 reviews | 4 rewrites | written 2026-10-01T18:55
  - client_research §8 Workbook References (section): 565 w | 4 reviews | 2 rewrites | written 2026-10-01T19:13
  - assessment §7 Gap Prioritisation (section): 1362 w | 6 reviews | 3 rewrites | written 2026-10-01T19:13
  - assessment §8 Recommendations (recommendation): 1272 w | 7 reviews | 5 rewrites | written 2026-10-01T19:14
  - assessment §8 Recommendations (recommendation): 1099 w | 7 reviews | 5 rewrites | written 2026-10-01T19:14
  - assessment §8 Recommendations (recommendation): 985 w | 7 reviews | 5 rewrites | written 2026-10-01T18:31
  - assessment §8 Recommendations (recommendation): 1052 w | 7 reviews | 5 rewrites | written 2026-10-01T18:30
  - assessment §8 Recommendations (recommendation): 969 w | 7 reviews | 5 rewrites | written 2026-10-01T18:31
  - assessment §9 Transformation Roadmap (section): 840 w | 4 reviews | 1 rewrites | written 2026-10-01T19:14
  - assessment §10 Data Gaps and Confidence (section): 896 w | 6 reviews | 4 rewrites | written 2026-10-01T18:41
  - assessment §11 Workbook Traceability (section): 199 w | 2 reviews | 0 rewrites | written 2026-10-01T18:41
  - assessment §1 Executive Summary (section): 1117 w | 7 reviews | 4 rewrites | written 2026-10-01T18:55
- Other report-stage gates: TECH_REGISTER_RECONCILE none; GS/TEMPLATE {'GS': {'FAIL': 1, 'PASS': 39}, 'TEMPLATE': {'PASS': 17}}; PRELIM_AMEND ["16 row(s): '27th largest US broker, 2020' -> '29th largest US broker, 2020 (per E-027)'; report-validator: E-027 states 29th; 27th has no source", "1 row(s): 'Hires first Chief Information Officer' -> 'Hires Chief Information Officer'; report-validator: no source states this was the first CIO"].

## 6. PAGES / PROMOTE

pages_workflow.json: not recorded. pipeline_state.pages:

| page | final version/status | attempts (pipeline_state) | sg_v4_fails (final) | versions | STAGE_PAGES gate ids named for this page |
|---|---|---|---|---|---|
| techstack | B/pass | 10 | 0 | {'A': 'pass', 'B': 'pass'} | {'CG-23': 1, 'CG-27': 1, 'SG-V4': 1} |
| heatmap | B/pass | 4 | 0 | {'A': 'pass', 'B': 'pass'} | {} |
| overview | B/pass | 1 | 0 | {'B': 'pass'} | {} |
| insights | B/pass | 1 | 0 | {'B': 'pass'} | {} |
| platform | B/pass | 1 | 0 | {'B': 'pass'} | {} |
| context | B/pass | 1 | 0 | {'B': 'pass'} | {} |

Total page attempts (pipeline_state) **18**; STAGE_PAGES_A rows {'FAIL': 4, 'PASS': 1} (attempt sum 6), STAGE_PAGES_B rows {'PASS': 1} (attempt sum 0); STAGE_PROMOTE rows none. Gate ids across all STAGE_PAGES FAIL rows: {'CG-23': 1, 'CG-27': 1, 'SG-V4': 1}. Special rows: {'PAGE_PREFLIGHT': 0, 'CONNECTOR_DRIFT': 0, 'SG_V4_BUDGET_RAISED': 0, 'SG_V4_BUDGET_OVERRIDE': 0, 'ENRICHMENT': 0, 'PRELIM_AMEND': 2, 'INGEST_A_REPOINT': 1, 'OWNER_DECISION': 0, 'REPORT_PROBES': 0, 'FLOORS_WAIVER': 0} (PAGE_PREFLIGHT and CONNECTOR_DRIFT: none recorded in any run; CG-*/ET-*/SG-* never appear as their own Gate_Log rows — only inside STAGE_PAGES detail and verdict files).
- Verdict files (07_qa/verdict*.json): `verdict_techstack_A.json` → techstack: pass reasons=0 gate_ids={} sg_v4=1; `verdict_techstack_B.json` → techstack: pass reasons=0 gate_ids={} sg_v4=0; `verdicts_A.json` → techstack:  reasons=7 gate_ids={} sg_v4=7
- PAGES lanes: A 12 lanes / $3.36, B 4 lanes / $1.05; 0 lane failures in either.
- PAGES_A FAIL rows:
  - claim on d5aed033-718d-4923-901f-2f761c489e0b refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 77.8s; rounds 0]
  - claim on a1550631-23a2-426f-9172-b2631605b308 refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 46.1s; rounds 0]
  - page(s) not passing on version A after 3 attempt(s): techstack: {'gate_id': 'CG-23', 'section': 'techstack', 'path': 'techstack.narrative_thread', 'message': "this , {'gate_id': 'CG-27', 'section': 'techstack', 'path': 'techstack.
  - page(s) not passing on version A after 3 attempt(s): techstack: SG-V4 grounding FAIL x60 over budget 8 — find grounding or drop the claim, techstack.narrative_thread (sim 0.438 < 0.5) [elapsed 172.3s; rounds 0]

## 7. ENRICHMENT / PRELIM

- Gate_Log ENRICHMENT rows: **none** (gates present: ['STAGE_PRELIM', 'PRELIM_AMEND']); STAGE_PRELIM: {'n': 1, 'verdicts': {'PASS': 1}, 'final': 'PASS', 'fail_details': []}. PRELIM ledger: [('2026-10-01T11:35Z', 4.3, 2, 7.5)].
- search_relay.jsonl: **absent**.
- Run_Metadata enrichment facets: only ['prelim_status', 'prelim_completed_at', 'connector_run_id', 'connector_run_id_prev', 'connector_ingest_after_seq'] — no enrichment facet counts recorded. Enrichment_Needed sheet rows: 4; Firmographics rows 10 states {'STATED': 8, 'ABSENT': 2}.
- PRELIM rows in Search_Log (blank SubCap_ID): **16**; tools {'clay': 2, 'explorium': 2, 'indeed': 1, 'web_search': 11}.
- PRELIM evidence (E-ids with Retrieved_At before the first category search at 2026-10-01T12:49Z): **30** (E-001…E-030); cited by Subcap_Scoring rows **0**; carrying SubCap_IDs 0; **orphaned (neither) 30**.
- Dispatch files: ['enrichment-connector-specialist.json', 'report-assessment-producer.json', 'report-research-producer.json', 'report-validator.json', 'research-challenger.json']; handbacks: {'research-conductor': 1, 'research-challenger': 21}.

## 8. Lock contention signals

- Gate_Log STAGE_PAGES_A @ 2026-10-01T19:27:48Z: claim on d5aed033-718d-4923-901f-2f761c489e0b refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 77.8s; rounds 0]
- Gate_Log STAGE_PAGES_A @ 2026-10-01T19:41:32Z: claim on a1550631-23a2-426f-9172-b2631605b308 refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again [elapsed 46.1s; rounds 0]
- cost_ledger PAGES_A @ 2026-10-01T19:27:52Z: pipeline FAIL: claim on d5aed033-718d-4923-901f-2f761c489e0b refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again
- cost_ledger PAGES_A @ 2026-10-01T19:41:35Z: pipeline FAIL: claim on a1550631-23a2-426f-9172-b2631605b308 refused while shipping heatmap: another session holds the lease; wait for it to lapse, then run again
- pipeline_state.json matches: none; driver/pipeline logs scanned 1 files, hits {'lease': 4}; agent_logs present: False (excluded from snapshots — nothing to read).

---

# Cross-run table

| run | subcaps | wall clock h | research FLOORS rounds (fail/total) | research handoffs | scoring critic rounds P1/P2/P3/P4 | scoring pipeline rounds | report reviews (REVISE+FAIL / total) | report rounds | page attempts (pipeline_state) / STAGE_PAGES FAIL rows | promote attempts | total USD | USD per stage |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Arbor Bank | 708 | 52.1 | 164/212 | 15 | 11/13/11/11 = 46 | 19 | 99/137 | 19 | 55 / 12 | 3 | $409.10 | PRELIM 6, RESEARCH 254, SCORING 41, REPORTS 74, PAGES_A 13, PAGES_B 22 |
| Susser Bank | 708 | 27.1 | 108/141 | 8 | 19/21/19/17 = 76 | 29 | 118/154 | 26 | 76 / 17 | 2 | $450.02 | PRELIM 3, RESEARCH 249, SCORING 49, REPORTS 110, PAGES_A 15, PAGES_B 24 |
| Cross Insurance Agency | 694 | 9.0 | 23/75 | 2 | 14/13/21/13 = 61 | 21 | 56/95 | 6 | 18 / 4 | 0 (no STAGE_PROMOTE row) | $82.71 | PRELIM 4, SCORING 42, REPORTS 32, PAGES_A 3, PAGES_B 1 |

Per-stage USD share: Arbor Bank: PRELIM 1%, RESEARCH 62%, SCORING 10%, REPORTS 18%, PAGES_A 3%, PAGES_B 5%; Susser Bank: PRELIM 1%, RESEARCH 55%, SCORING 11%, REPORTS 24%, PAGES_A 3%, PAGES_B 5%; Cross Insurance Agency: PRELIM 5%, SCORING 51%, REPORTS 39%, PAGES_A 4%, PAGES_B 1%

Tokens (cache_read / cache_write / uncached / output): Arbor Bank cr 771,810,779 / cw 69,595,105 / unc 21,524 / out 2,789,168; Susser Bank cr 846,835,457 / cw 70,962,340 / unc 22,224 / out 3,243,199; Cross Insurance Agency cr 93,838,824 / cw 9,164,670 / unc 3,376 / out 1,056,711

Evidence & search: Arbor Bank: Search_Log 6332 rows (1508 distinct query+timestamp, 345 true re-runs), Evidence_Detail 252 rows (211 cited), evidenced cells 148 / absent 568; Susser Bank: Search_Log 6319 rows (1486 distinct query+timestamp, 175 true re-runs), Evidence_Detail 428 rows (385 cited), evidenced cells 231 / absent 494; Cross Insurance Agency: Search_Log 4999 rows (1316 distinct query+timestamp, 443 true re-runs), Evidence_Detail 70 rows (39 cited), evidenced cells 40 / absent 657

# What the numbers say (12 bullets)

1. **Research is the cost centre and the estimate under-shoots ~1.8×.** Arbor research charged $254.15 of $409.10 (62%), Susser $249.41 of $450.02 (55%); the first handoff estimated $141.56 for 708 cells in both runs (pilot $0.19/cell + $0.44/category). Cross recorded **no** research charge at all (0 `workflow agents charged` rows), so its $82.71 total is scoring+reports+pages only.
2. **Research closes by attrition, not in one pass.** Arbor needed 15 handoffs and 212 FLOORS rounds (164 FAIL); 13 of 16 categories took ≥11 rounds (P3C2 20, P3C1 19, P1C1 18) and 4 categories were closed by FLOORS_WAIVER (8 cells). Susser: 8 handoffs, 141 rounds (108 FAIL). Cross: 75 rounds but P2C2, P3C2, P3C4 and P4C1 passed FLOORS in a single round with **0 evidenced cells** each.
3. **The dominant floors blockers are the same everywhere:** `challenge_failed` 68, `absence_undeclared_empty` 62, `single_source_fact` 60, `primary_unfired` 55 (Arbor); `volleys_incomplete` 73, `primary_unfired` 57, `absence_undeclared_empty` 52, `single_source_fact` 50 (Susser). Challenge_Log FAIL rate: Arbor 205/387, Susser 135/363, Cross 26/67.
4. **Search volume is logged ~5× over actual searches, and the ceiling check reads rows.** Arbor Search_Log 6332 rows but only 1508 distinct (query, timestamp) pairs (4824 rows are one search written per facet × per batch cell); true re-runs 345 (Arbor), 175 (Susser), 443 (Cross). `stage_advance.json` (Arbor) read "6233 search-ops against a ceiling of 60" — the row count.
5. **Evidence yield per search is low and falls to near zero without Exa/Tavily.** Evidenced cells / evidence rows / Search_Log rows: Arbor 148/252/6332 (21% of 708 cells), Susser 231/428/6319 (33%), Cross 40/70/4999 (6% of 694; web_search-only, `REDUCED RIGOUR`). Search rows with Kept=0: Arbor 4928/6332, Susser 4870/6319, Cross **4838/4999**. Unattached evidence rows: 41/43/31.
6. **Scoring loops on the same two blockers every round.** Every SCORING gate FAIL row carries `dashboard_incomplete=13` and `rollup_missing=2` (Arbor 21/21, Susser 36/36, Cross 29/29); critic rounds per run 46 / 76 / 61 (Susser P2 21 rounds `FFFFFFFFFFFFFFFFFPPPP`, Cross P3 21 `FFFFFFFFFFFFFFFPPPPPP`); subcaps re-scored >1× 100 / 165 / 40; first score → SCORING PASS 18.94 h / 10.04 h / 3.14 h. No MOVE gate or `critic_moves` record exists; moves live only in critic prose (88 / 107 / 56 named).
7. **Report review REVISE rate is 59–77% and the stage stops on 'last 2 rounds advanced nothing'.** Non-PASS reviews: Arbor 99/137 over 19 rounds (3 STAGE FAILs incl. one signal-15 kill), Susser 118/154 over 26 rounds (9 STAGE FAILs; assessment §8 Recommendations 25 reviews / 22 rewrites, §6 19/17), Cross 56/95 over 6 rounds. REPORTS cost $109.85 (Susser, 24%), $73.57 (Arbor); Susser's `report_reviews.jsonl` holds 28 of the 154 reviews in Provenance.
8. **SG-V4 grounding is bypassed by owner budget in both promoted runs.** Default budget 8; admitted prose fails Arbor overview/insights/platform/context = 173/112/204/39 (`--sg-v4-budget 250`, 8 SG_V4_BUDGET_RAISED rows), Susser 138/66/193/29 (budget 300, 8 SG_V4_BUDGET_OVERRIDE rows); verdict files record heatmap sg_v4_fails 997 (Arbor B) and 1517 (Susser B).
9. **Pages take 50–76 attempts per run and ET-07 (cited E-id does not resolve) is the most frequent blocker.** Attempts (pipeline_state): Arbor 55 (heatmap 15), Susser 76 (heatmap 21, techstack 16), Cross 18; ET-07 named in 4 Arbor and 7 Susser STAGE_PAGES FAIL rows. Promote refused: Arbor 2× `retained_pages_fail_current_gates` (CG-PAR on overview/platform), Susser 1× FK violation (`E-025` not in evidence_index). PAGE_PREFLIGHT and CONNECTOR_DRIFT rows: none in any run.
10. **Ingest is a ~30-minute poll with no cost line.** INGEST_A 1735.9 s / INGEST_B 2138.3 s (Arbor), 1929.9 / 1282.4 s (Susser), 12.8 / 1710.8 s (Cross).
11. **PRELIM evidence is almost never cited by scoring.** PRELIM E-ids (registered before the first category search): Arbor 26 → 2 cited, 24 orphaned; Susser 26 → 1 cited, 25 orphaned; Cross 30 → 0 cited, 30 orphaned. search_relay: Arbor 47 open / 4 served / 43 empty; Susser 92 open / 23 served / 71 empty / 27 blocked; Cross none.
12. **Wall clock is mostly waiting, and the only lock signal is Cross's lease refusal.** Arbor 52.1 h wall vs 16.8 h recorded elapsed (PAGES_B 844.8 min wall vs 36.5 min agent time; PROMOTE refused 02:24Z, succeeded 07:22Z); Susser 27.1 h vs 20.2 h; Cross 9.0 h vs 8.5 h. Signal-15 terminations: Arbor 2, Susser 1, Cross 0. Lock/lease: Cross PAGES_A 2× `claim … refused … another session holds the lease` (19:27Z, 19:41Z; 124 s); Arbor and Susser none; agent_logs absent in all three.
