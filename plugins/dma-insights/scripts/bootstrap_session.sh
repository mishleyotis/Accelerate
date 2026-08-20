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

# TRACE-PROOFING, and it is not optional. On 2026-08-20 a routine session ran
# this script as `bash -x` to capture its log lines for a report; xtrace
# expanded every command, printing the base64 service-account key, a minted
# OAuth access token, a signed identity JWT and the connector's capability URL
# into the transcript. Both credentials had to be rotated. A script that
# handles secrets must not be traceable into a log by a caller who only wanted
# verbose output, so tracing is turned off HERE, where the secrets are,
# whatever the caller asked for. The log lines below are the supported way to
# see what this script did; they name states, never values.
set +x
export PS4=''

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
# supported spelling: the key JSON base64-encoded to ONE line, generated
# with `gcloud secrets versions access latest --secret=dmai-routine-sa-key
# --project=digital-maturity-assessor | base64 -w0` and pasted unquoted.
# Decode and validation live in gcp_token.py ensure-key, which tolerates
# the measured paste imperfections (76-column wraps, quotes, stripped
# padding, urlsafe alphabet, a zsh %-tail), refuses a value that is not a
# service-account key BY NAME, and writes the file 0600. Every consumer
# (mcp_auth_headers.sh, drive_fetch.py, mcp_proxy.py) reads the key through
# the same load_key rungs, so even when THIS script never ran — the
# provisioning-lottery case — the first in-session use self-heals the file
# from the environment variable.
mkdir -p "$(dirname "$KEY_FILE")" && chmod 700 "$(dirname "$KEY_FILE")"
if [ -f "$REPO_DIR/plugins/dma-insights/scripts/gcp_token.py" ]; then
  ENSURE="$(python3 "$REPO_DIR/plugins/dma-insights/scripts/gcp_token.py" ensure-key --key "$KEY_FILE" 2>&1)" \
    && log "$ENSURE" \
    || { log "$ENSURE"; log "connector auth will 403 until DMA_ROUTINE_SA_KEY_B64 is fixed in the environment settings (see retrieval command in the header above)"; }
elif [ -n "${DMA_ROUTINE_SA_KEY_B64:-}" ]; then
  # clone failed, so decode inline — python3 mirrors ensure-key's tolerance
  umask 077
  python3 - > "$KEY_FILE" <<'PY' 2>/dev/null || log "DMA_ROUTINE_SA_KEY_B64 did not decode (and the repo clone failed, so ensure-key is unavailable)"
import base64, json, os, sys
raw = "".join(os.environ["DMA_ROUTINE_SA_KEY_B64"].split()).strip("'\"").rstrip("%")
raw = raw.replace("-", "+").replace("_", "/")
raw += "=" * (-len(raw) % 4)
sys.stdout.write(json.dumps(json.loads(base64.b64decode(raw))))
PY
  [ -s "$KEY_FILE" ] || rm -f "$KEY_FILE"
fi
if [ ! -s "$KEY_FILE" ]; then
  log "no key file and no usable DMA_ROUTINE_SA_KEY_B64 — connector auth"
  log "will 403. Set the variable in the environment settings."
fi

# ---- 3 · the connector path token, fresh from Secret Manager ------------
# Fetched per boot so a rotation needs no client-side update anywhere. The
# token is no longer plugin config (the URL is static /mcp and the token
# travels as a header) — it lands in the cache file mcp_auth_headers.sh
# reads, so the helper skips a Secret Manager round-trip per connection.
PATHTOK=""
if [ -s "$KEY_FILE" ]; then
  ACT="$(python3 "$REPO_DIR/plugins/dma-insights/scripts/gcp_token.py" access --key "$KEY_FILE" 2>/dev/null)" || ACT=""
  if [ -n "$ACT" ]; then
    PATHTOK="$(curl -sf -H "Authorization: Bearer $ACT" \
      "https://secretmanager.googleapis.com/v1/projects/$PROJECT/secrets/dmai-mcp-path-token/versions/latest:access" \
      | python3 -c 'import sys,json,base64;sys.stdout.write(base64.b64decode(json.load(sys.stdin)["payload"]["data"]).decode())' 2>/dev/null)" || PATHTOK=""
  fi
  if [ -n "$PATHTOK" ]; then
    ( umask 077 && printf '%s' "$PATHTOK" > "$(dirname "$KEY_FILE")/pathtok" ) \
      || log "could not cache the path token beside the key"
  else
    log "could not fetch the connector path token from Secret Manager"
  fi
