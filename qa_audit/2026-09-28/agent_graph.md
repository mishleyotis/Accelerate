# AGENT GRAPH — 28-09-2026 · dma-insights 1.20.0

## Documented topology (routing.md + research-conductor.md + surface-producer.md)
```
TOP SESSION (Routine) ─┬─ research-conductor ──(agent_run.py, 16 lanes)──> research-pXcY-producer ×16
                       │        ├──> technographic-scanner, enrichment-connector-specialist (PRELIM)
                       │        ├──> research-challenger (per converged category) ──10% sample──> finding-challenger
                       │        ├──> enrichment-web-specialist / enrichment-connector-specialist (relay batches, in-process)
                       │        ├──> scoring-p1..p4-producer ──> scoring-critic
                       │        ├──> report-research-producer, report-assessment-producer ──> report-validator
                       │        └──> <page>-surface-producer ×6 (page-batch) ──> ship_page.py --claim ──> promote_run (driver)
                       ├─ package-vetter
                       ├─ surface-producer ──> <page>-surface-producer ×6 ──(documented fan-out)──> 24 per-surface producers ──> finding-challenger ──> page-consolidator ──> checkers ×3
                       └─ qa-overseer ──> rectifier ──> learning-grader / learning-testgen (weekly)
```

## Actual topology (frontmatter + code)
- Only two agents carry the Agent tool: `surface-producer` and `research-conductor` (inventory.json has_agent). The six page producers CANNOT fan out; routing.md:82 itself says the top session dispatches every stage directly (MEM-0106), which contradicts routing.md:142-150. **Edge documented, mechanism absent** (F-C01-021).
- `research-conductor` dispatches lanes through `scripts/agent_run.py` (16 concurrent `claude -p` children, `DEFAULT_LANES=16`, nesting depth 1) over `engine.brief batch` packets; relay batches go to in-process subagents via the Agent tool. **Matches the documented research tier.**
- `engine.pipeline run` (code, not an agent) is the coordinator of record for a research-engine run: it dispatches, gates, records cost, and calls `promote_run` last. `surface-producer.md:3` says it is the only agent permitted to submit or promote; `surface-producer.md:101-115` says the driver ships. **Two coordinators documented for one stage.**
- Learning pair spawned only by the rectifier cycle (never from production) — matches.
- Never-spawned agents: 0 (every agent is named by at least one other file).

