---
description: Run one client's Digital Maturity Assessment end to end — preflight the binding with the person, then drive research, scoring, reports, pages and promotion through engine.pipeline — from any session, or resume a stopped run.
argument-hint: "<Entity name>" [--entity-id <slug>] [--website <url>] | --resume <RUN_ID>
---

Run — or resume — one client's DMA. You are the person's counterpart for the
one decision a machine may not take (the binding); everything after it is
`engine.pipeline run`, a command that walks fourteen stages gate by gate,
dispatches every lane over a brief it writes, ships pages to the connector as
the work becomes ready, and promotes as its last call. Do not narrate stages
the driver runs; run the driver.

The engine is `${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/`; every
`python3 -m engine.…` below runs from `${CLAUDE_PLUGIN_ROOT}/skills/dma-research`.

## 1 · Tooling first, measured, never assumed

**Your connectors are measured, not typed.** Since 2026-10-10 the session's
own transcript names every MCP tool it holds (`scripts/session_roster.py`
folds Claude Code's `deferred_tools_delta` records, including a connector
that drops mid-session), so there is nothing to transcribe — Interac's
session typed 334 names by hand and abbreviated whole families on the first
try. The doctor judges that roster before any run root exists, and
`engine.pipeline run` writes it as the run's baseline at PREFLIGHT
(`connector_contract.ensure_baseline`, `sources: ["transcript"]`). Check it
in one line:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/connector_contract.py" check --from-session --strict
```

Type a list ONLY to add what the transcript cannot see — the built-ins,
because whether this session holds `Workflow` decides how research runs —
and it is unioned with the measured roster, never instead of it. **A resumed
session re-records** (a resume or worker restart can drop the Workflow tool;
SWBC and B1 lost it mid-run): `printf 'Bash\nRead\nAgent\nWorkflow\n' |
connector_contract.py baseline --tools - --root <ROOT>`, leaving `Workflow`
out if you do not hold it. A degraded run whose baseline says
`workflow_tool: false` runs research as driver-run lean lanes. When
`check --from-session` says NO SESSION ROSTER (tool search off), fall back to
typing every tool you hold:

```bash
printf '%s\n' <every tool name you hold> \
  | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/connector_contract.py" baseline --tools - --root <ROOT>
```

`--strict` is not optional. Without it a STOP still exits 0 and the gate
passes a session with no connectors at all — which is the exact
condition it exists to catch.

**You are the connector tier.** Since 2026-09-14 the enrichment connectors
are held by this session and by no lane: they bind once, at session start,
and every category lane is a separate `claude -p` child that holds none of
them. A lane emits `search_requests`; the driver batches them; you service
each batch with one fresh in-process subagent, which inherits your
connectors. So the baseline you just wrote is not paperwork — it is the run's
only statement of what enrichment is reachable at all.

What the verdicts mean for the run, which is not what they meant before:

| Verdict | What it is | What to do |
|---|---|---|
| No baseline and no readable roster | Nothing knows whether a cell can be enriched or honestly declared absent | `engine.pipeline run` **REFUSES** at PREFLIGHT before a single lane is dispatched. Write the baseline by hand (above). A session whose transcript names its tools is never here — PREFLIGHT adopts that roster. |
| Baseline short — families missing | A measured, disclosed limit | The run proceeds **DEGRADED**: it records `enrichment_degraded`, its lanes are told to close cells with `engine.cli absence … --enrichment-unavailable`, and the ENRICHMENT gate discloses the gap per category rather than re-dispatching against it. This is not a stop. |
| Baseline complete | Enrichment is reachable through you | Ordinary run. |

Report which families are missing and that a human attaches them on the
Routine's own edit screen — then start the run anyway and say it is degraded.
Measured 2026-09-12: a run started without Exa or Tavily could not declare a
single cell absent, so no floors gate could pass, and it re-dispatched sixteen
categories ~18 times for $96.65 and closed nothing. The degraded path exists
so that never repeats; refusing to start is not the remedy, and neither is
starting silently.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/doctor.py" --heal
cd "${CLAUDE_PLUGIN_ROOT}/skills/dma-research" && DMA_RUN_ROOT=<ROOT> python3 -m engine.pipeline env
```

