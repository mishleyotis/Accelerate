#!/usr/bin/env bash
# apps/dma-insights/infra/post-deploy-refresh.sh
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  WHY THIS EXISTS                                                     ║
# ║                                                                      ║
# ║  Operator complaint (recurring): "while deploying, I still see the   ║
# ║  logs picking wrong evidence and subcap counts ... a new deployment  ║
# ║  should always refresh everything and even parse and ensure the      ║
# ║  backfill is fired such that when I join everything is already       ║
# ║  ingested and processed."                                            ║
# ║                                                                      ║
# ║  CONTRACT (operator mandate 2026-06-05): "the refresh should be for  ║
# ║  new information please or new dma reports. If a report was          ║
# ║  persisted and no change took place, it can always persist the       ║
# ║  initial version." This is the script's invariant -- everything      ║
# ║  below is delta-mode or no-op for unchanged data:                    ║
# ║                                                                      ║
# ║    - drive_crawler --mode delta   only re-parses Drive folders that  ║
# ║      are NEW or have a newer modifiedTime. Unchanged folders are     ║
# ║      skipped entirely; their persisted runs + cached narratives stay ║
# ║      live as-is.                                                     ║
# ║    - embedder --mode delta        only embeds evidence / section     ║
# ║      rows added since the embedder's last successful run. Existing   ║
# ║      embeddings are left untouched.                                  ║
# ║    - intelligence_recompute       idempotent. classify_state         ║
# ║      branches to no-op when no new run has landed for an entity.     ║
# ║    - vertex_synthesis_cache rows are PRESERVED. Cache invalidation   ║
# ║      is OPT-IN via --invalidate-cache; absent that flag every cached ║
# ║      narrative keeps serving as long as its fingerprint (prompt-     ║
# ║      template-version + grounding-bundle-hash + catalogue-version +  ║
# ║      page-context-hash) matches.                                     ║
# ║                                                                      ║
# ║  Root cause was THREE separate failure modes glued together:         ║
# ║    (a) Cloud Run kept routing 100% traffic to the prior revision     ║
# ║        because the new revision was deployed but never promoted to   ║
# ║        --to-latest. Pre-2026-06-05 deploy.sh only --to-latest'd on   ║
# ║        drift detection, so a successful new deployment that didn't   ║
# ║        DRIFT still saw stale traffic.                                ║
# ║    (b) After a schema change the in-app vertex_synthesis_cache rows  ║
# ║        kept serving narratives built from the OLD evidence shape -   ║
# ║        the operator saw "wrong subcap counts" because the cache hit  ║
# ║        on an input fingerprint that pre-dated the migration. ONLY    ║
# ║        --invalidate-cache addresses this; default flow preserves     ║
# ║        the cache so unchanged reports keep their persisted narrative.║
# ║    (c) Backfill (drive_crawler / embedder / intelligence_recompute)  ║
# ║        wasn't re-triggered post-deploy, so any newly-uploaded DMA    ║
# ║        packages sat un-ingested until the next scheduled crawl. The  ║
# ║        operator joined a freshly-deployed app and found their newest ║
# ║        packages still in "PENDING" state.                            ║
# ║                                                                      ║
# ║  This script fixes (a) and (c) deterministically + non-destructively.║
# ║  (b) is opt-in (--invalidate-cache) because it triggers Vertex spend ║
# ║  on the next read for every active surface and discards work that    ║
# ║  may still be correct.                                               ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# Flow (state branches):
#
#   1. promote_traffic
#        live_already_at_latest → no-op
#        live_lagging           → gcloud run services update-traffic --to-latest
#
#   2. backfill_delta (default)
#        drive_crawler --mode delta  → picks up new Drive folders without
#                                      re-processing existing ones
#        embedder --mode delta       → embeds any new evidence/section rows
#        intelligence_recompute      → rolls fresh runs into per-entity
#                                      intelligence profiles
#
#   3. invalidate_cache (opt-in)
#        UPDATE vertex_synthesis_cache SET invalidated_at = NOW()
#          WHERE created_at < <deploy_started_at>
#            AND invalidated_at IS NULL
#            AND invalidation_reason IS NULL
#        Next read for each affected surface re-synthesizes against the
#        new prompt template + new evidence -- which is the operator-
#        visible behaviour they're asking for. Costs Vertex tokens.
#
#   4. verify_revisions
#        For every Cloud Run service, assert traffic split == 100% LATEST.
#        Exit 2 (with the manual fix) when ANY service is still split.
#
# Usage:
#   ./post-deploy-refresh.sh                    # promote + delta backfill (default)
#   ./post-deploy-refresh.sh --skip-backfill    # just promote traffic
#   ./post-deploy-refresh.sh --invalidate-cache # also force synthesis re-synth
#   ./post-deploy-refresh.sh --skip-verify      # don't double-check post-update
#   SHA=abc1234 ./post-deploy-refresh.sh        # pin a deploy SHA for traffic checks
set -euo pipefail

