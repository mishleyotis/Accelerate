# dma-insights — plugin changelog

## 1.24.1 — 2026-10-11 — a research share always funds a whole round

Owner, R-INTERAC-20261010: "I see workflows failing and being restarted.
Please diagnose and fix the above to ensure this never recurs."

Twelve of sixteen category workflows returned `AT_STAGE_BUDGET` or handed
back cells nothing could close, with the envelope $49.77 from its ceiling.
Eleven defects — three in the driver↔governor budget handshake, two in how
concurrent agents and successive handoffs name their files, three in how a
gate term reaches an agent able to close it, two rules a challenger kept
having to state that the engine could check at the write, and one contract
rule HANDOFF enforced that the write never did:

- **The share** (`engine/pipeline.py`): with the envelope funding the scope,
  shares were `remaining × cells / total` — blind to the ~$1.40 orchestrator
  and challenge every category pays whatever its size. P3C2/P3C4 got $0.81,
  P1C3 $1.22, P4C1 $1.49 against a $1.74 first wave: refused in
  milliseconds, no agent run. A share is now never below one whole round at
  the governor's own `tier_usd` (`_round_floor_usd`: every first-wave batch
  + orchestrator + challenge), plus a cells-proportional part of any
  surplus; when the floors do not all fit, whole categories are allocated
  cheapest first (the existing deferral), never undersized shares.
- **The spend order** (`workflows/dma-pillar-research.js`): only wave 1 held
  the orchestrator-and-challenge reserve, so the gap wave and round 2 spent
  it on collectors — P1C3, P3C1, P3C2, P4C4 ended "syntheses written,
  challenge not affordable", repair evidence bought and never synthesised.
  Every wave now holds the reserve; a synthesis is written only when its
  challenge is funded; an unfunded gap wave is skipped and the category goes
  to its challenge with what it has.
- **The verdict**: a round-2 wave that did not fit replaced the round-1 gate
  verdict (FAIL with its cells) with a bare `AT_STAGE_BUDGET`; it now hands
  back the verdict.
- **The ops files**: the prompts said "ONE ops file" without naming it, and
  sixteen workflows share one session — P4C1's challenger re-ran a file
  P1C3's had overwritten in the scratchpad and recorded P1C3's verdicts
  again. Every collector, orchestrator and challenge prompt now names its own
  `OPS DIR` under `<run>/07_qa/ops/`, unique per category, role, pass and
  batch (the round-1 gap pass is tagged `1g`, so it no longer shares a tag
  with round 2) and deterministic, so a resume still replays from cache.
- **The unclosable cell** (`engine/floors_gate.py`): a declared absence a
  repair wave later attached evidence to is no longer a declared absence and
  has no synthesis author, so `record_challenge` refuses it — yet the gate
  reported it `challenge_missing` and handed it back every round (P1C1: five
  cells; P4C1.4.3). It is now the blocking term `absence_superseded`, and
  the orchestrator's prompt names those cells as its own: a synthesis from
  the attached rows closes them.
- **The term nobody was told about**: `absence_single_tool` was the commonest
  blocking term on the run and the collector's repair lines never named it;
  with the evidence engine timing out under sixteen workflows, collectors
  fell straight to WebSearch — which is not an enrichment tool — so every
  repair wave re-failed (P3C2.2.CIB1: 27 searches over three rounds, all
  `web_search`). The repair lines now route every term in
  `floors_gate.BLOCKING_TERMS` (hoisted to a module constant, test-asserted
  against the prompt), `absence_single_tool` through searxng / the engine /
  edgar, and an engine error or timeout falls to searxng, not WebSearch.
- **Stale challenge packets**: every handoff restarts its rounds at r1, so
  `briefs/wf_challenge_<CAT>_r1` kept packets from earlier handoffs that
  judge text no longer there; the challenge step now clears it first and
  works only the packets it just built.
- **The ceiling nobody was shown** (`engine/brief.py`, `engine/ledger.py`):
  five challenge FAILs on `ceiling_reasoning`, a round each — a 5.0 ceiling
  on one source identity (P3C2.2.CIB1, twice), 3.0 on T4/T5 rows
  (P1C2.6.2), bands contradicting the stated number. `assessment.ceiling_for`
  already computed the number `score` refuses above; the writer never saw
  it. `brief reuse` now prints `evidence_ceiling` {value, band_max, why} per
  cell, the orchestrator prompt concludes at it, and the ledger refuses a
  `Ceiling_Band` above the evidence's band at the write.
