# Mined evidence — B1 Bank sessions (DMA-2026-B1BANK-001)

Method: `mcp__claude-code-remote__list_events` (kinds user/assistant/result, limit 100), paged newest→oldest with `before_id`, 60 pages per session (the cap). Pages saved to `scratchpad/sessions/<id>.jsonl`; pages the tool returned inline (too small to be file-saved) were transcribed by hand to `scratchpad/tools/inline_notes_*.md`. Timestamps are UTC, `created_at` of the event. Both sessions' RESEARCH and SCORING stages ran before 2026-10-08T16:17Z, i.e. **before the oldest page the 60-page cap reached**, so research-round, floors-gate and critic-round counts are "not stated" below unless a later message restated them. `$` figures come from three different meters and are labelled: **session meter** (CCR `total_cost_usd` / `get_session.usage.cost_usd`), **engine ledger** (`engine.cost report`, `07_qa/cost_ledger.jsonl`), **model usage** (per-model `costUSD`).

---

## Session 1 — session_01KU8y6us2Vx2UqyivesN44K "B1 Bank web app promotion"

- Created 2026-10-08T02:34:25Z · last update 2026-10-09T05:42:16Z (≈27.1 h). Origin web_claude_ai, model claude-opus-5-5, permission auto, `worker_epoch` 6 (several container restarts), goal `iterations` 9.
- Pages read: 60 (coverage 2026-10-08T16:17:54Z → 2026-10-09T05:42:16Z). Events kept: 374 in JSONL + 8 inline pages transcribed.
- **Session meter at close** (`get_session.usage`): `cost_usd 646.14`, `output_tokens 12,325,872`, `input_tokens 35,203,206`, `cache_read_tokens 1,163,461,964`, `cache_write_tokens 82,382,574`. The in-transcript `result.total_cost_usd` counter only reaches **$481.62** (2026-10-09T05:42:16Z); the gap to 646.14 is not explained in the transcript (the session restarted several times).
- **Model split** (result event 2026-10-08T16:43:36Z, cumulative): haiku-5-5 `costUSD 23.41`, `inputTokens 29,670,337`, `outputTokens 2,092,505`, **`webSearchRequests 1911`**; opus-5-5 `costUSD 226.45`, `outputTokens 2,831,790`; sonnet-5-5 `costUSD 202.89`, `outputTokens 4,083,065`.
- Outcome: both reports approved and rendered; **not promoted**. Handed off to a new session.

### 1. Dollar / token / budget figures (verbatim)
| Time (UTC) | Meter | Quote |
|---|---|---|
| 10-08 16:57:39 | engine ledger | "(workflow spend captured: 82 agent(s), $191.74)" … "run DMA-2026-B1BANK-001 · 47 record(s) in …/07_qa/cost_ledger.jsonl ⏎ cost $1131.51 (budget $20.00 for 4 pillar(s)) OVER" |
| 10-08 16:57:46 | assistant → user | "B1 Bank has spent $1,131.51 of the $1,150 ceiling. 3 of 19 report sections are still open … Each final whole-report review has been reopening 1–2 sections it hadn't flagged before, so finishing likely needs another $250–400." |
| 10-08 17:07:40 | engine ledger | "49 record(s) … wall clock 120.4 min (target 120, schedule 98.0) OVER ⏎ cost $1131.51 (budget $20.00 for 4 pillar(s)) OVER" |
| 10-08 17:08:00 | assistant | "**Spend:** $1,131.51 recorded against the $1,150 ceiling, plus a few dollars for the final reviewer that isn't recorded yet. The run took about 2 hours." |
| 10-08 17:08:00 | assistant | "The run went well over its $20 starting estimate, mostly because the search services were out of credit and the reports took many review rounds." |
| 10-08 17:09:43 | assistant | "My earlier estimate for that [six pages + publishing], and for the report rounds that were still open then, was $250–400." |
| 10-08 17:34:27 | assistant | "Raising the ceiling to $1,500, the figure I recommended earlier." (`--max-usd 1500`) |
| 10-08 18:45:53 | engine ledger | "57 record(s) … PAGES_A 124.5m — (32 attempts over 30 lanes) ⏎ cost $1140.77 (budget $20.00 for 4 pillar(s)) OVER ⏎ unrecorded stages: PREFLIGHT, START, CHALLENGE, GATES, RELAY, PACKAGE, INGEST_B, PAGES_B, PROMOTE" |
| 10-08 18:46:10 | cost_ledger.jsonl tail | `{"attempts": 16, "elapsed_s": 4068.8, … "lanes": 15, "model": null, "note": "pipeline FAIL: page(s) halted on version A …"}` |
| 10-08 18:48:42 | assistant | "Spend is $1,140.77 of $1,500. This page attempt cost $9.26 and took about two hours." |
| 10-08 16:18:17 → 05:42:16 | session meter | `total_cost_usd` 432.83 → 443.30 (16:30) → 450.51 (16:40) → 452.75 (16:43) → 463.60 (17:04) → 469.96 (17:33) → 471.14 (17:37) → 478.31 (18:50) → 480.11 (19:05) → 481.62 (05:42) |

