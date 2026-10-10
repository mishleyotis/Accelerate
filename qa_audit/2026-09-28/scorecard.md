# SCORECARD — 28-09-2026 · dma-insights 1.20.0

| axis | checks | pass | partial | fail | unknown | pass rate (of decided) |
|---|---|---|---|---|---|---|
| A Packaging & manifest | 7 | 2 | 2 | 3 | 0 | 43% |
| B Routing | 5 | 0 | 2 | 3 | 0 | 20% |
| C Orchestration | 9 | 3 | 4 | 2 | 0 | 56% |
| D Verification economy | 12 | 4 | 3 | 3 | 2 | 55% |
| E Token economy | 10 | 5 | 2 | 1 | 2 | 75% |
| F Resilience | 13 | 4 | 3 | 3 | 3 | 55% |
| G Memory | 9 | 3 | 0 | 2 | 4 | 60% |
| H Hooks | 4 | 0 | 1 | 1 | 0 | 25% |
| I Tools | 1 | 0 | 0 | 0 | 0 | 0% |
| J Contracts & doctrine | 6 | 0 | 1 | 4 | 1 | 10% |
| K Security & spend | 1 | 0 | 0 | 1 | 0 | 0% |
| L Prompt craft | 1 | 0 | 0 | 1 | 0 | 0% |
| M Templates | 9 | 4 | 2 | 1 | 2 | 71% |
| N Continuity | 9 | 2 | 3 | 4 | 0 | 39% |
| O Promotion | 16 | 6 | 2 | 3 | 5 | 64% |

