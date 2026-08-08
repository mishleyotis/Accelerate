#!/usr/bin/env bash
# Preflight for the app-scheduled synthesis routine.
#
# Runs FIRST, before any run is claimed. Every check prints OK / WARN / FAIL and
# nothing else — no secret, no prefix of a secret, no token. A routine that
# starts work with a broken credential fails halfway through a promote at 03:00
# with a claimed run and no one watching; this turns that into a refusal with a
# named cause.
#
# WARN vs FAIL — the distinction is the whole point of this script, so it is
# stated once here rather than argued per check:
#
#   FAIL  the routine CANNOT complete its job correctly. It must not claim a
#         run. Credentials that will not mint; a connector that refuses the
#         call (the connector is the only writer of serving content, so no
#         connector means no output at all); a PAT GitHub rejects or that
#         expires inside the next firing interval; a Drive tree that cannot be
#         READ. "Could not read" is a FAIL, never a WARN — from the outside it
#         is indistinguishable from the empty tree the routine treats as
#         "nothing to do", and that mistake is silent.
#
#   WARN  degraded but workable: the run can still complete correctly and
#         produce the right output. A missing convenience variable with a sane
#         default; a secrets doc outage that Secret Manager covers; an intake
#         tree that listed successfully and is genuinely empty.
#
# The composite verdict and the exit status are computed from the SAME
# variable, so a run can never print FAIL and exit 0.
#
# Credentials come from Secret Manager at call time (scripts/routine_secrets.py).
# Nothing is exported into the environment and nothing is written to disk, so a
# later `env` dump or an inherited subprocess cannot leak them.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${GCP_PROJECT:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
PY="${PYTHON:-python3}"
FAIL=0
WARNS=0

# A stale token in the environment overrides the activated account and fails
# with a 401 that reads like a permissions problem.
unset CLOUDSDK_AUTH_ACCESS_TOKEN
# Only go looking for gcloud when the environment has not already supplied one;
# an explicit gcloud on PATH is a deliberate choice and must win.
if ! command -v gcloud >/dev/null 2>&1; then
  for p in /root/google-cloud-sdk/bin /usr/lib/google-cloud-sdk/bin; do
    [ -d "$p" ] && PATH="$p:$PATH"
  done
fi
export PATH

say()  { printf '%-22s %-5s %s\n' "$1" "$2" "${3:-}"; }
warn() { say "$1" WARN "${2:-}"; WARNS=$((WARNS + 1)); }
bad()  { say "$1" FAIL "${2:-}"; FAIL=1; }

# 1 · gcloud identity — everything below needs it.
#     `gcloud config get-value account` is a CONFIG READ: it prints the
#     configured account name and exits 0 against a completely emptied
#     credential store. Minting a token is the only check that proves the
#     credential behind that name still exists and works. The token itself is
#     discarded here and never printed.
if gcloud auth print-access-token >/dev/null 2>&1; then
  ident=$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -1)
  say "gcloud identity" OK "${ident:-active credential, account name unreadable}"
else
  bad "gcloud identity" "the credential store cannot mint a token; re-authenticate before this routine runs"
fi

# 2 · the stored credentials, and whether they actually WORK.
#     exit 0 = all good · 2 = degraded but workable · 1 = fatal.
"$PY" "$HERE/routine_secrets.py"
case "$?" in
  0) say  "secrets" OK   "loaded at call time, not persisted" ;;
  2) warn "secrets" "degraded but workable — see the WARN line(s) above" ;;
  *) bad  "secrets" "a credential could not be read, is rejected, or expires inside this firing interval" ;;
esac

# 3 · the deployed services this routine drives
for svc in dmai-mcp dmai-api dmai-web; do
  rev=$(gcloud run services describe "$svc" --project="$PROJECT" --region="$REGION" \
        --format='value(status.latestReadyRevisionName)' 2>/dev/null)
  [ -n "$rev" ] && say "$svc" OK "$rev" || bad "$svc" "not deployed or unreadable"
done

# 4 · the connector answers a real tool call. It exposes no health route — it is
#     an MCP server on a capability path, so a bare GET is a 404 by design and
#     proves nothing. This makes a real call over the same path AND with the
#     same identity token the routine's own calls use, which is the only check
#     that catches either a bad path token or a missing run.invoker grant.
#     Content enters the app through this connector and nowhere else, so a
#     refusal here means the routine has no write path: FAIL, not WARN.
export PREFLIGHT_SCRIPTS_DIR="$HERE"
tools=$("$PY" - <<'PY' 2>&1 | tail -1
import os
import sys
# Append rather than insert: an explicit PYTHONPATH stays ahead, and in
# production nothing else offers a module by this name.
sys.path.append(os.environ["PREFLIGHT_SCRIPTS_DIR"])
try:
    import dma_connector as C
    C.call("get_run_progress", run_id="00000000-0000-0000-0000-000000000000")
    # Any structured answer — including "unknown run" — proves the path token
    # resolved, the identity was accepted, and the server is serving tools.
    print("OK")
except Exception as e:                                        # noqa: BLE001
    print(f"ERR {type(e).__name__}: {str(e)[:300]}")
PY
)
case "$tools" in
  OK*) say "mcp tool call" OK "connector answered over its capability path" ;;
  *)   bad "mcp tool call" "${tools}" ;;
esac

# 5 · pending work — if there is none, the routine should stop, not synthesise
if [ -n "${INTAKE_FOLDER_ID:-}" ]; then
  say "intake folder id" OK "$INTAKE_FOLDER_ID"
else
  warn "intake folder id" "INTAKE_FOLDER_ID unset; default in routine_secrets.py"
fi

echo
if [ "$FAIL" != "0" ]; then
  echo "PREFLIGHT FAIL — do not claim a run. Fix the FAIL lines above first."
elif [ "$WARNS" != "0" ]; then
  echo "PREFLIGHT WARN — proceed; $WARNS degraded-but-workable check(s) above."
else
  echo "PREFLIGHT PASS — proceed."
fi
exit "$FAIL"