Derived (arithmetic on the quoted figures): REPORTS end-game 16:18→17:04 cost **$30.77** on the session meter; the stop-hook loop 17:33→05:42 (no work done) cost **$11.66** on the session meter; PAGES_A attempt cost **$9.26** on the engine ledger but **$7.17** session meter (471.14→478.31).

### 2. RESEARCH
- Stage summary printed by the driver (10-08 17:37:03): "[KG] done — DQ_Bank 6333 rows ⏎ [RESEARCH] done — every category gate PASS ⏎ [HANDOFF] done — handoff written and verified; research ready".
- Coverage (reviewer note 10-08 16:29:52): "Subcap_Scores: 347 of 708 cells are NO_EVIDENCE declared absences struck at the 1.0 rubric floor (Coverage: Researched 361 of 708) … Category score tracks Coverage Floor_Pass_Pct at r=0.91 across the 16 categories".
- Search volume: haiku `webSearchRequests 1911` (session meter, 16:43:36); Search_Log seq numbers quoted up to **5507** (16:40:29: "Search_Log 5507 also looked for a completion statement"); duplicated seq numbers: "Search_Log Seq 5470 and 5482 each label four different queries" (16:43:24).
- Search credit: "the search services were out of credit" (17:08:00). Rounds, lanes started, floors-gate failures, re-dispatches: **not stated in pages read**.
- Workbook write collision (REPORTS stage, 10-08 16:17:58): review row "10 REVISE 2026-10-08T16:17:23Z | Whole-report pass r1 (re-recorded: the first write was lost to a concurrent workbook write)."
- Lock file visible in the run dir listing (session 2, 10-09 05:28:36): `DMA_Scoring_Workbook_b1-bank_2026-10-08.xlsx.lock`, `tmpusqe4j5u.xlsx.part`.
- Connector availability: 10-08 18:48:42 "the session restart disconnected Clay and Vibe, so I can't rerun the scans"; 18:49:02 "The background page agents don't have Clay or Vibe either; they only reach the DMA Insights connector."; 18:56:25 "the Clay connector now shows up in this session's server list, but its tools still can't be called here. Vibe isn't connected at all."
- NOT_RUN: 17:08:00 "The FDIC enforcement check couldn't run because its built-in test search failed. It is recorded as not run, not as "no actions found"."

### 3. SCORING
- "[SCORING] done — SCORING gate PASS; findings packet verified" (17:37:03). Scores: composite 1.43 (Activating) vs peer 1.65; P1 1.58/1.53, P2 1.25/1.70, P3 1.56/1.72, P4 1.28/1.62 (17:08:00).
- Critic rounds per pillar, FAIL reasons, scores moved, stage cost/time: **not stated in pages read**. Only indirect evidence: PR #78 fix list (17:08:00) "a scoring critic could loop on rewrites"; and findings-memory rows read in session 2 (10-09 05:34:25, 7-day window, run attribution not stated): "MEM-0594 … The scoring critic's FAIL never reached the scorers: the scorer brief served only unscored rows, so every cell the critic named was invisible"; "MEM-0593 … A gap waiver recorded after scoring had already opened was never disclosed, so its cells read as plain 'unscored' and blocked the SCORING gate"; "MEM-0589 … The research driver trusted a recorded floors PASS after the gate's rules tightened, so claimed cells the live gate refuses were never re-dispatched".

