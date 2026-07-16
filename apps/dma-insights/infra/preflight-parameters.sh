#!/usr/bin/env bash
#
# Pre-deployment parameter validation.
#
# Per the 2026-05-28 audit (item E in the pending register): every
# required parameter MUST be defined + non-empty BEFORE we start
# building images or invoking Terraform. The alternative is a
# half-deployed state where Cloud Run revisions exist but can't
# start because a secret is empty.
#
# Usage:
#   bash infra/preflight-parameters.sh                 # validate-only
#   bash infra/preflight-parameters.sh --create-secrets  # also create the
#                                                       # OOB secrets if absent
#
# Exits:
#   0  → all parameters present + non-empty
#   1  → at least one required parameter missing or empty (fail-closed)
#   2  → unsupported flag

set -euo pipefail
_NF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "${_NF_DIR}/gcloud-noise-filter.sh" ] && . "${_NF_DIR}/gcloud-noise-filter.sh"

MODE="validate"
for arg in "$@"; do
  case "$arg" in
    --create-secrets) MODE="create" ;;
    --help|-h)
      cat <<EOF
Usage: $0 [--create-secrets]

Validates that every parameter required by Terraform + the production-
readiness guard at app/config.py is defined in the current environment
+ non-empty.

When --create-secrets is passed, also (idempotently) creates the
out-of-band Secret Manager secrets that Terraform's data blocks expect.
EOF
      exit 0
      ;;
    *)
      echo "FATAL: unknown flag '$arg' -- use --help" >&2
      exit 2
      ;;
  esac
done

# ── Required parameters ──────────────────────────────────────────
#
# Two categories:
#   * GCP_VARS — needed by Terraform variable.tf + gcloud config.
#   * APP_SECRETS — used by app/config.py REQUIRED_FOR_PROD_BACKEND.
#                   The deployment doc §0.5 stores these as Secret
#                   Manager secrets; Cloud Run mounts them as env vars.

declare -a GCP_VARS=(
  PROJECT_ID
  REGION
  GOOGLE_OAUTH_CLIENT_ID
)
declare -a APP_SECRETS=(
  GOOGLE_OAUTH_CLIENT_SECRET     # → dma-insights-oauth-client-secret
  DMA_BOT_API_KEY                # → dma-insights-bot-api-key
  RAG_API_BEARER_KEY             # → dma-insights-rag-api-key
  REDIS_URL                      # → dma-insights-redis-url
)
# Clay connector secrets — required when DMA_CLAY_DEFERRED is unset
# (default). Operators on Clay tiers without webhook support can set
# DMA_CLAY_DEFERRED=1 to defer this until upgrade; the backend's Clay
# client already fails-closed when the secret is empty (per ADR 0010)
# AND skips outbound enrichment when DMA_CLAY_DEFERRED=1 is also set
# on the Cloud Run env.
declare -a CLAY_SECRETS=(
  CLAY_WEBHOOK_URL               # → dma-insights-clay-webhook-url
  CLAY_WEBHOOK_SECRET            # → dma-insights-clay-webhook-secret
)

# Non-secret env vars with canonical Zennify defaults. preflight
# auto-fills these with a WARN when unset, so the operator doesn't
# have to manually re-source them every Cloud Shell open. Override
# in .deploy.parameters.env when targeting a different deployment.
declare -A NON_SECRET_DEFAULTS=(
  [DRIVE_ROOT_FOLDER_ID]=1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P
  [OPS_SHEET_ID]=1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8
  [VERTEX_LOCATION]=us-central1
  [CATALOGUE_DEFAULT_VERSION]=v7.0
  [DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION]=v5.0
  [VERTEX_FLASH_MODEL]=gemini-2.5-flash
  [VERTEX_PRO_MODEL]=gemini-2.5-pro
  [VERTEX_EMBEDDING_MODEL]=text-embedding-004
)
# VERTEX_PROJECT_ID defaults to PROJECT_ID (the common case); we set
# it separately AFTER the PROJECT_ID check below.

