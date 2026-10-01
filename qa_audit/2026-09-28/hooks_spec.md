# HOOKS SPEC — Axis H — 28-09-2026 · dma-insights 1.20.0

## H-1 Existing hooks (25 handler runs, all plugin-scoped; user settings.json and project .claude/settings.json declare no hooks, so nothing merges)

| script | event / matcher | measured ms | timeout | fail mode | verdict |
|---|---|---|---|---|---|
| session_brief.py | SessionStart, SubagentStart, PostCompact (all) | 234 | 10 | open | fine; prints routing rules only — no RUN_ID/phase echo (F-E10-034) |
| ensure_headless.py | SessionStart | 54 | 10 | open | fine |
| deny_whole_page_fetch.py | PreToolUse WebFetch / Exa fetch | 60 | 10 | open | deny verified for research agent_type or DMA_ACTOR; Tavily extract not matched (L-11) |
| guard_dispatch.py | PreToolUse Agent / Task | 770 | 30 | open | denies foreign cells; passes a stale run id (F-C08-022); >200 ms |
| guard_driver_lock.py | PreToolUse Bash | 56 | 10 | open | fine |
| deny_credential_ops.py | PreToolUse Bash | 42 | 10 | open | git-token patterns only; sa.json not covered (F-K04-039) |
| deny_bulk_read.py | PreToolUse Bash | 33 | 10 | open | **false positive measured during this audit**: it denied a heredoc WRITE of a markdown file because the command text contained the handoff filename (F-H01-043) |
| deny_artefact_writes.py | PreToolUse Bash; Write/Edit/MultiEdit/NotebookEdit | 63 | 10 | open | deny verified on a workbook path |
| guard_actor_scope.py | PreToolUse Bash | 45 | 10 | open | denies research/evidence/absence/challenge out of scope; does not see `engine.assessment score` (regex covers engine.cli and engine.memory only) — the ledger still refuses |
| autoapprove_builtins.py | PreToolUse Bash / Write / Edit | 62 | 10 | open | auto-approves `rm -rf` inside a run root and drive_fetch push (F-K02-024); correctly prompts on rm outside a run root, force-push, curl POST, gsutil, pip |
| autoapprove_connector.py | PreToolUse mcp__.* ; WebSearch / WebFetch | 49–84 | 10 | open | **auto-approves credit spend** (F-K01-003) and withdraw_run (F-K03-025); run_subroutine, export-to-csv, Slack send, Gmail draft, Drive share correctly prompt |
| precheck_submit.py | PreToolUse submit_page_payload | 54 | 10 | **closed (exit 2)** | blocked a payload with a bad envelope; the one fail-closed hook |
| precheck_promote.py | PreToolUse promote_run | 82 | 10 | open | allows without reading progress (F-H01-038, by design) |
| verdict_watch.py | PostToolUse submit / promote | 54 | 10 | open | fine |
| artifact_cadence.py | PostToolUse Task / Agent | 81 | 30 | open | fine |
| stage_advance.py | PostToolUse Task / Agent; PostToolUse Bash; Stop | 571 | 90 | open | runs on EVERY Bash result (F-H01-023) |
| harvest_on_return.py | PostToolUse Agent / Task | 459 | 120 | open | fine (a prose return produced no queue entry) |
| record_handback.py | SubagentStop research-* | 504 | 60 | open | writes 07_qa/handbacks that nothing reads (F-J02-011) |

Per-Bash-call overhead: ≈301 ms pre (56+42+33+63+45+62) + 571 ms post ≈ 0.9 s.

Credit-spending test, one per spending tool (hook run with synthetic PreToolUse input): Clay run_subroutine PROMPT ✓ · Vibe enrich-business ALLOW ✗ · Vibe enrich-prospects ALLOW ✗ · Vibe export-to-csv PROMPT ✓ · Tavily tavily_research ALLOW ✗ · Tavily tavily_crawl ALLOW ✗ · Exa agent_run PROMPT ✓ · Firecrawl scrape PROMPT ✓ · Drive share PROMPT ✓ · Gmail create_draft PROMPT ✓ · Slack send PROMPT ✓.

## H-2 Doctrine rules enforced only by prose — classification

