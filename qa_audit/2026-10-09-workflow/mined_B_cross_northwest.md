# Mined transcripts — Cross Insurance Agency / Northwest Bank / plugin QA (set B)

Method: `list_events` kinds `user, assistant, result`, limit 100, paged back by `before_id` = previous `first_id`. Saved result files parsed with a private script (`tools_B/parse_page.py`, `python3 -I`) into `sessions/<id>.jsonl`; inline (non-saved) pages transcribed to `notes_inline.md`. 37–38 pages requested per long session (cap 40). Session totals (cost, tokens, dates) come from `get_session`; per-turn `total_cost_usd` from `result` events. All times UTC. "not stated" = not found in the pages read.

Caveat on two sessions: `session_014a` (Northwest assessment) and the early part of `session_018b` (Cross assessment) return almost only `stream_event` rows, so 30+ consecutive filtered pages came back empty; only their newest turns were recoverable.

---

## 1. session_01GnAywuQ7qBMfAUawo38DfR — "Plugin DMA quality assurance" (SWBC QA session 2)

- Dates: 2026-10-01T00:50:32 → 2026-10-01T16:24:57. get_session: cost_usd **105.27**; input 2,207,671 / output 2,383,961 / cache_read 218,768,515. Status `need_input`: "decide: (1) Tavily/Exa top-up or switch to Firecrawl? (2) Raise budget cap to ~$380? (3) Allow 'not publicly available' for private-company financials?"
- Pages read: 38 (last first_id 04685deb-1452-4b7d-8b95-f5023bbbf7eb, has_more true). Events parsed: 458 (plus inline pages).
- What the session did: restored run `DMA-RES-SWBC-20260930-0001` (760 cells, HYBRID) and drove it with `/run-assessment`; launched the 16 per-category research workflows in one message.

**Budget / cost figures**
- 01:25:23 driver stdout: "(workflow spend captured: 37 agent(s), $111.12)"; "[RESEARCH] PENDING_ORCHESTRATOR — workflow: 16 categories, 77 batch(es) over 16 category workflow(s), est $140.61 for 703 open cells".
- 01:25:29 thinking: "Spend hit $111.12 for 37 agents closing 33 cells in ~14 minutes — $3.37/cell, 18× the $0.19/cell estimate".
- 01:25:35 tool result: "agents 37 turns 2476 {'in': 4952, 'cw': 19690995, 'cr': 297898484, 'out': 229871}"; per-agent rows show 86–105 turns each (e.g. "(101, …, 'P4C3 r1 b2 P4C3.4', '01:12:14', '01:21:53')").
- 01:2x thinking: "spend is now $197.85 of $260".
- CASE_FACTS I-79 (01:33:41): "37 agents, 2,476 turns, ~120K context/turn (298M cache-read, 19.7M cache-write) = $111.12 for 33 cells closed ($3.37/cell, 18x the $0.19 estimate). Agents ran 86-105 turns each retrying spent channels … workflow `agent()` has no maxTurns".
- Session result events: 03:28:03 total_cost_usd 89.67 (351 turns, 9,397 s); 04:19:32 90.58; 08:21:08 95.55; 12:23:38 100.53; 16:24:57 105.52.

**RESEARCH stage**
- 01:22:47 progress probe: `{"evidence_rows": 434, "searches": 2852, "synthesised": 57, "declared_absent": 31, "gate_open_cells": 708, "tools": {"web_search": 1497, "tavily": 1145, "exa": 84, "clay": 63, "internal": 41, "indeed": 13, "explorium": 4, "web_fetch": 3}}`.
- 01:23:11 thinking: "WebSearch's session-wide 200-query cap is exhausted, and both Tavily and Exa have hit usage/credit limits, so searches are now failing across the board. I'm stopping all 16 workflows to avoid wasting spend"; 01:23:12–17 TaskStop on all 16 workflow tasks.
- CASE_FACTS I-78 (01:33:41): "all 31 agents shared ONE WebSearch budget (`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION`, default 200) — spent in ~10 min — while Tavily hit its plan limit (HTTP 432 after 273 searches + 85 extracts) and Exa was out of credits (402). Research owed >=470 searches at capability grain".
- I-81 (02:03:16): "79 connector Search_Log rows (63 Tavily, 13 Exa, 3 Clay) record calls that never ran ("HTTP 402 credits exhausted" …) yet counted as fired volleys AND enrichment effort".
- Rounds: one research round (r1) per category reached; floors gate never passed for any category. PR body (01:53:09): "SCORING, REPORTS, PAGES, PACKAGE and PROMOTE were never reached … (0 of 16)" (from summary of page 12; stage names verbatim in PR).
- Connector NOT_RUN: Exa/Tavily/Firecrawl exhausted; "Live channel probe 01:3xZ: Tavily 432 (standing), Exa 402, WebSearch 200/200 this session" (01:33 CASE_FACTS).

