#!/usr/bin/env bash
#
# Two-phase Cloud Run deploy — closes the traffic-shifts-before-
# migrations race window the audit identified as P1.
#
# Old flow (deploy.sh):
#   terraform apply  →  Cloud Run revision created + traffic flipped
#                       to it immediately  →  migrate.sh runs while
#                       the new image is serving against the OLD schema
#   Risk window: 10-60s where every request from a real user hits
#   the new code against the old DB schema. Migration failures during
#   this window leave the new image serving 5xx on every request.
#
# New flow (this script):
#   1. Build images (gcloud builds submit)
#   2. Deploy a NEW Cloud Run revision with --no-traffic
#      (revision lives but doesn't receive traffic)
#   3. Run migrations against the live DB
#   4. Probe the new revision's /readyz via its revision-specific URL
#      (NOT the service URL — that's still pointing at the old revision)
#   5. ONLY after /readyz is green, flip 100% traffic to the new
#      revision via `gcloud run services update-traffic --to-latest`
#   6. Final verify against the service URL
#
# Failure recovery:
#   At any failure point, the OLD revision is still serving traffic.
#   No rollback needed -- just delete the failed new revision OR
#   leave it (no-traffic revisions are billed only when they receive
#   requests, which they don't).
#
# Usage:
#   bash infra/deploy-two-phase.sh                   # build + deploy
#   bash infra/deploy-two-phase.sh --skip-build      # use existing image
#   bash infra/deploy-two-phase.sh --skip-migrate    # no DDL changes
#   bash infra/deploy-two-phase.sh --skip-db-verify  # secret known stable

set -euo pipefail

# ── SHA contract (cloudbuild ↔ deploy-two-phase, 2026-06-06 R5) ──────
# When an operator submits cloudbuild with an explicit substitution like
#   gcloud builds submit --substitutions=_IMAGE_SHA=abc1234
# Cloud Build tags the produced images with `:abc1234` and pushes
# `gcr.io/$PROJECT_ID/dma-insights-backend:abc1234`. If this script is
# then run with `SHA` unset, the default `git rev-parse --short HEAD`
# fallback may resolve to a DIFFERENT short hash (e.g. when the
# operator already moved HEAD or is running from a different worktree).
# Phase 2 then tries to deploy `:<head-sha>` -- which doesn't exist --
# and the deploy aborts deep into the chain with an opaque image-not-
# found error.
#
# The fix is to make the contract explicit:
#   - If you ran cloudbuild with `_IMAGE_SHA=X`, ALSO export SHA=X here.
#   - If you didn't, the script defaults to `git rev-parse --short HEAD`.
#   - Phase 0.5 checks that `gcr.io/$PROJECT_ID/dma-insights-backend:$SHA`
#     actually exists and aborts with an actionable hint when it doesn't.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"

# Resolve the image tag. Default = the NEWEST commit on the deploy branch
# (resolve-deploy-sha.sh fetches origin + syncs the working tree to it), so a
# stale checkout, a leftover feature branch (the bde8329 incident), or a
# leaked `SHA` env var can NEVER ship an old image. An explicit `SHA=X` still
# pins a specific pre-built image, but is then guarded against staleness below.
SHA_WAS_EXPLICIT=false
[[ -n "${SHA:-}" ]] && SHA_WAS_EXPLICIT=true
if [[ "$SHA_WAS_EXPLICIT" == false ]]; then
  SHA="$(bash "${SCRIPT_DIR}/resolve-deploy-sha.sh")" || {
    echo "FATAL: could not resolve the newest deploy SHA (see above)." >&2
    exit 2
  }
fi

# Never silently deploy a STALE commit: if an explicit SHA was passed that is
# an ANCESTOR of the deploy-branch tip, it's behind the newest code — refuse.
# (Set DEPLOY_ALLOW_STALE=1 only to intentionally roll BACK to an older build.)
if [[ "$SHA_WAS_EXPLICIT" == true && "${DEPLOY_ALLOW_STALE:-}" != "1" ]]; then
  NEWEST="$(NO_SYNC=1 bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null || true)"
  if [[ -n "$NEWEST" && "$NEWEST" != "$SHA" ]] \
     && git merge-base --is-ancestor "$SHA" "$NEWEST" 2>/dev/null; then
    echo "FATAL: SHA=$SHA is STALE — it is behind the newest deploy-branch tip ${NEWEST}." >&2
    echo "  Deploy the newest code by re-running with SHA unset, or set" >&2
    echo "  DEPLOY_ALLOW_STALE=1 to intentionally roll back to ${SHA}." >&2
    exit 2
  fi
fi

# ── Required env ───────────────────────────────────────────────
# Fall back to the active gcloud project so an operator who ran
# `gcloud config set project <id>` (the standard setup, shown in the Cloud
# Shell prompt) does NOT also have to export PROJECT_ID. Only error when BOTH
# are unset. Export both so every sub-script (preflight, migrate, terraform,
# post-deploy-refresh) and gcloud invocation sees them.
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
: "${PROJECT_ID:?PROJECT_ID unset and no active gcloud project — run: gcloud config set project <id>}"
: "${REGION:=us-central1}"
export PROJECT_ID REGION
SKIP_BUILD=false
SKIP_MIGRATE=false
SKIP_DB_VERIFY=false
SKIP_REFRESH=false
INVALIDATE_CACHE=false
for arg in "$@"; do
  case "$arg" in
    --skip-build) SKIP_BUILD=true ;;
    --skip-migrate) SKIP_MIGRATE=true ;;
    --skip-db-verify) SKIP_DB_VERIFY=true ;;
    # Accept the same post-deploy flags as deploy.sh so an operator's
    # muscle-memory (`deploy-two-phase.sh --skip-refresh --invalidate-cache`)
    # doesn't FATAL. --skip-refresh skips Phase 8; --invalidate-cache is
    # forwarded to post-deploy-refresh.sh.
    --skip-refresh) SKIP_REFRESH=true ;;
    --invalidate-cache) INVALIDATE_CACHE=true ;;
    *) echo "FATAL: unknown flag '$arg'" >&2; exit 2 ;;
  esac
