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
  # The cached Cloud SQL Connector. Per-connection `Connector()` spends one
  # Cloud SQL ADMIN API request per connection, and under NullPool that is
  # one per checkout — measured as a 429 on
  # sqladmin.googleapis.com/.../connectSettings during a live firing on
  # 2026-08-31. Every service that opens a database connection needs this
  # copy, so a missing one is FATAL rather than a silent fallback.
  cp packages/shared/cloudsql.py apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/cloudsql.py is missing" >&2; exit 1; }
  cp packages/shared/abbreviations.py apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/abbreviations.py is missing" >&2
    exit 1
  }
  # The listing collapses a reference row into the row that quotes the same
  # artefact. Without this the api does not start, which is correct: serving
  # the un-merged listing would put a citation with no quote in front of a
  # reader beside the quote it was missing.
  cp packages/shared/evidence_merge.py apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/evidence_merge.py is missing" >&2
    exit 1
  }
  # The one pattern that says what may not appear in a sentence a client
  # reads. dma_api/redaction.py imports it at module load to withhold an
  # empty_state whose prose names a MEM id, a gate id or a connector call
  # (MEM-0137, measured live on three promoted clients). Missing means the api
  # does not start, which is the intended failure: the alternative is serving
  # `get_evidence('platform')` to a client and passing every test.
  cp packages/shared/internal_ids.py apps/api/shared/ 2>/dev/null || {
    echo "FATAL: packages/shared/internal_ids.py is missing" >&2
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
  # dma_mcp/resources.py serves the dual-source section map as an MCP resource
  # (join://section-sources) and derives gold://web-app-requirements from it.
  # Generated by scripts/gen_recording_map.py; a missing copy leaves those two
  # resources stated-empty rather than crashing, but a deploy should ship it.
  cp packages/shared/section_sources.json apps/mcp/shared/ || {
    echo "FATAL: packages/shared/section_sources.json is missing "
         "(run scripts/gen_recording_map.py)" >&2; exit 1; }
  # dma_mcp/validation.py imports the abbreviation list at load time: CG-27
  # reads it, and it is the same copy the api's evidence projection reads.
  cp packages/shared/abbreviations.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/abbreviations.py is missing" >&2; exit 1; }
  # The cached Cloud SQL Connector. Per-connection `Connector()` spends one
  # Cloud SQL ADMIN API request per connection, and under NullPool that is
  # one per checkout — measured as a 429 on
  # sqladmin.googleapis.com/.../connectSettings during a live firing on
  # 2026-08-31. Every service that opens a database connection needs this
  # copy, so a missing one is FATAL rather than a silent fallback.
  cp packages/shared/cloudsql.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/cloudsql.py is missing" >&2; exit 1; }
  # The platform fit engine. `get_platform_fit` computes from it and CG-30
  # re-runs it at submit, so a missing copy would take the tool down and the
  # gate with it -- the gate that exists because four definitions of one
  # number reached two clients.
  cp packages/shared/platform_fit.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/platform_fit.py is missing" >&2; exit 1; }
  # CG-49 refuses a client-visible absence that names this system's
  # machinery, and CG-50 asks whether a missing product name fell past a hard
  # clip. Both rules are shared with the api and the worker rather than
  # restated per image — a rule held in two places drifts.
  cp packages/shared/internal_ids.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/internal_ids.py is missing" >&2; exit 1; }
  cp packages/shared/excerpt_clip.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/excerpt_clip.py is missing" >&2; exit 1; }
  # The clip rule, shared with the worker so it is not held in two places.
  # `register_evidence` refuses a hard-clipped excerpt at the door; the
  # worker names a clipped CORPUS at the tier it arrives in. A missing copy
  # here takes registration down entirely -- which is the safe direction,
  # and deliberately so: the alternative was 4,461 clipped clauses reaching
  # a client with nothing saying they were cuts (MEM-0129, MEM-0143).
  cp packages/shared/excerpt_clip.py apps/mcp/shared/ || {
    echo "FATAL: packages/shared/excerpt_clip.py is missing" >&2; exit 1; }
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
  # THE OAUTH SECRETS, ALL THREE, EVERY DEPLOY.
  #
  # `--set-secrets` REPLACES the container's whole secret set — it does not
  # merge with what the previous revision carried. So a secret wired by hand
  # onto one revision is silently dropped by the next deploy, and the drop is
  # invisible until someone tries to sign in.
  #
  # That is exactly what happened. The client id was scripted here; the client
  # secret and the signing key were created later and bound by hand onto
  # revision 00101. Deploy 16 rolled 00102 from this script, which knew about
  # one of the three, and /authorize began answering
  #   "authorization server not configured: OAUTH_CLIENT_ID and
  #    OAUTH_SIGNING_KEY must be wired from Secret Manager"
  # — a connector that had been verified end-to-end 39/39 was broken by a
  # deploy that changed no code. Every one of the three is wired here now, so
  # the configuration lives in the repo rather than in a revision's history.
  #
  # Each is guarded on the secret existing: a project that has not created
  # them yet still deploys, and rung B of the gate answers 401 naming the
  # secret that is missing rather than failing the release.
  MCP_SECRETS="MCP_PATH_TOKEN=dmai-mcp-path-token:latest"
  MCP_OAUTH_MISSING=""
  for pair in "OAUTH_CLIENT_ID=dmai-oauth-client-id" \
              "OAUTH_CLIENT_SECRET=dmai-oauth-client-secret" \
              "OAUTH_SIGNING_KEY=dmai-oauth-signing-key"; do
    # `sm_name`, not `secret` — scripts/scan_secrets.py reads `secret=` as a
    # hardcoded credential assignment and fails the release. The scanner is
    # right to be blunt about that shape; the variable is what moves.
    var="${pair%%=*}"; sm_name="${pair#*=}"
    if gcloud secrets describe "$sm_name" --project="$PROJECT_ID" >/dev/null 2>&1; then
      gcloud secrets add-iam-policy-binding "$sm_name" \
        --project="$PROJECT_ID" \
        --member="serviceAccount:dmai-mcp@${SA_DOMAIN}" \
        --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
      MCP_SECRETS="${MCP_SECRETS},${var}=${sm_name}:latest"
    else
      MCP_OAUTH_MISSING="${MCP_OAUTH_MISSING} ${sm_name}"
    fi
  done
  if [ -z "$MCP_OAUTH_MISSING" ]; then
    say "svc_mcp: all three OAuth secrets wired from Secret Manager"
  else
    say "svc_mcp: claude.ai sign-in stays 401 —${MCP_OAUTH_MISSING} not present"
  fi
  gcloud run deploy dmai-mcp --source=apps/mcp \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-mcp@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-mcp@${PROJECT_ID}.iam;DB_NAME=dma_insights;MCP_SERVICE_URL=https://dmai-mcp-dukrne5v4a-uc.a.run.app" \
    --set-secrets="$MCP_SECRETS" \
    --memory=2Gi --cpu=2 \
    --concurrency=4 --timeout=900 --min-instances=1 --allow-unauthenticated --quiet
  # INGRESS IS OPEN; IDENTITY IS READ IN-APP (owner decision, 2026-08-20).
  #
  # History, kept because it is the reason the current shape is safe: this
  # deploy passed `--allow-unauthenticated` until 2026-08-16 while NOTHING
  # read the identity tokens the plugin dutifully sent — authentication
  # rested on the path token alone, a capability that says WHICH connector
  # and can never say WHO. The 2026-08-16 fix closed ingress at IAM. That
  # posture could not serve claude.ai's custom-connector client (it speaks
  # OAuth, not Google IAM), so on 2026-08-20 the owner directed: reachable
  # from claude.ai, any @zennify.com account authorised. Ingress reopened —
  # and this time every request's bearer IS read: dma_mcp/oauth_gate.py
  # verifies a Google-signed ID token (routine SA, or @zennify.com humans)
  # or a Google OAuth access token minted through the pre-registered
  # "DMA Insights" client (audience-checked, verified @zennify.com only).
  # The path token stays as defense in depth on the service path. The
  # domain/deployer invoker grants below are kept: harmless under open
  # ingress, and load-bearing again if ingress is ever re-closed.
  for member in "domain:${MCP_INVOKER_DOMAIN:-zennify.com}" \
                "serviceAccount:${MCP_INVOKER_SA:-claude-deployer@${PROJECT_ID}.iam.gserviceaccount.com}"; do
    gcloud run services add-iam-policy-binding dmai-mcp \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="$member" --role="roles/run.invoker" --quiet >/dev/null
  done
  # Prove it rather than assuming it, both directions: an ANONYMOUS request
  # must be refused BY THE APP with the OAuth challenge (401 + WWW-Authenticate
  # naming the resource metadata), and the discovery document must be public.
  mcp_url=$(gcloud run services describe dmai-mcp --project="$PROJECT_ID" \
      --region="$REGION" --format='value(status.url)')
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "${mcp_url}/mcp" \
      -H 'Content-Type: application/json' -d '{}' || echo 000)
  challenge=$(curl -s -o /dev/null -w '%{header_json}' -X POST "${mcp_url}/mcp" \
      -H 'Content-Type: application/json' -d '{}' | grep -c resource_metadata || true)
  meta=$(curl -s -o /dev/null -w '%{http_code}' \
      "${mcp_url}/.well-known/oauth-protected-resource" || echo 000)
  if [ "$code" = "401" ] && [ "$meta" = "200" ]; then
    say "svc_mcp: anonymous call refused in-app (401, challenge headers: ${challenge}); discovery public (200)"
  else
    echo "FATAL: dmai-mcp anonymous probe expected 401 with public discovery," \
         "got /mcp=$code metadata=$meta. The identity gate is not standing" \
         "where ingress is open. Refusing to call this deploy done." >&2; exit 1
  fi
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
  # Client share links (owner, 2026-10-07): an Ed25519 pair, created once.
  # The PRIVATE key is mounted on dmai-web only (it mints); the PUBLIC key on
  # dmai-share only (it verifies) — so the internet-facing service can never
  # mint a link. Generated here, never echoed, never written outside a 0700
  # temp dir that is removed before the next command. To revoke EVERY link at
  # once: add a new version of both secrets (same two openssl lines).
  if ! gcloud secrets describe dmai-share-signing-key --project="$PROJECT_ID" >/dev/null 2>&1; then
    KD="$(mktemp -d)"; chmod 700 "$KD"
    openssl genpkey -algorithm ed25519 -out "$KD/k.pem" 2>/dev/null
    openssl pkey -in "$KD/k.pem" -pubout -out "$KD/pub.pem" 2>/dev/null
    gcloud secrets create dmai-share-signing-key --project="$PROJECT_ID" \
      --data-file="$KD/k.pem" --quiet
    if gcloud secrets describe dmai-share-verify-key --project="$PROJECT_ID" >/dev/null 2>&1; then
      gcloud secrets versions add dmai-share-verify-key --project="$PROJECT_ID" \
        --data-file="$KD/pub.pem" --quiet
    else
      gcloud secrets create dmai-share-verify-key --project="$PROJECT_ID" \
        --data-file="$KD/pub.pem" --quiet
    fi
    rm -rf "$KD"
  fi
  gcloud secrets add-iam-policy-binding dmai-share-signing-key \
    --project="$PROJECT_ID" \
    --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  # The share service's URL follows the project's run.app pattern, so it is
  # known before the service exists; the share block below re-reads the real
  # URL and corrects dmai-web if the two ever differ.
  SHARE_BASE_URL="${API_URL/dmai-api/dmai-share}"
  # Role grants (allowlists until the auth stage's users table): ADMIN and
  # ANALYST are strictly these emails; every other @zennify.com Google
  # account signs in as AE. Override per deploy via the environment.
  ADMIN_EMAILS="${ADMIN_EMAILS:-mishley.otiende@zennify.com,dma@zennify.com}"
  ANALYST_EMAILS="${ANALYST_EMAILS:-mishley.otiende@zennify.com,dma@zennify.com}"
  PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  # The IAP assertion audience for THIS service — the app rejects
  # assertions minted for anything else.
  IAP_AUDIENCE="/projects/${PROJECT_NUMBER}/locations/${REGION}/services/dmai-web"

  # ── usage telemetry: web log lines → BigQuery ──────────────────────────
  #
  # The web service writes one structured stdout line per usage event
  # (apps/web/lib/usage.js: page views, heartbeats, feature actions, client
  # opens). A log sink routes ONLY those lines (jsonPayload.usage_v=1) into
  # the dmai_usage dataset, which Admin › Usage analytics reads through
  # /api/admin/usage. Nothing touches the application database: invariant 2
  # keeps the API's writes to annotations and alert actions.
  #
  # CONVERGE, TOLERANT. Every step reads first and writes only when the state
  # is wrong, and a step the deployer lacks the grant for (logging.configWriter,
  # bigquery.admin — infra/grants-for-admin.sh) warns and moves on: a release
  # must not abort over telemetry. The page states "not recording" until the
  # sink exists rather than showing an empty chart as if nobody came.
  #
  # Retention: 400-day partitions — a year of quarter-over-quarter adoption,
  # then gone. The sink only carries lines from its creation onward; there is
  # no backfill.
  USAGE_DATASET="${USAGE_DATASET:-dmai_usage}"
  USAGE_SINK="dmai-usage"
  usage_warn() { echo "  usage: WARN — $* (Usage analytics stays 'not recording' until fixed)" >&2; }
  gcloud services enable bigquery.googleapis.com --project="$PROJECT_ID" --quiet \
    >/dev/null 2>&1 || usage_warn "could not enable bigquery.googleapis.com"
  if ! bq --project_id="$PROJECT_ID" show --dataset "${PROJECT_ID}:${USAGE_DATASET}" >/dev/null 2>&1; then
    say "  usage: creating dataset ${USAGE_DATASET}"
    bq --project_id="$PROJECT_ID" mk --dataset --location="$REGION" \
      --default_partition_expiration=34560000 \
      --description="DMA Insights usage telemetry (web log sink). No client content." \
      "${PROJECT_ID}:${USAGE_DATASET}" >/dev/null 2>&1 \
      || usage_warn "could not create dataset ${USAGE_DATASET} (needs bigquery.admin)"
  fi
  USAGE_FILTER='resource.type="cloud_run_revision" AND resource.labels.service_name="dmai-web" AND jsonPayload.usage_v=1'
  USAGE_DEST="bigquery.googleapis.com/projects/${PROJECT_ID}/datasets/${USAGE_DATASET}"
  CUR_FILTER="$(gcloud logging sinks describe "$USAGE_SINK" --project="$PROJECT_ID" \
                 --format='value(filter)' 2>/dev/null || echo "__missing__")"
  if [ "$CUR_FILTER" = "__missing__" ]; then
    say "  usage: creating log sink ${USAGE_SINK}"
    gcloud logging sinks create "$USAGE_SINK" "$USAGE_DEST" --project="$PROJECT_ID" \
      --log-filter="$USAGE_FILTER" --use-partitioned-tables --quiet >/dev/null 2>&1 \
      || usage_warn "could not create log sink ${USAGE_SINK} (needs logging.configWriter)"
  elif [ "$CUR_FILTER" != "$USAGE_FILTER" ]; then
    say "  usage: correcting the ${USAGE_SINK} filter"
    gcloud logging sinks update "$USAGE_SINK" "$USAGE_DEST" --project="$PROJECT_ID" \
      --log-filter="$USAGE_FILTER" --quiet >/dev/null 2>&1 \
      || usage_warn "could not update log sink ${USAGE_SINK}"
  fi
  # The sink writes as its own identity; the web reads as dmai-web. Dataset-
  # scoped grants, plus the project-level jobUser BigQuery requires to run a
  # query at all.
  SINK_WRITER="$(gcloud logging sinks describe "$USAGE_SINK" --project="$PROJECT_ID" \
                  --format='value(writerIdentity)' 2>/dev/null || true)"
  DS_POLICY="$(bq --project_id="$PROJECT_ID" get-iam-policy --format=prettyjson \
                "${PROJECT_ID}:${USAGE_DATASET}" 2>/dev/null || true)"
  if [ -n "$SINK_WRITER" ] && ! printf '%s' "$DS_POLICY" | grep -q "${SINK_WRITER#serviceAccount:}"; then
    bq --project_id="$PROJECT_ID" add-iam-policy-binding --member="$SINK_WRITER" \
      --role=roles/bigquery.dataEditor "${PROJECT_ID}:${USAGE_DATASET}" >/dev/null 2>&1 \
      || usage_warn "could not grant the sink writer dataEditor on ${USAGE_DATASET}"
  fi
  if ! printf '%s' "$DS_POLICY" | grep -q "dmai-web@${SA_DOMAIN}"; then
    bq --project_id="$PROJECT_ID" add-iam-policy-binding \
      --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
      --role=roles/bigquery.dataViewer "${PROJECT_ID}:${USAGE_DATASET}" >/dev/null 2>&1 \
      || usage_warn "could not grant dmai-web dataViewer on ${USAGE_DATASET}"
  fi
  if ! gcloud projects get-iam-policy "$PROJECT_ID" \
       --flatten='bindings[].members' \
       --filter="bindings.role=roles/bigquery.jobUser AND bindings.members=serviceAccount:dmai-web@${SA_DOMAIN}" \
       --format='value(bindings.role)' 2>/dev/null | grep -q jobUser; then
    gcloud projects add-iam-policy-binding "$PROJECT_ID" \
      --member="serviceAccount:dmai-web@${SA_DOMAIN}" \
      --role=roles/bigquery.jobUser --condition=None --quiet >/dev/null 2>&1 \
      || usage_warn "could not grant dmai-web bigquery.jobUser"
  fi

  gcloud run deploy dmai-web --source=apps/web \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-web@${SA_DOMAIN}" \
    --set-env-vars="^;^API_URL=${API_URL};ADMIN_EMAILS=${ADMIN_EMAILS};ANALYST_EMAILS=${ANALYST_EMAILS};IAP_AUDIENCE=${IAP_AUDIENCE};GCP_PROJECT=${PROJECT_ID};GCP_REGION=${REGION};WORKER_JOB=dmai-worker;INTAKE_FOLDER_ID=${INTAKE_FOLDER_ID:-1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo};SHARE_BASE_URL=${SHARE_BASE_URL};USAGE_DATASET=${USAGE_DATASET}" \
    --set-secrets="SESSION_SECRET=dmai-session-secret:latest,SHARE_SIGNING_KEY=dmai-share-signing-key:latest" \
    --quiet
  # NO `--allow-unauthenticated` HERE, DELIBERATELY, AND NO
  # `--no-allow-unauthenticated` EITHER. On an existing service gcloud
  # touches the IAM policy only when one of those flags is given, so
  # omitting both leaves dmai-web's door to the converge block below —
  # which is the whole point of that block.
  #
  # MEASURED 2026-09-04. That block was rewritten on 2026-09-01 to "read
  # first and write only when the state is actually wrong", and it still
  # wrote on every single release: this command re-granted `allUsers` a few
  # lines earlier ("Setting IAM Policy...done" in the release log), so the
  # converge step always found it and always removed it again. One
  # guaranteed SetIamPolicy per release, on the door, while people are
  # using the app — exactly the churn behind the IAP "Error code: 11" a
  # user hit at 17:56:03 on 2026-09-01. The fix was two blocks away from
  # the thing that undid it.
  #
  # The posture is unchanged and is stated below rather than here: IAP
  # authenticates at the door and invokes as the IAP service agent, which
  # the converge block grants; direct public invocation stays closed.

  # ── Google sign-in at the door: Cloud Run integrated IAP ─────────────
  # Google authenticates every request (Google-managed OAuth client,
  # org-internal), the app verifies the forwarded assertion (lib/iap.js)
  # and enforces @zennify.com. Grants: the Workspace domain.
  #
  # CONVERGE, DO NOT RE-APPLY. This block said "IAP is configured once" and
  # then reconfigured it on every single release: enable the API, create the
  # service identity, bind the invoker, `services update --iap`, drop
  # allUsers, bind the domain — six writes to the door, unconditionally,
  # every deploy. MEASURED 2026-09-01: a user loading the app at 17:56:03
  # got IAP "Error code: 11 — incorrectly configured OAuth client ID" while
  # the audit log shows this block running ReplaceService at 17:56:18 and
  # three SetIamPolicy calls at 17:56:19, 17:56:22 and 17:56:25. The OAuth
  # client id was identical before and after; nothing was misconfigured. The
  # door was simply being rebuilt around someone standing in it.
  #
  # So each step now READS first and writes only when the state is actually
  # wrong. On the steady-state path this whole block is six describes and no
  # writes, and a release stops interrupting the people using the app.
  #
  # Each write still tolerates a permission failure: the deploy service
  # account may lack the org-level permission to enable the API or bind IAP
  # policy, and a release that has already rolled the services must not
  # abort on it.
  if ! gcloud services list --enabled --project="$PROJECT_ID" \
       --filter="config.name:iap.googleapis.com" --format='value(config.name)' \
       2>/dev/null | grep -q iap; then
    say "  iap: enabling the API (first time)"
    gcloud services enable iap.googleapis.com --project="$PROJECT_ID" --quiet || true
    gcloud beta services identity create --service=iap.googleapis.com \
      --project="$PROJECT_ID" --quiet >/dev/null 2>&1 || true
  fi

  IAP_SA="service-${PROJECT_NUMBER}@gcp-sa-iap.iam.gserviceaccount.com"
  WEB_POLICY="$(gcloud run services get-iam-policy dmai-web \
                --project="$PROJECT_ID" --region="$REGION" \
                --format=json 2>/dev/null || echo '{}')"
  if ! printf '%s' "$WEB_POLICY" | grep -q "$IAP_SA"; then
    say "  iap: granting the IAP service agent run.invoker"
    gcloud run services add-iam-policy-binding dmai-web \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="serviceAccount:${IAP_SA}" \
      --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
  fi

  # The one that took the door down. `--iap` on an already-IAP-enabled
  # service is a no-op in intent and a ReplaceService in fact.
  IAP_ON="$(gcloud run services describe dmai-web \
            --project="$PROJECT_ID" --region="$REGION" \
            --format='value(metadata.annotations."run.googleapis.com/iap-enabled")' \
            2>/dev/null || true)"
  if [ "$IAP_ON" != "true" ]; then
    say "  iap: enabling on dmai-web (currently '${IAP_ON:-unset}')"
    gcloud run services update dmai-web \
      --project="$PROJECT_ID" --region="$REGION" --iap --quiet || true
  fi

  # Direct (non-IAP) invocation stays closed: drop the public grant, but
  # only if it is actually there — removing a binding that does not exist
  # is still a SetIamPolicy write.
  if printf '%s' "$WEB_POLICY" | grep -q "allUsers"; then
    say "  iap: removing the public invoker grant"
    gcloud run services remove-iam-policy-binding dmai-web \
      --project="$PROJECT_ID" --region="$REGION" \
      --member="allUsers" --role="roles/run.invoker" --quiet >/dev/null 2>&1 || true
  fi

  # Who may pass Google's door: the Zennify workspace. (Tolerant: this
  # org-level grant may require an admin; a release must not abort on it.)
  if ! gcloud iap web get-iam-policy --project="$PROJECT_ID" \
       --resource-type=cloud-run --service=dmai-web --region="$REGION" \
       --format=json 2>/dev/null | grep -q "domain:zennify.com"; then
    say "  iap: granting zennify.com access"
    gcloud iap web add-iam-policy-binding \
      --project="$PROJECT_ID" --resource-type=cloud-run \
      --service=dmai-web --region="$REGION" \
      --member="domain:zennify.com" --role="roles/iap.httpsResourceAccessor" \
      --quiet >/dev/null 2>&1 || true
  fi

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

