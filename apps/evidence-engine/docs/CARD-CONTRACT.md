# The evidence card — derived contract (v1, 2026-10-10)

Derived from, in authority order: `apps/mcp/dma_mcp/register.py`
(`register_evidence` — what the connector reads from `item`),
`plugins/dma-insights/skills/dma-research/engine/ledger.py`
(`append_evidence` — what `engine.cli evidence` reads), the fields every
public-URL row of the Golden 1, Baxter and Logix `heatmap.evidence` indexes
carries (`e_id · url · source_name · excerpt · tier · claim_type ·
published_date · supports_subcap_ids · surfaces · discovered_by`), and the
brief's baseline card. The contract is enforced by
`evidence_engine/contract.py` and `tests/test_contract.py`, and the
one-to-one mapping by `tests/test_register_mapping.py`, which asserts that
`card["item"]` satisfies every refusal `register.py` applies before it
fetches, and that `item_to_engine_flags(card)` renders the exact
`engine.cli evidence` argument list.

## 1. Shape

```json
{
  "card_id": "EV-3f9a1c2e",
  "item": {
    "source_name": "National Credit Union Administration — Call report, 2026 Q2",
    "source_url": "https://ncua.gov/…",
    "excerpt": "Total assets of $6.11 billion at June 30, 2026, up 4.2 percent over the year.",
    "claim_type": "FACT",
    "tier": "T1",
    "published_date": "2026-08-15",
    "linked_subcap_ids": [],
    "origin": "producer"
  },
  "provenance": {
    "url_status": "live",
    "original_url": null,
    "archive_timestamp": null,
    "retrieved": "2026-10-10",
    "recency": "CURRENT",
    "source_type_hint": "regulator",
    "tier_basis": "registry: ncua.gov is a prudential regulator (T1)",
    "excerpt_offsets": [1234, 1312],
    "content_hash": "sha256:…",
    "context_handle": "CTX-7d2b…",
    "facet_hints": ["works", "corroborates"],
    "query_ids": ["Q-03"],
    "origin_cluster": "OC-9c0e…",
    "syndication_count": 1,
    "relevance": 0.87,
    "entity_match": "confirmed",
    "entity_match_basis": "legal name and charter number on page",
    "ladder_rung": "regulator",
    "via": "searxng"
  }
}
```

`item` **is** the `register_evidence` argument: a producer calls
`register_evidence(run_id, item=card["item"])` and nothing else. A collector
renders the same block as `engine.cli evidence --source … --url … --tier …
--excerpt … --published … --claim-type … --origin public --subcap <cell>`
through `contract.item_to_engine_flags`, adding only the cells **it**
decided and its own `--actor`. `provenance` is the engine's and is never
sent to either write path.

## 2. Field rules — `item`

| Field | Rule | Where the rule comes from |
|---|---|---|
| `source_name` | Publisher + document, ≤ 160 chars, **no abbreviation the shared list expands** (a label, not a span: expanded) | `abbreviations.py`; CG-27 |
| `source_url` | The URL the connector will fetch and verify against. A live URL as crawled (canonicalised: scheme + host lower-cased, fragment dropped, tracking params dropped); for a dead page, the Wayback **`id_`** raw-snapshot URL, with the original in `provenance.original_url` | `register.py` fetches `source_url`; `url_unreachable` otherwise |
| `excerpt` | Verbatim substring of the cleaned text at `provenance.excerpt_offsets`; **50–500 chars**; sentence-complete (starts at a sentence start, ends at a terminal mark or the document end); never a clause ending in a cut word; whitespace exactly as the cleaned text; no ellipsis inserted | `register.py` 50–500 + `excerpt_clip.clause_truncated`; `ledger.append_evidence`; `EXCERPT_FIELDS` |
| `claim_type` | `FACT` when `tier` ∈ {T1, T2}, else `INFERENCE` — the label the tier *licenses*. The agent may **lower** it (INFERENCE / HYPOTHESIS / CEILING_ESTIMATE); raising it is refused downstream | `contract.claim_label_for`; `register.py fact_tier`; ET-10 |
| `tier` | The registry hint `T1…T5`; never `T1` on the entity's own domain; `T1` for a named machine scan source; `T5` for vendor collateral path shapes | `source_rules.py`; `ledger.is_own_host`; `contract.SCAN_TIER` |
| `published_date` | ISO `YYYY-MM-DD` the **page states** (publication metadata, JSON-LD, `<time>`, dateline, URL path), else `null`. Never the retrieval date, a modified date or a copyright year; never in the future | `fetch.published_date`; `ledger._refuse_retrieval_date_as_published`; invariant 9 |
| `linked_subcap_ids` | Always `[]` from the engine | Division of labour |
| `origin` | Always `"producer"` (the connector enum) — the engine never emits `connector`, `internal` or `package` rows | `register._ORIGINS` |

The ERS, the recency band and the identifiers are the server's; the card
never carries an `e_id`, an `ers` or a band in `item`.

## 3. Field rules — `provenance`

