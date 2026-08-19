#!/usr/bin/env bash
# DMA Insights — every-release deployment. Idempotent. Builds images, runs
# the migrate Job, rolls services, syncs Jobs and Scheduler triggers.
# Sections activate as each deployable lands (walking-skeleton discipline:
# every stage ends with this script run against production).
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-digital-maturity-assessor}"
REGION="${REGION:-us-central1}"
SA_DOMAIN="${PROJECT_ID}.iam.gserviceaccount.com"

say() { printf '\n== %s ==\n' "$*"; }

# --- 1 · migrate (Cloud Run Job, pre-deploy; deploy proceeds only on success)
if [ -f migrations/Dockerfile ]; then
  say "migrate job (runs prod_apply.py: alembic + catalogue loads + VERIFY log lines)"
  gcloud run jobs deploy dmai-migrate --source=migrations \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-migrate@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-migrate@${PROJECT_ID}.iam;DB_NAME=dma_insights;LOAD_CATALOGUES=v7.0:current,v5.0" \
    --max-retries=0 --task-timeout=1800 --memory=1Gi --quiet
  gcloud run jobs execute dmai-migrate --project="$PROJECT_ID" --region="$REGION" --wait
fi

# --- 2 · services (api first: web depends on it; mcp independent) ---------
#
# The api image READS cross-service contracts at runtime, and the Dockerfile
# copies only `dma_api` — so those files have to be staged in beside it. Same
# pattern as corpus_gates.json for the jobs below: staged, never committed to
# apps/api, so packages/shared holds the single copy CI checks.
#
# This is not hypothetical tidiness. enrichment_register.json was NOT staged,
# the loader swallowed the FileNotFoundError into an empty dict, and all five
# enrichment surfaces served without their status while every test passed —
# because in the repo the file is there. Gate D now fails CI if a shared file
# the code reads is not staged for the deployable that reads it.
stage_shared_into_api() {
  cp packages/shared/enrichment_register.json apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/enrichment_register.json is missing" >&2
    exit 1
  }
  # dma_api/evidence.py imports this at module load to spell out the
  # abbreviations in a package-supplied source label. Missing means the api
  # does not start, which is the intended failure: a silent fallback here
  # would serve "Logix FCU" to a client and pass every test.
  cp packages/shared/abbreviations.py apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/abbreviations.py is missing" >&2
    exit 1
  }
}

if [ -f apps/api/Dockerfile ]; then
  say "svc_api"
  stage_shared_into_api
  # IAP_AUDIENCE is the assertion audience of the WEB service — the API
  # verifies the assertion the BFF forwards and pins it to that audience, so
  # a token minted for anything else cannot be replayed here. Computed the
  # same way the web's own copy is, below; a mismatch between the two would
  # refuse every write rather than accept a wrong one.
  API_PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  gcloud run deploy dmai-api --source=apps/api \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-api@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-api@${PROJECT_ID}.iam;DB_NAME=dma_insights;IAP_AUDIENCE=/projects/${API_PROJECT_NUMBER}/locations/${REGION}/services/dmai-web" \
    --concurrency=80 --min-instances=1 --no-allow-unauthenticated --quiet
  # web calls api service-to-service with an ID token
  gcloud run services add-iam-policy-binding dmai-api \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null
