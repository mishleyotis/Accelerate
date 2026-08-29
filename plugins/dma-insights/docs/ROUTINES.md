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

Five live: **2a** synthesis lane A, **2e** synthesis lane B (the same work
ten minutes later, which is how two clients get produced per cycle without
a session spawning another), **2b** weekly rectification, **2c** daily
refresh-and-drift, **2d** the hourly watchdog. 2a-ii is retained as a
deleted routine's record, not as a live one.

**NO VERSION LITERAL AND NO CLIENT NAME LIVES IN ANY OF THESE PROMPTS**
(owner, 2026-08-23). Both rules exist because both failed in the same week.
The version floors were prose — ">= 0.6.0", ">= 0.8.0" — and prose is never
evaluated, so a container carrying 0.2.0 with five of forty-seven agents
cleared all of them by never being compared to one; every prompt now runs
`plugins/dma-insights/scripts/plugin_version.py` and obeys its verdict. The
client names were a five-name learning curriculum reordering the synthesis
queue, which decided which client a firing carried and kept re-offering
names that had already failed vetting; the gate now walks the queue in the
queue's own order. The one name-based rule that remains is
`run_gate.HELD_OUT`, and it SUBTRACTS.

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

**AUTHENTICATING IS NOT THE SAME AS BEING ALLOWED (measured 2026-08-21T02:34Z,
and it is what had actually been killing the routine).** The paragraph above
says the variable is "enough on its own." It is enough for AUTH. It is not
enough to run. A session created with this repo attached bound the connector
perfectly — `mcp__plugin_dma-insights_connector__get_run_progress` existed and
the session called it — and then stopped on:

```
Waiting on permission: mcp__plugin_dma-insights_connector__get_run_progress
```

A trigger-fired container has nobody to answer that prompt. The firing burns
its twelve-hour slot, stages nothing and records nothing — precisely the trace
the 00:08 firing left (fired 00:10:43Z, zero staged rows, zero findings, 178
clients still INGESTED per MEM-0118).

Every prior diagnosis reached for MEM-0112 (binding) because from the outside
the two are indistinguishable: a session that *cannot* call a tool and one that
is *not allowed* to call it both simply stop, with `claude plugin list` enabled
and the doctor green. MEM-0112 is real; it was not the blocker.

So there is a THIRD prerequisite beside the script and the variable, and its
scope is the trap:

* The grant must be **user scope** — `~/.claude/settings.json`. The repo's own
  `.claude/settings.json` is PROJECT scope, and project permission rules are
  **not applied in a non-interactive session**: the workspace is untrusted and
  the rules are skipped. A grant committed there reviews as correct, appears in
  every diff as the fix, and changes nothing.
* The server segment must be **glob-free**: `mcp__<server>__*` is honoured;
  `mcp__*` is skipped with a warning and approves nothing.
* `acceptEdits` does **not** auto-approve MCP calls — it covers file edits and
  common filesystem commands only. `dontAsk` auto-DENIES anything not
  pre-approved. Neither mode substitutes for the grant.

`bootstrap_session.sh` now writes that grant (merged, never clobbering the
plugin keys it wrote earlier in the same run; refusing rather than repairing a
malformed settings file, since a broken settings.json silently disables every
setting in it). Because settings are read at session START, this only helps a
session the script ran BEFORE — which is exactly the environment-setup-script
path, and one more reason that wiring is load-bearing rather than belt-and-
braces. A session spawned via `create_session` can carry the same grant
directly through `extra_allowed_tools`.

Pinned by `plugins/dma-insights/scripts/tests/test_bootstrap_permission_grant.py`.

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

Status at 2026-08-29 (`list_triggers`, reconciled this day): the live
account carried THREE triggers, not five — `dma-synthesis-sequence`
(the pre-2026-08-23 prompt under the old name, version literals and the
named client curriculum still in it), `dma-rectification-weekly` and
`dma-refresh-drift-daily` (both on pre-plugin_version floors; both with
FAILED last runs) — and lane B (§ 2e) and the watchdog (§ 2d) were
MISSING with no deletion record in this file, which per § 3 reads as
drift, not decision. Reconciled doc → trigger: the three were updated
to this file's fenced prompts (the synthesis trigger renamed to `-a`),
lane B and the watchdog recreated from their fences. A recreated
trigger carries NO claude.ai connectors (API-created; the org's
`connectors` parameter is disabled) — lane B needs its connectors
re-attached BY HAND in the routines UI or its STEP 0 stops every
firing; the watchdog needs none by design. This reconciliation also
landed the research tier in the prompts: a G1/G2 STOP with no package
in the intake tree is named a RESEARCH gap (research-conductor's job),
and the rectifier's corpus step gained the research-engine suite and
the two stress drivers.

Status at 2026-08-19 (`list_triggers`, evening): all three then-declared
triggers existed and were enabled. (b) and (c) were created 2026-08-19T21:24Z from this file's fenced
prompts; a firing that finds this paragraph disagreeing with `list_triggers`
has found the drift section 3's manual reconciliation exists to catch.

### 2a · dma-synthesis-sequence-a — every 12 hours · EXISTS

**Two lanes, not one session spawning another (owner, 2026-08-23; mechanism
revised the same day).** The owner asked for two clients a cycle in two
sessions. The first design had this Routine spawn a sibling with the
claude-code-remote `create_session` tool. Measured 2026-08-23: **no
trigger-fired session carries any claude-code-remote tool** — a firing gated
two clients, could not spawn, produced one, and correctly reported the second
unstarted. Correct behaviour, and one client short every cycle.

So the parallelism moved to the schedule, which needs no tool to be present:
this Routine (**lane A**) and `dma-synthesis-sequence-b` (**lane B**, § 2e)
fire the same work ten minutes apart, each in its own fresh session, each
carrying exactly ONE client. Lane A claims first; the queue selector removes
a claimed entity, so lane B is offered a different one. If they ever do
collide, `claim_run` is atomic — lane B's claim is refused and it falls
through to its first `GATE: RESERVE` line.

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
| **Trigger** | `trig_011Qkj9VgeRgktdhgaZxkeut` (the surviving synthesis trigger, renamed from `dma-synthesis-sequence` and re-pointed at this fenced prompt 2026-08-29; the id this row carried before, trig_01WTf9nQdFPQb6jiSVVyf37u, no longer exists), cron `8 */12 * * *`, enabled, push notifications on, created 2026-08-19, renamed to `-a` 2026-08-23. Observed `last_fired_at` 2026-08-23T06:08:06Z with `next_run_at` 12:08 — a six-hour gap where the cron reads twelve, so the effective cadence is the trigger's, not this table's arithmetic; read `next_run_at` rather than computing it. |
| **Cadence, and why** | One client per firing, end to end — vetting, six pages, verdicts, repairs, gold-standard audit, learning-loop close — is a multi-hour session, which is exactly why a session carries one and the schedule supplies the second. Two lanes a cycle feed the weekly rectification about the volume of sightings it can absorb, and a failed firing costs one client of queue progress, not a cycle. |
| **May** | Produce the ONE run `run_gate.py pick` emits — the queue's own order, **no client named to be admitted** (owner, 2026-08-23) — then submit and promote, but only **through the installed plugin**: `/dma-insights:dma-surface-production`, its routing table, its agents. Fall through to a `GATE: RESERVE` when a package fails vetting. Repair via the routed single-surface path. Write the findings memory (STEP 4 is mandatory, green or not). |
| **May not** | Produce more than one client per firing (the cycle's second is lane B's); touch a held-out entity — `run_gate.HELD_OUT` names them and the gate already subtracts them, which is the one name-based rule left anywhere in the walk; edit `apps/` code; force a promote past a failed vetting or an unresolved PENDING_REVIEW identity; fabricate technographics when an enrichment grant is refused (record the attempt honestly — MEM-0082 is the permanent lesson); improvise ad-hoc multi-agent workflows around the plugin, because the plugin **is** the system under test. |
| **Report shape** | Under 25 lines: client + run id; the gate's verdict lines; the claim outcome (first attempt, after lease expiry, or fell through to a RESERVE); first-pass verdict counts by gate (the learning-curve datum); repairs made and how routed; final six-page state; gold-standard deltas vs the exemplar `plugins/dma-insights/fixtures/gold_manifest.json` names; enrichment honesty (what ran, what was refused, search_requests relayed); memory pushed yes/no; finding ids written; explicit confirmation that no PERMANENT class recurred. |

The live prompt, kept here verbatim so a drifted trigger is detectable by
diff. Last pushed doc -> trigger 2026-08-23T06:31:46Z. That revision: no
version literal anywhere (STEP 0 runs `plugin_version.py` and obeys its
verdict), no client named to be admitted (STEP 1 walks the queue and nothing
else; the gold exemplar is read from `plugins/dma-insights/fixtures/gold_manifest.json` rather
than named here), one client per firing with lane B carrying the second, and
STEP -1 self-provisioning by real `git clone` rather than by a
claude-code-remote tool no trigger-fired session carries.

```
You are the scheduled DMA synthesis routine (dma-insights). ONE client per firing, end to end, through the installed plugin only — its skills, agents, hooks and routing are the system under test, so do not improvise around them and do not use ad-hoc multi-agent workflows. ONE CARVE-OUT, DEFINED BY THIS SAME TASK: STEP 0's RECOVERY MODE is part of these instructions, not an improvisation around them. When the version check reports UPDATED_MID_SESSION, dispatching every routed stage via agent_run.py and following the skill's files from the current checkout IS the sanctioned path — the same agents, the same routing, the same gates, run through fresh child processes that bind the CURRENT install, where the in-process Agent and Skill tools would run the stale one this session bound at start. What this sentence bans is inventing a different pipeline; executing the prescribed pipeline through the prescribed fallback launcher is these instructions. Measured 2026-08-24 12:18Z: a lane read the two as contradictory and ended a healthy firing over it — the reject-rather-than-triage failure the owner keeps flagging. A sibling Routine fires this same prompt ten minutes behind you and carries the cycle's second client; you carry yours and only yours.

STEP -1 — SELF-PROVISION IF THE REPOSITORY IS MISSING. If /home/user/Accelerate/plugins/dma-insights does not exist: (a) get the repository. `git clone --branch claude/dma-insights-onboarding-0ryrd0 https://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST thing to try, with that exact real URL — never a placeholder. If the claude-code-remote add_repo tool happens to be present it is the tidier route (owner mishleyotis, repo accelerate, access push — GitHub push access is always attached (owner, 2026-08-20) through the harness's own credentials; you may push ONLY this session's own outcome branch, never the plugin branch, never main; the plugin, skills, agents and gates remain the weekly rectifier's alone (constraint [B]); no GitHub PAT exists anywhere and the plugin's credential guard denies credential-shaped pushes deterministically), followed by register_repo_root — BUT DO NOT WAIT ON IT: measured 2026-08-23, no trigger-fired session carries any claude-code-remote tool, so a step that depends on one is a step that does not run. The repo's .claude/settings.json declares the plugin from its own marketplace, so it loads on your NEXT turn; (b) run `bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh` — it lands the service-account identity from the DMA_ROUTINE_SA_KEY_B64 environment variable (base64 of the key JSON on one line; raw DMA_ROUTINE_SA_KEY also accepted), fetches the connector path token fresh from Secret Manager, and installs the plugin with its config; (c) KNOW THE BINDING TRUTH (MEM-0112, measured twice 2026-08-20): a plugin installed MID-SESSION never binds its MCP tools into this session's callable set — `claude plugin list` showing enabled, the doctor green and mcp_raw probe UP all prove the SERVER and the install, none of them proves THIS session can call the tools. STEP -1 running at all also means the environment setup script failed to pre-provision this container — name that in the report. After (b), run STEP 0's callable-tools stress test; if the connector tools are not callable, write the resume state (Drive bundles + memory handoff), report the binding defect, and END THIS FIRING cleanly — the next firing binds at session start. If /root/.dma/sa.json is still absent or empty after (b), the connector cannot authenticate — STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must be added in the claude.ai/code environment settings, one line, the base64 of Secret Manager secret dmai-routine-sa-key.

STEP 0 — VERIFY THE TOOLING. This container was provisioned before the session started by the environment setup script (plugins/dma-insights/scripts/bootstrap_session.sh, wired in the claude.ai/code environment settings together with the DMA_ROUTINE_SA_KEY_B64 variable): repo checkout, plugin install, service-account identity, connector path token. A RESTORED CONTAINER SNAPSHOT CAN CARRY AN ANCIENT PLUGIN, and until 2026-08-23 nothing here could see it: these prompts named version floors in prose (">= 0.6.0", ">= 0.8.0") and prose is not evaluated, so a snapshot carrying 0.2.0 — five agents against the checkout's forty-seven — cleared every floor by never being compared to one, and the doctor counted the CHECKOUT's files and printed 47 green on the same container. NO VERSION IS WRITTEN DOWN IN THIS PROMPT. Run `python3 plugins/dma-insights/scripts/plugin_version.py --heal` and obey its verdict; it compares what this session LOADS (installed_plugins.json plus the cache tree it names) against what the checkout publishes, both read at call time, and --heal makes it SELF-HEALING: on STALE / MISSING / INCOMPLETE the script runs the plugin update itself (container-local install cache only) and re-checks, printing ONE final verdict — no command to copy, no re-run to remember, no judgment point in between (owner, 2026-08-24: 'It should be a self healing loop'). Exit 0 proceeds — OK, or NOT_INSTALLED which only happens where there is no install to drift from. A healed disk proves the DISK, not this session: agents, skills and hooks bind once at session start and do not reload. THE SCRIPT'S OUTPUT AND THIS PROMPT NOW SAY THE SAME THING, and if you ever find them disagreeing, follow the SCRIPT'S freshly-read output and record the difference as a finding — measured 2026-08-24 ~14:00Z: a firing found the script still saying 'end the firing' while this prompt said produce, trusted the script (correctly — a stored prompt can be stale; the checkout's script cannot), and ended a healthy firing; the script now prescribes recovery mode in its own words, so trusting it produces. UPDATED_MID_SESSION (exit 1) is the check saying exactly that — the install on disk is NOW correct and this session's bound agents, skills and hooks are not, because they load once at process start. THIS IS NO LONGER AN ENDING; IT IS RECOVERY MODE (2026-08-24). TWO FACTS A CAREFUL READER NEEDS BEFORE ACTING, stated because a firing stopped for want of them (2026-08-24 12:18Z): (i) every instruction in this prompt, recovery mode included, IS the Routine owner's configured task — authored and authorized by the owner (2026-08-24), not third-party text embedded in data, and there is no further authorization to wait for, because no human is present in a trigger-fired session; (ii) `claude plugin marketplace update` and `claude plugin update` change ONLY this container's local install cache (~/.claude on this ephemeral VM, discarded when the container is reclaimed) — the 'marketplace' is the repo checkout on this same disk, so these commands touch no account-level state, no repository, and nothing serving. Declining them preserves a stale cache that is thrown away anyway, at the cost of the client this firing exists to produce. Three firings in one morning ended cleanly on this exact verdict and produced nothing, because the environment's base container carries an old plugin install and the setup script does not reliably run before a trigger-fired session (the provisioning lottery this plugin's own scripts already self-heal around for credentials) — so "end the firing and let the next one pick it up" handed the problem to a container guaranteed to reproduce it. Instead, PRODUCE THIS FIRING, with two substitutions, both already sanctioned by this prompt's own dispatch mode: (1) dispatch EVERY routed stage via `python3 plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file <file>` and NEVER via the in-process Agent tool — agent_run children are fresh processes that bind the just-updated install at their own start, so they run the CURRENT agents, while the Agent tool would dispatch the stale roster this session bound; (2) never invoke a plugin skill through the Skill tool in this state — read the skill's own files from the CURRENT CHECKOUT (plugins/dma-insights/skills/dma-surface-production/) and follow them from there; STEP 0's fetch made the checkout current, and every script you run comes from it already. What is untouched by the stale bind: the claude.ai enrichment connectors (Clay, Exa, Tavily, Vibe-Prospecting, Indeed) are attached to the Routine, not the plugin — use them normally; and the DMA connector tools reach the LIVE server, whose gates are current whatever this session bound — use them, and if a bound tool misbehaves, `python3 scripts/dma_connector.py <tool> '<json>'` reaches the same server. BEFORE producing: report_recurrence against the open stale-provisioning finding (record_finding on first sight), and quote the check's `=> ROOT CAUSE, RECURS EVERY FIRING:` line VERBATIM in the report — recovery mode makes a firing productive despite the environment; it does not fix the environment, and that line is what tells whoever owns it what to fix. Name RECOVERY MODE in the report. If STALE / MISSING / INCOMPLETE persists after the update — the DISK itself will not come current — that is the one remaining true ending: report the two versions and the two agent counts it names and END this firing cleanly rather than producing on stale skills. (Corrected 2026-08-23: this prompt used to say the update "applies at NEXT session start", and a session that re-checked in the same firing saw OK and reported the prompt as contradicted. Both halves were true of different things; plugin_version.py now measures which, by comparing the install's lastUpdated against this session's process start rather than asserting a mechanism.) AHEAD means the CHECKOUT is the stale half and updating the plugin would downgrade it: pull the branch. MANIFEST_SPLIT is a repo defect — report it, never work around it. A shadowed record at a lower scope is named in the output and is not a failure; the highest version is what loads. THEN the dma-insights doctor command (/dma-insights:doctor) fully green, including its own installed-plugin row and the live tool-roster check. THEN THE BINDING STRESS TEST — never assume, confirm (owner, 2026-08-20): the doctor and mcp_raw probe prove the SERVER; they do not prove this session. Make a REAL in-session MCP tool call — call get_memory_digest (days=1) or list_pending_runs AS A TOOL CALL, and require a real response. If no mcp__plugin_dma-insights_connector__ tool is callable (ToolSearch finds none), the binding is absent (MEM-0112 class): update the client resume bundles and memory handoff if any work context exists, report the binding defect with what `claude plugin list`, the doctor, the probe and ToolSearch each said, and END the firing — never proceed to the gate on an unbound session. THEN the access preflight, in this order: (a) `python3 plugins/dma-insights/scripts/drive_fetch.py check` — REQUIRED: the intake folder must answer the routine service account; if it fails, STOP and report its exact message — a synthesis that cannot reach the DMA drive folder does not start; (b) enrichment connectors — REQUIRED (owner, 2026-08-20: the routine never runs in degrade mode). Check which claude.ai connector tools this session carries (Clay, Exa, Tavily, Vibe-Prospecting/Explorium, Indeed; they appear as mcp__<Name>__ tools when attached to this Routine in the claude.ai routines UI — plugins/dma-insights/docs/CONNECTORS.md). If Exa, Tavily AND at least one of Clay/Vibe-Prospecting are present, proceed at full depth and record any absent extras per facet. If that minimum is not met, STOP without producing anything and report exactly which connectors the session carries versus the Routine record — the fix is attaching them on this Routine's own edit screen in the claude.ai routines UI (the connector browse list's Use buttons enable a connector for the org, NOT for a Routine — measured 2026-08-20). If the plugin is missing, stale, or the doctor fails, STOP and report exactly what is missing, naming bootstrap_session.sh and DMA_ROUTINE_SA_KEY_B64 so the fix is actionable — producing anything with degraded tooling is worse than producing nothing.

