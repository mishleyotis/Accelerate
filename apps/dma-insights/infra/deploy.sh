#!/usr/bin/env bash
# apps/dma-insights/infra/deploy.sh
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  ERROR HISTORY — keep this list in sync with new failure modes.      ║
# ║  Per the operator mandate: every recurring error gets logged here    ║
# ║  + the fix that neutralized it, so future revisions can't regress.   ║
# ╠══════════════════════════════════════════════════════════════════════╣
# ║  E1  IPv6 routing failures from Cloud Shell                          ║
# ║      → 'dial tcp [2a00:…]:443: cannot assign requested address'      ║
# ║      FIX: kernel-level IPv6 disable via sudo sysctl (L1) +           ║
# ║           GODEBUG=netdns=go (L2) + escalating-parallelism retry (L4) ║
# ║                                                                      ║
# ║  E2  'Image not found' during terraform apply                        ║
# ║      → operator ran ./deploy.sh assuming it built; it only applied   ║
# ║      FIX: PHASE 1 below — auto-build via gcloud builds submit when   ║
# ║           gcr.io is missing any of the 3 images at $SHA              ║
# ║                                                                      ║
# ║  E3  'Stale frontend' / 'fix appears not applied'                    ║
# ║      → live revision still served old container image                ║
# ║      FIX: PHASE 3 verifier — gcloud run services describe asserts    ║
# ║           image tag == $SHA on both backend + frontend; exit 3 with  ║
# ║           the force-promote command on drift                         ║
# ║                                                                      ║
# ║  E4  Browser cached old .jsx after redeploy                          ║
# ║      → nginx had no Cache-Control headers                            ║
# ║      FIX: frontend-nginx.template now sends no-cache + Dockerfile    ║
# ║           stamps ?v=$SHA on every script URL (URL-level cache-bust)  ║
# ║           — PHASE 3 verifier curls for both                          ║
# ║                                                                      ║
# ║  E5  ./deploy.sh prompted for project_id, operator typed 'latest'    ║
# ║      → terraform tried to manage a GCP project named 'latest'        ║
# ║      FIX: terraform.tfvars commits project_id default; validation    ║
# ║           rule on the variable rejects non-project-ID strings        ║
# ║                                                                      ║
# ║  E6  Postgres password drift after key rotation                      ║
# ║      → secret vs SQL user passwords desync                           ║
# ║      FIX: pre-flight verify via recover-db-passwords.sh; failure     ║
# ║           branch above offers --rotate or heal escape hatches        ║
# ║                                                                      ║
# ║  E7  Cloud Shell pwd != repo root → relative cd fails                ║
# ║      FIX: SCRIPT_DIR + REPO_ROOT derived via $(cd "$(dirname …)")    ║
# ║           pattern so every reference is absolute                     ║
# ║                                                                      ║
# ║  E8  Terraform state lock from interrupted prior run                 ║
# ║      → 'Error acquiring the state lock'                              ║
# ║      FIX: classify lock-error branch + emit force-unlock command     ║
# ║                                                                      ║
# ║  E9  alembic_version VARCHAR(32) truncation on revision IDs > 32 ch  ║
# ║      → 'StringDataRightTruncation' during migrate.sh                 ║
# ║      FIX: NOT this script — see env.py widener + test_migration_id_  ║
# ║           lengths.py CI guard + migrate.sh diagnostic                ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Resilient deploy wrapper for DMA Insights on Cloud Shell.
#
# Defense layers (most-reliable first):
#   1. Kernel-level IPv6 disable via sysctl (needs sudo, available in Cloud Shell)
#   2. GODEBUG=netdns=go to force Go's pure-Go resolver
#   3. terraform init -reconfigure to handle fresh checkouts + backend changes
#   4. Escalating-parallelism retry (10 → 4 → 2 → 1) so flaky-network failures
#      shrink the blast radius on each attempt
#   5. Error-pattern detection that aborts fast on un-retryable errors
#      (missing image, state lock) instead of burning 4 attempts on hopeless cases
#
# Usage:
#   ./deploy.sh                       # build images + terraform apply + verify (DEFAULT)
#   ./deploy.sh --skip-build          # apply existing image only (faster, prior SHA must exist)
#   ./deploy.sh --skip-verify         # skip post-deploy live-revision check
#   SHA=abc1234 ./deploy.sh           # pin a specific image SHA
#   PROJECT_ID=my-proj ./deploy.sh    # override the project
#   PARALLELISM_OVERRIDE=1 ./deploy.sh # force serial apply (slowest, safest)
#
# As of 2026-05-24 this script BUILDS IMAGES FIRST by default. The prior
# version only ran `terraform apply` — operators kept seeing "stale
# frontend" because they assumed `./deploy.sh` triggered cloudbuild, but
# it only applied whatever image already existed at the SHA. State
# branches for the build step:
#
#   already_built  → gcr.io already has all 3 images at $SHA; skip build
#   needs_build    → gcloud builds submit; ~4 min for backend+frontend+worker
#   build_failed   → exit 2 with the build URL (operator inspects logs)
#   skip_build     → operator passed --skip-build; require existing images
set -euo pipefail

