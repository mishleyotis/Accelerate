# QA report — Northwest Bank DMA through the plugin (2026-10-01)

Run `nwbi-2026-10-01`, Northwest Bank (Northwest Bancshares, Inc.), driven
only through `/dma-insights:run-assessment` and the commands it prescribes.
Issue register with the evidence behind each line: `CASE_FACTS.md`.

## What ran

| Step | Result | Time |
|---|---|---|
| Connector baseline + strict check | READY (exa, tavily, clay, explorium, indeed) | <1 min |
| Doctor | 16/17 → red row was N-03 (doctor cannot see a `--root` baseline) | 22 s |
| Route | `AMBIGUOUS` (6) on "Northwest Bank" → `NEW_VERSION` (7) with `--fresh` on the corpus id | <1 s |
| Preflight | FY2025 revenue lines, LOB census, one AskUserQuestion (entity, binding, mode, budget) → RB + CL + RIA, FULL, PUBLIC, 729 cells, $200 ceiling | ~6 min |
| Start | folder opened, prior package archived (12 items, 0 failed) | 37 s |
| PRELIM | PASS, 1 round (relay serviced in-session) | 341 s |
| KG | PASS, 6,491 diagnostic questions | 7 s |
| RESEARCH | 16 category workflows, 81 batches, 32 agents concurrently; stopped at 27 min at **215/729 cells (29%)** when the session's search capacity ran out (N-27) | 27 min |
| SCORING → PROMOTE | not reached live (blocked by RESEARCH); exercised through the plugin's stub walk — see O3 | — |

True spend at stop: **$76.40** (PRELIM $2.84 + research workflows $73.56,
per-message accounting — N-25). Marginal research cost over the productive
window: $0.19–0.21 per closed cell, matching the plugin's $0.19 rate.

## Objective 1 — efficient research, token economy, few approvals

**Verdict: not met as shipped; fixed in this PR, the live re-measure is still owed.**

- **Approvals.** No prompt reached the owner, but only because this session
  ran in auto mode. Replaying all 3,055 workflow tool calls through the
  plugin's own approvers shows **729 (24%) would prompt in a
  default-permission session**: 626 of 1,382 Bash calls and 102 of 102
  Firecrawl scrapes (N-26). The causes are python heredocs written to
  generate ops files (377) and writes into a run root the approver could
  not see (N-26, N-11). **Fix:** JSON-lines batch ops written with the
  Write tool, `<ROOT>` defined under the plugin's run tree, and a start-time
  warning when a root would make writes prompt.
- **Tokens.** Every batch agent opened at a **66,178-token floor**, made up of
  the session's skill listing, the deferred-tool roster and the repo
  charter, plus a ToolSearch turn. A type without those measured 49,261.
  **Fix (N-19):** a lean `research-batch-producer` agent type.
  - Engine CLI output was 55% of everything agents read. **Fix (N-21):** the
    capability card drops from 7,288 to 2,733 chars.
  - Every agent rediscovered that Exa was out of credits. **Fix (N-18):** the
    outage is recorded once and carried to every agent.
  - Agents opened internal-document briefs on a PUBLIC run. **Fix (N-22).**
  - Agents reverse-engineered the absence flags from engine source, because
    the sheet's own example was refused by the CLI. **Fix (N-24).**
