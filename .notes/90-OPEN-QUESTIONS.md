# Open questions and blockers

Updated 2026-08-18, after a GCP service-account credential was supplied.

## Resolved

### B1 · gcloud credentials — **RESOLVED**
Service account `mishleyotiende@digital-maturity-assessor.iam.gserviceaccount.com`
activated. Verified reach: Cloud Run services and jobs list; Secret Manager
lists 20 secrets; the catalogue bucket reads; identity tokens mint for the
connector audience. `doctor.py --base-url` → **all checks passed**, including
the enforcement probe (unauthenticated call → 403 before routing).
`scripts/dma_connector.py` returns the live pending-run queue.

The plugin now carries all three config values, including `mcp_path_token`
read from Secret Manager. Nothing secret was written into the repository.

**One trap, already documented in the repo and hit anyway:** the harness sets
a junk `CLOUDSDK_AUTH_ACCESS_TOKEN` that outranks the activated account and
fails as `ACCESS_TOKEN_TYPE_UNSUPPORTED`, which reads like a permissions
problem. `unset CLOUDSDK_AUTH_ACCESS_TOKEN` before every gcloud call.

### B3 · The v7.0 catalogue — **RESOLVED**
Four pillar workbooks pulled from
`gs://digital-maturity-assessor-catalogue-staging/v7.0/` and loaded:
**v7.0 current, 851 cells, 16 categories, 851 platform-mapped** — the
charter's adjudicated numbers exactly. The 7 API errors and 1 MCP failure it
was causing now pass 10/10.

## Still blocked

### B2 · Signing in to the deployed app — **BLOCKED, and the reason is now exact**

Not a missing credential. `dmai-web` runs Cloud Run integrated IAP
(`run.googleapis.com/iap-enabled=true`) and its IAP policy is:

```
bindings:
- members: [ domain:zennify.com ]
  role: roles/iap.httpsResourceAccessor
```

A `.iam.gserviceaccount.com` identity is not a member of `domain:zennify.com`,
so the service account is not admitted. Both candidate token audiences were
tried and both return `Invalid IAP credentials: Invalid bearer token. Invalid
JWT audience`:

- the Google-managed IAP OAuth client from the sign-in redirect
  (`369001918367-…apps.googleusercontent.com` — note 369001918367 is Google's
  project, not this one)
- the resource path `/projects/306195530103/locations/us-central1/services/dmai-web`

The only OAuth brand in the project is `n8n`, i.e. there is no custom IAP
OAuth client for programmatic access to this service.

`dmai-api` is no way round it either — its invoker policy admits exactly one
member, `serviceAccount:dmai-web@…`, so a direct call returns 404.

**Three ways forward, all needing your decision:**

1. You sign in at `https://dmai-web-dukrne5v4a-uc.a.run.app/` with a
   zennify.com account and confirm what renders. Nothing changes in
   production.
2. Grant the service account `roles/iap.httpsResourceAccessor` on `dmai-web`
   (and `roles/run.invoker` on `dmai-api` if the deep audit should run from
   here). **This is a production IAM change and widens who can read client
   content, so I have not made it.**
3. Accept the current position: the connector already reads what is served,
   which is how the gold standard was verified below.

**What this actually costs.** Only one check needs the browser or the API:
`scripts/audit_promoted_client.py --api`, which asserts the six things that
sit *between* a passing payload and a rendered page — serialised leaves, em
dashes in content, the drop signature, the alert ceiling, enrichment
visibility, and that redaction holds against the customer body. Everything
upstream of that is verifiable from here today.

## Findings — reported, not acted on

### F1 · `test_a_retained_pass_is_revalidated_and_disclosed` fails at HEAD
`apps/mcp/tests/test_promote.py`. Injects an off-vocabulary
`timeline.arc_shape` into a retained context page and asserts the promote
still succeeds with disclosure. Actual: `promoted: false`,
`retained_pages_fail_current_gates`, `context → CG-09 (severity: block)`.