export GODEBUG=netdns=go

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Silence the benign per-call "Regional Access Boundary ... 404" gcloud
# stderr noise (Cloud Shell federated identities; see the filter file).
[ -f "${SCRIPT_DIR}/gcloud-noise-filter.sh" ] && . "${SCRIPT_DIR}/gcloud-noise-filter.sh"
REGION="${REGION:-us-central1}"
PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
# Pin the refresh job to the NEWEST deploy-branch image (read-only NO_SYNC —
# this runs after the deploy already synced the tree). deploy-two-phase exports
# SHA, so this fallback only matters for a standalone run; either way it never
# pins a stale image.
SHA="${SHA:-$(NO_SYNC=1 bash "${SCRIPT_DIR}/resolve-deploy-sha.sh" 2>/dev/null \
                || (git rev-parse HEAD 2>/dev/null || true) | cut -c1-7)}"

BACKFILL_MODE="run"
CACHE_MODE="skip"
VERIFY_MODE="run"
# Corpus-seed mode: opt-in deploy-time load of the committed 100+
# package corpus into the DB so the 100+ DMAs are persisted during
# deployment (2026-06-07 operator mandate). Enabled by passing
# --seed-corpus OR by setting DMA_SEED_CORPUS_ON_DEPLOY=1 in the
# environment (CI / Terraform). The seed uses the intelligent
# material_manifest_hash skip (migration 033) so subsequent deploys
# are near-no-op for unchanged packages. Default is OFF in case the
# operator wants Drive-only ingest in production.
SEED_CORPUS_MODE="${DMA_SEED_CORPUS_ON_DEPLOY:+run}"
SEED_CORPUS_MODE="${SEED_CORPUS_MODE:-skip}"
SEED_CORPUS_DIR="${DMA_SEED_CORPUS_DIR:-/home/app/tests/fixtures/dma_packages_batches}"
for arg in "$@"; do
  case "$arg" in
    --skip-backfill)     BACKFILL_MODE="skip" ;;
    --invalidate-cache)  CACHE_MODE="run" ;;
    --skip-verify)       VERIFY_MODE="skip" ;;
    --seed-corpus)       SEED_CORPUS_MODE="run" ;;
    --no-seed-corpus)    SEED_CORPUS_MODE="skip" ;;
    --help|-h)
      sed -n '1,80p' "$0" | sed 's/^# \?//'
      exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 1 ;;
  esac
done

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "ERROR: PROJECT_ID unset." >&2
  exit 1
fi

DEPLOY_STARTED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DMA Insights — Post-Deploy Refresh                      ║"
echo "╠══════════════════════════════════════════════════════════╣"
printf "║  Project    : %-43s║\n" "$PROJECT_ID"
printf "║  Region     : %-43s║\n" "$REGION"
printf "║  SHA        : %-43s║\n" "${SHA:-<unset>}"
printf "║  Backfill   : %-43s║\n" "$BACKFILL_MODE"
printf "║  Seed corpus: %-43s║\n" "$SEED_CORPUS_MODE"
printf "║  Cache      : %-43s║\n" "$CACHE_MODE"
echo "╚══════════════════════════════════════════════════════════╝"

