# Headless workflow audit — 2026-09-03

**The question asked.** Can a scheduled DMA firing run from a Slack request to
a promoted client on the web app with no person approving a tool call, and
if not, what stops it?

**The answer, measured.** Inside a session, yes: after this change every
tool an agent or a Routine is told to use is either auto-approved by a hook
the plugin ships, or refused on the record, and the stage machine that hands
research to scoring to reports to the package is computed and announced by
hooks rather than remembered from prose. Outside a session, no — and none
of the four things that stop it is a code defect this repository can close:

| # | inhibitor | measured | who closes it |
|---|---|---|---|
| 1 | **Every Routine stopped firing after 2026-08-30.** Six independent crons show `next_run_at` 3–4 days in the past and no `enabled` / `ended_reason` / `suspension_reason` on any record. Simultaneous, reasonless, account-wide: the usage-limit pause the owner reported in the same period. | `routine_health.py --file /root/.dma/triggers_live.json`: 5 OVERDUE, 1 FAILED (spend limit, 2026-08-24) | the account owner — claude.ai/settings/usage, then the Routines UI |
| 2 | **No Routine carries Exa or Tavily; only lane A carries Clay; the intake carries nothing.** The connector preflight REQUIRES exa + tavily + one of explorium/clay, so every research and synthesis firing stops at STEP 0(d) by design. | `list_triggers` → `mcp_connections` per record | a human, on each Routine's own edit screen (the API's `connectors` parameter is disabled for this org; the browse list's Use buttons enable a connector for the ORG, not a Routine) |
| 3 | **The live intake prompt was the 2026-08-30 text.** No `doctor.py --heal`, no derived connector contract, and it ended at "the run may START" without starting one. | `routine_sync.py diff --live`: 2g DRIFTED; 2b–2e in sync | `routine_sync.py push --routine 2g` → `update_trigger` (rendered below; applied from this session where the tool is present) |
| 5 | **Tavily and Exa prompt on every surface and "allow for all sessions" does not stick (owner, 2026-09-04).** Both hooks approve every spelling and the user-scope grant matches; the one control that overrides hooks and allow rules in every mode, never offers to remember the choice, and reaches claude.ai/code, the CLI and chat alike is an **organisation per-tool setting of `ask`** on the connector (permissions reference). Also measured: a fetched connector attaches as `mcp__claude_ai_<Server>__…`, a spelling no grant covered; and Cowork runs shell as `mcp__workspace__bash`, which no `Bash` rule or hook reached. | `why_did_it_prompt.py <tool>`; `/mcp` in the prompting session shows the per-tool setting | the org's claude.ai admin (connector tool controls). The two spellings and the Cowork tool are now covered by hooks and grants |
| 4 | **The container is a restored snapshot.** Every session starts on the plugin the image carried (0.9.12, 47 agents) until `doctor.py --heal` runs; hooks bind once, so the healed install reaches the NEXT session or a headless child, never the running one. | `doctor.py`: UPDATED_MID_SESSION on every fresh session | the environment owner — `bootstrap_session.sh` in the environment's setup-script field, so the image is current before the session binds |

Everything below is what was found and what was changed, in the order the
goal asked for it.

---

## 1 · The prompt surface — every tool, every agent, ruled on

### What was already true

