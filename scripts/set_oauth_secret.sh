#!/usr/bin/env bash
# Store the Google OAuth client secret for the DMA Insights connector.
#
# WHY THIS SCRIPT EXISTS (measured 2026-08-20): the value in Secret Manager
# was a 24-character placeholder beginning "YOU", not a Google secret — and
# Google answered every token exchange with invalid_client, which the
# claude.ai dialog reports only as "Authorization with DMA Insights failed".
# A placeholder that LOOKS stored is the failure mode this script prevents:
# it validates the shape before writing, and proves the pair works against
# Google afterwards.
#
#   bash scripts/set_oauth_secret.sh
#
# The value is read from the terminal with echo off. It is never passed as an
# argument (arguments show in ps and shell history), never echoed, and never
# written to disk.
set -uo pipefail
PROJECT=digital-maturity-assessor

printf 'Paste the client secret from console.cloud.google.com/apis/credentials\n'
printf '(OAuth client "DMA Insights", Client secrets section — starts GOCSPX-)\n> '
read -rs VALUE
printf '\n'

case "$VALUE" in
  GOCSPX-*) : ;;
  *) echo "REFUSED: a Google client secret always begins GOCSPX-." >&2
     echo "You pasted something ${#VALUE} characters long starting '${VALUE:0:3}'." >&2
     exit 1 ;;
esac
[ "${#VALUE}" -ge 30 ] || { echo "REFUSED: too short (${#VALUE} chars; Google issues 35)." >&2; exit 1; }

printf "%s" "$VALUE" | "${GCLOUD_BIN:-$(command -v gcloud || echo /opt/google-cloud-sdk/bin/gcloud)}" secrets versions add dmai-oauth-client-secret \
  --project="$PROJECT" --data-file=- --quiet >/dev/null || {
  echo "Could not write the secret. Check you are authenticated: gcloud auth list" >&2
  exit 1; }
unset VALUE
echo "Stored as a new version of dmai-oauth-client-secret."
echo
echo "Now prove it works (no secret is printed):"
echo "  python3 scripts/verify_oauth_client.py"
