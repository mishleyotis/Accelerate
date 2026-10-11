# Evidence engine — golden-set evaluation report

Run `v1-20261011T034953Z` · 2026-10-11T03:49:53+00:00 → 2026-10-11T04:08:46+00:00 (1132.7 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261011T034953Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (123/123 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 123 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 3 multi-URL clusters (177 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 159.2 · p95 224 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 99.2% (122/123; 0 unchecked for time) | 100% (hard) | BELOW | LIVE |
| Source recall, same url_key | 31.4% (11/35) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 34.3% (12/35) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 51.4% (11 carded + 7 surfaced-unreadable / 35) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 83.8% (1905 vs 11790 tokens over 11 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 98.5% (28511 vs 1910349 tokens, 180 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | 12.0 points | ≤ 5 points | ABOVE | both |
| research_brief answer size an agent reads (tokens, whole answer) | mean 2530.5 · p95 3784 · max 3807 (cards 64.2% of it) | (informational) | — | offline |
| Parallel rate-limit ceiling | not run → recommend `EE_PARALLEL_RPS=?` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 25 rows = 25 distinct URLs drawn with seed 20261010 from 27 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 10 rows, 10 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 1800.0 s.
- The golden set has **no question field**. Each question is derived from the row's excerpt: its content words minus the entity's name tokens, stop words and any platform name the vendor guard (`query.guard`) would refuse — an agent does not know the vendor before it finds the evidence — as `What does <entity> report about <terms>?`. Platform names were stripped from 4 question(s).

### Entities derived from the golden rows

| Client key | Split | Legal name (derived) | Own domain(s) | Aliases | Note |
|---|---|---|---|---|---|
| golden1 | tuning | Golden 1 Credit Union | golden1.com | — |  |
| baxter | tuning | Baxter Credit Union | bcu.org | BCU |  |
| logix | heldout | Logix Federal Credit Union | — (none in rows) | Logix FCU | no own-domain host among this client's rows: the engine gets no site: query and can never return entity_match=confirmed for it |

Derivation: the most frequent institution-shaped phrase (…Credit Union / Bank / …) in the client's excerpts and source names that is linked to the client key (key inside the phrase, or the phrase's initials are a host label among the client's rows); the own domain is the registrable domain among the rows' hosts whose label carries the key, sits inside the legal name, or equals its initials. No location, charter or CIK is available, so `entity_match` can only be `confirmed` on an own-domain page.

## 4. Source recall (baseline)

| Split | Client key | Rows | Re-found (url_key) | Re-found (host) | Surfaced but unreadable | Zero-card answers | Errors |
|---|---|---|---|---|---|---|---|
| tuning | baxter | 15 | 3 (20.0%) | 4 (26.7%) | 3 | 0 | 0 |
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 3 | 0 | 0 |
| heldout | logix | 10 | 4 (40.0%) | 4 (40.0%) | 1 | 0 | 0 |
| **tuning** | all | 25 | 7 (28.0%) | 8 (32.0%) | 6 | | |
| **heldout** | all | 10 | 4 (40.0%) | 4 (40.0%) | 1 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: robots_disallowed (slot refunded) ×1; fetch failed: http N from www.savvymoney.com (served by nginx) (WAF or access de ×1; fetch failed: http N from www.scworld.com (served by cloudflare) (WAF or access  ×1; fetch failed: http N from thefinancialbrand.com (served by cloudflare) (WAF or a ×1; fetch failed: timed out fetching www.goldenN.com after Ns ×1; fetch failed: breaker_open:www.goldenN.com (slot refunded) ×1; fetch failed: http N from www.insight.com (served by AkamaiGHost) (WAF or access ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 1/5; T3: 7/21; T4: 0/2; T5: 3/6.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-28f0525b | tuning | 3 | 197 | 7 | — | {"confirmed": 2, "probable": 1} | 44358 ms |  |
| G-72e90e5c | tuning | 5 | 144 | 9 | url | {"probable": 2, "confirmed": 3} | 22922 ms |  |
| G-b3b2565b | tuning | 3 | 168 | 9 | — | {"probable": 2, "confirmed": 1} | 26929 ms |  |
| G-f61d5bd5 | tuning | 2 | 112 | 2 | url | {"confirmed": 1, "probable": 1} | 56172 ms |  |
| G-31d70f32 | tuning | 4 | 95 | 6 | url | {"probable": 4} | 39254 ms |  |
| G-ed0ae381 | tuning | 3 | 152 | 3 | — | {"probable": 3} | 28610 ms |  |
| G-d5cf26ee | tuning | 4 | 116 | 8 | — | {"probable": 2, "confirmed": 2} | 33706 ms |  |
| G-7f52fa54 | tuning | 6 | 137 | 7 | — | {"probable": 5, "confirmed": 1} | 41997 ms |  |
| G-849e6d39 | tuning | 3 | 143 | 5 | — | {"probable": 3} | 25398 ms |  |
| G-3ac029f4 | tuning | 6 | 87 | 7 | url | {"probable": 6} | 26433 ms |  |
| G-5f2468a7 | tuning | 5 | 144 | 9 | — | {"probable": 2, "confirmed": 3} | 6727 ms |  |
| G-dc790262 | tuning | 3 | 158 | 7 | host | {"confirmed": 2, "ambiguous": 1} | 27650 ms |  |
| G-71e0ee4d | tuning | 5 | 140 | 8 | — | {"probable": 2, "confirmed": 3} | 41724 ms |  |
| G-4c50e3d0 | tuning | 5 | 132 | 6 | url | {"probable": 5} | 23873 ms |  |
| G-09782531 | tuning | 4 | 149 | 8 | — | {"probable": 2, "confirmed": 2} | 26592 ms |  |
| G-9d8d0ecc | tuning | 6 | 147 | 6 | — | {"probable": 5, "ambiguous": 1} | 33399 ms |  |
| G-9497e56e | tuning | 4 | 159 | 4 | — | {"probable": 4} | 51264 ms |  |
| G-031af79c | tuning | 5 | 135 | 6 | — | {"probable": 3, "confirmed": 2} | 49520 ms |  |
| G-477d3bf9 | tuning | 6 | 207 | 10 | — | {"probable": 2, "confirmed": 4} | 28663 ms | stripped 1 platform name(s) |
| G-8d3ac455 | tuning | 2 | 178 | 9 | — | {"confirmed": 2} | 26497 ms |  |
| G-0e516f75 | tuning | 5 | 115 | 10 | url | {"probable": 2, "confirmed": 1, "ambiguous": 2} | 20534 ms |  |
| G-52b47f1a | tuning | 4 | 103 | 9 | — | {"probable": 1, "confirmed": 3} | 22743 ms |  |
| G-2ab20603 | tuning | 6 | 196 | 9 | — | {"probable": 2, "confirmed": 4} | 20805 ms |  |
| G-40b1e5f2 | tuning | 6 | 170 | 11 | url | {"probable": 2, "confirmed": 4} | 22695 ms | stripped 1 platform name(s) |
| G-854ee8db | tuning | 5 | 180 | 9 | — | {"probable": 3, "confirmed": 2} | 17632 ms | stripped 2 platform name(s) |
| G-e17d0b25 | heldout | 8 | 137 | 8 | — | {"probable": 6, "ambiguous": 2} | 18976 ms |  |
| G-3a1e7d51 | heldout | 8 | 138 | 11 | url | {"probable": 7, "ambiguous": 1} | 46659 ms |  |
| G-7f981e71 | heldout | 8 | 102 | 10 | — | {"confirmed": 1, "probable": 7} | 15994 ms |  |
| G-7089793b | heldout | 4 | 110 | 10 | — | {"probable": 3, "ambiguous": 1} | 17007 ms |  |
| G-4a494c46 | heldout | 8 | 120 | 9 | url | {"probable": 6, "ambiguous": 2} | 25509 ms |  |
| G-116af624 | heldout | 8 | 118 | 9 | — | {"probable": 7, "ambiguous": 1} | 27313 ms |  |
| G-bde7e098 | heldout | 8 | 102 | 11 | url | {"probable": 5, "confirmed": 2, "ambiguous": 1} | 18015 ms |  |
| G-6a9172d1 | heldout | 8 | 90 | 11 | — | {"probable": 8} | 21006 ms | stripped 1 platform name(s) |
| G-b4c11e10 | heldout | 7 | 66 | 9 | url | {"probable": 6, "ambiguous": 1} | 17587 ms |  |
| G-29834d49 | heldout | 3 | 115 | 9 | — | {"probable": 1, "ambiguous": 2} | 22490 ms |  |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 28475 ms · p95 51264 ms · max 56172 ms over 35 calls. Warm repeats: tuning cold 44358 ms → warm 4345 ms (cached search calls {'searxng': 9, 'parallel': 6}); heldout cold 18976 ms → warm 4344 ms (cached search calls {'searxng': 8, 'parallel': 6})
- Totals: hits 4762 · fetched 281 · cards 123 · fetch failures shown 241 · dropped shown 80 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 996.8, "warm_repeat": 8.7, "liveness": 89.2, "token_efficiency": 36.2}
- Breakers open at the end: ['dfpi.ca.gov', 'golden1.com', 'help.golden1.com', 'ibanknet.com', 'ori-cms-104.golden1.com', 'safe.bcu.org', 'thefinancialbrand.com', 'tyfone.com', 'web.archive.org', 'www-104.golden1.com', 'www.bbb.org', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.globenewswire.com', 'www.golden1.com', 'www.ibanknet.com', 'www.insight.com', 'www.solosuit.com', 'www.yahoo.com', 'www.youtube.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": "429", "last_retry_after": null, "opens": 2, "streak_403": 0, "streak_empty": 0, "streak_timeout": 0, "seconds_since_failure": 460.944}. Coalescer: {"inflight": 0, "upstream_calls": 470, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×76; same excerpt already carded from another copy (syndication is not corroboration) ×4
- Fetch-failure reasons (shown subset): robots_disallowed (slot refunded) ×51; breaker_open:www.goldenN.com (slot refunded) ×22; breaker_open:safe.bcu.org (slot refunded) ×21; breaker_open:goldenN.com (slot refunded) ×13; no extractable text (a scanned PDF, an empty page, or a binary) ×11; breaker_open:ibanknet.com (slot refunded) ×11; http N from safe.bcu.org (served by cloudflare) (WAF or access denied) ×7; http N from www.bcu.org ×7

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 123.

Golden NEGATIVE rows with a considered defect (hard_clip, not_sentence_complete, machine_text, internal_jargon): 131; the anti-pattern list + `contract.item_problems` excerpt rules would have refused **131** (100.0%).

| Defect class | Golden rows | Refused | Share | By rule |
|---|---|---|---|---|
| hard_clip | 35 | 35 | 100.0% | excerpt_clause_truncated ×35; excerpt_not_sentence_complete ×34 |
| not_sentence_complete | 118 | 118 | 100.0% | excerpt_not_sentence_complete ×118; excerpt_clause_truncated ×34 |
| machine_text | 5 | 5 | 100.0% | boilerplate:"averageUserRating"\s*: ×5 |
| internal_jargon | 7 | 7 | 100.0% | boilerplate:\b[Pp][1-4][Cc]\d(\.\d+){0,2}\b ×7 |

## 7. Card size

| Projection | Cards | Mean tokens | p95 | Min | Max |
|---|---|---|---|---|---|
| item + minimal provenance | 123 | 159.2 | 224 | 116 | 269 |
| item + standard provenance | 123 | 202.1 | 269 | 157 | 308 |
| item + full provenance | 123 | 314.6 | 384 | 257 | 424 |
| item only | | 114.7 | 180 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 25 | 7 | 8218 | 1134 | 86.2% | 11 |
| heldout | 10 | 4 | 3572 | 771 | 78.4% | 1 |
| **all** | 35 | 11 | 11790 | 1905 | 83.8% | 12 |

Secondary (every produced card against its own source page): 98.5% reduction, 180 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 34071.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: 12.0
- source_recall_host: 8.0
- url_liveness: 2.1
- token_reduction: 7.8
- excerpt_fidelity: 0.0
- max_gap_points: 12.0
- within_bar: False

## 10. Parallel rate-limit ramp

- not run

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

## 12. Golden-set version deltas

- v1 is the first version; no previous run to diff against.