| rule (where) | class | evidence |
|---|---|---|
| "run the gold-standard gate on your own output before you return" (conductor, surface-producer) | HOOK (PostToolUse on report / assemble / techscan render) calling the existing tool | template drift recurring per owner; tool exists, hook absent (F-M08-013) |
| "read list_open_rejections and get_run_progress first" (surface-producer, tool doc) | HOOK (SessionStart for producer sessions) | 200 rejections open, 25 days, unnoticed (F-O04-007) |
| "never re-synthesise a passing page" | HOOK (PreToolUse Agent for a page whose verdict is PASS) | cheap; verdicts file exists per version |
| "FACT only on T1/T2" | GATE-SCRIPT (server CG + ledger refusal) | 77 FACT rows on T3/T4 (F-J04-004) |
| "do not repeat a query already run" | GATE-SCRIPT (ledger.append_search refuses) + PreToolUse warn | duplicate accepted (F-D05-033) |
| "synthesis agents do not search" | HOOK (PreToolUse WebSearch/WebFetch by agent_type) + allow-list edit | 31 agents can (F-D02-008) |
| "approve every credit-spending call" | HOOK (fix autoapprove_connector) | fails today (F-K01-003) |
| "M5 does not exist" | GATE-SCRIPT (precheck_submit already rejects M5 in payloads) + CI lint over skills/ | prose breaches (F-L14-041) |
| "vendor-agnostic diagnostic queries" | PROMPT + PostToolUse warn on the search log | 0 vendor names in descriptions; queries unmeasured |
| "storyline challenge before promote" | PROMPT (judgement) | keep in the skill |
| "one story per page / thread written last" | PROMPT (judgement) | keep |
| "work only your own category" | GATE-SCRIPT (ledger.assert_actor_scope) + HOOK seam (exists) | correct owner split; hook misses the scoring verb |

## H-3 Candidates