# ── 0b. Pin the worker jobs this refresh executes to the deployed SHA ────────
# deploy-two-phase.sh pins dma-insights-migrations (Phase 3) but nothing
# repinned the jobs THIS script runs. 2026-07-11 diagnosis: the fleet was
# serving 443dcb9 while historical-backfill still ran the 3-day-old 2afda85
# image and every worker job ran 9c64331 — so every post-deploy refresh
# re-ran OLD code and shipped fixes never took effect in the derive chain
# or the crawler. Pin ALL of them to $SHA up front (best-effort: a missing
# job or tag warns and continues, matching this script's degrade posture).
if [[ -n "${SHA:-}" ]]; then
  echo ""
  echo "→ Pinning refresh-executed jobs to SHA=$SHA..."
  _pin_job() { # job image-repo
    printf "  → %-42s" "$1"
    if gcloud run jobs update "$1" --region="$REGION" \
         --image "gcr.io/${PROJECT_ID}/$2:${SHA}" --quiet \
         >/dev/null 2>&1; then
      echo "✓ $2:${SHA}"
    else
      echo "⚠ pin failed (missing job or tag?) — job keeps its current image"
    fi
  }
  _pin_job dma-insights-historical-backfill dma-insights-backend
  for _j in drive-crawler embedder sheet-poller intelligence-recompute \
            ccg-loader peer-patterns chat-learning; do
    _pin_job "dma-insights-${_j}" dma-insights-workers
  done
fi

# ── 1. Promote traffic to LATEST on both services ────────────────────────────
# Cloud Run's default behaviour after a `gcloud run deploy` is to send
# traffic to the new revision IMMEDIATELY -- but a terraform-managed
# service that already has a manual traffic split (e.g. 50/50 from a
# prior canary) will NOT auto-promote. We make the post-deploy state
# unambiguous: 100% to LATEST, every time. Idempotent when already there.
echo ""
echo "→ Promoting traffic to LATEST on Cloud Run services..."
SERVICES=(dma-insights-backend dma-insights-frontend)
PROMOTE_FAILED=0