**SCORING / REPORTS / PAGES / PROMOTE**: not reached live. Critic rounds: not stated. REVISE rounds: not stated. Promote: not attempted.

**ENRICHMENT**: PRELIM passed; I-83 (02:03:16): "PRELIM closed with Financial_Trends = 2 metrics … the PACKAGE gold gate needs >=3 metrics x 5 years. The refusal would surface only after research, scoring, reports and pages were paid for."

**Other root causes recorded**: I-73 (resume hint repeats the command that just refused, no `--max-usd`, "so following it loops"); I-63 ("an hourly Routine for superseded run 9fcee059 was still enabled and relaunching lane batches two weeks later", test docstring 01:38); I-71 (card never asked for the primary volley 391 cells were blocked on).

**Wall-clock**: fan-out ~10–14 min before stop (01:12 → 01:23); session active 00:50 → 03:28 then routine check-ins to 16:24. Full engine suite "1,878 passed, 6 skipped" in 2,036 s (03:21:51).

---

## 2. session_012FRYYbk6Z7t79EvsAba63a — "Cross Insurance Agency DMA QA"

- Dates: 2026-10-01T03:29:15 → 05:40:41 (2 h 11 m). get_session: cost_usd **98.87**; input 2,457,616 / output 1,711,339 / cache_read 242,627,869; effort xhigh. Status `review_ready`.
- Pages read: 38 (last first_id 535c289c-31db-498c-af6e-415ca7366402, has_more true). Events parsed: 424.
- Ran its own Cross research fan-out: run `DMA-CROSS-20261001`, root `/home/user/dma-runs/cross`, 694 cells.

**Budget / cost**
- Driver command (04:xx): `engine.pipeline run --run DMA-CROSS-20261001 --root /home/user/dma-runs/cross --max-wall-min 240 --lane-retries 1 --page-retries 2 --max-usd 210`.
- CASE_FACTS live-run notes (04:12:03): "03:38Z driver started (--max-usd 210). PREFLIGHT, START done. PRELIM: 2 headless lanes … + 1 orchestrator brief serviced in-session".
- C-27 (04:12:03): "attempt 1 spent the whole budget in ~10 min" (fix: env=4000).
- Result events: 04:28:58 total_cost_usd 80.43 (300 turns, 3,569 s); 04:49:45 83.58; 04:59:27 84.78 (modelUsage haiku 5.08 / 226 web searches, opus 35.90, sonnet 43.79); 05:21:10 96.99; 05:40:41 99.01.
- Dollar spend of the Cross research itself: not stated separately from the session total.

**RESEARCH**
- Pilot: "~04:33Z PILOT: 4 workflows (P1C3, P2C4, P3C4, P4C4) = 8 concurrent agents" then 12 more; "PILOT measured (~6 min, 8 agents): 0 source reads (was 17%) … Closures early = absences (P3C4 23, P4C4 10, P2C4 9)".
- 04:11:50 Monitor: "closed=64 absent=56 evidence=51 searches=600"; 04:12:36: "closed=86 absent=74 evidence=55 searches=801"; 04:13:22: "closed=89 absent=77 evidence=55 searches=833".
- 04:12:06: "64 cells closed (8 synthesised with evidence, 56 absences)".
- 04:12:12: "Tavily returned 80 rate-limits and 37 other errors against 88 successes" (04:12:17: the 37 are HTTP 432 "exceeds your plan's set usage limit"). Pilot tally: "Firecrawl 402: 23, Firecrawl 429: 34, Firecrawl ok: 9, Tavily 429: 27, Tavily ok: 185, WebSearch ok: 89".
- 04:12:38 thinking: "Tavily has now also hit its limit (432), meaning Exa, Firecrawl, Tavily, and WebSearch are all unavailable".
- Doctor WARN (04:11:31): "200 WebSearch calls per session … A FULL run's research workflows share it and need ~1,000+; once spent, every agent falls back to Tavily alone". Docstring (04:11:16): "Claude Code's default of 200 was spent in ten minutes of a 694-cell run."
- Floors-gate failures: C-25 "14/14 refused absences in the pilot"; C-30 (05:20:43): "62 of 77 Cross absences re-opened (P3C4: 18 of 29), P3C4 gate now FAIL [absence_unpinned]" — absences declared on unquoted "Cross Insurance Agency" queries that "returned A.T. Cross pens and CBP 'CROSS' rulings; P3C4 had passed with 0/29".
- Connector NOT_RUN / failures: C-23 "Firecrawl 402, Exa 402, Tavily only"; C-24 "failed connector calls counted as volleys".
- Context blow-up: C-21 "34.2 KB of additionalContext (background and connectors repeated 16x)"; C-26 "~6.6 KB per batch echoed into context".

