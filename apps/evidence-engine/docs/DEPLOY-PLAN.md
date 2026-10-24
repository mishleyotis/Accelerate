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
| Static egress (**opt-in, `EE_STATIC_EGRESS=1`**) | address `dmai-evidence-egress`, router `dmai-evidence-router`, NAT `dmai-evidence-nat` (all-traffic VPC egress on the engine and SearXNG) | one stable IP so SearXNG engine health can be measured and a block is diagnosable; the NAT bills per hour plus data | **the one always-on charge in this plan**; NOT created by the default deploy — its own approval |
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

## Routing (owner, 2026-10-11): the deploy is automatic after merge, behind one approval

1. A merge to the default branch runs CI's `deploy` job (every check green,
   Workload Identity as the CI deployer, `infra/deploy.sh` ships web/api/mcp
   as before — the last default-branch run did exactly that, 27 minutes).
2. The same job then runs `infra/evidence-engine/ci_gate.sh`. It reads
   `infra/evidence-engine/APPROVAL.json` through `approval_check.py`; with no
   file, or a metric at or below 90 percent, it prints why and passes (the
   release of the existing services is never held). The metric the owner
   chose (2026-10-11, "Fix the above to ensure deploy happens", after
   same-URL recall stayed at 36 % / 70 % and 22 % / 22 % while question
   coverage read 100 % on both splits of both golden sets) is **question
   coverage — the share of briefs answered by at least one entity-confirmed
   or probable card, recomputed from the per-call rows of the results file
   the approval names, above 90 percent on tuning AND held-out**; the gate
   prints the same-URL recall beside it. With a clearing approval it runs
   `deploy-evidence.sh` with `EE_DEPLOY_APPROVED=1` and the smoke test.
3. No prerequisite by hand for the default plan: the CI deployer already
   holds `iam.serviceAccountAdmin` and `resourcemanager.projectIamAdmin`
   (`infra/grants-for-admin.sh`), so the gate sets
   `EE_GRANT_PROJECT_ROLES=1` and makes the four identities and their
   logging binding itself. The static egress (address + router + NAT, the
   plan's one always-on charge) is **opt-in** (`EE_STATIC_EGRESS=1`, which
   also needs `compute.networkAdmin` from `grant-deployer.sh`); without it the
   services use Cloud Run's default egress. `searxng/health.sh` decides
   whether it is worth turning on. Every step is idempotent.
4. The approval file is written by the person who approves, with the run
   id; a file that does not clear the bar cannot be committed
   (`scripts/tests/test_ci_deploy_job.py`).
