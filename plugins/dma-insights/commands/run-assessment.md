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

**Record the connectors YOU hold before anything else runs.** No subprocess
can enumerate a session's bound MCP tools (MEM-0112) — only you can, and
every check below reads what you write here, so writing it second makes the
first one lie. Write the list, one tool name per line, and hand it to the
contract:

```bash
printf '%s\n' <every mcp__ tool name you hold> \
  | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/connector_contract.py" baseline --tools - --root <ROOT>
printf '%s\n' <the same list> \
  | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/connector_contract.py" check --tools - --strict
```

`--strict` is not optional. Without it a STOP still exits 0 and the gate you
just built passes a session with no connectors at all — which is the exact
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
| No baseline written | Nothing knows whether a cell can be enriched or honestly declared absent | `engine.pipeline run` **REFUSES** at PREFLIGHT before a single lane is dispatched. Write the baseline. |
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
lagging install record is cosmetic), so a session that binds the checkout
reads OK through a heal. `UPDATED_MID_SESSION` means the bound tree moved
under this session and THIS session still holds the old roster — carry on,
because the driver dispatches every lane as a fresh child process that binds
the current tree. Its `connector
contract` row now reads the baseline you wrote: UNVERIFIED means you skipped
the step above, and a short baseline is the DEGRADED row of the table, not a
provisioning defect. Any OTHER row red after the heal is a provisioning
defect: report the row and stop.

`engine.pipeline env` names every hard dependency (the claude CLI, a
connector identity rung, the **enrichment-connector baseline** you just wrote,
`agent_run.py`, `ship_page.py`, `mcp_raw.py`, `drive_fetch.py`, the pinned
templates against the manifest); a hard failure stops you here, with the
check's own fix line.

## 2 · Route the name before you prepare anything

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/route_client.py" --client "$ARGUMENTS" --json
```

Obey the exit code: 4 NEW_ENGAGEMENT is yours; 3 NEEDS_SCORING means the
research package exists and scoring is the missing step (`engine.pipeline
plan` on that run tells you where it stands — resume it, do not restart);
0 READY_TO_SYNTHESISE and 5 ALREADY_SERVED are the synthesis lane's, stop and
name the run; 6 AMBIGUOUS — report the near matches, never guess; 2 is the
script failing, which is not a routing answer.

Then the three places work already exists, before any research
(`registry.py pull` + `registry.py list --open-only`; `drive_fetch.py
find-artifact --client "<Entity>"` and its `run_manifest.json`;
`get_client_state`). An open run or an IN_PROGRESS manifest is a run to
RESUME: `python3 -m engine.pipeline plan --run <RUN_ID> --root <ROOT>` says
where it stopped, and step 5 continues it. With `--resume <RUN_ID>` you skip
straight to step 5.

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
ingests it) → REPORTS (two producers and the validator into the pinned Docs,
rendered into the branded shell) → PAGES_A (techstack and heatmap shipped to
version A through `ship_page.py --claim`) → PACKAGE (technographic scan,
`assemble package`, the gold gate) → INGEST_B → PAGES_B (the A pages restaged
from disk; overview, insights, platform, then context) → PROMOTE. Every stage
lands `STAGE_<NAME>` in Gate_Log with its wall clock and a cost-ledger line.

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
