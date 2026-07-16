#!/usr/bin/env bash
# Verify the operator has Drive API access to the DMA Drive root folder,
# via the production worker SA (impersonated). Replaces the §0.2.10 probe
# block in DEPLOYMENT.md that was a Cloud Shell paste hazard (same
# multi-line `case/esac` + nested-quote shape as the Sheets probe; same
# fix pattern).
#
# What this script proves:
#   • You can impersonate the worker SA from Cloud Shell (you have
#     roles/iam.serviceAccountTokenCreator on the SA).
#   • The impersonated SA has the Drive API scope.
#   • The SA has been shared on the Drive folder as Viewer (or higher).
#     For folders inside a Shared Drive, the SA must be a Shared-Drive
#     member, not just folder-shared.
#
# Usage:
#   bash apps/dma-insights/infra/preflight-drive-folder.sh
#   # or with explicit args:
#   DRIVE_ROOT_FOLDER_ID=… WORKER_SA=… PROJECT_ID=… \
#     bash apps/dma-insights/infra/preflight-drive-folder.sh
#
# Exit codes:
#   0  → OK (folder readable as the SA, proceed to deploy)
#   1  → DRIVE_403 — SA isn't shared on the folder. Prints exact share URL.
#   2  → DRIVE_404 — folder ID typo OR the folder lives in a Shared Drive
#                    where the SA isn't a member.
#   3  → NO_TOKEN — couldn't impersonate the SA (missing IAM role)
#   4  → PROJECT_ID / DRIVE_ROOT_FOLDER_ID missing
set -euo pipefail
export GODEBUG=netdns=go

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# Canonical Zennify default per CLAUDE.md "Drive folder ID is constant".
DRIVE_ROOT_FOLDER_ID="${DRIVE_ROOT_FOLDER_ID:-1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P}"
DRIVE_SCOPES="https://www.googleapis.com/auth/drive.readonly,https://www.googleapis.com/auth/cloud-platform"

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "FATAL: PROJECT_ID not set." >&2
  echo "  Run:  gcloud config set project <PROJECT_ID>  OR  export PROJECT_ID=..." >&2
  exit 4
fi
if [[ -z "$DRIVE_ROOT_FOLDER_ID" ]]; then
  echo "FATAL: DRIVE_ROOT_FOLDER_ID not set + no canonical default available." >&2
  exit 4
fi

# Auto-resolve order (matches DEPLOYMENT.md §0.5.3):
#   1. Custom `dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com`
#      if it exists (the SA §0.5.3's "Worker SA" block creates).
#   2. Default compute SA (legacy fallback).
# Without (1), the probe tests the wrong SA's share status — the
# operator shares with the custom SA but the script's auto-resolve
# tests the compute SA, producing a false 403.
if [[ -z "${WORKER_SA:-}" ]]; then
  CUSTOM_WORKER_SA="dma-insights-worker@${PROJECT_ID}.iam.gserviceaccount.com"
  if gcloud iam service-accounts describe "$CUSTOM_WORKER_SA" \
       --project="$PROJECT_ID" >/dev/null 2>&1; then
    WORKER_SA="$CUSTOM_WORKER_SA"
  else
    PROJ_NUM="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)' 2>/dev/null || true)"
    if [[ -z "$PROJ_NUM" ]]; then
      echo "FATAL: couldn't resolve PROJECT_NUMBER from PROJECT_ID='$PROJECT_ID'." >&2
      exit 4
    fi
    WORKER_SA="${PROJ_NUM}-compute@developer.gserviceaccount.com"
  fi
fi

echo "→ Drive folder preflight"
echo "  PROJECT_ID            = $PROJECT_ID"
echo "  WORKER_SA             = $WORKER_SA"
echo "  DRIVE_ROOT_FOLDER_ID  = $DRIVE_ROOT_FOLDER_ID"
echo ""

echo "[1/2] Impersonating $WORKER_SA with Drive scope…"
TOKEN="$(gcloud auth print-access-token \
         --impersonate-service-account="$WORKER_SA" \
         --scopes="$DRIVE_SCOPES" 2>/tmp/_drive_token_err || true)"
