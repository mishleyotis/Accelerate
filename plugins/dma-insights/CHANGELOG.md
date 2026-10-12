# dma-insights — plugin changelog

## 1.27.0 — 2026-10-12 — find the registrant, for every sub-vertical in the US and Canada

Owner: "The tool is supposed to be find registrant as we deal with 9
subverticals in US and Canada."

- **`find_registrant` replaces EDGAR's SEC-only company search.** The old
  lookup answered for public companies only — IMA Financial Group, a private
  broker, came back with nothing. The evidence engine now routes by
  sub-vertical (CU, RB, CL, CIB, AM, RIA/WM, IC, IB, FC) and country to the
  registry that holds the institution, all free and keyless:
  NCUA (charter, type, assets, members, field of membership, HQ, CEO),
  FDIC BankFind (certificate, primary regulator, assets), SEC Investment
  Adviser Public Disclosure and FINRA BrokerCheck (CRD, SEC number), the
  Farm Credit Administration directory (UNINUM), OSFI (Canadian federally
  regulated institutions) and SEC EDGAR (any public or Form D parent, CIK).
  NAIC/state insurance departments and Canadian provincial and securities
  regulators publish no registry API; they are searched on their own hosts
  and come back as `candidates`, never as records. Every registry asked
  reports ok, no_match, candidates, error or not_run, and `ambiguous` when
  two records tie.
- **Measured live** (2026-10-12): IMA Financial Group, Inc. → EDGAR CIK
  1673769 (the SEC-only search had returned 0); Navy Federal → NCUA charter
  5536, Vienna VA, $204.4B, 15.5M members; First Technology → NCUA 23521,
  San Jose CA; Glacier Bank → FDIC 30788; Edelman Financial Engines →
  IAPD/BrokerCheck CRD 104510; Edward Jones → CRD 250; Horizon Farm Credit →
  FCA 720345; Manufacturers Life → OSFI. Three defects found and fixed on the
  way: sector words alone made matches ("Colonial Farm Credit" read as
  "Horizon Farm Credit"), EDGAR answered HTTP 500 to a comma, and NCUA's
  search misses a name carrying "Federal Credit Union".
- The tool's description says which gold columns a record fills
  (Firmographics Regulator, identifier, charter type, HQ, status, assets,
  members — stated, never held; the record URL as a T1 Source_URL read
  through `engine.cli fetch`) and that the identifier is the ET identity
  anchor. Research agents are told to identify the registrant first.

## 1.26.0 — 2026-10-11 — research tools named for what they find, split by source class

Owner: "For each of the MCP tools, avoid generic names, split by
functionality to ensure thorough results, as per gold standard
requirements. Ensure clear description of tools", and "Apart from evidence
tiers, check the gold standard scoring workbook columns eg excerpts, URLs,
dates etc."

- **A tool surface for the four research services.** Agents no longer see
  `research_brief`, `fetch` or `get_company_facts`. `scripts/evidence_proxy.py`
  serves `evidence`, `searxng`, `fetch` and `edgar` through
  `references/research_tool_surface.json` (`scripts/research_tool_surface.py`):
  39 tools, each with a specific name, a description that names the source
  class, the tier it earns and the gold-workbook columns its output fills,
  and preset arguments the agent cannot override. Calls are mapped back to
  the upstream tool; an upstream tool the surface does not name (EDGAR's
  insider-trading reads) is not exposed. The snapshot stays the upstream
  listing; upstream names still pass through for a session bound earlier.
- **Split by source class, so quiet classes are searched in their own
  right.** `find_evidence_all_sources` stays the batched first call; the
  cells it leaves unanswered are chased with `find_regulator_evidence`,
  `find_trade_press_evidence`, `find_news_wire_evidence`,
  `find_job_posting_evidence`, `find_customer_review_evidence`,
  `find_academic_evidence`, `find_contradicting_evidence` and
  `find_corroborating_evidence`; the entity's own site has
  `read_entity_newsroom` / `_careers` / `_investor_pages` / `_about_pages`.
  The engine gained `research_brief(source_classes=[…])`: `site:` probes over
  the source registry's hosts for the class (the sub-vertical's pack first,
  rotated across a batch's questions; `site:gov` for regulators) and only
  hits that classify into it are kept, counted in `search.class_filtered`.
- **Measured live before shipping** (local pinned SearXNG + Parallel, IMA
  Financial Group, P1C1.1–P1C1.2's 16 cells and twelve class-matched
  questions). Two defects were found and fixed in the same change: a
  regulator-class brief carded **15 T1 spans from BDC filings that list the
  entity as a borrower** — the page named the entity, the span was about the
  fund — so a per-class card must now name the entity in its own excerpt
  and an `ambiguous` match is dropped (`search.off_entity_dropped`); and
  quoting the legal name with its `, Inc.` suffix starved job-board and
  review-site probes, so per-class probes use the plain name and lead with a
  bare `site:<host> "<name>"`. After the fixes, on class-matched questions
  the review tool returned 2 App Store cards where the all-sources call
  returned none of that class; the trade-press tool 11 cards covering all
  15 cells from the two insurance trade titles the all-sources call also
  reached; the regulator tool an honest 0 for a private broker. Limits: `site:` probes rely on Google CSE, DuckDuckGo and
  Brave (Bing and Parallel ignore the operator), so a rested Google CSE
  thins the class tools; Indeed and LinkedIn pages are found but refused by
  robots.txt and are probed last — Indeed postings come through the Indeed
  connector.
