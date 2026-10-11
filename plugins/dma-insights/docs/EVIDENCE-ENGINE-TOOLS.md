# The evidence engine — tool reference

Generated from `apps/evidence-engine/evidence_server.py` by `gen_evidence_tools_md.py`; signatures read with `ast`, descriptions are each tool's docstring verbatim. Regenerate rather than hand-edit.

**6 tools**, FastMCP over streamable HTTP, deployed as `dmai-evidence` (plugin server name `evidence`, scoped tool prefix `mcp__plugin_dma-insights_evidence__`). Contract: `apps/evidence-engine/docs/CARD-CONTRACT.md`.

| Tool | Signature |
|---|---|
| `research_brief` | `research_brief(run_id: str, entity: dict, questions: list[str], sub_vertical: str | None = None, facet: str | None = None, subcap_labels: list[str] | None = None, max_cards: int = 8, token_budget: int = 2400, provenance: str = 'standard', reference_date: str | None = None, allow_names_from_cards: dict | None = None)` |
| `crawl_entity` | `crawl_entity(run_id: str, entity: dict, page_budget: int | None = None, depth: int | None = None, path_focus: list[str] | None = None, question: str = '', max_cards: int = 12, token_budget: int = 1500, reference_date: str | None = None)` |
| `filings_evidence` | `filings_evidence(run_id: str, cik_or_ticker: str, forms: list[str] | None = None, years: list[int] | None = None, topics: list[str] | None = None, max_cards: int = 10, token_budget: int = 1500, reference_date: str | None = None, entity: dict | None = None)` |
| `expand_context` | `expand_context(context_handle: str, window: int = 2, run_id: str | None = None)` |
| `verify_cards` | `verify_cards(run_id: str, card_ids: list[str], recheck_liveness: bool = True)` |
| `coverage_report` | `coverage_report(run_id: str)` |

## `research_brief`

```
research_brief(run_id: str, entity: dict, questions: list[str], sub_vertical: str | None = None, facet: str | None = None, subcap_labels: list[str] | None = None, max_cards: int = 8, token_budget: int = 2400, provenance: str = 'standard', reference_date: str | None = None, allow_names_from_cards: dict | None = None)
```

Ranked evidence cards for one or more questions about an entity, plus
a coverage block (novelty, saturation, conflict candidates, the ladder
rungs searched). One call replaces a search → open → read → excerpt loop.
`entity`: {legal_name, domains[], aliases[], location, charter, cik,
ticker}. `facet` ∈ works|fails|value|contradicts|corroborates (omit for
all five). `subcap_labels` are opaque labels for logging only. A vendor
name in a question is refused unless `allow_names_from_cards` maps it to
the card_id it came from. `provenance` ∈ minimal|standard|full.

## `crawl_entity`

```
crawl_entity(run_id: str, entity: dict, page_budget: int | None = None, depth: int | None = None, path_focus: list[str] | None = None, question: str = '', max_cards: int = 12, token_budget: int = 1500, reference_date: str | None = None)
```

Cards from the institution's OWN pages (sitemap + newsroom, press,
careers, investor relations, disclosures; robots honoured; budget and
depth capped) with a crawl manifest (seen, fetched, skipped,
robots-blocked). `path_focus` ⊆ newsroom|careers|ir|disclosures|about.

## `filings_evidence`

```
filings_evidence(run_id: str, cik_or_ticker: str, forms: list[str] | None = None, years: list[int] | None = None, topics: list[str] | None = None, max_cards: int = 10, token_budget: int = 1500, reference_date: str | None = None, entity: dict | None = None)
```

Cards anchored in 10-K/10-Q/8-K sections and XBRL facts with exact
values and filing URLs (edgartools in-process, cached, 8 req/s global).

## `expand_context`

```
expand_context(context_handle: str, window: int = 2, run_id: str | None = None)
```

The sentences around a card's span, ON DEMAND only — for
disambiguation, a challenger check or a contradiction review.

## `verify_cards`

```
verify_cards(run_id: str, card_ids: list[str], recheck_liveness: bool = True)
```

Re-run liveness, verbatim-offset integrity, contract and date checks
on cards. Used by the adversarial verifier and before promotion.
Confidence only moves down.

## `coverage_report`

```
coverage_report(run_id: str)
```

Per-facet and per-label card counts, source diversity, single-source
concentration (flag > 40%), recency distribution, open conflict
candidates, saturation by facet, and the ladder rungs searched.