## Per-check detail
| axis | check | result | evidence |
|---|---|---|---|
| A | A-01 | PASS | 0 dangling |
| A | A-02 | PARTIAL | 12 refs missing at stated path; 0 broken per audit_skills resolver |
| A | A-03 | FAIL | ≥5 version strings (F-A03-020) |
| A | A-04 | FAIL | 4/4 duplicates diverge (F-A04-012) |
| A | A-05 | FAIL | 3 retired skills triggerable (F-A05-001) |
| A | A-06 | PASS | clean clone digest e827602c == tree; audit_coverage/chain/gen_gates --check green |
| A | A-07 | PARTIAL | catalogue+template pinned; gold_manifest v5.0 skew; mutation not halted (F-F06-009) |
| B | B-1 | PARTIAL | 0 >1024 chars; 16 blanket-priority descriptions; 0 vendor names |
| B | B-2 | FAIL | duplicates + retired overlap ≈1.0 with no disambiguation |
| B | B-3 | FAIL | 84.4%/90.6% top-1, 6 retired routes, 0 deck confusions |
| B | B-4 | FAIL | 5/6 SKILL.md oversized; reading manifest present in surface-production, not enforced |
| B | B-5 | PARTIAL | zennify-design-system/narrative both claim supersedes; no cycle found |
| C | C-1 | FAIL | page-producer fan-out documented without Agent tool (F-C01-021) |
| C | C-2 | PASS | engine.brief packets ≈750 tok, RUN_ID+category keyed, returns from sheets |
| C | C-3 | PARTIAL | research lanes yes; per-surface producers no ambiguity rule |
| C | C-4 | PASS | 16 lanes, nesting 1, batching per category |
| C | C-5 | PARTIAL | 0 never-spawned; 6 page producers duplicate assembly the driver does |
| C | C-6 | PARTIAL | tiering exists; reasons unstated; Sonnet unit passes gates (F-14) |
| C | C-7 | FAIL | 9 agents >20 tools; contradictory tool precedence (F-L11-042) |
| C | C-8 | PARTIAL | foreign cell denied; unverified excerpt refused; stale run id passes; duplicate query accepted |
| C | C-9 | PASS | preflight autobind or END; STOPPED_BUDGET on a person |
| D | D-01 | UNKNOWN | no run transcripts on disk; allow-lists say search is possible |
| D | D-02 | FAIL | 31 agents (F-D02-008) |
| D | D-03 | PASS | search_requests → harvest_on_return → relay batch → specialist → relay record → reconcile (code-traced) |
| D | D-04 | FAIL | 67% verifiable (F-D04-005) |
| D | D-05 | FAIL | duplicate query accepted (F-D05-033); rate unmeasured |
| D | D-06 | UNKNOWN | fetch_cache exists per run; rate unmeasured |
| D | D-07 | PASS | challenge brief carries synthesis+evidence, not rationale (brief.challenge_batch _abridge) |
| D | D-08 | PARTIAL | research-challenger never judges own cell; page-consolidator challenges its own storyline |
| D | D-09 | PASS | E-ids by reference in packets |
| D | D-10 | PASS | excerpt_unverified refusal at register (C-8a) |
| D | D-11 | PARTIAL | escalation split exists (relay/absence) but stated in 3 places differently |
| D | D-12..20 | PARTIAL | declared absence carries ladder/proxy_log/hunted; no per-facet status, no cost, no triage record; batching per category not per proxy class |
| E | E-01 | FAIL | heatmap session 23% before first call (F-E01-026) |
| E | E-02 | PASS | connector schema ≈6.7k tok; deferred by harness |
| E | E-03 | PASS | brief 2,997 B; returns to sheets |
| E | E-04 | PASS | brief.as_markdown puts rules after material |
| E | E-05 | PARTIAL | cost.schedule forecast + cost_ledger exist; error not measurable (no run) |
| E | E-06 | PASS | checkpoint_required counter in engine.cli search (60 ops) |
| E | E-07 | UNKNOWN | no completed run on disk |
| E | E-08 | UNKNOWN | no transcripts |
| E | E-09 | PASS | ceilings default and bite ($5/pillar, 10 rounds) |
| E | E-10 | PARTIAL | PostCompact re-injects brief, not parameters (F-E10-034) |
| F | F-01/02 | UNKNOWN | lane retry once documented; not injected (needs model runs) |
| F | F-03 | UNKNOWN | connector sanity checks: CG-32 (Clay handle) exists; not injected |
| F | F-04 | PASS | resume recovers position from workbook |
| F | F-05 | PARTIAL | corrupt handoff refused for an unrelated reason |
| F | F-06 | FAIL | detected, not halted |
| F | F-07 | PASS | handback computed from sheets whether lane finished or died |
| F | F-08 | PARTIAL | --no-push continues; remediation queue not found |
| F | F-09 | FAIL | no caps/version tokens (F-G05-017) |
| F | F-10 | FAIL | reported, not refused (F-F10-032) |
| F | F-11 | PASS | registry + watchdog STALLED/UNREADABLE with resume plan |
| F | F-12 | UNKNOWN | not injected; deny_whole_page_fetch limits page text to 240-char windows |
| F | F-13 | PASS | 3/3 ISO cases against pinned reference date; Q-dates UNVERIFIED (F-L11-031) |
| F | F-14 | PARTIAL | band 3/3, label 3/3, one arithmetic slip |
| G | G-01 | FAIL | 3 agents + 1 hook write |
| G | G-02 | UNKNOWN | client memory files absent here |
| G | G-03 | UNKNOWN | registry file not in container |
| G | G-04 | UNKNOWN | same |
| G | G-05 | FAIL | no version tokens |
| G | G-06 | UNKNOWN | no open engagements here |
| G | G-07 | PASS | engine.cli resume derives state from workbook, not chat |
| G | G-08 | PASS | get_memory_digest read first is in every brief; recall_for_gates server-side |
| G | G-09 | PASS | no protected categories found in memory tool contracts |
| H | H-1 | PARTIAL | 25 handlers all fail-open; spend hooks fail the test (F-K01-003); 0.9 s per Bash |
| H | H-2 | DONE | classification in hooks_spec.md |
| H | H-3 | DONE | 25 candidates assessed |
| H | H-4 | FAIL | same rule enforced 3 ways (scope: hook+ledger+prose; template: prose only) |
| I | I | DONE | tools_spec.md; 34-tool server ungrouped |
| J | J-1 | FAIL | v3 vs v7, 3 manifest shapes, no handoff version |
| J | J-2 | FAIL | 6 orphans, 124 dead candidates, dead schemas |
| J | J-3 | FAIL | rubric.py 0 rows |
| J | J-4 | FAIL | FACT on T3 27%, 100% FACT items, scans at T3 |
| J | J-5 | UNKNOWN | no completed inputs on disk |
| J | J-6 | PARTIAL | 174 thin/absence test functions; no live walk |
| K | K | FAIL | credit tools auto-approved; withdraw auto-approved; rm inside run root; no secrets in tree |
| L | L | FAIL | worst rows 2/10; 46 contradictions; invariant breaches in prose |
| M | M-01 | PASS | 6 templates + catalogue hashed |
| M | M-02 | PASS | template.bind pins digest per run |
| M | M-03 | PASS | report_shell.docx copy-then-fill |
| M | M-04 | PARTIAL | section_sources/tab_recording_map cover pages; workbook↔report map partial |
| M | M-05 | UNKNOWN | no shipped deliverables on disk |
| M | M-06 | PASS | driver passes contract PATH; producers call get_page_contract |
| M | M-07 | PARTIAL | producer_version free string; contract cr-… recorded server-side |
| M | M-08 | FAIL | prose only |
| M | M-09 | UNKNOWN |  |
| N | N-01 | FAIL | 3 shapes |
| N | N-02 | FAIL | no version/hash on handoff |
| N | N-03 | FAIL | is_file checks |
| N | N-04 | PARTIAL | Gate_Log + preflight record decisions; no decision log file |
| N | N-05 | PARTIAL | research-close resume mechanically verified (stress REQ 5b); assessment/report boundaries not walked |
| N | N-06 | FAIL | 4 facets unreached on goeasy |
| N | N-07 | PARTIAL | preflight answers persisted; spend approvals not persisted |
| N | N-08 | PASS | registry log/beat/close |
| N | N-09 | PASS | client folder + memory backup pushed per stage |
| O | O-01 | PARTIAL | prose + get_run_progress in surface-producer; no SessionStart call |
| O | O-02 | UNKNOWN | claim is a write on prod; not exercised |
| O | O-03 | UNKNOWN | history not exposed |
| O | O-04 | FAIL | attempts=5 open |
| O | O-05 | UNKNOWN |  |
| O | O-06 | PASS | surface_export scaffold + ship_page from disk |
| O | O-07 | FAIL | 28% |
| O | O-08 | PASS | expect_of on every submit |
| O | O-09 | PASS | parts by 131072 B; no repartition |
| O | O-10 | PASS | get_staged_payload section/part reads documented and used |
| O | O-11 | FAIL | no id map |
| O | O-12 | PARTIAL | free-string producer_version |
| O | O-13 | UNKNOWN |  |
| O | O-14 | UNKNOWN | withdraw not exercised |
| O | O-15 | PASS | staged read is unredacted by contract |
| O | O-16 | PASS | 542 findings/60 d, 106 refinements, digest wired |

