# The evidence engine — tool reference

Generated from `apps/evidence-engine/evidence_server.py` by `gen_evidence_tools_md.py`; signatures read with `ast`, descriptions are each tool's docstring verbatim. Regenerate rather than hand-edit.

**7 tools**, FastMCP over streamable HTTP, deployed as `dmai-evidence` (plugin server name `evidence`, scoped tool prefix `mcp__plugin_dma-insights_evidence__`). Contract: `apps/evidence-engine/docs/CARD-CONTRACT.md`.

| Tool | Signature |
|---|---|
| `research_brief` | `research_brief(run_id: str, entity: dict, questions: list[str | dict], sub_vertical: str | None = None, facet: str | None = None, subcap_labels: list[str] | None = None, max_cards: int = 8, token_budget: int = 2400, provenance: str = 'standard', reference_date: str | None = None, allow_names_from_cards: dict | None = None, source_classes: list[str] | None = None)` |
| `crawl_entity` | `crawl_entity(run_id: str, entity: dict, page_budget: int | None = None, depth: int | None = None, path_focus: list[str] | None = None, question: str = '', max_cards: int = 12, token_budget: int = 1500, reference_date: str | None = None)` |
| `filings_evidence` | `filings_evidence(run_id: str, cik_or_ticker: str, forms: list[str] | None = None, years: list[int] | None = None, topics: list[str] | None = None, max_cards: int = 10, token_budget: int = 1500, reference_date: str | None = None, entity: dict | None = None)` |
| `expand_context` | `expand_context(context_handle: str, window: int = 2, run_id: str | None = None)` |
| `verify_cards` | `verify_cards(run_id: str, card_ids: list[str], recheck_liveness: bool = True)` |
| `coverage_report` | `coverage_report(run_id: str)` |
| `find_registrant` | `find_registrant(entity: dict, sub_vertical: str | None = None, country: str | None = None, run_id: str | None = None)` |

## What agents see — the research tool surface

Agents never see the upstream names above. `scripts/evidence_proxy.py` serves each research service through `references/research_tool_surface.json`: a specific name per function, a description that states the source class, the tier it earns and the gold-workbook columns its output fills, and preset arguments the agent cannot override. An upstream tool the surface does not name is not exposed.

