# Mined evidence — group C: First Tech, Arbor Bank (x2), Susser Bank, workflow audit

Method: `list_events` with `kinds: ["user","assistant","result"]`, 100 raw events per page, paging back with `before_id`. Saved pages parsed with `tools/ingest_C_firsttech.py` into `sessions/<id>.C.jsonl`; small inline pages recorded by hand in `sessions/<id>.C.inline_notes.md`. Session-level totals from `get_session` (`sessions/C_session_metadata.md`). All timestamps UTC. Every number below is quoted from the transcript; "not stated" means the transcript pages read do not contain it. Quotes are verbatim and under 300 chars.

Coverage limits: the First Tech session is ~48 h long; I read its newest ~36 pages (2026-10-07 13:21 → 19:33). Its 10-05/10-06 research, scoring and reports stages were not reached, so RESEARCH/SCORING round counts for First Tech are "not stated" here. The Arbor "DMA run promotion" session's middle is mostly test-suite output; its oldest pages (10-06 14:50 → 10-07 10:16) were not reached.

---

## 1. session_01Hej3inXHC5Rfik9EEMLMMD — "First Tech Credit Union assessment"

- Dates: created 2026-10-05T18:49:33Z, last update 2026-10-07T19:33:54Z (~48.7 h).
- Pages read: 36 (35 saved + 1 inline). Events read: 718 filtered events in JSONL + ~23 inline. Range covered: 2026-10-07T13:21 → 19:33. Run: `6fa6ff19-7016-4e10-9f49-3ddfb2de4940` (version 3; v2 `3f539a31` SUPERSEDED).

### 1.1 Dollar / token / budget lines
- `get_session`: `cost_usd 551.52`, `output_tokens 5,795,600`, `cache_read 1,271,556,747`, `context used_tokens 717,050 / 1,000,000`. Goal recorded: "peer details should be promoted".
- 13:22:27 `result`: `total_cost_usd 182.4259` for the current process; `modelUsage` opus-5-5 `costUSD 170.33`, `outputTokens 990,722`, `thinkingTokens 368,377`, `cacheReadInputTokens 513,648,270`; sonnet-5-5 `costUSD 11.96`, `outputTokens 275,709`; haiku `0.13`. `duration_api_ms 13,408,250` (~3.7 h of API time in this process alone).
- 13:27:33 → 13:27:42: three consecutive idle turns answering scheduled-routine notifications; `total_cost_usd` 182.67 → 182.75 → 182.83 (~$0.08 per idle turn). Assistant: "Another scheduled-routine notification arrived. I can't open it from this session, so I haven't acted on it… These notifications will keep coming until the routines are paused or deleted".
- Per-stage $ for RESEARCH / SCORING / REPORTS: not stated in the pages read (the $551.52 session total vs the ~$182 process total implies at least one earlier process/resume carrying the rest; the split is not stated).

### 1.2 RESEARCH
- Not reached in the pages read. No `engine.cost report` row for First Tech RESEARCH was found. Connector NOT_RUN: not stated.

### 1.3 SCORING critic rounds
- Not stated (stage not reached in the pages read).

### 1.4 REPORTS rounds / REVISE
- Not stated for this run.

### 1.5 PAGES / PROMOTE
- 13:22:09 tool output: `pages {'heatmap': ('PASS', '2026-10-07T12:34:29'), 'overview': ('PASS', …), 'insights': …, 'platform': …, 'context': …, 'techstack': ('PASS', '2026-10-07T12:34:29')}` — all six promoted together 12:34:29 after submissions 12:30–12:34.
- Earlier in the day (inline notes): heatmap passed pass-1 clean then was refused at pass-2 on `CG-14, CG-10, CG-48, ET-09, AG-01, AG-03`; platform refused on `ET-07` (JSONB key order). Retry counts per page: not stated as a number.
- 14:33:15 USER: "Heatmaps not fully promoted". 14:37:25 USER: "Got it wrong. It is the customer view that lacks heatmap details for most clients". 14:37:43 USER: "Fix the evidence drawer too". 14:38:00 USER: "Ensure no recurrence of above issues in future runs".
- 15:19–15:24: heatmap and techstack re-shipped (CG-52 customer-text repair; "63 of 619 drawers rewritten"); `promote_run` True 15:25:01 — pages redone at the end of the run, after the 12:34 promotion.
- 18:52:53 USER: "Yes, repair Susser and Arbor heatmaps and repromote. Repair all please. Still, under the customer view, I do not see the First Tech value chain heatmap". 18:53:19 USER: "Also, the value chain cells are not clickable". Arbor and Susser heatmaps re-promoted 18:58 (CG-52) from this session.
- Other repair work in the same session: T. Rowe Price heatmap 67 pass-2 blocks (`CG-10 x55, ET-10 x6, ET-11 x5, ET-01 x1`); Golden 1 105 issues. A CI deploy was "cancelled by another session's PR #74 merge"; plugin version lived "in three places".
- CONNECTOR_DRIFT: not stated in this session.

