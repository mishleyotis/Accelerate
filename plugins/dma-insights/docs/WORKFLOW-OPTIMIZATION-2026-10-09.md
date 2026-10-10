# Workflow optimisation — measured on the runs of 2026-09-25 .. 2026-10-09

Owner's ask (2026-10-09): research for 700+ subcaps under $10 and still
thorough; scoring under $5 with the critic passing first time; reports under
$5 without three rounds; app submission woven into each stage so promotion
is already done when the assessment ends; enrichment at PRELIM budgeted and
reused. This document is the measurement, the root causes, what landed, and
what is still open — each with the number that motivated it.

Sources: 23 Claude Code Remote sessions (2026-09-28 .. 10-09) read through
`list_events`; the Drive run snapshots of Arbor Bank, Susser Bank and Cross
Insurance Agency (`07_qa/cost_ledger.jsonl`, `Gate_Log`, `Search_Log`,
`Challenge_Log`, `report_reviews.jsonl`, `pipeline_state.json`); the
`run_manifest.json` of B1 Bank, First Tech, Susser and Arbor. The mined
reports are checked in under `qa_audit/2026-10-09-workflow/`.

---

## 1. What the runs cost, stage by stage

| run | cells | wall h | USD (engine ledger) | RESEARCH | SCORING | REPORTS | PAGES | research handoffs / FLOORS rounds | critic rounds P1/P2/P3/P4 | report reviews (non-PASS) | page ship attempts |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Arbor Bank (10-05..07) | 708 | 52.1 | **$409** (budget shown as $20, raised to $475) | $254 (62%) | $41 | $74 | $35 | 15 / 212 (164 FAIL) | 11/13/11/11 = 46 | 137 (99) over 19 rounds | 55 |
| Susser Bank (10-05..06) | 708 | 27.1 | **$450** (raised to $510) | $249 (55%) | $49 | $110 | $38 | 8 / 141 (108 FAIL) | 19/21/19/17 = 76 | 154 (118) over 26 rounds | 76 |
| Cross Insurance (10-01..05) | 694 | 9.0 + 4 days | $83 excl. research (research never booked) | not recorded | $42 | $32 | $4 | 2 / 75 (23 FAIL) | 14/13/21/13 = 61 | 95 (56) over 6 rounds | 18; 5 promote attempts |
| B1 Bank (10-08..09) | 708 | 37.8 | **$1,236** (budget shown as $20, raised to $1,150 then $1,500) | n/s | n/s | $192 of workflow spend captured at REPORTS end; 77 workflow dirs | n/s | n/s | n/s | 19 sections, ≥5 `dma-reports.js` relaunches in 25 min | all six pages (re)produced in the resume session; 7 byte-identical resubmissions |
| First Tech (10-05..07) | 691 | 48.7 | session $552 | n/s | 2 pipeline rounds, P3/P4 critic round 7 | 5 rounds, 2290 s | heatmap + techstack re-shipped post-promote (CG-52) | — | 7 rounds on P3/P4 | — | — |
| SWBC (09-30..10-01, four sessions) | 760 | — | ≈$873 across sessions; **no SWBC research run ever reached SCORING** | $253..338 on one run; $73 on a second | — | — | $26 (pages for an old 418-cell run) | r0..r2 then stopped at channel exhaustion | — | — | — |

The budget the engine printed on every one of these runs was **"$20.00 for 4
pillar(s)"**; the owner's actual ceilings were $150 .. $1,500. Research took
55–62 % of the money; reports 18–24 %; scoring ~10 %; pages 8 %.

### Where the research dollars went (Arbor / Susser / Cross)

| measure | Arbor | Susser | Cross |
|---|---|---|---|
| Search_Log rows | 6,332 | 6,319 | 4,999 |
| distinct (query, timestamp) searches | 1,508 | 1,486 | 1,316 |
| rows with Kept = 0 | 78 % | 77 % | 97 % |
| evidenced cells / 708 | 148 (21 %) | 231 (33 %) | 40 (6 %) |
| challenge FAIL / total | 205 / 387 (53 %) | 135 / 363 | 26 / 67 |
| PRELIM evidence rows → cited by a scored cell | 26 → 2 | 26 → 1 | 30 → 0 |
| top floors blockers | challenge_failed 68 · absence_undeclared_empty 62 · single_source_fact 60 · primary_unfired 55 | volleys_incomplete 73 · primary_unfired 57 · absence_undeclared_empty 52 · single_source_fact 50 | volleys_incomplete 11 · single_source_fact 10 |
| first research estimate vs actual | $141.56 → $254 (1.8×) | $141.56 → $249 (1.8×) | $138.90 → not recorded |

The challenge FAIL text was the same four sentences in every run: *"INFERENCE
needs 2+ evidence ids and a named inference"*, *"FACT needs two source
identities"*, *"evidence[] is empty: the claim asserts specific content but
cites no registered row"*, *"cell is in open_contradictions and the
disposition is empty"*. Each cost a Sonnet challenge lane, a repair batch and
a re-challenge.

### Where the scoring rounds went

Every SCORING gate FAIL row — 21 of 21 (Arbor), 36 of 36 (Susser), 29 of 29
(Cross) — carried `dashboard_incomplete=13; rollup_missing=2`: the rollup
refused to write the dashboard without a headline, and only the critic
writes the headline, only after every pillar passes. The stage read FAIL on
a fixed blocker round after round. The critic FAIL notes that remained after
the 2026-10-05 mechanical caps were: the rationale argues M3 for an M2
score; names no gap to the next level; cites E-ids not on the row.

### Where the report rounds went

| REVISE reason class (keyword over the note text) | Arbor | Susser | Cross |
|---|---|---|---|
| citation form / wrong E-id | 57 | 75 | 29 |
| figure does not reconcile with the sheet | 22 | 53 | 25 |
| dates / currency / stale | 31 | 37 | 15 |
| "round fixes landed / unchanged since round" (a repeat) | 52 | 24 | 6 |
| routed upstream (no writer could fix it) | 5 | 3 | 0 |

The writer's brief carried the section's control block and a **list of sheet
names**; the writer re-read the workbook and chose its own citations; the
validator re-derived the same figures a round later. B1 Bank added the other
loop: evidence kept landing during REPORTS (998 → 1,005 rows) and every
whole-report pass reopened 1–2 passed sections on a figure that had moved;
the session's own fix was *"I've stopped registering evidence until both
reports pass."*

### Where the page attempts went