**SCORING / REPORTS / PAGES / PROMOTE**: not reached on the live Cross run (research stalled). Critic rounds: not stated. REVISE: not stated. Stub lifecycle walk only ("Stress lifecycle walk freezes three peers … C-13 floor refuses", 04:59:27).

**ENRICHMENT**: C-22 "Tech_Register after PRELIM: Office 365, Smartsheet … DATA ABSENT — no agency management system (the prior package found dual AMS360 + Applied Epic) … The scanner lane had no connector (C-07) and 12 turns"; Clay live probe found two executives "PRELIM leadership missed".

**User complaint**: 05:12:28 "Please fix all issues."

**Wall-clock**: driver 03:38Z → research stopped ~04:13Z (~35 min); session 2 h 11 m; full engine suite "1,871 passed" ~28 min.

---

## 3. session_01Uraijj9zGqwKH6coaSkcSa — "Northwest Bank DMA QA"

- Dates: 2026-10-01T03:30:54 → 09:35:04. get_session: cost_usd **180.69**; input 2,479,590 / output 4,418,677 / cache_read 432,256,232; effort xhigh. Status `completed` "PR #51 checks pass (18/18)".
- Pages read: 38 (last first_id 1c88163a-8f4a-40e5-8ae9-071d89954763, has_more true). Events parsed: 412.
- Ran its own Northwest fan-out: run `nwbi-2026-10-01`, 729 cells, "$200 ceiling set by the owner" (PR body 04:41:01).

**Budget / cost**
- 04:16Z (CASE_FACTS): "171/729 closed (23%) … 555 evidence rows, 1,313 searches, $66.05 true; 65 agents started (~32 live); max context 309K".
- 04:21:16 `engine.cost ceiling`: "OK: within the ceiling (booked $2.84 + in-flight workflows $72.57)"; "search rows 1508 … cells 729 closed 215 (29%)".
- 04:21:22: "26 min: 215/729 (29%), ~$75.40, marginal still ~$0.21/cell".
- 04:22:20 thinking: "Research stopped at 215/729 closed (29%), 690 evidence rows, $76.40 spend—capped by WebSearch's shared 200-call session limit (402 of 596 calls refused)".
- N-25 CRITICAL (PR body 04:41:01): "`capture_workflows` charged every transcript entry, i.e. once per content block, so workflow spend was booked 3.2× ($128.05 for $39.83). It now charges once per message. Verified live: $73.56 booked."
- N-31: "`cost report` judged the run against the $5/pillar default ("$76.40, budget $20.00, OVER") while the driver enforced the owner's $200". cost report (04:39): "wall clock 13.7 min (target 120, schedule 98.5) · cost $76.40 (budget $20.00 for 4 pillar(s)) OVER · RESEARCH $73.56 96%".
- Re-handoff estimate (04:39): "16 categories, 60 batches, est $104.70 for 514 open cells; spent $76.40 of $200. NOT started: search capacity is still exhausted in this session".
- Session result events: 04:41:35 total_cost_usd 162.42 (439 turns, 4,230 s); 05:24:51 167.31; 05:53:51 173.99; 09:35:04 180.97.

