# Evidence engine — golden-set evaluation report

Run `v1-20261011T041104Z` · 2026-10-11T04:11:04+00:00 → 2026-10-11T04:38:55+00:00 (1670.3 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261011T041104Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (117/117 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 117 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 0 multi-URL clusters (145 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 158.7 · p95 220 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 97.4% (114/117; 0 unchecked for time) | 100% (hard) | BELOW | LIVE |
| Source recall, same url_key | 34.8% (8/23) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 43.5% (10/23) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 43.5% (8 carded + 2 surfaced-unreadable / 23) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 86.5% (1320 vs 9766 tokens over 8 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 99.2% (22706 vs 2680242 tokens, 145 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | None points | ≤ 5 points | not measured | both |
| Search-level recall, measured in the hit list (tuning) | 65.2% (15/23); surfaced but not carded 7; median rank 11; by source {'searxng': 13, 'parallel': 13} | (diagnostic) | — | LIVE |
| research_brief phases (mean / p95 ms) | search 20139 / 24511 · fetch 37891 / 45026 · rank_and_cards 1825 / 8242 | (informational) | — | LIVE |
| research_brief answer size an agent reads (tokens, whole answer) | mean 3296.8 · p95 3814 · max 4127 (cards 59.3% of it) | (informational) | — | offline |
| Parallel rate-limit ceiling | not run → recommend `EE_PARALLEL_RPS=?` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 25 rows = 25 distinct URLs drawn with seed 20261010 from 27 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 10 rows, 10 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 2400.0 s.
- The golden set has **no question field**. Each question is derived from the row's excerpt: its content words minus the entity's name tokens, stop words and any platform name the vendor guard (`query.guard`) would refuse — an agent does not know the vendor before it finds the evidence — as `What does <entity> report about <terms>?`. Platform names were stripped from 1 question(s).

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
| tuning | baxter | 13 | 4 (30.8%) | 6 (46.2%) | 2 | 0 | 0 |
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 0 | 0 | 0 |
| **tuning** | all | 23 | 8 (34.8%) | 10 (43.5%) | 2 | | |
| **heldout** | all | 0 | 0 (n/a) | 0 (n/a) | 0 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: robots_disallowed (slot refunded) ×1; fetch failed: http N from www.scworld.com (served by cloudflare) (WAF or access  ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 2/4; T3: 5/14; T4: 0/2; T5: 1/2.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-28f0525b | tuning | 8 | 222 | 16 | host | {"probable": 3, "confirmed": 3, "ambiguous": 2} | 64712 ms |  |
| G-72e90e5c | tuning | 7 | 166 | 12 | url | {"probable": 3, "confirmed": 4} | 38580 ms |  |
| G-b3b2565b | tuning | 6 | 239 | 13 | — | {"probable": 3, "confirmed": 1, "ambiguous": 2} | 70020 ms |  |
| G-f61d5bd5 | tuning | 3 | 132 | 3 | url | {"confirmed": 1, "probable": 2} | 64695 ms |  |
| G-31d70f32 | tuning | 7 | 87 | 11 | url | {"probable": 6, "ambiguous": 1} | 65918 ms |  |
| G-ed0ae381 | tuning | 6 | 207 | 6 | — | {"probable": 4, "ambiguous": 2} | 65992 ms |  |
| G-d5cf26ee | tuning | 6 | 175 | 13 | — | {"probable": 4, "confirmed": 2} | 72883 ms |  |
| G-7f52fa54 | tuning | 5 | 168 | 6 | — | {"probable": 2, "confirmed": 2, "ambiguous": 1} | 70335 ms |  |
| G-849e6d39 | tuning | 7 | 161 | 7 | — | {"probable": 5, "confirmed": 2} | 66393 ms |  |
| G-3ac029f4 | tuning | 8 | 114 | 10 | url | {"probable": 7, "confirmed": 1} | 54857 ms |  |
| G-5f2468a7 | tuning | 7 | 166 | 12 | — | {"probable": 4, "confirmed": 3} | 20913 ms |  |
| G-dc790262 | tuning | 8 | 197 | 14 | host | {"probable": 7, "confirmed": 1} | 54415 ms |  |
| G-71e0ee4d | tuning | 4 | 155 | 7 | — | {"probable": 2, "confirmed": 2} | 64671 ms |  |
| G-4c50e3d0 | tuning | 7 | 160 | 8 | url | {"probable": 6, "ambiguous": 1} | 65609 ms |  |
| G-09782531 | tuning | 8 | 168 | 13 | — | {"probable": 6, "confirmed": 2} | 57758 ms |  |
| G-9d8d0ecc | tuning | 6 | 151 | 7 | — | {"probable": 4, "ambiguous": 2} | 65426 ms |  |
| G-9497e56e | tuning | 3 | 204 | 3 | — | {"probable": 3} | 55255 ms |  |
| G-031af79c | tuning | 4 | 167 | 6 | — | {"probable": 1, "confirmed": 1, "ambiguous": 2} | 55519 ms |  |
| G-477d3bf9 | tuning | 8 | 247 | 15 | — | {"probable": 6, "confirmed": 2} | 70106 ms | stripped 1 platform name(s) |
| G-8d3ac455 | tuning | 5 | 217 | 13 | url | {"probable": 2, "confirmed": 1, "ambiguous": 2} | 69203 ms |  |
| G-0e516f75 | tuning | 8 | 140 | 15 | url | {"probable": 5, "ambiguous": 3} | 50361 ms |  |
| G-52b47f1a | tuning | 6 | 135 | 11 | url | {"probable": 4, "confirmed": 1, "ambiguous": 1} | 50157 ms |  |
| G-2ab20603 | tuning | 8 | 235 | 16 | — | {"probable": 7, "confirmed": 1} | 62939 ms |  |
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

- research_brief elapsed: mean 59857 ms · p95 70335 ms · max 72883 ms over 23 calls. Warm repeats: tuning cold 64712 ms → warm 21334 ms (cached search calls {'searxng': 17, 'parallel': 8})
- Totals: hits 4013 · fetched 237 · cards 117 · fetch failures shown 214 · dropped shown 55 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 1376.8, "warm_repeat": 21.3, "liveness": 106.8, "token_efficiency": 162.8}
- Breakers open at the end: ['finovate.com', 'ibanknet.com', 'ori-cms-104.golden1.com', 'safe.bcu.org', 'thefinancialbrand.com', 'tyfone.com', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.roundpaper.com', 'www.savvymoney.com', 'www.yahoo.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "streak_timeout": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 500, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×44; same excerpt already carded from another copy (syndication is not corroboration) ×11
- Fetch-failure reasons (shown subset): could not connect to www.goldenN.com: Server disconnected without send ×28; breaker_open:safe.bcu.org (slot refunded) ×25; http N from www.bcu.org ×21; robots_disallowed (slot refunded) ×21; could not connect to goldenN.com: Server disconnected without sending  ×17; no extractable text (a scanned PDF, an empty page, or a binary) ×14; http N from safe.bcu.org (served by cloudflare) (WAF or access denied) ×7; http N from ori-cms-N.goldenN.com (WAF or access denied) ×7

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 117.

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
| item + minimal provenance | 117 | 158.7 | 220 | 117 | 261 |
| item + standard provenance | 117 | 200.9 | 258 | 160 | 303 |
| item + full provenance | 117 | 309.8 | 378 | 256 | 402 |
| item only | | 114.3 | 175 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 23 | 8 | 9766 | 1320 | 86.5% | 10 |
| heldout | 0 | 0 | 0 | 0 | n/a | 0 |
| **all** | 23 | 8 | 9766 | 1320 | 86.5% | 10 |

Secondary (every produced card against its own source page): 99.2% reduction, 145 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 13164.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: None
- source_recall_host: None
- url_liveness: None
- token_reduction: None
- excerpt_fidelity: None
- max_gap_points: None
- within_bar: None

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
- 2 tuning call(s) were skipped for time.

## 12. Golden-set version deltas

- v1 is the first version; no previous run to diff against.

