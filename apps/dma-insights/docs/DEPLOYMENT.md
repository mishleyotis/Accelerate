# DMA Insights — Deployment Guide

This guide takes a fresh GCP project from zero to a fully running DMA
Insights deployment on Google Cloud Run, complete with Cloud SQL +
pgvector, Secret Manager, Cloud Scheduler triggers, OAuth, Clay
enrichment, and the DMA Bot loop wired end-to-end. Every command is
copy-paste-runnable; nothing is hand-waved.

---

## §0.0 — One-shot REDEPLOY (set parameters + pull all secrets, then deploy)

Redeploy the current commit to an **existing** project. This sets every
required parameter and pulls all secrets from Secret Manager, then runs the
race-free two-phase deploy (migrations run *before* any traffic shift; the OLD
revision keeps serving if any gate fails). Run from Cloud Shell, or any shell
with `gcloud` authenticated to the project, at the repo root.

```bash
# ── 0. Get the NEWEST deploy code FIRST (self-healing; inline on purpose) ──
# Run this from anywhere inside the repo, BEFORE anything else. It is inline
# (relies on no repo script) so it fixes a stale or wrong-branch checkout even
# when that checkout predates this very guide — the bde8329 incident, where a
# redeploy shipped an old image because HEAD lagged the deploy branch. It
# resets to the committed deploy-branch tip (a deploy ships COMMITTED code;
# commit/stash any local work first). Override the branch with DEPLOY_BRANCH=.
DEPLOY_BRANCH="${DEPLOY_BRANCH:-claude/deploy-zennify-cloud-run-AUdu6}"
git fetch origin "$DEPLOY_BRANCH"
git checkout -B "$DEPLOY_BRANCH" "origin/$DEPLOY_BRANCH"

# Works whether you are at the repo root or already inside apps/dma-insights —
# `git rev-parse --show-toplevel` resolves the repo root from any CWD. (A bare
# `cd apps/dma-insights` fails — "No such file or directory" — when you are
# already in it, and would silently skip the exports below.)
cd "$(git rev-parse --show-toplevel)/apps/dma-insights"

# ── 0b. Silence the benign "Regional Access Boundary … 404" noise ────
# Cloud Shell federated identities (f631843d16|you@…) have no Regional
# Access Boundary account, so gcloud's bundled google-auth logs
#   "Regional Access Boundary HTTP request failed after retries: …
#    404 … Account not found for email …"
# on ~every gcloud call (google-auth 2.51.0–2.55.0 log it at WARNING;
# 2.55.1 demoted it to DEBUG — non-fatal by design either way: auth
# falls back to a no-op trust boundary and the command proceeds). Every
# deploy script already sources this filter itself; sourcing it HERE
# also covers the interactive gcloud calls below. It drops EXACTLY that
# one line from stderr — real warnings/errors/exit codes untouched.
source infra/gcloud-noise-filter.sh

# ── 1. The ONLY parameters you must set ───────────────────────────────
export PROJECT_ID="digital-maturity-assessor"   # ← your GCP project id
export REGION="us-central1"                       # ← Cloud Run region
gcloud config set project "$PROJECT_ID" >/dev/null
# Resolve the image tag = the NEWEST deploy-branch tip (re-confirms step 0 +
# is the same resolver every deploy script uses). A leaked $SHA can never
# ship an old image; pin a specific pre-built image with SHA=… (it is then
# guarded against being older than the deploy-branch tip — DEPLOY_ALLOW_STALE=1
# to force a rollback).
unset SHA                                          # drop any leaked value
export SHA="$(bash infra/resolve-deploy-sha.sh)"   # newest deploy-branch tip
export _IMAGE_SHA="$SHA"

# ── 2. Pull ALL secrets from Secret Manager into the environment ──────
# Emits `export VAR='…'` for every present secret: DATABASE_URL[_SYNC],
# REDIS_URL, GOOGLE_OAUTH_CLIENT_SECRET, DMA_BOT_API_KEY, RAG_API_BEARER_KEY,
# CLAY_* (fail-closed/optional, ADR 0010). Fail-closed if PROJECT_ID is unset.
# (The OAuth *client ID* is PUBLIC — not a secret — so it is set below, not here.)
source <(bash infra/load-from-secret-manager.sh --emit-exports)

# ── 2b. OAuth web-client ID (PUBLIC) ──────────────────────────────────
# Baked into the frontend bundle AND used by the backend to verify the JWT
# `aud` claim, so BOTH must be the SAME value. The repo default works for the
# canonical project; export YOUR client id to override. It flows to the
# frontend build (build.sh → _GOOGLE_OAUTH_CLIENT_ID → VITE_…) and to the
# backend (terraform reads TF_VAR_google_oauth_client_id).
# IMPORTANT: add the deployed frontend URL to this client's "Authorized
# JavaScript origins" in the GCP console, or Google Identity Services refuses
# to render the sign-in button (the "client id won't set" symptom).
export GOOGLE_OAUTH_CLIENT_ID="${GOOGLE_OAUTH_CLIENT_ID:-306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com}"
export TF_VAR_google_oauth_client_id="$GOOGLE_OAUTH_CLIENT_ID"

# ── 3. Deploy (canonical, race-free two-phase) ────────────────────────
# preflight params/Cloud-SQL/Redis → build images @ $SHA → deploy backend
# --no-traffic → migrate on live DB → probe candidate /readyz → promote
# traffic → deploy+promote frontend → post-deploy data refresh.
bash infra/deploy-two-phase.sh
```

> **Redeploy checklist** (§26.5 has the full version): deploy a NEW SHA —
> never `--skip-build` after data/derive changes (the startup pack is baked
> at build time); verify the Cloud Build log carries the **regen ✓ +
> gemini ✓ + source_sha ✓** lines and frontend-image-smoke's
> `✓ startup pack is FRESH`; Phase 6/7 SHA gates are unchanged (they verify
> the *image*; the pack gates verify the *data inside it*); after promote,
> run `post-deploy-smoke.sh` with `FRONTEND_URL` + `SHA` exported so checks
> [8/9] (Gemini live) and [9/9] (pack freshness) assert for real.

Fail-closed prerequisites the script enforces (by design — see §0.6 + §22):
`PROJECT_ID`/`REGION` set; Cloud SQL `RUNNABLE` and its password matches the
secret (auto-heals on drift, §22.3); `REDIS_URL` is the TLS `rediss://` form
(plaintext = deploy blocker, §0.2.7); the image migration head matches the DB
(drift → `/readyz` 503 → promotion blocked, §7). **Set `ENV=prod` on the Cloud
Run services** (Terraform does this) or the production-readiness guard silently
no-ops — see §21.

---

## §0 — Zero-to-prod bootstrap (read this first)

Source of truth for every name, secret, and image referenced below:

| Artifact | Authoritative file |
|---|---|
| Cloud Run services + jobs | `infra/terraform/main.tf` |
| Cloud Run Job names | `locals.jobs` in `main.tf` lines 632-700 |
| Cloud Build pipeline | `infra/cloudbuild.yaml` |
| Container images | `infra/docker/{backend,frontend,worker}.Dockerfile` |
| Secret IDs | `local.backend_secrets` in `main.tf` line 1110+ |
| Required env vars | `backend/app/config.py::REQUIRED_FOR_PROD_BACKEND` |
| Migration head | `backend/alembic/versions/` (currently `062_recommendation_fit_fields`) |

If the docs below contradict any of the above, the source file wins.

### §0.1 — Required local tools (Cloud Shell)

Every command in §0 is designed to run from **GCP Cloud Shell**
(`https://shell.cloud.google.com`). Cloud Shell ships with the right
versions of every tool below; the snippet here only verifies them
in case a customised shell is in use.

```bash
# Run this verbatim in Cloud Shell — fail-soft (never exits the shell).
missing=()
for tool in gcloud terraform docker git jq openssl psql curl python3; do
  command -v "$tool" >/dev/null || missing+=("$tool")
done
node --version 2>/dev/null | grep -qE '^v(2[2-9]|[3-9][0-9])' \
  || missing+=("node>=22")
# pnpm via corepack (Cloud Shell pre-installs Node, not pnpm).
corepack enable 2>/dev/null
command -v pnpm >/dev/null || missing+=("pnpm (run: corepack enable)")
if (( ${#missing[@]} == 0 )); then
  echo "✓ All tools present."
else
  echo "✗ Missing: ${missing[*]}"
  echo "  In Cloud Shell most of these auto-install; in a custom shell"
  echo "  install them from the legacy table further down."
fi

# Anchor a workspace path so every subsequent `cd` is absolute.
# Cloud Shell sessions are ephemeral; $HOME survives across them but
# shell-level `export` does NOT — re-open the Cloud Shell tab and
# $REPO is gone. Every §0.x block below begins with a `${REPO:=...}`
# self-heal so you don't have to re-run §0.1 every time.
export REPO="$HOME/Accelerate"
[[ -d "$REPO" ]] || git clone https://github.com/dma-lang/Accelerate.git "$REPO"
cd "$REPO"
echo "✓ REPO=$REPO"
```

If `corepack enable` complains about being unable to write, re-run with:

```bash
sudo corepack enable          # Cloud Shell allows sudo without prompt
```

### §0.2 — Required real parameters (per-parameter setup + validation)

Every parameter below MUST be a real value sourced from the GCP
Console / OAuth screen / Drive / Ops Sheet. Placeholders, `latest`,
or git-branch names are explicitly rejected by `preflight-parameters.sh`.

> **Deferrable parameters (read this BEFORE you start exporting).**
> Two `DEFER` flags let you bootstrap a working deploy without every
> optional integration. Set the relevant flag in your shell BEFORE
> you paste the §0.2 env-writer block at the bottom of this section:
>
> | Flag | Defers | When to use |
> |---|---|---|
> | `export DMA_CLAY_DEFERRED=1` | `CLAY_WEBHOOK_URL` + `CLAY_WEBHOOK_SECRET` (§0.2.8-§0.2.9) | Your Clay tier doesn't support webhooks, OR you haven't issued the secret yet. Backend fails closed on empty Clay secret per ADR 0010 — enrichment is simply skipped. **`infra/deploy-two-phase.sh` auto-creates empty placeholder secrets for the two Clay env refs so `gcloud run services update` doesn't fail with `Secret … was not found`.** |
> | `export DEPLOY_MODE=minimal` | All live-mode params (backfill / RAG) | You only want the chrome + auth working; no live AE workflows. |
>
> The §0.2 env-writer block at the bottom **auto-detects deferred
> Clay** when both `CLAY_WEBHOOK_*` are unset and sets
> `DMA_CLAY_DEFERRED=1` for you. If the preflight ever FATALs with
> "Clay secrets unset AND DMA_CLAY_DEFERRED isn't '1'", it now prints
> the exact one-liner to fix it in place.
>
> If you've already issued every secret in Secret Manager, §0.2.0
> below pulls them into your shell automatically — you skip §0.2.4
> through §0.2.9 entirely and go straight to the env-writer.

#### §0.2.0 — Pre-flight: pull existing values from Secret Manager (FIRST STEP)

**This is the canonical first step of every Cloud Shell session.** It
reads the `latest` version of each known DMA Insights secret from
Google Secret Manager, exports it into the current shell, and (with
`--write-env`) persists it to `.deploy.parameters.env` so a fresh
Cloud Shell session can `source` it back without re-running.

The helper script `infra/load-from-secret-manager.sh` is fully
**read-only against Secret Manager** — it never writes. It is
re-runnable any number of times. It never exits with a status that
would kill an interactive shell.

```bash
# Self-heal $REPO if a fresh Cloud Shell tab lost it. Default matches
# what §0.1 sets. Operator's prompt shows `~/Accelerate` → this works.
: "${REPO:=$HOME/Accelerate}"
cd "$REPO/apps/dma-insights" || {
  echo "WARN: $REPO/apps/dma-insights not found — clone the repo (§0.1) then retry"
  echo "      (your prompt should now be in apps/dma-insights/ on success)"
}

# PROJECT_ID is the only required env var.
export PROJECT_ID=digital-maturity-assessor

# Step 1: human-readable probe — shows what's present / missing.
bash infra/load-from-secret-manager.sh

# Step 2: load every present secret into the CURRENT shell. This is
# the line you run after every fresh Cloud Shell open.
source <(bash infra/load-from-secret-manager.sh --emit-exports)

# Step 3 (recommended): also persist to .deploy.parameters.env so
# `set -a; source .deploy.parameters.env; set +a` re-loads everything
# without another Secret Manager round-trip.
bash infra/load-from-secret-manager.sh --write-env
chmod 600 .deploy.parameters.env
```

Expected output of step 1 when all 8 secrets are present:

```text
→ Probing Secret Manager (project=digital-maturity-assessor)…
  ✓ CLAY_WEBHOOK_SECRET            loaded from dma-insights-clay-webhook-secret      (64 chars, starts a1b2c3…)
  ✓ CLAY_WEBHOOK_URL               loaded from dma-insights-clay-webhook-url         (74 chars, starts https…)
  ✓ DATABASE_URL                   loaded from dma-insights-database-url             (191 chars, starts postg…)
  ✓ DATABASE_URL_SYNC              loaded from dma-insights-database-url-sync        (190 chars, starts postg…)
  ✓ DMA_BOT_API_KEY                loaded from dma-insights-bot-api-key              (64 chars, starts d4e5f6…)
  ✓ GOOGLE_OAUTH_CLIENT_SECRET     loaded from dma-insights-oauth-client-secret      (35 chars, starts GOCSP…)
  ✓ RAG_API_BEARER_KEY             loaded from dma-insights-rag-api-key              (64 chars, starts 9a8b7c…)
  ✓ REDIS_URL                      loaded from dma-insights-redis-url                (102 chars, starts redis…)

✓ All 8 secrets present.
  Run `source <(bash infra/load-from-secret-manager.sh --emit-exports)` to load them.
  Or  `bash infra/load-from-secret-manager.sh --write-env` to persist.
```

When secrets are missing, the script lists exactly which `✗ MISSING`
entries need to be created via §0.2.x → §0.5.1 — without exiting
your shell.

State branches:

| Outcome | What to do next |
|---|---|
| **All 8 secrets present** | After `source <(... --emit-exports)`, every secret env var is set. Skip §0.2.4-§0.2.9 + §0.2.7 entirely (don't re-roll bot keys / OAuth secrets — they'd invalidate the active credentials). Proceed to the non-secret sections §0.2.1-§0.2.3 + §0.2.10-§0.2.14. |
| **Some secrets present, some missing** | The script printed which. For each `✗ MISSING` line, follow the matching §0.2.x section to source a new value. Then re-run `bash infra/load-from-secret-manager.sh --write-env` to refresh the env file. |
| **All 8 missing (fresh project)** | Follow every §0.2.x section below; §0.5.1 creates all 8 secrets from scratch. |

**Re-opening a fresh Cloud Shell session?** After step 3 above ran
once, restore everything with this block (self-heals $REPO if a new
tab dropped it):

```bash
: "${REPO:=$HOME/Accelerate}" \
  && cd "$REPO/apps/dma-insights" \
  && export PROJECT_ID=digital-maturity-assessor \
  && set -a && source .deploy.parameters.env && set +a \
  && echo "✓ ${#REDIS_URL} chars in REDIS_URL — env restored"
```

Then proceed straight to whichever section you were on.

Create / verify the parameter file:

```bash
: "${REPO:=$HOME/Accelerate}"
cd "$REPO/apps/dma-insights"
[[ -f .deploy.parameters.env ]] || cp .env.example .deploy.parameters.env
chmod 600 .deploy.parameters.env   # rw owner only — contains secrets
```

Then fill in each still-missing variable. **For each parameter we
list (a) what it is, (b) how to obtain it in Cloud Shell, (c) the
expected format, (d) where it lands at runtime, (e) the validation
command. Validations are fail-soft — they print a warning instead of
exiting the shell, so you can paste an entire section verbatim.**

#### §0.2.1 — `PROJECT_ID`  (canonical GCP project ID)

- **What it is:** the GCP project where Cloud Run, Cloud SQL, Vertex,
  Secret Manager, and Pub/Sub all live. The canonical Zennify project
  is `digital-maturity-assessor`.
- **How to obtain (Cloud Shell):**
  ```bash
  gcloud projects list --format="table(projectId, name, lifecycleState)"
  # Pick the project whose name matches "DMA Insights" / "digital-maturity-assessor".
  ```
  Or in the Console: <https://console.cloud.google.com/projectselector2>.
  Set it:
  ```bash
  export PROJECT_ID=digital-maturity-assessor
  ```
- **Format:** lowercase letters / digits / hyphens; 6-30 chars; starts
  with a letter; ends with letter or digit.
- **Where it lands:** Terraform `var.project_id` + every gcloud
  invocation's `--project` flag + Cloud Run service env `GCP_PROJECT_ID`.
- **Validation:**
  ```bash
  gcloud projects describe "$PROJECT_ID" \
    --format='value(projectId, lifecycleState, projectNumber)'
  # Expect: "digital-maturity-assessor ACTIVE 0123456789".
  # If the projectNumber is empty or lifecycleState != ACTIVE, STOP.
  ```

#### §0.2.2 — `REGION`  (canonical Cloud Run + Cloud SQL region)

- **What it is:** the single GCP region where every Cloud Run service,
  Cloud Run Job, Cloud SQL instance, Redis instance, and Artifact
  Registry repo lives. Canonical: `us-central1` (matches Vertex
  Flash/Pro availability + the n8n bot's Drive ACL).
- **How to obtain (Cloud Shell):**
  ```bash
  gcloud run regions list --format='value(locationId)' | head
  # Pick a region that ALSO appears in:
  gcloud ai-platform locations list --format='value(locationId)' | head
  ```
- **Format:** `<continent>-<area><digit>` (e.g. `us-central1`).
- **Where it lands:** every `gcloud run` / `gcloud sql` / `gcloud
  redis` invocation's `--region` flag + Terraform `var.region`.
- **Validation:**
  ```bash
  export REGION=us-central1
  gcloud run regions list --filter="locationId=$REGION" \
    --format='value(locationId)' | grep -q "^$REGION$" \
    && echo "✓ REGION=$REGION is a Cloud Run region" \
    || echo "WARN: $REGION not in 'gcloud run regions list' — re-check spelling"
  ```

#### §0.2.3 — `ALLOWED_ORIGINS`  (CORS allow-list for the frontend)

- **What it is:** comma-separated list of HTTPS origins the backend's
  CORS middleware accepts. MUST include the exact public frontend URL.
- **How to obtain (Cloud Shell, after Cloud Run frontend exists):**
  ```bash
  gcloud run services describe dma-insights-frontend \
    --region "$REGION" --format='value(status.url)'
  # Use the printed URL.
  ```
  For the canonical production zennify.com domain:
  ```bash
  export ALLOWED_ORIGINS="https://dma-insights.zennify.com"
  ```
- **Format:** comma-separated `https://...` URLs. No trailing slash.
  Wildcard `*` is REJECTED in prod by `config.py::assert_production_ready`.
- **Where it lands:** Cloud Run backend env `ALLOWED_ORIGINS` (NOT a
  secret — it's a plain env var).
- **Validation:**
  ```bash
  if [[ "$ALLOWED_ORIGINS" == https://* ]] && [[ "$ALLOWED_ORIGINS" != "*" ]]; then
    echo "✓ ALLOWED_ORIGINS shape OK"
  else
    echo "WARN: ALLOWED_ORIGINS must start with https:// and NOT be '*' (got '$ALLOWED_ORIGINS')"
  fi
  ```

#### §0.2.4 — `GOOGLE_OAUTH_CLIENT_ID` + `GOOGLE_OAUTH_CLIENT_SECRET`

- **What it is:** the OAuth 2.0 Web client used by the Google Sign-In
  button on the login page.
- **How to obtain (Console UI is required; gcloud cannot create OAuth
  consent screen clients):**
  1. Go to <https://console.cloud.google.com/apis/credentials> and
     select the right `PROJECT_ID` in the top-bar dropdown.
  2. If the OAuth consent screen has not been configured, click
     "OAuth consent screen" → "External" (or "Internal" if the
     project is in a Workspace) and fill required fields. Add scopes
     `openid`, `email`, `profile`.
  3. Back on "Credentials" → "Create credentials" → "OAuth client ID"
     → Application type "Web application".
  4. **Authorised redirect URIs** must EXACTLY include:
     ```
     https://dma-insights.zennify.com/api/v1/auth/google/callback
     https://<staging-frontend>.run.app/api/v1/auth/google/callback
     ```
     (Add a localhost entry for local dev if needed.)
  5. After creation, the modal displays `client_id` (ends in
     `.apps.googleusercontent.com`) and `client_secret`. Copy both.
- **Cloud Shell setup:**
  ```bash
  export GOOGLE_OAUTH_CLIENT_ID="123456789012-abc...xyz.apps.googleusercontent.com"
  export GOOGLE_OAUTH_CLIENT_SECRET="GOCSPX-..."   # 24-byte secret
  ```
- **Format:** `client_id` ends in `.apps.googleusercontent.com`;
  `client_secret` starts with `GOCSPX-`.
- **Where they land:** `client_id` is a Cloud Run backend env var
  (not a secret — it's public); `client_secret` lives in Secret
  Manager as `dma-insights-oauth-client-secret`.
- **Validation:**
  ```bash
  if [[ "$GOOGLE_OAUTH_CLIENT_ID" == *.apps.googleusercontent.com ]] \
     && [[ "$GOOGLE_OAUTH_CLIENT_SECRET" == GOCSPX-* ]]; then
    echo "✓ OAuth credentials shape OK"
  else
    echo "WARN: OAuth shape mismatch — client_id must end in"
    echo "      .apps.googleusercontent.com; client_secret starts with GOCSPX-"
  fi
  # Verify the client_id resolves at Google's discovery endpoint:
  curl -sf "https://accounts.google.com/.well-known/openid-configuration" >/dev/null \
    && echo "✓ Google OIDC discovery reachable" \
    || echo "WARN: cannot reach Google OIDC discovery (Cloud Shell egress?)"
  ```

#### §0.2.5 — `DMA_BOT_API_KEY`

- **What it is:** the long-lived bearer the n8n / Claude-project bot
  pipeline uses to POST DMA package payloads to `/api/v1/ingest/assessment`
  and `/api/v1/ingest/package`. Per ADR 0012, also accepted via
  Authorization header for /ingest/assessment.
- **How to obtain:** generate a fresh 32-byte URL-safe random:
  ```bash
  export DMA_BOT_API_KEY="$(openssl rand -hex 32)"
  echo "Generated DMA_BOT_API_KEY (give this to the n8n bot operator)"
  echo "  → $DMA_BOT_API_KEY"
  ```
  Share with the bot operator out-of-band (Slack DM / 1Password). The
  bot operator updates the n8n credential vault; this app never sees
  the value again after deploy.
- **Format:** 64-hex-char string (no quotes / no whitespace).
- **Where it lands:** Secret Manager as `dma-insights-bot-api-key`;
  Cloud Run backend mounts it as env var via Terraform
  `local.backend_secrets`.
- **Validation:**
  ```bash
  [[ "${#DMA_BOT_API_KEY}" -ge 48 ]] \
    && echo "✓ DMA_BOT_API_KEY length OK (${#DMA_BOT_API_KEY} chars)" \
    || echo "WARN: DMA_BOT_API_KEY < 48 chars — re-roll with openssl rand -hex 32"
  ```

#### §0.2.6 — `RAG_API_BEARER_KEY`

- **What it is:** the bearer the external Claude-project queries
  POST to `/api/v1/rag/answer` with for retrieval-grounded answers
  outside the browser session.
- **How to obtain:** generate fresh 32-byte URL-safe random:
  ```bash
  export RAG_API_BEARER_KEY="$(openssl rand -hex 32)"
  echo "Generated RAG_API_BEARER_KEY (paste into the Claude project's secret store)"
  echo "  → $RAG_API_BEARER_KEY"
  ```
- **Format:** 64-hex-char.
- **Where it lands:** Secret Manager as `dma-insights-rag-api-key`;
  Cloud Run backend mounts as env var.
- **Validation:**
  ```bash
  [[ "${#RAG_API_BEARER_KEY}" -ge 48 ]] \
    && echo "✓ RAG_API_BEARER_KEY length OK" \
    || echo "WARN: RAG_API_BEARER_KEY < 48 chars — re-roll with openssl rand -hex 32"
  ```

#### §0.2.7 — `REDIS_URL`  (managed Redis — Upstash recommended, Memorystore optional)

- **What it is:** the connection URL for ephemeral per-user state:
  daily rate limits (`rl:{surface}:{user_id}:{ymd}`), RAG L1 cache,
  chat session resume tokens. The backend connects with `redis-py` so
  ANY URL `redis-py` understands works (Upstash, Memorystore, self-
  managed, ElastiCache via private peering, etc.).
- **Scheme matters for TLS:**
  - `redis://`  → plaintext TCP (Memorystore basic tier; self-managed)
  - `rediss://` → TLS (Upstash, ElastiCache, Memorystore standard tier
                  with `--transit-encryption-mode SERVER_AUTHENTICATION`)
  Use `rediss://` whenever the provider supports it — Cloud Run's
  egress to the public internet is over TLS by default and Upstash
  rejects plaintext on its TLS ports.

**Recommended path: Upstash Redis (no VPC required).**

Upstash is a serverless Redis-as-a-service. It works from Cloud Run
WITHOUT a VPC connector — connections go over the public internet on
TLS. This is the simplest setup for the first deploy.

1. Sign up at <https://upstash.com/> with the Zennify Google account.
2. **Create database** → name `dma-insights` → region closest to
   `$REGION` (e.g. `us-east-1` is fine even when GCP is `us-central1`;
   latency cost is ~30ms which is negligible against the Vertex call
   it gates).
3. From the database page, copy the **"Endpoint URL with password"**
   field — it looks like:
   ```
   rediss://default:<PASSWORD>@<DB_NAME>-<NN>.upstash.io:6379
   ```
   *(Upstash also shows a `redis://` plaintext URL — DO NOT use it.
   Use the `rediss://` TLS variant.)*

Cloud Shell setup:

```bash
# Replace with the rediss:// URL you copied from Upstash.
export REDIS_URL="rediss://default:AaPiAAIg...@capable-weevil-41954.upstash.io:6379"
```

If you already pasted the URL into Secret Manager (or the §0.2.0
auto-detect found it), nothing more to do — proceed to validation.

**Alternative: Cloud Memorystore for Redis (requires VPC + PSA setup).**

Use this path ONLY if your security policy forbids egress to
non-Google managed services. Memorystore needs **Private Service
Access** enabled on the project's VPC BEFORE the create call works —
this is the `FAILED_PRECONDITION: Google private service access is
not enabled` error.

```bash
# One command — idempotent + self-healing + polls each long-running
# step to convergence. Replaces the 5-step paste block that previously
# lived here (2026-05-30 operator hit it: empty $REGION caused the
# Redis create to fail, the follow-up describe also failed, REDIS_HOST
# came back empty, and REDIS_URL became `redis://:6379/0`).
PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/setup-memorystore.sh"

# Pick up the REDIS_URL the script wrote (export inside a subshell
# doesn't reach the caller — the script saves to a sourceable file).
source ~/.dma-redis-url
echo "$REDIS_URL"   # sanity check
```

What the script does step-by-step (every step is idempotent — safe to
re-run on failure):
1. Validates `$PROJECT_ID` + `$REGION` (fail-fast if missing).
2. Reserves the `/16` PSA range; skipped if it already exists.
3. Connects the VPC peering to `servicenetworking.googleapis.com`;
   skipped if already peered.
4. **Polls** until the peering is visible (replaces the fragile
   "Wait ~30s for the peering to converge" sleep that didn't actually
   wait).
5. Creates `dma-insights-redis` (basic tier, 1 GB, redis_7_0,
   `PRIVATE_SERVICE_ACCESS`); skipped if the instance already exists.
6. **Polls** until the instance reports `state=READY` (up to 10 min).
7. Reads `host` + `port` from the descriptor (no more empty-host bug).
8. Writes `export REDIS_URL=…` to `~/.dma-redis-url` (mode 0600) so the
   operator can `source` it after the script exits.

Note: Memorystore basic tier ships plaintext (`redis://`). For
`rediss://` on Memorystore you need standard tier with
`--transit-encryption-mode SERVER_AUTHENTICATION`, which also
returns a CA cert the client must trust — much heavier setup. Stick
with Upstash for the first deploy.

- **Format:** `redis://[user][:password]@host:port[/db]` OR
  `rediss://...`. Preflight accepts both schemes; rejects anything
  else.
- **Where it lands:** Secret Manager as `dma-insights-redis-url`.
  Cloud Run backend mounts as env. **No VPC connector needed for
  Upstash;** Memorystore DOES require a VPC connector (Terraform
  creates `dma-insights-vpc-connector` automatically when
  `var.use_memorystore=true`).
- **Validation:** one command. The wrapper script auto-classifies
  the backend (Upstash vs Memorystore vs unknown) and gives you a
  clear PASS / WARN-EXPECTED / FAIL verdict — so a Cloud Shell probe
  failure on a Memorystore URL doesn't look like a deploy-blocker
  (it isn't; Cloud Run reaches Memorystore via the VPC connector).

  Canonical form — pulls the live URL from Secret Manager (`dma-insights-
  redis-url`). This is the SAFE form to paste; works from any directory
  inside the repo. **Do not paste a literal `REDIS_URL='rediss://...'`
  before this command** — operators kept accidentally pasting the
  placeholder `...` as if it were a real value (2026-05-31), tripping
  the new `PLACEHOLDER_URL` verdict.

  ```bash
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-redis.sh" --from-secret
  ```

  Testing a fresh URL *before* writing it to Secret Manager? Export it
  in your shell first, then run without `--from-secret`:

  ```bash
  export REDIS_URL='rediss://default:THE_REAL_TOKEN_FROM_UPSTASH@your-host-12345.upstash.io:6379'
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-redis.sh"
  ```

  Exit codes:
  - `0` — OK (Upstash reachable, or Memorystore correctly classified
    as VPC-internal and unreachable from Cloud Shell)
  - `1` — UPSTASH_FATAL: re-check the URL (deploy blocker)
  - `2` — SCHEME_INVALID: URL must start with `redis://` or `rediss://`

  > Why a script, not an inline snippet: the previous version of this
  > validation pasted a Python heredoc into the shell. A partial copy
  > that dropped the heredoc-terminator left Cloud Shell stuck at the
  > `>` (continuation) prompt indefinitely. The script eliminates that
  > footgun and adds backend-classification logic so the WARN messages
  > are actionable per backend type.

#### §0.2.8-§0.2.9 — `CLAY_WEBHOOK_URL` + `CLAY_WEBHOOK_SECRET`  (DEFERRABLE)

> **Defer if your Clay tier doesn't support webhooks.** Run this
> ONE line in your Cloud Shell **before** the §0.2 env-writer block
> below — that's all it takes:
>
> ```bash
> export DMA_CLAY_DEFERRED=1
> ```
>
> The §0.2 env-writer also auto-detects this case: if you leave BOTH
> `CLAY_WEBHOOK_URL` and `CLAY_WEBHOOK_SECRET` unset, the env-writer
> sets `DMA_CLAY_DEFERRED=1` for you and announces it (no preflight
> FATAL). The backend's Clay client fail-closes when the secret is
> empty (ADR 0010), so outbound enrichment is simply skipped until
> you add the URL + secret + `unset DMA_CLAY_DEFERRED`.
>
> If you already hit the FATAL once (the preflight says "2 required
> parameter(s) missing" listing the two Clay vars), this one-liner
> fixes it in-place without re-running the env-writer:
>
> ```bash
> export DMA_CLAY_DEFERRED=1
> echo 'DMA_CLAY_DEFERRED=1' >> .deploy.parameters.env
> bash infra/preflight-parameters.sh
> ```

#### §0.2.8 — `CLAY_WEBHOOK_URL`  (outbound firmographics enrichment)

- **What it is:** per ADR 0010, when an entity is ingested the backend
  POSTs an enrichment request to a Clay table webhook URL; Clay runs
  its enrichment chain and posts the result back to
  `/api/v1/clay/webhook` HMAC-signed with `CLAY_WEBHOOK_SECRET`.
- **How to obtain:**
  1. Log in to Clay (<https://app.clay.com/>) → the "DMA Insights
     Firmographics" table.
  2. "Table settings" → "Webhooks" → "Inbound webhook" → "Copy URL".
- **Cloud Shell setup:**
  ```bash
  export CLAY_WEBHOOK_URL="https://api.clay.com/v1/webhooks/<your-table-id>/<your-hash>"
  ```
- **Format:** must start with `https://`.
- **Where it lands:** Secret Manager as `dma-insights-clay-webhook-url`.
- **Validation:**
  ```bash
  [[ "$CLAY_WEBHOOK_URL" == https://* ]] \
    && curl -sfI "$CLAY_WEBHOOK_URL" >/dev/null \
    && echo "✓ CLAY_WEBHOOK_URL https + reachable" \
    || echo "WARN: CLAY_WEBHOOK_URL not reachable from Cloud Shell (Clay may reject HEAD; proceed)"
  ```

#### §0.2.9 — `CLAY_WEBHOOK_SECRET`  (HMAC for Clay → backend callback)

- **What it is:** shared HMAC secret. Backend rejects inbound Clay
  webhook callbacks whose `X-Clay-Signature` HMAC doesn't match.
- **How to obtain:**
  ```bash
  export CLAY_WEBHOOK_SECRET="$(openssl rand -hex 32)"
  ```
  Paste it into Clay's outbound webhook signing-secret field for the
  same table.
- **Format:** any non-empty string; 32-byte hex recommended.
- **Where it lands:** Secret Manager as `dma-insights-clay-webhook-secret`.
- **Validation:**
  ```bash
  if [[ -n "$CLAY_WEBHOOK_SECRET" ]] && [[ "${#CLAY_WEBHOOK_SECRET}" -ge 32 ]]; then
    echo "✓ CLAY_WEBHOOK_SECRET set (${#CLAY_WEBHOOK_SECRET} chars)"
  else
    echo "WARN: CLAY_WEBHOOK_SECRET missing or < 32 chars"
  fi
  ```

#### §0.2.10 — `DRIVE_ROOT_FOLDER_ID`  (DMA Drive root for ingest)

> **If §0.2.10 + §0.2.11 returned `403 — operator ADC lacks scope`,** the
> operator's `gcloud auth application-default login` defaults to
> `cloud-platform` + `userinfo` only — neither covers Drive/Sheets, so
> the probes 403. The fix is NOT to re-run `gcloud auth application-
> default login --scopes=...drive` (Workspace orgs typically block
> sensitive-scope re-auth with the "This app is blocked" page). Use the
> **worker SA impersonation token** instead — it's first-party, bypasses
> the consent screen, AND is what the production worker actually uses.
> Paste this once at the top of your shell, then re-run the probes:
>
> ```bash
> # Resolve PROJECT_ID + the project's default compute SA (the worker SA).
> : "${PROJECT_ID:=$(gcloud config get-value project 2>/dev/null)}"
> PROJ_NUM=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
> export WORKER_SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
> echo "WORKER_SA=$WORKER_SA"
>
> # The 'serviceAccountTokenCreator' role on the WORKER_SA is required
> # for the impersonation. Self-grant if you're an Owner:
> gcloud iam service-accounts add-iam-policy-binding "$WORKER_SA" \
>   --member="user:$(gcloud config get-value account)" \
>   --role="roles/iam.serviceAccountTokenCreator" \
>   --condition=None >/dev/null 2>&1 || true
> ```
>
> After that, both the §0.2.10 + §0.2.11 probes below will
> auto-impersonate the WORKER_SA with the right scopes and the 403 will
> resolve **provided** the Drive folder + Ops Sheet are shared with
> `$WORKER_SA` as Viewer. The 403 message now prints both fix paths
> with exact commands.

- **What it is:** the Google Drive folder that contains the per-entity
  `<Entity> - DMA` sub-folders the n8n bot drops into. The Drive
  crawler + `historical_backfill` job iterate this folder.
- **How to obtain:**
  1. Open the Drive folder in the browser:
     <https://drive.google.com/drive/folders/1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P>.
  2. The folder ID is the trailing path segment in the URL.
- **Cloud Shell setup:**
  ```bash
  export DRIVE_ROOT_FOLDER_ID="1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P"
  ```
- **Format:** ~33-char base64-ish string (no slashes / no spaces).
- **Where it lands:** Terraform `var.drive_root_folder_id` →
  passed into the `historical_backfill` Cloud Run Job + `drive_crawler`
  worker as env var. NOT in Secret Manager (it's not a secret).
- **Validation:** one command — replaces the 70+ line Drive probe block
  that was a Cloud Shell paste hazard (multi-line `case/esac`, nested-
  quote escapes, env-var interdependencies). Same hazard class as the
  Sheets probe; same script-based fix.

  ```bash
  # Resolves WORKER_SA from $PROJECT_ID, impersonates the SA with the
  # Drive scope, then probes. Idempotent. Works from any directory
  # inside the repo.
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-drive-folder.sh"
  ```

  Exit codes:
  - `0` — OK (folder readable as the worker SA, proceed to deploy)
  - `1` — DRIVE_403: the worker SA hasn't been shared on the folder.
    The script prints the exact folder URL + SA email + role to pick.
    **One-click fix** on Google's side; no code changes needed. Note
    that if the folder lives in a **Shared Drive**, sharing the folder
    isn't enough — add the SA as a member of the Shared Drive itself.
  - `2` — DRIVE_404: folder ID wrong, OR Shared-Drive membership missing
  - `3` — NO_TOKEN: your operator account lacks
    `roles/iam.serviceAccountTokenCreator` on the worker SA. The
    script prints the exact IAM-binding command.
  - `4` — PROJECT_ID / DRIVE_ROOT_FOLDER_ID missing

#### §0.2.11 — `OPS_SHEET_ID`  (canonical AE-assignment Ops Sheet)

- **What it is:** Google Sheet the `sheet_poller` worker reads to map
  entities → AE owners (per ADR 0002 hybrid assignment).
- **How to obtain:**
  1. Open the canonical Ops Sheet:
     <https://docs.google.com/spreadsheets/d/1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8>.
  2. ID is the path segment after `/spreadsheets/d/`.
- **Cloud Shell setup:**
  ```bash
  export OPS_SHEET_ID="1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8"
  ```
- **Format:** Sheet ID, 44 chars.
- **Where it lands:** Terraform `var.ops_sheet_id` → passed to
  `sheet_poller` Cloud Run Job as env var.
- **Validation:** one command — replaces the 50-line probe block that
  was a Cloud Shell paste hazard (multi-line `case/esac`, nested-quote
  escapes, and inline error messages the operator's shell mangled on
  paste; 2026-05-30 operator hit exactly that).

  ```bash
  # Works from any directory inside the repo. Resolves WORKER_SA from
  # $PROJECT_ID, impersonates the SA with the Sheets scope, then probes.
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-ops-sheet.sh"
  ```

  Exit codes:
  - `0` — OK (sheet readable as the worker SA, proceed to deploy)
  - `1` — SHEETS_403: the worker SA hasn't been shared on the sheet
    yet. The script prints the exact share URL + email to paste
    + role to pick. **This is a one-click fix on Google's side** —
    no code changes needed, just go to the printed URL and Share →
    Viewer → paste the email → uncheck Notify → Share.
  - `2` — SHEETS_404: sheet ID wrong / sheet doesn't exist
  - `3` — NO_TOKEN: your operator account lacks
    `roles/iam.serviceAccountTokenCreator` on the worker SA. The
    script prints the `gcloud iam service-accounts add-iam-policy-
    binding` command to fix it.
  - `4` — PROJECT_ID / OPS_SHEET_ID missing

#### §0.2.12 — `VERTEX_PROJECT_ID` + `VERTEX_LOCATION`

- **What they are:** project + region for Vertex AI calls (Gemini
  Flash, Gemini Pro, text-embedding-004). Almost always the same as
  `PROJECT_ID` + `REGION`.
- **Cloud Shell setup:**
  ```bash
  export VERTEX_PROJECT_ID="$PROJECT_ID"
  export VERTEX_LOCATION="$REGION"
  ```
- **Format:** project_id pattern + region pattern.
- **Where they land:** Cloud Run backend + worker env vars (NOT secrets).
- **Validation:**
  ```bash
  # Self-heal env vars in case this block is pasted standalone.
  # Falls back to PROJECT_ID + REGION (set in §0.2.1 + §0.2.2) when
  # the §0.2.12 "Cloud Shell setup" block above hasn't run yet.
  : "${PROJECT_ID:=digital-maturity-assessor}"
  : "${REGION:=us-central1}"
  : "${VERTEX_PROJECT_ID:=$PROJECT_ID}"
  : "${VERTEX_LOCATION:=$REGION}"

  # 1) Shape check — VERTEX_LOCATION must match the Cloud Run region
  # pattern. We DO NOT use `gcloud ai-platform locations list` (legacy
  # command set; crashes when the SDK lacks the ai-platform component)
  # or `gcloud ai locations list` (requires aiplatform.googleapis.com
  # enabled AND prints a confusing global region too). The functional
  # test is the live publishers/models call below.
  [[ "$VERTEX_LOCATION" =~ ^[a-z]+-[a-z0-9]+[1-9]$ ]] \
    && echo "✓ VERTEX_LOCATION='$VERTEX_LOCATION' shape OK" \
    || echo "WARN: VERTEX_LOCATION '$VERTEX_LOCATION' doesn't match <continent>-<area><digit>"

  # 2) Live probe (fail-soft) — try `:generateContent` on each known
  # Gemini model ID. The list endpoint
  # (.../publishers/google/models?pageSize=N) returns a static HTML 404
  # at the regional sub-domain (the publishers metadata lives at the
  # GLOBAL `aiplatform.googleapis.com` host, not the regional one).
  # The REGIONAL endpoint only serves the actual generateContent path,
  # so the canonical probe is the same call shape the backend uses at
  # runtime — POST with a 1-token prompt.
  #
  # Probes a candidate list in priority order; the first model that
  # accepts (HTTP 200 or 429 quota) is exported as the recommended
  # VERTEX_FLASH_MODEL / VERTEX_PRO_MODEL.
  TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null)
  if [[ -z "$TOKEN" ]]; then
    echo "WARN: no ADC token — run \`gcloud auth application-default login\`"
  elif [[ -z "$VERTEX_LOCATION" || -z "$VERTEX_PROJECT_ID" ]]; then
    echo "WARN: VERTEX_LOCATION or VERTEX_PROJECT_ID still empty — re-run §0.2.1+§0.2.12"
  else
    echo "→ Probing Gemini models in $VERTEX_LOCATION (one POST per model)…"
    working_flash=""; working_pro=""
    # Priority order — 2.5 family is what Zennify's canonical project
    # has access to as of 2026-05-29. Older variants are kept as
    # fallbacks for projects that pinned them earlier.
    for model in \
        gemini-2.5-flash \
        gemini-2.0-flash-001 \
        gemini-1.5-flash-002 \
        gemini-1.5-flash \
        gemini-2.5-pro \
        gemini-1.5-pro-002 \
        gemini-1.5-pro; do
      url="https://${VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/${VERTEX_PROJECT_ID}/locations/${VERTEX_LOCATION}/publishers/google/models/${model}:generateContent"
      code=$(curl -s -o /dev/null -w '%{http_code}' \
        -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"contents":[{"role":"user","parts":[{"text":"hi"}]}],"generationConfig":{"maxOutputTokens":1}}' \
        "$url" 2>/dev/null)
      case "$code" in
        200|429)
          tag="OK"; [[ "$code" == "429" ]] && tag="OK (quota — path works)"
          echo "  ✓ $model — HTTP $code ($tag)"
          [[ "$model" == *flash* && -z "$working_flash" ]] && working_flash="$model"
          [[ "$model" == *pro*   && -z "$working_pro"   ]] && working_pro="$model"
          ;;
        403)
          echo "  ✗ $model — HTTP 403 (ADC lacks roles/aiplatform.user; see §0.5.2)"
          break
          ;;
        404) echo "  ✗ $model — HTTP 404 (not enabled in $VERTEX_LOCATION)" ;;
        000) echo "  ✗ $model — HTTP 000 (DNS / API enablement propagating)" ;;
        *)   echo "  ✗ $model — HTTP $code" ;;
      esac
    done
    echo
    if [[ -n "$working_flash" ]]; then
      echo "✓ Recommended: export VERTEX_FLASH_MODEL=$working_flash"
      export VERTEX_FLASH_MODEL="$working_flash"
    else
      echo "WARN: no flash model accepted — request access at https://console.cloud.google.com/vertex-ai/model-garden"
    fi
    if [[ -n "$working_pro" ]]; then
      echo "✓ Recommended: export VERTEX_PRO_MODEL=$working_pro"
      export VERTEX_PRO_MODEL="$working_pro"
    else
      echo "WARN: no pro model accepted — fall back to flash for both surfaces"
    fi

    # Persist the working models to .deploy.parameters.env so a fresh
    # Cloud Shell session restores them automatically.
    if [[ -n "$working_flash" || -n "$working_pro" ]] \
       && [[ -f .deploy.parameters.env ]]; then
      # Drop any prior VERTEX_*_MODEL lines, append fresh ones.
      tmp=$(mktemp)
      grep -vE '^(VERTEX_FLASH_MODEL|VERTEX_PRO_MODEL)=' \
        .deploy.parameters.env > "$tmp" || true
      [[ -n "$working_flash" ]] && echo "VERTEX_FLASH_MODEL=$working_flash" >> "$tmp"
      [[ -n "$working_pro"   ]] && echo "VERTEX_PRO_MODEL=$working_pro"   >> "$tmp"
      mv "$tmp" .deploy.parameters.env
      chmod 600 .deploy.parameters.env
      echo "✓ Persisted to .deploy.parameters.env"
    fi
  fi
  ```

#### §0.2.13 — `VERTEX_FLASH_MODEL`, `VERTEX_PRO_MODEL`, `VERTEX_EMBEDDING_MODEL`

- **What they are:** specific Gemini model IDs the backend calls.
  Defaults are baked into `config.py` (gemini-2.5-flash + gemini-2.5-pro
  as of 2026-05-29 — verified against the canonical Zennify project
  via the discovery loop below). Pin via env vars when targeting a
  project with different Model Garden access.
- **Cloud Shell setup:**
  ```bash
  # Verified working on digital-maturity-assessor / us-central1 (the
  # canonical Zennify project). Other projects may need different IDs —
  # the discovery loop in §0.2.13 validation exports the right ones.
  export VERTEX_FLASH_MODEL="gemini-2.5-flash"
  export VERTEX_PRO_MODEL="gemini-2.5-pro"
  export VERTEX_EMBEDDING_MODEL="text-embedding-004"
  ```
- **Format:** valid published Gemini model IDs.
- **Where they land:** Cloud Run backend env (NOT secrets).
- **Validation:**
  ```bash
  # Self-heal env in case the section is pasted standalone.
  : "${PROJECT_ID:=digital-maturity-assessor}"
  : "${REGION:=us-central1}"
  : "${VERTEX_PROJECT_ID:=$PROJECT_ID}"
  : "${VERTEX_LOCATION:=$REGION}"
  : "${VERTEX_FLASH_MODEL:=gemini-2.5-flash}"
  : "${VERTEX_PRO_MODEL:=gemini-2.5-pro}"
  : "${VERTEX_EMBEDDING_MODEL:=text-embedding-004}"

  # The plain `GET .../publishers/google/models/<m>` returns Google's
  # static HTML 404 from the regional sub-domain because publisher
  # metadata lives at the GLOBAL host, not the regional one. The
  # regional endpoint only serves the actual `:generateContent` /
  # `:predict` call shapes the backend uses at runtime — those are
  # the canonical probes below.
  TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null)
  if [[ -z "$TOKEN" ]]; then
    echo "WARN: no ADC token — run \`gcloud auth application-default login\`"
  else
    # Text models — POST :generateContent with 1-token max output.
    for m in "$VERTEX_FLASH_MODEL" "$VERTEX_PRO_MODEL"; do
      url="https://${VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/${VERTEX_PROJECT_ID}/locations/${VERTEX_LOCATION}/publishers/google/models/${m}:generateContent"
      code=$(curl -s -o /dev/null -w '%{http_code}' \
        -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
        -d '{"contents":[{"role":"user","parts":[{"text":"hi"}]}],"generationConfig":{"maxOutputTokens":1}}' \
        "$url")
      case "$code" in
        200|429) echo "✓ $m reachable (HTTP $code)" ;;
        403)     echo "✗ $m HTTP 403 — ADC lacks roles/aiplatform.user (see §0.5.2)" ;;
        404)     echo "✗ $m HTTP 404 — not enabled in $VERTEX_LOCATION; re-run §0.2.12 discovery loop" ;;
        *)       echo "WARN: $m HTTP $code" ;;
      esac
    done

    # Embedding model — POST :predict with a tiny instance payload.
    embed_url="https://${VERTEX_LOCATION}-aiplatform.googleapis.com/v1/projects/${VERTEX_PROJECT_ID}/locations/${VERTEX_LOCATION}/publishers/google/models/${VERTEX_EMBEDDING_MODEL}:predict"
    code=$(curl -s -o /dev/null -w '%{http_code}' \
      -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
      -d '{"instances":[{"content":"hi"}]}' \
      "$embed_url")
    case "$code" in
      200|429) echo "✓ $VERTEX_EMBEDDING_MODEL reachable (HTTP $code)" ;;
      403)     echo "✗ $VERTEX_EMBEDDING_MODEL HTTP 403 — IAM (see §0.5.2)" ;;
      404)     echo "✗ $VERTEX_EMBEDDING_MODEL HTTP 404 — try text-embedding-005 OR textembedding-gecko-multilingual" ;;
      *)       echo "WARN: $VERTEX_EMBEDDING_MODEL HTTP $code" ;;
    esac
  fi
  ```

#### §0.2.14 — `CATALOGUE_DEFAULT_VERSION` + `DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION`

- **What they are:** per ADR 0014, current production catalogue and
  the v5 default used for historical Drive backfills.
  - `CATALOGUE_DEFAULT_VERSION`: current production (v7.0).
  - `DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION`: legacy default for
    Drive folders whose `run_manifest.json` has no `rubric_version`
    (v5.0).
- **Cloud Shell setup:**
  ```bash
  export CATALOGUE_DEFAULT_VERSION="v7.0"
  export DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION="v5.0"
  ```
- **Format:** `^v[0-9]+(\.[0-9]+)?$` (e.g. `v5.0`, `v7.0`, `v7.1`).
- **Where they land:** Cloud Run backend env + `historical_backfill`
  Cloud Run Job env. NOT secrets.
- **Validation:**
  ```bash
  for v in "$CATALOGUE_DEFAULT_VERSION" "$DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION"; do
    [[ "$v" =~ ^v[0-9]+(\.[0-9]+)?$ ]] \
      && echo "✓ $v shape OK" \
      || echo "WARN: '$v' does not match v<N>(.<M>) (e.g. v5.0 or v7.0)"
  done

  # After §0.7 (Terraform apply + Cloud SQL exists), verify both are
  # loaded in `ccg_catalog_versions`:
  # psql "$DATABASE_URL_SYNC" -c "SELECT version FROM ccg_catalog_versions ORDER BY version;"
  ```

#### §0.2.15 — Final preflight against `.deploy.parameters.env`

Save every export to `.deploy.parameters.env`. **Do NOT use an
unquoted heredoc** — secrets that contain shell metacharacters
(backticks, `$()`, `:`, JSON braces) get evaluated and corrupt the
file. Use the `printf '%s=%q\n'` loop below which uses bash's
`%q` quoting to safely escape any character.

```bash
: "${REPO:=$HOME/Accelerate}"
cd "$REPO/apps/dma-insights"

# Auto-defer Clay when neither secret is set in the shell. The Clay
# connector is optional (ADR 0010 fails closed on empty secret), and
# operators on tiers without webhook support routinely defer it. If
# you DO have Clay creds, just `export CLAY_WEBHOOK_URL=... CLAY_WEBHOOK_SECRET=...`
# before pasting this block — the auto-defer only fires when both are
# blank. To explicitly opt-IN to Clay while leaving secrets blank
# temporarily, `export DMA_CLAY_DEFERRED=0` before this block.
if [[ -z "${CLAY_WEBHOOK_URL:-}" && -z "${CLAY_WEBHOOK_SECRET:-}" \
      && -z "${DMA_CLAY_DEFERRED:-}" ]]; then
  export DMA_CLAY_DEFERRED=1
  echo "ℹ Auto-deferring Clay (both CLAY_WEBHOOK_* are unset). To enable Clay,"
  echo "  export CLAY_WEBHOOK_URL + CLAY_WEBHOOK_SECRET before re-running."
fi

# Write each variable through bash's %q-escape so JSON / backticks /
# colons / quotes in secret values can't break the file or trigger
# command execution.
{
  printf '# Generated %s by §0.2 of DEPLOYMENT.md\n' "$(date -Iseconds)"
  # DMA_CLAY_DEFERRED comes FIRST so the deferral state is obvious at
  # the top of the file (the rest of the order doesn't matter).
  for v in \
      DMA_CLAY_DEFERRED \
      PROJECT_ID REGION ALLOWED_ORIGINS \
      GOOGLE_OAUTH_CLIENT_ID GOOGLE_OAUTH_CLIENT_SECRET \
      DMA_BOT_API_KEY RAG_API_BEARER_KEY REDIS_URL \
      CLAY_WEBHOOK_URL CLAY_WEBHOOK_SECRET \
      DRIVE_ROOT_FOLDER_ID OPS_SHEET_ID \
      VERTEX_PROJECT_ID VERTEX_LOCATION \
      VERTEX_FLASH_MODEL VERTEX_PRO_MODEL VERTEX_EMBEDDING_MODEL \
      CATALOGUE_DEFAULT_VERSION DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION
  do
    val="${!v-}"
    if [[ -n "$val" ]]; then
      printf '%s=%q\n' "$v" "$val"
    else
      printf '# %s=  (unset — see §0.2.x)\n' "$v"
    fi
  done
} > .deploy.parameters.env
chmod 600 .deploy.parameters.env
echo "✓ wrote .deploy.parameters.env"

# Reload + run the canonical preflight (this is what deploy-two-phase.sh
# Phase 0 runs). The preflight self-heals every non-secret default
# (DRIVE_ROOT_FOLDER_ID / OPS_SHEET_ID / VERTEX_LOCATION /
# CATALOGUE_DEFAULT_VERSION / etc.) so missing-but-known values WARN
# instead of FAIL.
set -a; source .deploy.parameters.env; set +a
bash infra/preflight-parameters.sh

# If you ever need to flip Clay back ON, set the secrets and re-run:
#   export CLAY_WEBHOOK_URL=https://... CLAY_WEBHOOK_SECRET=...
#   unset DMA_CLAY_DEFERRED
#   set -a; source .deploy.parameters.env; set +a  # picks up new shell vars
#   bash infra/preflight-parameters.sh

# Strict-live variant — runs Vertex/Drive/Ops probes when set.
DEPLOY_MODE=live bash infra/preflight-parameters.sh
```

State branches the preflight handles automatically:

| Variable | Behavior |
|---|---|
| `GOOGLE_OAUTH_CLIENT_SECRET` >80 chars + contains `{` or `"client_secret"` | Prints a WARN suggesting you stored the raw `client_secret_*.json` instead of just the `client_secret` field; gives the `jq` one-liner to extract it. |
| `DRIVE_ROOT_FOLDER_ID` / `OPS_SHEET_ID` unset | Auto-filled with the canonical Zennify values + WARN. Override in `.deploy.parameters.env` for a different deployment. |
| `CLAY_WEBHOOK_URL` / `CLAY_WEBHOOK_SECRET` unset + `DMA_CLAY_DEFERRED=1` | WARN, Clay enrichment disabled — set when the project's Clay tier doesn't yet support webhooks. |
| `VERTEX_PROJECT_ID` unset | Auto-fills from `PROJECT_ID`. |

If `preflight-parameters.sh` exits non-zero after these self-heals
ran, the flagged parameter is genuinely missing — go back to the
matching §0.2.x section.

### §0.3 — Authenticate + select project (Cloud Shell)

```bash
# Cloud Shell pre-authenticates the operator's Google account into
# `gcloud`. Verify; re-auth if the session is older than the gcloud
# token expiry.
gcloud auth list --format='value(account, status)' \
  | grep -q "ACTIVE" \
  || gcloud auth login --update-adc

# Application Default Credentials (ADC) — separate token from `gcloud
# auth login`. Used by the Drive / Vertex / Sheets validation curls
# above. Cloud Shell may need an explicit ADC refresh:
gcloud auth application-default print-access-token >/dev/null 2>&1 \
  || gcloud auth application-default login

# Pin the project for every subsequent gcloud call.
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
gcloud config set compute/region "$REGION"

# Re-confirm:
gcloud config list --format='value(core.account, core.project, run.region)'
# Expect: <your-email> $PROJECT_ID $REGION
```

If `gcloud auth list` returns an unexpected account (e.g. a personal
Gmail), `gcloud config set account <correct-email>` to switch.

Verify billing is enabled — Cloud Run + Vertex billing-account check:

```bash
gcloud beta billing projects describe "$PROJECT_ID" \
  --format='value(billingAccountName, billingEnabled)'
# Expect: "billingAccounts/0123ABCD-... True". If billingEnabled=False,
# this project will not bill-eligible Cloud Run / Vertex calls.
```

### §0.4 — Enable required GCP APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  containerregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  servicenetworking.googleapis.com \
  vpcaccess.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  aiplatform.googleapis.com \
  iamcredentials.googleapis.com \
  iam.googleapis.com \
  compute.googleapis.com \
  redis.googleapis.com \
  storage.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$PROJECT_ID"

# Verify all enabled:
ENABLED_APIS=$(gcloud services list --enabled --format='value(config.name)' \
  --project="$PROJECT_ID")
for api in \
  run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com sqladmin.googleapis.com pubsub.googleapis.com \
  aiplatform.googleapis.com redis.googleapis.com drive.googleapis.com \
  sheets.googleapis.com cloudresourcemanager.googleapis.com; do
  echo "$ENABLED_APIS" | grep -q "^${api}$" \
    && echo "✓ $api" \
    || echo "✗ $api NOT enabled"
done
```

If any line prints `✗`, re-run `gcloud services enable <api>` for
that specific API (some APIs take ~30s to flip).

### §0.5 — Create / validate Secret Manager secrets + IAM + service accounts

This step is OPERATOR-managed because every secret is sourced
out-of-band (OAuth screen, Clay UI, openssl). Terraform `data` blocks
reference each secret by name; if any secret is missing or empty,
`terraform apply` fails loudly. **No placeholders accepted** — the
production-readiness guard at `app/config.py::assert_production_ready`
refuses to boot if any required secret holds an empty string.

#### §0.5.1 — Create / populate the 6 OOB secrets

The canonical (idempotent) one-liner is `infra/preflight-parameters.sh
--create-secrets`. The expanded loop below shows what it does so you
can audit / debug it.

```bash
declare -A SECRET_MAP=(
  [dma-insights-oauth-client-secret]="$GOOGLE_OAUTH_CLIENT_SECRET"
  [dma-insights-bot-api-key]="$DMA_BOT_API_KEY"
  [dma-insights-rag-api-key]="$RAG_API_BEARER_KEY"
  [dma-insights-redis-url]="$REDIS_URL"
  [dma-insights-clay-webhook-url]="$CLAY_WEBHOOK_URL"
  [dma-insights-clay-webhook-secret]="$CLAY_WEBHOOK_SECRET"
)

skipped=()
written=()
for sid in "${!SECRET_MAP[@]}"; do
  val="${SECRET_MAP[$sid]}"
  if [[ -z "$val" ]]; then
    echo "  ⚠ $sid: SKIPPED (local value empty — already in Secret Manager? §0.2.0)"
    skipped+=("$sid")
    continue
  fi

  # Create if absent (idempotent).
  gcloud secrets describe "$sid" --project="$PROJECT_ID" >/dev/null 2>&1 \
    || gcloud secrets create "$sid" \
         --replication-policy=automatic --project="$PROJECT_ID"

  # Always add a new version. Cloud Run resolves `latest` so a new
  # version flows to next revision rollout (recover-db-passwords.sh
  # forces revision rolls to pick up rotated values).
  echo -n "$val" | gcloud secrets versions add "$sid" \
    --data-file=- --project="$PROJECT_ID" >/dev/null
  echo "  ✓ $sid: latest version added"
  written+=("$sid")
done
echo
echo "→ Wrote ${#written[@]} secret(s); skipped ${#skipped[@]} (empty local value)."

# Per-secret validation: confirm `latest` is non-empty AND matches the
# local export when the local was non-empty. Skipped secrets are
# verified to AT LEAST have a non-empty `latest` from a prior session.
# Fail-soft — never exits the shell.
echo
echo "→ Round-trip validation (Secret Manager → local export)"
problems=0
for sid in "${!SECRET_MAP[@]}"; do
  remote=$(gcloud secrets versions access latest --secret="$sid" \
             --project="$PROJECT_ID" 2>/dev/null)
  if [[ -z "$remote" ]]; then
    echo "  ✗ $sid: 'latest' is EMPTY"
    problems=$(( problems + 1 ))
  elif [[ -n "${SECRET_MAP[$sid]}" ]] \
       && [[ "$remote" != "${SECRET_MAP[$sid]}" ]]; then
    echo "  ✗ $sid: 'latest' does NOT match local value"
    problems=$(( problems + 1 ))
  else
    echo "  ✓ $sid: latest non-empty (${#remote} chars)"
  fi
done
if (( problems == 0 )); then
  echo "✓ All ${#SECRET_MAP[@]} secrets round-tripped cleanly."
else
  echo "✗ $problems secret(s) failed round-trip — see lines above"
fi
```

> **Idempotent re-run guarantee.** This loop can be re-run any number
> of times without harm. Empty `SECRET_MAP[…]` values are SKIPPED
> (so re-running after `source <(... --emit-exports)` doesn't blank
> out secrets you didn't intend to rotate). Non-empty values append
> a new `latest` version — operators that ran §0.2.0's
> `--emit-exports` get a no-op idempotent re-add (same value, new
> version number), which is cheap and harmless.

#### §0.5.2 — Create service accounts + IAM bindings

The deploy uses 3 service accounts. Each gets the minimum role set.

> **Race-condition guard.** `gcloud iam service-accounts create`
> returns BEFORE the SA is globally consistent — the very first
> `add-iam-policy-binding` for a fresh SA can fail with
> `Service account does not exist`. The `_wait_for_sa` helper below
> polls `iam service-accounts describe` until the SA is reachable
> (typically 1-3 seconds). Run this helper after every create call.
>
> **Paste discipline.** Each SA's block is wrapped in `() { ... }`
> braces — paste blocks one at a time, NOT all three at once. If
> Cloud Shell merges your paste (the prior version had this exact
> bug), the function definition fails to parse and prints a clear
> bash syntax error instead of silently swallowing bindings.

##### Helper functions (paste this block FIRST)

```bash
# Poll until the SA is globally consistent. Returns non-zero after
# 30 attempts (~30s) so the loop never hangs.
_wait_for_sa() {
  local email="$1"
  for _ in {1..30}; do
    gcloud iam service-accounts describe "$email" \
      --project="$PROJECT_ID" >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo "✗ FATAL: SA $email never appeared (30s)" >&2
  return 1
}

# Bind a list of roles to a single SA, verify each binding, print a
# per-role ✓/✗ summary. Fail-soft so a single missing role doesn't
# kill the shell.
_bind_roles() {
  local email="$1"; shift
  local roles=("$@")
  local label="${email%%@*}"
  echo "→ Binding ${#roles[@]} role(s) to $label"
  for role in "${roles[@]}"; do
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:$email" --role="$role" \
      --condition=None --quiet >/dev/null 2>&1
  done
  # Re-list once and grep — much faster than per-role get-iam-policy.
  local policy
  policy=$(gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:$email" \
    --format='value(bindings.role)' 2>/dev/null)
  local missing=0
  for role in "${roles[@]}"; do
    if echo "$policy" | grep -Fxq "$role"; then
      echo "  ✓ $role"
    else
      echo "  ✗ $role MISSING — re-run: gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$email --role=$role"
      missing=$(( missing + 1 ))
    fi
  done
  if (( missing == 0 )); then
    echo "✓ $label: all ${#roles[@]} role(s) bound"
  else
    echo "✗ $label: $missing role(s) MISSING (see above)"
  fi
}
```

##### Backend SA (paste this block AFTER the helpers)

```bash
(
  BACKEND_SA="dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "$BACKEND_SA" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create dma-insights-backend \
      --display-name="DMA Insights Backend" --project="$PROJECT_ID"
    _wait_for_sa "$BACKEND_SA" || exit 1
  fi
  _bind_roles "$BACKEND_SA" \
    roles/cloudsql.client \
    roles/secretmanager.secretAccessor \
    roles/pubsub.publisher \
    roles/aiplatform.user \
    roles/storage.objectViewer \
    roles/logging.logWriter \
    roles/monitoring.metricWriter
)
```

##### Worker SA (paste this block NEXT)

```bash
(
  WORKER_SA="dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com"
  if ! gcloud iam service-accounts describe "$WORKER_SA" \
        --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create dma-insights-worker \
      --display-name="DMA Insights Worker" --project="$PROJECT_ID"
    _wait_for_sa "$WORKER_SA" || exit 1
  fi
  _bind_roles "$WORKER_SA" \
    roles/cloudsql.client \
    roles/secretmanager.secretAccessor \
    roles/pubsub.publisher \
    roles/pubsub.subscriber \
    roles/aiplatform.user \
    roles/run.invoker \
    roles/logging.logWriter
)
```

##### Cloud Build SA (paste this block LAST)

```bash
(
  CLOUDBUILD_SA="$(gcloud projects describe "$PROJECT_ID" \
    --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
  # Cloud Build's default SA is the project's compute SA; it already
  # exists, so no create+wait needed.
  _bind_roles "$CLOUDBUILD_SA" \
    roles/run.admin \
    roles/iam.serviceAccountUser \
    roles/artifactregistry.writer \
    roles/secretmanager.secretAccessor \
    roles/cloudsql.client
)

echo "✓ All 3 service accounts + IAM bindings complete"
```

> **Idempotent re-run.** Every step above is safe to re-run. The
> create-or-skip guard, the `_wait_for_sa` poll, and the `_bind_roles`
> verification together mean a partial paste (or a race-condition
> drop) can always be recovered by re-pasting the exact same block.

##### §0.5.2-recover — Recovery from a partial IAM bind

If a prior paste hit the race condition (the first `roles/cloudsql.client`
binding dropped with `Service account does not exist`) OR Cloud Shell
merged two blocks together (paste-corruption swallowed the trailing
Cloud Build IAM loop entirely), use these three blocks to triage and
heal. **Paste them ONE AT A TIME** — never all three at once; Cloud
Shell will merge them again.

**Block 1 — re-add any missing backend role + verify all 7:**

```bash
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/cloudsql.client --condition=None --quiet

backend_email="dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com"
policy=$(gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:$backend_email" \
  --format='value(bindings.role)')
for role in roles/cloudsql.client roles/secretmanager.secretAccessor \
            roles/pubsub.publisher roles/aiplatform.user \
            roles/storage.objectViewer roles/logging.logWriter \
            roles/monitoring.metricWriter; do
  echo "$policy" | grep -Fxq "$role" \
    && echo "✓ backend has $role" \
    || echo "✗ backend MISSING $role — re-bind with: gcloud projects add-iam-policy-binding \"$PROJECT_ID\" --member=serviceAccount:$backend_email --role=$role --condition=None"
done
```

**Block 2 — re-add the four worker roles that paste-corruption commonly cuts (subscriber / aiplatform / run.invoker / logging) + verify all 7:**

```bash
worker_email="dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com"
for role in roles/pubsub.subscriber roles/aiplatform.user \
            roles/run.invoker roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$worker_email" --role="$role" \
    --condition=None --quiet >/dev/null
done

policy=$(gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:$worker_email" \
  --format='value(bindings.role)')
for role in roles/cloudsql.client roles/secretmanager.secretAccessor \
            roles/pubsub.publisher roles/pubsub.subscriber \
            roles/aiplatform.user roles/run.invoker roles/logging.logWriter; do
  echo "$policy" | grep -Fxq "$role" \
    && echo "✓ worker has $role" \
    || echo "✗ worker MISSING $role — re-bind with: gcloud projects add-iam-policy-binding \"$PROJECT_ID\" --member=serviceAccount:$worker_email --role=$role --condition=None"
done
```

**Block 3 — bind Cloud Build SA's 5 roles (commonly swallowed entirely by paste-corruption) + verify:**

```bash
cb_email="$(gcloud projects describe "$PROJECT_ID" \
  --format='value(projectNumber)')-compute@developer.gserviceaccount.com"
for role in roles/run.admin roles/iam.serviceAccountUser \
            roles/artifactregistry.writer roles/secretmanager.secretAccessor \
            roles/cloudsql.client; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$cb_email" --role="$role" \
    --condition=None --quiet >/dev/null
done

policy=$(gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:$cb_email" \
  --format='value(bindings.role)')
for role in roles/run.admin roles/iam.serviceAccountUser \
            roles/artifactregistry.writer roles/secretmanager.secretAccessor \
            roles/cloudsql.client; do
  echo "$policy" | grep -Fxq "$role" \
    && echo "✓ cloudbuild has $role" \
    || echo "✗ cloudbuild MISSING $role — re-bind with: gcloud projects add-iam-policy-binding \"$PROJECT_ID\" --member=serviceAccount:$cb_email --role=$role --condition=None"
done
```

After all three recovery blocks run, you should see **7 + 7 + 5 = 19
`✓` lines** with no `✗`.

Validation:

```bash
# Verify every required role bound.
EXPECTED_BACKEND_ROLES=(
  roles/cloudsql.client roles/secretmanager.secretAccessor
  roles/pubsub.publisher roles/aiplatform.user
)
for role in "${EXPECTED_BACKEND_ROLES[@]}"; do
  gcloud projects get-iam-policy "$PROJECT_ID" \
    --flatten="bindings[].members" \
    --filter="bindings.members:serviceAccount:$BACKEND_SA AND bindings.role=$role" \
    --format='value(bindings.role)' | grep -q "$role" \
    && echo "✓ backend has $role" \
    || echo "✗ backend MISSING $role"
done
```

#### §0.5.3 — Share Drive + Sheet with worker SA (+ validate impersonation)

The worker SA needs **Viewer** access to the Drive root folder and the
Ops Sheet. Cloud Shell can't do that part — it's a Drive UI step:

1. Open <https://drive.google.com/drive/folders/$DRIVE_ROOT_FOLDER_ID>
   (or the canonical folder).
2. **Share** → add `dma-insights-worker@<project>.iam.gserviceaccount.com`
   as a **Viewer**. Notify off.
3. Open the Ops Sheet (URL in §0.2.11). **Share** → add the same SA as
   **Viewer**. Notify off.

> **Why impersonate at all?** The operator's own ADC has Drive + Sheets
> scope, so a naive `curl` from Cloud Shell tells you whether YOUR
> account can read those resources — not whether the worker SA can.
> The worker SA is what actually runs in production, so we impersonate
> it to verify the SHARE step above worked. Without impersonation, the
> validation is meaningless.

##### §0.5.3-grant — Grant impersonation rights at the SA resource level

The `roles/iam.serviceAccountTokenCreator` role can be bound at two
levels:

- **Project level** (what the prior version did) — slower; can take
  30-60s for `iam.serviceAccounts.getAccessToken` to land in the IAM
  cache, AND grants impersonation on every SA in the project.
- **SA resource level** (what we now use) — propagates in a few
  seconds AND scopes impersonation to just the worker SA. Strictly
  better.

The previous error `PERMISSION_DENIED: Failed to impersonate ...
Permission 'iam.serviceAccounts.getAccessToken' denied on resource`
was a **propagation race** — the role bind landed but the next
`print-access-token` ran before IAM caught up. The block below
binds at the SA resource level AND polls until impersonation
actually works (typically 5-15s).

```bash
WORKER_SA="dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com"
ME="user:$(gcloud config get-value account 2>/dev/null)"

# Bind tokenCreator ON THE SA RESOURCE — propagates faster + tighter scope.
gcloud iam service-accounts add-iam-policy-binding "$WORKER_SA" \
  --member="$ME" \
  --role=roles/iam.serviceAccountTokenCreator \
  --condition=None --quiet >/dev/null

# Poll until impersonation actually works. 30s budget = 15 attempts at
# 2s each — typically succeeds in attempt 3-7.
echo "→ Polling until impersonation propagates…"
WORKER_TOKEN=""
for i in {1..15}; do
  if WORKER_TOKEN=$(gcloud auth print-access-token \
       --impersonate-service-account="$WORKER_SA" 2>/dev/null) \
     && [[ -n "$WORKER_TOKEN" ]]; then
    echo "  ✓ Impersonation ready after $((i * 2))s"
    break
  fi
  sleep 2
done
if [[ -z "$WORKER_TOKEN" ]]; then
  echo "  ✗ Impersonation never propagated. Verify the IAM bind landed:" >&2
  echo "    gcloud iam service-accounts get-iam-policy $WORKER_SA" >&2
fi
```

##### §0.5.3-probe — Probe Drive + Sheets as the worker SA

> **Shared Drive gotcha.** The canonical Zennify DMA folder
> (`1uvt3kh8…`) lives on a **Shared Drive**, not in My Drive. The
> Drive API returns 403 for Shared Drive content unless the request
> carries `supportsAllDrives=true`. Production code in
> `app/scripts/historical_backfill.py` already passes that flag — the
> probe below mirrors it. **If your DMA folder lives in My Drive,
> the flag is harmless; if it's on a Shared Drive, the flag is
> required.**

```bash
# Both probes are now in scripts (same paste-block class as §0.2.10 +
# §0.2.11). Run the two scripts in sequence — each emits OK or a
# specific 403/404 verdict with the exact share URL + SA email to
# paste. Operators who get OK on both can proceed; on 403/404, the
# script's verdict tells them precisely which fix to apply.
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-drive-folder.sh"
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-ops-sheet.sh"
```

##### §0.5.3-diagnose-step1 — Re-issue the worker SA token WITH Drive + Sheets scopes

> **DO NOT try `gcloud auth application-default login --scopes=...drive`
> in a managed Workspace.** Most Workspace orgs block the OAuth
> consent flow for unverified-app + sensitive-scope combinations.
> You'll see Google's red **"This app is blocked"** page. The fix
> doesn't go through ADC re-auth at all.
>
> Instead: re-issue the WORKER SA's impersonation token with explicit
> Drive + Sheets scopes. SA impersonation tokens bypass the OAuth
> consent screen entirely — they're first-party Google calls — so
> they cannot trip the "app blocked" wall. This is also the **most
> accurate test** because the worker SA is what actually runs in
> production; using your own ADC tells you nothing about whether the
> SA has access.

```bash
# Re-issue WORKER_TOKEN with explicit Drive + Sheets scopes.
# The --scopes flag on impersonation tokens is well-supported and
# never opens an OAuth consent screen.
WORKER_TOKEN=$(gcloud auth print-access-token \
  --impersonate-service-account="$WORKER_SA" \
  --scopes=https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/spreadsheets.readonly,https://www.googleapis.com/auth/cloud-platform)

# Verify the token actually carries those scopes:
curl -s "https://oauth2.googleapis.com/tokeninfo?access_token=$WORKER_TOKEN" \
  | jq -r '.scope' | tr ' ' '\n' | grep -E "drive|spreadsheets"
# Expect:
#   https://www.googleapis.com/auth/drive.readonly
#   https://www.googleapis.com/auth/spreadsheets.readonly
```

If the `grep` returns nothing, `gcloud` rejected the `--scopes` flag.
Update gcloud (`gcloud components update`) and retry.

##### §0.5.3-diagnose-step2 — Probe Drive + Sheets AS THE WORKER SA with raw errors

This is the canonical test — does the production worker SA actually
see the resources? Run with the scoped `WORKER_TOKEN` from
step 1, and a `_probe()` helper that prints raw HTTP code + body so
no error is silently swallowed.

```bash
# The two preflight scripts emit the same diagnostic info this block
# used to — raw HTTP code + verdict + the exact share URL/email — and
# handle their own token impersonation so you don't have to set
# WORKER_TOKEN by hand. Run them in sequence:
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-drive-folder.sh"
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/preflight-ops-sheet.sh"
```

Interpret the output:

| Outcome | Meaning |
|---|---|
| **All probes 200** | Worker SA has the access it needs. §0.5.3 is done. |
| Drive 404 | Folder ID is wrong OR the SA was never added to the ACL. Run §0.5.3-recover-add-perm. |
| Drive 403 | SA IS visible to a Drive API call but not authorized — usually a `driveId` (Shared Drive) issue, OR an org-level access policy. Open §0.5.3-recover-shared-drive. |
| Sheets 404 | Same as Drive 404 + Sheet is on a Shared Drive the SA isn't a Shared Drive member of. |
| Sheets 403 | Same as Drive 403. |

##### §0.5.3-recover-add-perm — Add the worker SA via API (when you ARE the owner)

If §0.5.3-diagnose-step2 returns 404 because the SA isn't on the ACL,
add it via the Drive API. **This requires YOUR account to be an
Editor / Manager / Owner of the resource** — otherwise the POST
itself will 403. If you can't run this, ask the actual owner.

```bash
# Your account's ADC scope (cloud-platform) DOES include Drive write
# for resources you OWN — so this POST works even without re-auth.
adc_token="$(gcloud auth application-default print-access-token 2>/dev/null)"

# Drive folder — add worker SA as reader.
curl -s -X POST \
  -H "Authorization: Bearer $adc_token" \
  -H "Content-Type: application/json" \
  -d '{"type":"user","role":"reader","emailAddress":"'"$WORKER_SA"'"}' \
  "https://www.googleapis.com/drive/v3/files/${DRIVE_ROOT_FOLDER_ID}/permissions?supportsAllDrives=true&sendNotificationEmail=false" \
  | jq -r 'if .id then "✓ Drive folder grant added: id=\(.id) role=\(.role)" else "✗ \(.error.message // .)" end'

# Ops Sheet — same shape.
curl -s -X POST \
  -H "Authorization: Bearer $adc_token" \
  -H "Content-Type: application/json" \
  -d '{"type":"user","role":"reader","emailAddress":"'"$WORKER_SA"'"}' \
  "https://www.googleapis.com/drive/v3/files/${OPS_SHEET_ID}/permissions?supportsAllDrives=true&sendNotificationEmail=false" \
  | jq -r 'if .id then "✓ Ops Sheet grant added: id=\(.id) role=\(.role)" else "✗ \(.error.message // .)" end'

echo "→ Sleeping 30s for Drive ACL propagation…"
sleep 30
```

After the sleep, re-run **§0.5.3-diagnose-step2** — both probes
should now return 200.

##### §0.5.3-recover-shared-drive — Shared Drive membership (if Drive returns 403 + driveId is non-null)

If the `files.get` body shows `"driveId": "0AB..."`, the resource
lives on a Shared Drive. Direct file-sharing isn't enough on a
Shared Drive — the SA needs **Shared Drive membership**:

1. Open <https://drive.google.com/drive/u/0/shared-drives>.
2. Right-click the Shared Drive that contains the folder → **Manage members**.
3. Add `dma-insights-worker@<project>.iam.gserviceaccount.com` as
   **Content manager** (or **Viewer** if you only need read).
4. Re-run §0.5.3-diagnose-step2 — Drive 200 should appear within
   30s of the add.

If you can't manage Shared Drive membership (your account isn't
the Drive's manager), the simpler workaround is to **move the
folder + sheet to My Drive** of a Workspace user the SA can read.
Production code accepts either layout.

##### §0.5.3-fallback — If everything above still 403s

If §0.5.3-diagnose-step2 returns 403 even after the worker SA was
added to the ACL AND the resource isn't on a Shared Drive, the
remaining causes are:

1. **Domain-Wide Delegation policy** — the Workspace admin has
   restricted which apps can use Drive scopes. The worker SA isn't
   on the allow-list. Open the Admin console → Security → API
   controls → Domain-wide delegation, and add the worker SA's
   numeric ID (`gcloud iam service-accounts describe $WORKER_SA
   --format='value(uniqueId)'`) with the Drive + Sheets scopes.
2. **Org-level Drive sharing restriction** — Admin → Apps → Google
   Workspace → Drive and Docs → Sharing settings. If "Sharing
   outside the organization" is **OFF**, the SA (which is a
   `*.iam.gserviceaccount.com` email — outside your Workspace
   domain) can't be granted access. Either flip the policy to
   "ON" or use a Workspace user account as the worker identity
   (less canonical but supported).

##### §0.5.3-recover — Recovery when impersonation still fails after the poll

If the polling block above prints `✗ Impersonation never propagated`,
the IAM bind didn't land. Most common causes:

1. **Operator account isn't a Project Owner / IAM Admin.** The bind
   silently succeeds but doesn't take effect. Verify with:
   ```bash
   gcloud iam service-accounts get-iam-policy "$WORKER_SA" \
     --format='value(bindings.role,bindings.members)' | grep tokenCreator
   ```
   If your account isn't listed, ask a project owner to run the bind.
2. **Org-level domain-wide-delegation policy blocks impersonation.**
   Visible via `gcloud org-policies list --project=$PROJECT_ID`.
3. **Conditional access on the role.** If `--condition=None` was
   omitted, IAM keeps prompting `gcloud alpha iam policies lint-condition`
   to check the condition; the bind appears to land but doesn't
   actually grant. The block above explicitly passes `--condition=None`.

#### §0.5.4 — Provision Cloud SQL (Postgres 16 + pgvector)

```bash
# One command — idempotent + resilient + auth-persistent. Replaces
# the 60-line paste block that previously lived here. Solves three
# recurring failure modes (2026-05-31 operator hit all three):
#   • tier `db-custom-2-7680` rejected by ENTERPRISE_PLUS-default
#     projects (the script pins --edition=ENTERPRISE)
#   • `gcloud sql connect` prompts for the postgres password every
#     session (the script writes ~/.dma-pg-superuser-pw + pulls
#     from Secret Manager — never prompts)
#   • stale local $SQL_PASSWORD after a re-run (the script ALWAYS
#     rotates the superuser password + destroys prior secret versions
#     so the latest is the only one that authenticates)
PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/setup-cloud-sql.sh"

# The superuser password is now in Secret Manager (current value only —
# previous versions destroyed) AND cached at ~/.dma-pg-superuser-pw.
#
# To run psql against the prod DB in ANY future session, use the
# dma-psql.sh helper — it starts cloud-sql-proxy AND resolves the
# password for you, then cleans up. (Plain `psql -h 127.0.0.1 -p 5432`
# does NOT work on its own: Cloud SQL isn't directly reachable —
# nothing listens on 5432 until the proxy is running. Sourcing the
# password only solves AUTH, not CONNECTIVITY.)
#   bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/dma-psql.sh" -c '\dt'

# Enable pgvector + pg_trgm + pgcrypto extensions. The script
# auto-picks the latest superuser password from Secret Manager OR
# the local cache — NEVER prompts.
INSTANCE_NAME=dma-insights-pg DB_NAME=dma_insights PROJECT_ID="$PROJECT_ID" \
  bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/setup-pg-extensions.sh"
# Expect rows "pgcrypto | 1.3 / pg_trgm | 1.6 / vector | 0.6.0" or higher.
```

**Operational notes:**

- **Re-running is safe.** Every re-run rotates the postgres password
  and destroys prior versions — the LATEST in Secret Manager is the
  only one that authenticates. Old shells (different terminals, stale
  cron jobs) using a previous password will fail-closed.
- **Persistence across sessions.** Secret Manager is the durable
  source of truth — your shell can disappear and the next session
  still picks up the right password. The `~/.dma-pg-superuser-pw`
  cache is a perf optimization; if missing, `setup-pg-extensions.sh`
  re-fetches it from Secret Manager automatically.
- **App-user password rotation** is a separate flow — see
  `recover-db-passwords.sh --rotate` for that.

#### §0.5.5 — Provision Pub/Sub topic + subscriptions

```bash
# Topic for ingest fan-out (best-effort publish; never wedges ingest).
gcloud pubsub topics describe dma.ingest.completed --project="$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud pubsub topics create dma.ingest.completed --project="$PROJECT_ID"

# Embedder + intelligence_recompute subscriptions (Cloud Run Jobs read).
for sub in dma-embedder-sub dma-intelligence-recompute-sub; do
  gcloud pubsub subscriptions describe "$sub" --project="$PROJECT_ID" >/dev/null 2>&1 \
    || gcloud pubsub subscriptions create "$sub" \
         --topic=dma.ingest.completed \
         --ack-deadline=600 \
         --message-retention-duration=7d \
         --project="$PROJECT_ID"
done

# Validation:
gcloud pubsub topics list --filter="name:dma.ingest.completed" --project="$PROJECT_ID" \
  --format='value(name)'
gcloud pubsub subscriptions list --filter="topic:dma.ingest.completed" --project="$PROJECT_ID" \
  --format='table(name, ackDeadlineSeconds, messageRetentionDuration)'
```

#### §0.5.6 — Provision Artifact Registry repository

```bash
gcloud artifacts repositories describe dma-insights \
  --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud artifacts repositories create dma-insights \
       --repository-format=docker --location="$REGION" \
       --description="DMA Insights container images" \
       --project="$PROJECT_ID"

# Docker auth helper:
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Validate the repo is reachable:
gcloud artifacts repositories describe dma-insights \
  --location="$REGION" --project="$PROJECT_ID" \
  --format='value(name, format)'
```

#### §0.5.7 — Final per-secret recap

Re-validate every secret exists + has a non-empty `latest` version:

```bash
EXPECTED_SECRETS=(
  dma-insights-oauth-client-secret
  dma-insights-bot-api-key
  dma-insights-rag-api-key
  dma-insights-redis-url
  dma-insights-clay-webhook-url
  dma-insights-clay-webhook-secret
  dma-insights-database-url
  dma-insights-database-url-sync
)
for sid in "${EXPECTED_SECRETS[@]}"; do
  if gcloud secrets describe "$sid" --project="$PROJECT_ID" >/dev/null 2>&1; then
    bytes=$(gcloud secrets versions access latest --secret="$sid" \
              --project="$PROJECT_ID" 2>/dev/null | wc -c)
    if (( bytes > 0 )); then
      echo "✓ $sid latest=$bytes bytes"
    else
      echo "✗ $sid latest is EMPTY"
    fi
  else
    echo "✗ $sid MISSING"
  fi
done
# Expect 8 lines, all "✓".
```

### §0.6 — Two-phase deploy (canonical path, closes the migration race)

Per ADR 0013, the canonical deploy is **two-phase** — it eliminates
the 10-60s window where the new revision serves traffic against the
old DB schema. The two-phase script is the single entry point that
fans out into Cloud Build, Terraform, migrations, the tag-URL readyz
probe, final traffic promotion, **and the post-deploy delta refresh**
(Phase 8, added 2026-06-05 — see §22 for the full contract).

> **Run this FIRST in a fresh Cloud Shell tab** — it self-heals the two
> things that bite a clean pull, then deploys. (1) `deploy-two-phase.sh`
> hard-requires `PROJECT_ID`; an unset var aborts at line ~61. (2) A
> stray earlier openpyxl re-save can leave the committed `*.xlsx`/`*.docx`
> DMA fixtures showing as locally modified, which makes `git pull` abort
> with *"Your local changes … would be overwritten by merge."* These
> fixtures are read-only test data — never operator-edited — so
> discarding the spurious local delta is always safe.

```bash
# 0) Self-heal $REPO + the parameter env (PROJECT_ID etc.) — the line
#    you run after every fresh Cloud Shell open (see §0.2 step 2).
export REPO="${REPO:-$HOME/Accelerate}"
cd "$REPO/apps/dma-insights"
if [[ -f .deploy.parameters.env ]]; then
  set -a; source .deploy.parameters.env; set +a
fi
: "${PROJECT_ID:?PROJECT_ID unset — run §0.2 step 2 to load secrets, or: export PROJECT_ID=<your-gcp-project>}"

# 1) Make the pull non-blocking: drop any spurious local mutation of the
#    committed binary DMA fixtures (safe — they are read-only test data).
git -C "$REPO" checkout -- 'apps/dma-insights/backend/tests/fixtures/**/*.xlsx' \
                           'apps/dma-insights/backend/tests/fixtures/**/*.docx' 2>/dev/null || true
git -C "$REPO" pull --ff-only origin claude/deploy-zennify-cloud-run-AUdu6
```

```bash
# Self-healing one-shot deploy. Every phase below is idempotent on
# success + has a documented failure mode that doesn't break the
# previous revision.
#
# Phases:
#   0   → preflight-parameters.sh (fail-closed if any parameter missing)
#   1   → gcloud builds submit (3 SHA-pinned images: backend/frontend/workers)
#   1.6 → DB liveness + password drift check (recover-db-passwords.sh ->
#         force-heal-db.sh fallback with REGENERATE-PASSWORD escape hatch
#         — see §22.3). Aborts deploy BEFORE Phase 2 if heal fails so the
#         OLD revision keeps serving 100% traffic.
#   2   → gcloud run services update --no-traffic --tag candidate-${SHA}
#         (NEW backend revision lives but receives NO traffic)
#   3   → migrate.sh (alembic upgrade head; OLD revision still serves 100%)
#   4   → curl ${TAG_URL}/readyz (probe NEW revision via its tag URL —
#         NOT the service URL, that still points at the OLD revision).
#         On 503: mid-deploy force-heal-db.sh + revision roll + re-probe.
#   5   → gcloud run services update-traffic --to-latest
#   6   → verify-deploy.sh (4-layer health check on service URL)
#   7   → frontend deploy (no migrations needed)
#   8   → post-deploy-refresh.sh: confirms 100% traffic on LATEST +
#         triggers drive_crawler/embedder/intelligence_recompute in DELTA
#         mode (NEW DMA reports only; persisted reports keep cached
#         narratives untouched — see §22.1 for the hard contract).
bash infra/deploy-two-phase.sh

# Skip build (re-use existing image at the current SHA):
bash infra/deploy-two-phase.sh --skip-build

# Skip migration (image-only change, no DDL):
bash infra/deploy-two-phase.sh --skip-migrate

# Skip Phase 8 refresh (fast iteration; you'll need to trigger backfill
# manually or wait for the scheduled drive_crawler crons):
bash infra/deploy-two-phase.sh --skip-refresh

# Also invalidate vertex_synthesis_cache rows older than the deploy
# (opt-in; costs Vertex tokens on the next read for every active
# surface — only use when a parser/code change actually changes how
# cached narratives should look):
bash infra/deploy-two-phase.sh --invalidate-cache
```

**Self-healing properties baked into the chain**:

| Failure mode | Self-heal step | Where in the chain |
|---|---|---|
| Cloud SQL instance MISSING | bail with terraform-apply instruction | Phase 1.6 (run `infra/ensure-db-ready.sh` first if uncertain) |
| Instance present but STOPPED | `preflight-cloud-sql.sh` auto-starts it | Phase 1.6 |
| Database `dma_insights` missing | `ensure-db-ready.sh` creates it (idempotent) | Phase 1.6 |
| SQL user missing OR password drift | `force-heal-db.sh` with regenerate-password escape hatch | Phase 1.6 + Phase 4 |
| `--enable-bin-log` on Postgres | engine-aware `--enable-point-in-time-recovery` branch | inside backup-before-heal.sh |
| /readyz 503 mid-deploy | `force-heal-db.sh` + revision roll + re-probe | Phase 4 |
| Newly-uploaded DMA reports unprocessed | drive_crawler/embedder/intelligence_recompute --mode delta | Phase 8 |
| Cached narrative pre-dates code change | opt-in `--invalidate-cache` | Phase 8 (via DMA_POST_DEPLOY_SQL) |

**Pre-flight escape hatch (run before deploy when DB state is uncertain)**:

```bash
# One-stop "make the DB ready" runner. Idempotent on a healthy DB.
# Handles missing instance / database / user / secret / schemas + heals
# password drift via the regenerate-password escape hatch in §22.3.
bash infra/ensure-db-ready.sh

# Diagnostic only (no writes):
bash infra/ensure-db-ready.sh --check-only
```

**Failure recovery without rollback.** At any failure in phases 1.6-4
(heal / deploy / migrate / readyz), the OLD revision is still serving
100% traffic. No `update-traffic --to-revisions` rollback is needed.
The failed candidate revision is labelled `candidate-${SHA}` and can
be deleted at leisure:

```bash
gcloud run revisions list --service=dma-insights-backend --region=${REGION}
gcloud run revisions delete <candidate-revision-name> --region=${REGION}
```

### §0.6c — CI test pipeline: zero-skip live-PG validation

`infra/cloudbuild.yaml` runs the backend test suite across two stages
so that **every** test executes in CI with **no skips** in the deploy
process:

- **Stage 1 `backend-tests`** (`python:3.12-slim`, no Postgres) — runs
  the full unit/parser suite. `DMA_BOT_API_KEY` + `RAG_API_BEARER_KEY`
  are set so the bearer-guard security tests run their assertions. The
  ~36 live-DB tests (gated on `SEED_CI_PG_URL`) skip here — they can't
  run without a database — and execute authoritatively in stage 2b.
- **Stage 2b `backend-tests-live-pg`** — spins up a `pgvector/pgvector
  :pg15` sidecar (matches Cloud SQL prod), round-trips alembic
  upgrade→downgrade→upgrade, then runs **every live-DB test file**
  against the seeded sidecar with `SEED_CI_PG_URL` + `DATABASE_URL` +
  `DMA_BOT_API_KEY` + `RAG_API_BEARER_KEY` set. A `grep SKIPPED` guard
  **fails the stage** if any test skips, so a future env-gate cannot
  silently reintroduce skips.

The DMA package parser tests run against the committed real samples at
`backend/tests/fixtures/dma_packages_real_samples/{Alma_Bank__DMA,
WSFS_Bank__DMA}` (no longer gated on dev-only `/tmp/dma-fixtures/`
paths), so the parser is exercised against real data on every run.

**Reproduce the live-PG stage locally — one command, no sudo, no typed
passwords.**

The script is recent, so pull first, then run it. This one-liner works
from **any** directory inside the repo (it resolves the repo root itself,
so you never hit `No such file or directory` from a relative path):

```bash
git -C "$(git rev-parse --show-toplevel)" pull
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/backend/scripts/run-local-tests.sh"
```

(Equivalently, from the repo root `~/Accelerate`:
`bash apps/dma-insights/backend/scripts/run-local-tests.sh` — the
relative path only works from the repo root, which is why the
`$(git rev-parse --show-toplevel)` form above is the safer copy-paste.)

That script is turnkey. It:

1. Brings up the pgvector Postgres + Redis via `docker compose` (creds +
   `vector`/`pgcrypto`/`pg_trgm` extensions are baked into
   `docker-compose.yml` + `scripts/init-extensions.sql` — **no
   `sudo -u postgres`, no role creation, nothing to type**).
2. Creates an isolated `dma_insights_ci` database inside that container
   (so the suite never clobbers your dev DB) via `docker compose exec`.
3. Ensures a project `.venv` with the dev deps (exact pins read from
   `pyproject.toml` — no duplicated list to drift).
4. Auto-wires every env var the suite needs — the local throwaway
   password is baked in, never keyed:
   `DATABASE_URL` / `DATABASE_URL_SYNC` / `SEED_CI_PG_URL` /
   `DMA_BOT_API_KEY` / `RAG_API_BEARER_KEY` / `REDIS_URL`.
5. Runs `alembic upgrade head` then the full `pytest` suite.

It also writes `backend/.env.local-ci` so you can re-run pytest by hand:

```bash
cd "$(git rev-parse --show-toplevel)/apps/dma-insights/backend"
source .env.local-ci && .venv/bin/python -m pytest tests/ -q
```

Useful flags (`RUNNER` resolves the script path from any cwd):

```bash
RUNNER="$(git rev-parse --show-toplevel)/apps/dma-insights/backend/scripts/run-local-tests.sh"
bash "$RUNNER" --reinstall      # refresh deps
bash "$RUNNER" -- -k auth -x    # passthrough to pytest
# Already have a Postgres you want to use? Point SEED_CI_PG_URL at it:
SEED_CI_PG_URL='postgresql+asyncpg://user:pw@host:5432/db' bash "$RUNNER" --no-db
```

<details>
<summary>Manual setup (only if you can't use Docker — needs a local
Postgres 16 you can already reach without sudo)</summary>

```bash
cd apps/dma-insights/backend

# Create the CI role + database against a Postgres you ALREADY administer.
# (Replace the psql connection with however you reach your local instance;
# the password below is a throwaway local-only value.)
psql -c "CREATE ROLE dma_insights LOGIN PASSWORD 'dma_insights_local' CREATEDB SUPERUSER" || true
psql -c "CREATE DATABASE dma_insights_ci OWNER dma_insights" || true

export DATABASE_URL_SYNC="postgresql+psycopg://dma_insights:dma_insights_local@127.0.0.1:5432/dma_insights_ci"
export DATABASE_URL="postgresql+asyncpg://dma_insights:dma_insights_local@127.0.0.1:5432/dma_insights_ci"
export SEED_CI_PG_URL="$DATABASE_URL"
export DMA_BOT_API_KEY=ci-bot-key RAG_API_BEARER_KEY=ci-rag-key

alembic upgrade head    # currently head=055 (evidence_tier_canonical: tier nullable, check narrowed to [1,7], fabricated 8s healed to NULL; 054 category display names; 053 platform_fit_breakdown: platform_scores.fit_breakdown+sequence_rank; 045-052 added the deep-QA data contract — runs evidence/coverage/uncertainty JSONB, insight interconnections, timeline NLP fields, recommendation outcomes, raw_artifacts, client_knowledge_sections(+embeddings), subcap_narratives, focus-area grounding; 044 added tech_stack_entries.l3_id + status enum)
python -m pytest tests/ -q
```

</details>

If you run `pytest` WITHOUT `SEED_CI_PG_URL` (no local DB), the live-DB
tests skip cleanly with `SEED_CI_PG_URL not set` — that is expected for
the fast unit lane (stage 1); the deploy pipeline covers them in
stage 2b.

### §0.7 — Terraform plan/apply (first-bootstrap only)

For first-bootstrap and infrastructure changes (Cloud SQL config,
Cloud Run Jobs, IAM bindings), use Terraform directly. Image-only
updates go through `deploy-two-phase.sh` (§0.6).

**You MUST ensure the 3 images exist at your SHA first.** `terraform
plan` reads `data "google_artifact_registry_docker_image"` for backend,
frontend, and workers during planning — a SHA with no built images
fails the whole plan with `Requested image was not found`. The
preflight below **builds any missing image** (it never skips or
excludes — per the deploy contract); it's a no-op when all 3 already
exist.

```bash
cd infra/terraform
terraform init

# Pin the SHA once, then ENFORCE images exist at it (builds if missing).
export SHA="$(git rev-parse --short HEAD)"
bash ../preflight-image-check.sh "$SHA"     # builds the 3 images if absent

terraform plan \
  -var "project_id=${PROJECT_ID}" \
  -var "region=${REGION}" \
  -var "image_sha=${SHA}" \
  -var "google_oauth_client_id=${GOOGLE_OAUTH_CLIENT_ID}" \
  -out=/tmp/dma.tfplan
terraform apply /tmp/dma.tfplan
```

> If `preflight-image-check.sh` triggers a build it takes ~5-15 min,
> then re-verifies all 3 landed before returning. If the build fails it
> exits non-zero and you should NOT run `terraform plan` — fix the build
> first (`gcloud builds list --limit=1`).

#### Operator note — `git pull` aborts on `.terraform.lock.hcl`

If `git pull` aborts with `Your local changes to the following files
would be overwritten by merge: apps/dma-insights/infra/terraform/.terraform.lock.hcl`,
the operator's local lockfile has uncommitted edits (almost always
from a prior local `terraform init`) that collide with a pinned-hash
update on the default branch.

**Resolution (safe default — discard local, pull, regenerate):**

```bash
cd "$HOME/Accelerate"
git diff -- apps/dma-insights/infra/terraform/.terraform.lock.hcl  # inspect first
git checkout HEAD -- apps/dma-insights/infra/terraform/.terraform.lock.hcl
git pull origin claude/deploy-zennify-cloud-run-AUdu6
( cd apps/dma-insights/infra/terraform && terraform init -input=false )
```

If the local diff added a NEW provider/version the remote doesn't
have (rare), instead:

```bash
git stash push -m "lockfile-local" -- apps/dma-insights/infra/terraform/.terraform.lock.hcl
git pull origin claude/deploy-zennify-cloud-run-AUdu6
git stash pop                           # may produce a merge conflict
( cd apps/dma-insights/infra/terraform && terraform init -input=false )  # regenerates
git add apps/dma-insights/infra/terraform/.terraform.lock.hcl
git commit -m "infra(terraform): reconcile lockfile after upstream pin"
git push origin claude/deploy-zennify-cloud-run-AUdu6
```

The lockfile IS committed (per Terraform's recommendation) so Cloud
Build's `terraform init` resolves the same provider hashes the
operator sees locally. The `.gitignore` excludes the per-init
`.terraform/` cache + `*.tfstate` + `*.tfplan` but keeps the
lockfile in source control on purpose.

### §0.8 — Post-bootstrap smoke

> Deeper variants: §5.7 (QA-gate smoke with role matrix) and §6.11
> (post-deploy smoke with failure-mode probes). This block is the
> minimal bootstrap pass.

```bash
# 1. Backend healthz / readyz
curl -fsSL "$(gcloud run services describe dma-insights-backend \
  --region ${REGION} --format='value(status.url)')/healthz"
curl -fsSL "$(gcloud run services describe dma-insights-backend \
  --region ${REGION} --format='value(status.url)')/readyz"

# 2. Frontend root + build-SHA stamp
FE_URL="$(gcloud run services describe dma-insights-frontend \
  --region ${REGION} --format='value(status.url)')"
curl -fsSL "${FE_URL}/" | grep -q 'x-build-sha' \
  && echo "✓ frontend build-SHA stamp present" \
  || { echo "FATAL: build-SHA stamp missing"; exit 1; }

# 3. First catalogue load + historical backfill
gcloud run jobs execute dma-insights-ccg-loader --region ${REGION} --wait
gcloud run jobs execute dma-insights-historical-backfill --region ${REGION} --wait
```

### §0.9 — Rollback (when bootstrap goes wrong)

Note: per ADR 0013, the two-phase deploy in §0.6 doesn't need a
traditional rollback for failures in phases 2-4 — the OLD revision
keeps serving 100% traffic. This section covers post-promotion
rollback (Phase 5+ failures) and out-of-band incidents.

```bash
# Roll Cloud Run traffic back to a known-good revision:
PRIOR_SHA=$(gcloud run revisions list --service=dma-insights-backend \
  --region=${REGION} --format="value(name)" --limit=2 | tail -1)
gcloud run services update-traffic dma-insights-backend \
  --to-revisions="${PRIOR_SHA}=100" --region=${REGION}

# Roll DB passwords (when a secret rotation went wrong):
bash infra/recover-db-passwords.sh

# Clean up failed candidate revisions left over from aborted two-phase deploys:
gcloud run revisions list --service=dma-insights-backend --region=${REGION} \
  --format="table(name,active,traffic,creationTimestamp)" | grep -v "100%"
# Then for each one with 0% traffic that you want to remove:
# gcloud run revisions delete <name> --region=${REGION}
```

---

## ⚡ Happy path (re-deploy after a code change)

If the project is already bootstrapped and you just want to ship a new
commit:

```bash
export REPO="$HOME/Accelerate"
cd "$REPO"
git pull origin claude/deploy-zennify-cloud-run-AUdu6

# CANONICAL — closes the traffic-shifts-before-migrations race (ADR 0013).
cd "$REPO/apps/dma-insights"
bash infra/deploy-two-phase.sh
```

That's it. `deploy-two-phase.sh`:

1. Phase 0 fail-closes via `preflight-parameters.sh` if any required
   secret / parameter is missing or pattern-invalid.
2. Phase 1 builds + pushes 3 images via Cloud Build.
3. Phase 2 deploys backend at the new SHA with `--no-traffic --tag
   candidate-${SHA}` — revision lives but receives NO traffic.
4. Phase 3 runs `migrate.sh` against live Cloud SQL — OLD revision
   keeps serving 100% throughout.
5. Phase 4 probes `/readyz` via the candidate tag URL (NOT the
   service URL — service still points at OLD).
6. Phase 5 promotes traffic to the new revision via
   `gcloud run services update-traffic --to-latest`.
7. Phase 6 verifies the post-promotion live revision with
   `verify-deploy.sh` (4-layer diagnostic).
8. Phase 7 deploys the frontend (no migration race).

**Failure semantics.** If any phase 2-4 step fails, the OLD revision
is still serving 100% — no rollback needed. The legacy single-phase
`./deploy.sh` is retained for emergency `--skip-migrate` hotfixes
that don't touch the schema.

### Legacy single-phase deploy (only for no-DDL hotfixes)

```bash
cd "$REPO/apps/dma-insights/infra"
./deploy.sh --skip-migrate    # explicit; refuses to silently skip migrations
```

`deploy.sh` (legacy) also:
1. Detects new alembic revisions via `alembic current` vs disk head
   (replaces the prior `git diff HEAD~5..HEAD` heuristic which
   silently missed older un-deployed migrations).
2. Verifies the live revision serves the new image **and** the live
   HTML carries the new build-SHA stamp **and** the .jsx files carry
   no-cache headers.

To re-run only the freshness checks (without redeploying):

```bash
./verify-deploy.sh                   # 4-layer freshness diagnostic
# Exit code = number of failed layers (0 = all green).
```

`deploy.sh` is end-to-end since 2026-05-24:

| Phase | What it does | State branches |
|---|---|---|
| 1. Image check | Polls gcr.io for the 3 images at $SHA | `already_built` → skip / `needs_build` → build |
| 2. Cloud Build | `gcloud builds submit` runs the 6-stage pipeline | `build_failed` → exit 2 with build-list pointer |
| 3. Terraform apply | Rolls all 4 Cloud Run revisions to the new SHA | escalating-parallelism retry (10→4→2→1) for IPv6 flakes |
| 4. Live verification | Confirms revisions match $SHA + `Cache-Control: no-cache` headers on `.jsx` | `live_lags_sha` → exit 3 + force-promote hint |

If verification reports the live revision still serves an older SHA,
the script tells you exactly how to force-promote. **Do not skip
verification** — the prior "stale frontend" symptom was caused by
silently-successful apply + browser cache of old `.jsx` files.

Then verify the round-trip works end-to-end with the §5§§TMP§§ playbook.

---

The deploy artifacts live entirely under `apps/dma-insights/infra/`:
- `terraform/main.tf` — every GCP resource (with input validation)
- `terraform/terraform.tfvars` — committed `project_id` default
- `deploy.sh` — wrapper that sets `GODEBUG=netdns=go` + retries
- `docker/{backend,frontend,worker}.Dockerfile` — three container images
- `cloudbuild.yaml` — 7-stage CI/CD pipeline (stage 7 is advisory)

State-branch contract:
- **Greenfield deploy** (no existing GCP project) → run §§1-15 in order.
- **Re-deploy** (image rebuild only) → §1 pull → §5 build → §16 promote.
- **Restoring a stale environment** (post key-rotation) → §4 secrets + §16 promote.
- **Recovering from a failed migration** → §18 disaster recovery.

> **Branch in use:** `claude/deploy-zennify-cloud-run-AUdu6`. Every command
> below assumes that branch is checked out. To pick up the latest
> remote changes BEFORE every deploy run §1 — there have been multiple
> security + functional fixes (RAG bearer timing attack, Vertex IAM,
> /readyz probes, migration 015 entity-delete guard, etc.) and skipping
> the pull leaves you on a stale codebase.

---

## ERROR HISTORY convention (read this before editing any infra file)

Every critical infrastructure file in `apps/dma-insights/infra/` and
`apps/dma-insights/backend/alembic/` carries a top-of-file **ERROR
HISTORY** comment block listing every recurring failure mode + the
fix that neutralized it. The convention:

- New failure modes get a new entry (`E<N>` / `M<N>` / `D<N>` / `A<N>`
  / `N<N>` / `V<N>` depending on the file).
- Fixes that span multiple files cross-reference each other so a reader
  who finds the symptom in one file can trace the full chain.
- Never silently revert a fix; if you must, add a new entry explaining
  why and what replaces it.

Files currently maintaining ERROR HISTORY blocks:

| File | Prefix | Coverage |
|---|---|---|
| `infra/deploy.sh` | E1–E9 | IPv6, image-missing, stale frontend, browser cache, project_id typos, pg drift, cwd, state-lock, alembic truncation |
| `infra/migrate.sh` | M1–M5 | password drift, alembic truncation, rollback erase, missing job, IPv6 |
| `infra/verify-deploy.sh` | V1–V3 | actionability, content-type check, stale-HEAD warning |
| `infra/docker/frontend.Dockerfile` | D1–D5 | heredoc, escaped backslashes, stale .jsx, wrong codebase, envsubst |
| `infra/docker/frontend-nginx.template` | N1–N5 | no-cache, proxy timeouts, IPv6 DNS, server-block scope, CDN edge |
| `backend/alembic/env.py` | A1–A5 | column truncation, async DSN, autogen empties, idempotency, generation immutability |

A grep across the tree for `ERROR HISTORY` lists every block:

```bash
grep -rn "ERROR HISTORY" apps/dma-insights/infra/ apps/dma-insights/backend/alembic/
```

---

## What changed (most recent batch — read me FIRST)

If you already deployed once and are surprised that fixes "aren't applied":

| Symptom | Root cause | Fix landed |
|---|---|---|
| Admin page still has old behaviour after pushing fixes | nginx had no `Cache-Control` → browser cached old `.jsx` for hours | `frontend-nginx.template` now sends `no-cache, no-store, must-revalidate` on every `.html/.jsx/.js/.json/.css/.map` (9b293ea) |
| `./deploy.sh` succeeds but UI unchanged | Script applied terraform but never rebuilt images — old image kept serving | `deploy.sh` now BUILDS images by default (this batch); idempotent skip if already built |
| `migrate.sh` fails with `StringDataRightTruncation` | alembic's `version_num` is VARCHAR(32); rev ID 35 chars | 3 layers: renamed rev to 23 chars + `env.py` widens column to 128 + CI test (cca0ff7) |
| OAuth `origin_mismatch` | OAuth client only had custom domain, not run.app URL | §3 + §15 documented; one-time GCP Console step |
| `pnpm: command not found` in Cloud Shell for §5 QA | Cloud Shell ships without pnpm/chromium/git-identity | New §5.0 pre-flight installs all of them idempotently (cba4083) |
| Cloud SQL password drift after rotation | Secret + actual user passwords desync | `recover-db-passwords.sh` + `migrate.sh` heal automatically |

**All of the above are now self-healing or guarded.** A fresh
`./deploy.sh` from a clean Cloud Shell session does the right thing
end-to-end with zero manual fix-up.

---

## 0 · Prerequisites (LEGACY — superseded by §0.1 above; kept for reference)

> **The canonical bootstrap path is `§0 — Zero-to-prod bootstrap`
> above (§0.1 through §0.8-new-placeholder). Run everything from GCP Cloud Shell.
> The table below describes the old workstation-based install path
> for operators who can't use Cloud Shell.**

| Tool | Version | Install |
|---|---|---|
| `gcloud` | ≥ 463.0 | https://cloud.google.com/sdk/docs/install |
| `terraform` | ≥ 1.9 | `brew install terraform` |
| `docker` | ≥ 24 | https://docs.docker.com/get-docker/ |
| `git` | ≥ 2.40 | bundled on macOS/Linux |
| `pnpm` | ≥ 9.0 | `corepack enable && corepack prepare pnpm@latest --activate` |
| `python` | 3.12 | `pyenv install 3.12` |
| `jq` | ≥ 1.6 | `brew install jq` (verifications need it) |
| `openssl` | ≥ 3.0 | bundled |

```bash
# Authenticate gcloud against the target project.
gcloud auth login
gcloud auth application-default login
export PROJECT_ID="digital-maturity-assessor"           # or your project
gcloud config set project "$PROJECT_ID"

# IMPORTANT for Cloud Shell users — force IPv4 to avoid the IPv6 routing
# bug that breaks every `terraform apply` from Cloud Shell. The deploy
# wrapper sets this automatically; export it here so other tooling
# (gcloud, curl, etc.) inherits the same behaviour.
export GODEBUG=netdns=go
```

---

## 1 · Pull / update the repo

This section is **either / or** — pick exactly one of §1a (fresh clone)
or §1b (existing checkout). Do not run both. The previous version of
this guide presented them as a single block, which caused operators
to chain them sequentially and land in the wrong directory.

After either path completes, you'll have a `REPO_ROOT` env var pointing
at the repo and your working directory set to `apps/dma-insights/`. The
rest of the guide assumes both.

### 1a · Fresh clone (no existing checkout)

If `~/Accelerate` does NOT already exist or is empty:

```bash
# CRITICAL: step OUT of any existing git checkout before cloning.
# `git clone` lands at $PWD — if you're already inside a repo, the new
# clone gets buried 4-6 levels deep (e.g.
# ~/Accelerate/Accelerate/apps/dma-insights/Accelerate). Reset to $HOME.
cd ~

# Defensive: if ~/Accelerate already exists from a prior session, this
# fresh-clone path is wrong — use §1b instead. Bail out loudly.
if [ -e ~/Accelerate ]; then
  echo "::error::~/Accelerate already exists — use §1b (existing checkout) instead."
  echo "          OR rename the existing dir aside first:"
  echo "          mv ~/Accelerate ~/Accelerate.legacy-\$(date +%s)"
  return 1 2>/dev/null || exit 1
fi

git clone https://github.com/dma-lang/Accelerate.git
cd Accelerate
git checkout claude/deploy-zennify-cloud-run-AUdu6

# Pin the absolute repo root + step into the app for the rest of the guide.
export REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT/apps/dma-insights"
echo "  REPO_ROOT=$REPO_ROOT"
echo "  PWD=$(pwd)"   # …/Accelerate/apps/dma-insights
```

### 1b · Existing checkout (you've cloned before)

If `~/Accelerate` already exists from a prior session:

```bash
# Find the repo no matter where you start — `git rev-parse` walks up.
# If you're not in a git checkout at all, the line below errors and
# you should use §1a instead.
cd ~/Accelerate                                 # OR wherever your clone lives
export REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Confirm the remote points at dma-lang/Accelerate (where every fix is
# pushed). If it points at a downstream mirror like
# accelerate-ctrl/Accelerate, that mirror may be behind by hours and
# you'll deploy stale code.
git remote -v
# Expected:
#   origin  https://github.com/dma-lang/Accelerate.git (fetch)
#   origin  https://github.com/dma-lang/Accelerate.git (push)
#
# If the remote is a different fork (e.g. accelerate-ctrl/Accelerate),
# either repoint origin OR add dma-lang as a second remote:
#   git remote set-url origin https://github.com/dma-lang/Accelerate.git
#   # OR — keep origin, add dma-lang explicitly:
#   git remote add dma-lang https://github.com/dma-lang/Accelerate.git
#   git fetch dma-lang claude/deploy-zennify-cloud-run-AUdu6
#   git checkout -B claude/deploy-zennify-cloud-run-AUdu6 dma-lang/claude/deploy-zennify-cloud-run-AUdu6

# Pull the latest fixes for the deploy branch.
git fetch origin claude/deploy-zennify-cloud-run-AUdu6
git checkout claude/deploy-zennify-cloud-run-AUdu6
git pull origin claude/deploy-zennify-cloud-run-AUdu6

cd "$REPO_ROOT/apps/dma-insights"
echo "  REPO_ROOT=$REPO_ROOT"
echo "  PWD=$(pwd)"   # …/Accelerate/apps/dma-insights
```

### 1c · Confirm you're on the right commit

Regardless of which path you took, sanity-check before continuing:

```bash
# Must print the head of claude/deploy-zennify-cloud-run-AUdu6 from
# dma-lang/Accelerate. If you see a commit from a different fork or
# from days ago, repoint origin per §1b before continuing.
git -C "$REPO_ROOT" log -1 --format='%h %ad %s%n  origin: %(upstream)' --date=short

# The apps/dma-insights directory must exist at this exact path.
ls "$REPO_ROOT/apps/dma-insights/infra/terraform/main.tf" >/dev/null \
  && echo "  ✓ repo layout looks good" \
  || { echo "::error::apps/dma-insights/infra/terraform/main.tf missing — wrong repo or wrong branch"; exit 1; }
```

**Before every deploy, ALWAYS run §1b first** (the pull). The latest
security + resilience fixes ship as commits on this branch; running an
old checkout against a fresh GCP project will rebuild stale Docker
images and miss the migrations / IAM bindings the rest of the guide
assumes.

> ⚠ **Local clone ≠ Cloud Run deployment.** Pulling latest code into
> your Cloud Shell filesystem updates your LOCAL workspace only.
> Cloud Run services keep serving whatever container image SHA was last
> rolled out via Terraform — until you complete §5 (build new images),
> §6 (terraform apply with the new SHA), and §8 (run migrations if
> alembic/versions/ changed), the deployed app is still on the prior
> SHA. See **§16 Promote a new image SHA later** for the exact
> end-to-end rollout sequence.

---

## 2 · Enable required GCP APIs

```bash
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  containerregistry.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  cloudfunctions.googleapis.com
```

Provision the GCS state bucket Terraform will use for its backend:

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-tfstate" \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets update "gs://${PROJECT_ID}-tfstate" --versioning
```

And buckets for the catalogue staging area + ingest materials:

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-catalogue-staging" \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets create "gs://${PROJECT_ID}-request-materials" \
  --location=us-central1 --uniform-bucket-level-access
```

---

## 3 · Set up Google OAuth (one-time, manual)

OAuth is **not** automatable via Terraform for standard web clients
(`google_iap_brand` / `google_iap_client` only manage IAP-protected
flows). This is a one-time manual step in the GCP Console.

1. Console → APIs & Services → Credentials → Create OAuth 2.0 Client ID.
2. Type: **Web application**. Name: `dma-insights-web`.
3. Authorized JavaScript origins:
   ```
   https://dma-insights.zennify.com
   http://localhost:5173
   ```
4. Authorized redirect URIs:
   ```
   https://dma-insights.zennify.com/api/v1/auth/google/callback
   http://localhost:5173/api/v1/auth/google/callback
   ```

> **⚠ Until §13 (custom-domain mapping) is complete, ALSO add the raw
> Cloud Run frontend URL** (`https://dma-insights-frontend-<hash>-uc.a.run.app`)
> **as an authorized JavaScript origin AND its
> `/api/v1/auth/google/callback` as a redirect URI.** Otherwise the
> first sign-in fails with `Error 400: origin_mismatch`. After §6
> finishes, grab the URL via `terraform output -raw frontend_url`,
> paste both entries into Console, wait ~30s for propagation, and
> retry sign-in in an Incognito window (to skip stale auth cache).
> Remove these entries once the custom domain is live.

5. Save. Copy the `client_id` and `client_secret` — you'll need them in §4.

---

## 4 · Populate Secret Manager

Terraform reads several secrets via `data "google_secret_manager_secret"`
blocks; if any are missing, `terraform plan` fails **immediately** with
"Secret X not found" (the QA audit added this fail-fast guard so prior
deploys no longer silently boot Cloud Run revisions that crash at startup).

**Security:** never paste secret values into chat tools or terminal
history. Use `read -s` for prompted input and `shred -u` for any temp
file containing key material.

### 4a · Create the two service accounts

```bash
PROJECT_ID="$(gcloud config get-value project)"

# Vertex AI runtime SA (alternative invoker SA; not strictly required
# now that the Compute Engine default SA has roles/aiplatform.user via
# Terraform, but kept for least-privilege rotation later).
gcloud iam service-accounts create dma-insights-vertex \
  --display-name "DMA Insights Vertex AI runtime"

# Drive + Sheets reader SA (drive_crawler + sheet_poller workers).
gcloud iam service-accounts create dma-insights-drive \
  --display-name "DMA Insights Drive + Sheets reader"

# Wait for propagation, then create JSON keys.
for sa in dma-insights-vertex dma-insights-drive; do
  email="${sa}@${PROJECT_ID}.iam.gserviceaccount.com"
  until gcloud iam service-accounts describe "$email" --quiet 2>/dev/null >/dev/null; do
    echo "waiting for $email to propagate…"; sleep 5
  done
  gcloud iam service-accounts keys create "/tmp/${sa}.key.json" \
    --iam-account "$email"
done
```

In Google Workspace, share the DMA Drive root folder
(`1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`) and the Ops Sheet
(`1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8`) with **both** the Drive
SA email (`dma-insights-drive@${PROJECT_ID}.iam.gserviceaccount.com`)
AND the Compute Engine default SA (used by the historical backfill —
see §9 + §11). Both as **Viewer**, "Notify people" unchecked.

### 4b · Populate the secret values

```bash
# OAuth client_secret from §3.
read -s -p "OAuth client_secret: " OAUTH_SECRET; echo
printf '%s' "$OAUTH_SECRET" | \
  gcloud secrets create dma-insights-oauth-client-secret \
  --data-file=- --replication-policy=automatic 2>/dev/null || \
  printf '%s' "$OAUTH_SECRET" | \
  gcloud secrets versions add dma-insights-oauth-client-secret --data-file=-
unset OAUTH_SECRET

# JWT signing key (RS256). Fresh per environment.
openssl genrsa -out /tmp/jwt-priv.pem 4096
gcloud secrets create dma-insights-jwt-signing-key \
  --data-file=/tmp/jwt-priv.pem --replication-policy=automatic 2>/dev/null || \
  gcloud secrets versions add dma-insights-jwt-signing-key \
    --data-file=/tmp/jwt-priv.pem
shred -u /tmp/jwt-priv.pem

# Bot API key (DMA Bot uses this for /ingest/assessment).
openssl rand -hex 32 | \
  gcloud secrets create dma-insights-bot-api-key --data-file=- \
  --replication-policy=automatic 2>/dev/null || \
  openssl rand -hex 32 | \
  gcloud secrets versions add dma-insights-bot-api-key --data-file=-

# RAG API key (Claude project queries /api/v1/rag/*). The endpoint uses
# hmac.compare_digest() (constant-time) per the v1 QA fix — so no
# brute-force timing attacks on this key.
openssl rand -hex 32 | \
  gcloud secrets create dma-insights-rag-api-key --data-file=- \
  --replication-policy=automatic 2>/dev/null || \
  openssl rand -hex 32 | \
  gcloud secrets versions add dma-insights-rag-api-key --data-file=-

# Vertex + Drive SA keys (created in §4a).
for sa in dma-insights-vertex dma-insights-drive; do
  src="/tmp/${sa}.key.json"
  if [ ! -f "$src" ]; then echo "ERROR: $src missing — re-run §4a"; continue; fi
  gcloud secrets create "${sa}-sa-key" \
    --data-file="$src" --replication-policy=automatic 2>/dev/null || \
    gcloud secrets versions add "${sa}-sa-key" --data-file="$src"
  shred -u "$src"
done

# Redis URL — Upstash or Memorystore, must start with redis:// or rediss://.
while true; do
  read -s -p "Redis URL (rediss:// or redis://): " REDIS_URL; echo
  case "$REDIS_URL" in
    rediss://*|redis://*) break ;;
    *) echo "  must start with redis:// or rediss://" ;;
  esac
done
printf '%s' "$REDIS_URL" | \
  gcloud secrets create dma-insights-redis-url --data-file=- \
  --replication-policy=automatic 2>/dev/null || \
  printf '%s' "$REDIS_URL" | \
  gcloud secrets versions add dma-insights-redis-url --data-file=-
unset REDIS_URL

# Clay connector — populated in §14. Empty for now (fail-closed).
gcloud secrets create dma-insights-clay-webhook-url    --replication-policy=automatic 2>/dev/null || true
gcloud secrets create dma-insights-clay-webhook-secret --replication-policy=automatic 2>/dev/null || true
```

### 4c · Verify

```bash
for s in dma-insights-oauth-client-secret dma-insights-jwt-signing-key \
         dma-insights-bot-api-key dma-insights-rag-api-key \
         dma-insights-vertex-sa-key dma-insights-drive-sa-key \
         dma-insights-redis-url; do
  echo "=== $s ==="
  gcloud secrets versions list "$s" --filter="state=ENABLED" \
    --format='value(name,state)'
done
# Each must show exactly one ENABLED version. If any is missing,
# `terraform plan` in §6 will fail fast.
```

### 4d · Disable superseded versions after rotation

`version=latest` resolves to the highest-numbered ENABLED version. To
keep rollback targets clean, disable older ENABLED versions after a
rotation:

```bash
for s in dma-insights-oauth-client-secret dma-insights-jwt-signing-key \
         dma-insights-bot-api-key dma-insights-rag-api-key \
         dma-insights-vertex-sa-key dma-insights-drive-sa-key \
         dma-insights-redis-url dma-insights-database-url; do
  latest=$(gcloud secrets versions list "$s" --filter="state=ENABLED" \
    --sort-by=~createTime --limit=1 --format='value(name)')
  for v in $(gcloud secrets versions list "$s" --filter="state=ENABLED" \
             --format='value(name)'); do
    [ "$v" = "$latest" ] && continue
    gcloud secrets versions disable "$v" --secret="$s"
  done
done
```

Disable (don't destroy) so you can re-enable for emergency rollback.

---

## 5 · Build + push the three container images via Cloud Build

> **For day-2 redeploys, skip this section — just run `./infra/deploy.sh`.
> Since 2026-05-24 the wrapper auto-builds when images aren't yet present
> at the target SHA. The flow below is for first-time bootstrap or
> when you want to inspect the build stages explicitly.**

Terraform pins Cloud Run revisions to specific image SHAs, so the
images **must exist** before `terraform apply` runs.

### Image-as-stress-test contract (read before changing cloudbuild.yaml)

The build pipeline is structured so the SAME image Cloud Build pushes
to `gcr.io` stress-tests itself against a real Postgres BEFORE Terraform
deploys it. The contract:

1. **Stage 1 (backend-tests)** — runs in `python:3.12-slim` with no
   Docker, no PG sidecar. Of 1050 tests collected, **1024 execute**
   (24 skip with `SEED_CI_PG_URL not set` because there's no live DB
   to point at; 2 skip for proprietary AlmaBank/WSFS fixtures that
   aren't shipped to the runner).
2. **Stage 2 (backend-build)** — builds the backend image with all
   fixtures baked in, pushes `:${SHA}` + `:latest` to gcr.io.
3. **Stage 2b (backend-tests-live-pg)** — spins up
   `pgvector/pgvector:pg15` as a docker sidecar, then runs the
   just-built image against it:
     - `alembic upgrade head → downgrade base → upgrade head` round-trip
     - probe `alembic_version` count, pgvector extension, FK validation
     - **`python -m app.scripts.seed_ci`** populates the 5 fixtures
     - **`pytest tests/test_persona_e2e.py tests/test_live_db_integration.py
       tests/test_job_executions_insert_no_ambiguous_params.py tests/test_seed_ci.py`**
       collects 40 tests, deselects 4 (TestVisualBaselines,
       test_backend_dockerfile_ships_fixtures, test_seed_ci_no_runtime_imports_from_tests_package,
       test_force_regen_rebuilds_fixtures) that need host-repo layout
       or write-access to host-owned fixtures, runs the remaining
       **35 tests** with `SEED_CI_PG_URL` set against the just-built
       image — the IMAGE is the stress test of what's about to be
       deployed
4. **Stages 3 onwards** — frontend / worker images, terraform-plan,
   e2e-personas, frontend-image-smoke.

**Env-var contract on stage 2b** (what flips the SEED-gated tests on):
```
SEED_CI_PG_URL     = postgresql+asyncpg://dma:dma_ci_password@dma-ci-mig-pg:5432/dma_insights_ci
DATABASE_URL       = postgresql+asyncpg://...    # same DSN, used by router code under test
DATABASE_URL_SYNC  = postgresql+psycopg://...    # same DSN, alembic / psycopg2 tests
ENV                = local                       # unlocks /auth/dev-login + skips prod-readiness guard
DMA_BOT_API_KEY    = ci-bot-key                  # unblocks bearer-guard regression test
```

Without these, the 24 tests skip with `SEED_CI_PG_URL not set —
persona E2E + persistence tests skipped` and bugs that surface only
against real PG slip into production. The 2026-05-27 FILTER-on-ROUND
parser bug (returned 500 from every `/overview` call) was caught only
because stage 7 e2e ran the live SPA against the live image — adding
it to stage 2b catches the same class of bug ~60s into the build
instead of ~4 min in.

The four gated test files cover:

| File | Coverage |
|---|---|
| `tests/test_persona_e2e.py` | Persona role gating + ingestion→DB→API→UI chain + `test_overview_pillar_scores_sql_executes_against_all_5_entities` (the FILTER-on-ROUND pin) |
| `tests/test_live_db_integration.py` | `/readyz` drift detection, ingest writes rows, parser_warnings JSONB round-trip, audit_log INSERTs |
| `tests/test_job_executions_insert_no_ambiguous_params.py` | asyncpg AmbiguousParameterError regression on the drive_crawler INSERT path |
| `tests/test_seed_ci.py::TestLivePersistence` | seed_ci writes 5 runs + idempotency under re-seed + `--only filter` subset |

Stage 2b's image-as-stress-test step is pinned by
`tests/test_infra_safeguards.py::test_cloudbuild_stage_2b_runs_live_pg_pytest` —
removing the live-PG pytest sub-step (e.g., to "speed up CI") trips that
regression test at stage 1 before the build can submit.



**SHA pinning rule:** capture `$SHA` **once** at the start of §5 and
reuse the exact same value through §6. A `git pull` between steps
advances `HEAD`; re-running `$(git rev-parse --short HEAD)` reassigns
`$SHA` and points Terraform at a SHA whose images haven't been built.
Persist the SHA to disk so it survives shell restarts.

```bash
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel)}"
cd "$REPO_ROOT/apps/dma-insights"
PROJECT_ID="$(gcloud config get-value project)"

# CAPTURE THE SHA ONCE — DO NOT RE-CAPTURE LATER.
SHA="$(git rev-parse --short HEAD)"
echo "$SHA" > /tmp/dma-insights-deploy-sha
echo "  → tagging images :$SHA"

# 7-stage pipeline (see infra/cloudbuild.yaml):
#   1. backend tests + ruff  (must pass — 364 tests at HEAD)
#   2. backend docker build → push to gcr.io
#   3. frontend tests + tsc + vite build  (must pass — 117 tests)
#   4. frontend docker build → push (nginx config from frontend-nginx.template)
#   5. worker docker build → push (shared image for 5 jobs)
#   6. terraform plan (visibility; no apply)
#   7. Playwright E2E + visual regression (advisory; non-blocking)
#
# Resilience: ./infra/build.sh is the recommended wrapper. It pre-
# validates cloudbuild.yaml for unescaped uppercase shell vars (the
# T18 failure mode), then invokes gcloud builds submit with the right
# substitutions. Falls back to direct gcloud if the wrapper isn't
# committed yet.
if [[ -x infra/build.sh ]]; then
  ./infra/build.sh "$SHA"
else
  gcloud builds submit . --config infra/cloudbuild.yaml \
    --substitutions=_IMAGE_SHA="$SHA"
fi
```

Verify all three images landed at that exact SHA:

```bash
SHA="$(cat /tmp/dma-insights-deploy-sha)"
for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
  matched=$(gcloud container images list-tags "gcr.io/${PROJECT_ID}/${img}" \
    --filter="tags:${SHA}" --format='value(tags)' | head -1)
  if [ -z "$matched" ]; then
    echo "::error::no image $img:$SHA — re-submit Cloud Build"
  else
    echo "  ✓ $img:$SHA"
  fi
done
```

All three must print `✓`. If any errors, check the build log:
```bash
gcloud builds list --limit=3 --sort-by=~createTime
gcloud builds log <build-id>
```

---

## 6 · Provision infrastructure with Terraform

**Use the deploy wrapper.** It handles the Cloud Shell IPv6 routing
bug + initializes the GCS backend + retries transient errors + injects
required variables:

```bash
cd "$REPO_ROOT/apps/dma-insights/infra"
./deploy.sh
```

The wrapper:
1. **Disables IPv6 at the kernel level** via `sudo sysctl -w
   net.ipv6.conf.all.disable_ipv6=1` (Cloud Shell allows passwordless
   sudo). This is the most reliable IPv6 mitigation — `GODEBUG=netdns=go`
   alone changes only the Go DNS resolver, but Go's Happy Eyeballs can
   still pick an IPv6 address it can't reach. Kernel-level disable makes
   IPv6 invisible to the resolver.
2. Exports `GODEBUG=netdns=go` (belt-and-suspenders fallback).
3. Reads `PROJECT_ID` from `gcloud config get-value project`.
4. Reads `SHA` from `git rev-parse --short HEAD` (override with
   `SHA=<value> ./deploy.sh` if you need to pin a specific image).
5. **Runs `terraform init -reconfigure -backend-config=…` first** so
   fresh checkouts (and checkouts whose state bucket changed) don't
   fail with "Backend initialization required". Idempotent + cheap.
6. **Escalating-parallelism retry** (`-parallelism=10 → 4 → 2 → 1`):
   each retry reduces concurrent API calls so flaky-network failures
   shrink monotonically. Cloud Shell's IPv6 NAT pool fails ~N
   independent times when N concurrent requests run; serialising
   shrinks the failure surface.
7. **Error-pattern detection** — distinguishes IPv6 routing failures
   from image-missing, state-lock contention, rate-limit, and unknown
   errors. Un-retryable errors (image missing, state lock) abort
   immediately with actionable remediation instead of wasting 4
   attempts. Retryable errors continue the escalation.

**Force a specific parallelism** if you already know the network is
flaky (skip the fast-but-failing first attempts):

```bash
# Run the apply fully serialised — slowest but most reliable.
PARALLELISM_OVERRIDE=1 ./deploy.sh

# Or moderate concurrency for known-flaky networks
PARALLELISM_OVERRIDE=2 ./deploy.sh
```

**Variable validation:** the Terraform module rejects bad inputs at
plan-time:
- `project_id` must match `^[a-z][a-z0-9-]{4,28}[a-z0-9]$` (catches
  the famous "I typed `latest`" mistake from prompt-driven runs).
- `image_sha` must match `^[0-9a-f]{7,40}$` (catches "latest" / typos).

If you must run terraform directly without the wrapper, the **right
directory is `apps/dma-insights/infra/terraform/`** (NOT `infra/`):

```bash
TF_DIR="$REPO_ROOT/apps/dma-insights/infra/terraform"
cd "$TF_DIR"
ls main.tf                   # sanity: file MUST exist before init
                             # If empty: you're in infra/, not infra/terraform/

# The state bucket gs://${PROJECT_ID}-tfstate MUST exist from §2.
# `-reconfigure` is safe + recommended (handles bucket changes).
terraform init -reconfigure -backend-config="bucket=${PROJECT_ID}-tfstate"

SHA="$(cat /tmp/dma-insights-deploy-sha)"   # the pinned SHA from §5

# ENFORCE images exist at $SHA before apply — builds any missing image
# (never skips). terraform's image data lookups fail the plan otherwise.
bash ../preflight-image-check.sh "$SHA"

GODEBUG=netdns=go terraform apply \
  -var "project_id=${PROJECT_ID}" \
  -var "image_sha=${SHA}" \
  -auto-approve
```

**What `terraform apply` creates** (verbatim from `main.tf`):
- **Cloud SQL Postgres 15** `dma-insights-pg`, REGIONAL HA,
  `db-custom-2-7680`, IAM auth + Query Insights, daily backups +
  PITR enabled (verify in §18).
- **Database `dma_insights`** + user `dma_insights` (password +
  DSN secret managed end-to-end by Terraform — see §7).
- **2 Cloud Run services** (`dma-insights-backend`, `dma-insights-frontend`).
- **5 Cloud Run Jobs** (drive_crawler, sheet_poller, embedder,
  ccg_loader, historical_backfill, migrations).
- **3 Cloud Scheduler triggers** (drive crawler 6h, sheet poller 5m,
  ccg loader hourly).
- **Pub/Sub topic** `dma.ingest.completed`.
- **IAM bindings**:
  - `roles/aiplatform.user` (Vertex Gemini + embeddings — added in QA-audit-v1)
  - `roles/cloudsql.client`
  - `roles/secretmanager.secretAccessor` + per-secret bindings
  - Public-invoker grants for the two services
  - (Drive access is per-folder ACL, NOT a project IAM role — see §9)
- **Public-invoker (`allUsers`) bindings** on backend + frontend.

Outputs (capture for §7 / §10):
```bash
terraform output            # prints all
# Specifically:
terraform output -raw backend_url
terraform output -raw frontend_url
terraform output -raw db_instance_name
terraform output -raw db_connection_name
```

### 6a · Stale state-lock recovery

If `apply` was interrupted, the GCS state lock object sticks around:
```bash
terraform force-unlock <LOCK_ID>     # ID is printed in the error
# Last-resort:
gsutil rm gs://${PROJECT_ID}-tfstate/dma-insights/terraform/default.tflock
```

### 6b · Image-not-found recovery during apply

If apply prints `Error code 5: Image 'gcr.io/…:<sha>' not found`:
```bash
# Diagnose what's actually in gcr.io
for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
  gcloud container images list-tags "gcr.io/$PROJECT_ID/$img" \
    --format='table(digest.slice(7:19),tags.join(","),timestamp.datetime)' --limit=5
done
# Recovery: re-run §5 with the SHA you want, then retry §6.
```

---

## 7 · Postgres user + DSN secret

Terraform owns the entire DB-user / DSN-secret chain — `apply` (§6)
generates a strong password, sets it on the `dma_insights` user, builds
the full DSN, stores it as `dma-insights-database-url` in Secret Manager,
and rolls a backend revision pointing at it. **No operator script.**

### 7a · Postgres superuser password (Alembic in §8 only)

Alembic needs the `postgres` superuser to run `CREATE EXTENSION vector`.
Set the password once and stash it:

```bash
PROJECT_ID="$(gcloud config get-value project)"
INSTANCE="$(terraform -chdir="$REPO_ROOT/apps/dma-insights/infra/terraform" \
  output -raw db_instance_name 2>/dev/null || echo dma-insights-pg)"

PG_PW="$(openssl rand -base64 32 | tr -d '+/=' | cut -c1-32)"
gcloud sql users set-password postgres --instance="$INSTANCE" --password="$PG_PW"
printf '%s' "$PG_PW" | gcloud secrets create dma-insights-pg-superuser-pw \
  --data-file=- --replication-policy=automatic 2>/dev/null \
  || printf '%s' "$PG_PW" | gcloud secrets versions add dma-insights-pg-superuser-pw --data-file=-

# Used by the migrations job — capture for §8.
export DMA_PG_SUPERUSER_PW="$PG_PW"
```

### 7b · App-user password rotation later

This `terraform apply` still evaluates the image data sources, so ensure
the images exist at `$SHA` first (builds if missing). Or just use
`recover-db-passwords.sh --rotate`, which wraps the same build-then-apply.

```bash
cd "$REPO_ROOT/apps/dma-insights/infra/terraform"
bash ../preflight-image-check.sh "$SHA"     # builds the 3 images if absent
terraform apply -replace=random_password.db_app_user \
  -var "project_id=$PROJECT_ID" -var "image_sha=$SHA" -auto-approve
```

---

## 8 · Run Alembic migrations (via Cloud Run Job)

Migrations run as the **`dma-insights-migrations` Cloud Run Job**
Terraform creates in §6 — never from Cloud Shell (5 GB RAM, OOMs on
`pip install`). The job uses the backend image, applies all 15
migrations (`001_extensions` through `015_runs_parser_warnings`), then
runs `app.scripts.post_migrate` to GRANT app-user privileges.

**Preferred (self-healing): use `infra/migrate.sh`.** This wrapper
verifies DB password state via `cloud-sql-proxy` first, runs
`recover-db-passwords.sh` automatically if drift is detected (heals the
`FATAL: password authentication failed for user "postgres"` failure
mode that recurs after Terraform replays / out-of-band password
changes), then triggers the migrations job and tails the last 30 log
lines.

```bash
cd "$REPO_ROOT/apps/dma-insights/infra"
./migrate.sh
```

Skip the verify step with `./migrate.sh --skip-verify` if you've just
ran `recover-db-passwords.sh` in the same shell. Use
`./migrate.sh --verify-only` to check drift without migrating.

**Manual fallback** (if you need to bypass the wrapper — same effect,
but you own the recovery decision):

```bash
PROJECT_ID="$(gcloud config get-value project)"

gcloud run jobs execute dma-insights-migrations \
  --region=us-central1 \
  --wait

# Confirm head + schema. Output ends with the most recent revision.
EXEC=$(gcloud run jobs executions list \
  --job=dma-insights-migrations --region=us-central1 --limit=1 \
  --format='value(name)')
gcloud beta run jobs executions logs read "$EXEC" --region=us-central1 | tail -20
# Expected last revision: 015_runs_parser_warnings
```

### 8a · What migration 015 adds (latest)

`015_runs_parser_warnings` (the most recent migration) adds two things
the QA audit identified as critical:

1. **`runs.parser_warnings JSONB`** — persists ingest-time warnings
   (e.g., subcap IDs from a v5.0/v6.x DMA that have no alias bridge to
   v7.0). Without this, those drops were silent and analysts couldn't
   audit them.
2. **`protect_active_entity_delete()` trigger** — blocks physical
   `DELETE` on entities with `status='ACTIVE'`. The CASCADE chain on
   `runs.entity_id → entities` would otherwise nuke all evidence +
   insights + recommendations in one stray DELETE. Hard-deletes still
   work for entities flipped to `status='ARCHIVED'` first.

**Verify after the job runs:**

```bash
# 1. Migration head
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT version_num FROM alembic_version;"
# Expected: 015_runs_parser_warnings

# 2. Trigger present
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT tgname FROM pg_trigger WHERE tgname = 'trg_protect_active_entity_delete';"
# Expected: trg_protect_active_entity_delete

# 3. Smoke-test the guard (must error)
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="DELETE FROM entities WHERE status='ACTIVE' LIMIT 1;"
# Expected error: cannot DELETE entity ... while status=ACTIVE
```

### 8b · Run migrations on every deploy that touches the schema

```bash
# Since 2026-05-24, deploy.sh builds images by default (no separate
# gcloud builds submit step needed). It is also idempotent — if the
# image already exists at $SHA, the build step short-circuits.
cd "$REPO/apps/dma-insights/infra"
./deploy.sh
# Then run migrations (also idempotent; alembic skips already-applied
# revisions). The script auto-widens alembic_version.version_num to
# VARCHAR(128) before the migration body runs, so revision-ID
# truncation can't recur (see §19 T14).
./migrate.sh
```

### 8c · Failed migration recovery

If the job exits non-zero:

```bash
# 1. Diagnose
gcloud beta run jobs executions list \
  --job=dma-insights-migrations --region=us-central1 --limit=5 \
  --format='table(name,status.completionTime,status.conditions[0].message)'

EXEC=$(gcloud run jobs executions list --job=dma-insights-migrations \
  --region=us-central1 --limit=1 --format='value(name)')
gcloud beta run jobs executions logs read "$EXEC" --region=us-central1
```

| Log line | Cause | Fix |
|---|---|---|
| `FATAL: password authentication failed for user "postgres"` | Cloud SQL postgres user password drifted from the secret. Common after manual `gcloud sql users set-password` or an earlier recovery script. | `cd $REPO_ROOT/apps/dma-insights/infra && ./recover-db-passwords.sh` then re-execute the migrations job. (See T15.) |
| `FATAL: password authentication failed for user "dma_insights"` | Same as above for the app user. | Same fix — `./recover-db-passwords.sh` heals both users in one shot. |
| `permission denied to create extension "vector"` | Job is using app user instead of superuser | `terraform apply -replace=null_resource.db_superuser_setup` |
| `permission denied for schema public` (during `post_migrate`) | App user missing schema grants. The migration job's `post_migrate.py` step does this, but if it was interrupted, GRANTs weren't applied. | Re-execute the migrations job — `post_migrate.py` is idempotent. |
| `connection refused on /cloudsql/...:5432` | Cloud SQL volume not mounted | Check `volume_mounts` block on `google_cloud_run_v2_job.migrations` |
| `ModuleNotFoundError: app.scripts.post_migrate` | Image SHA is older than this commit | Re-run §5 with current HEAD |
| `relation "..." already exists` | Stale state from a partial earlier run | Inspect with `gcloud sql connect`, drop the offending table, OR restore §18 from PITR |

### 8d · Migration rollback procedure

If you need to roll back to a prior revision (e.g., 015 caused
unexpected behaviour):

```bash
# 1. Update the job to run downgrade instead of upgrade
PRIOR_REV="014_build_qa_gates"
gcloud run jobs update dma-insights-migrations --region us-central1 \
  --args="alembic,downgrade,${PRIOR_REV}"

# 2. Execute
gcloud run jobs execute dma-insights-migrations --region us-central1 --wait

# 3. Confirm
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT version_num FROM alembic_version;"
# Expected: matches PRIOR_REV

# 4. CRITICAL — restore the job args to upgrade for next deploy
gcloud run jobs update dma-insights-migrations --region us-central1 \
  --args="alembic,upgrade,head"
```

---

## 9 · Share Drive folders with the service account

The `dma-insights-historical-backfill` Cloud Run Job (called in §11)
reads DMA folders directly from Google Drive using the Compute Engine
default SA. **Drive access is ONLY granted via per-folder ACLs in Google
Drive — there is NO project-level `roles/drive.reader` to grant.**

> ⚠ **Common misconception:** `roles/drive.reader` looks like a Cloud
> IAM role but is actually a Google Workspace / Drive-level role. If
> you grant it via `google_project_iam_member` or
> `gcloud projects add-iam-policy-binding`, the Cloud Resource Manager
> API rejects it with `Error 400: Role roles/drive.reader is not
> supported for this resource`. The Terraform module does NOT create
> such a binding (it used to in earlier revisions — that bug was
> removed). The actual permission grant is the per-folder share below.

**Get the SA email:**
```bash
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
echo "${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
# e.g. 306195530103-compute@developer.gserviceaccount.com
```

**Share the DMA Assets folder** (one-time):

1. Open Google Drive → navigate to **"DMA Assets"** folder
   (`1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`).
2. Right-click → **Share**.
3. Add `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` as **Viewer**.
4. Uncheck "Notify people" (service accounts have no inbox).
5. Save.

Do the same for:
- **Ops Sheet** (`1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8`)
- The Drive-reader SA (`dma-insights-drive@${PROJECT_ID}.iam.gserviceaccount.com`)

---

## 10 · Load the v7.0 capability catalogue

The 4 pillar workbooks live on your operator workstation (NOT in git).
Place them under `apps/dma-insights/docs/reference/catalogue/v7.0/`:

```
docs/reference/catalogue/v7.0/
  Pillar_1_Comprehensive_Capability_Mapping_v7.0.xlsx
  Pillar_2_Comprehensive_Capability_Mapping_v7.0.xlsx
  Pillar_3_Comprehensive_Capability_Mapping_v7.0.xlsx
  Pillar_4_Comprehensive_Capability_Mapping_v7.0.xlsx
```

Upload + trigger the loader:

```bash
PROJECT_ID="$(gcloud config get-value project)"

# Verify 4 files
ls "$REPO_ROOT/apps/dma-insights/docs/reference/catalogue/v7.0/"Pillar_*.xlsx | wc -l   # 4

# Upload
gsutil cp \
  "$REPO_ROOT/apps/dma-insights/docs/reference/catalogue/v7.0/"Pillar_*.xlsx \
  "gs://${PROJECT_ID}-catalogue-staging/v7.0/"

# Trigger. DO NOT pass --args=… — the job's command + args are baked
# by Terraform; overriding drops the module path.
gcloud run jobs execute dma-insights-ccg-loader --region us-central1 --wait
```

**Verify:**
```bash
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT COUNT(*) FROM ccg_subcaps WHERE version='v7.0';"
# Expected: 851

gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT version, frozen_at FROM ccg_catalog_versions;"
# Expected: v7.0 | <timestamp>
```

An admin then reviews the diff at `/admin/catalogue` and promotes
staging → canonical.

---

## 11 · Historical backfill — ingest the 115 prior DMAs

The `dma-insights-historical-backfill` Cloud Run Job reads DMA folders
**directly from Google Drive** via the Drive API (no GCS zip staging —
the QA audit replaced the old GCS-zip path). It iterates every folder
ending in ` - DMA` under the DMA Assets root, downloads each ingest-
worthy file, and runs the canonical `parse_package` + `persist_package`
pipeline.

**Prerequisites** (must be done first):
- §9 — DMA Assets folder shared with the SA
- §10 — v7.0 catalogue loaded (older subcaps alias-bridge through this)
- §8 — migration 015 applied (`runs.parser_warnings` exists)

**Old-DMA tolerance:** the parser does NOT force v7.0. Runs scored
against v5.x/v6.x preserve their original `runs.ccg_catalog_version` and
their subcap IDs flow through `ccg_subcap_aliases` at read time. Truly
unresolved IDs land in `runs.parser_warnings` as audit warnings — never
silently dropped. The Runs page shows `data_source='DRIVE_BACKFILL'`
on each (a v2 fix; previously they were mis-labelled `MANUAL_BACKFILL`).

**Trigger the job:**
```bash
gcloud run jobs execute dma-insights-historical-backfill \
  --region us-central1 \
  --wait

# Watch live logs
gcloud logging read \
  'resource.type="cloud_run_job" AND resource.labels.job_name="dma-insights-historical-backfill"' \
  --limit 200 --format "value(textPayload)" --freshness 30m
```

Expected final log line:
```
historical_backfill: 115/115 ingested, 0 skipped, 0 failed.
```

Re-running is safe — already-ingested folders are skipped (idempotent
via `runs.request_id` / `runs.drive_folder_id` uniqueness).

**Audit any warnings:**
```bash
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT request_id, ccg_catalog_version, jsonb_array_length(parser_warnings) AS n_warnings FROM runs WHERE jsonb_array_length(parser_warnings) > 0 ORDER BY n_warnings DESC LIMIT 10;"
# Expected: rows where old subcap IDs from v5.x/v6.x couldn't be resolved
# to v7.0. Each warning includes the original subcap_id + the reason.
```

**Alternative — per-package upload via admin UI:** for one-off ingests,
sign in as admin → `/admin/ingest` → drag a `.zip` onto the dropzone.
Both paths converge in `persist_package`; warnings show in
`/admin/imports/audit`.

### 11.1 · Repopulate after an extraction-quality fix (data-quality wave)

When the parser/extractor logic changes (e.g. the 2026-06-23 leadership +
insight-card + tech-stack-prototype wave), the **code** ships with the deploy
but the **already-persisted rows** still hold the old extraction. The
`app/scripts/diagnose_extraction.py` corpus harness proves the new coverage
against the 113 fixture packages locally (no DB); production data is refreshed
by re-running the pipeline in this order:

```bash
# 0. Apply the schema change (e.g. 044 adds tech_stack_entries.l3_id +
#    normalises status onto the DETECTED|CONFIRMED|CONFIRMED_REMOVED enum).
alembic upgrade head        # head=062_recommendation_fit_fields

# 1. Tech stack + insight cards + firmographics.leadership are written by
#    parse_package/persist_package, so a re-ingest re-runs the new extractors
#    over every package. Idempotent (skips nothing on --force):
gcloud run jobs execute dma-insights-historical-backfill --region us-central1 --wait
#    (or per-package via /admin/ingest for a spot refresh.)

# 2. Leadership + insights ALSO have in-place derive backfills that don't
#    require a full re-ingest — run them to repopulate just those columns
#    for entities whose firmographics.leadership / top_findings are empty:
python -m app.scripts.derive_leadership      # fills firmographics.leadership
python -m app.scripts.derive_insights        # (re)derives insight_cards + top_findings

# 3. Refresh the no-backend first-paint pack so the static snapshot matches:
python -m app.scripts.export_startup_data --out ../startup-data --sha $(git rev-parse --short HEAD)
python -m app.scripts.export_startup_pages
```

Verify with the corpus harness (any env, no DB):
`python -m app.scripts.diagnose_extraction` → expect leadership ~76/113,
insight `so_what` ~94%, zero old-style synthetic titles, tech `status_enum`
== all rows, `l3_id` ≥ ~300 rows.

---

## 12 · Verify the deploy

```bash
# Re-derive REPO_ROOT in case this is a fresh shell — falls back to a
# git lookup if the §1 export was lost. Refuses to assume $HOME/Accelerate.
REPO_ROOT="${REPO_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -d "$REPO_ROOT/apps/dma-insights/infra/terraform" ] \
  || { echo "::error::REPO_ROOT=$REPO_ROOT is not the dma-insights repo — re-run §1"; exit 1; }
BACKEND=$(terraform -chdir="$REPO_ROOT/apps/dma-insights/infra/terraform" output -raw backend_url)
FRONTEND=$(terraform -chdir="$REPO_ROOT/apps/dma-insights/infra/terraform" output -raw frontend_url)
SHA="$(cat /tmp/dma-insights-deploy-sha)"

echo "  frontend: ${FRONTEND}"
echo "  backend:  ${BACKEND}"
```

### 12.0 · Freshness verification (NEW — answers "is the live revision really my latest commit?")

**Easiest:** run the standalone diagnostic:

```bash
cd "$REPO/apps/dma-insights/infra"
./verify-deploy.sh
```

It runs all four layers below + a backend health check, prints a
state-branch table inline, and exits with the count of failed layers
(0 = all green). Use as a CI gate.

---

**Manual** (if you want to inspect each layer yourself):

```bash
SHA="$(git -C "$REPO" rev-parse --short HEAD)"
FE="$FRONTEND"

# Layer 1 — Cloud Run revision is pinned to the new image SHA
LIVE_IMAGE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(spec.template.spec.containers[0].image)')
LIVE_SHA="${LIVE_IMAGE##*:}"
[[ "$LIVE_SHA" == "$SHA" ]] \
  && echo "✓ Cloud Run image tag: $LIVE_SHA == HEAD" \
  || echo "✗ Cloud Run image tag: $LIVE_SHA != HEAD ($SHA)"

# Layer 2 — Live HTML carries the build-SHA stamp
META_SHA=$(curl -s "$FE/" | grep -oE '<meta name="x-build-sha" content="[^"]+"' \
             | head -1 | sed -E 's/.*content="([^"]+)".*/\1/')
[[ "$META_SHA" == "$SHA" ]] \
  && echo "✓ Live HTML stamped: x-build-sha=$META_SHA" \
  || echo "✗ Live HTML stamped: x-build-sha=$META_SHA (expected $SHA)"

# Layer 3 — Source files (.jsx etc) carry no-cache headers
curl -sI "$FE/src/app-root.jsx" | grep -i 'cache-control'
# Expected: cache-control: no-cache, no-store, must-revalidate
```

If all three pass, the deploy is fully live and no browser can serve a
stale view longer than one navigation.

The Dockerfile **also** appends `?v=<sha>` to every `<script src="src/…">`
and vendor URL at build time. This is defence-in-depth: even if a CDN
edge stubbornly caches the old file, the URL is different on the new
revision so the cache lookup misses → fresh fetch guaranteed.

### 12.0a · "I deployed but the UI looks identical to before" — diagnostic

Run all three layers above. The state branches are:

| Layer-1 | Layer-2 | Layer-3 | What it means / what to do |
|---|---|---|---|
| ✓ | ✓ | ✓ | Deploy is fully live. The change you expected really IS in this build — verify your fix is in the standalone-src/ tree (`grep -l <symbol> apps/dma-insights/frontend/standalone-src/src/`). |
| ✓ | ✗ | ✓ | New image is rolled out but its `<meta>` stamp shows an older SHA → you're hitting a stale CDN edge cache for `/index.html`. Wait 5 min OR force-promote: `gcloud run services update-traffic dma-insights-frontend --region=us-central1 --to-latest` |
| ✗ | — | — | Cloud Run revision still serves the old image. Force-promote (above). |
| ✓ | ✓ | ✗ | nginx config older than 9b293ea — rebuild: `./deploy.sh` (auto-detects + rebuilds). |

### 12a · Liveness + readiness

```bash
# /healthz — always 200
curl -sf "${BACKEND}/healthz" | jq .
# Expected: {"status":"ok"}

# /readyz — probes DB + Redis (QA-audit-v2 fix)
curl -sf "${BACKEND}/readyz" | jq .
# Happy path:  {"status":"ready"}
# Redis blip:  {"status":"ready","redis":"down: ..."}    (still 200 — soft dependency)
# DB down:     HTTP 503                                  (Cloud Run drains the instance)

curl -sf "${FRONTEND}/healthz"
# Expected: "ok"
```

### 12b · API surface

```bash
# OpenAPI spec (≥48 routes after QA audit added /api/v1/prospecting)
curl -sf "${BACKEND}/openapi.json" | jq '.paths | length'   # ≥ 48

# OAuth callback resolves
curl -sI "${BACKEND}/api/v1/auth/google" | head -1   # HTTP/2 200

# All bearer-gated routes 401 without credentials
curl -sI "${BACKEND}/api/v1/rag/evidence" | head -1  # HTTP/2 401
```

### 12c · IAM bindings (QA-audit fix)

```bash
# Vertex IAM binding — without this, every Gemini call returns 403
gcloud projects get-iam-policy "$PROJECT_ID" --format=json | \
  jq -r '.bindings[] | select(.role == "roles/aiplatform.user") | .members[]'
# Expected: serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com

# Drive access is NOT a project IAM role — it's a per-folder ACL.
# Verify the SA appears on the DMA Assets folder's share list manually
# in Google Drive (see §9). There is no gcloud command for this.
```

### 12d · Sign-in + dashboard

```bash
# Open the frontend in an Incognito window (clears stale auth cache)
echo "${FRONTEND}"
```

Expected flow:
1. LoginPage renders (centered card, Zennify logo, Google sign-in button).
2. Click "Sign in with Google" → consent screen → return to `/`.
3. Dashboard renders with empty-state tiles (no runs yet on a fresh DB).

If sign-in fails with `Error 400: origin_mismatch` → see §19 T3.

### 12e · 16 surfaces functional

After §11 backfill, every page should render data:

| Route | Expected |
|---|---|
| `/` | Dashboard with active-runs + alerts tiles |
| `/clients` | Directory with entity rows |
| `/clients/:id/overview` | ScoreRing, WhyNowStrip with "Why this matters →" CTA |
| `/clients/:id/insights` | Insight cards, click card → modal with "Explain with AI →" |
| `/clients/:id/heatmap` | Pillar/category/capability/subcap zooms |
| `/clients/:id/platform` | 5 platform cards, each with a Fit Score number, Readiness traffic-light, and "Generate AI pitch →" CTA |
| `/clients/:id/context` | Timeline + Gantt + financials (Analyst+) |
| `/clients/:id/health` | Alerts + Evidence Age + Version Diff + Patterns + Gates (Analyst+) |
| `/clients/:id/techstack` | 4-layer grid |
| `/clients/:id/techstack/:techId` | Detail page |
| `/clients/:id/runs` | Run history with `DRIVE_BACKFILL` badges |
| `/alerts` | Alerts list |
| `/prospecting` | Entity table (no 404 — see 12g below) |
| `/admin` | Users + QA gates + Catalogue queue |
| `/admin/import/audit` | File audit ledger |

### 12f · platform_scores persisted at ingest time

```bash
# Confirm platform fit + readiness are persisted (not just on-the-fly)
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT platform_id, fit_score, readiness_index, state, jsonb_array_length(prerequisite_checks) AS prereqs FROM platform_scores WHERE run_id = (SELECT id FROM runs ORDER BY completed_at DESC NULLS LAST LIMIT 1);"
# Expected: 5 rows (salesforce, databricks, tableau, twilio, ncino)
# fit_score > 0, prereqs > 0, state IN ('READY','INSUFFICIENT_EVIDENCE')
# readiness_index IN ('green','amber','red')
```

### 12g · /prospecting endpoint

```bash
# QA-audit-v2 added this router; pre-fix it 404'd.
JWT="$(curl -s -X POST -H 'Content-Type: application/json' \
  -d '{"id_token":"<paste a real Google id_token>"}' \
  "${BACKEND}/api/v1/auth/google" -i \
  | grep -oP 'dma_session=\K[^;]+' | head -1)"
curl -sf -b "dma_session=$JWT" "${BACKEND}/api/v1/prospecting" | jq '.filter_counts'
# Expected: {"low_maturity": N, "stale_run": N, "unassigned": N}
```

### 12h · AI chat surfaces reachable

In the browser, sign in and verify each surface streams tokens:

| Surface | How to trigger |
|---|---|
| `subcap_narrative` | `/clients/:id/heatmap` → click any subcap cell → SynthesisDrawer opens with streaming AI narrative |
| `why_now` | `/clients/:id/overview` → "Why this matters →" button on WhyNowStrip |
| `insight_explanation` | `/clients/:id/insights` → click any IC card → modal → "Explain with AI →" |
| `platform_story` | `/clients/:id/platform` → any READY card → "Generate AI pitch →" |
| `meeting_prep` | (CTA placement pending — backend ready, Pro-model rate-limited) |

Each panel must:
- Stream tokens character-by-character (provisional render).
- End with a `done` event + clickable cited E-ID chips (chips open EvidenceDrawer).
- Fall back to a "Insight withheld" message if V1-V3 validators flag fabricated IDs.

### 12i · Old-DMA alias bridge

Open the heatmap for any entity ingested in §11. Cells from v5.x/v6.x
runs render via alias bridge; you may see an "aliased from v5.0" pill
on individual cells. Never empty/missing cells unless the subcap was
truly dropped in v7.0 (then it's in `runs.parser_warnings`).

### 12j · JWT-expiry handler (QA-audit-v2)

```text
1. Sign in.
2. DevTools → Application → Cookies → delete `dma_session`.
3. Navigate to `/clients`.
Expected: LoginPage renders instantly (NOT a "Couldn't load entities"
banner). This is the `dma:auth-expired` global event firing.
```

### 12k · Cache wipe on logout (QA-audit-v2)

```
1. Sign in as User A → load a client → log out.
2. Sign in as User B → DevTools → Application → IndexedDB → "dma-insights-query-cache".
Expected: store is empty. The QA-audit fix calls
`queryClient.clear() + idb.clear()` on logout.
```

---

## 13 · Map a custom domain (optional)

```bash
gcloud beta run domain-mappings create \
  --service dma-insights-frontend \
  --domain dma-insights.zennify.com \
  --region us-central1
```

Add the CNAME record Cloud Run prints to your DNS. Google-managed SSL
provisions in ~10 min.

**After custom domain is live:** remove the raw `*.run.app` entries
you added to the OAuth client in §3.

---

## 14 · Wire the Clay enrichment connector

Clay can't sign requests on egress (no `hmac_sha256()` accessor in HTTP
API enrichments). The setup uses a Cloud Function signing relay in
front of `/api/v1/clay/webhook`.

### 14a · Create the Clay table

1. Clay → + New Table → `DMA Insights — Entity Enrichment`.
2. Input columns: `entity_id`, `domain`, `name`, `ticker`.
3. Enrichment columns:
   - **Find Company** → `aum_usd`, `revenue_usd`, `headcount`, `hq_address`, `primary_regulator`.
   - **Find People** → `leadership` as JSON `[{name, title, tenure, linkedin_url}]`.
   - **Find Articles & Posts** → `thought_leadership` as JSON.

### 14b · Receive entity-refresh triggers (Monitor webhook source)

4. **+ Add at bottom → Source → Monitor webhook**. Clay generates a URL
   like `https://api.clay.com/v3/sources/webhook/<id>/pull` — this is
   `CLAY_WEBHOOK_URL`.

### 14c · Deploy the signing relay

```bash
PROJECT_ID="$(gcloud config get-value project)"
REGION=us-central1

# Generate the shared secret
openssl rand -hex 32 | gcloud secrets versions add dma-insights-clay-webhook-secret --data-file=-

# Relay source lives under infra/clay-relay/{main.py,requirements.txt}
# in the repo (extracted from this doc's heredocs in 2026-05-30 —
# heredocs in markdown were Cloud Shell paste hazards). Point gcloud
# functions at the source dir directly; no /tmp staging needed.
RELAY_SRC="$REPO_ROOT/apps/dma-insights/infra/clay-relay"
BACKEND_URL="$(terraform -chdir="$REPO_ROOT/apps/dma-insights/infra/terraform" output -raw backend_url)"
gcloud functions deploy dma-insights-clay-relay \
  --gen2 --region="$REGION" --runtime=python312 \
  --entry-point=relay --source="$RELAY_SRC" \
  --trigger-http --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},DMA_BACKEND_URL=${BACKEND_URL}"

RELAY_URL="$(gcloud functions describe dma-insights-clay-relay --gen2 --region="$REGION" --format='value(serviceConfig.uri)')"
echo "  RELAY_URL=$RELAY_URL"
```

5. Back in Clay → **+ Add Enrichment → HTTP API**:
   - Method: `POST`
   - Endpoint: `$RELAY_URL` from above
   - Headers: `Content-Type: application/json`
   - Body: map every output column via `/colname` references.

### 14d · Wire the webhook URL into our backend

```bash
echo -n "https://api.clay.com/v3/sources/webhook/<id>/pull" | \
  gcloud secrets versions add dma-insights-clay-webhook-url --data-file=-

# Roll the backend revision to pick up the new env values
gcloud run services update dma-insights-backend --region us-central1 \
  --update-env-vars=CLAY_ROLL_VAR="$(date +%s)"
```

### 14e · Smoke-test

```bash
# 1. Trigger an enrichment for an entity
curl -X POST -b "dma_session=$JWT" \
  "${BACKEND}/api/v1/clay/enrich/<entity_uuid>"
# Expected: {"entity_id":"…","status":"accepted","table_run_id":null}

# 2. Simulate Clay → relay → backend
SECRET="$(gcloud secrets versions access latest --secret=dma-insights-clay-webhook-secret)"
BODY='{"entity_id":"<entity_uuid>","leadership":[{"name":"A","title":"CEO"}]}'
SIG="sha256=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET" -hex | cut -d ' ' -f2)"
curl -X POST -H "X-Clay-Signature: $SIG" -H "Content-Type: application/json" \
  -d "$BODY" "${BACKEND}/api/v1/clay/webhook"
# Expected: 204 No Content
```

Fail-closed: if `dma-insights-clay-webhook-secret` is empty, the
backend `verify_signature` rejects every inbound webhook with 401.

---

## 15 · Wire the DMA Bot loop

The DMA Bot is already deployed at
`https://dma-bot-306195530103.us-central1.run.app`. Hand it our
bot-api-key + canonical `/ingest/assessment` URL:

```bash
BACKEND="$(terraform -chdir="$REPO_ROOT/apps/dma-insights/infra/terraform" output -raw backend_url)"
gcloud run services update dma-bot \
  --region us-central1 \
  --update-env-vars \
    "DMA_INSIGHTS_BASE_URL=${BACKEND}" \
    "DMA_INSIGHTS_BOT_API_KEY=$(gcloud secrets versions access latest --secret=dma-insights-bot-api-key)"
```

**End-to-end test:**
1. In DMA Insights, click "+ Request DMA", attach materials, submit.
2. Watch the Ops Sheet `Requests` tab — a new row appears within 5s
   with `REQ-{8 hex}` + `status=pending`.
3. When the Claude project finishes, the bot POSTs to
   `${BACKEND}/api/v1/ingest/assessment` with `Bearer <key>`. Our run
   flips to `ACTIVE` and SSE wakes the Dashboard tile.

---

## 16 · Promote a new image SHA later

After §6 the cluster is running. To roll a new commit (Cloud Shell or
any workstation with `gcloud` + `git`):

```bash
# 1. Pull latest changes
export REPO="$HOME/Accelerate"
cd "$REPO"
git pull origin claude/deploy-zennify-cloud-run-AUdu6

# 2. ONE COMMAND — builds images + applies + verifies. Idempotent;
#    rerun safely. State branches are documented in the script header.
cd "$REPO/apps/dma-insights/infra"
./deploy.sh

# 3. Migrations (only if the commit touched alembic/versions/; the
#    script itself is idempotent so it's safe to run every time)
./migrate.sh
```

The script does, in order:
1. Detect $SHA from git HEAD (or honour `SHA=<sha>` env override).
2. Check gcr.io for all 3 images at $SHA. If present, skip the build.
3. Otherwise `gcloud builds submit` runs the 6-stage Cloud Build.
4. `terraform apply` (with IPv4 kernel mitigation + escalating-
   parallelism retry).
5. Post-deploy verifies `gcloud run services describe` for both
   backend + frontend report image tag = $SHA AND the frontend
   serves `Cache-Control: no-cache` on `.jsx` files.
6. Exits non-zero with actionable hints if any check fails.

### 16a · Force-promote when verification reports drift

Sometimes Cloud Run creates the new revision but keeps serving traffic
on the old one (this happens when the readiness probe of the new
revision flaps once). Force-promote both services:

```bash
for svc in dma-insights-backend dma-insights-frontend; do
  gcloud run services update-traffic "$svc" \
    --region=us-central1 --to-latest
done
./deploy.sh --skip-build --skip-verify     # re-runs apply + verify only
```

### 16b · Skip the build (advanced)

If you've already built the images (`gcloud builds list` shows a SUCCESS
at the SHA you want), you can shave ~4 minutes by skipping the build
step:

```bash
./deploy.sh --skip-build                   # apply + verify only
```

The script will refuse to proceed if fewer than 3 images exist at
the target SHA — protects against accidental "stale image" deploys.

---

## 17 · Day-2 ops

| Task | Command |
|---|---|
| Rotate any secret | `echo -n NEW \| gcloud secrets versions add <name> --data-file=-` (revision auto-restarts) |
| Promote a new SHA | See §16 |
| Tail backend logs | `gcloud logging tail "resource.type=cloud_run_revision AND resource.labels.service_name=dma-insights-backend"` |
| Pause a Scheduler trigger | `gcloud scheduler jobs pause <name> --location us-central1` |
| Replay one Ops sheet row | `gcloud run jobs execute dma-insights-sheet-poller --args=--once,--row=<row_id>` |
| Re-embed everything (model bump) | `gcloud run jobs execute dma-insights-embedder --args=--rebuild,--model=text-embedding-005` |
| Catalogue diff UI | navigate to `/admin/catalogue` |
| Build QA gate ledger | navigate to `/admin/build-qa` |
| Import audit | navigate to `/admin/import/audit` |
| Verify backups enabled | See §18a |

---

## 18 · Disaster recovery

### 18a · Cloud SQL backups + PITR

Verify backups + point-in-time recovery are enabled:

```bash
gcloud sql instances describe dma-insights-pg \
  --format='value(settings.backupConfiguration.enabled,
                  settings.backupConfiguration.pointInTimeRecoveryEnabled,
                  settings.backupConfiguration.startTime,
                  settings.backupConfiguration.backupRetentionSettings.retainedBackups)'
# Expected: True True 03:00 7
```

If PITR is disabled:
```bash
gcloud sql instances patch dma-insights-pg --enable-point-in-time-recovery
```

### 18b · Restore from a backup (emergency only)

```bash
# List backups
gcloud sql backups list --instance=dma-insights-pg

# Restore to a NEW instance (NEVER overwrite live data)
gcloud sql backups restore <BACKUP_ID> \
  --restore-instance=dma-insights-pg-restored \
  --backup-instance=dma-insights-pg

# After verifying the restored instance, swap DSN secret to point at it
# and promote a new backend revision via terraform apply.
```

### 18c · Migration rollback

If a migration broke production, follow §8d (Failed migration rollback)
to downgrade via the Cloud Run Job.

### 18d · Other failure modes

| Failure | Recovery |
|---|---|
| Cloud SQL primary loss | REGIONAL HA fails over to standby; DSN unchanged. |
| Cloud Run cold-start storms | Bump `min_instance_count` in `main.tf` and re-apply. |
| Stuck Cloud Run Job | `gcloud run jobs executions cancel <execution>` then re-execute. |
| Bad image rolled out | `./deploy.sh` with a known-good `SHA=<prior_sha>`. |
| Catalogue corrupted | Revert to a prior frozen `ccg_catalog_versions.version`; `ccg_subcap_aliases` keeps every saved run readable. |
| Clay table deleted | Clear `dma-insights-clay-webhook-url`; D1 falls back to package-supplied leadership. |
| OAuth client revoked | Recreate per §3; update `dma-insights-oauth-client-secret`; revision restarts automatically. |
| pgvector indexes corrupted | `REINDEX INDEX CONCURRENTLY ix_evidence_embeddings_cosine;` (RAG goes seq-scan during rebuild). |
| Accidental `DELETE FROM entities` | **Blocked by migration 015 trigger** for `status='ACTIVE'` rows. Archive first if you really need to hard-delete. |
| Stray `DELETE` of ARCHIVED entity nuked children | Restore from PITR (§18b) — that's why backups exist. |

### 18f · Backfill order (cold-starting the AI layer)

When standing up a fresh environment or recovering from a full data
wipe, the AI layer's components have strict dependencies. Run them
in this order — running out of order produces empty tables or
inconsistent embeddings.

```
1.  alembic upgrade head                # 016+ migrations + AI tables
2.  ccg_loader v7.0                     # catalogue rows must exist before
                                        # any subcap_score persists
3.  POST /ingest/package per zip        # entities + runs + subcap_scores +
                                        # evidence_index + recommendations
4.  workers/embedder --run-id <UUID>    # vectors for evidence_index +
                                        # insight_cards + recommendations
                                        # (no archetype work yet)
5.  workers/peer_patterns --all         # peer_archetypes per subvertical
                                        # — REQUIRES step 4 done so all
                                        # subcap_scores for the cohort exist
6.  workers/chat_learning --since …     # chat_learning_signals — REQUIRES
                                        # chat_messages embeddings (which
                                        # are written inline by the worker
                                        # when missing; safe to run last)
```

### State-branch invariants

- **embedder before peer_patterns**: peer_patterns reads subcap_scores
  directly (not embeddings), so technically can run before the embedder.
  But running embedder first guarantees `evidence_embeddings` is non-
  empty, which makes the cohort-similarity SQL in /rag/evidence return
  results — otherwise that endpoint silently returns [].
- **peer_patterns before /entities/{id}/archetype** is consumed by the
  frontend: the frontend handles `insufficient_data=True` gracefully,
  but without this worker run the chip never appears.
- **chat_learning needs ≥ 1 chat_feedback row** to write any signal rows.
  If feedback hasn't been collected yet the worker exits 0 with
  signals_written=0 — that's expected behavior, not a bug.

### Cloud Scheduler triggers

| Worker | Frequency | Why |
|---|---|---|
| `embedder` | Pub/Sub `dma.ingest.completed` (event-driven) | Embed within minutes of ingest |
| `peer_patterns` | weekly (Sunday 02:00 UTC) | Archetypes change slowly; weekly is plenty |
| `chat_learning` | nightly (03:00 UTC) | Pick up the previous day's feedback |

### 18e · Data-loss matrix

| Scenario | Likelihood | Mitigation |
|---|---|---|
| Hard-delete entity | Blocked by trigger for ACTIVE; PITR restore for ARCHIVED | ✅ |
| Redis flush mid-SSE | Tokens already in user's screen; full text re-fetchable via DB | ✅ |
| Vertex 429 mid-stream | Vertex retry/backoff (QA fix); falls back to template if exhausted | ✅ |
| IndexedDB cross-user | Cache cleared on logout (QA fix) | ✅ |
| Migration failure | §8c diagnosis → §8d rollback | ✅ |
| Catalogue ingest failure | Loader is admin-approval-gated; staging schema isolates | ✅ |

---

## 19 · Troubleshooting

### T1 — `dial tcp [2a00:1450:…]:443: connect: cannot assign requested address`

**Cause:** Cloud Shell's IPv6 NAT pool is unreliable. `GODEBUG=netdns=go`
alone is insufficient — Go's Happy Eyeballs algorithm still tries IPv6
addresses first when AAAA records exist. The kernel-level disable is
the only fully reliable mitigation.

**Fix (preferred):** the deploy wrapper now:
1. Disables IPv6 at the kernel level via `sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1` (Cloud Shell allows passwordless sudo).
2. Sets `GODEBUG=netdns=go` as a fallback.
3. Retries with escalating-parallelism (10 → 4 → 2 → 1) so even if a few requests fail, the next attempt has fewer concurrent races.

```bash
cd "$REPO_ROOT/apps/dma-insights/infra" && ./deploy.sh
```

**Fix (manual, when not using the wrapper):**
```bash
# 1. Disable IPv6 at kernel level (most reliable)
sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1
sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1

# 2. Belt-and-suspenders Go resolver
export GODEBUG=netdns=go

# 3. Ensure images exist at the SHA (builds if missing), then apply
cd "$REPO_ROOT/apps/dma-insights/infra/terraform"
SHA="$(cat /tmp/dma-insights-deploy-sha)"
bash ../preflight-image-check.sh "$SHA"
terraform apply \
  -var "project_id=$(gcloud config get-value project)" \
  -var "image_sha=${SHA}" \
  -parallelism=2 \
  -auto-approve
```

**Fix (if sudo unavailable):** sudo is needed for the kernel disable.
Cloud Shell typically allows it; if your shell doesn't, run once:
```bash
sudo true     # primes the sudo cache; no actual change
./deploy.sh   # now disable_ipv6_at_kernel will succeed
```

**If IPv6 keeps failing even after all the above:** the Cloud Shell
NAT pool is in a bad state. See **T12**.

### T2 — `Error 403: project 'latest'` / variable-validation error

**Cause:** ran `terraform plan` / `apply` without `-var` flags and typed
`latest` at the prompt.

**Fix:** always use the deploy wrapper — it injects variables. The
Terraform module now has validation blocks that reject inputs like
`latest` with a descriptive error before any API calls fire.

If you must run terraform directly (ensure images exist first — builds
if missing):
```bash
SHA="$(cat /tmp/dma-insights-deploy-sha)"
bash ../preflight-image-check.sh "$SHA"
terraform apply \
  -var "project_id=$(gcloud config get-value project)" \
  -var "image_sha=${SHA}" \
  -auto-approve
```

The `terraform.tfvars` file provides `project_id = "digital-maturity-assessor"`
as a default; `image_sha` must always be supplied explicitly.

### T3 — `Error 400: origin_mismatch` during Google sign-in

**Cause:** the OAuth web client doesn't list the URL the browser is
hitting. Until §13 (custom domain) is complete, the live frontend is
the raw `*.run.app` URL — that origin must be on the OAuth allowlist.

**Fix:**
1. Console → APIs & Services → Credentials → click `dma-insights-web`.
2. Add `$(terraform -chdir=…/terraform output -raw frontend_url)` to
   **Authorized JavaScript origins**.
3. Add the same URL with `/api/v1/auth/google/callback` appended to
   **Authorized redirect URIs**.
4. Save. Wait 30s. Hard-refresh in Incognito.

Cannot be automated via Terraform — `google_iap_brand` only manages
IAP-protected clients, not standard OAuth 2.0 web clients.

### T4 — `terraform plan` fails with "Secret X not found"

**Cause:** the QA-audit fix added `data` blocks that require all
out-of-band secrets (`dma-insights-{redis-url, oauth-client-secret,
bot-api-key, rag-api-key}`) to exist before plan runs.

**Fix:** re-do §4b for the missing secret(s), then retry plan.

### T5 — `Image 'gcr.io/…:<sha>' not found` during apply

**Cause:** the SHA you passed isn't in gcr.io. Common causes:
- `git pull` advanced HEAD between §5 build and §6 apply.
- Docker push silently failed in §5.

**Fix:**
```bash
# Diagnose which SHAs exist
for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
  gcloud container images list-tags "gcr.io/$PROJECT_ID/$img" \
    --format='table(digest.slice(7:19),tags.join(","),timestamp.datetime)' --limit=5
done
# Pick a SHA all three images have, OR re-run §5 with current HEAD.
```

### T6 — IntelligencePanel shows only "fallback" / never streams

**Cause:** the Cloud Run backend SA doesn't have `roles/aiplatform.user`.

**Fix:**
```bash
gcloud projects get-iam-policy "$PROJECT_ID" --format=json | \
  jq -r '.bindings[] | select(.role == "roles/aiplatform.user") | .members[]'
# If missing the Compute Engine default SA — re-run §6 (deploy.sh).
# The QA-audit fix added this binding to terraform; old deploys lacked it.
```

### T7 — Historical backfill returns "0 ingested"

**Cause:** the SA doesn't have read access to the Drive folder.

**Fix:** §9 — share the DMA Assets folder with
`<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` as Viewer.

### T8 — `/readyz` returns 503 in prod

**Cause:** the DB is unreachable. Cloud Run is correctly draining the
instance.

**Diagnose:**
```bash
gcloud sql instances describe dma-insights-pg \
  --format='value(state,settings.activationPolicy)'
# Expected: RUNNABLE / ALWAYS
```
If state isn't `RUNNABLE`, see §18d.

### T9 — Sign-in works but every page shows "Couldn't load"

**Cause:** the backend can connect to the DB but the app user lacks
schema privileges (migration ran but `post_migrate` didn't).

**Fix:**
```bash
gcloud run jobs execute dma-insights-migrations --region us-central1 --wait
# This is idempotent — it re-runs `post_migrate` which GRANTs USAGE
# + ALL on public schema to the dma_insights user.
```

### T10 — SSE stream stuck at "Reconnecting…"

**Cause:** Redis is unreachable.

**Diagnose:**
```bash
curl -sf "${BACKEND}/readyz" | jq .
# Look for {"status":"ready","redis":"down: ..."}
```

**Fix:** check Upstash / Memorystore console; rotate the URL via §4d
if the connection string changed.

The QA-audit added an `error` event the frontend listens for — users
see "Reconnecting…" instead of a frozen panel.

### T14 — `StringDataRightTruncation: value too long for type character varying(32)` during `migrate.sh`

**Symptom (verbatim from the Cloud Run Job logs):**
```text
INFO  [alembic.runtime.migration] Running upgrade 020_job_executions
  -> 021_runs_data_source_drive_backfill, …
psycopg.errors.StringDataRightTruncation:
  value too long for type character varying(32)
[SQL: UPDATE alembic_version SET version_num='021_…' WHERE …]
```

**Root cause:** alembic's `alembic_version.version_num` column is
VARCHAR(32) by default. Any revision ID longer than 32 chars fails
the version-tracking UPDATE — the migration body actually executes,
but the bookkeeping write fails and the whole transaction rolls back.
The failure is opaque because nothing in the error mentions the column.

**Author-time guard (already in repo):**
- `tests/test_migration_id_lengths.py` parameterises over every
  migration file and asserts revision ID length ≤ 32 chars.
- `alembic/env.py` widens the column to VARCHAR(128) at the start of
  every online run (idempotent — short-circuits when already wide).
- The offending revision was renamed `021_runs_data_source_drive_backfill`
  → `021_runs_drive_backfill` (35 → 23 chars).

**Live-DB recovery for an environment that already saw this failure:**

Two acceptable paths. **Path A (preferred)** is the new release
landing the env.py widener — re-run `migrate.sh`; the widener runs
before the next migration attempt, the row UPDATE succeeds, alembic
catches up to head. Path B is the manual hot-fix for environments
that can't redeploy immediately.

```bash
# ── Path A (preferred): redeploy + re-run migrate
cd "$REPO/apps/dma-insights/infra"
./deploy.sh                       # ships env.py widener
./migrate.sh                      # widener runs, then 021 lands cleanly

# ── Path B (manual hot-fix): widen the column directly first
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);"
# Re-run the failed job
gcloud run jobs execute dma-insights-migrations --region=us-central1 --wait
```

**Verify recovery:**
```bash
gcloud sql connect dma-insights-pg --user=postgres -d dma_insights \
  --command="SELECT version_num, character_maximum_length(version_num::text)
             FROM alembic_version, information_schema.columns
             WHERE table_name='alembic_version' AND column_name='version_num';"
# Expected: version_num = '021_runs_drive_backfill', length = 128
```

**Why this is now defence-in-depth instead of a one-time fix:**
1. CI test fails any new migration with a 33+ char ID at PR time.
2. env.py widener ALTERs the column to 128 on every alembic run,
   so even if (1) is ever bypassed the prod DB tolerates it.
3. Filename-↔-revision-ID drift is also CI-guarded
   (`test_filename_matches_revision_id`).
4. down_revision integrity is CI-guarded (`test_down_revisions_resolve`).

### T13 — "Admin page still has same issues" / "fix appears not applied" / fix in git but UI unchanged

**Symptom:** A fix was committed + pushed (visible in `git log`) but
the live admin / dashboard / heatmap page in the browser still shows
the prior behaviour — buttons still spin forever, role toggle absent,
old layout, etc.

**Causes (in order of likelihood):**

1. **Live revision is at an older SHA.** Each git push does NOT auto-
   deploy. Cloud Build + `terraform apply` must run to produce a new
   image and roll out a new Cloud Run revision.

2. **Browser cache.** Before the nginx hardening in this batch the
   `.jsx` files were cached by the browser + Cloud Run edge for hours.
   A redeploy was invisible until the operator hard-refreshed.
   Mitigation: nginx now sends `Cache-Control: no-cache, no-store,
   must-revalidate` for all `.html|.jsx|.js|.json|.css|.map` paths.
   Old sessions opened before this batch still need ONE hard refresh
   to pick up the new headers; thereafter every `terraform apply` is
   visible on next navigation.

3. **Wrong file edited.** The live AE-facing UI is served from
   `frontend/standalone-src/`, NOT `frontend/src/`. The `src/` tree
   is for tests + future iteration only. Verify your edit landed in
   the standalone tree:
   ```bash
   grep -l '<symbol-you-changed>' \
     "$REPO/apps/dma-insights/frontend/standalone-src/src/"
   ```

**Diagnostic (run all three):**

```bash
# 1. What SHA is HEAD locally?
HEAD_SHA=$(git -C "$REPO" rev-parse --short HEAD)
echo "HEAD     : $HEAD_SHA"

# 2. What SHA is the live frontend revision serving?
LIVE_IMAGE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(spec.template.spec.containers[0].image)')
LIVE_SHA="${LIVE_IMAGE##*:}"
echo "Live img : $LIVE_SHA"

# 3. What revision (Cloud Run revisions are independent of image SHA)?
gcloud run revisions list --service=dma-insights-frontend \
  --region=us-central1 --limit=3 \
  --format='table(metadata.name,status.conditions[0].lastTransitionTime,spec.containers[0].image.basename())'

# Compare HEAD_SHA vs LIVE_SHA. If they differ → redeploy is required.
```

**Fix:**

```bash
cd "$REPO/apps/dma-insights/infra"
./deploy.sh                    # builds + applies; ~6 min end-to-end
```

After the apply finishes, hard-refresh the browser once
(Cmd+Shift+R / Ctrl+Shift+R). With the nginx cache-control fix from
this batch in place, every subsequent navigation will pick up the
latest revision automatically — no more "fix not applied" confusion.

**Verification the fix is live:**

```bash
# Headers on a JSX file MUST show no-cache after this batch deploys
FE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(status.url)')
curl -sI "$FE/src/pages-alerts-prospecting-admin.jsx" \
  | grep -i cache-control
# → cache-control: no-cache, no-store, must-revalidate
```

### T12 — `pnpm: command not found` / `Chrome installation not found` / `No such file or directory` from §5 commands

**Symptom (verbatim from a real Cloud Shell session):**
```
$ cd apps/dma-insights/frontend          # already inside apps/dma-insights/
-bash: cd: apps/dma-insights/frontend: No such file or directory
$ pnpm dev &
-bash: pnpm: command not found
$ npx lhci autorun
❌  Chrome installation not found
$ git commit -m "..."
*** Please tell me who you are.
```

**Cause:** Cloud Shell ships without `pnpm`, without `chromium`, and
loses git identity between sessions. §5 commands assume those exist.
Earlier playbook versions also used relative `cd` paths that broke when
the operator started from a non-repo-root pwd.

**Fix:** **Always run §5.0 first** (Cloud Shell pre-flight). It
installs `pnpm` via corepack, installs `chromium` via apt, sets git
identity, anchors `$REPO=$HOME/Accelerate` so every later `cd` is
absolute. The pre-flight is idempotent and takes ~20s when everything
is already installed.

```bash
# Copy-paste this once per Cloud Shell session, then run §5.1..§5.7
export REPO="$HOME/Accelerate"
cd "$REPO"
# (continue with §5.0.1 onward)
```

### T11 — `terraform apply` fails with "Backend initialization required"

**Symptom:**
```
Error: Backend initialization required, please run "terraform init"
Reason: Initial configuration of the requested backend "gcs"
```

**Cause:** the GCS backend has never been initialized in this checkout
(or the backend config changed since the last init). Common on fresh
clones, after `rm -rf .terraform`, or when `$PROJECT_ID` changed.

**Fix (preferred):** `./deploy.sh` now runs `terraform init -reconfigure`
automatically. Update your local checkout and re-run:

```bash
cd "$REPO_ROOT" && git pull origin claude/deploy-zennify-cloud-run-AUdu6
cd "$REPO_ROOT/apps/dma-insights/infra"
./deploy.sh
```

**Fix (manual):** init in the `terraform/` subdirectory — NOT in `infra/`:

```bash
cd "$REPO_ROOT/apps/dma-insights/infra/terraform"
ls main.tf                   # must exist before init (otherwise wrong dir)
terraform init -reconfigure -backend-config="bucket=${PROJECT_ID}-tfstate"
```

If `ls main.tf` fails with "No such file or directory", you're in
`infra/` instead of `infra/terraform/` — that's the most common
operator error here. The terraform config lives ONE level deeper than
the `deploy.sh` wrapper.

If `terraform init` itself fails with "BucketNotFoundException", the
state bucket from §2 was never created. Create it now:

```bash
gcloud storage buckets create "gs://${PROJECT_ID}-tfstate" \
  --location=us-central1 --uniform-bucket-level-access
gcloud storage buckets update "gs://${PROJECT_ID}-tfstate" --versioning
```

### T12 — Persistent IPv6 failures even after kernel disable + low parallelism

**Symptom:** `deploy.sh` runs through all 4 attempts (parallelism 10
→ 4 → 2 → 1) and STILL fails with `cannot assign requested address`.
sudo IPv6 disable applied successfully (the script confirms
`disable_ipv6=1`), but apply continues to hit IPv6 addresses.

**Cause:** Cloud Shell's NAT pool has stuck IPv6 entries that persist
even after kernel-level disable. The next-hop router may still be
holding state.

**Fix (in order of effort):**

```bash
# 1. Restart the Cloud Shell VM (fresh NAT pool, ~30 s downtime).
#    Top-right hamburger menu → "Restart"
#    Then re-run ./deploy.sh.

# 2. Force fully serial apply (no concurrent requests at all):
PARALLELISM_OVERRIDE=1 ./deploy.sh

# 3. Wait 5-10 minutes — Google rotates IPv6 endpoints and fresh
#    ones may be reachable. Then retry.

# 4. Run terraform from a non-Cloud-Shell environment:
#    - Your laptop (stable network) — use ADC, NOT a downloaded SA key:
gcloud auth application-default login
cd "$REPO_ROOT/apps/dma-insights/infra"
./deploy.sh

#    DO NOT use exported sa-key.json. Service-account key files are
#    long-lived credentials with no auto-rotation; the operator runbook
#    requires ADC (Application Default Credentials) which short-lives
#    and is auto-refreshed.
#
#    - GitHub Actions / Cloud Build trigger:
#      Use Workload Identity Federation (OIDC) bindings; not key-file
#      auth. See terraform/cloudbuild.tf for the binding.
```

The persistent-failure mitigation works because the underlying issue
is Cloud Shell's network configuration, not your code or terraform
state. Once you're off Cloud Shell, the apply runs cleanly.

### T13 — `Image not found` during apply with an obviously-correct SHA

**Symptom:** apply errors with `Error code 5: Image 'gcr.io/PROJECT/IMG:SHA' not found` even though `gcloud container images list-tags` clearly shows the SHA.

**Cause:** Terraform's `data "google_artifact_registry_docker_image"`
data source query is racing with Cloud Build's eventual consistency.
The image landed in gcr.io but artifact registry's index hasn't yet
populated.

**Fix:** wait 30-60 seconds for eventual consistency, then retry:
```bash
sleep 60
./deploy.sh
```

If it persists, force-refresh the image lookup:
```bash
gcloud container images list-tags "gcr.io/${PROJECT_ID}/dma-insights-backend" \
  --filter="tags:${SHA}" --format='value(tags)'
# Should print the SHA. If it doesn't, the Cloud Build push truly failed
# — re-run ./deploy.sh (auto-rebuilds when images are absent) and try again.
```

### T14 — `googleapi: Error 400: Role roles/X is not supported for this resource`

**Symptom:** apply fails with messages like:
```
Error: Request `Create IAM Members roles/drive.reader ... for project "..."`
returned error: googleapi: Error 400: Role roles/drive.reader is not
supported for this resource., badRequest
```

**Cause:** the role identifier looks like a Cloud IAM role but is actually
a different scope. Common offenders:
- `roles/drive.reader` — Google Workspace / Drive role, NOT a project IAM role
- `roles/sheets.*` — same scope problem
- `roles/firebase.*` — must be set at the firebase project scope, not GCP project
- Custom roles named `projects/.../roles/...` referenced as bare strings

`deploy.sh` v3 now classifies this as `config_invalid` and aborts on the
first attempt with a clear remediation pointer (no more 4-attempt
retry loops on hopeless configuration errors).

**Fix:** the resource is wrong by construction; retrying never helps.
Edit `apps/dma-insights/infra/terraform/main.tf` and:
1. Identify the offending `google_project_iam_member` block.
2. Either remove it (if the permission is granted via a different
   mechanism — e.g. Drive folder ACL for `drive.reader`), or replace
   it with a project-IAM-compatible role.
3. `git pull` to pick up the fix, then `./deploy.sh`.

For Drive access specifically, the permission grant is **per-folder
sharing in Google Drive** — see §9.

### T15 — `FATAL: password authentication failed for user "postgres"` (or `"dma_insights"`) — frontend returns 503

**Symptom:** sign-in page returns **HTTP 503**, OR the migrations job
fails with:
```
psycopg.OperationalError: connection failed: connection to server on
socket "/cloudsql/PROJECT:REGION:dma-insights-pg/.s.PGSQL.5432" failed:
FATAL:  password authentication failed for user "postgres"
```

**Cause — password drift.** Terraform owns the canonical postgres
password via `random_password.db_superuser` (or `db_app_user`). It
pushes that password to (a) the SQL user, via
`null_resource.db_superuser_setup`, and (b) the DSN secret
`dma-insights-database-url-superuser`. The contract is: secret + SQL
user agree because Terraform set both from the same source.

When something runs `gcloud sql users set-password` out of band
(a previous recovery script, an operator typo, a Cloud SQL credential
reset), the SQL user's password changes but the secret doesn't. Apps
load the secret, try the old password, and get 401.

**Fix — re-sync from Terraform state:**

```bash
cd "$REPO_ROOT/apps/dma-insights/infra"
./recover-db-passwords.sh
```

The script:
1. Reads `random_password.db_superuser` + `random_password.db_app_user` from Terraform state (source of truth).
2. Verifies the current secrets against the live SQL users (via `cloud-sql-proxy` + `psql`).
3. If drift is detected, runs `terraform apply -replace=null_resource.db_*_setup` which re-pushes the state's password onto the SQL user.
4. Re-verifies the connection works.
5. **Forces Cloud Run revisions to roll** (`DMA_SECRET_ROLL=<timestamp>` env-var bump on the backend service + all Cloud Run jobs). This is critical: Cloud Run resolves `version = "latest"` at container start and caches it for the container lifetime; without the roll, running revisions keep serving the OLD password even after the secret has a new version. Re-running the migrations job (Cloud Run Job) gets a fresh container that picks up the latest secret value automatically, but the long-lived backend service revision needs the explicit roll.
6. Prints the migrations re-run command.

**Variants:**
```bash
./recover-db-passwords.sh                 # heal drift (default)
./recover-db-passwords.sh --rotate        # ⭐ BULLETPROOF: fresh random passwords for both users + re-roll all revisions
./recover-db-passwords.sh --verify-only   # check; no changes (CI-friendly)
./recover-db-passwords.sh --diagnose      # dump secret versions + Cloud Run env vars + last 2 job executions
```

**Last resort — when `recover-db-passwords.sh` reports success but the
backend still 503s with `InvalidPasswordError`:**

The standard heal uses Terraform as the source-of-truth (it re-randomizes
the password, then pushes the new value to both Cloud SQL + Secret
Manager + rolls revisions). If `terraform apply` fails silently
(network, lock, IAM), only ONE side actually updated and drift persists.

`infra/force-heal-db.sh` flips the source-of-truth direction:
**Secret Manager wins.** It reads the password embedded in the live
`dma-insights-database-url` secret, force-sets the Cloud SQL `dma_insights`
user to that exact value, then rolls every Cloud Run revision so the
backend service + jobs re-read the secret. It never invokes Terraform
and never re-randomizes.

```bash
./force-heal-db.sh                  # secret → SQL → roll revisions
./force-heal-db.sh --verify-only    # confirm via cloud-sql-proxy; no writes
./force-heal-db.sh --no-roll        # update creds only; skip the revision roll
```

Use this when:
- `recover-db-passwords.sh` reports `✓ Recovery complete` but sign-in
  still 503s with `InvalidPasswordError: password authentication failed
  for user "dma_insights"`.
- You manually rotated the secret in Secret Manager and need Cloud SQL
  to catch up to the new value.
- You're not sure where the drift is and want a bulletproof reset that
  doesn't depend on Terraform state being recoverable.

**SHA resolution (heal + --rotate modes):** `terraform apply` evaluates the
three `data "google_artifact_registry_docker_image"` blocks during planning,
so the script needs a SHA whose images actually exist in `gcr.io`. The
resolver picks the first non-empty source from this priority chain so
operators never have to think about it:

| Priority | Source | When it fires |
|---|---|---|
| 1 | explicit `$SHA` env | operator was deliberate (e.g. mid-deploy override) |
| 2 | `/tmp/dma-insights-deploy-sha` | written by `infra/build.sh`; picked up by `deploy-two-phase.sh` Phase 3 |
| 3 | deployed Cloud Run backend revision's image tag | standalone recovery — the running app's images are guaranteed to exist |
| 4 | `git rev-parse --short HEAD` | developer / first-deploy fallback |

The script prints `→ SHA=<sha> (resolved via: <source>)` at startup so
the operator can confirm. **If the resolved SHA's images don't exist in
gcr.io** (only possible for sources 1 or 4), an inline preflight calls
`gcloud builds submit` to build all three before `terraform apply` runs
— operators never have to run cloud-build by hand. Source 2 + 3 skip
the preflight (those SHAs are pre-verified to have built images).

This eliminates the previous failure mode where `recover-db-passwords.sh
--rotate` would exhaust 4 retries with `Requested image was not found`
when the operator's `git HEAD` was ahead of the deployed revision by
doc-only commits.

**Use `--rotate` when:**
- The "heal" mode reports no drift but jobs still 503 with `InvalidPasswordError` (means Cloud Run is serving a stale cached value).
- You're not sure what state things are in and want a clean reset.

**Use `--diagnose` when:**
- The healing succeeded but the migrations job still fails. The diagnostic
  dumps which secret VERSION the migrations job env var is bound to (should
  be `latest`), and the last-4-chars of each secret's password so you can
  see if multiple passwords are in play.

After the script succeeds:
```bash
gcloud run jobs execute dma-insights-migrations --region=us-central1 --wait
```

`deploy.sh` v4 also auto-classifies `password authentication failed`
errors and aborts attempt 1 with a pointer to `recover-db-passwords.sh`
(no more 4-attempt retry loops on hopeless auth errors).

---

## 20 · Local development

```bash
cd "$REPO_ROOT/apps/dma-insights"
docker compose up -d            # Postgres+pgvector on :5433, Redis on :6380

cd backend
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env             # edit if needed
.venv/bin/alembic upgrade head   # applies all 15 migrations
.venv/bin/uvicorn app.main:app --reload --port 8000

# In another terminal:
cd ../frontend
pnpm install
pnpm dev                         # Vite dev server on :5173
```

**Backend test sweep + lint** (must pass before pushing):
```bash
cd "$REPO_ROOT/apps/dma-insights/backend"
.venv/bin/python -m pytest tests/ -q       # 364 tests, 1 skipped
.venv/bin/ruff check app/ tests/ ../workers/
```

**Frontend test sweep + tsc + build:**
```bash
cd "$REPO_ROOT/apps/dma-insights/frontend"
pnpm exec vitest run                       # 117 tests
pnpm exec tsc --noEmit
pnpm exec vite build
pnpm run build:standalone                  # wireframe-guide artifact
```

**Ingest a fixture locally:**
```bash
cd "$REPO_ROOT/apps/dma-insights/backend"
curl -X POST -H "Cookie: dma_session=<dev-jwt>" \
  -F file=@/path/to/AlmaBank_DMA_Complete_Package.zip \
  http://localhost:8000/api/v1/ingest/package
```

**Trigger Playwright E2E (advisory until baselines are committed):**
```bash
cd "$REPO_ROOT/apps/dma-insights/frontend"
pnpm exec playwright install --with-deps chromium
pnpm test:e2e              # persona golden-path
pnpm test:visual           # 7-breakpoint visual regression
```

---

## 21 · Cost model (steady state, mid-2026 GCP pricing)

| Component | Monthly cost |
|---|---|
| Cloud SQL `db-custom-2-7680` REGIONAL HA | ~$280 |
| Cloud Run (2 services + 5 jobs, modest traffic) | ~$60 |
| Cloud Scheduler (3 jobs) | <$1 |
| Secret Manager (~9 secrets × 1 version) | ~$1 |
| Vertex AI Gemini Flash (~5k req/day, cached 72h) | ~$30 |
| Vertex AI text-embedding-004 (~100 docs/week) | ~$5 |
| Upstash Redis (managed regional) | $0–50 |
| Cloud Storage (state + staging + materials) | <$5 |
| Clay enrichment | per-entity (see Clay pricing) |
| **Floor** | **≈$380/mo** |

Drop `min_instance_count` to 0 in non-prod envs to trim the floor
(cold-start trade-off).

---

## 22 · Where things live

| Concern | File / Resource |
|---|---|
| All GCP resources | `infra/terraform/main.tf` |
| TF default vars | `infra/terraform/terraform.tfvars` |
| Deploy wrapper | `infra/deploy.sh` (sets `GODEBUG=netdns=go` + retries + classifies errors) |
| DB password recovery | `infra/recover-db-passwords.sh` (heals secret↔SQL drift) |
| 7-stage CI pipeline | `infra/cloudbuild.yaml` |
| Backend container | `infra/docker/backend.Dockerfile` |
| Frontend container | `infra/docker/frontend.Dockerfile` + `frontend-nginx.template` |
| Worker container | `infra/docker/worker.Dockerfile` |
| Migrations | `backend/alembic/versions/00{1..15}_*.py` |
| Latest migration | `015_runs_parser_warnings.py` |
| Package parser orchestrator | `backend/app/services/parsers/dma_package.py` |
| Package persistence | `backend/app/services/parsers/package_persist.py` |
| Platform fit + readiness | `backend/app/services/platform_fit.py` + `platform_prerequisites.py` |
| Vertex client (retry/backoff) | `backend/app/services/vertex_client.py` |
| Intelligence builder (SSE) | `backend/app/services/intelligence_builder.py` |
| Grounding validators (V1-V3) | `backend/app/services/grounding_validator.py` |
| Catalogue resolver (old → v7.0) | `backend/app/services/catalogue_resolver.py` |
| RAG read API | `backend/app/routers/rag.py` |
| Prospecting router | `backend/app/routers/prospecting.py` |
| Clay connector | `backend/app/services/clay_client.py`, `backend/app/routers/clay.py` |
| OAuth + dev-login | `backend/app/routers/auth.py` |
| Catalogue loader | `workers/ccg_loader/main.py` |
| Sheet poller | `workers/sheet_poller/main.py` |
| Historical backfill | `backend/app/scripts/historical_backfill.py` |
| Embedder live IO | `workers/embedder/live.py` |
| Frontend API client (timeout + 401) | `frontend/src/lib/api.ts` |
| Frontend auth (cache clear on logout) | `frontend/src/lib/auth.ts` |
| Frontend chat panel | `frontend/src/components/IntelligencePanel.tsx` |
| Status matrix | `docs/STATUS.md` |
| Plan | `~/.claude/plans/quizzical-hatching-lighthouse.md` |
| ADRs | `docs/decisions/0001-…` through `0010-clay-connector.md` |

If you can't find something, `docs/STATUS.md` maps every plan gate
(G00.* → G15.*) to the file that satisfies it.

## 23 · Pub/Sub fan-out for `dma.ingest.completed`

After this batch, `persist_package()` and the historical backfill
publish a Pub/Sub message on every successful ingest commit. The
embedder Cloud Run Job subscribes to the topic and runs a one-shot
`embed_run(run_id=…)` per message.

### 23.1 — Topic + subscription provisioning

```bash
PROJECT_ID=digital-maturity-assessor       # or your env's project
TOPIC=dma.ingest.completed
SUB=dma-ingest-completed-embedder

gcloud pubsub topics create "$TOPIC" --project "$PROJECT_ID"

# Pull subscription (used by --subscribe mode on Cloud Run Job).
gcloud pubsub subscriptions create "$SUB" \
  --topic "$TOPIC" \
  --ack-deadline=120 \
  --expiration-period=never \
  --message-retention-duration=2d \
  --project "$PROJECT_ID"
```

### 23.2 — IAM bindings

The **backend** service account (whatever runs `/ingest/package` +
`historical_backfill`) needs `roles/pubsub.publisher` on the topic.
The **embedder** service account needs `roles/pubsub.subscriber` on
the subscription.

```bash
BACKEND_SA="dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com"
EMBEDDER_SA="dma-insights-embedder@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "$TOPIC" \
  --member="serviceAccount:${BACKEND_SA}" \
  --role="roles/pubsub.publisher" \
  --project "$PROJECT_ID"

gcloud pubsub subscriptions add-iam-policy-binding "$SUB" \
  --member="serviceAccount:${EMBEDDER_SA}" \
  --role="roles/pubsub.subscriber" \
  --project "$PROJECT_ID"
```

### 23.3 — Backend env vars

```
GCP_PROJECT_ID=digital-maturity-assessor
PUBSUB_INGEST_TOPIC=dma.ingest.completed
PUBSUB_PUBLISH_TOPIC_TIMEOUT_SECONDS=2.0
```

`GCP_PROJECT_ID` unset disables publishing (publish_disabled_in_dev
branch). All publish failures are logged + swallowed; ingest never
fails because the topic is missing or unauthed.

### 23.4 — Embedder Cloud Run Job: long-lived subscribe mode

```bash
gcloud run jobs deploy dma-insights-embedder-subscriber \
  --image gcr.io/${PROJECT_ID}/dma-insights-worker:${SHA} \
  --command python --args=-m,workers.embedder.main,--subscribe,--subscription,${SUB} \
  --service-account "$EMBEDDER_SA" \
  --set-env-vars "GCP_PROJECT_ID=${PROJECT_ID},DATABASE_URL=…" \
  --max-retries=3 \
  --region us-central1
```

The job blocks on `subscriber.subscribe(...)` and processes one message
at a time per replica. Failures (NACK) trigger Pub/Sub redelivery up
to the topic's retry policy. Idempotency is preserved by the embedder
service: `select_candidates(existing_embedded_ids=…)` skips any artifact
already embedded under the current `model_version`.

### 23.5 — One-shot CLI use (unchanged)

```bash
python -m workers.embedder.main --run-id <UUID>        # ad-hoc backfill
python -m workers.embedder.main --since 2026-05-01     # date-range sweep
```

## 24 · Nightly Cloud Scheduler jobs

Two pure-logic workers run on Cloud Scheduler triggers:

### 24.1 — `chat_learning` (nightly, 02:30 UTC)

Reads chat_feedback + chat_messages, clusters questions via KMeans,
and writes `chat_learning_signals` rows that the next `/answer` call
consults for the adversarial-learning re-rank.

```bash
gcloud scheduler jobs create http dma-chat-learning-nightly \
  --schedule "30 2 * * *" \
  --uri "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/chat-learning" \
  --http-method POST \
  --oidc-service-account-email "$EMBEDDER_SA" \
  --time-zone "UTC"
```

(Or use a Cloud Run Job + Scheduler invoker pattern — same outcome.)

### 24.2 — `peer_patterns` (weekly, Sunday 04:00 UTC)

Computes archetype centroids per (subvertical, catalogue_version) so
the D3 archetype chip + D6 Patterns tab stay fresh.

```bash
gcloud scheduler jobs create http dma-peer-patterns-weekly \
  --schedule "0 4 * * 0" \
  --uri "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/peer-patterns" \
  --http-method POST \
  --oidc-service-account-email "$EMBEDDER_SA" \
  --time-zone "UTC"
```

### 24.3 — Manual one-off invocation (for ops + testing)

```bash
python -m workers.chat_learning.main --once
python -m workers.peer_patterns.main --once
```

## 25 · Drive crawler — live continuous ingestion

The `drive_crawler` worker is the **live continuous** counterpart to the
one-shot `historical_backfill.py` script. Cloud Scheduler triggers it
every 6h. Each cycle:

1. Builds a Drive v3 service via Application Default Credentials.
2. Lists `{Client} - DMA` folders under `DRIVE_ROOT_FOLDER_ID`.
3. Reconciles every folder against the DB ledger
   (entities.drive_folder_id → runs): a folder with no ACTIVE ingested
   run is a candidate REGARDLESS of `modifiedTime` (2026-07-06 fix —
   a checkpoint/watermark must never hide a never-ingested folder);
   `--since` remains a fast-path modifiedTime filter. Folders mapping
   by normalized name to seeded `local:…` entities stay excluded.
4. For each candidate — one Drive service PER concurrent task (service
   objects are not concurrency-safe) + transient retry w/ backoff —
   downloads + parses + persists + publishes `dma.ingest.completed`.
5. Writes one `import_scans` audit row at the end.

State-branch contract: `cold_start | watermark_advance | no_new_files |
quota_exceeded`. See the docstring at the top of
`workers/drive_crawler/main.py` and `app/services/drive_client.py`.
Exit-code contract (partial-ok = 0; systemic all-fail = 7) is in
`infra/EXIT_CODES.md` § drive_crawler.

### 25.1 — Service account + IAM

```bash
SA_EMAIL="dma-drive-crawler@${PROJECT_ID}.iam.gserviceaccount.com"

# Drive read on the root folder is granted via Drive's UI (add the SA
# as a Viewer on folders/1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P or its
# parent Shared Drive), not via gcloud.

# GCS write for stage artifacts (zip extraction)
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/storage.objectAdmin"

# Pub/Sub publisher for dma.ingest.completed
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/pubsub.publisher"

# Cloud SQL client for DB upserts
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"
```

### 25.2 — Cloud Scheduler trigger

```bash
gcloud scheduler jobs create http dma-drive-crawler-6h \
  --schedule "0 */6 * * *" \
  --uri "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/drive-crawler" \
  --http-method POST \
  --oidc-service-account-email "$SA_EMAIL" \
  --time-zone "UTC"
```

### 25.3 — One-shot CLI use

```bash
# Dry-run — configured root + state matrix; no GCP creds needed
python -m workers.drive_crawler.main --dry-run

# Live --once — single pass (Cloud Run Job mode)
python -m workers.drive_crawler.main --once

# Watermark override
python -m workers.drive_crawler.main --once --since 2026-01-01T00:00:00Z
```

## 26 · Sheet poller — Ops sheet AE assignment + bot loop

The `sheet_poller` worker reads all 8 tabs of the live Ops Sheet every
5 min during business hours, hourly otherwise. It upserts into the 8
`ops_*` tables, mirrors Requests status transitions into local `runs`
rows, and emits SSE events on row transitions.

State-branch contract: `incremental_sync | full_sync_on_drift |
sheet_unavailable | row_conflict`. See `workers/sheet_poller/main.py`
and the pure helpers in `app/services/sheets_client.py`.

### 26.1 — Service account + IAM

```bash
SA_EMAIL="dma-sheet-poller@${PROJECT_ID}.iam.gserviceaccount.com"

# Sheets read on the Ops sheet — grant via Sheets UI, not gcloud.

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/cloudsql.client"
```

### 26.2 — Cloud Scheduler triggers

```bash
# Business hours: every 5 min, 8:00–18:00 ET, Mon–Fri
gcloud scheduler jobs create http dma-sheet-poller-business \
  --schedule "*/5 8-18 * * 1-5" \
  --uri "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/sheet-poller" \
  --http-method POST \
  --oidc-service-account-email "$SA_EMAIL" \
  --time-zone "America/New_York"

# Off-hours: hourly
gcloud scheduler jobs create http dma-sheet-poller-offhours \
  --schedule "0 0-7,19-23 * * *" \
  --uri "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/sheet-poller" \
  --http-method POST \
  --oidc-service-account-email "$SA_EMAIL" \
  --time-zone "America/New_York"
```

### 26.3 — One-shot CLI use

```bash
# Dry-run — configured tabs + state matrix; no GCP creds needed
python -m workers.sheet_poller.main --dry-run

# Live --once — single poll cycle
python -m workers.sheet_poller.main --once

# Subset of tabs
python -m workers.sheet_poller.main --once --tabs Requests Audit
```

---

## §1 Customer Intelligence Recompute Job

The persistent per-customer intelligence layer is recomputed
automatically after every successful ingest via the `dma.ingest.completed`
Pub/Sub topic. The recompute job is part of the embedder worker
binary; production wires it via a Pub/Sub push subscription.

### 27.1 — Pub/Sub subscription

```bash
gcloud pubsub subscriptions create dma-ingest-intelligence \
  --topic dma.ingest.completed \
  --push-endpoint "https://dma-insights-worker-${ENV_SUFFIX}.run.app/jobs/intelligence-recompute" \
  --push-auth-service-account "$SA_EMAIL" \
  --ack-deadline 60 \
  --message-retention-duration 7d
```

### 27.2 — What the job does

For each `dma.ingest.completed` event:

1. Load every prior `RunSnapshot` for the entity (pillar scores,
   archetype, theme tags, below-median subcaps, tech stack).
2. Call `customer_intelligence.compute_profile()` to derive the
   deterministic rollup (maturity history, velocity, recurring/emerging
   themes, persistent/closed gaps, tech drift).
3. Call Gemini Pro with `build_summary_prompt()` for the
   intelligence_summary_md (3-5 paragraph executive view) with
   citation-grounding via grounding_validator.
4. Embed the summary via `text-embedding-004` for cross-entity RAG.
5. UPSERT `customer_intelligence_profiles` keyed on `entity_id`.

### 27.3 — Failure modes

- `gemini_unavailable` — Vertex AI raises; row persists with
  `intelligence_summary_md = NULL`. UI shows "Summary pending".
- `validator_rejected` — Gemini cited a fabricated E-ID. Same
  end-state as `gemini_unavailable` plus a
  `gemini_hallucination_alerts` row.
- `re_ingest_same_request_id` — incoming run.request_id already in
  maturity_history; the row is in-place updated rather than appended.

### 27.4 — Backfill

For entities ingested before §1 went live, run:

```bash
# (2026-06-10 audit: the planned `workers.intelligence_backfill` module
# was never built — the real, idempotent path is the recompute worker
# in --all mode, proven against the full corpus.)
cd ${REPO:?}/apps/dma-insights
PYTHONPATH=backend python -m workers.intelligence_recompute.main --all
```

The backfill walks every ACTIVE run per entity, computes the profile,
and UPSERTs. Idempotent — safe to re-run.

---

## §2 Evidence Dedup Migration Playbook

Migration `018_intelligence_layer` adds the content-hash column +
freshness banding + customer intelligence tables. The one-time
backfill below is required for existing deployments with non-empty
`evidence_index`.

### 28.1 — Apply the migration

```bash
cd apps/dma-insights/backend
alembic upgrade head
```

The migration itself runs the content_hash backfill in a single
`UPDATE evidence_index SET content_hash = encode(digest(...), 'hex')`
statement (idempotent — same input → same hash). For a 100k-row
evidence_index this completes in ~3 seconds.

### 28.2 — Verify

```sql
-- All rows must have a content_hash post-migration.
SELECT COUNT(*) FROM evidence_index WHERE content_hash IS NULL;
-- expect: 0

-- Generated columns must be populated.
SELECT freshness_band, COUNT(*)
FROM evidence_index
GROUP BY freshness_band
ORDER BY 1;

-- Check the staleness threshold against today.
SELECT
  COUNT(*) FILTER (WHERE is_stale)               AS stale_count,
  COUNT(*) FILTER (WHERE NOT is_stale)           AS fresh_count,
  ROUND(100.0 * COUNT(*) FILTER (WHERE is_stale) / COUNT(*), 2) AS stale_pct
FROM evidence_index;
```

### 28.3 — Backfill evidence_run_links

The new `evidence_run_links` table is the canonical per-run reference;
existing evidence rows need a one-shot link to their originating run:

```bash
# (2026-06-10 audit: the planned `workers.evidence_links_backfill`
# module was never built. New ingests populate evidence_run_links at
# persist time; for rows that pre-date migration 018 run this SQL
# one-shot — same semantics, re-runnable via ON CONFLICT DO NOTHING.)
# Single-line -c form (the doc-wide no-heredoc contract:
# test_infra_safeguards bans heredocs in bash fences — a lost
# terminator hangs Cloud Shell at the `>` prompt).
bash infra/dma-psql.sh -c "INSERT INTO evidence_run_links (evidence_id, run_id, first_seen_in_run) SELECT id, run_id, true FROM evidence_index ON CONFLICT DO NOTHING;"
```

### 28.4 — Dedup audit hygiene

`dedup_audit` is append-only. The worker emits one row per dedup
decision; the table is read by the admin "Import Audit" page.
Recommended retention: 1 year. Purge older rows nightly:

```sql
DELETE FROM dedup_audit
WHERE created_at < NOW() - INTERVAL '1 year';
```

### 28.5 — Roll-back

`alembic downgrade -1` reverses the migration — drops the three new
tables (`focus_areas`, `customer_intelligence_profiles`, `dedup_audit`,
`evidence_run_links`) and the three new `evidence_index` columns
(`content_hash`, `is_stale`, `freshness_band`).

Roll-back is destructive to per-customer intelligence rows; back up
`customer_intelligence_profiles` first if you need the data.

---

### §2.2 — Evidence freshness refresh

The `evidence_index.is_stale` + `freshness_band` columns are
trigger-maintained on insert/update. Rows whose `published_date`
crosses a 1y/2y/3y band boundary between writes need a periodic
refresh to keep the dashboard accurate.

Cloud Scheduler config (provisioned in Terraform):

```hcl
resource "google_cloud_scheduler_job" "evidence_freshness_refresh" {
  name        = "dma-insights-evidence-freshness-refresh"
  schedule    = "0 6 * * *"     # 06:00 UTC daily
  time_zone   = "UTC"
  description = "Recompute is_stale / freshness_band for rows that crossed a band boundary."

  http_target {
    http_method = "POST"
    uri         = "${var.backend_url}/api/v1/admin/maintenance/refresh-evidence-freshness"
    oidc_token {
      service_account_email = var.backend_invoker_sa_email
    }
  }
}
```

The admin endpoint runs:
```sql
SELECT refresh_evidence_freshness();
```
and returns `{rows_changed: int}` for observability. Typical refresh
touches 0-30 rows per day per environment.

---

## §3 — `intelligence_recompute` Cloud Run Service (long-lived subscriber)

The customer-intelligence worker has two modes, mirroring the embedder.
The long-lived mode is the production deployment unit. It subscribes
to `dma.ingest.completed` and recomputes the affected entity's
`customer_intelligence_profiles` row on every successful ingest.

### 29.1 — Pub/Sub subscription (terraform-managed)

```hcl
resource "google_pubsub_subscription" "ingest_completed_intelligence" {
  name  = "dma-ingest-completed-intelligence"
  topic = google_pubsub_topic.ingest_completed.name
  ack_deadline_seconds       = 300   # Vertex can take ~minute
  message_retention_duration = "604800s"
  expiration_policy {
    ttl = ""   # never expire
  }
}
```

The 300-second ack-deadline is critical — Vertex Pro structured-output
calls can occasionally take 60+ seconds (vs the embedder's < 5 s).

### 29.2 — Service definition

```yaml
# Cloud Run Service (NOT a Cloud Run Job — needs to stay up for Pub/Sub)
name: dma-insights-intelligence-recompute
image: gcr.io/${PROJECT_ID}/dma-insights-workers:${IMAGE_SHA}
command: ["python", "-m", "workers.intelligence_recompute.main", "--subscribe"]
env:
  - GCP_PROJECT_ID: ${PROJECT_ID}
  - DATABASE_URL: from secret dma-insights-database-url
  - VERTEX_PROJECT: ${PROJECT_ID}
  - VERTEX_LOCATION: us-central1
service_account: dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com
min_instances: 1     # always keep one warm
max_instances: 3     # bursty re-ingest peaks
cpu: 1
memory: 1Gi
timeout: 3600s       # Cloud Run hard cap; each message handler is ~60s
```

### 29.3 — IAM requirements

The service account needs:

- `roles/pubsub.subscriber` on the subscription
- `roles/cloudsql.client` to reach Postgres
- `roles/aiplatform.user` for Vertex Pro + text-embedding-004
- `roles/secretmanager.secretAccessor` for `dma-insights-database-url`

### 29.4 — Monitoring

The structured logger emits one of the 6 state labels per recompute.
Add a Cloud Logging metric:

```
resource.type="cloud_run_revision"
resource.labels.service_name="dma-insights-intelligence-recompute"
jsonPayload.message=~"intelligence_recompute: entity=.*state="
```

Alert when `state=vertex_unavailable` exceeds 5% of dispatches over
1 hour — likely a Vertex outage or quota issue.

### 29.5 — Roll-back

```bash
gcloud run services update-traffic dma-insights-intelligence-recompute \
  --to-revisions PRIOR_REVISION=100
```

The worker is idempotent. After roll-back, the next message dispatch
re-runs the computation cleanly — `should_skip` returns False when
the run/catalogue identifiers don't match the last computed profile.

---

## §4 — Cloud Scheduler for one-shot backfill

For administrative recomputes (e.g. after a code change to the
deterministic rollup primitives or to the prompt template), use the
Cloud Scheduler → Cloud Run Job invocation pattern:

### 30.1 — Cloud Run Job

```yaml
# Cloud Run Job (NOT a Service). Runs to completion and exits.
name: dma-insights-intelligence-backfill
image: gcr.io/${PROJECT_ID}/dma-insights-workers:${IMAGE_SHA}
command: ["python", "-m", "workers.intelligence_recompute.main", "--all"]
env:
  - DATABASE_URL: from secret
  - VERTEX_PROJECT: ${PROJECT_ID}
timeout: 14400s     # 4 hours — 100 entities × ~ a minute each
```

### 30.2 — Scheduler

```hcl
resource "google_cloud_scheduler_job" "intelligence_backfill_weekly" {
  name             = "intelligence-backfill-weekly"
  schedule         = "0 3 * * 1"     # Mondays 3am UTC
  time_zone        = "UTC"
  http_target {
    uri        = "https://us-central1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-intelligence-backfill:run"
    http_method = "POST"
    oauth_token {
      service_account_email = "dma-insights-scheduler@${var.project_id}.iam.gserviceaccount.com"
    }
  }
}
```

### 30.3 — Manual one-shot for a single entity

```bash
gcloud run jobs execute dma-insights-intelligence-backfill \
  --args "workers.intelligence_recompute.main,--entity-id,<UUID>" \
  --region us-central1 --wait
```

The `--entity-id` flag overrides the default `--all` and recomputes
only one entity. Useful when an analyst wants to force a regenerate
after editing focus_areas or other inputs that flow into the rollup.

### 30.4 — Cost ceiling

Per Vertex pricing (May 2026):
- Gemini Pro structured-output: ~$0.0012/1K input tokens, $0.005/1K output tokens.
- One recompute ≈ 3K input + 1K output tokens ≈ $0.0086 per entity.
- 100 entities × weekly = $0.86/wk ≈ $45/yr per environment.

Live cost reporting lives on `/admin/vertex-budget` (the same surface
that tracks `rag_answer` cost).

---

## §5 — Deploy-gated QA gates: operator command playbook

The STATUS.md gates below cannot be flipped to ✅ from in-repo code
alone — each one requires the operator to run a command against the
live deploy. This section is the canonical command sequence; each
gate's verification flips it from 🔶/⏳ to ✅ once executed.

### §5.0 — Cloud Shell pre-flight (run ONCE per Cloud Shell session)

Cloud Shell ships with `gcloud`, `gsutil`, `psql`, `node`, `npm`,
`python3`, and `git` — but NOT with `pnpm` or `chromium`. The
playbook below is idempotent: every command short-circuits when
its outcome is already true. Re-running §5.0 between Cloud Shell
sessions costs ~20s and emits zero side effects when already met.

State branches per pre-flight step:
- `already_met`     → echo SKIP, exit 0
- `needs_install`   → install via apt/npm/corepack
- `install_failed`  → echo the failing command + exit non-zero (operator can re-run)

```bash
# ── 0.1 anchor at the repo root (REPO is referenced by every later step)
export REPO="$HOME/Accelerate"
test -d "$REPO/apps/dma-insights" || {
  echo "ERROR: $REPO/apps/dma-insights missing — clone the repo first:"
  echo "  git clone https://github.com/dma-lang/Accelerate.git $REPO"
  return 1 2>/dev/null || exit 1
}
cd "$REPO"

# ── 0.2 git identity (Cloud Shell loses this between sessions)
git config --global user.email  "${USER_EMAIL:-dma@zennify.com}"
git config --global user.name   "${USER_NAME:-DMA Insights Operator}"
git config --global init.defaultBranch main

# ── 0.3 pnpm via corepack (Node ships with corepack; pnpm is just enabled)
if ! command -v pnpm >/dev/null 2>&1; then
  corepack enable
  corepack prepare pnpm@9.12.3 --activate
fi
pnpm --version   # → 9.12.x

# ── 0.4 chromium for @lhci/cli (Lighthouse needs a browser binary)
if ! command -v chromium >/dev/null 2>&1 \
   && ! command -v google-chrome >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y chromium
fi
export CHROME_PATH="$(command -v chromium || command -v google-chrome)"
test -x "$CHROME_PATH" || { echo "ERROR: Chrome install failed"; return 1; }

# ── 0.5 backend venv (Cloud Shell's system python lacks our deps)
cd "$REPO/apps/dma-insights/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -e '.[dev]'
fi

# ── 0.6 frontend deps
cd "$REPO/apps/dma-insights/frontend"
pnpm install --frozen-lockfile

# ── 0.7 playwright browsers (chromium-only — PDF + visual + e2e all need it)
pnpm exec playwright install --with-deps chromium

# ── 0.8 GCP project + ADC
gcloud config set project digital-maturity-assessor
gcloud auth list --filter=status:ACTIVE --format='value(account)' \
  | grep -q . || gcloud auth login
gcloud auth application-default print-access-token >/dev/null 2>&1 \
  || gcloud auth application-default login

# ── 0.9 IPv6 mitigation for terraform + gcloud on Cloud Shell
export GODEBUG=netdns=go

echo "✓ Cloud Shell pre-flight complete."
```

After §5.0 succeeds, every subsequent §5.x command works
verbatim. If a session restarts, re-run §5.0 (it's idempotent).

### §5.1 — G04.OAUTH.LIVE (live Google OAuth sign-in round-trip)

Pre-req: Cloud Run frontend service is up + `oob_oauth_client_secret`
secret resolved to a non-empty value via the latest `DMA_SECRET_ROLL`
revision.

```bash
# 1. Get the live frontend URL.
FE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(status.url)')

# 2. Open in an incognito Chrome window so cookies are clean.
open "$FE/#/login"   # macOS  |  xdg-open on Linux

# 3. Sign in with a @zennify.com Google account.
#    Watch DevTools Network panel:
#       POST /api/v1/auth/google → 200 with {user_id, email, role, name}
#       GET  /api/v1/auth/me     → 200 with same shape

# 4. Verify the JWT is in the HttpOnly cookie (DevTools → Application →
#    Cookies → `dma_session`, HttpOnly=true, SameSite=Lax, Secure=true).

# 5. Sign out + sign back in. The second flow must NOT re-prompt for
#    consent (proves refresh-token bookkeeping is correct).
```

Flip STATUS.md G04.OAUTH.LIVE to ✅ when steps 3 + 4 + 5 all succeed.

### §5.2 — G05.OPS.MIRROR (Google Sheets live IO)

Pre-req: Sheets API enabled on the GCP project; service account JSON
mounted into the sheet_poller Cloud Run Job; the Ops Sheet (per the
plan §④) shared as "Viewer" with that SA's email.

```bash
# 1. Verify the service account email.
SA=$(gcloud iam service-accounts list \
  --filter="displayName:dma-insights-sheet-poller" \
  --format='value(email)' | head -1)
echo "Share Ops Sheet 1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8 with: $SA"

# 2. Confirm Sheets API enabled.
gcloud services enable sheets.googleapis.com

# 3. Trigger a manual sheet_poller run.
gcloud run jobs execute dma-insights-sheet-poller \
  --region=us-central1 --wait

# 4. Tail logs — must show "8 tabs mirrored, N upserts" with N >= 0.
gcloud logging read \
  'resource.type=cloud_run_job AND resource.labels.job_name=dma-insights-sheet-poller' \
  --limit=50 --format='value(textPayload)' --freshness=10m

# 5. Verify ops_requests has rows after the poll.
psql -h /tmp -p 5432 -U dma_insights -d dma_insights \
  -c "SELECT COUNT(*) FROM ops_requests"
```

Flip G05.OPS.MIRROR to ✅ when step 5 returns > 0.

### §5.3 — G11.BOT.ROUNDTRIP (live n8n DMA bot round-trip)

Pre-req: `dma-insights-bot-api-key` secret populated with the bot's
shared key (n8n side has the same key).

```bash
# 1. Submit a request DMA via the live admin UI's "Request a DMA"
#    modal (Dashboard or Clients page).
#    Form fields: entity name, domain, optional notes/materials.

# 2. Backend acknowledges with REQ-{8 hex} request_id.
#    Watch DevTools Network: POST /api/v1/runs/new → 201

# 3. Confirm the n8n bot received the trigger:
#    - Open n8n bot's execution log
#    - Find the run matching the request_id printed in step 2

# 4. After the bot finishes (typically 15-30 min), it POSTs back to
#    /api/v1/ingest/assessment with the AppPayloadV1 envelope.
#    Verify via Cloud Run logs:
gcloud logging read \
  'resource.type=cloud_run_revision AND resource.labels.service_name=dma-insights-backend AND textPayload:"ingest.assessment"' \
  --limit=20 --freshness=2h --format='value(textPayload)'

# 5. Confirm the runs row landed:
psql ... -c "SELECT * FROM runs WHERE request_id = 'REQ-...' LIMIT 1"
```

Flip G11.BOT.ROUNDTRIP to ✅ when step 5 returns the populated row.

### §5.4 — G12.PERF.BUDGET (Lighthouse perf budget)

`frontend/lighthouserc.cjs` already encodes the plan's thresholds
(Performance ≥ 0.85, FCP < 1.5s, TTI < 3s). Operator runs against
the live Cloud Run URL (NOT localhost — the throttled local dev
server can never beat 1.5s FCP).

Pre-req: §5.0 done (in particular Chrome installed + CHROME_PATH set).

State branches:
- `all_thresholds_met`    → exit 0; flip G12.PERF.BUDGET to ✅
- `perf_below_85`         → exit non-zero; HTML report names the failed audits
- `chrome_missing`        → "Chrome not found" — re-run §5.0.4
- `cloud_run_unreachable` → curl `$FE` returns 5xx; check backend revision

```bash
FE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(status.url)')
test -n "$FE" || { echo "ERROR: frontend service not deployed"; return 1; }

# Sanity-check the URL is reachable before paying lighthouse's 60s tax
curl -sfI "$FE" >/dev/null || { echo "ERROR: $FE not reachable"; return 1; }

cd "$REPO/apps/dma-insights/frontend"
mkdir -p artifacts/lighthouse                              # autorun writes here
LHCI_BUILD_URL="$FE" \
  CHROME_PATH="${CHROME_PATH:-$(command -v chromium)}" \
  npx --yes @lhci/cli@0.13.x autorun --config=./lighthouserc.cjs
# Exit 0 → all assertions pass. JSON + HTML in artifacts/lighthouse/
# Exit non-0 → assertion(s) failed; open the HTML report for the
# failed audit + actual numbers.
```

Flip G12.PERF.BUDGET to ✅ on exit 0.

### §5.5 — G12.RESPONSIVE.SUITE + G04.CHROME.RESPONSIVE + G06.D1.PIXEL

All three gates are served by the same `playwright.visual.config.ts`
suite covering 12 routes × 7 breakpoints. The wrapper below
auto-starts/cleans-up both servers via a `trap`, auto-creates the
baselines dir on first run, and runs the suite headlessly.

Pre-req: §5.0 done.

State branches per step:
- `first_run_no_baselines`     → suite writes baseline PNGs (all "new")
- `baselines_match`            → exit 0; diff ≤ 2%
- `baselines_diff`             → exit non-zero; diff PNGs in `test-results/`
- `dev_server_failed_to_start` → trap kills any orphans, exit non-zero
- `backend_down`               → frontend renders LoginPage skeleton; capture proceeds

```bash
cd "$REPO/apps/dma-insights/frontend"
mkdir -p e2e/visual/__snapshots__ test-results            # bootstrap dirs

# Start backend + frontend in the background; trap kills both on exit.
(
  cd "$REPO/apps/dma-insights/backend"
  exec .venv/bin/uvicorn app.main:app --port 8000 \
    > /tmp/dma-backend.log 2>&1
) &
BE_PID=$!

(
  cd "$REPO/apps/dma-insights/frontend"
  exec pnpm dev --host 0.0.0.0 --port 5173 \
    > /tmp/dma-frontend.log 2>&1
) &
FE_PID=$!

trap '[ -n "${BE_PID:-}" ] && kill $BE_PID 2>/dev/null; \
      [ -n "${FE_PID:-}" ] && kill $FE_PID 2>/dev/null' EXIT INT TERM

# Wait for ports — don't sleep blindly.
for i in $(seq 1 30); do
  curl -sf http://localhost:5173 >/dev/null 2>&1 && break
  sleep 1
done
curl -sf http://localhost:5173 >/dev/null || {
  echo "ERROR: frontend dev server didn't come up; see /tmp/dma-frontend.log"
  return 1
}

# First-time: capture baselines. Subsequent runs: assert ≤ 2% diff.
if [ -z "$(ls -A e2e/visual/__snapshots__/ 2>/dev/null)" ]; then
  echo "→ First-time baseline capture"
  pnpm test:visual:update
  git add e2e/visual/__snapshots__/
  git commit -m "test(visual): capture baselines (12 routes × 7 breakpoints)"
else
  echo "→ Asserting against committed baselines"
  pnpm test:visual
fi
```

Flip all 3 gates to ✅ after a non-baseline run exits 0.

### §5.6 — PDF export

`frontend/e2e/pdf-export.e2e.ts` runs the dashboard + 4 client-overview
surfaces through chromium's `page.pdf()`. Uses the same server-management
pattern as §5.5.

State branches (also in `pdf-export.e2e.ts` docstring):
- `route_renders_clean`       → PDF > 5KB, asserted
- `route_blanks_out`          → PDF < 5KB, test fails — silent rendering bug
- `playwright_browser_missing`→ test SKIPPED (browser != chromium)
- `not_logged_in`             → captures LoginPage as regression signal

```bash
cd "$REPO/apps/dma-insights/frontend"
mkdir -p artifacts/pdf-export

# If §5.5 already started servers in this session, skip; otherwise start.
if ! curl -sf http://localhost:5173 >/dev/null 2>&1; then
  ( cd "$REPO/apps/dma-insights/backend" && \
    exec .venv/bin/uvicorn app.main:app --port 8000 > /tmp/dma-backend.log 2>&1 ) &
  BE_PID=$!
  ( cd "$REPO/apps/dma-insights/frontend" && \
    exec pnpm dev --host 0.0.0.0 --port 5173 > /tmp/dma-frontend.log 2>&1 ) &
  FE_PID=$!
  trap '[ -n "${BE_PID:-}" ] && kill $BE_PID 2>/dev/null; \
        [ -n "${FE_PID:-}" ] && kill $FE_PID 2>/dev/null' EXIT INT TERM
  for i in $(seq 1 30); do
    curl -sf http://localhost:5173 >/dev/null 2>&1 && break
    sleep 1
  done
fi

pnpm exec playwright test pdf-export.e2e.ts --project=chromium
# Output: artifacts/pdf-export/<route>.pdf (5 files)
ls -la artifacts/pdf-export/                              # all 5 should be > 5KB
```

Flip the PDF export outstanding item to ✅ after the run passes
and all 5 PDFs are non-empty.

### §5.7 — End-to-end smoke after deploy

After running §5.1 through §5.6, do a final cross-stack walkthrough
against the live Cloud Run deploy. This is browser-driven; the
backend assertions can be cURL-ed in parallel for confidence.

```bash
FE=$(gcloud run services describe dma-insights-frontend \
  --region=us-central1 --format='value(status.url)')

# 0. Backend-side smoke (no browser required — sanity for the live URL)
curl -sf "$FE/api/v1/healthz" | grep -q '"ok":true'        # → backend up
curl -sI "$FE/api/v1/auth/me" | head -1 | grep -q '401'    # → cookie required
curl -sf "$FE/api/v1/admin/healthz" | head -1              # → 401 (gated)

# Now in an incognito browser at $FE:
# 1. Sign in (§5.1) — admin role; verify role chip shows "Admin"
# 2. Trigger drive scan (Admin → Drive crawl → "Run now").
#    Verify /admin/jobs/executions populates within 5s with a "running" row
#    that transitions to "succeeded" + folders_seen > 0.
# 3. After backfill or live drive_crawler run, open Dashboard.
#    Verify entity count > 0; recent runs strip renders.
# 4. Open a client → Overview / Insights / Heatmap / Platform render with
#    real data (no skeleton placeholders); `data-source="narrative"`
#    visible on at least one section.
# 5. Open IntelligencePanel, ask "Summarize maturity gaps" →
#    streams tokens; cited E-IDs are clickable; no "offline mode" banner.
# 6. Thumb-down the answer with reason="hallucinated" →
#    /chat/messages/:id/feedback → 200; next equivalent question
#    re-synthesizes (audit_log row with invalidation_reason=
#    'feedback_invalidated' visible in admin → audit).
```

All 6 steps green → deploy is end-to-end production-ready. Mark
the final §5.7 outstanding item as ✅ in STATUS.md.


## §6 — Drive backfill failure catalog (post 2026-05-24 fix)

**Why this section exists.** Up to commit `c0bdc74` the operator
reported "Currently none has been ingested from the drive" even though
all upstream plumbing (Cloud Scheduler, Cloud Run Job, SA, Drive
folder share) was green. Root cause was four silent failure modes
stacked on top of each other; this section documents each, how to
detect, and how to fix.

### §6.1 Failure mode A — folder name filter

**Symptom.** `historical_backfill: found 0 candidate folder(s)` in
the job log, even though the SA has Viewer access and the folder is
visibly populated in the Drive UI.

**Pre-c0bdc74 cause.** The matcher required folder names ending with
` - DMA` literally. Every operator-uploaded package today uses a
different naming convention (`RegionsBank_DMA_20260518`,
`Amalgamated_Bank_DMA_2026`, `ANB_DMA_Complete_Bundle`,
`WSFS_DMA_Engagement_Package`, `AmeriCU_DMA_Deliverable_2026-04-29`) —
none of these match the strict suffix, all are silently dropped.

**Detection (post-fix).** Run:
```bash
gcloud run jobs execute dma-insights-historical-backfill \
  --region=us-central1 --wait \
  --update-env-vars=DRIVE_FOLDER_NAME_INCLUDE=
```
First log line must read `found N candidate folder(s) matching
pattern (default: contains the token "DMA")`. `N=0` after the fix
means the SA genuinely cannot see anything — verify Drive share.

**Override.** Operators with a non-standard convention can set
`DRIVE_FOLDER_NAME_INCLUDE=<regex>` on the Cloud Run Job env. The
regex must match (Python `re.search` semantics) the folder names you
want ingested.

### §6.2 Failure mode B — Cloud Scheduler triggers worker, but worker is a no-op

**Symptom.** `drive_crawler` `job_executions` rows appear in
Admin → Job History at the scheduled cadence, every one transitions
through `running → succeeded` quickly, but `folders_new=0` /
`files_parsed=0` always, AND no rows ever appear in `entities` /
`runs` / `subcap_scores`.

**Pre-c0bdc74 cause.** `workers/drive_crawler/main.py:_main_body`
listed folders, printed a summary JSON, then `return 0`. It never
called `_ingest_folder`. The script docstring even said it would —
but the call was never wired. The actual ingest path was the
operator-only `gcloud run jobs execute
dma-insights-historical-backfill` CLI invocation.

**Detection (post-fix).** After a scheduled run completes, query:
```sql
SELECT job_name, status, folders_seen, folders_new, files_parsed,
       files_skipped, files_errored, started_at, completed_at
FROM job_executions
WHERE job_name = 'drive_crawler'
ORDER BY started_at DESC LIMIT 5;
```
On a cold-start environment with N folders in the root, the FIRST
scheduled run should show `folders_seen=N, folders_new=N,
files_parsed≈N` (allowing for SKIPs on incomplete packages).

**Manual recovery.**
```bash
gcloud run jobs execute dma-insights-drive-crawler \
  --region=us-central1 --wait
# Watch the job log; expect per-folder `[i/N] <name>` lines followed
# by `✓ run_id=<uuid>` for successes, `→ <reason>` for SKIPs.
```

### §6.3 Failure mode C — Admin button writes the row but never invokes the worker

**Symptom.** Admin → Overview "Drive crawl" button click writes a
`job_executions` row that stays in `running` indefinitely (or
transitions to `failed` only when a watchdog finally times it out).
Operator sees the button spin then "succeeded" with all-zero
counters, OR sees it stuck at "running" until they reload.

**Pre-c0bdc74 cause.** `POST /api/v1/admin/jobs/{name}:execute`
INSERTed the row then published a Pub/Sub fan-out to topic
`admin-job-triggered`. No worker subscribed to that topic. The actual
worker never ran.

**Detection (post-fix).**
```bash
# Local — verify the dispatcher fires a subprocess
ENV=local DMA_BOT_API_KEY=test python -c "
import asyncio
from app.services.cloud_run_dispatch import dispatch_job
ok, reason = asyncio.run(dispatch_job(
    job_name='drive_crawler',
    execution_id='00000000-0000-0000-0000-000000000000'
))
print('dispatched:', ok, 'reason:', reason)
"
# Expect: dispatched: True reason: skipped_local_env_subprocess_fired

# Prod — hit the admin endpoint, then assert the row leaves 'running'
curl -sf -b admin-cookies.txt -X POST \
  "$BE/api/v1/admin/jobs/drive_crawler:execute" \
  -H 'Content-Type: application/json' -d '{"mode":"delta","args":{}}' \
  | tee /tmp/exec.json
EID=$(jq -r .id /tmp/exec.json)
for i in $(seq 1 60); do
  STATUS=$(curl -sf -b admin-cookies.txt "$BE/api/v1/admin/jobs/executions/$EID" | jq -r .status)
  echo "[$i] $STATUS"
  [ "$STATUS" != "running" ] && break
  sleep 5
done
# Expect: status flips to 'succeeded' (or 'failed' with a real error) within 30s
```

If the row stays at `running` past 60s, the dispatcher dispatched but
the worker is silently stuck. Inspect the Cloud Run Job log for the
matching `DMA_JOB_EXECUTION_ID` to find the actual failure.

### §6.4 Failure mode D — parser silently drops valid packages

**Symptom.** `drive_crawler` `job_executions` row shows
`folders_seen=N, files_parsed=0`. The per-folder log shows
`SKIP:<folder> — incomplete package (no run manifest found)` for
folders that clearly contain a complete DMA package.

**Pre-c0bdc74 causes (3 independent bugs):**

1. **AmeriCU shape** — `run_manifest.json` in `03_scoring_workbook/`.
   Parser priority-1 only checked `.`, `07_governance/`,
   `08_appendices/`. **Fixed** in `parsers/dma_package.py:329-340`
   by adding `03_scoring_workbook` + `02_research_workbook` to both
   priority-1 fixed-path list and the priority-2 glob search.

2. **Sparse layout** — `_find_root` required ≥3 of 8 canonical
   `0N_*` subfolders. Some real packages ship only `01_evidence/` +
   `03_scoring_workbook/` + `07_governance/`. **Fixed** by relaxing
   threshold to ≥2 canonical subfolders WITH at least one
   manifest-bearing kind (07_governance / 08_appendices /
   03_scoring_workbook).

3. **Hand-uploaded packages** with no canonical numbered subfolder
   at all — `_has_manifest_anywhere` fallback now accepts any tree
   that contains MANIFEST.json / run_manifest*.json / *qa_verdict*.json
   at depth ≤ 2.

**Post-fix coverage.** The end-to-end simulation
`tests/test_drive_backfill_e2e_simulation.py` exercises all 5
real-world shapes (RegionsBank flat / Amalgamated nested with no
export CSVs / ANB nested / WSFS flat with l1_run_id / AmeriCU with
manifest in 03_scoring_workbook). All 5 produce non-empty
`subcap_scores` + `evidence` + `peers` envelopes.

### §6.5 Failure mode E — XLSX-only scoring workbook

**Symptom.** `parse_package(folder)` returns a non-empty
`run_manifest` but `subcap_scores=[]`. Admin UI then shows the
entity in Directory but D3 Heatmap is empty.

**Pre-c0bdc74 cause.** Parser only read `export_scoring_detail.csv`
(+ glob variants). Packages that ship only the assessment workbook
XLSX (Amalgamated, AmeriCU) had no fallback — scoring data was
unreachable.

**Fix.** New `_scoring_from_xlsx_fallback` in
`parsers/dma_package.py` reads per-pillar sheets
(`P{1..4}_Subcap_Scoring` / `P{1..4}_Scoring_Detail` / variants)
with flexible header normalisation. Covers both real XLSX shapes
we've seen.

**Detection.**
```sql
-- Any active run with zero scores indicates the XLSX fallback failed
SELECT e.display_id, r.request_id, COUNT(s.id) AS n_scores
FROM runs r
JOIN entities e ON e.id = r.entity_id
LEFT JOIN subcap_scores s ON s.run_id = r.id
WHERE r.status = 'ACTIVE'
GROUP BY e.display_id, r.request_id
HAVING COUNT(s.id) = 0;
```

### §6.6 Failure mode F — variant evidence and peer filenames

**Symptom.** Entity Directory + D1 Overview render, but D2
Insights/Evidence drawer is empty, AND D3 peer overlay shows
"no peers".

**Pre-c0bdc74 causes.**
- Evidence: parser only read `01_evidence/evidence_index.csv` or
  `.json`. Amalgamated ships `A1_Evidence_Inventory.csv` instead.
- Peers: parser only read `06_peers/peer_scores_*.json`. Amalgamated
  + AmeriCU ship `06_peers/peer_set.json` (one consolidated file).

**Fix.** Both fall-backs now in `parsers/dma_package.py` — variant
filename matching for evidence + `peer_set.json` /
`02_l1_peer_benchmarks.json` synthesised PeerScore rows.

### §6.7 Failure mode G — auth role drift

**Symptom (security).** A user removed from the server-side admin
allow-list still sees admin nav in the frontend.

**Pre-c0bdc74 cause.** `standalone-src/src/pages-auth-dashboard-directory.jsx:85`
called `ctxSignIn(body.email)` — only the email passed.
`app-root.jsx:148` then re-derived role via hardcoded ADMIN_EMAILS
sets, ignoring the server `role` field.

**Fix.** `signIn()` now consumes the full server response via
`normalizeServerUser()`. Backend `CurrentUserResponse` schema now
exposes `can_act_as` so the segmented control matches the server's
hierarchy.

**Detection (post-fix).**
```bash
# Sign in as Mishley (admin), then verify /auth/me returns can_act_as
curl -sf -b admin-cookies.txt "$BE/api/v1/auth/me" \
  | jq '{role, can_act_as}'
# Expect: {"role": "ADMIN", "can_act_as": ["ADMIN", "ANALYST", "AE"]}
```

If the `can_act_as` field is missing or wrong, the backend deploy
predates this fix — redeploy.

### §6.8 Failure mode H — Vite frontend 404s

**Symptom.** When the production Dockerfile is flipped to serve
`dist/` (Phase E in the remediation plan), 4 pages render empty
states despite having seeded data:

- `HealthPage.tsx` → `/health/version-diff` 404
- `HeatmapPage.tsx` → `/heatmap/subcap/{id}` 404
- `InsightsPage.tsx` → `/techstack/landscape` 404
- `PlatformPage.tsx` → `/platforms/roadmap` 404

**Pre-c0bdc74 cause.** Vite frontend pages call these 4 endpoints
which didn't exist on the backend.

**Fix.** All 4 added as slim composition routes over existing
handlers. Each carries the same auth + role gating as the underlying
endpoint:
- `/health/version-diff` → `require_analyst`
- others → `CurrentUserDep` (any authenticated user)

**Detection.**
```bash
for ep in heatmap/subcap/P1C1.1.1 techstack/landscape platforms/roadmap; do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' \
    -b cookies.txt "$BE/api/v1/entities/fce-001/$ep")
  echo "$ep: $STATUS"
done
curl -s -o /dev/null -w '%{http_code}' -b cookies.txt \
  -G "$BE/api/v1/entities/fce-001/health/version-diff" \
  --data-urlencode "run_a=REQ-XXXXXXXX" --data-urlencode "run_b=REQ-YYYYYYYY"
# All should return 200 (or 404 with a clear "X not present" message,
# not "Not Found" from the framework).
```

### §6.9 Failure mode I — RAG streaming endpoint mismatch

**Symptom.** IntelligencePanel cursor never animates; the full
answer pops in at once.

**Pre-c0bdc74 cause.** `standalone-src/src/backend-loader.js:351`
posted to `/api/v1/rag/answer` (non-streaming) even though it was
called `streamAnswer`. SSE was never received.

**Fix.** Now POSTs to `/api/v1/rag/answer/stream` first with
`Accept: text/event-stream`; falls back to `/answer` on 404/415.

**Detection.**
```bash
curl -sf -b cookies.txt -X POST "$BE/api/v1/rag/answer/stream" \
  -H 'Content-Type: application/json' \
  -H 'Accept: text/event-stream' \
  -d '{"question":"summary","response_style":"concise"}' | head -3
# Expect: SSE frames `data: {"token":..., "done":...}\n\n`
# Not: a single JSON blob.
```

### §6.10 Pre-deploy simulation checklist

Run BEFORE every deploy to catch silent regressions. The canonical
gate is the 21-stage harness — it walks the WHOLE pipeline (syntax →
preflight → alembic round-trip → post_migrate grants → seed
idempotency → uvicorn boot → 13 prod + 8 entity endpoints → full
pytest → ruff/tsc/vitest/builds → terraform/image-pin/exit-code/region
contracts → parser fixture + real-sample audit) and never bails on
first failure:

```bash
cd ${REPO:?}/apps/dma-insights
# Point at a scratch Postgres (fresh DB = the honest first-deploy test).
export DATABASE_URL=postgresql+asyncpg://...      \
       DATABASE_URL_SYNC=postgresql+psycopg://... \
       SEED_CI_PG_URL=postgresql+asyncpg://...    \
       WRITE_SURFACES_PG_URL=postgresql+asyncpg://... \
       ENV=local DMA_BOT_API_KEY=ci-bot-key RAG_API_BEARER_KEY=ci-rag-key
bash infra/simulate-all-deploy-stages.sh
# Expect: 21/21 PASS. (--stages 3,4,5 re-runs just the DB stages.)
# 2026-06-10 baseline: full pytest inside stage 10 = 2,190+ passed;
# the corpus-gated modules (adversarial_resilience,
# skip_path_integration, catalogue_alias_bridge live test) PASS only
# against a corpus+catalogue-seeded DB — by design (they are deploy
# gates that verify the seed actually happened).
```

Targeted drill-downs when a stage flags (same suites the stages run):

```bash
cd ${REPO:?}/apps/dma-insights/backend
# Parser end-to-end against every real shape we've seen
python3 -m pytest tests/test_drive_backfill_e2e_simulation.py -v

# Folder discovery + dispatcher unit tests
python3 -m pytest tests/test_drive_backfill_discovery.py \
                  tests/test_cloud_run_dispatch.py \
                  tests/test_dma_package_real_shapes.py \
                  tests/test_auth_can_act_as.py -v

# Full backend sweep
python3 -m pytest tests/ -q
# Expect: 900+ passed, 8 skipped (3 fixture-gated + 1 bearer + 4 cffi
#         env-only). 0 errors, 0 failures.

# 4. Linter
python3 -m ruff check app/ tests/ ../workers/
# Expect: All checks passed!
```

### §6.11 Post-deploy smoke (operator commands)

After the new image lands on Cloud Run:

```bash
PROJECT=digital-maturity-assessor
BE=$(gcloud run services describe dma-insights-backend \
       --region=us-central1 --format='value(status.url)')

# 1. Readiness
curl -sf "$BE/healthz" | jq .          # status: ok
curl -sf "$BE/readyz"  | jq .          # status: ready
                                        # (or 503 if DB unreachable)

# 2. Trigger a live drive crawl + watch it complete
gcloud run jobs execute dma-insights-drive-crawler \
  --region=us-central1 --wait
# Expect: exit code 0; log shows `[i/N] <name>` per folder, ✓ for OKs.

# 3. Verify rows landed
psql -h ... -d dma_insights -c "
  SELECT job_name, status, folders_seen, folders_new, files_parsed,
         files_errored, started_at
  FROM job_executions
  WHERE job_name = 'drive_crawler'
  ORDER BY started_at DESC LIMIT 1;
"
# Expect: status='succeeded', folders_seen >= N (your folder count),
#         files_parsed >= 1.

psql -h ... -d dma_insights -c "
  SELECT count(*) as entities, count(distinct entity_id) as unique
  FROM runs WHERE data_source = 'DRIVE_BACKFILL';
"
# Expect: >= 1 entity per successfully ingested folder.

# 4. Per-entity render check
ENT=$(psql -h ... -d dma_insights -tA -c "
  SELECT display_id FROM entities
  WHERE data_source = 'DRIVE_BACKFILL'
  ORDER BY created_at DESC LIMIT 1;
")
for endpoint in overview insights heatmap platforms context health \
                techstack run-history; do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' -b admin-cookies.txt \
    "$BE/api/v1/entities/$ENT/$endpoint")
  echo "$endpoint: $STATUS"
done
# Expect: every endpoint 200. 404 means the entity isn't ACTIVE yet —
#         check the runs.status column.

# 5. Cross-user persistence — sign in as a SECOND user, confirm same
#    insight_card UUIDs render for the same entity. This is the
#    operationally critical "persisted across sessions/users" check.
```

If ANY check fails, the deploy is silently broken — DO NOT mark it
green until the root cause is identified and patched.



## §7 — `/readyz` migration-drift gate (D1, post 2026-05-24)

**Why this section exists.** Prior to this commit, `/readyz` only
checked DB-reachability and Redis-reachability. A deploy that shipped
container image @ migration revision N landing on a DB still at
revision N-1 passed the probe; the affected endpoints then 500'd
silently when an AE hit them. This gap was the root cause of the
"feature works locally / breaks in prod" class of incident.

**Fix.** `/readyz` now performs a third check in production: read
`alembic_version.version_num` from the DB and compare against
`alembic.ScriptDirectory.get_current_head()` from the image. Mismatch
→ 503 with diagnostic detail. Skipped in local/test so the
in-process TestClient (no real DB) still passes.

**State matrix:**

| env  | DB reachable | DB head == code head | alembic_version present | Result |
|------|--------------|----------------------|--------------------------|--------|
| prod | ✓            | ✓                    | ✓                        | 200 `{status: ready, migration_head: <head>}` |
| prod | ✓            | ✗                    | ✓                        | 503 `migration drift: db=X code=Y — run alembic upgrade head` |
| prod | ✓            | n/a                  | ✗                        | 503 `migration check failed: <Error>` |
| prod | ✗            | n/a                  | n/a                      | 503 `db unavailable: <Error>` |
| local| any          | any                  | any                      | 200 (check skipped) |

**Detection (post-fix smoke):**
```bash
BE=$(gcloud run services describe dma-insights-backend \
       --region=us-central1 --format='value(status.url)')

# Healthy deploy:
curl -sf "$BE/readyz" | jq .
# {"status":"ready","migration_head":"020_job_executions"}

# Forced drift simulation — stamp DB to an older revision:
psql -h ... -d dma_insights -c \
  "UPDATE alembic_version SET version_num='019_synthesis_cache';"
curl -sf "$BE/readyz"
# HTTP/2 503
# {"detail":"migration drift: db=019_synthesis_cache code=020_job_executions — run alembic upgrade head"}

# Recovery: run the migrations job manually
gcloud run jobs execute dma-insights-migrations --region=us-central1 --wait
curl -sf "$BE/readyz" | jq .   # back to ready
```

**Catches:**
- New revision deployed against un-migrated DB (forgot to run jobs)
- Rollback to old image while DB is on new schema (orphan column writes)
- Hotfix branch with a private migration that wasn't run upstream
- Concurrent deploys where one revision wins the cutover before
  its migrations finished applying

### §7.1 Intelligence chat staleness banner (UI/UX brief mandate)

**Why this section exists.** Per the UI/UX brief, "staleness should
always be flagged." The backend `/rag/answer` already computed
`bundle_stale_pct` + `stale_disclaimer` per the 3-year evidence
mandate, but the standalone IntelligencePanel never consumed them —
the AE got no signal when an answer was grounded in mostly-stale
evidence.

**Fix.**
- `standalone-src/src/backend-loader.js:streamAnswer` JSON-fallback
  path now forwards `bundle_stale_pct` + `stale_disclaimer`. The SSE
  path already forwarded all unknown fields via `{...obj}`.
- `standalone-src/src/drawers.jsx:IntelligencePanel` reads both
  fields off the streamed message and renders an amber inline
  banner below the answer body when `stale_disclaimer` is set —
  with the percentage in parentheses for AE situational awareness.

**Detection.**
```bash
# Force a stale answer:
curl -sf -b cookies.txt -X POST "$BE/api/v1/rag/answer" \
  -H 'Content-Type: application/json' \
  -d '{"question":"What is the strategic posture?","page_context":{"route":"/clients/fce-001/overview","entity_id":"fce-001","user_role":"AE"},"response_style":"concise","max_paragraphs":3,"require_citations":true}' \
  | jq '{bundle_stale_pct, stale_disclaimer}'
# When >40% of bundle is stale:
# {"bundle_stale_pct": 0.62, "stale_disclaimer": "Most evidence is dated..."}
```

If the response includes `stale_disclaimer` but the UI doesn't show
the amber banner, the standalone bundle predates this fix —
rebuild via `pnpm run build:standalone`.



## §8 — PRD §17 Drive feedback loop (F4)

**Why this section exists.** PRD v3.0 §17 requires writing 5
structured feedback files back to each entity's source Drive folder
after every successful Phase 0 ingest. Until this batch the channel
was unwritten — downstream DMA bots had no way to learn from
Insights-side decisions (thin-evidence flags, freshness alerts,
narrative overrides, waivers).

**Fix.** New `backend/app/services/drive_feedback.py`. Called from
`parsers/package_persist.publish_post_commit` as a sibling to the
Pub/Sub fan-out — best-effort, ingest never wedges.

**5 files emitted (each with $schema version stamp):**

| File | Source | Schema |
|---|---|---|
| `thin_evidence_feedback.json`     | `subcap_scores.is_thin_evidence=true` rows | `thin_evidence_feedback_v1` |
| `evidence_freshness_alerts.json`  | `evidence_index.freshness_band ∈ {dated, stale, undated}` | `evidence_freshness_alerts_v1` |
| `tech_inference_handoff.json`     | `tech_stack` where `inference_source != 'explorium_direct'` | `tech_inference_handoff_v1` |
| `narrative_overrides.json`        | `narrative_overrides` table (AE-curated) | `narrative_overrides_v1` |
| `waiver_decisions.json`           | `waivers` table (admin-granted) | `waiver_decisions_v1` |

**State-branch matrix** (returned in `FeedbackWriteResult.state` and
written to `audit_log.after_json`):

| state | meaning | operator action |
|---|---|---|
| `drive_folder_unknown` | entity has no `source_folder_id` | check entity row; set folder ID via admin |
| `dev_skip` | env ≠ prod/staging | none (expected in local) |
| `dry_run` | caller passed `dry_run=True` | none (preview only) |
| `upload_ok` | all 5 files accepted by Drive | none |
| `upload_failed` | at least one upload returned 4xx/5xx | inspect `error_kind` + `error_message` |
| `drive_perms_missing` | every upload returned 403 | re-share folder with SA email |

**Detection (post-deploy smoke):**
```bash
# 1. Wait for an ingest to complete via the live drive_crawler:
gcloud run jobs execute dma-insights-drive-crawler \
  --region=us-central1 --wait

# 2. Query the audit_log for the feedback row:
psql -h ... -d dma_insights -c "
  SELECT
    target_id AS run_id,
    after_json->>'state' AS state,
    jsonb_array_length(after_json->'written') AS files_written,
    jsonb_array_length(after_json->'failed') AS files_failed,
    after_json->>'error_kind' AS error_kind,
    created_at
  FROM audit_log
  WHERE action = 'drive_feedback_written'
  ORDER BY created_at DESC LIMIT 5;
"
# Expect: state='upload_ok', files_written=5, files_failed=0.

# 3. Verify the files actually landed in Drive (visual check or API):
ENT_FOLDER_ID=$(psql -h ... -tA -c \
  "SELECT source_folder_id FROM entities WHERE display_id='fce-001';")
gcloud auth activate-service-account --key-file=$SA_KEY
curl -sf -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://www.googleapis.com/drive/v3/files?q='${ENT_FOLDER_ID}'+in+parents+and+name+contains+'feedback'&fields=files(name,modifiedTime)" \
  | jq .
# Expect: 5 files, modifiedTime within seconds of the ingest.
```

**Catches:**
- Bot regression where a previous run's thin-evidence flag is silently
  lost (bot's next pass doesn't see the feedback channel)
- Folder permission drift (SA re-share missed during account rotation)
- DMA bot iterations that ignored Insights-side AE edits

## §9 — B5 / B3 quality gates added 2026-05-24

**B5: jsdom canvas stub.** `frontend/vitest.setup.ts` stubs
`HTMLCanvasElement`, `matchMedia`, `ResizeObserver`,
`IntersectionObserver`, and `getComputedStyle(pseudoElt)`. Removed 17+
"Error: Not implemented" lines per test run so real failures surface.
No behavioral change — pure stub layer; tests that ASSERT on canvas
content must mock individually.

**B3: endpoint contract test.**
`backend/tests/test_endpoint_contract.py` scrapes every `/api/v1/...`
URL from `standalone-src/src/backend-loader.js` and asserts the
backend `app.routes` table has a matching template registered. Plus
9 hard-pinned critical routes (the 4 Vite endpoints fixed in c0bdc74,
RAG stream + non-stream, auth/me, healthz, readyz).

**Detection:** the test FAILS at build time when:
- New frontend call lands without backend route → 404 prevention
- Backend route renamed without updating frontend → catches drift
- Critical route accidentally unregistered (router missing from
  `main.py` include_router list)

When this test fails, the failure message lists the missing paths +
the fix-options (register / remove / alias).



## §10 — Production-readiness guard + full IAM/Secret Manager runbook

> **Canonical path:** §0.5 (script-driven secrets + IAM bootstrap) is
> what you run. This section is the manual least-privilege REFERENCE —
> per-grant explanations and copy-paste fallbacks for when §0.5's
> scripts need surgery. Don't run both end-to-end.

Every command can be copy-pasted; every secret is named explicitly;
every IAM grant is scoped to least-privilege.

### §10.1 Production-readiness guard (fail-fast at startup)

`backend/app/config.py` exposes `assert_production_ready(settings)`
which is called from `create_app()`. When `env in (prod, dev)` and
ANY required setting is unset OR still holds a dev default, the call
raises `RuntimeError` — Cloud Run sees the startup probe fail and
holds the new revision out of traffic.

Required-for-prod settings:

| Setting | Dev default that must NOT leak | Cloud Run env var | Source |
|---|---|---|---|
| `database_url` | `localhost:5433` | `DATABASE_URL` | Secret Manager: `dma-insights-db-url` |
| `redis_url` | `localhost:6380` | `REDIS_URL` | Secret Manager: `dma-insights-redis-url` |
| `google_oauth_client_id` | `""` | `GOOGLE_OAUTH_CLIENT_ID` | direct env (public) |
| `google_oauth_client_secret` | `""` | `GOOGLE_OAUTH_CLIENT_SECRET` | Secret Manager: `dma-insights-oauth-client-secret` |
| `jwt_private_key_path` | `./local-data/jwt-private.pem` | `JWT_PRIVATE_KEY_PATH` | mounted secret volume from `dma-insights-jwt-private-pem` (OR `JWT_PRIVATE_KEY_PEM` env) |
| `dma_bot_api_key` | `""` | `DMA_BOT_API_KEY` | Secret Manager: `dma-insights-bot-api-key` |
| `rag_api_bearer_key` | `""` | `RAG_API_BEARER_KEY` | Secret Manager: `dma-insights-rag-api-key` |
| `gcp_project_id` | `""` | `GCP_PROJECT_ID` | direct env: `digital-maturity-assessor` |

> **NOT boot-required — corrected 2026-06-15 to match `config.py::REQUIRED_FOR_PROD_BACKEND`:**
> `clay_webhook_url` / `clay_webhook_secret` are **deferred** (ADR 0010 amendment, 2026-06-10).
> The Clay client fail-closes on empty secrets (enrichment is simply skipped), so empty Clay
> values do **NOT** block boot. `jwt_public_key_path` is likewise **not** in the guard — only
> the JWT *private* key is checked. (`deploy-two-phase.sh` still creates empty placeholder Clay
> secrets so `gcloud run services update` doesn't 404 on the env refs.)

The guard requires the **7 settings above + a JWT private key**.
`test_production_readiness_guard.py` and `test_clay_prod_config_contract.py` (which asserts the
guard PASSES with empty Clay values) lock the contract.

### §10.2 One-time GCP project bootstrap

```bash
export PROJECT_ID=digital-maturity-assessor
export REGION=us-central1
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID \
  --format='value(projectNumber)')

# Enable the 11 APIs we depend on.
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  sqladmin.googleapis.com \
  drive.googleapis.com \
  sheets.googleapis.com \
  aiplatform.googleapis.com \
  pubsub.googleapis.com \
  cloudscheduler.googleapis.com \
  storage.googleapis.com \
  --project=$PROJECT_ID
```

### §10.3 Service accounts (least-privilege per Cloud Run service)

```bash
# Create one SA per Cloud Run service / worker class.
for SA in backend frontend rag-api drive-crawler sheet-poller \
          embedder peer-patterns ccg-loader chat-learning \
          intelligence-recompute historical-backfill; do
  gcloud iam service-accounts create dma-insights-${SA} \
    --display-name="DMA Insights ${SA}" \
    --project=$PROJECT_ID
done
```

### §10.4 Secret Manager — create + grant access

```bash
# Create the 9 secret IDs (start empty; populate via versions).
for SECRET in db-url redis-url oauth-client-secret jwt-private-pem \
              jwt-public-pem bot-api-key rag-api-key \
              clay-webhook-url clay-webhook-secret; do
  gcloud secrets create dma-insights-${SECRET} \
    --replication-policy=automatic \
    --project=$PROJECT_ID
done

# Populate (operator runs this with actual values; placeholders below).
# Example for the bot API key — repeat per secret.
echo -n "$(openssl rand -hex 32)" | \
  gcloud secrets versions add dma-insights-bot-api-key \
    --data-file=- --project=$PROJECT_ID

# Grant the backend SA read access to ALL 9 secrets it consumes.
BACKEND_SA="dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com"
for SECRET in db-url redis-url oauth-client-secret jwt-private-pem \
              jwt-public-pem bot-api-key rag-api-key \
              clay-webhook-url clay-webhook-secret; do
  gcloud secrets add-iam-policy-binding dma-insights-${SECRET} \
    --member="serviceAccount:${BACKEND_SA}" \
    --role=roles/secretmanager.secretAccessor \
    --project=$PROJECT_ID
done

# RAG API SA only needs the rag-api-key.
RAG_SA="dma-insights-rag-api@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud secrets add-iam-policy-binding dma-insights-rag-api-key \
  --member="serviceAccount:${RAG_SA}" \
  --role=roles/secretmanager.secretAccessor

# Workers need db-url + their own scoped credentials.
for WORKER in drive-crawler sheet-poller embedder peer-patterns \
              ccg-loader chat-learning intelligence-recompute \
              historical-backfill; do
  WORKER_SA="dma-insights-${WORKER}@${PROJECT_ID}.iam.gserviceaccount.com"
  for S in db-url redis-url; do
    gcloud secrets add-iam-policy-binding dma-insights-${S} \
      --member="serviceAccount:${WORKER_SA}" \
      --role=roles/secretmanager.secretAccessor
  done
done
```

### §10.5 Cloud SQL access (backend + workers)

```bash
# Grant Cloud SQL Client to every SA that talks to Postgres.
for SA in backend rag-api drive-crawler sheet-poller embedder \
          peer-patterns ccg-loader chat-learning \
          intelligence-recompute historical-backfill; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:dma-insights-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/cloudsql.client
done
```

### §10.6 Vertex AI access (backend + intelligence_recompute + embedder)

```bash
# `aiplatform.user` covers Gemini generate + text-embedding-004.
for SA in backend intelligence-recompute embedder rag-api; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:dma-insights-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/aiplatform.user
done
```

### §10.7 Drive + Sheets (workers + historical_backfill)

```bash
# OAuth flow handles user-scoped Drive access; for SA-scoped reads
# of the shared "DMA Assets" folder + Ops Sheet, the SAs must be
# shared INTO those Drive items (no IAM role grants the SA cross-
# tenant Drive access).
#
# Operator (Mishley) runs these in the Drive UI:
#  1. Share folder/1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P with:
#       dma-insights-drive-crawler@digital-maturity-assessor.iam.gserviceaccount.com  (Editor)
#       dma-insights-historical-backfill@...                                           (Viewer)
#  2. Share sheet 1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8 with:
#       dma-insights-sheet-poller@...                                                  (Editor — needs write for status writes)
#  3. Share the per-entity folders (auto-created by drive_crawler) — these
#     inherit from the root, no per-folder share needed if root is Editor.
#
# Verify in Cloud Run logs after first scheduled run:
#   drive_crawler: "found N candidate folder(s)"   ← if N=0, the SA can't see them
#   sheet_poller:  "synced Requests rows N"        ← if rows show 403, share-permission missing

# F4 Drive feedback writes — drive-crawler SA also needs Editor on
# each entity folder (already covered by Editor on root if folders
# inherit; verify in the §6.4 detection block).
```

### §10.8 Cloud Storage (request materials + catalogue staging)

```bash
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION \
  gs://dma-insights-request-materials/
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION \
  gs://dma-insights-catalogue-staging/

# Backend writes uploaded materials before posting to the bot.
gsutil iam ch \
  serviceAccount:dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com:objectAdmin \
  gs://dma-insights-request-materials/

# Catalogue loader reads staged workbooks.
gsutil iam ch \
  serviceAccount:dma-insights-ccg-loader@${PROJECT_ID}.iam.gserviceaccount.com:objectViewer \
  gs://dma-insights-catalogue-staging/
```

### §10.9 Pub/Sub (ingest fan-out + RAG learning)

```bash
# Topic
gcloud pubsub topics create dma.ingest.completed --project=$PROJECT_ID

# Backend publishes; embedder + intelligence_recompute subscribe.
gcloud pubsub topics add-iam-policy-binding dma.ingest.completed \
  --member="serviceAccount:dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/pubsub.publisher

for SA in embedder intelligence-recompute; do
  gcloud pubsub topics add-iam-policy-binding dma.ingest.completed \
    --member="serviceAccount:dma-insights-${SA}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/pubsub.subscriber
done

# Subscriptions (one per subscriber service)
gcloud pubsub subscriptions create embedder-ingest-sub \
  --topic=dma.ingest.completed \
  --push-endpoint=$(gcloud run services describe dma-insights-embedder \
                     --region=$REGION --format='value(status.url)')/push \
  --push-auth-service-account=dma-insights-embedder@${PROJECT_ID}.iam.gserviceaccount.com \
  --ack-deadline=600

gcloud pubsub subscriptions create intelligence-recompute-ingest-sub \
  --topic=dma.ingest.completed \
  --push-endpoint=$(gcloud run services describe dma-insights-intelligence-recompute \
                     --region=$REGION --format='value(status.url)')/push \
  --push-auth-service-account=dma-insights-intelligence-recompute@${PROJECT_ID}.iam.gserviceaccount.com \
  --ack-deadline=900
```

### §10.10 Cloud Run Jobs (worker dispatch)

```bash
# Backend's admin-button dispatcher invokes Cloud Run Jobs REST API.
# Grant `roles/run.invoker` on each job to the backend SA.
for JOB in drive-crawler sheet-poller historical-backfill embedder \
           peer-patterns ccg-loader chat-learning intelligence-recompute; do
  gcloud run jobs add-iam-policy-binding dma-insights-${JOB} \
    --region=$REGION \
    --member="serviceAccount:dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role=roles/run.invoker
done
```

### §10.11 Cloud Scheduler (drive crawl 6h, sheet poll 5min, GC nightly)

```bash
# Scheduler needs roles/run.invoker on each scheduled job.
SCHED_SA="dma-insights-scheduler@${PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create dma-insights-scheduler \
  --display-name="DMA Insights Cloud Scheduler" --project=$PROJECT_ID

for JOB in drive-crawler sheet-poller; do
  gcloud run jobs add-iam-policy-binding dma-insights-${JOB} \
    --region=$REGION \
    --member="serviceAccount:${SCHED_SA}" \
    --role=roles/run.invoker
done

# 6-hourly drive crawl
gcloud scheduler jobs create http drive-crawler-6h \
  --schedule='0 */6 * * *' \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/dma-insights-drive-crawler:run" \
  --http-method=POST \
  --oauth-service-account-email=$SCHED_SA \
  --location=$REGION

# 5-min sheet poll during US business hours, hourly otherwise
gcloud scheduler jobs create http sheet-poller-business \
  --schedule='*/5 14-23 * * 1-5' \
  --time-zone='UTC' \
  --uri=".../dma-insights-sheet-poller:run" \
  --http-method=POST \
  --oauth-service-account-email=$SCHED_SA \
  --location=$REGION

gcloud scheduler jobs create http sheet-poller-offhours \
  --schedule='0 0-13 * * *' \
  --uri=".../dma-insights-sheet-poller:run" \
  --http-method=POST \
  --oauth-service-account-email=$SCHED_SA \
  --location=$REGION
```

### §10.12 Cloud Run service deploys (with full env wiring)

```bash
# Backend
gcloud run deploy dma-insights-backend \
  --image=us-central1-docker.pkg.dev/$PROJECT_ID/dma-insights/backend:$IMAGE_SHA \
  --region=$REGION \
  --service-account=dma-insights-backend@${PROJECT_ID}.iam.gserviceaccount.com \
  --add-cloudsql-instances=$PROJECT_ID:$REGION:dma-insights-db \
  --set-env-vars="ENV=prod,GCP_PROJECT_ID=$PROJECT_ID,LOG_LEVEL=info,\
ALLOWED_ORIGINS=https://insights.zennify.com,\
GOOGLE_OAUTH_CLIENT_ID=306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com" \
  --set-secrets="DATABASE_URL=dma-insights-db-url:latest,\
REDIS_URL=dma-insights-redis-url:latest,\
GOOGLE_OAUTH_CLIENT_SECRET=dma-insights-oauth-client-secret:latest,\
DMA_BOT_API_KEY=dma-insights-bot-api-key:latest,\
RAG_API_BEARER_KEY=dma-insights-rag-api-key:latest,\
CLAY_WEBHOOK_URL=dma-insights-clay-webhook-url:latest,\
CLAY_WEBHOOK_SECRET=dma-insights-clay-webhook-secret:latest" \
  --update-secrets="/secrets/jwt-private.pem=dma-insights-jwt-private-pem:latest,\
/secrets/jwt-public.pem=dma-insights-jwt-public-pem:latest" \
  --set-env-vars="JWT_PRIVATE_KEY_PATH=/secrets/jwt-private.pem,\
JWT_PUBLIC_KEY_PATH=/secrets/jwt-public.pem" \
  --memory=2Gi --cpu=2 \
  --min-instances=1 --max-instances=10 \
  --port=8000 \
  --no-allow-unauthenticated  # frontend acts as auth proxy
```

After this command, hit `/readyz`:
```bash
curl -sf $(gcloud run services describe dma-insights-backend \
  --region=$REGION --format='value(status.url)')/readyz | jq .
```
- Output `{"status":"ready","migration_head":"020_..."}` → deploy is live + healthy.
- Output 503 + `migration drift` → run `dma-insights-migrations` job (§T17).
- Service refuses to start → **production-readiness guard caught a
  misconfiguration**; check Cloud Run logs for the typed error
  listing every missing/leaking key.

### §10.13 OAuth client setup (one-time + post-rotation)

```bash
# In GCP Console → APIs & Services → Credentials → OAuth 2.0 Client IDs,
# edit the existing `digital-maturity-assessor` web client:
#   Authorized JavaScript origins:
#     https://insights.zennify.com
#   Authorized redirect URIs:
#     https://insights.zennify.com/api/v1/auth/google/callback

# Rotate the client secret (post-first-prod-login per security policy):
#   1. In OAuth UI → "Reset Secret"
#   2. Update the Secret Manager version:
echo -n "$NEW_SECRET" | \
  gcloud secrets versions add dma-insights-oauth-client-secret --data-file=-
#   3. Force backend revision restart so it picks up :latest:
gcloud run services update dma-insights-backend \
  --region=$REGION --update-env-vars="OAUTH_ROTATED_AT=$(date +%s)"
```

### §10.14 Smoke after every deploy (matches §6.11 + adds §10 layer)

```bash
BE=$(gcloud run services describe dma-insights-backend \
       --region=$REGION --format='value(status.url)')

# 1. Production-readiness guard didn't block startup
curl -sf $BE/healthz | jq .          # status: ok

# 2. Migration drift gate clean
curl -sf $BE/readyz | jq .           # status: ready + migration_head

# 3. All 9 critical routes resolve (per B3 endpoint contract test)
for r in /api/v1/auth/me /api/v1/entities/fce-001/heatmap/subcap/P1C1.1.1 \
         /api/v1/entities/fce-001/platforms/roadmap \
         /api/v1/entities/fce-001/techstack/landscape \
         /api/v1/entities/fce-001/health/version-diff \
         /api/v1/rag/answer /api/v1/rag/answer/stream; do
  STATUS=$(curl -s -o /dev/null -w '%{http_code}' "$BE$r")
  echo "$r → $STATUS"
done
# Expect: 401 (auth required) or 405 (POST-only) — NOT 404.

# 4. Live drive crawl ingests + writes feedback files (§6 + §8)
gcloud run jobs execute dma-insights-drive-crawler \
  --region=$REGION --wait
psql -h /cloudsql/... -d dma_insights -c "
  SELECT after_json->>'state' AS state,
         jsonb_array_length(after_json->'written') AS written
  FROM audit_log WHERE action='drive_feedback_written'
  ORDER BY created_at DESC LIMIT 5;
"
# Expect: state='upload_ok', written=5 per row.
```

If any of these checks fails, the deploy is silently broken — DO NOT
mark it green until the root cause is identified and patched.



## §11 — F6 R-rules (ingestion-time intelligence)

**Why.** Per PRD §6 the parser must enforce 3 detection rules before
ingesting any package:

| Rule | Action | Caught failure |
|---|---|---|
| **R05** Client-provided document | quarantine | external SME deliverable mistakenly dropped into a `*_DMA_*` folder; Insights would silently ingest it as analyst output |
| **R06** Pre-v5.5 framework | downgrade | legacy v5.0 / v5.4 report ingested with v7.0 alias-bridge translation (otherwise `subcap_id` orphans) |
| **R07** Test-case / sample | skip | Nyumba Zetu / sample-bank / __test__ / acme-bank folder ingested into prod entity directory |

**Files.** `app/services/parsers/r_rules.py` (3 detectors + orchestrator
+ severity ladder). 39 tests in `tests/test_r_rules.py` — including
parameterised positive checks against all 5 real packages confirming
NONE matches R07 (so no operator surprises).

**Wiring.** R07 fires upstream of the parser in
`_ingest_folder` (`historical_backfill.py`): a `skip` action writes
a single `import_files` audit row (`status=SKIPPED`, `parser_warnings`
JSONB carries the rule hit) and returns `SKIP:<reason>`. The folder
is operator-overridable via the admin queue. R05/R06 run later in
the parser pipeline with file-level metadata.

**Severity ladder (locked by tests):**
```text
skip (5)  >  quarantine (4)  >  downgrade (3)  >  warn (2)  >  allow (1)
```

**Detection (post-deploy smoke):**
```bash
# Verify R07 catches a synthetic test folder:
psql -h ... -d dma_insights -c "
  SELECT filename, parser_warnings->'r_rules'->0->>'rule_id' AS rule,
         parser_warnings->>'highest_severity' AS severity
  FROM import_files
  WHERE status='SKIPPED'
    AND parser_warnings->>'highest_severity'='skip'
  ORDER BY created_at DESC LIMIT 10;
"
# Expect: rows for any Nyumba/sample/acme folder the scheduler saw.

# Override an R07 skip (operator-only, from admin UI):
psql -h ... -d dma_insights -c "
  UPDATE import_files
  SET status='DETECTED', parser_warnings = parser_warnings ||
      '{\"operator_override\": true, \"override_by\": \"$ADMIN_EMAIL\"}'::jsonb
  WHERE id = '<file_id>';
"
# Then re-trigger crawl; folder will ingest on the next pass.
```

## §12 — Pattern-recognition stress coverage (deep AI / KMeans pipeline)

The peer-pattern KMeans pipeline at `workers/peer_patterns/service.py`
already shipped, but lacked adversarial coverage. This batch adds 15
stress tests that lock the contract:

| Stress scenario | Asserted invariant |
|---|---|
| N=0 cohort | empty list (no row written) |
| N=1 cohort | `label=insufficient_data` (never crash) |
| N=2 cohort | same — below 3-entity floor |
| Zero-variance input | converges to ≥1 cluster, total membership preserved |
| Vector misalignment | union of subcap keysets, rows aligned to union dim |
| Determinism | same input → same membership (modulo cluster permutation) |
| Synthetic 2-cluster cohort | detects ≥ 2 archetypes, silhouette > 0.4 |
| Synthetic 3-cluster cohort | detects ≥ 2 archetypes |
| Silhouette ≥ 0.9 on well-separated | proves the metric works |
| Pick-k correctness | chooses k=2 on 2-cluster data |
| Real-shape rollup (5 × 700) | ≥1 archetype, total=5, silhouette > 0.6 |
| Anti-fabrication | every defining_subcap_id resolves in input keyset |

Real-DMA-shape simulation: 5 entities × 700 subcaps → 4 archetypes
detected with silhouette 0.67 (high separability). All 15 stress
tests pass.

**Detection.** The stress suite runs as part of CI (`pytest -q`).
A pattern-recognition regression (silhouette drop / membership
non-determinism / fabricated subcap IDs) fails the build.



## §13 — 2026-05-28 production-incident remediation runbook

Codifies the operator-facing commands for the four fixes shipped in
commits `b7ccb4f` (H1 + H5), `cba7ddf` (H2 + H6 + H7 + H8), `8271ee3`
(sync-DSN unification), `f715b2e` (e2e suite), and `<this commit>`
(diagnostics + self-heal repair endpoints).

The 2026-05-28 historical backfill log surfaced FOUR distinct
silent-no-op classes:

| Class | Count per run | Root cause | Fixed by |
|---|---|---|---|
| `source_folder_id` column missing | 26 | SQL typo in post-commit Drive feedback | b7ccb4f (H5) |
| `DATABASE_URL_SYNC not set` warnings | 14 | Terraform worker spec only injects `DATABASE_URL` | b7ccb4f → 8271ee3 (H1) |
| `no DMA package detected` parse failures | 16 | `_find_root` required MANIFEST.json | cba7ddf (H6) |
| `no run manifest found` parse failures | 5 | Same root cause as H6 | cba7ddf (H6) |

Plus 2 latent issues exposed by the fixes:

| Class | Symptom after fix | Surfaced by |
|---|---|---|
| Mid-run progress invisible | `job_executions.folders_seen` stays NULL until completion | cba7ddf (H2 fix) |
| Catalogue child rows missing | New `catalogue_empty_for_version` warning fires per scored package | cba7ddf (H8 fix) |

### §13.1 — Post-deploy verification checklist

Run these after the new image is live. Each command has an expected
output; anything else means a fix didn't land.

```bash
# 0. Pin the project + repo root.
export PROJECT_ID="$(gcloud config get-value project)"
export REPO_ROOT="$HOME/Accelerate"

# 1. Confirm the new image SHA is deployed to Cloud Run.
gcloud run services describe dma-insights-backend \
  --region us-central1 --format='value(spec.template.containers[0].image)'
# Expected: ends with the SHA you just deployed.

# 2. Trigger a fresh historical backfill.
gcloud run jobs execute dma-insights-historical-backfill \
  --region us-central1 --wait

# 3. Confirm the 4 P0 error classes are GONE.
gcloud logging read '
  resource.type="cloud_run_job"
  AND resource.labels.job_name="dma-insights-historical-backfill"
  AND (
    textPayload=~"source_folder_id"
    OR textPayload=~"DATABASE_URL_SYNC not set"
    OR textPayload=~"no DMA package detected"
    OR textPayload=~"no run manifest found"
  )
' --limit 10 --freshness=30m --format='value(textPayload)'
# Expected: NO MATCHES. (Pre-fix: 61 matches per run.)

# 4. Confirm the H6 docx-only ingest warning IS firing (one per
#    previously-rejected folder).
gcloud logging read '
  resource.type="cloud_run_job"
  AND resource.labels.job_name="dma-insights-historical-backfill"
  AND textPayload=~"docx_only_package_no_manifest"
' --limit 5 --freshness=30m --format='value(textPayload)'
# Expected: ~21 matches (previously-rejected folders now ingesting).

# 5. Confirm job_executions counters are now updating mid-run.
#    (See §13.2 below for the cloud-sql-proxy + psql pattern.)
```

### §13.2 — Cloud SQL access via `infra/dma-psql.sh`

`gcloud sql connect` prompts for a password every session, and a plain
`psql -h 127.0.0.1 -p 5432` fails with "Connection refused" because
Cloud SQL isn't directly reachable — `cloud-sql-proxy` has to be
running first. The `dma-psql.sh` helper handles BOTH (proxy + password)
in one command, then cleans up the proxy on exit. All args pass
straight through to `psql`:

```bash
PSQL="$(git rev-parse --show-toplevel)/apps/dma-insights/infra/dma-psql.sh"

# Interactive shell:
bash "$PSQL"

# One-off inspections (any psql flag works):
bash "$PSQL" -c '\d ccg_catalog_versions'
bash "$PSQL" -c 'SELECT version, frozen_at, notes FROM ccg_catalog_versions ORDER BY released_at;'

# Connect as the app user instead of postgres:
DB_USER=dma_insights_app bash "$PSQL" -c 'SELECT 1'
```

Auth resolution (never prompts): `$PGPASSWORD` → `~/.dma-pg-superuser-pw`
→ Secret Manager `dma-insights-pg-superuser-pw` → the legacy
`dma-insights-database-url-superuser` DSN secret.

### §13.3 — Verify job_executions lifecycle is live

```bash
# Should show the most recent backfill row with non-NULL counters,
# status='succeeded' (or 'failed' with a real error_message).
# NEVER status='running' with all-NULL counters indefinitely.
# dma-psql.sh (§13.2) handles proxy + password automatically.
bash "$(git rev-parse --show-toplevel)/apps/dma-insights/infra/dma-psql.sh" -c "
SELECT id, job_name, status,
       folders_seen, files_parsed, files_skipped, files_errored,
       started_at, completed_at, duration_sec,
       LEFT(COALESCE(error_message, ''), 80) AS error_excerpt
  FROM job_executions
 WHERE started_at > NOW() - INTERVAL '1 hour'
 ORDER BY started_at DESC
 LIMIT 5;
"
```

Expected columns:
- `folders_seen` and `files_parsed` populate within the first 60s of the run
  (post H2 fix; pre-fix they stayed NULL until completion).
- `status` flips to `succeeded` or `failed` at the end with `completed_at`
  and `duration_sec` populated.

### §13.4 — Catalogue band-aid: the FK pre-requisite

Two `ccg_catalog_versions` rows MUST exist before the backfill runs,
because production Drive packages reference `v7.0` (current) and
`v5.5` (legacy pre-thread DMAs). Without them, `runs_ccg_catalog_version_fkey`
violations block every persist attempt.

The new self-heal endpoint inserts them idempotently:

```bash
# Sign in as admin (one-time per session).
COOKIE_JAR=/tmp/dma_admin_cookies.txt
curl -sf -c "$COOKIE_JAR" -X POST \
  "https://${BACKEND_URL}/api/v1/auth/dev-login?email=mishley.otiende@zennify.com"
# In prod (ENV != local), dev-login returns 403; use real OAuth instead.

# Repair: insert v7.0 + v5.5 band-aid rows (default).
curl -sf -b "$COOKIE_JAR" -X POST \
  -H 'Content-Type: application/json' \
  "https://${BACKEND_URL}/api/v1/admin/repair:catalogue-stubs" \
  -d '{"versions": ["v7.0", "v5.5"]}'
# Expected: {"inserted_versions": ["v7.0","v5.5"], "count": 2}
# On re-run:    {"inserted_versions": [], "count": 0}  (idempotent)
```

Or run the SQL directly (when the backend isn't reachable):

```sql
INSERT INTO ccg_catalog_versions
    (version, released_at, source_sha256s, loader_run_id, frozen_at, notes)
VALUES
    ('v7.0', NOW(), '{}'::jsonb, gen_random_uuid(), NOW(),
     'band-aid: pre-loader placeholder; replace via ccg_loader job'),
    ('v5.5', NOW(), '{}'::jsonb, gen_random_uuid(), NOW(),
     'band-aid: legacy DMA package compatibility')
ON CONFLICT (version) DO NOTHING;
```

**Critical contract**: `ON CONFLICT DO NOTHING` is the safety guard.
Once the real ccg_loader has populated `source_sha256s` /
`loader_run_id` with real metadata, re-running the repair endpoint
MUST NOT overwrite those values. The integration test
`test_repair_catalogue_stubs_self_heal` locks this against regression.

### §13.5 — Detecting the H8 red flag (catalogue placeholder, no children)

After the band-aid is in place, every scored package will land with
`scores=0` and emit a `catalogue_empty_for_version` warning until the
ccg_loader runs FOR REAL (i.e. actually populates `ccg_subcaps` child
rows). The new diagnostics endpoint surfaces this:

```bash
curl -sf -b "$COOKIE_JAR" \
  "https://${BACKEND_URL}/api/v1/admin/diagnostics" | jq .
```

```json
{
  "catalogue_versions_referenced_but_missing": [],
  "catalogue_versions_with_no_child_rows": [
    {"version": "v7.0", "frozen_at": "2026-05-28T...", "notes": "band-aid: ..."},
    {"version": "v5.5", "frozen_at": "2026-05-28T...", "notes": "band-aid: ..."}
  ],
  "job_executions_stuck_running": [],
  "runs_with_unresolved_catalogue": [
    {"id": "...", "request_id": "DMA-ASM-WSFS-...", "ccg_catalog_version": "v7.0"},
    ...
  ],
  "_summary": {"total_issues": 22, "healthy": false}
}
```

### §13.6 — Running the ccg_loader for real (populates ccg_subcaps)

Once the band-aid is in place + the operator has uploaded the
canonical v7.0 pillar workbooks to GCS:

```bash
# 0. Pin the bucket name (created by Terraform as
#    "${PROJECT_ID}-catalogue-staging").
export BUCKET="${PROJECT_ID}-catalogue-staging"

# 1. Upload the 4 pillar workbooks.
ls "$REPO_ROOT/apps/dma-insights/docs/reference/catalogue/v7.0/"Pillar_*.xlsx | wc -l
# Expected: 4

gcloud storage cp \
  "$REPO_ROOT/apps/dma-insights/docs/reference/catalogue/v7.0/"Pillar_*.xlsx \
  "gs://${BUCKET}/v7.0/"

# 2. Trigger the loader (its baked args read gs://${BUCKET}/v7.0/).
gcloud run jobs execute dma-insights-ccg-loader \
  --region us-central1 --wait

# 3. Verify ccg_loader_runs row was actually written. Pre-fix this
#    silently no-op'd because DATABASE_URL_SYNC was missing; post-
#    8271ee3, it derives the sync DSN from DATABASE_URL.
psql ... -c "
SELECT id, version, status, loader_started_at,
       jsonb_object_keys(source_files) AS file
  FROM ccg_loader_runs
 ORDER BY loader_started_at DESC LIMIT 5;
"
# Expected: status='AWAITING_APPROVAL', 4 file keys for Pillar_1..4.

# 4. Approve to promote staging → canonical ccg_subcaps.
curl -sf -b "$COOKIE_JAR" -X POST \
  "https://${BACKEND_URL}/api/v1/admin/catalogue/<loader_run_id>:approve"

# 5. Confirm ccg_subcaps now populated.
psql ... -c "SELECT version, COUNT(*) AS subcaps FROM ccg_subcaps GROUP BY version;"
# Expected: v7.0 | 851 (the canonical full v7 catalogue size).

# 6. Re-confirm: diagnostics endpoint now shows healthy.
curl -sf -b "$COOKIE_JAR" "https://${BACKEND_URL}/api/v1/admin/diagnostics" \
  | jq '._summary'
# Expected: {"total_issues": 0, "healthy": true}
```

### §13.7 — Self-heal: closing stuck `running` jobs

If a worker dies mid-run (Cloud Run timeout, OOM, deploy in-flight),
its `job_executions` row stays at `status='running'` forever. The
admin UI then displays "in progress" indefinitely.

```bash
curl -sf -b "$COOKIE_JAR" -X POST \
  "https://${BACKEND_URL}/api/v1/admin/repair:close-stuck-jobs"
```

Returns:
```json
{
  "closed_count": 1,
  "closed": [
    {"id": "...", "job_name": "historical_backfill",
     "started_at": "2026-05-28T03:21:14+00:00"}
  ]
}
```

**Safety guards** (locked by `test_repair_close_stuck_jobs_filter`):
- Only `status='running'` rows are touched (already-terminal rows untouched).
- Only rows started >30 min ago are closed (actively-progressing
  workers untouched).

### §13.8 — Cloud Shell IPv6 routing gotcha

Cloud Shell prefers IPv6 by default. Some Google API endpoints
(notably `pubsub.googleapis.com`) return AAAA records that Cloud
Shell's network can't route, causing `cannot assign requested address`
on terraform/gcloud calls. Every helper script in this repo sets
`GODEBUG=netdns=go` to force Go's DNS resolver (which prefers IPv4).

If you run `terraform apply` or `gcloud` commands **directly** from
Cloud Shell (bypassing the wrapper scripts), prepend it:

```bash
GODEBUG=netdns=go terraform apply ...
```

The `test_godebug_netdns_set_in_every_cloud_shell_script`
infra-safeguard pins this requirement on every release script.

### §13.9 — Validation checklist for the next operator (5-min smoke)

| Check | Command | Pass criteria |
|---|---|---|
| New image deployed | §13.1 step 1 | SHA matches expected |
| Backfill runs | §13.1 step 2 | exit 0 |
| P0 errors gone | §13.1 step 3 | 0 matches |
| H6 ingest active | §13.1 step 4 | ~21 matches |
| job_executions populates | §13.3 | counters non-NULL within 60s |
| Catalogue parent rows exist | §13.4 | repair returns count: 0 (re-run idempotent) |
| Catalogue children populated | §13.6 step 5 | v7.0: 851 subcaps |
| Diagnostics clean | §13.6 step 6 | healthy: true |

If every row passes → the 2026-05-28 incident is fully closed.


## §14 — Resilience surfaces shipped 2026-05-28 (track 2 of 3)

Three operator-facing resilience surfaces landed on top of the §13
remediation. Each is opt-in for operators but always-on for the
backend (i.e. the deploy doesn't need any per-environment toggle).

### §14.1 — Backend startup diagnostic

Every backend revision runs `app/services/startup_diagnostic.py`
during `lifespan` startup. It runs the same 4 SQL queries as
`GET /admin/diagnostics` and emits structured Cloud Logging entries
for each:

```
startup_diagnostic.healthy
  overall_healthy=true
  catalogue_versions_with_no_child_rows=0
  job_executions_stuck_running=0
  ...
```

or, when issues exist:

```
startup_diagnostic.issue_detected
  category="catalogue_versions_with_no_child_rows"
  count=2
  human="ccg_catalog_versions rows exist but have no ccg_subcaps children — loader has not run for real"
  sample_rows=[{"version":"v7.0"},{"version":"v5.5"}]

startup_diagnostic.summary
  overall_healthy=false
  total_issues=2
  remediation="Use POST /api/v1/admin/repair:catalogue-stubs ..."
```

Find them after a deploy:
```bash
gcloud logging read '
  resource.type="cloud_run_revision"
  AND resource.labels.service_name="dma-insights-backend"
  AND jsonPayload.event=~"startup_diagnostic"
' --limit 20 --freshness=15m --format='value(jsonPayload.event,jsonPayload.category,jsonPayload.count)'
```

Hard contract (locked by `test_diagnostic_handles_engine_unavailable_gracefully`,
`test_diagnostic_handles_connect_failure_gracefully`): the diagnostic
MUST NEVER raise. If the DB is unreachable at startup the deploy
still completes so the operator can hit `/healthz` and roll back if
needed.

### §14.2 — Explicit `DATABASE_URL_SYNC` injection (Terraform)

Pre-2026-05-28 the worker + backend specs in
`infra/terraform/main.tf` only injected `DATABASE_URL` (asyncpg).
Sync code paths (job_executions lifecycle, synthesis_cache invalidation,
ccg_loader_runs writes) relied on the application-level
`resolve_sync_dsn()` resolver to derive the +psycopg form.

That fallback still exists (belt-and-braces) but Terraform now also
explicitly injects a new secret `dma-insights-database-url-sync`
into both:

  - `google_cloud_run_v2_service.backend`
  - `google_cloud_run_v2_job.worker[*]` (every worker job)

Visible via:
```bash
gcloud run services describe dma-insights-backend \
  --region us-central1 \
  --format='value(spec.template.containers[0].env)' \
  | grep DATABASE_URL_SYNC
# Expected: present, sourced from `dma-insights-database-url-sync`

gcloud run jobs describe dma-insights-historical-backfill \
  --region us-central1 \
  --format='value(template.template.containers[0].env)' \
  | grep DATABASE_URL_SYNC
# Expected: present
```

The new secret holds the SAME password as `dma-insights-database-url`
(both reference `random_password.db_app_user`), just with the
`+psycopg` driver suffix. Password rotation via
`recover-db-passwords.sh` continues to work — the script touches
`force_revision_rolls` which now also rolls revisions sourcing the
new secret.

Regression locked by `test_terraform_injects_database_url_sync_into_workers_and_backend`.

### §14.3 — Cloud Logging deep links in `/admin/jobs/executions`

Every `JobExecutionOut` response now includes a `logs_url` field
pointing at Cloud Logging filtered to the worker's stdout/stderr for
that specific execution:

```json
{
  "id": "abc-...",
  "job_name": "historical_backfill",
  "status": "failed",
  "error_message": "...",
  "logs_url": "https://console.cloud.google.com/logs/query;query=...?project=digital-maturity-assessor"
}
```

Two filter modes:
  - **execution_name available** → filter to that exact Cloud Run
    execution (ZERO noise).
  - **execution_name not available** (e.g. older rows pre-instrumentation)
    → ±10-minute timestamp window around `started_at`. Coarser but
    still useful.

The admin UI renders this as a "View logs" link in each row's
action menu, so the operator can jump from a stuck or failed
job to the worker's stdout/stderr in one click without manually
building the Cloud Logging filter URL.

Returns `null` (omitted from response) when:
  - `gcp_project_id` is empty (local dev / tests)
  - The row has no `job_name` (synthetic / corrupted data)

### §14.4 — Operator runbook delta

Add these to your post-deploy verification:

```bash
# 5a. Confirm the startup diagnostic ran (look for a single
#     `.healthy` OR a `.summary` line per backend revision).
gcloud logging read '
  resource.type="cloud_run_revision"
  AND resource.labels.service_name="dma-insights-backend"
  AND (
    jsonPayload.event="startup_diagnostic.healthy"
    OR jsonPayload.event="startup_diagnostic.summary"
  )
' --limit 3 --freshness=15m \
  --format='value(timestamp,jsonPayload.event,jsonPayload.total_issues)'

# 5b. Confirm DATABASE_URL_SYNC is in the worker env (not just
#     derived via the fallback).
for job in historical-backfill drive-crawler ccg-loader embedder; do
  echo "=== $job ==="
  gcloud run jobs describe "dma-insights-$job" --region us-central1 \
    --format='value(template.template.containers[0].env)' \
    | grep -o 'DATABASE_URL_SYNC' | head -1
done
# Expected: "DATABASE_URL_SYNC" prints for every job.

# 5c. Confirm a recent failed job_executions row has a usable logs_url.
curl -sb "$COOKIE_JAR" \
  "https://${BACKEND_URL}/api/v1/admin/jobs/executions?limit=5" \
  | jq '.items[] | {id, job_name, status, logs_url}'
# Expected: logs_url populated as a console.cloud.google.com URL for
#           every row that has been through Cloud Run dispatch.
```


## §15 — Operator self-serve catalogue upload (2026-05-28)

The `/admin/catalogue:upload` route is now end-to-end functional.
Pre-2026-05-28 it staged to a local `/tmp` directory + published a
Pub/Sub message with no subscriber, so the ccg_loader Cloud Run Job
never actually ran. Operators had to manually `gcloud storage cp`
workbooks + `gcloud run jobs execute` for every catalogue version.

Post this commit, the route:
  1. Uploads workbook bytes to `gs://${PROJECT_ID}-catalogue-staging/v<X.Y>/<filename>`
     via `app/services/catalogue_staging.py::upload_workbook_to_staging`.
  2. INSERTs a `job_executions` row with status='running' and the
     staging path captured in `args` (jsonb) for forensics.
  3. Dispatches the ccg_loader Cloud Run Job directly via
     `cloud_run_dispatch.dispatch_job` (Cloud Run Jobs Run API,
     NOT Pub/Sub) with `--version=<v>` and `--workbooks-dir=gs://...`
     as the run override args.
  4. On dispatch failure, marks the row failed with
     `dispatch_failed:<reason>` so the admin UI never shows
     "running" forever for a job that won't start.

### §15.1 — End-to-end catalogue load via the admin UI

```text
1. Admin → Catalogue tab → "Upload v7.0 pillar workbooks" panel
2. Drop the 4 Pillar_*.xlsx files (one at a time, or one ZIP)
3. Frontend POSTs each to /admin/catalogue:upload with version=v7.0
4. Backend uploads to gs://${PROJECT_ID}-catalogue-staging/v7.0/
5. Backend dispatches ccg_loader Cloud Run Job:
     python -m workers.ccg_loader.main \
       --version v7.0 \
       --workbooks-dir gs://${PROJECT_ID}-catalogue-staging/v7.0/
6. Worker downloads from GCS, parses, validates, writes
   ccg_loader_runs row with status='AWAITING_APPROVAL'.
7. Admin → Catalogue queue → click "Apply" on the awaiting row.
   /admin/catalogue/{run_id}:approve promotes staging → canonical
   ccg_subcaps / ccg_pillars / ccg_capabilities.
```

### §15.2 — Resilience properties of the new path

| Failure mode | Pre-fix behaviour | Post-fix behaviour |
|---|---|---|
| GCS bucket missing | upload route 500s | falls back to /tmp, `backing=local_fallback` in response so operator sees the degraded state |
| GCS perms denied | upload route 500s | same fallback as above |
| Dispatch fails (project_id missing, IAM denied) | job_executions stays `running` forever | row flipped to `failed` with `dispatch_failed:<reason>` |
| Operator re-uploads same file | accumulates duplicate /tmp dirs | idempotent — same SHA → same GCS path; ON CONFLICT semantics in GCS overwrite |
| Worker crashes mid-load | job_executions stays `running` forever | covered by `/admin/repair:close-stuck-jobs` (auto-close after 30min) |

### §15.3 — Verification command

```bash
# 0. Sign in.
COOKIE_JAR=/tmp/dma_admin_cookies.txt
curl -sf -c "$COOKIE_JAR" -X POST \
  "https://${BACKEND_URL}/api/v1/auth/dev-login?email=mishley.otiende@zennify.com"

# 1. Upload one of the pillar workbooks.
curl -sf -b "$COOKIE_JAR" -X POST \
  -F "workbook=@$REPO_ROOT/apps/dma-insights/docs/reference/catalogue/v7.0/Pillar_1_Comprehensive_Capability_Mapping_v7.0.xlsx" \
  -F "version=v7.0" \
  "https://${BACKEND_URL}/api/v1/admin/catalogue:upload" | jq .
```

Expected response:
```json
{
  "execution_id": "abc12345-...",
  "uploaded_at": "2026-05-28T...",
  "uploaded_filename": "Pillar_1_Comprehensive_Capability_Mapping_v7.0.xlsx",
  "uploaded_bytes": 4194304,
  "workbooks_dir_arg": "gs://digital-maturity-assessor-catalogue-staging/v7.0/",
  "backing": "gcs",
  "version_hint": "v7.0",
  "dispatch_reason": "dispatched",
  "next_step": "Poll /api/v1/admin/jobs/executions/abc12345-... for status..."
}
```

### §15.4 — Operations panel (frontend visibility)

`frontend/src/components/OperationsPanel.tsx` is now rendered at the
top of the Admin page. Polls:
  - GET /admin/diagnostics every 10s
  - GET /admin/jobs/executions every 3s when any job is running,
    every 30s otherwise

Surfaces:
  - 4 diagnostic cards (one per non-empty category)
  - 2 repair buttons:
      "Repair catalogue stubs" → POST /admin/repair:catalogue-stubs
      "Close stuck jobs"       → POST /admin/repair:close-stuck-jobs
  - Recent job table with progress + duration + a "View logs ↗" link
    per row that opens Cloud Logging filtered to that exact execution

Render-state matrix (locked by 7 vitest tests):
  loading       → "Loading diagnostics…"
  error         → "Couldn't load diagnostics: <message>"
  healthy       → "✓ All operational diagnostics healthy"
  issues        → "⚠ N operational issues detected" + per-category cards
  repair-busy   → button disabled + inline spinner; toast on result


## §16 — Per-folder quarantine + `--retry-failed-only` backfill (2026-05-28, track 3 of 3)

### Problem this solves

The 2026-05-28 historical-backfill run processed 115 Drive folders.
The actual outcome was a mixture:

  - 5/115 ingested cleanly
  - ~50/115 legitimate skips (no DMA report DOCX in the folder, or
    malformed package shapes the parser couldn't grok)
  - ~60/115 real failures (FK violations against `ccg_catalog_versions`
    before the catalogue stubs landed; a few `failed_persist` from
    stale subcap_id aliases)

Pre-fix, the **only signal** the operator had was the streaming stdout
of the Cloud Run Job. There was no row-per-folder record of the
outcome, so a second invocation had no way to filter to JUST the
failures — re-running re-processed every folder regardless. That's
fine for idempotency, but it triples the wall-clock time of every
retry cycle.

### What we shipped

#### 1. Migration `022_backfill_quarantine`

`apps/dma-insights/backend/alembic/versions/022_backfill_quarantine.py`

Creates `backfill_quarantine` — one row per (run_id, drive_folder_id):

```sql
CREATE TABLE backfill_quarantine (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL,           -- job_executions.id (NO FK)
    drive_folder_id VARCHAR(64) NOT NULL,
    folder_name     TEXT NOT NULL,
    outcome         VARCHAR(32) NOT NULL,    -- locked enum below
    reason          TEXT,
    error_message   TEXT,
    ingested_run_id UUID,
    processed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT ck_backfill_quarantine_outcome CHECK (outcome IN (
        'ok',
        'skipped_no_report',
        'skipped_already_ingested',
        'failed_parse',
        'failed_persist',
        'failed_other'
    ))
);

CREATE INDEX ix_backfill_quarantine_folder_recency
    ON backfill_quarantine (drive_folder_id, processed_at DESC);
CREATE INDEX ix_backfill_quarantine_run_id
    ON backfill_quarantine (run_id);
```

Why NO foreign key on `run_id → job_executions.id`:
  - The historical_backfill worker writes quarantine rows BEFORE the
    job_executions row is finalised at completion.
  - The worker can also be invoked via `gcloud run jobs execute` where
    the job_executions row is created by the post-run reconciler
    (track_job_execution + DMA_JOB_EXECUTION_ID env var).
  - Either way, quarantine has to be able to stand alone — the FK
    would prevent inserts and silently break the per-folder ledger.

The `(drive_folder_id, processed_at DESC)` index makes the dominant
query — "latest outcome per folder" via `DISTINCT ON (drive_folder_id)`
— land in ≤ 10 ms even with thousands of rows.

#### 2. `historical_backfill.py` — three new helpers + flag

`apps/dma-insights/backend/app/scripts/historical_backfill.py`

```python
def _classify_outcome(res: str) -> tuple[str, str, str | None, str | None]:
    """Pure function — maps res string to (outcome, reason, ingested_run_id, error_message).

    OK:{uuid}        → ('ok',                        'ingested', uuid, None)
    SKIP:...already  → ('skipped_already_ingested',  body,       None, None)
    SKIP:...         → ('skipped_no_report',         body,       None, None)
    ERROR:parse:msg  → ('failed_parse',              'parse_failed', None, msg)
    ERROR:persist:m  → ('failed_persist',            'persist_failed', None, m)
    ERROR:...        → ('failed_other',              'other',     None, full)
    (anything else)  → ('failed_other',              'unrecognized_result', None, full)
    """
```

Pure, no I/O, no DB — easy to unit-test (10 branches, every state
covered by `tests/test_backfill_quarantine.py::TestClassifyOutcome`).

```python
def _write_quarantine_row(...) -> None:
    """Best-effort sync INSERT. Swallows EVERY exception so a quarantine-write
    failure never blocks the backfill loop. Uses the shared sync-DSN resolver
    so it works in both Cloud Run Jobs (where DATABASE_URL_SYNC is wired via
    secret_key_ref) and in local CLI invocations.

    Contract:
      - no run_id  → returns silently (no row to FK back to)
      - no DSN     → returns silently
      - DB error   → emits a ::warning:: line, returns
    """
```

```python
def _load_retry_targets() -> set[str]:
    """SELECT DISTINCT ON (drive_folder_id) drive_folder_id, outcome
       FROM backfill_quarantine
       ORDER BY drive_folder_id, processed_at DESC

    Returns the set of drive_folder_id values whose LATEST outcome is one of:
      - failed_parse / failed_persist / failed_other  (real errors — retry)
      - skipped_no_report                              (operator may have
                                                        added a DMA DOCX)

    NEVER retried:
      - ok                       (already ingested)
      - skipped_already_ingested (intentional)

    DB failure → returns empty set (caller treats as 'nothing to retry').
    """
```

#### 3. The `--retry-failed-only` flag

```bash
# Full first-pass over every folder (default):
python -m app.scripts.historical_backfill

# Re-run JUST the folders whose latest outcome was failed_* or skipped_no_report:
python -m app.scripts.historical_backfill --retry-failed-only

# Combine: scan a different root folder + retry-only.
python -m app.scripts.historical_backfill <ROOT_FOLDER_ID> --retry-failed-only
```

Operator output:

```text
historical_backfill: --retry-failed-only — 60 folder(s) flagged for retry
                     (failed_* or skipped_no_report latest outcome)
historical_backfill: scanning Drive folder 1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P
historical_backfill: root folder accessible — name='DMA Assets',
                     mimeType='application/vnd.google-apps.folder'
historical_backfill: found 115 candidate folder(s) matching pattern
                     (default: contains the token "DMA")
historical_backfill: --retry-failed-only filtered 115 → 60 folder(s)
[1/60] RegionsBank_DMA_20260518 (ok=0 skip=0 fail=0)
   ✓ run_id=550e8400-e29b-41d4-a716-446655440000
…
```

#### 4. Per-folder loop instrumentation

After every folder is processed (OK / SKIP / ERROR), the loop calls
`_classify_outcome(res)` + `_write_quarantine_row(...)`. The
`_ex.execution_id` (from the `track_job_execution` context manager)
threads through as the `run_id`. If the tracker isn't active (running
outside `track_job_execution`, e.g. local CLI without
DMA_JOB_EXECUTION_ID), `run_id=None` is passed and the helper returns
silently — no rows written, no crash.

### Operator runbook — retry the 60 failures (one-click UI workflow)

The flow is now self-serve from the Admin → Operations panel:

1. Open `/admin` as an ADMIN user. The Operations panel polls
   `/admin/diagnostics` every 10s.

2. If the **Catalogue placeholder without children** card is rendered,
   click **Repair catalogue stubs**. The placeholder rows land
   immediately; the next 10s poll shows the card vanish.

3. The **Drive folders flagged for retry** card surfaces the count
   (e.g. "60") + lists the first 5 folder names + outcomes. Click
   **Retry failed folders**.

4. The button POSTs
   `/api/v1/admin/jobs/historical_backfill:execute` with
   `{ mode: "retry", args: { extra_args: ["--retry-failed-only"] } }`.
   The backend:
     - Validates `mode="retry"` against `JOB_REGISTRY["historical_backfill"]`.
     - **Auto-closes any stuck row** of the SAME `job_name` (status='running'
       AND started_at < NOW() - 30min) before INSERTing the new one — so
       the operator never has to click "Close stuck jobs" first.
     - INSERTs a new `job_executions` row with status='running'.
     - Dispatches the Cloud Run Job via the REST API (or fires a local
       subprocess in non-prod) with `args=["--retry-failed-only"]` —
       the worker reads `sys.argv` and narrows the candidate set via
       `_load_retry_targets()`.

5. The Recent jobs table polls at 3s while running. Click **View logs ↗**
   to open Cloud Logging filtered to that execution.

6. After the retry completes, the next 10s diagnostics poll re-reads
   `backfill_folders_flagged_for_retry`. If the catalogue stubs were
   landed first, the count typically shrinks to 0 (all failures
   resolved) or a small remainder (genuine parser bugs not yet fixed).

### Pre-dispatch self-heal — what happens automatically

When the operator dispatches ANY job via `/jobs/{job_name}:execute`,
the BE runs this UPDATE INSIDE the same transaction as the new INSERT:

```sql
UPDATE job_executions
   SET status='failed', completed_at=NOW(),
       error_message='auto-closed pre-dispatch — running >30min with '
                     'no progress; superseded by new dispatch'
 WHERE job_name = :name
   AND status = 'running'
   AND started_at < NOW() - INTERVAL '30 minutes';
```

Why it's needed:
  - A previous `historical_backfill` execution might have died externally
    (Cloud Run hit its 1-hour ceiling, OOM, container crash) leaving
    its job_executions row stuck `running`.
  - Without this hook, the admin UI shows two parallel `running` rows
    after the next dispatch and the operator has to manually click
    "Close stuck jobs" first.

Why it's safe:
  - 30-minute floor — no chance of clobbering an active worker.
  - Best-effort wrap — any SQL error here is logged + swallowed; the
    new INSERT still fires.
  - Only matches the SAME `job_name` — concurrent dispatches of
    different jobs are unaffected.

### Manual operator path (if the UI is unreachable)

```bash
# CLI fallback — same effect as clicking the UI button.
gcloud run jobs execute dma-insights-historical-backfill \
  --region=us-central1 \
  --args=--retry-failed-only \
  --wait

# Verify the failure set shrank.
psql -tA -c "
SELECT outcome, count(*)
  FROM (
    SELECT DISTINCT ON (drive_folder_id) outcome
      FROM backfill_quarantine
  ORDER BY drive_folder_id, processed_at DESC
  ) latest
GROUP BY outcome
ORDER BY outcome;
"
# Expected before retry:  ok=5  skipped_no_report=~50  failed_*=~60
# Expected after retry:   ok=~65 skipped_no_report=~50 failed_*=0
```

### What this is NOT

- NOT a replacement for fixing the parser bug that drove the
  `failed_parse` failures. Use `--retry-failed-only` once after a
  parser fix lands; subsequent runs on a healthy parser are normal
  full backfills (skip the flag).
- NOT a substitute for the catalogue stubs repair. If you flip
  `--retry-failed-only` without first landing the catalogue placeholders,
  every retry re-fails with the same FK error and writes another
  `failed_persist` row.
- NOT an alternative state machine to `job_executions`. The
  quarantine table is per-FOLDER (1 row per attempt × folder),
  whereas `job_executions` is per-RUN (1 row per backfill invocation).

### Tests

`apps/dma-insights/backend/tests/test_backfill_quarantine.py` —
21 tests (15 pure-logic + 6 live-PG, skipped without SEED_CI_PG_URL):

- `TestClassifyOutcome` — 10 tests cover every outcome branch + 2
  edge cases (empty string, unrecognised prefix).
- `TestWriteQuarantineRowBestEffort` — 3 tests confirm the
  swallows-every-error contract holds (no run_id / DB unreachable /
  no DSN).
- `TestLoadRetryTargetsFailureModes` — 2 tests confirm the same for
  the loader.
- `TestQuarantineLivePg` — 6 tests against a real PG with migration
  022 applied:
  - real INSERT writes a real row that reads back
  - real INSERT with `failed_parse` outcome reads back with
    `error_message` preserved
  - the CHECK constraint actually rejects a bogus outcome
  - `_load_retry_targets` returns exactly the 4 actionable outcomes
    out of the 6-folder matrix
  - the "latest outcome per folder" rule actually uses the most
    recent row (fail → ok flow: no retry)
  - empty DB returns empty set (no test-prefix collision)

`apps/dma-insights/backend/tests/test_retry_failed_only_e2e_contract.py` —
11 tests pinning the wire-format across the full BE→FE→worker chain.
Every link of `FE POST → JOB_REGISTRY → JOB_DISPATCH → extra_args →
args_list → sys.argv → _load_retry_targets → /admin/diagnostics` has
a regression lock. When this file fails, the failure message names
the exact link that drifted.

`apps/dma-insights/frontend/src/components/__tests__/OperationsPanel.test.tsx` —
204 frontend tests including the new 3 for the retry surface:
  - card renders with sample rows when category non-empty
  - click dispatches the correct POST payload + surfaces dispatch toast
  - card OMITTED when migration 022 isn't applied (key absent from response)

### Self-heal contract

Every line of this track is best-effort:

**Backfill loop (worker):**
1. Runs `_classify_outcome` (pure — never raises).
2. Runs `_write_quarantine_row` (catches every exception — emits
   `::warning::` log line but never throws).
3. Continues to the next folder regardless.

**Admin dispatch (backend):**
1. Pre-dispatch auto-closes stuck rows of the same `job_name` —
   the operator's "Retry failed folders" click works even if a
   previous dispatch died externally.
2. The `/admin/diagnostics` endpoint OMITS the
   `backfill_folders_flagged_for_retry` key when the table doesn't
   exist (migration 022 not applied) — the UI's `?? []`
   null-coalesce handles both states cleanly. No 500 ever.
3. `JOB_REGISTRY` rejects unknown modes BEFORE dispatch — a
   FE→BE wire drift returns 400 with the allowed mode list, not
   a stuck worker.

**Operations panel (frontend):**
1. The retry-card renders only when `length > 0` AFTER null-coalesce
   — undefined OR empty array → card hidden.
2. The dispatch button is `disabled` while `isPending` — operator
   can't double-click into two parallel runs.
3. Toast surfaces the new execution id so the operator can scroll
   to the matching row in the Recent jobs table.

Result: a quarantine subsystem outage NEVER blocks ingest progress;
a stuck previous dispatch is auto-recovered on the next click;
a missing migration silently degrades the UI category instead of
breaking the diagnostics page.


## §17 — Operator visibility + abort + smarter retries (2026-05-28)

### Symptoms this addresses

Operator reported three concrete UI failures:
  1. **"Most jobs on the UI are stuck on in progress."** — the Recent
     jobs table showed `status=running` for hours with no counter
     updates.
  2. **"There is even no progress tracker."** — the Progress cell
     rendered the literal string `"in progress"` regardless of how
     many folders the worker had actually processed.
  3. **"You cannot even abort."** — no operator-side mechanism to
     cancel a dispatch beyond waiting for the 30-minute close-stuck-jobs
     repair endpoint to flip the row to failed.

### Root-cause analysis

| Symptom | Root cause | Fix |
|---|---|---|
| Stuck "in progress" string | `summarize_execution` returned literal `"in progress"` for any running row; live counters were ignored | New running-state branch reads `folders_seen + files_parsed + files_skipped + files_errored` and renders `"45/115 folders (39%) — ok=30 skip=12 fail=3"` |
| Counters stale by minutes | `historical_backfill` flushed every 5 folders (~50s at typical folder pace) | Per-folder flush — one cheap UPDATE per folder |
| No abort path | No `mark_cancelled` helper + no admin route to flip a row | New `POST /admin/jobs/executions/{id}:abort` + `mark_cancelled` (idempotent, audit-logged) |
| Operator's abort takes minutes to land | Worker had no signal that the row was cancelled | New `_check_aborted` polls the row's status after every folder; worker exits gracefully when it flips to 'cancelled' |
| Retries no better than original | Single-attempt _ingest_folder with first-line error message | When `--retry-failed-only` is active: 3 attempts with 2s/4s/8s exponential backoff on transient HTTP (403/429/500/502/503/504); full traceback captured into quarantine error_message |

### What changes for the operator

#### Recent jobs table — Progress cell

Pre-fix:
```
Job                  Status     Progress       Started    Duration  Logs
historical_backfill  running    in progress    14:23      —         View logs ↗
```

Post-fix:
```text
Job                  Status     Progress                                  Started   Duration  Actions
historical_backfill  running    45/115 folders (39%) — ok=30 skip=12 fail=3  14:23     2m 15s    [Abort] View logs ↗
```

The Progress cell updates every ~10-15 seconds (one update per folder
processed) so the operator can watch the run advance in real time.

#### Abort button

Every row with `status='running'` now renders an inline **Abort** button.
The flow:

1. Operator clicks **Abort** on a stuck-or-slow job row.
2. Browser shows a `window.confirm()` dialog naming the job + execution
   id ("Abort historical_backfill (id=9f1c0c8a…)? The worker may
   finish its current folder before exiting.").
3. On confirm: POST `/api/v1/admin/jobs/executions/{id}:abort` →
   `mark_cancelled` flips status='running' → 'cancelled' atomically
   in the DB. `completed_at = NOW()`, `error_message = 'aborted by
   {actor.email}: aborted via admin UI'`.
4. The audit_log row is written (best-effort).
5. The worker process polls the row's status after every folder; on
   the next poll it sees `status='cancelled'`, prints
   `"ABORT signal received (row flipped to 'cancelled' by operator).
   Stopping at [45/115]. ..."` and exits 0 (the cancellation was
   intentional, not a failure).
6. The job row stays at status='cancelled' (the worker doesn't
   re-flip it — `mark_succeeded` and `mark_failed` both filter on
   `WHERE id=:id` only, not status — but the operator perceives the
   abort the moment the DB row flips).

Idempotency:
  - Double-clicking Abort: second click is a no-op (the
    `mark_cancelled` UPDATE is gated by `WHERE status='running'`; the
    second call re-reads the existing 'cancelled' state and returns it).
  - Abort on a finished row: returns the row's current state — the
    UI hides the Abort button when status≠'running' so this can't
    happen via the UI, but defensive against direct curl access.

#### Smarter retries

When the operator dispatches `--retry-failed-only`, the worker switches
to a MORE robust per-folder execution model:

| Behaviour | First pass (`mode=full`) | Retry pass (`mode=retry` + `--retry-failed-only`) |
|---|---|---|
| Drive transient HTTP errors (429, 503, 504, 403 rate-limit) | Surface as failed_other immediately | 3 attempts with 2s → 4s → 8s exponential backoff |
| Non-Drive exceptions | Surface immediately | 1 retry on the second attempt (transient DB / network blips recover) |
| Captured error context | First line of the exception | **Full traceback** (truncated to 2 KB) into `backfill_quarantine.error_message` |
| Per-folder tmp dir | Reused if the folder is retried within one run | Fresh tmp dir per attempt — partial downloads from a failed attempt don't poison the next |
| Quarantine row | One per (run, folder) pair | Same — but with richer error_message + attempt count visible in the log line |

The operator's retry click therefore has a higher success rate than
the original pass would have had even if you replayed it verbatim.

### Backend changes

```python
# backend/app/services/job_executions.py — summarize_execution
if status == "running":
    folders_seen = row.get("folders_seen")
    files_parsed = row.get("files_parsed") or 0
    files_skipped = row.get("files_skipped") or 0
    files_errored = row.get("files_errored") or 0
    progressed = files_parsed + files_skipped + files_errored
    if folders_seen is None and progressed == 0:
        return {"result_summary": "starting…", "error_count": 0}
    if folders_seen is not None and folders_seen > 0:
        pct = int(100 * progressed / folders_seen) if folders_seen else 0
        return {
            "result_summary": (
                f"{progressed}/{folders_seen} folders ({pct}%) "
                f"— ok={files_parsed} skip={files_skipped} fail={files_errored}"
            ),
            "error_count": files_errored,
        }
```

```python
# backend/app/services/job_executions_db.py — mark_cancelled
def mark_cancelled(execution_id: str, *,
                   cancelled_by_email: str | None = None,
                   reason: str | None = None) -> dict[str, Any]:
    """RUNNING → CANCELLED. Idempotent — re-running on an
    already-cancelled (or already-finished) row is a no-op via the
    WHERE status='running' filter."""
```

```python
# backend/app/routers/admin.py
@router.post("/jobs/executions/{execution_id}:abort", ...)
async def abort_job_execution(execution_id: str, actor, session) -> JobExecutionOut:
    """Operator-initiated abort."""
```

```python
# backend/app/scripts/historical_backfill.py
def _check_aborted(execution_id: str | None) -> bool:
    """Polls job_executions.status. Returns True iff cancelled.
    Best-effort — every error returns False (worker keeps running)."""

# Per-folder loop:
if _check_aborted(_ex.execution_id):
    print("ABORT signal received ... Stopping at [i/total].")
    return  # exit 0
```

```python
# Retry-with-backoff (worker side):
attempts = 3 if retry_failed_only else 1
for attempt in range(1, attempts + 1):
    try:
        res = await _ingest_folder(...)
        break
    except HttpError as he:
        transient = he.status_code in (403, 429, 500, 502, 503, 504)
        if attempt < attempts and transient:
            await asyncio.sleep(2 ** attempt)
            continue
        res = f"ERROR:drive:... (attempt {attempt}/{attempts})\n{traceback}"
        break
```

### Frontend changes

```tsx
// frontend/src/components/OperationsPanel.tsx
const abortJob = useMutation({
  mutationFn: (executionId: string) =>
    apiPost<JobExecutionOut>(
      `/api/v1/admin/jobs/executions/${executionId}:abort`,
    ),
  onSuccess: (data) => {
    setToast(`Aborted ${data.job_name}. Status now: ${data.status}.`);
    void qc.invalidateQueries({ queryKey: ["admin", "jobs", "executions"] });
  },
});

// In the Recent jobs table:
{j.status === "running" && (
  <button onClick={() => {
    if (window.confirm(`Abort ${j.job_name}?`)) {
      abortJob.mutate(j.id);
    }
  }} disabled={abortJob.isPending}>
    Abort
  </button>
)}
```

### Tests

- `tests/test_abort_and_retry_lenience.py` — 16 tests (13 pure-logic
  + 3 live-PG): abort route present, mark_cancelled idempotent,
  abort gated to running rows on FE, worker poll exits early,
  retry mode uses 3 attempts + backoff + full traceback, transient
  HTTP codes targeted, live-counter rendering.
- `tests/test_admin_jobs.py::TestSummarizeExecution` — running state
  now covered with both starting-state and live-counter branches.
- `frontend/src/components/__tests__/OperationsPanel.test.tsx` — adds 3
  tests: Abort button visible only on running rows, Abort dispatches
  the correct POST, live progress string renders.

### Self-heal contract additions

1. `mark_cancelled` filters on `status='running'` — re-cancelling is
   a no-op (idempotent, operator double-click safe).
2. `_check_aborted` swallows every error (no DSN / DB unreachable /
   row missing → returns False; worker keeps running).
3. The abort `audit_log` write is best-effort — a failed audit row
   doesn't block the abort response (the row IS already flipped).
4. The retry-with-backoff loop never exceeds 3 attempts even under
   pathological transient-error storms — backoff is bounded at 8s.
5. Workers exit code 0 on graceful abort — the cancellation is
   intentional, not a failure (CI / scheduler treats it cleanly).

### Operator runbook deltas

Pre-fix: `wait 30 minutes → click Close stuck jobs → dispatch new run`.

Post-fix:
1. Click **Abort** on the stuck row (immediate).
2. Wait ~10s for the worker to see the signal + exit gracefully.
3. Address the underlying cause (catalogue stubs / parser bug / etc.).
4. Dispatch a fresh run (auto-cleanup of any leftover stuck rows
   already runs pre-dispatch via §16).


## §18 — End-to-end ingestion → UI render tracing (2026-05-28)

### Problem this addresses

Operator-reported gap: "UI state still reads that there are never any
runs even while running jobs via the CLI. There is no tracing to check
whether the data synthesised is actually loaded and presented on the UI."

Three concrete bugs underneath:

1. **Worker silently runs invisibly.** When `python -m
   app.scripts.historical_backfill` is invoked from Cloud Shell without
   `DATABASE_URL_SYNC` wired, the worker's `_safe_create_row` catches
   the resolution failure, returns None, and the tracker proceeds
   with `execution_id=None`. Every subsequent counter UPDATE is a no-op
   — the worker runs, ingests data, exits cleanly, and NEVER writes a
   `job_executions` row. The admin UI shows no runs.

2. **No end-to-end pipeline check.** Even when the worker IS visible,
   the operator can't tell whether the data it ingested is actually
   making it to the UI. They have to manually navigate to a client
   page + spot-check the directory.

3. **Worker→UI chain breaks silently.** A break anywhere between
   ingest → DB → API → UI render surfaces only when the operator
   notices the directory is empty or the scores don't render.

### Fixes — visibility

#### Worker — Secret Manager fallback for DSN resolution

`backend/app/services/sync_dsn.py::resolve_sync_dsn` gains a 4th
resolution step:

```text
1. DATABASE_URL_SYNC env var (explicit, wins)
2. DATABASE_URL env var (derived: +asyncpg → +psycopg)
3. DATABASE_URL env var (postgresql:// → postgresql+psycopg://)
4. Google Secret Manager `dma-insights-database-url-sync` via ADC ← NEW
5. None — caller treats as "no sync DB available"
```

The Secret Manager lookup is cached at module level so re-resolves
don't burn API calls. Operator can disable for tests via
`DMA_DISABLE_SECRET_DSN_FALLBACK=1`. Every failure mode (lib missing,
no ADC, secret absent, IAM denied) returns None — graceful + silent.

This makes `python -m app.scripts.historical_backfill` work from any
Cloud Shell session where the operator's gcloud auth grants
`secretAccessor` on the project, eliminating the "UI shows no runs"
root cause for the most common operator workflow.

#### Worker — loud warning when row write fails

`workers/_runner.py::_safe_create_row` now emits a box-drawing-char
banner to stderr when the DB write fails AND structured-logs the
error. The operator sees this in their terminal AND in Cloud Run logs:

```text
╔══════════════════════════════════════════════════════════════╗
║  WARNING: job_executions row NOT written.                     ║
║  This run will NOT appear in the admin UI.                    ║
║  Cause: cannot resolve sync DSN (DATABASE_URL_SYNC unset +    ║
║  Secret Manager fallback failed). Worker will run             ║
║  invisibly. To fix:                                           ║
║    a. Set DATABASE_URL_SYNC=postgresql+psycopg://...           ║
║    b. Or run via `gcloud run jobs execute ...` (Terraform     ║
║       wires DATABASE_URL_SYNC into the Cloud Run Job env).    ║
║  Error: <short error string>                                  ║
╚══════════════════════════════════════════════════════════════╝
```

The worker continues — we don't BLOCK ingest on DB-write failure
(better invisible ingest than no ingest at all) — but the operator
knows what's happening + how to fix.

#### `/admin/trace/ingest` — end-to-end pipeline check

`GET /api/v1/admin/trace/ingest` (admin-only) returns a snapshot of
EVERY step from worker → DB → API → UI render:

```json
{
  "pipeline_steps": [
    { "label": "entities ingested",            "ok": true,  "detail": {...} },
    { "label": "runs persisted",               "ok": true,  "detail": {...} },
    { "label": "latest run readable",          "ok": true,  "detail": {...} },
    { "label": "scores persisted",             "ok": false, "detail": {"count": 0, ...} },
    { "label": "report sections",              "ok": true,  "detail": {...} },
    { "label": "evidence persisted",           "ok": true,  "detail": {...} },
    { "label": "entity visible in directory",  "ok": true,  "detail": {...} },
    { "label": "UI overview will render scores", "ok": false, "detail": {...} }
  ],
  "checks_passed": 6,
  "checks_total": 8,
  "pipeline_healthy": false,
  "latest_entity_id": "uuid",
  "latest_entity_drive_folder_id": "1ABC...",
  "ui_render_ok": false
}
```

Step 8 — "UI overview will render scores" — is the critical one. It
runs the SAME AVG(score) aggregation the `/api/v1/entities/{id}/
overview` endpoint uses, so a `false` here means the live AE-facing
PillarBar will render with zero data. Operator sees this and immediately
knows the catalogue resolution broke even if scores landed in
`subcap_scores`.

Self-heal contract: every step is wrapped in try/except; a missing
table (pre-migration) OMITS that step; the endpoint NEVER raises so
operators triaging a broken system always have this surface available.

#### Operations panel — Pipeline status card

`frontend/src/components/OperationsPanel.tsx` renders the trace at
the TOP of the Operations section — the operator's first visual
signal on page load. Three render states:

```text
healthy   → green card, "✓ end-to-end healthy", (5/5 checks)
           + "Latest entity: View in UI ↗" link
warning   → amber card, "⚠ break detected", (3/5 checks)
           + per-step ✓/✗ markers naming which steps failed
error     → "Couldn't load /admin/trace/ingest" card +
           OTHER diagnostics still poll independently
```

Polls every 15s. The "View in UI ↗" link routes to `/clients/{id}`
so the operator can validate the UI rendering manually with one click.

### Tests

`backend/tests/test_visibility_and_deep_extract.py` — 22 tests (21
pure + 1 live-PG):

- Track 1 (CLI visibility): banner is loud, Secret Manager fallback
  exists, explicit env wins, opt-out env var honoured, failures
  swallowed.
- Track 2 (trace endpoint): registered + admin-gated, step labels
  locked, self-heal response shape present.
- Track 3 (frontend card): renders correctly, links to latest entity,
  formatTraceDetail handles every detail shape.
- Track 4 (deep extract): see §19.

`frontend/src/components/__tests__/OperationsPanel.test.tsx` — 3
new tests (16 total):
  - healthy state renders (X/Y checks) + step labels
  - warning state shows break-detected + failing step
  - error state falls back gracefully without crashing other diagnostics

### Self-heal contract additions

1. `resolve_sync_dsn` cached Secret Manager lookup — never re-pulls,
   never raises, returns None on any failure path.
2. Worker emits a stderr banner BEFORE silently degrading — the operator
   ALWAYS sees the visibility gap if it occurs.
3. `/admin/trace/ingest` wraps every step independently — one query's
   missing table doesn't kill the others.
4. Frontend trace query uses `retry: false` so a trace endpoint
   failure doesn't burn polling cycles + falls back to its error card.

### Empty-pipeline affordance — "Run full backfill"

When the trace reports `latest_entity_id === null` (entities=0 — fresh
deploy or empty DB), the trace card renders an additional sub-section
with a **Run full backfill** button. POSTs to
`/api/v1/admin/jobs/historical_backfill:execute` with `mode=full` and
no extra args — walks every `* - DMA` folder under the configured
Drive root.

Without this affordance the UI was unusable for first-time setup: the
operator landed on /admin, saw "no runs", and had no surface to start
an ingest. The retry-failed-only button was unhelpful (nothing to
retry yet). The full-backfill button bridges that gap.

The button is HIDDEN once any entity exists — the operator's path
then shifts to the per-folder retry surface (§16) for failed folders.


## §19 — Retries do deeper extraction (lenient parser + OCR fallback)

### Problem this addresses

Operator-reported gap: "Retries should also focus on deep information
retrieval from obtained reports and more robust parsing, not just
trying drive access. Even the Retries can try visual scans if stuff
fails; it should be thorough to ensure the information is retrieved
and persisted."

§17 made retries more robust at the DRIVE layer (3 attempts with
backoff on transient HTTP). This section makes them more thorough at
the PARSER layer — when a folder's canonical workbook layout is
missing, the retry pass falls through to a deep-extraction chain
instead of giving up.

### What changes

The historical_backfill worker now sets `DMA_INGEST_LENIENT=1` when
`--retry-failed-only` is active. The parser consults this env var
and runs `deep_extract_folder()` as a fallback when:
  - no `MANIFEST.json` found
  - AND no `run_manifest*.json` in the folder

The deep-extract chain (5 strategies, each tried in order until one
yields ≥ 200 chars of usable text):

| Strategy | What it does | Lib dependency |
|---|---|---|
| `docx_text` | Walks every `*.docx` (depth ≤3), extracts paragraphs + table cells via python-docx | python-docx (always installed) |
| `docx_ocr` | For DOCX with low text → OCR every embedded image via pytesseract | pytesseract (optional) |
| `pdf_ocr` | Rasterizes every PDF page (pdf2image) → OCR each | pytesseract + pdf2image + poppler (optional) |
| `folder_name_only` | Falls back to inferring institution from folder name | none |
| `none` | Total failure — caller treats as `failed_other` | n/a |

Output ladder: each successful strategy returns a `DeepExtractResult`
with:

```python
@dataclass
class DeepExtractResult:
    scraped_text: str        # all extracted text concatenated
    run_id: str | None       # mined via regex from scraped text
    institution: str | None  # inferred from folder name
    ocr_pages: int           # how many image pages were OCR'd
    docx_paths_scraped: list[str]  # which files contributed
    strategy: str            # which ladder rung succeeded
    warnings: list[str]      # surfaced into parser_warnings
```

The parser appends `lenient_mode_deep_extract: strategy=X
text_chars=N ocr_pages=M docx_count=K` to `parser_warnings` so the
operator can see in the admin Import Audit which retry strategy
recovered the data.

### Library availability

Every OCR helper detects its dep at import time and returns `("", 0)`
when missing. As of 2026-05-28 the worker Dockerfile ships the OCR
stack by default:

```dockerfile
# infra/docker/worker.Dockerfile
RUN apt-get install -y --no-install-recommends \
    tesseract-ocr libtesseract-dev poppler-utils
RUN pip install pytesseract==0.3.13 pdf2image==1.17.0 Pillow==10.4.0
```

Image grows by ~120 MB. Acceptable for the once-per-deploy cost +
unlocks the full deep-extract chain in production retries.

The backend Dockerfile does NOT ship OCR — the `/ingest/package`
endpoint accepts canonical zips from the bot pipeline (no DOCX-only
recovery path needed there). Only the worker container (which runs
`historical_backfill`) needs OCR.

Tests cover both states:
  - `test_deep_extract_recovers_text_from_real_docx` — exercises the
    docx_text strategy with a real python-docx-built fixture (always
    available).
  - `test_ocr_returns_empty_when_libs_missing` — confirms the
    graceful-degradation contract still holds for envs without OCR
    binaries (local dev / CI test runner).

### When the operator sees this

Click **Retry failed folders** in the Operations panel → the worker
runs in lenient mode → each per-folder log line in Cloud Logging
includes the `lenient_mode_deep_extract` warning naming the
strategy. After completion, the **Drive folders flagged for retry**
count shrinks (folders that previously yielded only `failed_other`
now yield `ok` or `failed_parse` with richer context).

### Tests

`backend/tests/test_visibility_and_deep_extract.py::TestDeepExtractPureLogic`
— 9 pure-logic tests:
  - `extract_run_id` finds REQ + DMA-ASM patterns
  - `infer_institution_from_folder` handles 4 separator styles
  - `scrape_docx_text` returns "" when path missing (no crash)
  - OCR helpers return ("", 0) when libs missing (graceful)
  - `deep_extract_folder` returns folder_name_only on empty folder
  - `has_scoreable_content` threshold honoured

`test_dma_package_parser_consults_lenient_env` — source-shape
assertion that `parse_package` calls `deep_extract_folder` under
the `DMA_INGEST_LENIENT` env gate.

`test_worker_activates_lenient_mode_in_retry` — source-shape
assertion that the worker sets the env var when
`--retry-failed-only` is active.

### Self-heal contract additions

1. The deep extractor never raises — every strategy degrades to
   `("", 0)` on dependency / file / OCR failure.
2. The fall-through ladder ALWAYS produces a result; the worst case
   is `strategy="none"` which the worker correctly logs as
   `failed_other` with explanatory text.
3. The OCR libs being absent is fine — the operator's first deploy
   doesn't need them; the chain still works at the docx_text layer.
4. The parser appends the strategy + char count to parser_warnings
   so the operator can see WHICH strategy recovered each folder
   without re-running locally.


## §20 — Standalone build auth hydration (2026-05-28 — closes e2e timeout)

### Symptom

Playwright e2e `Admin persona › Admin page is accessible` test timed out
waiting for `aside.sb, main.login-card, [data-page="login"]`. 19/20
other tests in the same persona suite passed despite using the same
`goTo()` + `loginAs()` helpers.

### Root cause

The standalone build's `AppProvider` initialized `authed` from
`sessionStorage["dma_user"]` ONLY. The HttpOnly `dma_session` JWT
cookie that Playwright injects via `addCookies` was never consumed by
the SPA — the comment on `signIn` claimed "/auth/me on boot" but
the actual boot useEffect didn't exist. Result:

  - operators returning to the app after a tab close had to sign in
    again every time, even with a valid cookie
  - Playwright e2e tests that injected the JWT + verified `/auth/me`
    returned 200 nevertheless saw the SPA stay on LoginPage
    (no `aside.sb`) and timed out
  - the `goTo` helper's selector list `aside.sb, main.login-card,
    [data-page="login"]` only matched the authenticated shell —
    LoginPage rendered NONE of the three (it uses inline-styled
    `<div>`s without those markers)

### Fix — three changes

#### 1. AppProvider hydration useEffect (one-shot /auth/me probe)

`frontend/standalone-src/src/app-root.jsx`:

```jsx
const [hydrating, setHydrating] = useState(!stored);
useEffect(() => {
  if (stored) {
    setHydrating(false);
    return;
  }
  (async () => {
    try {
      const r = await fetch("/api/v1/auth/me", {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      if (r.ok) {
        const body = await r.json();
        if (body && body.email) signIn(body);
      }
    } catch (e) {
      // Network blip / proxy down → leave authed=false (LoginPage)
    } finally {
      setHydrating(false);
    }
  })();
}, []);
```

Idempotent — sessionStorage hit skips the fetch. Best-effort —
network errors leave `authed=false` so the user lands on LoginPage
with the BackendErrorBanner showing the underlying failure.

#### 2. Router hydrating-state spinner

```jsx
function Router() {
  const { route, authed, hydrating } = useApp();
  if (hydrating) return <LoadingScreen variant="boot" dark />;
  if (!authed && path !== "/login") return <LoginPage />;
  // ...
}
```

Without this, the user would briefly see LoginPage flash during the
boot fetch even when their cookie was valid + about to authenticate.

#### 3. LoginPage data-page marker + e2e helper widened selectors

`frontend/standalone-src/src/pages-auth-dashboard-directory.jsx` —
outer container gains `data-page="login"`.

`frontend/e2e/helpers.ts::goTo` — selector list expanded:
```
'aside.sb, #gis-script, main.login-card, [data-page="login"]'
```

Now matches either:
  - `aside.sb` — authenticated shell
  - `#gis-script` — LoginPage's Google sign-in script (boot done)
  - `[data-page="login"]` — synchronous LoginPage marker

### Tests

`frontend/src/__tests__/standalone-auth-hydration.test.ts` — 7
source-shape tests:
  - `fetch("/api/v1/auth/me")` call exists in app-root.jsx
  - call is INSIDE a useEffect (not a top-level)
  - signIn receives the full body (not derived email — security)
  - try/catch wraps the fetch (best-effort)
  - sessionStorage-present path short-circuits the fetch
  - Router renders LoadingScreen when hydrating (no LoginPage flash)
  - `hydrating` is exposed in the AppProvider context
  - LoginPage carries `data-page="login"`

These run in <100ms against the parsed source files — much faster
than the Playwright suite + catch regressions BEFORE the slow e2e
container catches them.

### Self-heal contract additions

1. Hydration ALWAYS resolves (sets hydrating=false in `finally`). A
   stuck fetch can't pin the user at the spinner forever.
2. signIn from `/auth/me` is best-effort — 401/5xx silently lands
   on LoginPage; no error toast (the dev-login banner already covers
   that signal).
3. The hydrating spinner uses the same `LoadingScreen variant="boot"`
   as the initial 600ms App boot — visually consistent.
4. The `goTo` selector list now triple-defends: `aside.sb` for the
   happy path, `#gis-script` for the GIS-loading window, and
   `[data-page="login"]` for the synchronous LoginPage marker.
5. Operators returning to the app with a still-valid cookie get
   silently re-authenticated — no Google sign-in roundtrip.

---

## §21 — 2026-05-28 audit remediation (Waves 1–5)

End-to-end audit surfaced 58 P0/P1/P2 defects. Fixes landed in five
batched waves; each commit's body documents the specific defect class.
This section captures the operator-facing changes.

### §21.1 — Cloud Run won't-boot (Wave 1)

`config.py::assert_production_ready(settings, *, role)` now refuses
to boot when `ENV=prod` AND any of the required-for-prod secrets are
empty or still hold the dev default. Previously this guard existed
but Terraform never set `ENV=prod` on the Cloud Run resources, so
the guard silently short-circuited and containers booted with dev
defaults. Without the env var:

- `assert_production_ready` returns at line 162 (`env not in
  ("prod","dev")`) without checking anything.
- `dma_bot_api_key=""` flows through, disabling the bearer guard.
- `database_url` still contains `localhost:5433`, but the asyncpg
  client connects to the Cloud SQL socket via the secret-bound DSN
  anyway, masking the misconfiguration until something else breaks.

Terraform fix (`infra/terraform/main.tf`):

```hcl
env { name = "ENV"             value = "prod" }
env { name = "GCP_PROJECT_ID"  value = var.project_id }
env { name = "CLAY_WEBHOOK_URL"    value_source { secret_key_ref { secret = "dma-insights-clay-webhook-url"    version = "latest" } } }
env { name = "CLAY_WEBHOOK_SECRET" value_source { secret_key_ref { secret = "dma-insights-clay-webhook-secret" version = "latest" } } }
```

Added to: backend service, migrations job, historical_backfill job,
worker for_each. Workers get only `ENV` + `GCP_PROJECT_ID` since
`REQUIRED_FOR_PROD_WORKER` is the minimal 2-key surface.

Two new out-of-band secrets MUST exist before terraform apply:

```bash
gcloud secrets create dma-insights-clay-webhook-url    --replication-policy=automatic
gcloud secrets create dma-insights-clay-webhook-secret --replication-policy=automatic
echo -n "<the Clay table-webhook URL>"       | gcloud secrets versions add dma-insights-clay-webhook-url    --data-file=-
echo -n "<the HMAC shared secret>"           | gcloud secrets versions add dma-insights-clay-webhook-secret --data-file=-
```

(If Clay is disabled in your env, store empty strings — the
production-readiness guard **still boots** (Clay was removed from
`REQUIRED_FOR_PROD_BACKEND` on 2026-06-10, ADR 0010 amendment). Per
ADR 0010 the connector simply fail-closes the webhook on the empty
secret, so enrichment is skipped until you populate it. Earlier
revisions of this guide said the guard would "refuse to boot" on
empty Clay — that is **no longer true**; `test_clay_prod_config_contract.py`
asserts the guard PASSES with empty Clay values.)

### §21.2 — Three missing Cloud Run Jobs (Wave 2)

`locals.jobs` previously only declared 4 workers (drive_crawler,
sheet_poller, embedder, ccg_loader). Two existing Cloud Schedulers
(`peer_patterns_weekly`, `chat_learning_nightly`) and the dispatch
map already referenced names that DID NOT EXIST as Terraform-
declared Cloud Run Jobs:

- `dma-insights-peer-patterns`
- `dma-insights-chat-learning`
- `dma-insights-intelligence-recompute`

Result: every scheduled invocation 404'd at the resource lookup AND
every admin "Recompute" button click resolved to "skipped_no_project"
/ "import_failed". Wave 2 adds the three to `locals.jobs` with the
canonical scheduled-args defaults; admin button overrides via
`container_overrides.args`.

Plus: `peer_patterns` + `intelligence_recompute` argparse-default to
no-op when called with empty args — Wave 2 also fixes JOB_DISPATCH
defaults to `["--all"]`.

`backend.Dockerfile` gains tesseract-ocr + poppler-utils +
pytesseract + pdf2image + Pillow so historical_backfill (uses
BACKEND image, not workers) can run `deep_extract`'s OCR fallback
strategies in retry mode.

### §21.3 — OperationsCard ported to standalone (Wave 3)

The Vite-tree `frontend/src/components/OperationsPanel.tsx` was the
previous landing for live pipeline trace + abort + repair, but per
ADR 0011 only `frontend/standalone-src/` ships in prod. Wave 3
lifts the features into the canonical surface:

- `backend-loader.js`: `window.DMA.admin.{diagnostics, traceIngest,
  abortJob, repairCatalogueStubs, repairCloseStuckJobs,
  runFullBackfill, runRetryFailedBackfill}`.
- `pages-alerts-prospecting-admin.jsx::OperationsCard`: rendered at
  the TOP of /admin home tab. Polls diagnostics every 10s, trace
  every 15s, jobs adaptive (3s while anything runs, 30s idle).
  Renders pipeline trace table, diagnostics tiles, action row
  (run-full-backfill, retry-failed-only, repair-catalogue-stubs,
  close-stuck-jobs), recent-jobs table with Abort + View-log
  buttons.

The existing per-worker cards (Drive crawl / Embedder / Peer
patterns) remain unchanged below.

### §21.4 — Ingest auth + audience strip (Wave 4)

`/api/v1/ingest/assessment` now accepts dual auth:

- Bot bearer (canonical Claude-project webhook callback)
- OR admin session cookie (lets operators replay an ingest without
  retrieving the bot secret from Secret Manager)

Non-admin cookie → 403. Wrong bearer → 401 (hard-reject; doesn't
fall through to cookie to keep structlog mismatch signals intact).

`audience_strip.INTERNAL_ONLY_KEYS` extended with `peer_benchmarks`
+ `peer_internals`; `INTERNAL_ONLY_NESTED` extended with
`peer_median`, `peer_gap`, `peer_delta`, `peer_cohort_size`. Any
future `?view=customer` response across any surface strips peer-
cohort scores -- commercially sensitive (would leak how other
Zennify clients scored on the same DMA).

### §21.5 — Migration 023 + hot-path indexes (Wave 5)

`alembic/versions/023_focus_areas_reconcile.py` reconciles a schema
drift between 011 (which creates `focus_areas` with columns `name`
+ `source_quote`) and 018 (which uses `title` + `verbatim_quote`).
Because 018 wraps its CREATE in `IF NOT EXISTS`, the 011 schema
stuck on a fresh DB walking 001→022. App code uses the 018 names,
so any future INSERT path would hit "column does not exist".

Reconciles via idempotent `ALTER TABLE ... RENAME COLUMN` wrapped
in DO-blocks that swallow undefined_column / duplicate_column. Safe
to re-run on either schema state.

Same migration adds two perf indexes:

- `ix_runs_entity_completed` on `runs (entity_id, completed_at
  DESC NULLS LAST)` — accelerates every `/entities/{id}/runs`
  query.
- `ix_evidence_index_entity_freshness` on `evidence_index
  (entity_id, freshness_band)` — accelerates `/entities/{id}/
  overview` filter.

### §21.6 — Operator runbook delta

Pre-deploy checklist for next push:

```bash
# 1. Apply migration 023 (idempotent).
gcloud run jobs execute dma-insights-migrations --region us-central1 --wait

# 2. terraform apply -- creates 3 missing Cloud Run Jobs + injects
#    ENV=prod + Clay secrets to backend.
terraform -chdir=infra/terraform apply

# 3. Verify scheduler endpoints now resolve.
gcloud run jobs list --region us-central1 | grep -E "peer-patterns|chat-learning|intelligence-recompute"

# 4. Trigger one of the previously-missing workers from /admin to
#    confirm dispatch path is alive.
#    Click "Recompute peer patterns" on /admin → expect status=running
#    in the Recent jobs table; transitions to succeeded < 5 min.

# 5. Verify production-readiness guard armed.
#    Tail Cloud Run logs for the backend revision; you should see
#    "Production-readiness check FAILED" if anything is wrong.
gcloud run services logs read dma-insights-backend --limit 50

# 6. Smoke /admin/diagnostics to verify OperationsCard renders.
curl -s -b /tmp/admin-cookies.txt \
  "https://dma-insights-backend-XXX.run.app/api/v1/admin/diagnostics" | jq .
```

Rollback: `terraform -chdir=infra/terraform plan -destroy -target=
google_cloud_run_v2_job.worker["peer_patterns"]` then `apply` if a
new worker Cloud Run Job misbehaves. Each is independent so single-
worker rollbacks don't disturb the others.

## §22 — Post-deploy refresh + lasting DB self-heal (2026-06-05)

This section documents the three operator-facing changes that close the
recurring deploy-time failure modes hit between 2026-06-03 and
2026-06-05. Each fix has a binding contract; the deploy chain wires
them in deterministic order.

### §22.1 — Post-deploy refresh chain

**Problem (operator quote):** "while deploying, I still see the logs
picking wrong evidence and subcap counts. A new deployment should
always refresh everything and even parse and ensure the backfill is
fired such that when I join everything is already ingested and
processed."

Three independent root causes, glued together by a single absence:

1. **Cloud Run kept routing 100% traffic to the prior revision** —
   `gcloud run services` is not auto-promote when the existing traffic
   split is anything other than `100% LATEST`. Pre-2026-06-05 `deploy.sh`
   only ran `--to-latest` on drift detection.
2. **Newly-uploaded DMA packages stayed un-ingested between scheduled
   crawls** — `drive_crawler_6h` runs every 6 hours, so an operator
   who deploys and then immediately checks the app sees yesterday's
   evidence corpus.
3. **(Opt-in only)** Pure-code changes don't bump the synthesis-cache
   fingerprint (catalogue_version + prompt_template_version both
   unchanged), so cached narratives keep serving the pre-deploy view
   of the world.

`infra/post-deploy-refresh.sh` (new, 2026-06-05) is the orchestrator:

```bash
./post-deploy-refresh.sh                    # promote traffic + delta backfill (default)
./post-deploy-refresh.sh --skip-backfill    # just promote traffic
./post-deploy-refresh.sh --invalidate-cache # also invalidate vertex_synthesis_cache
./post-deploy-refresh.sh --skip-verify      # don't double-check post-update
```

**Hard contract (operator mandate 2026-06-05):** *"the refresh should be
for new information please or new dma reports. If a report was
persisted and no change took place, it can always persist the initial
version."* The script honours this — everything below is delta-mode or
no-op for unchanged data:

| Step | Action | What it preserves |
|---|---|---|
| 1 promote_traffic | `gcloud run services update-traffic --to-latest` on backend + frontend | idempotent when already at 100% LATEST |
| 2 backfill_delta | `drive_crawler --mode delta` → `embedder --mode delta` → `intelligence_recompute` (idempotent) | unchanged Drive folders skipped; unchanged evidence/section rows not re-embedded; intelligence_profiles only rewritten when classify_state detects change |
| 3 invalidate_cache (opt-in) | UPDATE vertex_synthesis_cache SET invalidated_at=NOW() WHERE created_at < deploy_start | cached narratives kept by default; only operator-requested |
| 4 verify_revisions | Re-read traffic split on every service, exit 2 on drift | defensive vs control-plane lag |

**Step 2c (2026-06-10) — derived-surfaces refresh + synthesis warm.**
After the backfill chain, the script runs three idempotent modules via
the backend job image (best-effort; lazy paths cover any failure):

```bash
# What the phase executes (also runnable by hand, e.g. in Cloud Shell
# against the prod DB via the backfill job). ORDER MATTERS — platform
# tags + cohort peer medians first, then the derive/enrich steps that
# read them:
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.repark_junk_entities" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.backfill_run_dates" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.apply_catalogue_platforms" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.broadcast_peer_medians" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.derive_insights" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.derive_focus_areas" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.derive_alerts" --wait
gcloud run jobs execute dma-insights-historical-backfill \
  --region=${REGION} --command=python \
  --args="-m,app.scripts.enrich_corpus" --wait
```

> **NON-NEGOTIABLE pre-deploy gate (2026-06-11 operator mandate):**
> `python -m app.scripts.deploy_parity_gate` must print PASS before any
> deploy ships. It verifies EVERY ACTIVE client carries the filled-page
> contract (score, findings, why-now, platform fit, renderable focus
> area, alerts-when-thin); any violation auto-invokes the self-healing
> ladder once and re-checks; residual violations exit 1 and BLOCK the
> deploy. The served frontend self-identifies at `/__build.txt` —
> refuse traffic flips to images whose SHA ≠ the gated commit.

> **Crawler scale-out (2026-06-11, prod timeout fix):** the drive
> crawler/backfill now honors Cloud Run task sharding. Update the jobs
> once: `gcloud run jobs update dma-insights-drive-crawler --tasks 8
> --parallelism 8 --task-timeout 1800 --region $REGION` (same for
> dma-insights-historical-backfill). Each task crawls the disjoint
> idx%COUNT slice — ~8× wall-clock, no shared Drive client, per-task
> quarantine. Slides/decks were already excluded from download
> (SKIP_SUBFOLDER_NAMES); unchanged folders skip persist via the
> artifact manifest.

- `repark_junk_entities` (2026-06-11) — ACTIVE entities whose names
  fail `entity_name_sanity` (raw Drive folder IDs, "… Engagement
  FINAL" noise, blanks) move to the PENDING_REVIEW admin queue;
  insert-time gating never re-screened pre-gate legacy rows, which is
  how junk cards reached the live dashboard. Clean clients untouched.
- `backfill_run_dates` (2026-06-11) — persists `runs.assessment_date`
  from request-id/manifest fallbacks for any pre-039 row (idempotent,
  only-when-empty) so RUN DATE never renders the ingest wall-clock.
- `apply_catalogue_platforms` — backfills `subcap_scores.platform_tags`
  from the v7.0 capability workbooks (baked into the backend image at
  `/home/app/docs/reference/catalogue/v7.0` — the relative default
  resolves) and recomputes persisted platform fit. **2026-06-10 final
  tests: with this missing, ALL 63k corpus rows had NULL tags and every
  D4 platform card rendered fit=0 / INSUFFICIENT_EVIDENCE.**
  Package-shipped tags always win; idempotent.
- `broadcast_peer_medians` — cohort-fallback peer medians for runs whose
  package shipped no category peer medians (11 in the 2026-06 corpus):
  fills `subcap_scores.peer_median` from the `peer_benchmarks` cohort
  for the entity's subvertical. Package-shipped values never
  overwritten; idempotent.
- `derive_insights` — re-runs the ingest insight ladder (recs →
  category-gaps → relative-priority) for any run with zero cards,
  grounds every card on the run's own evidence E-IDs, and backfills a
  DERIVED 4-part SCQA document_sections row where no NON-EMPTY exec
  summary shipped (heading-only DOCX rows count as missing and are
  dropped). Idempotent (`--force` re-derives).
- `derive_focus_areas` — pre-warms the focus-area ladder (DOCX verbatim
  → Gemini → deterministic heuristic) for every entity with zero
  RENDERABLE focus areas (scaffolding rows like "2 Top Findings" are
  filtered by `focus_area_sanity` and don't count) so D3 focus mode
  serves populated cards immediately.
- `derive_alerts` (2026-06-11) — materializes THIN_EVIDENCE alerts from
  `subcap_scores.is_thin_evidence` (per-subcap below the per-category
  aggregation threshold, one aggregated alert per category above it;
  severity high/medium per the wireframe `buildAlerts` contract; waived
  content_keys never resurrected). **Before this the `alerts` table had
  NO producer — the QA audit found 0 rows corpus-wide while 53k subcap
  rows carried the thin flag, so the Alerts page, dashboard OPEN ALERTS
  KPI, sidebar badge, entity open_alerts and the D6 Health table all
  rendered empty.** Fresh ingests derive inline (package_persist); this
  step backfills/refreshes the corpus. Idempotent.
- `enrich_corpus` — walks entities × {why_now, platform_story,
  firmographics_extraction} through the synthesis-orchestrator gates;
  cache-hit = 0 tokens; honest-cold (nothing persisted) when Vertex
  creds are absent; output E-IDs are validated against the supplied
  bundle (fail-closed); firmographics fields require a verbatim
  supporting quote from the entity's own report excerpts. `--dry-run`
  reports the gate matrix with zero Vertex calls.

The module list and its order are pinned by
`tests/test_post_deploy_refresh_job_names.py::test_post_deploy_refresh_runs_derived_surface_modules`.

Cache invalidation costs Vertex tokens on the next read per surface, so
it stays opt-in. The mechanism: the script injects an UPDATE statement
into `app/scripts/post_migrate.py` via a one-shot `DMA_POST_DEPLOY_SQL`
env-var; only `UPDATE` / `DELETE` are accepted and the statement is
capped at 8192 chars to keep the entry point from becoming an arbitrary
SQL surface.

**Cloud Run Job names** (must match terraform-declared names):
`dma-insights-drive-crawler`, `dma-insights-embedder`,
`dma-insights-intelligence-recompute`, `dma-insights-migrations`. The
script `gcloud run jobs describe`s each before executing; a missing
job logs a warning and skips that step rather than aborting.

### §22.2 — Wiring: deploy.sh + deploy-two-phase.sh

`infra/deploy.sh` (simple wrapper) and `infra/deploy-two-phase.sh`
(prod entrypoint with mid-deploy self-heal) both call
`post-deploy-refresh.sh` automatically:

**`deploy.sh` flags:**

```bash
./deploy.sh                       # build + apply + migrate + refresh (default)
./deploy.sh --skip-refresh        # skip post-deploy traffic promote + backfill
./deploy.sh --invalidate-cache    # also invalidate synthesis-cache (opt-in)
./deploy.sh --skip-build          # apply existing image only
./deploy.sh --skip-verify         # skip Cloud Run revision check
```

**`deploy-two-phase.sh` phase chain (post-2026-06-05):**

| Phase | What runs | Exit code on failure |
|---|---|---|
| 0 | `preflight-parameters.sh` (env probe + secrets self-heal) | 1 |
| 1 | `build.sh` (gcloud builds submit; SHA-pinned images) | 2 |
| 1.6 | DB liveness + password drift check (`recover-db-passwords.sh --verify-only`; falls through to `force-heal-db.sh`) | 1 (pre-build abort) |
| 2 | terraform apply (creates revision-WITHOUT-traffic on backend) | 3 |
| 3 | migrate.sh against new revision | 4 |
| 4 | `/readyz` probe (with mid-deploy `force-heal-db.sh` if 503) | 5 |
| 5 | traffic shift to LATEST | 5 |
| 6 | `verify-deploy.sh` (post-promotion health) | 6 |
| 7 | frontend deploy | — |
| 8 | **`post-deploy-refresh.sh` (NEW)** — traffic promote confirm + delta backfill | warn-only (best-effort) |

Phase 8 is intentionally best-effort: backend + frontend are LIVE at
this point, and the refresh is "make the app feel fresh on first page
load." A backfill failure logs a copy-paste retry command + the deploy
overall succeeds.

### §22.3 — Lasting DB self-heal fixes

`infra/force-heal-db.sh` + `infra/backup-before-heal.sh` had two
production-blocking bugs that surfaced on 2026-06-05:

**Bug 1 (`backup-before-heal.sh`): `--enable-bin-log` is MySQL-only.**

```text
ERROR: (gcloud.sql.instances.patch) HTTPError 400: Invalid request:
  Binary log can only be enabled for MySQL instances.
::warning::could not enable backups — likely missing
  cloudsql.instances.update; continuing best-effort
```

**Fix:** detect engine via `databaseVersion` and pass the correct
PITR flag. PostgreSQL uses `--enable-point-in-time-recovery`; MySQL
uses `--enable-bin-log`. The case branch defaults to PostgreSQL when
the version probe returns empty (safe default for this infra).

**Bug 2 (`force-heal-db.sh`): `set-password` succeeds but verification
keeps failing.**

```
✓ set-password OK
⚠ post-set verification STILL failing — possible Cloud SQL replication delay; retrying in 10s...
::error::password set-password reports success but SQL still rejects it. Manual diagnosis needed.
FATAL: both DB heal paths failed; aborting deploy BEFORE Phase 2.
```

**Root cause:** the password bytes in Secret Manager can become
un-authenticatable via SCRAM-SHA-256 due to upstream encoding mishaps,
leaving the value set in Cloud SQL but un-readable by psql.

**Fix (regenerate-password escape hatch):** when the verification chain
exhausts, generate a fresh 48-char URL-safe password and write it to
both sides atomically:

```text
Step 1 → Write new password to Secret Manager (atomic, versioned)
Step 2 → Set the new password on the Cloud SQL user
Step 3 → Verify via psql that the NEW password authenticates
```

Secret-first ordering means if Step 2 fails the secret is still
consistent for the next heal cycle. SCRAM-SHA-256 deadlock is no
longer terminal.

### §22.4 — Comprehensive `ensure-db-ready.sh`

The new orchestrator handles all six missing-state cases the operator
hit at various points. Run it as a one-stop "make the DB ready"
command:

```bash
./ensure-db-ready.sh                # full chain (default)
./ensure-db-ready.sh --check-only   # report state, no writes
./ensure-db-ready.sh --skip-migrate # don't run alembic at the end
```

Exit-code contract:

| Code | Meaning | Operator action |
|---|---|---|
| 0 | instance + DB + user + secret + schemas all live | none |
| 1 | caller-side error (unset PROJECT_ID) | `gcloud config set project <id>` |
| 2 | M1: instance missing | `terraform apply -target=google_sql_database_instance.pg` (~10 min) |
| 3 | secret missing AND we couldn't create it | grant `roles/secretmanager.admin` to your IAM, re-run |
| 4 | user setup failed (createdb / set-password / SCRAM mismatch) | run `force-heal-db.sh --verify-only` for diagnostics |
| 5 | migrations failed AFTER password chain healed | check `gcloud beta run jobs executions logs read` for the migrations job |

Idempotent: re-running on a healthy DB is a no-op. Six missing-state
branches handled:
- **M1** Cloud SQL instance MISSING → bail with terraform-apply instruction
- **M2** Instance present but STOPPED → delegate to `preflight-cloud-sql.sh`
- **M3** Database 'dma_insights' missing → `gcloud sql databases create`
- **M4** User missing OR password drift → delegate to `force-heal-db.sh`
- **M5** Secret missing → seed fresh DSN + create SQL user atomically
- **M6** Schemas stale → delegate to `migrate.sh`

### §22.5 — Admin → Prompt Quality (self-improving prompts read side)

`GET /api/v1/admin/prompt-quality?days=30` (ADMIN-gated) returns a
three-part rollup powered by `app/services/prompt_quality.py`:

| Sub-view | Source columns | Verdict logic |
|---|---|---|
| **by_surface** | `vertex_synthesis_cache.surface` GROUP BY surface | hallucination_rate red >5%, green ≤5% |
| **by_version** | `... GROUP BY surface, prompt_template_version, model` | "active" = MAX(last_seen) per surface |
| **version_diffs** | sliding baseline v1→v2, v2→v3 ... | `candidate_better` / `candidate_worse` / `tie` (<2pp) / `insufficient_data` (<25 samples) |

The endpoint is consumed by a new `PromptQualitySection` on the Admin
page (`frontend/src/pages/AdminPage.tsx`). 5-min staleTime on the
TanStack query, role-gated (`enabled: isAdmin`). Verdict pills mirror
the backend's `_classify_verdict` primitive exactly — schema drift
surfaces at `tsc` time via the `PromptQualityVersionDiffRow.verdict`
Literal type.

Proportional hallucination attribution caveat:
`gemini_hallucination_alerts` (migration 007) has `surface` but no
`prompt_template_version`. Until migration 027 adds the column, alerts
are attributed proportionally per version's share of total surface
responses. Documented in the service docstring and tagged in the
hallucination_rate column.

### §22.6 — Visual regression baselines (2026-06-05 refresh)

Every standalone visual baseline at every viewport (7 viewports × 12
routes = 84 PNGs) was regenerated against the post-LoginPage-redesign
build. The cached baselines pre-dated the commit chain that added the
hero JPG (`pavilion_zennify_branded.jpg`), the prototype boot loader,
the hosted `<GoogleLogin>` widget, and the dropped Zennify email box.
Without regeneration CI reported ~656500 px (32%) diff on every
non-login route at standalone-1920 because the stub server returns 401
on `/auth/me`, every protected route falls back to the LoginPage, and
the LoginPage redesign invalidated every baseline.

Regenerate command (run from `apps/dma-insights/frontend/`):

```bash
pnpm run build:standalone
CI=1 pnpm exec playwright test \
  --config playwright.visual.standalone.config.ts \
  --update-snapshots
git add e2e/visual/standalone-responsive.visual.ts-snapshots/
git commit -m "dma-insights(visual): regenerate baselines for <reason>"
```

84 PNGs at 13 min wall-clock (single-worker; Chromium headless on the
stub server). Don't parallelize — the `webServer` `reuseExistingServer`
flag plus single-`workers: 1` config keeps the captures byte-stable.

### §22.7 — Deployment QA checklist (run before every `deploy-two-phase.sh`)

```bash
# 1. Syntax sanity: every infra script parses
cd apps/dma-insights/infra
for s in *.sh; do bash -n "$s" || echo "✗ $s"; done

# 2. Backend tests + ruff
cd ../backend
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check app/ tests/ ../workers/

# 3. Frontend tsc + vitest
cd ../frontend
pnpm exec tsc --noEmit
pnpm exec vitest run

# 4. Visual baselines current at every viewport
CI=1 pnpm exec playwright test --config playwright.visual.standalone.config.ts

# 5. Drift check on the DB before pre-flight
cd ../infra
./force-heal-db.sh --verify-only      # exit 0 = no drift; exit 2 = drift
# If drift: ./ensure-db-ready.sh      # comprehensive heal + verify

# 6. Two-phase deploy (with refresh)
SHA=$(git rev-parse --short HEAD) ./deploy-two-phase.sh
```

Expected end-state: every service at 100% traffic on the just-pushed
SHA's revision, every Cloud Run Job dispatched once in delta mode,
operator sees fresh evidence + subcap counts on first page load.

### §22.8 — Purging partial/junk entities + resuming the backfill (2026-06-10)

Context: before the strict ingest gate, the Drive backfill persisted
0-subcap-score ("partial") packages and entities with junk names (raw
Drive folder IDs, "… DMA Engagement FINAL", bare fragments). On the
live app these rendered hollow/garbled directory cards. The repair is
a one-time purge + an incremental backfill resume. **The ~95 cleanly
ingested clients are untouched throughout — delta mode and the
material-manifest hash skip them without re-processing.**

Run from Cloud Shell, in order (every command single-line):

```bash
# 0. Make sure the FIXED workers image is live (the 2026-06-10 fastapi
#    ModuleNotFoundError crash means any crawl before this fix fails
#    per-folder). Deploy the current SHA first if you haven't:
cd ~/Accelerate/apps/dma-insights/infra && SHA=$(git rev-parse --short HEAD) ./deploy-two-phase.sh

# 1. Backup BEFORE any destructive step (restores documented in §22.3):
./backup-before-heal.sh

# 2. Dry-run the purge — prints every candidate, writes NOTHING:
gcloud run jobs execute dma-insights-historical-backfill --region us-central1 --args=-m,app.scripts.purge_partial_entities --wait

# 3. Review the dry-run output in the job logs, then APPLY:
gcloud run jobs execute dma-insights-historical-backfill --region us-central1 --args=-m,app.scripts.purge_partial_entities,--apply --wait

# 4. Resume the crawl. Delta mode skips the ~95 unchanged folders via
#    modifiedTime; the purged folders re-ingest only when their scored
#    deliverable lands (strict gate). Then retry quarantined failures:
gcloud run jobs execute dma-insights-drive-crawler --region us-central1 --wait
gcloud run jobs execute dma-insights-historical-backfill --region us-central1 --args=-m,app.scripts.historical_backfill,--retry-failed-only --wait

# 5. Refresh derived surfaces (embedder, intelligence, insights, focus
#    areas, enrichment — fills firmographics/why-now/peer gaps):
./post-deploy-refresh.sh
```

Post-repair sanity checks (each must return 0):

```bash
bash infra/dma-psql.sh -c "SELECT COUNT(*) FROM entities e WHERE e.status='ACTIVE' AND NOT EXISTS (SELECT 1 FROM runs r JOIN subcap_scores s ON s.run_id=r.id WHERE r.entity_id=e.id);"
bash infra/dma-psql.sh -c "SELECT COUNT(*) FROM document_sections ds JOIN runs r ON r.id=ds.run_id WHERE ds.entity_id <> r.entity_id;"
```

Junk-NAMED entities with real scores are not deleted — the purge flips
them to `status='PENDING_REVIEW'`; confirm/fix names in Admin →
Pending review (`GET /api/v1/admin/pending-review`). AE-facing
directory/dashboard/cohort surfaces only ever read `status='ACTIVE'`.

## §23 — Troubleshooting catalog

Cross-build failure modes that surface during deploy or migration
but aren't tied to a specific operator workflow above. Each item is
**self-contained**: symptom -> root cause -> fix command. Run the
fix command verbatim against any environment exhibiting the symptom;
every command is idempotent + non-destructive on a healthy DB.

### §23.1 — Migration 018 `generation expression is not immutable`

**Symptom** (verbatim from a recent failed `dma-insights-migrations`
execution):

```text
psycopg.errors.InvalidObjectDefinition: generation expression is not immutable
[SQL:
    ALTER TABLE evidence_index
        ADD COLUMN IF NOT EXISTS is_stale BOOLEAN
            GENERATED ALWAYS AS (
                ... < (CURRENT_DATE - INTERVAL '3 years') ...
            ) STORED
]
```

**Root cause:**
Postgres requires `GENERATED ALWAYS AS … STORED` expressions to be
IMMUTABLE. `CURRENT_DATE` is `STABLE` (its value depends on the
transaction start time), so the migration is rejected at execute
time. This slipped past the old CI guard because that guard only
ran `alembic upgrade head --sql` (which prints DDL without
executing it), and immutability is enforced at execute time.

**Fix (already applied to migration 018):**
Replace the GENERATED columns with regular `is_stale BOOLEAN` and
`freshness_band VARCHAR(8)` columns plus a `BEFORE INSERT OR UPDATE`
trigger that calls a plpgsql function. Triggers may use `CURRENT_DATE`
freely because they fire per-row at write time, not at schema-
definition time.

A `refresh_evidence_freshness()` plpgsql helper recomputes drift for
rows whose `published_date` crosses a 1y/2y/3y band boundary between
writes. A daily Cloud Scheduler job calls it (see §2b below).

**CI safeguard (new):**
`infra/cloudbuild.yaml` Stage 1 now spins up an ephemeral Postgres
in the build container and runs `alembic upgrade head` against it
for REAL — not just `--sql`. Any future migration with runtime-only
errors (generated columns, trigger compilation, FK validation against
pre-existing rows, CHECK constraint NOT VALID, etc.) fails at
build time instead of deploy time. Round-trip stability
(`upgrade head` → `downgrade -1` → `upgrade head`) is asserted too.

**Fail-soft contract (resilience for routine builds):**
The live-Postgres setup is BEST-EFFORT by default. `apt-get install
postgresql` inside `python:3.12-slim` is heavy (~60 MB) and
occasionally fails due to Debian mirror flakes, missing `postgres`
user in the image, or restricted `/tmp` permissions. When that
happens, the step logs `::warning::Live Postgres infra setup
failed` and the build CONTINUES — the offline DDL guard + the
pytest sweep are the always-on safety net. Only a REAL alembic
upgrade failure (i.e. the live check actually caught a migration
bug, not an infra hiccup) returns rc=2 from the inner block and
ALWAYS escalates.

**pgvector hard dependency:**
The migrations (010, 016, 017, 018, 019) create `vector(768)`
columns for chat_messages.embedding, evidence_embeddings, etc.,
AND they run `CREATE EXTENSION IF NOT EXISTS vector` themselves
inside the migration body. Without pgvector installed, that
migration step fails with "extension vector is not available"
which surfaces as rc=2 ("real migration bug") even though the
migration is correct — the issue is purely infra.

The CI pgvector strategy (belt + suspenders, after two iterations
of failure):

  1. **Pin to PG 15** via `apt install postgresql-15 postgresql-
     contrib-15` instead of the unpinned `postgresql` meta-package.
     The default meta-package can pull PG 17 (Sept 2024), for which
     pgvector apt packaging isn't yet in stable Debian mirrors.
     PG 15 has stable pgvector packaging across releases.
  2. **Apt install `postgresql-15-pgvector`** explicitly.
  3. **VERIFY the extension control file exists** at
     `/usr/share/postgresql/15/extension/vector.control`. apt-get
     install can return rc=0 even when the package is unavailable
     (depending on apt config / repo gaps), so we re-check the
     actual file.
  4. **Test CREATE EXTENSION as the postgres user before alembic
     runs.** If it fails here, alembic would fail too — return rc=1
     (fail-soft skip) BEFORE the misleading "real migration bug"
     escalation path fires.

An earlier attempt to stub `vector` as a composite type via
`CREATE TYPE vector AS (placeholder TEXT)` surfaced as
"syntax error at or near vector(768)" because the parameterized-
type syntax only works for built-in / extension-provided types.
Always install the real pgvector package; never stub the type.

A previous unpinned variant let PG 17 + missing pgvector-17 reach
the alembic stage and explode confusingly with rc=2 "extension
vector is not available". The pinned + verify approach above
prevents that confusion permanently.

To force strict enforcement (e.g. before a major migration push),
re-run the build with:

```bash
gcloud builds submit . --config infra/cloudbuild.yaml \
  --substitutions=_IMAGE_SHA="$SHA",_STRICT_LIVE_MIGRATION=1
```

…or invoke the wrapper:

```bash
STRICT_LIVE_MIGRATION=1 ./infra/build.sh
```

In strict mode, any infra hiccup also fails the build, so you
know the live check actually ran.

**Recovery if you hit T17 in production:**
1. Apply the fix locally (already in head as of commit fixing 018).
2. Push.
3. Re-run the deploy pipeline (`./deploy.sh`) — Stage 1 now catches
   migration errors before the image is even built.
4. Run `./infra/migrate.sh` — the self-healing wrapper applies the
   updated 018, then 019 + 020.

### §23.2 — `gcloud builds submit` rejects custom `--substitutions` keys

**Symptom** (Cloud Shell):
```text
ERROR: (gcloud.builds.submit) INVALID_ARGUMENT: generic::invalid_argument:
invalid value for 'build.substitutions': key in the template "PG_BIN"
is not a valid built-in substitution
```

**Root cause:**
Cloud Build pre-parses `cloudbuild.yaml` looking for substitution tokens
of the form `$NAME` or `${NAME}` where `NAME` is uppercase. It treats
EVERY such token as either a built-in substitution (`$PROJECT_ID`,
`$BUILD_ID`, `$REVISION_ID`, `$SHORT_SHA`) or a user-defined one
(`$_FOO`, must be prefixed with underscore). Any uppercase `$NAME` that
is neither — like a shell variable `$PG_BIN`, `$HEAD_REV`, `$PGDATA` —
is REJECTED at submit time before the build even starts.

Lowercase shell vars like `$rc` work because Cloud Build's parser only
treats uppercase tokens as candidates.

**Fix** (always for new shell vars in `cloudbuild.yaml`):
Double-escape uppercase shell variables as `$$NAME` or `$${NAME}`. The
first `$` is consumed by Cloud Build's parser; the second is passed
through to the shell, which sees `$NAME`.

Wrong:
```yaml
PG_BIN="$(ls -d /usr/lib/postgresql/*/bin | tail -1)"
echo "$PG_BIN"        # Cloud Build rejects: $PG_BIN parsed as substitution
```

Right:
```yaml
PG_BIN="$(ls -d /usr/lib/postgresql/*/bin | tail -1)"
echo "$${PG_BIN}"     # Cloud Build emits $PG_BIN; shell expands it
```

Built-in Cloud Build substitutions that DO work unescaped:
  `$PROJECT_ID`, `$BUILD_ID`, `$PROJECT_NUMBER`, `$LOCATION`,
  `$REVISION_ID`, `$COMMIT_SHA`, `$SHORT_SHA`, `$REPO_NAME`,
  `$BRANCH_NAME`, `$TAG_NAME`, `$TRIGGER_NAME`, `$TRIGGER_BUILD_CONFIG_PATH`

User-defined substitutions (declared in `substitutions:` block) work
unescaped if they start with `_` — e.g. `$_IMAGE_SHA`.

EVERY OTHER `$NAME` (uppercase) in cloudbuild.yaml shell scripts must
be `$$NAME`.

**Comment-line gotcha (cost us a second build):**
Cloud Build's substitution parser scans the entire YAML file looking
for tokens, INCLUDING content inside YAML comment lines (`# ...`).
A comment like:

```yaml
    # NOTE: Cloud Build interprets $UPPERCASE as substitutions
```

…will fail submission just as loudly as a live `echo $UPPERCASE`.
If a comment needs to reference an uppercase variable name, escape
it the same way: `$$UPPERCASE`. The `infra/build.sh` pre-flight no
longer excludes comment lines — it catches this class explicitly.

**Sanity check before pushing a cloudbuild.yaml change:**
```bash
# List all uppercase $VAR references that aren't already escaped or
# valid built-ins / user-defined. Any output here is a likely future
# build failure.
grep -nE '\$[A-Z][A-Z_]+' apps/dma-insights/infra/cloudbuild.yaml \
  | grep -v '\$\$' \
  | grep -vE '\$(PROJECT_ID|BUILD_ID|PROJECT_NUMBER|LOCATION|REVISION_ID|COMMIT_SHA|SHORT_SHA|REPO_NAME|BRANCH_NAME|TAG_NAME|TRIGGER_NAME)\b' \
  | grep -v '#'
```

**Recovery:** edit `cloudbuild.yaml` to add `$$` escapes; re-run
`gcloud builds submit`. The submit-time validation runs in <1s so
iteration is fast.

---

## §24 — Deploy-time DMA corpus seed + daily NEW-folder probe (2026-06-07)

> Per the operator mandate: "Ensure the 100+ DMAs are loaded onto
> the DB and persisted during deployment. The drive probe should
> check for new DMA folders on a daily basis and set up their
> profile and ingest all relevant material."

### What ships

| Surface | Cadence | What it does |
|---|---|---|
| `dma-insights-drive-crawler-6h` (existing) | every 6h | Delta-ingest of all KNOWN Drive folders. Skips unchanged folders via mtime + (post-033) material-manifest hash. |
| `dma-insights-drive-crawler-daily-discovery` (NEW, §24) | 02:00 CT daily | Dedicated NEW-folder discovery sweep. Cold-start cost only on folders that haven't been seen; intelligent skip on the rest. Catches folders uploaded between 6h-aligned slots. |
| `post-deploy-refresh.sh --seed-corpus` (NEW, §24) | on-demand at deploy | Loads the committed 100+ package corpus baked into the backend image into the DB. Idempotent re-runs are near-no-op via the migration-033 intelligent skip. |
| `historical_backfill --dir <path>` (extended) | on-demand | The CLI entrypoint behind --seed-corpus. Walks the package roots under `<path>`, calls parse_package + persist_package for each. |

### How to enable the corpus seed at deploy time

The deploy default is **OFF** — production environments that source
DMAs only from Drive should NOT seed the committed corpus. Two ways
to enable for dev / staging environments:

1. **Environment variable** (recommended for CI):
   ```bash
   export DMA_SEED_CORPUS_ON_DEPLOY=1
   bash infra/deploy-two-phase.sh
   ```
2. **Command-line flag** (one-off):
   ```bash
   bash infra/post-deploy-refresh.sh --seed-corpus
   ```

The seed runs the `dma-insights-historical-backfill` Cloud Run Job
with `--args="--dir,/home/app/tests/fixtures/dma_packages_batches"`.
The image already ships the corpus; no GCS bucket or sidecar
required for the initial deployment.

### Operational notes

- **Image size cost:** ~250 MB image bloat. Acceptable for dev /
  staging; production deployments that source from Drive only can
  comment the `COPY backend/tests/fixtures/dma_packages_batches`
  line in `infra/docker/backend.Dockerfile` to drop the bloat. The
  Drive crawler keeps the production Drive-first path intact.
- **Idempotency:** migration 033 (`runs.material_manifest_hash`)
  makes re-runs near-no-op. Verified locally: pass 1 seeds 19
  packages + warms 86 hashes; pass 2 SKIPs 103 / re-ingests 0 (only
  the 2 Pentegra twin-folder packages re-ingest, which is benign).
- **Daily NEW-folder probe:** the
  `dma-insights-drive-crawler-daily-discovery` Scheduler runs the
  same `dma-insights-drive-crawler` Cloud Run Job once at 02:00 CT
  every day. Same image, same entrypoint, same idempotency — the
  point of the daily slot is to catch folders uploaded outside the
  6h grid. NEW folders create entities + initial runs; existing
  folders skip.
- **Failure mode:** corpus seed is best-effort. If the historical
  backfill job fails (e.g. quota, network), the deploy is still LIVE
  and the operator can re-run manually:
  ```bash
  gcloud run jobs execute dma-insights-historical-backfill \
    --region=us-central1 \
    --args="--dir,/home/app/tests/fixtures/dma_packages_batches" \
    --wait
  ```

### Future migration

Move the corpus out of the image into a GCS bucket (`gs://dma-insights-corpus-prod/...`)
and bind-mount via Cloud Run's GCS volume support. This keeps the
runtime image lean while preserving the deploy-time hydration
contract. The intelligent skip logic doesn't care about file
location — only file content.

---

### §23.3 — First sign-in lands as AE, admin pages 403

**Symptom:** the deploying operator signs in via Google OAuth and gets
role AE; `/admin` and the Health/Context tabs are gated; every
`/api/v1/admin/*` probe returns 403 even though sign-in succeeded.

**Cause:** roles are assigned from the `admin_emails` allowlist at
first sign-in (`app/config.py`). The shipped default contains only
`chris.conant@zennify.com`. Any other operator lands as AE.

**Fix (before first sign-in):** set the allowlist on the backend
service —

```bash
gcloud run services update dma-insights-backend --region=${REGION} \
  --update-env-vars="DMA_ADMIN_EMAILS=you@zennify.com,chris.conant@zennify.com"
```

**Fix (after a wrong-role sign-in):** an existing ADMIN promotes via
Admin → Users (PATCH `/admin/users/{id}/role`); or run a one-shot
UPDATE on `users.role` via `infra/dma-psql.sh` when no ADMIN exists yet.

### §23.4 — UI renders in a system font (DM Sans never loads)

**Symptom:** the app works but typography looks like Segoe/system-ui;
`document.fonts.check('600 14px "DM Sans"')` in the browser console
returns `false`.

**Cause:** `frontend/index.html` loads DM Sans + DM Mono from
`fonts.googleapis.com` / `fonts.gstatic.com` (design system v2.4.15,
added 2026-06-10 — before that the font was silently never loaded).
A VPC egress policy or CSP that blocks those two hosts reverts every
user to the fallback stack.

**Fix:** allow egress to both hosts, or self-host the two woff2
families and swap the `<link>` tags in `frontend/index.html` for
`@font-face` rules served from the frontend bucket/image. Verify with
the `document.fonts.check` probe above after a hard reload.

## §25 — Cost optimization & resource retention (2026-06)

Audit triggered by a ~$68/day backend bill. The fixes below lower cost
**without touching the persistence contract** ("ingest once, serve forever";
"once Vertex interprets, persist it"). Every datum lives in Postgres (canonical)
or Redis (per-user ephemeral) — none of these changes delete, expire, or gate
persisted data. They only change *how often* idempotent maintenance jobs wake,
*how long* a serving instance/stream stays up, and *how many old Docker images*
are retained.

### §25.1 — Scheduler cadences (scheduled runs/day ~390 → ~73)

| Job | Was | Now | Persistence note |
|---|---|---|---|
| sheet_poller | `*/5 * * * *` (288/day) | `*/15 6-20 CT` (~57) | Upserts Ops-Sheet rows; reducing frequency only delays a *sync*, never drops data — the sheet is the source of truth and the poller short-circuits on no-change. |
| ccg_loader | hourly (24) | daily | Catalogue ships ~quarterly; loaded rows persist when written. |
| embedder | hourly (24) | every 6h | **Backstop only** — `post_commit_workers.dispatch_post_commit_workers` embeds each run in real time on ingest. Idempotent (skips embedded runs). |
| intelligence_recompute | hourly (24) | every 6h | Same backstop role; UPSERTs `customer_intelligence_profiles`; idempotent-skips unchanged entities. |

The real-time path is unchanged: ingest → post-commit dispatch → embedder +
recompute write embeddings/intelligence immediately. The schedulers are the
self-healing backstop for a *failed* dispatch — now bounded at 6h instead of 1h.

### §25.2 — Safeguard against runaway job cost (item #1: "failing jobs firing a lot")

A hung/failing job is the main runaway vector: Cloud Run bills CPU+mem for the
FULL `timeout`, times `(1 + max_retries)` attempts, on every fire. `local.jobs`
now carries a per-job `timeout` + `max_retries` cap (see `infra/terraform/main.tf`):
sheet_poller `180s`/`0`, ccg_loader `600s`/`0`, peer_patterns/chat_learning
`600-900s`/`0`, embedder/intelligence_recompute `900s`/`1`, drive_crawler
`1800s`/`1`. Frequent light jobs get **0 retries** — the next scheduled run *is*
the retry.

**Why this is persistence-safe:** every worker is transactional + idempotent. A
timeout-kill aborts the open transaction → rolls back → **no partial/corrupt
state is committed**; the next scheduled run re-does the work. To confirm a job
isn't silently failing (the "firing a lot" symptom is often *failing* a lot):

```bash
for j in sheet-poller embedder ccg-loader intelligence-recompute drive-crawler; do
  echo "== dma-insights-$j =="
  gcloud run jobs executions list --job="dma-insights-$j" --region="$REGION" \
    --limit=10 --format='value(name,status.completionTime,status.conditions[0].type)'
done
```

### §25.3 — Serving instances (frontend → scale-to-zero; SSE bounded)

- Frontend `min_instance_count` 1 → 0 (static nginx, ~1-2s cold start). Backend
  stays `min 1` (slow Cloud-SQL-proxy cold start on the critical path);
  `cpu_idle = true` is explicit on both so the warm instance bills memory +
  near-zero idle CPU, never full vCPU 24/7. No data is held in instance memory
  (Postgres/Redis are canonical), so scale-to-zero loses nothing.
- **Item #5 — SSE bounded lifetime.** `routers/sse.py` now closes each stream
  after `MAX_STREAM_SECONDS` (15 min) with a `reconnect` event; the browser's
  `EventSource` auto-reconnects (re-subscribes + re-sends the snapshot). A tab
  left open no longer pins a backend request (and a concurrency slot, billing
  CPU) overnight. **Persistence-safe:** SSE is a live-notification channel only
  — the events are also persisted (`job_executions`, `runs`) and the client
  re-syncs on every (re)connect, so nothing processed across sessions/users is
  lost when a stream rolls.

### §25.4 — Item #6: container image retention (one-time, persistence-safe)

gcr.io accumulated every SHA-tagged image (backend/frontend/workers × every
deploy) with no cleanup, growing storage cost. Apply the committed policy ONCE
per environment (it is NOT a Terraform resource on purpose — the gcr.io repo is
auto-created and adopting it into TF would risk breaking `terraform apply`):

```bash
# Preview first (dry-run prints what WOULD be deleted; deletes nothing):
gcloud artifacts repositories set-cleanup-policies gcr.io \
  --location=us --project="$PROJECT_ID" \
  --policy=apps/dma-insights/infra/gcr-cleanup-policy.json --dry-run

# Enforce once the preview looks right:
gcloud artifacts repositories set-cleanup-policies gcr.io \
  --location=us --project="$PROJECT_ID" \
  --policy=apps/dma-insights/infra/gcr-cleanup-policy.json
```

The policy **keeps the 15 most-recent versions per image** (the live SHA plus 14
rollback targets are NEVER deletable), deletes untagged build cruft after 7
days, and prunes tagged releases older than 60 days. This touches **Docker
layers in Artifact Registry only** — it cannot affect any Postgres/Redis data
processed across sessions or users, and the keep-15 rule guarantees the running
revision's image is never removed (no rollback/outage risk).

### §25.5 — Flagged for an operator cost/reliability decision (NOT auto-applied)

- **Cloud SQL `REGIONAL` → `ZONAL`** (~$3-4/day): removes HA standby. Data
  persistence is unaffected (same DB, same backups/PITR) — only failover SLA
  changes. Acceptable for an internal read-mostly tool; operator's call.
- **`db-custom-2-7680` → `db-custom-1-3840`** (~$3/day): only if query load is
  low (it sits behind the synthesis + TanStack caches). No data impact.
- **Redis tier** (external `dma-insights-redis-url`, not in this TF): if it is a
  Standard/HA Memorystore, a Basic tier ~halves it. Redis holds only per-user
  *ephemeral* state (ADR 0004), so tier changes don't risk canonical data.

## §26 — Gemini at deploy (bake-time enablement + per-surface assertions)

> Added 2026-07-02 (master plan Part 3 / RC1). Before this, the
> `regen-startup-pack` Cloud Build stage set `DMA_DISABLE_VERTEX=1`, so
> the committed startup pack was **Gemini-free by construction** (0
> vertex provenance markers across 945 pack files), no endpoint read the
> enrichment caches back into responses, and nothing in the deploy
> pipeline asserted a single Vertex call worked. Every AI surface could
> silently degrade to deterministic templates forever.

### §26.1 What runs Gemini-hot now

1. **Bake (Cloud Build `regen-startup-pack`)** — the regen containers run
   on the special `cloudbuild` Docker network so the build VM's metadata
   server provides ADC as `{project_number}@cloudbuild.gserviceaccount.com`,
   with `VERTEX_PROJECT_ID`/`GOOGLE_CLOUD_PROJECT=$PROJECT_ID` set and
   `DMA_DISABLE_VERTEX` **removed**. After `run_derive_chain` the stage
   additionally runs:
   - `python -m app.scripts.enrich_corpus --surfaces all` — full surface
     warm: `why_now`, `platform_story`, `firmographics_extraction`, and
     the new `thought_leadership_extraction` (all validator-gated,
     persisted to `vertex_synthesis_cache` + domain tables with
     `source:"vertex"` + `model_id` + `synthesized_at` provenance);
   - `python -m workers.embedder.main --since 2000-01-01` — the
     evidence/section embedding pass (idempotent; skips embedded rows).
   Both run BEFORE `export_startup_data`/`export_startup_pages` so the
   snapshot captures the enrichment.
   IAM: terraform grants `roles/aiplatform.user` to the **Cloud Build
   SA** (`google_project_iam_member.cloud_build_aiplatform_user`) next to
   the existing compute-SA grant (which covers Cloud Run runtime + jobs).
2. **Runtime read-path** — the D1 overview endpoint now merges
   validator-passed cache rows back into responses (why_now uplift
   signal, firmographics gap-fill provenance, thought-leadership fill,
   entity-level `ai_enrichments`), each field stamped
   `source:"vertex"` + `model_id` + `synthesized_at`
   (`app/services/overview_gemini_merge.py`).
3. **Startup guard** — `assert_production_ready(role="backend")` performs
   a 1-token Vertex reachability probe (`count_tokens`) under
   `ENV=prod|dev`, so an IAM/project misconfiguration fails the revision
   at startup with the exact fix hint instead of degrading every AI
   surface to templates.

### §26.2 The assertions (`qa_gemini_surfaces`)

`backend/app/scripts/qa_gemini_surfaces.py` runs a stratified 5-entity
sample and asserts per surface; exit codes in `infra/EXIT_CODES.md`.

| Where | Mode | Gate |
|---|---|---|
| Cloud Build `regen-startup-pack` (end of chain, after `apply_startup_data_fixes`) | `--mode baked` | **HARD** — a cold pack fails the build |
| `infra/post-deploy-refresh.sh` §2c (after `run_derive_chain`) | `--mode baked` vs the live DB | best-effort (deploy already live; prints remediation) |
| `backend/scripts/post-deploy-smoke.sh` check 8 | `--mode live --base-url $BE` | HARD within the smoke gate |

Baked-mode checks: validator-passed `why_now`/`platform_story` cache
rows; `parsed_facts._gemini_extracted`; `intelligence_summary_md`;
Gemini-clustered (`synthesized:gemini-flash`) focus areas;
thought-leadership + subcap-narrative (WARN-only today); embeddings
counts (WARN-only when the bake skipped the embedder). Live-mode checks:
`POST /api/v1/rag/answer` returns `fallback_used=false` with ≥1
citation, and a sampled overview carries a `source:"vertex"` why_now
signal. Live auth: export `DMA_SMOKE_TOKEN=<session JWT>` (e.g. from
`/api/v1/auth/dev-login` on non-prod); without it the live gate degrades
to route-registration checks and WARNs.

### §26.3 `_ALLOW_COLD_GEMINI` (the only escape hatch)

- Cloud Build: `--substitutions=_ALLOW_COLD_GEMINI=true` lets a
  deliberately-cold regen ship — the assertions downgrade to loud
  warnings and the pack manifest (`startup-data/pages_manifest.json`) is
  stamped `"gemini": "cold"` (a green run stamps `"gemini": "hot"`).
- Backend/service env: `_ALLOW_COLD_GEMINI=true` (or
  `ALLOW_COLD_GEMINI=true`) downgrades the startup probe + the smoke
  gate to warnings.
- `DMA_DISABLE_VERTEX=1` remains the *intentionally cold* switch for QA
  harnesses/local sandboxes (fast-fail to deterministic fallbacks —
  unchanged).

Default is **assertions HARD**: a deploy that cannot prove its Gemini
surfaces work does not ship silently.

### §26.4 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| regen fails: `Gemini surface assertions FAILED` | Cloud Build SA lacks Vertex access | `gcloud projects add-iam-policy-binding $PROJECT_ID --member=serviceAccount:$(gcloud projects describe $PROJECT_ID --format='value(projectNumber)')@cloudbuild.gserviceaccount.com --role=roles/aiplatform.user` (or `terraform apply` — the binding is in main.tf) |
| probe fails at revision startup | compute SA lacks `roles/aiplatform.user`, wrong `VERTEX_PROJECT_ID`, or Model Garden lacks the pinned models | see §0.2.13 model discovery; the probe error message carries the binding command |
| smoke check 8 WARNs `DMA_SMOKE_TOKEN unset` | no session JWT exported | mint one via dev-login (non-prod) or a real session; re-run `post-deploy-smoke.sh` |
| `why_now_vertex_provenance FAIL` on a warm-looking deploy | enrich_corpus never ran against the live DB | `infra/post-deploy-refresh.sh` (derive chain includes it) or `python -m app.scripts.enrich_corpus --surfaces all` |

### §26.5 — Pack freshness gate (`source_sha` + `_ALLOW_STALE_PACK`)

> Added 2026-07-02 (master plan Part 14). Before this, the regen stage
> was **fail-open**: a failed export logged `::warning:: … keeping
> committed pack` and the build kept going, so the frontend silently
> baked the STALE committed `startup-data/` snapshot;
> `pages_manifest.json` stamped `source_sha: "unknown"` at every deploy
> (no `SOURCE_SHA` reached the exporter), and nothing anywhere asserted
> the baked pack matched the build. `--skip-build` after data/derive
> changes shipped an old pack with zero signal.

The freshness contract, end to end:

1. **Stamp** — the `regen-startup-pack` stage passes
   `SOURCE_SHA=${_IMAGE_SHA}` into the regen containers.
   `export_startup_pages` writes it to `pages_manifest.json`
   `source_sha`; `export_startup_data` writes it to
   `manifest.json`/`scores.json`/`dashboard.json` (it also receives an
   explicit `--sha ${_IMAGE_SHA}`). A **local** run without the env
   stamps a truthful `local-<git short sha>` (never a fake build SHA);
   only a git-less checkout falls back to `"unknown"`.
2. **Exporters are HARD** — `export_startup_data` /
   `export_startup_pages` run via the regen step's `step_hard`: a
   non-zero exit **fails the build** (no more `|| echo … continuing`).
   The regen then greps the just-written manifest and fails loud if the
   stamp ≠ `${_IMAGE_SHA}` (`source_sha ✓` log line), and runs
   `qa_pack_parity --strict` (also `step_hard`) proving the exported
   pack matches the regen DB value-for-value before the Gemini gate.
3. **Check 6 (build)** — `frontend-image-smoke` fetches
   `/startup-data/pages_manifest.json` from the **built image** and
   asserts `source_sha == ${_IMAGE_SHA}`. This measures the OUTCOME, so
   any upstream miss (regen infra hiccup that kept the committed pack, a
   stale cache) lands here with exit 4.
4. **Check 9 (live)** — `post-deploy-smoke.sh` optionally asserts the
   **deployed** frontend serves a pack matching the deployed SHA
   (`FRONTEND_URL` + `DEPLOY_SHA`/`SHA` env) — the only gate that can
   catch `--skip-build` reusing an old image, since Cloud Build never
   runs on that path.

`_ALLOW_STALE_PACK=true` (Cloud Build substitution; env var for smoke
check 9) is the **ONE sanctioned escape** — every use prints a loud
WARNING naming the stale artifact that ships. It is deliberately
separate from `_ALLOW_COLD_GEMINI` (§26.3): *stale* (old data) and
*cold* (no Gemini enrichment) are different failures with different
blast radii. Exit codes: `infra/EXIT_CODES.md` "Pack-freshness gates".

**Redeploy checklist (pack freshness + Gemini):**

- [ ] Deploy a **new SHA** — never `--skip-build` after data/derive/
      exporter changes (the pack is baked at build time; an old image ==
      an old pack, and only smoke check 9 can catch it post-hoc).
- [ ] Cloud Build log shows the three gate lines: **regen ✓**
      (`✓ regenerated GEMINI-HOT first-paint pack`), **gemini ✓**
      (`qa_gemini_surfaces --mode baked` SUMMARY with 0 FAIL), and
      **source_sha ✓** (`pages_manifest.json source_sha=<sha> matches
      _IMAGE_SHA`), plus frontend-image-smoke
      `✓ startup pack is FRESH`.
- [ ] Phase 6/7 SHA gates are **unchanged and still authoritative** for
      the *image*: Phase 6 verifies the frontend serves
      `<meta x-build-sha> == $SHA`; Phase 7 runs `verify-deploy.sh`.
      The pack gates above verify the *data inside* that image.
- [ ] Post-deploy: `post-deploy-smoke.sh` all 9 checks green
      (`[8/9]` Gemini live, `[9/9]` pack freshness with
      `FRONTEND_URL`+`SHA` exported).
- [ ] `_ALLOW_STALE_PACK` / `_ALLOW_COLD_GEMINI` left at `"false"`
      unless this deploy is deliberately shipping stale/cold — in which
      case say so in the deploy notes.
