#!/usr/bin/env bash
# Preflight for the app-scheduled synthesis routine.
#
# Runs FIRST, before any run is claimed. Every check prints OK / WARN / FAIL and
# nothing else — no secret, no prefix of a secret, no token. A routine that
# starts work with a broken credential fails halfway through a promote at 03:00
# with a claimed run and no one watching; this turns that into a refusal with a
# named cause.
#
# Credentials come from Secret Manager at call time (scripts/routine_secrets.py).
# Nothing is exported into the environment and nothing is written to disk, so a
# later `env` dump or an inherited subprocess cannot leak them.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${GCP_PROJECT:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
FAIL=0

# A stale token in the environment overrides the activated account and fails
# with a 401 that reads like a permissions problem.
unset CLOUDSDK_AUTH_ACCESS_TOKEN
for p in /root/google-cloud-sdk/bin /usr/lib/google-cloud-sdk/bin; do
  [ -d "$p" ] && PATH="$p:$PATH"
done
export PATH

say() { printf '%-22s %-5s %s\n' "$1" "$2" "${3:-}"; }
bad() { say "$1" FAIL "${2:-}"; FAIL=1; }

# 1 · gcloud identity — everything below needs it
if ident=$(gcloud config get-value account 2>/dev/null) && [ -n "$ident" ]; then
  say "gcloud identity" OK "$ident"
else
  bad "gcloud identity" "no active account; Secret Manager is unreachable"
fi

# 2 · the stored credentials, and whether they actually WORK.
#     exit 0 = all good · 2 = secrets read but the Drive tree is not reachable
#     by the stored key · 1 = a secret could not be read at all.
#     Only 1 is fatal: the scheduled session reads the package tree through its
#     Google Drive CONNECTOR (the user's own OAuth) and the stored key is the
#     headless fallback, so an unshared folder degrades rather than blocks.
python3 "$HERE/routine_secrets.py"
case "$?" in
  0) say "secrets" OK   "loaded at call time, not persisted" ;;
  2) say "secrets" WARN "readable; stored key cannot see the Drive tree — the
                         session's Drive connector must supply the package" ;;
  *) bad "secrets" "a secret could not be read from Secret Manager" ;;
esac

# 3 · the deployed services this routine drives
for svc in dmai-mcp dmai-api dmai-web; do
  rev=$(gcloud run services describe "$svc" --project="$PROJECT" --region="$REGION" \
        --format='value(status.latestReadyRevisionName)' 2>/dev/null)
  [ -n "$rev" ] && say "$svc" OK "$rev" || bad "$svc" "not deployed or unreadable"
done

# 4 · the connector answers a real tool call. It exposes no health route — it is
#     an MCP server on a capability path, so a bare GET is a 404 by design and
#     proves nothing. This lists the tools over the same path the routine's own
#     calls take, which is the only check that would catch a bad path token.
tools=$(python3 - <<'PY' 2>&1 | tail -1
import sys
sys.path.insert(0, "scripts")
try:
    import dma_connector as C
    r = C.call("get_run_progress", run_id="00000000-0000-0000-0000-000000000000")
    # Any structured answer — including "unknown run" — proves the path token
    # resolved and the server is serving tools.
    print("OK")
except Exception as e:                                        # noqa: BLE001
    print(f"ERR {type(e).__name__}: {str(e)[:120]}")
PY
)
case "$tools" in
  OK*) say "mcp tool call" OK "connector answered over its capability path" ;;
  *)   say "mcp tool call" WARN "${tools}" ;;
esac

# 5 · pending work — if there is none, the routine should stop, not synthesise
if [ -n "${INTAKE_FOLDER_ID:-}" ]; then
  say "intake folder id" OK "$INTAKE_FOLDER_ID"
else
  say "intake folder id" WARN "INTAKE_FOLDER_ID unset; default in routine_secrets.py"
fi

echo
if [ "$FAIL" = "0" ]; then
  echo "PREFLIGHT PASS — proceed."
else
  echo "PREFLIGHT FAIL — do not claim a run. Fix the FAIL lines above first."
fi
exit "$FAIL"
