#!/usr/bin/env bash
# apps/dma-insights/infra/build.sh
#
# Resilient Cloud Build invoker. Wraps `gcloud builds submit` so the
# recurring T18 failure mode never reaches the GCP API.
#
# Symptom this fixes:
#   ERROR: (gcloud.builds.submit) INVALID_ARGUMENT:
#     invalid value for 'build.substitutions': key in the template
#     "PG_BIN" is not a valid built-in substitution
#
# Root cause:
#   Cloud Build's submit-time validator parses every $UPPERCASE token
#   in cloudbuild.yaml as a substitution candidate. Built-ins
#   ($PROJECT_ID etc.) and user-defined ($_FOO) work; any other
#   uppercase $NAME — typically shell variables a contributor added
#   without realising — fails the entire submission.
#
# Self-heal strategy:
#   1. Pre-flight: grep cloudbuild.yaml for unescaped uppercase $VAR
#      that aren't valid built-ins or _-prefixed user vars.
#   2. If any found → list them, exit non-zero with a fix hint.
#   3. Otherwise → submit normally, with explicit substitutions.
#
# Usage:
#   ./build.sh              # uses git HEAD SHA
#   ./build.sh <sha>        # explicit override
#   ./build.sh --dry-run    # validate cloudbuild.yaml without submitting
#
# State branches:
#   yaml_clean + submit_ok       → exit 0
#   yaml_clean + submit_fail     → exit gcloud's rc; user reads logs
#   yaml_has_unescaped_uppercase → exit 1 with the offending lines +
#                                  the $${NAME} fix hint
#   wrapper_missing              → operator falls back to direct
#                                  gcloud (documented in DEPLOYMENT.md
#                                  §6 invocation block)
set -euo pipefail

# Cloud Shell IPv6 NAT mitigation (same as deploy.sh + migrate.sh).
export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"
CLOUDBUILD_YAML="${SCRIPT_DIR}/cloudbuild.yaml"

# ── Resolve target SHA ──────────────────────────────────────────────
DRY_RUN=false
SHA_OVERRIDE=""
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --help|-h)
      grep '^#' "$0" | sed 's/^# \?//' | head -35
      exit 0
      ;;
    *)
      SHA_OVERRIDE="$arg"
      ;;
  esac
done

if [[ -n "$SHA_OVERRIDE" ]]; then
  SHA="$SHA_OVERRIDE"
elif [[ "$DRY_RUN" == "true" ]]; then
  # --dry-run must be SIDE-EFFECT-FREE. resolve-deploy-sha.sh syncs the tree
  # (fetch + `checkout -B` onto the deploy branch) — correct at submit time,
  # catastrophic under test runners: the pytest safeguard that shells
  # `build.sh --dry-run` was checking the deploy branch out into whatever
  # worktree the suite ran in (2026-07-06: three consecutive full-suite runs
  # self-hijacked mid-run, deleting migrations 055/056 out from under the
  # parametrized migration tests and swapping heatmap.py under the sentinel
  # test — harmless only in CI's git-less image). Dry-run tolerates an empty
  # SHA, so read HEAD if present and never invoke the resolver here.
  SHA="$( (git rev-parse HEAD 2>/dev/null || true) | cut -c1-7 )"
else
  # Default to the NEWEST commit on the deploy branch (fetch origin + sync the
  # tree) so a stale/wrong checkout can't build an old image (the bde8329
  # incident). Each step is guarded with `|| true` so a missing `git` / no-.git
  # tarball — under `set -euo pipefail` — yields SHA="" instead of a
  # pipefail-127 exit.
  SHA="$(bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null || true)"
  if [[ -z "$SHA" ]]; then
    SHA="$( (git rev-parse HEAD 2>/dev/null || true) | cut -c1-7 )"
  fi
fi

# SHA is ONLY required at submit time. --dry-run validates
# cloudbuild.yaml without contacting GCP, so it must work in
# environments without a git checkout (e.g. Cloud Build's own
# pytest stage, which uploads source-only tarballs with no .git).
if [[ -z "$SHA" && "$DRY_RUN" != "true" ]]; then
  echo "ERROR: cannot determine SHA. Pass one as the first argument." >&2
  exit 1
fi

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# PROJECT_ID is similarly only required at submit time.
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  if [[ "$DRY_RUN" != "true" ]]; then
    echo "ERROR: PROJECT_ID unset. Run: gcloud config set project digital-maturity-assessor" >&2
    exit 1
  fi
  PROJECT_ID="dry-run-no-project"
fi

# ── Pre-flight: validate cloudbuild.yaml substitutions ──────────────
echo "→ Pre-flight: validating cloudbuild.yaml for unescaped uppercase shell vars..."

