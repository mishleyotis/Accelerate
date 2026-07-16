#!/usr/bin/env bash
# Pre-apply image ENFORCEMENT for the DMA Insights terraform deploy.
#
# Contract (agreed 2026-05-29): when an image is missing at the target
# SHA, this script BUILDS it — it never skips, excludes, or merely warns.
# Run it BEFORE any `terraform plan`/`apply` that reads the three
# `data "google_artifact_registry_docker_image"` blocks (backend,
# frontend, workers). Without it, terraform plan dies with
# "Requested image was not found" and cannot apply.
#
# Why terraform needs this: main.tf looks up all three images at
# `var.image_sha` during the PLAN phase. A SHA with no built images
# (e.g. a fresh HEAD commit that only changed docs/scripts) fails the
# whole plan. Building the images first is the only fix — excluding the
# data blocks was explicitly rejected.
#
# Usage:
#   ./preflight-image-check.sh                 # SHA = git HEAD; build if missing
#   ./preflight-image-check.sh <sha>           # explicit SHA; build if missing
#   SHA=abc1234 ./preflight-image-check.sh     # SHA from env; build if missing
#   ./preflight-image-check.sh --check-only    # verify only; exit 1 if missing
#                                              # (CI/advisory — does NOT build)
#
# Exits 0 when all three images exist at the SHA (after building if it
# had to); non-zero if a build was needed and failed, or --check-only
# found a gap.
set -euo pipefail

# Cloud Shell IPv6 NAT-pool mitigation — force IPv4 DNS for gcloud.
export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# apps/dma-insights — the Cloud Build context root (matches deploy.sh).
BUILD_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

# Capture any inherited $SHA env BEFORE parsing (the arg loop must not
# clobber it).
SHA_FROM_ENV="${SHA:-}"
CHECK_ONLY=false
SHA_ARG=""
for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=true ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \?//' | head -30; exit 0 ;;
    -*) echo "unknown flag: $arg" >&2; exit 2 ;;
    *) SHA_ARG="$arg" ;;
  esac
done

# SHA resolution priority: explicit arg > $SHA env > deploy-handoff > git HEAD.
SHA="$SHA_ARG"
[[ -z "$SHA" ]] && SHA="$SHA_FROM_ENV"
# Resolve the SHA to check: explicit env > NEWEST deploy-branch tip > the
# build.sh handoff file > local HEAD. The resolver is tried BEFORE /tmp so a
# STALE leftover /tmp/dma-insights-deploy-sha from a prior deploy can't poison
# the check (a contributor to the bde8329 incident).
[[ -z "$SHA" ]] && SHA="$(NO_SYNC=1 bash "$SCRIPT_DIR/resolve-deploy-sha.sh" 2>/dev/null || true)"
[[ -z "$SHA" && -f /tmp/dma-insights-deploy-sha ]] && SHA="$(cat /tmp/dma-insights-deploy-sha)"
[[ -z "$SHA" ]] && SHA="$( (git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || true) | cut -c1-7 )"
if [[ -z "$SHA" ]]; then
  echo "ERROR: could not resolve an image SHA. Pass one explicitly:" >&2
  echo "  $0 \$(git rev-parse --short HEAD)" >&2
  exit 2
fi

PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
if [[ -z "$PROJECT" || "$PROJECT" == "(unset)" ]]; then
  echo "ERROR: gcloud project not set. Run: gcloud config set project <PROJECT_ID>" >&2
  exit 2
fi

# Count how many of the 3 images exist at $SHA. Echoes the missing names.
missing_images() {
  local missing=()
  for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
    local found
    found=$(gcloud container images list-tags "gcr.io/${PROJECT}/${img}" \
      --filter="tags:${SHA}" --format='value(tags)' --limit=1 2>/dev/null | head -1 || true)
    if [[ -z "$found" ]]; then
      missing+=("$img")
    fi
  done
  printf '%s\n' "${missing[@]:-}"
}

echo "→ Image preflight @ gcr.io/${PROJECT}/...:${SHA}"
MISSING=()
while IFS= read -r line; do
  [[ -n "$line" ]] && MISSING+=("$line")
done < <(missing_images)

for img in dma-insights-backend dma-insights-frontend dma-insights-workers; do
  if printf '%s\n' "${MISSING[@]:-}" | grep -qx "$img"; then
    printf '  [MISSING] gcr.io/%s/%s:%s\n' "$PROJECT" "$img" "$SHA" >&2
  else
    printf '  [OK]      gcr.io/%s/%s:%s\n' "$PROJECT" "$img" "$SHA"
  fi
done

if (( ${#MISSING[@]} == 0 )); then
  echo "✓ All 3 images present at ${SHA}. Safe to run terraform plan/apply."
  exit 0
fi

# ── Missing image(s): --check-only reports; default BUILDS them ─────────────
if [[ "$CHECK_ONLY" == "true" ]]; then
  cat >&2 <<EOF

✗ ${#MISSING[@]} image(s) missing at SHA ${SHA} (--check-only — not building).
  Build them with:
    bash ${SCRIPT_DIR}/preflight-image-check.sh ${SHA}
  or:
    gcloud builds submit ${BUILD_DIR} \\
      --config ${BUILD_DIR}/infra/cloudbuild.yaml \\
      --substitutions=_IMAGE_SHA=${SHA}
EOF
  exit 1
fi

echo ""
echo "→ ${#MISSING[@]} image(s) missing — BUILDING all 3 via Cloud Build (~5-15 min)."
echo "  (Per the deploy contract, a missing image is built, never skipped.)"
echo "    gcloud builds submit ${BUILD_DIR} \\"
echo "      --config ${BUILD_DIR}/infra/cloudbuild.yaml \\"
echo "      --substitutions=_IMAGE_SHA=${SHA} --timeout=30m"
if ! gcloud builds submit "$BUILD_DIR" \
       --config "${BUILD_DIR}/infra/cloudbuild.yaml" \
       --substitutions="_IMAGE_SHA=${SHA}" \
       --timeout=30m; then
  echo "" >&2
  echo "✗ Cloud Build FAILED at SHA=${SHA}. terraform plan/apply will still" >&2
  echo "  fail on the image data lookups. Inspect the build:" >&2
  echo "    gcloud builds list --limit=1 --filter='substitutions._IMAGE_SHA=${SHA}'" >&2
  exit 1
fi

# Re-verify all three landed (catches a tag mismatch in cloudbuild.yaml).
echo "→ Re-verifying images landed at gcr.io…"
STILL_MISSING=()
while IFS= read -r line; do
  [[ -n "$line" ]] && STILL_MISSING+=("$line")
done < <(missing_images)
if (( ${#STILL_MISSING[@]} > 0 )); then
  echo "✗ After build, still missing: ${STILL_MISSING[*]}" >&2
  echo "  Likely a tag mismatch in cloudbuild.yaml (_IMAGE_SHA not stamped" >&2
  echo "  onto every image). terraform apply will fail — do NOT proceed." >&2
  exit 1
fi
echo "✓ All 3 images built + present at ${SHA}. Safe to run terraform plan/apply."