BUILD_MODE="auto"
VERIFY_MODE="auto"
MIGRATE_MODE="auto"
REFRESH_MODE="run"      # post-deploy-refresh.sh by default — fixes the
                        # recurring "wrong evidence + subcap counts" / "old
                        # revision still serving" symptoms. Operator opts
                        # out with --skip-refresh for fast local iteration.
INVALIDATE_CACHE="skip" # opt-in via --invalidate-cache: sets
                        # vertex_synthesis_cache.invalidated_at on every
                        # row created before THIS deploy so the next read
                        # re-synthesizes against the freshly-deployed code.
                        # Costs Vertex tokens on next read per surface.
for arg in "$@"; do
  case "$arg" in
    --skip-build)        BUILD_MODE="skip" ;;
    --skip-verify)       VERIFY_MODE="skip" ;;
    --migrate)           MIGRATE_MODE="run" ;;       # run migrate.sh after a successful deploy
    --skip-migrate)      MIGRATE_MODE="skip" ;;      # explicit override of auto-detect
    --skip-refresh)      REFRESH_MODE="skip" ;;      # skip post-deploy traffic-promote + backfill
    --invalidate-cache)  INVALIDATE_CACHE="run" ;;   # also invalidate synthesis-cache
    --help|-h)
      sed -n '1,80p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