# Live-mode required (full prod with backfill + RAG). Set
# `DEPLOY_MODE=minimal` to demote these to WARN. NOTE the honest scope
# (2026-07-04 line audit): minimal mode ONLY relaxes THIS preflight —
# terraform has no minimal-mode wiring, so all worker jobs + schedulers
# still deploy fully enabled; jobs missing their params fail at RUN
# time instead of deploy time. Treat it as "let me deploy the app
# surface while I finish parameterising the ingest jobs".
declare -a LIVE_MODE_REQUIRED=(
  DRIVE_ROOT_FOLDER_ID                    # Drive crawler + historical_backfill
  OPS_SHEET_ID                            # sheet_poller
  VERTEX_PROJECT_ID                       # Vertex AI calls (Gemini + embedding)
  VERTEX_LOCATION                         # Vertex region for the models
  CATALOGUE_DEFAULT_VERSION               # current production catalogue (v7.0)
  DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION  # v5.* for historical Drive backfills
)

# Optional but recommended; we WARN (not FAIL) if these are missing.
declare -a RECOMMENDED=(
  ALLOWED_ORIGINS
  VERTEX_FLASH_MODEL                      # default: gemini-2.5-flash
  VERTEX_PRO_MODEL                        # default: gemini-2.5-pro
  VERTEX_EMBEDDING_MODEL                  # default: text-embedding-004
)

# Self-heal non-secret defaults BEFORE validation. 2026-05-29 QA audit
# Fix-I — opt-in policy:
#
#   USE_ZENNIFY_CANONICAL_DEFAULTS=1 (default)
#     → auto-fill with the canonical Zennify production values; preserves
#       the legacy turnkey deploy behaviour.
#
#   USE_ZENNIFY_CANONICAL_DEFAULTS=0
#     → DO NOT auto-fill. Missing values fall through to the validation
#       pass below and FAIL the preflight with a clear error message.
#       This is the right policy for any non-canonical deploy (a fork,
#       a customer install, a staging clone) where the canonical Drive
#       folder + Ops Sheet + Vertex region are NOT the right values.
#
# The QA audit flagged that the previous unconditional auto-fill made
# every non-canonical deploy silently target Zennify's Drive folder
# (`1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`) and Ops Sheet — a confidentiality
# + correctness defect waiting to happen.
DEPLOY_MODE="${DEPLOY_MODE:-live}"
USE_ZENNIFY_CANONICAL_DEFAULTS="${USE_ZENNIFY_CANONICAL_DEFAULTS:-1}"

if [[ "$USE_ZENNIFY_CANONICAL_DEFAULTS" == "1" ]]; then
  for var in "${!NON_SECRET_DEFAULTS[@]}"; do
    if [[ -z "${!var:-}" ]]; then
      export "$var"="${NON_SECRET_DEFAULTS[$var]}"
      echo "  ⚙ $var: auto-filled with canonical default '${NON_SECRET_DEFAULTS[$var]}'"
    fi
  done
  # Special case: VERTEX_PROJECT_ID defaults to PROJECT_ID.
  if [[ -z "${VERTEX_PROJECT_ID:-}" && -n "${PROJECT_ID:-}" ]]; then
    export VERTEX_PROJECT_ID="$PROJECT_ID"
    echo "  ⚙ VERTEX_PROJECT_ID: auto-filled from PROJECT_ID ('$PROJECT_ID')"
  fi
else
  echo "  ℹ USE_ZENNIFY_CANONICAL_DEFAULTS=0 — auto-fill disabled."
  echo "    All NON_SECRET_DEFAULTS must be set explicitly OR the preflight will fail."
fi

# ── Validation pass ──────────────────────────────────────────────
echo "→ Validating deployment parameters…"
PROBLEMS=0
# Fail closed on the secrets-loader sentinel: `source <(load-from-
# secret-manager.sh --emit-exports)` cannot abort the caller's shell,
# so a missing REQUIRED secret exports DMA_SECRETS_MISSING instead and
# THIS gate (which every deploy runs) turns it into a hard stop
# (2026-07-04 line audit — DATABASE_URL used to go missing silently).
if [[ -n "${DMA_SECRETS_MISSING:-}" ]]; then
  echo "  ✗ Secret Manager loader reported missing REQUIRED secrets:"
  for v in ${DMA_SECRETS_MISSING}; do
    echo "      • $v"
  done
  echo "    Populate them (DEPLOYMENT.md §0.2.x / §0.5.1), re-source the"
  echo "    loader, then re-run this preflight."
  PROBLEMS=$((PROBLEMS + 1))