fi
if [ -f apps/mcp/Dockerfile ]; then
  say "svc_mcp"
  # dma_mcp/gaps.py imports the shared gap module at load time. Deploy 8
  # shipped without this and the container failed its startup probe; Cloud Run
  # kept traffic on the previous revision, so it was a failed deploy rather
  # than an outage — but only by Cloud Run's grace, not by design.
  cp packages/shared/enrichment_gaps.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/enrichment_gaps.py is missing" >&2; exit 1; }
  cp packages/shared/contracts_data.json apps/mcp/shared/ || {
    echo "FATAL: packages/shared/contracts_data.json is missing" >&2; exit 1; }
  # dma_mcp/validation.py imports the abbreviation list at load time: CG-27
  # reads it, and it is the same copy the api's evidence projection reads.
  cp packages/shared/abbreviations.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/abbreviations.py is missing" >&2; exit 1; }
  # Capability-URL token: the streamable-HTTP path embeds it, so the
  # Cowork connector needs only the URL. Rotating the secret rotates the
  # URL. Created once, never echoed.
  if ! gcloud secrets describe dmai-mcp-path-token --project="$PROJECT_ID" >/dev/null 2>&1; then
    head -c 24 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=' | gcloud secrets create dmai-mcp-path-token \
      --project="$PROJECT_ID" --data-file=- --quiet
  fi
  gcloud secrets add-iam-policy-binding dmai-mcp-path-token \
    --project="$PROJECT_ID" \
    --member="serviceAccount:dmai-mcp@${SA_DOMAIN}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  gcloud run deploy dmai-mcp --source=apps/mcp \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-mcp@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-mcp@${PROJECT_ID}.iam;DB_NAME=dma_insights" \
    --set-secrets="MCP_PATH_TOKEN=dmai-mcp-path-token:latest" \
    --memory=2Gi --cpu=2 \
    --concurrency=4 --timeout=900 --min-instances=1 --no-allow-unauthenticated --quiet
  # THE CONNECTOR IS NOT PUBLIC, and this line is why it stays that way.
  #
  # This deploy passed `--allow-unauthenticated` until 2026-08-16, which
  # grants roles/run.invoker to allUsers. The plugin minted a Google identity
  # token on every connection and sent it; nothing on the other side read it.
  # Authentication rested entirely on the path token in the URL — on the one
  # component permitted to write serving content — while dmai-api and dmai-web
  # were correctly closed. Fixing the IAM policy by hand would have been undone
  # by the next release, silently, which is the only reason this comment is
  # here rather than in a runbook.
  #
  # The path token is a capability, not an identity. It says WHICH connector;
  # it cannot say WHO, it travels in a URL, and it cannot be revoked per user.
  for member in "domain:${MCP_INVOKER_DOMAIN:-zennify.com}" \
                "serviceAccount:${MCP_INVOKER_SA:-claude-deployer@${PROJECT_ID}.iam.gserviceaccount.com}"; do
    gcloud run services add-iam-policy-binding dmai-mcp \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="$member" --role="roles/run.invoker" --quiet >/dev/null
  done
  # Prove it rather than assuming it: an ANONYMOUS request to a bogus path
  # token must die at IAM (403), not reach the application (404).
  mcp_url=$(gcloud run services describe dmai-mcp --project="$PROJECT_ID" \
      --region="$REGION" --format='value(status.url)')
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST \
      "${mcp_url}/mcp/deploy-probe-no-such-path-token" \
      -H 'Content-Type: application/json' -d '{}' || echo 000)
  case "$code" in
    401|403) say "svc_mcp: anonymous call rejected at IAM (HTTP $code)" ;;
    *) echo "FATAL: dmai-mcp answered an ANONYMOUS request with HTTP $code." \
            "403 means IAM rejected it; anything else means the connector is" \
            "reachable without a Google identity. Refusing to call this deploy" \
            "done." >&2; exit 1 ;;
  esac