- **Cost truth.** Two problems:
  - Workflow spend was booked **3.2× too high**, because usage was counted
    per transcript entry instead of per API message. The driver would have
    stopped this run at a $200 ceiling it had not reached. **Fix (N-25).**
  - Nothing enforced the ceiling while the workflows ran. **Fix (N-20):**
    every batch checks it first.
  - The step-4 estimate quoted the retired lane model ("$13.24, within
    budget"). **Fix (N-09):** it now quotes the measured rate ($145.55).

## Objective 2 — research builds the heatmap with evidence linkage, one workflow per category

**How parallelism is enforced (measured):**

- `RESEARCH_UNIT = "category"`: the driver writes one workflow invocation per
  category (16), and the session starts all 16 in one message.
- The runtime caps each workflow at min(16, CPUs−2) agents, which is 2 on
  this host. That gives **32 batch agents concurrently**, confirmed from the
  transcripts.
- Each category's open cells are packed into capability batches of at most
  12 cells, each with a fresh context. An independent `research-challenger`
  and the floors gate run per category, for up to 2 rounds.
- Writes go through one `engine.cli batch` per capability, so the run-wide
  workbook lock is taken once per capability.
- All 16 categories closed cells in parallel: 5–23 each at the stop.

**Linkage (audited on the live workbook):**

- 215 cells closed: 188 syntheses and 27 earned absences.
- Every synthesis cites evidence: 614 citations.
- 0 unresolved ids, 0 excerpts outside 50–500 chars, and 0 missing back-links
  between `Evidence_Detail.SubCap_IDs` and the scoring rows' `Evidence_IDs`.
- 358 of 690 evidence rows are honestly UNVERIFIED (undated, not given fake
  dates). The exception is the preflight's own two statements, which carried
  an engine-written "excerpt" and a retrieval date (N-28, fixed).
- The linkage is built in the workbook **as each capability batch lands**. The
  web app sees it only at INGEST_A, after scoring. That is by design: the app
  serves promoted runs only.

**What stopped it (N-27, critical):**

- Every workflow agent runs in the conducting session, and Claude Code caps
  WebSearch per session (200 by default).
- 596 WebSearch attempts were made and 402 were refused. Exa answered all 65
  calls with HTTP 402, and Tavily hit its plan limit (HTTP 432).
- Demand is ~6.2 search calls per closed cell, about 2,000 WebSearch calls
  for 729 cells.
- **Fix:** the handoff now measures the WebSearch budget against demand
  before starting, and the command puts the figure to the owner. The sheet
  also stops treating the capped tool as mandatory.
- **The capacity itself is an owner/environment action** (below).

## Objective 3 — synthesis and artifacts to the gold-standard templates

**Verdict: not reached live.** The run cannot pass RESEARCH without search
capacity. What was verified:

- The plugin's own stub walk drives SCORING → INGEST → REPORTS → PAGES →
  PACKAGE (gold gate) → PROMOTE through the real command line (result
  below).
- The gold gate (`engine.gold_standard`, calibrated to the Golden 1 reference
  package) is wired into the deliverable gate: a package with no recorded
  PASS cannot be pushed.
- One defect reaches every package: the preflight banked non-verbatim,
  wrongly-dated evidence (N-28, fixed).

**Stub walk on the fixed tree: 34/34 steps PASS.**

- The run goes PRELIM → … → PROMOTE.
- It stops at the dollar ceiling, and only a person's raise continues it.
- A stalled category ends its stage instead of looping.
- An ingest timeout resumes at INGEST_A.
- A page that fails its verdict is the only page re-dispatched, and it
  carries the reasons.
- A refused promote fails; the next run promotes and records two connector
  versions.
- A second run redoes nothing.
- A v6 workbook continues under v7.

The gold gate at PACKAGE returned 0 findings. Its verdict now also lands in
`Gate_Log`, where the push gate reads it (N-29).

## What the owner has to do (not code)

1. **Search capacity.** Do one of these before resuming:
   - Raise `CLAUDE_CODE_MAX_WEB_SEARCHES_PER_SESSION` in the environment
     (~2,000 for a 729-cell run; searches are billed).
   - Or top up Exa and lift the Tavily plan limit so the connectors carry
     the volleys.
2. **Resume** in a fresh session, once this PR is merged so the session binds
   the fixed plugin:
   - `python3 -m engine.pipeline run --run nwbi-2026-10-01 --root /home/user/dma-runs/northwest-bank --max-usd 200`
   - Nothing done is redone: 215 cells and 690 evidence rows persist, and the
     run is snapshotted to the client's Drive `memory-backup`.
3. **Budget.** $76.40 is spent of $200. The remaining 514 cells project to
   ~$100 of research at the measured rate. Scoring, reports and pages are on
   top of that, so the $200 ceiling will likely need raising at SCORING.

## Untested live

- The lean batch agent, JSON-lines ops, and the in-workflow ceiling. This
  session's agent roster predates them.
- The approval replay after the fixes, and the PRELIM routing to two
  specialists.

These need the resumed run.
