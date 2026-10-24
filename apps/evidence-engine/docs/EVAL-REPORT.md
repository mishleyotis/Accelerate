# Evidence engine — golden-set evaluation report

Two live runs against golden **v1** (built 2026-10-10, tuning = Golden 1 + Baxter, held-out = Logix),
both with Parallel Search MCP as the only discovery source (SearXNG not deployed), BM25-only ranking,
one `research_brief` per sampled golden row. Full per-run detail: §A (baseline) below and
`EVAL-REPORT-iter2.md` (iteration 2); results JSON under `eval/results/`.

## 0. Baseline → iteration 2 (the two tuning iterations the brief allows for recall)

| Metric | Bar | Baseline `v1-20261010T195014Z` (commit e27ee5f) | Iteration 2 `v1-20261010T201357Z` (commit 7ba577c) | Verdict |
|---|---|---|---|---|
| Excerpt fidelity | 100 % hard | 100 % (116/116) | 100 % (154/154) | MEETS |
| URL liveness (live or archived) | 100 % hard | 100 % (117/117) | 100 % (156/156) | MEETS |
| Boilerplate leakage | 0 | 0 | 0 | MEETS |
| Syndication inflation | 0 | 0 | 0 | MEETS |
| Entity precision (cards wrongly `confirmed`/`probable`) | ≥ 98 % | none found; `ambiguous` flagged on 37 % of cards | `ambiguous` now ranked after probable | reported, see §A.4 note |
| Source recall, same URL — all / tuning / held-out | ≥ 80 % | 34.3 % / 28.0 % / 50.0 % | **37.1 % / 28.0 % / 60.0 %** | BELOW — escalated (§0.2) |
| Search-level recall (URL surfaced, card or refused) | diagnostic | 48.6 % | 48.6 % | — |
| Token efficiency on re-found URLs (page → card) | ≥ 60 % | 78.6 % | **82.6 %** | MEETS |
| Card size, item + minimal provenance (heuristic tokens) | ~120 | mean 165.9 / item alone 121.4 | mean 165.6 / item alone 121.1 | item meets; provenance adds ~45 |
| Generalisation gap (held-out − tuning, recall) | ≤ 5 pts | 22 pts, held-out better | 32 pts, held-out better | ABOVE (direction is the safe one) |
| research_brief elapsed, mean / p95 / max | — | 34.7 s / 127 s / 171 s | **20.5 s / 41 s / 50 s** | — |
| Parallel ceiling | measured | no 429 up to 2/s → `EE_PARALLEL_RPS=1.4` adopted as the default | not re-run | — |

### 0.0 Iterations 3–5 and golden v2 (2026-10-11, after the owner raised the target to > 90 %)

Code at each run: iter 3 `514e15a`, iter 4 `bada7f7`, iter 5 and v2 `34e844f`. Backends: local SearXNG
(Google CSE + Bing answer; Brave, DuckDuckGo, Qwant block this egress) + Parallel. Per-run detail in
`EVAL-REPORT-iter3.md`, `EVAL-REPORT-iter4.md`, `EVAL-REPORT-iter5.md`, `EVAL-REPORT-v2.md`.

| Run | Questions | Rows (tuning / held-out) | Same-URL recall tuning / held-out | Golden URL in hit list | Brief answered by ≥ 1 independent entity-confirmed card | Brief mean (search / fetch) | Liveness |
|---|---|---|---|---|---|---|---|
| iter 2 (ref.) | excerpt-derived (v1) | 25 / 10 | 28.0 % / 60.0 % | — | — | 20.5 s | 100 % |
| iter 3 | v1 | 25 / 10 | 28.0 % / 40.0 % | 80 % (28/35, replayed from the search cache) | — | 28.5 s | 99.2 % |
| iter 4 | v1 | 23 / 0 (deadline) | 34.8 % / — | 65 % (live) | 100 % / — | 59.9 s (20 / 38) | 97.4 % |
| **iter 5** | v1 | 25 / 10 | **36.0 % / 70.0 %** | 64 % / 80 % | **100 % / 100 %** | 45.6 s (16.7 / 26.9) | 98.9 % |
| **v2** | toolkit diagnostic questions | 18 / 9 | **22.2 % / 22.2 %** (gap 2.5 pts) | 39 % / 33 % | **100 % / 100 %** | 40.9 s (16.8 / 22.7) | 99.4 % |