# Auto-detect whether migrations are needed.
#
# 2026-05-28 audit fix (E): the previous heuristic walked
# `git diff HEAD~5..HEAD` which:
#   1. Misses migrations outside the last 5 commits (a re-deploy of an
#      older revision)
#   2. Fails on shallow CI clones (diff returns nothing -> false skip)
#
# New approach: ask the live DB for its current alembic head, compare
# to the disk head. If they differ, migrations are pending and we run.
# This is the SAFE direction: even a re-deploy of a 6-month-old SHA
# correctly detects pending migrations against today's DB state.
#
# Fallback: if we can't query the DB (no DSN available at this stage),
# fall back to git-diff with a tunable window (default 30 commits, vs
# 5 previously) so re-deploys of recent SHAs still work.
#
# State branches:
#   --migrate         → always run
#   --skip-migrate    → never run
#   auto + db-head != disk-head → run
#   auto + db-head == disk-head → skip
#   auto + db unreachable + git diff has alembic → run
#   auto + db unreachable + git diff clean → skip with warn
if [[ "$MIGRATE_MODE" == "auto" ]]; then
  DISK_HEAD="$(
    cd "$(git rev-parse --show-toplevel)/apps/dma-insights/backend" \
      && ls alembic/versions/*.py 2>/dev/null \
      | sort \
      | tail -1 \
      | xargs -I {} basename {} .py \
      || true
  )"
  if [[ -n "${DATABASE_URL_SYNC:-}" ]]; then
    DB_HEAD="$(
      cd "$(git rev-parse --show-toplevel)/apps/dma-insights/backend" \
        && alembic current 2>/dev/null \
        | awk '/\(head\)/{print $1; exit} {sub(/\s+/," "); print $NF}' \
        | head -1 \
        || true
    )"
    if [[ -n "$DB_HEAD" && "$DB_HEAD" != "$DISK_HEAD" ]]; then
      MIGRATE_MODE="run"
      echo "  → DB head ($DB_HEAD) != disk head ($DISK_HEAD); will run migrate.sh"
    else
      MIGRATE_MODE="skip"
      echo "  → DB head matches disk head ($DISK_HEAD); skipping migrate.sh"
    fi
  else
    # Fallback: git diff over a wider window. The 30-commit window
    # covers the typical 2-week deploy cycle without re-running every
    # deploy.
    if git -C "$(git rev-parse --show-toplevel)" diff --name-only HEAD~30..HEAD 2>/dev/null \
         | grep -q '^apps/dma-insights/backend/alembic/versions/'; then
      MIGRATE_MODE="run"
      echo "  → auto-detected alembic migrations in the last 30 commits (no DB DSN to query); will run migrate.sh"
    else
      MIGRATE_MODE="skip"
      echo "  → no DB DSN to query AND no alembic changes in last 30 commits; skipping migrate.sh (use --migrate to force)"
    fi
  fi
fi

# ── Defense layer 1: kernel-level IPv6 disable ───────────────────────────────
# Cloud Shell's IPv6 routing pool is unreliable. `GODEBUG=netdns=go` only
# changes the resolver; Go's Happy Eyeballs algorithm can still pick an
# IPv6 address it can't reach. The most reliable fix is to disable IPv6
# at the kernel level so the resolver can't even consider it.
disable_ipv6_at_kernel() {
  if ! command -v sudo >/dev/null 2>&1; then
    echo "  → sudo not installed; skipping kernel IPv6 disable"
    return
  fi
  # Try non-interactive sudo first; Cloud Shell typically allows it.
  if ! sudo -n true 2>/dev/null; then
    echo "  → sudo requires a password (interactive); skipping kernel IPv6 disable"
    echo "    If retries fail with IPv6 errors, run once:  sudo true"
    echo "    then re-run ./deploy.sh."
    return
  fi
  echo "  → disabling IPv6 at kernel level (sysctl)"
  # `|| true` so a single sysctl failure doesn't abort the whole script;
  # the GODEBUG fallback (layer 2) still helps.
  sudo sysctl -w net.ipv6.conf.all.disable_ipv6=1 >/dev/null 2>&1 || true
  sudo sysctl -w net.ipv6.conf.default.disable_ipv6=1 >/dev/null 2>&1 || true
  sudo sysctl -w net.ipv6.conf.lo.disable_ipv6=1 >/dev/null 2>&1 || true
  # Verify it took.
  if [[ "$(cat /proc/sys/net/ipv6/conf/all/disable_ipv6 2>/dev/null || echo 0)" == "1" ]]; then
    echo "  ✓ IPv6 disabled (kernel reports disable_ipv6=1)"
  else
    echo "  ⚠ sysctl returned OK but disable_ipv6 still reads 0 — falling back to GODEBUG only"
  fi
}

# ── Defense layer 2: Go resolver (always set, belt-and-suspenders) ───────────
export GODEBUG=netdns=go

# ── Resolve variables ────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# Default the image tag to the NEWEST commit on the deploy branch
# (resolve-deploy-sha.sh fetches origin + syncs the tree), so a stale/wrong
# checkout can't ship an old image (the bde8329 incident). Explicit `SHA=X`
# still overrides, but is guarded against staleness just below.
SHA_WAS_EXPLICIT=false
[[ -n "${SHA:-}" ]] && SHA_WAS_EXPLICIT=true
if [[ "$SHA_WAS_EXPLICIT" == false ]]; then
  SHA="$(bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null || (git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || true) | cut -c1-7)"
fi
if [[ "$SHA_WAS_EXPLICIT" == true && "${DEPLOY_ALLOW_STALE:-}" != "1" ]]; then
  NEWEST="$(NO_SYNC=1 bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null || true)"
  if [[ -n "$NEWEST" && "$NEWEST" != "$SHA" ]] \
     && git -C "${REPO_ROOT}" merge-base --is-ancestor "$SHA" "$NEWEST" 2>/dev/null; then
    echo "ERROR: SHA='${SHA}' is STALE (behind the newest deploy-branch tip ${NEWEST})." >&2
    echo "  Re-run with SHA unset to deploy newest, or DEPLOY_ALLOW_STALE=1 to roll back." >&2
    exit 1
  fi
fi

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: Cannot determine PROJECT_ID." >&2
  echo "  Fix: gcloud config set project digital-maturity-assessor" >&2
  exit 1
fi

if [[ -z "${SHA}" ]]; then
  echo "ERROR: Cannot determine git SHA. Are you inside the Accelerate repo?" >&2
  exit 1
fi

# Reject obvious typos before they reach Terraform (`latest`, branch names, etc.)
if ! echo "${SHA}" | grep -qE '^[0-9a-f]{7,40}$'; then
  echo "ERROR: SHA '${SHA}' does not look like a git commit SHA." >&2
  echo "  Get the correct value with: git rev-parse --short HEAD" >&2
  exit 1
fi

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  DMA Insights — Terraform Apply          ║"
echo "╠══════════════════════════════════════════╣"
printf "║  Project : %-30s║\n" "${PROJECT_ID}"
printf "║  SHA     : %-30s║\n" "${SHA}"
echo "╚══════════════════════════════════════════╝"
echo ""

# Apply IPv6 disable BEFORE init so even the init network calls benefit.
disable_ipv6_at_kernel
echo ""

# ── Build images (default) ───────────────────────────────────────────────────
# Check whether all 3 images already exist at $SHA; if so skip the build.
# Otherwise run cloudbuild + push. State branches:
#   already_built → 3 images present → SKIP
#   needs_build   → 0-2 present       → BUILD
#   skip_build    → --skip-build flag → SKIP + require 3 present (fail fast)
images_present_count() {
  local count=0
  for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
    if gcloud container images list-tags "gcr.io/${PROJECT_ID}/${img}" \
         --filter="tags:${SHA}" --format='value(tags)' --limit=1 2>/dev/null \
         | grep -q .; then
      count=$((count + 1))
    fi
  done
  echo "$count"
}

if [[ "$BUILD_MODE" == "skip" ]]; then
  present=$(images_present_count)
  echo "→ --skip-build: $present/3 images present at SHA=${SHA}"
  if [[ "$present" != "3" ]]; then
    echo "✗ --skip-build requires all 3 images already present at SHA=${SHA}." >&2
    echo "  Found $present/3. Run without --skip-build to build them now." >&2
    exit 2
  fi
else
  present=$(images_present_count)
  if [[ "$present" == "3" ]]; then
    echo "→ All 3 images already present at SHA=${SHA}; skipping build."
  else
    echo "→ Building 3 images at SHA=${SHA} (found $present/3 pre-existing)..."
    BUILD_DIR="${REPO_ROOT}/apps/dma-insights"
    if ! gcloud builds submit "$BUILD_DIR" \
           --config "$BUILD_DIR/infra/cloudbuild.yaml" \
           --substitutions="_IMAGE_SHA=${SHA}" \
           --timeout=30m; then
      echo "" >&2
      echo "✗ cloudbuild failed at SHA=${SHA}. Inspect the build:" >&2
      echo "  gcloud builds list --limit=1 --filter='substitutions._IMAGE_SHA=${SHA}'" >&2
      exit 2
    fi
    # Sanity-check post-build
    present=$(images_present_count)
    if [[ "$present" != "3" ]]; then
      echo "✗ Build reported success but only $present/3 images present." >&2
      echo "  This means cloudbuild.yaml has a stage that doesn't actually push." >&2
      exit 2
    fi
    echo "✓ All 3 images built + pushed at SHA=${SHA}"
  fi
fi
echo ""

cd "${SCRIPT_DIR}/terraform"

# ── Initialize the GCS backend (idempotent) ──────────────────────────────────
echo "→ terraform init (backend=gcs bucket=${PROJECT_ID}-tfstate)"
if ! terraform init \
      -reconfigure \
      -backend-config="bucket=${PROJECT_ID}-tfstate" \
      -input=false; then
  cat <<EOF >&2

✗ terraform init failed. Most likely causes:
  1. The state bucket gs://${PROJECT_ID}-tfstate doesn't exist. Create it:
       gcloud storage buckets create gs://${PROJECT_ID}-tfstate \\
         --location=${REGION} --uniform-bucket-level-access
       gcloud storage buckets update gs://${PROJECT_ID}-tfstate --versioning
  2. Your account lacks roles/storage.objectAdmin on the bucket.
  3. Wrong project active. Verify: gcloud config get-value project
EOF
  exit 1
fi
echo "✓ terraform init complete"
echo ""

# ── Defense layer 4: escalating-parallelism retry strategy ───────────────────
# Each attempt reduces concurrent API calls. Cloud Shell's flaky IPv6 routing
# means N concurrent requests yields ~N independent chances to hit a bad
# v6 endpoint — serialising shrinks the failure surface monotonically.
#
# Attempt 1: parallelism=10 (Terraform default) — fast path when network is healthy
# Attempt 2: parallelism=4  — moderate concurrency, fewer races
# Attempt 3: parallelism=2  — near-serial, very reliable
# Attempt 4: parallelism=1  — fully serialised last resort
#
# Override via PARALLELISM_OVERRIDE=N to pin a single parallelism across
# all attempts (useful when you know IPv6 is broken and want to skip the
# fast-but-unreliable first attempts).
if [[ -n "${PARALLELISM_OVERRIDE:-}" ]]; then
  declare -a PARALLELISMS=("${PARALLELISM_OVERRIDE}" "${PARALLELISM_OVERRIDE}" "${PARALLELISM_OVERRIDE}" "${PARALLELISM_OVERRIDE}")
else
  declare -a PARALLELISMS=(10 4 2 1)
fi
declare -a WAITS=(2 4 8 16)

LAST_ERROR_KIND="unknown"
MAX_ATTEMPTS="${#PARALLELISMS[@]}"

for ((idx = 0; idx < MAX_ATTEMPTS; idx++)); do
  attempt=$((idx + 1))
  parallelism="${PARALLELISMS[$idx]}"
  wait_sec="${WAITS[$idx]}"

  echo ""
  echo "→ Attempt ${attempt}/${MAX_ATTEMPTS} (parallelism=${parallelism})"

  # Tee stderr to a tmp file so we can post-mortem-classify the error
  # without losing the live console output the operator sees.
  ERR_FILE="$(mktemp /tmp/dma-deploy-err.XXXXXX)"
  set +e
  terraform apply \
      -var "project_id=${PROJECT_ID}" \
      -var "image_sha=${SHA}" \
      -parallelism="${parallelism}" \
      -auto-approve \
      2> >(tee "$ERR_FILE" >&2)
  rc=$?
  set -e

  if [[ $rc -eq 0 ]]; then
    rm -f "$ERR_FILE"
    echo ""
    echo "✓ terraform apply succeeded on attempt ${attempt}/${MAX_ATTEMPTS} (parallelism=${parallelism})"

    # ── Post-deploy verification: live revision actually serves the new SHA
    # State branches:
    #   live_matches_sha           → green, fresh frontend confirmed
    #   live_lags_sha              → red, Cloud Run rolled the new revision but
    #                                serving traffic still on old (warn the
    #                                operator + tell them how to force-promote)
    #   cache_headers_missing      → frontend not yet revised with the no-cache
    #                                nginx config (older image still mounted)
    #   service_unreachable        → 5xx — backend probably mid-roll
    #   gcloud_unavailable         → skip verification (e.g. CI without auth)
    if [[ "$VERIFY_MODE" == "skip" ]]; then
      echo "→ --skip-verify: skipping post-deploy live-revision check"
      exit 0
    fi
    echo ""
    echo "→ Verifying live Cloud Run revisions match SHA=${SHA}..."
    if ! command -v gcloud >/dev/null 2>&1; then
      echo "  ⚠ gcloud not on PATH; skipping verification"
      exit 0
    fi
    drift=0
    for svc in dma-insights-backend dma-insights-frontend; do
      live_image=$(gcloud run services describe "$svc" --region="$REGION" \
        --format='value(spec.template.spec.containers[0].image)' 2>/dev/null || true)
      live_sha="${live_image##*:}"
      if [[ "$live_sha" == "$SHA" ]]; then
        printf "  ✓ %-30s revision serving SHA=%s\n" "$svc" "$live_sha"
      else
        printf "  ✗ %-30s revision serving SHA=%s (expected %s)\n" "$svc" "${live_sha:-none}" "$SHA"
        drift=$((drift + 1))
      fi
    done

    # Cache-control header check on a JSX file — proves the new nginx
    # config is in effect (no more browser cache surprises).
    fe_url=$(gcloud run services describe dma-insights-frontend \
      --region="$REGION" --format='value(status.url)' 2>/dev/null || true)
    if [[ -n "$fe_url" ]]; then
      hdr=$(curl -sI "$fe_url/src/app-root.jsx" 2>/dev/null \
              | tr -d '\r' | grep -i '^cache-control:' || true)
      if echo "$hdr" | grep -qi 'no-cache'; then
        echo "  ✓ Frontend serves Cache-Control: no-cache on .jsx files"
      else
        echo "  ⚠ Frontend missing no-cache headers on .jsx (got: ${hdr:-<none>})"
        echo "    → operator browsers will cache old JSX; ask users to hard-refresh once"
      fi

      # Build-SHA stamping check — proves the live HTML was actually
      # built from THIS commit, not a cached prior revision. The
      # Dockerfile injects <meta name="x-build-sha" content="${SHA}">
      # at build time; if curl can read it back, the live HTML is fresh.
      # State branches:
      #   meta_matches_sha    → the live HTML is definitely the new build
      #   meta_lags_sha       → live HTML is from a prior image; force-promote
      #   meta_missing        → image predates the SHA-stamping fix; rebuild
      live_sha=$(curl -s "$fe_url/" 2>/dev/null \
        | grep -oE '<meta name="x-build-sha" content="[^"]+"' \
        | head -1 | sed -E 's/.*content="([^"]+)".*/\1/' || true)
      if [[ -z "$live_sha" ]]; then
        echo "  ⚠ Live HTML lacks <meta name='x-build-sha'> — image was"
        echo "    built before the SHA-stamping fix landed. Re-run:"
        echo "      ./deploy.sh    (will rebuild + stamp)"
      elif [[ "$live_sha" == "$SHA" ]]; then
        echo "  ✓ Live HTML stamped with build SHA=$SHA (fresh)"
      else
        echo "  ✗ Live HTML stamped with build SHA=$live_sha (expected $SHA)"
        drift=$((drift + 1))
      fi
    fi

    if [[ "$drift" -gt 0 ]]; then
      cat <<EOF >&2

