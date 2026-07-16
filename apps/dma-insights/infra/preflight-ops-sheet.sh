#!/usr/bin/env bash
# Verify the operator has Sheets API access to the DMA Ops Sheet, via
# the production worker SA (impersonated). Replaces the 50+ line probe
# block in DEPLOYMENT.md §0.2.11 that was a Cloud Shell paste hazard
# (multi-line case/esac, env-var interdependencies, nested-quote
# escapes the operator's shell mangled on paste).
#
# What this script proves:
#   • You can impersonate the worker SA from Cloud Shell (you have
#     roles/iam.serviceAccountTokenCreator on the SA).
#   • The impersonated SA has the Sheets API enabled in the project.
#   • The SA has been shared on the Ops Sheet as Viewer (or higher).
#
# Why SA impersonation (not your gcloud ADC): default ADC tokens don't
# carry the spreadsheets.readonly OAuth scope — you'd get a 403 even
# if you personally can open the sheet. Production reads happen as
# the worker SA, so this script tests the production permission grant.
#
# Usage:
#   bash apps/dma-insights/infra/preflight-ops-sheet.sh
#   # or with explicit args:
#   OPS_SHEET_ID=… WORKER_SA=… PROJECT_ID=… \
#     bash apps/dma-insights/infra/preflight-ops-sheet.sh
#
# Exit codes:
#   0  → OK (sheet readable as the SA, proceed to deploy)
#   1  → SHEETS_403 — SA isn't shared on the sheet. Script prints the
#                    exact "go to https://… → Share → paste <email> →
#                    Viewer" instruction so it's a one-click fix.
#   2  → SHEETS_404 — sheet ID typo or sheet doesn't exist
#   3  → NO_TOKEN — couldn't impersonate the SA (missing IAM role)
#   4  → PROJECT_ID / OPS_SHEET_ID missing
set -euo pipefail
export GODEBUG=netdns=go

# ── Resolve inputs ──────────────────────────────────────────────────
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# Canonical Zennify default per CLAUDE.md "constant" rule. Operators
# deploying non-canonically must set OPS_SHEET_ID explicitly.
OPS_SHEET_ID="${OPS_SHEET_ID:-1vQq4AMjtcS5eduDf_qIfXQYM7l0xYnVcmo-weqeXPs8}"
SHEETS_SCOPES="https://www.googleapis.com/auth/spreadsheets.readonly,https://www.googleapis.com/auth/cloud-platform"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "FATAL: PROJECT_ID not set." >&2
  echo "  Run:  gcloud config set project <PROJECT_ID>  OR  export PROJECT_ID=..." >&2
  exit 4
fi
if [[ -z "$OPS_SHEET_ID" ]]; then
  echo "FATAL: OPS_SHEET_ID not set + no canonical default available." >&2
  exit 4
fi

# Auto-resolve the worker SA from $PROJECT_ID if the operator didn't
# pass it. Order of preference (matches DEPLOYMENT.md §0.5.3):
#   1. Custom `dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com`
#      if it exists (this is what §0.5.3's "Worker SA" block creates;
#      it's the SA the Cloud Run workers actually run as).
#   2. Default compute SA `${PROJ_NUM}-compute@developer.gserviceaccount.com`
#      (the legacy fallback for project setups that didn't run §0.5.3).
# 2026-05-30 operator hit this: auto-resolve picked the compute SA, but
# their workers were running as the custom worker SA, so the probe
# tested the WRONG SA's share status.
if [[ -z "${WORKER_SA:-}" ]]; then
  CUSTOM_WORKER_SA="dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com"
  if gcloud iam service-accounts describe "$CUSTOM_WORKER_SA" \
       --project="$PROJECT_ID" >/dev/null 2>&1; then
    WORKER_SA="$CUSTOM_WORKER_SA"
  else
    PROJ_NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || true)"
    if [[ -z "$PROJ_NUM" ]]; then
      echo "FATAL: couldn't resolve PROJECT_NUMBER from PROJECT_ID='$PROJECT_ID'." >&2
      echo "  Pass WORKER_SA=... explicitly OR check gcloud auth + project visibility." >&2
      exit 4
    fi
    WORKER_SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
  fi
fi

echo "→ Ops Sheet preflight"
echo "  PROJECT_ID    = $PROJECT_ID"
echo "  WORKER_SA     = $WORKER_SA"
echo "  OPS_SHEET_ID  = $OPS_SHEET_ID"
echo ""

