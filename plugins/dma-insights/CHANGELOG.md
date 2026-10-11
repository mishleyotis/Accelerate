# dma-insights — plugin changelog

## 1.23.0 — 2026-10-10 — the research layer

- **Evidence engine** (`apps/evidence-engine`, Cloud Run `dmai-evidence`,
  plugin server `evidence`, six tools): `research_brief` returns
  register-ready cards (verbatim sentence-complete span verified against the
  page, registry tier hint, licensed claim label, page-stated ISO date, origin
  cluster with syndication count, entity match, recency band) plus a coverage
  block with the saturation stop rule and flagged-never-resolved conflict
  candidates; `crawl_entity`, `filings_evidence` (edgartools in-process),
  `expand_context`, `verify_cards`, `coverage_report`. Contract and the diff
  from the brief's baseline: `apps/evidence-engine/docs/CARD-CONTRACT.md`.
- **Five connectors** declared in `.mcp.json`: `searxng`, `fetch`, `edgar`
  (self-hosted via Supergateway on secret paths; `infra/evidence-engine`),
  `parallel` and `alphaxiv` (vendor, `type: http`). Access through
  `scripts/evidence_proxy.py` + `evidence_auth_headers.sh` — siblings of the
  connector's proxy and helper, which are untouched.
- **Grants** by role (`scripts/provision_agent_tools.py`): engine on the
  research/servicing tier; verify slice on the verifiers and assemblers;
  raw fallbacks on the servicing tier only; per-page producers unchanged
  (owner decision 2026-09-14 stands; recorded in docs/CONNECTORS.md).
- **Hooks**: `rate_gate.py` (PreToolUse, raw fallbacks, fail open) and
  `source_health.py` (PostToolUse, all six); the whole-page-fetch guard lists
  the raw readers.
- **Doctor**: six `research layer:` rows (`scripts/research_layer.py`);
  WARNING for a raw fallback, BLOCKER for the engine only without a search
  fallback.
- **Docs**: `docs/EVIDENCE-ENGINE-TOOLS.md` (generated), CONNECTORS.md
  research-layer section, RESEARCH-PROTOCOL § Tools rung 3, the production
  evidence doctrine, `enrichment_sources.json` search connectors +
  `_free_chain`.
- **Measured** (`apps/evidence-engine/docs/EVAL-REPORT.md`, golden v1 from the
  repo's own corpus, Logix held out): excerpt fidelity 100 %, URL liveness
  100 %, boilerplate 0, syndication inflation 0, token reduction 82.6 % on
  re-found pages; source recall 37.1 % after the two tuning iterations the
  brief allows (fetchability-bound: WAF 403s and one client's own site; one
  free discovery source) — escalated, not tuned further. `tests/` in the
  engine: 302 offline tests; no client string in engine code (CI grep).
- **Not deployed**: every resource-creating step waits on
  `apps/evidence-engine/docs/DEPLOY-PLAN.md` approval.