## Role class per agent
| agent | model | role | tools | search | note |
|---|---|---|---|---|---|
| evidence-integrity-checker | opus | verification | 16 | Y |  |
| exclusion-boundary-auditor | opus | verification | 16 | Y |  |
| finding-challenger | opus | verification | 17 | Y |  |
| numeric-reconciliation-checker | opus | verification | 16 | Y |  |
| enrichment-connector-specialist | sonnet | research | 24 | - | >20 tools |
| enrichment-ledger-auditor | opus | verification | 17 | Y |  |
| enrichment-planner | sonnet | utility | 20 | Y |  |
| enrichment-web-specialist | sonnet | research | 22 | Y | >20 tools |
| learning-grader | sonnet | verification | 20 | - |  |
| learning-testgen | haiku | utility | 17 | - |  |
| rectifier | opus | utility | 22 | - | >20 tools |
| package-vetter | opus | verification | 8 | - |  |
| page-consolidator | opus | utility | 7 | - |  |
| surface-producer | opus | coordinator | 33 | - | >20 tools |
| context-risk-producer | sonnet | synthesis | 18 | Y |  |
| context-sentiment-producer | sonnet | synthesis | 18 | Y |  |
| context-surface-producer | sonnet | utility | 12 | Y |  |
| context-timeline-producer | sonnet | synthesis | 18 | Y |  |
| heatmap-evidence-producer | sonnet | synthesis | 18 | Y |  |
| heatmap-focus-producer | sonnet | synthesis | 19 | Y |  |
| heatmap-freshness-producer | sonnet | synthesis | 18 | Y |  |
| heatmap-grid-producer | sonnet | synthesis | 18 | Y |  |
| heatmap-signals-producer | sonnet | synthesis | 19 | Y |  |
| heatmap-surface-producer | sonnet | utility | 13 | Y |  |
| heatmap-valuechain-producer | sonnet | synthesis | 20 | Y |  |
| insights-cards-producer | sonnet | synthesis | 19 | Y |  |
| insights-landscape-producer | sonnet | synthesis | 21 | Y | >20 tools |
| insights-surface-producer | sonnet | utility | 12 | Y |  |
| overview-findings-producer | sonnet | synthesis | 18 | Y |  |
| overview-governance-producer | sonnet | synthesis | 18 | Y |  |
| overview-hero-producer | sonnet | synthesis | 18 | Y |  |
| overview-market-producer | sonnet | synthesis | 18 | Y |  |
| overview-narrative-producer | sonnet | synthesis | 18 | Y |  |
| overview-opportunity-producer | sonnet | synthesis | 19 | Y |  |
| overview-people-producer | sonnet | synthesis | 22 | Y | >20 tools |
| overview-surface-producer | sonnet | utility | 12 | Y |  |
| overview-whynow-producer | sonnet | synthesis | 18 | Y |  |
| platform-conversation-producer | sonnet | synthesis | 18 | Y |  |
| platform-fit-producer | sonnet | synthesis | 19 | Y |  |
| platform-roadmap-producer | sonnet | synthesis | 18 | Y |  |
| platform-surface-producer | sonnet | utility | 13 | Y |  |
| techstack-layers-producer | sonnet | synthesis | 21 | Y | >20 tools |
| techstack-register-producer | sonnet | synthesis | 21 | Y | >20 tools |
| techstack-surface-producer | sonnet | utility | 13 | Y |  |
| adversarial-verifier | opus | verification | 17 | Y |  |
| deployed-app-auditor | opus | verification | 16 | Y |  |
| qa-overseer | opus | utility | 21 | - | >20 tools |
| report-assessment-producer | sonnet | synthesis | 7 | - |  |
| report-research-producer | sonnet | synthesis | 7 | - |  |
| report-validator | opus | verification | 7 | - |  |
| research-p1c1-producer | sonnet | research | 9 | Y |  |
| research-p1c2-producer | sonnet | research | 9 | Y |  |
| research-p1c3-producer | sonnet | research | 9 | Y |  |
| research-p1c4-producer | sonnet | research | 9 | Y |  |
| research-p2c1-producer | sonnet | research | 9 | Y |  |
| research-p2c2-producer | sonnet | research | 9 | Y |  |
| research-p2c3-producer | sonnet | research | 9 | Y |  |
| research-p2c4-producer | sonnet | research | 9 | Y |  |
| research-p3c1-producer | sonnet | research | 9 | Y |  |
| research-p3c2-producer | sonnet | research | 9 | Y |  |
| research-p3c3-producer | sonnet | research | 9 | Y |  |
| research-p3c4-producer | sonnet | research | 9 | Y |  |
| research-p4c1-producer | sonnet | research | 9 | Y |  |
| research-p4c2-producer | sonnet | research | 9 | Y |  |
| research-p4c3-producer | sonnet | research | 9 | Y |  |
| research-p4c4-producer | sonnet | research | 9 | Y |  |
| research-challenger | sonnet | verification | 5 | - |  |
| research-conductor | opus | research | 18 | Y |  |
| technographic-scanner | sonnet | research | 16 | Y |  |
| scoring-critic | opus | verification | 7 | - |  |
| scoring-p1-producer | sonnet | synthesis | 7 | - |  |
| scoring-p2-producer | sonnet | synthesis | 7 | - |  |
| scoring-p3-producer | sonnet | synthesis | 7 | - |  |
| scoring-p4-producer | sonnet | synthesis | 7 | - |  |

## Fan-out and concurrency
| measure | observed | recommended | why |
|---|---|---|---|
| max parallel research lanes | 16 (one per category), capped by `LANES_PER_CPU=2 × cpus` | 16 | one workbook under a file lock serialises writes; 16 is the category grain, not per-subcap |
| nesting depth | 1 (MEM-0106) | 1 | measured stall at depth 2 |
| batching grain | category (≈43–55 subcaps per lane) | keep | 851 subcaps would be 851 agents otherwise |
| relay batches | one fresh subagent per batch, grouped by capability and connector | keep | results never re-enter the top context |

## Value per agent
- 6 page producers duplicate what `engine.pipeline` + `surface_export.scaffold` do for `convert` sections (routing.md: most sections are convert, only 4 are produce). Candidate: merge page producers into the driver's page-batch step (C-5).
- 24 per-surface producers exist to make one-surface repair cheap; sound, but 20 of them share one prompt shape — a template with a surface parameter would remove 20 files.
- 16 category researchers are generated from one template (`gen_research_agents.py`); fine.
- `learning-testgen` is the only haiku agent; extraction/format work elsewhere (techscan render, gates markdown) is already code.