done

BACKEND_SVC="dma-insights-backend"
FRONTEND_SVC="dma-insights-frontend"
BACKEND_IMG="gcr.io/$PROJECT_ID/dma-insights-backend:$SHA"
FRONTEND_IMG="gcr.io/$PROJECT_ID/dma-insights-frontend:$SHA"

echo "→ Two-phase deploy"
echo "  PROJECT_ID  = $PROJECT_ID"
echo "  REGION      = $REGION"
echo "  IMAGE_SHA   = $SHA"

# ── Phase 0: pre-deploy parameter validation ──────────────────
echo ""
echo "==[ PHASE 0: parameter validation ]==="
bash "${SCRIPT_DIR}/preflight-parameters.sh"

# ── Phase 0.5: cloudbuild ↔ deploy-two-phase SHA contract check ────
# When SKIP_BUILD=true the operator is relying on images that Cloud
# Build already produced. Verify those tags actually exist for THIS
# SHA before we go further -- without this check, Phase 2 fails 5+
# minutes into the deploy with an opaque "image not found" error and
# the operator has to walk the chain backwards to figure out the
# `_IMAGE_SHA != SHA` mismatch. The check is cheap (one `gcloud
# container images describe` per image) and catches the recurring
# "I ran cloudbuild with X but deploy-two-phase defaulted to Y"
# foot-gun directly.
if [[ "$SKIP_BUILD" == "true" ]]; then
  echo ""
  echo "==[ PHASE 0.5: verify pre-built images exist for SHA=$SHA ]==="
  missing=()
  for img in dma-insights-backend dma-insights-frontend; do
    if gcloud container images describe \
         "gcr.io/${PROJECT_ID}/${img}:${SHA}" \
         --format='value(image_summary.digest)' >/dev/null 2>&1; then
      echo "  ✓ gcr.io/${PROJECT_ID}/${img}:${SHA} exists"
    else
      missing+=("${img}")
    fi
  done
  if [[ "${#missing[@]}" -gt 0 ]]; then
    echo "" >&2
    echo "✗ Cloud Build images do NOT exist for SHA=${SHA}:" >&2
    for m in "${missing[@]}"; do
      echo "    gcr.io/${PROJECT_ID}/${m}:${SHA}    [MISSING]" >&2
    done
    echo "" >&2
    echo "This is the cloudbuild ↔ deploy-two-phase SHA mismatch:" >&2
    echo "  - You ran cloudbuild with '--substitutions=_IMAGE_SHA=X' but" >&2
    echo "    here SHA defaulted to '\$(git rev-parse --short HEAD)' = ${SHA}." >&2
    echo "  - Or you ran cloudbuild on a different commit." >&2
    echo "" >&2
    echo "Fix one of:" >&2
    echo "  (a) Re-run cloudbuild with --substitutions=_IMAGE_SHA=${SHA}" >&2
    echo "      (matches the deploy SHA)" >&2
    echo "  (b) Re-run this script with SHA=<cloudbuild-sha> set:" >&2
    echo "      SHA=<cloudbuild-sha> bash ${BASH_SOURCE[0]} --skip-build" >&2
    echo "  (c) Drop --skip-build so Phase 1 rebuilds the images." >&2
    echo "" >&2
    exit 1
  fi
fi

# ── Phase 1: build images ─────────────────────────────────────
# Resilient to session/SSH disconnects. The build is submitted ASYNC and
# runs server-side on Cloud Build, so a dropped session never kills it.
# On (re-)run this:
#   1. short-circuits if images for SHA already exist (a prior run's
#      build finished) → straight to Phase 2,
#   2. else reattaches to an in-flight build for SHA (no resubmit),
#   3. else submits a fresh async build,
# then polls to completion. If the session drops mid-poll, just re-run
# the script: it reattaches (or skips, if done) instead of restarting
# the ~30-min build. This is what stops "reconnect resets the whole
# thing" — the long last stage (qa-gates) no longer has to survive the
# session, only the lightweight poll does.
if [[ "$SKIP_BUILD" != "true" ]]; then
  echo ""
  echo "==[ PHASE 1: build images via Cloud Build (async, reattach-safe) ]==="

  if gcloud container images describe "$BACKEND_IMG" --project="$PROJECT_ID" \
        --format='value(image_summary.digest)' >/dev/null 2>&1 \
     && gcloud container images describe "$FRONTEND_IMG" --project="$PROJECT_ID" \
        --format='value(image_summary.digest)' >/dev/null 2>&1; then
    echo "→ Images for SHA=$SHA already exist — skipping build (a prior run finished it)."
  else
    BUILD_ID="$(gcloud builds list --region "$REGION" --project "$PROJECT_ID" \
        --filter="substitutions._IMAGE_SHA=$SHA AND status=(QUEUED,WORKING)" \
        --format='value(id)' --limit=1 2>/dev/null | head -n1 || true)"
    if [[ -n "$BUILD_ID" ]]; then
      echo "→ Reattaching to in-flight build $BUILD_ID for SHA=$SHA (no resubmit)."
    else
      echo "→ Submitting async build for SHA=$SHA ..."
      # Thread a custom OAuth client id into the frontend bundle when set
      # (else the cloudbuild "" default + LoginPage fallback apply).
      SUBS="_IMAGE_SHA=$SHA"
      if [[ -n "${GOOGLE_OAUTH_CLIENT_ID:-}" ]]; then
        SUBS="${SUBS},_GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}"
      fi
      # --project explicit: gcloud does NOT read the PROJECT_ID env var,
      # and the poll below describes with --project "$PROJECT_ID" — an
      # active gcloud config pointing at another project would submit
      # there and poll here forever (2026-07-04 line audit).
      BUILD_ID="$(gcloud builds submit \
        --config "${SCRIPT_DIR}/cloudbuild.yaml" \
        --substitutions="$SUBS" \
        --region "$REGION" \
        --project "$PROJECT_ID" \
        --async --format='value(id)' \
        "${SCRIPT_DIR}/..")"
      echo "  build id: $BUILD_ID"
    fi
    echo "$BUILD_ID" > "/tmp/dma-deploy-build-${SHA}.id" 2>/dev/null || true
    echo "→ Polling build $BUILD_ID to completion."
    echo "  (Safe to disconnect — the build runs server-side. Re-run this"
    echo "   script to reattach; it will NOT restart the build.)"
    echo "  Live logs: gcloud builds log --stream $BUILD_ID --region $REGION"
    # A persistent describe failure (revoked creds, deleted build, API
    # outage) maps to UNKNOWN — cap consecutive UNKNOWNs so the deploy
    # can't hang forever printing '?' (2026-07-04 line audit).
    UNKNOWN_POLLS=0
    while :; do
      ST="$(gcloud builds describe "$BUILD_ID" --region "$REGION" \
            --project "$PROJECT_ID" --format='value(status)' 2>/dev/null || echo UNKNOWN)"
      case "$ST" in
        SUCCESS) echo "  ✓ build $BUILD_ID SUCCESS"; break ;;
        FAILURE|INTERNAL_ERROR|TIMEOUT|CANCELLED|EXPIRED)
          echo "" >&2
          echo "✗ build $BUILD_ID ended: $ST" >&2
          echo "  gcloud builds log $BUILD_ID --region $REGION   # full logs" >&2
          exit 1 ;;
        QUEUED|WORKING) UNKNOWN_POLLS=0; printf '.'; sleep 20 ;;
        *)
          UNKNOWN_POLLS=$((UNKNOWN_POLLS + 1))
          if [[ "$UNKNOWN_POLLS" -ge 30 ]]; then
            echo "" >&2
            echo "✗ build $BUILD_ID status UNKNOWN for 30 consecutive polls (~10 min)" >&2
            echo "  gcloud builds describe is failing persistently (credentials?" >&2
            echo "  wrong project? API outage). Nothing was promoted — investigate," >&2
            echo "  then re-run this script to reattach to the build." >&2
            exit 1
          fi
          printf '?'; sleep 20 ;;
      esac
    done
  fi