- **Gold columns in every description.** A card tool says which
  Evidence_Detail column each field fills — Source_Name, Source_URL, Tier
  (registry, never typed; own domain never T1), Date_Published (a date the
  page states, never the retrieval date), Claim_Type, SubCap_IDs, Excerpt
  (verbatim 50–500, sentence-complete) — and what the ledger computes (E_ID,
  ERS, Recency, Retrieved_At, Access_Status, the scoring row's Evidence_IDs
  and Source_URLs). A search tool says a snippet is never an Excerpt; an
  EDGAR tool says how a filing becomes a T1 row.
- **The page-read guard now fires on the plugin's own readers.** They were
  listed in `deny_whole_page_fetch.FETCHERS` but missing from the hook's
  matcher; the matcher now carries every reader and searcher it lists.
- Grants, the challenge slice (`find_contradicting_evidence`,
  `find_corroborating_evidence`), `search_order` (every find_* brief
  counts), the rate gate, source health, auto-approve, the workflow, relay,
  agent bodies and docs read the new names; `docs/EVIDENCE-ENGINE-TOOLS.md`
  carries the generated surface table.

## 1.25.0 — 2026-10-11 — the research connectors bind, stay bound, and answer under load

Owner: "Confirm connector reachability especially the open source ones …
Fix accessibility issues so these connectors bind always in case sessions
restart and at the beginning", then, from a live round: "The open-source
evidence engine timed out twice at 60 seconds in P3C4, with 16 workflows
hitting it at once."

- **Parallel and alphaXiv were silently unbound.** Both are also claude.ai
  connectors at the same URL; when the account attaches them Claude Code
  suppresses the plugin's server ("Suppressing plugin MCP server …
  duplicates a claude.ai connector") and the tools bind as
  `mcp__Parallel_Search__*` / `mcp__alphaXiv__*` — names no manifest held,
  so every research agent ran without Parallel (the IMA session bound 4 of
  6). The registry now grants both spellings (`SHADOWED_BY_CLAUDE_AI` in
  `scripts/provision_agent_tools.py`), alphaXiv contributes its three read
  tools, and the rate gate, source health, page-read guard, auto-approve,
  relay, `agent_run` and the doctor all read the alias. Tests pin every copy.
- **A cold start no longer costs a session its tools.** The CLI gives a
  server 30 s to answer `initialize` and never asks twice; the research
  services run at min-instances 0 and the proxy could spend a 60 s token
  mint plus 3×120 s upstream, or answer an empty tool list "until the next
  initialize" that never came. `evidence_proxy.py` now answers within
  `DMA_RESEARCH_INIT_BUDGET_S` (20 s), lists the last-known tools (runtime
  cache, else `references/research_layer_tools.json`), recovers in the
  background and sends `notifications/tools/list_changed`; a call made while
  warming waits for the service. Proved end to end against a 25 s cold stub.
- **Searches run at the sources' rate, not 1/s.** The engine's fan-out
  waited on the per-WEBSITE politeness bucket (1/s, burst 1) keyed by the
  source name, and the configured source buckets (SearXNG 4/s, Parallel
  1.4/s) were never acquired. Load harness (`apps/evidence-engine/eval/load.py`,
  the 686-cell IMA volley through the real Engine, simulated sources): the
  old wiring dropped 2,744 of its queries at the budget and ran 48 Parallel
  calls; the fixed wiring dropped 11 and ran 1,036, answering all 346 of an
  instance's questions in 14.4 min (5x scale; 11–15 min projected for the
  whole run on two instances), 0 errors.
- **Sixteen workflows share one queue, in the proxy.** Every agent in a
  session shares one proxy process, which handled one message at a time.
  Calls now run concurrently; heavy calls (`research_brief`, `crawl_entity`,
  `filings_evidence`) pass an admission gate (`DMA_RESEARCH_ADMIT`, 12 —
  both engine instances busy, each brief inside Cloud Run's 300 s) and the
  rest wait locally where no server clock runs; light calls never wait
  behind them. A Cloud Run 429/503 (instances full or cold) is retried, not
  handed to the collector as an outage; a waiting call sends progress when
  the client gave a token. `.mcp.json` gives evidence a 30-minute per-server
  `timeout` (it overrides the environment's `MCP_TOOL_TIMEOUT=60000`, which
  had cut briefs that then finished server-side: IMA P1C1 probe, 31 cards
  stored, 0 returned) and the raw fallbacks 180 s. The availability marker
  follows each call's transport outcome, so `search_order.py` lifts
  brief-first when the engine dies mid-session and restores it after.
- **The engine bounds its own search phase.** `EE_SEARCH_PHASE_BUDGET_S`
  (120 s, a guard inside Cloud Run's 300 s): queries still queued for a
  source token are cut and counted (`search.budget_cut`); started calls are
  never cancelled (coalesced joiners from other briefs ride on them).
- **Collectors queue every brief at once.** One message fires every
  capability's `research_brief` of the batch; one optional message of
  fallbacks; then one write turn per capability (was: search, write, search,
  write — each later brief joined the back of a sixteen-category queue).
- **A small category gets at least one full wave.** Shares were split by
  cells alone, so a two-cell category got $0.38 against a $1.84 floor (one
  batch + orchestrator + challenge) and closed AT_STAGE_BUDGET with money
  left. Each invocation is now floored at its fixed costs and the rest is
  split by cells; the shares still partition the envelope.

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