- **The citation nobody could take back** (`engine/ledger.py`,
  `engine/cli.py`): when the rows a repair wave attached to a declared
  absence answer another question (P4C2: an ad brand-lift study on a
  BI-inventory cell, fraud ML on a content-generation cell), the orchestrator
  rightly writes no synthesis — and with no write that removes a citation,
  `absence_superseded` could never close (four cells). `attach --detach
  --why` (`ledger.detach_evidence`) takes the row back from a declared
  absence only — never from a synthesised cell — both directions of the
  link, a Provenance 'detach' row; the absence then stands. The orchestrator
  prompt detaches instead of reporting a gap no one can close.
- **The facet answered with no search behind it** (`engine/ledger.py`):
  P2C1 failed 12 of 15 cells on `facet_coverage` — the evidence engine
  timed out, no contradicts volley was logged, and the syntheses answered
  `DQ_Contradicts` anyway. A `DQ_<facet>` stating a finding now needs a
  Search_Log row on that cell for that facet, else `NOT_RUN: <why>`; the
  ledger refuses it at the write and the orchestrator prompt says so.
  The challenge packet's `facets_answered` no longer counts a `NOT_RUN` /
  `NO_FINDING` field (it told challengers a volley fired that the record
  says did not); those facets ride in `facets_not_run`.

- **The URL rule 5 asked for at HANDOFF, never at the write**
  (`engine/ledger.py`): with all sixteen categories passed and $219.61 of
  RESEARCH spent, HANDOFF refused the workbook — 19 cells cited evidence with
  no URL in `Source_URLs`. 46 internal rows carried the local `01_intake/`
  path (38 bare, 8 `file://`) though `intake_manifest.json` holds each
  document's Drive URL, 5 carried none, and one Clay reading (E-031) was
  registered with no URL. Now an intake path is verified verbatim against the
  landed document and recorded as the manifest's source of record; a local
  path with none, and a connector reading with no URL, are refused at the
  write. `engine.cli rehome-intake` re-points a register written before the
  rule (a row moves only when exactly one landed document quotes its span)
  and `engine.cli cite-record` gives a URL-less connector reading the record
  it reports on — both Provenance-logged. Tests:
  `test_intake_source_of_record_2026_10_11.py`.

- **A re-strike kept its old ending** (`engine/assessment.py`,
  `workflows/dma-pillar-scoring.js`): the rescore prompt said to put the
  critic's reason "at the head of the existing rationale", so 7 of the 8 P3
  rows the critic moved still concluded "final 3 (Competing)" or "final 2.5"
  beside a struck 2.0–2.5, and named M4 as the gap from M2. The critic passed
  the scores and could not move text. `rubric_problems` now refuses a
  rationale whose last "final N" is not the score struck, and the rescore
  prompt rewrites the rationale: the struck level argued, the level
  immediately above as the gap, arithmetic that lands on the score.
  The same rescore argued "ADJ_STALE -0.3" on three rows (P2C1.8.3,
  P3C3.1.1, P4C3.2.2) whose Caps_Applied read "none applied"; an `ADJ_`
  label the rationale applies with a delta is now written to Caps_Applied
  ("ADJ_STALE -0.3 (stated in the rationale)") when `--adj`/`--caps` did not
  already name it — a hand-struck score may state its adjustment in prose,
  so the write records it rather than refusing. A label named only as not
  owed is not an application.

- **SCORING was never priced** (`engine/pipeline.py`, `engine/cost.py`,
  `workflows/dma-pillar-scoring.js`): the stage cost $87.52 against a $25
  envelope — 11 scorers $67.82 ($0.095 a row), 8 critic rounds $15.87, 4
  rescores $1.52, solutions $0.73. The handoff printed "est $None", handed
  every pillar the whole envelope as its `remaining`, and the workflow logged
  the envelope and checked nothing. `cost.SCORING_TIER_USD` holds the
  measured prices; `_scoring_price` prices each pillar from its briefs' rows,
  refuses before dispatch when a binding envelope cannot fund the stage
  (naming the `--stage-budget SCORING=` that would), and hands each pillar
  its share; the workflow prices every scorer (its first critic round held
  in reserve), critic and rescore before starting it, and reports rather
  than enforces an envelope the owner made non-binding. Tests:
  `test_scoring_budget_2026_10_12.py` (the real workflow under node at
  shares from $0 to $40, `scoring_governor_harness.mjs`).

