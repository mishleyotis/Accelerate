# Production readiness — what is ready, what is not, and what nobody measured

**Re-ask the question, do not read this table:**

```
python3 plugins/dma-insights/scripts/readiness.py --triggers <list_triggers.json> \
                                                  --tests --lifecycle
```

`--triggers` takes a saved `list_triggers` response — a script cannot call
that API and a session can. `--offline` skips the one lane that reaches the
live service; it reports `NOT_MEASURABLE_HERE`, never READY, because a
skipped check that reads as a passing one is the failure this file exists to
refuse. `scripts/goal_status.py` looks for one at
`.qa/triggers.json`; it is deliberately not committed, because a snapshot of
external state checked into a repository is stale the day after and reads as
current forever.

This document explains the lanes and records what they said on **2026-08-30**.
The script is the answer; a table in a document is a photograph of one.

---

## 1. Why the answer has three verdicts and not two

Every green report this project has been wrong about was green because
something never looked.

- The doctor printed forty-seven rows green while the session it was
  describing carried a **five-agent** install: it counted the CHECKOUT's files.
- `classification.py` matched the Client Research Profile as `client_profile`
  priority 3, the scanner wrote that into `import_files.classified_kind`, and
  `_classify_artefact` dropped it — classified, recorded, unread, for the
  whole life of the artefact (AUD-0169/0171).
- Two of six live Routines were unhealthy, one for six days, and nothing
  anywhere reported it, because the watchdog watches RUNS (AUD-0174).
- Fourteen findings were filed in a severity vocabulary the ledger's own tool
  does not know, so every mode of that tool died on a `KeyError` and the
  generated table went stale behind it (AUD-0178).

In each case the summary line was true about what it measured and silent
about what it did not. So `readiness.py` reports:

| verdict | meaning |
|---|---|
| `READY` | measured here, passed |
| `BLOCKED` | measured here, failed — the row names the fix |
| `NOT_MEASURABLE_HERE` | the lane is real, this container cannot see it, and the row names who can and how |

**`NOT_MEASURABLE_HERE` is never counted as ready.** `--strict` exits
non-zero on it, which is what CI should use. A lane nobody measured is
exactly the lane that fails.

The script **re-derives nothing**. Each lane shells out to the check that
owns it, so this cannot drift into disagreeing with them; if a rule changes,
it changes in one place.

---

## 2. The lanes

| lane | the question | who owns it |
|---|---|---|
| `coverage` | does every workbook tab, report section, deliverable and derived field have an owner that writes it? | `audit_coverage.py --strict` |
| `skills` | does every bundled script answer `--help`, and does every reference into the skill tree resolve? | `audit_skills.py` |
| `taxonomy` | any stale catalogue literal, any fifth maturity band the charter says must not exist? | `check_taxonomy_drift.py` |
| `approvals` | is every MCP tool a session attaches either auto-approved or refused on the record — nothing prompting by omission? | `audit_autoapprove.py --strict` |
| `install` | is what this session LOADS what the checkout PUBLISHES? | `plugin_version.py` |
| `connector` | is the MCP deployment reachable, does the token audience match the URL, does the service enforce the token? | `doctor.py` |
| `routines` | did every enabled Routine's last firing succeed? | `routine_health.py --strict` |
| `tests` | do the contract, engine, worker, api and mcp suites pass? | `pytest` (opt-in: `--tests`) |
| `lifecycle` | do the five lifecycle requirements walk through the REAL command line, in order? | `stress_run_lifecycle.py` (opt-in: `--lifecycle`) |

### What a verdict is a property OF

A blocked lane is not one thing, so every lane declares its **scope** and the
script reports it — `repository` (true of this checkout wherever it is read),
`container` (true of the machine the check ran on), `external` (true of the
live system). `scripts/goal_status.py` reads that field rather than
re-deriving the split: only a **repository**-scoped blocker fails the standing
goal, because a stale install on an ad-hoc container is real, is somebody's
problem, and is not this checkout failing anything. Reporting it as one
teaches a reader to stop believing the row.

| lane | scope |
|---|---|
| `coverage` `skills` `taxonomy` `approvals` `tests` `lifecycle` | repository |
| `install` `connector` | container |
| `routines` | external |

Two lanes measure **this container** rather than production, and the script
says so rather than pretending otherwise:

- **`connector`.** A container with no credential path has measured its own
  emptiness, not the deployment, so reporting BLOCKED there would call a
  serving system broken — as wrong as the reverse. The downgrade therefore
  requires **every failing row** of the doctor's report to be about
  *obtaining* a credential (identity minting, the account, the audience, the
  path token, the network). Keyed on the whole output instead, as the first
  draft was, it downgraded a stale INSTALL — a row the `install` lane already
  owns — into "no live credential path", because most of the doctor's
  *passing* rows contain the word `token`. That is a check inventing a reason
  for its own verdict, which is the failure this whole file refuses.
- **`install`.** This one is NOT downgraded, deliberately. A stale install is
  not an artefact of where the check ran; it is the live defect that
  abandoned `dma-refresh-drift-daily`, and every trigger-fired session meets
  it. `plugin_version.py --heal` brings the DISK current; agents, skills and
  hooks bind once at session start, so a firing that heals itself is running
  recovery mode, not a fixed session.

