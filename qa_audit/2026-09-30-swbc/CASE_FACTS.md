# CASE FACTS — SWBC live-run QA (2026-09-30)

Persistent block. Updated as the run proceeds; every issue gets an ID and a status.

## Engagement
- Entity: SWBC (multi-LOB; hybrid DMA). Scope doc: Google Doc 1d4_FeFork3CVpTFc0JIoLKTTiFQeKmQ-oo3qanKBQgQ
- Fresh run. Branch: ccr-bcc99dc1-pabayz. Plugin version at start: 1.20.0
- Prior audit: qa_audit/2026-09-28 (structural; 42/43 fixed, F-H01-038 REPRODUCED)

## Objectives under test
- O1 Efficient research, token economy, auto-approved tools (few prompts)
- O2 Research ↔ web-app submission contract; heatmap evidence linkage built as research progresses; per-pillar parallel workflow, one per category (4×4)
- O3 Synthesis + all output artifacts match the gold-standard templates

## Environment facts
- claude CLI 2.1.285 present; gcloud absent; identity from the routine SA key file (dmai-routine@) — doctor OK
- Connector live: 34 tools; unauth probe -> 401 (enforced)
- Run root: /home/user/dma-runs/swbc ; toolkits: /home/user/dma-runs/toolkits (pulled from Drive, 2026-05-04 copies)
- Connector baseline written from session tools: clay, drive, exa, explorium, indeed, tavily present; quartr absent (optional)
- Server state for swbc: 1 prior run 7968492e (INGESTED 2026-09-11, v7.0, composite 2.01, 418 scored cells of 851); entity_name/sub_vertical/size_tier NULL; 6 facets enriched_not_promoted, peer_scores never_enriched
- Scope doc: multi-LOB (FIG/Institutional, Insurance P&C+benefits, Mortgage, Wealth, Swivel payments); hybrid mode; sponsor Angelica Palm (CMO)

## Binding (owner-confirmed 2026-09-30)
- Primary IB; supplementary IC, CL, RIA (variant cells only); HYBRID; FULL; 760 cells
- Internal doc landed: 01_intake/SWBC_Context_for_DMA_2026-09.md sha e024e3d4