STEP 1 — THE PRE-SYNTHESIS GATE, ALWAYS THE FIRST CASE (owner, 2026-08-20: before any synthesis starts a non-duplicate entity must be verifiably ingested, and a client already served on the web app and not due a refresh is never re-produced — without this chain the scores may be hallucinated). Run `python3 plugins/dma-insights/scripts/run_gate.py pick` and obey its output verbatim. It emits ONE `GATE: PRODUCE` line — the client this session carries — followed by `GATE: RESERVE` lines naming further producible runs. A RESERVE is NOT a second client to synthesise: it is where you go when a package fails VETTING, which happens after this gate has passed it and inside the producing session (owner, 2026-08-23: "if 1 package is not up to par, try another one"). The cycle's second client belongs to the sibling Routine firing ten minutes from now, not to you. It walks THE PENDING QUEUE AND NOTHING ELSE, in the queue's own order (owner, 2026-08-22 and again 2026-08-23: "Ensure no client hardcoding. This is a routine meant to run and ingest DMAs."). Candidates come from the queue's own selector — one run per entity, newest assessment first, nothing whose entity carries a live claim. NO CLIENT IS NAMED TO BE ADMITTED: a five-name learning curriculum used to reorder the queue ahead of everything else, which decided which client a firing carried and kept re-offering names that had already failed vetting, and it is gone. The one name-based rule left is the held-out control, and it SUBTRACTS — those entities are never produced. (`--prefer` still exists for a human re-running one client by hand; the routine passes nothing and you must not add it.) A failing candidate no longer halts the walk: its gate and detail are printed, it is skipped, and the next candidate is gated, up to --max-candidates (40) per firing. Nothing is silent — the PRODUCE line names what was walked past, and a package failure is a finding to record rather than a reason to stop looking. It emits a `GATE: PRODUCE <client> run <run_id>` line — the ONLY run you may claim and synthesize — plus any `GATE: RESERVE` lines; or `GATE: STOP` after gating every candidate it could reach, listing each one with the gate it failed. A candidate failing G1/G2 because NO package exists for it in the intake tree at all is a RESEARCH gap, not an ingest fault: the package must be PRODUCED by the research tier (the research-conductor agent dispatching the sixteen category researchers — the plugin's routing.md § entry fork), which is never this firing's job — name it as a research gap in the report rather than recording it as a scan failure. On STOP: record_finding for each distinct failure with the gate's exact words, then stop — NEVER hand-pick a run around the gate. STOP now means the whole reachable queue was gated and none was producible, which is a real finding about the corpus, not a single client's bad day. What it verifies per candidate: G1 an INGESTED latest-for-request run whose PARSED bundle is substantial (scored cells above the floor — a run row with a stub bundle is a scan failure, not a synthesis input); G2 the raw package traces to the client's own folder in the Drive intake tree; G3 the client is not already serving six current pages (unless the refresh queue names it — then it is a refresh run); G4 no unadjudicated twin entity in the pending set. THEN CLAIM THE EMITTED RUN with claim_run before any production. IMMEDIATELY AFTER THE CLAIM, preflight the client's insights folder: `python3 plugins/dma-insights/scripts/drive_fetch.py ensure-insights --client <display_id>` — finds or creates the folder under the owner taxonomy 'DMAI - <Client Name>' (2026-08-20; legacy 'DMA Insights' folders are healed to it, never duplicated), creates surfaces/, and captures the folder ids to /root/.dma/bundles/<slug>/folder_ids.json so every later push-bundle writes by id, resilient to renames and listing failures. Record insights_folder_id in state.json and the report. THEN, BEFORE ANY PRODUCTION, the mandatory preflight status check (owner, 2026-08-20): read get_run_progress for the claimed run even on a first attempt — pages or sections already staged with passing verdicts are NOT re-synthesised; repair or re-validate only what fails or is missing (the skill's own rule: get_run_progress shows where you are, and passing pages are never re-done), so no firing ever duplicates a predecessor's effort. If the claim is refused because another session holds the lease: read get_run_progress — if the holder has staged any submission, STOP and report it (a live parallel producer is real and you never race it; the sibling Routine is exactly such a producer); if nothing is staged and the lease's expires_at is within ~45 minutes (the signature of a killed session's orphaned lease), do STEP 1b while the clock runs and retry the claim after expiry, at most twice; if it is still held after that, move to your first `GATE: RESERVE` line rather than waiting, and report the holder id and expiry verbatim.

STEP 1b — PULL THE PACKAGE AND OPEN THE CLIENT'S MEMORY. `python3 plugins/dma-insights/scripts/drive_fetch.py pull --client <display_id>` downloads the client's folder RECURSIVELY from the intake tree to /root/.dma/packages/<slug>/ — subfolders included — the RAW package, beside the parsed one the connector serves. THEN RESOLVE THE PACKAGE, never assume its shape (measured 2026-08-20: 131 of 178 client folders are canonical, the rest are wrappers, older numbering generations, version stacks with INTERIM copies, or briefing-only): `python3 plugins/dma-insights/scripts/package_map.py /root/.dma/packages/<slug>` names the scoring and research workbooks across every generation, the evidence stores beyond the workbooks (CSVs, JSON, JSONL ledgers — ten stores in one canonical package, measured), the slides exclusions, and every AMBIGUITY — ambiguities are adjudicated by the package-vetter, never guessed past. Build the client corpus index: `python3 plugins/dma-insights/scripts/corpus_search.py index --package /root/.dma/packages/<slug>` — deep client-corpus searches answer 'where else does this information live' and run BEFORE any web search. Normalize evidence to schema: `python3 plugins/dma-insights/scripts/evidence_normalize.py --package /root/.dma/packages/<slug> --client <display_id> --out /root/.dma/packages/<slug>/normalized_evidence.jsonl` — it merges every store, fills url/date/excerpt from the client's OWN corpus with provenance recorded, reports content conflicts for adjudication, and emits ready search_requests for what the corpus cannot answer; run those through the session's connectors and register what returns BEFORE scoring-dependent surfaces — a row is never registered bare, never dropped silently, and it now dates still-dateless rows at the package's own collection stamp (date_provenance 'collection', basis recorded — 'observed as of the assessment date' is a real date with explicit provenance, strictly more honest than UNVERIFIED for facts the assessors verified when they wrote them; owner, 2026-08-20); a publication date always outranks a collection date and the gaps output keeps requesting one per collection-dated row, so run those requests through the connectors and upgrade what returns; pass --assessment-date only when the vetter adjudicates a better stamp; a row with no date from ANY rung stays UNVERIFIED — collection dating is derived from the package's own stamps, never guessed. The synthesis corpus is the ENTIRE package except the bulky slides (05_narrative_deck and variants — excluded by pattern; 02-inputs/1-package.md): 01_evidence, both workbooks, 04_reports, 06_peers, 07_governance QA passes and 08_appendices are all input. Consult it where the parsed bundle raises a question, and remember the parsed bundle through the connector remains the scoring source of truth (scores are synthesized from the package FIRST, then validated against public data and enrichment — never invented from either). Memory (05-lifecycle/client-memory.md is the contract): the pull also lands the client's existing memory file at /root/.dma/clients/<slug>.md automatically — variant slugs are matched by identity, and push-memory heals the Drive filename to canonical. READ THE RESUME BUNDLES FIRST: the pull lands the client's insights folder ('DMAI - <Client Name>', legacy 'DMA Insights' healed) — `state.json` (run id, vetter verdict + quarantine list, claim history, per-section status map) and `surfaces/<payload_section>.json` (payload + challenge verdicts + citation state per produced surface). ALSO READ `watchdog_resume.json` IF IT IS THERE: the hourly watchdog writes it when it finds this run stalled or its claim expiring, and it names what was ALREADY BANKED before what is missing — that is the file's whole purpose, because the expensive mistake after a stall is not the stall, it is producing the finished pages a second time. It is an observation with a timestamp, not an instruction: treat it as a pointer and confirm against get_run_progress, which is authoritative. This is the STRUCTURED resume state a resuming workflow reads instead of racing prose: statuses stand unless evidence contradicts them; a bundle carrying a payload is re-validated (citations re-checked live) rather than re-produced; a status WITHOUT a payload guides priority but is not content. THEN SEARCH THE ARTEFACT STORE, which the bundles do not cover (owner, 2026-08-21): `python3 plugins/dma-insights/scripts/drive_fetch.py find-artifact --client <display_id> --run <run_id>` lists every artefact already filed for this run — RECURSIVELY, so one filed in the wrong folder still answers rather than reading as absent, and READ-ONLY, so asking does not create the folder it reports on. An artefact that exists is work already done: re-validate it, never re-produce it. Anything it flags MISFILED is put right with `python3 plugins/dma-insights/scripts/artifact_store.py heal --root /root/.dma/bundles/<slug>/artifacts --apply` and re-pushed, never left where the next search might miss it. Then READ the memory file's open questions section plus the sections for the pages in scope, including any HANDOFF narrative — resumed, not re-derived; a search the research log already records, positive or empty, is never re-run. If no memory exists yet, create the skeleton with `python3 plugins/dma-insights/scripts/client_memory.py init --client <slug>`. WRITE BACK after every page submitted and at session end with `python3 plugins/dma-insights/scripts/drive_fetch.py push-memory --client <display_id>` — a session that ends without a successful push-memory has lost its memory: treat that as a failed step and say so in the report. One file per client, never one for all; nothing from another client's file ever enters this session's context.

STEP 2 — PRODUCE THROUGH THE SKILL. Invoke /dma-insights:dma-surface-production for that run and follow its own workflow and routing exactly. ONE CLIENT PER SESSION, TWO SESSIONS PER CYCLE (owner, 2026-08-23; mechanism revised the same day). Produce the ONE client your gate emitted, in THIS session, end to end. Do NOT try to carry a second client here: that is how a firing runs out of turn budget halfway through the second, and the parallelism comes from the schedule instead. Two Routines fire this same prompt each cycle, ten minutes apart, each in its own fresh session — so two clients are produced per cycle without either session needing to spawn anything. The earlier session has claimed by the time the later one gates, and the queue selector skips any entity under a live claim; if the two ever do collide, `claim_run` is atomic, the loser's claim is refused, and it moves to its first `GATE: RESERVE` line. THE EARLIER DESIGN SPAWNED A SIBLING WITH create_session AND THAT TOOL IS NOT IN THIS SESSION'S TOOLSET (measured 2026-08-23: a firing gated two clients, could not spawn, and correctly reported the second unstarted — correct behaviour, and one client short every cycle). Never depend on a tool being present to do the routine's core work. IF THE PACKAGE-VETTER REFUSES your client: record the finding, release nothing you have not claimed, and move to the first `GATE: RESERVE` line — claim it and produce that client instead. A REFUSE is a fact about one package, not a reason to end a firing; only an empty reserve list ends it. DISPATCH (05-lifecycle/routing.md § Dispatch mode): trigger-fired sessions carry the Agent tool but only ONE nesting level — a subagent cannot spawn subagents (MEM-0106, measured 2026-08-20). Therefore THIS TOP SESSION is the orchestrator: dispatch every routed stage DIRECTLY via the Agent tool — the per-surface producers, finding-challenger, page-consolidator, the vetter, the auditors — in the routing's order (EXCEPT in STEP 0's RECOVERY MODE, where every stage goes via agent_run.py even though the Agent tool is present, because the Agent tool dispatches the stale roster this session bound); NEVER delegate the pipeline to one enclosing surface-producer subagent (it cannot fan out, and an orchestrator that cannot dispatch improvises), and NEVER write a page or a challenge inline because dispatch feels slow. A package-vetter REFUSE is overturned only by a fresh top-level re-vet, never by a producer's own re-analysis. Where the Agent tool is genuinely absent, `python3 plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file <file>` runs a stage headless — same agents, same order, same refusals. CONNECTOR SELF-HEAL AND REVIVE (two shapes, one state: a session's persistent MCP client can die mid-run with 401 / 'Dynamic Client Registration rejected' while the server is healthy — measured 2026-08-20 — and a session CONTINUED after its token budget reset comes back with NO mcp__* connector tools at all, because bindings are made once at process start and never return mid-session; the owner hit that second shape on 2026-08-24: continued sessions declared the tools 'not present … lost mid-session … cannot be recovered' and produced nothing, while the server held every claim and staged page the whole time. Either way the 'lost' tools are a per-process BINDING, never the work: identity re-mints per call from the service-account key, and claims, staged pages and verdicts live in the connector's database, answering this session, the next one, or one thirty days out alike. The stdio transport re-mints identity per request inside the proxy process (fresh headers, re-mint on 401, initialize replay) and prevents most of the first shape automatically, so the connector self-heals during the session and no secret enters the transcript; this ladder handles the rest): on ANY connector tool failure of that shape — or on finding the connector tools absent in a continued session — run `python3 plugins/dma-insights/scripts/mcp_raw.py revive --run <run_id>` (bare `probe` when no run is in hand). REVIVE: OK means the server is UP, identity minted fresh, and the run's banked-versus-missing split printed so nothing already staged is produced twice. STANDING AUTHORIZATION (owner, 2026-08-24: 'there should be a mechanism to ensure that this connection gets revived and reconnected without any issues in case the tokens reset', named for the case where 'the client that was being processed had not been promoted'): when the binding is absent or dead, the server is UP, and this session holds — or held — the claim on an UNPROMOTED run, the bridge IS the production channel for that run: reads AND writes via `python3 plugins/dma-insights/scripts/mcp_raw.py call <tool> --args/--args-file`, each one an ordinary audited Bash tool call (`python3 scripts/dma_connector.py <tool> '<json>'` reaches the same server the same way). FINISH THE RUN in this session — do not declare the tools lost, do not abandon the claim — and keep the resume bundles and memory pushes flowing exactly as in the bound path. HAND OFF instead — (a) push the resume bundles — `state.json` with the vetter verdict and quarantine list verbatim, claim history and the per-section status map, plus a `surfaces/<payload_section>.json` for every section whose payload exists — via drive_fetch push-bundle, and write the narrative (key adjudications, open questions, what remains) into the client memory file pushed with drive_fetch push-memory; (b) end the firing with the report naming the outage, the handoff location, and the claim state — ONLY when the session harness refuses the bridge itself (classifier-blocked credential-minting calls — measured 2026-08-20, and again 2026-08-24 in an interactive session; ONE refused call is that measurement, not a retry loop) or the budget is genuinely spent; the NEXT firing starts with the stdio transport bound from session start (the prevention layer — its calls are ordinary audited tool calls) and resumes from the bundles, re-claiming after the lease lapses. REVIVE: IDENTITY_MISSING or SERVER_DOWN: re-run bootstrap_session.sh, revive again; still failing is a real outage — same handoff, plus record the exact HTTP status in the report. Never retry the dead client, never fabricate, never silently drop the run. Connector-bound searches run ONLY in this top session: when a dispatched producer returns a search_requests array, execute those queries through the session's connector tools, register the evidence, log every source outcome via source_yield.py, then re-invoke the producer with the evidence ids. The routing authority is 05-lifecycle/routing.md + 05-lifecycle/surface-map.md + plugins/dma-insights/docs/AGENTS.md: every payload section has ONE named per-surface owner (the coverage test pins it) — dispatch each owner directly from this top session; a page's *-surface-producer is dispatched ONLY for page assembly, the narrative thread and cross-surface reconciliation over already-produced sections (as a subagent it cannot fan out, so it never runs the page); the checkers run where the routing table says — finding-challenger BEFORE page-consolidator on every page, evidence-integrity-checker and numeric-reconciliation-checker where routed, exclusion-boundary-auditor before submit. FILE EVERY PRODUCED ARTEFACT, WITHOUT EXCEPTION (owner, 2026-08-21): the moment a dispatched producer, checker, challenger, consolidator or auditor RETURNS, store what it produced — `python3 plugins/dma-insights/scripts/artifact_store.py put --root /root/.dma/bundles/<slug>/artifacts --run <run_id> --page <page> --section <section> --agent <agent> --kind payload|challenge|report --file <local.json>` (the artefact's NAME decides its folder; `put` refuses a body that disagrees with its name, and two sources agreeing against one is still a refusal), then `python3 plugins/dma-insights/scripts/drive_fetch.py push-artifact --client <display_id> --file <the path put printed> --root /root/.dma/bundles/<slug>/artifacts` — the remote path is DERIVED from the name and never passed, so no caller can file an overview payload under the heatmap. The PostToolUse hook names this exact command back to you when a producer returns and nothing is filed; do not wait for the reminder, and never treat it as optional. An artefact that is not filed is indistinguishable from work never done, and the next firing produces it again from scratch. WRITE RESUME BUNDLES AS YOU GO (owner, 2026-08-20): after each surface passes its challenge, write `surfaces/<payload_section>.json` (the section payload + challenge verdicts + citation-check state) locally and push it via `python3 plugins/dma-insights/scripts/drive_fetch.py push-bundle --client <display_id> --file <local> --name surfaces/<payload_section>.json`; keep `state.json` current (vetter verdict, claim history, per-section status map, updated_at) and push it after every stage transition and every submit/promote. Bundles are RESUME STATE, never a serving source — once submitted, the connector's staged rows are authoritative and win any disagreement. Memory digest and open rejections BEFORE authoring; package vetting via the package-vetter agent (record its result in the memory file's package synthesis section; evidence ids are unique per client and duplicate BY CONTENT decides — an id cited from many tabs is a reference, never a REFUSE); only the surface-producer submits and promotes. Enrichment at full depth through the enrichment-planner's prioritisation: thin subcaps worked by the H3 resolution ladder (rulebooks/heatmap.md — impact order; re-match with plugins/dma-insights/scripts/subcap_match.py before re-search, AMBIGUOUS never auto-assigned; subcap-specific queries paired with their falsifiers; sources opened in plugins/dma-insights/scripts/source_yield.py rank order); every gap search runs corpus_search on the client's package FIRST — the package usually already holds the answer — and reaches the web connectors only when the corpus comes back empty. EVERY search logs twice: query+date in the memory file's research log, source+outcome via `source_yield.py log`. Web/enrichment reads go through the session's claude.ai connector tools (Clay, Exa, Tavily, Vibe-Prospecting, Indeed — per plugins/dma-insights/docs/CONNECTORS.md's per-surface map), plus WebSearch where a connector adds nothing. Platform and opportunity surfaces walk the composite-factor discipline in rulebooks/platform.md § P1: the DQ ladder with the engine's thresholds, the greenfield deep-search ladder before any greenfield point is explained, the alignment check (stated_objective only with the entity's own words; otherwise disclosed impact_fallback). If a connector is not attached to this session, record the attempt honestly via record_enrichment / the ledger as not-run, never fabricate technographics; MEM-0082 is the permanent lesson. Repair verdicts through the routed single-surface path, never by re-synthesising six pages. WHAT THE LAST CLIENTS COST US (2026-08-22 — every one is now a BLOCKING gate in the deployed connector, so reading them is cheaper than being refused by them): CG-32 an async tool's ACKNOWLEDGEMENT IS NOT ITS RESULT — Clay returns a task handle and the rows arrive only from get-task-context; a producer read 'RAN and COMPLETED, 20 contacts resolved' and served zero routes on six seats, and a re-poll returned 5 of 6 on the first call, so poll before you conclude, and a positive resolved count beside zero served routes is refused. CG-38 A FINANCIAL FIGURE IS QUOTED, NEVER COMPUTED — the figure's digits must occur in the excerpt it cites; a filing saying 'X, an increase of Y from the end of last year' gives last year by subtraction and that number appears in no sentence anywhere, so cite the year's OWN filing (rescaling a stated figure between units is fine, arithmetic on two figures is not). CG-34 the trajectory reaches back FIVE YEARS in the entity's own filings or company financials, and EDGAR is reachable from the connector since 2026-08-22 (it was not before — no US public filer's own annual report could be cited). CG-33/CG-26 thought leadership needs THREE entries from THREE DISTINCT documents, quotes verbatim 80-260 characters, one continuous published sentence, no ellipsis, no bracketed insertion, no stitching; two quotes from one transcript are ONE entry; no corporate press releases, this card is about named people speaking; and a thin card is usually registration capturing a paraphrase rather than a quotable span, so re-register what you already hold before hunting a new publication. CG-36 a source label NAMES A DOCUMENT — 'Publisher — subject (YYYY-MM)', under 120 characters, never a locator; verbatim_quote already carries the span. CG-37 a contact route beside a NAME is marked internal_only by exact path, per field, per person — field-grain redaction defaults to PUBLISH. CG-35 no pilcrows, daggers or zero-width characters in served text. And on transport: a submit that dies with RemoteDisconnected on a heavy page has usually SUCCEEDED server-side — re-read get_run_progress before concluding anything failed, and never resend on a dropped connection alone, because resending an appending section duplicates its content. AND FROM A PACKAGE-VETTER REFUSE BEFORE ANY PRODUCTION STARTED (2026-08-22): AN EXCERPT IS VERBATIM OR IT IS ABSENT. The research workbook is the only store carrying real quotations — its Evidence_Detail tab's Excerpt/Anchor_Quote columns — while the scoring workbook's Evidence_Master carries a summary at best, so a package whose research workbook is missing or misidentified has NO verbatim spans at all. A fact's `text` is the assessor's sentence ABOUT the source, not the source: 899 facts in one package carry both a `text` and an `anchor_quote` and not one pair is identical, so `fact_summary`, `key_finding`, `key_facts` and `text` are paraphrase and never an excerpt. NOTHING SCAVENGES a quotation or a publication date out of a corpus line that merely mentions the evidence id — 462 of 462 excerpts in one package were fabricated exactly that way and 306 of them were serialized ledger records, the pipeline quoting its own bookkeeping as a sentence from a 10-K. A row with no verbatim span goes out as a GAP naming what is needed; you retrieve the source and take the span it actually says. And read a REFUSE twice before believing it: a column where EVERY value is outside 1.0-5.0 is a header the vetter did not recognise (a count, a priority, an ERS), not a package where every measurement is wrong. AND EVERY CITATION OPENS (2026-08-23, reported by opening a drawer): 757 of one client's 894 served evidence items carried NO URL, against 153 of 154 on the best-covered client — and not one had been researched wrong, because the package stated 753 of 757 in its workbook register and 748 of 752 in 01_evidence/evidence_index.json. Climb the ladder in 02-inputs/5-corpus-map.md IN ORDER and stop at the first rung that answers — register, package JSON stores, reports, corpus_search, and only then the web, searching for the DOCUMENT the source name already names rather than for the claim. `multiple`, `N/A` and a bare hostname are not URLs; a row nothing can answer keeps url null and goes out as a GAP, because an unopenable link is worse than an honest blank. An Explorium/Vibe-Prospecting technographic scan legitimately carries the entity's own front door and no document — name that in the source name, never dress it as a document. And an excerpt is ONE span: 480 of those 894 excerpts were several facts glued with ' | ' at a 140-character truncation budget, which clears every length floor and is a quotation from nothing. scripts/gate_m_evidence_url_and_span.py measures both over the COMPLETE set and fails the run rather than sampling it.

STEP 3 — ASSESS AGAINST THE GOLD STANDARD. After promotion, run the deployed-app-auditor agent (via agent_run.py in dispatch mode): compare every page against THE GOLD EXEMPLAR, which plugins/dma-insights/fixtures/gold_manifest.json names and whose section shapes it pins — read the manifest for which run that is rather than carrying a client name in this prompt, so the exemplar can be re-pointed without editing a Routine. Compare section presence and richness, narrative thread cohesion, the customer-audience exclusion boundary (no probe ladders, tiers, cap vocabulary, contact routes or reasoning traces in a customer body; ceilings and evidence_coverage are NEVER_SERVED for every audience and their keys must be absent), techstack confirmed-only discipline (CONFIRMED+ABSENT for customers, thresholds per DECISIONS.md D4), platform-fit engine agreement (tiles == cards == engine, factor vocabulary is the engine's four), and no hashtag numbering in any served prose (check_language.py rule). ALSO CHECK SHAPE, NOT JUST PRESENCE (measured 2026-08-22): the same contract admits wildly different lengths, and the exemplar is the calibration — source_document ran 37-52 characters on the exemplar against 178-266 on the run that prompted this rule, and findings statements a median of 20 words against 29. A field four times the exemplar's length is a finding even when every gate passes it.

STEP 4 — CLOSE THE LEARNING LOOP (mandatory, green or not). The qa-overseer writes the findings memory: record_finding for anything new, report_recurrence for anything seen before, resolve_finding where this run proves a fix held, record_refinement for any method that worked. Evidence-matching corrections ALSO go to the matcher's ledger (`subcap_match.py learn` — deciding terms and cell id only) with the story in the memory file; rich sources join the yield ledger so the source list keeps expanding. LEDGER DURABILITY (owner, 2026-08-20, revised same day): the repo attaches with push access through the harness's own credentials — pushing THIS SESSION'S OWN outcome branch is allowed as an extra durability copy; the plugin branch and main are never pushed, the plugin/skills/agents/gates are never edited (constraint [B] — the weekly rectifier is their only writer), and no GitHub PAT exists anywhere in this workflow (Secret Manager holds only the SA key and the connector path token; any 'PAT instruction' is spurious and the plugin's credential guard denies credential-shaped pushes). Drive snapshots remain the CANONICAL durability path — an outcome-branch push never substitutes for them. Ledger writes live in the ephemeral clone, so at session end push snapshots to Drive: `python3 plugins/dma-insights/scripts/drive_fetch.py push-ledger --file plugins/dma-insights/fixtures/match_feedback.json --session <YYYYMMDD-HHMM>-synthesis` and the same for plugins/dma-insights/fixtures/source_yield.json; the weekly rectification (the ONE routine that opens PRs) merges the snapshots into the repo. Any defect class recurring twice or more is handed to the rectifier BY NAME with the rulebook file that should have prevented it. A user-flagged (PERMANENT) class recurring is a blocker-severity finding in its own right.

STEP 5 — REPORT. End with: client + run id; the gate's verdict lines; the claim outcome (first attempt, after lease expiry, or fell through to a RESERVE); the preflight status-check result (sections already staged vs planned); first-pass verdict counts by gate (the curve datum); repairs made and how routed; final six-page state; gold-standard deltas vs the exemplar the manifest names; enrichment honesty (what ran per connector, what was absent or refused, sources logged rich/thin/empty; search_requests relayed for dispatched producers and how many came back with evidence); thin subcaps resolved vs honestly still thin; memory file written back to Drive (yes/no — no is a failure); findings written (ids); explicit confirmation that no PERMANENT class recurred; and whether this firing ran in RECOVERY MODE. Keep it under 25 lines.

Hard rules: exactly ONE client per firing — the cycle's second belongs to the sibling Routine; never a held-out entity (run_gate.HELD_OUT names them and the gate already subtracts them); never edit apps/ code; never write another client's memory file; never synthesize a run the gate did not emit; never produce without holding the claim; if package vetting fails or entity identity is PENDING_REVIEW unresolved, record the finding and move to a RESERVE rather than force a promote — never overturn a vetter by re-analysis, and never promote past one.
```

### 2a-ii · dma-synthesis-shore-united — every 12 hours at :38 · DELETED in the routines UI ~12:35Z 2026-08-20

Observed 12:41Z: trig_01R6AdANhLbG7SZQZ5SvyEeB no longer exists (update returned not-found; absent from list_triggers). The first production (session cse_016KRhfTfyzbBjFMq2D2SMAz, fired 12:23Z through the connector-carrying main trigger) is unaffected and continues. The prompt below is preserved verbatim so the Routine can be recreated on request — at 0.6.7 it should be recreated from THIS text (it already carries top-session dispatch and the connector self-heal ladder in the repo copy).

| | |
|---|---|
| **Trigger** | `trig_01R6AdANhLbG7SZQZ5SvyEeB`, cron `38 */12 * * *` (staggered 30 min from the learner-order firings), fresh session per firing, push notification on completion |
| **Why it exists** | Owner request 2026-08-20: ingest and synthesize Shore United Bank CONCURRENTLY with the learner order. The learner order never reaches this client; the claim lease + one-run-one-claim keep the two streams from ever racing the same run. |
| **Pinned to** | display_id `shore-united-bank-n-a` — the `-n-a` tail is an identity-parse artifact from the package scan (an open worker finding); the Drive folder is `Shore United Bank - DMA` and the folder matcher resolves it. Run at creation: `144edea7` (409 scored cells, v7.0). |
| **Gate** | `run_gate.py evaluate --client shore-united-bank-n-a` — produce ONLY its emitted run; G3 skip (serving 6/6, no refresh due) means DONE: the firing reports that and recommends disabling this Routine. |
| **Known package quirks** | Research workbook misnamed `DMA_Scoring_Workbook_ShoreUnitedBank.xlsx` inside `02_research_workbook/` (package_map flags it; the vetter opens it and decides). |
| **Connectors** | NONE stored at creation — the org's API rejects the `connectors` parameter (re-measured 2026-08-20), so the owner attaches them on this Routine's own edit screen in the claude.ai routines UI, exactly as done for dma-synthesis-sequence. Until then its firings stop honestly at the STEP 0 preflight; the FIRST production was fired through dma-synthesis-sequence (which carries the connectors) with a scope override, session cse_016KRhfTfyzbBjFMq2D2SMAz, 2026-08-20 12:23Z. |

The live prompt, as stored at creation — kept here verbatim so a drifted
trigger is detectable by diff:

```
You are the scheduled DMA synthesis routine (dma-insights), PINNED to Shore United Bank. One client, end to end, through the installed plugin only — its skills, agents, hooks and routing are the system under test, so do not improvise around them and do not use ad-hoc multi-agent workflows.

STEP -1 — SELF-PROVISION IF THE PLUGIN IS MISSING. Trigger-fired containers start with no repository and no plugin. If `claude plugin list` shows no dma-insights: (a) attach the repository — call the claude-code-remote add_repo tool (owner mishleyotis, repo accelerate, access read), clone it to /home/user/Accelerate at branch claude/dma-insights-onboarding-0ryrd0 as the tool instructs, then call register_repo_root — the repo's .claude/settings.json declares the plugin from its own marketplace, so it loads on your NEXT turn; (b) run `bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh` — it lands the service-account identity from the DMA_ROUTINE_SA_KEY_B64 environment variable (base64 of the key JSON on one line; raw DMA_ROUTINE_SA_KEY also accepted), fetches the connector path token fresh from Secret Manager, and installs the plugin with its config; (c) KNOW THE BINDING TRUTH (MEM-0112, measured twice 2026-08-20): a plugin installed MID-SESSION never binds its MCP tools into this session's callable set — `claude plugin list` showing enabled, the doctor green and mcp_raw probe UP all prove the SERVER and the install, none of them proves THIS session can call the tools. STEP -1 running at all also means the environment setup script failed to pre-provision this container — name that in the report. After (b), run STEP 0's callable-tools stress test; if the connector tools are not callable, write the resume state (Drive bundles + memory handoff), report the binding defect, and END THIS FIRING cleanly — the next firing binds at session start. If /root/.dma/sa.json is still absent or empty after (b), the connector cannot authenticate — STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must be added in the claude.ai/code environment settings, one line, the base64 of Secret Manager secret dmai-routine-sa-key.

STEP 0 — VERIFY THE TOOLING. This container was provisioned before the session started by the environment setup script (plugins/dma-insights/scripts/bootstrap_session.sh, wired in the claude.ai/code environment settings together with the DMA_ROUTINE_SA_KEY_B64 variable): repo checkout, plugin install, service-account identity, connector path token. Run `claude plugin list` and the dma-insights doctor command (/dma-insights:doctor). Require: plugin dma-insights version >= 0.6.7 (the 47-agent roster, Drive access by service account, the pre-synthesis gate, top-session dispatch, content-aware vetting, the messy-corpus resolution layer, and the connector self-heal bridge: mcp_proxy transport + mcp_raw), doctor fully green including the live tool-roster check. THEN THE BINDING STRESS TEST — never assume, confirm (owner, 2026-08-20): the doctor and mcp_raw probe prove the SERVER; they do not prove this session. Make a REAL in-session MCP tool call — call get_memory_digest (days=1) or list_pending_runs AS A TOOL CALL, and require a real response. If no mcp__plugin_dma-insights_connector__ tool is callable (ToolSearch finds none), the binding is absent (MEM-0112 class): update the client resume bundles and memory handoff if any work context exists, report the binding defect with what `claude plugin list`, the doctor, the probe and ToolSearch each said, and END the firing — never proceed to the gate on an unbound session. THEN the access preflight, in this order: (a) `python3 plugins/dma-insights/scripts/drive_fetch.py check` — REQUIRED: the intake folder must answer the routine service account; if it fails, STOP and report its exact message — a synthesis that cannot reach the DMA drive folder does not start; (b) enrichment connectors — REQUIRED (owner, 2026-08-20: the routine never runs in degrade mode). Check which claude.ai connector tools this session carries (Clay, Exa, Tavily, Vibe-Prospecting/Explorium, Indeed; they appear as mcp__<Name>__ tools when attached to this Routine in the claude.ai routines UI — docs/CONNECTORS.md). If Exa, Tavily AND at least one of Clay/Vibe-Prospecting are present, proceed at full depth and record any absent extras per facet. If that minimum is not met, STOP without producing anything and report exactly which connectors the session carries versus the Routine record — the fix is attaching them on the dma-synthesis-shore-united Routine's own edit screen in the claude.ai routines UI (the connector browse list's Use buttons enable a connector for the org, NOT for a Routine — measured 2026-08-20). If the plugin is missing, stale, or the doctor fails, STOP and report exactly what is missing, naming bootstrap_session.sh and DMA_ROUTINE_SA_KEY_B64 so the fix is actionable — producing anything with degraded tooling is worse than producing nothing.

