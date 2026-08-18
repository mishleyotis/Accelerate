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

### F3 · Credential hygiene — **rotation requested, status unknown**
The credentials used to unblock this session on 2026-08-18 were supplied
out of band in plaintext rather than through Secret Manager. Rotation was
recommended to the owner; whether it has happened is not recorded here.

Details were given to the owner in session and are deliberately **not**
written down here — a note that says which identity to go after is a pointer,
and this file is in the repository.

Two things a later session should carry forward regardless:

- **Treat any long-lived key reaching this build out of band as suspect**
  until the owner confirms rotation. It is a bearer secret with no expiry,
  which is why the exposure outlives the conversation that caused it.
- **The charter already settles the general case** — *"Secret Manager:
  anything secret, never committed, never echoed"*, and *"IAM DB auth → no DB
  password exists"*, which is the same instinct applied to the database.
  Anything that must persist belongs where `dmai-mcp-path-token` already is.

Nothing secret was written into the repository at any point.
`scripts/scan_secrets.py` passes on the working tree (3165 files); credential
material lived only in the session scratchpad, outside the repo, and dies with
the container.

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

## Findings from the Logix remediation (2026-08-18)

### MEM-0087 · a machine technographic scan can be filed below T1
Recorded and gated (`source_rules.scan_tier_violation`). Same scan output:
**ERS 3.75 at T4, 4.4-4.8 at T1**. T4's ceiling sits below the L1-L2 a
CONFIRMED tech row needs, so the surface read "0 of 6 detected" over six real
products. `E-CC-308` stands mis-tiered because dedup merges dates and links but
never tier; the corrected registrations are `E-CC-324`..`E-CC-331`.

### MEM-0088 · the stated pillar and category grains were lost in silence
`parse_grain_summaries` was the only companion parser that did not take the
observations list. Logix: `rollups.pillars 0, categories 0`; Baxter: 4 and 17.
Fixed forward (aliases + three named observations). **The Logix run cannot be
backfilled** — the ingested tier is read-only once scanned and the package's
artefact bytes are not in `gs://digital-maturity-assessor-dmai-artefacts/`.
Recovering its stated grains needs a re-scan of the package.

### B4 · Logix has no peer benchmark, and it is a package property
`peer_table` is **0 rows** on Logix against **144** on Baxter (named peers:
Alliant CU, CEFCU, Consumers CU, GreenState CU, Lake Michigan CU, plus
Median/P25/P75, at CATEGORY grain). `peer_median` is null on all 705 cells,
and the payload says so in `peer_basis: cannot_estimate` with a ~900-character
`proxy_disclosure` that the overview now renders.

**Decision left open, deliberately.** The Surface Spec sanctions an
INFERENCE-labelled "peer proxy" at floor N=3. The only cohort available is
another client's peer panel, and borrowing it would put a benchmark on a client
dashboard that was never selected for that client. That is a judgement for the
owner, not a default. Ask before proxying.

### F4 · Tavily was unavailable this session
It requires authorisation through claude.ai connector settings. Clay, Explorium,
Exa and Indeed were all reachable and used.
