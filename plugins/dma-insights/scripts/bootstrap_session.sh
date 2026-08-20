#!/usr/bin/env bash
# DMA Insights — environment setup script for fresh session containers.
#
# WHY THIS EXISTS (measured 2026-08-19): a fresh container in the CCR
# environment has python3/node/git/curl and NOTHING else this product
# needs — no gcloud, no Google identity, no plugin, no repo when the
# session was fired by a trigger, and its disk does not survive container
# reclaim. Plugins register their MCP tools at session START, so this
# provisioning cannot run as a step inside the session; it must run as the
# ENVIRONMENT SETUP SCRIPT (claude.ai/code -> environment settings), which
# executes before the session begins. Wire it there as:
#
#   curl -sfL https://raw.githubusercontent.com/mishleyotis/Accelerate/claude/dma-insights-onboarding-0ryrd0/plugins/dma-insights/scripts/bootstrap_session.sh | bash
#
# and set ONE environment variable in the same settings screen:
#
#   DMA_ROUTINE_SA_KEY   — the dmai-routine@ service-account key JSON.
#                          Retrieval (Cloud Shell):
#                          gcloud secrets versions access latest \
#                            --secret=dmai-routine-sa-key \
#                            --project=digital-maturity-assessor
#
# The key is deliberately weak: run.invoker on dmai-mcp and dmai-api plus
# secretAccessor on dmai-mcp-path-token, nothing else. It must NEVER be
# committed — this repository is public.
#
# Fail-open by design: a session that starts without the plugin is caught
# by every routine's STEP 0 and stops honestly; a setup script that blocks
# session start entirely is a worse failure mode. Every problem is logged
# loudly instead.
set -uo pipefail

log() { echo "dma-bootstrap: $*"; }

REPO_DIR="${DMA_REPO_DIR:-/home/user/Accelerate}"
REPO_URL="https://github.com/mishleyotis/Accelerate"
# Until PR #2 merges, the plugin's source of record is the working branch;
# after the merge, flip this default to main.
BRANCH="${DMA_REPO_BRANCH:-claude/dma-insights-onboarding-0ryrd0}"
MCP_URL="${DMA_MCP_HOST:-https://dmai-mcp-dukrne5v4a-uc.a.run.app}"
KEY_FILE="${DMA_SA_KEY_FILE:-/root/.dma/sa.json}"
PROJECT="digital-maturity-assessor"

# ---- 1 · the repository (public — anonymous clone works) ----------------
if [ ! -d "$REPO_DIR/.git" ]; then
  log "cloning $REPO_URL @ $BRANCH"
  git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" 2>&1 | tail -1 \
    || log "clone FAILED — plugin install below will also fail"
else
  git -C "$REPO_DIR" fetch origin "$BRANCH" 2>/dev/null \
    && git -C "$REPO_DIR" checkout -q "$BRANCH" 2>/dev/null \
    && git -C "$REPO_DIR" merge -q --ff-only "origin/$BRANCH" 2>/dev/null \
    || log "repo present but could not fast-forward $BRANCH (continuing on what is checked out)"
fi

# ---- 2 · the service-account key from the environment variable ----------
# The environment-settings field is .env format — one KEY=value per line —
# so the multi-line key JSON cannot be pasted raw (measured 2026-08-20:
# "Couldn't parse ... Use KEY=value format"). DMA_ROUTINE_SA_KEY_B64 is the
# supported spelling: the key JSON base64-encoded to a single line. The raw
# spelling still works for contexts that can carry newlines.
mkdir -p "$(dirname "$KEY_FILE")" && chmod 700 "$(dirname "$KEY_FILE")"
if [ -n "${DMA_ROUTINE_SA_KEY_B64:-}" ]; then
  umask 077
  printf '%s' "$DMA_ROUTINE_SA_KEY_B64" | base64 -d > "$KEY_FILE" 2>/dev/null \
    || log "DMA_ROUTINE_SA_KEY_B64 did not base64-decode"
elif [ -n "${DMA_ROUTINE_SA_KEY:-}" ]; then
  umask 077
  printf '%s' "$DMA_ROUTINE_SA_KEY" > "$KEY_FILE"