`doctor.py --heal` repairs a STALE / MISSING / DIVERGED install and re-checks
once. Its `installed plugin` row judges the tree this session actually BOUND
(measured; on a directory marketplace that is the checkout in place, and a
lagging install record is cosmetic), and since 2026-10-10 it judges CONTENT:
the SessionStart hook fingerprints what the session bound, so a branch
switched and switched back — Interac's `git checkout` of a stale default
branch, then a fast-forward to the commit it started on — reads OK. The same
hook fast-forwards that stale local default-branch ref in the background
(`git_refs.py`, never the checked-out branch, never the worktree), so a
checkout of it lands on the tip. **Do not switch branches to "get current"**:
the session's own branch is cloned at the tip. `UPDATED_MID_SESSION` now
means bound files really differ (the row names them) and THIS session holds
the old roster — carry on, because the driver dispatches every lane as a
fresh child process that binds the current tree. Its `connector contract`
row reads the run's baseline, else this session's transcript: UNVERIFIED
means neither is readable, and a short roster is the DEGRADED row of the
table, not a provisioning defect. `[warn]` rows are cosmetic — the
`live tool roster` row warns when the manifest's "(N tools)" lags the
deployed connector (`manifest_counts.py --write` in a PR fixes it; CI fails
a PR that forgets) — and never a reason to stop or to ask the owner. Any
row reading FAIL after the heal is a provisioning defect: report the row
and stop.

Pillar toolkits (the per-subcap diagnostic questions) are pulled by the KG
stage into `<ROOT>/toolkits` when `DMA_TOOLKITS_DIR` is unset; set it only to
pin a local copy.

`engine.pipeline env` names every hard dependency (the claude CLI, a
connector identity rung, the **enrichment-connector baseline** you just wrote,
`agent_run.py`, `ship_page.py`, `mcp_raw.py`, `drive_fetch.py`, the pinned
templates against the manifest); a hard failure stops you here, with the
check's own fix line.

## 2 · Route the name before you prepare anything

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/route_client.py" --client "$ARGUMENTS" --json
```

When the person asked for a NEW run of a client the corpus already holds,
add `--fresh`: exit 7 NEW_VERSION is yours, and starting the run supersedes
the folder's previous package in place (`drive_fetch.py archive-remote`, run
by `open_folder` before its first push — moves, never deletes).

Obey the exit code: 4 NEW_ENGAGEMENT is yours; 3 NEEDS_SCORING means the
research package exists and scoring is the missing step (`engine.pipeline
plan` on that run tells you where it stands — resume it, do not restart);
0 READY_TO_SYNTHESISE and 5 ALREADY_SERVED are the synthesis lane's, stop and
name the run (and when the JSON says `partial: true`, say the run is
half-assessed and offer `--fresh`); 6 AMBIGUOUS — report the near matches, never guess; 8 RESUME_IN_FLIGHT — the intake folder holds a run snapshot the connector cannot see yet: restore it (the command it prints) and continue at step 5, never start a new run; 2 is the
script failing, which is not a routing answer.

Then the three places work already exists, before any research
(`python3 -m engine.registry pull` + `python3 -m engine.registry list
--open-only`, from `${CLAUDE_PLUGIN_ROOT}/skills/dma-research`; `drive_fetch.py
find-artifact --client "<Entity>"` and its `run_manifest.json`;
`get_client_state`). An open run or an IN_PROGRESS manifest is a run to
RESUME: `python3 -m engine.pipeline plan --run <RUN_ID> --root <ROOT>` says
where it stopped, and step 5 continues it. With `--resume <RUN_ID>` you skip
straight to step 5 — after step 1's tool baseline, which a resume always
re-records.

## 3 · Preflight the binding — with the person

```bash
python3 -m engine.preflight init --entity "<Entity>" --entity-id <slug> --out <ROOT>/preflight.json
```

Fill it in this order and nothing else counts: (a) read the financial
statements — call report, annual report, 10-K or statutory filing — and put
the REVENUE LINES into `financials.revenue_lines`, each with the line of
business it implies (or the search ladder in `financials.not_run`); (b)
census the lines of business, and give every plausible sub-vertical an
ACCEPT or REJECT with a reason; (c) **ask** — put the sub-vertical and scope
in one `AskUserQuestion` and the evidence mode in another, and record the
answers verbatim with who answered and when. Then
`python3 -m engine.preflight check --file <ROOT>/preflight.json`
lists every remaining problem at once.
**Multi-LOB.** The binding has ONE primary `sub_vertical`, whose variant
cells replace the universal cells they vary. When the owner wants other
ACCEPTed lines of business covered too, offer it in the same question: each
named one goes in `binding.supplementary_sub_verticals` AND, verbatim from the
answer, in `binding_question.answer_supplementary_sub_verticals`. A
supplement adds only its own variant (tier-2) cells, additively — nothing
universal is researched twice. The skeleton's `_row_shapes` shows every
row's keys.

**HYBRID / INTERNAL.** Land every internal document before starting:
`python3 -m engine.intake add --root <ROOT> --file <doc> --title '<title>'
[--source-url <where it lives>]`. PREFLIGHT refuses a HYBRID/INTERNAL run with
an empty `01_intake/`, every lane's brief lists the documents, and HANDOFF
refuses a run that registered no `--origin internal` evidence.

Where the census leaves exactly one reading, `engine.preflight autobind`
may bind PUBLIC mode and record that nobody was asked and why; where it is
ambiguous it refuses, and that is the answer — never hand-write the binding.

Push the answered preflight to the client folder so a headless firing can
reuse it rather than ask again:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/drive_fetch.py" push-package --client "<Entity>" --file <ROOT>/preflight.json --name preflight.json`.

