################################################################
# DMA Insights — Cloud Run + Cloud SQL + Pub/Sub + Scheduler
#
# This is the canonical IaC. Apply with:
#   terraform init -backend-config="bucket=$PROJECT_ID-tfstate"
#   terraform plan -var "image_sha=<SHA>"
#   terraform apply
#
# Locked decisions (per ADR 0001-0009):
#   - 4 Cloud Run services (frontend, backend, rag-api, sse-api)
#   - 4 Cloud Run Jobs (drive_crawler, sheet_poller, embedder,
#     ccg_loader) sharing one worker image (command differs)
#   - Cloud SQL Postgres 15 with pgvector + pgcrypto extensions
#   - Upstash Redis (managed, regional) referenced by URL secret
#   - Secret Manager for all keys (OAuth, bot, RAG, Vertex SA)
#   - Cloud Scheduler triggers: drive_crawler every 6h; sheet_poller
#     every 5min during business hours, else hourly; ccg_loader
#     hourly poll of catalogue-staging bucket
################################################################

terraform {
  required_version = ">= 1.9"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.7"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }
  backend "gcs" {
    prefix = "dma-insights/terraform"
  }
}

variable "project_id" {
  type        = string
  description = "GCP project ID (e.g. digital-maturity-assessor). Defaults to the Zennify DMA project."
  default     = "digital-maturity-assessor"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = <<-EOT
      project_id must be a valid GCP project ID (lowercase letters, digits, hyphens; 6-30 chars).
      Did you accidentally type 'latest'?
      Get the correct value with:  gcloud config get-value project
    EOT
  }

  # Defence-in-depth blocklist of common typos that ALSO satisfy the
  # generic regex (e.g. 'latest' is 6 chars of lowercase letters).
  # If you actually need a project literally called one of these, add
  # it here AND tell the on-call you're doing so — these names are
  # almost always image-tag aliases pasted into the wrong field.
  validation {
    condition = !contains(
      ["latest", "head", "main", "master", "current", "stable", "production"],
      var.project_id,
    )
    error_message = <<-EOT
      project_id='${var.project_id}' is a tag-alias word, not a GCP project ID.
      You almost certainly meant to pass this to `-var image_sha=...` (image tag) or to set the right project first.
      Run: gcloud config get-value project    # to print the real project id
    EOT
  }
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "image_sha" {
  type        = string
  description = "7-40 char hex git SHA of the container images to deploy (e.g. 0ae9b20). Get with: git rev-parse --short HEAD"

  validation {
    condition     = can(regex("^[0-9a-f]{7,40}$", var.image_sha))
    error_message = <<-EOT
      image_sha must be a 7-40 character lowercase hex git SHA.
      Did you accidentally type 'latest'?
      Get the correct value with:  git rev-parse --short HEAD
    EOT
  }
}

variable "google_oauth_client_id" {
  type        = string
  description = "OAuth 2.0 web-client ID for Google sign-in. Public (also baked into the frontend bundle); must match the value rendered by the GIS button so the JWT `aud` claim verifies on the backend."
  default     = "306195530103-ub6t46i8sd9q1eatpt6dgo0i9811mnrp.apps.googleusercontent.com"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Cloud SQL ──────────────────────────────────────────────────────
resource "google_sql_database_instance" "pg" {
  name             = "dma-insights-pg"
  database_version = "POSTGRES_15"
  region           = var.region
  settings {
    tier              = "db-custom-2-7680"
    availability_type = "REGIONAL"
    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
    insights_config {
      query_insights_enabled  = true
      record_application_tags = true
    }
  }
  deletion_protection = true
}

resource "google_sql_database" "main" {
  name     = "dma_insights"
  instance = google_sql_database_instance.pg.name
}

# ── App-user password + DSN-in-Secret-Manager (end-to-end) ──────────
# Generates a strong password for the `dma_insights` Postgres user,
# (re)sets it via gcloud, and stores the full DSN in Secret Manager so
# the Cloud Run backend's DATABASE_URL env var can source it. One
# `terraform apply` does the whole chain — no operator script needed.
#
# `special = false` so the password is URL-safe (no `:`, `@`, `/` to
# encode inside the DSN). 32 chars of alphanumerics = ~190 bits of
# entropy, well above any reasonable threshold for a 1-tenant DB.
resource "random_password" "db_app_user" {
  length  = 32
  special = false
}

# Idempotent create-or-reset via gcloud — `google_sql_user` would 409
# on a pre-existing user (e.g. from a previous deploy attempt), so we
# use a null_resource provisioner that handles both cases.
# Triggers re-run whenever the password rotates OR the instance is
# rebuilt — the local-exec is deterministic so re-runs are safe.
#
# Requires gcloud on the terraform executor. Cloud Shell ships with
# gcloud + ADC; for non-Cloud-Shell runs the operator's ADC user must
# have roles/cloudsql.admin on the project.
resource "null_resource" "db_app_user_setup" {
  triggers = {
    instance      = google_sql_database_instance.pg.name
    password_hash = sha256(random_password.db_app_user.result)
  }
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      DMA_PW       = random_password.db_app_user.result
      DMA_INSTANCE = google_sql_database_instance.pg.name
    }
    command = <<-EOT
      set -euo pipefail
      # Try create; on 409 (user exists), reset the password instead.
      if ! gcloud sql users create dma_insights \
            --instance="$DMA_INSTANCE" --password="$DMA_PW" 2>/tmp/sql_create_err; then
        if grep -qi 'already exists\|HTTPError 409' /tmp/sql_create_err; then
          gcloud sql users set-password dma_insights \
            --instance="$DMA_INSTANCE" --password="$DMA_PW"
        else
          cat /tmp/sql_create_err >&2
          exit 1
        fi
      fi
    EOT
  }
  depends_on = [google_sql_database.main]
}

# The full DSN — including the password — lives in Secret Manager. The
# backend's DATABASE_URL env sources it via secret_key_ref so the
# password never ends up in Terraform state, Cloud Run config, or
# logs. (Secret Manager values ARE recorded in TF state by Terraform
# itself, but only the secret resource's ID; the version content is
# write-only and never re-read.)
resource "google_secret_manager_secret" "database_url" {
  secret_id = "dma-insights-database-url"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url" {
  secret      = google_secret_manager_secret.database_url.id
  secret_data = "postgresql+asyncpg://dma_insights:${random_password.db_app_user.result}@/dma_insights?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"

  depends_on = [null_resource.db_app_user_setup]

  lifecycle {
    create_before_destroy = true
  }
}