Hard bars across all four runs: excerpt fidelity 100 %, boilerplate 0, syndication inflation 0, token
reduction 84–87 % on re-found pages. Liveness fell below 100 % only at RE-CHECK: a host that served
the page at research time answered 403 (WAF) or refused the connection minutes later; the connector's
own fetch would refuse those too, so those cards would not register — the report counts them.

What moved recall: concise operator-free queries (iter 3), SearXNG as a backend (iter 3), the fetch
slice ordered by entity band and question-term overlap and widened to 20 (iter 4), refused connections
treated as dead hosts with the snapshot path (iter 5). Search-level recall on v1 reached 64–80 %; the
gap between "in the hit list" and "carded" is now (iter 5, per row): robots.txt (72 refusals), WAF 403
without a snapshot, a client site that refuses this egress, pages written in fragments that the
sentence-completeness rule refuses (57 drops), and the 30 s fetch budget (17 cancellations).

**What v2 shows.** Asked the subcap's own diagnostic question, every brief returned at least one
entity-confirmed card from an independent source (tuning and held-out), but the specific page a
previous citation used is re-found 22 % of the time: a diagnostic question has many valid evidence
pages, and same-URL recall then measures agreement with one earlier citation, not whether the question
was answered. On v1 (questions derived from the golden excerpt) the same engine re-finds 36 % / 70 %.

**Status against the owner's > 90 % condition (2026-10-11).** On same-URL recall — the metric
`infra/evidence-engine/approval_check.py` is written against — the engine is below the bar on every
split of every run, after six iterations; no free-source path to 90 % on that metric is visible (the
remaining losses are fetchability and the one-URL framing). On question coverage it is at 100 % on both
splits of both golden sets. The metric that governs the deploy approval is the owner's to choose; no
`APPROVAL.json` exists and the gate is closed.

**Speed.** A brief is 40–46 s on these backends: ~17 s of search (18 queries; SearXNG's engines pace
themselves) and ~25 s of fetch (20 slots, 1 req/s per host, a 30 s budget). The levers left are fewer
queries when a facet is named (1 facet query instead of 5), a smaller slice when the hit list is short,
and the engine's own warm cache (a repeated brief answers in 4–30 s).

### 0.1 What iteration 1 and 2 changed (commits 1b31c9a, 7ba577c)

1. A transport timeout trips the host breaker (`STREAK_TIMEOUT=2`), `EE_FETCH_TIMEOUT_S` 30 → 12,
   no second live attempt, and a fetch-phase budget of 45 s cancels stragglers — the baseline lost
   60 s per URL on one tuning client's own site that never answered.
2. The fetch slice is host-diverse (`PER_HOST_CAP=3`, overflow back-fills) and a hit refused before
   any bytes moved (robots, open breaker, never-fetch host) refunds its slot: iteration 2 shows
   `(slot refunded)` on 68 robots and 43 breaker refusals, and fetched 285 documents against 218.
3. A 401/403 is dead at page level, so the first 403 goes to the Wayback snapshot (the connector would
   refuse the same live URL); wikipedia/wikimedia are never fetched.
4. `build_cards` orders confirmed/probable before ambiguous; `verify_cards`' date check can fail;
   the clause-clip check covers widths 80/100/120/140.

### 0.2 Why recall stays below the bar, and what is escalated

- The remaining loss is **fetchability, not retrieval**: of the 22 golden URLs not re-found in
  iteration 2, 4 were surfaced by search and then refused by a WAF (Cloudflare/Akamai 403 on
  thefinancialbrand, scworld, savvymoney, insight) with no Wayback snapshot, and 19 cards' worth of
  the tuning client's own site answered 403/timeout. The connector's own `register_evidence` fetch
  refuses those same pages, so no card from them could register anyway.
- Discovery ran on one free source. The brief's primary backend (SearXNG, FSI engine profile, regulator
  and trade-press `site:` probes from the registry's `site_pack`) is not deployed (Phase E is stopped
  for approval); the registry's `site_pack` is empty in this environment, so no regulator probes ran.