## 4 · Start, and state the cost before spending it

```bash
python3 -m engine.cli start --run <RUN_ID> --root <ROOT> --entity "<Entity>" --entity-id <slug> \
        --reference-date <YYYY-MM-DD> --preflight <ROOT>/preflight.json
python3 -m engine.cost estimate --run <RUN_ID> --root <ROOT>
python3 -m engine.cost schedule --run <RUN_ID> --root <ROOT>
```

`start` derives sub-vertical, scope and mode from the preflight, opens the
`<Entity> - DMA` folder at `status: IN_PROGRESS`, registers the run and binds
the pinned templates. It refuses on a stale install and on a zip that
predates its templates; a refusal is a stop, not a flag to add. Report the
estimate and the schedule (a run projected over $5 per pillar is reported
over budget, with the figure) before the next command.

## 5 · Run the driver, and watch it

```bash
python3 -m engine.pipeline run --run <RUN_ID> --root <ROOT> --max-wall-min 240 --lane-retries 1 --page-retries 2
```

**SCORING runs as persisted workflows too — one per pillar.** At SCORING the
driver stops `AWAITING_WORKFLOW` and writes `<ROOT>/07_qa/scoring_workflow.json`
(workflow `/home/user/Accelerate/plugins/dma-insights/workflows/dma-pillar-scoring.js`,
one `args` per pillar still owed). Start every invocation in ONE message; each
pillar's scorers run in parallel, its own critic starts the moment they finish,
and the critic's `--move CELL:TARGET:why` rows go straight back to that pillar's
scorer (`engine.assessment moves`). Then run the file's `then`. The engine
refuses, at write time, a score above the row's own Ceiling_Band, above 2.0 on
own-site-only evidence, a stale row without ADJ_STALE, and STALE_DATA above LOW
confidence — so the critic judges what a rule cannot. No Workflow tool in this
session (a resumed session loses it)? `--scoring-mode lanes` is sound: scoring
needs no connector. Never re-score rows by hand.

**REPORTS runs as persisted workflows too, one per report.** At REPORTS the
driver first runs a preflight that refuses on blockers no writer can close: a
locked peer set below the template's floor (its size above it is the run's
own decision, never a refusal), or unscored cells. It names them in
`REPORT_PREFLIGHT`; fix them at source and resume.
Then it stops `AWAITING_WORKFLOW` and writes `<ROOT>/07_qa/reports_workflow.json`
(workflow `workflows/dma-reports.js`, one `args` per open report), and you
start every invocation in ONE message. Each open section is written by its
report's producer and reviewed by `report-validator` on its own track, with no
round barrier, and a writer touches only its section. A review that names an
upstream item (`--upstream probe|sheet|evidence|owner|scores: …`) takes that
section out of the loop and returns it to you. Service each one (a probe
through `enrichment-web-specialist`, a sheet or evidence fix through its
engine command, an owner decision with the person, scores through the pillar
scorer and its critic), then run the file's `then`. With no Workflow tool,
the handoff's `agent_prompts` holds the same prompts for in-session agents.
`--report-mode lanes` keeps the old round loop, which now also stops the
moment every open section waits upstream. The same open sections, statuses and
reviews handed again across `--stall-rounds` handoffs stop the stage (the
loop guard below). A template's LENGTH upper bound is measured and reported
back on every write (`length_notes`), never refused. Measured at Arbor Bank (2026-10-06):
whole-report lanes behind a round barrier took 430 min, 19 rounds and 137
reviews, and a third of the returns were upstream items the writer could not
close.