# ── dma-insights-database-url-sync (psycopg form for sync code paths) ──
#
# Workers + backend need a SYNC DSN (psycopg, not asyncpg) for paths
# that can't use async — job_executions lifecycle UPDATEs from worker
# processes, synthesis_cache invalidation post-commit hooks, and
# ccg_loader's `_persist_loader_run` writes.
#
# Same credentials as `dma-insights-database-url` — only the driver
# suffix differs. The application code has a `resolve_sync_dsn()` helper
# that derives the +psycopg form from `DATABASE_URL` at runtime if
# this secret isn't injected (fallback for older deploys + tests),
# but injecting the secret explicitly is the architecturally clean
# path: it makes the requirement visible in the Cloud Run env, and
# tools like `gcloud run services describe ...` show it without
# needing to read application code.
#
# Production-readiness contract: every job/service that calls a sync
# DB helper MUST inject this secret. The `resolve_sync_dsn` fallback
# stays as belt-and-braces in case a future operator unsets one of
# the env_from refs.
resource "google_secret_manager_secret" "database_url_sync" {
  secret_id = "dma-insights-database-url-sync"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url_sync" {
  secret      = google_secret_manager_secret.database_url_sync.id
  secret_data = "postgresql+psycopg://dma_insights:${random_password.db_app_user.result}@/dma_insights?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"

  depends_on = [null_resource.db_app_user_setup]

  lifecycle {
    create_before_destroy = true
  }
}

# ── postgres superuser password + DSN (for migrations only) ─────────
# Migrations need superuser privileges to create extensions (pgvector
# requires `cloudsqlsuperuser` role, which `postgres` has by default
# in Cloud SQL). The app user `dma_insights` doesn't — it can only
# CRUD/DDL within `public` after post_migrate grants. So we manage
# two passwords: one for the app, one for migrations.
#
# The migrations DSN uses `postgresql+psycopg://` (sync, psycopg3)
# because alembic + asyncpg don't mix — alembic is sync.
resource "random_password" "db_superuser" {
  length  = 32
  special = false
}

resource "null_resource" "db_superuser_setup" {
  triggers = {
    instance      = google_sql_database_instance.pg.name
    password_hash = sha256(random_password.db_superuser.result)
  }
  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    environment = {
      PG_PW        = random_password.db_superuser.result
      DMA_INSTANCE = google_sql_database_instance.pg.name
    }
    # `postgres` always exists in Cloud SQL — just reset its password.
    command = <<-EOT
      set -euo pipefail
      gcloud sql users set-password postgres --instance="$DMA_INSTANCE" --password="$PG_PW"
    EOT
  }
  depends_on = [google_sql_database.main]
}