✗ ${drift} Cloud Run service(s) still serving an old SHA after apply.
  Force a 100% traffic split to the latest revision:

    for svc in dma-insights-backend dma-insights-frontend; do
      gcloud run services update-traffic "\$svc" \\
        --region=${REGION} --to-latest
    done

  Then re-run with --skip-build --skip-verify to skip the build/verify
  loop, OR just re-run plain ./deploy.sh (it will short-circuit the
  build if images are already present at the target SHA).
EOF
      exit 3
    fi
    echo ""
    # 2026-05-28 audit fix (F-304): the success message used to print
    # here BEFORE migrations ran. The previous order (apply → print
    # "fully live" → migrate) meant the new backend image was already
    # serving traffic against the OLD schema during the migration
    # window. Now we run migrations + verify-deploy FIRST, then
    # surface success only if both pass.
    #
    # KNOWN P1 DEFERRAL: Terraform's google_cloud_run_v2_service
    # promotes traffic on apply (no --no-traffic equivalent today).
    # The deploy.sh flow still has a window where traffic has shifted
    # but migrations haven't run -- bounded to a few seconds for the
    # gcloud calls below + migrate.sh runtime (~10-60s typically).
    # Per DEPLOYMENT.md §11 the proper fix is two-phase deploy with
    # explicit --to-revisions traffic management; tracked as F-NN.

    # ── Chained migration run (opt-in via --migrate or auto-detected) ────────
    # State branches:
    #   migrate_run     → invoke ./migrate.sh; pass through its exit
    #   migrate_skip    → no schema changes detected → no-op
    #   migrate_failed  → bubble up exit 4 with the diagnostic
    if [[ "$MIGRATE_MODE" == "run" ]]; then
      echo ""
      echo "→ Running database migrations (./migrate.sh)…"
      if ! "${SCRIPT_DIR}/migrate.sh"; then
        echo "" >&2
        echo "✗ Migrations failed AFTER traffic shifted to new image." >&2
        echo "  ROLLBACK IMMEDIATELY: gcloud run services update-traffic" >&2
        echo "  dma-insights-backend --to-revisions=\$PRIOR_REVISION=100" >&2
        echo "  See DEPLOYMENT.md §19 T14 for VARCHAR(32) truncation rescue." >&2
        exit 4
      fi
      echo "✓ Migrations applied"
    fi

    # ── Post-migration readiness verification ──────────────────────────
    # Calls verify-deploy.sh to confirm /readyz reports green at the
    # current alembic head + the backend can reach Cloud SQL + the
    # frontend artifact carries the deployed build SHA. Non-zero exit
    # surfaces as deploy failure even though traffic has shifted --
    # operator must roll back manually.
    if [[ -x "${SCRIPT_DIR}/verify-deploy.sh" ]]; then
      echo ""
      echo "→ Running post-deploy verification (./verify-deploy.sh)…"
      if ! "${SCRIPT_DIR}/verify-deploy.sh"; then
        echo "" >&2
        echo "✗ verify-deploy.sh reported the live revision unhealthy" >&2
        echo "  AFTER traffic shifted. ROLLBACK or investigate /readyz" >&2
        echo "  + Cloud Logging. See DEPLOYMENT.md §52.6." >&2
        exit 5
      fi
      echo "✓ Post-deploy verification passed"
    fi

    # ── Post-deploy refresh: promote traffic + fire backfill for NEW data ───
    # Fixes the recurring operator complaint: "logs picking wrong evidence +
    # subcap counts after deploy".
    #
    # CONTRACT: this step REFRESHES (picks up new data, promotes traffic);
    # it does NOT discard prior work. Specifically:
    #   - Persisted DMA reports that haven't changed since the prior run
    #     KEEP their cached narratives -- no re-synthesis cost.
    #   - drive_crawler runs in --delta mode: only NEW Drive folders or
    #     folders with newer drive_modified_time are re-parsed; unchanged
    #     reports are skipped.
    #   - embedder runs in --delta mode: only embeds evidence/section rows
    #     that are newer than the last successful embedder run.
    #   - intelligence_recompute is idempotent: only writes a fresh row
    #     when classify_state detects a meaningful change.
    #
    # The synthesis-cache is therefore PRESERVED by default. Operators
    # opt in to invalidation only when the new code path actually changes
    # how cached narratives should look (e.g. a parser fix that changes
    # the evidence bundle without bumping prompt_template_version). The
    # --invalidate-cache flag is the explicit lever for that.
    #
    # Three root causes the refresh closes:
    #   (a) Cloud Run rolled the new revision but TRAFFIC stayed on the
    #       old one (no auto-promote on terraform-managed services with
    #       split traffic) → promote-to-LATEST on both services.
    #   (b) New DMA packages sat un-ingested between scheduled crawls →
    #       trigger drive_crawler / embedder / intelligence_recompute in
    #       delta mode so NEW data is fresh on next page load. Unchanged
    #       reports stay cached.
    #   (c) (opt-in via --invalidate-cache) Pure-code changes don't bump
    #       the synthesis-cache fingerprint, so the operator keeps seeing
    #       narratives synthesized against pre-deploy evidence → mass
    #       invalidate via post_migrate.py's DMA_POST_DEPLOY_SQL hook.
    # The refresh script is fail-loud on traffic-promote failures (exit 2)
    # and best-effort on backfill (per-job failures land in /admin/import).
    if [[ "$REFRESH_MODE" == "run" ]]; then
      echo ""
      echo "→ Running post-deploy refresh (traffic promote + delta backfill)…"
      REFRESH_ARGS=()
      if [[ "$INVALIDATE_CACHE" == "run" ]]; then
        REFRESH_ARGS+=("--invalidate-cache")
      fi
      if ! SHA="${SHA}" "${SCRIPT_DIR}/post-deploy-refresh.sh" "${REFRESH_ARGS[@]}"; then
        echo "" >&2
        echo "✗ Post-deploy refresh failed." >&2
        echo "  Deploy + migrate succeeded; re-run just the refresh:" >&2
        echo "    SHA=${SHA} ${SCRIPT_DIR}/post-deploy-refresh.sh" >&2
        exit 6
      fi
    fi

    echo ""
    echo "✓ Deploy fully live + migrations applied + verified + refreshed at SHA=${SHA}"
    exit 0
  fi

  # Classify the failure — different errors deserve different responses.
  if grep -qE "Image .* not found|Image '[^']+' not found|no such image" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="image_missing"
    rm -f "$ERR_FILE"
    cat <<EOF >&2