- Questions are derived from the golden excerpts (no question field exists), which favours the page
  the excerpt came from; the recall of a diagnostic question is lower still.
- Two tuning iterations were spent (timeouts/breakers; slice diversity + 403 archive). Per §7 of the
  brief, recall is **escalated to the owner** rather than tuned further: the levers left are (a)
  deploying SearXNG and measuring again, (b) a static egress IP for the WAF-fronted trade press,
  (c) a question field in golden v2 so recall measures the protocol, not the excerpt vocabulary.
- Iteration 2 opened the `web.archive.org` breaker once (the 403→snapshot path now calls it far more);
  a dedicated Wayback bucket is an obvious next change and is NOT made here (it would be a third
  iteration).

### 0.3 Changes after iteration 2, validated offline only (commit after 7ba577c)

- A newline is a sentence boundary (the extractors emit one line per block), so a heading and the
  dateline under it are two spans — the local transcript had carded "title\nANYTOWN, ST, …" as one.
- An archived page is classified and named by its original host, never by web.archive.org (it had
  landed as `other`/T3 with a `web.archive.org —` source name).
- One excerpt per brief: the same words from a syndicated or archived copy are dropped with the
  reason recorded — syndication is never corroboration. None of these change fidelity, liveness or
  recall; they are covered by `tests/test_tools_e2e.py` and `docs/E2E-TRANSCRIPT.md`.

---

# A. Baseline run (verbatim, written by the harness)

Run `v1-20261010T195014Z` · 2026-10-10T19:50:14+00:00 → 2026-10-10T20:00:23+00:00 (608.3 s) · golden **v1** (built 2026-10-10) · mode **LIVE** · results `eval/results/v1-20261010T195014Z.json`

This is the FIRST measurement of the engine against the golden set: every live figure below is the baseline, not a tuned result. Nothing in this report was adjusted after the run.

## 1. Scorecard

| Metric | Measured | Brief's bar | Verdict | Where measured |
|---|---|---|---|---|
| Excerpt fidelity (text[start:end]==excerpt ∧ normalised span in connector text) | 100.0% (116/116 cards) | 100% (hard) | MEETS | offline, over the live run's cards |
| Boilerplate leakage (anti-pattern matches in produced excerpts) | 0 of 116 | 0 (hard) | MEETS | offline |
| Syndication inflation (clusters whose cards disagree with membership) | 0 of 2 multi-URL clusters (172 clusters) | 0 (hard) | MEETS | offline |
| Card size, item + minimal provenance (tokens) | mean 165.9 · p95 219 | ~120 target | ABOVE | offline (heuristic: 4 chars/token over compact JSON (tiktoken not installed)) |
| URL liveness of produced cards (live or archived) | 100.0% (117/117; 0 unchecked for time) | 100% (hard) | MEETS | LIVE |
| Source recall, same url_key | 34.3% (12/35) | ≥ 80% | BELOW | LIVE (baseline) |
| Source recall, same host (loose) | 40.0% (14/35) | (informational) | — | LIVE |
| Search-level recall: golden URL surfaced, card OR fetch refused/dropped (lower bound) | 48.6% (12 carded + 5 surfaced-unreadable / 35) | (diagnostic) | — | LIVE |
| Token efficiency on re-found URLs (full cleaned page → card, item+minimal) | 78.6% (2888 vs 13494 tokens over 14 URLs) | ≥ 60% | MEETS | LIVE fetch, offline count |
| Token efficiency per produced card (its source page → the card) | 96.7% (28565 vs 864440 tokens, 174 cards) | (informational) | — | offline |
| Generalisation (largest tuning↔held-out gap) | 22.0 points | ≤ 5 points | ABOVE | both |
| Parallel rate-limit ceiling | no 429 observed up to 2/s → recommend `EE_PARALLEL_RPS=1.4` | measured, never assumed | — | LIVE |

## 2. What was measured live, what offline