resource "google_secret_manager_secret" "database_url_superuser" {
  secret_id = "dma-insights-database-url-superuser"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "database_url_superuser" {
  secret      = google_secret_manager_secret.database_url_superuser.id
  secret_data = "postgresql+psycopg://postgres:${random_password.db_superuser.result}@/dma_insights?host=/cloudsql/${google_sql_database_instance.pg.connection_name}"

  depends_on = [null_resource.db_superuser_setup]

  lifecycle {
    create_before_destroy = true
  }
}

# ── JWT signing key (RS256 private key in Secret Manager) ───────────
# Generated once by terraform (tls_private_key — pure-Go, no external
# tooling needed). Stored in Secret Manager; backend Cloud Run mounts
# the value as env JWT_PRIVATE_KEY_PEM. The matching public key is
# derived from the private key at backend boot (jwt_service.py), so
# there's only one secret to manage + no key-pair drift.
resource "tls_private_key" "jwt_signing" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "google_secret_manager_secret" "jwt_signing_key" {
  secret_id = "dma-insights-jwt-signing-key"
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "jwt_signing_key" {
  secret      = google_secret_manager_secret.jwt_signing_key.id
  secret_data = tls_private_key.jwt_signing.private_key_pem

  lifecycle {
    create_before_destroy = true
  }
}

# ── Secret Manager handles ──────────────────────────────────────────
# These secrets are created out-of-band in deployment §4 (gcloud
# secrets create) so the values never sit in Terraform state. The
# Cloud Run env blocks below reference them by name; Terraform does
# NOT own the secret resources. To rotate, run `gcloud secrets
# versions add` and the Cloud Run revision restarts automatically
# because env_vars use `version = "latest"`.
#
# (Optional later hardening: `terraform import google_secret_manager_secret.X …`
#  to bring them under TF management, but that's only needed if you
#  want TF to enforce replication policy / labels.)

# ── Pub/Sub topic for ingest → embedder + intelligence_recompute ────
resource "google_pubsub_topic" "ingest_completed" {
  name = "dma.ingest.completed"
}

# Embedder subscription — the embedder worker subscribes here with
# --subscribe; one job per ingest dispatches embed_run().
resource "google_pubsub_subscription" "ingest_completed_embedder" {
  name  = "dma-ingest-completed-embedder"
  topic = google_pubsub_topic.ingest_completed.name

  ack_deadline_seconds       = 60
  message_retention_duration = "604800s" # 7 days

  expiration_policy {
    ttl = "" # never expire — long-lived subscription
  }
}

# Intelligence-recompute subscription — workers/intelligence_recompute
# subscribes here; on each message it recomputes the entity's
# customer_intelligence_profiles row (Vertex Pro summary + embedding).
resource "google_pubsub_subscription" "ingest_completed_intelligence" {
  name  = "dma-ingest-completed-intelligence"
  topic = google_pubsub_topic.ingest_completed.name

  ack_deadline_seconds       = 300 # Vertex calls can take ~minute
  message_retention_duration = "604800s"

  expiration_policy {
    ttl = ""
  }
}

# ── Hard image-existence precondition ────────────────────────────────
# Before any Cloud Run service / job is updated, assert that all three
# images exist in gcr.io at the requested image_sha. If they don't,
# the apply fails *before* any half-rolled revision is created — which
# avoids the 30–60s-per-resource rollback the operator was hitting.
#
# Uses google_artifact_registry_docker_image; gcr.io is backed by an
# Artifact Registry "gcr.io" repo in us. Failed lookup => null =>
# precondition fires.
data "google_artifact_registry_docker_image" "backend" {
  project       = var.project_id
  location      = "us"
  repository_id = "gcr.io"
  image_name    = "dma-insights-backend:${var.image_sha}"

  lifecycle {
    postcondition {
      condition     = self.image_size_bytes > 0
      error_message = "Image gcr.io/${var.project_id}/dma-insights-backend:${var.image_sha} not found. Run: gcloud builds submit apps/dma-insights/ --config apps/dma-insights/infra/cloudbuild.yaml --substitutions=_IMAGE_SHA=${var.image_sha}"
    }
  }
}

data "google_artifact_registry_docker_image" "frontend" {
  project       = var.project_id
  location      = "us"
  repository_id = "gcr.io"
  image_name    = "dma-insights-frontend:${var.image_sha}"

  lifecycle {
    postcondition {
      condition     = self.image_size_bytes > 0
      error_message = "Image gcr.io/${var.project_id}/dma-insights-frontend:${var.image_sha} not found. Run: gcloud builds submit apps/dma-insights/ --config apps/dma-insights/infra/cloudbuild.yaml --substitutions=_IMAGE_SHA=${var.image_sha}"
    }
  }
}

data "google_artifact_registry_docker_image" "workers" {
  project       = var.project_id
  location      = "us"
  repository_id = "gcr.io"
  image_name    = "dma-insights-workers:${var.image_sha}"

  lifecycle {
    postcondition {
      condition     = self.image_size_bytes > 0
      error_message = "Image gcr.io/${var.project_id}/dma-insights-workers:${var.image_sha} not found. Run: gcloud builds submit apps/dma-insights/ --config apps/dma-insights/infra/cloudbuild.yaml --substitutions=_IMAGE_SHA=${var.image_sha}"
    }
  }
}

# ── Cloud Run service: backend (FastAPI) ────────────────────────────
resource "google_cloud_run_v2_service" "backend" {
  # Two hard preconditions:
  #   (1) The backend image must exist in gcr.io at the requested SHA
  #       — refuses to roll an unrunnable revision.
  #   (2) The dma-insights-database-url Secret Manager *version* must
  #       exist — otherwise Cloud Run rejects the env source with
  #       "Secret … versions/latest was not found".
  depends_on = [
    data.google_artifact_registry_docker_image.backend,
    google_secret_manager_secret_version.database_url,
    google_secret_manager_secret_version.jwt_signing_key,
  ]
  name     = "dma-insights-backend"
  location = var.region
  # Allow Terraform to recreate the service when a revision is
  # tainted (e.g. created with a missing image during a half-failed
  # apply). Production rollbacks go via `gcloud run services
  # update-traffic` against a prior revision, not via destroy.
  deletion_protection = false
  template {
    containers {
      image = "gcr.io/${var.project_id}/dma-insights-backend:${var.image_sha}"
      ports {
        container_port = 8000
      }
      env {
        name  = "VERTEX_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "VERTEX_LOCATION"
        value = var.region
      }
      env {
        # Full DSN lives in Secret Manager — includes the dma_insights
        # user's password. Format the operator must store:
        #
        #   postgresql+asyncpg://dma_insights:<PW>@/dma_insights?host=/cloudsql/<connection_name>
        #
        # where <PW> is URL-encoded and <connection_name> is
        # `${PROJECT}:${REGION}:dma-insights-pg`. See DEPLOYMENT.md §7
        # for the one-shot script that generates the password, sets
        # it on the user, builds the DSN, and stores the secret.
        #
        # Why a secret (not a static value with a separate password
        # env): Cloud Run env entries are EITHER a literal `value` OR
        # a `value_source`, never both, so we can't interpolate a
        # secret into a templated string at deploy time. Storing the
        # whole DSN is the only way to keep the password out of TF
        # state + Cloud Run config.
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-database-url"
            version = "latest"
          }
        }
      }
      # 2026-05-28: backend also calls sync DB helpers (post-commit
      # synthesis_cache invalidation, startup_diagnostic). The
      # resolver fallback makes this optional but explicit injection
      # is the durable path. See workers env block (~line 808) for
      # the full rationale.
      env {
        name = "DATABASE_URL_SYNC"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-database-url-sync"
            version = "latest"
          }
        }
      }
      env {
        name = "REDIS_URL"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-redis-url"
            version = "latest"
          }
        }
      }
      env {
        name = "GOOGLE_OAUTH_CLIENT_SECRET"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-oauth-client-secret"
            version = "latest"
          }
        }
      }
      # The OAuth web-client ID is the JWT `aud` the backend MUST validate
      # against. It's public (it's baked into the frontend bundle too) so
      # it ships as a plain env var, not a Secret Manager reference. If
      # this is unset/empty, pyjwt raises InvalidAudienceError on every
      # sign-in attempt → backend returns 401 → user sees a generic
      # "not authorised" error.
      env {
        name  = "GOOGLE_OAUTH_CLIENT_ID"
        value = var.google_oauth_client_id
      }
      env {
        name = "DMA_BOT_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-bot-api-key"
            version = "latest"
          }
        }
      }
      env {
        name = "RAG_API_BEARER_KEY"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-rag-api-key"
            version = "latest"
          }
        }
      }
      # RS256 private key (PEM) for session-cookie signing. The matching
      # public key is derived from this at backend boot — see
      # backend/app/services/jwt_service.py:_public_key. Until this is
      # set, every container worker generates an ephemeral keypair at
      # request time, which (a) costs ~200-800ms on cold start and (b)
      # invalidates every session JWT across revision rollouts.
      env {
        name = "JWT_PRIVATE_KEY_PEM"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jwt_signing_key.secret_id
            version = "latest"
          }
        }
      }
      # CORS origins for direct cross-origin API calls. The browser
      # never hits this path today (frontend nginx proxies /api/* so
      # everything's same-origin) but having it set right means
      # external integrations or the GIS popup callback work without
      # surprise CORS rejections.
      env {
        name  = "ALLOWED_ORIGINS"
        value = "https://dma-insights.zennify.com,http://localhost:5173"
      }
      # `ENV=prod` arms `assert_production_ready()` (see
      # backend/app/config.py:147). Without it the guard short-circuits
      # at `if settings.env not in ("prod", "dev"): return` and the
      # container happily boots with dev defaults — silently disables
      # the bearer guard, leaks dev DSNs into Cloud Run env, etc.
      env {
        name  = "ENV"
        value = "prod"
      }
      # Pub/Sub publisher + Vertex client both need the project ID.
      # Resolver fallbacks exist (GOOGLE_CLOUD_PROJECT metadata) but
      # explicit injection makes the env contract visible.
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      # Clay enrichment connector — outbound trigger URL + inbound
      # webhook HMAC secret. Per ADR 0010 the backend POSTs to
      # CLAY_WEBHOOK_URL when an entity needs firmographics, then
      # Clay calls back to /api/v1/clay/webhook signed with
      # CLAY_WEBHOOK_SECRET. Empty values fail-close the connector.
      env {
        name = "CLAY_WEBHOOK_URL"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-clay-webhook-url"
            version = "latest"
          }
        }
      }
      env {
        name = "CLAY_WEBHOOK_SECRET"
        value_source {
          secret_key_ref {
            secret  = "dma-insights-clay-webhook-secret"
            version = "latest"
          }
        }
      }
      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        # Throttle CPU between requests on the always-on min instance so the
        # warm-pool instance bills memory + near-zero idle CPU (not 2 full
        # vCPU 24/7). Explicit = guards against drift; this is the default but
        # the cost model hinges on it. The backend has no in-process
        # scheduler/background loop, so the idle instance genuinely idles.
        cpu_idle = true
      }
      # The Cloud SQL Auth Proxy sidecar (declared via `volumes
      # { cloud_sql_instance { … } }` below) creates a unix socket at
      # /cloudsql/<connection_name>/.s.PGSQL.5432, but it only exists
      # inside the container if we mount the named volume. DATABASE_URL
      # above uses `host=/cloudsql/<connection_name>` — without this
      # mount, asyncpg can't find the socket → every DB query 500s.
      # Symptom user hit: POST /api/v1/auth/google returns 500 because
      # the auth handler's INSERT INTO users fails to connect.
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      # Startup probe on the dependency-free /healthz so Cloud Run only
      # routes traffic (and only marks a fresh revision Ready) once the
      # uvicorn worker is actually serving HTTP — not merely accepting
      # TCP on :8000. This closes the cold-start window where the first
      # request after a revision roll returned empty/again-later (the
      # recurring "/healthz: no response but /readyz green" verify race).
      #
      # /healthz (NOT /readyz) is the startup target on purpose: /readyz
      # fail-closes (503) on migration drift, and deploy-two-phase.sh
      # rolls a --no-traffic revision BEFORE migrations run — gating
      # startup on /readyz would deadlock that revision until migrate.sh
      # completes, breaking the two-phase flow.
      startup_probe {
        http_get {
          path = "/healthz"
          port = 8000
        }
        initial_delay_seconds = 3
        timeout_seconds       = 3
        period_seconds        = 3
        failure_threshold     = 40 # ~120s headroom for a slow cold start
      }
      # Liveness on the same dependency-free route — restarts a wedged
      # worker, but tolerant (3 consecutive misses) so a transient blip
      # doesn't flap the instance.
      liveness_probe {
        http_get {
          path = "/healthz"
          port = 8000
        }
        timeout_seconds   = 3
        period_seconds    = 30
        failure_threshold = 3
      }
    }
    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.pg.connection_name]
      }
    }
  }
}