fi
for v in "${GCP_VARS[@]}" "${APP_SECRETS[@]}"; do
  val="${!v:-}"
  if [[ -z "$val" ]]; then
    echo "  ✗ $v: NOT SET (required)"
    PROBLEMS=$((PROBLEMS + 1))
  else
    # Mask the value when logging; just show length + a prefix.
    short="${val:0:6}..."
    echo "  ✓ $v: present (${#val} chars, starts ${short})"
  fi
done

# Clay secrets — required by default, deferred when DMA_CLAY_DEFERRED=1.
if [[ "${DMA_CLAY_DEFERRED:-0}" == "1" ]]; then
  for v in "${CLAY_SECRETS[@]}"; do
    val="${!v:-}"
    if [[ -z "$val" ]]; then
      echo "  ⚠ $v: NOT SET (DMA_CLAY_DEFERRED=1 — Clay enrichment disabled)"
    else
      short="${val:0:6}..."
      echo "  ✓ $v: present (${#val} chars, starts ${short}) — Clay deferred but stored"
    fi
  done
else
  for v in "${CLAY_SECRETS[@]}"; do
    val="${!v:-}"
    if [[ -z "$val" ]]; then
      echo "  ✗ $v: NOT SET (required — or set DMA_CLAY_DEFERRED=1 to defer)"
      PROBLEMS=$((PROBLEMS + 1))
    else
      short="${val:0:6}..."
      echo "  ✓ $v: present (${#val} chars, starts ${short})"
    fi
  done
fi

# OAuth client_secret sanity check — operators sometimes paste the
# entire client_secret_*.json file as the secret value instead of
# extracting just the `client_secret` field. A real GOCSPX-* secret
# is ~24 chars and ASCII-only; >80 chars with `{` or `:` markers is
# almost certainly the raw JSON.
if [[ -n "${GOOGLE_OAUTH_CLIENT_SECRET:-}" ]]; then
  cs="$GOOGLE_OAUTH_CLIENT_SECRET"
  if [[ "${#cs}" -gt 80 ]] && { [[ "$cs" == *"{"* ]] || [[ "$cs" == *"\"client_secret\""* ]]; }; then
    echo "  ⚠ GOOGLE_OAUTH_CLIENT_SECRET: ${#cs} chars + contains JSON markers."
    echo "    Looks like you stored the full client_secret_*.json file." >&2
    echo "    Extract only the .web.client_secret field:" >&2
    echo "      jq -r '.web.client_secret // .installed.client_secret' client_secret_*.json" >&2
    echo "    Then re-add it to Secret Manager:" >&2
    echo "      echo -n \"<value>\" | gcloud secrets versions add \\" >&2
    echo "        dma-insights-oauth-client-secret --data-file=- --project=\"\$PROJECT_ID\"" >&2
    # Don't FATAL — operator may have a legitimate long secret; just warn.
  fi
fi

# Live-mode required vars: required when DEPLOY_MODE=live (default);
# downgraded to WARN when DEPLOY_MODE=minimal (which also disables the
# affected jobs in Terraform). The audit pinned these as P1 because
# the old default treated DRIVE_ROOT_FOLDER_ID + OPS_SHEET_ID as
# merely "recommended" — operators could ship a deploy with backfill
# jobs configured but no folder ID set, and the workers would crash
# at startup with no operator-visible trace.
DEPLOY_MODE="${DEPLOY_MODE:-live}"
for v in "${LIVE_MODE_REQUIRED[@]}"; do
  val="${!v:-}"
  if [[ -z "$val" ]]; then
    if [[ "$DEPLOY_MODE" == "minimal" ]]; then
      echo "  ⚠ $v: NOT SET (minimal mode — backfill/RAG jobs will be disabled)"
    else
      echo "  ✗ $v: NOT SET (required for DEPLOY_MODE=live)"
      PROBLEMS=$((PROBLEMS + 1))
    fi
  else
    short="${val:0:6}..."
    echo "  ✓ $v: present (${#val} chars, starts ${short})"
  fi
done