---

## 3. Measured 2026-08-30

`readiness.py --triggers <live> --lifecycle`, on an engineering container
against this checkout. Re-run it; do not quote it.

| lane | verdict | what it said |
|---|---|---|
| `coverage` | **READY** | no artefact required by a contract lacks a writer |
| `skills` | **READY** | every bundled script answers `--help`; no dead reference into the skill tree |
| `taxonomy` | **READY** | no stale catalogue literal against v7.0 |
| `approvals` | **READY** | 124 of 184 attached MCP tools auto-approved, 58 refused on the record, 2 guarded by their own precheck, **0 unclassified**. It was 16 of 86 before the read/write split existed |
| `lifecycle` | **READY** | all five requirements walked through the real command line, in order |
| `tests` | READY *(run separately)* | `4288 passed, 142 skipped` plus 22 `pg8000` errors, which are this container having no PostgreSQL — `tests/schema/` needs a live database |
| `install` | **BLOCKED** *(container)* | 0.9.12 loaded against 1.9.0 published; 47 agents dispatched against 68 carried. The live defect, met in the container measuring it |
| `connector` | **BLOCKED** *(container)* | the doctor's 15 checks passed 14; the one failure IS the stale install above, not a deployment fault — token audience, identity minting, the 401 on an unauthenticated call and the 33-tool roster all reconciled |
| `routines` | **BLOCKED** *(external)* | 4 of 6 healthy. `dma-rectification-weekly` FAILED (spend limit), `dma-refresh-drift-daily` ABANDONED (stale install). Neither is a code defect — see section 4 |

**The honest summary: the repository is ready and the environment is not.**
Every lane whose verdict is a property of this checkout is green, including
the run lifecycle walked end to end. Both blocked lanes and both unhealthy
Routines reduce to two facts that live outside the code — a plugin install
that does not reliably reach a scheduled container, and an account spend
limit — and both are in section 4 with the person who can close them.

---

## 4. What is NOT ready — the standing items, and who owns each

These are carried by the script itself, so a readiness answer cannot read as
complete while they are open. **No script in this repository can close any of
them.**

| item | owner | specified in |
|---|---|---|
| **Routine spend limit.** `dma-rectification-weekly` has failed on "You've hit your individual spend limit" (five_hour rate limit, rejected) since 2026-08-24. Not a code defect. | the account owner, at `claude.ai/settings/usage` | `docs/ROUTINES.md` |
| **Stale install on a trigger-fired container.** `dma-refresh-drift-daily` reaches a permission prompt the plugin's own auto-approve hook ALLOWS — verified by running the hook against that exact tool name — which means the hook did not RUN. A scheduled session has nobody to answer the prompt, and cannot heal its own bound hooks. | the environment owner: `bootstrap_session.sh` must run BEFORE the session starts (claude.ai/code environment settings, with `DMA_ROUTINE_SA_KEY_B64`) | `docs/ROUTINES.md` |
| **Owner-names-the-client channel.** There is no interface through which the owner can say which client to assess next: `run_gate.py pick` has no `--client`, its one human lever `--prefer` is passed by nothing, and no Slack surface exists anywhere. **Specified, NOT BUILT.** | whoever builds it — the contract is section 3 of the doc | `docs/CLIENT-SELECTION.md` |
| **Connector authorisation.** Atlassian, Zapier and Zennify_Brains need OAuth; lane B (`trig_01NXSfaTVuWEubFAcA4mbbeL`) carries no claude.ai connectors. A Routine that reaches its enrichment preflight without them stops without producing — by design, because the owner ruled the routine never runs in degrade mode. | the account owner, on **each Routine's own edit screen** in the claude.ai routines UI. The connector browse list's *Use* buttons enable a connector for the ORG, not for a Routine — measured 2026-08-20. | `docs/CONNECTORS.md` |

---

## 5. What this document does NOT cover

**The app's own production deployment.** The charter's standard is "not done
until live in prod", and that is the `web` / `api` / `mcp` Cloud Run services,
the `worker` / `migrate` Jobs and the three Scheduler triggers. Nothing here
measures them: this container has no `gcloud`, and readiness for a served
surface is a question about what production RETURNS, not about what a
checkout contains. That lane belongs to `infra/deploy.sh` and to the
`deployed-app-auditor` agent, which reads what production actually serves
rather than what an agent said it produced.

**Whether a given run is promotable.** That is per-run and it already has its
own instruments — `get_validation_verdict`, `list_open_rejections`, the
adversarial verifier, the evidence-integrity checker. Readiness is about the
machinery; a verdict is about one client.

**The 62 findings still open in `.qa/AUD-DISPOSITIONS.json`.** Nine are
BLOCKER. They are open, they are recorded, and several belong to the supplied
v4.2 archive rather than to this repository. `python3 scripts/aud_ledger.py
--open` prints them worst-first, and `--verify` RUNS the check behind every
closed row rather than restating it. Readiness does not silently absorb that
ledger; the two questions are different and both have to be asked.