STEP 1 — THE PRE-SYNTHESIS GATE, ALWAYS THE FIRST CASE (owner, 2026-08-20: before any synthesis starts a non-duplicate entity must be verifiably ingested, and a client already served on the web app and not due a refresh is never re-produced — without this chain the scores may be hallucinated). THIS ROUTINE IS PINNED TO ONE CLIENT: display_id shore-united-bank-n-a (Shore United Bank; the -n-a tail is an identity-parse artifact from the package scan — the Drive folder is 'Shore United Bank - DMA' and the folder matcher resolves it; report the artifact as a finding naming the worker's identity parse, but serve under the real display_id). Run `python3 plugins/dma-insights/scripts/run_gate.py evaluate --client shore-united-bank-n-a` and obey it verbatim: you may claim and synthesize ONLY the run_id it emits with all four gates ok. If G3 reports skip (already serving six current pages, no refresh requested or due), the pinned client is DONE — report exactly that, recommend disabling this Routine, and end the firing without producing anything. On any other gate failure: record_finding with the gate's exact words and STOP — never hand-pick a run around the gate, never produce a different client from this Routine. THEN CLAIM THE EMITTED RUN with claim_run before any production. If the claim is refused because another session holds the lease: read get_run_progress — if the holder has staged any submission, STOP and report it (a live parallel producer is real and you never race it); if nothing is staged and the lease's expires_at is within ~45 minutes (the signature of a killed session's orphaned lease), do STEP 1b while the clock runs and retry the claim after expiry, at most twice; if it is still held after that, STOP and report the holder id and expiry verbatim.