fi
if [ -s "$KEY_FILE" ] && ! python3 -c "import json;json.load(open('$KEY_FILE'))" 2>/dev/null; then
  log "key file does not parse as JSON — check the pasted value"
fi
if [ ! -s "$KEY_FILE" ]; then
  log "DMA_ROUTINE_SA_KEY_B64 is not set and no key file exists — connector"
  log "auth will 403. Set the variable in the environment settings."
fi

# ---- 3 · the connector path token, fresh from Secret Manager ------------
# Fetched per boot so a rotation needs no client-side update anywhere.
PATHTOK=""
if [ -s "$KEY_FILE" ]; then
  ACT="$(python3 "$REPO_DIR/plugins/dma-insights/scripts/gcp_token.py" access --key "$KEY_FILE" 2>/dev/null)" || ACT=""
  if [ -n "$ACT" ]; then
    PATHTOK="$(curl -sf -H "Authorization: Bearer $ACT" \
      "https://secretmanager.googleapis.com/v1/projects/$PROJECT/secrets/dmai-mcp-path-token/versions/latest:access" \
      | python3 -c 'import sys,json,base64;sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())' 2>/dev/null)" || PATHTOK=""
  fi
  [ -n "$PATHTOK" ] || log "could not fetch the connector path token from Secret Manager"
fi

# ---- 4 · the plugin, installed from the repo marketplace ----------------
if command -v claude >/dev/null 2>&1; then
  claude plugin marketplace add "$REPO_DIR" >/dev/null 2>&1 \
    || claude plugin marketplace update zennify-dma >/dev/null 2>&1 \
    || log "marketplace add/update failed"
  INSTALL_ARGS=(--scope user --config "mcp_base_url=$MCP_URL" --config "repo_root=$REPO_DIR")
  [ -n "$PATHTOK" ] && INSTALL_ARGS+=(--config "mcp_path_token=$PATHTOK")
  claude plugin install dma-insights@zennify-dma "${INSTALL_ARGS[@]}" >/dev/null 2>&1 \
    || claude plugin update dma-insights@zennify-dma >/dev/null 2>&1 \
    || log "plugin install failed"
  claude plugin enable dma-insights@zennify-dma >/dev/null 2>&1 || true
  log "plugin state: $(claude plugin list 2>/dev/null | grep -A2 'dma-insights@zennify-dma' | tr '\n' ' ' | tr -s ' ')"
else
  log "claude CLI not found — cannot install the plugin"
fi

# ---- 5 · skill script dependencies (pandas et al., wheel-only) ----------
if [ -x "$REPO_DIR/plugins/dma-insights/scripts/dma-deps" ]; then
  "$REPO_DIR/plugins/dma-insights/scripts/dma-deps" install >/dev/null 2>&1 \
    && log "skill script dependencies installed" \
    || log "dma-deps install failed — skills needing pandas/matplotlib will degrade"
fi

# ---- 6 · prove the wire before the session starts -----------------------
# The one check that matters: an ID token minted from the key opens the
# connector and the tool roster answers. Codes only, never tokens.
if [ -s "$KEY_FILE" ] && [ -n "$PATHTOK" ]; then
  IDT="$(python3 "$REPO_DIR/plugins/dma-insights/scripts/gcp_token.py" id --audience "$MCP_URL" --key "$KEY_FILE" 2>/dev/null)" || IDT=""
  if [ -n "$IDT" ]; then
    CODE="$(curl -s -o /tmp/dma_boot_probe -w '%{http_code}' -X POST "$MCP_URL/mcp/$PATHTOK" \
      -H "Authorization: Bearer $IDT" -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')"
    NTOOLS="$(python3 - <<'PY' 2>/dev/null
import json, re
raw = open("/tmp/dma_boot_probe").read()
m = re.search(r"data: (\{.*\})", raw)
d = json.loads(m.group(1) if m else raw)
print(len(d.get("result", {}).get("tools", [])))
PY
)" || NTOOLS="?"
    rm -f /tmp/dma_boot_probe
    log "connector probe: HTTP $CODE, $NTOOLS tools advertised"
  else
    log "connector probe skipped: ID token did not mint"
  fi
fi

log "done"
exit 0
