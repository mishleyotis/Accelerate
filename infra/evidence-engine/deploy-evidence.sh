#!/usr/bin/env bash
# DMA Insights — evidence-engine release. Idempotent. Creates ONLY new
# resources (four services, their identities, secrets, buckets, the static
# egress); never touches dmai-mcp, dmai-api, dmai-web, dmai-worker or any
# existing service (brief §10 HALT condition).
#
# GATED. Every resource-creating gcloud command below runs only when
# EE_DEPLOY_APPROVED=1 is set by a person after reading
# apps/evidence-engine/docs/DEPLOY-PLAN.md (brief §7.2 "gate before spend").
# Without it the script prints the plan it WOULD execute and exits 0.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"
SEC_UA="${SEC_EDGAR_USER_AGENT:-Zennify DMA-Insights evidence-engine (+https://www.zennify.com)}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"

say() { printf '\n== %s ==\n' "$*"; }
# Cloud Build's default for `run deploy --source` is 10 minutes; the engine
# image installs its wheels and bakes two ONNX models. 30 minutes, per build.
export CLOUDSDK_BUILDS_TIMEOUT="${CLOUDSDK_BUILDS_TIMEOUT:-1800}"
# IAM is eventually consistent: a service account created a second ago can
# read "does not exist" to the policy API (measured 2026-10-11, the first
# approved run: `projects add-iam-policy-binding` on the new dmai-evidence
# failed INVALID_ARGUMENT one second after `service-accounts create`). So a
# role binding is retried with backoff (5 s, 10 s, ... up to ~2.5 min in
# all), and a freshly created identity is waited for before anything binds
# it. Everything else runs once: a real error still stops the release.
BIND_ATTEMPTS="${EE_BIND_ATTEMPTS:-7}"
BIND_SLEEP_S="${EE_BIND_SLEEP_S:-5}"
retry_bind() {
  local n=1
  until "$@"; do
    if [ "$n" -ge "$BIND_ATTEMPTS" ]; then
      echo "binding still refused after ${n} attempts: $*" >&2
      return 1
    fi
    echo "  binding refused (attempt ${n}/${BIND_ATTEMPTS}); IAM may not see a new identity yet — retrying in $((n * BIND_SLEEP_S)) s" >&2
    sleep $((n * BIND_SLEEP_S))
    n=$((n + 1))
  done
}
run() {
  if [ "${EE_DEPLOY_APPROVED:-0}" != "1" ]; then printf 'PLAN: %q ' "$@"; printf '\n'; return 0; fi
  case " $* " in
    *" add-iam-policy-binding "*) retry_bind "$@" ;;
    *" run deploy "*" --source="*) source_deploy "$@" ;;
    *) "$@" ;;
  esac
}
# A failed source build tells this log only "Build failed; check build logs
# for details" (de59ebe, 2026-10-11: the build's own error was never seen).
# So a failed `run deploy --source` prints the newest failed Cloud Build's
# log since the deploy began, read as the identity this script already runs
# as, then fails exactly as before. A log it cannot read is said, not hidden.
source_deploy() {
  local since rc=0
  since="$(date -u -d '-60 seconds' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)"
  "$@" || rc=$?
  [ "$rc" -eq 0 ] && return 0
  build_log_since "$since" || true
  return "$rc"
}
build_log_since() {
  local since="$1" id="" created="" where="" w
  for w in "--region=$REGION" ""; do
    while read -r id created; do
      [ -n "$id" ] && [[ "$created" > "$since" || "$created" == "$since" ]] && { where="$w"; break 2; }
      id=""
    done < <(gcloud builds list --project="$PROJECT_ID" ${w:+"$w"} --filter="status=FAILURE" \
               --sort-by=~createTime --limit=5 --format='value(id,createTime)' 2>/dev/null || true)
  done
  if [ -z "$id" ]; then
    echo "build log: no failed Cloud Build since $since is listed for this identity (region $REGION or global)" >&2
    return 1
  fi
  echo "--- Cloud Build $id (failed at $created): last 80 lines ---" >&2
  gcloud builds log "$id" --project="$PROJECT_ID" ${where:+"$where"} 2>&1 | tail -80 >&2 \
    || echo "build log: $id could not be read by this identity" >&2
  echo "--- end of Cloud Build $id ---" >&2
}
# A just-created identity is visible to `describe` before the policy API sees
# it, so this is a floor, not a guarantee — retry_bind is the guarantee.
wait_for_sa() {
  [ "${EE_DEPLOY_APPROVED:-0}" = "1" ] || return 0
  local i
  for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
    gcloud iam service-accounts describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1 && return 0
    sleep "$BIND_SLEEP_S"
  done
  echo "service account $1 never became visible" >&2
  return 1
}
EXISTING=(dmai-mcp dmai-api dmai-web dmai-worker dmai-share)
for s in "${EXISTING[@]}"; do
  case " $* " in *" $s "*) echo "refusing: this script never names an existing service ($s)" >&2; exit 2;; esac