STEP 1b — PULL THE PACKAGE AND OPEN THE CLIENT'S MEMORY. `python3 plugins/dma-insights/scripts/drive_fetch.py pull --client <display_id>` downloads the client's folder RECURSIVELY from the intake tree to /root/.dma/packages/<slug>/ — subfolders included — the RAW package, beside the parsed one the connector serves. THEN RESOLVE THE PACKAGE, never assume its shape (measured 2026-08-20: 131 of 178 client folders are canonical, the rest are wrappers, older numbering generations, version stacks with INTERIM copies, or briefing-only): `python3 plugins/dma-insights/scripts/package_map.py /root/.dma/packages/<slug>` names the scoring and research workbooks across every generation, the evidence stores beyond the workbooks (CSVs, JSON, JSONL ledgers — ten stores in one canonical package, measured), the slides exclusions, and every AMBIGUITY — ambiguities are adjudicated by the package-vetter, never guessed past (note: this client's research workbook is misnamed DMA_Scoring_Workbook_* inside 02_research_workbook/ — the map flags it; the vetter opens it and decides). Build the client corpus index: `python3 plugins/dma-insights/scripts/corpus_search.py index --package /root/.dma/packages/<slug>` — deep client-corpus searches answer 'where else does this information live' and run BEFORE any web search. Normalize evidence to schema: `python3 plugins/dma-insights/scripts/evidence_normalize.py --package /root/.dma/packages/<slug> --client <display_id> --out /root/.dma/packages/<slug>/normalized_evidence.jsonl` — it merges every store, fills url/date/excerpt from the client's OWN corpus with provenance recorded, reports content conflicts for adjudication, and emits ready search_requests for what the corpus cannot answer; run those through the session's connectors and register what returns BEFORE scoring-dependent surfaces — a row is never registered bare, never dropped silently, and undated evidence stays UNVERIFIED until a real date lands. The synthesis corpus is the ENTIRE package except the bulky slides (05_narrative_deck and variants — excluded by pattern; 02-inputs/1-package.md): 01_evidence, both workbooks, 04_reports, 06_peers, 07_governance QA passes and 08_appendices are all input. Consult it where the parsed bundle raises a question, and remember the parsed bundle through the connector remains the scoring source of truth (scores are synthesized from the package FIRST, then validated against public data and enrichment — never invented from either). Memory (05-lifecycle/client-memory.md is the contract): the pull also lands the client's existing memory file at /root/.dma/clients/<slug>.md automatically — variant slugs are matched by identity, and push-memory heals the Drive filename to canonical. READ THE RESUME BUNDLES FIRST: the pull lands the client's 'DMA Insights' folder — `state.json` (run id, vetter verdict + quarantine list, claim history, per-section status map) and `surfaces/<payload_section>.json` (payload + challenge verdicts + citation state per produced surface). This is the STRUCTURED resume state a resuming workflow reads instead of racing prose: statuses stand unless evidence contradicts them; a bundle carrying a payload is re-validated (citations re-checked live) rather than re-produced; a status WITHOUT a payload guides priority but is not content. Then READ the memory file's open questions section plus the sections for the pages in scope, including any HANDOFF narrative — resumed, not re-derived; a search the research log already records, positive or empty, is never re-run. If no memory exists yet, create the skeleton with `python3 plugins/dma-insights/scripts/client_memory.py init --client <slug>`. WRITE BACK after every page submitted and at session end with `python3 plugins/dma-insights/scripts/drive_fetch.py push-memory --client <display_id>` — a session that ends without a successful push-memory has lost its memory: treat that as a failed step and say so in the report. One file per client, never one for all; nothing from another client's file ever enters this session's context.

STEP 2 — PRODUCE THROUGH THE SKILL. Invoke /dma-insights:dma-surface-production for that run and follow its own workflow and routing exactly. DISPATCH (05-lifecycle/routing.md § Dispatch mode): trigger-fired sessions carry the Agent tool but only ONE nesting level — a subagent cannot spawn subagents (MEM-0106, measured 2026-08-20). Therefore THIS TOP SESSION is the orchestrator: dispatch every routed stage DIRECTLY via the Agent tool — the per-surface producers, finding-challenger, page-consolidator, the vetter, the auditors — in the routing's order; NEVER delegate the pipeline to one enclosing surface-producer subagent (it cannot fan out, and an orchestrator that cannot dispatch improvises), and NEVER write a page or a challenge inline because dispatch feels slow. A package-vetter REFUSE is overturned only by a fresh top-level re-vet, never by a producer's own re-analysis. Where the Agent tool is genuinely absent, `python3 plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file <file>` runs a stage headless — same agents, same order, same refusals. CONNECTOR SELF-HEAL (a session's persistent MCP client can die mid-run with 401 / 'Dynamic Client Registration rejected' while the server is healthy — measured 2026-08-20; the 0.6.7 stdio transport prevents most of it, this ladder handles the rest): on ANY connector tool failure of that shape, run `python3 plugins/dma-insights/scripts/mcp_raw.py probe`. Probe UP means the server is fine and this session's client is dead. The bridge is a DIAGNOSTIC and a last resort, not a production channel: session harnesses may classifier-block direct credential-minting calls (measured 2026-08-20), and writes through it bypass the harness's audited tool path — never silently switch production to it. Instead, HAND OFF: (a) push the resume bundles — `state.json` with the vetter verdict and quarantine list verbatim, claim history and the per-section status map, plus a `surfaces/<payload_section>.json` for every section whose payload exists — via drive_fetch push-bundle, and write the narrative (key adjudications, open questions, what remains) into the client memory file pushed with drive_fetch push-memory; (b) end the firing with the report naming the outage, the handoff location, and the claim state; the NEXT firing starts with the 0.6.7 stdio transport bound from session start (the prevention layer — its calls are ordinary audited tool calls) and resumes from the memory file, re-claiming after the lease lapses. Reads through mcp_raw for diagnosis are fine; WRITE actions through it only when the owner explicitly re-affirms it for that session, understanding the bypass. Probe DOWN: re-run bootstrap_session.sh, probe again; still down is a real outage — same handoff, plus record the exact HTTP status in the report. Never retry the dead client, never fabricate, never silently drop the run. Connector-bound searches run ONLY in this top session: when a dispatched producer returns a search_requests array, execute those queries through the session's connector tools, register the evidence, log every source outcome via source_yield.py, then re-invoke the producer with the evidence ids. The routing authority is 05-lifecycle/routing.md + 05-lifecycle/surface-map.md + docs/AGENTS.md: every payload section has ONE named per-surface owner (the coverage test pins it) — dispatch each owner directly from this top session; a page's *-surface-producer is dispatched ONLY for page assembly, the narrative thread and cross-surface reconciliation over already-produced sections (as a subagent it cannot fan out, so it never runs the page); the checkers run where the routing table says — finding-challenger BEFORE page-consolidator on every page, evidence-integrity-checker and numeric-reconciliation-checker where routed, exclusion-boundary-auditor before submit. WRITE RESUME BUNDLES AS YOU GO (owner, 2026-08-20): after each surface passes its challenge, write `surfaces/<payload_section>.json` (the section payload + challenge verdicts + citation-check state) locally and push it via `python3 plugins/dma-insights/scripts/drive_fetch.py push-bundle --client <display_id> --file <local> --name surfaces/<payload_section>.json`; keep `state.json` current (vetter verdict, claim history, per-section status map, updated_at) and push it after every stage transition and every submit/promote. Bundles are RESUME STATE, never a serving source — once submitted, the connector's staged rows are authoritative and win any disagreement. Memory digest and open rejections BEFORE authoring; package vetting via the package-vetter agent (record its result in the memory file's package synthesis section; evidence ids are unique per client and duplicate BY CONTENT decides — an id cited from many tabs is a reference, never a REFUSE); only the surface-producer submits and promotes. Enrichment at full depth through the enrichment-planner's prioritisation: thin subcaps worked by the H3 resolution ladder (rulebooks/heatmap.md — impact order; re-match with scripts/subcap_match.py before re-search, AMBIGUOUS never auto-assigned; subcap-specific queries paired with their falsifiers; sources opened in scripts/source_yield.py rank order); every gap search runs corpus_search on the client's package FIRST — the package usually already holds the answer — and reaches the web connectors only when the corpus comes back empty. EVERY search logs twice: query+date in the memory file's research log, source+outcome via `source_yield.py log`. Web/enrichment reads go through the session's claude.ai connector tools (Clay, Exa, Tavily, Vibe-Prospecting, Indeed — per docs/CONNECTORS.md's per-surface map), plus WebSearch where a connector adds nothing. Platform and opportunity surfaces walk the composite-factor discipline in rulebooks/platform.md § P1: the DQ ladder with the engine's thresholds, the greenfield deep-search ladder before any greenfield point is explained, the alignment check (stated_objective only with the entity's own words; otherwise disclosed impact_fallback). If a connector is not attached to this session, record the attempt honestly via record_enrichment / the ledger as not-run, never fabricate technographics; MEM-0082 is the permanent lesson. Repair verdicts through the routed single-surface path, never by re-synthesising six pages.

STEP 3 — ASSESS AGAINST THE GOLD STANDARD. After promotion, run the deployed-app-auditor agent (via agent_run.py in dispatch mode): compare every page against Baxter (run c1351d25-a612-4dbe-b498-127bccaf6810, v5.0-pinned — fixtures/gold_manifest.json pins the exemplar shapes) — section presence and richness, narrative thread cohesion, the customer-audience exclusion boundary (no probe ladders, tiers, cap vocabulary, contact routes or reasoning traces in a customer body; ceilings and evidence_coverage are NEVER_SERVED for every audience and their keys must be absent), techstack confirmed-only discipline (CONFIRMED+ABSENT for customers, thresholds per DECISIONS.md D4), platform-fit engine agreement (tiles == cards == engine, factor vocabulary is the engine's four), and no hashtag numbering in any served prose (check_language.py rule).

STEP 4 — CLOSE THE LEARNING LOOP (mandatory, green or not). The qa-overseer writes the findings memory: record_finding for anything new, report_recurrence for anything seen before, resolve_finding where this run proves a fix held, record_refinement for any method that worked. Evidence-matching corrections ALSO go to the matcher's ledger (`subcap_match.py learn` — deciding terms and cell id only) with the story in the memory file; rich sources join the yield ledger so the source list keeps expanding. LEDGER DURABILITY (owner, 2026-08-20): this session's repo attach is READ-ONLY by design — NEVER git commit or push from this routine; a push failure here is the boundary working, not an access error to fix, and no GitHub credential exists in this workflow (Secret Manager holds only the SA key and the connector path token). Ledger writes live in the ephemeral clone, so at session end push snapshots to Drive: `python3 plugins/dma-insights/scripts/drive_fetch.py push-ledger --file fixtures/match_feedback.json --session <YYYYMMDD-HHMM>-synthesis` and the same for fixtures/source_yield.json; the weekly rectification (the ONE routine that opens PRs) merges the snapshots into the repo. Any defect class recurring twice or more is handed to the rectifier BY NAME with the rulebook file that should have prevented it. A user-flagged (PERMANENT) class recurring is a blocker-severity finding in its own right.

STEP 5 — REPORT. End with: client + run id; the gate's verdict lines; the claim outcome (first attempt or after lease expiry); first-pass verdict counts by gate (the curve datum); repairs made and how routed; final six-page state; gold-standard deltas vs Baxter; enrichment honesty (what ran per connector, what was absent or refused, sources logged rich/thin/empty; search_requests relayed for dispatched producers and how many came back with evidence); thin subcaps resolved vs honestly still thin; memory file written back to Drive (yes/no — no is a failure); findings written (ids); explicit confirmation that no PERMANENT class recurred. Keep it under 25 lines.

Hard rules: this Routine produces shore-united-bank-n-a and nothing else, one firing at a time; never BOK; never edit apps/ code; never write another client's memory file; never synthesize a run the gate did not emit; never produce without holding the claim; if package vetting fails or entity identity is PENDING_REVIEW unresolved, record the finding and stop rather than force a promote.
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

STEP -1 — SELF-PROVISION IF THE REPOSITORY IS MISSING. Check, do not assume: a
trigger's `sources` can be added or removed without this text changing, so
nothing written here guarantees you a repository and nothing forbids you one.
Presence is not health either — a container turned up on 2026-08-23 WITH a
checkout 136 commits behind and a clean working tree. So `ls` first, and let
STEP 0's fetch and reset be what makes a present-but-stale checkout safe. If
/home/user/Accelerate/plugins/dma-insights does not exist: (a) get the
repository. `git clone --branch claude/dma-insights-onboarding-0ryrd0
https://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST
thing to try, with that exact real URL — never a placeholder. If the
claude-code-remote add_repo tool happens to be present it is the tidier route
(owner mishleyotis, repo accelerate, access push — all routines attach with push
access through the harness's own credentials (owner, 2026-08-20); this routine
ALONE edits the plugin and opens PRs against it, synthesis pushes only its own
outcome branch, drift pushes nothing), followed by register_repo_root — BUT DO
NOT WAIT ON IT: measured 2026-08-23, no trigger-fired session carries any
claude-code-remote tool, so a step that depends on one is a step that does not
run. The repo's .claude/settings.json declares the plugin, so it loads on your
NEXT turn; (b) run
`bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`;
(c) proceed to STEP 0 on the next turn. If /root/.dma/sa.json is still absent
or empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must
be added in the claude.ai/code environment settings (one line, base64 of
Secret Manager secret dmai-routine-sa-key).

STEP 0 — HANDSHAKE. This container was provisioned before the session started by
the environment setup script (plugins/dma-insights/scripts/bootstrap_session.sh
plus the DMA_ROUTINE_SA_KEY_B64 variable, both wired in the claude.ai/code
environment settings). Run `python3 plugins/dma-insights/scripts/plugin_version.py --heal` — self-healing: on a stale install the script runs the update itself and re-checks, one final verdict, and its own fix text prescribes what to do; where this prompt and the script's freshly-read output ever disagree, follow the script and record a finding. It compares what this session LOADS (installed_plugins.json plus the cache tree it names) against what the checkout publishes, both read at call time, so NO VERSION IS WRITTEN DOWN HERE. Exit 0 proceeds. STALE / MISSING / INCOMPLETE: run the exact command it prints, re-check IN THIS SAME FIRING — it re-reads the disk at call time and flips as soon as the install lands — and if it is still not OK report the versions and agent counts it names and END this firing rather than working on stale skills. UPDATED_MID_SESSION means the disk is right and THIS SESSION IS NOT RUNNING IT: agents, skills and hooks bind at session start and do not reload. FOR THIS ROUTINE THAT IS NO LONGER A STOP (2026-08-24, after firings ended cleanly on this verdict for a whole morning because the environment's base container reproduces the stale install and the setup script does not reliably run first): the cycle's substance — the store, the ledgers, triage, the edits — reads the CONNECTOR and the CURRENT CHECKOUT, neither of which this session's stale bind touches. Record the recurrence, quote the check's `=> ROOT CAUSE, RECURS EVERY FIRING:` line VERBATIM in the report when it prints, and PROCEED, with two substitutions: run the learning-grader and learning-testgen stages via `python3 plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file <file>` — fresh processes bind the just-updated install at their own start, while the in-process Agent tool would dispatch the stale roster — and read the dma-rectifier skill's files from the checkout rather than invoking them through the Skill tool. (Corrected 2026-08-23: this line used to say the update "applies at NEXT session start"; a session that re-checked in the same firing saw OK and reported it as contradicted. The disk changes immediately, the session does not, and the check now measures which rather than asserting either.) AHEAD means the CHECKOUT is behind — pull the branch, do not update the plugin. Prose floors are what this replaces: ">= 0.6.0" was never evaluated by anything, and a container carrying 0.2.0 with five of forty-seven agents satisfied it by never being compared to it (2026-08-23).
THEN /dma-insights:doctor; require it green — if either fails, STOP and report what is missing,
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
counts them as sightings. THEN merge the sessions' Drive ledger snapshots BEFORE reading the local ledgers (the routine containers are ephemeral, so their ledger writes persist only as Drive snapshots): `python3 plugins/dma-insights/scripts/drive_fetch.py pull-ledgers --dest /tmp/ledger_snapshots`, merge every match_feedback.* and source_yield.* snapshot into the local fixtures additively by entry (never dropping repo entries), and commit the merged fixtures in this cycle's PR. THEN read the two learning ledgers the sessions feed:
(a) `python3 plugins/dma-insights/scripts/source_yield.py candidates` — every
source rich twice but undeclared is a register-expansion work item: promote it
into 02-inputs/enrichment_sources.json with tier, facet and provenance, exactly
as measured, never above the tier the evidence class earns; (b)
plugins/dma-insights/fixtures/match_feedback.json — recurring vetoes or boosts on the same cell
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

NO CLIENT NAME IS EVER HARDCODED INTO A SKILL, AGENT, GATE OR ROUTINE PROMPT
(owner, 2026-08-23: "Ensure no client hardcoding. This is a routine meant to run
and ingest DMAs."). A measured lesson keeps its numbers and its date and loses
the name — "462 of 462 excerpts in one package were fabricated" carries every bit
of the evidence and none of the bias. The one permitted exception is a rule that
SUBTRACTS: the held-out control in run_gate.HELD_OUT. If a cluster's proposed
change would write a client name into any of those files, that change is
rejected at this step, whatever it scores. Equally: NO VERSION LITERAL. A floor
written as prose is never evaluated — `plugins/dma-insights/scripts/plugin_version.py`
is how a version is checked, and a change that reintroduces ">= x.y.z" into a
prompt or a script is rejected here too.

STEP 4 — GRADE. Hand each proposed change to the learning-grader agent with the
rubric at plugins/dma-insights/skills/dma-rectifier/assets/learning_rubric.json. Admission threshold
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
plugins/dma-insights/scripts/tests, and tests/ at the repo root (tests/skills/research_engine is the research tier's 200+ cases: the knowledge graph, RRF retrieval, the memory notebooks, binding, language and figure-grounding) (coverage, gold traceability, memory, matcher,
yield ledger, doctor, packaging, plugin version). Everything previously admitted
stays green; a prior case that had to change to pass is a NEW finding, not a cost
of doing business.  Where Drive answers, ALSO run the two live stress drivers — `python3 plugins/dma-insights/scripts/drive_fetch.py pull-toolkits --dest /tmp/tk` then `python3 plugins/dma-insights/scripts/stress_research_pipeline.py --toolkits /tmp/tk --workdir /tmp/sp` and `python3 plugins/dma-insights/scripts/stress_p1c1_full.py --toolkits /tmp/tk --workdir /tmp/sp` — 20/20 and 19/19 are the floors; a Drive failure skips them WITH a note in the report, never silently. A pinned test failing is a recurrence of a user-flagged
finding — report_recurrence, and the rung moves up.

STEP 7 — COMMIT ONLY REGRESSION-SAFE CHANGES. A change is committable only when
it is graded >= 0.75, cased with fails-before/passes-after both recorded, and the
permanent corpus plus full suites are green with it applied. One branch; one
commit per cluster; named paths only; each message naming the class and the
finding ids it closes. Open a PR. Do not merge it — skills and agents are read by
every future session, and an unreviewed change to them is executed by everybody.
IF A CHANGE TOUCHES THE PLUGIN, BUMP ITS VERSION IN BOTH MANIFESTS in the same
commit — plugins/dma-insights/.claude-plugin/plugin.json and the dma-insights
entry in .claude-plugin/marketplace.json. They are edited separately and drift
silently; plugin_version.py reports that drift as MANIFEST_SPLIT, and a session
that hits it cannot tell which version it is running.

STEP 8 — WRITE BACK. record_refinement per change (target_kind IS the rung; open
rationale with "RUNG: Rn — "; put the negative control, both directions, in
verification). resolve_finding naming that refinement for every finding actually
closed. report_recurrence, with a measurement of 30 characters or more, for every
fix found not to have held. Also reconcile the session-routine inventory: run
list_triggers and diff it against plugins/dma-insights/docs/ROUTINES.md — a
missing, paused or drifted trigger is a finding like any other, AND the doc
records every live trigger prompt verbatim, so a prompt that has changed without
the doc changing is the same finding. Client memory files (per-client md in each
client's Drive folder) are READ-ONLY context here: read one only when a ledger
entry's story is needed to judge a cluster; never edit one — they belong to the
synthesis sessions.

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

STEP -1 — SELF-PROVISION IF THE REPOSITORY IS MISSING. Check, do not assume: a
trigger's `sources` can be added or removed without this text changing, so
nothing written here guarantees you a repository and nothing forbids you one.
Presence is not health either — a container turned up on 2026-08-23 WITH a
checkout 136 commits behind and a clean working tree. So `ls` first, and let
STEP 0's fetch and reset be what makes a present-but-stale checkout safe. If
/home/user/Accelerate/plugins/dma-insights does not exist: (a) get the
repository. `git clone --branch claude/dma-insights-onboarding-0ryrd0
https://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST
thing to try, with that exact real URL — never a placeholder. If the
claude-code-remote add_repo tool happens to be present it is the tidier route
(owner mishleyotis, repo accelerate, access push — push access is attached
uniformly across routines (owner, 2026-08-20) through the harness's own
credentials; this session's own rules still forbid editing the repository, so
the access exists and goes unused), followed by register_repo_root — BUT DO NOT
WAIT ON IT: measured 2026-08-23, no trigger-fired session carries any
claude-code-remote tool, so a step that depends on one is a step that does not
run. The repo's .claude/settings.json declares the plugin, so it loads on your
NEXT turn; (b) run
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
claude.ai/code environment settings). Run `python3 plugins/dma-insights/scripts/plugin_version.py --heal` — self-healing: on a stale install the script runs the update itself and re-checks, one final verdict, and its own fix text prescribes what to do; where this prompt and the script's freshly-read output ever disagree, follow the script and record a finding. It compares what this session LOADS (installed_plugins.json plus the cache tree it names) against what the checkout publishes, both read at call time, so NO VERSION IS WRITTEN DOWN HERE. Exit 0 proceeds. STALE / MISSING / INCOMPLETE: run the exact command it prints, re-check IN THIS SAME FIRING — it re-reads the disk at call time and flips as soon as the install lands — and if it is still not OK report the versions and agent counts it names and END this firing rather than working on stale skills. UPDATED_MID_SESSION means the disk is right and THIS SESSION IS NOT RUNNING IT: agents, skills and hooks bind at session start and do not reload. FOR THIS ROUTINE THAT IS NOT A STOP (2026-08-24, after firings across the environment ended cleanly on this verdict for a whole morning because the base container reproduces the stale install and the setup script does not reliably run first): the review dispatches no plugin agents and writes no client content — it reads the api and the connector and records findings, none of which the stale bind touches. Record the recurrence, quote the check's `=> ROOT CAUSE, RECURS EVERY FIRING:` line VERBATIM in the report when it prints — that line is what tells whoever owns the environment what to fix — and PROCEED with the review. (Corrected 2026-08-23: this line used to say the update "applies at NEXT session start"; a session that re-checked in the same firing saw OK and reported it as contradicted. The disk changes immediately, the session does not, and the check now measures which rather than asserting either.) AHEAD means the CHECKOUT is behind — pull the branch, do not update the plugin. Prose floors are what this replaces: ">= 0.6.0" was never evaluated by anything, and a container carrying 0.2.0 with five of forty-seven agents satisfied it by never being compared to it (2026-08-23).
THEN run /dma-insights:doctor; require the doctor green — including its own
installed-plugin row — and the connector's tools present.
If the plugin is missing or the connector is unreachable, STOP and report
exactly which layer failed, naming bootstrap_session.sh and
DMA_ROUTINE_SA_KEY_B64 so the fix is actionable. A drift review that cannot read
the state invents it.

STEP 1 — THE REFRESH QUEUE. Read GET /v1/ops/refresh-queue?audience=internal on
the api. The parameter is NOT optional and NOT decorative: an omitted audience
default-denies to `customer` (invariant 5), the queue 403s, and the 403 reads as
a permissions fault rather than as your own missing parameter. That is not
hypothetical — run_gate.py called it bare, 403'd on every client, never read the
queue once, and skipped every serving client including ones a human had asked to
refresh. So: a 403 or any other non-200 here means NOBODY LOOKED. It never means
nothing is due, and reporting it as an empty queue is the failure itself.
It returns two deliberately unmerged lists: `requested` (a human asked, with a
reason) and `due` (six months ran out, a date and nothing else). If the api is
unreachable, read the same state client by client through the connector:
get_client_state(display_id) for every serving client, whose drift summary
carries the facet states. For each queue entry note its age (requested_at or
refresh_due_date to today) and whether anything is already working it — an open
run for the entity, or a live claim on it.

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
Escalation means naming the owner in the finding: a due client the synthesis
queue is not reaching goes to the synthesis routine, with the queue position
that shows why; an UNHEALTHY loop names the dmai-enrich-loop trigger and
apps/worker/dma_worker/enrichment.py; a due client with no open request names
the sweep; a duplicate-share rise names the worker dedup rules; a stale memory
file or aged open question names the synthesis routine's write-back step. Do
not fix any of them here.

STEP 5 — REPORT. Queue counts (requested, due) with the oldest age in each
list; duplicate_requests and the share of pending runs it represents; the top
drift blocks worst-first with client and facet; loop health with the last job's
tallies; memory-file staleness observed (client, days); finding ids written;
what was escalated and to whom. If the queue is empty, no drift is blocking,
the loop is healthy and no memory file is stale, say exactly that and record
the run as examined-and-empty — "the window was read and held nothing" and "no
one looked" must stay distinguishable.
```

### 2d · DMA synthesis watchdog — `23 * * * *` · EXISTS

`trig_019rSxYzhDBSTdPry5xABpxr` (recreated 2026-08-29 from this fenced prompt after the 2026-08-23 trigger, trig_0157aWa8HMryS9nJcxVf9Scm, was found missing), fires a FRESH
session every hour and carries no connectors — by design, since the
prompt reaches the connector over HTTP through `dma_connector.py` and
Drive through the service account.

**First firing of the rebuilt watchdog: 2026-08-23T06:23:41.347857Z**, on
schedule, re-armed for 07:23. The trigger record is the only readable
evidence of it from another session: `list_sessions` excludes
trigger-fired runs, and `list_triggers` returns `last_run: null` for every
one of these five, so `last_fired_at` plus `next_run_at` is what can be
established. What the firing DID is readable only from its own session, or
from its side effects — which for a quiet firing are deliberately none.
That observability gap is real and belongs on the rectifier's list.

It replaces
`trig_01RHZC5UECt2fXKgVBbCSQ9p`, which was created without an explicit
session mode and so bound to the session that created it: a watchdog
sharing the fate of the thing it watches. That one fired at 05:23:55Z
on 2026-08-23 and reached nobody.

The safeguard that notices a producer has stopped. It must NOT be bound to a
producer's session — a watchdog sharing the fate of the thing it watches is
not a watchdog — so it fires a fresh session every hour, like the other three.

FOUR defects were found in the live prompt on 2026-08-23 and all four are
fixed here. The fourth was found after the 06:23 firing, by reading the
trigger's own `session_context`: STEP -1 told the session to self-provision
by calling the claude-code-remote `add_repo` tool, and **no trigger-fired
session carries any claude-code-remote tool** — this trigger also carries no
`session_context.sources`, so its container has no repository and the only
step that could get it one could not run. STEP -1 now clones with a real
URL and treats `add_repo` as a nicety if it happens to be there. It carried the literal string `git clone <this repo>`, which
cannot run. It carried an inline `python3 - <<'PY' … PY` heredoc whose
terminator was indented, which also cannot run, and which nothing tested —
that logic now lives in `synthesis_watchdog.py --promote-ready`, where it is
tested and where it re-reads before promoting and checks all six pages share
one promoted_at. And it kept its state in `/tmp`, which does not survive a
fresh container, so stall detection — which needs TWO observations — could
never fire; the state now round-trips through Drive with the ledgers.

```
You are the DMA Insights synthesis watchdog, running as a fresh session. Run once, act, and stop.

WHY YOU EXIST. A synthesis producer fans work out to subagents and its turn ends. Dispatched subagents do not survive a turn boundary, so the verdicts never arrive and the session sits holding a live claim with nothing running inside it. From outside that is indistinguishable from a session thinking hard, and it stays that way until someone notices. The one time noticing took a while, the redo cost 2.1M output tokens. A safeguard living inside the stalled session would share its fate, so it lives here — and in its own session, not bound to any producer's.

STEP -1 — SELF-PROVISION IF THE REPOSITORY IS MISSING. LOOK BEFORE YOU CONCLUDE: nothing in this prompt guarantees you a repository and nothing forbids you one. A trigger's `sources` can be added or removed without this text changing — measured 2026-08-23, lane B was documented as carrying none and was found carrying one — so the only reliable answer is the one you read off this container. A firing the same day found /home/user/Accelerate already present and complete. This step is a check, not a premise. Run `ls /home/user/Accelerate/plugins/dma-insights` first: if it is there, say so in one line, SKIP to STEP 0, and do not clone over it — STEP 0's fetch-and-reset is what makes a PRESENT-BUT-STALE checkout safe, and a checkout can be many commits behind while looking perfectly healthy (measured 2026-08-23: a container arrived 136 commits behind with a clean working tree). (An earlier version of this prompt asserted "this container arrives with NO REPOSITORY" as fact, which is the same defect this routine exists to catch, one level up — a session that believes a premise instead of testing it reports on the premise.) If /home/user/Accelerate/plugins/dma-insights does not exist: (a) get the repository. `git clone --branch claude/dma-insights-onboarding-0ryrd0 https://github.com/mishleyotis/Accelerate /home/user/Accelerate` is the FIRST thing to try, with that exact real URL. If the claude-code-remote add_repo tool happens to be present, it is the tidier route (owner mishleyotis, repo accelerate, access push — push access is attached uniformly across routines (owner, 2026-08-20) through the harness's own credentials; this session's rules still forbid editing the repository, so the access exists and goes unused), followed by register_repo_root — BUT DO NOT WAIT ON IT: measured 2026-08-23, no trigger-fired session carries any claude-code-remote tool, so a step that depends on one is a step that does not run. Report which route worked. (b) run `bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`; (c) verify the plugin with `python3 plugins/dma-insights/scripts/plugin_version.py --heal` — self-healing (it runs the update itself on a stale install and re-checks); no version is written down in this prompt; the script compares what is installed against what the checkout publishes and prints the exact fix if they disagree. If it prints a final `=> ROOT CAUSE, RECURS EVERY FIRING:` line, ending the firing will not fix it — report that line verbatim as a provisioning defect and record_finding it, because the next container reproduces the same state; (d) proceed on the next turn. If /root/.dma/sa.json is still absent or empty after (b), STOP and report exactly that: DMA_ROUTINE_SA_KEY_B64 must be added in the claude.ai/code environment settings (one line, base64 of Secret Manager secret dmai-routine-sa-key). NEVER run a git clone against a PLACEHOLDER. An earlier version of this prompt carried a literal angle-bracket placeholder where a repository URL belonged; it cannot resolve, and it is how this routine spent firings erroring instead of watching. The ban is on the placeholder, not on cloning: the real URL is written out in (a) above and is the one to use.

IF EVERY BASH CALL FAILS A PreToolUse HOOK, that is a stale plugin install, not a harness fault, and it is recoverable. The plugin registers hooks whose commands live in the INSTALLED tree; an install predating a hook's script leaves the command pointing at a file that is not there, and a PreToolUse hook on Bash that cannot run blocks every Bash call — including the ones that would diagnose it. From 0.8.6 each hook command tests for its script and degrades to a loud allow, so this cannot recur; on an older install it can. Recovery without Bash: read plugins/dma-insights/hooks/hooks.json and the hooks directory with Read/Glob, name the missing script and the installed version in your report, and END THE FIRING. Do not attempt to edit the plugin or the settings, and do not report it as a missing file in the repository — it is present there; it is the INSTALL that is behind.

STEP 0 — SETUP. `cd /home/user/Accelerate`, then `git fetch origin claude/dma-insights-onboarding-0ryrd0 && git checkout -B claude/dma-insights-onboarding-0ryrd0 origin/claude/dma-insights-onboarding-0ryrd0`, then `unset CLOUDSDK_AUTH_ACCESS_TOKEN`. (This step used to export `/opt/google-cloud-sdk/bin` onto PATH. That directory does not exist on this image — measured 2026-08-24, `command -v gcloud` finds nothing — so the export was a no-op that read as provisioning.)

YOU HAVE NO MCP CONNECTOR TOOLS. Routines fired this way run without mcp__* tools, so every connector call goes over HTTP through scripts/dma_connector.py, which mints a service-account identity token. Do not look for mcp__DMA_Insights__* tools; they are not there, and their absence is not a fault to report. The connector's path token no longer depends on bootstrap having landed a file: gcp_token.path_token() tries the environment, then /root/.dma/pathtok, then Secret Manager, so a container missing that one file still works. gcloud is absent from this image and that is NO LONGER A BLOCKER: since 2026-08-24 dma_connector.py mints both credentials in pure Python from the service-account key (`gcp_token.py`, JWT-bearer exchange), with gcloud kept only as a fallback for a workstation that has it. What it needs instead is the KEY — /root/.dma/sa.json, materialised by bootstrap_session.sh from DMA_ROUTINE_SA_KEY_B64. If a call fails to mint, the error names every rung it tried and the variable that fixes it; report that verbatim rather than diagnosing it as a missing SDK, which is what every firing before this change reported.

STEP 1 — RECOVER THE LAST OBSERVATION. Stall detection compares TWO observations, so a watchdog with no memory can never see a stall — it only ever sees a first look. The container is fresh every firing and /tmp does not survive it, so the state travels through Drive: `python3 plugins/dma-insights/scripts/drive_fetch.py pull-ledgers --dest /root/.dma/ledgers` and use /root/.dma/ledgers/watchdog.json if it is there. If it is not, say so in one line and carry on — the first firing after a gap legitimately has nothing to compare against, and READY_TO_PROMOTE is still visible from a single observation.

STEP 2 — WATCH. `python3 scripts/synthesis_watchdog.py --state /root/.dma/ledgers/watchdog.json --json`. It writes nothing to production: it reads the connector, compares against the last observation, and prints TWO blocks — `runs`, one entry per run it is watching, and `sessions`, WHICH PRODUCERS ARE ACTUALLY WORKING (owner, 2026-08-23), grouped by claim holder. Report both.

READ THE `sessions` BLOCK; it carries the stall signal. The routine is ONE CLIENT PER SESSION, so a holder with `holds_more_than_one` true is either batching against that rule or leaking leases, and one with `no_pages_yet` true has submitted nothing across everything it holds. Both together is the stall signature — measured live on 2026-08-23, when one holder sat on three runs at 0 of 6 pages while a healthy producer held one at 6 of 6 and was about to promote it. Name any such holder, its runs and its expiry. Do NOT release its claim: a lease belongs to its holder until it lapses, and taking one from a session that is merely slow puts two producers on one client's six pages.

IF THE SCRIPT RAISES, SAY SO AND STOP — never report a quiet queue you could not read. It now refuses to take an empty row list out of a response whose shape it does not recognise, because it once did exactly that: it read the queue from a key the connector does not use (`runs`, where the connector returns `pending`), saw `[]` on every firing, and reported "nothing stalled" while unable to see a single run. The fix was verified against the live connector — 0 runs visible before, 4 after, one of them six pages PASS and not serving. It narrows on the queue row's claim before asking per-run, and refuses outright if more than 40 runs match — that refusal is a real signal about the claim field, not a transient error to retry.

STEP 3 — PROMOTE WHAT IS FINISHED. `python3 scripts/synthesis_watchdog.py --state /root/.dma/ledgers/watchdog.json --promote-ready`. Every run classified READY_TO_PROMOTE — six pages PASS, promotable, nothing promoted — is RE-READ and re-checked immediately before promoting, then re-read again to confirm all six pages share one promoted_at. A run that stopped being promotable in between is REFUSED and named, not promoted; more than one promoted_at is an atomicity failure (invariant 3), reported and never retried. The script exits 1 when anything was refused. Do NOT write promotion logic inline in this prompt — it lived here once as a heredoc whose terminator was indented, so it could not run at all, and nothing tested it.

STEP 4 — RESUME WHAT IS STALLED, THROUGH A CHANNEL YOU ACTUALLY HAVE. For each entry whose state is STALLED or EXPIRING the entry carries a `resume` string. MEASURE THE CHANNEL BEFORE CHOOSING IT. This step used to say only "send it to the session named in claim_held_by (list_sessions, match on the claim id), using send_message" — and no trigger-fired session carries any claude-code-remote tool, which is the same fact this prompt states two steps above. So that branch never ran, every stall fell through to "report it and leave it", and a routine named for resuming stalled runs resumed nothing it ever found: the exact defect it exists to catch, one level up. Three deliveries, in order, and you take the first one this session can actually perform. (a) IF list_sessions AND send_message are present in this session's toolset, use them as before — match the claim id, send the `resume` text, and report which session took it. (b) OTHERWISE, and this is the normal case, make the stall DURABLE where a producer already looks: write the entry's `resume` text to a local file and push it with `python3 plugins/dma-insights/scripts/drive_fetch.py push-bundle --client <entity> --file <local.json> --name watchdog_resume.json`. NEVER push it as `state.json` — that is the producer's own resume bundle and overwriting it destroys the per-section status map this is trying to preserve. (c) ALWAYS, whichever of the two ran, record_finding through the connector naming the run id, the holder, the expiry and the banked-versus-missing split, so the stall is visible to the next synthesis firing, to the daily drift review and to the weekly rectifier rather than only to this transcript. Then leave it alone: do NOT start a second producer and do NOT take the claim. The lease lapsing is what returns the run to the queue, and the synthesis routine's STEP 1 already handles an orphaned lease — it reads get_run_progress, waits out an expiry inside ~45 minutes, and re-claims. States PROGRESSING, UNCLAIMED and DONE need nothing; do not wake them.

STEP 5 — KEEP THE MEMORY. Push the state back so the next firing can compare against it: `python3 plugins/dma-insights/scripts/drive_fetch.py push-ledger --file /root/.dma/ledgers/watchdog.json --session <YYYYMMDD-HHMM>-watchdog`. A firing that ends without this leaves the next one blind to stalls, so treat a failed push as a failed step and say so.

REPORTING. If nothing was actionable, say so in one line and stop — do not message anyone, do not comment anywhere, do not open a pull request. Report only when you promoted something, sent a resume, refused a promotion, or found a run you could not route.

NEVER: re-produce a page that get_run_progress already shows as PASS. Never start a fresh synthesis for a run holding a live claim. Never edit the repository (the self-provision steps only read it). A submit_page_payload that dies with RemoteDisconnected has usually SUCCEEDED server-side on a heavy page — always re-read get_run_progress before concluding anything failed, and never re-submit on the strength of a dropped connection alone.
```

---

---

### 2e · dma-synthesis-sequence-b — every 12 hours at :18 · EXISTS

Lane B: the cycle's SECOND client. Created 2026-08-23 to replace a mechanism
that could not run — see § 2a for why. It is not a different routine; it is
the same routine on a ten-minute offset, and § 2a's prompt is its
specification.

| | |
|---|---|
| **Trigger** | `trig_01NXSfaTVuWEubFAcA4mbbeL` (recreated 2026-08-29 from this fenced prompt after trig_01U8v332dJzmcz47DWRK9qyR was found missing; CONNECTORS ARE NOT ATTACHED on the recreated trigger — the API cannot pass them, so until a human re-attaches Exa, Tavily, Clay and the rest on its edit screen in the claude.ai routines UI, every lane-B firing will STOP at the connector preflight, by design), cron `18 */12 * * *`, fresh session per firing, push notifications on, created 2026-08-23T06:33:07Z, first `next_run_at` 2026-08-23T12:18:00Z |
| **Why ten minutes** | Long enough that lane A has run its gate and taken its claim — the queue selector removes a claimed entity, so lane B is simply offered a different one. Short enough that the two overlap and the cycle really is parallel. Ten minutes is a comfort margin, not a correctness one: correctness is `claim_run` being atomic. |
| **On collision** | Lane B's claim is refused; it moves to its first `GATE: RESERVE` line rather than waiting or racing. Two producers on one client's six pages is the outcome the claim exists to prevent. |
| **May / May not** | Exactly as § 2a, with one addition: lane B never treats lane A's claim as an orphaned lease. A lease held by a session that started ten minutes ago is a live producer, not a stall. |
| **Connectors — GAP CLOSED 2026-08-23** | Created through the API, which carries no claude.ai connectors, and this organisation has the API's `connectors` parameter disabled (the call was refused by name). A human attached them in the routines UI: read back off the trigger record at 10:33Z, `mcp_connections` carries Clay, DMA-Insights, Exa, Firecrawl, Google-Drive, LunarCrush, Indeed, PDF-Viewer, Vibe-Prospecting, Tavily and Context7 — the preflight minimum (Exa + Tavily + one of Clay / Vibe-Prospecting) is met, so lane B no longer stops at STEP 0. The preflight stays in the prompt: it checks what the SESSION carries, and a trigger record is not a session. |
| **`sources` — the doc was wrong** | This table said the trigger carried no `session_context.sources` and that its container therefore arrived with no repository. Read back off the live record at 10:33Z it carries `sources: [{git_repository: mishleyotis/Accelerate}]`, which is why a firing found /home/user/Accelerate already present and reported the prompt as false. Two lessons kept rather than one: a trigger's record changes without this doc changing, so **neither this table nor a prompt may assert what a container holds** — STEP -1 now reads it off the container; and the self-provision step no longer depends on a claude-code-remote tool either way. |

The live prompt, kept here verbatim so a drifted trigger is detectable by
diff. It deliberately delegates the body of the work to § 2a's prompt rather
than duplicating 35,000 characters that would then drift:

```
You are the scheduled DMA synthesis routine (dma-insights), lane B. ONE client per firing, end to end, through the installed plugin only — its skills, agents, hooks and routing are the system under test, so do not improvise around them and do not use ad-hoc multi-agent workflows. ONE CARVE-OUT, DEFINED BY THIS SAME TASK: STEP 0's RECOVERY MODE (lane A's prompt carries it in full) is part of these instructions, not an improvisation — under UPDATED_MID_SESSION, agent_run.py dispatch and checkout-read skills ARE the sanctioned path, and the in-firing `claude plugin ... update` commands change only this ephemeral container's local install cache, nothing account-level and nothing serving. This lane declined exactly that on 2026-08-24 12:18Z, reading it as contradicting this opening sentence, and ended a healthy firing without a client — that reading is wrong, and this sentence now says so itself.

