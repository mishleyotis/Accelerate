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
- Still owed to reach $0.014/cell: the Haiku tier for the mechanical turns
  (log, attach, batch) and the context floor (66k tokens at turn 1 measured
  on Northwest; the CLAUDE.md build charter and 54 skill listings load into
  every research agent). Those two are the next 3–5× — see §6.

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
