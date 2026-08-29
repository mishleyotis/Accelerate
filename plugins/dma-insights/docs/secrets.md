# Where every secret is accessed

The rule everywhere: report whether a credential could be obtained, never
the credential. No token is printed, echoed, logged, or written by any
script in this plugin — `doctor.py` and `mcp_auth_headers.sh` both follow
it, and a change that breaks it fails review.

## 1. The capability-path token (the `X-DMA-Path-Token` header)

**What it is.** The capability the connector is mounted under. Since
2026-08-16 it is a capability only — Cloud Run IAM (`roles/run.invoker`,
`domain:zennify.com` plus the deployer service account) is the identity
layer, so the token alone opens nothing. Since 2026-08-20 it travels as
the `X-DMA-Path-Token` HEADER on the static `{mcp_base_url}/mcp` URL
(owner: install must be automatic, all tools availed — a token embedded
in the URL made every install sit MCP-pending until a human pasted it,
and a URL is also what an access log or an xtrace prints). The
URL-segment form `/mcp/{token}` still works for back-compat.

**Where it lives.**
- Source of record: Secret Manager, secret `dmai-mcp-path-token`, project
  `digital-maturity-assessor`.
- Server side: Cloud Run injects it into the `dmai-mcp` service as the
  `MCP_PATH_TOKEN` environment variable from `dmai-mcp-path-token:latest`,
  read once at process boot and baked into the route. Rotation therefore
  requires a new secret version AND a new service revision, then every
  consumer updates.
- Client side (this plugin): no config field at all. At connection time
  `scripts/mcp_auth_headers.sh` obtains it by rung — `DMA_MCP_PATH_TOKEN`
  env override, the 600-mode cache file `/root/.dma/pathtok` that
  `bootstrap_session.sh` lands, else Secret Manager REST with an access
  token from the same identity rungs — and sends it as the header.
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

## 1b. The routine service-account key (`DMA_ROUTINE_SA_KEY_B64`)

**What it is.** The JSON key of
`dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com` — the
identity fresh routine containers use, because they have no gcloud and no
other Google credential (measured 2026-08-19).

**Its IAM is deliberately weak: exactly** `roles/run.invoker` on the
`dmai-mcp` and `dmai-api` services and `roles/secretmanager.secretAccessor`
on `dmai-mcp-path-token`. It cannot deploy, read the database, touch
storage, or mint other identities.

**Its DRIVE reach is not weak, and this section used to omit it.** Drive
access is granted by FOLDER SHARING, not by IAM, so no role above bounds it.
`scripts/drive_fetch.py` mints `https://www.googleapis.com/auth/drive` — the
FULL read-write scope, not `drive.readonly` — from this same key, and the
routine uses it to write back into client folders (push-bundle, push-memory,
push-ledger). So the real blast radius of this key is: call two Cloud Run
services, read one secret, **and read or write every Drive file or folder
shared with `dmai-routine@`.**

Two consequences worth stating where the key is described:

* Whoever shares a folder with this service account sets its reach. Sharing
  a parent folder shares everything under it, and nothing in this repository
  can see or limit that.
* Files it writes back carry internal-audience content and are outside every
  server-side redaction check — `get_report_bundle` takes no audience
  parameter, and the exclusion-boundary auditor compares two API projections,
  never a file on Drive.

**Where it lives.**
- Escrow: Secret Manager, secret `dmai-routine-sa-key`, same project.
- Runtime: the `DMA_ROUTINE_SA_KEY_B64` environment variable in the CCR
  environment settings (claude.ai/code → environments → `Default - full
  network access`), set by hand once. **The variable alone is sufficient** —
  `gcp_token.py`'s `load_key` reads it directly, so `mcp_auth_headers.sh`
  authenticates the connector at session start with nothing having to run
  beforehand. `bootstrap_session.sh` still writes `/root/.dma/sa.json`
  (0600) when it runs, and the file is preferred when present, but no part
  of the identity path depends on the bootstrap having run.

**Why the variable and not a file (measured 2026-08-20).** A plugin's MCP
servers register at session START. A firing that bootstrapped its key as a
step inside the session reached 14/14 on the doctor over direct HTTP and
still had none of the connector's 33 tools, because registration had
already happened and there is no supported MCP hot-reload mid-session. A
credential that must be fetched before the session can be authenticated
has to live somewhere the session already has at its first instruction —
which is the environment.
- NEVER in this repository — the repository is public.

**How a person retrieves it** (to fill the environment variable — the
settings field is .env format, one KEY=value per line, so the value is the
base64 of the key JSON):

    gcloud secrets versions access latest \
      --secret=dmai-routine-sa-key --project=digital-maturity-assessor \
      | base64 -w0

**Rotated 2026-08-20** after a routine ran `bootstrap_session.sh` under
`bash -x` and xtrace printed the key, an OAuth token and a signed JWT into
its transcript. Key `5afa7791…` was destroyed and `f01ea66a…` issued as
version 2; the capability path token went to version 3 in the same pass and
the old path was verified dead (404). The script now disables tracing
itself so the same report can never reproduce the leak.

**Rotated again 2026-08-20 (owner-requested clean slate).** Key `f01ea66a…`
destroyed, `e13dcc98…` issued and escrowed as version 3; versions 1 and 2
DISABLED so `latest` is the only accessible one. Note for anyone comparing
by eye: every service-account key's base64 opens with the same ~50
characters, because every key JSON begins with the same type declaration —
so two rotations LOOK identical at a glance. Verify a rotation by the key
id, never the prefix (and no, the prefix is not written out here: it
decodes to the very pattern scan_secrets.py hunts, and the fixture yields
to the gate):

    gcloud secrets versions access latest --secret=dmai-routine-sa-key \
      --project=digital-maturity-assessor \
      | python3 -c 'import sys,json;print(json.load(sys.stdin)["private_key_id"][:12])'

**Rotation.**
1. `gcloud iam service-accounts keys create` a new key for `dmai-routine@`,
   add it as a new version of `dmai-routine-sa-key`, update the
   `DMA_ROUTINE_SA_KEY_B64` environment variable from it (base64 -w0).
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
- No Drive restriction. This is an absence, not a safeguard: see §1b — the
  routine key holds the full `auth/drive` scope and its reach is whatever
  has been shared with it.

## Preflight

`/doctor` (`scripts/doctor.py`) verifies both access points before a run:
gcloud present → active account → identity token mints for the configured
audience → unauthenticated probe is REFUSED by the service (a 404 means the
service is public — the 2026-08-16 lesson: four checks proved a credential
existed and none proved anything enforced it). The `deployed-app-auditor`
then proves reachability end to end by calling a real tool
(`list_pending_runs`), because a doctor that passes while the tools are
absent has checked the wrong thing.