for v in "${RECOMMENDED[@]}"; do
  val="${!v:-}"
  if [[ -z "$val" ]]; then
    echo "  ⚠ $v: NOT SET (recommended; will use config.py default)"
  else
    short="${val:0:6}..."
    echo "  ✓ $v: present (${#val} chars, starts ${short})"
  fi
done

if [[ $PROBLEMS -gt 0 ]]; then
  echo "" >&2
  echo "FATAL: $PROBLEMS required parameter(s) missing. Bootstrap aborted." >&2
  echo "" >&2

  # Specific actionable hint when the ONLY missing params are the two
  # Clay secrets AND DMA_CLAY_DEFERRED isn't set. This is the most
  # common "intent vs state" mismatch — the operator decided to defer
  # Clay (per ADR 0010) but never `export DMA_CLAY_DEFERRED=1`, so the
  # env-writer wrote a `# (unset)` comment and the preflight aborted.
  # Print the EXACT one-liner that resolves it.
  if [[ "${DMA_CLAY_DEFERRED:-0}" != "1" ]] \
     && [[ -z "${CLAY_WEBHOOK_URL:-}" ]] \
     && [[ -z "${CLAY_WEBHOOK_SECRET:-}" ]]; then
    echo "Detected: Clay secrets are unset AND DMA_CLAY_DEFERRED isn't '1'." >&2
    echo "If you're deferring Clay (the common case on tiers without webhook" >&2
    echo "support), run this one-liner from your repo root and the preflight" >&2
    echo "will pass:" >&2
    echo "" >&2
    echo "  export DMA_CLAY_DEFERRED=1" >&2
    echo "  echo 'DMA_CLAY_DEFERRED=1' >> .deploy.parameters.env" >&2
    echo "  bash infra/preflight-parameters.sh" >&2
    echo "" >&2
  fi

  echo "Set these env vars (in .deploy.parameters.env OR your shell) then re-run." >&2
  echo "See docs/DEPLOYMENT.md §0.2 for the canonical parameter list + how to obtain each value." >&2
  echo "Or set DEPLOY_MODE=minimal to bootstrap without live-mode params (backfill/RAG disabled)." >&2
  exit 1
fi

echo "✓ All required deployment parameters present (DEPLOY_MODE=$DEPLOY_MODE)"

