# dma-insights — plugin changelog

## 1.24.1 — 2026-10-11 — a research share always funds a whole round

Owner, R-INTERAC-20261010: "I see workflows failing and being restarted.
Please diagnose and fix the above to ensure this never recurs."

Twelve of sixteen category workflows returned `AT_STAGE_BUDGET` or handed
back cells nothing could close, with the envelope $49.77 from its ceiling.
Nine defects — three in the driver↔governor budget handshake, two in how
concurrent agents and successive handoffs name their files, three in how a
gate term reaches an agent able to close it, one rule a challenger kept
having to state that the engine already knew:

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
