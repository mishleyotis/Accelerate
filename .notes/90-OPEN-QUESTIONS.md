# Open questions and blockers (2026-08-18)

## Blockers — need the user

### B1 · gcloud has no credentials in this container
`gcloud auth list` → "No credentialed accounts". No ADC file, no metadata
server, no service-account key. CLI installed (581.0.0), project
`digital-maturity-assessor` and region `us-central1` set.

Blocks: reading `dmai-mcp-path-token` from Secret Manager (so the plugin's
one required config stays unset and the connector's tools are unavailable);
minting the Google ID token the connector needs; `verify_deployed.py`;
`audit_promoted_client.py --api`; `INTAKE_STATUS` worker executions;
`gsutil` access to the catalogue bucket.

Options: a service-account key I can activate; a `gcloud auth login
--no-launch-browser` device flow the user completes; or accept local-only
operation and have the user run the GCP-touching steps.

### B2 · The deployed app cannot be logged into from here
`https://dmai-web-dukrne5v4a-uc.a.run.app/` → 302 to Google OAuth,
`Invalid IAP credentials: empty token`. Cloud Run integrated IAP, Google
sign-in, `@zennify.com` only. There is no password or token path —
`ALLOW_DEV_LOGIN` is local-compose only and explicitly never set in prod.

Proven instead: the identical auth path locally — `POST /api/signin` →
`{"ok":true,"role":"ADMIN"}`, page renders `authed:true`, non-zennify 403.

Options: the user logs in and confirms what they see; or, once B1 is
resolved, I verify serving content through `dmai-api` with an ID token
(which reaches the same promoted rows the web tier renders).

### B3 · The v7.0 catalogue cannot be seeded locally
`ccg_versions` and `ccg_subcaps` are both 0 rows. The loader
(`python -m ccg_loader --version v7.0 --dir <xlsx>`) needs the four pillar
workbooks, which live at
`gs://digital-maturity-assessor-catalogue-staging/v7.0/`. No `.xlsx` exists
in the checkout. Downstream of B1.

Consequence: 7 API tests error and 1 MCP test fails on the missing FK
target. Not a code defect.

## Findings — reported, not acted on

### F1 · `test_a_retained_pass_is_revalidated_and_disclosed` fails at HEAD
`apps/mcp/tests/test_promote.py`. Injects an off-vocabulary
`timeline.arc_shape` into a retained context page and asserts the promote
still succeeds with disclosure. Actual: `promoted: false`,
`retained_pages_fail_current_gates`, `context → CG-09 (severity: block)`.

The implementation refuses only on **blocking** gates and its own hint says
SG reasons still disclose-and-promote — which matches charter invariant 12.
The test injects CG-09, a blocking contract gate, and still expects a
promote. Reading: the implementation was narrowed (commit `6e008b1`) and the
test still encodes the older behaviour.

Never caught because the fixture calls `pytest.skip("no migrated local
database")` and CI's `python-tests` job runs with no Postgres service — so
this test has never executed in CI.

Claim label: **CONFIRMED** it fails at HEAD against a migrated local DB.
**HIGH** confidence the test, not the promote path, is the stale side —
falsifier I could not rule out: nobody has stated whether disclose-only was
meant to survive for contract gates too. Needs the owner's call.

Adjacent, worth deciding separately: should CI's `python-tests` job get a
Postgres service? Right now a whole class of DB-backed tests is skipped
there and only runs on a developer's machine.

### F2 · Duplicate skills between the plugin and account-synced skills
`~/.claude/skills/synced/` carries `dma-assessment`, `dma-first-call-deck`,
`dma-governance`, `dma-research` — the plugin ships the same four. The
plugin README says to remove duplicates so a session does not load two of
each. **`dma-surface-production` is NOT duplicated**, so the ingestion skill
is unaffected. Not acted on: these are account-synced, not the
`~/.claude/skills/dma-*` paths the README names, and removing them is the
user's call.

## Resolved during Phase 0

- **Which tree is live.** Root `apps/{web,api,mcp,worker}` is the deployed
  build. `apps/dma-insights/` is a 2026-07-16 snapshot of the prior app;
  root `CLAUDE.md` says reference only, do not extend or import. The task
  brief's "React frontend + Cloud Build" description matches the legacy
  tree, but Baxter is the reference client in **both**, and every live
  deployment artefact (`dmai-*`, `infra/deploy.sh`, the plugin's connector)
  belongs to the root build. Proceeding against the root build.
- **Target GCP project.** `digital-maturity-assessor`, `us-central1` —
  named in root `CLAUDE.md`, `infra/`, `scripts/verify_deployed.py` and the
  plugin README.
- **Where the four rulebook artifacts live.** See `10-ARCHITECTURE-MAP.md`.