# ── Pattern sanity checks ──────────────────────────────────────
echo "→ Sanity-checking parameter shapes…"
if [[ ! "$PROJECT_ID" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "FATAL: PROJECT_ID '$PROJECT_ID' doesn't match the GCP project naming pattern" >&2
  echo "       (lowercase letters, digits, hyphens; 6-30 chars; start with a letter, end with letter/digit)." >&2
  exit 1
fi

if [[ ! "$REGION" =~ ^[a-z]+-[a-z0-9]+[1-9]$ ]]; then
  echo "FATAL: REGION '$REGION' doesn't match a Cloud Run region pattern (e.g. us-central1)." >&2
  exit 1
fi

if [[ -n "${GOOGLE_OAUTH_CLIENT_ID:-}" ]] \
   && [[ ! "$GOOGLE_OAUTH_CLIENT_ID" =~ \.apps\.googleusercontent\.com$ ]]; then
  echo "FATAL: GOOGLE_OAUTH_CLIENT_ID '$GOOGLE_OAUTH_CLIENT_ID' doesn't end in .apps.googleusercontent.com" >&2
  echo "       — it's not a real OAuth web client ID. Visit https://console.cloud.google.com/apis/credentials" >&2
  exit 1
fi

if [[ -n "${REDIS_URL:-}" ]] \
   && [[ "$REDIS_URL" != redis://* && "$REDIS_URL" != rediss://* ]]; then
  echo "FATAL: REDIS_URL '$REDIS_URL' must start with redis:// or rediss://" >&2
  exit 1
fi

# CLAY_WEBHOOK_URL shape — only enforced when Clay isn't deferred AND
# the value is non-empty. Guard against `set -u` unbound-variable
# crashes when DMA_CLAY_DEFERRED=1.
if [[ "${DMA_CLAY_DEFERRED:-0}" != "1" ]] \
   && [[ -n "${CLAY_WEBHOOK_URL:-}" ]] \
   && [[ "$CLAY_WEBHOOK_URL" != https://* ]]; then
  echo "FATAL: CLAY_WEBHOOK_URL '$CLAY_WEBHOOK_URL' must be an https:// URL" >&2
  exit 1
fi

# Catalogue version shapes — required for live mode; cheap to validate.
if [[ "$DEPLOY_MODE" == "live" ]]; then
  if [[ -n "${CATALOGUE_DEFAULT_VERSION:-}" ]] && [[ ! "$CATALOGUE_DEFAULT_VERSION" =~ ^v[0-9]+(\.[0-9]+)?$ ]]; then
    echo "FATAL: CATALOGUE_DEFAULT_VERSION='$CATALOGUE_DEFAULT_VERSION' must match v<N>(.<M>) (e.g. v7.0)" >&2
    exit 1
  fi
  if [[ -n "${DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION:-}" ]] && [[ ! "$DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION" =~ ^v[0-9]+(\.[0-9]+)?$ ]]; then
    echo "FATAL: DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION='$DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION' must match v<N>(.<M>) (e.g. v5.0)" >&2
    exit 1
  fi
  # The backfill default must be a different (older) major than the
  # current default, otherwise Drive historical assessments will mis-
  # map to current-version subcaps. We DON'T enforce strict ordering
  # (operators may roll v5.0 forward); we just warn if they match.
  if [[ -n "${CATALOGUE_DEFAULT_VERSION:-}" ]] \
       && [[ "$CATALOGUE_DEFAULT_VERSION" == "${DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION:-}" ]]; then
    echo "  ⚠ CATALOGUE_DEFAULT_VERSION == DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION; "
    echo "    historical Drive backfills will resolve to the same catalogue as new ingests."
  fi
fi

echo "✓ Parameter shapes look right"

# ── Optional: create OOB secrets ────────────────────────────────
if [[ "$MODE" == "create" ]]; then
  command -v gcloud >/dev/null || {
    echo "FATAL: gcloud not on PATH; --create-secrets requires gcloud" >&2
    exit 1
  }
  echo "→ Creating out-of-band Secret Manager secrets idempotently…"
  declare -A SECRET_MAP=(
    [GOOGLE_OAUTH_CLIENT_SECRET]=dma-insights-oauth-client-secret
    [DMA_BOT_API_KEY]=dma-insights-bot-api-key
    [RAG_API_BEARER_KEY]=dma-insights-rag-api-key
    [REDIS_URL]=dma-insights-redis-url
    [CLAY_WEBHOOK_URL]=dma-insights-clay-webhook-url
    [CLAY_WEBHOOK_SECRET]=dma-insights-clay-webhook-secret
  )
  for env_var in "${!SECRET_MAP[@]}"; do
    secret_id="${SECRET_MAP[$env_var]}"
    # ${!env_var:-} NOT ${!env_var}: under `set -u` a bare indirect
    # expansion of an unset var aborts MID-LOOP with a cryptic bash
    # error, leaving Secret Manager half-updated — and the documented
    # DMA_CLAY_DEFERRED=1 path is exactly that state (2026-07-04 line
    # audit). Empty values are SKIPPED loudly, never pushed as empty
    # secret versions.
    val="${!env_var:-}"
    if [[ -z "$val" ]]; then
      echo "  ⏭ $secret_id: $env_var unset/empty — skipped (deferred or set later via §0.2.x)"
      continue
    fi
    if ! gcloud secrets describe "$secret_id" --project="$PROJECT_ID" >/dev/null 2>&1; then
      echo "  → creating secret $secret_id"
      gcloud secrets create "$secret_id" --replication-policy=automatic --project="$PROJECT_ID" >/dev/null
    fi
    echo -n "$val" | gcloud secrets versions add "$secret_id" --data-file=- --project="$PROJECT_ID" >/dev/null
    echo "  ✓ $secret_id: latest version updated"
  done
  echo "✓ OOB secrets processed (present values pushed; empty ones skipped above)"
fi

echo ""
echo "✓ Pre-deployment validation passed for project=$PROJECT_ID region=$REGION"
echo "  Next: bash infra/build.sh --dry-run  →  bash infra/build.sh"
