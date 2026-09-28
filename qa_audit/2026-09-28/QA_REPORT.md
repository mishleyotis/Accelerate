# QA REPORT — dma-insights plugin 1.20.0 — audit date 28-09-2026

Auditor: independent QA lead (Claude, session 01SqSjYiyecAiKJfb6zyxQn9). Scope: `plugins/dma-insights` at commit d661bd8, the account-level synced skills, the live DMA Insights connector (free reads only), and a synthetic run built by the plugin's own lifecycle suite. Nothing in the plugin was changed; fault injection ran on a scratchpad copy. No credits were spent.

## Branch state — W1 blockers landed (28-09-2026, branch `claude/dma-qa-w1-blockers`, stacked on PR #40)

The audit above measured the plugin at d661bd8 and changed nothing. The W1 tier
of the remediation programme has since landed on this branch: the five BLOCKERs
and the four findings that share their root cause. The verdict stays
**DO-NOT-SHIP** until W2–W4 land and the deliverables are regenerated; what
changed is recorded here so the register and this report agree.

### Fixes landed

| finding | commit | what landed | proof |
|---|---|---|---|
| seed 6 / J-3 — `rubric.py` untested | 91884e5 | `tests/skills/research_engine/test_rubric.py`; meta-test `test_every_engine_module_is_tested.py` (every `engine/*.py` bar `__init__`, `pipeline_stub` imported by a test) | both pass; 42/42 modules covered |
| F-J04-004 BLOCKER — FACT on T3/T4 | 717710d | `contract.claim_label_for(tier)`: label derived from provenance; `ledger.append_evidence` refuses an explicit FACT on T3/T4; `--claim-type` optional (89 call sites kept); server gate **ET-10** (`gates.py`, `validation2._check_fact_tier`); `1-gates.md` regenerated (71 gates) | `test_claim_tier.py` 14 pass; `apps/mcp/tests/test_fact_tier.py` pass; replay of the 368 goeasy rows → 77 ET-10 reasons (= the audit's count); `gen_gates_md --check` current |
| F-J04-015 HIGH — FACT-on-tier / scan rows at T3 | 717710d (partial) | the FACT-on-tier half closes under ET-10; the scan-tier half (5 provider rows at T3) has no engine registration path to fix in W1 → **W2** | as above |
| F-A05-001 / F-B03-002 BLOCKER — retired skills routable | 168ed3d | `scripts/hooks/deny_retired_skills.py` (PreToolUse on `Skill`): `dma-p1`, `dma-orchestrator`, `dma-core` and the `anthropic-skills:` copies of the four plugin skills are refused and the owner named; `dma-research` description claims the six legacy phrases the router sent astray | `test_deny_retired_skills.py` 17 pass; probes deny the three, allow `dma-insights:*`. **Owner precondition open:** delete the account-level skills on claude.ai, then re-run `routing_eval.jsonl` (bar ≥95 % top-1, 0 retired routes) |
| F-A04-012 HIGH — diverged account copies | 168ed3d | same hook redirects `anthropic-skills:dma-{assessment,research,governance,first-call-deck}` to the plugin copy | same tests |
| F-K01-003 BLOCKER — spend auto-approved | bf330bc, fb4d862 | `SPEND_SUFFIXES` (tavily_research, tavily_crawl, enrich-business, enrich-prospects, match-business, match-prospects) removed from the read list and withheld; the one way through is an unexpired record with a quoted cost in `<run>/07_qa/approvals.json` (`engine.cli approve --tool --cost --approved-by`); the two prose sites that promised auto-approval now name the record; the audit roster gains Tavily research and the Vibe server | `audit_autoapprove.py --strict` rc 0: 133/199 approved, **62 withheld** (was 55/184), 3 guarded, 0 UNCLASSIFIED; probes: all six spend tools → no decision (prompt), `fetch-entities`/`tavily_search`/`tavily_extract` → allow; 539 hook tests + `test_approve.py` 7 pass |
| F-K03-025 MEDIUM — `withdraw_run` auto-approved | bf330bc | `withdraw_run` joins `GUARDED_SUFFIXES`: no hook, prompts on every connector prefix | `test_withdraw_run_prompts_on_every_prefix` |
| F-L14-041 BLOCKER — band rule, retired hex, M5 in shipped prose | 7fda49e | deck `color_level_system.py` = `bands.js` fills (`#FFCB99/#62D7B8/#27BBAF/#139F94`) and strict `<2/<3/<4`; Slide 13 = `engine/rubric.py` levels (L5 **Leading**, cuts 1.5/2.5/3.5/4.5); the retired hex removed from 22 files incl. the two template palette lists; `check_taxonomy_drift.py` widened (ungated `Transformational`, the 1.50/2.50/3.50 cut-offs, `#185F60`, `17 rollups`, `~72 capabilit`; `deprecated/` skipped); assessment `SKILL.md` → v5.6, 205/292/164/190, S3 cap 2.0, no ceiling at 5.0, one rollup per category (16), 136 capabilities, catalogue path instead of `/mnt`; `report_template.md` M5 → Leading; `heatmap_editor.py` accepts `null` for the retired P1C5 block and renders it NOT ASSESSED instead of refusing a v7.0 run | `check_taxonomy_drift.py` → 0 (and `test_check_taxonomy_drift.py` plants each of the five defects and expects the rule to fire); `test_deck_bands_match_app.py` pins accents, cut-offs, legends, levels and the editor to `bands.js` / `contract.band_of` / `rubric.py` (39 tests between the two files, incl. a python-pptx render of one block); `check_docs_in_sync` rc 0; `sync_config_yaml` OK; `verify_config_vs_template` 0/0; `audit_skills` 0 broken refs |

### Suites on the W1 head

`apps/mcp/tests` (with `pg8000` installed, as CI does): 1410 passed, 94 skipped. `plugins/dma-insights/scripts/tests`: 2146 passed, 1 skipped, 3 failed on a first run taken from a mid-edit tree (stale drift hits and five path references); the three tests pass on the final tree (32/32 in `test_audit_skills.py` + `test_check_taxonomy_drift.py`) and the full suite is being re-run on the final head. `tests/skills/research_engine`: the 196-test subset touching B3 passed (22 min); the full suite is running on the final head and CI runs it on the PR. `stress_run_lifecycle.py` exit 0, `stress_pipeline_stub.py` 34/34; `gen_gates_md --check`, `audit_coverage --strict`, `audit_chain --strict`, `audit_autoapprove --strict`, `audit_skills`, `check_taxonomy_drift` all rc 0. Counts are in the W1 PR body.

### Still open after W1

- Owner: delete `dma-p1`, `dma-orchestrator`, `dma-core` and the four `anthropic-skills:` duplicates on claude.ai; then the routing eval is re-run.
- Owner decision: the nine deck templates are v5.0-shaped (17 heatmap blocks); the catalogue has 16 categories. The editor now renders the P1C5 block NOT ASSESSED; re-authoring the templates to 16 blocks is not resolved here.
- ET-10 will refuse already-staged pages carrying FACT rows on T3/T4 (goeasy: 77 rows). Re-registration with the derived label is the repair.
- No deck was rendered end to end: no PPTX template exists in this container (they are fetched from Drive at run time). The editor's scored and unscored paths are exercised on a synthetic 8-shape block.
- F-J04-015's scan-tier half, and everything in W2–W4.

## Executive summary

**Verdict: DO-NOT-SHIP** (as installed on this account). 43 findings: 5 BLOCKER, 16 HIGH, 18 MEDIUM, 4 LOW; 37 reproduced, 6 inferred and capped at HIGH. Full table: `findings_register.csv`.

The three findings that matter most:

1. **Retired skills are still routable and the router picks them (F-A05-001, F-B03-002).** `dma-p1`, `dma-orchestrator` and `dma-core` are installed at account level with live "ALWAYS use" triggers, alongside four account copies of the plugin's own skills that have drifted (one says 17 categories, ~836 subcaps, M1–M5). A Sonnet router given only the installed descriptions routed 6 of 64 utterances to retired skills and scored 84.4% top-1 against a 95% bar. Every later gate then runs against the wrong contract. This is regression seed 10, present today.
2. **Claims labelled FACT rest on weak evidence, and synthesis outruns its excerpts (F-J04-004, F-D04-005).** On the live goeasy heatmap staging, 77 of 285 FACT rows sit on T3 or T4 sources; every cell item is labelled FACT; 42% of rows are undated. The evidence CLI defaults `--claim-type` to FACT and no gate in the engine or the server ties label to tier. A 30-cell entailment sample found only 67% of syntheses verifiable from their stored excerpts, with 12 of 67 claims unsupported, including a named-executive attribution. This is regression seed 2 and the "plausible output with no evidence behind it" class the audit was weighted toward.
3. **Spend is auto-approved, and shipped prose breaks the band invariant (F-K01-003, F-L14-041).** The connector auto-approval hook allow-lists Tavily research/crawl and Vibe enrich/match as "read-only", so a headless session can spend credits with no prompt. Separately, the first-call-deck skill carries band boundaries at 1.50/2.50/3.50 and the retired M5 hex, and the assessment skill still prints an M5 Transformational row; the charter calls that a bug whatever the tests say.

What held: the research engine's write path is fail-closed (unverified excerpts refused, foreign-category writes refused at the ledger and at the hook, whole-page fetches denied in research lanes); briefs are small (≈750 tokens) and self-contained; chunked transport supplies `expect` on every list; resume rebuilds state from the workbook; the clean clone reproduces the tree digest; three independent Sonnet scorers agreed on band and label.

## Regression seeds — status
| seed | present now? | check |
|---|---|---|
| 1 narrated searches | not measurable (no transcripts); the engine only accepts searches through `engine.cli search`, which logs | D-01, F-D05-033 |
| 2 FACT default / FACT on T3 | **FIXED in W1** (717710d): label derived from tier, ledger refuses FACT on T3/T4, ET-10 at submit | F-J04-004 |
| 3 connectors unused, web primary | contradiction still in prose (dma-research SKILL.md "web_search PRIMARY" vs "connector required"); relay exists | F-L11-042 |
| 4 subcaps scored on no capability evidence | not measurable on a scored run; scoring refuses uncited rationale (engine.assessment) | F-14 |
| 5 dead values | **YES** — 6 orphans, 3 dead schemas, 124 dead candidates, empty evidence_index.csv | F-J02-011, F-J01-006 |
| 6 green suite over a minority of modules | **FIXED in W1** (91884e5): rubric.py tested; meta-test keeps 42/42 covered | J-3 |
| 7 gate-id collisions | not found; `gen_gates_md --check` green | J-2 |
| 8 substring classifier | not found in techscan.py | J-4 |
| 9 dropped adversarial volleys | floors gate counts five volleys per cell | D |
| 10 retired skills routed to | **plugin guard landed in W1** (168ed3d); account-level skills still installed until the owner deletes them | F-A05-001 |
| 11 memory registry near cap | not measurable here (file absent); no caps exist in code | F-G05-017 |
| 12 connector filters ignored | Indeed company filter unguarded; CG-32 guards Clay handles | F-03 |
| 13 synthesis re-searching | allow-lists permit it (31 agents); not observed in this run's rows (368/368 package-discovered) | F-D02-008 |
| 14 proxy re-running failed queries | duplicate query accepted at the write | F-D05-033 |
| 15 template drift | enforcement is prose only; last three deliverables not on disk | F-M08-013 |
| 16 refusals found by a person | **YES** — 200 rejections open, 25 days, no session-start read | F-O04-007 |
| 17 enrichment held server-side never reaching the workbook | **YES** — goeasy: 4 of 7 facets never enriched on the promoted run | F-N06-014 |
| 18 CG-01 supersede trap | mechanism documented; not triggered on this run | promotion_replay.md |

## Axis verdicts
- **A Packaging** — Manifest clean (0 dangling, clean clone digest matches), but five version strings, four diverged duplicates and three retired skills. FAIL on A-03/04/05.
- **B Routing** — 84.4% top-1, six retired routes; five of six SKILL.md oversized. FAIL.
- **C Orchestration** — Research tier is sound (16 lanes, depth 1, category grain, bounded briefs, gates on a person). Production tier documents a fan-out no page producer can perform; two coordinators named for one stage. PARTIAL.
- **D Verification economy** — Relay for new retrieval is code and traced; but 31 synthesis/verification agents can search, 67% excerpt sufficiency, duplicate queries accepted, no triage record. FAIL.
- **E Token economy** — Briefs and returns are economical; page-production reading load is 23–28% of the window before the first call. PARTIAL.
- **F Resilience** — Resume, orphan detection, unverified-excerpt refusal and date handling pass; catalogue drift and contract skew are reported, not halted; no memory caps. PARTIAL.
- **G Memory** — No caps, tokens or locks anywhere; three agents plus a hook write. FAIL on what is measurable.
- **H Hooks** — 25 handlers, all fail-open except submit precheck; spend hook fails its test; ~0.9 s per Bash call; one false-positive deny measured on this audit. FAIL.
- **I Tools** — Most candidate tools exist as engine commands; the misses are `score_apply`, `verify_claim`, `absence_project`, local CG-15, an id map and `list_submissions`. See tools_spec.md.
- **J Contracts and doctrine** — v3-era readers against a v7 writer, three manifest shapes, unversioned handoff, FACT on T3, scans at T3. FAIL.
- **K Security and spend** — No secrets in the tree; credit tools and withdraw auto-approved; `rm -rf` allowed inside a run root; service-account key readable but not auto-approved. FAIL on spend.
- **L Prompt craft** — Worst rows 2/10 (dma-research, first-call-deck); 46 cross-file contradictions; invariant breaches in prose. FAIL. See prompt_craft_scorecard.md.
- **M Templates** — Pinned per run with hashes, copy-then-fill; drift tools exist but no hook runs them. FAIL on M-08.
- **N Continuity** — Registry and Drive mirror pass; manifest split across five files and three shapes; handoff has no version; enrichment held server-side unreached. FAIL.
- **O Promotion** — Transport mechanics pass (expect, parts, section reads); rejections ignored for 25 days, one page at five attempts, 28% local catch rate, 18 runs for one package. FAIL.

## Test suite
3,714 tests collected across `plugins/dma-insights/scripts/tests`, `tests/skills` and the surface-production script tests. An isolated run of `scripts/tests` passed 2,051 with 1 skipped in 5 m 36 s. A combined run started concurrently with the lifecycle stress suite showed one failure early and then exceeded the 25-minute ceiling at 60%; the failure did not reproduce in the isolated rerun, and the remaining ≈1,660 tests in `tests/skills` were not completed inside the audit budget (recorded as an open item, not as green). The plugin's own lifecycle stress suite passed 34/34.

## Open questions (not measurable with this access)
- D-01/D-05/D-06/E-07/E-08/O-03/O-05/O-13 need run transcripts or a submission-history tool (tools_spec.md `list_submissions`).
- O-02 and O-14 (claim contention, withdraw effect) are writes on the production connector; a staging connector or a synthetic run in the app would settle them.
- G-03/G-04/G-06 need the owner's Cowork memory registry file (not in this container).
- J-5 golden replay and M-05 drift on the last three shipped deliverables need those artefacts on disk.
- N-05 at assessment and report close needs a model-driven run past the no-credit boundary.

## Self-check
Each BLOCKER and HIGH was re-read against its measurement: the routing number is from a fresh Sonnet router that never saw the labels; the FACT-on-T3 count is from the staged rows themselves; the spend hook was run, not read; the band-boundary lines were grepped; rubric.py's zero rows is by the census's loose name match, so the real gap can only be smaller than measured elsewhere, not larger here. Six findings that rest on code reading alone are marked INFERRED and capped at HIGH (governance v3 readers, memory tokens, handoff version, manifest shapes, id map, compaction echo). Nothing moved up in this step. What was tried and held: unverified excerpt registration (refused), foreign-category writes (refused twice), whole-page fetch in a research lane (denied), destructive commands outside a run root (prompted), a corrupt handoff (refused, wrong reason), a duplicate evidence registration (never reached the ledger because the excerpt was unverified), a stale run id (passed — recorded).

## Deliverables (this folder)
INVENTORY.md · inventory.json · findings_register.csv · scorecard.md · routing_eval.jsonl · routing_eval_results.jsonl · routing_eval_report.md · token_budget.csv · fault_injection_results.md · verification_economy.md · hooks_spec.md · tools_spec.md · agent_graph.md · prompt_craft_scorecard.md · template_alignment.md · continuity_test.md · promotion_replay.md · gap_coordination.md · remediation_plan.md · contracts_census.md
