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
# THE CHECKOUT IS THE MARKETPLACE, so this step decides which plugin version
# the session binds. `.claude/settings.json` registers zennify-dma as a
# DIRECTORY source pointing at $REPO_DIR, and Claude Code installs enabled
# plugins from it at session start — before any prompt runs. So a checkout
# that is behind at this moment is a session that binds a plugin that is
# behind, and no STEP 0 inside the session can undo it: agents, skills and
# hooks load once.
#
# That is the whole shape of the livelock measured 2026-08-23/24 and reported
# by two synthesis firings: container arrives with a stale checkout (136
# commits behind, clean working tree — which looks perfectly healthy), the
# plugin installs from it at 0.6.2, the routine's STEP 0 then fetches the
# branch, plugin_version.py correctly reports STALE against the now-current
# checkout, the routine updates the install to 0.9.7, re-checks, gets
# UPDATED_MID_SESSION — the disk is right and the session is not — and ends
# the firing without producing. The next firing repeats it exactly. Nothing
# is broken anywhere and no client is ever produced.
#
# `merge --ff-only` was the wrong verb for this: it fails on a detached HEAD,
# on any divergence, and on a dirty tree, and the old ||-chain then logged
# "continuing on what is checked out" and installed the plugin from the stale
# tree anyway — fail-open, at the one point in provisioning where failing
# open pins the defect for every firing that follows. A routine container's
# checkout is disposable, so the right verb is a hard reset to the branch
# tip; a tree with LOCAL MODIFICATIONS is somebody's work and is never reset,
# it is reported instead.
CHECKOUT_STATE="unknown"
CHECKOUT_NOTE=""
if [ ! -d "$REPO_DIR/.git" ]; then
  log "cloning $REPO_URL @ $BRANCH"
  if git clone --branch "$BRANCH" "$REPO_URL" "$REPO_DIR" 2>&1 | tail -1; then
    CHECKOUT_STATE="cloned"
  else
    CHECKOUT_STATE="clone_failed"
    CHECKOUT_NOTE="clone of $BRANCH failed"
    log "clone FAILED — plugin install below will also fail"
  fi
elif ! git -C "$REPO_DIR" fetch origin "$BRANCH" 2>/dev/null; then
  CHECKOUT_STATE="fetch_failed"
  CHECKOUT_NOTE="could not fetch origin/$BRANCH"
  log "FETCH FAILED for $BRANCH — cannot tell whether this checkout is current"
elif [ -n "$(git -C "$REPO_DIR" status --porcelain --untracked-files=no 2>/dev/null)" ]; then
  # Tracked files differ from HEAD: real work. Never discarded.
  CHECKOUT_STATE="dirty"
  CHECKOUT_NOTE="working tree has local modifications; not reset"
  log "checkout has LOCAL MODIFICATIONS — refusing to reset it; the plugin"
  log "installed below is whatever this tree holds, which may not be $BRANCH"
else
  # Clean tree: reset covers every shape the measured failures took —
  # behind, detached, or on another branch entirely.
  if git -C "$REPO_DIR" checkout -q -B "$BRANCH" "origin/$BRANCH" 2>/dev/null \
     && git -C "$REPO_DIR" reset -q --hard "origin/$BRANCH" 2>/dev/null; then
    CHECKOUT_STATE="reset"
  else
    CHECKOUT_STATE="reset_failed"
    CHECKOUT_NOTE="could not reset a clean tree to origin/$BRANCH"
    log "could not reset to origin/$BRANCH on a clean tree — unexpected"
  fi
fi

# VERIFY rather than assume: the states above say what was attempted, this
# says what is true. It is the fact plugin_version.py needs to tell a stale
# BIND apart from a stale CHECKOUT, and they have different fixes.
HEAD_SHA="$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo '')"
ORIGIN_SHA="$(git -C "$REPO_DIR" rev-parse "origin/$BRANCH" 2>/dev/null || echo '')"
if [ -n "$HEAD_SHA" ] && [ "$HEAD_SHA" = "$ORIGIN_SHA" ]; then
  CHECKOUT_CURRENT=true
  log "checkout at origin/$BRANCH ($(git -C "$REPO_DIR" rev-parse --short HEAD 2>/dev/null), $CHECKOUT_STATE)"