**RESEARCH**
- "RESEARCH ran as 16 category workflows with 32 agents concurrently" (PR body). "16 categories / 81 batches / 729 open cells with no preflight check of required searches against the cap" (wf_ae470eb2 journal, 04:21:34).
- N-27 (04:24:17): "16 workflows spent it in ~20 min: 596 WebSearch attempts, 402 refused; Exa 65/65 HTTP 402; Tavily 432 plan limit. Research stalled at 215/729 (29%); later batches returned NO_CONNECTORS and closed nothing while still costing … measured 6.2 search calls/closed cell".
- Batch gate verdicts (04:21:34 journals): P2C2 "WEBSEARCH_CAP_EXHAUSTED closed 0 open 10"; P1C1 "NO_CONNECTORS closed 0 open 8 … the run had already fired 1075 searches"; P2C1 "CONNECTORS_EXHAUSTED closed 0 open 7 … Clay … rejected both 'job_title' and 'title'"; P4C2 "SEARCH_BUDGET_EXHAUSTED closed 0 open 16"; P4C3 "NO_CONNECTORS closed 0 open 12"; P1C2 "BLOCKED_NO_PRIMARY_SEARCH closed 0 open 9" then "NO_CONNECTORS" twice; P1C3: "preflight shows no internal documents, so the task's "HYBRID" claim is wrong".
- Rounds: 4 of 16 workflows reached "challenge r1" (P3C4, P3C1, P2C1, P1C1) at 04:21:26; none passed the floors gate. 04:21:47: stopped all 16 workflows.
- Workbook lock (engine/cli.py docstring, 04:18:27): "one engine.cli write took ~10 s — interpreter start, a 740 KB workbook load, the exclusive lock, a full save — and every writer in the run shares that one lock. A batch agent made 27 writes (4.5 of its 12 minutes); 76 batches would have held the lock ~5.7 hours".
- Context: "Context floor 66,178 tokens at turn 1 for every agent (N-19); contexts reach 190-260K by turn 20-35".
- Permission prompts (N-26, 04:21:10): "in a default-permission session 729 (24%) would have prompted the owner — 626 of 1,382 Bash calls and all 102 Firecrawl scrapes. 377 were python heredocs".

**SCORING → PROMOTE**: "not reached live (blocked by RESEARCH); exercised through the plugin's stub walk" (QA_REPORT). Stub walk 04:33:16: "34/34 steps PASS"; "a lane that advances nothing ends the stage rather than looping … dispatched three times at most, not ten"; "heatmap shipped twice, techstack once"; "--max-wall-min defaults to 240 minutes"; "PROMOTE is a FAIL when the connector refuses; the next run promotes". Critic rounds / REVISE: not stated.

**Wall-clock**: research 27 min (stopped 04:22Z); session 6 h incl. routine check-ins.

---

## 4. session_018bwxAeT6fPRuesGJs174Gh — "Cross Insurance Agency assessment" (first attempt, cross-insurance-agency-20261001)

- Dates: 2026-10-01T05:12:34 → 11:18:23. get_session: cost_usd **39.21**; input 2,201,519 / output 516,388 / cache_read 53,883,267. Status `need_input` "Exa out of credits, Tavily over limit; cap raised to 5000"; needs_action "1. Top up Exa + Tavily. 2. Start new session. 3. Tell me to resume cross-insurance-agency-20261001."
- Pages read: 38 (only 7 non-empty; last first_id 9affdaaf-f801-477b-8045-97a6374f1d98, has_more true). Events parsed: 52 + inline.

**Budget / cost**
- 05:39:47: "Spent: $5.87 is recorded. The tokens used by the stopped research agents aren't recorded yet; they get added when the run resumes."; proposed "resume cross-insurance-agency-20261001 with --max-usd 160".
- 05:39:49 result total_cost_usd 35.65 (haiku 4.64 / 207 web searches; opus 2.77; sonnet 28.23; duration_api_ms 5,033,725 ≈ 84 min). 08:11:16: 37.18; 11:18:23: 39.26.
- Ledger vs reality: $5.87 booked vs $35.65 session spend at the same instant (research agent tokens unbooked).

**RESEARCH**
- 05:39:10: "P4C4 came back with nothing written: 0 searches, 0 evidence and a gate FAIL after 8 agents and ~612K tokens."
- 05:39:13 P4C4 journal: 8 agent results all NO_CONNECTORS/FAIL; blocking terms "Tavily HTTP 432 usage limit exceeded", "Exa HTTP 402 credits exceeded", "WebSearch budget exhausted (200 of 200 …)", "Clay search-contacts DSL rejected fields job_title and title"; floors FAIL terms `absence_single_tool, absence_undeclared_empty, absence_unsearched, primary_unfired, volleys_incomplete`; "Evidence coverage is 0/30 (floor 70%)".
- 05:39:20 thinking: "Search is completely blocked … I'm stopping the remaining 15 workflows now rather than letting them burn tokens for no output." 05:39:22–27 TaskStop on 16 workflows + log watcher.
- 05:39:34 pipeline plan: "categories not passing: P1C1 … P4C4" (all 16); "SCORING gate NOT_RUN"; PAGES_B pending all six pages.
- 08:11:12: "each of the 694 cells needs a main search plus five angle searches … roughly 4,000 searches against a cap of 200. One category already used up the whole cap last time."
- 11:18:17 fix: "`CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` is now 5000, up from 200"; "capped at 8 searches per capability. That's about 800 searches for the whole run instead of about 4,000"; "Last time 8 agents spent about 612K tokens before finding that out"; "a round that closes no cells now skips the challenge and the second round".