YOU ARE THE CYCLE'S SECOND CLIENT. Lane A (Routine `dma-synthesis-sequence-a`) fired ten minutes ago with this same prompt and has already claimed its client. That is the whole mechanism: two Routines, two fresh sessions, two clients per cycle, and NEITHER session spawns anything. The earlier design had lane A spawn a sibling with the claude-code-remote create_session tool — measured 2026-08-23, that tool is not in a trigger-fired session's toolset, so the firing gated two clients, could not spawn, and correctly reported the second unstarted: correct behaviour, and one client short every cycle. A schedule needs no tool to be present.

Because lane A claimed first, the queue selector will not offer you its entity — a live claim removes it. If you somehow gate the same one anyway, `claim_run` is atomic: your claim is refused, and you move to your first `GATE: RESERVE` line rather than waiting or racing. Never work a run another session holds.

STEP -1 — CHECK, DO NOT ASSUME, IN EITHER DIRECTION. Read back off this trigger's own record on 2026-08-23, the Routine DOES carry `sources: [{git_repository: mishleyotis/Accelerate}]`, so the container usually arrives with the repository already present. The instruction this replaces asserted the opposite — "carries no `sources`, so nothing GUARANTEES a repository" — and a firing found the checkout there and correctly reported the prompt false. Neither a prompt nor a doc may assert what a container holds; the container is the authority. Run `ls /home/user/Accelerate/plugins/dma-insights` FIRST. If it is there, say so in one line and skip to STEP 0; do not clone over it. STEP 0's `git fetch` + `git checkout -B` is what makes a present-but-stale checkout safe, and that is the case worth guarding: a container arrived on 2026-08-23 with a checkout 136 commits behind and a clean working tree, which looks healthy and is not. Only if the path is missing: `git clone --branch claude/dma-insights-onboarding-0ryrd0 https://github.com/mishleyotis/Accelerate /home/user/Accelerate` with that exact real URL, never a placeholder, then `bash /home/user/Accelerate/plugins/dma-insights/scripts/bootstrap_session.sh`.