# --- 2a · dmai-share (public client links; owner, 2026-10-07) ------------
# The SAME image dmai-web just shipped, with SHARE_MODE=1: every route but
# /s/<token>… answers 404 there (apps/web/tests/share-link.test.js fails CI
# on a route that forgets). Ingress is open — a client has no Zennify login —
# and identity is read in-app: a link signed by the key only dmai-web holds,
# bound to one client and run, expiring, revocable, admitting only the email
# addresses and organisation domains it was shared to. Its own service
# account holds exactly two grants: invoke svc_api, read the PUBLIC key.
if [ -f apps/web/Dockerfile ]; then
  say "share (public client links)"
  SHARE_SA="dmai-share@${SA_DOMAIN}"
  if ! gcloud iam service-accounts describe "$SHARE_SA" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud iam service-accounts create dmai-share --project="$PROJECT_ID" \
      --display-name="DMA Insights public share links" --quiet || {
      echo "FATAL: cannot create the dmai-share service account. A project owner" \
           "runs once: gcloud iam service-accounts create dmai-share --project=$PROJECT_ID" >&2
      exit 1; }
  fi
  gcloud secrets add-iam-policy-binding dmai-share-verify-key \
    --project="$PROJECT_ID" --member="serviceAccount:${SHARE_SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
  gcloud run services add-iam-policy-binding dmai-api \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:${SHARE_SA}" --role="roles/run.invoker" --quiet >/dev/null
  # The admission cookie's HMAC key (lib/share signAccess): generated here,
  # never echoed, readable by dmai-share alone.
  if ! gcloud secrets describe dmai-share-cookie-secret --project="$PROJECT_ID" >/dev/null 2>&1; then
    head -c 48 /dev/urandom | base64 | gcloud secrets create dmai-share-cookie-secret \
      --project="$PROJECT_ID" --data-file=- --quiet
  fi
  gcloud secrets add-iam-policy-binding dmai-share-cookie-secret \
    --project="$PROJECT_ID" --member="serviceAccount:${SHARE_SA}" \
    --role="roles/secretmanager.secretAccessor" --quiet >/dev/null

  # ── One-time sign-in links: Google Cloud Identity Platform (owner,
  # 2026-10-07). Google emails the recipient a single-use link; nothing is
  # admitted until it is followed. Converged every release, tolerant of a
  # deployer that lacks a permission — but the OUTCOME is never silent: OTP
  # is switched on only when the live config reads back correct, and
  # otherwise the release says, loudly, that links admit typed addresses.
  SHARE_HOST="${SHARE_BASE_URL#https://}"
  IDP="https://identitytoolkit.googleapis.com"
  gcloud services enable identitytoolkit.googleapis.com apikeys.googleapis.com \
    --project="$PROJECT_ID" --quiet >/dev/null 2>&1 || true
  AT="$(gcloud auth print-access-token 2>/dev/null || true)"
  idp() { curl -s -H "Authorization: Bearer ${AT}" -H "x-goog-user-project: ${PROJECT_ID}" \
            -H "content-type: application/json" "$@"; }
  idp -X POST "${IDP}/v2/projects/${PROJECT_ID}/identityPlatform:initializeAuth" -d '{}' >/dev/null || true
  if ! gcloud secrets describe dmai-share-idp-api-key --project="$PROJECT_ID" >/dev/null 2>&1; then
    # An API key identifies the project to Identity Platform and is
    # restricted to that one API; it is still kept in Secret Manager.
    key_name() { gcloud services api-keys list --project="$PROJECT_ID" \
      --filter="displayName='DMA share sign-in'" --format='value(name)' \
      --limit=1 2>/dev/null || true; }
    KEY_NAME="$(key_name)"
    if [ -z "$KEY_NAME" ]; then
      gcloud services api-keys create --project="$PROJECT_ID" \
        --display-name="DMA share sign-in" \
        --api-target=service=identitytoolkit.googleapis.com --quiet >/dev/null 2>&1 || true
      KEY_NAME="$(key_name)"
    fi
    if [ -n "$KEY_NAME" ]; then
      # Held in a variable for one command, never echoed; an empty read
      # creates nothing rather than an empty secret.
      KS="$(gcloud services api-keys get-key-string "$KEY_NAME" --project="$PROJECT_ID" \
        --format='value(keyString)' 2>/dev/null || true)"
      if [ -n "$KS" ]; then
        printf '%s' "$KS" | gcloud secrets create dmai-share-idp-api-key \
          --project="$PROJECT_ID" --data-file=- --quiet >/dev/null 2>&1 || true
      fi
      unset KS
    fi
  fi
  # Email link (passwordless) on; the share host authorised; Google's
  # emailed link pointed at this service's own handler (/s/auth-action).
  CFG="$(idp "${IDP}/admin/v2/projects/${PROJECT_ID}/config" || true)"
  PATCH="$(printf '%s' "$CFG" | SHARE_HOST="$SHARE_HOST" SHARE_BASE_URL="$SHARE_BASE_URL" python3 -c '