fi
if [ -f apps/web/Dockerfile ]; then
  say "web"
  # Session-cookie signing secret: created once, never echoed (Secret Manager).
  if ! gcloud secrets describe dmai-session-secret --project="$PROJECT_ID" >/dev/null 2>&1; then
    head -c 48 /dev/urandom | base64 | gcloud secrets create dmai-session-secret \
      --project="$PROJECT_ID" --data-file=- --quiet
  fi
  gcloud secrets add-iam-policy-binding dmai-session-secret \
    --project="$PROJECT_ID" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  API_URL="$(gcloud run services describe dmai-api --project="$PROJECT_ID" \
    --region="$REGION" --format='value(status.url)' 2>/dev/null || true)"
  # Role grants (allowlists until the auth stage's users table): ADMIN and
  # ANALYST are strictly these emails; every other @zennify.com Google
  # account signs in as AE. Override per deploy via the environment.
  ADMIN_EMAILS="${ADMIN_EMAILS:-mishley.otiende@zennify.com,dma@zennify.com}"
  ANALYST_EMAILS="${ANALYST_EMAILS:-mishley.otiende@zennify.com,dma@zennify.com}"
  PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  # The IAP assertion audience for THIS service — the app rejects
  # assertions minted for anything else.
  IAP_AUDIENCE="/projects/${PROJECT_NUMBER}/locations/${REGION}/services/dmai-web"
  gcloud run deploy dmai-web --source=apps/web \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-web@${SA_DOMAIN}" \
    --set-env-vars="^;^API_URL=${API_URL};ADMIN_EMAILS=${ADMIN_EMAILS};ANALYST_EMAILS=${ANALYST_EMAILS};IAP_AUDIENCE=${IAP_AUDIENCE};GCP_PROJECT=${PROJECT_ID};GCP_REGION=${REGION};WORKER_JOB=dmai-worker;INTAKE_FOLDER_ID=${INTAKE_FOLDER_ID:-1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo}" \
    --set-secrets="SESSION_SECRET=dmai-session-secret:latest" \
    --allow-unauthenticated --quiet

  # ── Google sign-in at the door: Cloud Run integrated IAP ─────────────
  # Google authenticates every request (Google-managed OAuth client,
  # org-internal), the app verifies the forwarded assertion (lib/iap.js)
  # and enforces @zennify.com. Grants: the Workspace domain.
  # IAP is configured once; the deploy service account may lack the
  # org-level permission to (re-)enable the API or bind IAP policy. These
  # steps are idempotent and must not abort a release that has already
  # rolled the services — so each tolerates a permission failure and the
  # release continues to the worker Job and Scheduler sync below.
  gcloud services enable iap.googleapis.com --project="$PROJECT_ID" --quiet || true
  gcloud beta services identity create --service=iap.googleapis.com \
    --project="$PROJECT_ID" --quiet >/dev/null 2>&1 || true
  gcloud run services add-iam-policy-binding dmai-web \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com" \
    --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
  gcloud run services update dmai-web \
    --project="$PROJECT_ID" --region="$REGION" --iap --quiet || true
  # Direct (non-IAP) invocation stays closed: drop the public grant.
  gcloud run services remove-iam-policy-binding dmai-web \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="allUsers" --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
  # Who may pass Google's door: the Zennify workspace. (Tolerant: this
  # org-level grant may require an admin; a release must not abort on it.)
  gcloud iap web add-iam-policy-binding \
    --project="$PROJECT_ID" --resource-type=cloud-run \
    --service=dmai-web --region="$REGION" \
    --member="domain:zennify.com" --role="roles/iap.httpsResourceAccessor" --quiet >/dev/null 2>&1 || true

  # The admin "Run scan now" button fires the worker Job as dmai-web.
  gcloud run jobs add-iam-policy-binding dmai-worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
  # …and the "Request refresh" button fires dmai-refresh the same way. The
  # API writes nothing for it: invariant 2 enumerates the API's writes as
  # annotations and alert actions, so the request is recorded by a Job under
  # the ingest identity instead (apps/api/dma_api/refresh_job.py).
  gcloud run jobs add-iam-policy-binding dmai-refresh \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
fi

# --- 2b · dmai-refresh (the web's refresh-request write path) -------------
# Same image as svc_api, different entrypoint and a DIFFERENT DB identity:
# dmai-worker maps to svc_worker, the only role granted INSERT on
# refresh_requests (0032). svc_api holds SELECT there and nothing else, so an
# endpoint that tried to write the queue would fail on a grant rather than on
# a code review.
if [ -f apps/api/Dockerfile ]; then
  say "dmai-refresh job (records a refresh request; writes refresh_requests only)"
  stage_shared_into_api   # same image, same runtime reads
  gcloud run jobs deploy dmai-refresh --source=apps/api \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --command="python,-m,dma_api.refresh_job" \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-worker@${PROJECT_ID}.iam;DB_NAME=dma_insights" \
    --max-retries=0 --task-timeout=120 --memory=512Mi --quiet
