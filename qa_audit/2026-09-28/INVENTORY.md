# INVENTORY — dma-insights plugin 1.20.0 — audit date 28-09-2026

Plugin root: `/home/user/Accelerate/plugins/dma-insights` · files hashed: 543 (SHA-256 in inventory.json) · manifest dangling paths: 0

## Manifest
| field | value |
|---|---|
| name | dma-insights |
| version | 1.20.0 |
| commands | 3 (doctor, setup-routines, run-assessment) |
| agents | 74 declared, 74 on disk |
| mcpServers | ./.mcp.json → scripts/mcp_proxy.py → https://dmai-mcp-dukrne5v4a-uc.a.run.app (34 tools) |
| hooks | hooks/hooks.json: 25 handler runs across SessionStart(2) PreToolUse(14) PostToolUse(6) Stop(1) SubagentStart(1) SubagentStop(1) PostCompact(1) |
| userConfig | mcp_base_url, repo_root |

## Skills
| skill | lines | tokens | desc chars | refs missing | files unreferenced from SKILL.md | version header |
|---|---|---|---|---|---|---|
| dma-assessment | 906 | 12290 | 851 | 3 ['engine/contract.py', 'engine/validator.py', 'references/templates/assessment_report_template.md'] | 15 | none |
| dma-first-call-deck | 903 | 15906 | 866 | 0 [] | 42 | none |
| dma-governance | 332 | 4065 | 985 | 0 [] | 8 | none |
| dma-rectifier | 413 | 6259 | 881 | 1 ['scripts/tests/test_permanent_regressions.py'] | 1 | none |
| dma-research | 802 | 11505 | 703 | 4 ['assets/revenue/AUM', 'scripts/agent_run.py', 'scripts/gen_research_agents.py', 'scripts/stress_run_lifecycle.py'] | 7 | none |
| dma-surface-production | 766 | 11085 | 1010 | 4 ['references/canonical_sources.json', 'references/tab_recording_map.json', 'scripts/inspect_client_folders.py', 'scripts/mcp_raw.py'] | 3 | none |

All six SKILL.md exceed 300 lines; five exceed both 500 lines and 5k tokens (B-4).

## Agents (74)
Models: {'opus': 15, 'sonnet': 58, 'haiku': 1}. Role classes: {'verification': 12, 'research': 20, 'utility': 11, 'coordinator': 1, 'synthesis': 30}. Agents with Agent tool: ['surface-producer', 'research-conductor']. With AskUserQuestion: ['research-conductor']. Write-capable: ['learning-testgen', 'rectifier', 'package-vetter', 'surface-producer'].