# ── Cloud Run service: frontend (nginx) ─────────────────────────────
resource "google_cloud_run_v2_service" "frontend" {
  depends_on          = [data.google_artifact_registry_docker_image.frontend]
  name                = "dma-insights-frontend"
  location            = var.region
  deletion_protection = false
  template {
    containers {
      image = "gcr.io/${var.project_id}/dma-insights-frontend:${var.image_sha}"
      ports {
        container_port = 8080
      }
      # nginx envsubst's BACKEND_URL into proxy_pass at container start.
      # Wiring backend.uri here means the frontend always proxies to the
      # currently-deployed backend revision, no manual sync needed.
      env {
        name  = "BACKEND_URL"
        value = google_cloud_run_v2_service.backend.uri
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
        # nginx serves a static SPA + reverse-proxies /api → backend; it
        # cold-starts in ~1–2s, so there is no reason to keep a warm instance
        # billing 24/7. cpu_idle (default true) further throttles CPU between
        # requests on any instance that is up.
        cpu_idle = true
      }
    }
    scaling {
      # Cost-optimised (2026-06): scale to zero when idle (was min 1). The
      # backend keeps min 1 (slow Cloud-SQL-proxy cold start on the critical
      # path); the frontend shell can absorb a 1–2s cold start on the first
      # hit after an idle window — a worthwhile trade for removing a full
      # always-on instance from the bill.
      min_instance_count = 0
      max_instance_count = 20
    }
  }
}

# ── Cloud Run Jobs (workers, share the same image) ─────────────────
locals {
  # Per-job execution caps (2026-06 cost safeguard). A hung/failing job is the
  # main runaway-cost vector: Cloud Run bills CPU+mem for the FULL `timeout`,
  # times (1 + max_retries) attempts, on every scheduler fire. The caps below
  # bound that blast radius. Every worker is transactional + idempotent, so a
  # timeout-kill rolls back cleanly and the NEXT scheduled run completes the
  # work — NO persisted data is lost (embeddings/intelligence/sheet rows are
  # write-once UPSERTs; a half-run never commits partial state). Frequent,
  # light jobs get max_retries = 0 because the next scheduled run already IS
  # the retry; slow or ingest-critical jobs keep one retry.
  jobs = {
    drive_crawler = { args = ["workers.drive_crawler.main", "--once"], timeout = "1800s", max_retries = 1 }
    # sheet_poller: fast (read sheet + upsert ~100 rows, <30s). 180s is 6× headroom;
    # 0 retries — a transient Sheets/API blip simply syncs at the next 15-min poll.
    sheet_poller = { args = ["workers.sheet_poller.main", "--once"], timeout = "180s", max_retries = 0 }
    # embedder --once: embed every run from the last 24h lacking section_embeddings.
    # Backstop to the post-commit dispatch; idempotent (skips embedded runs).
    embedder = { args = ["workers.embedder.main", "--once"], timeout = "900s", max_retries = 1 }
    # ccg_loader: --workbooks-dir points at the catalogue-staging bucket; override
    # args at execute time only to load a different version. Daily; idempotent.
    ccg_loader = {
      args        = ["workers.ccg_loader.main", "--version", "v7.0", "--workbooks-dir", "gs://${var.project_id}-catalogue-staging/v7.0/"]
      timeout     = "600s"
      max_retries = 0
    }
    # peer_patterns / chat_learning / intelligence_recompute: were missing as
    # Cloud Run Jobs pre-2026-05-28 (scheduler + admin-button dispatch 404'd);
    # default args reflect the canonical scheduled invocation (admin button
    # overrides via container_overrides at execute time). All idempotent.
    peer_patterns          = { args = ["workers.peer_patterns.main", "--all"], timeout = "900s", max_retries = 0 }
    chat_learning          = { args = ["workers.chat_learning.main"], timeout = "600s", max_retries = 0 }
    intelligence_recompute = { args = ["workers.intelligence_recompute.main", "--all"], timeout = "900s", max_retries = 1 }
    cross_entity_patterns  = { args = ["workers.cross_entity_patterns.main", "--all"], timeout = "900s", max_retries = 0 }
    # evidence_crawler: fetches cited pages for evidence rows that have a URL but
    # no excerpt and lifts a cross-encoder-grounded quote. Network-bound (many
    # hosts, per-host throttle) so 1800s timeout; internal wall-clock budget
    # (--budget-sec) stops it well before that. 0 retries — idempotent + additive,
    # the next weekly run resumes any rows left unfilled.
    evidence_crawler = { args = ["workers.evidence_crawler.main", "--budget-sec", "1500"], timeout = "1800s", max_retries = 0 }
  }
}