## Heat map by component (findings by severity)
| component | BLOCKER | HIGH | MEDIUM | LOW |
|---|---|---|---|---|
| MCP connector surface | 0 | 0 | 1 | 0 |
| PostCompact hook | 0 | 0 | 1 | 0 |
| SKILL.md sizes and references | 0 | 0 | 1 | 0 |
| account skills (synced) | 1 | 0 | 0 | 0 |
| account vs plugin skill copies | 0 | 1 | 0 | 0 |
| agent model choice | 0 | 0 | 0 | 1 |
| agents/*.md tool allow-lists | 0 | 1 | 0 | 0 |
| connector rejections | 0 | 1 | 0 | 0 |
| credential file on disk | 0 | 0 | 0 | 1 |
| cross-file rules | 0 | 1 | 0 | 0 |
| dma-governance + dma-assessment scripts | 0 | 1 | 0 | 0 |
| dma-surface-production reading load | 0 | 0 | 1 | 0 |
| engine + hooks + governance schemas | 0 | 1 | 0 | 0 |
| engine catalogue pin | 0 | 1 | 0 | 0 |
| engine.cli evidence + connector gates | 1 | 0 | 0 | 0 |
| engine.cli search | 0 | 0 | 1 | 0 |
| enrichment state → workbook | 0 | 1 | 0 | 0 |
| evidence id map | 0 | 0 | 1 | 0 |
| evidence register | 0 | 1 | 0 | 0 |
| heatmap-evidence-producer | 0 | 1 | 0 | 0 |
| heatmap-evidence-producer output | 0 | 1 | 0 | 0 |
| hooks.json Bash matchers | 0 | 0 | 1 | 0 |
| local pre-validators | 0 | 1 | 0 | 0 |
| memory files | 0 | 1 | 0 | 0 |
| memory writers | 0 | 0 | 1 | 0 |
| package scan / ingest | 0 | 0 | 1 | 0 |
| recency vocabulary | 0 | 0 | 1 | 0 |
| research_handoff.json contract | 0 | 1 | 0 | 0 |
| routing.md vs agent frontmatter | 0 | 0 | 1 | 0 |
| run manifest | 0 | 1 | 0 | 0 |
| scoring arithmetic | 0 | 0 | 1 | 0 |
| scripts/hooks/autoapprove_builtins.py | 0 | 0 | 1 | 0 |
| scripts/hooks/autoapprove_connector.py | 1 | 0 | 1 | 0 |
| scripts/hooks/guard_dispatch.py | 0 | 0 | 1 | 0 |
| scripts/hooks/precheck_promote.py | 0 | 0 | 0 | 1 |
| shipped skill prose | 1 | 0 | 0 | 0 |
| skill descriptions | 1 | 0 | 0 | 0 |
| sub-agent ambiguity rule | 0 | 0 | 0 | 1 |
| template enforcement | 0 | 1 | 0 | 0 |
| version strings | 0 | 0 | 1 | 0 |
| workbook contract check | 0 | 0 | 1 | 0 |