# ── Step 1: impersonation token ─────────────────────────────────────
echo "[1/2] Impersonating $WORKER_SA with Sheets scope…"
TOKEN="$(gcloud auth print-access-token \
         --impersonate-service-account="$WORKER_SA" \
         --scopes="$SHEETS_SCOPES" 2>/tmp/_sheets_token_err || true)"
if [[ -z "$TOKEN" ]]; then
  echo "  ✗ couldn't obtain a token. gcloud stderr:" >&2
  sed 's/^/    /' /tmp/_sheets_token_err >&2 || true
  echo "" >&2
  echo "  ═══════════════════════════════════════════════════════════════" >&2
  echo "    VERDICT: NO_TOKEN — you can't impersonate the worker SA." >&2
  echo "" >&2
  echo "    Most likely fix: your operator account needs the role" >&2
  echo "    `roles/iam.serviceAccountTokenCreator` on $WORKER_SA." >&2
  echo "" >&2
  echo "    Grant it:" >&2
  echo "      gcloud iam service-accounts add-iam-policy-binding $WORKER_SA \\" >&2
  echo "        --member=\"user:\$(gcloud config get-value account)\" \\" >&2
  echo "        --role=roles/iam.serviceAccountTokenCreator \\" >&2
  echo "        --project=$PROJECT_ID" >&2
  echo "  ═══════════════════════════════════════════════════════════════" >&2
  exit 3
fi
echo "  ✓ token issued"

# ── Step 2: probe the Sheets API ────────────────────────────────────
echo ""
echo "[2/2] GET sheets.googleapis.com/v4/spreadsheets/$OPS_SHEET_ID"
SHEET_URL="https://docs.google.com/spreadsheets/d/$OPS_SHEET_ID"
probe_out="$(curl --silent --max-time 15 -w '\n%{http_code}' \
              -H "Authorization: Bearer $TOKEN" \
              "https://sheets.googleapis.com/v4/spreadsheets/${OPS_SHEET_ID}?fields=properties.title,sheets.properties.title" \
              2>/dev/null || echo "$'\n'000")"
code="${probe_out##*$'\n'}"
body="${probe_out%$'\n'*}"

echo ""
echo "═══════════════════════════════════════════════════════════════"
case "$code" in
  200)
    echo "  VERDICT: OK — sheet readable as $WORKER_SA. Proceed to deploy."
    echo ""
    if command -v jq >/dev/null 2>&1; then
      title="$(printf '%s' "$body" | jq -r '.properties.title' 2>/dev/null || true)"
      tabs="$(printf '%s' "$body" | jq -r '[.sheets[].properties.title] | join(", ")' 2>/dev/null || true)"
      [[ -n "$title" ]] && echo "  Title : $title"
      [[ -n "$tabs"  ]] && echo "  Tabs  : $tabs"
    fi
    exit 0
    ;;
  403)
    echo "  VERDICT: SHEETS_403 — the SA isn't shared on the sheet yet."
    echo ""
    echo "  This is a ONE-CLICK fix on Google's side (no code changes):"
    echo ""
    echo "    1. Open the sheet in your browser:"
    echo "       $SHEET_URL"
    echo "    2. Click  Share  (top-right)"
    echo "    3. Paste this email exactly:"
    echo ""
    echo "         $WORKER_SA"
    echo ""
    echo "    4. Set role to  Viewer  → uncheck \"Notify people\" → Share"
    echo "    5. Re-run this script — should print VERDICT: OK"
    echo "═══════════════════════════════════════════════════════════════"
    exit 1
    ;;
  404)
    echo "  VERDICT: SHEETS_404 — sheet ID '$OPS_SHEET_ID' not visible to this token."
    echo ""
    echo "  Check that the sheet exists at:"
    echo "    $SHEET_URL"
    echo ""
    echo "  If it does exist, the SA may not be shared on it — share as"
    echo "  Viewer (steps under SHEETS_403 above) and re-run."
    echo "═══════════════════════════════════════════════════════════════"
    exit 2
    ;;
  000)
    echo "  VERDICT: NETWORK — Cloud Shell couldn't reach Sheets API."
    echo "  Check egress / try again from a fresh shell."
    echo "═══════════════════════════════════════════════════════════════"
    exit 5
    ;;
  *)
    echo "  VERDICT: HTTP $code — unexpected response from Sheets API."
    echo "  Body excerpt:"
    printf '%s\n' "$body" | head -10 | sed 's/^/    /'
    echo "═══════════════════════════════════════════════════════════════"
    exit 6
    ;;
esac
