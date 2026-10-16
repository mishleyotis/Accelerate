# Evidence engine — golden-set evaluation report

Run `v1-20261010T201357Z` · 2026-10-10T20:13:57+00:00 → 2026-10-10T20:29:00+00:00 (901.5 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261010T201357Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (154/154 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 154 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 2 multi-URL clusters (218 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 165.6 · p95 220 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 100.0% (156/156; 0 unchecked for time) | 100% (hard) | MEETS | LIVE |
| Source recall, same url_key | 37.1% (13/35) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 42.9% (15/35) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 48.6% (13 carded + 4 surfaced-unreadable / 35) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 82.6% (2276 vs 13093 tokens over 13 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 96.4% (35996 vs 1004181 tokens, 220 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | 32.0 points | ≤ 5 points | ABOVE | both |
| Parallel rate-limit ceiling | not run → recommend `EE_PARALLEL_RPS=?` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 25 rows = 25 distinct URLs drawn with seed 20261010 from 27 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 10 rows, 10 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 1500.0 s.
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
| tuning | baxter | 15 | 3 (20.0%) | 5 (33.3%) | 2 | 0 | 0 |
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 1 | 0 | 0 |
| heldout | logix | 10 | 6 (60.0%) | 6 (60.0%) | 1 | 0 | 0 |
| **tuning** | all | 25 | 7 (28.0%) | 9 (36.0%) | 3 | | |
| **heldout** | all | 10 | 6 (60.0%) | 6 (60.0%) | 1 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: http N from www.savvymoney.com (served by nginx) (WAF or access de ×1; fetch failed: http N from www.scworld.com (served by cloudflare) (WAF or access  ×1; fetch failed: http N from thefinancialbrand.com (served by cloudflare) (WAF or a ×1; fetch failed: http N from www.insight.com (served by AkamaiGHost) (WAF or access ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 1/5; T3: 9/21; T4: 0/2; T5: 3/6.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-28f0525b | tuning | 6 | 24 | 8 | — | {"probable": 3, "confirmed": 1, "ambiguous": 2} | 36244 ms |  |
| G-72e90e5c | tuning | 8 | 21 | 10 | url | {"probable": 5, "confirmed": 3} | 17767 ms |  |
| G-b3b2565b | tuning | 8 | 18 | 9 | — | {"probable": 6, "ambiguous": 2} | 18153 ms |  |
| G-f61d5bd5 | tuning | 4 | 22 | 5 | url | {"confirmed": 1, "probable": 1, "ambiguous": 2} | 39844 ms |  |
| G-31d70f32 | tuning | 8 | 27 | 8 | url | {"probable": 6, "ambiguous": 2} | 22191 ms |  |
| G-ed0ae381 | tuning | 3 | 23 | 4 | — | {"probable": 3} | 50061 ms |  |
| G-d5cf26ee | tuning | 8 | 16 | 11 | — | {"probable": 3, "confirmed": 1, "ambiguous": 4} | 14970 ms |  |
| G-7f52fa54 | tuning | 6 | 26 | 6 | — | {"probable": 4, "ambiguous": 2} | 33683 ms |  |
| G-849e6d39 | tuning | 5 | 24 | 6 | — | {"probable": 4, "ambiguous": 1} | 26670 ms |  |
| G-3ac029f4 | tuning | 6 | 26 | 6 | url | {"probable": 5, "ambiguous": 1} | 41046 ms |  |
| G-5f2468a7 | tuning | 7 | 21 | 10 | — | {"probable": 5, "confirmed": 2} | 1758 ms |  |
| G-dc790262 | tuning | 5 | 31 | 6 | host | {"probable": 3, "confirmed": 1, "ambiguous": 1} | 16544 ms |  |
| G-71e0ee4d | tuning | 7 | 25 | 9 | — | {"probable": 1, "ambiguous": 6} | 15133 ms |  |
| G-4c50e3d0 | tuning | 6 | 30 | 6 | url | {"probable": 5, "ambiguous": 1} | 34472 ms |  |
| G-09782531 | tuning | 7 | 28 | 10 | — | {"probable": 2, "ambiguous": 5} | 14458 ms |  |
| G-9d8d0ecc | tuning | 2 | 23 | 3 | — | {"probable": 2} | 19392 ms |  |
| G-9497e56e | tuning | 4 | 25 | 5 | — | {"probable": 4} | 23167 ms |  |
| G-031af79c | tuning | 2 | 20 | 3 | — | {"probable": 2} | 37970 ms |  |
| G-477d3bf9 | tuning | 4 | 23 | 9 | — | {"probable": 2, "ambiguous": 2} | 14409 ms | stripped 1 platform name(s) |
| G-8d3ac455 | tuning | 7 | 21 | 9 | — | {"probable": 1, "ambiguous": 6} | 17339 ms |  |
| G-0e516f75 | tuning | 8 | 23 | 10 | url | {"probable": 4, "ambiguous": 4} | 10952 ms |  |
| G-52b47f1a | tuning | 6 | 28 | 9 | host | {"probable": 2, "confirmed": 2, "ambiguous": 2} | 17241 ms |  |
| G-2ab20603 | tuning | 8 | 22 | 10 | — | {"probable": 3, "ambiguous": 5} | 22015 ms |  |
| G-40b1e5f2 | tuning | 6 | 24 | 9 | url | {"probable": 4, "confirmed": 1, "ambiguous": 1} | 14934 ms | stripped 1 platform name(s) |
| G-854ee8db | tuning | 8 | 27 | 10 | — | {"probable": 2, "confirmed": 1, "ambiguous": 5} | 14158 ms | stripped 2 platform name(s) |
| G-e17d0b25 | heldout | 8 | 23 | 9 | url | {"probable": 3, "ambiguous": 5} | 13562 ms |  |
| G-3a1e7d51 | heldout | 8 | 24 | 10 | url | {"probable": 8} | 9731 ms |  |
| G-7f981e71 | heldout | 8 | 21 | 10 | — | {"confirmed": 1, "probable": 6, "ambiguous": 1} | 15898 ms |  |
| G-7089793b | heldout | 8 | 29 | 12 | url | {"probable": 2, "ambiguous": 6} | 9593 ms |  |
| G-4a494c46 | heldout | 7 | 25 | 11 | url | {"probable": 4, "ambiguous": 3} | 15480 ms |  |
| G-116af624 | heldout | 6 | 22 | 8 | — | {"probable": 5, "ambiguous": 1} | 16180 ms |  |
| G-bde7e098 | heldout | 8 | 20 | 10 | url | {"probable": 4, "confirmed": 2, "ambiguous": 2} | 13720 ms |  |
| G-6a9172d1 | heldout | 8 | 21 | 10 | url | {"probable": 7, "ambiguous": 1} | 15364 ms | stripped 1 platform name(s) |
| G-b4c11e10 | heldout | 8 | 26 | 9 | — | {"probable": 7, "ambiguous": 1} | 15087 ms |  |
| G-29834d49 | heldout | 2 | 26 | 5 | — | {"probable": 2} | 17932 ms |  |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 20489 ms · p95 41046 ms · max 50061 ms over 35 calls. Warm repeats: tuning cold 36244 ms → warm 11523 ms (cached search calls {'parallel': 5}); heldout cold 13562 ms → warm 2506 ms (cached search calls {'parallel': 5})
- Totals: hits 835 · fetched 285 · cards 154 · fetch failures shown 222 · dropped shown 50 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 717.2, "warm_repeat": 14.0, "liveness": 100.8, "token_efficiency": 68.2}
- Breakers open at the end: ['dfpi.ca.gov', 'dockets.justia.com', 'golden1.com', 'help.golden1.com', 'ori-cms-104.golden1.com', 'thefinancialbrand.com', 'tyfone.com', 'web.archive.org', 'www.bbb.org', 'www.businesswire.com', 'www.consumerfinance.gov', 'www.creditunionsonline.com', 'www.globenewswire.com', 'www.golden1.com', 'www.insight.com', 'www.instagram.com', 'www.sacbee.com', 'www.yahoo.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "streak_timeout": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 170, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×50
- Fetch-failure reasons (shown subset): robots_disallowed (slot refunded) ×68; breaker_open:www.goldenN.com (slot refunded) ×20; http N from www.bcu.org ×19; never_fetch host (not evidence-grade; slot refunded) ×8; breaker_open:goldenN.com (slot refunded) ×8; breaker_open:www.bbb.org (slot refunded) ×8; breaker_open:www.creditunionsonline.com (slot refunded) ×7; http N from www.bbb.org (served by cloudflare) (WAF or access denied) ×6

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 154.

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
| item + minimal provenance | 154 | 165.6 | 220 | 119 | 238 |
| item + standard provenance | 154 | 207.5 | 263 | 163 | 278 |
| item + full provenance | 154 | 313.6 | 370 | 262 | 385 |
| item only | | 121.1 | 176 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 25 | 7 | 8218 | 1233 | 85.0% | 11 |
| heldout | 10 | 6 | 4875 | 1043 | 78.6% | 1 |
| **all** | 35 | 13 | 13093 | 2276 | 82.6% | 12 |

Secondary (every produced card against its own source page): 96.4% reduction, 220 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 34071.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: 32.0
- source_recall_host: 24.0
- url_liveness: 0.0
- token_reduction: 6.4
- excerpt_fidelity: 0.0
- max_gap_points: 32.0
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