**ENRICHMENT / PRELIM**: done once — "firmographics, $307.1M revenue, leadership, timeline, 16 peers, a tech stack baseline … question bank … 6,218 rows" (05:39:47). Earlier 125-cell run d5aed033 "still on file with nothing published from it".

**SCORING / REPORTS / PAGES / PROMOTE**: not reached. Critic / REVISE: not stated.

**User messages**: 08:10:25 "2"; 11:16:32 "1) Remove this cap bug please and batch accordingly to ensure proper token consumption".

**Wall-clock**: fan-out ~05:12 → 05:39 (≈27 min) for 0 cells closed; session 6 h incl. idle.

---

## 5. session_01DRQaUvWLCeFTpoeqtKMMZS — "Cross Insurance Agency assessment" (short)

- Dates: 2026-10-01T11:26:56 → 11:29:03 (2 min). cost_usd **1.07**. Pages read: 2 (complete). Events: 40.
- 11:26:56 USER: "Please assess Cross Insurance Agency. Ensure to submit all web app sections such that promotion happens appropriately at the assessment end. Recall to plan and consider the efficient promotion and token optimization."
- 11:28:31: "There's an existing run, but it covers only 18% of the client." AskUserQuestion offered "Fresh full run (Recommended)" vs synthesising from the 125-cell run. 11:29:03 "[Request interrupted by user]"; result err=True, total_cost_usd 1.07. Nothing else ran. All stage figures: not stated.

---

## 6. session_0152VQ1VesELtr4kdVDPaGj5 — "Cross Insurance Agency assessment" (10-01 → 10-06, the run that promoted)

- Dates: 2026-10-01T11:29:13 → 2026-10-06T01:22:37. get_session: cost_usd **378.21**; input 10,557,487 / output 3,565,769 / cache_read 1,123,140,067 / cache_write 24,990,681. Final result event 01:22:37 total_cost_usd **389.14** (haiku 20.81 / 908 web searches; opus 226.82; sonnet 141.52).
- Pages read: 38 (last first_id e2382d09-baef-4af2-bf9b-895053ef8dae, has_more true — pages 1–38 cover 2026-10-05T14:10 → 10-06T01:22 only; the 10-01→10-05 research/scoring/reports portion was not reached within the page cap). Events parsed: 435.

**Budget / cost**
- 14:15:59 result (10-05): total_cost_usd 349.21; assistant text: "Spend is about $110 of the $150 budget" (run ledger figure, source: that result event). Session result trail: 14:12:13 347.50; 15:57:21 352.94; 16:05:53 355.78; 16:29:25 359.48; 23:29:07 368.01; 23:43:32 371.10; 23:47:10 373.76; 10-06 00:12:17 375.68; 00:14:34 380.16; 00:24:51 382.95; 00:53:00 385.22; 01:22:37 389.14. ≈$40 of session spend after the promote went to gate-engineering (AG-13/AG-14) and CI repair.
- `--max-usd` for this run: not stated in pages read. search_ops: not stated.

**PAGES / PROMOTE**
- 14:15:28 `promote_run` (file `promote_attempt_5.json`) → promoted True at 2026-10-05T14:15:29; rows_written heatmap 1447 / overview 57 / insights 10 / platform 19 / context 11 / techstack 32. File name implies **5 promote attempts**; attempts 1–4 outcomes: not stated in pages read.
- 14:15:59 result: "rewrote all 1,248 workbook-style citations (E-001)… and re-promoted" (from the same result event).
- 14:13:11 local precheck: "fail {'CG-27': 2}" — "'APIs' reaches a client surface unexplained" at `overview.opportunity.tiles[0].addressable_cells[2].feature_that_addresses_it` (and [3]); fixed before promote.
- Subagents in the promote turn: overview-opportunity-producer 2, platform-conversation-producer 2, platform-fit-producer 2, platform-roadmap-producer 1, enrichment-connector-specialist 1 (result 14:15:59).
- 14:15:53: "Cross Insurance is re-promoted around the Zennify set, at 14:15 UTC, with all six pages live." Platform scores MuleSoft 45.8 / Data Cloud 44.5 / FSC 42.6 / Platform Foundation 40.9 / Agentforce 42.5; "the assessment report itself never names MuleSoft, Data Cloud or Agentforce".
- 16:05:53: "CI on that branch went red, so the Deployer didn't run … Another editor's commit 07112e90 … that script has failed 4 of its 34 checks, which blocks every deploy".
- 23:43:32 result (25 turns, 864 s): "every card scored 0.987–0.991 on Addressable opportunity, because every driving cell sits at the 1.0 floor … Catalogue interconnect decided the order (MuleSoft 0.337 against Platform Foundation 0.019)"; "the new checks refuse all five platform cards and all five recommendations for missing rebuttals". 23:47:10: "full run hit its 15-minute timeout" (test suite). 01:21:42 (10-06): "AG-10 collides with the governance skill's own audit-check numbering" → renumbered AG-14; "Once it deploys, I'll rebuild Cross Insurance Agency's platform page … then re-promote it" (a 6th promote pending).

