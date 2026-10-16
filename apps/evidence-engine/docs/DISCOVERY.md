# Phase A — discovery summary (read-only), 2026-10-10

What the brief assumed, what the repository actually holds, and what the
engine is therefore built against. Every row below was read from the
checkout at `96abc60` or measured against the live connector; nothing is
recalled.

## 1. The plugin as it is

| Brief assumed | Repository holds | Consequence for this build |
|---|---|---|
| Plugin "v0.3.2 or later" | `plugins/dma-insights/.claude-plugin/plugin.json` is **1.22.0**; 76 agents; 36 connector tools | Version bumps to 1.23.0 |
| `.mcp.json` assembles self-hosted URLs from `user_config` **sensitive tokens**; a URL path token (`/mcp-****`) | One server, `connector`, is a **stdio proxy** (`scripts/mcp_proxy.py`) that mints headers through `scripts/mcp_auth_headers.sh`: a Google ID token (`Authorization: Bearer`, Cloud Run `run.invoker`) and the capability token as the **`X-DMA-Path-Token` header** read from env → cache file → Secret Manager. The path-segment design was retired 2026-08-20 ("install must be automatic"); `user_config` holds only `mcp_base_url` and `repo_root`, neither sensitive | The evidence engine is declared the same way: a second stdio proxy entry pointing the SAME header rungs at the engine's URL (its own audience, its own Secret Manager token). No token in `user_config`, no URL segment, nothing to paste. The brief's token-masking rule is honoured where it bites: no credential is printed, logged or committed |
| Hook matchers `mcp__plugin_dma-insights_<server>__<tool>` | `hooks/hooks.json` matches `mcp__.*__submit_page_payload` / `mcp__.*__promote_run` (server-agnostic, by design — a Routine attaches the same server under `DMA-Insights`); agents' `tools:` lines use the scoped form `mcp__plugin_dma-insights_connector__<tool>` | New hooks follow the same pattern; `doctor.tool_roster_check` already derives scoped prefixes from every server in `.mcp.json`, so adding servers there extends the check for free |
| Agent scoping through `mcpServers:` frontmatter | `scripts/package_plugin.py` lists `mcpServers` in **`FORBIDDEN_AGENT_KEYS`** ("the hosted schema refuses"); `tests/skills/test_agent_tool_provisioning.py` pins every `tools:` line to the role table in `scripts/provision_agent_tools.py` (K ≤ 5 capability tools per agent; `CONNECTOR_TIER` ceilings; exact holder sets per connector family; fleet tripwire ≤ 1,300 grants) | Scoping is done by adding engine tool names to role rows in the provisioner and regenerating; `mcpServers:` is never written |
| `fsi_domains.yaml` seeds the tier registry | **No such file anywhere in the repo.** The tier rules live in `apps/mcp/dma_mcp/source_rules.py` (regulatory suffixes/hosts, vendor-collateral path shapes, scan producers) and `skills/dma-research/engine/contract.py` (`SCAN_TIER`, `FACT_TIERS`); the enrichment registry is `skills/dma-surface-production/02-inputs/enrichment_sources.json` | The engine commits its own `registry/fsi_domains.yaml`, seeded from `source_rules.py`'s lists so the two cannot disagree (a test pins the shared hosts), and the plugin's registry file gains the six connectors |
| `agnostic_lint` rules exist in the plugin | **No `agnostic_lint`** in the repo. The nearest rules are the quote-admissibility tests in the client-profile template and `source_rules.vendor_collateral` | The engine ships a committed vendor-name guard (`engine/query_guard.py`) and the evidence-led exception path; it is documented as new, not as a mirror |
| Recency labels `CURRENT / RECENT / LEGACY / UNVERIFIED` | `CURRENT (<12) · RECENT (<24) · DATED (<36) · STALE (<48) · ARCHIVAL (≥48) · UNVERIFIED` months before the run's reference date — `engine/contract.py RECENCY_LADDER`, `apps/mcp/dma_mcp/register.py _recency_band` (QA Report B-09; the H7 contract reads the same words) | The card carries the six-word ladder; `LEGACY` never appears |
| Dates formatted DMY | `register_evidence` parses `published_date` with `date.fromisoformat(v[:10])`; `engine.cli evidence --published` takes `YYYY-MM-DD` / `YYYY-MM` / `YYYY-Qn` / `YYYY` | The card's `published_date` is ISO `YYYY-MM-DD`. A DMY string would be stored as **undated** (UNVERIFIED) — the opposite of the brief's intent |
| Excerpt ≤ 25 words | `register_evidence` and `ledger.append_evidence` refuse an excerpt outside **50–500 characters**; `excerpt_clip.clause_truncated` refuses a clause hard-cut mid-word at the clip width; `abbreviations.EXCERPT_FIELDS` forbids rewriting a span | The excerpt is the minimal **sentence-complete** span of 50–500 chars that carries the fact; the selector targets ≤ 40 words and never emits a span that ends mid-word or mid-clause. "≤ 25 words" is kept as a *preference weight*, not a cap, because 25 words of prose is frequently under 50 characters only in headlines and often cuts the figure the fact needs |
| Baxter payload = gold standard, Logix = counter-example | `docs/GOLD-STANDARD.md` names **Golden 1 Credit Union** (`DMA-2026-GOLDEN1-001`, run `40971653…`) as the gold package; `fixtures/gold_manifest.json` (2026-08-20) pins Baxter and Logix as the *app-page* exemplars of that date. Measured on the live staged `heatmap.evidence`: Baxter 98 rows, **35 clause-truncated at 80/100/120 chars, 47 undated, 15 Explorium-connector rows, 56 distinct URLs**; Golden 1 541 rows, 499 dated, 1 truncated, but only **40 rows carry a URL** (the rest are the client's internal package); Logix 16 rows, all URLs, 11 dated | Golden set (Phase D): positives = every **public-URL** row of Golden 1 and Baxter (tuning); Logix is the held-out client. Baxter's truncated spans are catalogued as negatives (the "hard clip" anti-pattern), not as positives |
| Phase A reads `3-mcp-tools.md` | The generated reference is `plugins/dma-insights/docs/MCP-TOOLS.md` (from `scripts/gen_mcp_tools_md.py` over `apps/mcp/server.py`); `skills/dma-surface-production/02-inputs/3-mcp-tools.md` is the hand-written map | Both are updated; the generated one is regenerated, the map gains the engine's six tools |

## 2. Where evidence actually enters

Two write paths exist, and the card must fit both without reformatting:

1. **The connector** — `register_evidence(run_id, item)`
   (`apps/mcp/dma_mcp/register.py`). Held by **one** agent, `surface-producer`
   (the write-lock; every other manifest denies it). The item's fields:
   `source_name`, `source_url`, `excerpt`, `claim_type`, `tier`,
   `published_date`, `linked_subcap_ids`, `facts`, `origin`
   (+ `connector{…}`, `split_of`, `customer_attribution`, `whole_row` for the
   other origins). The server fetches `source_url` itself and refuses
   `excerpt_not_verbatim` / `url_unreachable`; computes ERS; allocates `E-CC-nnn`.
2. **The research engine** — `engine.cli evidence|batch` writing the run
   workbook (`skills/dma-research/engine/ledger.append_evidence`), which is
   what the haiku collectors and the sonnet orchestrator use (the research
   tiers hold **no** connector write). It verifies the span against the text
   `engine.cli fetch` cached under the run (`fetch_cache/`), refuses
   own-domain T1, a scan below T1, a FACT off T1/T2, a retrieval date posing
   as a publication date, and fills an omitted date from the page's own
   metadata. Its flags: `--source --url --tier --excerpt --published
   --claim-type --origin --subcap --actor --unverified`.

Both normalise an excerpt the same way for the verbatim test: whitespace
collapsed, case folded, nothing else (`fetch.normalise`, pinned equal to the
connector's by `test_fetch_windows.py::test_the_extractor_agrees_with_the_connectors`).
The engine's cleaned text therefore has to be **the same prose** those two
extractors produce from the same bytes, or a span the engine verified will
fail at the ledger. Section 5 of `CARD-CONTRACT.md` states how that is
guaranteed.

## 3. The research tiers the engine serves

`agents/research/research-evidence-collector.md` (haiku; WebSearch, WebFetch,
Exa, Tavily; `engine.cli fetch` + `batch`), `research-category-orchestrator`
(sonnet; engine-only), `research-challenger` (sonnet; engine-only),
`research-conductor` / `enrichment-web-specialist` (the servicing tier that
holds the connectors), `finding-challenger` / `adversarial-verifier`
(opus; connector reads only, no web by design: "a checker that fetches can
be shown a page nobody registered"). The protocol
(`skills/dma-research/references/RESEARCH-PROTOCOL.md § Tools`) is the one
statement of tool order; the engine slots in as rung 3 (discovery) and rung
5 (reading) and its cards are what a collector registers.

Lean headless lanes (`scripts/agent_run.py lean_command`) run
`claude -p --strict-mcp-config --setting-sources ""` with **no MCP servers at
all** — so on a degraded run the collectors cannot reach any MCP connector,
the engine included. The engine therefore also ships a thin CLI
(`engine.cli evidence-brief`, calling the same HTTP endpoint) so a lean lane
reaches it over Bash exactly as it reaches `engine.cli fetch`.

## 4. Upstream facts verified on 2026-10-10

| Item | Verified | Correction to the brief |
|---|---|---|
| FastMCP | `fastmcp==4.1.0` (Apache-2.0); `FastMCP.http_app(path=, stateless_http=, json_response=)`, `Middleware.on_call_tool`, `Client(transport=url)` | brief said "native Streamable HTTP" — correct; the transport literal is `"http"` |
| trafilatura / htmldate | 2.3.1 / 1.11.0, both Apache-2.0; `extract(html, url=, favor_recall=, include_tables=)`; `find_date(html, url=, original_date=True)` | none |
| pypdfium2 | 5.14.0, BSD-3-Clause + Apache-2.0 (PDFium) | none; PyMuPDF (AGPL) is not used |
| Ranking | `bm25s` 0.3.13 (**no licence string in its wheel metadata** — the project is MIT on GitHub; recorded, and `rank-bm25` 0.2.2 Apache-2.0 is the committed fallback); `fastembed` 0.9.0 Apache-2.0 | models chosen by golden-set measurement in Phase D among: `BAAI/bge-small-en-v1.5` (MIT, 384-d, 67 MB), `snowflake-arctic-embed-xs` (Apache-2.0), `all-MiniLM-L6-v2` (Apache-2.0, the connector's own family); rerankers `Xenova/ms-marco-MiniLM-L-6-v2` (Apache-2.0, 80 MB), `BAAI/bge-reranker-base` (MIT, 1.04 GB). `jina-reranker-v2-base-multilingual` is **CC-BY-NC-4.0** and excluded |
| Dedupe | `datasketch` 2.0.0 MIT (`MinHash`, `MinHashLSH`) | none |
| Filings | `edgartools` 5.61.1 MIT; `set_identity`, `Company(...)`, `get_filings(form=)`, `get_financials()`; local cache via `EDGAR_LOCAL_DATA_DIR` / `use_local_storage()` | none |
| SEC fair access | sec.gov "Accessing EDGAR data": **"Current max request rate: 10 requests/second"**, declared User-Agent `Sample Company Name AdminContact@…`, `Accept-Encoding: gzip, deflate`; `data.sec.gov/submissions/CIK….json` answered 200 to the declared UA from this container | engine bucket **8 req/s global** stands (0.8 × ceiling) |
| Parallel Search MCP | `https://search.parallel.ai/mcp`, anonymous **200** on `initialize` (server "Parallel Web Search MCP Server" 1.27.0), `tools/list` → **`web_search`** (`objective`, `search_queries[]`, `session_id`, `model_name`) and **`web_fetch`** (`urls[]`, `objective`, `search_queries`, `full_content`, `allow_live_fetch`, …); docs: free anonymously "at lower rate limits", limits unpublished, excerpts capped ≈ 25,000 chars per call, `/mcp-oauth` for keyed use | the ceiling is **measured** (Phase D ramp), never assumed |
| alphaXiv MCP | `https://api.alphaxiv.org/mcp/v1` answers **401 `Missing Authorization`** anonymously with `ratelimit: limit=1500000; w=3600` headers; OAuth is per user | agents call it directly; the engine never does (no user credential server-side) |
| Wayback | `archive.org/wayback/available?url=…&timestamp=…` answers with the closest snapshot; `…/web/<ts>id_/<url>` returns the original bytes without the toolbar | the `id_` form is what the card's `source_url` carries for an archived page, because the connector will fetch and verify against it |
| SearXNG | `search.formats: [html, json]` enables the JSON API; `search.suspended_times.{SearxEngineAccessDenied=86400, SearxEngineCaptcha=86400, SearxEngineTooManyRequests=3600, cf_SearxEngineCaptcha, cf_SearxEngineAccessDenied, recaptcha_SearxEngineCaptcha}`; `search.ban_time_on_fail=5`, `max_ban_time_on_fail=120`; `outgoing.request_timeout=2.0`, `outgoing.max_request_timeout=10.0`, `useragent_suffix`, `enable_http2`, `proxies`, `retries` | brief's `outgoing.max_request_timeout: 12` is a valid key; key names confirmed |
| `mcp-searxng` | MIT; Node ≥ 22; tools **`searxng_web_search`, `searxng_search_suggestions`, `searxng_instance_info`, `web_url_read`**; env `SEARXNG_URL` | brief named no tool names; these are the real ones |
| `mcp-server-fetch` | PyPI 2026.8.18, MIT; one tool **`fetch`** (`url`, `max_length`=5000, `start_index`, `raw`); honours robots.txt for model-initiated calls; `--user-agent`, `--proxy-url` | none |
| `sec-edgar-mcp` | PyPI 1.1.0, **AGPL-3.0**, Python ≥ 3.11, 18 tools (`get_cik_by_ticker`, `get_company_info`, `search_companies`, `get_company_facts`, `get_recent_filings`, `get_filing_content`, `get_filing_sections`, `get_financials`, `get_segment_data`, `get_key_metrics`, `compare_periods`, `discover_company_metrics`, `get_xbrl_concepts`, `discover_xbrl_concepts`, `get_insider_transactions`, `get_insider_summary`, `analyze_insider_sentiment`, `get_recommended_tools`); env `SEC_EDGAR_USER_AGENT` | **Licence flag.** It is run unmodified in its own container as a raw fallback only; AGPL §13 obliges offering its source to network users, which the service's `/` page does by linking the upstream repository. The engine itself links `edgartools` (MIT) in-process, so no AGPL code enters the engine |
| Supergateway | `supercorp/supergateway:uvx` image; `--stdio "<cmd>" --outputTransport streamableHttp --streamableHttpPath /<path> --port 8000`; `--stateful` + `--sessionTimeout` for legacy sessions; `--apiKey` for a required client key | stateless vs `--stateful` decided by measured latency in Phase E |

## 5. GCP and the deploy pattern

Project `digital-maturity-assessor`, region `us-central1`
(`infra/deploy.sh`). Services deploy with `gcloud run deploy --source`,
`--no-allow-unauthenticated`, a per-service service account, Direct VPC
egress for the DB services; secrets in Secret Manager only; `provision.sh`
creates identities and buckets idempotently. `dmai-mcp` serves
`/mcp/{token}` and `/mcp` + header, `stateless_http=True, json_response=True`
behind `OAuthGate(HeaderPathToken(...))`. **Nothing in this build modifies
`dmai-mcp` or any existing service** (HALT condition); the engine is a new
service `dmai-evidence` with new identity `dmai-evidence@…`, new buckets
`${PROJECT_ID}-dmai-evidence-text` / `-cache`, new secret
`dmai-evidence-path-token`, and the three backends are new services
`dmai-searxng`, `dmai-fetch`, `dmai-edgar`. The plan is printed in
`docs/DEPLOY-PLAN.md` and **stops for approval** before any
resource-creating `gcloud` command runs (Phase E).

## 6. What the engine must never do (from the repo's own rules)

- Never T1 for a page on the entity's own domain (ledger refusal, Arbor
  Bank 2026-10-06); never below T1 for a named machine scan; never a FACT
  label on T3–T5; never a retrieval date as a publication date; never a
  clause hard-cut mid-word; never an abbreviation introduced into a span
  (labels like `source_name` are spelled out: "National Credit Union
  Administration", not "NCUA" — `packages/shared/abbreviations.py`).
- Never a subcap link, a claim verdict or a final tier: the card carries
  `linked_subcap_ids: []`, a `tier` that is the registry's **hint** and a
  `claim_type` that is the label the hinted tier *licenses* (the same
  derivation `contract.claim_label_for` applies when a writer states none),
  both of which the agent may lower and the ledger will still check.
- Never a model call at request time (invariant 1): BM25, MinHash, the
  ONNX embedding/reranker and the date/extraction libraries are
  deterministic, local and bundled; nothing here is the serving path.
- Never a vendor or platform name injected into a query (`query_guard`);
  an evidence-led follow-up must name the `card_id` the name came from.