- **LIVE (network)**: `Engine.research_brief` with the real `HttpFetcher` and the Parallel Search MCP as the only discovery source (SearXNG is not deployed; `SEARXNG_URL` unset) — one call per sampled golden row, sequential; `verify_cards(recheck_liveness=True)` over every produced card; one fetch of every sampled golden URL through the engine's fetcher for the token-efficiency denominator; the Parallel ramp through `search.ParallelClient` directly.
- **OFFLINE (no network)**: excerpt fidelity re-read from the Store, boilerplate matching, the golden-negative refusal census, syndication consistency, token counts.
- Ranking ran **bm25-only** (no bundled models in this environment: `EE_MODELS_DIR` unset).
- **Two passes over one store**: 18 row(s) were answered live in the prior pass `v1-20261010T192618Z` (its research phase hit the time deadline before the held-out rows); this pass ran the remaining 17 row(s) live and re-ran liveness, fetches, offline metrics and the ramp over everything. Cold elapsed times are each row's own first call.

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
| tuning | golden1 | 10 | 4 (40.0%) | 4 (40.0%) | 2 | 0 | 0 |
| heldout | logix | 10 | 5 (50.0%) | 5 (50.0%) | 1 | 0 | 0 |
| **tuning** | all | 25 | 7 (28.0%) | 9 (36.0%) | 4 | | |
| **heldout** | all | 10 | 5 (50.0%) | 5 (50.0%) | 1 | | |

