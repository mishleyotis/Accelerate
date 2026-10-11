# Evidence engine — golden-set evaluation report

Run `v1-20261011T050505Z` · 2026-10-11T05:05:05+00:00 → 2026-10-11T05:36:21+00:00 (1876.1 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261011T050505Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (187/187 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 187 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 1 multi-URL clusters (250 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 162.5 · p95 233 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 98.9% (185/187; 0 unchecked for time) | 100% (hard) | BELOW | LIVE |
| Source recall, same url_key | 45.7% (16/35) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 54.3% (19/35) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 60.0% (16 carded + 5 surfaced-unreadable / 35) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 83.9% (2701 vs 16813 tokens over 16 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 98.9% (40778 vs 3806230 tokens, 252 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | 34.0 points | ≤ 5 points | ABOVE | both |
| Search-level recall, measured in the hit list (tuning) | 64.0% (16/25); surfaced but not carded 7; median rank 15; by source {'parallel': 14, 'searxng': 11} | (diagnostic) | — | LIVE |
| Search-level recall, measured in the hit list (heldout) | 80.0% (8/10); surfaced but not carded 1; median rank 26; by source {'searxng': 5, 'parallel': 7} | (diagnostic) | — | LIVE |
| research_brief phases (mean / p95 ms) | search 16700 / 20035 · fetch 26949 / 30032 · rank_and_cards 1989 / 8745 | (informational) | — | LIVE |
| research_brief answer size an agent reads (tokens, whole answer) | mean 3575.0 · p95 4111 · max 4699 (cards 63.4% of it) | (informational) | — | offline |
| Parallel rate-limit ceiling | not run → recommend `EE_PARALLEL_RPS=?` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 25 rows = 25 distinct URLs drawn with seed 20261010 from 27 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 10 rows, 10 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 3600.0 s.
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
| tuning | baxter | 15 | 5 (33.3%) | 8 (53.3%) | 3 | 0 | 0 |
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 1 | 0 | 0 |
| heldout | logix | 10 | 7 (70.0%) | 7 (70.0%) | 1 | 0 | 0 |
| **tuning** | all | 25 | 9 (36.0%) | 12 (48.0%) | 4 | | |
| **heldout** | all | 10 | 7 (70.0%) | 7 (70.0%) | 1 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: robots_disallowed (slot refunded) ×1; fetch failed: http N from www.savvymoney.com (served by nginx) (WAF or access de ×1; fetch failed: http N from www.scworld.com (served by cloudflare) (WAF or access  ×1; fetch failed: http N from thefinancialbrand.com (served by cloudflare) (WAF or a ×1; fetch failed: http N from www.insight.com (served by AkamaiGHost) (WAF or access ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 2/5; T3: 10/21; T4: 0/2; T5: 4/6.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-28f0525b | tuning | 6 | 75 | 15 | host | {"probable": 3, "confirmed": 3} | 49316 ms |  |
| G-72e90e5c | tuning | 8 | 60 | 12 | url | {"probable": 4, "confirmed": 4} | 34807 ms |  |
| G-b3b2565b | tuning | 6 | 90 | 14 | url | {"probable": 6} | 46690 ms |  |
| G-f61d5bd5 | tuning | 7 | 70 | 7 | url | {"confirmed": 1, "probable": 6} | 48231 ms |  |
| G-31d70f32 | tuning | 6 | 74 | 10 | url | {"probable": 5, "ambiguous": 1} | 45432 ms |  |
| G-ed0ae381 | tuning | 8 | 208 | 8 | — | {"probable": 5, "ambiguous": 3} | 47235 ms |  |
| G-d5cf26ee | tuning | 7 | 147 | 14 | — | {"probable": 4, "confirmed": 2, "ambiguous": 1} | 53159 ms |  |
| G-7f52fa54 | tuning | 7 | 172 | 8 | — | {"probable": 3, "confirmed": 2, "ambiguous": 2} | 51832 ms |  |
| G-849e6d39 | tuning | 8 | 150 | 8 | — | {"probable": 4, "confirmed": 3, "ambiguous": 1} | 47011 ms |  |
| G-3ac029f4 | tuning | 8 | 127 | 11 | url | {"probable": 7, "confirmed": 1} | 46640 ms |  |
| G-5f2468a7 | tuning | 8 | 60 | 12 | — | {"probable": 5, "confirmed": 3} | 20709 ms |  |
| G-dc790262 | tuning | 8 | 168 | 15 | host | {"probable": 7, "confirmed": 1} | 39096 ms |  |
| G-71e0ee4d | tuning | 4 | 147 | 9 | — | {"probable": 2, "confirmed": 2} | 41037 ms |  |
| G-4c50e3d0 | tuning | 7 | 147 | 7 | url | {"probable": 6, "ambiguous": 1} | 45845 ms |  |
| G-09782531 | tuning | 8 | 151 | 13 | — | {"probable": 6, "confirmed": 2} | 52120 ms |  |
| G-9d8d0ecc | tuning | 6 | 156 | 7 | — | {"probable": 4, "ambiguous": 2} | 47762 ms |  |
| G-9497e56e | tuning | 6 | 175 | 8 | — | {"probable": 4, "confirmed": 1, "ambiguous": 1} | 40282 ms |  |
| G-031af79c | tuning | 4 | 180 | 5 | — | {"probable": 2, "confirmed": 1, "ambiguous": 1} | 38131 ms |  |
| G-477d3bf9 | tuning | 8 | 232 | 16 | — | {"probable": 6, "confirmed": 2} | 49405 ms | stripped 1 platform name(s) |
| G-8d3ac455 | tuning | 5 | 181 | 12 | url | {"probable": 2, "confirmed": 1, "ambiguous": 2} | 54962 ms |  |
| G-0e516f75 | tuning | 8 | 129 | 15 | url | {"probable": 6, "ambiguous": 2} | 50408 ms |  |
| G-52b47f1a | tuning | 8 | 158 | 14 | host | {"probable": 5, "confirmed": 1, "ambiguous": 2} | 50278 ms |  |
| G-2ab20603 | tuning | 8 | 231 | 17 | — | {"probable": 7, "confirmed": 1} | 40738 ms |  |
| G-40b1e5f2 | tuning | 8 | 180 | 17 | url | {"probable": 6, "confirmed": 2} | 55239 ms | stripped 1 platform name(s) |
| G-854ee8db | tuning | 8 | 193 | 16 | — | {"probable": 6, "confirmed": 2} | 49370 ms | stripped 2 platform name(s) |
| G-e17d0b25 | heldout | 8 | 158 | 18 | url | {"probable": 8} | 27208 ms |  |
| G-3a1e7d51 | heldout | 5 | 146 | 10 | url | {"probable": 5} | 54963 ms |  |
| G-7f981e71 | heldout | 8 | 35 | 13 | — | {"confirmed": 1, "probable": 7} | 49381 ms |  |
| G-7089793b | heldout | 8 | 47 | 14 | url | {"probable": 6, "ambiguous": 2} | 50115 ms |  |
| G-4a494c46 | heldout | 8 | 55 | 13 | url | {"probable": 8} | 47080 ms |  |
| G-116af624 | heldout | 8 | 65 | 14 | — | {"probable": 8} | 47231 ms |  |
| G-bde7e098 | heldout | 8 | 50 | 13 | url | {"probable": 6, "confirmed": 2} | 46162 ms |  |
| G-6a9172d1 | heldout | 8 | 65 | 14 | url | {"probable": 8} | 46952 ms | stripped 1 platform name(s) |
| G-b4c11e10 | heldout | 8 | 54 | 15 | url | {"probable": 8} | 33342 ms |  |
| G-29834d49 | heldout | 8 | 48 | 11 | — | {"probable": 8} | 49246 ms |  |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 45640 ms · p95 54963 ms · max 55239 ms over 35 calls. Warm repeats: tuning cold 49316 ms → warm 30295 ms (cached search calls {'searxng': 17, 'parallel': 8}); heldout cold 27208 ms → warm 4612 ms (cached search calls {'searxng': 16, 'parallel': 8})
- Totals: hits 4384 · fetched 425 · cards 187 · fetch failures shown 285 · dropped shown 76 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 1597.6, "warm_repeat": 34.9, "liveness": 131.9, "token_efficiency": 107.6}
- Breakers open at the end: ['amroar.com', 'finovate.com', 'fintechmagazine.com', 'logix.com', 'ori-cms-104.golden1.com', 'safe.bcu.org', 'thebusinessjournal.com', 'thefinancialbrand.com', 'tyfone.com', 'web.archive.org', 'www.bbb.org', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.cuinsight.com', 'www.cutimes.com', 'www.globenewswire.com', 'www.golden1.com', 'www.ibanknet.com', 'www.insight.com', 'www.yahoo.com', 'www.youtube.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "streak_timeout": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 790, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×57; same excerpt already carded from another copy (syndication is not corroboration) ×19
- Fetch-failure reasons (shown subset): robots_disallowed (slot refunded) ×72; http N from www.bcu.org ×21; breaker_open:safe.bcu.org (slot refunded) ×19; fetch_phase_budget: still fetching after Ns ×17; http N from safe.bcu.org (served by cloudflare) (WAF or access denied) ×7; http N from www.cuinsight.com (served by cloudflare) (WAF or access de ×7; no extractable text (a scanned PDF, an empty page, or a binary) ×6; http N from ori-cms-N.goldenN.com (WAF or access denied) ×6

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 187.

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
| item + minimal provenance | 187 | 162.5 | 233 | 116 | 269 |
| item + standard provenance | 187 | 204.8 | 273 | 156 | 311 |
| item + full provenance | 187 | 312.8 | 393 | 253 | 430 |
| item only | | 118.0 | 190 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 25 | 9 | 10798 | 1439 | 86.7% | 11 |
| heldout | 10 | 7 | 6015 | 1262 | 79.0% | 1 |
| **all** | 35 | 16 | 16813 | 2701 | 83.9% | 12 |

Secondary (every produced card against its own source page): 98.9% reduction, 252 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 34071.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: 34.0
- source_recall_host: 22.0
- url_liveness: 1.5
- token_reduction: 7.7
- excerpt_fidelity: 0.0
- max_gap_points: 34.0
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