| Tool (agent-facing) | Upstream | Preset | What it is for |
|---|---|---|---|
| `mcp__plugin_dma-insights_evidence__find_evidence_all_sources` | `evidence:research_brief` | — | PRIMARY research call — run it FIRST for every capability. |
| `mcp__plugin_dma-insights_evidence__find_regulator_evidence` | `evidence:research_brief` | `source_classes=['regulator']` | Evidence from REGULATOR and government records only: .gov bodies (NCUA, FDIC, OCC, Federal Reserve, SEC, CFPB, FFIEC, state departments of financial institutions), NAIC, FINRA and non-US prudential regulators. |
| `mcp__plugin_dma-insights_evidence__find_trade_press_evidence` | `evidence:research_brief` | `source_classes=['trade_press']` | Evidence from FINANCIAL-SERVICES TRADE PRESS only, sector pack first: American Banker, Banking Dive, The Financial Brand, CU Times, CUInsight, CreditUnions.com, Insurance Journal, ThinkAdvisor, InvestmentNews, PYMNTS, Fintech Futures, trade associations (America's Credit Unions, ABA, ICBA). |
| `mcp__plugin_dma-insights_evidence__find_news_wire_evidence` | `evidence:research_brief` | `source_classes=['news']` | Evidence from NEWS outlets and press-release WIRES only: Reuters, Bloomberg, WSJ, FT, CNBC, AP, PR Newswire, Business Wire, GlobeNewswire. |
| `mcp__plugin_dma-insights_evidence__find_job_posting_evidence` | `evidence:research_brief` | `source_classes=['job_board']` | Evidence from JOB POSTINGS only (the evidence ladder's 'careers' rung): Indeed, Glassdoor, LinkedIn Jobs, Lever, Greenhouse, Workday and iCIMS career sites. |
| `mcp__plugin_dma-insights_evidence__find_customer_review_evidence` | `evidence:research_brief` | `source_classes=['review_site']` | Evidence from CUSTOMER REVIEW and rating sites only: Apple App Store and Google Play listings, Trustpilot, BBB, WalletHub, Bankrate, NerdWallet, DepositAccounts, G2. |
| `mcp__plugin_dma-insights_evidence__find_academic_evidence` | `evidence:research_brief` | `source_classes=['academic']` | Evidence from ACADEMIC and economic research only: arXiv, SSRN, Semantic Scholar, OpenAlex, DOI-resolved papers, NBER. |
| `mcp__plugin_dma-insights_evidence__find_contradicting_evidence` | `evidence:research_brief` | `facet=contradicts` | Hunts evidence AGAINST a claim: every question is searched with the contradicts lens (discontinued, replaced, outage, complaint, settlement) across all source classes. |
| `mcp__plugin_dma-insights_evidence__find_corroborating_evidence` | `evidence:research_brief` | `facet=corroborates` | Hunts a SECOND, independent source for a claim the run already holds: every question is searched with the corroborates lens across all source classes. |
| `mcp__plugin_dma-insights_evidence__read_entity_newsroom` | `evidence:crawl_entity` | `path_focus=['newsroom']` | Evidence cards from the institution's OWN newsroom, press and blog pages (/news, /newsroom, /press, /press-releases, /media, /blog, /insights), sitemap first, robots.txt honoured, page budget and depth capped, with a crawl manifest (seen, fetched, skipped, robots-blocked). |
| `mcp__plugin_dma-insights_evidence__read_entity_careers` | `evidence:crawl_entity` | `path_focus=['careers']` | Evidence cards from the institution's OWN careers pages (open roles, team pages, culture and benefits statements), sitemap first, robots.txt honoured, budget capped, with a crawl manifest. |
| `mcp__plugin_dma-insights_evidence__read_entity_investor_pages` | `evidence:crawl_entity` | `path_focus=['ir', 'disclosures']` | Evidence cards from the institution's OWN investor-relations and disclosure pages (annual reports, financial statements, governance, board and committee charters, regulatory disclosures), sitemap first, robots.txt honoured, budget capped, with a crawl manifest. |
| `mcp__plugin_dma-insights_evidence__read_entity_about_pages` | `evidence:crawl_entity` | `path_focus=['about']` | Evidence cards from the institution's OWN about, leadership and history pages (who leads it, its charter story, field of membership, locations), sitemap first, robots.txt honoured, budget capped, with a crawl manifest. |
| `mcp__plugin_dma-insights_evidence__find_sec_filing_evidence` | `evidence:filings_evidence` | — | Evidence cards anchored in SEC filings: 10-K, 10-Q and 8-K sections (business, risk factors, MD&A, material events) and XBRL facts with exact values, each card citing the filing URL on sec.gov. |
| `mcp__plugin_dma-insights_evidence__find_registrant` | `evidence:find_registrant` | — | Finds the institution in the REGISTRY that holds it — for all nine sub-verticals in the US and Canada, the first identity step of every run. |
| `mcp__plugin_dma-insights_evidence__expand_card_context` | `evidence:expand_context` | — | The sentences around an evidence card's excerpt, ON DEMAND, from the page the engine cached (`context_handle` from the card's provenance; `window` sentences each side). |
| `mcp__plugin_dma-insights_evidence__verify_evidence_cards` | `evidence:verify_cards` | — | Re-checks registered evidence cards before they are believed: the URL is still live (or archived), the excerpt is still verbatim at its offsets in the cached page, the item still passes the card contract (Source_Name, Source_URL, Tier, Excerpt length, Claim_Type licence) and the stated Date_Published still parses and is not in the future. |
| `mcp__plugin_dma-insights_evidence__report_evidence_coverage` | `evidence:coverage_report` | — | The run's evidence coverage, for deciding whether a facet is done: card counts per facet and per label, source diversity, single-source concentration (flag above 40% — a Triangulation risk), the Recency distribution (CURRENT…UNVERIFIED), open conflict candidates, saturation by facet, the evidence-ladder rungs searched (what an absence's Negative_Ladder may cite), and the health of every search backend and upstream search engine. |
| `mcp__plugin_dma-insights_searxng__keyword_search_web_pages` | `searxng:searxng_web_search` | `categories=general` | Keyword search of the general web through the run's own SearXNG metasearch (free, keyless engines paced per engine: Google CSE, Bing, Brave, DuckDuckGo, Qwant, mwmbl, Wikipedia). |
| `mcp__plugin_dma-insights_searxng__keyword_search_news` | `searxng:searxng_web_search` | `categories=news` | Keyword search of NEWS indexes only (Bing News, DuckDuckGo News, Brave News) through the run's own SearXNG. |
| `mcp__plugin_dma-insights_searxng__keyword_search_papers` | `searxng:searxng_web_search` | `categories=science` | Keyword search of SCHOLARLY indexes only (arXiv, Semantic Scholar, OpenAlex, Crossref) through the run's own SearXNG: papers, working papers and sector studies. |
| `mcp__plugin_dma-insights_searxng__suggest_query_refinements` | `searxng:searxng_search_suggestions` | — | Autocomplete suggestions for a partial or vague query from the run's SearXNG — the words people actually search with (a product's market name, a programme's public title). |
| `mcp__plugin_dma-insights_searxng__check_search_engines` | `searxng:searxng_instance_info` | — | What the run's SearXNG instance can do right now: its categories, the engines configured and enabled, defaults and plugins. |
| `mcp__plugin_dma-insights_searxng__read_web_page_section` | `searxng:web_url_read` | — | Reads ONE web page as markdown, in a bounded way: `readHeadings: true` lists its headings, `section` returns one section by heading, `startChar`/`maxLength` pages through it, `paragraphRange` takes paragraphs. |
| `mcp__plugin_dma-insights_fetch__read_web_page_markdown` | `fetch:fetch` | — | Fetches one URL and returns its content as markdown (`raw` for the original HTML), `max_length` characters from `start_index` — page through a long page instead of reading it whole. |
| `mcp__plugin_dma-insights_edgar__get_cik_for_ticker` | `edgar:get_cik_by_ticker` | — | Converts a stock ticker to the registrant's SEC CIK (Central Index Key), which every other SEC tool accepts as `identifier`. |
| `mcp__plugin_dma-insights_edgar__get_sec_registrant_profile` | `edgar:get_company_info` | — | The registrant's SEC profile: legal name, CIK, SIC industry code, exchange, state of incorporation and fiscal year end — Firmographics registry fields (stated, never held) and the identity anchor for every filing cited. |
| `mcp__plugin_dma-insights_edgar__list_sec_filings` | `edgar:get_recent_filings` | — | Lists the registrant's recent SEC filings (`form_type` e.g. |
| `mcp__plugin_dma-insights_edgar__read_10k_10q_sections` | `edgar:get_filing_sections` | — | Extracts named sections — business description, risk factors, MD&A — from one 10-K or 10-Q (`accession_number`, `form_type`). |
| `mcp__plugin_dma-insights_edgar__read_filing_full_text` | `edgar:get_filing_content` | — | The full text of one SEC filing, paged (`offset`, `max_chars`) — for an exhibit, a proxy statement (DEF 14A: board, committees, executive officers) or any form the section tool does not cover. |
| `mcp__plugin_dma-insights_edgar__read_8k_material_events` | `edgar:analyze_8k` | — | The material events one 8-K reports, by item: 1.01 material agreements (a platform or vendor contract), 2.02 results, 5.02 officer and director changes (leadership panel), 7.01 Regulation FD disclosures, 8.01 other events. |
| `mcp__plugin_dma-insights_edgar__get_financial_statements` | `edgar:get_financials` | — | The registrant's financial statements from its filings (`statement_type`: all, income, balance or cash) — revenue, assets, deposits, expenses — for the financial trajectory and Firmographics (each figure with its Unit and As at period). |
| `mcp__plugin_dma-insights_edgar__get_key_financial_metrics` | `edgar:get_key_metrics` | — | Named key metrics from the registrant's XBRL data (`metrics`, e.g. |
| `mcp__plugin_dma-insights_edgar__get_business_segment_data` | `edgar:get_segment_data` | — | Revenue and results by reported segment (`segment_type`: geographic or business) — which lines of business the registrant reports, for the LOB census and subsidiary or segment Firmographics (admissible when the unit names the entity). |
| `mcp__plugin_dma-insights_edgar__compare_financial_periods` | `edgar:compare_periods` | — | One metric across a span of fiscal years (`metric`, `start_year`, `end_year`) with the change between them — the reported series a growth figure or trajectory is computed from. |
| `mcp__plugin_dma-insights_edgar__get_xbrl_company_facts` | `edgar:get_company_facts` | — | Every XBRL fact the registrant has reported across its filings, by concept and period — the complete reported record when a named metric is not enough. |
| `mcp__plugin_dma-insights_edgar__list_reported_metrics` | `edgar:discover_company_metrics` | — | Which XBRL metrics the registrant actually reports, with data counts (`search_term` filters by name) — run it before get_key_financial_metrics so a metric is asked for by the concept the registrant uses. |
| `mcp__plugin_dma-insights_edgar__list_xbrl_concepts` | `edgar:discover_xbrl_concepts` | — | Every XBRL concept present in one filing (`accession_number`, or the latest `form_type`; `namespace_filter` e.g. |
| `mcp__plugin_dma-insights_edgar__get_xbrl_filing_concepts` | `edgar:get_xbrl_concepts` | — | Specific XBRL concept values from one filing (`concepts`, `accession_number` or the latest `form_type`) — an exact reported figure with its period, cited to that filing. |

**Appendix `cards`** (appended to every tool that names it):

OUTPUT → GOLD WORKBOOK. Each card is one Evidence_Detail row: register card['item'] UNCHANGED through `engine.cli evidence` (or register_evidence). Source_Name ← item.source_name (publisher and page title, spelled out). Source_URL ← item.source_url (the page the excerpt is on; provenance.url_status 'archived' means an archive copy). Tier ← item.tier (set by the source registry from the URL, never typed by you; the entity's own domain is never T1). Date_Published ← item.published_date: a date the PAGE states, else null — never the retrieval date; null bands the row UNVERIFIED. Claim_Type ← item.claim_type (FACT only on T1/T2, else INFERENCE). SubCap_IDs ← item.linked_subcap_ids (exactly the cell ids you passed for the question the card answered — the engine never invents one). Excerpt ← item.excerpt (verbatim, 50–500 characters, sentence-complete; provenance.excerpt_offsets locate it in the cached page). The ledger then computes E_ID, Fact_ID, ERS, Recency (CURRENT ≤12 months · RECENT ≤24 · DATED ≤36 · STALE ≤48 · ARCHIVAL older · UNVERIFIED undated), Retrieved_At and Access_Status, and appends the E_ID and Source_URL to each cell's Evidence_IDs and Source_URLs on its P*_Subcap_Scoring row. by_question[] with answered=false is that cell's nothing-found material (Proxy_Searched, Negative_Ladder, Proxy_Log); coverage.ladder_searched names the rungs searched. Log the call as one Search_Log row per cell (SubCap_ID, Facet, Query, Tool=evidence_engine, Hits, Kept, Outcome).

**Appendix `snippets`** (appended to every tool that names it):

OUTPUT IS A RESULT LIST, NOT EVIDENCE: each result is a title, a URL and the search engine's snippet. A snippet is a summary the search engine wrote — never register it as an Excerpt and never take a date from it. To cite a result, read the page through `engine.cli fetch --url <url> --query '<cell question>'` (it caches the page so the ledger can verify the span) or ask find_evidence_all_sources for cards. Log each query as a Search_Log row (SubCap_ID, Facet, Query, Tool=searxng, Hits, Kept, Outcome).

**Appendix `page`** (appended to every tool that names it):

OUTPUT IS PAGE TEXT for the servicing tier and the technographic scanner (category researchers and challengers are refused by the deny_whole_page_fetch hook and read through `engine.cli fetch`, whose cached copy is what the ledger verifies an Excerpt against). Take Excerpt as a verbatim 50–500 character, sentence-complete span; take Date_Published only from a date the page itself states (byline, publication metadata, URL path), never the date you read it.

**Appendix `registry`** (appended to every tool that names it):

OUTPUT → GOLD WORKBOOK. A registry record states identity facts, never a judgement: Firmographics rows Regulator (the registry or primary_regulator), Charter or registry identifier (charter number, FDIC certificate, CRD, CIK, UNINUM), Charter type, Headquarters (city and region), Status, and — where the registry states them — Total assets and Members, each with its Unit and As at; registry answers are stated, never held. Cite the match's record_url as the Evidence row's Source_URL (a regulator or filing authority: Tier T1, Claim_Type FACT) after reading the record through `engine.cli fetch`, so the Excerpt is verbatim from the record and Date_Published is the date it states. The identifier is the identity anchor the ET gates check every later source against: a namesake (match_score below 1.0, a different city, `ambiguous`) is not the entity until the record says so. A `candidates` row is a page to open, not a fact.

**Appendix `sec`** (appended to every tool that names it):

SEC EDGAR is the filing authority's copy: a filing or XBRL fact is Tier T1, Claim_Type FACT. For the Evidence_Detail row cite the filing document URL on sec.gov/Archives (Source_URL), name the form and period in Source_Name (e.g. 'Form 10-K for fiscal 2025 — Example Bancorp'), take Date_Published from the filing date, and take a verbatim Excerpt from the filing text; a bare XBRL number is a Firmographics Value with its Unit and As at period, cited to the same filing.

## `research_brief`

```
research_brief(run_id: str, entity: dict, questions: list[str | dict], sub_vertical: str | None = None, facet: str | None = None, subcap_labels: list[str] | None = None, max_cards: int = 8, token_budget: int = 2400, provenance: str = 'standard', reference_date: str | None = None, allow_names_from_cards: dict | None = None, source_classes: list[str] | None = None)
```

Ranked evidence cards for one or more questions about an entity, plus
a coverage block (novelty, saturation, conflict candidates, the ladder
rungs searched). One call replaces a search → open → read → excerpt loop.
BATCH A WHOLE CAPABILITY: pass `questions` as objects
`{"question": "...", "subcap_ids": ["P1C1.1.1"], "facet": "primary"}` —
one per cell question (and one per owed facet naming every cell it bears
on). One search pass and one fetch slice serve them all; cards come back
with `item.linked_subcap_ids` = the cells of the question each answered
(the caller's ids, echoed, never invented) and `by_question[]` says which
questions got no card. `max_cards`/`token_budget` are then per question.
`entity`: {legal_name, domains[], aliases[], location, charter, cik,
ticker}. `facet` ∈ works|fails|value|contradicts|corroborates (omit for
all five). `subcap_labels` are opaque labels for logging only. A vendor
name in a question is refused unless `allow_names_from_cards` maps it to
the card_id it came from. `provenance` ∈ minimal|standard|full.
`source_classes` ⊆ regulator|filing|entity_owned|trade_press|news|
academic|vendor|job_board|review_site|other restricts the search to
those classes' registered hosts and keeps only hits that classify into
them (omit for every class).

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

## `find_registrant`

```
find_registrant(entity: dict, sub_vertical: str | None = None, country: str | None = None, run_id: str | None = None)
```

The institution in the registry that holds it — every sub-vertical,
US and Canada. Asks, by sub-vertical (CU RB CL CIB AM RIA/WM IC IB FC)
and country (US|CA; omit for both): NCUA (credit unions), FDIC BankFind
(banks), SEC IAPD and FINRA BrokerCheck (advisers, broker-dealers), the
Farm Credit Administration directory (Farm Credit), OSFI (Canadian
federally regulated institutions) and SEC EDGAR (any public parent)
directly; NAIC/state insurance departments and Canadian provincial and
securities regulators, which publish no registry API, are searched on
their own hosts and returned as candidates. Each match carries the
registry's identifier (CIK, CRD, FDIC certificate, NCUA charter, FCA
UNINUM), the record URL and the fields the registry states; every
registry asked reports ok, no_match, candidates, error or not_run.