- **A one-peer set nobody could widen** (`engine/prelim.py`): REPORTS
  refused client_research §4 ("fails below three; the engagement owner
  widens the set") while `lock_peer_set` refused any different set, so no
  command existed for the owner's decision. `engine.prelim widen-peers`
  adds peers to the locked set only — every locked peer stays — only while
  no Peer_Median, quartile or Peer_Scores is written against it, and only
  with the owner, reason and selection rule recorded (Provenance and a
  non-blocking `PEER_SET_WIDENED` Gate_Log row). Tests:
  `test_widen_peers_2026_10_12.py`.

- **Report probes ran and could not be logged** (`engine/pipeline.py`): the
  REPORTS probe round checkpointed each category's search window but not
  RELAY's, which the probe lanes' connector searches log under and which
  RESEARCH had left at 955 against 60. All 56 probe searches ran, every
  `engine.cli search` was refused, and the writers saw peer absences with
  no search behind them. The probe round now opens a fresh RELAY window
  too. Test: `test_widen_peers_2026_10_12.py`.

- **Connector readings landed as package evidence** (`apps/worker`,
  `engine/assemble.py`): the ingest hardcoded `origin='package'` and never
  read the workbook's `Origin`, so every Clay/Vibe technographic reading
  reached the server with no tool and ET-12 ("the register cites no machine
  technographic scan") could never pass for an engine-produced run — the
  "worker fix in flight" of 2026-10-09 had not landed. Both readers now carry
  `origin` and the retrieval time (read when stated, never reported missing),
  `evidence_index.json` exports them, a connector row lands as `connector`
  with its tool, and a re-scan corrects a row an earlier ingest landed as
  `package`. Every other origin is unchanged. Needs a worker deploy.
  Tests: `apps/worker/tests/test_connector_origin_lands_2026_10_12.py`.
- **SG-V4 labels counted as prose** (`engine/pipeline.py`): `publisher` and
  `source_domain` join the verbatim leaves the driver's budget skips (9 of the
  Interac heatmap's 20 counted FAILs).

- **A version-A page could stop the whole run** (`engine/pipeline.py`):
  techstack failed ET-07/ET-12 against evidence the server ingested before
  the workbook's repairs (links attached later, connector provenance the
  worker dropped), and a page halted on version A stopped every later stage.
  `--defer-to-b PAGE` (an owner decision, logged as a non-blocking
  `PAGES_DEFERRED_TO_B` Gate_Log row and remembered on resume) moves it:
  PAGES_A no longer owes it and PAGES_B produces it against version B.

- **A report re-tripped GS-RPT-NOTOKENS on its own gate table**
  (`engine/gold_standard.py`, `engine/reports.py`): the finding quoted the
  leftover tokens with their braces, the report's gate table rendered every
  Gate_Log row ever written, and the client research report then failed the
  token check on an old gate message, not on any template residue — the
  package refused at PACKAGE. The finding names tokens without braces, and
  the gate table renders the latest verdict per gate and scope.

Tests: `tests/skills/research_engine/test_research_budget_floor_2026_10_11.py`
— the driver's shares swept across envelope sizes, and the real workflow
source run under node (`research_governor_harness.mjs`) at every share from
$0 to $7: a category either runs no agent or its last collector is followed
by a synthesis and a challenge, and never spends past its share.

## 1.24.0 — 2026-10-11 — the six connectors, batched and ordered

Owner: "There were 6 connectors mentioned … Ensure all are mapped to the
agents and well orchestrated. The goal is to avoid calling web search
severally and batch queries to the open source connectors first … getting
back the tool results in schemas … that align with gold standard scoring
workbook requirements."

- **Mapped**: `research-evidence-collector` and `technographic-scanner` now
  hold the raw research fallbacks (`searxng`, `fetch`, `edgar`, `parallel`)
  beside the engine; `alphaxiv` is mapped to the research tier (collector,
  conductor, web specialist) and contributes tools the day its listing is
  captured (OAuth per user). Per-page producers unchanged (2026-09-14).
- **Batched**: `research_brief` takes `questions[]` as objects
  `{question, subcap_ids, facet}` — one search pass and one fetch slice for a
  whole capability, cards ranked PER QUESTION and returned with
  `item.linked_subcap_ids` = the caller's cells (echoed, never invented) and
  `by_question[]` naming what nothing answered; `max_cards`/`token_budget`
  per question; a per-call query budget (`query.per_question_budget`). The
  card is the gold evidence row: `engine.cli evidence-brief --cell
  CELL=QUESTION …` prints one search line per question and one evidence line
  per card, `--subcap` filled from the cells the engine echoed.
- **Ordered**: the research workflow's collector prompt and the collector's
  manifest put ONE batched `research_brief` per capability first, the raw
  layer next, Exa/Tavily after, WebSearch last; `hooks/search_order.py`
  (PreToolUse on WebSearch/Exa/Tavily search; PostToolUse counter) refuses a
  research actor's general search before its first brief and past three per
  brief while `evidence_proxy.py`'s availability marker
  (`/root/.dma/research_layer/evidence.json`) says the engine is up; it steps
  aside when the engine is down or answered an error. FAILS OPEN.
- **Contract**: `connector_contract` family `evidence` logs as
  `evidence_engine` (`contract.SEARCH_TOOL_OF_FAMILY`).
- **Deploy gate** (`infra/evidence-engine`): governs on question coverage
  recomputed from the results file (owner, same day: "Fix the above to
  ensure deploy happens"); same-URL recall reported beside it; the static
  egress NAT is opt-in (`EE_STATIC_EGRESS=1`); CI makes the identities'
  logging binding itself (the deployer holds projectIamAdmin).

## 1.23.0 — 2026-10-10 — the research layer

- **Evidence engine** (`apps/evidence-engine`, Cloud Run `dmai-evidence`,
  plugin server `evidence`, six tools): `research_brief` returns
  register-ready cards (verbatim sentence-complete span verified against the
  page, registry tier hint, licensed claim label, page-stated ISO date, origin
  cluster with syndication count, entity match, recency band) plus a coverage
  block with the saturation stop rule and flagged-never-resolved conflict
  candidates; `crawl_entity`, `filings_evidence` (edgartools in-process),
  `expand_context`, `verify_cards`, `coverage_report`. Contract and the diff
  from the brief's baseline: `apps/evidence-engine/docs/CARD-CONTRACT.md`.
- **Five connectors** declared in `.mcp.json`: `searxng`, `fetch`, `edgar`
  (self-hosted via Supergateway on secret paths; `infra/evidence-engine`),
  `parallel` and `alphaxiv` (vendor, `type: http`). Access through
  `scripts/evidence_proxy.py` + `evidence_auth_headers.sh` — siblings of the
  connector's proxy and helper, which are untouched.
- **Grants** by role (`scripts/provision_agent_tools.py`): engine on the
  research/servicing tier; verify slice on the verifiers and assemblers;
  raw fallbacks on the servicing tier only; per-page producers unchanged
  (owner decision 2026-09-14 stands; recorded in docs/CONNECTORS.md).
- **Hooks**: `rate_gate.py` (PreToolUse, raw fallbacks, fail open) and
  `source_health.py` (PostToolUse, all six); the whole-page-fetch guard lists
  the raw readers.
- **Doctor**: six `research layer:` rows (`scripts/research_layer.py`);
  WARNING for a raw fallback, BLOCKER for the engine only without a search
  fallback.
- **Docs**: `docs/EVIDENCE-ENGINE-TOOLS.md` (generated), CONNECTORS.md
  research-layer section, RESEARCH-PROTOCOL § Tools rung 3, the production
  evidence doctrine, `enrichment_sources.json` search connectors +
  `_free_chain`.
- **Measured** (`apps/evidence-engine/docs/EVAL-REPORT.md`, golden v1 from the
  repo's own corpus, Logix held out): excerpt fidelity 100 %, URL liveness
  100 %, boilerplate 0, syndication inflation 0, token reduction 82.6 % on
  re-found pages; source recall 37.1 % after the two tuning iterations the
  brief allows (fetchability-bound: WAF 403s and one client's own site; one
  free discovery source) — escalated, not tuned further. `tests/` in the
  engine: 302 offline tests; no client string in engine code (CI grep).
- **Not deployed**: every resource-creating step waits on
  `apps/evidence-engine/docs/DEPLOY-PLAN.md` approval.