import json, os, sys
try: c = json.load(sys.stdin)
except Exception: c = {}
doms = list(c.get("authorizedDomains") or [])
if os.environ["SHARE_HOST"] and os.environ["SHARE_HOST"] not in doms: doms.append(os.environ["SHARE_HOST"])
print(json.dumps({"signIn": {"email": {"enabled": True, "passwordRequired": False}},
  "authorizedDomains": doms,
  "notification": {"sendEmail": {"callbackUri": os.environ["SHARE_BASE_URL"] + "/s/auth-action"}}}))')"
  idp -X PATCH "${IDP}/admin/v2/projects/${PROJECT_ID}/config?updateMask=signIn.email.enabled,signIn.email.passwordRequired,authorizedDomains,notification.sendEmail.callbackUri" \
    -d "$PATCH" >/dev/null || true
  IDP_OK="$(idp "${IDP}/admin/v2/projects/${PROJECT_ID}/config" | SHARE_HOST="$SHARE_HOST" python3 -c '
import json, os, sys
try: c = json.load(sys.stdin)
except Exception: print("no"); sys.exit()
e = (c.get("signIn") or {}).get("email") or {}
ok = e.get("enabled") and not e.get("passwordRequired") and os.environ["SHARE_HOST"] in (c.get("authorizedDomains") or [])
print("yes" if ok else "no")' || echo no)"
  SHARE_SECRETS="SHARE_VERIFY_KEY=dmai-share-verify-key:latest,SHARE_COOKIE_SECRET=dmai-share-cookie-secret:latest"
  if [ "$IDP_OK" = "yes" ] && gcloud secrets describe dmai-share-idp-api-key --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud secrets add-iam-policy-binding dmai-share-idp-api-key \
      --project="$PROJECT_ID" --member="serviceAccount:${SHARE_SA}" \
      --role="roles/secretmanager.secretAccessor" --quiet >/dev/null
    SHARE_SECRETS="${SHARE_SECRETS},SHARE_IDP_API_KEY=dmai-share-idp-api-key:latest"
    say "  share: one-time sign-in links ON (Identity Platform, ${SHARE_HOST} authorised)"
  else
    echo "WARNING: share links are admitting TYPED addresses — one-time sign-in is OFF." >&2
    echo "  Identity Platform could not be configured by this deployer. A project owner, once:" >&2
    echo "  Console > Identity Platform > Enable; Providers > Email/Password > enable," >&2
    echo "  'Email link (passwordless sign-in)'; Settings > Authorized domains > add ${SHARE_HOST};" >&2
    echo "  then the next release creates the API key and switches OTP on." >&2
  fi
  WEB_IMAGE="$(gcloud run services describe dmai-web --project="$PROJECT_ID" \
    --region="$REGION" --format='value(spec.template.spec.containers[0].image)')"
  # One link at a time: list its jti (shown in the share dialog and in the
  # share_link_minted log line) in infra/share-revoked.txt and release.
  SHARE_REVOKED="$(grep -v '^[[:space:]]*#' infra/share-revoked.txt 2>/dev/null \
    | tr -d '[:space:]' | paste -sd, - || true)"
  gcloud run deploy dmai-share --image="$WEB_IMAGE" \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="$SHARE_SA" \
    --set-env-vars="^;^API_URL=${API_URL};SHARE_MODE=1;SHARE_REVOKED_JTIS=${SHARE_REVOKED}" \
    --set-secrets="$SHARE_SECRETS" \
    --min-instances=0 --max-instances=10 --concurrency=80 \
    --allow-unauthenticated --quiet
  share_url="$(gcloud run services describe dmai-share --project="$PROJECT_ID" \
    --region="$REGION" --format='value(status.url)')"
  if [ "$share_url" != "$SHARE_BASE_URL" ]; then
    say "  share: correcting dmai-web SHARE_BASE_URL to ${share_url}"
    gcloud run services update dmai-web --project="$PROJECT_ID" --region="$REGION" \
      --update-env-vars="SHARE_BASE_URL=${share_url}" --quiet
  fi
  # Prove the door, both directions, or refuse to call this release done:
  # the app's own routes must not exist on the public service, a junk link
  # must be refused, and the static bundle must be served.
  bad=""
  for probe in "GET /" "POST /api/signin" "POST /api/share" "GET /status" \
               "GET /api/entity/x/overview?audience=internal" "GET /s/not-a-token"; do
    m="${probe%% *}"; u="${probe#* }"
    c=$(curl -s -o /dev/null -w '%{http_code}' -X "$m" "${share_url}${u}" || echo 000)
    [ "$c" = "404" ] || bad="${bad} ${probe}=${c}"
  done
  c=$(curl -s -o /dev/null -w '%{http_code}' "${share_url}/proto/app.css" || echo 000)
  [ "$c" = "200" ] || bad="${bad} GET /proto/app.css=${c}"
  if [ -n "$bad" ]; then
    echo "FATAL: dmai-share door probe failed:${bad}. The public service is" \
         "answering something other than client links. Refusing to call this" \
         "deploy done." >&2; exit 1
  fi
  say "share: public, client links only — app routes 404, junk link 404, bundle 200 (${share_url})"
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
  # The cached Cloud SQL Connector. Per-connection `Connector()` spends one
  # Cloud SQL ADMIN API request per connection, and under NullPool that is
  # one per checkout — measured as a 429 on
  # sqladmin.googleapis.com/.../connectSettings during a live firing on
  # 2026-08-31. Every service that opens a database connection needs this
  # copy, so a missing one is FATAL rather than a silent fallback.
  cp packages/shared/cloudsql.py apps/worker/shared/ || {
    echo "FATAL: packages/shared/cloudsql.py is missing" >&2; exit 1; }
  cp packages/shared/enrichment_gaps.py apps/worker/shared/ || {
    echo "FATAL: packages/shared/enrichment_gaps.py is missing" >&2; exit 1; }
  cp packages/shared/contracts_data.json apps/worker/shared/ || {
    echo "FATAL: packages/shared/contracts_data.json is missing" >&2; exit 1; }
  # The clip rule. The package parse is where clipped evidence ENTERS the
  # system -- it never passes register_evidence -- so a worker that cannot
  # import this must not read a corpus in silence.
  cp packages/shared/excerpt_clip.py apps/worker/shared/ || {
    echo "FATAL: packages/shared/excerpt_clip.py is missing" >&2; exit 1; }
  gcloud run jobs deploy dmai-worker --source=apps/worker \
    --project="$PROJECT_ID" --region="$REGION" \
    --service-account="dmai-worker@${SA_DOMAIN}" \
    --network=default --subnet=default --vpc-egress=private-ranges-only \
    --set-env-vars="^;^DB_INSTANCE_CONNECTION_NAME=${PROJECT_ID}:${REGION}:dmai-pg;DB_USER=dmai-worker@${PROJECT_ID}.iam;DB_NAME=dma_insights;INTAKE_FOLDER_ID=${INTAKE_FOLDER_ID:-1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo};MAX_PACKAGES=${MAX_PACKAGES:-10};EVIDENCE_REPAIR_ONLY=${EVIDENCE_REPAIR_ONLY-Golden 1}" \
    --max-retries=0 --task-timeout=3600 --memory=2Gi --cpu=2 --quiet
  # EVIDENCE_REPAIR_ONLY NAMES THE ONE CLIENT THE EVIDENCE REPAIR MAY TOUCH.
  #
  # The pass fills a null `source_url` from the client's own workbook. Its
  # first production firing (2026-09-04T13:13:20Z) reported `99 run(s)` of
  # work across the corpus and started at the top of the alphabet — 1st
  # Security Bank, Amalgamated, ATB — none of which anybody had asked about.
  # Owner's instruction the same day: strictly Golden 1, do not add clients.
  #
  # It is set HERE rather than by hand because `--set-env-vars` replaces the
  # whole set: a value bound onto one execution is dropped by the very next
  # release, silently. Unset (`EVIDENCE_REPAIR_ONLY=`) turns the pass OFF; it
  # does not widen it to everyone. To repair a different client, name it —
  # deliberately, one client at a time.
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
  # THE GRANT THE SCHEDULER NEEDS TO RUN WHAT WAS JUST DEPLOYED. Every other
  # job here gets one — dmai-worker, dmai-refresh, and the exporter/scanner
  # pair in the loop below — and dmai-enrich was the single one that did not.
  # Deploying a job does not make it runnable: the scheduler below posts to
  # the Run Admin API as dmai-worker@, and without run.invoker on THIS job
  # that POST is PERMISSION_DENIED.
  #
  # Measured 2026-08-21: dmai-enrich-loop had been ENABLED and failing with
  # status code 7 on every hourly firing, while `gcloud run jobs get-iam-policy
  # dmai-enrich` returned no bindings at all. Nothing surfaced it, because a
  # scheduler job that fails still reads as ENABLED and the enrichment loop's
  # own failure mode is silence — it looks identical to a loop with nothing to
  # do. Granted by hand to stop the bleeding; here so it survives the next
  # rebuild.
  gcloud run jobs add-iam-policy-binding dmai-enrich \
    --project="$PROJECT_ID" --region="$REGION" \
    --member="serviceAccount:dmai-worker@${SA_DOMAIN}" \
    --role="roles/run.invoker" --quiet >/dev/null
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