fi

# ---- 4 · the plugin, installed from the repo marketplace ----------------
# Refuse to register a marketplace from a directory that does not hold one.
# Measured 2026-08-20: run with DMA_REPO_DIR pointing at a path that did not
# exist (a test harness), `claude plugin marketplace add` accepted it anyway
# and rewrote the caller's settings.json to a dead source — a working install
# was replaced by a broken one because the clone had failed silently earlier.
# A provisioning script must leave a half-provisioned machine no worse than
# it found it.
if [ ! -f "$REPO_DIR/.claude-plugin/marketplace.json" ]; then
  log "no marketplace manifest at $REPO_DIR/.claude-plugin/marketplace.json —"
  log "skipping plugin install rather than registering a dead source"
elif command -v claude >/dev/null 2>&1; then
  # THE ||-CHAIN TRAP (measured 2026-08-20, five consecutive dead firings):
  # `marketplace add` on an already-registered marketplace exits 0 WITHOUT
  # refreshing, and `plugin install` on an already-installed plugin exits 0
  # WITHOUT updating — so on a container restored from a snapshot the whole
  # chain short-circuits on success-shaped no-ops and the session starts on
  # the snapshot's ancient plugin (0.2.0 observed), which fails STEP 0's
  # version floor and kills the firing in minutes. Update steps therefore
  # run UNCONDITIONALLY, and the installed version is verified against the
  # repo's own plugin.json at the end — a mismatch is logged loudly.
  claude plugin marketplace add "$REPO_DIR" >/dev/null 2>&1 || true
  claude plugin marketplace update zennify-dma >/dev/null 2>&1 \
    || log "marketplace update failed"
  INSTALL_ARGS=(--scope user --config "mcp_base_url=$MCP_URL" --config "repo_root=$REPO_DIR")
  claude plugin install dma-insights@zennify-dma "${INSTALL_ARGS[@]}" >/dev/null 2>&1 || true
  claude plugin update dma-insights@zennify-dma >/dev/null 2>&1 \
    || log "plugin update failed"
  claude plugin enable dma-insights@zennify-dma >/dev/null 2>&1 || true
  WANT="$(python3 -c "import json;print(json.load(open('$REPO_DIR/plugins/dma-insights/.claude-plugin/plugin.json'))['version'])" 2>/dev/null)" || WANT=""
  # PRUNE STALE CACHED VERSIONS (measured 2026-08-20, second binding killer):
  # after an update the old version's cache dir remains beside the new one,
  # and a session can resolve the STALE .mcp.json — a 0.2.0 http config with
  # an unresolvable path-token variable shadowed the 0.6.8 stdio proxy, so
  # `plugin list` said 0.6.8 while the session bound nothing. Keep only the
  # version the repo ships.
  if [ -n "$WANT" ] && [ -d "$HOME/.claude/plugins/cache/zennify-dma/dma-insights" ]; then
    for d in "$HOME"/.claude/plugins/cache/zennify-dma/dma-insights/*/; do
      v="$(basename "$d")"
      [ "$v" = "$WANT" ] || { rm -rf "$d" && log "pruned stale plugin cache $v"; }
    done
  fi
  HAVE="$(claude plugin list 2>/dev/null | grep -A2 'dma-insights@zennify-dma' | grep -o 'Version: [0-9.]*' | head -1 | cut -d' ' -f2)" || HAVE=""
  if [ -n "$WANT" ] && [ "$HAVE" != "$WANT" ]; then
    log "PLUGIN VERSION MISMATCH: installed ${HAVE:-none}, repo ships $WANT —"
    log "the session will fail its version floor; plugin update above must be fixed"
  else
    log "plugin at ${HAVE:-unknown} (repo ships ${WANT:-unknown})"
  fi
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