"Surfaced but unreadable": the search returned the golden URL but the engine emitted no card for it — fetch failed: http N from www.savvymoney.com (served by nginx) (WAF or access de ×1; fetch failed: http N from www.scworld.com (served by cloudflare) (WAF or access  ×1; fetch failed: http N from thefinancialbrand.com (served by cloudflare) (WAF or a ×1; fetch failed: timed out fetching www.goldenN.com after Ns ×1; fetch failed: http N from www.insight.com (served by AkamaiGHost) (WAF or access ×1. These are fetchability losses, not retrieval losses (the connector's own `register_evidence` fetch would refuse the same pages as `url_unreachable`).

Re-found by golden tier: T1: 0/1; T2: 1/5; T3: 9/21; T4: 0/2; T5: 2/6.

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
| G-477d3bf9 | tuning | 4 | 23 | 9 | — | {"probable": 2, "ambiguous": 2} | 15233 ms | stripped 1 platform name(s) |
| G-8d3ac455 | tuning | 8 | 23 | 8 | — | {"probable": 1, "ambiguous": 7} | 40022 ms |  |
| G-0e516f75 | tuning | 8 | 24 | 10 | url | {"ambiguous": 5, "probable": 3} | 12991 ms |  |
| G-52b47f1a | tuning | 4 | 25 | 4 | host | {"probable": 1, "ambiguous": 2, "confirmed": 1} | 37479 ms |  |
| G-2ab20603 | tuning | 7 | 22 | 9 | — | {"ambiguous": 4, "probable": 3} | 9207 ms |  |
| G-40b1e5f2 | tuning | 6 | 25 | 9 | url | {"probable": 4, "ambiguous": 1, "confirmed": 1} | 22487 ms | stripped 1 platform name(s) |
| G-854ee8db | tuning | 8 | 27 | 9 | — | {"probable": 2, "ambiguous": 5, "confirmed": 1} | 14509 ms | stripped 2 platform name(s) |
| G-e17d0b25 | heldout | 7 | 23 | 8 | url | {"ambiguous": 4, "probable": 3} | 10003 ms |  |
| G-3a1e7d51 | heldout | 8 | 24 | 9 | url | {"probable": 7, "ambiguous": 1} | 9954 ms |  |
| G-7f981e71 | heldout | 3 | 24 | 4 | — | {"confirmed": 1, "probable": 2} | 8923 ms |  |
| G-7089793b | heldout | 6 | 23 | 9 | url | {"ambiguous": 4, "probable": 2} | 9246 ms |  |
| G-4a494c46 | heldout | 5 | 25 | 8 | — | {"probable": 4, "ambiguous": 1} | 7377 ms |  |
| G-116af624 | heldout | 5 | 23 | 7 | — | {"probable": 4, "ambiguous": 1} | 8075 ms |  |
| G-bde7e098 | heldout | 6 | 17 | 6 | url | {"probable": 4, "confirmed": 1, "ambiguous": 1} | 10540 ms |  |
| G-6a9172d1 | heldout | 6 | 23 | 6 | url | {"probable": 4, "ambiguous": 2} | 8950 ms | stripped 1 platform name(s) |
| G-b4c11e10 | heldout | 6 | 24 | 7 | — | {"probable": 5, "ambiguous": 1} | 10438 ms |  |
| G-29834d49 | heldout | 3 | 21 | 3 | — | {"probable": 2, "ambiguous": 1} | 11880 ms |  |

## 5. Timing, counts, breakers

- research_brief elapsed: mean 34702 ms · p95 127341 ms · max 171171 ms over 35 calls. Warm repeats: tuning cold 14916 ms → warm 2167 ms (cached search calls {'parallel': 5}); heldout cold 10003 ms → warm 198 ms (cached search calls {'parallel': 5})
- Totals: hits 827 · fetched 218 · cards 116 · fetch failures shown 200 · dropped shown 34 (the tool truncates both lists at 10 per answer, so these are lower bounds).
- Phase wall time (s): {"research": 247.4, "warm_repeat": 2.4, "liveness": 92.0, "token_efficiency": 265.6}
- Breakers open at the end: ['dockets.justia.com', 'www.businesswire.com', 'www.creditunionsonline.com', 'www.insight.com']. Parallel breaker: {"name": "parallel", "state": "closed", "backoff_s": 0.0, "retry_in_s": 0.0, "last_kind": null, "last_retry_after": null, "opens": 0, "streak_403": 0, "streak_empty": 0, "seconds_since_failure": null}. Coalescer: {"inflight": 0, "upstream_calls": 85, "joined": 0}.
- Errors: 0
- Drop reasons (shown subset): no verbatim sentence-complete span answers the question ×34
- Fetch-failure reasons (shown subset): robots_disallowed ×67; timed out fetching www.goldenN.com after Ns ×34; http N from www.bcu.org ×17; timed out fetching goldenN.com after Ns ×10; http N from www.creditunionsonline.com (served by cloudflare) (WAF or  ×7; http N from www.savvymoney.com (served by nginx) (WAF or access denied ×7; http N from www.businesswire.com (served by AkamaiGHost) (WAF or acces ×6; http N from en.wikipedia.org (served by HAProxy) (WAF or access denied ×5

## 6. Boilerplate: produced cards and the golden-negative census

Produced excerpts matching an anti-pattern: **0** of 116.

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
| item + minimal provenance | 116 | 165.9 | 219 | 120 | 245 |
| item + standard provenance | 116 | 207.8 | 262 | 165 | 288 |
| item + full provenance | 116 | 315.7 | 375 | 269 | 390 |
| item only | | 121.4 | 174 | | |

Counter: heuristic: 4 chars/token over compact JSON (tiktoken not installed).

## 8. Token efficiency

Tokens of CONTENT, not of a transcript: the denominator is the full cleaned text (`pipeline.document_from_fetch`, trafilatura main content) of the golden page as the engine's fetcher reads it — what an agent on the raw-fetch path would have to read — and the numerator is the card(s) the engine returned for that URL (item + minimal provenance). Measured only on URLs the engine re-found (a URL with no card has nothing to compare).

| Split | Sampled URLs | Re-found | Raw tokens (re-found) | Card tokens | Reduction | Fetch failed |
|---|---|---|---|---|---|---|
| tuning | 25 | 9 | 9758 | 1675 | 82.8% | 11 |
| heldout | 10 | 5 | 3736 | 1213 | 67.5% | 1 |
| **all** | 35 | 14 | 13494 | 2888 | 78.6% | 12 |

Secondary (every produced card against its own source page): 96.7% reduction, 174 cards. Raw tokens of ALL sampled golden pages the fetcher could read: 34071.

## 9. Generalisation (tuning vs held-out, points)

- source_recall_url: 22.0
- source_recall_host: 14.0
- url_liveness: 0.0
- token_reduction: 15.3
- excerpt_fidelity: 0.0
- max_gap_points: 22.0
- within_bar: False

## 10. Parallel rate-limit ramp

- 90 `web_search` calls in 61.2 s; ok by rate {"1.0": 30, "2.0": 60}; errors by rate {}; latency p50 1871.0 ms, p95 2417 ms.
- First 429: null; raw probe after it: null.
- Measured ceiling: **no 429 observed up to 2/s** → recommended `EE_PARALLEL_RPS=1.4` (measured × 0.7; adopted as the engine's default in commit 7ba577c).

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