| agent | model | tools | search? | role | spawner files |
|---|---|---|---|---|---|
| evidence-integrity-checker | opus | 16 | Y | verification | 10 |
| exclusion-boundary-auditor | opus | 16 | Y | verification | 11 |
| finding-challenger | opus | 17 | Y | verification | 57 |
| numeric-reconciliation-checker | opus | 16 | Y | verification | 11 |
| enrichment-connector-specialist | sonnet | 24 | - | research | 18 |
| enrichment-ledger-auditor | opus | 17 | Y | verification | 6 |
| enrichment-planner | sonnet | 20 | Y | utility | 12 |
| enrichment-web-specialist | sonnet | 22 | Y | research | 18 |
| learning-grader | sonnet | 20 | - | verification | 14 |
| learning-testgen | haiku | 17 | - | utility | 11 |
| rectifier | opus | 22 | - | utility | 63 |
| package-vetter | opus | 8 | - | verification | 34 |
| page-consolidator | opus | 7 | - | utility | 47 |
| surface-producer | opus | 33 | - | coordinator | 66 |
| context-risk-producer | sonnet | 18 | Y | synthesis | 8 |
| context-sentiment-producer | sonnet | 18 | Y | synthesis | 9 |
| context-surface-producer | sonnet | 12 | Y | utility | 9 |
| context-timeline-producer | sonnet | 18 | Y | synthesis | 9 |
| heatmap-evidence-producer | sonnet | 18 | Y | synthesis | 10 |
| heatmap-focus-producer | sonnet | 19 | Y | synthesis | 10 |
| heatmap-freshness-producer | sonnet | 18 | Y | synthesis | 8 |
| heatmap-grid-producer | sonnet | 18 | Y | synthesis | 14 |
| heatmap-signals-producer | sonnet | 19 | Y | synthesis | 8 |
| heatmap-surface-producer | sonnet | 13 | Y | utility | 14 |
| heatmap-valuechain-producer | sonnet | 20 | Y | synthesis | 6 |
| insights-cards-producer | sonnet | 19 | Y | synthesis | 11 |
| insights-landscape-producer | sonnet | 21 | Y | synthesis | 11 |
| insights-surface-producer | sonnet | 12 | Y | utility | 8 |
| overview-findings-producer | sonnet | 18 | Y | synthesis | 10 |
| overview-governance-producer | sonnet | 18 | Y | synthesis | 10 |
| overview-hero-producer | sonnet | 18 | Y | synthesis | 16 |
| overview-market-producer | sonnet | 18 | Y | synthesis | 9 |
| overview-narrative-producer | sonnet | 18 | Y | synthesis | 10 |
| overview-opportunity-producer | sonnet | 19 | Y | synthesis | 9 |
| overview-people-producer | sonnet | 22 | Y | synthesis | 9 |
| overview-surface-producer | sonnet | 12 | Y | utility | 10 |
| overview-whynow-producer | sonnet | 18 | Y | synthesis | 10 |
| platform-conversation-producer | sonnet | 18 | Y | synthesis | 6 |
| platform-fit-producer | sonnet | 19 | Y | synthesis | 12 |
| platform-roadmap-producer | sonnet | 18 | Y | synthesis | 8 |
| platform-surface-producer | sonnet | 13 | Y | utility | 6 |
| techstack-layers-producer | sonnet | 21 | Y | synthesis | 7 |
| techstack-register-producer | sonnet | 21 | Y | synthesis | 10 |
| techstack-surface-producer | sonnet | 13 | Y | utility | 11 |
| adversarial-verifier | opus | 17 | Y | verification | 25 |
| deployed-app-auditor | opus | 16 | Y | verification | 35 |
| qa-overseer | opus | 21 | - | utility | 28 |
| report-assessment-producer | sonnet | 7 | - | synthesis | 11 |
| report-research-producer | sonnet | 7 | - | synthesis | 11 |
| report-validator | opus | 7 | - | verification | 14 |
| research-p1c1-producer | sonnet | 9 | Y | research | 21 |
| research-p1c2-producer | sonnet | 9 | Y | research | 5 |
| research-p1c3-producer | sonnet | 9 | Y | research | 4 |
| research-p1c4-producer | sonnet | 9 | Y | research | 4 |
| research-p2c1-producer | sonnet | 9 | Y | research | 3 |
| research-p2c2-producer | sonnet | 9 | Y | research | 3 |
| research-p2c3-producer | sonnet | 9 | Y | research | 4 |
| research-p2c4-producer | sonnet | 9 | Y | research | 3 |
| research-p3c1-producer | sonnet | 9 | Y | research | 3 |
| research-p3c2-producer | sonnet | 9 | Y | research | 3 |
| research-p3c3-producer | sonnet | 9 | Y | research | 3 |
| research-p3c4-producer | sonnet | 9 | Y | research | 3 |
| research-p4c1-producer | sonnet | 9 | Y | research | 3 |
| research-p4c2-producer | sonnet | 9 | Y | research | 3 |
| research-p4c3-producer | sonnet | 9 | Y | research | 3 |
| research-p4c4-producer | sonnet | 9 | Y | research | 6 |
| research-challenger | sonnet | 5 | - | verification | 10 |
| research-conductor | opus | 18 | Y | research | 36 |
| technographic-scanner | sonnet | 16 | Y | research | 23 |
| scoring-critic | opus | 7 | - | verification | 22 |
| scoring-p1-producer | sonnet | 7 | - | synthesis | 13 |
| scoring-p2-producer | sonnet | 7 | - | synthesis | 3 |
| scoring-p3-producer | sonnet | 7 | - | synthesis | 3 |
| scoring-p4-producer | sonnet | 7 | - | synthesis | 6 |

## Commands
| command | targets |
|---|---|
| doctor | ['scripts/doctor.py', 'scripts/agent_run.py'] |
| setup-routines | ['scripts/setup_routines.py', 'scripts/setup_routines.py'] |
| run-assessment | ['skills/dma-research/engine/', 'skills/dma-research', 'scripts/connector_contract.py'] |