ET-07 (a cited row linked to no cell) was the top page blocker (Arbor 4,
Susser 7 STAGE rows; B1 techstack ×4, overview ×6, context ×4 — *"finding
them page by page cost three separate repair rounds"*). SG-V4 was waived on
every promoted run (budget 8 → 250 / 300 / 257; 620 prose FAILs on B1's six
promoted pages). The two ingest waits idled 1,736 + 2,138 s (Arbor), 1,930 +
1,282 s (Susser), 13 + 1,711 s (Cross) for a Scheduler that fires every 30
minutes. Arbor's 52.1 h wall clock held 16.8 h of recorded work.

---

## 2. Root causes, by the owner's five headings

**Research.** (a) No stage ceiling: one run-wide `--max-usd`, and every
workflow agent's spend was booked to RESEARCH, so no stage could be judged.
(b) The estimate undershot 1.8× and only ever inflated. (c) Challenge rounds
spent judgement on rules a ledger can read (the four sentences above).
(d) PRELIM's rows named no cell, so `reusable()` excluded them from every
proposal: the run paid for the profile, then paid sixteen lanes to re-find
it. (e) Lock: whole-file openpyxl load+save (~2–3 s load, ~1.7 s save on a
1.4 MB workbook; flat ~17–19 writes/min whatever the writer count); the only
measurement of waits was two lease refusals, because nothing wrote a wait
down. (f) Connector exhaustion (WebSearch 200/session, Exa 402, Tavily 432)
kept agents spending while closing nothing — covered by PR #52/#66 already;
the envelope now stops the bleed sooner.

**Scoring.** The dashboard/headline fixed blocker (above); critic rounds
uncapped per workflow (3) and re-handed by the driver (10); the three
remaining critic rules were judgement calls only because nothing refused
them at the write.

**Reports.** Writers chose citations from the whole workbook; validators
re-derived figures; the register moved under the sections; the
cross-section pass reopened sections it had not flagged; each reopening
relaunched a two-round workflow.

**App promotion.** Pass-2 gates (ET-07, CG-40, CG-50) found one page and one
ship at a time; the techstack preflight existed, the other pages' did not;
pages redone after promotion for defects the gates had not caught (SG-V4
waived wholesale); two 30-minute ingest waits per run.

**Enrichment.** PRELIM's connector scans reached the server as
`origin=package` (ET-12 could never pass; worker fix in flight), PRELIM
evidence never reached the research lanes (d), and a resumed session lost
Clay/Vibe, so scans were run twice (B1: "2 scans run twice").

---

## 3. What landed in this change (each enforced, each tested)

| # | mechanism | where | the number it answers | test |
|---|---|---|---|---|
| 1 | **Per-stage envelopes**: PRELIM $2 · RESEARCH $10 · SCORING $5 · REPORTS $5 · PAGES $3, overridable per family (`--stage-budget RESEARCH=12`), persisted on the run, run-wide default = their sum. A stage at its envelope stops as `STOPPED_STAGE_BUDGET` naming the flag; the handoff refuses before a workflow is bought; the workflow invocation carries `budget` and runs one round when the estimate does not fit. | `cost.STAGE_BUDGET_USD`, `pipeline.stage_budget_block`, handoffs, `dma-pillar-research.js` | $409 / $450 / $1,236 against a printed $20 | `test_workflow_optimization_2026_10_09.py` §1–2 |
| 2 | **Workflow agents charged to the stage they worked** (`stage_of_transcript`), one ledger row per family per capture; `cost report` prints `envelopes` and `over_envelopes`. | `cost.capture_workflows`, `cost.report` | every agent booked to RESEARCH | §1 |
| 3 | **Dispatch guard reads the envelopes**: an agent whose family is spent is not dispatched. | `scripts/hooks/guard_dispatch.py` | — | §3 |
| 4 | **Challenge-at-write**: FACT needs two source identities; INFERENCE needs 2+ ids and a named step; FACT/INFERENCE with no id is refused; an open DQ_Contradicts needs a disposition. | `ledger.label_fit_problems` | 205 / 135 / 26 challenge FAILs, four sentences | §4 |
| 5 | **Evidence freeze during REPORTS**: `engine.narrative freeze / thaw / freeze-state`; the driver freezes at REPORTS start and thaws when both reports render; `append_evidence` refuses while frozen and names BLOCKED_UPSTREAM (kind evidence). | `ledger.freeze`, `pipeline._freeze_evidence` | B1 998 → 1,005 rows mid-REPORTS; §8 relaunched twice in 12 min | §5 |
| 6 | **PRELIM evidence reaches the lanes**: rows naming no cell rank in `reusable()` as `from_categories: ["PRELIM"]`; `shared.prelim_evidence` (connector readings first, by ERS, ≤20 rows) rides in every research packet with the attach rule; the research prompt reads it before searching. | `brief.reusable`, `brief.shared`, `dma-pillar-research.js` | 26 → 2, 26 → 1, 30 → 0 | §6 |
| 7 | **Report evidence pack**: each section brief carries the ERS-ranked rows for its inputs (excerpt, cells, tier, recency), the strongest/weakest scored cells with claim, rationale and challenge verdict, and the critic's notes; bounded at 16k chars; the writer prompt cites from it and never re-reads the workbook for citations. | `brief.report_evidence_pack`, `report_section_briefs`, `dma-reports.js` | REVISE "wrong E-id" 57 / 75 / 29, "figure drift" 22 / 53 / 25 | §7 |
| 8 | **Critic rules at the score write**: the rationale must name the level it strikes (M-level or band word) and no higher one; name a gap to the next level under 5.0; cite no off-row E-id. Critic rounds per workflow default 2 (`--critic-rounds`), round 1 samples one row per capability. | `assessment.rubric_problems`, `Options.critic_rounds`, `dma-pillar-scoring.js` | 46 / 76 / 61 critic rounds | §8 |
| 9 | **Rollup without a headline**: the grains and dashboard are written from the scores; `headline_missing` is its own gate term, so a SCORING FAIL reads what is actually open. | `assessment.rollup`, `assessment.gate` | 21/21, 36/36, 29/29 FAIL rows on `dashboard_incomplete=13` | §8 |
| 10 | **Page gates read from the workbook for every page**: ET-07 (a cited row that names no cell) across Tech_Register, Issue_Register, Focus_Areas, Report_Narrative (blocking) and Entity_Timeline (advisory, the connector's stated-exception surface); the workbook floors behind CG-14, S9_focus_invalid and CG-18c; the techstack three unchanged. **And the register links its citations at the write**: `techscan.record` attaches every cited row to the cells the register row names (both ways, through `ledger.attach_evidence`; the scanner is allowed `attach` for this one path), so a techstack row never reaches PAGES with an unlinked citation. | `page_preflight.unlinked_citations`, `page_floors`, `techscan.record`, `pipeline._pages_preflight` | ET-07 top page blocker; B1 three separate repair rounds | §9 |
| 11 | **Lock waits measured**: any wait ≥ 2 s (and every timeout) is written beside the lock as `<lock>.waits.jsonl`; `lock_wait_summary` reads it. | `workbook.file_lock` | "lags" with no measurement behind them | §10 |
| 12 | **Ingest kick**: `--ingest-kick-cmd` / `$DMA_INGEST_KICK_CMD` runs the package scan now (e.g. `gcloud run jobs execute dmai-worker --region us-central1 --wait`) before the poll; never fatal. | `pipeline._kick_ingest` | 1,736 + 2,138 s idle per run | §11 |

Fixtures changed with the rules: the fixture rationale now argues the level
it strikes (`rationale_for`, `absence_rationale`); the run-wide default is
`cost.run_budget_default()`.

---

### Which dollar figure stops a run

Three instruments, one of them the stop (`pipeline.envelopes_binding`):
`--stage-budget STAGE=USD` binds whatever else is set; `--max-usd` is the
owner's single run ceiling and the stop — the run ends `STOPPED_BUDGET` at
the owner's figure and raising it is how it continues, while the envelopes
report their spend (the cost report, the state file, the dispatch guard
read the same `binding` flag) without stopping; a run with no dollar
figure typed is bound by every envelope, which partition the default
ceiling (their sum, $25 on four pillars). `--max-usd 0` switches the
ceiling off, envelopes with it. The cost report judges the ceiling the
driver persisted (`cost.run_budget`), never a default of its own.

## 4. The ideal-state workflow, stage by stage

Each stage has an **entry predicate**, an **envelope**, a **first-time-right
rule set at the write**, and an **exit gate**. Nothing below waits on a human
except the three decisions the engine cannot make (sub-vertical binding,
budget raise, gap waiver).

### PRELIM — $2, one round, the institution before its capabilities
- Connector pass first (Clay company + contacts, Vibe technographics,
  Indeed), banked as `origin=connector` rows and **linked to the cells they
  bear on at registration** (`attach`), so ET-07 and ET-12 are answered here.
- Promotion-readiness census at `prelim complete`: the workbook floors behind
  O7 (two named leaders), C1 (three dated events), O1 (locked peers), H1
  (three focus areas with a quote), ET-12 (machine scan) — the same census
  the driver runs before PAGES, read a stage earlier. *Landed for the
  pages path; wiring it into `prelim complete` as a disclosure is the next
  step.*
- One **category keyword sweep per category** (16 queries, not 700): the
  category's subcap keywords against the entity domain and the trade press,
  logged `--prelim` with the cells it bears on; the research lanes read these
  as `prelim_evidence` and only differentiate per cell.

### RESEARCH — $10 for 700+ cells
Arithmetic: $10 / 708 cells = **$0.014 per cell**. The measured workflow
rate is $0.19 per open cell plus $0.44 per category challenge, so the
envelope forces the design, not the prompt:
- **Capability grain, one discovery pass per capability** (136 passes), two
  differentiating searches per cell, every search logged once per cell it
  bears on (the Search_Log rows that look like 6,332 searches are 1,508).
- **Write-time rules** (#4) so a cell is challenge-ready when written; the
  challenge lane judges synthesis quality and ceiling reasoning only.
- **PRELIM first** (#6): attach before search.
- **One repair round, routed by the gate's own cells**, never a re-dispatch
  of a category; a cell the owner has waived is disclosed, not re-bought.
- **Budget rides with the work** (#1): the workflow reads `budget` and spends
  one round when the estimate does not fit; the guard refuses the next agent
  when the envelope is spent.
- **The research tiers** (owner, 2026-10-09, same day — §9 below): haiku
  collects, sonnet judges; every wave is priced before it starts; whole
  categories are funded end to end or deferred by name. The pilot constant
  is gone from the estimate: `cost.research_price` prices the SHAPE.

### SCORING — $5
- The three scorer refusals and the headline fix (#8, #9) make round 1 the
  round that passes; the critic samples one row per capability and judges
  what a rule cannot (does the evidence show the level argued; is the gap the
  real one); round 2 judges moved rows only; a FAIL after that returns to the
  driver's gate, which names rows.
- The scorer brief already carries the critic's `--move` rows; `score`
  refuses above the target.

### REPORTS — $5
- The register is **frozen** (#5); a fact a writer needs is BLOCKED_UPSTREAM
  (kind evidence), serviced once by the conducting session, and only the
  sections that cite it reopen.
- The writer cites from the **evidence pack** (#7); the validator judges
  weighing, absence rigour, inference honesty and tone — the citation and
  figure checks are the write path's (`narrative.write` already refuses an
  unresolvable id and an uncarried figure).
- Rounds per section 2; a cross-section REVISE names the section and the
  figure; the stall rule counts fixes landed inside a section, not only READY
  sections (open item below).

### PAGES and PROMOTE — $3
- `engine.ship state` + PAGE_NEEDS decide the ship order; `_pages_preflight`
  reads ET-07, the floors and the techstack three for every page in hand
  before an agent runs (#10); `section_precheck.py` runs pass-1 at write time
  (already); `ship_page.py` replays both passes before a submit (already).
- Pages ship to version A as soon as their inputs exist; the ingest is kicked
  (#12), not awaited; version B restages A's pages from disk.
- Still owed: judge a stored SG-V4 verdict against a raised budget without a
  resubmission (B1: 7 byte-identical resubmissions, two of them a 3.4 MB
  heatmap), and the worker fix that carries `origin=connector` + tool into
  `evidence_index` so ET-12 passes on a research-engine run.

---

## 5. Antipatterns → the hook or refusal that stops them

| antipattern (measured) | stopped by |
|---|---|
| a run spends its whole budget in RESEARCH, later stages run "OVER" or stop | stage envelopes; `STOPPED_STAGE_BUDGET`; `guard_dispatch` envelope refusal |
| a workflow is handed again with the same work and no spend landed | `_handoff_guard` (existing) + `not_worked` warning (existing) |
| a FACT on one host, an INFERENCE with one id and no step, an evidence-less claim | `ledger.label_fit_problems` at `synthesise` / `batch` |
| a rationale that argues M3 for an M2 score, names no gap, cites an off-row id | `assessment.rubric_problems` at `score` |
| the SCORING gate FAILs on `dashboard_incomplete` while scoring is in flight | `rollup` writes the dashboard without a headline; `headline_missing` is its own term |
| evidence registered mid-REPORTS reopens passed sections | `ledger.freeze` (driver sets it; writers return BLOCKED_UPSTREAM) |
| a writer cites what it found by re-reading the workbook | the evidence pack in the brief; the writer prompt forbids re-derivation |
| a cited row linked to no cell discovered page by page at the server | `page_preflight` ET-07 before any page agent; advisory for timeline |
| PRELIM profile re-found by sixteen lanes | `shared.prelim_evidence` + `reusable()` PRELIM proposals + the prompt's attach rule |
| a 30-minute idle per ingest | `--ingest-kick-cmd` |
| lock lag nobody can measure | `<lock>.waits.jsonl` + `lock_wait_summary` |

---

## 6. Beyond the ask — ideas with the arithmetic

1. **Context floor is the real per-turn price.** Measured 66,178 tokens at
   turn 1 for every research agent (Northwest), 26.8k on the lane path; the
   repo CLAUDE.md (11.5 KB build charter) and 54 skill listings ride into
   every agent. A research agent needs the command sheet and its packet,
   nothing else. Running research agents under a minimal project context
   (a `CLAUDE.md`-free worktree or an agent definition that clears the
   project memory) is a 2–3× on every turn before any prompt work.
2. **Haiku for the mechanical turns.** `engine.cli batch` lines, `attach`,
   `fetch --via-text` and the Search_Log writes carry no judgement; at $1/1M
   against Sonnet's $3 this is the 0.65 lever `cost.LEVERS` already names
   and has never measured. Tier by COMMAND: a lane composes ops in Sonnet,
   a Haiku sidecar runs them.
3. **An append-only journal under the workbook.** The 1.4 MB xlsx is
   loaded and saved on every transaction; throughput is flat at ~18
   writes/min however many writers. A SQLite journal of (sheet, row, actor,
   at) rendered to the xlsx at stage boundaries removes the serialisation
   and gives the lock waits file (#11) something to converge to zero.
   (OPEN_FIXES item 7; the waits file is the measurement that justifies it.)
4. **Search demand preflight.** 708 cells × (1 primary + 2 differentiating)
   ≈ 2,100 searches against WebSearch's 200/session and the paid connectors'
   plans; `engine.cost lane-fit` should print the demand against the
   connectors' known remaining credit and refuse to start a round it cannot
   finish (Northwest: 402 of 596 WebSearch calls refused).
5. **One connector pass per entity, cached on disk.** Clay/Vibe/Indeed
   responses were not saved (B1: "The Clay result wasn't saved to disk, so
   I'll write the record myself"), so every resume re-bought them. Bank the
   raw response under `01_evidence/connectors/<tool>/<sha>.json` at PRELIM
   and let `register_evidence` read from it.
6. **Judge stored verdicts, don't reship.** A raised `--sg-v4-budget`
   should re-read `verdict_<page>_<version>.json`; a page whose stored count
   fits the new budget passes without a submit.
7. **Idle turns cost money.** 57 stop-hook firings over 12 h (B1, ~$11.66)
   and three routine notifications in 10 s (First Tech) each bought a model
   turn with nothing to do. When the driver state is `STOPPED_STAGE_BUDGET`,
   `AT_USD_CEILING` or `NEEDS_CONNECTOR`, the stage_advance Stop hook should
   say "waiting on a person" once and let the session stop.
8. **Pages that need no report ship at INGEST_A.** `ship.PAGE_NEEDS` already
   says techstack and heatmap need the scored workbook only; context needs
   PRELIM's tabs and the overview's sentiment ordering (O9 before C4) — split
   C4 from the rest of context and three pages ship before REPORTS starts.
9. **A gold-parity dry run at INGEST_A.** `engine.gold_standard package` is
   run at PACKAGE; running the structural half (missing sections, held
   fields) right after scoring would have caught B1's `GS-RPT-NOHEDGE`
   placeholder four hours earlier.

---

## 7. Stress tests run on this change

- `tests/skills/research_engine/test_workflow_optimization_2026_10_09.py`:
  30 cases, every one able to fail (envelopes stop mid-stage and at the
  handoff; a raised envelope is remembered; the dispatch guard; the four
  label-fit refusals and the fixture that still passes; freeze/thaw through
  the library and the CLI; PRELIM proposals and the shared block; the
  evidence pack; the three rubric refusals; rollup without a headline; ET-07
  blocking and advisory; the lock-wait file including a forced timeout; the
  ingest kick's non-fatal failure; the workflows' text).
- The stub chaos walk (`scripts/stress_pipeline_stub.py`, 34 steps through
  the real driver with a stub dispatcher) found the first real defect this
  change exposes: the fixture's PRELIM register rows named no cell, so the
  new ET-07 preflight refused PAGES_A with three blockers — exactly the
  B1 Bank shape, caught before any page agent ran rather than at the
  connector. The fix is where a real run makes the link: `techscan.record`
  links its citations at the write when the scanner names a cell, and the
  research lane that reads `shared.prelim_evidence` attaches the PRELIM
  rows it reuses (`pipeline_stub.lane_research` does so from the first cell
  it works, through `ledger.attach_evidence`); the lane banks its own rows
  before citing PRELIM's (a lane that cites only the institution's rows
  for a cell's figures is refused by the ungrounded-figure rule, as it
  should be). The fixture's PRELIM itself names no cell — a fixture that
  gave a cell evidence by default would contradict every test that declares
  that cell absent, and the ledger refuses an absence over evidence. The walk then
  met the second gate it was built to meet: the H1 floor (three to five
  client priorities) against a fixture that closed PRELIM with one, and the
  degraded lane that declared an absence over a cell PRELIM's rows already
  reached (the ledger refuses an absence over the run's own evidence). The
  fixture now closes PRELIM with three stated priorities, as a real run
  does; the degraded stub lane writes the INFERENCE the institution's rows
  support, at a Building ceiling, instead of an absence. Each of these is a
  defect the old walk would have let a live run carry to the connector.
  Walk result and the suites' counts are recorded in the PR.
- `test_page_preflight.test_the_first_tech_register_is_refused_before_any_page_agent`
  now pins ET-07 beside ET-12 / CG-40 / CG-50 on the first-register shape:
  two unlinked ids, each named with the register rows citing it, neither a
  connector matter.
- Run on this tree (2026-10-09): the stub chaos walk 34/34; the plugin
  audits 376 passed; the acceptance walks 101 passed (one lane-ceiling case
  failed on an earlier head and was fixed before the final run); scoring
  stage + enforcement + audit 50 passed; budget ceiling + optimisation 47
  passed; PRELIM phase, reproductions, KG, unsearched subcaps, actor scope
  and page preflight passed after the three repairs named above. The full
  engine suite runs in CI on the PR's head; its two shards are the record.
- What the suites taught, each now a rule in code: the PRELIM block rides
  in research packets only and gives way before a lead or a cell; a PRELIM
  row is proposed to a cell on two matched terms, never one; the fixture's
  PRELIM names no cell (the lane attaches); an owner's `--max-usd` is the
  stop and the envelopes report; a `raw` score's rationale argues the
  applied level.

## 8. Open, stated

- The SQLite journal (idea 3) and the Haiku sidecar (idea 2) are not in this
  change; both are measured as the next levers and neither is a prompt edit.
- `prelim complete` does not yet refuse on the page census (#10 runs at
  PAGES). The register now links its rows at the write; the remaining
  unlinked PRELIM rows are the identity-grain ones (firmographics, the
  financial series) the connector exempts by name, so the census can be
  wired at `prelim complete` as one call in the next change.
- The worker's `evidence_ids.py` still writes `origin='package'` with no
  `connector_tool` (ET-12 on a research-engine run); B1 shipped techstack
  under a 62-FAIL SG-V4 waiver for that reason.
- The REPORTS stall rule counts READY sections only (OPEN_FIXES, 2026-10-06).

## 9. The research tiers — haiku collects, sonnet judges (owner, 2026-10-09)

**The ask.** "Whether research runs degraded or using connectors, my
expectation is the great batching enables the budget to be as set … Use Haiku
for the research agents and subagents such that they get evidence fast …
ensure all gold standard scoring workbooks are filled eg the excerpts …
efficient subcap clustering through category grain orchestrators that would
now use Sonnet 5 to determine completeness … Or leave at sonnet 5 or use
haiku? Please decide such that we do not end up with poor results … Ensure to
use the gold standard workbook to decide."

**What the first stress test found** (R-IMA-20261009, IMA Financial Group,
686 T1_CORE cells, DEGRADED — Exa 402, Tavily 432):

| reading | value | cause |
|---|---|---|
| RESEARCH estimate | **$137.38** against a $10 envelope | unbatched sonnet pilot constant ($0.19/cell + $0.44/category) |
| RESEARCH envelope "spent" before any research agent ran | **$5.71** | PRELIM's row re-attributed: a dispatcher that records its own cost never moved the driver's recorded marker |
| PRELIM | $5.71 against $2, 98 turns, **122K-token average context**, sonnet | the shape, not the tool: cost = turns × context × rate |
| E-001 | `--published 2026-10-09` on an undated trade-press profile; excerpt a description, not a quote | a sonnet lane; nothing refused it |

**The decision, taken against the gold workbook's row contract**
(`references/templates/gold_reference.json`, `P1_Subcap_Scoring` headers;
`engine/ledger.py SYNTHESIS_REQUIRED`):

| gold row | fields | who can be wrong about it, and how it is caught | tier |
|---|---|---|---|
| **Evidence** | `Excerpt` verbatim 50–500 chars, `Tier`, `Date_Published`, `Recency` (computed), `ERS` (computed: tier · recency · specificity · corroboration), `SubCap_IDs`, `Source_URL` | mechanical. The ledger refuses a non-verbatim span against the fetch cache, a FACT on T3, an own-site T1, a scan below T1, a cell outside the run, an actor outside its category — and now a publication date equal to the retrieval date unless the page states it. Recency and ERS are computed server-side from what the collector supplies, so the collector cannot mis-score them. | **haiku** — `research-evidence-collector`, actor `research-pXcY-collector`, which the scope refuses `synthesis` and `absence` |
| **Synthesis** | `Dominant_Claim` (one checkable thing), `What_We_Found` ≥120 chars, `Triangulation` (the step named), `Ceiling_Reasoning` + `Ceiling_Band` (tier table), `Claim_Label` the excerpts earn, `DQ_Works/Fails/Value/Corroborates/Contradicts`, `Why_It_Matters`, `DMA_Impact`, the declared absence's `--hunted` ladder | judgement. The challenge FAILs on exactly these seven dimensions, and a FAIL buys a repair round that re-pays a context floor. | **sonnet** — `research-category-orchestrator`, actor `research-pXcY-producer` (the category's identity, so the challenge's independence stays checkable) |
| **Completeness** | the floors gate's blocking terms per cell; which cells a repair wave collects for | judgement over the whole category | **sonnet** — the same orchestrator pass |
| **Challenge** | seven dimensions per cell | unchanged | **sonnet** — `research-challenger` |

Why not haiku for synthesis: the measured failure mode of every run in §1 was
not slow collection but syntheses the challenge sent back (212 / 141 floors
rounds). A cheaper first draft that fails more often is not cheaper. Why not
sonnet for collection: 2.0–2.5× on every rate for work the ledger already
polices. The sixteen `research-pXcY-producer` manifests stay sonnet as the
LANE-mode identity (one context that collects and synthesises) and the actor
name the category's writes carry.

**The price model** (`cost.research_price`, `cost.RESEARCH_TIERS`): cost =
turns × context × rate, per tier shape — a collector batch of ≤12 cells is one
open turn (checkpoint + every card of the batch in one `cat`; the driver
writes the cards to `briefs/research_cards/<CAT>/` at handoff) plus two turns
per capability (parallel searches; one Bash that caches text, writes the ops
file and runs `engine.cli batch`); an orchestrator pass is three fixed turns
plus one per ~8 cells; a challenge three plus one per ~10 cells. Degraded or
connector-backed changes the search tool, never the shape, so the price is
the same (pinned: `test_degraded_and_connector_backed_research_price_the_same`).

| 686 cells, 16 categories | projected | per cell |
|---|---|---|
| unbatched sonnet pilot (the old estimate) | $137.38 | $0.19 |
| all-sonnet at the new shape | $36.03 | $0.053 |
| **haiku collectors + sonnet orchestrator + sonnet challenge** | **$26.73** | **$0.039** |
| of which: collection $8.05 · repair wave $1.25 · orchestrator $12.33 · challenge $5.10 | | |

The orchestrator line is the largest because synthesis OUTPUT is irreducible:
686 gold-shaped rows ≈ 340K output tokens ≈ $3.40 on sonnet before a single
reasoning turn. The physical floor of this shape (web text written to cache
+ synthesis output) is ~$6–7; **$10 is not reachable for 686 cells at gold
quality with any tiering**, and the model says so instead of estimating to
the envelope.

**How the envelope is upheld anyway — three instruments, in order:**

1. **At handoff, whole categories or none.** When the estimate does not fit
   what is left of the envelope, the driver allocates the remainder to whole
   categories end to end (collect + synthesise + challenge), cheapest first,
   and lists the rest under `deferred_for_budget` with the flag that funds
   them. On R-IMA-20261009: **$10 funds 6 of 16 categories** (P1C3, P3C1,
   P3C2, P3C3, P3C4, P4C4); 10 deferred, ~$26.73 funds the scope. An envelope
   that funds no category stops the stage `AT_STAGE_BUDGET before dispatch`
   with the cheapest category's price — no agent is paid for.
2. **In the workflow, every wave is priced before it starts.** The handoff
   hands `budget.tier_usd` (collector batch, orchestrator, challenge),
   `budget.share_usd` (the category's own end-to-end estimate) and
   `budget.usd_per_output_token` (blended over the tiers). The governor
   converts `budget.spent()` — the output tokens of every workflow in the turn
   — at that rate and refuses a wave that would cross the run's remainder or
   the category's share. The first wave RESERVES the orchestrator and the
   challenge before it spends a dollar on a collector: evidence with no
   synthesis buys nothing. A refused wave names its cells as
   `unreached_cells` and the category returns `AT_STAGE_BUDGET`.
3. **After the workflows, the ledger.** `capture_workflows` prices every
   agent's transcript into the ledger by stage; the driver's envelope check
   stops the stage when the measured spend crosses the ceiling; the dispatch
   guard refuses the next agent of a spent family.

**Other defects closed in the same change:** PRELIM's spend is no longer read
as RESEARCH's (`_record` moves the recorded marker when the dispatcher books
its own cost); an open cell is never routed as a repair too (48 of P1C1's 47
open cells were, doubling its share); a workflow whose agent type is not bound
in the session (the roster is bound at start — the first live wave failed
three agents at $0 on `agent type not found`) runs the same prompt on the same
model as a plain subagent and says so once.

**Owner levers.** `--collector-model`, `--synthesis-model` (default haiku /
sonnet), `--batch-cells` (12), `--stage-budget RESEARCH=<usd>` (the handoff
prints the figure that funds the scope). `engine.cost report --by-stage` after
the first tiered run replaces every projection above with a measurement, and
`workflow_calibration` corrects the next estimate by the ratio.

**Live measurement — wave 1** (R-IMA-20261009, P3C2, 26 cells, 3 collector
batches, DEGRADED, 12.7 min wall; the new agent types were not bound in the
session, so every agent ran as a plain workflow subagent on its model):

| agent | model | turns | cache read | cache write | ≈ cost |
|---|---|---|---|---|---|
| collect P3C2.1–3 (11 cells) | haiku | 29 | 2.74M | 0.24M | $0.59 |
| collect P3C2.4,5,7 (11 cells) | haiku | 48 | 5.11M | 0.64M | $1.33 |
| collect P3C2.8 (4 cells) | haiku | 47 | 4.62M | 0.36M | $0.93 |
| orchestrate (26 cells) | sonnet | 41 | 4.65M | 0.34M | $1.90 |
| challenge (6 syntheses) | sonnet | 8 | 0.36M | 0.08M | $0.27 |
| **wave** | | **173** | | | **$5.02 → $0.19/cell; 7 of 26 cells closed** |

What it bought: 8 evidence rows, every excerpt verbatim against the fetch
cache at the write, tiers from the ladder (a privacy notice T5, trade press
T3, an AG-filed notice T2), NO fabricated date (4 of 5 undated rows banded
UNVERIFIED; haiku refused to register a breach notice whose affiliation it
could not confirm); 6 syntheses on sonnet that read as the gold row
(HYPOTHESIS labels the excerpts earn, Triangulation naming the step,
Ceiling_Reasoning from the tier table, Activating bands) and PASSED the
independent challenge first time; 1 declared absence; a gap list naming,
per cell, the facets still owed. The gate FAILED on volleys: the collectors
fired one WebSearch per turn, skipped the `primary` facet on every cell and
`fails`/`value` on many, so 19 cells could be neither synthesised nor
declared absent.

Where the dollars went, measured, and the fix for each:

| driver | measured | fix |
|---|---|---|
| **turn-1 floor 73,778 tokens** — the in-session harness (system prompt, tool schemas, CLAUDE.md); the prompt is ~3K; the lane path measured 26.8K | 60–70 % of every turn's context; re-written on cache expiry (turns 1 and 2 both wrote 73.8K) | the largest lever left, and not a prompt edit: on a DEGRADED run nothing in research needs a session connector, so collectors and the orchestrator can run as headless haiku/sonnet lanes with the manifests' `maxTurns` bound (`agent_run.py`), a ~2.7× cut on the floor — next change |
| one search per turn (12 / 25 / 22 WebSearch calls = 12 / 25 / 22 turns) | 4.8 turns per cell against a design of 0.6 | the collector prompt now enumerates the SIX volleys per capability (primary + five facets) to fire in ONE message and log with every cell; cards pre-rendered to disk |
| the orchestrator read engine source for 17 turns to learn `absence`'s required flags (`--proxy-log`, the ladder shape) and the volley rule | 41 turns, half exploration | the exact signature, the ladder JSON and the "a cell missing a facet is a gap, never an absence" rule are in the prompt; "do not read skills/, docs/, engine/" |
| `ungrounded figure '066'` — an E-id in prose read as a number | 6 syntheses refused once, re-written in brackets | `quality._CITATION` strips bare E-ids |
| `fetch` refused `--actor` in batch lines; evidence then had no cache to verify against | 3 lines refused | `fetch` accepts the flag |
| a re-fetch replaced a cached text two spans had been verified against | E-069/E-070 "not verbatim" against their own source | `fetch.store_text` keeps a verified text; the new one lands beside it |
| the ledger charged the collectors to PAGES and the orchestrator to SCORING | RESEARCH envelope $0 after a $5.06 wave | `cost.stage_of_agent` reads the workflow PHASE metadata beside the transcript |
| transcript `usage.output_tokens` is the streamed chunk's (3–8 per message) | every workflow agent since 2026-09-30 priced at ~0 output | `cost._output_tokens` reads the content's length when larger |
| WebSearch payloads 3–7K chars | not a driver | — (degraded is not more expensive per search than Tavily basic) |

**Recalibrated projection** (`cost.RESEARCH_TIERS` now carries the measured
shapes; the orchestrator at ~24 turns assumes the prompt fix): 686 cells ≈
**$81.72 ($0.12/cell)**; all-sonnet collection ≈ $123; the pilot $137.
**$10 funds 2 categories end to end** (the driver handed P3C1 and P3C2 and
deferred 14 by name). After wave 1 was booked ($5.06), the remainder funds
P3C2's second pass alone. The envelope held: nothing was started that the
envelope could not pay for, and the stage stops `AT_STAGE_BUDGET` with the
fourteen categories and the figure (`--stage-budget RESEARCH=82`) named.

**Live measurement — wave 2** (P3C2 again, six-volley prompt live, 2
collector batches + 1 gap-only batch): the two collectors fired 18 WebSearch
calls each and **closed the volley gaps** — P3C2.1.1 and P3C2.7.1 went from
`primary_unfired` + `volleys_incomplete` to primary and all five facets
logged. Two new defects stopped it short of synthesis: the gap-only
collector found its six CLOSED cells on no card (cards covered open cells
only) and did nothing, and the governor, converting the runtime's token
counter at the output-token rate (8–10× too high), refused the orchestrator
pass with $4.94 of envelope left. Both are fixed below. Wave cost ≈ $2.26.
After both waves the driver's arithmetic was exact: $2.66 left, the cheapest
category ~$4.20 end to end, so it stopped **AT_STAGE_BUDGET before dispatch**
and named `--stage-budget RESEARCH=82` — no agent paid for that it could not
finish.

## 10. Findings register — every defect the live waves hit, root-caused

Filed in the connector's findings memory (MEM-0610..0630, read by every
session through `get_memory_digest`) and closed in code with a test, except
where marked OPEN.

| MEM | defect | root cause | fix | test |
|---|---|---|---|---|
| 0611 | estimate $137 vs $10 | per-cell sonnet pilot constant, never comparable to the envelope | `cost.research_price` (measured tiers); whole categories or none | `test_the_tiered_price_is_measured…`, `test_a_tight_envelope_hands_whole_categories…` |
| 0612 | PRELIM's $5.71 read as RESEARCH's | recorded marker moved only on the non-recording path | `_record` moves it for a recording dispatcher | `test_prelim_spend_is_not_read_as_research_spend` |
| 0613 | retrieval date as publication date | nothing refused it | ledger refuses `published == today` unless the span/URL states it | `test_todays_date_is_refused…` |
| 0614 | open cells routed as repairs too | open batches and repairs assumed disjoint | repairs = closed cells only | `test_an_open_cell_is_never_routed_as_a_repair_too` |
| 0615 | new agent type not bound → 3 agents failed | roster bound at session start | same prompt, same model, plain subagent; logged | `test_an_unbound_agent_type_runs…` |
| 0616 | card omits the primary question (25/25 cells failed) | card and gate held the volley rule separately | card owes `primary`; facets from what is owed | `test_the_card_owes_the_primary_question…` |
| 0617 | one search per turn, facets skipped | prompt did not name the six volleys | six volleys in one message, card log lines; verified live in wave 2 | `test_the_workflow_runs_collectors…` |
| 0618 | orchestrator read source for the absence signature | brief omitted required flags | exact command + ladder JSON + "missing facet is a gap" in the prompt | `test_the_workflow_runs_collectors…` |
| 0619 | E-id read as an ungrounded figure | citation strip matched brackets only | bare `E-NNN` stripped | `test_an_evidence_id_in_prose_is_not…` |
| 0620 | `fetch --actor` refused | sheet and parser disagreed | `fetch` accepts `--actor` | `test_fetch_accepts_the_actor_flag…` |
| 0621 | re-fetch overwrote verified text | destructive cache write | verified text kept, new one `.alt.txt` | `test_a_verified_cache_text_is_kept…` |
| 0622 | collectors booked to PAGES, orchestrator to SCORING | transcript-head scan | phase metadata decides (`stage_of_agent`) | `test_a_workflow_agent_is_charged_by_its_phase…`, `test_capture_reads_the_phase_metadata…` |
| 0623 | workflow output priced ~0 | `usage.output_tokens` is the streamed chunk's | max(usage, content length) | `test_workflow_output_tokens_are_read_from_the_content…` |
| 0624 | governor refused a payable orchestrator pass | runtime counter converted at the output rate | measured `RUNTIME_USD_PER_TOKEN` | `test_the_governor_converts_the_runtime_counter…` |
| 0625 | gap-only wave found no card | cards covered open cells only | `_repairs.json` per category | `test_a_gap_only_wave_gets_a_repair_card…` |
| 0626 | 14 never-handed categories "stalled" | stall counted any spend as work on every category | only a handed category can stall | `test_a_category_deferred_for_budget_never_stalls` |
| 0627 | challenger judged truncated claims | packet cut claim 200 / ceiling 160, no triangulation | judged fields whole to 700 chars | `test_the_challenger_sees_the_judged_fields_whole` |
| 0630 | audit saw workflow-read artefacts as orphans | audit ignored `.js` readers | workflows count as code readers | `test_the_shipped_plugin_has_no_orphan` |
| 0610 | `record_finding` returns a raw Postgres error for an engine run id | no input validation before the insert | `memory._uuid_field_errors` refuses by field name (reaches production at the next `infra/deploy.sh`) | `test_a_non_uuid_run_id_is_refused_by_name_not_by_postgres` |
| 0628 | snapshot fails on two client folders | two Drive folders for one entity | owner chose "IMA Financial - DMA" (2026-10-09); `DMA_CLIENT_FOLDER` pins a decided folder by exact name or id for every drive call; snapshot pushed and restored round-trip | `test_the_owners_pin_chooses_and_never_redirects` |
| 0629 | 73.8K in-session context floor per research agent | harness, not prompt | CLOSED by §11: lean headless lanes (6.5K floor measured; ~11.7K live with the manifest) | `test_lean_tiers_2026_10_09.py` |

Also fixed while running the suites: `test_a_scripts_own_subcommand_is_not_read_as_a_shell_verb`
was red on the base branch because the hook ran from pytest's cwd, where the
repo-relative script path does not exist; the test now runs the hook from
the repository root.

## 11. Lean headless tiers — the context floor closed, measured on two whole categories

"Fix the context floor too, run collectors headless" and "I do not see the
workflow" (owner, 2026-10-09). On a DEGRADED run nothing in research needs a
session connector, so `--research-mode auto` (the default) resolves to
**tiers**: every collector, orchestrator and challenge is a lean headless
`claude -p` child (`agent_run.py lean_command`: `--strict-mcp-config`,
`--setting-sources ""`, only the tools the tier uses, the manifest body as
`--append-system-prompt-file`, run from the run directory), and the session
sees ONE persisted workflow per round, `workflows/dma-research-tiers.js`,
whose haiku runner starts `engine.tiers` jobs and reports each category's
phases, dollars and gate. A connector-backed run keeps the in-session
workflow (the only holder of Exa/Tavily/Clay). `--tiers-direct` lets the
driver run the lanes itself (stub, CI, a Routine with no Workflow tool).

**Turn-1 context of one haiku child, measured:**

| configuration | tokens |
|---|---|
| in-session workflow subagent | 73,778 |
| `--agent`, from the repo root | 31,189 |
| `--agent`, from the run directory | 18,344 |
| lean (no MCP schemas, no settings, four tools) | 6,537 |
| lean collector, live (manifest included) | ~11.7K (4,710 written + 7,028 read) |

**Two whole categories, 57 cells each, R-IMA-20261009 (degraded, WebSearch only):**

| | P2C2 (lean, first prompts) | P2C1 (lean, visible, cell-own primaries) |
|---|---|---|
| rounds to floors PASS | 2 | 2 |
| wall clock | 557 s | 617 s + 777 s |
| cost | $1.36 ($0.024/cell) | $2.09 + $1.28 = $3.37 ($0.059/cell) + runner $0.43 |
| syntheses / absences | 4 / 53 | **20 / 37** |
| evidence rows (tiers) | 4 (T3) | **20** (T2 2 · T3 3 · T5 15) |
| per-cell primary queries (distinct) | 10 | **59** |
| absence hunts (distinct) | 2 of 53 | **37 of 37** |
| challenge | PASS | 3 FAIL → repaired → PASS |

P2C1 cost more because it found more: five times the syntheses and evidence
P2C2 found, every absence its own hunt. Round 1 was inflated by the
shared-window defect below (14 cells closed nothing in round 0).

**Defects the P2C1 run hit, each closed at the root:**

| MEM | defect | root cause | fix | test |
|---|---|---|---|---|
| 0631 | 8 parallel collectors walled at the search ceiling; 19 logged searches refused, 14 cells closed nothing | the window was the CATEGORY's; eight conversations shared one actor and one 60-op window | a collector lane's window is its CAPABILITY (`ledger._collector_scope`); a category producer keeps the category's; the search CLI prints the lane's own window | `test_parallel_collectors_each_hold_their_capabilitys_window` |
| 0632 | orchestrator burned 5 turns on one cell's What_We_Found | the anchor rule counted only bracketed `[E-NNN]`; "IMA" is no two-word proper noun; adding a year then tripped the ungrounded-figure rule | a bare E-id and a named domain are anchors | `test_a_bare_evidence_id_or_a_domain_is_a_checkable_anchor` |
| 0633 | orchestrator learnt four write rules by refusal | prompt omitted them | the prompt states `--inferable`+`--validation-question`, cell-registered figures, absence-as-synthesis, the 20-char disposition | `test_the_orchestrator_is_told_every_rule_it_burned_turns_on` |
| 0634 | 19 of 20 evidence rows UNVERIFIED though URLs read /20230406/ and /2024/07/ | `html_text` drops `<head>`; the windows carry no metadata, so a lane could not see the date the page states | `fetch.published_date` (publication meta, JSON-LD, a publication `<time>`, the URL path; never modified/copyright/retrieval) recorded beside the cache, printed by `fetch`, and filled at the evidence write when omitted | `test_the_page_states_its_date_and_nothing_else_does`, `test_an_omitted_date_is_filled_from_the_fetched_page` |
| 0635 | a passing named scope exited FAILED ("0 categories … made no progress") | the workflow branch checked the stall before the scope | `--only-categories` that passes ends `SCOPE_COMPLETE` (exit 0) on both paths; the resume command carries the scope flags | `test_a_named_scope_that_passes_is_scope_complete_not_failed` |
| 0636 | the visible runner's $0.62 booked to PAGES | no stage row for phase `Tiers` | `_PHASE_STAGE["tiers"] = RESEARCH`; the run's three rows re-attributed | `test_the_tiers_runner_is_booked_to_research` |
| 0636 | one runner per category would spend ~$5 a round watching | a runner is an in-session subagent at the session floor ($0.12–$0.31 a round) | ONE runner per round (`_merge_tier_invocations`); `engine.tiers start/wait` take a comma list and print a brief, never the round result | `test_tiers_with_a_session_hand_the_visible_workflow`, `test_one_wait_reports_every_category_in_brief` |
| — | `engine/tiers.py --help` failed the skills audit (and goal status), caught locally before push | relative import ran before the run-by-path guard | guard first | `test_the_audit_exits_zero_at_the_pinned_backlog` |

**Price model refit** (`cost.LEAN_SHAPES` on three measured orchestrator and
challenge passes; the lean repair wave 25% with its re-challenge): a 57-cell
category projects **$2.17** (measured $1.36 and $3.37); **686 cells ≈ $26**
plus ~$0.3 a round for the runner. The in-session projection was $81.72 and
the pilot $137 — lean tiers cut research cost by ~3×, and the quality per
dollar rose with it.

**The $10 envelope at full scope, stated.** $10 funds about four 57-cell
categories end to end. The allocator hands whole categories cheapest first
and names the rest under `deferred_for_budget`; nothing is started that the
envelope cannot finish, degraded or not, so the budget is UPHELD by
construction. Covering all 686 cells of a T1_CORE scope at the quality above
takes ~$26 (`--stage-budget RESEARCH=26`), or a narrower scope. That figure
is the owner's decision, not the driver's.

## 12. "I never saw the workflow" — four root causes, measured, closed

The owner's question, answered from the sessions themselves (31 sessions
2026-09-28..10-09 by origin; nine DMA run sessions audited event by event)
and the product documentation.

| # | cause | evidence | fix | MEM |
|---|---|---|---|---|
| 1 | **The surface.** 27 of 31 sessions, and every DMA run session, are followed from the Claude Android app; workflows render in the CLI, Desktop and IDE (`/workflows`), and phone progress is documented only for Remote Control sessions | `list_sessions` origin; code.claude.com/docs/en/workflows, /remote-control | every `engine.pipeline run`/`status` ends with an **OWNER UPDATE** block (spend vs ceiling and each envelope, categories passing/failing, what is handed and how it is worked, next command; also `07_qa/progress.md`); the stage_advance hook makes the session relay it verbatim at every handoff and `then` | 0637 |
| 2 | **The tool drops on a resume.** "No such tool available: Workflow. Workflow is disabled for this session" (SWBC 10-01 08:10); "The session restart removed the Workflow tool" (B1 10-08 17:37, then `--pages-mode lanes --allow-lanes`); Cross 10-01 and Arbor 10-06 the same | session events | step 1's tool baseline lists built-ins and records `workflow_tool`; a resume re-records it; a degraded run whose session holds no Workflow runs research as driver-run lean lanes (`--tiers-direct`) instead of handing a workflow nobody can start, and says so | 0639 |
| 3 | **Silent substitution.** The hook said "STOP and restart, never substitute agents", the skill and driver said "do not restart, run the prompts as agents"; neither told the owner | grep of the plugin | one rule, every stage: tell the owner in one line, then the stage's fallback; a handoff worked by in-session agents writes `HANDOFF_<STAGE>_WORKED_VIA` WARN and shows in the update | 0639 |
| 4 | **Unpriced substitutes.** In-session agents' transcripts (`subagents/agent-*.jsonl`) were never captured: R-IMA-20261009's PRELIM relay agent, $8.85 over 158 turns, never booked — the run read $18.41 of $25 while it had spent **$27.26** | the agent's own usage | `capture_workflows` prices an in-session agent whose PROMPT names the run, at the stage its description names (else its agent type), `via` recorded | 0638 |

Also: before 09-30 (research), 10-05 (scoring), 10-06 (reports, pages) the
stages ran as driver lanes, never as workflows — the 10-01 runs and Susser's
two-hour report round ("I see that the report round does not use
/workflows") predate the handoffs. And two driver verdicts (`PASS_SCOPE`)
had never reached the Gate_Log: the ledger refused them and `_record`
swallowed the refusal; `PASS_SCOPE` and `WARN` joined `GATE_VERDICTS` and a
test scans every verdict the driver writes (MEM-0640).