### 4. REPORTS (19 sections: assessment 11, client research 8)
Whole-report adversarial passes kept reopening already-passed sections; each reopening relaunched `dma-reports.js` with `rounds: 2`:
| Time | Event |
|---|---|
| 16:16:44 / 16:16:58 | assessment §6 REVISE (KlariVis go-live contradiction) and §10 REVISE: "§10.1 says 'Of the 998 registered sources, 416 carry no publication date' … Evidence_Detail now holds 1005 rows … E-999 to E-1005 were registered after 14:51Z on 2026-10-08, after this section was written." |
| 16:18:03 | Workflow `wf_f0f3f817` launched: assessment §6 + §10. `ls subagents/workflows | wc -l` → **77** workflow runs so far. |
| 16:18:09 | "seven sections are back with the writers … **Assessment report:** 9 of 11 sections pass … **Client research:** §1, §2, §6, §7 and §8 are still in their final round. These reopenings come from facts that changed after a section was written, not from new standards. I've stopped registering evidence until both reports pass" |
| 16:29:26→16:29:57 | client research §4 reopened ("Only defect found across sections 1 to 8" — evidence-coverage artefact caveat); Workflow `wf_1051c949` §4. |
| 16:30:27→16:31:01 | assessment §8 reopened ("Reopened for cross-section figure drift … REC-05 … TS-044 KlariVis … (2) Every card's Rebuttal C … E-033 is the holding company's consolidated figure"); Workflow `wf_cbc443a1` §8. |
| 16:40:05→16:40:32 | client research §5 reopened ("Cross-section contradiction on the Progressive conversion basis"); Workflow `wf_691d2c61` §5. "Each final review now finds one remaining inconsistency, down from four or five per pass earlier." |
| 16:43:09→16:43:30 | assessment §8 REVISE **again** `{'absence_rigour': 'REVISE', 'evidence_support': 'REVISE', …}`: "FIXES (both REC-02, which was not rewritten) … The section runs 7108 words against a 4400 guide"; Workflow `wf_3fe88fed` §8 (second §8 relaunch in 12 min). |
| 16:57:39 | driver: "[REPORTS] PENDING_ORCHESTRATOR — workflow: 2 report workflow(s), 3 writable section(s)" (client_research §2, §4; assessment §5). |
| 17:02:21 | user: "Hold the budget and finish the reports kindly. No budget raise anymore" |
| 17:04:04 | assistant fixed the last 3 sections by hand: "I fixed them directly instead of running another rewrite round … One independent validator is reviewing just those three sections now." |
| 17:07:24 | "[REPORTS] PASS — rendered … (20.6s)"; sizes "client_research … 14413/3050 words READY ⏎ assessment … 27051/8400 words READY" (actual/guide). |
- Challenge/critic reuse: not stated; the reviewer notes show figures were **re-derived** against sheets each pass ("every prose figure in sections 1-8 re-derived against Subcap_Scores, Category_Rollup, …", 16:40:29).

### 5. PAGES / PROMOTION
- 17:07:24 preflight halt before any agent: "[PAGES_A] FAIL — 2 page blocker(s) found in the workbook before any page agent ran: [CG-50] TS-006 'Q2 Digital Banking Platform' appears in none of its cited excerpt(s) E-076, E-079 (searched for ['Holdings'])" + "[CG-50] TS-034 'b1BANK Mobile Banking app (vendor undisclosed)' appears in none of its cited excerpt(s) E-082".
- 17:09:43 diagnosis: "the check that confirms each cited source names its product ignores words shorter than three characters, so it never searches for "Q2"."
- 17:37:17 "No such tool available: Workflow" after restart → fallback `--pages-mode lanes --allow-lanes` (17:37:28).
- 18:45:45 result after 4068.8 s: "[PAGES_A] FAIL — page(s) halted on version A — not retried … heatmap: the SG-V4 prose repair did not converge: 17 grounding fail(s) after repair, 17 before (budget 8). Last verdict: SG-V4 grounding FAIL x17 over budget 8 … focus_areas.focus_areas[0].name (sim 0.336 < 0.5); techstack: the repair did not converge: 6 blocking reason(s) after repair, 6 before." Also "[BRIEF] WARNING PAGES_A lane page-techstack: 5 row(s) dropped to fit the packet ceiling".
- Techstack verdict (18:46:00, `status local_precheck_fail`, 6 reasons): ET-07 ×4 (E-074, E-075, E-081, E-082 "linked to NO capability cell"), ET-12 ("the register cites no machine technographic scan"), CG-50 (page agent reverted TS-006 to the long name).
- 18:48:42 root cause: "B1's Clay and Vibe scans did run, but their readings came in through the workbook. The connector's ingest stores every workbook row without naming the scanning tool, so the check can't see them … Those responses weren't saved, and the session restart disconnected Clay and Vibe".
- 18:48:18 "No such tool available: AskUserQuestion" — grounding decision could not be asked.
- promote_run: never called. CONNECTOR_DRIFT: not stated.