**SCORING critic rounds / REPORTS REVISE rounds / RESEARCH rounds for this run**: not stated in pages read (those days fall before page 38).

**User complaints (verbatim)**
- 16:27:18: "Proceed. Also, the entity name is hyphernated. Ensure correct punctuation when naming entities. Names should only be hyphernated if they are originally so"
- 23:20:34: "Noticed on platform recommendations, the greenfield opportunities and strategic alignment parameters rarely receive scores. Ensure each of these parameters is weighed accordingly. Curate a robust fix against this"
- 23:24:19: "Also, most just seem to be prioritizing Mulesoft just because there are many systems. The recommendations are not rebutted to ensure stress testing."
- 15:56:35: "Done. Please land the fixes"

**Wall-clock**: 4 d 14 h from session create to last turn; promote at day 5 (10-05 14:15).

---

## 7. session_014aT6Jb6GxfECNa2Rhfprsb — "Northwest Bank assessment"

- Dates: 2026-10-01T05:13:58 → 2026-10-02T00:24:46. get_session: cost_usd **283.69**; input 702,163 / output 4,247,140 / cache_read 690,087,603. Status `failed`: "You've hit your weekly limit · resets Oct 3, 11am (UTC)".
- Pages read: 38 (3 non-empty; last first_id 826def23-b3ab-4cd9-a82a-53591f3d1177, has_more true). Events parsed: 11 + inline. The run's research/scoring/reports turns are stream-only and were not recoverable.

**Budget / cost**: 14:37:15 result total_cost_usd 278.22; 16:21:57 280.93 (opus $184.00, sonnet $95.78, haiku $1.14 / 35 web searches); 20:23:58 283.75. `--max-usd`: not stated. Run-ledger dollars: not stated.

**PROMOTE**: 14:36:48 workflow result: "promote_run(ba6b2090-f27d-4274-856d-dd9c792c2be0) succeeded on the first call. promoted=true at 2026-10-01T14:35:55Z, and it replaces the 11:41Z version. Rows written: heatmap 1078, overview 69, insights 9, platform 18, context 26, techstack 27. 45 alerts are open." → **two promotions** (11:41Z and 14:35Z). 14:37:13: "the consistency check found nothing blocking and the adversarial check found 7 blocking problems, all fixed before promoting" (B1–B5 listed: half-value fit for installed ActionIQ/Avaya/Communicator, 16 drawer wordings, timeline date, "34 package ids whose stored excerpts carried analyst or engine wording … replaced or dropped. 31 new verbatim spans").
- get_client_state: composite 1.88, scored_cells 651, status PROMOTED.

**RESEARCH / SCORING / REPORTS rounds**: not stated (unrecoverable). Session ended on weekly rate limit (00:24:45, ×3) while routine "Re-check PR #53" fired.

---

## 8. session_012JBufP5dZEV4VE2FbQLYYX — "Issue fix request"

- Dates: 2026-10-01T19:35:43 → 2026-10-02T00:33:47. cost_usd **2.97** (last result 3.51 incl. rate-limit turns). Pages read: 6 (complete). Events: 166.
- 19:36:01 USER: "I keep on getting this. Please fix this." — production page crash "Cannot read properties of null (reading 'split')" (Context C1 timeline). Fix in PR #54 (19:40:22, total_cost_usd 1.58, 23 turns, 265 s).
- 19:42:36 USER: "Fix and ensure the live app is okay. These are keys you can use to authenticate and install gcloud…"; 19:51:28 "I will rotate the keys later. Redeploy now. Avoid excuses. Use gcloud"; 19:52:06 / 19:52:28 "You are not redeploying using the plugin but redeploying the web app by authenticating to gcloud".
- 19:44:26: "The repo's security policy hook blocked me from using the service-account key"; 19:50:22 auto-mode classifier denial "[Auto-Mode Bypass]"; 19:52:09: "I can't run gcloud from this session". 20:01:10: CI 18/18 passed on PR #54. 00:33:46 weekly limit ×3.
- No DMA stage figures (not a run session): all "not stated".

---

## Cross-session quantitative table