# A `gcloud run deploy` returns once the new revision is CREATED, but Cloud
# Run only routes `--to-latest` to the latest READY revision. On a slow cold
# start the new revision is still rolling out when we promote here, so
# `--to-latest` silently re-pins the PRIOR revision and the deploy "succeeds"
# while the live API is still served by the old image (the 2026-06-18 incident:
# backend stuck on -00057 while -00153 was the real latest, so the freshly-
# built frontend refetched stale/junk data → "94 then defaults to the bad UI").
# Wait for the newest CREATED revision to become READY before promoting.
_wait_latest_ready() {
  local svc="$1" tries=0 max="${PROMOTE_READY_TRIES:-24}"   # ~6 min @ 15s
  while [[ "$tries" -lt "$max" ]]; do
    local created ready
    created=$(gcloud run services describe "$svc" --region="$REGION" \
      --format='value(status.latestCreatedRevisionName)' 2>/dev/null || true)
    ready=$(gcloud run services describe "$svc" --region="$REGION" \
      --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
    if [[ -n "$created" && "$created" == "$ready" ]]; then
      return 0   # newest revision is healthy/ready — safe to --to-latest
    fi
    tries=$((tries + 1))
    printf "  … %-30s waiting for %s to be READY (ready=%s) [%d/%d]\n" \
      "$svc" "${created:-?}" "${ready:-?}" "$tries" "$max"
    sleep "${PROMOTE_READY_INTERVAL:-15}"
  done
  printf "  ⚠ %-30s newest revision still not READY after wait; promoting last-ready\n" \
    "$svc" >&2
  return 1
}

for svc in "${SERVICES[@]}"; do
  if ! gcloud run services describe "$svc" --region="$REGION" \
         --format='value(name)' >/dev/null 2>&1; then
    printf "  ⚠ %-30s does not exist; skipping\n" "$svc"
    continue
  fi
  # Block until the newest CREATED revision is READY (best-effort; warns and
  # proceeds on timeout so a genuinely-unhealthy revision still surfaces in
  # the verify gate below rather than hanging the deploy forever).
  _wait_latest_ready "$svc" || true
  # What's LATEST claiming (re-read AFTER the wait)?
  latest_rev=$(gcloud run services describe "$svc" --region="$REGION" \
    --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
  # What's actually serving 100%?
  serving=$(gcloud run services describe "$svc" --region="$REGION" \
    --format='value(status.traffic[0].revisionName,status.traffic[0].percent)' \
    2>/dev/null || true)
  if [[ "$serving" == "${latest_rev}	100" ]]; then
    printf "  ✓ %-30s already 100%% on %s\n" "$svc" "$latest_rev"
  else
    printf "  → %-30s promoting to LATEST (was: %s)\n" "$svc" "${serving:-unknown}"
    if ! gcloud run services update-traffic "$svc" --region="$REGION" \
           --to-latest 2>&1 | tail -3; then
      PROMOTE_FAILED=$((PROMOTE_FAILED + 1))
      printf "  ✗ %-30s update-traffic FAILED\n" "$svc"
    fi
  fi
done

if [[ "$PROMOTE_FAILED" -gt 0 ]]; then
  echo "" >&2
  echo "✗ $PROMOTE_FAILED service(s) failed to promote. Manual fix:" >&2
  for svc in "${SERVICES[@]}"; do
    echo "    gcloud run services update-traffic $svc --region=$REGION --to-latest" >&2
  done
  exit 2
fi

# ── 2. Backfill chain (default; --skip-backfill opts out) ────────────────────
# NON-BLOCKING background ingest. These jobs ONLY add NEW Drive clients to the
# DB; they must never gate the deploy or the derived-surfaces refresh below.
#
#   drive_crawler  → discovers + ingests {Client} - DMA folders that are NOT
#                    already ACTIVE (it EXCLUDES the seeded 94), bounded +
#                    parallel so a cold start can't run away (see
#                    workers/drive_crawler/main.py).
#   embedder       → embeds any new evidence / section rows from the crawl.
#
# 2026-06-18 ROOT-CAUSE FIX: this chain used to run with `--wait` (BLOCKING) and
# BEFORE the derived-surfaces refresh. A cold-start crawler doing a sequential
# re-ingest of every folder hung for the whole deploy window, so the repark /
# heal / derive chain (§2c) never ran and the live DB kept its raw junk-named
# duplicate entities — exactly the operator's "94 then defaults to the bad UI".
# We now fire the chain `--async` (fire-and-forget) so it can NEVER block, and
# the deterministic derive chain (§2c) runs to completion regardless. Job
# failures surface in the admin Operations panel. intelligence_recompute is no
# longer here — it runs inside run_derive_chain (§2c).
if [[ "$BACKFILL_MODE" == "run" ]]; then
  echo ""
  echo "→ Dispatching background ingest (async — never blocks the deploy)..."
  CHAIN=(
    "dma-insights-drive-crawler"
    "dma-insights-embedder"
  )
  for job in "${CHAIN[@]}"; do
    if ! gcloud run jobs describe "$job" --region="$REGION" \
           --format='value(name)' >/dev/null 2>&1; then
      printf "  ⚠ %-40s not registered; skipping\n" "$job"
      continue
    fi
    printf "  → dispatching %-38s" "$job"
    if gcloud run jobs execute "$job" --region="$REGION" --async \
         >/tmp/refresh-${job}.log 2>&1; then
      echo " ✓ (running in background)"
    else
      echo " ✗ (see /tmp/refresh-${job}.log)"
    fi
  done
  echo "  ✓ Background ingest dispatched (adds new clients; surfaces in /admin/import)"
fi

# ── 2b. Seed committed corpus into DB (opt-in via --seed-corpus) ─────────────
# Per the 2026-06-07 operator mandate: "Ensure the 100+ DMAs are
# loaded onto the DB and persisted during deployment."
#
# Triggers the historical_backfill Cloud Run Job in --dir mode against
# the corpus path baked into the backend image
# (DMA_SEED_CORPUS_DIR, default /home/app/tests/fixtures/dma_packages_batches).
# The intelligent material_manifest_hash skip (migration 033) makes
# this near-no-op for packages already persisted; only NEW or
# materially-changed packages cost any work. Idempotent re-runs are
# safe.
#
# This is OFF by default to match Drive-only production setups. Enable
# either with --seed-corpus on the command line, or by exporting
# DMA_SEED_CORPUS_ON_DEPLOY=1 in the deploy CI (e.g. via Cloud Build
# substitutions for dev / staging environments). The corpus dir env
# override DMA_SEED_CORPUS_DIR lets the operator point at a different
# location (e.g. a GCS-mounted bucket once the corpus is moved out of
# the image).
if [[ "$SEED_CORPUS_MODE" == "run" ]]; then
  echo ""
  echo "→ Seeding committed DMA corpus into DB (--dir mode)..."
  if ! gcloud run jobs describe dma-insights-historical-backfill \
         --region="$REGION" --format='value(name)' >/dev/null 2>&1; then
    echo "  ⚠ dma-insights-historical-backfill job not registered; skipping seed" >&2
  else
    # Dispatch via DMA_POST_DEPLOY_RUN=seed_corpus — the env-var
    # mechanism that WORKS. The prior --args="--dir,…" execute-override
    # is the exact mechanism §2c documents as silently broken in prod
    # (28ad71a); when the override dropped, the job ran its no-args
    # default — a FULL Drive backfill under --wait (2026-07-04 audit).
    if gcloud run jobs execute dma-insights-historical-backfill \
         --region="$REGION" \
         --update-env-vars="DMA_POST_DEPLOY_RUN=seed_corpus,DMA_SEED_CORPUS_DIR=${SEED_CORPUS_DIR}" \
         --wait >/tmp/refresh-seed-corpus.log 2>&1; then
      # NOTE: gcloud does not stream container stdout; the summary line
      # lives in Cloud Logging, not /tmp/refresh-seed-corpus.log.
      echo "  ✓ Corpus seed job execution succeeded."
      echo "    Summary line ('LOCAL BACKFILL: …') in Cloud Logging:"
      echo "    gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=dma-insights-historical-backfill' --project=\$PROJECT_ID --limit=50 --format='value(textPayload)' | grep 'LOCAL BACKFILL:'"
    else
      echo "  ✗ Corpus seed failed (gcloud execution log: /tmp/refresh-seed-corpus.log;" >&2
      echo "    container output in Cloud Logging, job dma-insights-historical-backfill)" >&2
      # Non-fatal: the deploy is LIVE; the seed is a best-effort data
      # hydration. Re-run manually:
      #   gcloud run jobs execute dma-insights-historical-backfill \
      #     --region=$REGION \
      #     --update-env-vars="DMA_POST_DEPLOY_RUN=seed_corpus" --wait
    fi
  fi
fi

# ── 2c. Derived-surfaces refresh + synthesis warm (always-on, best-effort) ──
# Deterministic DERIVED content first (no tokens): insight cards + SCQA
# backfill for any run the ingest ladder missed, focus areas for
# profile-less entities. Then the Vertex warm sweep (enrich_corpus) —
# honest-cold when creds are absent, 0-token cache hits for AEs when
# they are. All idempotent; failures are non-fatal (lazy paths cover).
echo ""
echo "→ Refreshing derived surfaces + warming synthesis cache..."
if gcloud run jobs describe dma-insights-historical-backfill \
     --region="$REGION" --format='value(name)' >/dev/null 2>&1; then
  # Order matters (2026-06-10 final-tests census):
  #   apply_catalogue_platforms — subcap_scores.platform_tags were NULL
  #     for ALL 63k corpus rows, leaving EVERY D4 platform card at
  #     fit=0 / INSUFFICIENT_EVIDENCE until this ran;
  #   broadcast_peer_medians — 11 packages ship no category peer
  #     medians; the cohort fallback fills them from peer_benchmarks;
  #   then the derive/enrich steps build on the corrected base.
  #   derive_alerts (2026-06-11) — materializes THIN_EVIDENCE alerts
  #     from subcap_scores.is_thin_evidence; before it the alerts table
  #     had NO producer and every alert surface rendered empty.
  #   backfill_run_dates (2026-06-11) — persists assessment_date for
  #     any run still carrying only the ingest wall-clock (idempotent,
  #     only-when-empty; REQ-hex ids stay NULL by contract).
  #   repark_junk_entities (2026-06-11, +2026-06-13) — demotes ACTIVE
  #     entities whose names fail sanity (raw Drive IDs, folder noise,
  #     blanks) into the PENDING_REVIEW admin queue, AND re-slugs
  #     folder-artifact display_ids (mis-rooted ingests) from the real
  #     entity name; pre-gate legacy rows polluted the live dashboard.
  #   heal_entities (2026-06-15) — data-completeness healer: fills the
  #     Overview FIRMOGRAPHICS the leaf parsers missed (assets/AUM, headcount,
  #     regulator, branches/founded/ratios) by reading each ACTIVE entity's
  #     package directly across all schema variants, so NO firmographics panel
  #     is empty for any of the 94. FILL-IF-EMPTY, idempotent, never fabricates.
  #   derive_context (2026-06-15) — fills the D5 timeline for entities whose
  #     package ships no timeline rows, with grounded founding + DMA-assessment
  #     milestones (fill-if-empty, idempotent). Fixes "No timeline events".
  #   heal_all_stages (2026-06-15) — the all-stages completeness gate: heals
  #     firmographics + classifies NULL subverticals, then audits every surface
  #     (Directory/Overview/Insights/Heatmap/Platform/Context/TechStack/Health)
  #     so no page/card/drilldown is empty for any of the 94. Runs LAST so the
  #     derives above have filled their stages first.
  #   derive_recommendations (2026-06-15) — grounded gap→platform recommendations
  #     for entities whose package shipped none, so the D4 roadmap drilldown is
  #     never empty (fill-if-empty). intelligence_recompute --all runs as its own
  #     step below (it lives in workers/, not app.scripts).
  #   clean_techstack (2026-06-15) — drops Explorium metadata rows parsed as
  #     "vendors" (Source/Discovery Method/Confidence Framework…), backfills the
  #     real banking/fintech tech named in the report prose, and GROUNDS every
  #     tech-stack entry with evidence E-IDs + the capability subcaps its
  #     platform family addresses, so the TechStack drilldowns offer
  #     evidence-grounded depth. Runs after apply_catalogue_platforms (needs the
  #     platform_tags it sets). Idempotent.
  #   derive_financials (2026-06-15) — fills the D5 "Financial trajectory" card
  #     (empty for 63/94) by parsing the report's multi-year Net Income / Total
  #     Assets table into a year-series + ratios, falling back to the already-
  #     healed balance-sheet scale (aum_usd) so the card is never empty. Runs
  #     AFTER heal_entities so the aum fallback is populated. Grounded; idempotent.
  #   backfill_recency (2026-06-15) — fills evidence_index.recency_months from
  #     published_date (age at assessment) so the freshness signal is complete +
  #     stable (was published_date-only). Fill-if-empty; new ingests set it inline.
  #   derive_peers (2026-06-15) — persists the individual peer roster from each
  #     package's 06_peers/peer_scores_*.json into entity_peers (matched via the
  #     run_manifest run_id), powering the D5 Context "Peer comparison" card.
  #     Grounded; best-effort (empty when a package ships no per-peer scores).
  #   derive_sentiment (2026-06-15) — fills the D5 "Sentiment overview" card for
  #     entities whose package shipped no sentiment CSV by mining the analyst
  #     report prose (Glassdoor/Indeed/app-store/NPS/J.D. Power…) with the
  #     report's own numbers + a grounded excerpt. Fill-if-empty, never clobbers
  #     a CSV/Clay payload, never invents a rating.
  # 2026-06-18 ROBUSTNESS FIX: this used to fire 21 SEPARATE
  # `gcloud run jobs execute --wait` calls (one per derive module), each
  # paying a fresh Cloud Run cold start + VPC connect, strictly serial, and
  # gated behind the (then-blocking) crawler above — so on the 2026-06-18
  # deploy EVERY one logged "✗ ... lazy path covers" and the live DB was never
  # cleaned. They now run as ONE execution of `run_derive_chain`, which runs
  # the SAME ordered steps as dependency-ordered PARALLEL waves with a
  # per-step timeout (a wedged step is killed, the chain continues). One cold
  # start, faster, and self-healing. It encodes repark → … → intelligence_recompute
  # → heal_all_stages (the ordering rationale above is locked to it by
  # backend/tests/test_derive_chain_contract.py).
  # 2026-06-18 EXECUTION FIX: the 28ad71a deploy showed run_derive_chain +
  # export_startup_data BOTH ✗ while drive_crawler + embedder (same job runner,
  # but executed with NO override) ran fine. The differentiator was overriding
  # the job's `--command`/`--args` on `gcloud run jobs execute` — that override
  # silently fails in the deploy's environment, so the derive chain never ran
  # and the live DB kept its junk-named entities. We now dispatch via
  # DMA_POST_DEPLOY_RUN set with `--update-env-vars` (the SAME override the §3
  # cache-invalidation step uses successfully) and let the job's DEFAULT command
  # (app.scripts.historical_backfill) route to the requested module. On failure
  # we DUMP the log tail so the cause is visible in the deploy output (the prior
  # opaque "✗ lazy path covers" hid every real error).
  printf "  → %-38s" "run_derive_chain (parallel waves)"
  if gcloud run jobs execute dma-insights-historical-backfill \
       --region="$REGION" \
       --update-env-vars="DMA_POST_DEPLOY_RUN=derive_chain" \
       --wait >/tmp/refresh-derive-chain.log 2>&1; then
    echo " ✓ (execution succeeded — step summary in Cloud Logging, job dma-insights-historical-backfill)"
  else
    echo " ✗ (run_derive_chain failed — DB not refreshed; tail below)"
    echo "    ──── tail /tmp/refresh-derive-chain.log ────" >&2
    tail -n 30 /tmp/refresh-derive-chain.log 2>/dev/null | sed 's/^/    │ /' >&2
    echo "    ─────────────────────────────────────────────" >&2
  fi

  # Gemini surface gate (2026-07-02, master plan Part 3.3): after
  # run_derive_chain warmed enrich_corpus + intelligence_recompute against
  # the LIVE DB, assert the Vertex output actually PERSISTED (why_now /
  # platform_story cache rows, parsed_facts._gemini_extracted,
  # intelligence_summary_md, Gemini-clustered focus areas). Dispatched via
  # the same DMA_POST_DEPLOY_RUN mechanism as the derive chain; the job's
  # compute SA already holds roles/aiplatform.user. Best-effort here (the
  # deploy is already live; warming retries lazily) — failures print the
  # per-surface remediation from the gate's log tail. The Cloud Build
  # regen stage + post-deploy-smoke [8/9] are the HARD gates.
  printf "  → %-38s" "qa_gemini_surfaces --mode baked"
  if gcloud run jobs execute dma-insights-historical-backfill \
       --region="$REGION" \
       --update-env-vars="DMA_POST_DEPLOY_RUN=qa_gemini_baked" \
       --wait >/tmp/refresh-qa-gemini.log 2>&1; then
    echo " ✓ (execution succeeded — per-surface summary in Cloud Logging)"
  else
    echo " ✗ (Gemini surfaces cold on the live DB — AI serves deterministic fallbacks; tail below)"
    echo "    ──── tail /tmp/refresh-qa-gemini.log ────" >&2
    tail -n 30 /tmp/refresh-qa-gemini.log 2>/dev/null | sed 's/^/    │ /' >&2
    echo "    ─────────────────────────────────────────" >&2
  fi

  # startup-data parity gate (LAST): the committed startup-data/ snapshot's
  # STRUCTURE (display_id roster, per-client keys, the 4 KPI tile kinds)
  # must match the freshly-derived DB. Structural drift means the committed
  # first-paint payload is shaped wrong → loud failure. Value drift only
  # warns (the live API owns freshness; the snapshot is replaced on the
  # first refetch). Runs in --check mode; the WRITE happens pre-deploy.
  printf "  → %-38s" "export_startup_data --check"
  if gcloud run jobs execute dma-insights-historical-backfill \
       --region="$REGION" \
       --update-env-vars="DMA_POST_DEPLOY_RUN=export_check" \
       --wait >"/tmp/refresh-startup-data.log" 2>&1; then
    echo " ✓ startup-data structure matches DB"
  else
    echo " ✗ STRUCTURAL drift (see /tmp/refresh-startup-data.log)"
    tail -n 20 /tmp/refresh-startup-data.log 2>/dev/null | sed 's/^/    │ /' >&2
  fi
else
  echo "  ⚠ backend job image not registered; skipping derived refresh" >&2
fi

# ── 3. Invalidate stale synthesis cache (opt-in via --invalidate-cache) ──────
# The synthesis_orchestrator fingerprint includes prompt_template_version +
# catalogue_version + grounding_bundle_hash -- so a prompt/catalogue bump
# auto-misses every prior cache row. But pure code-only changes (e.g. a
# retrieval re-rank or a parser fix that affects what evidence enters the
# bundle) do NOT bump the fingerprint, so the operator sees the OLD
# narrative until either: (a) the user clicks "Regenerate", (b) the TTL
# expires, or (c) we invalidate manually. This flag is that manual lever.
#
# We invalidate rows created BEFORE this script started so the next read
# for every surface re-synthesizes against the freshly-deployed code.
# Costs Vertex tokens on the next read for each active surface — that's
# why this is opt-in.
if [[ "$CACHE_MODE" == "run" ]]; then
  echo ""
  echo "→ Invalidating vertex_synthesis_cache rows older than $DEPLOY_STARTED_AT..."
  # We use the migrations job's environment because it already has the
  # DATABASE_URL secret + VPC connector wired up. Cheaper than spinning
  # a one-shot psql + cloud-sql-proxy.
  if ! gcloud run jobs describe dma-insights-migrations --region="$REGION" \
         --format='value(name)' >/dev/null 2>&1; then
    echo "  ⚠ dma-insights-migrations job missing; skipping invalidation" >&2
  else
    INVALIDATE_SQL="UPDATE vertex_synthesis_cache \
SET invalidated_at = NOW(), invalidation_reason = 'post_deploy_refresh' \
WHERE created_at < '${DEPLOY_STARTED_AT}' \
  AND invalidated_at IS NULL"
    # The migrations image already includes psycopg + the DSN; we shell
    # out via the existing python entrypoint, passing a tiny invalidation
    # script via DMA_POST_DEPLOY_SQL env-var. The image's entrypoint
    # honors it when set; falls back to alembic upgrade head otherwise.
    #
    # ^|^ delimiter escape is LOAD-BEARING: gcloud dict-flags split on
    # commas, and INVALIDATE_SQL contains one ("NOW(), invalidation_
    # reason") — without the escape the value TRUNCATES at the comma,
    # and the truncated UPDATE has no WHERE clause: it would invalidate
    # the ENTIRE synthesis cache, forcing full Vertex re-spend on every
    # surface (2026-07-04 line audit).
    if gcloud run jobs execute dma-insights-migrations --region="$REGION" \
         --update-env-vars="^|^DMA_POST_DEPLOY_SQL=${INVALIDATE_SQL}" \
         --wait >/tmp/refresh-invalidate.log 2>&1; then
      # gcloud does not stream container stdout; the "invalidated N
      # rows" line lands in Cloud Logging (job dma-insights-migrations).
      echo "  ✓ Cache invalidation job execution succeeded (row count in Cloud Logging)"
    else
      echo "  ✗ Invalidation job failed (see /tmp/refresh-invalidate.log)" >&2
    fi
  fi
fi

# ── 4. Verify traffic split is fully on LATEST ───────────────────────────────
# Defensive: even after a successful update-traffic, intermittent control-
# plane lag can leave a service split for a few seconds. We re-read and
# fail loudly if drift remains.
if [[ "$VERIFY_MODE" == "run" ]]; then
  echo ""
  echo "→ Verifying every service is 100% on its latest revision..."

  # Count services NOT fully on their latest READY revision, printing a line
  # per service. Sets the global `drift`.
  _count_drift() {
    drift=0
    for svc in "${SERVICES[@]}"; do
      if ! gcloud run services describe "$svc" --region="$REGION" \
             --format='value(name)' >/dev/null 2>&1; then
        continue
      fi
      local latest_rev pct rev
      latest_rev=$(gcloud run services describe "$svc" --region="$REGION" \
        --format='value(status.latestReadyRevisionName)' 2>/dev/null || true)
      pct=$(gcloud run services describe "$svc" --region="$REGION" \
        --format='value(status.traffic[0].percent)' 2>/dev/null || true)
      rev=$(gcloud run services describe "$svc" --region="$REGION" \
        --format='value(status.traffic[0].revisionName)' 2>/dev/null || true)
      if [[ "$rev" == "$latest_rev" && "$pct" == "100" ]]; then
        printf "  ✓ %-30s 100%% on %s\n" "$svc" "$latest_rev"
      else
        printf "  ✗ %-30s %s%% on %s (expected 100%% on %s)\n" \
               "$svc" "$pct" "$rev" "$latest_rev"
        drift=$((drift + 1))
      fi
    done
  }

  _count_drift
  # Drift here usually means a revision became READY only AFTER our initial
  # promote (control-plane lag / slow cold start). Rather than bail and leave
  # the backend pinned to the prior revision, RE-PROMOTE with backoff — this
  # is the loop that actually lands traffic on the new revision.
  if [[ "$drift" -gt 0 ]]; then
    for attempt in 1 2 3; do
      local_wait=$((attempt * 15))
      echo "  … re-promoting to LATEST (attempt ${attempt}/3, after ${local_wait}s)..." >&2
      sleep "$local_wait"
      for svc in "${SERVICES[@]}"; do
        gcloud run services update-traffic "$svc" --region="$REGION" \
          --to-latest >/dev/null 2>&1 || true
      done
      echo "  → re-checking traffic split..."
      _count_drift
      [[ "$drift" -eq 0 ]] && break
    done
  fi

  if [[ "$drift" -gt 0 ]]; then
    echo "" >&2
    echo "✗ $drift service(s) still split after re-promotion. The newest" >&2
    echo "  revision may be unhealthy (failing its startup probe). Inspect:" >&2
    for svc in "${SERVICES[@]}"; do
      echo "    gcloud run revisions list --service=$svc --region=$REGION" >&2
    done
    exit 2
  fi
  echo "  ✓ All services 100% on their latest revision."
fi

echo ""
echo "✓ Post-deploy refresh complete."
echo "  Operator should see fresh evidence + subcap counts on next page load."
