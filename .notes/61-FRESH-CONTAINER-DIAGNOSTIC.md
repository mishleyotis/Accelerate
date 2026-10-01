# Fresh-container plugin health report

Diagnostic sweep of a fresh workspace container for the dma-insights build.
Read-only; no configuration changed. Container has the repository attached
(branch `claude/dma-insights-onboarding-0ryrd0` at HEAD, working tree at
`/home/user/Accelerate`).

## 1. `claude plugin list 2>&1`

```
No plugins installed. Use `claude plugin install` to install a plugin.
```

**Finding:** no plugins are installed in this fresh container, despite the
repo carrying a `plugins/dma-insights` tree.

## 2. Plugin directories / marketplaces

`ls ~/.claude/plugins/ 2>&1`
```
synced
```

`ls ~/.claude/plugins/cache 2>&1`
```
ls: cannot access '/root/.claude/plugins/cache': No such file or directory
```

`cat ~/.claude/plugins/known_marketplaces.json 2>&1`
```
cat: /root/.claude/plugins/known_marketplaces.json: No such file or directory
```

**Finding:** no plugin cache and no marketplace registry exist. Only a
`synced` entry is present under `~/.claude/plugins/`.

## 3. `mcp__plugin_dma-insights_connector__*` tools

**No.** A `ToolSearch` for `plugin_dma-insights_connector` returned zero
matching deferred tools, and a broader search for `list_pending_runs dma
connector` also returned nothing matching that tool — only unrelated
connector-discovery meta-tools (`SuggestConnectors`, `ListConnectors`,
`SearchMcpRegistry`). `list_pending_runs` was therefore never called: there
is no tool to call it on. This is consistent with finding 1 — the
dma-insights plugin (and its bundled MCP connector) is not installed in
this fresh container, so its tools never register.

## 4. Toolchain / GCP presence

`which gcloud gsutil python3 node git curl 2>&1`
```
/usr/local/bin/python3
/opt/node22/bin/node
/usr/bin/git
/usr/bin/curl
```
(`gcloud` and `gsutil` printed nothing — not found on `PATH`.)

`ls /opt/google-cloud-sdk 2>&1`
```
ls: cannot access '/opt/google-cloud-sdk': No such file or directory
```

`ls ~/.config/gcloud 2>&1`
```
ls: cannot access '/root/.config/gcloud': No such file or directory
```

`env | grep -oE '^(GOOGLE|GCP|CLOUDSDK)[A-Z_]*'` (names only)
```
CLOUDSDK_PROXY_TYPE
CLOUDSDK_AUTH_ACCESS_TOKEN
CLOUDSDK_PROXY_PORT
CLOUDSDK_CORE_CUSTOM_CA_CERTS_FILE
CLOUDSDK_PROXY_ADDRESS
```

**Finding:** `python3`, `node`, `git`, `curl` are present. `gcloud`/`gsutil`
are absent — no SDK install directory, no `gcloud` config directory. Five
`CLOUDSDK_*` env vars are pre-set (proxy type/port/address, custom CA certs
file, and an auth access token variable name) even though the `gcloud`
binary itself is not installed.

## 5. Repo state

```
$ pwd
/home/user/Accelerate

$ git remote -v
origin	https://github.com/mishleyotis/Accelerate (fetch)
origin	https://github.com/mishleyotis/Accelerate (push)

$ git branch --show-current
claude/dma-insights-onboarding-0ryrd0

$ git log --oneline -1
3ec8b2d All three session routines exist now, and the doc says so

$ ls plugins
dma-insights
```

**Finding:** repo is attached and current; `plugins/dma-insights` exists on
disk but (per findings 1–3) is not installed/registered with the `claude`
CLI in this container.

## 6. `python3 plugins/dma-insights/scripts/doctor.py --no-probe 2>&1`

```
DMA Insights — install doctor

  [ok] plugin manifest                            /home/user/Accelerate/plugins/dma-insights/.claude-plugin/plugin.json
  [ok] plugin enabled state                       defaultEnabled=false — the plugin ships disabled and must be enabled per install (informational row, never fails)
  [ok] connector definition                       /home/user/Accelerate/plugins/dma-insights/.mcp.json
  [ok] hooks wired                                5 handler run(s): every entry parses, exists, has a numeric timeout and exits 0 on a benign event
  [ok] skills inventory                           6 of exactly 6: dma-assessment, dma-first-call-deck, dma-governance, dma-rectifier, dma-research, dma-surface-production
  [ok] agents inventory                           16 of exactly 16: adversarial-verifier, context-surface-producer, deployed-app-auditor, finding-challenger, heatmap-surface-producer, insights-surface-producer, learning-grader, learning-testgen, overview-surface-producer, package-vetter, page-consolidator, platform-surface-producer, qa-overseer, rectifier, surface-producer, techstack-surface-producer
  [FAIL] skill script dependencies                  declared: 13  present: 1  missing: 12
         -> run: dma-deps install (or dma-deps install --venv)
  [FAIL] gcloud found                               not on PATH or in the usual install locations
         -> install the Google Cloud SDK, or set GCLOUD_BIN
  [FAIL] active google account                      none active
         -> gcloud auth login, or activate a service account
  [ok] token audience                             https://dmai-mcp-dukrne5v4a-uc.a.run.app (--no-probe: nothing to compare it against)
  [FAIL] identity token mints                       skipped: no gcloud or no active account
  [ok] connector rejects an unauthenticated call  not probed (--no-probe)
  [ok] live tool roster reconciles                SKIPPED: not probed (--no-probe)
  [ok] connector path token                       not in this environment — expected: the plugin stores it in the OS keychain as user_config.mcp_path_token, not as an env var

10/14 checks passed.
```