# ── Migrations Cloud Run Job (uses the BACKEND image, not workers) ──
# Runs `alembic upgrade head` then `python -m app.scripts.post_migrate`
# to GRANT the app user the rights it needs on the freshly-created
# tables. Executed manually via:
#   gcloud run jobs execute dma-insights-migrations --region us-central1 --wait
#
# Lives in a separate resource (not `local.jobs`) because:
#   1. It uses the BACKEND image (which carries alembic), not the
#      workers image.
#   2. It needs the SUPERUSER DSN (pgvector extension requires
#      cloudsqlsuperuser), not the app DSN.
#   3. The post_migrate step runs as superuser to grant the app user
#      its public-schema rights — a per-job env contract.
resource "google_cloud_run_v2_job" "migrations" {
  depends_on = [
    data.google_artifact_registry_docker_image.backend,
    google_secret_manager_secret_version.database_url_superuser,
  ]

  name                = "dma-insights-migrations"
  location            = var.region
  deletion_protection = false
  template {
    template {
      containers {
        image = "gcr.io/${var.project_id}/dma-insights-backend:${var.image_sha}"
        # Use bash -lc so the chained alembic + python invocation is
        # one container exec. /install/bin/alembic is on PATH (Dockerfile
        # adds /install/bin) so we can call it directly.
        # `bash -c` (NOT `-lc`). A login shell (`-l`) sources
        # /etc/profile which resets PATH to Debian defaults
        # (/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin)
        # — clobbering the Dockerfile's `ENV PATH="/install/bin:$PATH"`
        # and making `alembic` (at /install/bin/alembic) not found.
        # We also use ABSOLUTE paths for alembic + python below as
        # belt-and-suspenders so a future PATH regression can't break
        # the chain.
        command = ["/bin/bash", "-c"]
        # `set -eo pipefail -x` traces every command — Cloud Run job
        # logs then show exactly which step failed (alembic vs
        # post_migrate vs the verification step inside post_migrate).
        # `&&` chains, not `;`, so a failed alembic short-circuits
        # before post_migrate runs and the job exits non-zero loudly.
        args = [
          <<-EOT
            set -eo pipefail -x
            echo '== identity =='
            whoami
            which alembic || echo "(alembic not on PATH; using absolute)"
            echo '== alembic upgrade head =='
            /install/bin/alembic -c /home/app/alembic.ini upgrade head \
              && echo '== alembic current ==' \
              && /install/bin/alembic -c /home/app/alembic.ini current \
              && echo '== post_migrate ==' \
              && /usr/local/bin/python -m app.scripts.post_migrate \
              && echo '== done =='
          EOT
        ]
        env {
          name = "DATABASE_URL_SYNC"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url_superuser.secret_id
              version = "latest"
            }
          }
        }
        # ENV gate — see backend service block for the rationale. The
        # migrations job only uses settings indirectly via env.py, but
        # arming the guard means post_migrate's startup-style imports
        # (which call get_settings()) match the rest of the deployment.
        env {
          name  = "ENV"
          value = "prod"
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.pg.connection_name]
        }
      }
      max_retries = 1
      timeout     = "600s"
    }
  }
}

# ── Historical backfill Cloud Run Job ───────────────────────────────
# Reads DMA folders DIRECTLY from Google Drive (root folder ID below),
# downloads each file, and runs the standard parse + persist pipeline.
# No GCS bucket or zip download required — fixes the original approach
# that required downloading 100+ folders as individual zips.
#
# Trigger manually when needed (idempotent; already-ingested folders skip):
#   gcloud run jobs execute dma-insights-historical-backfill \
#     --region us-central1 --wait
#
# The SA (default compute) must have Viewer access to the Drive root
# folder (see DEPLOYMENT.md §17 for the manual sharing step).
resource "google_cloud_run_v2_job" "historical_backfill" {
  depends_on = [
    data.google_artifact_registry_docker_image.backend,
    google_secret_manager_secret_version.database_url,
  ]

  name                = "dma-insights-historical-backfill"
  location            = var.region
  deletion_protection = false
  template {
    template {
      containers {
        image   = "gcr.io/${var.project_id}/dma-insights-backend:${var.image_sha}"
        command = ["/usr/local/bin/python", "-m", "app.scripts.historical_backfill"]
        # DRIVE_ROOT_FOLDER_ID is INTENTIONALLY HARDCODED, not a
        # Terraform variable. Operator decision (2026-05-29): the
        # canonical DMA Assets root folder ID is constant — never
        # changes across deploys, environments, or lifecycle events.
        # Variableizing it would only introduce drift risk between
        # the Terraform definition + DEPLOYMENT.md §9 (which shares
        # this same folder ID with the SA's ACL) + CLAUDE.md
        # ("Drive folder `folders/1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`").
        # If a future engagement needs a different folder, change
        # all three pin sites in one PR rather than parameterizing.
        env {
          name  = "DRIVE_ROOT_FOLDER_ID"
          value = "1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P"
        }
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.database_url.secret_id
              version = "latest"
            }
          }
        }
        # historical_backfill writes job_executions + backfill_quarantine
        # rows via the sync DSN (matches the worker pattern at line
        # 858+). Without this, `_safe_create_row` silently no-ops and
        # the UI never sees retry candidates.
        env {
          name = "DATABASE_URL_SYNC"
          value_source {
            secret_key_ref {
              secret  = "dma-insights-database-url-sync"
              version = "latest"
            }
          }
        }
        env {
          name  = "VERTEX_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "ENV"
          value = "prod"
        }
        # post-deploy-refresh dispatches run_derive_chain through this job
        # (DMA_POST_DEPLOY_RUN=derive_chain) against the LIVE DB with
        # Vertex hot. The chain's 300s default per-step budget is too
        # tight for the Vertex-hot steps on this job's 2 vCPU
        # (deepen_narrative hard-timed out at 300s in the 2026-07-04
        # Cloud Build regen — same chain, same workload). Matches the
        # cloudbuild regen ENV_ARGS; the job-level 7200s timeout remains
        # the overall backstop. NOTE: DMA_ALLOW_HOLLOW is deliberately
        # NOT set here — the fail-loud hollow gate stays armed for live
        # Drive ingestion.
        env {
          name  = "DERIVE_STEP_TIMEOUT_SEC"
          value = "1500"
        }
        env {
          name  = "DMA_EXPLAINER_BUDGET_SEC"
          value = "600"
        }
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        resources {
          limits = {
            cpu    = "2"
            memory = "4Gi"
          }
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.pg.connection_name]
        }
      }
      max_retries = 0 # operator re-runs explicitly; idempotent on drive_folder_id
      timeout     = "7200s"
    }
  }
}