### 6. ENRICHMENT
- subagent_stats (16:18:17 result): `enrichment-web-specialist 1, technographic-scanner 1, general-purpose 3`.
- Scans ran in research but were unusable for ET-12 (above); FDIC enforcement sweep NOT_RUN (17:08:00). record_enrichment: not seen in pages read.

### 7. User messages and diagnoses
- Goal/stop-hook prompt (fired **57 times** in pages read, 17:08:04 → 05:42:16, each answered with a near-identical "B1 Bank is still not on the web app"): "Please assess B1 Bank and promote the entity to the web app. Ensure to avoid redos by always formulating a clear plan with antipatterns that would fail tests to ensure less token consumption. Use necessary workflows for each stage to ensure parallelization and great speed management…"
- 17:02:21 "Hold the budget and finish the reports kindly. No budget raise anymore" · 17:34:14 "Raise it" · 18:57:18 "Give the prompt for the new session".
- Assistant's stated root causes: budget overrun = search services out of credit + many report review rounds (17:08:00); PAGES failure = ingest drops `connector_tool` (ET-12), CG-50 skips 2-char tokens, unlinked evidence (ET-07), SG-V4 titles paraphrased (18:48:42).

### 8. Wall-clock
- Session 02:34:25 → 05:42:16 next day (≈27.1 h). Engine ledger: "wall clock 120.4 min (target 120, schedule 98.0) OVER" at REPORTS end (17:07:40); PAGES_A 124.5 min (18:45:53). REPORTS tail 16:17→17:07 ≈ 50 min of relaunches. Idle goal-hook loop 17:33→05:42 ≈ 12 h.

---

## Session 2 — session_01CG6YjSpyVBPah7Ev3AYHRK "B1 Bank DMA assessment resume"