## Issues register
| ID | Obj | Sev | Where | What | Status |
|---|---|---|---|---|---|
| I-01 | O1 | HIGH | apps/mcp/server.py list_pending_runs | Returns every pending run corpus-wide: 354 rows / 157 KB / 5,018 lines, 162 superseded; no filter. One routine call overflows the tool-result budget; the pipeline's INGEST poll reads it every poll. | FIXED-CODE (display_id + latest_only params; pipeline passes display_id with fallback) - NEEDS CONNECTOR DEPLOY |
| I-02 | O2 | HIGH | engine.pipeline KG; run-assessment s1 | Toolkits (per-subcap diagnostic questions) never fetched; KG silently degraded to 71 category-level questions. | FIXED (KG stage pulls toolkits into <run>/toolkits when unset; command documents it) |
| I-03 | O1/O2 | HIGH | scripts/route_client.py; run-assessment s2 | No way to request a fresh run: any scored cell => READY_TO_SYNTHESISE => stop. Existing run 418/851 cells routed synthesis-ready with no coverage check. | FIXED (--fresh -> NEW_VERSION exit 7; partial:true under 80% of 686) |
| I-04 | O1 | LOW | doctor skill script dependencies | Fresh container: jsonschema missing; doctor fails until dma-deps install is run by hand (fix line present). | NOTED |
| I-05 | O1/O2 | MED | scripts/hooks/deny_credential_ops.py | Docs-URL rule denied any MENTION of a Google Docs URL as 'a shell fetch' - blocks --source-url/--url provenance for internal evidence in every HYBRID lane. Key-file rule also fires on mentions (kept: security control, low cost). | FIXED (fetch-only match; 8 regression cases) |
| I-06 | O2 | HIGH | engine/contract.py selected(); preflight binding | Multi-LOB entity could bind only ONE sub-vertical; other accepted LOBs' variant cells never researched. Owner decision: primary IB + supplementary IC/CL/RIA variant cells only, additive, no universal re-research. | FIXED (binding.supplementary_sub_verticals; SWBC 694 -> 760 cells) |
| I-07 | O1 | MED | engine/preflight.py skeleton | Row shapes lived in Python comments that json.dump drops; first fill refused 10 rows for unseen keys (source_name, implies_lob, lob, basis). | FIXED (_row_shapes in file) |
| I-08 | O2 | HIGH | engine/contract.py selected() + workbook seed guard | 38 of 165 variant cells (23%) carry bare tier T2; selector matched on tier label so they were unreachable for EVERY binding (IB lost 4: P1C1.4.IB1, P1C2.9.IB1, P4C1.9.IB1, P4C3.8.IB1). Seed guard also let them through unowned. | FIXED (sub_vertical_of from id suffix; all 165 resolve) |
| I-09 | O2 | HIGH | engine (no intake), run-assessment, SKILL.md | HYBRID mode was a label: 01_intake existed only in SKILL prose; lanes never told where internal docs are; no gate checks an internal citation exists. | FIXED (engine/intake.py; PREFLIGHT refuses empty intake; shared brief lists docs; HANDOFF refuses 0 internal rows) |
| I-10 | O3 | HIGH | engine/assemble.py open_folder; scripts/drive_fetch.py | Supersede checked only the LOCAL folder: fresh container reported "no previous package" while Drive root held the 2026-09-11 package (workbook, 2 reports, deck, handoff, preflight); push then OVERWROTE the prior run_manifest.json. Package scan would pick between two workbooks. | FIXED (drive_fetch archive-remote; open_folder calls it before first push; SWBC's 6 prior items moved to _superseded/prior-package_2026-09-16, 0 failed) |
| I-11 | O1 | MED | scripts/hooks/deliverable_gate.py | Gate denied EVERY push-package, including preflight.json that run-assessment step 3 instructs before any gold verdict can exist. | FIXED (working files exempt when both --file and --name are working files; 7 cases) |
| I-12 | O1 | MED | engine/cost.py; run-assessment s4 | `engine.cost estimate --run --root` (as documented) errors; the flag-less estimate priced the default selection (694) not the run (760). lane-fit joined root/run_id and crashed. | FIXED (estimate reads the run: $13.80 levered / $20 budget; lane-fit root fixed) |
| I-13 | O2 | MED | agents/research/categories maxTurns | P2C2 (353t) and P2C3 (345t) exceed a 340-turn lane at capability grain once supplementary variants are added -> guaranteed cold re-dispatch. | FIXED (maxTurns 400 via gen_research_agents.py; 16 manifests regenerated) |
| I-14 | O1/O2 | MED | engine/cost.py schedule vs agent_run capacity | Schedule promised 16 lanes / 99 min; host cap is 8 lanes (4 CPU x 2) -> 2 waves. | FIXED (schedule reads host_capacity: 8 lanes, 2 waves, 133 min - honestly over the 120 target) |
| I-15 | O1 | LOW | scripts/bootstrap_session.sh | Write(path) allow rules are ignored by Claude Code and print 3 warnings into every headless lane log; Edit rules already cover writes. | FIXED |
| I-16 | O1 | NOTE | engine.cost levers | Levered estimate applies x0.0169 to measured cost ($817 -> $13.80); to be checked against the real ledger. | WATCH |
| I-17 | O1/O2 | HIGH | engine/brief.py prelim_brief; engine/pipeline.py PRELIM | PRELIM dispatched enrichment-connector-specialist as a claude -p child; children hold NO enrichment connectors by design. It spent $0.25/10 turns, wrote nothing, asked to be re-dispatched; technographic-scanner's Clay/Explorium calls failed. PRELIM never ran the relay, so leadership/firmographics could only stall. | FIXED (connector pass written as an ORCHESTRATOR brief, logged [RELAY], driver waits for the session; this run serviced by in-process subagent) |
| I-18 | O2 | MED | engine/preflight.py record | Preflight entity.website read by nothing; connector lane refused to enrich without a resolved domain. | FIXED (website firmographic recorded at start, cited) |
| I-19 | O1 | HIGH | scripts/hooks/guard_dispatch.py stale_run | Refused every Agent dispatch naming a run started via engine.cli start at a non-env root: accepted a workbook only if its FILENAME held the run id, but start names it by entity slug + date. | FIXED (run registry maps run->root; bogus ids still refused) |
| I-20 | O2 | HIGH | 4 agent manifests, techscan CLAY_PLAN, clay_plan.py, autoapprove_connector, 4 rulebooks | Every Clay step named `find-and-enrich-company` / `find-and-enrich-contacts-at-company`, which the live Clay connector no longer has (it exposes search-companies/search-contacts + add-*-data-points). Agents were granted only dead names, so Clay could not run for any agent; in-session subagent reported Clay NOT_RUN. | FIXED (manifests, plans, approver, docs use live names; DSL verified live: `select from companies where domain = "swbc.com"` resolved SWBC) |
| I-21 | O2 | MED | engine/brief.py PRELIM rules | Brief said register the machine scan "never T1"; the connector's ET-11 gate and clay_taxonomy.json say T1, never T4 - a producer following the brief trips ET-11. | FIXED (brief cites ET-11) |
| I-22 | O2 | LOW | record_enrichment arg | Needs the connector run UUID, which does not exist before INGEST_A; PRELIM lanes cannot record against a run. | OPEN (note: record by display_id; UUID later) |
| I-23 | QA | LOW | scripts/tests/test_audit_builtin_approvals.py | Fails on the ORIGINAL commit too in this container (/root/.dma holds real secrets, so the approver declines a path under it). Environment-coupled test. | PRE-EXISTING |
| I-24 | O1 | MED | scripts/hooks/deny_credential_ops.py (my I-05 fix) | My first fetch-only regex was unanchored: cubic backtracking, adversarial test timed out at 60 s. | FIXED (\A anchor; 200 KB in 26 ms; 331/331) |

## Live-run observations
- PRELIM PASS in 1 round, 614.7 s (connector half serviced in-session; Explorium resolved SWBC, Clay NOT_RUN due to I-20)
- KG PASS: pulled 4/4 toolkits (I-02 fix live), DQ_Bank 6,747 rows, 9.4 s
- Data conflict to carry: Clay annual_revenue band 1B-10B vs ~$450M (LinkedIn) vs FIG $250M (company exec summary)
| I-25 | O1/O2 | HIGH | engine/brief.py (dispatch/batch md); RESEARCH-PROTOCOL | Research briefs named `--run R` but never the run root; protocol also made every lane REGENERATE the brief it was handed. Round 0: lanes ran `find /`, rebuilt briefs past the 120 s Bash default, got backgrounded, and headless lanes that ended their turn to wait simply exited. 16 lanes finished in 8-30 turns with ~1 cell worked. | FIXED (shared.run_root + a root line in every brief header; protocol: prompt IS the packet, never end a turn to wait) |
| I-26 | O1 | HIGH | engine/kg.py dqs_for | Re-read the whole DQ_Bank per cell: 794 calls x 6,747 rows = 5.4M openpyxl reads, 95-258 s CPU per category brief and per worklist/floors pass. | FIXED (DQ index per workbook state: 4.3 s) |
| I-27 | O2 | CRITICAL | engine/ledger.py search ceiling; runstate.checkpoint | The 60-search 'per conversation' ceiling was RUN-WIDE (Search_Log has no actor; one global mark) and lanes had no CLI to checkpoint: 16 parallel category lanes shared ONE window of 60 for the whole research stage (2 lanes walled at 60 in round 0). Parallel per-category workflows were structurally starved. | FIXED (window per category / PRELIM; driver checkpoints each category at dispatch; tested) |
| I-28 | - | - | pipeline log | (Withdrawn: suspected buffered log; opts.log already flushes - driver was busy in slow post-round work.) | WITHDRAWN |

## Parallelism enforcement (O2 answer, measured)
- One claude -p lane per CATEGORY (16), dispatched by agent_run.py ThreadPoolExecutor, host-capped at 8 concurrent (4 CPU x 2). Pillar is not a scheduling unit: all 16 categories are peers in one batch.
- Isolation is enforced: assert_actor_scope refuses a lane writing another category's cells; leads_in lets a lane cite (attach) another lane's source without re-searching.
- Before I-27 the parallelism was nominal: every lane drew on one shared 60-search window.
- Connector work is NOT parallel in lanes (children hold no connectors); it returns to the session as relay batches (round 0: 61 requests / 20 batches) serviced by in-session subagents (here: 4, one per pillar).

## Round 0 (old code) outcome
- 16 lanes, 8-30 turns each, ~$0.3-0.8 each; driver stopped and restarted with fixes I-25..I-27.