| event | candidate | status | spec (event · matcher · inputs · decision · output/exit · timeout · fail mode · +/− test · latency · prose it deletes) |
|---|---|---|---|
| SessionStart | cold boot: hash check, registry pointer, parameter echo | CONFIRM (partial today) | SessionStart · all · run root from cwd or registry · run `engine.template binding` and `contract.catalogue_hash` vs Handoff_Lock, read 07_qa/pipeline_state.json · print run/root/stage/budget, exit 0 · 10 s · open · +: drifted catalogue prints HALT line; −: clean run prints echo · ≈300 ms · deletes "re-read this manifest, trust the two commands over anything you remember" |
| UserPromptSubmit | inject RUN_ID, phase, skill hint, retired→current map | CONFIRM | UserPromptSubmit · all · prompt text · legacy-phrase table (P1 research, research handoff, CCG/RSG, SIB, ESG P1C5, dma-p1/orchestrator/core) → append "route to dma-insights:dma-research" · exit 0 · 5 s · open · +: "P1 research for X" gets the hint; −: "first call deck" gets nothing · ≈20 ms · closes the 6 routing misses |
| PreToolUse search | vendor-name lint on diagnostic queries | REJECT as block; CONFIRM as PostToolUse warn | judgement-adjacent; a warn on the Search_Log row is enough |
| PreToolUse search | query-cache check | CONFIRM, but as the ledger's refusal first | PreToolUse · WebSearch, mcp Exa/Tavily search, Bash engine.cli search · normalised query · look up Search_Log + search_relay for this run · deny with the existing row id · 10 s · open · +: repeat denied; −: new query allowed · ≈150 ms (openpyxl read-only) |
| PreToolUse search/fetch (synthesis context) | block for synthesis/verifier agent_types | CONFIRM | PreToolUse · WebSearch, WebFetch, Exa, Tavily · agent_type · deny when agent_type is a producer/checker/verifier · message "emit search_requests" · 10 s · open · +: finding-challenger WebSearch denied; −: enrichment-web-specialist allowed · ≈60 ms · deletes 31 allow-list entries |
| PreToolUse credit tools | approval token with quoted cost | CONFIRM | PreToolUse · tavily_research, tavily_crawl, enrich-*, match-*, run_subroutine*, agent_run, firecrawl billed · run root · allow only when 07_qa/approvals.json names tool+cost+approver · no decision otherwise (prompt) · 10 s · closed for these names · +: enrich without token prompts; −: with token allows · ≈50 ms |
| PreToolUse memory write | block sub-agents; block evidence/score patterns | CONFIRM | PreToolUse · record_finding, record_refinement, Bash client_memory.py · agent_type + tool_input · deny unless top session or qa-overseer; deny bodies matching E-ids or "score:" · 10 s · closed · ≈40 ms |
| PreToolUse Skill | block retired skills | CONFIRM until deleted | PreToolUse · Skill · skill name ∈ {dma-p1, dma-orchestrator, dma-core} → deny with redirect · 5 s · closed · ≈20 ms |
| PostToolUse search/fetch | append to the search log | REJECT | engine.cli search is the only sanctioned search path and already logs; a hook would double-log |
| PostToolUse run-dir write | schema-validate the handoff | CONFIRM | PostToolUse · Bash engine.cli handoff · file path · validate schema_version + sha256 (needs F-J01-018) · systemMessage on FAIL · 30 s · open · ≈200 ms |
| PostToolUse Slack send | em-dash sanitiser | REJECT here | no Slack tool in any plugin agent; the top session posts |
| PreCompact | checkpoint + parameter echo | CONFIRM | PreCompact · all · run root · write 07_qa/param_echo.json (run, root, stage, budget, open cells); PostCompact prints it · 10 s · open · ≈100 ms · closes E-10 |
| SubagentStop | validate return against schema; reject prose | PARTIAL today (record_handback computes from sheets) | add "reject prose" only for relay specialists (must have called engine.relay record) |
| Stop | refuse to end with a blocking gate open | CONFIRM | Stop · all · 07_qa/pipeline_state.json · exit 2 when a stage FAIL has no handback and the touched deliverable's gate verdict is not PASS · 90 s · closed · ≈600 ms (existing stage_advance) |
| SubagentStop research | refuse close of a below-floor subcap without a declared absence | CONFIRM | SubagentStop · research-* · handback.still_open · systemMessage listing cells with no absence record · 60 s · open |
| PreToolUse Agent (proxy role) | require exclusion list in brief | CONFIRM | PreToolUse · Agent with enrichment-*-specialist · prompt · deny unless it carries an "already searched" block · 30 s · open (guard_dispatch extension) |
| PostToolUse deliverable write | template_diff → run manifest | CONFIRM | PostToolUse · Bash engine.cli report / assemble package / techscan render / strip · artefact path · run gold_standard + template drift; write verdict into run_manifest.gates · systemMessage on FAIL · 90 s · open · 1–3 s at stage boundaries only |
| Stop / PreToolUse Drive upload | block while template_diff not clean | CONFIRM | PreToolUse · Bash drive_fetch.py push · run_manifest.gates · deny (exit 2) while any verdict != PASS · 10 s · closed · ≈50 ms · deletes "do not hand back until the gate prints PASS" |
| PreCompact + stage Stop | manifest + stage packet | CONFIRM | call `engine.assemble checkpoint` (exists) |
| SessionStart producer | list_open_rejections + get_run_progress | CONFIRM | SessionStart · all · connector via mcp_proxy stdio · print outstanding repairs and PASS pages · 30 s · open · ≈1 s once per session |
| PreToolUse submit_page_payload | clean local validation + expect | PARTIAL today (envelope only) | extend precheck_submit: require 07_qa/local_validation.json with payload sha and self_heal + local CG-15 PASS; require expect for every list path (ship_page already supplies it) |
| PreToolUse page synthesis on a PASS page | block | CONFIRM | guard_dispatch reads verdicts_<ver>.json; deny dispatch of <page>-surface-producer when the page is PASS |
| PostToolUse submit | verdict → run manifest | CONFIRM (extend verdict_watch) | write submission_id, verdict, opened/closed rejection ids into run_manifest |
| PreToolUse promote_run | six PASS + 0 open rejections | CONFIRM (read verdicts file, not the network) | deny when any page verdict != PASS |
| PreToolUse register_evidence | id-map lookup | CONFIRM | read 07_qa/evidence_id_map.json by content hash; deny re-registration with the known id |

## H-4 Anti-patterns present
- Network calls in hooks: none today; the proposed producer SessionStart read is the one exception, once per session.
- Judgement logic in a hook: none.
- Silent fail-open on a safety rule: every hook but precheck_submit is fail-open by design. For the credential and spend guards, fail-open is the wrong default.
- Hooks editing files the model edits: none.
- Same rule three ways: actor scope = hook + ledger + prose (acceptable: the ledger owns it, the hook is a seam); template alignment = prose only; scoring arithmetic = prose only; "read rejections first" = prose + tool doc, no hook.
- Over-broad text matching: deny_bulk_read denies any Bash command whose text contains the handoff filename, including writes of unrelated files (F-H01-043).
- Six guards plus one announcer on every Bash call: consolidate into one guard process reading one JSON.