Everything else is identical to lane A. Follow the `dma-synthesis-sequence-a` Routine prompt exactly as written — STEP 0 verify the tooling (`python3 plugins/dma-insights/scripts/plugin_version.py --heal` — no version is written down in this prompt; the script compares what this session loads against what the checkout publishes, and --heal makes it run the update and the re-check itself, one command, printing one final verdict whose own fix text prescribes recovery mode — the script and this prompt say the same thing, and where they ever disagree, follow the script's freshly-read output and record the difference as a finding. If it prints a final `=> ROOT CAUSE, RECURS EVERY FIRING:` line, report that line verbatim and record the recurrence — and on UPDATED_MID_SESSION do NOT end the firing: enter lane A's STEP 0 RECOVERY MODE, producing this firing with every stage dispatched via `python3 plugins/dma-insights/scripts/agent_run.py --agent <name> --prompt-file <file>` (never the in-process Agent tool, which carries the stale roster this session bound) and the skill's files read from the CURRENT CHECKOUT rather than through the Skill tool; three firings in one morning ended cleanly on this verdict and produced nothing — then /dma-insights:doctor green and the in-session binding stress test), STEP 1 the pre-synthesis gate (`python3 plugins/dma-insights/scripts/run_gate.py pick`, obeyed verbatim, walking the pending queue and nothing else — no client is named to be admitted), STEP 1b pull the package and open the client's memory, STEP 2 produce through /dma-insights:dma-surface-production with top-session dispatch, STEP 3 assess against the gold exemplar plugins/dma-insights/fixtures/gold_manifest.json names, STEP 4 close the learning loop, STEP 5 report.

Read that Routine's prompt as your specification: it is the authority, and it is kept verbatim in plugins/dma-insights/docs/ROUTINES.md § 2 alongside this one, so the two lanes cannot drift apart unnoticed. If the two ever disagree, lane A wins and the difference is a finding to record.

CONNECTOR PREFLIGHT IS STILL REQUIRED, AND IT IS A MEASUREMENT RATHER THAN AN EXPECTATION. Connectors are attached per Routine in the claude.ai routines UI. Read back off this trigger's own record on 2026-08-23, the Routine carries ELEVEN — Clay, Context7, DMA-Insights, Exa, Firecrawl, Google-Drive, Indeed, LunarCrush, PDF-Viewer, Tavily and Vibe-Prospecting — so the preflight minimum is met and the expected outcome is that you PROCEED. The instruction this replaces said the Routine "was created without them (the API refused the connectors parameter for this organization)" and called this lane "THE ONE AT RISK": true when it was written, false since a human attached them in the UI, and left in place it primed this lane to expect a stop. A LANE THAT STOPS OVER CONNECTORS IT HAS is the reject-rather-than-triage failure in its own right (owner, 2026-08-23: "most default to rejecting in case of issues, rather than triaging and fixing"). Still check what you actually carry, because an attachment can be removed and a SESSION's toolset is the only authority — a trigger record is not a session: Exa, Tavily and at least one of Clay / Vibe-Prospecting must be present as mcp__<Name>__ tools. If that minimum is genuinely not met, STOP WITHOUT PRODUCING ANYTHING and report exactly which connectors this session carries — the fix is a human attaching them on this Routine's own edit screen in the claude.ai routines UI (the connector browse list's Use buttons enable a connector for the org, NOT for a Routine). The routine never runs in degrade mode (owner, 2026-08-20), and a lane that produces a thin client because it could not enrich is worse than a lane that says so.