else
  echo "==[ PHASE 1: build skipped (--skip-build) ]==="
fi

# Confirm images exist before deploying.
echo "→ Verifying images landed at gcr.io"
for img in "$BACKEND_IMG" "$FRONTEND_IMG"; do
  if ! gcloud container images describe "$img" --project="$PROJECT_ID" --format=json >/dev/null 2>&1; then
    echo "FATAL: image $img missing from gcr.io. Build may have failed silently." >&2
    exit 1
  fi
  echo "  ✓ $img"
done

# ── Clay placeholder secrets when deferred ─────────────────────
# When DMA_CLAY_DEFERRED=1 (or both CLAY_WEBHOOK_* secrets are missing
# in Secret Manager), the Cloud Run service spec's secret_key_ref still
# points at `dma-insights-clay-webhook-{url,secret}` — those refs MUST
# resolve at deploy time or Phase 2 fails with "Secret … was not found".
# Auto-create empty-payload placeholders here so deferred deploys go
# through without operator intervention. ADR 0010's backend Clay client
# fail-closes on empty values, so empty == deferred semantically.
# When the operator later supplies real values via `gcloud secrets
# versions add ...`, Cloud Run's `latest` ref picks them up on the next
# revision roll.
for SECRET in dma-insights-clay-webhook-url dma-insights-clay-webhook-secret; do
  if ! gcloud secrets describe "$SECRET" --project="$PROJECT_ID" \
       >/dev/null 2>&1; then
    echo "  ℹ Creating $SECRET (empty placeholder — Clay deferred per ADR 0010)"
    gcloud secrets create "$SECRET" --replication-policy=automatic \
      --labels=deferred=true --project="$PROJECT_ID" >/dev/null
  fi
  # Ensure at least one version exists so secret_key_ref(version=latest)
  # resolves. `gcloud secrets versions add` rejects truly empty payloads,
  # so a single newline is the minimum-valid placeholder.
  if ! gcloud secrets versions list "$SECRET" --project="$PROJECT_ID" \
       --format='value(name)' 2>/dev/null | grep -q .; then
    printf '\n' | gcloud secrets versions add "$SECRET" --data-file=- \
      --project="$PROJECT_ID" >/dev/null
    echo "  ℹ Added empty initial version to $SECRET"
  fi
done