| Field | Values | Note |
|---|---|---|
| `url_status` | `live` \| `archived` | `archived` ⇒ `original_url` and `archive_timestamp` set, `source_url` is the `id_` snapshot |
| `retrieved` | ISO date | the engine's fetch date |
| `recency` | `CURRENT` \| `RECENT` \| `DATED` \| `STALE` \| `ARCHIVAL` \| `UNVERIFIED` | computed against the run's `reference_date` when the caller gives one, else today; undated or future ⇒ `UNVERIFIED` |
| `source_type_hint` | `regulator` \| `filing` \| `entity_owned` \| `trade_press` \| `news` \| `academic` \| `vendor` \| `job_board` \| `review_site` \| `other` | from `registry/fsi_domains.yaml` + path shapes |
| `tier_basis` | prose | the registry rule that produced `item.tier` |
| `excerpt_offsets` | `[start, end]` into the cleaned text whose `sha256` is `content_hash` | `cleaned[start:end] == item.excerpt`, re-checked by `verify_cards` |
| `content_hash` | `sha256:<hex>` of the cleaned text | the same text `expand_context` reads |
| `context_handle` | `CTX-<hash8>` | opaque; `expand_context` resolves it |
| `facet_hints` | subset of `works · fails · value · contradicts · corroborates` | which facet queries retrieved it |
| `query_ids` | `Q-nn` | the expanded queries that hit |
| `origin_cluster` / `syndication_count` | `OC-<hash8>` / int | near-duplicate cluster; a syndicated copy is **one** origin |
| `relevance` | 0–1 | final rank score; informational |
| `entity_match` / `entity_match_basis` | `confirmed` \| `probable` \| `ambiguous` + prose | `confirmed` = own domain, or legal name + (location \| charter \| CIK) on the page; only `confirmed` may feed tech-stack / firmographic surfaces, and the tool result says so |
| `ladder_rung` | `entity_site` \| `regulator` \| `filings` \| `trade_press` \| `news` \| `careers` \| `academic` \| `other` | which proxy-ladder rung the source sits on |
| `via` | `searxng` \| `parallel` \| `crawl` \| `edgar` \| `cache` (+ `rerouted_from:<source>` when a breaker tripped) | search provenance |

## 4. Diff from the brief's baseline card

| Baseline | Here | Why |
|---|---|---|
| flat object | `item` + `provenance` | zero-transformation registration: the producer passes `item` as is |
| `url`, `source_name`, `excerpt`, `published` | `item.source_url`, `item.source_name`, `item.excerpt`, `item.published_date` | the connector's names |
| `published: "15 March 2026"` (DMY) | ISO `2026-03-15` | the connector parses ISO only; DMY would store as undated |
| `recency: CURRENT|RECENT|LEGACY|UNVERIFIED` | the six-word ladder | repo vocabulary (QA Report B-09) |
| `tier_hint` | `item.tier` + `provenance.tier_basis` | the item needs a tier; the hint is labelled as one by its basis |
| (none) | `item.claim_type` (licensed default) | the connector requires it; derivation is the ledger's own |
| (none) | `item.linked_subcap_ids: []`, `item.origin: "producer"` | required by the connector; both deliberately inert |
| `excerpt ≤ 25 words` | 50–500 chars, sentence-complete, ≤ 40-word target | the connector's refusals; see DISCOVERY §1 |
| `archive_url` | `original_url` + `archive_timestamp`, with the snapshot in `source_url` | the connector fetches `source_url`; a dead original there would be refused |
| `entity_match` | + `entity_match_basis` | a verdict a challenger can check |
| (none) | `ladder_rung`, `via` | the proxy-ladder report and breaker provenance the brief asks for elsewhere |

## 5. Verbatim integrity — how it is guaranteed across three extractors

The excerpt is verified three times by three programs: the engine (at card
creation and in `verify_cards`), the research ledger (`fetch_cache` text)
and the connector (`_fetch` at registration). All three compare
`normalise(excerpt) in normalise(text)` with `normalise = collapse
whitespace, strip, casefold`. The engine therefore:

1. extracts **main content** with trafilatura for *ranking and excerpt
   selection*, but
2. verifies the chosen span against the **connector-identical** extraction
   (`textnorm.connector_text`, a byte-for-byte copy of
   `apps/mcp/dma_mcp/fetching._html_text` / `_pdf_text` ligature folding,
   pinned by `tests/test_textnorm_matches_connector.py` which imports the
   connector module by path when the checkout is present), and
3. emits a card only when the span is present in **both** texts. A span
   trafilatura produced that the tag-stripping extractor does not contain
   (an inline-tag join such as `<b>Fin</b>ancial`) is dropped, never
   repaired.

PDF text is produced by `pypdfium2` for ranking and by the connector's
`pypdf` path for verification when `pypdf` is importable; the ligature
folds are identical.

## 6. Size

Target ≤ ~120 tokens per `item` + `provenance` serialised compactly;
measured by `eval/token_budget.py` (cl100k-class heuristic: 4 chars/token,
plus a true count when `tiktoken` is importable) and reported as mean and
p95 in `docs/EVAL-REPORT.md`. The `item` block alone is what an agent needs
to register; `provenance` is returned by default and can be trimmed with
`research_brief(..., provenance="minimal")` to `url_status, recency,
entity_match, origin_cluster, context_handle`.