fi

# --- 3 · worker Job + Scheduler sync (stage 1 / 0.5) ----------------------
if [ -f apps/worker/Dockerfile ]; then
  say "worker job (package scan; requires the intake folder shared with dmai-worker@)"
  # The enrichment routine reads the gap computation and the contract at
  # runtime; the Dockerfile copies only dma_worker, so both are staged in here
  # the same way the api's register is. Gate D fails CI if either is missing.
  cp packages/shared/enrichment_gaps.py apps/worker/shared/ || {
    echo "FATAL: packages/shared/enrichment_gaps.py is missing" >&2; exit 1; }
  cp packages/shared/contracts_data.json apps/worker/shared/ || {
    echo "FATAL: packages/shared/contracts_data.json is missing" >&2; exit 1; }
  gcloud run jobs deploy dmai-worker --source=apps/worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-worker@${PROJECT_ID}.iam;DB_NAME=dma_insights;INTAKE_FOLDER_ID=${INTAKE_FOLDER_ID:-1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo};MAX_PACKAGES=${MAX_PACKAGES:-10}" \
    --max-retries=0 --task-timeout=3600 --memory=2Gi --cpu=2 --quiet
  gcloud run jobs add-iam-policy-binding dmai-worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-worker@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null
  # ── the enrichment loop ────────────────────────────────────────────
  #
  # Same image, different entrypoint — the routine needs the same database
  # identity and the same staged contracts as the scan. Owner, 2026-08-15:
  # "There should be a working enrichment routine; not you doing it as Claude
  # Code." This is that routine; the schedule below is what makes it a loop
  # rather than a script someone remembers to run.
  say "dmai-enrich job (computes each run's gaps and records what it resolved)"
  gcloud run jobs deploy dmai-enrich --source=apps/worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --command="python,-m,dma_worker.enrichment" \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-worker@${PROJECT_ID}.iam;DB_NAME=dma_insights;ENRICH_TRIGGER=schedule" \
    --max-retries=1 --task-timeout=900 --memory=1Gi --quiet
  # Hourly. The gap set only changes when a run is submitted or re-promoted,
  # so a tighter cadence would spend the same answer repeatedly; an hour keeps
  # the loop visibly alive without becoming noise.
  if ! gcloud scheduler jobs describe dmai-enrich-loop --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs create http dmai-enrich-loop \
      --project="$PROJECT_ID" --location="$REGION" --schedule="7 * * * *" \
      --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/dmai-enrich:run" \
      --http-method=POST --oauth-service-account-email="dmai-worker@${SA_DOMAIN}" --quiet || true
  fi

  # package scan every 30 minutes (charter: mandatory trigger #1)
  if ! gcloud scheduler jobs describe dmai-package-scan --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
    gcloud scheduler jobs create http dmai-package-scan \
      --project="$PROJECT_ID" --location="$REGION" \
      --schedule="*/30 * * * *" \
      --uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/dmai-worker:run" \
      --http-method=POST \
      --oauth-service-account-email="dmai-worker@${SA_DOMAIN}" --quiet
  fi
fi