else
  CHECKOUT_CURRENT=false
  BEHIND="$(git -C "$REPO_DIR" rev-list --count "HEAD..origin/$BRANCH" 2>/dev/null || echo '?')"
  [ -n "$CHECKOUT_NOTE" ] || CHECKOUT_NOTE="HEAD is not origin/$BRANCH"
  log "CHECKOUT IS NOT $BRANCH ($CHECKOUT_STATE, $BEHIND commits behind) —"
  log "the plugin installed below comes from THIS tree, so the session will"
  log "bind that version; $CHECKOUT_NOTE"
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
WANT=""
HAVE=""
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

# ---- 4b · the breadcrumb, so a stale session can name its own cause -----
# WHY A FILE AND NOT A LOG LINE. Everything this script logs is written
# before the session exists and is read by nobody: the setup script's output
# does not reach the session's transcript, so from inside a firing there is
# no way to tell these three apart —
#
#   1. this script never ran (the environment setup field is empty, or the
#      curl failed) — the plugin then comes from whatever the container image
#      or snapshot carried, which is how 0.2.0 and 0.6.2 both survived;
#   2. it ran and could not bring the checkout to the branch tip, so it
#      installed the plugin from a stale tree;
#   3. it ran, the checkout was current, the install matched — and the
#      session STILL bound something older, which is a different bug.
#
# All three surface inside a firing as the same two words, STALE or
# UPDATED_MID_SESSION, and the routines' answer to both is "end the firing,
# the next one picks it up". When the cause is (1) or (2) the next one does
# not pick it up, because the next container reproduces it; the routines then
# report the same non-failure forever and produce nothing. plugin_version.py
# reads this file and says which of the three it is, with the fix for that
# one. Facts only — no token, no key, no path token ever goes in here.
PROV_FILE="$(dirname "$KEY_FILE")/provisioning.json"
STAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)"
( umask 077 && cat > "$PROV_FILE" <<JSON
{
  "bootstrap_ran_at": "$STAMP",
  "repo_dir": "$REPO_DIR",
  "branch": "$BRANCH",
  "head": "$HEAD_SHA",
  "origin_head": "$ORIGIN_SHA",
  "checkout_current": $CHECKOUT_CURRENT,
  "checkout_state": "$CHECKOUT_STATE",
  "checkout_note": "$CHECKOUT_NOTE",
  "plugin_installed": "$HAVE",
  "plugin_expected": "$WANT"
}
JSON
) && log "provisioning record written to $PROV_FILE" \
  || log "could not write the provisioning record to $PROV_FILE"

# ---- 5 · the grant that makes an unattended session able to CALL the tools --
# INSTALLING THE PLUGIN IS NOT THE SAME AS BEING ALLOWED TO USE IT, and the
# gap between those two is what has killed every scheduled firing.
#
# Measured 2026-08-21: a session created with this repo attached bound the
# connector correctly — `mcp__plugin_dma-insights_connector__get_run_progress`
# existed and was called — and then stopped dead on
#   "Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress"
# A trigger-fired container has nobody to answer that prompt, so the firing
# burns its slot, stages nothing, and records nothing. That is exactly the
# signature the 00:08 firing left: fired 00:10:43Z, zero findings, zero rows.
#
# THE SCOPE MATTERS AND THE OBVIOUS CHOICE IS THE WRONG ONE. The repo's own
# .claude/settings.json is PROJECT scope, and project permission rules are not
# applied in a non-interactive session — the workspace is untrusted, the rules
# are skipped, and the grant would have looked right in review while changing
# nothing. User scope is the scope that survives, so the grant goes here, in
# the script the environment setup field runs BEFORE the session starts.
#
# The server segment must be glob-free: `mcp__<server>__*` is honoured,
# `mcp__*` is skipped with a warning and approves nothing.
#
# Merged, never clobbered — this file already carries enabledPlugins,
# extraKnownMarketplaces and pluginConfigs written above, and losing those
# would uninstall the plugin to fix its permissions.
#
# The python below writes to a temp file rather than running inside `$( )`:
# bash mis-parses a here-document nested in a command substitution when the
# closing paren sits on its own line — it warned `unterminated here-document`
# and leaked a stray `)` into the log on the first cut of this block.
# THE CONNECTOR IS NOT THE ONLY SERVER THAT PROMPTS, and until 2026-08-24
# it was the only one granted. The routines read the world through the
# claude.ai enrichment connectors — CONNECTORS.md names Clay, Exa, Tavily,
# Vibe-Prospecting/Explorium and Indeed as the enrichment set, and the agents'
# own allow-lists add Google Drive and Quartr — and every one of those is a
# separate MCP server with a separate permission rule. A trigger-fired session
# calling an ungranted one stops on a prompt nobody can answer: measured
# 2026-08-21 as "Waiting on permission: mcp__…__search_jobs", which burns the
# firing exactly as the connector prompt did before it was granted here.
#
# THE SET IS DERIVED, NOT TYPED. Every `mcp__<Server>__` spelling that appears
# anywhere in the plugin tree is a server something in this product is
# expected to call, and reading them out means adding a connector to an
# agent's allow-list grants it on the next boot with nothing else to remember.
# The two extras below are declared because they are real and NOT derivable:
# CONNECTORS.md requires them of the TOP session, which is not an agent, so
# they appear in no allow-list to be read out of.
#
# Note the spelling gap that makes a hand-typed list wrong: the Routine record
# and the docs say "Vibe-Prospecting", "Google-Drive", "PDF-Viewer" with
# HYPHENS, while the tool names carry UNDERSCORES. A rule written the way the
# docs read matches nothing and fails silently.
GRANTS="$(
  {
    grep -rhoE "mcp__[A-Za-z0-9_-]+__" \
      "$REPO_DIR/plugins/dma-insights/agents" \
      "$REPO_DIR/plugins/dma-insights/skills" \
      "$REPO_DIR/plugins/dma-insights/docs" 2>/dev/null
    printf 'mcp__Vibe_Prospecting__\nmcp__Indeed__\n'
    printf 'mcp__plugin_dma-insights_connector__\n'
  } | sort -u | sed 's/$/*/'
)"
CLAUDE_SETTINGS="${HOME:-/root}/.claude/settings.json"
GRANT_OUT="$(mktemp)"
CLAUDE_SETTINGS="$CLAUDE_SETTINGS" DMA_GRANTS="$GRANTS" \
python3 - >"$GRANT_OUT" 2>/dev/null <<'PY' || echo "permission grant FAILED" >"$GRANT_OUT"
import json, os, pathlib