**PAGES_A and PAGES_B run as persisted workflows too — one per ship group.**
At each page group the driver ships whatever page section files are already
on disk, then stops `AWAITING_WORKFLOW` with `<ROOT>/07_qa/pages_workflow.json`
(workflow `${CLAUDE_PLUGIN_ROOT}/workflows/dma-page-production.js`). Every page
of the group runs its own chain side by side: per-surface producers in
parallel, then the finding-challenger and page-consolidator on the produce
sections, then the page's surface-producer assembles. A page that failed its
verdict comes back as a REPAIR (assembler alone, with the verdict's reasons)
until `--page-retries` ships are spent. The workflow never submits or promotes:
run the file's `then`, and the driver ships, hands back failures, and promotes.
No Workflow tool? `--pages-mode lanes`.

**The machine technographic scan is banked at PRELIM, and pages are
preflighted.** PRELIM's technology baseline does not sign off until a Clay Tech
Stack and a Vibe Prospecting technographic reading are registered as connector
evidence and cited on the rows they detect, or both are declared
`python3 -m engine.page_preflight not-run --tool clay|vibe --reason …`. Those
connectors are bound at PRELIM; by PAGES_A a resumed session may hold neither.
Before PAGES_A or PAGES_B dispatches any page agent, the driver reads the
techstack page's ET-12, CG-40 and CG-50 against the workbook
(`engine.page_preflight check`). A blocker that needs a connector stops the run
`NEEDS_CONNECTOR`, naming the tools. The watchdog reports
`NEEDS_CONNECTOR_SESSION` and never revives it in place: resume in a session
that holds them.

**Nothing loops.** Every workflow stage passes one guard
(`<ROOT>/07_qa/handoff_guard.json`): the same work handed with nothing moved
across `--stall-rounds` handoffs, or more than `--max-rounds` handoffs, stops
the stage FAILED with its blockers named. A fired guard STAYS fired — re-running
the driver (by you, the watchdog or a cron) does not buy the workflow again —
until what it measures changes (a repair at source) or a person passes
`--reset-guard`. The watchdog reports a handoff a dead session was holding as
`AWAITING_WORKFLOW` and its `--revive` hands the Workflow calls to the session
that ran it; a handoff still receiving writes reads `WORKFLOW_RUNNING` and is
left alone.

**Peer figures come from the sub-vertical cohort.** Before SCORING rolls up,
the driver fills every blank `Peer_Benchmarks` figure from the connector's
`get_cohort_benchmarks`: the mean of every other assessed entity in the
sub-vertical (active promoted runs, floor of three, aggregates only). The
locked peer set is identified, not scored; peer metrics are researched only on
the run's focus areas (`relay.report_probes`).

**RESEARCH runs as persisted workflows — started by you.** The driver is a
Python process and cannot start a Workflow, so at RESEARCH it stops with
outcome `AWAITING_WORKFLOW` (exit 0) and writes
`<ROOT>/07_qa/research_workflow.json`: the workflow
(`${CLAUDE_PLUGIN_ROOT}/workflows/dma-pillar-research.js`), one `args` object
PER CATEGORY still to pass, and a measured `estimate` (open cells, batches,
USD, and whether it fits `--max-usd`). In ONE message, start every invocation
— `Workflow({scriptPath: <workflow>, args: <invocation>})` per category.
Concurrency is capped per workflow (min(16, CPUs−2)), so sixteen category
workflows are what makes research parallel; inside each, the category's open
cells run as capability batches of ≤ 12 cells, each a fresh **haiku**
`research-evidence-collector` (searches, verbatim spans the fetch cache
verifies, tiers, stated dates — no judgement), then one **sonnet**
`research-category-orchestrator` pass judges completeness from the gate
summary and the evidence pack and writes every synthesis and declared
absence, a gap-only collector wave repairs what it names, then the independent
challenge and the floors gate (2026-10-09, decided against the gold workbook).
Every batch writes through ONE `engine.cli batch` per capability (one workbook
load, lock and save instead of ~10 s per command under the run-wide lock).
**Every wave is priced before it starts** against the RESEARCH envelope and the
category's own share (`budget` in the handoff); when the estimate does not fit,
the driver hands whole categories end to end, cheapest first, and lists the
rest under `deferred_for_budget` with the `--stage-budget RESEARCH=<usd>` that
funds them — a deferred category is a decision for a person, not a loop. The agents
run in THIS session and hold Exa, Tavily and Clay themselves; one that finds
none stops and returns `NO_CONNECTORS` — except on a DEGRADED run, where the
driver passes `degraded: true` and the agents search with WebSearch and close
cells with `absence --enrichment-unavailable` instead of stopping. When all have returned, run the
file's `then` command: the driver prices the workflow agents into the cost
ledger (so the ceiling sees them), re-reads the floors gates, re-hands only
categories still failing — and says so if the last handoff was never worked.
**No Workflow tool? Do not restart — and tell the owner first.** A resumed session can lose it; say so in one line ("this session has no Workflow tool; running RESEARCH as in-session agents") before the substitute starts, because nothing of it will show as a workflow. The
handoff's `agent_prompts` names a directory of the SAME batch and challenge
prompts, rendered from the workflow's own source
(`workflows/render-prompts.mjs`), with a `manifest.json`. Spawn one in-session
Agent per `batch` row (its file's text as the prompt, `model` and
`subagent_type` from the row), all in one message; when a category's batches
have returned, spawn its `challenge` row; then run `then`. Same work, same
tier, same tools — no new session. `--research-mode lanes` stays refused with
the real dispatcher unless `--allow-lanes` waives it, because lanes hold no
connector and cannot pass a gate.

**A DEGRADED run researches as lean headless tiers** (`--research-mode auto`,
the default, 2026-10-09). Nothing in research needs a session connector when
there is none, so every collector, orchestrator and challenge runs as a lean
`claude -p` child at a ~6.5K-token floor (the in-session floor is 73.8K), with
its exact cost booked. The handoff names `workflows/dma-research-tiers.js` and
ONE invocation for the round: start it, and its haiku runner starts every
category's job (`engine.tiers start`) and waits on them (`engine.tiers wait`),
reporting each category's phases, dollars and gate in /workflows. The lanes
are watchable live with `agent_run.py watch --log-dir <ROOT>/agent_logs`;
`python3 -m engine.tiers status --run <R> --root <ROOT>` reads the jobs. Then
run `then`. `--only-categories P2C1,P4C3` narrows the stage (a pilot); a
passing scope ends `SCOPE_COMPLETE` (exit 0) and a run without the flag
continues the rest. `--tiers-direct` lets the driver run the lanes itself
(a Routine with no Workflow tool). Measured 2026-10-09: ~10 minutes and
$1.4–$3.4 a 57-cell category; Interac 2026-10-10: $0.059/cell and 0 of 5
categories passing, which is what made every lane carry `--max-budget-usd`
at its priced shape, a collector's search window its capability's cells + 5
facets + 3, and a repair route to the tier that can close it (§13 of the
optimisation doc). Measured the same day: every WebSearch request bills
$0.01 inside the lane's cost — 77% of a disciplined collector lane — so the
gold contract's ~1,340 searches for 686 cells are ~$13 of fees before a
token is written. At the enforced shape a 43-cell category is ~$1.7 end to
end and the 686-cell scope ≈ $27; the owner set the RESEARCH envelope to
**$28** (2026-10-10, "keep gold") so a 16-category pass fits one run with
every rule kept. A tighter `--stage-budget RESEARCH=<usd>` funds whole
categories cheapest first and names the rest; funding Exa, relaxing a
volley rule, or narrowing the scope (`--only-categories`) is the owner's
call, never the driver's.

**Where the owner sees the run: the conversation.** The owner follows DMA
sessions from the Claude app, and a workflow's progress view (`/workflows`)
renders in the CLI, Desktop and IDE, not in a cloud session on the phone
(measured 2026-10-09: "I never saw the workflow"). So every `engine.pipeline
run` and `status` ends with an **OWNER UPDATE** block (spend against the
ceiling and every envelope, categories passing and failing, what is handed
and how it is being worked, the next command; also `07_qa/progress.md`), and
you put that block in your reply verbatim at every handoff and every `then`
(the stage_advance hook reminds you). When a workflow returns, relay its
per-category lines the same way. A handoff worked by in-session agents
instead of a workflow is recorded as a `HANDOFF_<STAGE>_WORKED_VIA` WARN row
and named in the block, and its agents' spend is captured into the ledger
like a workflow's — never silent, never unpriced.

**The run survives a fresh container.** The driver snapshots the run
(workbook, evidence, QA, briefs; not transcripts) to the client's Drive
`memory-backup` folder at every stage boundary. On a new container, restore
before resuming: `python3 -m engine.snapshot restore --run <R>
--client "<Entity>"`.

**The ceilings are enforced now, and they are the defaults** — name them only
to change them. `--max-usd` defaults to $5 per pillar in scope and STOPS the
run when the cost ledger crosses it; `--max-rounds 10` caps the rounds of any
looping stage; `--stall-rounds 2` ends a stage after two consecutive rounds
that advance nothing; `--max-wall-min 240` is a clean stop, not a failure;
`--enrichment-heals 1` is how many fresh lane instances a category with no
connector search gets before the gap is disclosed instead of worked again.
None of these was enforced before 2026-09-12, which is how one run reached
$96.65 against a $20 budget while closing nothing.

**`STOPPED_BUDGET` is a decision, not an error to retry.** The run exits 1,
the spend is remembered on disk, and a re-run REFUSES before dispatching
anything — a second process does not get a second budget. The hourly watchdog
reports it as `AT_USD_CEILING` and will not revive it. Read
`engine.cost report --by-stage`, decide whether the remaining work is worth
it, and continue with a higher `--max-usd` — that raise is the decision, and
it is a person's.

Run it in the background and watch with
`python3 -m engine.pipeline status --run <RUN_ID> --root <ROOT> --watch` and
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/agent_run.py" watch --log-dir <ROOT>/agent_logs`.
The driver: PRELIM → KG → RESEARCH (sixteen lanes over `engine.brief`
packets, challenge lanes, the floors gates; a FAILED category is re-dispatched
with the handback and the gate's blocking terms, a PASSED one never) →
HANDOFF → SCORING (four pillar lanes, the solutions duty, the critic, the
rollup, the SCORING gate) → INGEST_A (the scored checkpoint pushed; the scan
ingests it) → REPORTS (the section workflow: a writer and a validator per open section,
then a whole-report cross-check, into the pinned Docs,
rendered into the branded shell) → PAGES_A (techstack and heatmap shipped to
version A through `ship_page.py --claim`) → PACKAGE (technographic scan,
`assemble package`, the gold gate) → INGEST_B → PAGES_B (the A pages restaged
from disk; overview, insights, platform, then context) → PROMOTE. Every stage
lands `STAGE_<NAME>` in Gate_Log with its wall clock and a cost-ledger line.

**Service the orchestrator briefs — they are yours.** The driver's lanes hold
no enrichment connector, so connector work comes back to you as prompt files,
announced in the log with `[RELAY]`: PRELIM writes
`briefs/prelim_r<N>/prelim-connectors.orchestrator.md` (leadership,
firmographics, peers) and waits for those sections; each research round
writes its relay batch under `briefs/relay_r<N>/`. For each, spawn ONE
in-process subagent (`enrichment-connector-specialist` for PRELIM,
`enrichment-web-specialist` for relay rows) with the file as its prompt — it
inherits your connectors. Run them on the fast tier (`model: sonnet`) and group
the batches by pillar — four subagents, not one per file: relay service is
spend the run's cost ledger never sees (measured 2026-09-30: ~1M subagent
tokens for 66 requests on the conducting session's own tier). Watch with
`tail -F <ROOT>/pipeline.log | grep --line-buffered '\[RELAY\]\|FAIL\|STOPPED'`.

**To stop it, use `python3 -m engine.pipeline stop --run <RUN_ID> --root <ROOT>`**
— it signals the pid that holds the run's driver lock. Never kill a pid a shell
captured for `nohup setsid …`: setsid forks, that pid is a dead wrapper, and the
real driver keeps spending (measured 2026-09-30: a whole extra round, past budget).

**To stop it: `python3 -m engine.pipeline stop --run <RUN_ID> --root <ROOT>`.**
It signals the pid that holds the run's driver lock. Never kill a pid a shell
captured for `nohup setsid …`: setsid forks, that pid is a dead wrapper, and the
real driver keeps spending (measured 2026-09-30: a whole extra round, past budget).

When it stops: a stage FAIL names the blocker (read `engine.pipeline plan`
and the stage's Gate_Log detail, repair at the source it names, run again —
nothing done is redone); `--max-wall-min` reached is a clean stop, run again;
a refused claim means another session holds the run's lease, wait for it to
lapse. Never `--force` anything and never waive the install check without
saying so in the report.

## 6 · Report

`python3 -m engine.cost report --run <RUN_ID> --root <ROOT>` — per-stage wall
clock against the schedule, USD against the budget. Your final report names
the client folder, the four deliverables, the connector run promoted and
when, every stage's verdict and elapsed time, and anything UNTESTED. Never
print a token, header or secret.
