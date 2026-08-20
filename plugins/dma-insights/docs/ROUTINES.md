# ROUTINES — the complete inventory of scheduled work

Two kinds of routine keep this product alive, and they live in two different
schedulers with two different reconciliation stories. This file lists **all of
them** — so "scheduled where it should be" is a checkable claim rather than a
recollection.

1. **App-side Cloud Scheduler routines** — cron triggers in GCP project
   `digital-maturity-assessor` (us-central1) that fire Cloud Run Jobs. No
   model is involved; they are the app doing its own bookkeeping. Declared in
   `plugins/dma-insights/routines.json`, reconciled by
   `plugins/dma-insights/scripts/setup_routines.py`.
2. **Claude-session routines** — CCR triggers that start a **fresh Claude
   session per firing** with a standalone prompt. These are the reasoning
   work: synthesis, rectification, drift review. They have no reconciler
   today; this file is their declaration.

The split is the build charter's invariant 1 applied to scheduling: the app
performs no inference, so anything that reasons runs as a Claude session, and
anything the app can do deterministically runs as a Job. A routine in the
wrong column is a design error, not a tuning choice.

---

## 1 · App-side Cloud Scheduler routines (4)

Provisioned by `infra/deploy.sh` (sections 3 and 4: worker Job + Scheduler
sync, then the corpus Jobs and the charter's other two triggers), declared in
`plugins/dma-insights/routines.json`, reconciled by
`plugins/dma-insights/scripts/setup_routines.py`. Three are **mandatory per
the build charter**; the enrich loop was added 2026-08-15 and kept in the
manifest so it is reconciled rather than remembered.

Reconciler report, run 2026-08-19 (`python3
plugins/dma-insights/scripts/setup_routines.py`, dry-run default):

```
28 scheduler job(s) in digital-maturity-assessor/us-central1; 4 declared

  ok      * dmai-package-scan                enabled, on schedule
  ok      * dmai-corpus-gate-scanner         enabled, on schedule
  ok      * dmai-pack-exporter               enabled, on schedule
  ok        dmai-enrich-loop                 enabled, on schedule

  * mandatory per the build charter

every declared routine is present, enabled and on schedule.
```

### dmai-package-scan — `*/30 * * * *` (mandatory)

| | |
|---|---|
| **Target** | Cloud Run Job `dmai-worker` (invoked as `dmai-worker@`) |
| **What it does** | The package scan — how runs come to exist (TRD §07, ten steps verbatim). Walks the intake tree, ingests completed assessment packages, creates runs. Idempotent: an unchanged tree creates nothing. |
| **Failure surface** | Nothing new is ever ingested and the app serves a frozen corpus — which from inside the app looks like *nothing at all*. Symptoms: `list_pending_runs` stops growing; Cloud Run Job executions for `dmai-worker` absent or failing. |
| **Reconciled by** | `setup_routines.py` — states `ok / MISSING / PAUSED / DRIFTED / DUPLICATE`; a missing mandatory routine is exit code 1. |

### dmai-pack-exporter — `0 2 * * *` (mandatory)

| | |
|---|---|
| **Target** | Cloud Run Job `dmai-pack-exporter` (runs as `dmai-api@` — it reads `serving_directory`, which is svc_api's grant; measured 42501 as `dmai-mcp`. Scheduler invokes it as `dmai-mcp@`.) |
| **What it does** | Nightly pack export (and on demand). Writes the corpus pack the gate scanner measures. |
| **Failure surface** | A stale pack — the 03:00 scanner then grades yesterday's corpus and reports it as today's. Symptoms: pack timestamps in GCS stop advancing; the Job's execution log. |
| **Reconciled by** | `setup_routines.py`, same states. The 02:00→03:00 ordering **is** the dependency (`infra/deploy.sh`, section 4) — a drift that reorders them silently breaks the scanner's claim to be measuring today. |

### dmai-corpus-gate-scanner — `0 3 * * *` (mandatory)

| | |
|---|---|
| **Target** | Cloud Run Job `dmai-corpus-gate-scanner` (runs as `dmai-mcp@`, `--fail-on-regression`; ceilings from the one ratcheted file, `packages/shared/corpus_gates.json`) |
| **What it does** | Nightly corpus gate sweep, also run on every CI run. Reads the exported pack, writes `gate_results`. Catches a corpus-wide regression no single package's ingest would show. |
| **Failure surface** | A regression ships unnoticed until a client page shows it. `--fail-on-regression` makes the Job execution itself fail, so the signal is a red execution in Cloud Run, not a quiet log line. |
| **Reconciled by** | `setup_routines.py`, same states. |

### dmai-enrich-loop — `7 * * * *` (declared, not charter-mandatory)

| | |
|---|---|
| **Target** | Cloud Run Job `dmai-enrich` (worker image, entrypoint `python -m dma_worker.enrichment`, as `dmai-worker@`). Registered on the older `namespaces/.../jobs/x:run` URI form — `setup_routines.py` canonicalises both API shapes to `<job>:run` so the duplicate check still sees them as one target. |
| **What it does** | Hourly: computes each active run's enrichment gaps and records every attempt (`RESOLVED / NOT_RUN / NO_SOURCE / FAILED`) in `enrichment_jobs`. **Since the 2026-08 sweep it also raises six-month cadence refresh requests**: `sweep_refresh_due` in `apps/worker/dma_worker/enrichment.py` inserts a `refresh_requests` row (`origin='cadence'`) for every promoted entity past `assessment_date + 6 months` with nothing already open — idempotent by the schema's one-open-row-per-entity constraint, and committed separately from the gap loop so a resolver failure never costs the due-date safeguard. Minute 7 so it does not contend with the half-hour scan. |
| **Failure surface** | Two, and both are readable as data rather than logs: `GET /v1/ops/enrichment-loop` (`apps/api/dma_api/main.py`) computes `healthy` strictly — a job that never closed, errored, **or scanned zero runs** is UNHEALTHY; and a due client sitting silent past its refresh date, visible as an empty `due` list in `GET /v1/ops/refresh-queue` that should not be empty. |
| **Reconciled by** | `setup_routines.py`, same states. |

**How reconciliation works.** `setup_routines.py` surveys every scheduler job
in the project, compares the four declared routines by name, state and
schedule, and flags any *other* job aimed at the same Cloud Run target as a
duplicate. Dry run by default; `--apply` creates (needs `--service-account`),
resumes and corrects; `--delete-duplicates` deletes only what the narrow rule
matched — identical target URI, non-canonical name — because the project
hosts ~24 scheduler jobs belonging to other systems and any broader rule
would reach them. The `/dma-insights:setup-routines` command
(`plugins/dma-insights/commands/setup-routines.md`) wraps this report-first:
change nothing without being asked.

---

## 2 · Claude-session routines (CCR triggers, fresh session per firing)

Each is a CCR trigger with `create_new_session_on_fire = true`: every firing
starts from nothing, loads the installed plugin, and must re-prove its
tooling before it acts. A bound session that remembers its own last run
in-context is precisely what these designs refuse — the connector's stores
(runs, findings, refinements) are the memory, and a fresh session proves it
can read them.

**The provisioning contract (measured 2026-08-19).** A fresh container in
this environment ships with python3/node/git/curl and nothing else this
product needs: no gcloud, no Google identity, no plugin, no repo, and its
disk does not survive container reclaim — even a persistent session loses
its toolchain between firings. Plugins register their MCP tools at session
START, so provisioning cannot be a step inside the routine. It is the
**environment setup script** (claude.ai/code → environment settings for
`Default - full network access`), which must be wired once, by hand, as:

```
curl -sfL https://raw.githubusercontent.com/mishleyotis/Accelerate/claude/dma-insights-onboarding-0ryrd0/plugins/dma-insights/scripts/bootstrap_session.sh | bash
```

**The environment variable is the load-bearing half, and it is enough on
its own.** `DMA_ROUTINE_SA_KEY_B64` — the `dmai-routine@` service-account
key JSON, base64-encoded to one line because the settings field is .env
format (retrieval and rotation: `plugins/dma-insights/docs/secrets.md`
§1b). `gcp_token.py` reads it directly, so `mcp_auth_headers.sh`
authenticates the connector at session start and the routine has live tools
from its first turn, whether or not the setup script ever ran.

That ordering is the whole reason the variable matters more than the
script. A plugin's MCP servers register at session START: on 2026-08-20 a
firing bootstrapped its key mid-session, reached 14/14 on the doctor over
direct HTTP, and still had none of the connector's 33 tools, because
registration had already happened and Claude Code has no MCP hot-reload.
Anything a session needs in order to authenticate must already be present
when it starts.

The setup script remains worth wiring as the belt to that braces: it clones
the repo, installs the plugin from the repo marketplace, lands the key at
`/root/.dma/sa.json`, fetches the connector path token fresh from Secret
Manager (so a token rotation needs no client update anywhere), installs the
skill script dependencies, and probes the connector roster — logging loudly
and never blocking session start, because every routine's STEP 0 is the
enforcement point. It refuses to register a marketplace from a directory
holding no manifest, having once rewritten a working install to a dead
source when a caller pointed it at a path that did not exist. It also
disables shell tracing for itself: run as `bash -x` on 2026-08-20 it
printed a service-account key and a signed token into a transcript, and
both credentials had to be rotated.

Status at 2026-08-19 (`list_triggers`, evening): **all three exist and are
enabled.** (b) and (c) were created 2026-08-19T21:24Z from this file's fenced
prompts; a firing that finds this paragraph disagreeing with `list_triggers`
has found the drift section 3's manual reconciliation exists to catch.

### 2a · dma-synthesis-sequence — every 12 hours · EXISTS

**Connectors — UI-attach required (measured 2026-08-20).** A trigger created
through the API carries NO claude.ai connectors, and this organisation has
the API's `connectors` parameter disabled — so connectors reach a routine's
fired sessions ONLY when a human attaches them in the claude.ai routines UI
(as was done for 2b and 2c). Until that edit is made on this trigger, fired
sessions run with the plugin's own connector (the 33 dma-insights tools,
which load regardless) plus web search; Google Drive, Clay and the rest are
absent, so the client-memory round-trip stays local-and-flagged and Clay
facets record as not-run. The DMA package itself is unaffected either way:
packages enter through the app's package scan (worker Job, server-side) and
sessions read the parsed package through the connector — invariant 2; a
session never parses a workbook from Drive.


| | |
|---|---|
| **Trigger** | `trig_01WTf9nQdFPQb6jiSVVyf37u`, cron `8 */12 * * *` (00:08 and 12:08 UTC; the minute is the creation anchor), enabled, push notifications on, created 2026-08-19 |
| **Cadence, and why** | One client per firing, end to end — vetting, six pages, verdicts, repairs, gold-standard audit, learning-loop close — is a multi-hour session. Twice daily walks the D7 learning sequence at a pace the weekly rectification can absorb (roughly two clients of sightings per day feeding one Monday review), and a failed firing costs at most half a day of queue progress. |
| **May** | Pick the first learner not yet serving six pages (D7 order, `docs/DECISIONS.md`); produce, submit, promote — but only **through the installed plugin**: `/dma-insights:dma-surface-production`, its routing table, its agents. Repair via the routed single-surface path. Write the findings memory (STEP 4 is mandatory, green or not). |
| **May not** | Produce more than one client per firing; touch BOK Financial or its twin (the held-out); edit `apps/` code; force a promote past a failed vetting or an unresolved PENDING_REVIEW identity; fabricate technographics when an enrichment grant is refused (record the attempt honestly — MEM-0082 is the permanent lesson); improvise ad-hoc multi-agent workflows around the plugin, because the plugin **is** the system under test. |
| **Report shape** | Under 25 lines: client + run id; first-pass verdict counts by gate (the learning-curve datum); repairs made and how routed; final six-page state; gold-standard deltas vs Baxter; enrichment honesty (what ran, what was refused); finding ids written; explicit confirmation that no PERMANENT class recurred. |

The live prompt, read back from the trigger after the 2026-08-20 congruency update — kept here verbatim
so a drifted trigger is detectable by diff:

```
You are the scheduled DMA synthesis routine (dma-insights). One client per firing, end to end, through the installed plugin only — its skills, agents, hooks and routing are the system under test, so do not improvise around them and do not use ad-hoc multi-agent workflows.

STEP -1 — SELF-PROVISION IF THE PLUGIN IS MISSING. Trigger-fired containers start with no repository and no plugin. If `claude plugin list` shows no dma-insights: (a) attach the repository — call the claude-code-remote add_repo tool (owner mishleyotis, repo accelerate, access read), clone it to /home/user/Accelerate at branch claude/dma-insights-onboarding-0ryrd0 as the tool instructs, then call register_repo_root — the repo's .claude/settings.json declares the plugin from its own marketplace, so it loads on your NEXT turn; (b) run `bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh` — it lands the service-account identity from the DMA_ROUTINE_SA_KEY_B64 environment variable (base64 of the key JSON on one line; raw DMA_ROUTINE_SA_KEY also accepted), fetches the connector path token fresh from Secret Manager, and installs the plugin with its config; (c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent or empty after (b), the connector cannot authenticate — STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must be added in the claude.ai/code environment settings, one line, the base64 of Secret Manager secret dmai-routine-sa-key.

STEP 0 — VERIFY THE TOOLING. This container was provisioned before the session started by the environment setup script (plugins/dma-insights/scripts/bootstrap_session.sh, wired in the claude.ai/code environment settings together with the DMA_ROUTINE_SA_KEY_B64 variable): repo checkout, plugin install, service-account identity, connector path token. Run `claude plugin list` and the dma-insights doctor command (/dma-insights:doctor). Require: plugin dma-insights version >= 0.6.2 (the 47-agent roster plus Drive access by service account), doctor fully green including the live tool-roster check. THEN the access preflight, in this order: (a) `python3 plugins/dma-insights/scripts/drive_fetch.py check` — REQUIRED: the intake folder must answer the routine service account; if it fails, STOP and report its exact message — a synthesis that cannot reach the DMA drive folder does not start; (b) enrichment connectors — REQUIRED (owner, 2026-08-20: the routine never runs in degrade mode). Check which claude.ai connector tools this session carries (Clay, Exa, Tavily, Vibe-Prospecting/Explorium, Indeed; they appear as mcp__<Name>__ tools when attached to this Routine in the claude.ai routines UI — docs/CONNECTORS.md). If Exa, Tavily AND at least one of Clay/Vibe-Prospecting are present, proceed at full depth and record any absent extras per facet. If that minimum is not met, STOP without producing anything and report exactly which connectors the session carries versus the Routine record — the fix is attaching them on the dma-synthesis-sequence Routine's own edit screen in the claude.ai routines UI (the connector browse list's Use buttons enable a connector for the org, NOT for a Routine — measured 2026-08-20). If the plugin is missing, stale, or the doctor fails, STOP and report exactly what is missing, naming bootstrap_session.sh and DMA_ROUTINE_SA_KEY_B64 so the fix is actionable — producing anything with degraded tooling is worse than producing nothing.

STEP 1 — PICK ONE CLIENT. list_pending_runs via the connector; respect is_latest_for_request=true rows only. The learning sequence (docs/DECISIONS.md D7 in the plugin): 1) t-rowe-price-group-inc, 2) houlihan-lokey-inc, 3) hughes-federal-credit-union, 4) sl-green-realty-corp-nyse-slg (adjudicate its twin 'slg' by the worker's dedup rules first), 5) corporate-america-credit-union. Take the FIRST not yet serving six pages. HELD OUT — never produce from this routine: bok-financial-corporation and its twin bok-financial. If all five learners serve, take stress candidates in order: brick-city-capital, thrivent, bank-of-utah. If those too are done, report "sequence complete" and stop.

STEP 1b — PULL THE PACKAGE AND OPEN THE CLIENT'S MEMORY. `python3 plugins/dma-insights/scripts/drive_fetch.py pull --client <client-slug>` downloads the client's folder from the intake tree to /root/.dma/packages/<slug>/ — the RAW package, beside the parsed one the connector serves; consult it where the parsed bundle raises a question, and remember the parsed bundle through the connector remains the scoring source of truth (scores are synthesized from the package FIRST, then validated against public data and enrichment — never invented from either). Memory (05-lifecycle/client-memory.md is the contract): if `<slug> — synthesis memory.md` exists in the client's folder it arrived with the pull — copy it to /root/.dma/clients/<slug>.md and READ the open questions section plus the sections for the pages in scope; a search the research log already records, positive or empty, is never re-run. If absent, create the skeleton with `python3 plugins/dma-insights/scripts/client_memory.py init --client <slug>`. WRITE BACK after every page submitted and at session end with `python3 plugins/dma-insights/scripts/drive_fetch.py push-memory --client <slug>` — a session that ends without a successful push-memory has lost its memory: treat that as a failed step and say so in the report. One file per client, never one for all; nothing from another client's file ever enters this session's context.

STEP 2 — PRODUCE THROUGH THE SKILL. Invoke /dma-insights:dma-surface-production for that run and follow its own workflow and routing exactly. The routing authority is 05-lifecycle/routing.md + 05-lifecycle/surface-map.md + docs/AGENTS.md: the surface-producer orchestrates; each page's *-surface-producer is a ROUTER that dispatches to the per-surface producers that own each payload section (every served path has a named owner — the coverage test pins it); the checkers run where the routing table says — finding-challenger BEFORE page-consolidator on every page, evidence-integrity-checker and numeric-reconciliation-checker where routed, exclusion-boundary-auditor before submit. Memory digest and open rejections BEFORE authoring; package vetting via the package-vetter agent (record its result in the memory file's package synthesis section); only the surface-producer submits and promotes. Enrichment at full depth through the enrichment-planner's prioritisation: thin subcaps worked by the H3 resolution ladder (rulebooks/heatmap.md — impact order; re-match with scripts/subcap_match.py before re-search, AMBIGUOUS never auto-assigned; subcap-specific queries paired with their falsifiers; sources opened in scripts/source_yield.py rank order). EVERY search logs twice: query+date in the memory file's research log, source+outcome via `source_yield.py log`. Platform and opportunity surfaces walk the composite-factor discipline in rulebooks/platform.md § P1: the DQ ladder with the engine's thresholds, the greenfield deep-search ladder before any greenfield point is explained, the alignment check (stated_objective only with the entity's own words; otherwise disclosed impact_fallback). Clay in the correct account — if the connector grant is refused in this scheduled context, record the attempt honestly via record_enrichment / the ledger as not-run, never fabricate technographics; MEM-0082 is the permanent lesson. Repair verdicts through the routed single-surface path, never by re-synthesising six pages.

STEP 3 — ASSESS AGAINST THE GOLD STANDARD. After promotion, run the deployed-app-auditor agent: compare every page against Baxter (run c1351d25-a612-4dbe-b498-127bccaf6810, v5.0-pinned — fixtures/gold_manifest.json pins the exemplar shapes) — section presence and richness, narrative thread cohesion, the customer-audience exclusion boundary (no probe ladders, tiers, cap vocabulary, contact routes or reasoning traces in a customer body; ceilings and evidence_coverage are NEVER_SERVED for every audience and their keys must be absent), techstack confirmed-only discipline (CONFIRMED+ABSENT for customers, thresholds per DECISIONS.md D4), platform-fit engine agreement (tiles == cards == engine, factor vocabulary is the engine's four), and no hashtag numbering in any served prose (check_language.py rule).

STEP 4 — CLOSE THE LEARNING LOOP (mandatory, green or not). The qa-overseer writes the findings memory: record_finding for anything new, report_recurrence for anything seen before, resolve_finding where this run proves a fix held, record_refinement for any method that worked. Evidence-matching corrections ALSO go to the matcher's ledger (`subcap_match.py learn` — deciding terms and cell id only) with the story in the memory file; rich sources join the yield ledger so the source list keeps expanding. Any defect class recurring twice or more is handed to the rectifier BY NAME with the rulebook file that should have prevented it. A user-flagged (PERMANENT) class recurring is a blocker-severity finding in its own right.

STEP 5 — REPORT. End with: client + run id; first-pass verdict counts by gate (the curve datum); repairs made and how routed; final six-page state; gold-standard deltas vs Baxter; enrichment honesty (what ran, what was refused, sources logged rich/thin/empty); thin subcaps resolved vs honestly still thin; memory file written back to Drive (yes/no — no is a failure); findings written (ids); explicit confirmation that no PERMANENT class recurred. Keep it under 25 lines.

Hard rules: one client per firing; never BOK; never edit apps/ code; never write another client's memory file; if package vetting fails or entity identity is PENDING_REVIEW unresolved, record the finding and stop rather than force a promote.
```

### 2b · dma-rectification-weekly — Mondays 13:00 UTC · EXISTS

| | |
|---|---|
| **Trigger** | `trig_01CoypdjU6bcwEewvRYxK3S3`, cron `0 13 * * 1`, `create_new_session_on_fire = true`, notifications push+email, created 2026-08-19. Parameters and their rationale: `plugins/dma-insights/skills/dma-rectifier/04-routine/1-weekly-routine.md`. |
| **Cadence, and why** | **Weekly** because the unit of value is a defect *class*, and a class needs several sightings to become visible — a daily run patches single sightings, which is the queue behaviour the rectifier exists to replace. **Monday 13:00 UTC** so the window read is a complete closed week, the Sunday nightlies' CI signal is already in the store, and refinements land pre-workday, reviewable before the week's production runs rather than into the middle of them. |
| **May** | Edit skills, agents, rulebooks and gates — it is the **only** writer of them (constraint [B], the rectifier as an invoked session); record refinements, resolve findings, report recurrences; commit on a branch and open a PR. |
| **May not** | Merge the PR; produce, submit or promote client content; lower the admission threshold to have something to report; scan for defects nobody sighted; edit anything it cannot name a finding for; commit a change the grader scored below 0.75, that testgen could not case, or that the regression re-run did not clear. |
| **Report shape** | `templates/run_report.md` from the rectifier skill, extended with: grader score per admitted change; testgen case counts (fails-before / passes-after); permanent-corpus and full-suite results; and the anti-pattern trend — this window's recurrence and reviewer-reject counts against the trailing four windows and the D3 convergence thresholds, stated as declining, flat or worsening. |

The live prompt — standalone, each firing starts from nothing; kept here
verbatim so a drifted trigger is detectable by diff. It executes the
dma-rectifier skill's run protocol with the admission pipeline
(learning-grader, learning-testgen, the regression re-run) spelled out,
because an unattended session follows what its prompt states, not what a
file it might not open implies:

```
You are the scheduled weekly DMA rectification routine (dma-insights), running as a
fresh session. Load the dma-rectifier skill from the installed dma-insights plugin
and run exactly one rectification cycle. You are the only writer of the plugin's
skills, agents, rulebooks and gates (constraint [B]); nothing you do produces,
submits or promotes client content.

STEP -1 — SELF-PROVISION IF THE PLUGIN IS MISSING. Trigger-fired containers
start with no repository and no plugin. If `claude plugin list` shows no
dma-insights: (a) call the claude-code-remote add_repo tool (owner mishleyotis,
repo accelerate, access read), clone to /home/user/Accelerate at branch
claude/dma-insights-onboarding-0ryrd0 as the tool instructs, then call
register_repo_root — the repo's .claude/settings.json declares the plugin, so
it loads on your NEXT turn; (b) run
`bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`;
(c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent
or empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must
be added in the claude.ai/code environment settings (one line, base64 of
Secret Manager secret dmai-routine-sa-key).

STEP 0 — HANDSHAKE. This container was provisioned before the session started by
the environment setup script (plugins/dma-insights/scripts/bootstrap_session.sh
plus the DMA_ROUTINE_SA_KEY_B64 variable, both wired in the claude.ai/code
environment settings). Run `claude plugin list` and /dma-insights:doctor; require
the dma-insights plugin present at version >= 0.6.0 (the 47-agent roster and its
ledgers) and the doctor green — if either fails, STOP and report what is missing,
naming bootstrap_session.sh and DMA_ROUTINE_SA_KEY_B64 so the fix is actionable.
Then confirm the connector's memory tools answer by calling them for real:
list_defect_classes, then get_memory_digest(days=7). Record the handshake
numbers: tools seen, open finding count, classes seen, oldest open, newest
sighting. If the memory tools are absent or error, STOP, report "memory
unreachable — no rectification performed", and change nothing. Never work from a
transcript, a scratchpad or a local file in place of the store.

STEP 1 — DRAIN, THEN READ. Call ingest_reviewer_feedback() first, so the week's
Accept/Reject verdicts are in the store before the digest is read. Window: the
closed week ending at the most recent Monday 00:00 UTC, PLUS every open finding
carrying a recurrence, whatever its age — a fix that did not hold never ages out
of scope. Read the digest in the order its own `reading` field states:
recurrences_in_window, new_findings_in_window, refinements_in_window (with `held`
per row), open_by_class, ageing_unrefined. Sweep the repository working tree for
feedback memory has never seen (the skill's scripts/drain_local.py emits
record_finding payloads); record those BEFORE triage so this run's clustering
counts them as sightings. THEN read the two learning ledgers the sessions feed:
(a) `python3 plugins/dma-insights/scripts/source_yield.py candidates` — every
source rich twice but undeclared is a register-expansion work item: promote it
into 02-inputs/enrichment_sources.json with tier, facet and provenance, exactly
as measured, never above the tier the evidence class earns; (b)
fixtures/match_feedback.json — recurring vetoes or boosts on the same cell
family are a vocabulary defect in that family's rulebook anchor and cluster like
any finding. For anything that looks new, search_findings first and read
paths_skipped before concluding it is new.

STEP 2 — THE TWICE-RECURRED CLASSES FIRST. Cluster with the skill's
scripts/triage.py. Order clusters by recurrence depth, then client reach, then
sighting count — a class that has recurred twice or more outranks everything,
because two recurrences mean two chosen rungs have already failed to hold. Budget:
open at most three clusters, and finish every one you open; a half-landed
structural change reads as closed to everyone who comes after.

STEP 3 — PROPOSE REFINEMENTS. Per cluster, one rung, chosen deliberately with a
recorded 15-40 word reason. A recurrence lands STRICTLY ABOVE the rung its
previous refinement landed on; a defect that reached a rendered client surface
never lands below R3. Draft the change with the finding ids in hand — an edit
with no finding behind it is a preference, and preferences are how skills drift
away from what was measured. Register expansions from STEP 1(a) are exempt from
the rung ladder — they are additive, carry their yield provenance, and still go
through the grader.

STEP 4 — GRADE. Hand each proposed change to the learning-grader agent with the
rubric at skills/dma-rectifier/assets/learning_rubric.json. Admission threshold
0.75. Below threshold, the change returns to the enrich-and-adjudicate loop with
the per-dimension scores as the work order; a change that cannot reach 0.75 this
run stays an open finding naming what it still lacks. The grader carries no write
tool and cannot edit what it grades — do not route around it.

STEP 5 — CASE. Hand each admitted change to the learning-testgen agent: 5-15
adversarial and regression cases per refinement, every one able to FAIL; a case
that cannot fail is rejected. Its fails_before:true cases are the negative
control at volume — run them against the state that produced the finding and
confirm they fail there, then against the fixed state and confirm they pass.

STEP 6 — RE-RUN THE CORPUS. Run the permanent regression corpus:
`python -m pytest scripts/tests/test_permanent_regressions.py` (it pins
fixtures/permanent_regressions.json — every user-flagged finding; pins must
resolve and the OPEN count may only shrink). Then the full suites: apps/mcp/tests,
apps/api/tests, scripts/tests — and the plugin's own suite,
plugins/dma-insights/scripts/tests (coverage, gold traceability, memory, matcher,
yield ledger, doctor, packaging). Everything previously admitted stays green; a
prior case that had to change to pass is a NEW finding, not a cost of doing
business. A pinned test failing is a recurrence of a user-flagged finding —
report_recurrence, and the rung moves up.

STEP 7 — COMMIT ONLY REGRESSION-SAFE CHANGES. A change is committable only when
it is graded >= 0.75, cased with fails-before/passes-after both recorded, and the
permanent corpus plus full suites are green with it applied. One branch; one
commit per cluster; named paths only; each message naming the class and the
finding ids it closes. Open a PR. Do not merge it — skills and agents are read by
every future session, and an unreviewed change to them is executed by everybody.

STEP 8 — WRITE BACK. record_refinement per change (target_kind IS the rung; open
rationale with "RUNG: Rn — "; put the negative control, both directions, in
verification). resolve_finding naming that refinement for every finding actually
closed. report_recurrence, with a measurement of 30 characters or more, for every
fix found not to have held. Also reconcile the session-routine inventory: run
list_triggers and diff it against plugins/dma-insights/docs/ROUTINES.md — a
missing, paused or drifted trigger is a finding like any other. Client memory
files (per-client md in each client's Drive folder) are READ-ONLY context here:
read one only when a ledger entry's story is needed to judge a cluster; never
edit one — they belong to the synthesis sessions.

STEP 9 — REPORT the anti-pattern trend. From templates/run_report.md, plus: the
handshake numbers; clusters opened, the rung each landed on and why; register
expansions made with their yield provenance; grader score per change; testgen
case counts; corpus and suite results; what closed with its negative control;
what stays open and the rung it waits on; the PR link; and the trend — this
window's recurrences and reviewer rejects against the trailing four windows and
DECISIONS.md D3's convergence thresholds, stated plainly as declining, flat or
worsening.

If there is nothing above threshold: say so, record the run as
examined-and-empty, and stop. Do not lower the threshold, do not scan for defects
nobody sighted, and do not tidy anything. An empty week is the system working.
```

### 2c · dma-refresh-drift-daily — daily 15:00 UTC · EXISTS

| | |
|---|---|
| **Trigger** | `trig_01CvwqVMuLzWyQUsgwor98Sx`, cron `0 15 * * *`, `create_new_session_on_fire = true`, created 2026-08-19. |
| **Cadence, and why** | **Daily** because the inputs move at day granularity: refresh due dates are dates, drift accumulates from each promote and each hourly enrich pass, and duplicates arrive with the half-hourly scan. Hourly would re-read the same answer (the app's own `dmai-enrich-loop` already raises the cadence rows hourly); weekly would let a due client sit silent for days. **15:00 UTC** sits after both nightlies (02:00 exporter, 03:00 scanner) and after the 12:08 synthesis firing has typically closed its loop, so it reads the day's production rather than racing it. |
| **May** | Read the refresh queue, pending runs, drift state and loop health; record findings and recurrences with measurements; escalate by naming the owner of each actionable item. |
| **May not** | **Promote — ever.** Nor submit, withdraw, claim a run, edit the repository, create refresh requests itself (the hourly sweep owns raising cadence rows; this session judges what the sweep raised), or resolve a finding it did not verify held. |
| **Report shape** | Queue counts (requested vs due) with oldest ages; duplicate share of pending runs; top drift blocks worst-first; enrichment-loop health; finding ids written; what was escalated and to whom — or the explicit empty result, recorded as examined-and-empty. |

The live prompt — standalone, each firing starts from nothing; kept here
verbatim so a drifted trigger is detectable by diff:

```
You are the scheduled daily DMA refresh-and-drift review (dma-insights), running
as a fresh session. You observe, record and escalate; you NEVER promote, never
submit a payload, never withdraw or claim a run, never edit the repository, and
never create refresh requests yourself — the app's hourly sweep
(sweep_refresh_due in apps/worker/dma_worker/enrichment.py) raises cadence rows;
your job is to judge what it raised and what it missed.

STEP -1 — SELF-PROVISION IF THE PLUGIN IS MISSING. Trigger-fired containers
start with no repository and no plugin. If `claude plugin list` shows no
dma-insights: (a) call the claude-code-remote add_repo tool (owner mishleyotis,
repo accelerate, access read), clone to /home/user/Accelerate at branch
claude/dma-insights-onboarding-0ryrd0 as the tool instructs, then call
register_repo_root — the repo's .claude/settings.json declares the plugin, so
it loads on your NEXT turn; (b) run
`bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`;
(c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent
or empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must
be added in the claude.ai/code environment settings (one line, base64 of
Secret Manager secret dmai-routine-sa-key).
(The self-provision steps are the one exception to "never edit the repository" —
they add nothing to it; the clone and the bootstrap only read it.)

STEP 0 — VERIFY THE TOOLING. This container was provisioned before the session
started by the environment setup script (plugins/dma-insights/scripts/
bootstrap_session.sh plus the DMA_ROUTINE_SA_KEY_B64 variable, both wired in the
claude.ai/code environment settings). Run /dma-insights:doctor; require the
plugin at version >= 0.6.0, the doctor green and the connector's tools present.
If the plugin is missing or the connector is unreachable, STOP and report
exactly which layer failed, naming bootstrap_session.sh and
DMA_ROUTINE_SA_KEY_B64 so the fix is actionable. A drift review that cannot read
the state invents it.

STEP 1 — THE REFRESH QUEUE. Read GET /v1/ops/refresh-queue on the api (internal
audience — the queue names actors and reasons and is never served to customers).
It returns two deliberately unmerged lists: `requested` (a human asked, with a
reason) and `due` (six months ran out, a date and nothing else). If the api is
unreachable, read the same state client by client through the connector:
get_client_state(display_id) for every serving client, whose drift summary
carries the facet states. For each queue entry note its age (requested_at or
refresh_due_date to today) and whether anything is already working it — an open
run for the entity, or its place in the synthesis routine's learner order.

STEP 2 — DUPLICATES. Call list_pending_runs and read its disclosure: the
top-level duplicate_requests count and per-row is_latest_for_request. Work is
only ever the is_latest_for_request=true row. Report the duplicate share; a
rising share is a worker dedup finding, not something to clean up by hand from
this session.

STEP 3 — ENRICHMENT DRIFT, WORST FIRST. Per serving client, the drift summary
orders facets worst-first — never_enriched outranks enriched_not_promoted
outranks current — and `blocking` names the facets that stop a client being
called done. Read the worst 10 clients at most. Then read
GET /v1/ops/enrichment-loop: `healthy` is strict, and a job that never closed,
errored, or scanned zero runs is UNHEALTHY — each of those is a finding, because
a loop that finds nothing to look at reports the same numbers as a loop with
nothing to do, and only one of those is fine. For the worst clients, ALSO read
that client's memory file from its Drive folder (READ-ONLY — "<client-slug> —
synthesis memory", per 05-lifecycle/client-memory.md): open questions older
than 14 days and thin-subcap resolution entries with no follow-up are drift the
facet states cannot see, and a memory file that exists but was last written
before the client's latest promotion means a session skipped its write-back —
each of those is a finding naming the synthesis routine. Never write a memory
file from this session.

STEP 4 — RAISE OR ESCALATE WHAT IS ACTIONABLE. For each actionable observation,
record_finding through the connector with a real measurement — the endpoint or
tool called and the count with its denominator, 30 characters minimum. Use
report_recurrence, not a new finding, when memory already knows it
(search_findings first; read paths_skipped before concluding it is new).
Escalation means naming the owner in the finding: a due client the learner order
will not reach goes to the synthesis routine by name; an UNHEALTHY loop names
the dmai-enrich-loop trigger and apps/worker/dma_worker/enrichment.py; a due
client with no open request names the sweep; a duplicate-share rise names the
worker dedup rules; a stale memory file or aged open question names the
synthesis routine's write-back step. Do not fix any of them here.

STEP 5 — REPORT. Queue counts (requested, due) with the oldest age in each
list; duplicate_requests and the share of pending runs it represents; the top
drift blocks worst-first with client and facet; loop health with the last job's
tallies; memory-file staleness observed (client, days); finding ids written;
what was escalated and to whom. If the queue is empty, no drift is blocking,
the loop is healthy and no memory file is stale, say exactly that and record
the run as examined-and-empty — "the window was read and held nothing" and "no
one looked" must stay distinguishable.
```

---

## 3 · The reconciliation rule

**Scheduler routines reconcile mechanically.**
`plugins/dma-insights/routines.json` is the declaration;
`plugins/dma-insights/scripts/setup_routines.py` is the reconciler (dry-run
by default, `--apply` to act, exit 1 while a mandatory routine is missing);
`/dma-insights:setup-routines` is the report-first wrapper. Run it after any
deploy that touches `infra/deploy.sh`'s scheduler section, and whenever a
routine is suspected of not firing — a paused job, a drifted schedule and a
duplicate all look like nothing at all from inside the app, and the reconciler
is the only thing that asks.

**Session routines have no reconciler today — reconciliation is manual.**
This file is their declaration; the check is `list_triggers` (CCR) diffed
against section 2 — name, cron, enabled state, fresh-session mode, and the
prompt itself, which is why 2a's live prompt is quoted verbatim. The
`/dma-insights:doctor` command checks plugin, identity, token audience and
connector reachability and has **no routine check yet**; when it grows one,
it should perform exactly this diff. Until then the diff belongs to the
weekly rectification session's checklist (its prompt's STEP 8 states it), so
the gap is examined at least weekly by the one routine whose job is noticing
what quietly stopped holding. A missing, paused or drifted trigger found by
that diff is a finding like any other: recorded, measured, and closed by a
refinement — not silently re-created.
