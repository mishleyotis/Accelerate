# dma-insights

> The MCP connector's display name is **DMA Insights** — its own
> initialize response says so, and it is the name to install it under in
> claude.ai's custom-connector dialog (docs/CONNECTORS.md § DMA Insights
> in claude.ai; access contract in docs/DECISIONS.md D8).

The six Digital Maturity Assessment skills, the 47 DMA agents, two operator
commands, the session/submit/verdict hooks and the remote DMA Insights MCP
connector, as one installable plugin.

**The research engine lives in `skills/dma-research/engine/`, and the
workbook is its substrate.** Every research step appends to the scoring
workbook as it happens; the gate, the handoff, both reports, the app's
ingest and the governance audit all read that same object. Before it, no
research step could touch a sheet and the workbook was written once at the
end from a parallel JSON plane — which made the resume, the live chain
integrity and the mid-run audit structurally impossible.

`docs/END-TO-END.md` is the run: every command, what refuses and why, and
what each stage hands the next. `scripts/aud_ledger.py` is the record of
what the headless-readiness audit found and what became of it — including
what is still open.

```
skills/    dma-research (+ engine/: the workbook substrate, the gate,
                         the validator, the two report renderers)
           dma-assessment · dma-governance
           dma-surface-production · dma-first-call-deck · dma-rectifier
agents/    surface-producer (conductor; the only one that submits/promotes)
           overview-surface-producer · heatmap-surface-producer
           platform-surface-producer · context-surface-producer
           finding-challenger · page-consolidator · qa-overseer
           deployed-app-auditor · package-vetter · adversarial-verifier
           rectifier
hooks/     precheck_submit (refuses a doomed submit before the network)
           verdict_watch (nudges the memory when a gate refuses twice)
           session_brief (the routing and memory rules — at session start
                          on all five sources, AND to every subagent via
                          SubagentStart, which is the channel the live
                          Routine actually dispatches producers through)
           deny_bulk_read (the never-cat rule, enforced rather than written)
commands/  /dma-insights:doctor          is this install able to do the work?
           /dma-insights:setup-routines  reconcile the scheduled routines
scripts/   dma-deps · mcp_auth_headers.sh · doctor.py · setup_routines.py
           audit_skills.py (broken-reference ceiling: 0)
           check_taxonomy_drift.py (counts come from the catalogue)
           gen_gates_md.py (the gate census, generated from the registry)
           hooks/ · tests/
           (no bin/: claude.ai-hosted plugins may not ship PATH-added
            executables — invoke dma-deps by path)
routines.json  the scheduled routines this product requires, declared
.mcp.json      the deployed connector, declared remote
```

## The agent hierarchy, and why it is faster

One monolithic producer re-produced six pages to fix one card. Work now
routes to the smallest true unit — the pipeline and the full routing table
live in `skills/dma-surface-production/05-lifecycle/routing.md`:

```
route → produce → challenge → consolidate → submit → learn
        (surface    (finding-    (page-        (surface-  (qa-
         producers,   challenger,  consolidator)  producer   overseer,
         fast tier)   dma-research  refuses        only)      writes the
                      discipline)   unchallenged              findings
                                    input)                    memory)
```

The four surface producers cover the six pages (overview, heatmap, platform,
and one agent for context + techstack + insights) and run on the fast model
tier; the challenger, consolidator and overseer reason on the strong tier,
because checking is where depth pays. Submission and promotion never leave
`surface-producer` — the plugin-level expression of the invariant that
content enters through the connector in one place.

## The two credentials, which are not the same thing

Most install failures are one of these missing, and they fail identically —
the connector's tools are simply absent, and absent carries no reason.

| | what it proves | where it lives | if it is wrong |
|---|---|---|---|
| **path token** | *which* connector you meant | fetched per connection by `scripts/mcp_auth_headers.sh` (env, cache file, Secret Manager) and sent as `X-DMA-Path-Token` | 404 — the static /mcp path answers nothing without it |
| **Google ID token** | *who you are* | minted per connection by `scripts/mcp_auth_headers.sh` from your active `gcloud` account | 403 — Cloud Run rejects the call before the connector sees it |

The ID token is minted for an **audience**, and Cloud Run checks it. The
audience defaults to the production service; override it with `DMA_MCP_HOST`
if you point `mcp_base_url` at a different deployment. Cloud Run gives one
service two URL forms (`<svc>-<hash>-<region>.a.run.app` and
`<svc>-<projnum>.<region>.run.app`) and **either audience is accepted at
either URL** — measured, all four combinations return 200 — so only a
genuinely different service is a problem.

Run `/dma-insights:doctor` and it will tell you which of the two is missing
rather than leaving you to infer it from an empty tool list.

### The third question, which is not about your credentials

A token that is minted and sent is not the same as a token that is *checked*.
Until **2026-08-16** `dmai-mcp` granted `roles/run.invoker` to `allUsers` with
ingress `all`: the plugin minted an identity token on every connection, sent
it, and nothing on the other side ever read it. Authentication rested entirely
on the 32-character path token in the URL — on the one component in this system
permitted to write serving content. `dmai-api` and `dmai-web` were locked down
correctly; the connector was the outlier.