# ── Phase 1.6: pre-deploy password verify (avoids Phase 4 503 race) ───
# 2026-06 root-cause fix for the recurring sequence:
#   Phase 2 deploys NEW revision; Cloud Run reads `postgres-dsn:latest`
#           at REVISION CREATION time and caches it on every instance.
#   Phase 3 migrate.sh detects drift → recover-db-passwords.sh or
#           force-heal-db.sh fires → secret value rotates.
#   Phase 4 probes /readyz on the candidate revision → 503 because that
#           revision still holds the OLD pre-rotation secret value.
#
# Moving the verify+heal in front of Phase 2 means whichever secret
# value lands in the candidate revision is the same one the SQL user
# will accept. Phase 3 migrations stay (the heal runs --verify-only
# here; if drift is found we heal NOW, then Phase 2 picks up the
# stable secret).
#
# Skippable via --skip-db-verify (matches the existing --skip-migrate
# / --skip-build flag conventions) for image-only or roll-back deploys
# where the operator already knows the secret is stable.
if [[ "${SKIP_DB_VERIFY:-false}" != "true" ]]; then
  echo ""
  echo "==[ PHASE 1.6: pre-deploy DB liveness + password drift check ]==="
  # ── Step 1: Cloud SQL liveness + auto-restart if STOPPED ─────────
  # Running preflight-cloud-sql.sh first ensures the password verify
  # below has something to actually connect to. STOPPED instances
  # (idle-policy stop, maintenance) get auto-started; FAILED state
  # aborts the deploy before any traffic-cutover risk. Skippable via
  # SKIP_CLOUD_SQL_CHECK=true for environments where the operator
  # already verified instance state out-of-band.
  if [[ "${SKIP_CLOUD_SQL_CHECK:-false}" != "true" ]] \
     && [[ -x "${SCRIPT_DIR}/preflight-cloud-sql.sh" ]]; then
    if ! "${SCRIPT_DIR}/preflight-cloud-sql.sh"; then
      echo "FATAL: Cloud SQL instance is not RUNNABLE; aborting deploy." >&2
      echo "  OLD revision still serves 100% — no rollback needed." >&2
      exit 1
    fi
  fi

  # ── Step 1b: Redis reachability (runbook "preflight params/Cloud-SQL/
  # Redis"). preflight-redis.sh existed but had NO caller in the deploy
  # chain — only a scheme check ran, so a stopped/unreachable Memorystore
  # or wrong Upstash URL surfaced only AFTER traffic promotion
  # (2026-07-04 line audit). The script itself is verdict-aware: only a
  # definitively-wrong URL fails (Upstash unreachable / bad scheme);
  # Memorystore VPC-internal unreachability from the operator shell is a
  # warning, not a blocker. Skippable via SKIP_REDIS_CHECK=true.
  if [[ "${SKIP_REDIS_CHECK:-false}" != "true" ]] \
     && [[ -x "${SCRIPT_DIR}/preflight-redis.sh" ]]; then
    if ! "${SCRIPT_DIR}/preflight-redis.sh"; then
      echo "FATAL: Redis preflight failed (wrong/malformed REDIS_URL)." >&2
      echo "  OLD revision still serves 100% — no rollback needed." >&2
      echo "  Fix REDIS_URL (Secret Manager: dma-insights-redis-url) or" >&2
      echo "  set SKIP_REDIS_CHECK=true if verified out-of-band." >&2
      exit 1
    fi
  fi

  # ── Step 2: Secret-vs-SQL-user password drift verify+heal ───────
  if "${SCRIPT_DIR}/recover-db-passwords.sh" --verify-only >/dev/null 2>&1; then
    echo "  ✓ DB passwords stable; safe to deploy new revision"
  else
    echo "  ⚠ password drift detected BEFORE deploy — healing now"
    if "${SCRIPT_DIR}/recover-db-passwords.sh"; then
      echo "  ✓ recover-db-passwords.sh healed the drift"
    elif [[ -x "${SCRIPT_DIR}/force-heal-db.sh" ]]; then
      echo "  ⚠ recover-db-passwords.sh failed; falling back to force-heal-db.sh"
      # 2026-06-06 QA-7: pass --no-roll so the fallback heals credentials
      # WITHOUT rolling the backend service. The two-phase deploy's
      # whole point is `--no-traffic` candidate isolation; a mid-Phase-1.6
      # service revision-roll would create an extra revision outside the
      # candidate-tag flow and confuse the Phase 4 readyz probe (which
      # expects ONE candidate at the tagged URL, not two roll-driven
      # revisions). The heal's credential rotation is what we want;
      # the revision-roll side-effect is what we don't.
      if ! "${SCRIPT_DIR}/force-heal-db.sh" --no-roll; then
        echo "FATAL: both DB heal paths failed; aborting deploy BEFORE Phase 2." >&2
        echo "       OLD revision still serves 100% — no rollback needed." >&2
        echo "       Diagnose with:" >&2
        echo "         ${SCRIPT_DIR}/recover-db-passwords.sh --diagnose" >&2
        exit 1
      fi
      echo "  ✓ force-heal-db.sh healed the drift (no service revision rolled)"
    else
      echo "FATAL: heal failed and no force-heal-db.sh fallback; aborting." >&2
      exit 1
    fi
    # Give Cloud SQL + Secret Manager a beat to propagate the new
    # password before Phase 2 reads `postgres-dsn:latest`.
    echo "  → settling Cloud SQL + Secret Manager (5s)..."
    sleep 5
  fi
fi

# ── Phase 2: deploy new revision with --no-traffic ────────────
echo ""
echo "==[ PHASE 2: deploy backend revision with --no-traffic ]==="
NEW_REVISION_PREFIX="${BACKEND_SVC}-${SHA}-"
gcloud run services update "$BACKEND_SVC" \
  --image "$BACKEND_IMG" \
  --region "$REGION" \
  --no-traffic \
  --tag "candidate-${SHA}" \
  --project "$PROJECT_ID"
# Extract the actual new revision name (initial capture). Phase 4 also
# uses `_get_latest_candidate_revision` which re-fetches via the tag
# so log captures point at the LIVE candidate revision even after
# Cloud Run rolls the tag mid-Phase-4 (a real symptom seen during the
# 2026-06-06 password-drift cascade: Phase 4 emitted logs from the
# pre-roll revision while the post-roll revision was actually serving
# the failing /readyz probe).
NEW_REVISION="$(gcloud run revisions list \
  --service "$BACKEND_SVC" --region "$REGION" \
  --project "$PROJECT_ID" \
  --format='value(name)' \
  --limit 1)"
echo "  ✓ new revision: $NEW_REVISION (no traffic yet — 0% is INTENTIONAL"
echo "    at this phase; traffic flips to 100% in Phase 5 after Phase 4"
echo "    proves /readyz is green on the candidate revision. The OLD"
echo "    revision keeps serving 100% so users see zero downtime.)"

# 2026-06-06 audit fix (anti-pattern A): the prior implementation
# captured NEW_REVISION ONCE here and re-used it in every Phase 4
# log-capture step. If Cloud Run rolled the candidate-${SHA} tag mid-
# Phase-4 (e.g. because force-heal-db.sh forced a revision roll), the
# captured NEW_REVISION pointed at a STALE revision and operator log
# diagnostics showed the wrong revision's stderr -- masking the real
# root cause. This helper re-fetches the tag binding on EVERY call so
# log captures always reflect the live candidate.
_get_latest_candidate_revision() {
  gcloud run services describe "$BACKEND_SVC" \
    --region "$REGION" --project "$PROJECT_ID" \
    --format=json 2>/dev/null \
  | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for t in (data.get('status') or {}).get('traffic') or []:
    if t.get('tag') == 'candidate-${SHA}':
        print(t.get('revisionName') or '')
        sys.exit(0)
" 2>/dev/null || true
}

