# Phase E — deploy plan (PRINTED, NOT EXECUTED — approval required)

Nothing below has run. `infra/evidence-engine/deploy-evidence.sh` prints
this plan and exits unless `EE_DEPLOY_APPROVED=1` is set by a person after
reading it (brief §7.2, §10). It creates **only new resources**; it never
names `dmai-mcp`, `dmai-api`, `dmai-web`, `dmai-worker` or `dmai-share`
(the script refuses if any appears in its arguments).

Project `digital-maturity-assessor`, region `us-central1`.

## Resources that would be created

| Kind | Name | Why | Ongoing cost driver |
|---|---|---|---|
| Service accounts | `dmai-evidence`, `dmai-searxng`, `dmai-fetch`, `dmai-edgar` | one identity per service, least privilege (`logging.logWriter` only at project level) | none |
| Secrets | `dmai-evidence-path-token`, `dmai-searxng-path-token`, `dmai-fetch-path-token`, `dmai-edgar-path-token`, `dmai-searxng-secret-key` | capability tokens (random, 48 hex) and SearXNG's session key; each readable only by its service, the evidence token also by `dmai-routine` (the plugin's identity rung) | Secret Manager access calls (negligible) |
| Buckets | `${PROJECT_ID}-dmai-evidence-text`, `-dmai-evidence-cache` | cleaned text by content hash; search/card caches with TTL | storage, small |
| Static egress | address `dmai-evidence-egress`, router `dmai-evidence-router`, NAT `dmai-evidence-nat` (all-traffic VPC egress on the engine and SearXNG) | one stable IP so SearXNG engine health can be measured and a block is diagnosable; the NAT bills per hour plus data | **the one always-on charge in this plan**; stated here for approval |
| Cloud Run `dmai-searxng` | SearXNG + mcp-searxng + door proxy; 1Gi, cpu-boost, max 2, concurrency 10 | search backend + raw fallback | per request |
| Cloud Run `dmai-fetch` | mcp-server-fetch via Supergateway; 1Gi, max 2, concurrency 10 | raw fallback | per request |
| Cloud Run `dmai-edgar` | sec-edgar-mcp (AGPL-3.0, unmodified) via Supergateway; `SEC_EDGAR_USER_AGENT` set | raw fallback | per request |
| Cloud Run `dmai-evidence` | the engine; **2Gi, 2 vCPU, cpu-boost, max 2, concurrency 8 (tune from measurement), timeout 300** | primary research interface | per request; **no min-instances** (an always-on instance is a separate approval, brief §6b) |
| IAM | `run.invoker` on each service for `dmai-routine` (and `dmai-evidence` on the three backends) | the plugin's proxy mints an ID token for each audience | none |

## What stays untouched

`dmai-mcp` and every existing service, Cloud SQL, Redis, the existing
buckets, the Scheduler triggers, `infra/deploy.sh`, `provision.sh`.

## Sequence once approved

1. `EE_DEPLOY_APPROVED=1 infra/evidence-engine/deploy-evidence.sh`
2. `infra/evidence-engine/smoke.sh` — wrong path 404s on all four; `tools/list` non-empty (6 / 4 / 1 / 18).
3. `SEARXNG_JSON_URL=… infra/evidence-engine/searxng/health.sh` before and after the NAT is attached; HALT if fewer than 3 general-web engines respond (present §6c options with costs).
4. Supergateway stateless vs `--stateful` (`STATEFUL=1` env) chosen on measured p50/p95 latency; recorded in `docs/EVAL-REPORT.md`.
5. Re-run `apps/evidence-engine/eval/harness.py --version v1 --live` against the live services; cold and warm latencies recorded.
6. Set the plugin's `evidence_base_url` default if the URL differs from `https://dmai-evidence-dukrne5v4a-uc.a.run.app`.

## Not in this plan (each its own approval)

Paid keys (Brave API, Mojeek API, Tavily/Exa credit), any proxy, `--min-instances 1`, Parallel's keyed tier.