✗ Image not found at SHA=${SHA}. Retry won't help.

Fix (build the images first):
  cd "${REPO_ROOT}/apps/dma-insights"
  gcloud builds submit . --config infra/cloudbuild.yaml \\
    --substitutions=_IMAGE_SHA="${SHA}"

Then re-run ./deploy.sh.
EOF
    exit 1
  fi

  if grep -qE "Error acquiring the state lock|conditionNotMet" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="state_lock"
    LOCK_ID=$(grep -oE 'ID:\s+[a-f0-9-]+' "$ERR_FILE" | head -1 | awk '{print $2}' || true)
    rm -f "$ERR_FILE"
    cat <<EOF >&2

✗ State lock contention — another apply is running, or a prior one was
  interrupted and didn't release the lock. Retry won't help.

Fix:
  terraform -chdir="${SCRIPT_DIR}/terraform" force-unlock ${LOCK_ID:-<LOCK_ID>}

Or, last resort (deletes the lock object directly):
  gsutil rm gs://${PROJECT_ID}-tfstate/dma-insights/terraform/default.tflock

Then re-run ./deploy.sh.
EOF
    exit 1
  fi

  # API-level config errors: HTTP 400 from the GCP API itself means our
  # terraform config is asking for something the API can't do. Common
  # examples: "Role roles/X is not supported for this resource" (wrong
  # IAM resource type for the role), "invalid argument" (malformed
  # field), "INVALID_ARGUMENT" with no detail. Retrying gives the same
  # answer — abort with a pointer to the offending resource so the
  # operator can fix the terraform code.
  if grep -qE "is not supported for this resource|googleapi: Error 400:|INVALID_ARGUMENT" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="config_invalid"
    OFFENDING_RESOURCE=$(grep -oE 'with [a-z_.]+(\[[^]]+\])?' "$ERR_FILE" | head -1 || true)
    rm -f "$ERR_FILE"
    cat <<EOF >&2