# ── Phase 3: run migrations against live DB ───────────────────
# Export SHA + PROJECT_ID so migrate.sh's image-pinning block can
# update dma-insights-migrations to the deploying SHA's image BEFORE
# `gcloud run jobs execute`. Without this, the migrations job runs
# whatever image terraform last applied — usually an older SHA whose
# post_migrate.py predates the GRANT chain the NEW backend's /readyz
# expects, and Phase 4 503s with `permission denied for table
# alembic_version` (the recurring 2026-06-06 symptom).
if [[ "$SKIP_MIGRATE" != "true" ]]; then
  echo ""
  echo "==[ PHASE 3: run migrations ]==="
  # DMA_MIGRATE_SKIP_VERIFY=1 skips migrate.sh's raw-TCP Cloud SQL drift
  # verify — needed on HTTPS-only operator shells (agent sandboxes) where the
  # raw-TCP probe can't reach Cloud SQL and false-detects drift. Default keeps
  # the verify; Phase 4's drift-retry and Phase 1.6 remain the heal owners.
  if ! SHA="$SHA" PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
       "${SCRIPT_DIR}/migrate.sh" ${DMA_MIGRATE_SKIP_VERIFY:+--skip-verify}; then
    echo "" >&2
    echo "✗ Migrations FAILED — the new revision exists but has NO traffic." >&2
    echo "  No rollback needed; the OLD revision is still serving 100%." >&2
    echo "  Delete the failed revision when ready:" >&2
    echo "    gcloud run revisions delete $NEW_REVISION --region=$REGION" >&2
    exit 3
  fi
  echo "✓ Migrations applied"
else
  echo "==[ PHASE 3: migrations skipped (--skip-migrate) ]==="
fi

# ── Phase 4: probe /readyz on the NEW revision via its tag URL ─
# A tagged revision gets a URL like
# https://candidate-SHA---dma-insights-backend-NNN-uc.a.run.app
echo ""
echo "==[ PHASE 4: probe new revision /readyz via tag URL ]==="
# gcloud's `--format=value(status.traffic[?tag='...'].url)` projection
# does NOT support JMESPath-style `[?…]` filters — only simple index +
# splat. The previous use silently returned an empty string on every
# Cloud Run release, which is why Phase 4 always blew up with
# "couldn't resolve tag URL for candidate-…". Two parallel resolution
# strategies (whichever wins first):
#   1. Use `--filter` (the supported way) + a JSON projection + jq.
#   2. Construct the deterministic Cloud Run tag URL from the service
#      URL — Cloud Run prefixes the tag with `{tag}---` in the same
#      domain. This works without any post-deploy API call and is
#      robust to gcloud projection-syntax churn.
SERVICE_URL="$(gcloud run services describe "$BACKEND_SVC" \
  --region "$REGION" --project "$PROJECT_ID" \
  --format='value(status.url)')"
if [[ -z "$SERVICE_URL" ]]; then
  echo "FATAL: couldn't describe service $BACKEND_SVC to derive tag URL" >&2
  exit 4
fi
# Substitute https:// → https://candidate-SHA--- to get the tag URL.
# Cloud Run's tag scheme always prefixes the tag + `---` to the host.
TAG_URL="${SERVICE_URL/https:\/\//https://candidate-${SHA}---}"
# Cross-check: confirm Cloud Run actually knows about this tag (so we
# fail fast if Phase 2's --tag never landed for some reason). Use
# `--format=json` + jq because the projection-filter syntax is broken.
if ! gcloud run services describe "$BACKEND_SVC" \
       --region "$REGION" --project "$PROJECT_ID" --format=json \
     | python3 -c "
import json, sys
data = json.load(sys.stdin)
tags = [t.get('tag') for t in (data.get('status') or {}).get('traffic') or []]
sys.exit(0 if 'candidate-${SHA}' in tags else 1)
"; then
  echo "FATAL: tag 'candidate-${SHA}' is not registered on the service." >&2
  echo "       Phase 2 likely failed silently; revision exists but no tag." >&2
  exit 4
fi
echo "  tag URL: $TAG_URL"
# 2026-06 mid-deploy self-heal contract:
#   attempts 1-2: pure probes with backoff (the candidate revision may
#                 just need warmup time)
#   attempt 3   : if still 503, run the FULL heal cycle:
#                   1. backup-before-heal.sh (snapshot before we touch
#                      anything)
#                   2. force-heal-db.sh (Secret-Manager-as-truth heal —
#                      bypasses terraform state, never blocks)
#                   3. re-roll the candidate revision with a fresh
#                      DMA_SECRET_ROLL env var bump so it re-reads
#                      `postgres-dsn:latest` from Secret Manager AND
#                      keeps the same tag (Cloud Run moves the
#                      candidate-${SHA} tag to the new revision)
#                 The revision-roll is the key — without it, the
#                 candidate from Phase 2 holds the pre-heal secret
#                 cached at revision creation and keeps 503'ing
#                 forever regardless of what we do to the DB.
#   attempts 4-5: probe the rolled revision
# OLD revision continues serving 100% throughout — zero traffic impact.
# Helper: probe /readyz and capture both the HTTP status AND the
# response body. The body is the actionable signal -- a 503 with
# detail="migration drift: db=023 code=026" routes to a different
# fix than a 503 with detail="db unavailable: InvalidPasswordError".
# Pre-2026-06-05 we discarded the body and the operator was blind.
_probe_readyz() {
  local url="$1"
  local timeout="${2:-30}"
  local tmp_body tmp_status
  tmp_body=$(mktemp /tmp/dma-readyz-body.XXXXXX)
  tmp_status=$(curl --silent --show-error --max-time "$timeout" \
                 --retry 2 --retry-all-errors \
                 -o "$tmp_body" -w '%{http_code}' \
                 "$url" 2>/dev/null) || true
  # On hard curl failure -w already emitted 000 INSIDE the substitution;
  # a `|| echo 000` here appended a SECOND line and mangled every
  # status log + the final FATAL diagnostic (2026-07-04 line audit).
  [[ "$tmp_status" =~ ^[0-9]{3}$ ]] || tmp_status="000"
  PROBE_STATUS="$tmp_status"
  PROBE_BODY="$(head -c 500 "$tmp_body" 2>/dev/null || true)"
  rm -f "$tmp_body"
}