# Drive API access for the historical backfill SA.
#
# IMPORTANT: there is NO project-level role grant here. Google Drive uses
# a per-document ACL model (Workspace), not Cloud IAM. The
# `roles/drive.reader` identifier looks like a Cloud IAM role but is
# actually a Workspace role — Cloud Resource Manager rejects it with
# `Error 400: Role roles/drive.reader is not supported for this resource`.
#
# The actual permission grant happens out-of-band — see DEPLOYMENT.md §9.
# An operator must share the DMA Assets root folder
# (1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P) with the Compute Engine default SA
# (<PROJECT_NUMBER>-compute@developer.gserviceaccount.com) as Viewer in
# Google Drive. That folder-level ACL is what gates Drive API reads.
#
# This terraform module also does NOT grant `roles/serviceusage.serviceUsageConsumer`
# because the default Compute SA already has it via the project-default
# permissions baked into every GCP project. If a custom SA is used later,
# add that role here.

resource "google_cloud_run_v2_job" "worker" {
  depends_on = [
    data.google_artifact_registry_docker_image.workers,
    google_secret_manager_secret_version.database_url,
  ]

  for_each = local.jobs
  # Cloud Run v2 Job names are RFC1035: lowercase + digits + hyphens.
  # Our Python module path uses underscores (workers.drive_crawler.main),
  # so we translate `_` → `-` only for the resource name. The args
  # below still reference the underscored module path.
  name                = "dma-insights-${replace(each.key, "_", "-")}"
  location            = var.region
  deletion_protection = false
  template {
    template {
      containers {
        image   = "gcr.io/${var.project_id}/dma-insights-workers:${var.image_sha}"
        command = ["python", "-m"]
        args    = each.value.args
        # Workers (ccg_loader, sheet_poller, drive_crawler, embedder)
        # all need the same DB + Vertex env as the backend. Sourced
        # from the same secret so password rotation cascades to all
        # jobs automatically.
        env {
          name = "DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = "dma-insights-database-url"
              version = "latest"
            }
          }
        }
        # 2026-05-28 H1 hotfix made permanent — workers need a sync
        # DSN for job_executions, synthesis_cache, ccg_loader_runs
        # writes. Previously workers ran with ONLY DATABASE_URL set
        # (asyncpg) and every sync call silently no-op'd through the
        # runner's `_safe_*` wrappers. Application code derives the
        # sync URL from DATABASE_URL as a fallback (see
        # `app/services/sync_dsn.py`), but injecting it explicitly is
        # the architecturally clean path — visible in Cloud Run env
        # config without reading code.
        env {
          name = "DATABASE_URL_SYNC"
          value_source {
            secret_key_ref {
              secret  = "dma-insights-database-url-sync"
              version = "latest"
            }
          }
        }
        env {
          name  = "VERTEX_PROJECT_ID"
          value = var.project_id
        }
        env {
          name  = "VERTEX_LOCATION"
          value = var.region
        }
        env {
          name = "REDIS_URL"
          value_source {
            secret_key_ref {
              secret  = "dma-insights-redis-url"
              version = "latest"
            }
          }
        }
        # Worker production-readiness — REQUIRED_FOR_PROD_WORKER in
        # backend/app/config.py only needs database_url + gcp_project_id
        # (workers don't sign JWTs, don't accept OAuth callbacks, don't
        # terminate Clay webhooks), but the ENV gate must still arm.
        env {
          name  = "ENV"
          value = "prod"
        }
        env {
          name  = "GCP_PROJECT_ID"
          value = var.project_id
        }
        # Cloud SQL unix-socket mount — must match the host=/cloudsql/…
        # in DATABASE_URL. Same gotcha as the backend in e196a25.
        volume_mounts {
          name       = "cloudsql"
          mount_path = "/cloudsql"
        }
        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }
      }
      volumes {
        name = "cloudsql"
        cloud_sql_instance {
          instances = [google_sql_database_instance.pg.connection_name]
        }
      }
      # Per-job caps (see local.jobs) — bound a hung/failing worker's burn.
      max_retries = each.value.max_retries
      timeout     = each.value.timeout
    }
  }
}

