# REMEDIATION PLAN — 28-09-2026 · dma-insights 1.20.0

Audit-only: nothing below has been changed. Each item names the findings it closes and the test that proves closure.

## W1 — Blockers
| item | closes | proof |
|---|---|---|
| 1. Delete the account-level `dma-p1`, `dma-orchestrator` and `dma-core` skills and the four account duplicates (`dma-assessment`, `dma-research`, `dma-governance`, `dma-first-call-deck`); add legacy-phrase redirects to `dma-research`'s description; ship a PreToolUse(Skill) deny for the three names until the sync is gone | F-A05-001, F-B03-002, F-A04-012 | re-run `routing_eval.jsonl` through a fresh Sonnet router: ≥95% top-1, 0 retired routes |
| 2. `autoapprove_connector.py`: move `tavily_research`, `tavily_crawl`, `enrich-*`, `match-*` and `withdraw_run` to WITHHELD; add the `cost_estimate` approval-token gate | F-K01-003, F-K03-025 | hook probe: every credit tool prompts without a token |
| 3. Claim labels from provenance: `--claim-type` required in `engine.cli evidence`; ledger and server gate refuse FACT on T3 or weaker; scan providers file at T1 | F-J04-004, F-J04-015 | replay the goeasy evidence rows through the gate: 0 FACT rows on T3/T4, 0 scan rows below T1 |
| 4. Invariant 6/7 in prose: fix `dma-first-call-deck/SKILL.md:457-480` (boundaries from `contract.band_of`, resolver hexes, drop the P1C5 row) and `dma-assessment/SKILL.md:188,198-199,227`; add a CI lint over `skills/` for `M5`, `Transformational`, `185F60`, `1.50–2.49` | F-L14-041 | grep over plugins/dma-insights/skills returns 0 |
| 5. Tests for `rubric.py`; a meta-test that fails when any engine module has 0 test rows | rubric.py zero rows | engine census: 0 modules with 0 rows |

## W2 — Structure
| item | closes | proof |
|---|---|---|
| Role separation: strip WebSearch/WebFetch from producers, checkers and verifiers; PreToolUse block by agent_type; producers emit `search_requests` | F-D02-008 | inventory: 0 synthesis/verification agents with search; hook probe denies |
| `verify_claim` tool and a VERIFY path before a synthesis is written; research capture stores full-sentence excerpts (minimum 120 chars) | F-D04-005 | D-04 sample ≥90% verifiable |
| Gap coordination: dossier fields on `engine.cli absence`; `engine.brief triage` dispositions; exclusion list in relay prompts; `append_search` refuses a logged query | F-D05-033, D-14, D-16 | C-8c: second identical query refused; gap_triage.json present per run |
| Template enforcement: PostToolUse gold-standard and drift on deliverable writes into run_manifest.gates; Stop and push denied while not PASS | F-M08-013 | placeholder report → push denied |
| Continuity: one `run_manifest.schema.json`; the research handoff packet gets schema_version, sha256 and a completeness verdict; `assessment.research_ready` calls `verify_handoff_lock`; validator refuses contract skew; orient and ledger refuse catalogue drift | F-N01-019, F-J01-018, F-F10-032, F-F06-009 | F-05, F-06 and F-10 injections all refuse naming the cause |
| Promotion mechanics: SessionStart producer hook reads `list_open_rejections` and `get_run_progress`; auto-close rejections on superseded runs; local CG-15; `evidence_id_map`; `list_submissions` server tool | F-O04-007, F-O07-010, F-O11-036, F-I01-028 | local catch rate ≥80% on the goeasy replay; O-03 measurable |
| Enrichment reach: the conductor reads `get_client_state` and `list_enrichment_gaps` in PRELIM and records facets in the manifest | F-N06-014 | next promoted run: 0 `never_enriched` facets with a workbook route |
| Governance and assessment scripts read v7 tabs through `engine.contract`; an empty evidence_index.csv is a refusal; dead-contract CI check; wire or delete the 6 orphans and 3 dead schemas | F-J01-006, F-J02-011 | dead-contract script green; governance on a v7 workbook produces a non-empty evidence index |
| Hooks: merge the six Bash guards; scope stage_advance; guard_dispatch checks the run id; credential guard covers sa.json; deny_bulk_read matches reads, not mentions; memory writes only by qa-overseer | F-H01-023, F-C08-022, F-K04-039, F-H01-043, F-G01-035, F-K02-024 | hook_latency under 200 ms per Bash; stale run id denied; heredoc write allowed |
| Memory: version tokens and a lock on notebooks and client memory; Drive push with etag; a stated cap with consolidation at 80% | F-G05-017 | a concurrent append during consolidate loses nothing |
| Topology: routing.md one-level dispatch; page producers become assemblers; one submitter statement | F-C01-021, F-L11-042 (submit rows) | agent_graph documented == actual |

## W3 — Economy
| item | closes | proof |
|---|---|---|
| Split page packs per surface; generate 1-gates.md per page; load gates only on refusal | F-E01-026 | tokens before first call ≤15% per phase (token_budget.csv) |
| Shrink SKILL.md files under 500 lines with per-phase reading manifests; fix the 12 dead references | F-B04-027 | audit_skills and inventory: 0 missing refs, ≤5k tokens |
| PreCompact parameter echo | F-E10-034 | post-compaction echo diff = 0 |
| Ingest keyed by (request_id, package sha); refuse empty ingests | F-O13-030 | one run per package version |
| `score_apply` engine command | F-F14-029 | F-14 rerun: 3 of 3 identical |

## W4 — Prompt craft and hygiene
| item | closes | proof |
|---|---|---|
| Resolve the 46 contradictions: one tool-precedence rule; one claim-label and one recency vocabulary owned by `engine.contract` and interpolated; quarter dates parsed | F-L11-042, F-L11-031 | prompt-craft L-11 rerun: 0 pairs |
| Apply the top three rewrites (dma-research SKILL.md core section; brief.py return and ambiguity block; session_brief numbered brief) | prompt_craft_scorecard rows 1–3, F-C03-040 | scorecard rows ≥7/10 |
| One VERSION constant; regenerate gold_manifest on v7.0; a per-agent model reason | F-A03-020, F-C06-037 | grep: one version string |
| precheck_promote stays client-side (no change) | F-H01-038 | — |
