# dma-insights

The five Digital Maturity Assessment skills, four DMA agents, and the remote
DMA Insights MCP connector, as one installable plugin.

```
skills/   dma-research · dma-assessment · dma-governance
          dma-surface-production · dma-first-call-deck
agents/   surface-producer · deployed-app-auditor
          package-vetter · adversarial-verifier
bin/      dma-deps            on PATH while the plugin is enabled
scripts/  mcp_auth_headers.sh · audit_skills.py
.mcp.json the deployed connector, declared remote
```

## Install

```bash
claude plugin marketplace add ./            # from the repository root
claude plugin install dma-insights@zennify-dma \
  --config mcp_base_url="$(gcloud run services describe dmai-mcp \
      --project=digital-maturity-assessor --region=us-central1 \
      --format='value(status.url)')" \
  --config mcp_path_token="$(gcloud secrets versions access latest \
      --secret=dmai-mcp-path-token --project=digital-maturity-assessor)" \
  --config repo_root="$PWD"
claude plugin enable dma-insights@zennify-dma
```

The plugin ships `defaultEnabled: false`. It connects to a production service
and the four agents can promote client-facing content, so it is opted into
rather than turned on by installing.

Read the token out of Secret Manager into the command, as above. Do not paste
it, do not put it in a file, and do not echo it — `claude mcp list` prints
the resolved server URL in full, and the token is a path segment of that URL.

## The three configuration values

| Key | Sensitive | What it is |
|---|---|---|
| `mcp_base_url` | no | Cloud Run URL of `dmai-mcp`. Default is the current production URL; override for staging. |
| `mcp_path_token` | **yes** | The capability path segment the connector is mounted under. Stored in the OS keychain, never in `settings.json` and never in this repository. |
| `repo_root` | no | Optional checkout of this repository. Only `precheck_gates.py` uses it. |

## Why the connector is remote

`apps/mcp` is a Cloud Run service speaking streamable HTTP, mounted under a
secret path token. It holds a bundled embedding model and a Cloud SQL
connection; it is not a stdio binary and bundling one would be a second,
divergent implementation of the only component allowed to write serving
content.

It needs two credentials and they answer different questions:

- **the path token** — *which* connector you meant. It is a path segment, so
  it lives in the URL, substituted from the keychain at connect time.
- **a Google-signed ID token** — *who* you are. Cloud Run enforces
  `roles/run.invoker` on the audience before the request reaches the MCP
  server, so a call without it is a 403 whatever the path token says.
  `scripts/mcp_auth_headers.sh` mints one per connection via `headersHelper`.

Neither is committed. The audience must equal the URL the request goes to, so
if you override `mcp_base_url`, set `DMA_MCP_HOST` to the same value.

## Dependencies

Seventeen bundled scripts import `pandas` or `python-pptx`. They are declared
in `requirements.txt`, not fixed in place:

```bash
dma-deps check      # what is missing and which scripts each gap blocks
dma-deps install    # into the current interpreter
dma-deps install --venv   # into ${CLAUDE_PLUGIN_DATA}/venv instead
```

Everything else runs on the standard library plus `openpyxl`.

## Checking the package

```bash
python3 scripts/audit_skills.py
```

Runs `--help` on every bundled script and resolves every path reference in
the skill trees, separating references *into* the skill tree (a dead one is a
defect) from paths in the client package or run working tree (`DMA_ROOT/…`,
`working/deck.pptx`, `templates/<sv>.pptx` — these are inputs and outputs and
cannot resolve at rest).

## Agents

| Agent | Invoke when | May submit or promote |
|---|---|---|
| `surface-producer` | a package must become rendered surfaces, or a verdict needs repairing | **yes — only this one** |
| `package-vetter` | a client folder arrives, before anything is parsed | no |
| `adversarial-verifier` | six pages already pass and the run is about to be believed | no |
| `deployed-app-auditor` | after a deploy or a promotion; a surface is reported wrong in production | no |

The three read-only agents have `submit_page_payload`, `promote_run`,
`register_evidence` and `claim_run` denied by name. That is the plugin-level
expression of the invariant that content enters through the connector and
nowhere else.

`deployed-app-auditor` is the only one that looks at what a client can
actually load. Every other check in this system inspects a payload on the way
in — and between a passing payload and a rendered page sit a redaction
walker, a generated column, a materialised view, a cache key and a frontend
resolver, none of which the payload ever saw. It reports `UNVERIFIABLE` when
it cannot fetch, and is instructed never to collapse that into `PASS`.

## Skill sourcing

These skills previously existed as real directories in `~/.claude/skills`,
with `dma-surface-production` duplicated into `.claude/skills` as a second
byte-identical original. `plugins/dma-insights/skills/` is now the single
source: it is the copy under version control, the copy a PR can review, and
the copy that ships to another machine. After installing, remove the
duplicates so a session does not load two of each:

```bash
rm -rf ~/.claude/skills/dma-{research,assessment,governance,surface-production,first-call-deck}
```