wanted = [w for w in (os.environ.get("DMA_GRANTS") or "").split() if w]
# The connector is the one rule this script must never be talked out of: it
# is what every routine needs before it can read anything at all.
if "mcp__plugin_dma-insights_connector__*" not in wanted:
    wanted.append("mcp__plugin_dma-insights_connector__*")
# `mcp__*` is skipped by the permission engine with a warning and approves
# nothing, so a glob that reached the server segment would look like a grant
# and be none. Dropped here rather than written and trusted.
wanted = [w for w in wanted if "*" not in w[: w.rindex("__") + 2]]
p = pathlib.Path(os.environ["CLAUDE_SETTINGS"])
p.parent.mkdir(parents=True, exist_ok=True)
try:
    cfg = json.loads(p.read_text())
    if not isinstance(cfg, dict):
        raise ValueError("settings.json is not an object")
except FileNotFoundError:
    cfg = {}
except Exception as e:                                       # noqa: BLE001
    # A malformed settings file silently disables EVERY setting in it, so
    # refuse rather than overwrite something a human may be mid-edit on.
    print(f"permission grant SKIPPED — {p} unreadable ({e})")
    raise SystemExit(0)

perms = cfg.setdefault("permissions", {})
allow = perms.setdefault("allow", [])
if not isinstance(allow, list):
    print("permission grant SKIPPED — permissions.allow is not a list")
    raise SystemExit(0)
added = [w for w in wanted if w not in allow]
if not added:
    print(f"all {len(wanted)} MCP grants already granted in user settings")
else:
    allow.extend(added)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, indent=2) + "\n")
    tmp.replace(p)                                           # atomic
    print(f"granted {len(added)} of {len(wanted)} MCP servers in user "
          f"settings: {', '.join(a.replace('mcp__', '').rstrip('_*') for a in added)}")
PY
log "$(cat "$GRANT_OUT")"
rm -f "$GRANT_OUT"

# ---- 6 · skill script dependencies (pandas et al., wheel-only) ----------
if [ -x "$REPO_DIR/plugins/dma-insights/scripts/dma-deps" ]; then
  "$REPO_DIR/plugins/dma-insights/scripts/dma-deps" install >/dev/null 2>&1 \
    && log "skill script dependencies installed" \
    || log "dma-deps install failed — skills needing pandas/matplotlib will degrade"
fi

# ---- 7 · prove the wire before the session starts -----------------------
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