# ── READY IS NOT WORKING: probe a route that opens a connection ──────
#
# On 2026-08-31 this script exited 0 with all three services Ready, 100% of
# traffic on the new revisions, and verify_deployed.py reporting "MATCH —
# every compiled module in production is byte-identical to a local build of
# HEAD". Every word of that was true. The next afternoon dmai-api answered
# /v1/directory, /v1/catalogue and /v1/ops/import-scans with a 504 after the
# full 300-second request timeout, because its Cloud SQL Connector was built
# with the default background refresh and a CPU-throttled instance has no CPU
# to advance that timer with. The bytes were right; the service was dead.
#
# So the probe hits a route that OPENS A DATABASE CONNECTION. /healthz stayed
# green through the entire outage — it touches nothing — which is exactly why
# it is the wrong thing to ask.
#
# A refusal is reported as a refusal, never as a pass: an operator whose
# account cannot invoke dmai-api gets NOT PROBED with the reason, in the
# shape the gates use, rather than silence that reads like success.
if command -v curl >/dev/null 2>&1; then
  say "smoke: does the api still reach the database?"
  API_URL="$(gcloud run services describe dmai-api --project="$PROJECT_ID" \
             --region="$REGION" --format='value(status.url)' 2>/dev/null || true)"
  SMOKE_TOKEN="$(gcloud auth print-identity-token \
                 --audiences="$API_URL" 2>/dev/null || true)"
  if [ -z "$API_URL" ] || [ -z "$SMOKE_TOKEN" ]; then
    echo "   NOT PROBED — no api URL or no identity token for this account"
  else
    # 45s, not 300: a healthy connection is milliseconds and the failure
    # being watched for is an unbounded hang, so waiting out Cloud Run's
    # whole request timeout only makes the report slower, never truer.
    SMOKE_CODE="$(curl -s -o /dev/null -m 45 -w '%{http_code}' \
                  -H "Authorization: Bearer $SMOKE_TOKEN" \
                  "$API_URL/v1/directory?audience=internal&limit=1" || echo 000)"
    case "$SMOKE_CODE" in
      200) echo "   OK — /v1/directory 200 (the api reached the database)" ;;
      401|403) echo "   NOT PROBED — this account cannot invoke dmai-api ($SMOKE_CODE)" ;;
      000) echo "!! /v1/directory did not answer in 45s — the api is not serving" >&2 ;;
      *)   echo "!! /v1/directory answered $SMOKE_CODE — the api is not serving" >&2 ;;
    esac
  fi
fi

say "deployed. Service URLs:"
gcloud run services list --project="$PROJECT_ID" --region="$REGION" \
  --filter="metadata.name:dmai-" --format='value(metadata.name,status.url)' || true