# Cloud Build accepts unescaped:
#   - Built-ins: PROJECT_ID, BUILD_ID, PROJECT_NUMBER, LOCATION,
#     REVISION_ID, COMMIT_SHA, SHORT_SHA, REPO_NAME, BRANCH_NAME,
#     TAG_NAME, TRIGGER_NAME, TRIGGER_BUILD_CONFIG_PATH
#   - User-defined: must start with `_` (e.g. $_IMAGE_SHA)
#
# Everything else uppercase MUST be $$NAME / $${NAME} to escape past
# the substitution parser into the shell.
BUILTINS='PROJECT_ID|BUILD_ID|PROJECT_NUMBER|LOCATION|REVISION_ID|COMMIT_SHA|SHORT_SHA|REPO_NAME|BRANCH_NAME|TAG_NAME|TRIGGER_NAME|TRIGGER_BUILD_CONFIG_PATH'

# Find any $UPPERCASE or ${UPPERCASE} that's NOT $$/$${, NOT a built-in,
# and NOT _-prefixed. The $$-escape filter is TOKEN-level (sed strips
# every $$NAME before matching), not `grep -v '$$'` line-level — a line
# containing BOTH a proper $$VAR escape and a bare $VAR used to pass
# validation and then fail the real submit with the exact T18
# INVALID_ARGUMENT this wrapper pre-empts (2026-07-04 line audit).
OFFENDERS="$(
  sed -E 's/\$\$\{?[A-Z_][A-Z_0-9]*\}?//g' "$CLOUDBUILD_YAML" \
    | grep -nE '\$\{?[A-Z][A-Z_0-9]*\}?' \
    | grep -vE "\\\$\\{?(${BUILTINS})\\}?\b" \
    | grep -vE '\$_[A-Z]' \
    || true
)"
# NOTE: We deliberately do NOT exclude comment lines. Cloud Build's
# substitution parser scans the entire YAML file (including content
# inside literal blocks AND comment lines) for $UPPERCASE tokens. A
# comment like `# $FOO is used here` will fail submission just as
# loudly as live code. The lesson cost us a build (see T18). Every
# comment that mentions $UPPERCASE patterns must use $$UPPERCASE.

if [[ -n "$OFFENDERS" ]]; then
  echo "" >&2
  echo "✗ Pre-flight FAILED — found unescaped uppercase shell vars in cloudbuild.yaml." >&2
  echo "  Cloud Build will reject these as invalid built-in substitutions." >&2
  echo "  Fix: replace \$NAME with \$\$NAME (or \${NAME} with \$\${NAME})." >&2
  echo "" >&2
  echo "  Offending lines:" >&2
  echo "$OFFENDERS" | sed 's/^/    /' >&2
  echo "" >&2
  echo "  See DEPLOYMENT.md §T18 for the full explanation." >&2
  exit 1
fi

echo "  ✓ cloudbuild.yaml substitutions clean"

if $DRY_RUN; then
  echo "→ --dry-run: skipping gcloud builds submit"
  exit 0
fi

# ── Submit ──────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════╗"
echo "║  DMA Insights — Cloud Build              ║"
echo "╠══════════════════════════════════════════╣"
echo "║  Project : ${PROJECT_ID}"
echo "║  SHA     : ${SHA}"
echo "╚══════════════════════════════════════════╝"
echo ""

# Record SHA for downstream steps (terraform apply, migrate.sh, etc.)
echo "$SHA" > /tmp/dma-insights-deploy-sha

cd "${SCRIPT_DIR}/.."
# Thread the OAuth web-client ID into the frontend build so a custom client id
# (operator's own GCP OAuth client) is inlined into the bundle instead of the
# hardcoded LoginPage fallback. When GOOGLE_OAUTH_CLIENT_ID is unset, the
# cloudbuild default ("") applies and LoginPage uses its documented fallback.
SUBS="_IMAGE_SHA=$SHA"
if [[ -n "${GOOGLE_OAUTH_CLIENT_ID:-}" ]]; then
  SUBS="${SUBS},_GOOGLE_OAUTH_CLIENT_ID=${GOOGLE_OAUTH_CLIENT_ID}"
  echo "  → threading _GOOGLE_OAUTH_CLIENT_ID into the frontend build"
fi
# Plain call (not `exec`): exec bypasses shell FUNCTIONS, which would
# skip the gcloud-noise-filter wrapper on the longest gcloud call of
# the deploy. Exit code propagates via `exit $?`.
gcloud builds submit . \
  --config infra/cloudbuild.yaml \
  --substitutions="$SUBS"
exit $?