Every check the doctor made passed throughout, because each measured that a
credential **existed** and none measured that anything **enforced** it. The
doctor now probes enforcement directly, and needs no secret to do it: an
unauthenticated POST to a deliberately bogus path token.

| answer | means |
|---|---|
| **403** / 401 | IAM rejected it before routing — enforced |
| **404** | it reached the application: the service is **public** |

The grant is now `domain:zennify.com` plus the deployer service account. If you
stand up another deployment, run the doctor against it before trusting it.

## Install

**By upload (Claude Desktop · Cowork · claude.ai)** — one archive carries all
six skills, all fourteen agents, both commands and the connector declaration, so
nothing is installed piecemeal. Package it so that `.claude-plugin/plugin.json`
sits at the **root of the zip** (do not wrap the contents in a folder):

```bash
cd plugins/dma-insights
zip -r ../../dma-insights-$(python3 -c "import json;print(json.load(open('.claude-plugin/plugin.json'))['version'])").zip . \
  -x '*__pycache__*' '*.pyc' '.DS_Store'
```

Upload it under **Customize → Plugins → Upload plugin** (the uploader accepts
`.zip` only; a `.plugin` extension is rejected). On enable you are prompted for
the three configuration values below — the base URL is prefilled with
production, the path token is stored in the OS keychain. The connector still
needs a Google identity: on a machine without an authenticated `gcloud` the
skills, agents and commands all load, and connector calls fail closed with a
403 until one exists.

**From GitHub**, which is what to use on a machine that does not have the repo:

```bash
claude plugin marketplace add mishleyotis/Accelerate
claude plugin install dma-insights@zennify-dma \
  --config mcp_base_url="$(gcloud run services describe dmai-mcp \
      --project=digital-maturity-assessor --region=us-central1 \
      --format='value(status.url)')" \
  --config repo_root="$PWD"
claude plugin enable dma-insights@zennify-dma
```

**From a local checkout**, replace the first line with
`claude plugin marketplace add ./` run at the repository root.

Then, in a session, prove it rather than assuming it:

```
/dma-insights:doctor            # plugin, gcloud identity, audience, path token
/dma-insights:setup-routines    # the four scheduled routines, reconciled
```

The plugin ships disabled (`defaultEnabled: false`): nothing loads until it is
enabled after install. `/dma-insights:doctor` reports the enabled state.

## Requirements on the machine

* **`gcloud`**, authenticated, with an account that may mint an identity token
  for the connector's audience and holds `roles/run.invoker` on `dmai-mcp`.
  The auth helper looks on `PATH` and in the usual install locations, and
  honours `GCLOUD_BIN`.
* **Read access to the path-token secret** (`dmai-mcp-path-token`), once, at
  install. It is stored in your OS keychain afterwards, never in
  `settings.json` and never in the repository.

## The scheduled routines

`routines.json` declares them; `/dma-insights:setup-routines` reconciles a
project against it and reports `ok` / `MISSING` / `PAUSED` / `DRIFTED` /
`DUPLICATE` per routine.

| routine | schedule | why it matters |
|---|---|---|
| `dmai-package-scan` | every 30 min | **how runs come to exist.** Without it nothing new is ingested and the app serves a frozen corpus |
| `dmai-corpus-gate-scanner` | nightly 03:00 | catches a corpus-wide regression no single ingest would show |
| `dmai-pack-exporter` | nightly 02:00 | pack export |
| `dmai-enrich-loop` | hourly at :07 | computes each run's enrichment gaps |

Reconciliation is **dry-run by default**. It creates, resumes and corrects only
with `--apply`, and deletes a duplicate only with `--delete-duplicates` on top
of that. A duplicate is defined narrowly — another scheduler job aimed at the
*same Cloud Run target* under a different name — because this project hosts
around two dozen jobs belonging to other systems and a looser rule would reach
them.


## The three configuration values

| Key | Sensitive | What it is |
|---|---|---|
| `mcp_base_url` | no | Cloud Run URL of `dmai-mcp`. Default is the current production URL; override for staging. |
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

Twenty-two bundled scripts import `pandas` or `python-pptx`. They are declared
in `requirements.txt`, not fixed in place:

```bash
scripts/dma-deps check      # what is missing and which scripts each gap blocks
scripts/dma-deps install    # into the current interpreter
scripts/dma-deps install --venv   # into ${CLAUDE_PLUGIN_DATA}/venv instead
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

Twelve in all: five producers (`surface-producer` plus the four per-page
producers), three pipeline QA (`finding-challenger`, `page-consolidator`,
`qa-overseer`), four standing QA/maintenance (below). The table lists the
five invoked directly; the seven others are routed by `surface-producer`
per the hierarchy above.

| Agent | Invoke when | May submit or promote |
|---|---|---|
| `surface-producer` | a package must become rendered surfaces, or a verdict needs repairing | **yes — only this one** |
| `package-vetter` | a client folder arrives, before anything is parsed | no |
| `adversarial-verifier` | six pages already pass and the run is about to be believed | no |
| `deployed-app-auditor` | after a deploy or a promotion; a surface is reported wrong in production | no |
| `rectifier` | findings accumulate, a defect looks familiar, or a skill/agent file is about to be edited | no |

The four read-only agents have `submit_page_payload`, `promote_run`,
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