# Helper: capture the last 80 log lines from the current candidate's
# Cloud Run revision so the operator sees container-startup errors.
# Resolves the freshest candidate revision dynamically -- Cloud Run
# moves the tag on every --update, so the revision name we computed
# in Phase 2 is stale once the heal-roll fires.
_capture_candidate_logs() {
  # Use the canonical fresh-fetch helper so this stays correct even
  # if Cloud Run rolls the candidate-${SHA} tag mid-Phase-4 (e.g. a
  # mid-deploy heal forced a revision roll).
  local current_candidate
  current_candidate="$(_get_latest_candidate_revision)"
  if [[ -z "$current_candidate" ]]; then
    echo "  ⚠ could not resolve current candidate revision" >&2
    return
  fi
  echo "  → candidate revision: $current_candidate" >&2
  echo "  → last 80 log lines from $current_candidate:" >&2
  gcloud beta run revisions logs read "$current_candidate" \
    --region="$REGION" --project="$PROJECT_ID" --limit=80 2>&1 \
    | sed 's/^/      /' >&2 || \
    echo "      (no logs returned -- container may not have started)" >&2
}

# Helper: re-trigger migrations when a 503 body indicates drift.
# Idempotent on already-migrated DB. Returns 0 on success / non-drift,
# 1 only when migrations failed.
_retry_migrate_on_drift() {
  if [[ "$PROBE_BODY" == *"migration drift"* ]] \
     || [[ "$PROBE_BODY" == *"migration check failed"* ]]; then
    echo "  ⚠ /readyz body indicates migration drift -- re-running migrate.sh" >&2
    if [[ -x "${SCRIPT_DIR}/migrate.sh" ]]; then
      # Pass SHA + PROJECT_ID + REGION explicitly so migrate.sh's
      # image-pin block fires here too -- otherwise the retry runs
      # the OLD migrations image and the same alembic_version 503
      # comes back on the next probe.
      if SHA="$SHA" PROJECT_ID="$PROJECT_ID" REGION="$REGION" \
         "${SCRIPT_DIR}/migrate.sh" --skip-verify; then
        echo "  ✓ migrate.sh succeeded; will probe again" >&2
        return 0
      else
        echo "  ✗ migrate.sh failed during mid-deploy retry" >&2
        return 1
      fi
    fi
  fi
  return 0
}

HEAL_FIRED=false
MIGRATE_RETRY_FIRED=false
PROBE_STATUS=000
PROBE_BODY=""
for attempt in 1 2 3 4 5 6; do
  # Per-attempt timeout escalates as the candidate cold-starts (Cloud
  # Run can take 60+ seconds on a low-RAM revision). Pre-fix 30s was
  # too tight for the post-roll revision -- it would 503 because the
  # uvicorn worker hadn't bound to :8080 yet.
  if [[ $attempt -le 2 ]]; then probe_timeout=30
  elif [[ $attempt -le 4 ]]; then probe_timeout=45
  else probe_timeout=60
  fi
  _probe_readyz "${TAG_URL}/readyz" "$probe_timeout"
  if [[ "$PROBE_STATUS" == "200" ]]; then
    echo "  ✓ /readyz green on attempt $attempt (status=200)"
    break
  fi
  echo "  attempt $attempt: status=$PROBE_STATUS body=${PROBE_BODY:-<empty>}"

  if [[ $attempt == 6 ]]; then
    echo "" >&2
    echo "FATAL: /readyz never returned 200 on the new revision." >&2
    echo "  Last response: status=$PROBE_STATUS body=$PROBE_BODY" >&2
    echo "  OLD revision still serves 100% traffic -- no rollback needed." >&2
    echo "" >&2
    echo "Diagnostic capture from the candidate revision:" >&2
    _capture_candidate_logs
    echo "" >&2
    echo "Common root causes for persistent 503:" >&2
    echo "  - body contains 'migration drift' -> re-run migrate.sh manually" >&2
    echo "  - body contains 'db unavailable' -> run ensure-db-ready.sh" >&2
    echo "  - body empty + 503 -> container crashed at startup (image bug)" >&2
    echo "  - body empty + 000 -> network timeout, retry from Cloud Shell" >&2
    echo "" >&2
    echo "Re-attempt this deploy with verbose probing:" >&2
    echo "  SHA=${SHA} bash ${SCRIPT_DIR}/deploy-two-phase.sh --skip-build" >&2
    exit 5
  fi

  # Mid-deploy self-heal: route by failure signal. Each branch fires at
  # most ONCE, in the attempt 3-4 window (not attempt==3 only): when the
  # drift-retry consumes attempt 3 with `continue`, the credential heal
  # must still be reachable at attempt 4 — the documented combined-cause
  # cascade (drift + password rotation, 2026-06-06) needs BOTH, and an
  # ==3 gate made them mutually exclusive (2026-07-04 line audit).
  # Attempts 3-4 with body indicating migration drift -> re-run migrate.sh
  if [[ $attempt -ge 3 && $attempt -le 4 ]] \
     && [[ "$MIGRATE_RETRY_FIRED" != "true" ]] \
     && ([[ "$PROBE_BODY" == *"migration drift"* ]] \
         || [[ "$PROBE_BODY" == *"migration check failed"* ]]); then
    MIGRATE_RETRY_FIRED=true
    if _retry_migrate_on_drift; then
      sleep 5
      continue
    fi
  fi

  # Attempts 3-4 with body indicating DB drift / no body at all -> full heal
  if [[ $attempt -ge 3 && $attempt -le 4 ]] && [[ "$HEAL_FIRED" != "true" ]]; then
    echo "  ⚠ /readyz failed 2× -- firing mid-deploy heal cycle"
    HEAL_FIRED=true
    if [[ -x "${SCRIPT_DIR}/backup-before-heal.sh" ]]; then
      BACKUP_TAG="phase4-heal-${SHA}-$(date +%s)" \
        "${SCRIPT_DIR}/backup-before-heal.sh" --skip-poll || \
        echo "  ⚠ pre-heal backup async-launch failed (continuing heal)" >&2
    fi
    if [[ -x "${SCRIPT_DIR}/force-heal-db.sh" ]]; then
      # 2026-06-06 QA-7: pass --no-roll so the heal repairs credentials
      # WITHOUT rolling the live backend service. THIS script issues
      # its own targeted candidate-revision roll below (with
      # --no-traffic --tag) -- the force-heal's roll would create a
      # competing live revision and break the candidate-isolation
      # contract of the two-phase deploy. The 503s the operator saw
      # during Phase 4 probing were the candidate URL serving a
      # stale revision because force-heal had quietly rolled a fresh
      # LIVE revision out from under it.
      if ! "${SCRIPT_DIR}/force-heal-db.sh" --no-roll; then
        echo "  ⚠ force-heal-db.sh failed in Phase 4 (continuing probe)" >&2
      else
        echo "  ✓ force-heal-db.sh healed credentials (no service roll); now rolling candidate revision"
      fi
    fi
    # Roll the candidate revision so it picks up the post-heal secret.
    # The --update-env-vars creates a new revision; the --tag flag
    # moves candidate-${SHA} to it so TAG_URL stays correct.
    if gcloud run services update "$BACKEND_SVC" \
         --no-traffic \
         --tag "candidate-${SHA}" \
         --update-env-vars="DMA_SECRET_ROLL=phase4-$(date +%s)" \
         --region "$REGION" \
         --project "$PROJECT_ID" >/dev/null 2>&1; then
      echo "  ✓ candidate revision rolled -- waiting 20s for cold-start before re-probe"
    else
      echo "  ⚠ candidate revision roll failed (continuing probe)" >&2
    fi
    # Cold-start budget: Cloud Run revisions need 15-45s after creation
    # before /readyz reliably serves 200. 8s pre-fix was too short.
    sleep 20
    continue
  fi
  # Standard backoff for attempts 1-2 + 4-5 (no heal applied here).
  sleep $((attempt * 4))