Exit code: 1 (doctor.py fails non-zero when any check fails).

**Finding:** manifest/hooks/skills/agents/connector-definition are all
structurally sound in the repo. The 4 failures are all environment-state,
not repo-content, problems: script dependencies aren't installed
(1 of 13 present), `gcloud` isn't on the machine, no Google account is
active, and identity-token minting is skipped as a consequence of the
missing `gcloud`/account.

## 7. Proxy / session-env

`ls /root/.ccr 2>&1`
```
README.md
agent-proxy-ca.crt
ca-bundle.crt
java-truststore.p12
```

`ls /root/.claude/session-env 2>&1`
```
ea6959ec-8495-5f77-b718-432089b29664
```

`head -30 /root/.ccr/README.md 2>&1`
```
# Claude Code agent proxy

Outbound HTTPS from this session goes through a local proxy at http://127.0.0.1:38389
(set via HTTPS_PROXY) which tunnels to a policy-enforcing egress proxy. TLS is
re-terminated there, so every tool must trust the CA bundle at
/root/.ccr/ca-bundle.crt. The standard CA environment variables, the system trust
store (where possible), a JVM truststore, the Bazel system bazelrc, the
browser NSS store, and gsutil's boto config are already set up.

## Quick diagnosis

1. Run: curl -sS http://127.0.0.1:38389/__agentproxy/status
   It reports proxy state, which trust and git accommodations are active
   (javaTrustStorePath, toolTrustFailureCodes, gitSshRewrite,
   gitConfigConflicts), and the most recent proxy-side failures.
2. Find the failure class below and apply the matching fix; gitConfigConflicts
   codes map to the git section, toolTrustFailureCodes to the JVM section.
3. Never disable TLS verification, never unset HTTPS_PROXY, and do not retry
   organization policy denials (403/407) — report them instead.

## Failure classes and fixes

### "certificate verify failed" / "self-signed certificate in chain" / PKIX errors

The failing tool is not reading the pre-set CA configuration. In order:

- If the tool has a CA flag or env var, point it at /root/.ccr/ca-bundle.crt
  (examples: --cacert, SSL_CERT_FILE, NODE_EXTRA_CA_CERTS, REQUESTS_CA_BUNDLE,
  AWS_CA_BUNDLE, DENO_CERT, CARGO_HTTP_CAINFO, PIP_CERT, GIT_SSL_CAINFO,
  BUNDLE_SSL_CA_CERT, HEX_CACERTS_PATH, NIX_SSL_CERT_FILE).
```
(truncated at 30 lines per instruction)

**Finding:** the agent-proxy CA material and session-env marker
(`ea6959ec-8495-5f77-b718-432089b29664`) are present as expected; no
gcloud-specific bootstrap is provided by `/root/.ccr`.

## Summary

A fresh container that has the repo attached still starts with:
- No plugins installed (`claude plugin list` empty; no cache, no
  marketplace registry) — the on-disk `plugins/dma-insights` tree is not
  registered with the CLI.
- No `mcp__plugin_dma-insights_connector__*` tools available — confirmed by
  tool search, not by a failed call (there was nothing to call).
- No `gcloud`/`gsutil` on `PATH`, no SDK directory, no active account —
  `CLOUDSDK_*` env var *names* are pre-set, but the binary itself is
  absent.
- Base toolchain (`python3`, `node`, `git`, `curl`) is present.
- `doctor.py --no-probe` confirms repo-side plugin structure is intact
  (10/14 checks) and the 4 failures are exactly: missing skill-script
  dependencies, missing `gcloud`, no active Google account, and identity
  token minting skipped as a downstream consequence.
- The outbound agent-proxy (`/root/.ccr`) is configured as documented; it
  does not itself provide `gcloud`.

None of the above was remediated — this container was read-only for the
`dma-insights` plugin content by design; only this report file was
written.