# ── Cloud Scheduler triggers ────────────────────────────────────────
resource "google_cloud_scheduler_job" "drive_crawler_6h" {
  name             = "dma-insights-drive-crawler-6h"
  schedule         = "0 */6 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-drive-crawler:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Daily NEW-folder discovery probe (2026-06-07 operator mandate:
# "the drive prob should check for new DMA folders on a daily basis
# and set up their profile and ingest all relevant material"). The 6h
# crawl above does delta-ingest for KNOWN folders; this dedicated
# daily probe runs once at 02:00 CT specifically to discover NEW DMA
# folders that landed in the Drive root since the last day -- so a
# folder uploaded by an analyst after the prior 6h crawl gets a
# canonical entity row + initial ingest within 24h without waiting
# for the next 6h-aligned slot.
#
# The drive_crawler job uses the same image + entrypoint as the 6h
# variant; intelligent change-detection (material_manifest_hash, since
# migration 033) makes the daily probe a near-no-op for already-
# ingested folders -- only NEW folders cost any work.
resource "google_cloud_scheduler_job" "drive_crawler_daily_new_folders" {
  name      = "dma-insights-drive-crawler-daily-discovery"
  schedule  = "0 2 * * *" # 02:00 CT daily — outside the 6h windows
  time_zone = "America/Chicago"
  # Cloud Scheduler caps attempt_deadline at 30m (1800s); 3600s is rejected
  # at apply with HTTP 400 `attempt_deadline must be between 15s and 30m0s`.
  # This field is only how long the scheduler waits for the trigger HTTP to
  # be ACKed — the `:run` endpoint returns immediately and the Cloud Run Job
  # then runs to its OWN task_timeout, independent of this deadline — so
  # 1800s is ample for a cold-start crawl trigger. Matches drive_crawler_6h.
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-drive-crawler:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

resource "google_cloud_scheduler_job" "sheet_poller_5min" {
  # Cost-optimised cadence (2026-06): every 15 min during 06:00–20:59 CT
  # (~57 runs/day) instead of every 5 min around the clock (288/day) — an
  # ~80% cut in cold-starts + Sheets-API reads. The Ops Sheet carries AE
  # assignments + new-request rows that are never urgent to the minute, and
  # the poller already short-circuits when no row changed since last_synced,
  # so off-hours edits simply sync at the next 06:00 poll. Drive-folder
  # discovery (new DMAs) is handled separately by the drive crawler, so this
  # window change cannot delay an ingest.
  name             = "dma-insights-sheet-poller-5min"
  schedule         = "*/15 6-20 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "600s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-sheet-poller:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

resource "google_cloud_scheduler_job" "ccg_loader_hourly" {
  # Watches gs://dma-insights-catalogue-staging/ for new Pillar_{1..4}_*.xlsx
  # workbooks. Cost-optimised (2026-06): DAILY poll (was hourly). The
  # catalogue ships ~quarterly (ADR 0005), so 24 cold-starts/day to detect a
  # 4×/year event was pure waste — daily is still ~90× more frequent than
  # the release cadence, and the manual trigger remains for an urgent bump.
  name             = "dma-insights-ccg-loader-hourly"
  schedule         = "0 4 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-ccg-loader:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# 2026-05-29 QA audit P1 — derived-data reconciliation.
#
# The post-commit dispatch path (app/services/post_commit_workers.py)
# fires the embedder + intelligence_recompute jobs directly after every
# successful ingest. The two schedulers below are belt-and-braces self-
# healing: any direct dispatch that failed (transient Cloud Run dispatch
# error, partial outage, manually-inserted run rows) gets picked up
# within an hour. Both workers are idempotent — the embedder skips runs
# that already have section_embeddings rows; intelligence_recompute
# UPSERTs the customer_intelligence_profiles row.
#
# Cost-optimised (2026-06): every 6h at :30 (was hourly). The post-commit
# dispatch (post_commit_workers) embeds each run in real time on ingest; this
# is only the self-healing backstop for a failed dispatch, and the embedder is
# idempotent (skips runs that already have section_embeddings). A 6h backstop
# bounds worst-case embedding latency at 6h for the rare missed dispatch while
# cutting 24→4 cold-starts/day.
resource "google_cloud_scheduler_job" "embedder_hourly" {
  name             = "dma-insights-embedder-hourly"
  schedule         = "30 */6 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-embedder:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Cost-optimised (2026-06): every 6h at :45 (was hourly), staggered 15 min
# after the embedder so the run-level embeddings it references are present.
# Like the embedder this is the self-healing backstop — the post-commit
# dispatch recomputes on ingest in real time, and the worker idempotent-skips
# unchanged entities (so it makes ZERO Vertex Pro calls on a stable corpus).
# 24→4 cold-starts/day.
resource "google_cloud_scheduler_job" "intelligence_recompute_hourly" {
  name             = "dma-insights-intelligence-recompute-hourly"
  schedule         = "45 */6 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-intelligence-recompute:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Weekly peer_patterns recompute — KMeans archetypes per subvertical.
# Plan §6: cohort recompute is weekly; the worker is idempotent so
# missed runs don't compound. Sunday 03:00 CT puts the spike outside
# business hours and outside the catalogue_loader hourly window.
resource "google_cloud_scheduler_job" "peer_patterns_weekly" {
  name             = "dma-insights-peer-patterns-weekly"
  schedule         = "0 3 * * 0"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-peer-patterns:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Weekly cross_entity_patterns recompute — recurring subcap gaps + open
# issues across each subvertical cohort → cross_entity_patterns rows. Sunday
# 04:00 CT, after peer_patterns (03:00) so both cohort recomputes land before
# the business week. Idempotent (full DELETE/INSERT per cohort).
resource "google_cloud_scheduler_job" "cross_entity_patterns_weekly" {
  name             = "dma-insights-cross-entity-patterns-weekly"
  schedule         = "0 4 * * 0"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-cross-entity-patterns:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Weekly evidence-excerpt crawl — fetches cited pages for evidence rows that
# arrived with a URL but no quote and lifts a cross-encoder-grounded excerpt.
# Sunday 05:00 CT, after peer_patterns (03:00) + cross_entity_patterns (04:00).
# Out of band from the hermetic qa-gates derive chain (which must not touch the
# network); idempotent + additive so a re-run only fills still-empty rows.
resource "google_cloud_scheduler_job" "evidence_crawler_weekly" {
  name             = "dma-insights-evidence-crawler-weekly"
  schedule         = "0 5 * * 0"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-evidence-crawler:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Nightly chat_learning rollup — KMeans cluster on chat_messages
# embeddings + weighted-effectiveness rollup → chat_learning_signals.
# Powers the adversarial-learning reranker in /rag/answer. Runs at
# 02:00 CT after all business-day chat traffic has settled.
resource "google_cloud_scheduler_job" "chat_learning_nightly" {
  name             = "dma-insights-chat-learning-nightly"
  schedule         = "0 2 * * *"
  time_zone        = "America/Chicago"
  attempt_deadline = "1800s"
  http_target {
    http_method = "POST"
    uri         = "https://${var.region}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${var.project_id}/jobs/dma-insights-chat-learning:run"
    oauth_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

# Daily evidence-freshness refresh — keeps `is_stale` + `freshness_band`
# accurate for rows whose published_date crossed a 1y/2y/3y band
# boundary between writes. See DEPLOYMENT.md §28b. The migration 018
# trigger handles INSERT/UPDATE freshness; this Scheduler call catches
# wall-clock drift. Runs at 06:00 UTC daily (chosen for low-traffic
# window across both US business hours zones).
resource "google_cloud_scheduler_job" "evidence_freshness_refresh" {
  name             = "dma-insights-evidence-freshness-refresh"
  schedule         = "0 6 * * *"
  time_zone        = "UTC"
  attempt_deadline = "600s"
  http_target {
    http_method = "POST"
    uri         = "https://dma-insights-backend-${data.google_project.project.number}-uc.a.run.app/api/v1/admin/maintenance/refresh-evidence-freshness"
    oidc_token {
      service_account_email = google_service_account.scheduler.email
    }
  }
}

resource "google_service_account" "scheduler" {
  account_id   = "dma-insights-scheduler"
  display_name = "DMA Insights Cloud Scheduler invoker"
}

resource "google_project_iam_member" "scheduler_runner" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.scheduler.email}"
}

# ── Cloud Run runtime SA → Secret Manager access ───────────────────
# The Cloud Run backend service uses the default compute service
# account (we don't bind a custom one). That SA needs Secret Accessor
# on every secret referenced via `value_source.secret_key_ref`,
# otherwise revision deploy fails with:
#
#   spec.template.spec.containers[0].env[N].value_from.secret_key_ref.name:
#   Permission denied on secret …
#
# Granting at project-level keeps it future-proof for any new secrets
# we add to env blocks later (e.g. Clay webhook secret).
data "google_project" "project" {
  project_id = var.project_id
}

# Fail-fast guard for out-of-band secrets (created by `gcloud secrets create`
# in DEPLOYMENT.md §4b — NOT managed by this Terraform module). Without these
# data blocks `terraform apply` would happily build Cloud Run revisions that
# crash at startup because the secret-bound env vars resolve to errors.
# Listing them here forces `terraform plan` to fail with a clear
# "Secret X not found" message if any are missing.
data "google_secret_manager_secret" "oob_oauth_client_secret" {
  secret_id = "dma-insights-oauth-client-secret"
  project   = var.project_id
}
data "google_secret_manager_secret" "oob_bot_api_key" {
  secret_id = "dma-insights-bot-api-key"
  project   = var.project_id
}
data "google_secret_manager_secret" "oob_rag_api_key" {
  secret_id = "dma-insights-rag-api-key"
  project   = var.project_id
}
data "google_secret_manager_secret" "oob_redis_url" {
  secret_id = "dma-insights-redis-url"
  project   = var.project_id
}
# Clay (firmographics + leadership enrichment) connector — per ADR 0010.
# Both secrets are managed out-of-band (DEPLOYMENT.md §4b) because the
# webhook URL is environment-specific and the shared secret rotates
# independently of the rest of the secret-manifest. Listing them here
# makes `terraform plan` fail loudly when either is missing, instead of
# Cloud Run silently booting with empty values → every /api/v1/clay/webhook
# call fail-closes on HMAC verification.
data "google_secret_manager_secret" "oob_clay_webhook_url" {
  secret_id = "dma-insights-clay-webhook-url"
  project   = var.project_id
}
data "google_secret_manager_secret" "oob_clay_webhook_secret" {
  secret_id = "dma-insights-clay-webhook-secret"
  project   = var.project_id
}

resource "google_project_iam_member" "cloud_run_secret_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Cloud SQL connectivity for the backend + worker service identities.
# The Cloud SQL Auth Proxy sidecar (provisioned via `volumes
# { cloud_sql_instance { … } }` on the Cloud Run resources) opens its
# upstream connection to Cloud SQL using the Cloud Run service's
# identity. Without `roles/cloudsql.client`, the proxy returns
# "connection refused" before any Postgres-level traffic flows —
# manifests as either a connection-refused error OR (in some provider
# versions) an empty 5s timeout. Adding this explicitly so we never
# rely on inherited Editor/Owner privileges.
resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Vertex AI access — required by the Gemini Flash/Pro stream calls in
# `services/vertex_client.py` and the text-embedding-004 embed calls in
# `workers/embedder`. Without this, every intelligence_builder run returns
# `vertex_error: 403 Permission denied on resource 'projects/$PROJECT/locations/$REGION/publishers/google/models/...'`
# and the SSE channel publishes only fallback events.
resource "google_project_iam_member" "cloud_run_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"
}

# Vertex AI access for the CLOUD BUILD service account (2026-07-02,
# master plan Part 3.1 / RC1). The `regen-startup-pack` Cloud Build
# stage now bakes the startup pack GEMINI-HOT: its containers run on the
# `cloudbuild` Docker network so the build-VM metadata server provides
# ADC as {project_number}@cloudbuild.gserviceaccount.com. Without this
# grant every bake-time Vertex call 403s, enrich_corpus stays
# honest-cold, and `qa_gemini_surfaces --mode baked` fails the build
# (unless `_ALLOW_COLD_GEMINI=true`). This is the legacy/default Cloud
# Build SA form; builds configured with a custom SA need the same role
# on that SA instead.
resource "google_project_iam_member" "cloud_build_aiplatform_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${data.google_project.project.number}@cloudbuild.gserviceaccount.com"
}

# Per-secret bindings — kept as belt-and-suspenders alongside the
# project-level binding above. Some Cloud Run projects had IAM
# propagation lag where the project-level grant took up to several
# minutes to apply to brand-new secrets; per-secret bindings are
# instant. Harmless redundancy.
locals {
  backend_secrets = [
    "dma-insights-bot-api-key",
    "dma-insights-clay-webhook-secret", # 2026-05-28 — Clay HMAC shared secret (ADR 0010)
    "dma-insights-clay-webhook-url",    # 2026-05-28 — Clay outbound trigger URL
    "dma-insights-database-url",
    "dma-insights-database-url-superuser",
    "dma-insights-database-url-sync", # 2026-05-28 — sync (psycopg) DSN
    "dma-insights-jwt-signing-key",
    "dma-insights-oauth-client-secret",
    "dma-insights-rag-api-key",
    "dma-insights-redis-url",
  ]
}

resource "google_secret_manager_secret_iam_member" "backend_secret_access" {
  for_each  = toset(local.backend_secrets)
  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${data.google_project.project.number}-compute@developer.gserviceaccount.com"

  # The secrets `dma-insights-database-url`,
  # `dma-insights-database-url-superuser`, and
  # `dma-insights-jwt-signing-key` are created by THIS terraform
  # module; the rest of backend_secrets is created out-of-band by §4.
  # The depends_on ensures the IAM binding doesn't fire 404 on the
  # first apply, when those three secrets haven't been created yet.
  # Harmless for the other secrets (terraform's dep graph is already
  # correct for those).
  depends_on = [
    google_secret_manager_secret.database_url,
    google_secret_manager_secret.database_url_superuser,
    google_secret_manager_secret.jwt_signing_key,
  ]
}

# ── Cloud Run services → public ingress ────────────────────────────
# Cloud Run v2 services default to deny-all on roles/run.invoker, which
# returns 403 to a browser before any in-app auth runs. The app's own
# JWT + role gating (`app/deps.py:get_current_user`) handles
# authentication on every protected endpoint, so public ingress is the
# correct pattern here — every API request that needs a user identity
# already 401s without a valid session cookie.
#
# If you want zero-trust at the network edge instead, replace these
# with an Identity-Aware Proxy load-balancer (out of scope for v1).
resource "google_cloud_run_v2_service_iam_member" "frontend_public_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.frontend.location
  name     = google_cloud_run_v2_service.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "backend_public_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.backend.location
  name     = google_cloud_run_v2_service.backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Outputs ────────────────────────────────────────────────────────
output "backend_url" {
  value = google_cloud_run_v2_service.backend.uri
}

output "frontend_url" {
  value = google_cloud_run_v2_service.frontend.uri
}

output "ingest_topic" {
  value = google_pubsub_topic.ingest_completed.id
}

# Operator-facing handles referenced by docs/DEPLOYMENT.md.
output "db_instance_name" {
  description = "Cloud SQL instance name — pass to `gcloud sql connect`."
  value       = google_sql_database_instance.pg.name
}

output "db_connection_name" {
  description = "Cloud SQL connection name (project:region:instance) for Cloud SQL Proxy / Cloud Run mount."
  value       = google_sql_database_instance.pg.connection_name
}

output "scheduler_sa_email" {
  description = "Service account that invokes the Cloud Run Jobs from Cloud Scheduler."
  value       = google_service_account.scheduler.email
}