`audit_autoapprove.py --strict` passed before this audit: of 184 MCP tools a
session attaches, 124 auto-approved, 57 refused on the record (writes,
sends, deletes, spends), 2 guarded by their own precheck hooks
(`submit_page_payload`, `promote_run`), 1 conditional (`slack_send_message`
into #deal-desk only), 0 unclassified. `WebSearch` and `WebFetch` were
approved by name. `permissions.defaultMode: dontAsk` and workspace trust are
written by `bootstrap_session.sh` and re-asserted by the `ensure_headless`
SessionStart hook.

### What was still prompting, and why

Every agent in this plugin does its work through **Bash**: the sixteen
category researchers, the four pillar scorers, the two report writers, the
conductor and the vetter each run `python3 -m engine.<module> …` for every
write they make, because the workbook's refusals ARE the write control. The
producers write section JSON to disk with **Write** so `ship_page.py` can
submit it without a byte passing through a model. Neither `Bash` nor
`Write`/`Edit` had a PreToolUse decision or a settings grant, and neither
the `default` nor the `auto` permission mode approves an arbitrary shell
command — so every one fell through to a prompt, and a trigger-fired
container has nobody to answer it. The MCP surface was 100 percent ruled on
and the workflow still could not run headless. That is the recurring report.

### What changed

**`hooks/autoapprove_builtins.py`** (PreToolUse on
`Bash|Write|Edit|MultiEdit|NotebookEdit`). Approves by GRAMMAR, not by list:

- Bash — every segment (split quote-aware on `&&` `||` `;` `|`) must be the
  research engine (`python3 -m engine.*`), a plugin or repo script
  (`plugins/dma-insights/scripts/*.py`, `skills/*/scripts|engine/*.py`,
  `scripts/*.py`, resolved against the session's cwd for relative paths),
  pytest, `claude -p --agent dma-insights:*`, a local git operation (no
  push), or a read-only shell verb; redirections only into a run root;
  inline python only when it names none of the process-, network- or
  filesystem-mutating modules. `printenv`, `curl`, `xargs`, `sudo`, `eval`,
  `find -exec`, backticks, backgrounding, a pipe into an interpreter, and
  any command that so much as names `sa.json`, `pathtok`, `slack_token` or
  `.claude/` draw NO decision — they fall through exactly as before.
- Write/Edit — approved when the target is under `$DMA_RUN_ROOT`,
  `/home/claude/dma_output`, `/root/.dma`, `/tmp`, or the repository's
  `plugins/dma-insights`, `fixtures`, `scripts`, `tests`, `docs` (the
  rectifier's writer scope). The deployables (`apps/`, `infra/`,
  `migrations/`, `packages/`) and every settings or credential file never.
- The two deny guards (`deny_credential_ops`, `deny_bulk_read`) are imported
  and asked FIRST; the hook says nothing when either would refuse. The
  harness resolves deny over allow anyway; this hook does not lean on it.
- It never denies. Its only power is to remove a prompt.

**`bootstrap_session.sh`** now also writes the same shapes as narrower
prefix grants (`Bash(python3 -m engine.*)`, `Write(/root/.dma/**)`, …) in
user settings — the belt for a session whose hooks bound from a stale
install. No bare `Bash`, no `Write` without a path.

**`audit_builtin_approvals.py`** harvests every command the 73 manifests,
the two skills and the six Routine prompts tell a session to run (124 on
this checkout), normalises the placeholders, and runs the real hook against
each. Result: **124 approved, 0 prompting.** `readiness.py`'s `approvals`
lane now runs both audits, and `test_audit_builtin_approvals.py` fails CI on
the first manifest line the grammar does not know.

### Where the prompts came from in THIS session

The auto-mode classifier blocked four of this audit's own Bash calls — a
smoke script, a pytest invocation of one file, an inline check — each
because the command TEXT contained strings that look dangerous (`rm -rf`,
`sudo`, `/etc/passwd`) in a test corpus. The same classifier stands behind
every Routine session: a command the plugin's hook does not approve is
judged by it, and its judgment is probabilistic. The hook is what makes the
judgment unnecessary for the pipeline's own commands.

## 2 · The agents and their tools

- `scripts/provision_agent_tools.py` (check mode): 34 connector tools · 73
  agents · **0 would change** — every `tools:` and `disallowedTools:` line is
  what the role table generates.
- **`test_agent_tools_match_bodies.py`** (new): for all 73 manifests, every
  connector tool a body instructs is in its `tools:` line, no body instructs a
  tool its deny list forbids, and every built-in and connector family any
  agent is granted is pre-approved in `agent_run.ALLOWED` — because
  `claude -p --permission-mode dontAsk --allowedTools=…` DENIES what is not
  listed (MEM-0111). Measured: 0 drift. The 23 "Write" hits an earlier
  check produced were the English verb in prose, not instructions.
- `agent_run.ALLOWED` gains **`Agent`**: the conductor, the surface-producer
  and the rectifier fan out through it, and a headless child that is one of
  them lost every dispatch it tried. `AskUserQuestion` is deliberately NOT
  pre-approved — nobody can answer it in a child, and its denial is what
  routes the conductor to `engine.preflight autobind`.
- **research-conductor** step 0(c) now runs `engine.preflight autobind` in a
  headless firing before ending on an unanswered question, and does not
  re-ask a binding the intake already recorded.

## 3 · The hooks that carry the workflow

| moment | hook | event | what it does |
|---|---|---|---|
| session start | `session_brief` | SessionStart (5 sources), SubagentStart | the routing rule, the memory-first rule, the submit boundary; research children get their own brief |
| session start | `ensure_headless` | SessionStart | `defaultMode: dontAsk` + workspace trust for the NEXT session (a restored snapshot loses it — inhibitor 4) |
| before a tool | `autoapprove_connector` | PreToolUse `mcp__.*`, `WebSearch\|WebFetch` | every MCP read approved or refused on the record |
| before a tool | **`autoapprove_builtins`** (new) | PreToolUse `Bash\|Write\|Edit\|MultiEdit\|NotebookEdit` | the pipeline's own commands and files, by grammar |
| before a tool | `deny_credential_ops`, `deny_bulk_read` | PreToolUse Bash | deterministic refusals with the sanctioned path in the reason |
| before submit / promote | `precheck_submit`, `precheck_promote` | PreToolUse | the five-second refusal; the atomic-promote advisory; both approve on the clean path |
| after submit / promote | `verdict_watch` | PostToolUse | a gate that refused twice → read `explain_gate`, record the recurrence |
| after an agent returns | `artifact_cadence` | PostToolUse Task\|Agent | a producer that returned must have filed an artifact |
| after an agent returns | **`stage_advance`** (new) | PostToolUse Task\|Agent, Bash (dispatch/gate) | the run's state, the criterion that closes it, the next agent(s) and the prompt |
| on Stop | **`stage_advance`** (new) | Stop | refuses ONCE per state to end a session whose run an agent can still advance |

### Completion criteria, as data

`engine.watchdog.COMPLETION_CRITERIA` names, per state, the gate that closes
it. The research half was already computed (PRELIM_OPEN … READY_FOR_HANDOFF);
the assessment half is new: `SCORING_OPEN` → `CRITIC_PENDING` →
`SCORING_GATE_OPEN` → `REPORTS_OPEN` → `PACKAGE_UNSHIPPED` → `SHIPPED`, each
with the agent that owns the next unit of work (`parallel` lanes for the
four scorers and the two report producers). This is what "the scoring
agents fire once research is done, the report writers and the validator
once scoring is done" now means mechanically — the watchdog Routine's
`--revive` and the in-session hook read the same plans.

### PRELIM — the enrichment phase, before any category

The connector calls that ought to run without approval, and do:
`technographic-scanner` (Clay `find-and-enrich-company` →
`add-company-data-points` → `get-task-context`; Vibe-Prospecting
`match-business` → `enrich-business`; Indeed) and
`enrichment-connector-specialist` (the contact pass) are dispatched INSIDE
PRELIM, in parallel, and every one of their tools is in `ENRICHMENT_TOOLS`
or `QUALIFIED_TOOLS`. `tech_baseline` will not close without a row in each
of OPS · CUST · DATA · INFRA; `leadership` will not close without two named
people. `orient` serves no category card until PRELIM is complete.

## 4 · The chain to the web app, stress-tested

- `audit_chain.py --strict`: 11/11 links have an owner, a gate and a reader.
- `audit_coverage.py --strict`: every tab, section, deliverable and derived
  field has a writer; 0 holes.
- `stress_run_lifecycle.py`: **32/32** (was 28/32 — the script closed three
  PRELIM sections where the engine now requires seven; fixed to walk the
  real closure: the Firmographics tab's ten must-present fields, two named
  leaders, thought leadership, all four estate layers).
- Research-engine suite incl. the new `test_stage_machine.py`: 45/45.
- Plugin suite: 1289+ passed, 1 skipped (the Drive-gated one).

**The chain hole that was found and closed.** The intake Routine ended at
"the run may START" and nothing started one: no Routine in the schedule
dispatched `research-conductor`, and the watchdog had no registry row to
revive because only `engine.cli start` writes one. An auto-bound preflight
sat in Drive until a person ran the start by hand. §2g STEP 6 now starts
the run and dispatches the conductor in the same firing; if the firing ends
first, the hourly watchdog revives the run from the state it stopped in.
That is the handover, and it needs no person.

**What the app then does, unchanged and verified by existence:** the
package scan (Cloud Scheduler, every 30 min) ingests the client folder;
`run_gate.py pick` offers the run to a synthesis lane; the surface-producer
pipeline (per-surface producer → finding-challenger → page-consolidator →
submit) stages six pages; `promote_run` publishes them atomically; the
deployed-app-auditor reads what production serves.

## 5 · Reconcilers that were blind to the live shape

- `routine_sync.py` read `prompt` at the top level; the API returns
  `{"data": [...]}` with the prompt under `derived_state.prompt`. It reported
  every live Routine as NOT IN THE SUPPLIED LIVE SET. Fixed; 2b–2e now read
  in sync and 2g DRIFTED, which is true.
- `routine_health.py` read a missing `enabled` as `False` and called all six
  DISABLED ("a person paused it"). A missing key is unknown; the schedule is
  what says whether a Routine fires. It now reports **OVERDUE** when
  `next_run_at` is more than two intervals in the past, which is the shape
  an account-level pause leaves.
- The canon's trigger ids (2026-08-30) matched none of the six live records;
  lane A, recorded as NOT CREATED, was found standing. All six headings and
  the table now carry the measured ids, pinned by a test.

## 6 · Standing items no code can close

1. Resume the Routines (inhibitor 1) — the account owner.
2. Attach Exa, Tavily and Clay to every research and synthesis Routine, and
   Slack to the intake (inhibitor 2) — a human, per Routine, in the UI.
3. Wire `bootstrap_session.sh` into the environment's setup-script field so
   the snapshot boots current (inhibitor 4) — the environment owner.
4. Push the 2g prompt to the live trigger (inhibitor 3) —
   `routine_sync.py push --routine 2g`, applied with `update_trigger`.
5. The rectification Routine's last firing FAILED on a spend limit
   (2026-08-24) and has not fired since; the ledgers the synthesis lanes push
   to Drive are merged only by it.

## 7 · Live headless probe — measured, not inferred (2026-09-04)

A real `claude -p` session, in **`default` permission mode** (the mode that
prompts, chosen deliberately — `dontAsk` would have hidden a prompt as a
silent denial), on this container after `doctor.py --heal` installed 1.17.1,
with the plugin's hooks bound at its start. The task exercised every tool
class the pipeline uses:

| step | tool | result |
|---|---|---|
| `python3 -m engine.cli counts` | Bash | ran |
| `python3 -m engine.preflight init …` into a run root | Bash | ran, wrote `preflight.json` |
| `audit_builtin_approvals.py --strict` | Bash | ran: 125/125, 0 would prompt |
| `grep -c` on the run root | Bash | ran |
| create `note.json` in the run root | Write | ran |
| replace a value in it | Edit | ran (`edit-ok` read back) |
| read it back | Read | ran |
| `get_memory_digest` | connector MCP | returned |
| `list_pending_runs` | connector MCP | returned |
| inline `python3 -c` (json only) | Bash | ran |

Stream summary: 14 tool calls, `permission_denials: []`, 80 hook events, 15
turns, final line `PROBE COMPLETE: 10 of 10 steps ran, refused: none`. Zero
permission prompts, zero denials, in the mode that prompts. Re-run it:

```
claude -p --permission-mode default --model haiku --output-format stream-json \
  --verbose --add-dir /root/.dma < plugins/dma-insights/scripts/probe_headless.md > stream.jsonl
python3 -c "import json;print([json.loads(l)['permission_denials'] for l in open('stream.jsonl') if '\"result\"' in l])"
```

**What this does and does not prove.** It proves the permission layer this
repository controls lets a headless session through every tool class the
agents use, against the live connector. It does not prove a full assessment
ends promoted in the web app from this container, and it cannot: the research
tier's connector preflight REQUIRES Exa and Tavily, which are attached to no
Routine and not to this session (inhibitor 2); every Routine is paused
(inhibitor 1); and pushing a synthetic package into the production intake
tree to watch the scan ingest it would put a fake client in front of the
package scan and the synthesis lanes, which I will not do without the owner
asking for it. The package-to-promotion half is proved by existence
(`audit_chain.py`, 11/11), by the acceptance walk
(`tests/acceptance`, 557 passed, `test_acceptance_full_run` from `start` to
a verified package), and — §8 — by the app's own ingest and promote code
running against a real PostgreSQL 16 in this container, not by a live
promotion.

## 8 · Ingest → promote, exercised against a real database (2026-09-04)

The half §7 could not reach live was run the way CI runs it, on this
container: `infra/local/up.sh` fell back to the system PostgreSQL 16 (no
docker daemon), installed pgvector, created the IAM-parity roles and
migrated the schema to head with Alembic — the same migrations the `migrate`
Job applies in production. Then the suites that open that database:

| suite | result | what it proves about the chain |
|---|---|---|
| `tests/schema/` | 35 passed, 12 skipped (catalogue not loaded) | four bands on the RAW score with no fifth enum value, generated columns STORED, api role denied on staging, null date → UNVERIFIED |
| `apps/worker/tests` + `apps/mcp/tests` + `apps/api/tests` + `packages/shared/tests` + `infra/jobs/tests` | **2431 passed, 11 skipped** (2 EDGAR unreachable, 2 catalogue not loaded, 2 deploy artefacts absent, others environment-gated) | the package scan, the parser, evidence persistence, the connector's validation and promote, the API's reads |
| `test_promote.py` + `test_ledger.py` + scan/persist/re-upload tests, `-v` | **70 passed, 0 skipped** | see below |

The promote tests that ran, by name, against the migrated schema rather than
a mock: `test_promote_all_or_nothing_then_idempotent`,
`test_injected_writer_failure_rolls_back_everything`,
`test_incomplete_run_writes_nothing_and_names_pages`,
`test_fix_one_page_repromotes_from_retained_staging`,
`test_registry_order_is_stable_and_covers_all_34`,
`test_a_retained_safeguard_failure_discloses_and_still_promotes`,
`test_a_retained_pass_that_fails_a_current_gate_refuses`,
`test_promotion_state_never_moves_backwards`. The ingest tests that ran:
`test_rerunning_on_unchanged_tree_processes_nothing`,
`test_changed_checksum_is_detected_and_reprocessed`,
`test_an_empty_walk_is_recorded_as_failed_not_succeeded`,
`test_a_package_retries_then_quarantines_instead_of_churning`,
`test_duplicate_content_lands_once_and_citations_resolve`,
`test_the_guard_matches_on_content_not_on_the_drive_file_id`. Invariants 3,
8, 9, 11 and 12 are therefore measured on a real database in this
container, not inferred from the tests' existence.

**The live serving tier, read and not written.** Two read-only walks of
production, with the container's own service identity (no token printed):

- `run_gate.py pick --count 1` gated the pending queue in its own order and
  came back `GATE: PRODUCE` for one client (run `bfc6cb31…`, 195 scored
  cells, 114 evidence rows, catalogue v7.0, first production) with two
  RESERVEs behind it. It walked past three: one already serving 6/6 and
  current, two whose ingested run parsed to **0 scored cells** — a stub the
  gate refuses with "report a scan finding", which is the package-quality
  failure the chain is built to stop, stopping it.
- `synthesis_watchdog.py --json` (observe only; `--promote-ready` was NOT
  passed): **17 pending runs, 0 promotable, 14 with all six pages missing,
  3 with one page PASS, 0 live claims, 0 sessions.** The newest claim
  expired 2026-09-03; the newest claim holder is a lane label from
  2026-09-01. Nothing has staged a page since the Routines stopped
  (inhibitor 1) — the queue is the shape of a pipeline whose producer is
  paused and whose gate is ready, which is exactly what the inhibitor table
  says.

**So what remains unproved, and why.** A page has not been staged and a run
has not been promoted *by a headless firing* since 2026-08-30. The code that
does both is proved here against the real schema; the connector is reachable
from a headless session (§7); the gate offers a producible run today. What
is missing is a firing — and every firing is paused at the account, every
research firing lacks Exa and Tavily, and every fresh session binds a stale
image until the setup script is wired. Those are the four rows of the
inhibitor table, and each is an owner's or admin's action. This container
will not stand in for that firing by pushing a synthetic package into the
production intake tree or by passing `--promote-ready` against a client's
run: both would put content in front of the scan and the synthesis lanes
that no person asked for.

## How to re-ask every question in this document

```
python3 plugins/dma-insights/scripts/audit_autoapprove.py --strict          # MCP surface
python3 plugins/dma-insights/scripts/audit_builtin_approvals.py --strict    # Bash/Write/Edit surface
python3 scripts/provision_agent_tools.py                                    # tool grants, 0 drift
python3 -m pytest plugins/dma-insights/scripts/tests/test_agent_tools_match_bodies.py -q
python3 plugins/dma-insights/scripts/audit_chain.py --strict
python3 plugins/dma-insights/scripts/stress_run_lifecycle.py
python3 plugins/dma-insights/scripts/routine_health.py --file <list_triggers.json> --strict
python3 plugins/dma-insights/scripts/routine_sync.py diff --live <list_triggers.json>
python3 plugins/dma-insights/scripts/readiness.py --triggers <list_triggers.json> --lifecycle
bash infra/local/up.sh                                                      # real PostgreSQL 16, schema at head
LOCAL_DATABASE_URL='postgresql://postgres:local@localhost:5432/dma_insights' \
  python3 -m pytest tests/schema/ apps/worker/tests/ apps/mcp/tests/ apps/api/tests/ -q -rs
python3 plugins/dma-insights/scripts/run_gate.py pick --count 1             # live queue, read-only
python3 scripts/synthesis_watchdog.py --state /tmp/wd.json --json           # live serving tier, observe only
```
