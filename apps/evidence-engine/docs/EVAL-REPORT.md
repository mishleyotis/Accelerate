# Evidence engine — golden-set evaluation report

Run `v1-20261010T192618Z` · 2026-10-10T19:26:18+00:00 → 2026-10-10T19:48:06+00:00 (1307.7 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261010T192618Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (51/51 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 51 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 1 multi-URL clusters (73 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 165.2 · p95 221 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 100.0% (51/51; 0 unchecked for time) | 100% (hard) | MEETS | LIVE |
| Source recall, same url_key | 27.8% (5/18) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 33.3% (6/18) | (informational) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 75.0% (1153 vs 4608 tokens over 6 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 97.2% (12178 vs 439268 tokens, 74 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | None points | ≤ 5 points | not measured | both |
| Parallel rate-limit ceiling | no 429 observed up to 2/s → recommend `EE_PARALLEL_RPS=1.4` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 25 rows = 25 distinct URLs drawn with seed 20261010 from 27 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 10 rows, 10 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 1500.0 s.
- The golden set has **no question field**. Each question is derived from the row's excerpt: its content words minus the entity's name tokens, stop words and any platform name the vendor guard (`query.guard`) would refuse — an agent does not know the vendor before it finds the evidence — as `What does <entity> report about <terms>?`. Platform names were stripped from 0 question(s).

### Entities derived from the golden rows

| Client key | Split | Legal name (derived) | Own domain(s) | Aliases | Note |
|---|---|---|---|---|---|
| golden1 | tuning | Golden 1 Credit Union | golden1.com | — |  |
| baxter | tuning | Baxter Credit Union | bcu.org | BCU |  |
| logix | heldout | Logix Federal Credit Union | — (none in rows) | Logix FCU | no own-domain host among this client's rows: the engine gets no site: query and can never return entity_match=confirmed for it |

Derivation: the most frequent institution-shaped phrase (…Credit Union / Bank / …) in the client's excerpts and source names that is linked to the client key (key inside the phrase, or the phrase's initials are a host label among the client's rows); the own domain is the registrable domain among the rows' hosts whose label carries the key, sits inside the legal name, or equals its initials. No location, charter or CIK is available, so `entity_match` can only be `confirmed` on an own-domain page.

## 4. Source recall (baseline)

| Split | Client key | Rows | Re-found (url_key) | Re-found (host) | Zero-card answers | Errors |
|---|---|---|---|---|---|---|
| tuning | baxter | 8 | 1 (12.5%) | 2 (25.0%) | 0 | 0 |
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 0 | 0 |
| **tuning** | all | 18 | 5 (27.8%) | 6 (33.3%) | | |
| **heldout** | all | 0 | 0 (n/a) | 0 (n/a) | | |

Re-found by golden tier: T1: 0/1; T2: 1/2; T3: 3/11; T4: 0/2; T5: 1/2.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-28f0525b | tuning | 6 | 24 | 8 | — | {"probable": 1, "confirmed": 1, "ambiguous": 4} | 14916 ms |  |
| G-72e90e5c | tuning | 7 | 21 | 9 | url | {"probable": 5, "confirmed": 2} | 9830 ms |  |
| G-b3b2565b | tuning | 8 | 18 | 9 | — | {"probable": 6, "ambiguous": 2} | 12369 ms |  |
| G-f61d5bd5 | tuning | 3 | 25 | 3 | url | {"confirmed": 1, "probable": 1, "ambiguous": 1} | 127341 ms |  |
| G-31d70f32 | tuning | 3 | 23 | 4 | url | {"probable": 2, "ambiguous": 1} | 78682 ms |  |
| G-ed0ae381 | tuning | 3 | 27 | 3 | — | {"probable": 3} | 70031 ms |  |
| G-d5cf26ee | tuning | 8 | 16 | 11 | — | {"probable": 3, "ambiguous": 4, "confirmed": 1} | 12065 ms |  |
| G-7f52fa54 | tuning | 1 | 25 | 2 | — | {"ambiguous": 1} | 69991 ms |  |
| G-849e6d39 | tuning | 3 | 26 | 3 | — | {"probable": 3} | 70967 ms |  |
| G-3ac029f4 | tuning | 3 | 26 | 3 | url | {"probable": 2, "ambiguous": 1} | 72041 ms |  |
| G-5f2468a7 | tuning | 6 | 21 | 9 | — | {"probable": 5, "confirmed": 1} | 1955 ms |  |
| G-dc790262 | tuning | 4 | 29 | 5 | host | {"probable": 3, "confirmed": 1} | 14584 ms |  |
| G-71e0ee4d | tuning | 5 | 27 | 7 | — | {"probable": 1, "ambiguous": 4} | 11833 ms |  |
| G-4c50e3d0 | tuning | 3 | 26 | 3 | url | {"probable": 3} | 70654 ms |  |
| G-09782531 | tuning | 8 | 27 | 10 | — | {"ambiguous": 5, "probable": 3} | 12171 ms |  |
| G-9d8d0ecc | tuning | 1 | 23 | 1 | — | {"probable": 1} | 69289 ms |  |
| G-9497e56e | tuning | 1 | 26 | 1 | — | {"probable": 1} | 77372 ms |  |
| G-031af79c | tuning | 1 | 21 | 2 | — | {"probable": 1} | 171171 ms |  |
| G-477d3bf9 | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-8d3ac455 | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-0e516f75 | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-52b47f1a | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-2ab20603 | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-40b1e5f2 | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-854ee8db | tuning | — | — | — | — | — | — | skipped: time budget exhausted |
| G-e17d0b25 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-3a1e7d51 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-7f981e71 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-7089793b | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-4a494c46 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-116af624 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-bde7e098 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-6a9172d1 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-b4c11e10 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |
| G-29834d49 | heldout | — | — | — | — | — | — | skipped: time budget exhausted |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 53736 ms · p95 171171 ms · max 171171 ms over 18 calls. Warm repeats: tuning cold 14916 ms → warm 5864 ms (cached search calls {'parallel': 5})
- Totals: hits 431 · fetched 93 · cards 51 · fetch failures shown 121 · dropped shown 12 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 967.3, "warm_repeat": 5.9, "liveness": 37.5, "token_efficiency": 235.4, "ramp": 61.2}
- Breakers open at the end: ['en.wikipedia.org', 'ori-cms-104.golden1.com', 'tyfone.com', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.yahoo.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 85, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×12
- Fetch-failure reasons (shown subset): timed out fetching www.goldenN.com after Ns ×34; robots_disallowed ×28; timed out fetching goldenN.com after Ns ×10; http N from www.bcu.org ×9; http N from en.wikipedia.org (served by HAProxy) (WAF or access denied ×5; http N from ori-cms-N.goldenN.com (WAF or access denied) ×4; http N from tyfone.com (served by cloudflare) (WAF or access denied) ×3; http N from www.businesswire.com (served by AkamaiGHost) (WAF or acces ×3

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 51.

Golden NEGATIVE rows with a considered defect (hard_clip, not_sentence_complete, machine_text, internal_jargon): 131; the anti-pattern list + `contract.item_problems` excerpt rules would have refused **130** (99.2%).

| Defect class | Golden rows | Refused | Share | By rule |
|---|---|---|---|---|
| hard_clip | 35 | 34 | 97.1% | excerpt_not_sentence_complete ×34 |
| not_sentence_complete | 118 | 118 | 100.0% | excerpt_not_sentence_complete ×118 |
| machine_text | 5 | 5 | 100.0% | boilerplate:"averageUserRating"\s*: ×5 |
| internal_jargon | 7 | 7 | 100.0% | boilerplate:\b[Pp][1-4][Cc]\d(\.\d+){0,2}\b ×7 |

Rows a defect class marks that NO rule refuses (gaps to extend the list from; golden ids only — excerpts in the results JSON):
- hard_clip: G-60d6957e (100 chars)

## 7. Card size

| Projection | Cards | Mean tokens | p95 | Min | Max |
|---|---|---|---|---|---|
| item + minimal provenance | 51 | 165.2 | 221 | 127 | 224 |
| item + standard provenance | 51 | 207.0 | 259 | 168 | 266 |
| item + full provenance | 51 | 315.6 | 375 | 269 | 385 |
| item only | | 120.6 | 176 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 18 | 6 | 4608 | 1153 | 75.0% | 9 |
| heldout | 0 | 0 | 0 | 0 | n/a | 0 |
| **all** | 18 | 6 | 4608 | 1153 | 75.0% | 9 |

Secondary (every produced card against its own source page): 97.2% reduction, 74 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 6903.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: None
- source_recall_host: None
- url_liveness: None
- token_reduction: None
- excerpt_fidelity: None
- max_gap_points: None
- within_bar: None

## 10. Parallel rate-limit ramp

- 90 `web_search` calls in 61.2 s; ok by rate {"1.0": 30, "2.0": 60}; errors by rate {}; latency p50 1871.0 ms, p95 2417 ms.
- First 429: null; raw probe after it: null.
- Measured ceiling: **no 429 observed up to 2/s** → recommended `EE_PARALLEL_RPS=1.4` (measured × 0.7; the engine's default stays 1.0 until this is adopted).

## 11. Limitations — read before quoting a number

- Discovery ran on ONE free source (Parallel Search MCP, anonymous). SearXNG — the brief's primary backend — is not deployed in this environment, so recall is the recall of Parallel alone through the engine's five facet queries and its own-domain `site:` query; the registry `site_pack` is empty, so no regulator/trade-press `site:` probes ran.
- Questions are DERIVED from golden excerpts (no question field exists). A derived question carries the excerpt's own vocabulary, which favours re-finding the page the excerpt came from; a diagnostic question an agent asks would not. Treat recall as an upper-ish bound of the retrieval path, not as the recall of the research protocol.
- Platform names in an excerpt were stripped from the question (the vendor guard refuses them; an agent does not know the vendor in advance), so golden rows whose fact IS a vendor relationship are asked about as capability terms only.
- Entities are derived from the golden rows alone: no location, charter number or CIK, so `entity_match` is `probable` at best off the own domain; `logix` has no own-domain host in its rows (no `site:` query, no `confirmed` match).
- Token counts use the 4-chars-per-token heuristic over compact JSON (`tiktoken` is not installed); the ~120 target and the reduction figures are heuristic tokens, not a tokenizer's.
- Token efficiency is tokens of content (cleaned page vs card), not a transcript measurement of an agent's turn; the denominator excludes the search hits an agent would also read.
- Ranking was BM25-only (`EE_MODELS_DIR` unset): the dense + cross-encoder rerank the design expects was not exercised.
- The research_brief answer truncates `fetch_failures` and `dropped` at 10, so drop/failure totals are lower bounds.
- Liveness is one GET (first chunk) per card URL at the time of the run; a WAF that answers a browser UA differently later is not captured. 0 card(s) were not checked because the time budget ran out.
- The golden-negative census applies only the EXCERPT rules (anti-pattern list, length, clause clip at 140, sentence completeness) to rows the golden builder tagged; `hard_clip` in the golden set covers widths 80/100/120/140 while the connector's `clause_truncated` signature is 140 only, so an 80/100/120 clip is refused only when it also fails sentence completeness.
- Tuning positives were sampled (one row per distinct URL, seeded); a golden URL with several rows was asked ONE question.
- Held-out positives: 10 rows from one client — the held-out split is small, so its recall moves in steps of ~8 points and the generalisation gap is coarse.
- The Parallel ramp is a polite, short measurement (≤ 90 calls, ≤ 60 s) from one network location; a free anonymous tier's ceiling may differ by hour and by origin.
- 7 tuning call(s) were skipped for time.

## 12. Golden-set version deltas

- v1 is the first version; no previous run to diff against.

