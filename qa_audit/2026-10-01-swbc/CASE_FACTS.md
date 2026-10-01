# CASE FACTS — SWBC live-run QA, session 2 (2026-10-01)

Persistent block. Read this first after any context loss. Every issue gets an ID (J-nn, continuing
from the 2026-09-30 register I-01..I-59 in ../2026-09-30-swbc/CASE_FACTS.md) and a status.

## Engagement
- Entity: SWBC (Southwest Business Corporation, San Antonio TX; private; multi-LOB; HYBRID).
- Scope doc: Google Doc 1d4_FeFork3CVpTFc0JIoLKTTiFQeKmQ-oo3qanKBQgQ ("Copy of SWBC Write Up for Gio")
  LOBs: FIG/Institutional (LPI, collections, AutoPilot), Insurance (P&C + benefits), Mortgage, Wealth, Swivel payments.
  Sponsor Angelica Palm (CMO). Asks: diversified-FS peer benchmarks, integration/MDM gap, attribution maturity, cross-line roadmap.
- Branch: ccr-ab97efe9-v23ykf (from main @ 9f9d0e5, PR #47 merged)
- Prior session binding (owner-confirmed 2026-09-30): Primary IB + supplementary IC/CL/RIA variant cells; HYBRID; FULL; 760 cells
- Prior spend $86.73 (incl. ~$43 failed category-per-agent workflow); research incomplete

## Objectives under test
- O1 Efficient research, token economy, auto-approved tools (few approval prompts)
- O2 Research matches web-app submission contract; heatmap + evidence linkage built AS research progresses;
     parallel: each pillar -> separate workflow per category (4x4=16). Check how enforced.
- O3 Synthesis then all output artifacts per gold-standard templates

## Environment facts (this container)
- Fresh container: /home/user/dma-runs absent; ~/.dma holds the identity material (names withheld: hook)
- claude CLI, gcloud present; python 3.11; 4 CPUs
- Session tools: Workflow, Agent, ToolSearch present; DMA connector (plugin) bound;
  Exa/Tavily/Clay/Vibe(Explorium)/Indeed/Drive/Firecrawl deferred (bound)

## Issues register (this session)
| ID | Obj | Sev | Where | What | Status |
|---|---|---|---|---|---|
| J-01 | O1 | HIGH | apps/mcp list_pending_runs (deploy) | I-01 code fix not live: connector tool schema takes no args on 2026-10-01 | OPEN |
| J-02 | O1 | LOW | commands/run-assessment.md s5 | "To stop it" paragraph duplicated; "The driver: ... RESEARCH (sixteen lanes ...)" still describes the lanes path, not workflows | OPEN |
| J-03 | O2 | LOW | workflows/dma-pillar-research.js header | Comment says session "runs this once per pillar"; I-58 made it once per category | OPEN |
| J-04 | O1 | LOW | hooks/deny_credential_ops | Denies a heredoc that merely NAMES the key-file / path-token files (writing a QA note). Session 1 kept this as a deliberate control (I-05). Cost: 1 retry. | ACCEPTED (control) |
| J-05 | O1 | MED | commands/run-assessment.md s1; scripts/doctor.py | Command runs `doctor.py --heal` with no DMA_RUN_ROOT right after writing the baseline at <ROOT>; doctor reads the baseline only from DMA_RUN_ROOT -> false FAIL "UNVERIFIED: no baseline" on every run (verified: passes with env set) | OPEN |
| J-06 | O1 | HIGH | scripts/route_client.py; run-assessment s2 | Fresh container cannot find the in-flight run: route_client says READY_TO_SYNTHESISE (old 418-cell connector run), `registry pull` NO_SOURCE (registry never pushed), find-artifact finds nothing. Only a manual pull-backup revealed run_snapshot_CURRENT.json -> DMA-RES-SWBC-20260930-0001. Following the command = synthesise a half run or --fresh (redo $198). | OPEN |
| J-07 | O1 | LOW | commands/run-assessment.md s2 | Names `registry.py pull` as a script; it is `python3 -m engine.registry` | OPEN |
| J-08 | - | - | (withdrawn) snapshot restore did not overwrite this session's baseline | WITHDRAWN |
| J-09 | O2 | CRITICAL | engine/pipeline.py _open_capabilities; workflow batch prompt | Handoff batched only cells with no claim and the prompt said skip closed cells; 35 closed cells in 8 categories blocked by primary_unfired / volleys_incomplete / boilerplate / single_source_fact could NEVER be repaired -> those 8 categories could never pass floors; P3C4 (0 open, 8 boilerplate) got an empty batch list | FIXED: `repair` map {cat:{cell:[terms]}} from the floors gate, repair cells batched, REPAIR_HOW per term in prompt; live: 40 repair cells, P3C4 2 batches |
| J-10 | O2 | HIGH | engine/ledger.py; floors_gate | I-51 placeholder dates still in register (E-055 swbc.com homepage + E-373..378) — no command could re-date or clear a date, no gate caught it. Invariant 9. | FIXED: `engine.cli redate` (+batch op, provenance row), writer refuses public --published == retrieval day unless quoted text states the year (new --anchor-quote), gate term `date_placeholder` (blocking) feeds the repair map; live: all 6 rows routed |
| J-11 | O1 | HIGH | scripts/hooks/stage_advance.py awaiting_workflow | 16 inlined Workflow calls = 10.7 KB; harness persisted hook output and showed a 2 KB preview = 2 of 16 calls visible | FIXED: inline only <= 8,000 chars, else sidecar research_workflow_calls.txt + roster + exact count (971 chars) |
| J-12 | O1 | MED | engine/cli.py _batch | Batch captured stdout only; every refusal prints to stderr -> refused line reported `ok:false, out:""`, reason lost (agent re-runs alone to learn why) | FIXED (stderr captured into `error`) |
| J-13 | O2 | HIGH | engine/workbook.py update_row/update_row_where/set_metadata | openpyxl `ws.cell(..., value=None)` ignores None -> no field could ever be CLEARED (redate --undated reported ok and persisted nothing) | FIXED (.value assignment) |
| J-14 | O2 | HIGH | heatmap.evidence / heatmap.cell_evidence (route `convert`) | Routed "format, no re-synthesis" but NO deterministic converter existed: LLM page producers re-transcribed ~760 cells / ~430 rows at PAGES_A, after SCORING+REPORTS. Research linkage was never rendered or contract-checked while research ran. | FIXED: engine/heatmap_live.py (index contract-validated via scaffold, cell_evidence skeleton with synthesis null, linkage census), built at every RESEARCH/HANDOFF/SCORING boundary ([HEATMAP] log), page brief `prebuilt_sections`, heatmap-evidence-producer told to ship/fill only. 1.7 s per build. Baseline 230/760 linked |
| J-15 | O1/O2 | CRITICAL | ledger.enrichment_binding; driver handoff; workflow prompt | Plugin had no notion of a bound-but-DEAD connector. Exa 402 (credits) + Tavily 429 (blocked, dev key) + Firecrawl 429 all session; markers `connector_exhausted_*` were hand-made in session 1 (01:30) and read by nothing; driver priced + handed off anyway; degraded path refused ("a connector WAS available") -> every empty cell unclosable; 32 agents rediscovered the outage per call. | FIXED: `engine.cli connector-down/up` (401/402/403/429 + provider words) -> 07_qa/connector_health.json; binding degrades only when EVERY required web family is down; absence refusal names --enrichment-unavailable; handoff carries `enrichment_down`; prompt: record once, stop calling, degraded close. LIVE: exa+tavily recorded down 04:0xZ. OWNER ACTION: top up Exa; Tavily production key |
| J-16 | O2 | MED | contract.ENRICHMENT_TOOLS | `internal` (a grep of the intake doc) and `clay` count as the "enrichment connector" an absence must show, so a HYBRID run can satisfy the owner's 2026-09-03 rule without any web enrichment. | OPEN — owner decision (quality bar), not changed |
| J-17 | O1 | MED | workflow prompt; engine.brief dispatch md | Prompt sent every batch agent to `engine.brief dispatch | head -c 4000` for shared.internal_documents; the markdown brief never renders that key (verified 8,972 B, no mention) -> wasted turn + hunt (agent-reported) | FIXED: handoff args carry `internal_docs` paths; prompt lists them, no dispatch call |
| J-18 | O2 | HIGH | engine/orient.py capability_card | Card skipped every synthesised cell and never listed `primary` as owed, and printed questions only for missing facets -> the ~25 primary_unfired repair cells had no card row and no primary question (agent-reported "card shows names only") | FIXED: synthesised cells owing primary/volleys stay on the card flagged repair; `primary` owed; every cell carries primary_question. Live agents pick it up immediately |
| J-19 | QA | INFO | full research_engine pytest suite | ~25 min for 18% on this 4-CPU host under 32 agents; my `timeout 1500` killed it (263 passed, 0 failed before kill) | run targeted files instead |

| J-06 | (update) | | | | FIXED: snapshot push publishes run_snapshot_CURRENT.json; `engine.snapshot current`; restore defaults --run; route_client RESUME (exit 8). LIVE: route_client --client SWBC -> RESUME exit 8 |
| J-02/J-05/J-07 | (update) | | commands/run-assessment.md | | FIXED (doctor with DMA_RUN_ROOT; `python3 -m engine.registry`; dup stop paragraph removed; RESEARCH described as workflows + repair; exit 8 documented; sidecar + connector-down documented) |
| J-20 | O1 | MED | workflow prompt (Clay) | 35 of 38 Clay search-contacts calls failed: agents filtered on job_title / title / latest_experience_title (the RESPONSE field). Filter field is `headline` (verified live: returns Angelica Palm CMO 2026-03) | FIXED (prompt gives the exact DSL) |
| J-21 | O1 | HIGH | engine/cost.py capture_workflows | Counted usage once per transcript LINE; Claude Code writes a line per content block, each with the message's full usage -> 2.4x lines (3,134 lines / 1,307 messages): $139.89 booked for $55.47 spent; USD ceiling trips on phantom spend | FIXED (dedupe by message id; negative delta booked as correction). LIVE: -$84.42 correction; ledger $337.73 -> $253.31. Session-1's 37 agents (~$111 booked) were counted the old way and cannot be recounted (transcripts gone): ledger still overstates by an unknown ~$45-65 |
| J-22 | O1/O2 | CRITICAL | workflow architecture; WebSearch | Built-in WebSearch is 200 calls PER SESSION, shared by every in-session workflow agent. Prompt made WebSearch the primary volley -> 32 agents exhausted it in 18 min ("this session has used its web search budget (200 of 200)", 131 refused). With Exa/Tavily/Firecrawl dead, research had NO search left; batches returned NO_CONNECTORS. Live capacity: 431 queries owed (capability grain) vs 200 per session. | FIXED in plugin: Tavily primary/WebSearch fallback, one query per facet per capability; handoff `search_capacity` (owed vs available) + [WORKFLOW] INSUFFICIENT log; hook says DO NOT START and names the two options (restore provider / lanes --allow-lanes, each lane its own 200). Run itself BLOCKED until a provider is restored or lanes are chosen |

## Live-run log
- 03:2x restore DMA-RES-SWBC-20260930-0001 from Drive snapshot (821 files, 20 s). Recorded spend $197.85; 0/16 categories pass.
- Handoff (pre-fix): 669 open cells, 72 batches, est $134.15. Post-fix: 669 open + 40 repair, 78 batches, est $141.75; handoff now 32 s (one floors gate per category).
- Driver ceiling passed as --max-usd 400 (spent 197.85 + est 141.75 + margin), per owner feedback I-56 (act on the measured figure).
- ~04:05Z launched 16 category workflows in one message (78 batches, 40 repairs): P1C1 wf_e490f65a-10c, P1C2 wf_2ba9a0a4-0ee, P1C3 wf_f7e6496c-13c, P1C4 wf_f1d68f39-2b9, P2C1 wf_9fba60ac-1cb, P2C2 wf_8302343e-73b, P2C3 wf_4623180b-159, P2C4 wf_8cb6040b-c78, P3C1 wf_cfc43bc3-a73, P3C2 wf_63fc7812-52d, P3C3 wf_28c37d0b-453, P3C4 wf_eff4a7c5-573, P4C1 wf_c22e8e7c-20c, P4C2 wf_f4ff37ce-3b8, P4C3 wf_2aa5f6e3-47a, P4C4 wf_6d67746a-91b
  THEN: python3 -m engine.pipeline run --run DMA-RES-SWBC-20260930-0001 --root /home/user/dma-runs/swbc --max-usd 400 ...
- 04:15Z stopped all 16 workflows (TaskStop): every search route dead. Round result (20 min, 32-wide): linked 230->289, absent 30->43, open 500->428, evidence 434->596, placeholder dates 6->0; 40 agents, 1,307 turns, $55.47 at engine rates (Sonnet $2/$10) = ~$0.77 per cell closed (estimate assumed $0.19).
- Agent census (40 agents): Bash 1,232 calls; WebSearch 324 (131 refused at cap); Tavily 238 (429); Exa 43 (all 402); Clay 38 (35 failed DSL); Firecrawl 39 (429/402 improvised); hook denials 3 (shell fetch of the Google Doc, correct).
- 04:17Z driver re-entry: [ENRICH] measured down exa,tavily; [HEATMAP] 289/760; re-handoff 572 open + 41 repair, 69 batches, est $123.51; P3C4 0 batches (repairs landed). Ledger corrected to $253.31.
- DECISION OWED (owner): restore a search provider (Exa credits / Tavily production key) and resume workflows, OR continue on headless lanes (own WebSearch each, REDUCED absence rigour disclosed).