if [[ -z "$TOKEN" ]]; then
  echo "  ✗ couldn't obtain a token. gcloud stderr:" >&2
  sed 's/^/    /' /tmp/_drive_token_err >&2 || true
  echo "" >&2
  echo "  ═══════════════════════════════════════════════════════════════" >&2
  echo "    VERDICT: NO_TOKEN — you can't impersonate the worker SA." >&2
  echo "" >&2
  echo "    Most likely fix: your operator account needs the role" >&2
  echo "    'roles/iam.serviceAccountTokenCreator' on $WORKER_SA." >&2
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

echo ""
echo "[2/2] GET drive.googleapis.com/drive/v3/files/$DRIVE_ROOT_FOLDER_ID (supportsAllDrives=true)"
FOLDER_URL="https://drive.google.com/drive/folders/$DRIVE_ROOT_FOLDER_ID"
probe_out="$(curl --silent --max-time 15 -w '\n%{http_code}' \
              -H "Authorization: Bearer $TOKEN" \
              "https://www.googleapis.com/drive/v3/files/${DRIVE_ROOT_FOLDER_ID}?fields=id,name,mimeType&supportsAllDrives=true" \
              2>/dev/null || echo "$'\n'000")"
code="${probe_out##*$'\n'}"
body="${probe_out%$'\n'*}"

echo ""
echo "═══════════════════════════════════════════════════════════════"
case "$code" in
  200)
    echo "  VERDICT: OK — folder readable as $WORKER_SA. Proceed to deploy."
    echo ""
    if command -v jq >/dev/null 2>&1; then
      name="$(printf '%s' "$body" | jq -r '.name' 2>/dev/null || true)"
      mt="$(printf '%s' "$body"   | jq -r '.mimeType' 2>/dev/null || true)"
      [[ -n "$name" ]] && echo "  Name      : $name"
      [[ -n "$mt"   ]] && echo "  MIME type : $mt"
    fi
    exit 0
    ;;
  403)
    echo "  VERDICT: DRIVE_403 — the SA isn't shared on the folder yet."
    echo ""
    echo "  One-click fix on Google's side (no code changes):"
    echo ""
    echo "    1. Open the folder in your browser:"
    echo "       $FOLDER_URL"
    echo "    2. Click  Share  (top-right)"
    echo "    3. Paste this email exactly:"
    echo ""
    echo "         $WORKER_SA"
    echo ""
    echo "    4. Set role to  Viewer  → uncheck \"Notify people\" → Share"
    echo "    5. Re-run this script — should print VERDICT: OK"
    echo ""
    echo "  Note: if the folder lives in a SHARED DRIVE, sharing the"
    echo "  folder isn't enough — add the SA as a member of the Shared"
    echo "  Drive itself (Shared Drive settings → Manage members)."
    echo "═══════════════════════════════════════════════════════════════"
    exit 1
    ;;
  404)
    echo "  VERDICT: DRIVE_404 — folder '$DRIVE_ROOT_FOLDER_ID' not visible."
    echo ""
    echo "  Three checks:"
    echo "    1. Folder exists at:"
    echo "       $FOLDER_URL"
    echo "    2. The SA ($WORKER_SA) is shared on it (Viewer is enough)."
    echo "    3. If it lives in a SHARED DRIVE, the SA needs to be a"
    echo "       Shared-Drive member (not just folder-shared)."
    echo "═══════════════════════════════════════════════════════════════"
    exit 2
    ;;
  000)
    echo "  VERDICT: NETWORK — Cloud Shell couldn't reach Drive API."
    echo "═══════════════════════════════════════════════════════════════"
    exit 5
    ;;
  *)
    echo "  VERDICT: HTTP $code — unexpected response from Drive API."
    echo "  Body excerpt:"
    printf '%s\n' "$body" | head -10 | sed 's/^/    /'
    echo "═══════════════════════════════════════════════════════════════"
    exit 6
    ;;
esac
