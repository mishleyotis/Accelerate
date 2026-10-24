# The session brief and the owner's follow-ups (record, 2026-10-10 → 2026-10-11)

This file is the reference an audit session reads to judge the research-layer
work (PR #92, merged as `f9e4077`) against what was asked. Part 1 is the brief
exactly as the owner pasted it on 2026-10-10. Part 2 is every later instruction
the owner gave in the same session, in order, quoted. Nothing here is an
instruction to a future session by itself; the audit prompt says how to use it.

## Part 2 — the owner's follow-up instructions, in order

1. "Finalize the above. Reread the entire conversation and inventory all pending items"
2. "Finalize everything above. Once CI is green, please merge to the default branch and redeploy"
3. "Raise source recall to more than 90%. Ensure the pipeline and all mcps are robust"
4. "Are you checking the connectors against the subcap requirements and diagnostic questions? Measuring token consumption? Ensuring that parallel searches happen fast and give quality results, even for proxy searches in case of absences."
5. "Report iteration 4 and v2 results when done"
6. "Approve the evidence-engine deploy once recall clears 90%"
7. "Once merged to the default branch, deploy is to happen automatically, ensure this routing works well"
8. "Also, the research phase should still enforce /workflows. Once changes land, and redeploy is successful, please do a stress test with IMA"
9. "My expectation is now the runs will never run degraded due to the open source connectors. Ensure agents fallback to them"
10. "There were 6 connectors mentioned in the original prompt. Ensure all are mapped to the agents and well orchestrated. The goal is to avoid calling web search severally and batch queries to the open source connectors first enabling ease of processing and getting back the tool results in schemas defined that align with gold standard scoring workbook requirements. Fix the above to ensure deploy happens"
11. "You have not confirmed the 6 connectors and their tools. Name them"
12. "Check on the deploy and give the prompt to gauge work done against the original prompt in another session."

## Part 1 — the brief, verbatim

# Session brief: gold-standard evidence engine + open-source research connectors for the dma-insights plugin

Paste everything below into a Claude Code session opened at the root of the **dma-insights plugin repo** (v0.3.2 or later).

---

## 0. Objective and design stance

Give the dma-insights plugin a free, open-source research layer that returns **gold-standard evidence, not raw pages**.

Today an agent that researches pays tokens to read whole pages, then picks excerpts itself. The upgrade moves the mechanical work **server-side**:
- crawling, extraction and cleaning;
- dating, deduplication and ranking;
- verbatim excerpt selection;
- provenance and liveness checks.

Agents receive compact, register-ready **evidence cards** and spend their tokens only on reasoning.

**Division of labour (non-negotiable):**

| The evidence engine does (mechanical, deterministic, testable) | The plugin's agents still do (reasoning) |
|---|---|
| Search fan-out, crawl, extract, clean, chunk | Decide which subcap an excerpt supports (deep, evidence-weighed linkage; never string matching) |
| Verbatim excerpt selection with offsets + hash | Claim labels: FACT / INFERENCE / HYPOTHESIS / CEILING_ESTIMATE |
| Publish-date extraction → recency label | Final evidence tier per the repo's decision tree |
| Near-duplicate and syndication clustering | Contradiction disposition and triangulation verdicts |
| Tier and source-type **hints**, liveness, archive fallback | Narrative, so-what, self-challenge |
| Coverage, concentration and saturation metrics | Stopping decisions, using the engine's saturation signal |

The engine never asserts a subcap link, a claim label or a final tier. It proposes; the reasoning agents adjudicate.

## 1. Architecture

### Six connectors, one of them new

| # | Connector | Built/hosted | Role |
|---|---|---|---|
| 1 | **evidence-engine** (NEW, custom, Python, open-source stack) | Cloud Run, this brief | **Primary research interface.** Composes the sources below and returns evidence cards. |
| 2 | **SearXNG** + `mcp-searxng` | Cloud Run (same project) | Search backend for the engine (internal), and a raw fallback tool |
| 3 | **Fetch** (`mcp-server-fetch`) | Cloud Run | Raw fallback read tool |
| 4 | **SEC EDGAR** (`sec-edgar-mcp`) | Cloud Run | Raw fallback; the engine uses the `edgartools` library in-process for card-grade filing evidence |
| 5 | **Parallel Search** (`https://search.parallel.ai/mcp`) | Vendor, free, no auth | Second search backend for the engine, plus a raw fallback |
| 6 | **alphaXiv** (`https://api.alphaxiv.org/mcp/v1`) | Vendor, free, OAuth | Academic full text; called by agents directly (the OAuth is per-user) |

Agents go to the **evidence-engine first**. The raw connectors are escape hatches for edge cases, debugging and engine outages, and their use is logged.

### Evidence engine internals (all open source; verify licences)

- **Server:** FastMCP (Python), native Streamable HTTP, so it needs no Supergateway.
- **Search fan-out:**
  - SearXNG over internal HTTP (the engine and SearXNG can share one container or VPC);
  - Parallel via its MCP endpoint, as an MCP client.
  - Merge, normalize URLs, and keep each result's origin source.
- **Fetch + extraction:**
  - `httpx` with HTTP/2, per-host politeness and robots.txt compliance;
  - `trafilatura` for main-content extraction;
  - `htmldate` for publish/update dates;
  - PDFs via `pypdfium2` (Apache/BSD; avoid AGPL PyMuPDF unless the licence is cleared).
  - Annual reports and call-report PDFs are first-class inputs.
- **Entity site crawl:** a bounded crawl of the institution's own domains, using `sitemap.xml` and newsroom, press, careers, investor-relations, annual-report and disclosure paths. Page budget and depth are capped per call.
- **Filings:** `edgartools` in-process, with a local cache on a writable volume. Bulk `companyfacts.zip` / `submissions.zip` are used for peer-scale pulls.
- **Ranking:**
  - stage 1: BM25 (`rank_bm25` or `bm25s`) over chunks;
  - stage 2: a small open-source embedding model plus a cross-encoder reranker, via `fastembed` (ONNX, CPU).
  - Bake the models into the image; verify the model licences and pick the best performer on the golden set (Section 4), not by reputation.
- **Dedupe:** MinHash/SimHash near-duplicate clustering. Syndicated press-release copies collapse into **one origin cluster**; syndication count is recorded but **never counted as independent corroboration**.
- **Storage:**
  - Full cleaned text goes to GCS, keyed by content hash.
  - A cache (Firestore or GCS JSON) holds search results, extractions and cards, with TTLs by recency class.
  - Agents never receive full documents unless they explicitly ask for a span.

## 2. Evidence card contract (token-optimized, gold-standard)

### Derive the contract from the data, not from this brief
1. Read the `register_evidence` input schema from the live DMA Insights connector (`tools/list`).
2. Read the evidence items in the **Baxter Credit Union** gold-standard payload (and Logix as the counter-example).

The card must map **1:1** onto `register_evidence`, so the producer registers it with zero reformatting tokens. Every field Baxter evidence carries must be present. Nothing internal-only may leak onto client-facing surfaces: internal fields are kept separate and stripped at the existing promotion allowlist.

### Baseline card (adjust to the real schema; record every change)
```json
{
  "card_id": "EV-<hash8>",
  "url": "https://...",            
  "url_status": "live|archived",
  "archive_url": null,
  "source_name": "NCUA",
  "source_type_hint": "regulator|filing|entity_owned|trade_press|news|academic|other",
  "tier_hint": "T2",              
  "published": "15 March 2026",
  "retrieved": "10 October 2026",
  "recency": "CURRENT|RECENT|LEGACY|UNVERIFIED",
  "excerpt": "<verbatim, <=25 words>",
  "excerpt_offsets": [1234, 1391],
  "content_hash": "sha256:...",
  "context_handle": "CTX-<hash8>",
  "facet_hints": ["works", "corroborates"],
  "query_ids": ["Q-03"],
  "origin_cluster": "OC-<hash8>",
  "syndication_count": 3,
  "relevance": 0.87,
  "entity_match": "confirmed|probable|ambiguous"
}
```

### Contract rules
- **Verbatim integrity:** `excerpt` must be an exact substring of the stored cleaned text at `excerpt_offsets`, with whitespace normalization documented. This is re-checked by a test on every card, not trusted.
- **Excerpt selection:**
  - Sentence-segment the text and score sentences against the query brief.
  - Pick the minimal verbatim span of 25 words or fewer that carries the fact: numbers, dates, named capability.
  - Prefer spans containing a concrete figure or date over generic marketing sentences.
  - Generic boilerplate (cookie banners, nav, "industry-leading", "innovative solutions") is filtered by a committed anti-pattern list. Extend it from Logix's known defects.
- **Dates:**
  - `recency` thresholds come from the repo's recency rules; read them, don't invent them.
  - If no date is extractable, the label is `UNVERIFIED`, never guessed.
  - Dates are formatted DMY.
- **Liveness:**
  - Every URL is checked at card creation.
  - If it is dead, look for a Wayback snapshot: set `url_status: archived` and record the snapshot date.
  - If neither works, **no card is emitted**. Unsourced evidence does not exist.
- **Entity disambiguation:**
  - `entity_match` must be `confirmed` (domain owned by the entity, or explicit legal-name + location/charter match) before a card can feed tech-stack or firmographic surfaces.
  - `ambiguous` cards are returned flagged, never silently included.
  - This enforces the tech-stack noise rule: attributed to the institution itself, corroborated, evidence-backed.
- **Tier hints:**
  - These come from a committed domain-to-source-type registry seeded with `fsi_domains.yaml`. The authoritative tier is assigned by the plugin's decision tree.
  - Machine-scan evidence stays **T1** per the plugin rule; the engine must never emit a lower hint for it.
- **Card size target:** at most ~120 tokens per card. Measure it, and report the average and p95.

## 3. Engine tools (progressive disclosure; every tool takes a token budget)

Expose a **small** tool surface; five to seven tools is the right size. Verbose tool lists cost tokens on every call.

| Tool | Input | Returns |
|---|---|---|
| `research_brief` | `run_id`, entity (legal name, domains, charter/CIK if known), sub-vertical, facet, question(s), subcap IDs (opaque labels only, for logging), `max_cards`, `token_budget` | Ranked evidence cards + a coverage block (below). One call replaces a search → open → read → excerpt loop. |
| `crawl_entity` | `run_id`, entity domains, page budget, path focus (newsroom, careers, IR, disclosures) | Cards from the institution's own pages + a crawl manifest (pages seen, skipped, robots-blocked) |
| `filings_evidence` | `run_id`, CIK/ticker, forms, years, topics | Cards anchored in 10-K/10-Q/8-K sections + XBRL facts with exact values and filing URLs |
| `expand_context` | `context_handle`, window (sentences) | The surrounding text **only on demand**: for disambiguation, challenger checks, or contradiction review |
| `verify_cards` | List of `card_id`s | Re-runs liveness, verbatim-offset integrity and date checks; used by `adversarial-verifier` and before promotion |
| `coverage_report` | `run_id` | Per-facet and per-subcap-label card counts, source diversity, **single-source concentration (flag if one origin cluster exceeds 40% of a unit's cards)**, recency distribution, open conflict candidates, saturation status |

### Coverage block (returned with every `research_brief`)
- **Novelty:** the share of returned cards with a new origin cluster versus what this `run_id` already holds.
- **Saturation signal:** `true` when two consecutive calls on the same facet add less than 10% novel origin clusters. Agents use it as a **stop rule**; this is the main token saver for deep research.
- **Conflict candidates:** cards from different origin clusters that carry different values for the same numeric field or date (for example two member counts). They are **flagged for the agents, never resolved or averaged** by the engine.
- **Proxy-ladder support:** when the cards returned for a question number zero, report which ladder rungs were searched (entity site, regulator, filings, trade press, news, careers). An absence finding then cites a documented search, not silence.

### Query hygiene
- The engine **expands** a question into the five facet queries (works / fails / value / contradicts / corroborates) and the domain-pack `site:` variants.
- It **never injects vendor or platform names**; the plugin's `agnostic_lint` rules are mirrored server-side as a guard.
- Evidence-led follow-ups (where a vendor name came *from* an evidence card) must pass the originating `card_id` and are logged as exceptions.

## 4. Gold-standard evaluation (gates delivery; build this before tuning)

### Golden set
Built from the real corpus, not invented:
- **Positives:** every evidence item in the **Baxter** payload (URL + excerpt + the fact it supports).
- **Negatives and anti-patterns:** the Logix defects and the anti-pattern catalogue (generic marketing, wrong-entity attribution, internal jargon, stale leadership, dead URLs).
- **Held-out:** at least one client never used for tuning (Logix, or the next real client in the DMA Drive), for generalization.

### Metrics and pass bars

Set each final bar from the measured baseline; never lower a bar to pass.

| Metric | How measured | Bar |
|---|---|---|
| Source recall | Share of Baxter evidence sources the engine re-finds within `max_cards`, given only entity + facet + question | Report baseline; target ≥ 80%; no regressions afterwards |
| Excerpt fidelity | Share of cards whose excerpt is an exact substring at its offsets | **100%** (hard) |
| URL liveness | Share of emitted cards with a resolvable live or archived URL | **100%** (hard) |
| Excerpt quality | `adversarial-verifier` blind-grades a sample of 50 cards per run: does the excerpt alone support a specific, dated, entity-attributed fact? | ≥ 90% |
| Entity precision | Share of `confirmed` cards actually about the entity (manual + verifier sample) | ≥ 98% |
| Boilerplate leakage | Cards matching the anti-pattern list | 0 |
| Syndication inflation | Origin clusters miscounted as independent corroboration | 0 |
| Token efficiency | Tokens consumed by agents per accepted evidence item: engine path vs current raw-fetch path, same questions | Report both; target at least 60% reduction with no recall or quality loss |
| Generalization | All metrics above on the held-out client | Within 5 points of the tuning set |

**Anti-gaming rules:**
- No Baxter- or client-specific strings, domains or rules in engine code. A grep check in CI enforces it.
- The golden set is versioned. Changing it requires a logged reason, and metric deltas are reported across golden-set versions.

## 5. Build phases

### Phase A: Discovery (read-only)
Read the repo end to end:
- `.mcp.json`, every `agents/*.md` frontmatter, `hooks/hooks.json`, `doctor.py`, `3-mcp-tools.md`;
- the enrichment-source registry or the Clay/Explorium taxonomy;
- the evidence-tier decision tree and recency thresholds;
- `04-craft/9-antipatterns.md`, the surface contracts, and the Baxter and Logix payloads (via the connector's read tools: `get_report_bundle`, `get_evidence`, `get_staged_payload` as available).

Confirm the GCP project, region, and the path-token + `user_config` pattern. Output a discovery summary and the derived card contract, then continue.

### Phase B: Self-hosted backends
Build SearXNG, Fetch and EDGAR as specified previously:
- Each is wrapped by Supergateway (`docker.io/supercorp/supergateway:uvx`) and exposed over Streamable HTTP on a secret path.
- SearXNG runs on `127.0.0.1` inside its container.
- SearXNG uses the FSI engine profile and `fsi_domains.yaml`.
- Supergateway: test stateless vs `--stateful` and choose on measured latency.

### Phase C: Evidence engine
- Implement Sections 1–3 under `infra/evidence-engine/` (or the repo's convention), with unit tests for every component:
  - extraction on a fixture corpus of saved FSI pages and PDFs;
  - verbatim-offset integrity;
  - date extraction;
  - dedupe clustering;
  - ranking order;
  - excerpt length and boilerplate filter;
  - entity matching.
- Fixtures are committed so the tests run offline in CI.

### Phase D: Evaluate
Build the golden set and run Section 4. Iterate on:
- ranking models and weights;
- chunk size;
- excerpt scorer;
- boilerplate list;
- crawl paths.

**Max two tuning iterations per metric before escalating** with the data. Report what was tried, what moved each metric, and what held.

### Phase E: Deploy (after approval)
- Print the plan and STOP for approval before any resource-creating `gcloud` command.
- Engine sizing: 2Gi memory or more (models in memory); `--cpu-boost`; `--max-instances 2`; `--concurrency` tuned from measurement.
- Re-run the Section 4 suite against the live services, plus the earlier smoke tests (wrong path returns 404; `tools/list` is non-empty).

### Phase F: Plugin wiring
- **`.mcp.json`:** declare `evidence-engine`, `searxng`, `fetch`, `edgar`, `parallel` and `alphaxiv`. Self-hosted URLs are assembled from `user_config` sensitive tokens, mirroring the existing connector. Plugin-declared servers are canonical; deny any account-level duplicates in `disallowedTools`, checking the real names from a live listing.
- **Agent scoping (`mcpServers:` frontmatter):**

| Agent | Connectors |
|---|---|
| Per-page producers + `surface-producer` | evidence-engine (primary), alphaxiv, raw fallbacks |
| `finding-challenger`, `adversarial-verifier` | evidence-engine (`verify_cards`, `expand_context`, independent `research_brief`), raw fallbacks |
| `page-consolidator` | evidence-engine `verify_cards` + `expand_context` only |
| Others | none, unless discovery shows a need |

- **Skill updates:**
  - `dma-research` and `dma-surface-production` instruct agents to call `research_brief` first, respect `saturation`, use `expand_context` only when needed, and register cards via `register_evidence` unchanged.
  - Raw fallback tools are used only when the engine is down or a card is disputed.
  - The write-lock is unchanged.
- **Enrichment-source registry:** add all six with facets, tier roles and fallback chains. Search hits are discovery only; cards are evidence candidates; tiers are assigned by the decision tree.
- **Docs and doctor:**
  - Regenerate `3-mcp-tools.md` from live `tools/list`.
  - `doctor.py` checks each connector: reachable, tools present, hook matchers name real tools.
  - A missing raw fallback is a WARNING. A missing evidence-engine with no working search fallback is a BLOCKER.

## 6. Rate limits: fixes and alternatives

### 6a. The engine absorbs rate limits centrally

The engine is now the single choke point, so limits are enforced once, globally, instead of per agent.

- **Per-source token buckets inside the engine**, shared across all requests:

| Source | Limit |
|---|---|
| SEC EDGAR | **8 requests/s global** (SEC fair-access ceiling is about 10/s with a declared User-Agent; verify current policy). `SEC_EDGAR_USER_AGENT` always set. |
| Per-host page fetches | **1 request/s per host**; robots.txt always honoured |
| Parallel | Measured ceiling × 0.7 (ramp 1/2/5/10 requests/s for 60s each; record the first 429 and its `Retry-After`) |
| SearXNG upstream engines | Governed by SearXNG settings (below) + engine concurrency cap |
| arXiv direct (if used) | 1 request per 3s per arXiv's API guidance |

- **Circuit breakers per source:**
  - On 429, CAPTCHA, 403 streak or empty-result streak, back off exponentially (30s → 10 min cap), honouring `Retry-After`.
  - Calls auto-route to the next source in the chain; the reroute is recorded in the card provenance.
- **Caching = the biggest rate-limit fix:**
  - Search results are cached 24h.
  - Extractions and cards are cached by content hash, with the TTL by recency class.
  - EDGAR facts are cached until the next filing date.
  - Repeat queries across agents and runs never hit upstream.
- **Request coalescing:** identical in-flight queries from the parallel agents are merged into one upstream call.
- **Plugin-side backstop:**
  - Keep a lightweight `rate_gate.py` PreToolUse hook only on the **raw fallback** tools: per-source bucket, `fcntl` lock, 5s timeout, **fail open**, exit 2 with a redirect message.
  - Plus `source_health.py` PostToolUse logging to `source_health.jsonl`, using tail-scan or a counts sidecar, never the O(n) re-read.

### 6b. Per-source fixes and fallback chains

| Need | Chain (free first; paid only with explicit approval) | Fixes |
|---|---|---|
| Web discovery | SearXNG → Parallel → Tavily/Exa (paid, confirm) | SearXNG: engine diversity so results stay useful with Google/Bing blocked (weight `mojeek`, `brave`, `duckduckgo`, `qwant`, academic engines); tune `search.suspended_times` (verify key names) so blocked engines cool off; `outgoing.max_request_timeout: 12`; Cloud Run `--concurrency 10`; **static egress IP** via a Serverless VPC connector + Cloud NAT with a reserved address, with engine health measured before and after |
| Page read | Engine fetch → Parallel `web_fetch` → Wayback snapshot (dated, recency-labelled) → Firecrawl/Tavily extract (paid, confirm) | Per-host politeness; retry once on 429/503, never on 403; robots.txt always honoured; static NAT IP shared with the engine |
| Filings | `edgartools` in-process (cached) → bulk `companyfacts.zip`/`submissions.zip` for peer-scale pulls → Quartr for earnings context | Global 8 requests/s bucket; local cache |
| Academic | alphaXiv → SearXNG academic engines (`arxiv`, `semantic scholar`, `openalex`, `crossref`) → Firecrawl paper tools (paid, confirm) | Measured alphaXiv bucket; arXiv's 3s guidance |
| Cold starts | n/a | `--cpu-boost`; models baked into the image; `--min-instances 1` for the engine only if measured cold starts cause agent timeouts (always-on cost; requires approval) |

### 6c. Alternatives if SearXNG stays degraded after 6b
Present each with measured engine health and its cost; never auto-enable.
1. **Brave Search API free tier** (keyed, not open source) as a SearXNG engine. Verify the current terms first.
2. **Rotating/residential proxy** in `outgoing.proxies`. Most effective against IP blocks; paid.
3. **Mojeek API.** Paid; only if Mojeek leads the FSI health table.
4. **Excluded:** Marginalia and YaCy. Their regulator and trade-press coverage is too thin for FSI evidence.

### 6d. Rate-limit tests (committed, in CI)
- **Burst:** 9 concurrent simulated agents, 50 `research_brief` calls; zero lost queries, every source under its bucket.
- **Breaker:** an injected 429 from Parallel reroutes to SearXNG; the breaker half-opens after backoff; the reroute appears in card provenance.
- **EDGAR global cap:** 100 lookups never exceed 8 requests/s, measured from timestamps.
- **Coalescing + cache:** the same query from 3 agents produces 1 upstream call; a repeat run produces 0.
- **Fail-open:** a corrupt hook state file allows the call and logs a warning.
- **Paid-only remainder:** when only paid sources remain, the engine returns a structured `needs_spend_approval` result. It never spends silently.

## 7. Hard rules (apply throughout)

1. **Preserve confirmed-correct structures:**
   - scoped hook matchers `mcp__plugin_dma-insights_<server>__<tool>`;
   - the write-lock (only `surface-producer` submits, promotes or registers);
   - `mcp_auth_headers.sh` exit-0 semantics;
   - existing hooks and their wiring.
2. **Gate before spend:** STOP for approval before any resource-creating `gcloud` command, paid key, proxy, always-on instance or credit use.
3. **Secrets are never printed, logged or committed.** Mask tokens as `/mcp-****`.
4. **Nothing faked:** every claim backed by real command output. Failing metrics are reported, not hidden.
5. **Verify every upstream name, flag, model, setting key and licence** against current docs or the installed version, as of 10 October 2026. Log corrections.
6. **Rate limits are measured where unpublished**, and published ones are re-verified.
7. **No client-specific hardcoding** in the engine (CI grep check).
8. **Confidence only moves down** in any verifier-facing output. Max two tuning iterations per metric, then escalate with data.

## 8. Packaging and hand-off

- Bump the plugin version (next patch) and update the CHANGELOG. Produce the plugin as a **zip** (the user uploads zips only). Engine and backend infra code are committed on the same branch.
- PR description includes:
  - the derived card contract (and the diff from this brief's baseline);
  - golden-set results, tuning set vs held-out, against every Section 4 bar;
  - the token-efficiency comparison;
  - measured rate limits and bucket sizes;
  - SearXNG engine health before/after the static IP;
  - cold and warm latencies;
  - every upstream-name correction;
  - an end-to-end Claude Code transcript excerpt where a producer researches one subcap via `research_brief`, registers cards via `register_evidence`, and `adversarial-verifier` passes `verify_cards` on them.

## 9. Definition of done

- [ ] All Section 4 hard bars met (excerpt fidelity 100%, URL liveness 100%, boilerplate 0, syndication inflation 0), and the remaining bars met or explicitly escalated with data.
- [ ] Held-out client within 5 points of the tuning set on every metric.
- [ ] Token reduction per accepted evidence item measured and reported against the raw-fetch baseline.
- [ ] Cards register via `register_evidence` with zero transformation, and survive the promotion allowlist with no internal-field leakage (checked on a staged payload).
- [ ] All six connectors reachable through the plugin's scoped names inside Claude Code; `doctor.py` covers them.
- [ ] Section 6d tests pass in CI; no client-specific strings in engine code.
- [ ] Zip delivered; no token in git history.

## 10. HALT conditions (stop and report; never work around)

- Excerpt fidelity or URL liveness below 100% after two fix iterations.
- Source recall on the held-out client more than 10 points below the tuning set (overfitting).
- `register_evidence` schema cannot be met 1:1 by the card without dropping a Baxter field.
- Fewer than 3 responding general-web SearXNG engines after the 6b fixes; present the 6c options with costs.
- Any deploy would modify `dmai-mcp` or an existing service.
- Any paid key, proxy, always-on instance or credit spend.
- Any change touching the write-lock, the core connector's hook matchers, or `mcp_auth_headers.sh` semantics.
