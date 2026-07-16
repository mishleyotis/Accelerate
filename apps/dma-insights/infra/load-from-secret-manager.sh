#!/usr/bin/env bash
#
# load-from-secret-manager.sh — pull the most-recent value of every
# known DMA Insights secret from Google Secret Manager, export it into
# the current shell, AND persist it to `.deploy.parameters.env` so a
# fresh Cloud Shell session can `source` it back without re-running.
#
# This is the canonical first step of DEPLOYMENT.md §0.2: it removes
# the need to manually re-source secrets every time the operator opens
# Cloud Shell. The script is fully idempotent + read-only against
# Secret Manager (it never WRITES to Secret Manager — that's §0.5.1).
#
# Usage (Cloud Shell):
#   export PROJECT_ID=digital-maturity-assessor
#   bash infra/load-from-secret-manager.sh                # detect + print
#   source <(bash infra/load-from-secret-manager.sh --emit-exports)
#   bash infra/load-from-secret-manager.sh --write-env    # persist to file
#
# Exit codes:
#   0 — every secret found (or the script ran in --emit-exports mode)
#   1 — at least one secret missing
#   2 — unsupported flag OR PROJECT_ID unset
#
# Self-healing contract:
#   * Missing values are listed verbatim — operator sees what to set.
#   * Present values are echoed with masking (first 6 chars only).
#   * Failure of one secret never short-circuits the others.
#   * NEVER calls `exit 1` from a context that would kill an interactive
#     shell — uses `return 1` when sourced.

set -uo pipefail
_NF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "${_NF_DIR}/gcloud-noise-filter.sh" ] && . "${_NF_DIR}/gcloud-noise-filter.sh"

MODE="detect"
for arg in "$@"; do
  case "$arg" in
    --emit-exports) MODE="emit" ;;
    --write-env)    MODE="write_env" ;;
    --help|-h)
      sed -n '2,30p' "$0"
      exit 0
      ;;
    *)
      echo "FATAL: unknown flag '$arg' — see --help" >&2
      exit 2
      ;;
  esac
done

if [[ -z "${PROJECT_ID:-}" ]]; then
  echo "FATAL: PROJECT_ID env var required (export PROJECT_ID=...)" >&2
  exit 2
fi

# Known secrets — one row per env var that maps to a Secret Manager id.
# The order here is the order the loader prints; keep alphabetical for
# operator readability.
declare -a SECRET_VARS=(
  CLAY_WEBHOOK_SECRET
  CLAY_WEBHOOK_URL
  DATABASE_URL
  DATABASE_URL_SYNC
  DMA_BOT_API_KEY
  GOOGLE_OAUTH_CLIENT_SECRET
  RAG_API_BEARER_KEY
  REDIS_URL
)
declare -A SECRET_ID=(
  [CLAY_WEBHOOK_SECRET]=dma-insights-clay-webhook-secret
  [CLAY_WEBHOOK_URL]=dma-insights-clay-webhook-url
  [DATABASE_URL]=dma-insights-database-url
  [DATABASE_URL_SYNC]=dma-insights-database-url-sync
  [DMA_BOT_API_KEY]=dma-insights-bot-api-key
  [GOOGLE_OAUTH_CLIENT_SECRET]=dma-insights-oauth-client-secret
  [RAG_API_BEARER_KEY]=dma-insights-rag-api-key
  [REDIS_URL]=dma-insights-redis-url
)

# Probe each secret. Build three lists: present, missing, and the
# emit-exports payload (for `source <(...)`).
declare -A SECRET_VAL=()
declare -a present_list=()
declare -a missing_list=()

for var in "${SECRET_VARS[@]}"; do
  sid="${SECRET_ID[$var]}"
  if val="$(gcloud secrets versions access latest \
              --secret="$sid" --project="$PROJECT_ID" 2>/dev/null)" \
       && [[ -n "$val" ]]; then
    SECRET_VAL["$var"]="$val"
    present_list+=("$var")
  else
    missing_list+=("$var")
  fi
done

# Helper: when both Clay secrets are missing AND DMA_CLAY_DEFERRED isn't
# already set, treat the absence as deferred (ADR 0010 — Clay client
# fail-closes on empty secret). Mirrors the §0.2 env-writer's auto-
# defer so the operator gets the same behavior whichever entry path
# they use. Splits Clay out of `missing_list` so write_env doesn't
# count it against the exit code, and emits an `export
# DMA_CLAY_DEFERRED=1` so `source <(... --emit-exports)` carries it
# back to the shell.
clay_missing=0
for var in "${missing_list[@]}"; do
  [[ "$var" == "CLAY_WEBHOOK_URL" || "$var" == "CLAY_WEBHOOK_SECRET" ]] \
    && clay_missing=$((clay_missing + 1))