A CONTINUED SESSION THAT FINDS THE CONNECTOR TOOLS 'NOT PRESENT' IS IN A KNOWN, RECOVERABLE STATE, NOT AT AN ENDING (owner, 2026-08-24: continued sessions declared the tools 'lost mid-session … cannot be recovered' and produced nothing; two of this environment's synthesis claims died the same day at 0/6 pages staged — holders stamped 12:15Z and 12:18Z — each lease pinning its client for ~95 minutes while the server held every claim the whole time). Bindings are made once at process start and never return mid-session; nothing server-side is lost — identity re-mints per call from the service-account key, and claims, staged pages and verdicts live in the connector's database, answering this session or one thirty days out alike. Run `python3 plugins/dma-insights/scripts/mcp_raw.py revive --run <run_id>` and, on REVIVE: OK, FINISH THE RUN through the bridge (`python3 plugins/dma-insights/scripts/mcp_raw.py call <tool> --args/--args-file`) under lane A's STANDING AUTHORIZATION (owner, 2026-08-24) for a claimed, unpromoted run — hand off only if the harness refuses the bridge itself or the budget is genuinely spent, and never declare the tools unrecoverable over a transport the bridge replaces.

Hard rules: exactly ONE client per firing; never a held-out entity (run_gate.HELD_OUT names them and the gate already subtracts them); never edit apps/ code; never edit the plugin, its skills, agents or gates (constraint [B] — the weekly rectifier is their only writer); never write another client's memory file; never synthesize a run the gate did not emit; never produce without holding the claim; if package vetting fails or entity identity is PENDING_REVIEW unresolved, record the finding and move to a RESERVE rather than force a promote. Begin your report by naming yourself lane B so the two firings are never confused in the record.
```


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
against section 2 — name, cron, enabled state, fresh-session mode, **model**,
and the prompt itself, which is why 2a's live prompt is quoted verbatim. The
`/dma-insights:doctor` command checks plugin, identity, token audience and
connector reachability and has **no routine check yet**; when it grows one,
it should perform exactly this diff. Until then the diff belongs to the
weekly rectification session's checklist (its prompt's STEP 8 states it), so
the gap is examined at least weekly by the one routine whose job is noticing
what quietly stopped holding. A missing, paused or drifted trigger found by
that diff is a finding like any other: recorded, measured, and closed by a
refinement — not silently re-created.

### Model, and why it is in the diff

Added 2026-08-23 (MEM-0219). The owner's standing instruction is that
everything defaults to Sonnet 5 while agents and subagents switch on their
own configuration. The repo half is settled and tested: `.claude/settings.json`
sets `"model": "sonnet"`, all 47 plugin agents declare their own model in
frontmatter (33 sonnet · 13 opus · 1 haiku), and
`scripts/tests/test_model_defaults.py` holds **both** halves — the default,
and that the deliberate opus and haiku overrides survive, so nobody satisfies
"everything on sonnet" by flattening the switching the same sentence asks for.

None of that reaches a Routine. **A trigger that fires a fresh session takes
its model from the trigger record, not from `settings.json`**, so the one
setting that decides what a scheduled firing runs on was the one setting
nothing tracked. Last direct observation, recorded in that test's docstring:
lane A ran `claude-sonnet-5`; `dma-rectification-weekly`
(`trig_01CoypdjU6bcwEewvRYxK3S3`) and `dma-refresh-drift-daily`
(`trig_01CvwqVMuLzWyQUsgwor98Sx`) ran `claude-opus-5`.

Those two are **not** assumed wrong. A rectifier and a drift scanner are
reasoning-heavy work, which is exactly what an override is for — the point of
putting model in the diff is that the value is *known and intended*, not that
it is uniform. A model that differs from this file is a finding; a model this
file records as a deliberate override is not.

Per-routine model is deliberately **not** transcribed into section 2 yet: this
session could not call `list_triggers` (every claude-code-remote MCP tool
returns "requires approval" here), and writing an unverified value into a file
whose whole discipline is verbatim accuracy would be worse than leaving the
column empty. Fill it from a session that can read the triggers, and from then
on the diff covers it.