| Session | Stage | Cost $ | Rounds | Retries | Wall-clock | Source quote |
|---|---|---|---|---|---|---|
| 01Gn SWBC QA2 | RESEARCH (16 cat, 31–37 agents) | $111.12 workflow / ledger $197.85 of $260 ceiling; session 105.27 | r1 only, 0/16 gates passed | 86–105 turns per agent; retry loops on spent channels | ~10–14 min to channel exhaustion | 01:25:29 "Spend hit $111.12 for 37 agents closing 33 cells in ~14 minutes — $3.37/cell, 18× the $0.19/cell estimate" |
| 01Gn | PRELIM | not stated | 1 | — | not stated | I-83 "PRELIM closed with Financial_Trends = 2 metrics … gold gate needs >=3" |
| 01Gn | SCORING/REPORTS/PAGES/PROMOTE | $0 (not reached) | 0 | — | — | "never reached … (0 of 16)" |
| 012F Cross QA | RESEARCH (694 cells) | session 98.87; run $ not stated; `--max-usd 210` | pilot + 12 workflows; 89/694 closed (77 absences) | C-27 "attempt 1 spent the whole budget in ~10 min" | 03:38Z → ~04:13Z | 04:12:36 "closed=86 absent=74 evidence=55 searches=801" |
| 012F | SCORING→PROMOTE | not reached | — | stub only | — | "Stress lifecycle walk … C-13 floor refuses" |
| 01Ur Northwest QA | RESEARCH (729 cells, 32 agents) | $76.40 true (booked $128.05 before N-25 fix) vs $200 ceiling; session 180.69 | r1; 4/16 reached challenge r1; 0 gates passed | lanes re-ran as NO_CONNECTORS batches | 27 min to stop | 04:22:20 "215/729 closed (29%), 690 evidence rows, $76.40 spend … 402 of 596 calls refused" |
| 01Ur | SCORING→PROMOTE | not reached live | stub 34/34 | "heatmap shipped twice, techstack once"; lanes "dispatched three times at most" | — | 04:33:16 stub walk |
| 018b Cross #1 | RESEARCH | ledger $5.87 vs session $35.65 | r1, 1/16 finished (P4C4 FAIL) | 16 workflows stopped | ~27 min | 05:39:10 "0 searches, 0 evidence and a gate FAIL after 8 agents and ~612K tokens" |
| 018b | PRELIM/ENRICH | included in $5.87 | 1 | — | not stated | "$307.1M revenue, leadership, timeline, 16 peers … 6,218 rows" |
| 01DR Cross short | — | 1.07 | — | — | 2 min | interrupted at AskUserQuestion |
| 0152 Cross (promoted) | PAGES/PROMOTE | run ledger "about $110 of the $150 budget" at promote; session 349.21 at promote → 389.14 end | 5 promote attempts (attempt_5 succeeded); 6th pending | CG-27 ×2 precheck fix; 1,248 citations rewritten | 10-01 11:29 → 10-05 14:15 promote | 14:15:28 promote_attempt_5 "True 2026-10-05T14:15:29" rows heatmap 1447 |
| 0152 | RESEARCH/SCORING/REPORTS | not stated (before page cap) | not stated | not stated | ~4 days | — |
| 014a Northwest (promoted) | PROMOTE | session 278.22 at re-promote; run ledger not stated | 2 promotions (11:41Z, 14:35Z) | "adversarial check found 7 blocking problems" fixed between | 05:14 → 14:35 (~9.4 h) | 14:36:48 "promote_run(ba6b2090…) succeeded on the first call … replaces the 11:41Z version" |
| 014a | RESEARCH/SCORING/REPORTS | not stated | not stated | not stated | not stated | (stream-only events) |
| 012J Issue fix | web crash fix | 2.97 | — | gcloud deploy refused ×3 | 5 h (incl. idle) | 19:36:01 "I keep on getting this. Please fix this." |

Totals for the 8 sessions (get_session cost_usd): 105.27 + 98.87 + 180.69 + 39.21 + 1.07 + 378.21 + 283.69 + 2.97 = **$1,089.98**; of which the two assessments that actually promoted (0152 Cross, 014a Northwest) account for $661.90, and the three QA sessions that each re-ran a live fan-out $384.83.

---

## Root causes observed (session id + timestamp)

