# Evidence engine — golden-set evaluation report

Run `v2-20261011T044125Z` · 2026-10-11T04:41:25+00:00 → 2026-10-11T05:04:15+00:00 (1369.2 s) · golden **v2** (built 2026-10-11) · mode **LIVE** · results `eval/results/v2-20261011T044125Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (155/155 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 155 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 1 multi-URL clusters (179 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 163.0 · p95 229 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 99.4% (154/155; 0 unchecked for time) | 100% (hard) | BELOW | LIVE |
| Source recall, same url_key | 22.2% (6/27) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 22.2% (6/27) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 29.6% (6 carded + 2 surfaced-unreadable / 27) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 86.3% (959 vs 7010 tokens over 6 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 98.3% (29456 vs 1736852 tokens, 180 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | 2.5 points | ≤ 5 points | MEETS | both |
| Search-level recall, measured in the hit list (tuning) | 38.9% (7/18); surfaced but not carded 3; median rank 12; by source {'parallel': 6, 'searxng': 2} | (diagnostic) | — | LIVE |
| Search-level recall, measured in the hit list (heldout) | 33.3% (3/9); surfaced but not carded 1; median rank 36; by source {'parallel': 3} | (diagnostic) | — | LIVE |
| research_brief phases (mean / p95 ms) | search 16774 / 20032 · fetch 22653 / 30032 · rank_and_cards 1475 / 4256 | (informational) | — | LIVE |
| research_brief answer size an agent reads (tokens, whole answer) | mean 3494.9 · p95 4267 · max 4283 (cards 59.8% of it) | (informational) | — | offline |
| Parallel rate-limit ceiling | not run → recommend `EE_PARALLEL_RPS=?` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).

## 3. Sample

- Tuning: 18 rows = 18 distinct URLs drawn with seed 20261010 from 18 distinct positive URLs (one row per URL, the longest excerpt). Held-out: 9 rows, 9 distinct URLs — all of them.
- research_brief arguments: `max_cards=8, token_budget=20000, provenance='full'`; time budget 3600.0 s.
- The golden set has **no question field**. Each question is derived from the row's excerpt: its content words minus the entity's name tokens, stop words and any platform name the vendor guard (`query.guard`) would refuse — an agent does not know the vendor before it finds the evidence — as `What does <entity> report about <terms>?`. Platform names were stripped from 0 question(s).

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
| tuning | golden1 | 11 | 3 (27.3%) | 3 (27.3%) | 2 | 0 | 0 |
| tuning | baxter | 7 | 1 (14.3%) | 1 (14.3%) | 0 | 0 | 0 |
| heldout | logix | 9 | 2 (22.2%) | 2 (22.2%) | 0 | 0 | 0 |
| **tuning** | all | 18 | 4 (22.2%) | 4 (22.2%) | 2 | | |
| **heldout** | all | 9 | 2 (22.2%) | 2 (22.2%) | 0 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: http N from thefinancialbrand.com (served by cloudflare) (WAF or a ×1; fetch failed: http N from tyfone.com (served by cloudflare) (WAF or access denie ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 0/3; T3: 4/15; T4: 0/2; T5: 2/6.

### Per call

| Golden id | Split | Cards | Hits | Fetched | Re-found | Entity match of cards | Elapsed | Note |
|---|---|---|---|---|---|---|---|---|
| G-f61d5bd5 | tuning | 7 | 143 | 9 | url | {"probable": 5, "confirmed": 1, "ambiguous": 1} | 46389 ms |  |
| G-31d70f32 | tuning | 4 | 164 | 7 | — | {"probable": 3, "ambiguous": 1} | 45296 ms |  |
| G-ed0ae381 | tuning | 4 | 109 | 10 | — | {"probable": 3, "ambiguous": 1} | 46009 ms |  |
| G-d5cf26ee | tuning | 8 | 231 | 13 | — | {"probable": 3, "confirmed": 2, "ambiguous": 3} | 36042 ms |  |
| G-7f52fa54 | tuning | 7 | 183 | 9 | — | {"confirmed": 3, "probable": 3, "ambiguous": 1} | 48938 ms |  |
| G-849e6d39 | tuning | 4 | 156 | 6 | — | {"probable": 4} | 48246 ms |  |
| G-3ac029f4 | tuning | 7 | 118 | 11 | url | {"probable": 5, "ambiguous": 2} | 48651 ms |  |
| G-dc790262 | tuning | 8 | 235 | 13 | — | {"confirmed": 1, "probable": 4, "ambiguous": 3} | 32810 ms |  |
| G-71e0ee4d | tuning | 7 | 187 | 13 | — | {"probable": 2, "ambiguous": 5} | 42153 ms |  |
| G-4c50e3d0 | tuning | 6 | 154 | 7 | url | {"confirmed": 1, "probable": 3, "ambiguous": 2} | 49239 ms |  |
| G-80d07a3a | tuning | 8 | 226 | 17 | — | {"probable": 7, "ambiguous": 1} | 31452 ms |  |
| G-9d8d0ecc | tuning | 8 | 175 | 13 | — | {"probable": 6, "confirmed": 1, "ambiguous": 1} | 47350 ms |  |
| G-9497e56e | tuning | 6 | 131 | 10 | — | {"probable": 2, "confirmed": 2, "ambiguous": 2} | 74524 ms |  |
| G-67f56e1f | tuning | 7 | 154 | 8 | — | {"probable": 5, "ambiguous": 2} | 44829 ms |  |
| G-031af79c | tuning | 6 | 131 | 9 | — | {"confirmed": 2, "probable": 3, "ambiguous": 1} | 48742 ms |  |
| G-1baffe74 | tuning | 8 | 88 | 16 | — | {"probable": 2, "ambiguous": 6} | 24846 ms |  |
| G-8d3ac455 | tuning | 7 | 187 | 13 | — | {"probable": 2, "ambiguous": 5} | 16786 ms |  |
| G-40b1e5f2 | tuning | 5 | 79 | 17 | url | {"probable": 3, "ambiguous": 2} | 28919 ms |  |
| G-e17d0b25 | heldout | 8 | 60 | 13 | — | {"probable": 8} | 40435 ms |  |
| G-7f981e71 | heldout | 5 | 53 | 12 | — | {"probable": 2, "ambiguous": 3} | 41471 ms |  |
| G-7089793b | heldout | 8 | 56 | 13 | — | {"confirmed": 1, "probable": 6, "ambiguous": 1} | 31929 ms |  |
| G-4a494c46 | heldout | 8 | 59 | 13 | url | {"probable": 7, "ambiguous": 1} | 34532 ms |  |
| G-116af624 | heldout | 8 | 70 | 12 | — | {"probable": 7, "ambiguous": 1} | 33050 ms |  |
| G-bde7e098 | heldout | 8 | 69 | 14 | url | {"confirmed": 1, "probable": 5, "ambiguous": 2} | 37121 ms |  |
| G-6a9172d1 | heldout | 5 | 63 | 14 | — | {"probable": 3, "ambiguous": 2} | 49403 ms |  |
| G-b4c11e10 | heldout | 7 | 39 | 15 | — | {"probable": 7} | 38178 ms |  |
| G-29834d49 | heldout | 6 | 58 | 16 | — | {"probable": 4, "ambiguous": 2} | 37106 ms |  |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 40905 ms · p95 49403 ms · max 74524 ms over 27 calls. Warm repeats: tuning cold 46389 ms → warm 30227 ms (cached search calls {'searxng': 15, 'parallel': 7}); heldout cold 40435 ms → warm 18842 ms (cached search calls {'searxng': 16, 'parallel': 8})
- Totals: hits 3378 · fetched 323 · cards 155 · fetch failures shown 236 · dropped shown 117 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 1104.6, "warm_repeat": 49.1, "liveness": 123.7, "token_efficiency": 90.3}
- Breakers open at the end: ['fintechmagazine.com', 'ori-cms-104.golden1.com', 'patents.google.com', 'safe.bcu.org', 'smatechnologies.com', 'technologymagazine.com', 'thefinancialbrand.com', 'tyfone.com', 'web.archive.org', 'www.appsruntheworld.com', 'www.bbb.org', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.cuinsight.com', 'www.golden1.com', 'www.google.com.pg', 'www.indeed.com', 'www.insight.com', 'www.loanlogics.com', 'www.openbankingtracker.com', 'www.solosuit.com', 'www.yahoo.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "streak_timeout": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 608, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×101; same excerpt already carded from another copy (syndication is not corroboration) ×16
- Fetch-failure reasons (shown subset): robots_disallowed (slot refunded) ×54; no extractable text (a scanned PDF, an empty page, or a binary) ×16; http N from www.bcu.org ×11; breaker_open:www.bbb.org (slot refunded) ×9; http N from safe.bcu.org (served by cloudflare) (WAF or access denied) ×7; http N from ori-cms-N.goldenN.com (WAF or access denied) ×6; http N from thefinancialbrand.com (served by cloudflare) (WAF or acces ×6; breaker_open:safe.bcu.org (slot refunded) ×6

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 155.

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
| item + minimal provenance | 155 | 163.0 | 229 | 117 | 253 |
| item + standard provenance | 155 | 204.5 | 274 | 159 | 297 |
| item + full provenance | 155 | 312.0 | 377 | 257 | 421 |
| item only | | 118.5 | 185 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 18 | 4 | 4698 | 604 | 87.1% | 9 |
| heldout | 9 | 2 | 2312 | 355 | 84.7% | 1 |
| **all** | 27 | 6 | 7010 | 959 | 86.3% | 10 |

Secondary (every produced card against its own source page): 98.3% reduction, 180 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 27786.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: 0.0
- source_recall_host: 0.0
- url_liveness: 1.8
- token_reduction: 2.5
- excerpt_fidelity: 0.0
- max_gap_points: 2.5
- within_bar: True

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
- Held-out positives: 9 rows from one client — the held-out split is small, so its recall moves in steps of ~8 points and the generalisation gap is coarse.
- The Parallel ramp is a polite, short measurement (≤ 90 calls, ≤ 60 s) from one network location; a free anonymous tier's ceiling may differ by hour and by origin.

## 12. Golden-set version deltas

- v2 is the first version; no previous run to diff against.