✗ Terraform config rejected by the GCP API (HTTP 400). Retry won't help —
  the resource is asking for something the API does not allow.

Offending resource: ${OFFENDING_RESOURCE:-<see error above>}

Common causes:
  - IAM role not supported at the chosen scope (e.g. roles/drive.reader
    is a Workspace role, NOT a project IAM role — Drive access is
    granted via per-folder sharing instead).
  - Required field missing (e.g. region, project_id).
  - Resource name violates naming rules (length, characters).

Fix: edit apps/dma-insights/infra/terraform/main.tf and re-run.
EOF
    exit 1
  fi

  # Resource-already-exists isn't a hard error — usually means a prior
  # apply created the resource but state wasn't recorded. Suggest import.
  if grep -qE "already exists|alreadyExists|409: Resource" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="resource_conflict"
    OFFENDING_RESOURCE=$(grep -oE 'with [a-z_.]+(\[[^]]+\])?' "$ERR_FILE" | head -1 || true)
    rm -f "$ERR_FILE"
    cat <<EOF >&2

✗ Resource already exists outside of Terraform's state. Retry won't help —
  Terraform can't recreate a resource that's already there.

Offending resource: ${OFFENDING_RESOURCE:-<see error above>}

Fix (import the existing resource into state):
  cd ${SCRIPT_DIR}/terraform
  terraform import '<RESOURCE_ADDRESS>' '<RESOURCE_ID>'
  ./deploy.sh