done

# ── Phase 5: promote traffic ───────────────────────────────────
echo ""
echo "==[ PHASE 5: promote traffic to new revision ]==="
# Promote the EXACT revision Phase 4 probed (the candidate-${SHA} tag
# holder), not --to-latest: a revision created between probe and promote
# by anything outside this script (concurrent terraform apply, another
# operator, a heal without --no-roll) would otherwise take 100% traffic
# UNPROBED — the race this script exists to close (2026-07-04 line
# audit). --to-latest remains only as a loud fallback when the tag
# lookup fails (promoting nothing at all would strand the deploy).
PROBED_REVISION="$(_get_latest_candidate_revision)"
if [[ -n "$PROBED_REVISION" ]]; then
  gcloud run services update-traffic "$BACKEND_SVC" \
    --to-revisions="${PROBED_REVISION}=100" \
    --region "$REGION" \
    --project "$PROJECT_ID"
  echo "  ✓ 100% traffic shifted to probed revision $PROBED_REVISION"
else
  echo "  ⚠ candidate-${SHA} tag lookup failed — falling back to --to-latest" >&2
  echo "    (the probed-revision binding is lost; verify Phase 7 output)" >&2
  gcloud run services update-traffic "$BACKEND_SVC" \
    --to-latest \
    --region "$REGION" \
    --project "$PROJECT_ID"
  echo "  ✓ 100% traffic shifted to LATEST"
fi

# NOTE: the full verify-deploy.sh run (backend + FRONTEND served-SHA
# checks) was MOVED to AFTER the frontend deploy below. It used to run
# here, BEFORE the frontend was rolled, so its Layer 1/2 frontend-image
# + HTML-stamp checks always saw the OLD frontend SHA, failed, and
# aborted the deploy — leaving the frontend permanently stuck on the
# prior image ("backend new, frontend old"). Verify now runs once BOTH
# services are on the new SHA.

# ── Phase 6: deploy the frontend (no migrations needed) ──
# The recurring "old website after deploy" symptom was rooted here.
# Pre-2026-06-05 Phase 7 was a single `gcloud run services update --image`
# which CREATES a new revision but does NOT auto-promote traffic when the
# prior state had a split (canary, interrupted rollout, etc.). The new
# image got built, the new revision got created, but traffic stayed on
# the old revision -- operator pulled + redeployed several times and
# kept seeing the old content because traffic was pinned to a stale
# revision the whole time.
#
# Fix: same pattern as backend Phase 2-5 -- create the revision, then
# explicitly promote to LATEST, then VERIFY the served HTML carries the
# expected x-build-sha stamp. Verification probes via curl so we
# discover edge-cache lag immediately and can re-prompt.
echo ""
echo "==[ PHASE 6: deploy frontend + verify served SHA ]==="

# 7a. Update the service to the new image.
gcloud run services update "$FRONTEND_SVC" \
  --image "$FRONTEND_IMG" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --quiet

# 7b. Explicitly promote traffic to LATEST. Idempotent when already
#     at 100% LATEST. Bypasses Cloud Run's default "auto-promote only
#     when prior state was 100% LATEST" rule which silently leaves
#     split-traffic states pinned.
echo "  → promoting frontend traffic to LATEST..."
gcloud run services update-traffic "$FRONTEND_SVC" \
  --to-latest \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --quiet >/dev/null

# 7c. Verify the served HTML carries the expected build-sha. Probes
#     via curl so we surface edge-cache lag + retry until propagated
#     or surface an actionable diagnostic.
FE_URL=$(gcloud run services describe "$FRONTEND_SVC" --region="$REGION" \
           --project="$PROJECT_ID" \
           --format='value(status.url)' 2>/dev/null || true)