# --- 4 · the corpus Jobs and the charter's other two Scheduler triggers ---
# The charter names three mandatory triggers; only the package scan existed.
# A trigger with no Job behind it is a scheduled 404, so the Jobs are deployed
# here first and the triggers point at them.
#
# They run as DIFFERENT identities, each the one whose grants it actually
# uses. The exporter reads `serving_directory`, which 0013 grants to svc_api
# alone (measured: as dmai-mcp it failed with 42501 permission denied), so it
# runs as dmai-api. The scanner reads no serving table — it reads the pack and
# writes `gate_results`, which is svc_mcp's — so it runs as dmai-mcp. Neither
# gains a database grant it does not use; the only widening is object access
# on the pack bucket, added in provision.sh.
if [ -d infra/jobs ]; then
  say "corpus jobs (pack-exporter, corpus-gate-scanner)"
  # The ceilings are ONE file — packages/shared/corpus_gates.json, the file CI
  # Gate B ratchets. It is staged into the build context rather than copied
  # into infra/, so there is no second copy in the tree to drift.
  JOBS_CTX="$(mktemp -d)"
  cp -R infra/jobs/. "$JOBS_CTX/"
  cp packages/shared/corpus_gates.json "$JOBS_CTX/corpus_gates.json"
  rm -rf "$JOBS_CTX/tests"

  gcloud run jobs deploy dmai-pack-exporter --source="$JOBS_CTX" \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-api@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --command="python,-m,corpus_jobs.pack_export" \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-api@${PROJECT_ID}.iam;DB_NAME=dma_insights;GCP_PROJECT=${PROJECT_ID}" \
    --max-retries=0 --task-timeout=900 --memory=1Gi --quiet

  gcloud run jobs deploy dmai-corpus-gate-scanner --source="$JOBS_CTX" \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-mcp@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --command="python,-m,corpus_jobs.gate_scan" \
    --args="--fail-on-regression" \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-mcp@${PROJECT_ID}.iam;DB_NAME=dma_insights;GCP_PROJECT=${PROJECT_ID}" \
    --max-retries=0 --task-timeout=900 --memory=1Gi --quiet
  rm -rf "$JOBS_CTX"

  # Cloud Scheduler invokes both as dmai-mcp (one OAuth identity for the two
  # triggers); the JOB's own service account is what the container then runs
  # as, and they differ on purpose — see above.
  for job in dmai-pack-exporter dmai-corpus-gate-scanner; do
    gcloud run jobs add-iam-policy-binding "$job" \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:dmai-mcp@${SA_DOMAIN}" \
      --role="roles/run.invoker" --quiet >/dev/null
  done

  # Scheduler: idempotent by describe-then-create, like the package scan.
  # `update` follows the create so a changed schedule lands on a re-run
  # rather than being silently kept at whatever was registered first.
  sched() { # name schedule job-name
    local uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${3}:run"
    if gcloud scheduler jobs describe "$1" --project="$PROJECT_ID" --location="$REGION" >/dev/null 2>&1; then
      gcloud scheduler jobs update http "$1" \
        --project="$PROJECT_ID" --location="$REGION" \
        --schedule="$2" --uri="$uri" --http-method=POST \
        --oauth-service-account-email="dmai-mcp@${SA_DOMAIN}" --quiet
    else
      gcloud scheduler jobs create http "$1" \
        --project="$PROJECT_ID" --location="$REGION" \
        --schedule="$2" --uri="$uri" --http-method=POST \
        --oauth-service-account-email="dmai-mcp@${SA_DOMAIN}" --quiet
    fi
  }
  # charter: mandatory trigger #3 — the exporter writes the pack…
  sched dmai-pack-exporter "0 2 * * *" dmai-pack-exporter
  # …and #2 reads it an hour later. The order is the dependency: the scanner
  # measures the exported pack, and a scanner that ran first would grade
  # yesterday's corpus and report it as today's.
  sched dmai-corpus-gate-scanner "0 3 * * *" dmai-corpus-gate-scanner
fi

# ── the deploy has not happened until the BYTES match ────────────────
#
# H1 from the acceptance curation: verify_deployed.py existed and was
# referenced by neither CI nor this script, so shipped defect 13 — four render
# fixes reported live against a revision built 58 minutes BEFORE they were
# committed — had zero enforcement. A deploy script that exits 0 without
# checking what it shipped is how that happens twice.
#
# Non-fatal by design: the services are already rolled by this point and
# aborting would leave a half-reported release. It PRINTS the verdict, which is
# the thing that was missing.
if [ -f scripts/verify_deployed.py ]; then
  say "verify: is production serving HEAD?"
  python3 scripts/verify_deployed.py || {
    echo "!! production is NOT serving HEAD — see the diff above" >&2
  }
fi

say "deployed. Service URLs:"
gcloud run services list --project="$PROJECT_ID" --region="$REGION" \
  --filter="metadata.name:dmai-" --format='value(metadata.name,status.url)' || true
