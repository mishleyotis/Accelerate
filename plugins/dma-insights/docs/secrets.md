# Where every secret is accessed

The rule everywhere: report whether a credential could be obtained, never
the credential. No token is printed, echoed, logged, or written by any
script in this plugin — `doctor.py` and `mcp_auth_headers.sh` both follow
it, and a change that breaks it fails review.

## 1. The capability-path token (`user_config.mcp_path_token`)

**What it is.** The URL path segment the connector is mounted under:
`{mcp_base_url}/mcp/{token}`. Since 2026-08-16 it is a capability only —
Cloud Run IAM (`roles/run.invoker`, `domain:zennify.com` plus the deployer
service account) is the identity layer, so the token alone opens nothing.

**Where it lives.**
- Source of record: Secret Manager, secret `dmai-mcp-path-token`, project
  `digital-maturity-assessor`.
- Server side: Cloud Run injects it into the `dmai-mcp` service as the
  `MCP_PATH_TOKEN` environment variable from `dmai-mcp-path-token:latest`,
  read once at process boot and baked into the route. Rotation therefore
  requires a new secret version AND a new service revision, then every
  consumer updates.
- Client side (this plugin): stored in the OS keychain by Claude Code when
  the user fills the `mcp_path_token` config field (`sensitive: true` in the
  manifest — never in settings.json). Interpolated into the connector URL by
  `.mcp.json` at connection time.
- CLI side (`scripts/dma_connector.py` in the repo): read from Secret
  Manager at call time (`gcloud secrets versions access latest
  --secret=dmai-mcp-path-token`), so the CLI follows a rotation
  automatically once the service revision is live.

**How a person retrieves it** (to fill the config field):

    gcloud secrets versions access latest \
      --secret=dmai-mcp-path-token --project=digital-maturity-assessor

**Rotation** (required after any exposure; the 2026-08-19 exposure is
rotated on the next connector deploy):
1. `python3 -c "import secrets; print(secrets.token_hex(16))" | gcloud secrets versions add dmai-mcp-path-token --data-file=-`
2. Redeploy `dmai-mcp` (`infra/deploy.sh`) so the new revision reads the new
   version. The old path 404s from that moment.
3. Every plugin user re-runs the retrieval command and updates the config
   field; the repo CLI needs nothing.

## 1b. The routine service-account key (`DMA_ROUTINE_SA_KEY`)

**What it is.** The JSON key of
`dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com` — the
identity fresh routine containers use, because they have no gcloud and no
other Google credential (measured 2026-08-19). Deliberately weak: exactly
`roles/run.invoker` on the `dmai-mcp` and `dmai-api` services and
`roles/secretmanager.secretAccessor` on `dmai-mcp-path-token`. It can call
the connector and read that one secret; it cannot deploy, read the
database, touch storage, or mint other identities.

**Where it lives.**
- Escrow: Secret Manager, secret `dmai-routine-sa-key`, same project.
- Runtime: the `DMA_ROUTINE_SA_KEY` environment variable in the CCR
  environment settings (claude.ai/code → environments → `Default - full
  network access`), set by hand once. `bootstrap_session.sh` writes it to
  `/root/.dma/sa.json` (0600) at container boot; `gcp_token.py` signs with
  it; `mcp_auth_headers.sh` and `doctor.py` fall back to it whenever gcloud
  is absent.
- NEVER in this repository — the repository is public.

**How a person retrieves it** (to fill the environment variable):

    gcloud secrets versions access latest \
      --secret=dmai-routine-sa-key --project=digital-maturity-assessor

**Rotation.**
1. `gcloud iam service-accounts keys create` a new key for `dmai-routine@`,
   add it as a new version of `dmai-routine-sa-key`, update the
   `DMA_ROUTINE_SA_KEY` environment variable from it.
2. `gcloud iam service-accounts keys delete` the old key id — from that
   moment the old JSON is dead everywhere, whatever still holds a copy.
3. Nothing else updates: the path token is fetched per boot, and the plugin
   store is rebuilt per boot.

## 2. The Google-signed ID token (per connection)

**What it is.** An OIDC identity token minted per connection by
`scripts/mcp_auth_headers.sh` via
`gcloud auth print-identity-token --audiences=<mcp_base_url>`; Cloud Run
enforces `roles/run.invoker` on that audience, so without this header every
call is 403 regardless of the path token.

**Failure posture (do not change).** On any failure the helper prints `{}`
and exits 0 — a helper that exits non-zero kills the whole MCP connection,
while a missing header degrades to a clean 403 the doctor can diagnose. The
helper also strips `CLOUDSDK_AUTH_ACCESS_TOKEN` before minting, because a
stale injected access token otherwise shadows the real identity.

**Audience trap.** The token's audience must be the *service URL*
(`DMA_MCP_HOST`, default the production `dmai-mcp` URL). A token minted for
the wrong audience 403s identically to a missing grant; `doctor.py`'s
audience check compares the two service names for exactly this reason.

## 3. What is deliberately NOT here

- No database password exists (IAM database auth throughout).
- No Anthropic key, no Clay key anywhere in this plugin or the app: Clay is
  a session-bound connector on the Claude side; the connector service holds
  no third-party API credentials.
- `repo_root` is a path, not a secret; it only lets `precheck_gates.py`
  import the connector's own gate modules.

## Preflight

`/doctor` (`scripts/doctor.py`) verifies both access points before a run:
gcloud present → active account → identity token mints for the configured
audience → unauthenticated probe is REFUSED by the service (a 404 means the
service is public — the 2026-08-16 lesson: four checks proved a credential
existed and none proved anything enforced it). The `deployed-app-auditor`
then proves reachability end to end by calling a real tool
(`list_pending_runs`), because a doctor that passes while the tools are
absent has checked the wrong thing.