done

say "0 · identities (new)"
for sa in dmai-evidence dmai-searxng dmai-fetch dmai-edgar; do
  if gcloud iam service-accounts describe "${sa}@${SA_DOMAIN}" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: ${sa}@${SA_DOMAIN}"
  else
    run gcloud iam service-accounts create "$sa" --project="$PROJECT_ID" --display-name="DMA Insights $sa"
    wait_for_sa "${sa}@${SA_DOMAIN}"
  fi
  # The project-level binding needs projectIamAdmin. The CI deployer holds
  # it (infra/grants-for-admin.sh, stage 0.1), so ci_gate.sh sets
  # EE_GRANT_PROJECT_ROLES=1; a hand run without the role leaves it off and
  # grant-deployer.sh (owner, one-time) makes the binding instead.
  if [ "${EE_GRANT_PROJECT_ROLES:-0}" = "1" ]; then
    run gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:${sa}@${SA_DOMAIN}" --role=roles/logging.logWriter --condition=None --quiet
  fi
done

say "1 · secrets (new; values generated, never printed)"
for secret in dmai-evidence-path-token dmai-searxng-path-token dmai-fetch-path-token dmai-edgar-path-token dmai-searxng-secret-key; do
  if gcloud secrets describe "$secret" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: $secret"
  else
    if [ "${EE_DEPLOY_APPROVED:-0}" = "1" ]; then
      openssl rand -hex 24 | tr -d '\n' | gcloud secrets create "$secret" --project="$PROJECT_ID" --data-file=- --replication-policy=automatic
      echo "created: $secret"
    else
      echo "PLAN: openssl rand -hex 24 | gcloud secrets create $secret --data-file=-"
    fi
  fi
done
grant_secret() { run gcloud secrets add-iam-policy-binding "$1" --project="$PROJECT_ID" \
  --member="serviceAccount:${2}@${SA_DOMAIN}" --role=roles/secretmanager.secretAccessor --quiet; }
grant_secret dmai-evidence-path-token dmai-evidence
grant_secret dmai-searxng-path-token dmai-searxng
grant_secret dmai-searxng-secret-key dmai-searxng
grant_secret dmai-fetch-path-token dmai-fetch
grant_secret dmai-edgar-path-token dmai-edgar
# The plugin's identity rungs (dmai-routine, and the owner's gcloud account)
# read the evidence token the way they read dmai-mcp's: through Secret Manager.
grant_secret dmai-evidence-path-token dmai-routine
# The engine mounts SearXNG's door token (SEARXNG_PATH_TOKEN) to call
# /searx-json/<token>/search; without the grant its deploy is refused.
grant_secret dmai-searxng-path-token dmai-evidence
# The plugin's raw fallbacks (searxng, fetch, edgar) mint their path tokens
# from Secret Manager under the plugin identity, exactly as the engine's.
for t in dmai-searxng-path-token dmai-fetch-path-token dmai-edgar-path-token; do
  grant_secret "$t" dmai-routine
done
# smoke.sh reads each path token to probe the right door; the identity that
# runs the release (the CI deployer) is granted read on the four it probes.
DEPLOYER_MEMBER="${GCP_DEPLOYER_SA:-$(gcloud config get-value account 2>/dev/null || true)}"
if [ -n "$DEPLOYER_MEMBER" ]; then
  for t in dmai-evidence-path-token dmai-searxng-path-token dmai-fetch-path-token dmai-edgar-path-token; do
    run gcloud secrets add-iam-policy-binding "$t" --project="$PROJECT_ID" \
      --member="serviceAccount:${DEPLOYER_MEMBER}" --role=roles/secretmanager.secretAccessor --quiet
  done
else
  echo "warning: no deployer identity known; smoke.sh may not read the path tokens" >&2
fi

say "2 · buckets (new; engine text + cache, uniform access)"
for suffix in dmai-evidence-text dmai-evidence-cache; do
  b="gs://${PROJECT_ID}-${suffix}"
  if gcloud storage buckets describe "$b" --project="$PROJECT_ID" >/dev/null 2>&1; then
    echo "exists: $b"
  else
    run gcloud storage buckets create "$b" --project="$PROJECT_ID" --location="$REGION" --uniform-bucket-level-access
  fi
  run gcloud storage buckets add-iam-policy-binding "$b" \
    --member="serviceAccount:dmai-evidence@${SA_DOMAIN}" --role=roles/storage.objectAdmin --quiet
done