- Created 2026-10-08T19:04:34Z · last update 2026-10-09T05:44:45Z (≈10.7 h). Origin android, model claude-opus-5-5, context used 616,974 / 1,000,000 tokens, branch `ccr-3f403b7a-1er9fx`, PR #83.
- Pages read: 60 (coverage 2026-10-09T04:25:00Z → 05:43:52Z; 10 pages inline-transcribed). Events kept: 433 in JSONL. The first ~9 h (19:04 → 04:25: PAGES_A repair of techstack/heatmap on version A, Clay/Vibe re-scan, PR #83) lie before the oldest page reached.
- **Session meter at close**: `cost_usd 82.17`, `output_tokens 1,221,367`, `cache_read 226,693,240`, `cache_write 6,673,582`. In-transcript `total_cost_usd`: 47.99 (04:25:00) → 48.77 (04:26:39) → 61.93 (04:41:41) → 75.08 (05:06:04) → 77.64 (05:15:02) → 83.09 (05:28:31) → 84.01 (05:29:24) → 87.19 (05:34:46).
- **Model split** (05:15:02): opus `costUSD 33.94`, `outputTokens 276,548`; sonnet `costUSD 43.69`, `outputTokens 800,172`; haiku `0.013`.
- **Engine ledger**: "run COMPLETE at $1,236.14 of $1,500" (QA overseer 05:43:09); 05:31:44 "spend at $1,236.14/$1,500 and 51 prose fails within the 257 budget". Derived: 1,236.14 − 1,140.77 (handoff figure) = **$95.37** engine-ledger spend for this resume.
- Outcome: **PROMOTED** — 05:31:36 "[PROMOTE] PASS — promoted 75a9292a-f690-4330-b825-50d0c0769d7b at 2026-10-09T05:31:03.671914+00:00 (16.2s)"; "all six pages (2,216 rows) atomically written" (05:31:44).

### 1. Budget / ceiling figures
- Every driver call: `engine.pipeline run … --max-usd 1500 --max-wall-min 240 --lane-retries 1 --page-retries 2` (05:00:20 `driver_resume_5.log`); `--sg-v4-budget 257` added at 05:12:24 (`driver_resume_6`), 05:14:06 (`_7`), 05:30:09 (`_8`). Eight resume logs exist (`driver_resume_1..8.log`, dir listing 05:28:36).
- SG-V4 budget raise, owner decision in-session: 05:12:23 "measured prose counts of platform 257, overview 182, and insights 60 — so the PAGES_B budget is set at the highest measured figure, 257". Final waivers (05:31:36): `[('techstack','A',62), ('overview','B',182), ('platform','B',257), ('insights','B',60), ('context','B',51)]`; default budget was 8 (`sg_v4_budget: int = 8`, pipeline.py line 600).
- Weekly usage limit: 04:25:00 synthetic assistant "You've hit your weekly limit · resets Oct 10, 11am (UTC)" (`api_error usage_limit_reached`, status 429, `rateLimitType seven_day`, `overageDisabledReason org_level_disabled`); 04:26:15 "11 of 18 agents finished before the limit. Resuming from run `wf_5c9f11fa-c06`"; QA 05:43:09 "7 of 18 agents lost; 0 finished agents re-run (per report)".

### 2. RESEARCH — not in window (completed in session 1). Related QA findings recorded 05:41:13: "10 workbook rows marked connector; 0 reach the store as connector origin (per run report); 2 scans run twice".

### 3. SCORING — not in window; no critic data in pages read.

### 4. REPORTS — complete before this session; no report work.

### 5. PAGES / PROMOTION (version B = connector run 75a9292a; version A = e3b7f92e)
| Time | Page | Gate(s) | What happened |
|---|---|---|---|
| 04:26:27 | overview, insights, platform | — | PAGES_B group 1 resumed from cache (`resumeFromRunId wf_5c9f11fa-c06`): 8 overview fragment producers + challenge + consolidate + assemble, 2 insights, 3 platform (18 agents). 04:26:31 "an agent finished without calling StructuredOutput". |
| 04:56:55 | overview | ET-07 ×6 | "E-028, E-033, E-039 and E-1005 in `exec_summary`, and E-048 and E-080 in `findings`, are linked to no cell" + "two narrative threads still say the Progressive cutover is 'scheduled for 10 August 2026', two months in the past." Fixed by hand (04:57–05:00); Clay Open Jobs re-run → E-CC-1787. |
| 05:01:36 | overview, insights, platform | — | "All three came back marked **repair**, so they failed on the server even though they were clean locally." |
| 05:05:44 | platform | CG-30 ×4 | "ranked 3 on the card, 4 by the engine" (platforms[2..4].rank) and "the card says 43.2 and the engine computes 43.3" (platforms[5].fit_score). Repair workflow `wf_1c8d6123` (05:06:00). |
| 05:08:59 | overview | CG-31 (not caught) | "overview's O5 opportunity tiles still carry the old order, and the overview dry-run doesn't catch it" → narrow repair via overview-opportunity-producer. QA 05:39:46: engine moved "CRM Analytics from INSUFFICIENT_EVIDENCE to READY, rank 6 to 3, fit 43.2 to 43.3" between run A and B; "The overview opportunity tiles kept the old ranks and passed the server once". |
| 05:12:13 | platform, overview | SG-V4 | "platform pass blocking 0 prose SG-V4 257 ⏎ overview pass blocking 0 prose SG-V4 182" |
| 05:13:58 | insights | SG-V4 | `insights {'B': 'sg_v4_over_budget'} 60` after budget raise; 05:14:03 "insights wasn't re-evaluated since its files are unchanged since budget 8. I'll touch its file timestamps so the driver re-ships it" → 05:14:50 pass. |
| 05:14:59 | context | — | Workflow `wf_9ca693ce` (risk, sentiment, timeline producers + assembler). |
| 05:28:09 | context | ET-07 ×4 + contradiction | "Context came back **BLOCKED** … E-023, E-042, E-049 and E-068 have no cell links … The timeline says the 3.0 ceiling 'lifted when the matter closed in June 2025'. The register … say it stays stamped (non-binding) until … 30 June 2027." Two parallel repairs (risk + timeline producers). |
| 05:31:36 | all six | — | "[PAGES_B] PASS — restaged ; shipped context to version B (26.4s) … [PROMOTE] PASS" ; `techstack {'A':'pass','B':'pass'} 0 · heatmap {'A':'pass','B':'pass'} 0 · overview B pass 182 · insights B pass 60 · platform B pass 257 · context B pass 51`. |
- QA overseer measurements (05:40:11–05:40:55): "2 of 2 pages called 'rejected': 0 server refusals between them (heatmap 6/6 PASS; techstack 0 submissions before the driver hold lifted)"; "**7 byte-identical resubmissions across 5 pages, 2 of them the 3.4 MB heatmap; all 7 server PASS both times**"; "6 of 6 pages over the default budget; 5 of 6 admitted only by raising the budget to the measured count; at least 145 of 620 counted FAILs are identifier/enum leaves or other-bank peer statements"; "2 of 6 promoted pages with SG-V4 NOT_RUN; driver count 0 on both, against 8 and 62 measured on the identical or prior payload"; "analysis pages: median failing-prose similarity 0.348-0.384 against 0.50; heatmap: 8 residual FAILs at 0.541-0.616 against 0.62". Total prose SG-V4 FAILs across the six promoted verdicts: **620** (05:35:29).
- Pages produced again after reports: yes — all six pages were (re)produced in this session (version A techstack/heatmap repaired before 04:25, version B four pages after). Overview was repaired twice, platform once, insights re-shipped once, context once.
- CONNECTOR_DRIFT: not stated. QA 05:39:55: "the manifest was hand-bumped to 35 … and on 2026-10-08/09 the connector serves 36. The same B1 doctor run reported UPDATED_MID_SESSION and the session ran in recovery mode".

### 6. ENRICHMENT
- 05:43:47 record_refinement: "run Clay Tech Stack and Vibe technographics again and register each reading through register_evidence as origin=connector … That gave E-CC-1770..1785 (T1, CURRENT), cited on 24 register rows. Then call record_enrichment for the techstack facet once per source (clay 14 rows, explorium 21 rows)".
- 04:58:12 third Clay call this run (Open Jobs, entityId 38291576) because E-080 (the research-stage Clay Open Jobs reading) was `origin package`, unlinked; 04:59:03 "The Clay result wasn't saved to disk, so I'll write the Open Jobs record myself"; QA 05:42:49 "E-CC-1787 … carries retrieved_at 05:05:02Z, while the Clay call returned at 04:58:22Z … no amend route exists".
- QA 05:41:13 (component worker): "10 workbook rows marked connector; 0 reach the store as connector origin (per run report); 2 scans run twice".

### 7. User messages
- 04:26:12 user: "Try again" (only human message in the window). Session's goal hook: none fired in window.
- Assistant root-cause statements: 04:26:15 weekly usage limit killed subagents; 05:01:36 server verdicts differ from local precheck; 05:08:59 cross-page rank drift; 05:14:03 driver mtime gate prevents re-judging under a raised budget.

### 8. Wall-clock
- Session 19:04:34 → 05:44:45 (≈10.7 h incl. the usage-limit wait). In-window: PAGES_B group 1 04:26 → 05:12 (46 min incl. two repairs); context 05:15 → 05:30 (15 min); promote 05:31:03; QA overseer 05:34 → 05:43. `duration_api_ms` at 05:34:46: 10,183,619 (≈2.83 h of API time for the session's main thread).

---

## Cross-session quantitative table

| Stage | Cost $ | Rounds | Retries | Wall-clock | Source quote (session · time) |
|---|---|---|---|---|---|
| Whole run (engine ledger) | $1,131.51 at REPORTS end; $1,140.77 at PAGES_A fail; **$1,236.14 at PROMOTE**, ceiling $1,500 (was $1,150; start estimate **$20.00**) | — | 8 driver resumes | engine "wall clock 120.4 min (target 120, schedule 98.0) OVER" at REPORTS end | KU8y 17:07:40 "cost $1131.51 (budget $20.00 for 4 pillar(s)) OVER"; CG6Y 05:43:09 "run COMPLETE at $1,236.14 of $1,500" |
| Whole run (session meters) | KU8y `cost_usd 646.14` (12.33M output tokens); CG6Y `cost_usd 82.17` (1.22M output tokens) → **$728.31** across the two sessions | — | — | KU8y ≈27.1 h; CG6Y ≈10.7 h | get_session.usage both sessions |
| PRELIM / enrichment | not stated | Clay Tech Stack + Vibe technographics run in research, **run again** in CG6Y; Clay Open Jobs run in research (E-080) and **again** 04:58 | — | — | CG6Y 05:41:13 "2 scans run twice"; CG6Y 05:43:47 "E-CC-1770..1785 … cited on 24 register rows" |
| RESEARCH | not stated (before window) | not stated | not stated | not stated | KU8y 17:37:03 "[RESEARCH] done — every category gate PASS"; KU8y 16:29:52 "347 of 708 cells are NO_EVIDENCE … Researched 361 of 708"; haiku webSearchRequests 1911 (KU8y 16:43:36) |
| SCORING | not stated | critic rounds not stated | — | — | KU8y 17:37:03 "[SCORING] done — SCORING gate PASS"; KU8y 17:08:00 PR #78 "a scoring critic could loop on rewrites" |
| REPORTS | session meter 432.83→463.60 over the last 46 min (**$30.77**); engine "workflow spend captured: 82 agent(s), $191.74" (cumulative at 16:57) | ≥5 `dma-reports.js` relaunches 16:18–16:43 (each `rounds: 2`); whole-report pass reopened §6, §10, CR§4, §8, CR§5, §8 again; 77 workflow dirs by 16:18 | 3 final sections hand-fixed + 1 validator | 16:17 → 17:07 (≈50 min for the tail alone) | KU8y 16:57:46 "Each final whole-report review has been reopening 1–2 sections it hadn't flagged before"; 16:18:09 "seven sections are back with the writers" |
| PAGES_A (techstack, heatmap, v.A) | engine **$9.26**; session 471.14→478.31 | heatmap SG-V4 17/17 before-after repair; techstack 6/6 | "32 attempts over 30 lanes"; "16 attempts … 15 lanes" in the halted record | 124.5 min / 4068.8 s | KU8y 18:45:53; 18:48:42 "This page attempt cost $9.26 and took about two hours" |
| PAGES_A repair + Clay/Vibe re-scan (CG6Y, before window) | session meter ≤ $47.99 by 04:25 | techstack waiver A 62; heatmap 8 residual | — | 19:04 → 04:25 (incl. weekly-limit stop) | CG6Y 04:25:00 "You've hit your weekly limit"; 05:31:36 waivers |
| PAGES_B (overview, insights, platform) | session 48.77 → 77.64 (**$28.87**) | 18 agents (11 cached, 7 re-run); overview repaired ×2, platform ×1, insights re-shipped ×1 | 7 byte-identical resubmissions across 5 pages | 04:26 → 05:15 (49 min) | CG6Y 05:40:23 "7 byte-identical resubmissions across 5 pages, 2 of them the 3.4 MB heatmap" |
| PAGES_B (context) + PROMOTE | session 77.64 → 84.01 (**$6.37**) | 3 producers + assembler; 1 repair (2 parallel producers) | — | 05:15 → 05:31:03 | CG6Y 05:31:36 "[PROMOTE] PASS … (16.2s)" |
| QA overseer | session 84.01 → 87.19 (**$3.18**) | 15 new findings + 5 sightings | — | 05:34 → 05:43 | CG6Y 05:43:21 |
| Idle goal-hook loop (KU8y) | session 469.96 → 481.62 (**$11.66**) | 57 stop-hook firings, 57 replies | — | 17:33 → 05:42 (≈12 h) | KU8y user "Stop hook feedback: [Please assess B1 Bank…]" ×57 |

---

## Root causes observed (each with session · timestamp)

1. **Reports re-opened by facts that moved under them.** Evidence kept being registered during REPORTS (998 → 1005 rows) so passed sections failed the whole-report pass on figure drift; the fix was to stop registering. — KU8y 16:17:58 ("E-999 to E-1005 were registered after 14:51Z … after this section was written"), 16:18:09 ("I've stopped registering evidence until both reports pass").
2. **Whole-report adversarial pass is not idempotent**: each pass reopened 1–2 sections it had not flagged before; §8 was relaunched twice in 12 minutes (16:31:01, 16:43:30), each relaunch a 2-round workflow. — KU8y 16:57:46, 16:40:37 ("down from four or five per pass earlier").
3. **Concurrent workbook writes lose data**: a review verdict was "re-recorded: the first write was lost to a concurrent workbook write"; `.xlsx.lock` + `.part` files present in the run dir. — KU8y 16:17:58; CG6Y 05:28:36.
4. **Search_Log sequence numbers duplicated** (5470 and 5482 each labelled four queries), forcing report rewrites to disambiguate citations. — KU8y 16:43:24.
5. **Budget model wrong by 60×**: engine budget "$20.00 for 4 pillar(s)" vs $1,131.51 actual; cost report still prints the $20 baseline. Owner-stated drivers: "search services were out of credit and the reports took many review rounds". — KU8y 16:57:39, 17:08:00.
6. **Session-meter vs engine-ledger disagreement**: engine said $1,131.51 while the CCR meter said $463.60 at the same moment; final session meters total $728.31 vs engine $1,236.14; stages "unrecorded: PREFLIGHT, START, CHALLENGE, GATES, RELAY, PACKAGE, INGEST_B, PAGES_B, PROMOTE". — KU8y 17:04:06 vs 17:07:40; 18:45:53.
7. **Connector-origin evidence lost at ingest**: Clay/Vibe scans ran in research but "package ingest stores no connector_tool", so ET-12 refused the techstack page and both scans had to be re-run and re-registered (E-CC-1770..1785); Clay Open Jobs likewise re-run (E-CC-1787). — KU8y 18:48:42; CG6Y 05:41:13 ("2 scans run twice"), 05:43:47.
8. **Connectors not persistent across restarts**: after a container restart Clay listed but uncallable, Vibe absent, background page agents never have Clay/Vibe; raw scan responses were not saved, so the only remedy was a new session. — KU8y 18:48:42, 18:49:02, 18:56:25.
9. **Tool loss on restart**: `Workflow` and `AskUserQuestion` tools disappeared after restarts, forcing `--pages-mode lanes` fallback and preventing the grounding decision from being asked. — KU8y 17:37:17, 18:48:18.
10. **CG-50 mirror drift / short-token skip**: engine preflight searched the vendor phrase ("Holdings") and dropped the 2-char token "Q2"; PAGES_A halted before any agent ran; a page agent then reverted the renamed row. — KU8y 17:07:24, 17:09:43, 18:48:42; CG6Y 05:41:26, 05:41:40.
11. **Unlinked evidence (ET-07) discovered page by page**: techstack ×4 (E-074/075/081/082), overview ×6 (E-028/033/039/1005/048/080), context ×4 (E-023/042/049/068) — "finding them page by page cost three separate repair rounds on this run". — KU8y 18:46:00; CG6Y 04:56:55, 05:28:09, 05:39:09.
12. **SG-V4 grounding gate fails its whole population**: default budget 8; heatmap 17/17 before/after repair (sim 0.336 vs 0.5); every page over budget; owner raised to 257; 620 prose FAILs on promoted pages; two pages promoted with SG-V4 NOT_RUN counted as 0. — KU8y 18:45:45; CG6Y 05:12:23, 05:40:40, 05:40:55.
13. **Driver cannot re-judge without re-shipping**: raising `--sg-v4-budget` did not re-read stored verdicts; pages had to be shipped again unchanged (insights needed a `touch`), "7 byte-identical resubmissions across 5 pages, 2 of them the 3.4 MB heatmap". — CG6Y 05:14:03, 05:40:23.
14. **Local precheck ≠ server verdict**: "All three came back marked repair, so they failed on the server even though they were clean locally" (platform CG-30 ×4). — CG6Y 05:01:36, 05:05:44.
15. **Cross-page drift after evidence repairs**: relinking evidence re-ranked the platform engine (CRM Analytics rank 6→3, fit 43.2→43.3); overview tiles passed the server with stale ranks (CG-31 silent) and needed a second repair. — CG6Y 05:08:59, 05:39:46.
16. **Weekly usage limit killed 7 of 18 page agents mid-workflow**; recovery relied on the workflow cache, no driver-side detection. — CG6Y 04:25:00, 04:26:15, 05:43:09.
17. **Goal hook loop with no work possible**: 57 stop-hook firings over ~12 h each answered by a full model turn (≈$11.66 session meter) while blocked on budget/connectors. — KU8y 17:08:04 → 05:42:16.
18. **Stale "future" dates served as upcoming**: "scheduled for 10 August 2026" restated as future 59 days after the date, in ≥2 sections; fixed by hand. — CG6Y 04:56:55, 05:43:18.
19. **Brief packet ceiling trims verdict reasons** ("5 row(s) dropped to fit the packet ceiling — last_verdict_reasons: 4 item(s) trimmed"), so repair lanes did not see all failing reasons. — KU8y 18:45:45.
20. **Scoring critic feedback path** (memory rows, run attribution not stated): "The scoring critic's FAIL never reached the scorers: the scorer brief served only unscored rows" (MEM-0594); "a scoring critic could loop on rewrites" fixed in PR #78. — CG6Y 05:34:25; KU8y 17:08:00.

Not found in the pages read: any `search_ops`/"against 60" line, any `AT_BUDGET_CEILING` or `CONNECTOR_DRIFT` string, per-category floors-gate failures, research lane/round counts, per-pillar critic rounds, `record_enrichment … NOT_RUN`.