done
CLAY_AUTO_DEFERRED=0
if [[ "$clay_missing" -ge 2 && -z "${DMA_CLAY_DEFERRED:-}" ]]; then
  CLAY_AUTO_DEFERRED=1
fi

case "$MODE" in
  emit)
    # Print one `export VAR='value'` per present secret. Caller sources
    # via process substitution: `source <(... --emit-exports)`.
    # Single-quote escape any embedded apostrophes by closing-and-
    # re-opening the quote (POSIX safe).
    for var in "${present_list[@]}"; do
      val="${SECRET_VAL[$var]}"
      # Replace "'" with "'\''"
      esc="${val//\'/\'\\\'\'}"
      printf "export %s='%s'\n" "$var" "$esc"
    done
    # Auto-defer Clay if both secrets are missing (the loader hasn't
    # been asked to populate them yet AND the operator hasn't set the
    # flag). Print to stderr so the user sees the message even when
    # sourcing via process substitution.
    if [[ "$CLAY_AUTO_DEFERRED" -eq 1 ]]; then
      printf "export DMA_CLAY_DEFERRED=1\n"
      echo "ℹ Auto-deferring Clay (both CLAY_WEBHOOK_* missing in Secret Manager)." >&2
    fi
    # Missing vars: `source <(...)` consumes stdout comments INVISIBLY
    # and discards the exit code, so a silent miss here meant the
    # operator deployed with DATABASE_URL unset (2026-07-04 line audit).
    # Three-layer fail-loud: (a) stderr block the operator actually
    # sees; (b) an exported DMA_SECRETS_MISSING sentinel that
    # preflight-parameters.sh fails closed on (the deploy gate that
    # ALWAYS runs); (c) exit 1 for callers that do check.
    real_missing=()
    for v in "${missing_list[@]}"; do
      if [[ "$CLAY_AUTO_DEFERRED" -eq 1 \
            && ( "$v" == "CLAY_WEBHOOK_URL" || "$v" == "CLAY_WEBHOOK_SECRET" ) ]]; then
        continue
      fi
      # Clay already deferred by an explicit operator flag counts as
      # handled too (matches the validation pass in preflight).
      if [[ "${DMA_CLAY_DEFERRED:-0}" == "1" \
            && ( "$v" == "CLAY_WEBHOOK_URL" || "$v" == "CLAY_WEBHOOK_SECRET" ) ]]; then
        continue
      fi
      real_missing+=("$v")
    done
    for var in "${missing_list[@]}"; do
      printf "# MISSING: %s (Secret Manager id=%s)\n" \
        "$var" "${SECRET_ID[$var]}"
    done
    if (( ${#real_missing[@]} > 0 )); then
      printf "export DMA_SECRETS_MISSING='%s'\n" "${real_missing[*]}"
      {
        echo "✗ ${#real_missing[@]} REQUIRED secret(s) missing from Secret Manager:"
        for v in "${real_missing[@]}"; do
          echo "    • $v (id=${SECRET_ID[$v]})"
        done
        echo "  The deploy preflight will fail closed on DMA_SECRETS_MISSING."
        echo "  Populate them (DEPLOYMENT.md §0.2.x / §0.5.1) and re-source."
      } >&2
      exit 1
    fi
    # All required secrets present — clear any stale sentinel from a
    # prior failed source in the same shell.
    printf "unset DMA_SECRETS_MISSING\n"
    exit 0
    ;;

  write_env)
    # Persist the present secrets into `.deploy.parameters.env` (creates
    # if missing; merges into existing). The merge keeps any non-secret
    # vars the operator added by hand.
    ENV_FILE=".deploy.parameters.env"
    TMP_FILE="$(mktemp)"
    if [[ -f "$ENV_FILE" ]]; then
      # Drop the prior values of the secrets we're about to write.
      grep -vE "^($(IFS='|'; echo "${SECRET_VARS[*]}"))=" \
        "$ENV_FILE" > "$TMP_FILE" || true
    fi
    {
      echo "# secrets refreshed from Secret Manager at $(date -Iseconds)"
      # Auto-defer Clay BEFORE the secrets list so the deferral state
      # is at the top of the file (matches §0.2 env-writer ordering).
      if [[ "$CLAY_AUTO_DEFERRED" -eq 1 ]]; then
        echo "DMA_CLAY_DEFERRED=1"
      fi
      for var in "${present_list[@]}"; do
        val="${SECRET_VAL[$var]}"
        # Interior newlines would corrupt the file's line-based re-run
        # merge (grep -vE strips only the FIRST physical line of a
        # multi-line value → dangling quote → unsourceable file). Skip
        # writing such a value; the shell export path still carries it
        # (2026-07-04 line audit).
        if [[ "$val" == *$'\n'* ]]; then
          echo "  ⚠ $var contains a newline — NOT persisted to the env file" >&2
          echo "    (use \`source <(... --emit-exports)\` for this one)" >&2
          continue
        fi
        esc="${val//\'/\'\\\'\'}"
        printf "%s='%s'\n" "$var" "$esc"
      done
    } >> "$TMP_FILE"
    mv "$TMP_FILE" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    echo "✓ wrote ${#present_list[@]} secret(s) to $ENV_FILE"
    if [[ "$CLAY_AUTO_DEFERRED" -eq 1 ]]; then
      echo "ℹ Auto-deferred Clay (DMA_CLAY_DEFERRED=1 written to $ENV_FILE)."
    fi
    # Separate "Clay deferred" (a soft, expected miss) from real misses.
    # If Clay is auto-deferred, drop its rows from the missing report so
    # the operator doesn't see a misleading "still missing" list for
    # something the loader already handled.
    real_missing=()
    for v in "${missing_list[@]}"; do
      if [[ "$CLAY_AUTO_DEFERRED" -eq 1 \
            && ( "$v" == "CLAY_WEBHOOK_URL" || "$v" == "CLAY_WEBHOOK_SECRET" ) ]]; then
        continue
      fi
      real_missing+=("$v")
    done
    if (( ${#real_missing[@]} > 0 )); then
      echo "✗ ${#real_missing[@]} secret(s) still missing:"
      for v in "${real_missing[@]}"; do
        echo "    • $v (id=${SECRET_ID[$v]})"
      done
      exit 1
    fi
    exit 0
    ;;

  detect|*)
    # Human-readable report. NEVER exit 1 in a way that kills an
    # interactive shell; we use `exit` here because this is the
    # standalone-script path, not a sourced path.
    echo "→ Probing Secret Manager (project=$PROJECT_ID)…"
    for var in "${SECRET_VARS[@]}"; do
      sid="${SECRET_ID[$var]}"
      if [[ -n "${SECRET_VAL[$var]:-}" ]]; then
        val="${SECRET_VAL[$var]}"
        short="${val:0:6}…"
        printf "  ✓ %-30s  loaded from %s  (%d chars, starts %s)\n" \
          "$var" "$sid" "${#val}" "$short"
      else
        printf "  ✗ %-30s  MISSING from %s\n" "$var" "$sid"
      fi
    done
    echo
    if (( ${#missing_list[@]} == 0 )); then
      echo "✓ All ${#SECRET_VARS[@]} secrets present."
      echo "  Run \`source <(bash infra/load-from-secret-manager.sh --emit-exports)\` to load them."
      echo "  Or  \`bash infra/load-from-secret-manager.sh --write-env\` to persist."
    else
      # Surface auto-deferred Clay separately so the operator sees that
      # the loader handled the soft-miss case automatically.
      real_missing=()
      for v in "${missing_list[@]}"; do
        if [[ "$CLAY_AUTO_DEFERRED" -eq 1 \
              && ( "$v" == "CLAY_WEBHOOK_URL" || "$v" == "CLAY_WEBHOOK_SECRET" ) ]]; then
          continue
        fi
        real_missing+=("$v")
      done
      if [[ "$CLAY_AUTO_DEFERRED" -eq 1 ]]; then
        echo "ℹ Clay auto-deferred (CLAY_WEBHOOK_URL + CLAY_WEBHOOK_SECRET not in"
        echo "  Secret Manager; --emit-exports / --write-env will set"
        echo "  DMA_CLAY_DEFERRED=1 for you per ADR 0010)."
      fi
      if (( ${#real_missing[@]} > 0 )); then
        echo "✗ ${#real_missing[@]} secret(s) missing — follow DEPLOYMENT.md §0.2.x:"
        for v in "${real_missing[@]}"; do
          echo "    • $v   →   set per §0.2.x then re-run §0.5.1 (create-or-update)"
        done
        exit 1
      fi
      # All "real" misses resolved (only Clay was missing) — exit clean.
      echo "✓ All required secrets present (Clay deferred)."
    fi
    ;;
esac