say "3 · static egress: VPC egress + Cloud NAT with a reserved address (EE_STATIC_EGRESS=1 only)"
# The plan's ONE always-on charge (the NAT bills per hour), so it is its own
# approval: off by default, and without it the services keep Cloud Run's
# default egress (dynamic IPs; no VPC flags, or they would lose the internet).
# searxng/health.sh measures engine health before and after; turn it on
# with EE_STATIC_EGRESS=1 when fewer than three general-web engines answer.
VPC_FLAGS=()
if [ "${EE_STATIC_EGRESS:-0}" = "1" ]; then
VPC_FLAGS=(--network=default --subnet=default --vpc-egress=all-traffic)
if gcloud compute addresses describe dmai-evidence-egress --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: address dmai-evidence-egress"
else
  run gcloud compute addresses create dmai-evidence-egress --region="$REGION" --project="$PROJECT_ID"
fi
if gcloud compute routers describe dmai-evidence-router --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: router"
else
  run gcloud compute routers create dmai-evidence-router --network=default --region="$REGION" --project="$PROJECT_ID"
fi
if gcloud compute routers nats describe dmai-evidence-nat --router=dmai-evidence-router --region="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  echo "exists: nat"
else
  run gcloud compute routers nats create dmai-evidence-nat --router=dmai-evidence-router --region="$REGION" \
    --project="$PROJECT_ID" --nat-all-subnet-ip-ranges --nat-external-ip-pool=dmai-evidence-egress
fi
else
  echo "skipped: static egress is off (EE_STATIC_EGRESS != 1); default Cloud Run egress, no always-on charge"
fi

say "4 · the three backends (new services)"
deploy_backend() { # name dir sa extra-env
  local name="$1" dir="$2" sa="$3" extra="$4"
  run gcloud run deploy "$name" --source="$ROOT/infra/evidence-engine/$dir" \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="${sa}@${SA_DOMAIN}" \
    --no-allow-unauthenticated --cpu-boost --max-instances=2 --concurrency=10 \
    --memory=1Gi --timeout=120 "${VPC_FLAGS[@]}" \
    --set-secrets="MCP_PATH_TOKEN=${name}-path-token:latest${extra}" --quiet
  # the engine and the plugin's identity may invoke it
  for member in dmai-evidence dmai-routine; do
    run gcloud run services add-iam-policy-binding "$name" --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:${member}@${SA_DOMAIN}" --role=roles/run.invoker --quiet
  done
}
deploy_backend dmai-searxng searxng dmai-searxng ",SEARXNG_SECRET_KEY=dmai-searxng-secret-key:latest"
deploy_backend dmai-fetch   fetch   dmai-fetch   ""
EDGAR_ENV="--set-env-vars=SEC_EDGAR_USER_AGENT=${SEC_UA}"
run gcloud run deploy dmai-edgar --source="$ROOT/infra/evidence-engine/edgar" \
  --project="$PROJECT_ID" --region="$REGION" --service-account="dmai-edgar@${SA_DOMAIN}" \
  --no-allow-unauthenticated --cpu-boost --max-instances=2 --concurrency=10 --memory=1Gi --timeout=120 \
  --set-secrets="MCP_PATH_TOKEN=dmai-edgar-path-token:latest" "$EDGAR_ENV" --quiet
for member in dmai-evidence dmai-routine; do
  run gcloud run services add-iam-policy-binding dmai-edgar --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${member}@${SA_DOMAIN}" --role=roles/run.invoker --quiet
done

say "5 · the engine (new service): 2Gi, cpu-boost, max 2 instances"
SEARXNG_URL="$(gcloud run services describe dmai-searxng --project="$PROJECT_ID" --region="$REGION" --format='value(status.url)' 2>/dev/null || echo 'https://dmai-searxng.PLAN')"
run gcloud run deploy dmai-evidence --source="$ROOT/apps/evidence-engine" \
  --project="$PROJECT_ID" --region="$REGION" \
  --service-account="dmai-evidence@${SA_DOMAIN}" \
  --no-allow-unauthenticated --cpu-boost --max-instances=2 \
  --concurrency="${EE_CONCURRENCY:-8}" --memory=2Gi --cpu=2 --timeout=300 "${VPC_FLAGS[@]}" \
  --set-env-vars="^;^SEARXNG_URL=${SEARXNG_URL};EE_GCS_BUCKET=${PROJECT_ID}-dmai-evidence-text;SEC_EDGAR_USER_AGENT=${SEC_UA};PARALLEL_MCP_URL=https://search.parallel.ai/mcp" \
  --set-secrets="EE_PATH_TOKEN=dmai-evidence-path-token:latest,SEARXNG_PATH_TOKEN=dmai-searxng-path-token:latest" --quiet
run gcloud run services add-iam-policy-binding dmai-evidence --project="$PROJECT_ID" --region="$REGION" \
  --member="serviceAccount:dmai-routine@${SA_DOMAIN}" --role=roles/run.invoker --quiet

say "6 · smoke (wrong path 404s; tools/list non-empty) — runs only after an approved deploy"
if [ "${EE_DEPLOY_APPROVED:-0}" = "1" ]; then "$HERE/smoke.sh"; else echo "PLAN: infra/evidence-engine/smoke.sh"; fi