If the existing resource is stale / wrong, delete it via gcloud first.
EOF
    exit 1
  fi

  # Postgres password drift — secret stored in Secret Manager and the
  # actual Cloud SQL user password no longer match. This happens when
  # someone runs `gcloud sql users set-password` out of band, or after
  # a Cloud SQL credential reset. Retrying the same apply won't fix it;
  # the operator needs to either heal (re-push terraform's password) or
  # rotate (issue fresh passwords). recover-db-passwords.sh does both.
  if grep -qE "password authentication failed for user|FATAL: +password authentication failed" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="pg_auth_failed"
    OFFENDING_USER=$(grep -oE 'password authentication failed for user "[^"]+"' "$ERR_FILE" | head -1 | sed -E 's|.*"([^"]+)".*|\1|' || true)
    rm -f "$ERR_FILE"
    cat <<EOF >&2

✗ Postgres password mismatch detected (user: ${OFFENDING_USER:-?}).
  The DSN secret has one password but the SQL user has another. This is
  drift — retrying won't help.

Fix: re-sync passwords from Terraform state to the SQL users:

  cd ${SCRIPT_DIR}
  ./recover-db-passwords.sh             # heal drift (re-push state's passwords)
  # OR
  ./recover-db-passwords.sh --rotate    # issue fresh random passwords

