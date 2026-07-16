# ADR 0010 — Clay enrichment connector

Status: ACCEPTED · Date: 2026-05-20

## Context

The DMA package (`02_research_workbook/research_handoff.json`) gives us a
minimal `entity` block — legal name, ticker, HQ, founded year, total
assets, regulator. For D1 Overview we also need richer firmographics
(AUM, revenue, headcount) and full leadership profiles (CEO, COO, CIO,
CDO, AE counterparts). Two leading options:

1. **Apollo / LinkedIn direct integration** — owned in-house, brittle
   (rate limits, login walls), would need our own scraping infra.
2. **Clay (clay.com) table webhook** — Clay already aggregates 75+
   enrichment sources behind one waterfall API; Zennify Ops uses Clay
   for prospecting today.

## Decision

Adopt Clay via its **Table Webhook** pattern:

- Outbound trigger: `POST {clay_webhook_url}` with `{entity_id, domain,
  name, ticker}` from `app/services/clay_client.py::trigger_enrichment`.
- Inbound callback: Clay POSTs the enriched payload to
  `POST /api/v1/clay/webhook` signed with
  `X-Clay-Signature: sha256=<hex hmac>` using `clay_webhook_secret`.
- Persistence: `firmographics.leadership`, `aum_usd`, `revenue_usd`,
  `headcount`, `hq_address`, `primary_regulator`, `clay_synced_at`.
- UI: `ClientOverviewPage.LeadershipSection` shows a `Pull from Clay` /
  `Refresh from Clay` CTA (Analyst+ gated server-side; AE sees the
  section read-only).

State-branch contract for the connector:
- `clay_webhook_url` unset → trigger returns `ClayDisabled` (button
  reads "Clay not configured"); inbound webhook 401s every payload.
- `clay_webhook_secret` unset → all inbound payloads 401 even if a
  `X-Clay-Signature` header is supplied. Fail-closed.

**Both Clay secrets are required in production.** The disabled
branches above exist for `env=local` / `env=test` convenience.
`app/config.py::assert_production_ready()` refuses to boot the
backend when either secret is empty under `env=prod`. Operators
who do not want Clay enrichment in their environment should NOT
deploy with empty secrets — they should set `env=local` (which
disables the guard wholesale) or open a follow-up ADR to introduce
an explicit `CLAY_ENABLED=false` toggle. 2026-05-28 audit (F-306)
confirmed this contract; `tests/test_clay_prod_config_contract.py`
pins both halves.

## Why not just call Apollo directly?

Apollo's leadership data is solid but: (a) we'd reinvent Clay's
waterfall logic, (b) we'd need our own LinkedIn fallback, (c) Zennify
already pays for Clay. Wrapping Apollo would be cheaper code only if we
already had it; we don't.

## Operational notes

- Clay table: `DMA Insights — Entity Enrichment` (owner: Mishley).
- Webhook URLs (per env): `dma-insights-clay-webhook-url` in Secret
  Manager.
- Webhook secret: `dma-insights-clay-webhook-secret`. Rotated quarterly
  by ops.
- Rate limit: 20 outbound triggers per analyst per hour (`/admin/rag-tuning`
  exposes the counter once stage-12 finalize lands).

## Consequences

- Adds a third-party dependency (`clay.com`). If Clay degrades, leadership
  data goes stale but D1 still renders from the package's research
  handoff — graceful degradation, not page failure.
- Adds two secrets to Secret Manager (`clay_webhook_url`,
  `clay_webhook_secret`).
- Adds an unauthenticated `POST /api/v1/clay/webhook` endpoint guarded
  only by HMAC; the route appears in the e2e_routes smoke test as
  `BEARER_GATED` (returns 401 without the right header). Documented in
  the deployment guide.

## Amendment — 2026-06-10: Clay DEFERRED for this version

Operator decision: Clay is **not in prod for this release**. The
firmographics provenance chain is now:

1. **Ingest (deterministic):** client research / Client Profile report
   extraction — `entity_profile.json` / `financial_baseline.json`
   structured fields (alias-tolerant, incl. the nested `financials`
   wrapper), Client-Profile DOCX narrative mining in STRICT mode (a
   field is accepted only when every amount in the text agrees — an
   acquired bank's "$2.2B assets" beside the entity's own "$35B" yields
   nothing rather than a wrong number).
2. **Gemini gap-fill (`firmographics_extraction` surface, Flash):**
   grounded on the entity's own report excerpts; STRICT-JSON output;
   each field requires a VERBATIM supporting quote present in the
   grounding text, else it is dropped (mirrors the E-ID validator).
   Runs in `enrich_corpus` post-deploy; persists into
   `firmographics.parsed_facts` for MISSING keys only.
3. Clay (when it ships): re-add `clay_webhook_url` /
   `clay_webhook_secret` to `REQUIRED_FOR_PROD_BACKEND`, flip
   `tests/test_clay_prod_config_contract.py` back to required-in-prod,
   and Clay-synced columns again take precedence over parsed facts.

Until then `assert_production_ready` does NOT require the Clay
secrets; `deploy-two-phase.sh` provisions placeholder secret versions
so Cloud Run secret refs resolve, and the Clay client's fail-closed
"disabled" branch is the production behavior.