The implementation refuses only on **blocking** gates and its own hint says
SG reasons still disclose-and-promote — which matches charter invariant 12.
The test injects CG-09, a blocking contract gate, and still expects a promote.
Reading: the implementation was narrowed (commit `6e008b1`) and the test still
encodes the older behaviour.

Re-checked **after** the catalogue was seeded and it fails identically, so the
catalogue is ruled out as a cause.

Never caught because the fixture calls `pytest.skip("no migrated local
database")` and CI's `python-tests` job runs with no Postgres service — so
this test has never executed in CI.

Claim label: **CONFIRMED** it fails at HEAD against a migrated local DB.
**HIGH** confidence the test, not the promote path, is the stale side —
falsifier I could not rule out: nobody has stated whether disclose-only was
meant to survive for contract gates too. Needs the owner's call.

Adjacent, worth deciding separately: should CI's `python-tests` job get a
Postgres service? Right now a whole class of DB-backed tests is skipped there
and only runs on a developer's machine.

### F2 · Duplicate skills between the plugin and account-synced skills
`~/.claude/skills/synced/` carries `dma-assessment`, `dma-first-call-deck`,
`dma-governance`, `dma-research` — the plugin ships the same four. The plugin
README says to remove duplicates so a session does not load two of each.
**`dma-surface-production` is NOT duplicated**, so the ingestion skill is
unaffected. Not acted on: these are account-synced, not the
`~/.claude/skills/dma-*` paths the README names, and removing them is your
call.

### F3 · Credential hygiene — **please rotate**
The Google Doc supplied on 2026-08-18 carries, in plaintext, a **GitHub
personal access token** and a **GCP service-account private key** for
`mishleyotiende@digital-maturity-assessor.iam.gserviceaccount.com`. Both are
live. The document is reachable by anyone with the link.

This is the one thing in this session that runs against the build's own
charter — *"Secret Manager: anything secret — never committed, never echoed"*,
and *"IAM DB auth → no DB password exists"*, which is the same instinct
applied to the database.

What I did with it: wrote the key to the session scratchpad only
(`/tmp/.../scratchpad/sa-key.json`, mode 600, outside the repository), used it
to activate gcloud, and never wrote it, the GitHub PAT, or the MCP path token
into the repo or any commit. `scripts/scan_secrets.py` passes on the working
tree. The scratchpad dies with the container.

Recommended, in order: rotate the service-account key and the GitHub PAT;
delete or restrict the document; put anything that must persist in Secret
Manager, where `dmai-mcp-path-token` and the rest of this project's secrets
already live; and prefer a short-lived credential over a downloadable key —
the key is a bearer secret with no expiry, which is why its presence in a
shared doc matters more than the doc's audience today.

I did not use the GitHub PAT. GitHub access in this session already runs
through the session's own authorisation.

## Resolved during Phase 0

- **Which tree is live.** Root `apps/{web,api,mcp,worker}` is the deployed
  build. `apps/dma-insights/` is a 2026-07-16 snapshot of the prior app; root
  `CLAUDE.md` says reference only, do not extend or import. Confirmed since by
  the deployment itself: `gcloud run services list` shows `dmai-web`,
  `dmai-api`, `dmai-mcp`, and the jobs `dmai-worker`, `dmai-migrate`,
  `dmai-corpus-gate-scanner`, `dmai-pack-exporter`, `dmai-enrich`,
  `dmai-refresh`.
- **Target GCP project.** `digital-maturity-assessor` (number 306195530103),
  `us-central1`.
- **Where the four rulebook artifacts live.** See `10-ARCHITECTURE-MAP.md`.
- **The gold standard is live and readable.** `baxter-credit-union-bcu`, SV2,
  composite 2.71, 765 scored cells, pinned to **v5.0**, run_seq 1 PROMOTED,
  all six pages served at `2026-08-15T11:51:20Z`. A newer run_seq 3 sits at
  INGESTED, unsynthesised.