## Hooks
| event | matcher | script | timeout s | measured ms (synthetic input) | fail mode |
|---|---|---|---|---|---|
| SessionStart | `(all)` | session_brief.py | 10 | 234 | open (missing script ⇒ allow + systemMessage) |
| SessionStart | `(all)` | ensure_headless.py | 10 | 54 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `WebFetch|mcp__Exa__web_fetch_exa` | deny_whole_page_fetch.py | 10 | 60 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Agent|Task` | guard_dispatch.py | 30 | 770 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash` | guard_driver_lock.py | 10 | 56 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash` | deny_credential_ops.py | 10 | 42 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash` | deny_bulk_read.py | 10 | 33 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash` | deny_artefact_writes.py | 10 | 63 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Write|Edit|MultiEdit|NotebookEdit` | deny_artefact_writes.py | 10 | 63 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash` | guard_actor_scope.py | 10 | 45 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `Bash|Write|Edit|MultiEdit|NotebookEdit|mcp__workspace__bash|mcp__workspace__web_fetch` | autoapprove_builtins.py | 10 | 62 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `mcp__.*` | autoapprove_connector.py | 10 | 69 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `WebSearch|WebFetch` | autoapprove_connector.py | 10 | 69 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `mcp__.*__submit_page_payload` | precheck_submit.py | 10 | 54 | open (missing script ⇒ allow + systemMessage) |
| PreToolUse | `mcp__.*__promote_run` | precheck_promote.py | 10 | 82 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `mcp__.*__submit_page_payload` | verdict_watch.py | 10 | 54 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `mcp__.*__promote_run` | verdict_watch.py | 10 | 54 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `Task|Agent` | artifact_cadence.py | 30 | 81 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `Task|Agent` | stage_advance.py | 90 | 571 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `Bash` | stage_advance.py | 90 | 571 | open (missing script ⇒ allow + systemMessage) |
| PostToolUse | `Agent|Task` | harvest_on_return.py | 120 | 459 | open (missing script ⇒ allow + systemMessage) |
| Stop | `(all)` | stage_advance.py | 90 | 571 | open (missing script ⇒ allow + systemMessage) |
| SubagentStart | `(all)` | session_brief.py | 10 | 234 | open (missing script ⇒ allow + systemMessage) |
| SubagentStop | `^(dma-insights:)?research-.*` | record_handback.py | 60 | 504 | open (missing script ⇒ allow + systemMessage) |
| PostCompact | `(all)` | session_brief.py | 10 | 234 | open (missing script ⇒ allow + systemMessage) |

Every hook fails OPEN by construction (the wrapper allows the call when the script is missing; scripts return exit 0 with no decision on any parse error). precheck_submit.py is the one hook that uses exit 2 (block).

## MCP server
| name | transport | tools | schema tokens (docstring+signature) | read/write split | callers |
|---|---|---|---|---|---|
| connector (dma-insights) | stdio proxy (scripts/mcp_proxy.py) → streamable HTTP on Cloud Run | 34 | ≈6,667 | 21 read / 13 write | every agent (allow-lists), ship_page.py, hooks precheck_submit/promote |

## Engine (skills/dma-research/engine)
Modules: 42 · public functions: 344 · LOC: 27632 · dead candidates (no call site outside own module/tests): 124

| module | loc | public | test rows | dead candidates |
|---|---|---|---|---|
| rubric.py | 46 | 2 | 0 | 1 |
| profile.py | 467 | 10 | 9 | 4 |
| surface_export.py | 353 | 9 | 14 | 5 |
| verify.py | 140 | 2 | 15 | 1 |
| ers.py | 329 | 8 | 23 | 5 |
| kg.py | 539 | 9 | 25 | 5 |
| grains.py | 285 | 8 | 27 | 3 |
| quality.py | 427 | 10 | 29 | 1 |
| ship.py | 169 | 2 | 40 | 0 |
| patch_validator.py | 165 | 3 | 45 | 0 |
| reports.py | 748 | 5 | 50 | 2 |
| retrieval.py | 335 | 7 | 56 | 2 |
| strip_working_area.py | 130 | 3 | 64 | 1 |
| validator.py | 483 | 3 | 76 | 1 |
| completeness.py | 432 | 5 | 82 | 0 |
| template.py | 399 | 9 | 83 | 4 |
| handoff.py | 368 | 2 | 91 | 0 |
| registry.py | 249 | 8 | 92 | 1 |
| techscan.py | 808 | 11 | 97 | 8 |
| gold_standard.py | 749 | 7 | 106 | 4 |
| fetch.py | 481 | 10 | 110 | 4 |
| pipeline_stub.py | 477 | 12 | 125 | 12 |
| prelim.py | 746 | 9 | 132 | 3 |
| orient.py | 443 | 2 | 136 | 0 |
| watchdog.py | 836 | 6 | 141 | 2 |
| relay.py | 1361 | 23 | 143 | 9 |
| narrative.py | 916 | 15 | 144 | 7 |
| report_spec.py | 239 | 3 | 158 | 0 |
| assemble.py | 621 | 10 | 196 | 4 |
| preflight.py | 781 | 9 | 218 | 0 |
| scope.py | 149 | 3 | 221 | 0 |
| memory.py | 771 | 10 | 233 | 4 |
| pipeline.py | 2216 | 2 | 237 | 1 |
| cost.py | 1038 | 14 | 283 | 8 |
| assessment.py | 952 | 13 | 302 | 3 |
| workbook.py | 1082 | 0 | 328 | 0 |
| floors_gate.py | 761 | 6 | 348 | 1 |
| runstate.py | 419 | 12 | 352 | 5 |
| brief.py | 2429 | 24 | 515 | 6 |
| contract.py | 1151 | 11 | 637 | 4 |
| cli.py | 698 | 3 | 665 | 0 |
| ledger.py | 1444 | 24 | 753 | 3 |

## Contracts
See contracts_census.md: 61 producer→consumer edges; 15 validated, 3 weak, 5 validated against an older schema, 29 trusted (plain json.load / exists), 3 doc-only, 6 orphans.

## Memory surfaces
| path | writer | reader | cap | version token |
|---|---|---|---|---|
| <run>/03_memory/<CAT>.md | engine.memory _append / consolidate | memory.parse/status; record_handback hook | none | none (consolidate read→write unlocked) |
| <run>/07_qa/memory_backup.json | engine.memory backup | memory.restore; stage_advance | none | sha256 digests |
| /root/.dma/clients/<slug>.md | client_memory.py; drive_fetch pull | drive_fetch push (blind PATCH); agents | none | none |
| Drive '<slug> — synthesis memory.md' | drive_fetch push_memory | drive_fetch pull | none | none |
| /root/.dma/bundles/<slug>/state.json | agents | artifact_cadence hook | none | none |
| dma_run_registry.jsonl | engine.registry | registry.read/latest/open_runs; watchdog | none | none |
| server findings memory (Postgres) | record_finding/refinement | get_memory_digest, search_findings | digest days ≤365, search ≤100, open ≤500 | content_hash dedup |

The 49,152-byte engagement registry named in the brief is not present in this container (no ~/.claude memory directory, no /root/.dma/clients); G-03 on that file is NOT MEASURABLE HERE.

## Duplicates (account-level synced copy vs plugin copy)
| skill | same sha? | account lines | plugin lines | loader uses |
|---|---|---|---|---|
| dma-research | False | 416 | 802 | both are listed to the model as separate skills (`anthropic-skills:` vs `dma-insights:`); the router picks by description text (B-3) |
| dma-governance | False | 297 | 332 | both are listed to the model as separate skills (`anthropic-skills:` vs `dma-insights:`); the router picks by description text (B-3) |
| dma-first-call-deck | False | 385 | 903 | both are listed to the model as separate skills (`anthropic-skills:` vs `dma-insights:`); the router picks by description text (B-3) |
| dma-assessment | False | 866 | 906 | both are listed to the model as separate skills (`anthropic-skills:` vs `dma-insights:`); the router picks by description text (B-3) |

Retired skills still installed with live triggers: ['dma-p1', 'dma-orchestrator', 'dma-core'] (account synced dir).

## Frozen assets
| asset | hash | status |
|---|---|---|
| engine/data/catalogue_v70_tier.json (catalogue_hash over cell ids+tiers) | 2d783cd2997ed4c5a8272a1e24f361fafe2070d7ec14c0679d5456d34f9aca42 | matches the synthetic run's Handoff_Lock pin |
| references/templates/* (template digest) | c341416eaa504f352d66237fcaec537bd7749d0feebbd23db88359e91b9dbecf | pinned into run at start (template_binding.json) |
| fixtures/gold_manifest.json | fetched 2026-08-20, ccg_catalog_version v5.0 | SKEW vs engine catalogue v7.0 |
| plugin tree digest (plugin_version.py) | e827602c95e747d12aae19921ebbc66e69ac716d439410aa5bc9f12f0e42e771 | clean clone == working tree |