1. **Session-shared WebSearch cap (200) consumed by 16–37 in-session workflow agents within ~10–20 min.** 01Gn 01:23:11; 01Ur 04:22:20 ("402 of 596 calls refused"); 012F 04:11:16 ("spent in ten minutes of a 694-cell run"); 018b 05:39:47. No preflight compared demand (01Ur N-27: "6.2 search calls/closed cell … ~2,000 WebSearch for 729 cells"; 018b 08:11:12 "roughly 4,000 searches against a cap of 200") with supply.
2. **Paid connectors exhausted mid-run and treated as fired volleys.** Exa HTTP 402, Tavily HTTP 432/429, Firecrawl 402/429 — 01Gn I-78 01:33:41 ("Tavily … HTTP 432 after 273 searches + 85 extracts"); 012F 04:12:12 ("80 rate-limits and 37 other errors against 88 successes"); 01Gn I-81 02:03:16 ("79 connector Search_Log rows … record calls that never ran … yet counted as fired volleys AND enrichment effort"); 012F C-24.
3. **No per-agent turn ceiling → retry loops at ~120K context/turn.** 01Gn I-79 01:33:41: "Agents ran 86-105 turns each retrying spent channels … workflow `agent()` has no maxTurns". $3.37/cell vs $0.19 estimate (18×).
4. **Research continued after channels were spent, closing nothing while costing.** 01Ur N-27 04:24:17 ("later batches returned NO_CONNECTORS and closed nothing while still costing"); 018b 05:39:10 (8 agents, ~612K tokens, 0 cells).
5. **Cost ledger wrong in both directions.** Over-booking 3.2× (01Ur N-25 04:41:01: "$128.05 for $39.83") would have halted the run early; under-booking (018b 05:39:47: "$5.87 is recorded" while the session had spent $35.65) hides spend until resume. Cost report judged against the $5/pillar default instead of the owner's `--max-usd` (01Ur N-31 04:39).
6. **Single workbook lock, ~10 s per engine.cli write.** 01Ur 04:18:27: "76 batches would have held the lock ~5.7 hours end to end, so concurrency past a few agents only queued them".
7. **Context floor and prompt bloat.** 01Ur 04:21:10 "Context floor 66,178 tokens at turn 1 for every agent … 190-260K by turn 20-35"; 012F C-21 04:12:03 "34.2 KB of additionalContext (background and connectors repeated 16x)"; C-26 "~6.6 KB per batch echoed into context"; 01Ur N-23 "~300K chars of exploration".
8. **Absences declared on unpinned entity queries (name collision "Cross").** 012F 05:20:43: "62 of 77 such records failed the rule … P3C4 had passed with 0/29" — cells closed as absent without real research, then re-opened (rework).
9. **Late-failing gates that are decidable at PRELIM.** 01Gn I-83 02:03:16: gold gate needs ≥3 financial metrics; "refusal would surface only after research, scoring, reports and pages were paid for". 01Gn I-71: the card never asked for the primary volley 391 cells were blocked on.
10. **Resume loop / stale routines.** 01Gn I-73 (resume hint repeats the refused command without `--max-usd`); 01Gn I-63 01:38 ("an hourly Routine for superseded run 9fcee059 was still enabled and relaunching lane batches two weeks later").
11. **Permission prompts in default mode (hidden by auto mode).** 01Ur 04:21:10 N-26: "729 (24%) would have prompted the owner — 626 of 1,382 Bash calls and all 102 Firecrawl scrapes. 377 were python heredocs".
12. **Promotion rework after the fact.** 0152: 5 promote attempts; 1,248 citations rewritten before attempt 5 (14:15:59); CG-27 ×2 (14:13:11); then owner complaints 23:20:34 / 23:24:19 drove new gates (AG-13/AG-14) that "refuse all five platform cards and all five recommendations" → 6th promote pending (10-06 01:22:33). 014a: two promotions (11:41Z, 14:35Z) after "7 blocking problems" found post-promote (14:37:13).
13. **Mid-run plugin edits / CI red blocking deploys.** 012F 04:11:45 doctor "UPDATED_MID_SESSION"; 0152 16:05:53 "that script has failed 4 of its 34 checks, which blocks every deploy".
14. **Weekly usage limit ended sessions.** 014a 00:24:45 and 012J 00:33:46 (10-02): "You've hit your weekly limit · resets Oct 3, 11am (UTC)".
15. **Owner-side blockers.** 018b needs_action "Top up Exa + Tavily. Start new session"; 01Gn needs_action "Raise budget cap to ~$380?"; 012J gcloud redeploy refused by policy hook + auto-mode classifier (19:44:26, 19:50:22).

Not found in any page read: explicit SCORING critic-round counts, REPORTS REVISE counts, `AT_BUDGET_CEILING`, `CONNECTOR_DRIFT`, `search_ops_since_checkpoint`, or an "against 60" reading — all "not stated" for this set.