if [[ -n "$FE_URL" ]]; then
  echo "  → verifying frontend serves SHA=$SHA at $FE_URL ..."
  verified=false
  for attempt in 1 2 3 4 5 6; do
    sleep $((attempt * 4))  # 4, 8, 12, 16, 20, 24s = 84s total
    served_sha=$(curl -s --max-time 10 "$FE_URL/" 2>/dev/null \
                  | grep -oE '<meta name="x-build-sha" content="[^"]+"' \
                  | head -1 | sed -E 's/.*content="([^"]+)".*/\1/' || true)
    if [[ "$served_sha" == "$SHA" ]]; then
      echo "  ✓ frontend serves SHA=$SHA (verified via <meta x-build-sha>)"
      verified=true
      break
    fi
    printf "  ⏳ attempt %d/6: served SHA=%s (waiting for edge propagation)\n" \
           "$attempt" "${served_sha:-MISSING}"
  done
  if ! $verified; then
    echo "" >&2
    echo "✗ frontend STILL not serving SHA=$SHA after 84s of polling." >&2
    echo "  Diagnostic:" >&2
    echo "    curl -s $FE_URL/ | grep -oE '<meta name=\"x-build-sha\" content=\"[^\"]+\"'" >&2
    echo "    gcloud run revisions list --service=$FRONTEND_SVC --region=$REGION" >&2
    echo "    gcloud run services describe $FRONTEND_SVC --region=$REGION \\" >&2
    echo "      --format='value(status.traffic[].revisionName,status.traffic[].percent)'" >&2
    echo "  Common causes:" >&2
    echo "    1. Cloud Run edge cache holds /index.html ~5 min; wait + re-check" >&2
    echo "    2. <meta x-build-sha> missing in served HTML = image pre-dates the" >&2
    echo "       SHA-stamping fix; rebuild without --skip-build" >&2
    echo "    3. Browser tab cached old HTML; operator must hard-refresh" >&2
    echo "       (Cmd+Shift+R / Ctrl+Shift+R) or open in incognito" >&2
    exit 7
  fi
else
  echo "  ⚠ Frontend service has no status.url — promotion succeeded but verification skipped"
fi

# ── Phase 7: post-promotion verify against service URL ────────
# Runs AFTER both backend (Phase 5) and frontend (Phase 6) are promoted
# to the new SHA, so verify-deploy.sh's frontend image + HTML-stamp
# (Layer 1/2) and backend liveness (Layer 4) checks all see the fresh
# build. (Previously this ran before the frontend deploy and always
# failed on the stale frontend SHA.)
echo ""
echo "==[ PHASE 7: verify-deploy on service URL ]==="
if [[ -x "${SCRIPT_DIR}/verify-deploy.sh" ]]; then
  # SHA passed EXPLICITLY (like Phases 3 + 8): without it verify-deploy
  # self-resolves to the deploy-branch TIP, so a pinned/rollback deploy
  # (SHA=X DEPLOY_ALLOW_STALE=1) always failed here AFTER promotion, and
  # a commit pushed mid-build false-failed a healthy deploy (2026-07-04
  # line audit).
  if ! SHA="$SHA" "${SCRIPT_DIR}/verify-deploy.sh"; then
    echo "" >&2
    echo "✗ verify-deploy.sh reported the live revision unhealthy." >&2
    echo "  Rollback: " >&2
    PRIOR="$(gcloud run revisions list --service="$BACKEND_SVC" \
      --region="$REGION" --project="$PROJECT_ID" \
      --format='value(name)' --limit=2 | tail -1)"
    echo "    gcloud run services update-traffic $BACKEND_SVC \\" >&2
    echo "      --to-revisions=$PRIOR=100 --region=$REGION" >&2
    exit 6
  fi
fi

# ── Phase 8: post-deploy refresh (promote traffic + delta backfill) ──
# Operator complaint loop ("logs picking wrong evidence + subcap counts
# after deploy") is closed here: this phase
#   (a) confirms 100% traffic on LATEST for both services (idempotent
#       when Phase 5 already did it);
#   (b) triggers drive_crawler/embedder/intelligence_recompute in DELTA
#       mode so any NEW DMA reports uploaded between scheduled crawls
#       are ingested + embedded + rolled into intelligence profiles
#       before the operator hits the app.
# Persisted reports that haven't changed keep their cached narratives
# (no cache invalidation by default — that's an opt-in flag on the
# refresh script).
echo ""
echo "==[ PHASE 8: post-deploy refresh — promote traffic + delta backfill ]==="
if [[ "$SKIP_REFRESH" == "true" ]]; then
  echo "  ⏭ refresh skipped (--skip-refresh)"
elif [[ -x "${SCRIPT_DIR}/post-deploy-refresh.sh" ]]; then
  REFRESH_ARGS=()
  [[ "$INVALIDATE_CACHE" == "true" ]] && REFRESH_ARGS+=("--invalidate-cache")
  # ${arr[@]+"${arr[@]}"}: an EMPTY array under set -u is an "unbound
  # variable" abort on bash < 4.4 (macOS /bin/bash) — which would kill
  # the script AFTER both services are live, skipping the refresh + the
  # success summary (2026-07-04 line audit).
  if ! SHA="${SHA}" "${SCRIPT_DIR}/post-deploy-refresh.sh" \
       ${REFRESH_ARGS[@]+"${REFRESH_ARGS[@]}"}; then
    echo "" >&2
    echo "⚠ post-deploy-refresh.sh exited non-zero (continuing — backend +" >&2
    echo "  frontend are LIVE at SHA=$SHA; refresh is best-effort)." >&2
    echo "  Re-run manually:" >&2
    echo "    SHA=${SHA} ${SCRIPT_DIR}/post-deploy-refresh.sh ${REFRESH_ARGS[*]}" >&2
  fi
else
  echo "  ⚠ post-deploy-refresh.sh not found; skipping refresh"
fi

echo ""
echo "✓ Two-phase deploy SUCCEEDED at SHA=$SHA"
echo "  - backend revision: $NEW_REVISION (100% traffic)"
echo "  - frontend updated to latest"
echo "  - migrations applied + verify-deploy green"
echo "  - post-deploy refresh: traffic promoted + delta backfill triggered"
