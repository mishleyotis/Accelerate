# apps/evidence-engine — gold-standard evidence cards, not raw pages

The research layer's primary interface (plugin server `evidence`, Cloud Run
`dmai-evidence`). An agent sends an entity, a facet and a question;
it gets back **register-ready cards** — a verbatim, sentence-complete
50–500-character span verified against the page, the registry's tier hint,
the claim label that tier licenses, the page-stated ISO date, origin cluster
and syndication count, entity match, recency band — plus a coverage block
(novelty, the saturation stop rule, conflict candidates flagged and never
resolved, the proxy-ladder rungs searched). The card's `item` is the
`register_evidence` argument verbatim and the exact `engine.cli evidence`
flag set. The engine never links a cell, never raises a claim label or a
tier, never resolves a conflict, never calls a model.

| Doc | What |
|---|---|
| `docs/DISCOVERY.md` | Phase A: every brief-vs-repository correction, verified upstream names, licences, limits |
| `docs/CARD-CONTRACT.md` | the derived card contract and its diff from the brief's baseline |
| `docs/EVAL-REPORT.md` | Phase D: golden-set metrics against every bar, tuning vs held-out, token efficiency, measured limits |
| `docs/DEPLOY-PLAN.md` | Phase E: the resources `infra/evidence-engine/deploy-evidence.sh` would create — **stopped for approval** |
| `../../plugins/dma-insights/docs/EVIDENCE-ENGINE-TOOLS.md` | the six tools, generated from `evidence_server.py` |

## Layout

```
evidence_server.py        FastMCP app: six tools, /healthz, X-DMA-Path-Token door
evidence_engine/
  contract.py             the card; every pre-fetch refusal of register_evidence / the ledger
  textnorm.py             connector-identical extraction + the one shared normalisation (pinned by test)
  extract.py  dates.py    trafilatura / pypdfium2; page-stated dates only, never guessed
  excerpt.py              sentence-complete verbatim span selection; registry/boilerplate.txt
  search.py  query.py     SearXNG JSON + Parallel MCP fan-out with RRF; facet expansion; vendor-name guard
  fetch.py  ratelimit.py  httpx, politeness, robots, Wayback; buckets, breakers, coalescing
  dedupe.py  rank.py      MinHash origin clusters; BM25 (+ optional ONNX rerank, bundled models)
  registry.py  entity.py  registry/fsi_domains.yaml tier hints (pinned to apps/mcp source_rules); entity match
  filings.py  crawl.py    edgartools in-process; bounded own-site crawl
  pipeline.py  tools.py   URL → Document → cards; the six tools over one Engine
  coverage.py  store.py   coverage/saturation/conflicts; content-addressed store with TTLs (+ GCS mirror)
registry/                 committed data: domains, boilerplate, platform names, abbreviations
eval/                     golden set builder (rows gitignored, manifest committed) and harness
tests/                    offline, deterministic, no model; fixtures/site is an invented institution
```

## Run

```
pip install -r requirements.txt
EE_PATH_TOKEN=<token> SEARXNG_URL=http://127.0.0.1:8080 python evidence_server.py     # :8080/mcp
python -m pytest tests -q                                                            # 296 tests, offline
python eval/build_golden.py --version v1 --fetch golden1=<run> ...                   # needs connector credentials
python eval/harness.py --version v1 --live                                           # needs network
```

With no `EE_MODELS_DIR` the engine ranks with BM25 only and says so
(`rerank: bm25-only`); the Dockerfile bakes `BAAI/bge-small-en-v1.5` (MIT)
and `Xenova/ms-marco-MiniLM-L-6-v2` (Apache-2.0) and switches the dense +
cross-encoder stage on.

## Hard rules it enforces

- No client-specific string anywhere in `evidence_engine/`, `registry/`,
  `evidence_server.py` or `tests/` (`tests/test_no_client_strings.py`; the
  golden set under `eval/golden/` is the one place clients are named).
- A card whose span is not in BOTH the clean text and the connector-shaped
  text is not emitted. A dead URL with no Wayback snapshot yields no card.
- Rate limits (brief §6a) are enforced once, here: SEC 8 req/s global,
  1 req/s per host, breakers 30 s → 10 min honouring `Retry-After`,
  identical in-flight queries coalesced, search cached 24 h, text cached by
  recency class. When only paid sources remain the engine returns
  `needs_spend_approval` and spends nothing.
