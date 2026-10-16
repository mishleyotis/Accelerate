# Mint a Google ID token for a private Cloud Run URL (the smoke probes).
# Sourced by infra/deploy.sh and infra/evidence-engine/smoke.sh.
#
#   id_token_into VAR AUDIENCE   -> 0 and VAR set, or 1 with ID_TOKEN_WHY set
#
# Why (2026-10-11, the de59ebe release): under CI's Workload Identity
# Federation credential, `gcloud auth print-identity-token --audiences=URL`
# printed nothing. deploy.sh's api smoke read "NOT PROBED — no api URL or no
# identity token for this account", and smoke.sh, which made the same call
# under `set -e`, would have died on its first probe and proved nothing.
# Routes, in order:
#   1. the active credential (a person's gcloud login, a service-account key)
#   2. impersonating the deployer service account ($GCP_DEPLOYER_SA, else the
#      active account): IAM Credentials generateIdToken
# The token only ever lands in VAR (printf -v), never on stdout or stderr.
# Each route's last error line is kept in ID_TOKEN_WHY for the caller to
# report: a probe that could not run says so, it never reads as a pass.
id_token_into() {
  local __var="$1" aud="$2" sa t ef
  ID_TOKEN_WHY=""
  printf -v "$__var" '%s' ""
  ef="$(mktemp)"
  t="$(gcloud auth print-identity-token --audiences="$aud" 2>"$ef" || true)"
  if [ -n "$t" ]; then rm -f "$ef"; printf -v "$__var" '%s' "$t"; return 0; fi
  ID_TOKEN_WHY="active credential: $(grep -v '^WARNING' "$ef" | tail -1)"
  sa="${GCP_DEPLOYER_SA:-$(gcloud config get-value account 2>/dev/null || true)}"
  if [ -n "$sa" ]; then
    t="$(gcloud auth print-identity-token --impersonate-service-account="$sa" \
           --include-email --audiences="$aud" 2>"$ef" || true)"
    if [ -n "$t" ]; then rm -f "$ef"; printf -v "$__var" '%s' "$t"; return 0; fi
    ID_TOKEN_WHY="$ID_TOKEN_WHY; impersonating $sa: $(grep -v '^WARNING' "$ef" | tail -1)"
  else
    ID_TOKEN_WHY="$ID_TOKEN_WHY; no deployer service account to impersonate"
  fi
  rm -f "$ef"
  return 1
}