### 1.6 ENRICHMENT
- 13:22:09: `enrichment {'current': 7, 'enriched_not_promoted': 0, 'never_enriched': 0} done True`. Clay / Vibe / Indeed repeat calls: not stated in the pages read.

### 1.7 Complaints and diagnoses
- See 1.5 for the five user complaints (14:33–18:53). Assistant diagnosis 13:22:25: "Three items are recorded on the pages as not established, because no usable source could be found: BECU's and Patelco's core banking platforms, and Golden 1's core."

### 1.8 Wall-clock
- Session 48.7 h end to end; pages promoted 10-07 12:34; customer-view heatmap repair 15:25; cross-client heatmap re-promotes 18:58; last event 19:33. Stage-level wall-clock: not stated.

---

## 2. session_01AUbGyUGhv2mxoYbie22JHi — "Arbor Bank promotion"

- Dates: 2026-10-06T07:47:43Z → 16:27:57Z (~8.7 h). Pages read: 27. Events read: 626. Range covered: 10-06 ~11:00 → 16:27 (07:47–11:00 not reached). Run `arbor-bank-2026-10-05`, connector run `651c85bc…`.

### 2.1 Dollar / token / budget
- `get_session`: `cost_usd 58.10`, `output 441,366` (this session's own spend; the run's spend below is the engine's ledger).
- 12:12:43 `engine.cost report`: "REPORTS 416.3m 25.0 +391.3 (116 attempts over 114 lanes) | wall clock 809.1 min (target 120, schedule 98.0) OVER | cost $372.26". Ceiling raised $400 → $475 in this session.
- 12:59:20: "PAGES_A 34.5m … $382.86".
- 14:48:23 resume prompt: "Budget: $382.86 spent of … $475"; "708/708 scored, composite 1.08, peer cohort N=3 recorded in 10 of 16 categories".
- 12:42:37 code comment committed: "Measured 2026-10-05 (Susser Bank): scoring as headless lanes took 294 min behind one all-pillar critic and a barrier".

### 2.2 RESEARCH
- Cost-report RESEARCH row: not stated in the pages read. 13:24:12 assistant: "568 of 708 cells have no evidence"; "106 of the 166 cell write-ups are quote-stitching" (research output quality, driving later REPORTS/PAGES churn).
- Lock/overwrite: 13:18:20 "The lane took it under its own id and locked the driver out for two hours".
- Connectors: Clay/Vibe lost after a worker restart; assistant: "your reconnect doesn't reach this session". 13:21:44 USER: "1) Reconnected 2) No. Are the duplicated cell write-ups similar… Ensure no future recurrence… 3) Find the root cause and fix to ensure that it never recurs again."

### 2.3 SCORING
- "One scorer reported a re-score it never saved." (12:42:37 commit text). Critic round count for Arbor: not stated. Susser measurement quoted above: 294 min.

### 2.4 REPORTS
- 13:18:20 assistant: "Why the reports took so long… 430 minutes, 19 rounds and 137 validator reviews, with 19 sections reopened after they had passed. Whole reports went through each round together… Over a third of the returns asked for things a writer can't do".
- Report lengths: "10,346 / 20,443 words vs maxima ~5,000 / 14,900" — "Nothing enforced the maximums".
- 12:40:42 USER: "The above is taking longer than expected for just a few remainder sections of the reports. Look into how this may never recur and employ /workflows and /agents".

### 2.5 PAGES / PROMOTE
- 13:05:50: "[PAGES_A] FAIL — page(s) not passing on version A after 3 attempt(s): techstack ET-12". Heatmap: "CG-15 40 refusals" (vacuity / quote-scaffold).
- 14:09:07 USER: "Fix the 18 failing tests and build the heatmap check".
- Promote outcome in this session: pages at PAGES_A FAIL; promotion completed later in the follow-on session (§4). CONNECTOR_DRIFT: not stated in this session.

### 2.6 ENRICHMENT
- Clay/Vibe connectors dropped mid-run (worker restart) and had to be reconnected by the owner (13:21:44 "1) Reconnected"). Repeat scan counts: not stated.

### 2.7 Complaints / diagnoses
- Complaints: 12:40:42, 13:21:44, 14:09:07 (quoted above). Diagnoses: 13:18:20 (reports: whole-report rounds, impossible asks, lane lock-out); 13:24:12 (quote-stitching; 568/708 cells unevidenced).

### 2.8 Wall-clock
- REPORTS 416.3 min vs 25 target; run wall clock 809.1 min vs 120 target (12:12:43). PAGES_A 34.5 min (12:59:20). Session 8.7 h.

---

## 3. session_0119jwbbvbe6our3B8DqJcnH — "Susser Bank promotion"

- Dates: 2026-10-06T07:48:07Z → 14:27:45Z (~6.7 h). Pages read: 27 (+inline notes). Events read: 666. Range: 10-06 ~09:15 → 14:27. Run `susser-bank-2026-10-05`.

### 3.1 Dollar / token / budget
- `get_session`: `cost_usd 80.80`, `output 667,312`, context used 773,108; status "report budget exhausted ($508.74/$510); 2 sections held on validator flags".
- 09:41:34 `engine.cost report`: "REPORTS 673.7m 25.0 +648.7 (230 attempts over 228 lanes) | cost $473.10 (budget $20.00 for 4 pillar(s)) OVER".
- Drivers driver49..driver52 launched with `--max-usd 510 --max-wall-min 120/90/60 --lane-retries 1/0`; spend readings in order: $485.04 → $489.74 → $497.02 → $498.73 → $508.74.
- 14:27:43 assistant: "pages are live… $510 report budget… run out ($508.74 spent)".
- 14:20:02 assistant: "The Assessment Report has 4 sections in a final round, capped at the remaining ~$11 of the $510 budget."

### 3.2 RESEARCH
- RESEARCH cost row: not stated in pages read. Tech register: rows "TS-009..TS-015 and TS-017 are still CLAIMED on Clay scan-only detections (E-144/E-145/E-175)" (09:41:34 validator note). Connector NOT_RUN: not stated.

### 3.3 SCORING
- Alkami `ScoringRefusal` appears in tests; critic rounds for Susser: not stated. (Arbor session's commit text measured Susser scoring at 294 min — §2.1.)

### 3.4 REPORTS rounds / REVISE reasons
- Stall rule hits: "stopped at round 6/5/4: the last 2 round(s) advanced nothing" (three drivers). §5 REVISE stuck; §6 UNREVIEWED at 4,646 words. Report sizes 13,301 / 3,050 and 28,562 / 8,400 words (actual / maximum).
- 09:41:34 validator verdict (client_research §2, §5; assessment §5), identical text: "REVISE, UPSTREAM-BLOCKED… The section and Tech_Register are both UNCHANGED since the 09:30/09:34 verdicts: no rewrite, and TS-009..TS-015 and TS-017 are still CLAIMED on Clay scan-only detections… (1) regrade TS-009..TS-015 and TS-017 to INFERRED (owner rule 2026-10-05: a scan-only row stays INFERRED)".
- 11:45:43 code docstring: "TS-016 held Salesforce as a broker-only claim… Every report section that read the register inherited the error, the validator reopened eight sections on it, and seven report rounds were spent on a fact no report writer may change."
- 14:20:02: "REPORTS still sends sections one round at a time through the driver. Each round writes, then validates, then reopens whatever the whole-report pass catches. That loop is where the two hours went: 230 lanes over this run."

### 3.5 PAGES / PROMOTE
- Overview pre-submit refusals 14:16–14:17: `CG-27 x3`, `CG-12 x3`. Promoted: "All six pages are live as of 2026-10-06 14:19:44 UTC" (14:20:02). 14:20:02: "I put the pages behind the report rewrite when they never depended on it. Once I shipped them directly, they went out in minutes."
- CONNECTOR_DRIFT: not stated.

### 3.6 ENRICHMENT
- Clay scan-only rows mis-graded CLAIMED (TS-009..TS-015, TS-017) → reports churn (§3.4). Register after fix: "5 CONFIRMED · 10 INFERRED · 2 CLAIMED" (14:20:02). Repeat Clay/Vibe/Indeed calls: not stated.

### 3.7 Complaints / diagnoses
- 14:13:35 USER: "The report has gone on for over 2 hours and no page promotion has began. Still, I see that the report round does not use /workflows". 14:14:05 USER: "I expected the following to be done in less than 1 hour."
- Diagnosis 14:20:02 (quoted in 3.4/3.5); 11:45:43 (register contradiction reopened eight sections for seven rounds).

### 3.8 Wall-clock
- REPORTS 673.7 min vs 25 target (09:41:34). Pages live 14:19:44, ~6.5 h after session start. Session 6.7 h.

---

## 4. session_01Wg1pNZua4rtrB8hDt4VBoN — "Arbor Bank DMA run promotion"

- Dates: 2026-10-06T14:50:34Z → 2026-10-07T14:11:01Z (~23.3 h). Model switched to claude-fable-5-1 (configured opus-5-5). Pages read: 35. Events read: 392 (most pages were test-suite notifications). Range: 10-07 10:16 → 14:11; the 10-06 14:50 → 10-07 10:16 span was not reached.

### 4.1 Dollar / token / budget
- `get_session`: `cost_usd 138.19`, `output 951,723`; summary "($409.10/$475 budget used)". Owner goal verbatim: "audit the repo and fix all issues I raised on this chat; ensure all root causes are fixed… Do not assume, audit."
- 12:43:40 assistant: "Arbor's reports still lead with integration and need a budgeted regeneration ($409.10 spent of $475 — your call)".
- 12:43:40 row 7: "`$475` ceiling forgotten on resume | `--max-usd` not given → per-pillar $20 default | `budget_usd_source: flag` remembered across resumes".
- Elsewhere in the session: "$570 later, in a resumed session that no longer held Clay or Vibe" (assistant narrative of the Arbor run; exact timestamp in JSONL extract).
- 10:19:19 docs text: "`--max-usd` is $5 per pillar in scope and STOPS the run; `--max-rounds 10`; `--stall-rounds 2` ends a stage after two rounds that advance nothing".

### 4.2 RESEARCH
- 12:30:16 ledger: `{'search_ops': 6332, 'search_ops_since_checkpoint': 59, 'window_scope': 'PRELIM'}`; per-category since-checkpoint PRELIM 59, RELAY 30, P4C3 11. 12:43:40 row 6: "Hook said 'AT_BUDGET_CEILING … 6332 against 60' on a promoted run | stats() … printed the lifetime count against a per-conversation ceiling".
- 12:48:00 Gate_Log counts: `('FLOORS', 212), ('SCORING_CRITIC', 46), ('GS', 28), ('SCORING', 23), ('TEMPLATE', 20), ('STAGE_RESEARCH', 15), ('STAGE_PAGES_B', 9), ('SG_V4_BUDGET_RAISED', 8), ('STAGE_PAGES_A', 6), ('STAGE_SCORING', 4), ('FLOORS_WAIVER', 4), ('TECH_REGISTER_RECONCILE', 4)`.
- Evidence origin: `Counter({'public': 245, 'connector': 6, 'client': 1})`; technographic providers: `{'clay': 6, 'explorium': 4, 'indeed': 0, 'exa': 0, 'tavily': 0, 'web': 6 …}`.
- 12:43:40 row 8: "Own-site pages filed T1; no re-tier command". Row 12: "Search_Log seq 6250-6253 reused … `len(rows)`".

### 4.3 SCORING
- Gate_Log `SCORING_CRITIC 46` rows vs `SCORING 23` and `STAGE_SCORING 4` (12:48:00). Rounds per pillar: not stated. "Arbor Bank served one cohort cell in six" (assistant narrative).

### 4.4 REPORTS
- 14:10:37 table: "Overview produced over 16 placeholder peers"; "Connector redeployed mid-run; pages refused and reports stale" → `CONNECTOR_DRIFT` logging added. Report regeneration deferred for budget (§4.1). Round counts for this session's REPORTS: not stated.

### 4.5 PAGES / PROMOTE
- 12:43:40 row 3: "SG-V4 noise (789 FAILs on the heatmap) | pass-2 collector bypassed `_V4_SKIP_KEYS`". Row 4: "Heatmap repair promoted from stale staged copy | `_page_ok` returned True when no ship time was recorded". Row 5: "Promote FK failure (232 rows remapped by hand) | writer bound package-local `e_id` verbatim". Row 10: "AG-01 `WITHDRAWN` cost a server round trip".
- 14:10:37: `CG-04 / CG-46 / AG-01 / AG-03` refusals "one submit round at a time" → `section_precheck.py` PostToolUse hook; `CG-18c` held the CL set.
- 12:43:48 Stop hook: "STAGE ADVANCE — run arbor-bank-2026-10-05 (Arbor Bank) is at PACKAGE_UNSHIPPED: both reports READY and the client folder's manifest is not COMPLETE". Promote outcome: pages promoted earlier (First Tech session confirms Arbor heatmap live and re-promoted 10-07 18:58).

### 4.6 ENRICHMENT
- `providers_never_run: []`, `broker_rows: 6` (12:48:00). Session narrative: a resumed session "no longer held Clay or Vibe". Repeat counts: not stated.

### 4.7 Complaints / diagnoses
- Owner quote in commit "Prevention over repair": "It is not about adding tests… I want preventive measures, hooks" (2026-10-07). 12:43:40: 12-row root-cause table (quoted in part above). 14:10:37: prevention table (PRELIM gates sub-vertical firmographics; REPORTS runs enforcement sweep; PAGES preflight refills cohort peers; CONNECTOR_DRIFT).

### 4.8 Wall-clock
- Session 23.3 h; engine test shards 28–64 min each (four shards, 10:19 → 13:53). Stage wall-clock for the Arbor run: see §2.8 (809.1 min at 12:12 on 10-06).

---

## 5. session_01VRjqoEQCQEHSSo3LvuasEf — "Research to assessment workflow audit"

- Dates: 2026-10-07T09:50:39Z → 12:23:10Z (~2.5 h). Pages read: 26 (complete). Events read: 559. Output: PR #66 "Nothing is done twice".

### 5.1 Dollar / token / budget
- `get_session`: `cost_usd 32.11`, `output 183,046`.
- Owner goal verbatim: "There has been a lot of issues on redoing research, redoing scoring, synthesis, critics, page production leading to a lot of token consumption. Ensure the entire flow is enforced and predictable such that the level of repetition reduces unless totally necessary."
- Code comments quoted by the audit (historic measurements, dates as stated in the comments): "seven rounds scored 57 of 708 cells at ~$44"; "$96.65 spent against a $20 four-pillar budget" (2026-09-12); "driver read $38 against a $110 ceiling while the session had spent more"; "Round 3 was handed with 0 batches, a $6.16 estimate (it cost ~$21)"; "One research round… was ~$83 against a $20 four-pillar budget when that ceiling was 200… ceiling is 340 now"; "goeasy was at 567 ops, 1425% of the cap"; "one batch agent closed 12 cells for ~$2.25; its category's challenge ~$0.44".

### 5.2–5.5 Redo paths found (subagent hand-backs 09:59:03 / 10:00:40; synthesis 11:31:15)
- RESEARCH: `append_synthesis` clears the verdict with no content hash (identical re-synthesis re-verdicted); "shared 60-search window per category reset by sibling batches"; "open cells in both capability and repair batches" (double dispatch).
- SCORING: `score()` "identical re-score not refused"; `critique()` "keeps no sample record, nothing limits `--move`" (critic can keep moving scores round after round).
- REPORTS: `write()` "clears verdict on every rewrite"; repair briefs "trimmed reasons 12→6→3" (writer never sees the full reason list).
- PAGES: watchdog "AWAITING_WORKFLOW after 15 min idle → Stop hook restarts same workflow (double spend)".
- Stress-walk result: "dispatched three times at most, not ten"; "`--max-wall-min` defaults to 240".
- "ten redo paths" closed in PR #66 (workflow_inflight hook + verdict repair; 2,018 tests pass).

### 5.6 ENRICHMENT — not examined in this session beyond the connector-window finding.
### 5.7 Complaints — the goal statement above. ### 5.8 Wall-clock — 2.5 h.

---

## Cross-session quantitative table

| Session | Stage | Cost $ | Rounds | Retries / lanes | Wall-clock | Source quote (session, time) |
|---|---|---|---|---|---|---|
| Susser (0119jwbb) | REPORTS | $473.10 at 09:41 → $508.74 of $510 at 14:27 (budget line "$20.00 for 4 pillar(s)") | stopped at round 6 / 5 / 4 across three drivers | 230 attempts over 228 lanes | 673.7 min vs 25 target | "REPORTS 673.7m 25.0 +648.7 (230 attempts over 228 lanes) \| cost $473.10 (budget $20.00 for 4 pillar(s)) OVER" (09:41:34) |
| Susser | REPORTS (register contradiction) | not stated | 7 rounds, 8 sections reopened | — | — | "the validator reopened eight sections on it, and seven report rounds were spent on a fact no report writer may change" (11:45:43) |
| Susser | PAGES | not stated | — | CG-27 x3, CG-12 x3 overview refusals | pages live 14:19:44 (~6.5 h after start) | "Once I shipped them directly, they went out in minutes." (14:20:02) |
| Susser | SCORING | not stated | 1 all-pillar critic | — | 294 min | "scoring as headless lanes took 294 min behind one all-pillar critic and a barrier" (Arbor promo 12:42:37) |
| Arbor promo (01AUbGyU) | REPORTS | $372.26 at 12:12 (run total) | 19 rounds, 137 validator reviews, 19 sections reopened after pass | 116 attempts / 114 lanes | 416.3 min vs 25 (430 min per 13:18) ; run 809.1 min vs 120 | "REPORTS 416.3m 25.0 +391.3 (116 attempts over 114 lanes) \| wall clock 809.1 min (target 120…) OVER \| cost $372.26" (12:12:43) |
| Arbor promo | PAGES_A | $382.86 run total at 12:59 | — | 3 attempts, FAIL techstack ET-12; heatmap CG-15 x40 | 34.5 min | "[PAGES_A] FAIL — page(s) not passing on version A after 3 attempt(s): techstack ET-12" (13:05:50) |
| Arbor promo | RESEARCH (lane lock) | not stated | — | — | 2 h lost | "The lane took it under its own id and locked the driver out for two hours" (13:18:20) |
| Arbor DMA (01Wg1pNZ) | whole run | $409.10 of $475 ceiling ("$570 later" narrative) | Gate_Log SCORING_CRITIC 46, FLOORS 212, SG_V4_BUDGET_RAISED 8 | SG-V4 789 heatmap FAILs; 232 FK rows remapped by hand | session 23.3 h | "($409.10 spent of $475 — your call)" (12:43:40) |
| Arbor DMA | RESEARCH (search ledger) | — | — | 6332 lifetime ops vs 60/window | — | "'AT_BUDGET_CEILING … 6332 against 60' on a promoted run" (12:43:40) |
| First Tech (01Hej3in) | whole session | $551.52 session; $182.43 current process (opus $170.33, 990,722 output tok) | not stated | heatmap pass-2 refusals CG-14/CG-10/CG-48/ET-09/AG-01/AG-03; platform ET-07 | 48.7 h session; pages 12:34, redone 15:25, cross-client re-promote 18:58 | "pages … ('PASS', '2026-10-07T12:34:29')" (13:22:09); "cost_usd 551.52" (get_session) |
| First Tech | idle routine turns | ~$0.08 each | 3 turns in 10 s | — | — | "Another scheduled-routine notification arrived. I can't open it from this session" (13:27:33) |
| Audit (01VRjqoE) | historic SCORING | ~$44 for 57/708 cells | 7 rounds | — | — | "seven rounds scored 57 of 708 cells at ~$44" (code comment, 09:59–11:31) |
| Audit | historic RESEARCH | ~$83 one round; $96.65 vs $20 budget | 1 round | — | — | "One research round… was ~$83 against a $20 four-pillar budget" |
| Audit | session | $32.11 | — | — | 2.5 h | get_session |
| Arbor/Susser promos | sessions | $58.10 / $80.80 | — | — | 8.7 h / 6.7 h | get_session |

---

## Root causes observed (each with session + timestamp)

1. **REPORTS runs whole reports through every round, one lane per section-round, with no parallel workflow** — 230 lanes (Susser 0119jwbb 09:41:34, 14:20:02); 116 lanes / 19 rounds / 137 reviews (Arbor 01AUbGyU 12:12:43, 13:18:20). Owner: "the report round does not use /workflows" (Susser 14:13:35).
2. **Validator reopens passed sections and asks for things a writer cannot change** — "19 sections reopened after they had passed… Over a third of the returns asked for things a writer can't do" (Arbor 01AUbGyU 13:18:20); "seven report rounds were spent on a fact no report writer may change" (Susser 11:45:43). Repair briefs "trimmed reasons 12→6→3" (Audit 01VRjqoE 09:59–10:00).
3. **Upstream data defect propagates into REPORTS instead of being fixed at source** — Clay scan-only rows graded CLAIMED (TS-009..TS-015, TS-017), 8 sections reopened (Susser 09:41:34, 11:45:43); 16 placeholder peers in Overview, peer_median written by nobody (Arbor DMA 01Wg1pNZ 12:43:40 row 2, 14:10:37).
4. **Report length unenforced** — 10,346/20,443 words vs ~5,000/14,900 maxima, "Nothing enforced the maximums" (Arbor 01AUbGyU 13:18:20); 28,562 vs 8,400 (Susser).
5. **Pages serialized behind reports although independent** — "I put the pages behind the report rewrite when they never depended on it" (Susser 14:20:02).
6. **Budget ceilings not remembered or mis-read** — "$475 ceiling forgotten on resume… per-pillar $20 default" (Arbor DMA 12:43:40 row 7); "driver read $38 against a $110 ceiling while the session had spent more" and "Round 3 … $6.16 estimate (it cost ~$21)" (Audit); search ledger reported lifetime 6332 vs per-window 60 (Arbor DMA 12:30:16, 12:43:40 row 6).
7. **Redo paths with no idempotency** — `append_synthesis`/`write()` clear verdicts without content hash, `score()` accepts identical re-score, `critique()` unbounded `--move`, watchdog restarts the same workflow after 15 min idle (Audit 01VRjqoE 09:59:03, 10:00:40, 11:31:15); "One scorer reported a re-score it never saved" (Arbor 01AUbGyU 12:42:37).
8. **Scoring critic serialized behind one all-pillar critic and a barrier** — 294 min (Arbor 01AUbGyU 12:42:37); Gate_Log SCORING_CRITIC 46 vs SCORING 23 (Arbor DMA 12:48:00); "seven rounds scored 57 of 708 cells at ~$44" (Audit).
9. **Lane/driver lock contention** — "locked the driver out for two hours" (Arbor 01AUbGyU 13:18:20).
10. **Pass-2 gates discovered only after pass-1 passes, one submit round each** — CG-04/CG-46/AG-01/AG-03 (Arbor DMA 14:10:37); CG-14/CG-10/CG-48/ET-09/AG-01/AG-03 heatmap, ET-07 platform (First Tech 01Hej3in, 10-07 morning); SG-V4 789 heatmap FAILs from skip-key bypass (Arbor DMA 12:43:40 row 3); "AG-01 WITHDRAWN cost a server round trip" (row 10).
11. **Pages redone after promotion for customer-view defects** — CG-52 repair 63/619 drawers, re-promote 15:25; Susser/Arbor heatmaps re-promoted 18:58 (First Tech 14:33–18:58). Heatmap repair once promoted from a stale staged copy (`_page_ok` with no ship time; Arbor DMA 12:43:40 row 4).
12. **Connector loss / drift mid-run** — Clay/Vibe lost after worker restart, "your reconnect doesn't reach this session" (Arbor 01AUbGyU 13:21:44 context); "$570 later, in a resumed session that no longer held Clay or Vibe"; "Connector redeployed mid-run; pages refused and reports stale" → CONNECTOR_DRIFT (Arbor DMA 14:10:37); ET-12 technographic FAIL after 3 attempts (Arbor 01AUbGyU 13:05:50).
13. **Thin research feeding downstream churn** — "568 of 708 cells have no evidence", "106 of the 166 cell write-ups are quote-stitching" (Arbor 01AUbGyU 13:24:12); heatmap CG-15 x40.
14. **Manual repair of promote mechanics** — 232 FK rows remapped by hand; Search_Log seq reused; verdict files truncated at 40 (Arbor DMA 12:43:40 rows 5, 12).
15. **Idle spend** — scheduled-routine notifications each cost a turn (~$0.08) with no action possible (First Tech 13:27:33–13:27:42).