Then re-run the apply:
  ./deploy.sh
  gcloud run jobs execute dma-insights-migrations --region=${REGION} --wait
EOF
    exit 1
  fi

  if grep -qE "cannot assign requested address|dial tcp \[" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="ipv6"
    echo ""
    echo "⚠ IPv6 routing failures detected (Cloud Shell NAT pool issue)."
    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
      next_p="${PARALLELISMS[$((idx+1))]}"
      echo "  Next attempt will lower parallelism to ${next_p}."
    fi
  elif grep -qiE "rate ?limit|quota exceeded|429" "$ERR_FILE" 2>/dev/null; then
    LAST_ERROR_KIND="rate_limit"
    echo ""
    echo "⚠ Rate limit hit. Backing off and lowering parallelism."
  else
    LAST_ERROR_KIND="unknown"
    echo ""
    echo "⚠ Apply failed with an unclassified error (see above)."
  fi
  rm -f "$ERR_FILE"

  if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
    echo "  Retrying in ${wait_sec}s..."
    sleep "${wait_sec}"
  fi
done

# ── All attempts exhausted ──────────────────────────────────────────────────
echo "" >&2
echo "✗ terraform apply failed after ${MAX_ATTEMPTS} attempts." >&2
case "$LAST_ERROR_KIND" in
  ipv6)
    cat <<EOF >&2

Persistent IPv6 failures indicate Cloud Shell's NAT pool is in a bad
state. In order of effort:

  1. Restart Cloud Shell (fresh VM = fresh NAT pool):
       Top-right hamburger menu → "Restart"  →  then re-run ./deploy.sh

  2. If sudo was unavailable above, request it once and retry:
       sudo true                # forces sudo cache; no actual change
       cd ${SCRIPT_DIR} && ./deploy.sh

  3. Force a fully-serial apply on the next try:
       PARALLELISM_OVERRIDE=1 ./deploy.sh

  4. Wait 5-10 minutes (Google rotates IPv6 endpoints) and retry.

  5. Run the apply from a non-Cloud-Shell environment (laptop, Cloud
     Build, GitHub Actions, a Cloud Run Job). Those have stable
     networking. Example for a laptop with gcloud installed:
       export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa-key.json
       cd \$REPO_ROOT/apps/dma-insights/infra && ./deploy.sh
EOF
    ;;
  rate_limit)
    cat <<EOF >&2

Rate limit / quota exceeded. Cool-down options:
  - Wait 5 minutes, then:  PARALLELISM_OVERRIDE=2 ./deploy.sh
  - Check active quotas:   gcloud services quota list --service=<svc>
EOF
    ;;
  unknown)
    cat <<EOF >&2

Last error type: unknown. Check the Terraform output above for the
specific failure. Common categories:
  - Permission: missing IAM role; grant + retry.
  - Resource conflict: name already taken; rename or import.
  - Quota: hit a project / region quota; raise + retry.
EOF
    ;;
esac
exit 1
