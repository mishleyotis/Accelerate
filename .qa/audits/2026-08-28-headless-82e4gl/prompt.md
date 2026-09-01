# Deep QA — DMA Insights: headless readiness audit (ledger/phase protocol)

## 0. What you are doing, and why it is not a conformance audit
The pipeline today ingests work by **watching a Google Drive tree**. That is
being retired. The intended architecture is:
```
  a DMA request arrives                                    ← Slack, OR the owner
  (Slack deal-desk message, or the owner typing               typing a request
   a request into a Routine)                                  into a Routine
            ↓
  a Routine fires HEADLESS — no human in the session
            ↓
  the assessment runs end to end:
      intake → triage/dedupe → PUBLIC|HYBRID|INTERNAL →
      internal docs → per-subcap research → synthesis →
      scoring → governance → reports
            ↓
  results are PUBLISHED TO THE DMAI APP, all of it:
      · the six rendered client surfaces      (exists today)
      · the governance ISSUE REGISTER          ← no path today
      · the RESEARCH / SCORING WORKBOOK        ← no path today
        (one file: "DMA Scoring Workbook, contract v3")
      · the CLIENT RESEARCH REPORT and the
        ASSESSMENT REPORT                      ← no path today
```
So your question is **not** "does the code match a spec." It is:
> **What must be true for this repo to run that loop unattended, and how far
> is it from being true?**
Every finding must answer *"and what does that mean for autonomous headless
operation?"* A defect that a human currently absorbs is a **blocker** in this
architecture, not a minor. Say so.
You are **read-only on behaviour.** You do not fix, refactor, or improve
anything. You may write findings to the findings memory and write your report.
**This document is the plan, not a reading list.** It contains 149 discrete
checks, each of which must end in a tracked state. The section immediately below
gives the phase order, the append-only ledger that records completeness, and the
drift-control protocol for a session that will be compacted before it finishes.
Read it before §1 and follow it — an audit run out of order, or from memory, is
the failure mode this whole document is written against.
---
## How to run this audit — phases, ledger, and drift control
*Unnumbered on purpose: it is the operating manual for the sections that follow, not one of them.*
This document is **149 discrete checks across 23 subsections**. That is more than
one session can hold, so it is written to be executed across many — by a model
that will be compacted, may be replaced mid-audit, and cannot be trusted to
remember what it already did. Everything below exists to make the audit
**resumable, completeness-tracked, and drift-resistant**. Run it as written.
---
### P0 · Anchor before you read anything else
Do these five things before the first check. They take minutes and they are what
makes the rest recoverable.
**1. Fingerprint this prompt.** The audit must fail loudly if its own
instructions change underneath it — the same discipline R23 applies to the
knowledge graph.
```bash
mkdir -p .qa && sha256sum <this-file> | tee .qa/prompt.sha256
```
Re-verify at every re-anchor. **A mismatch is a HARD HALT**: stop, report which
checks were completed under which fingerprint, and ask before continuing. A
finding produced under a prompt you can no longer reconstruct is not auditable.
**2. Confirm the pinned artefacts resolve.** The three template ids in §4 and
the repository itself. If a template will not open, record it and mark every
check that depends on it `BLOCKED` rather than guessing from the skills.
**3. Build the ledger** (next section). Do not hand-type it.
**4. Record the baseline** — commit sha of the default branch, date, model
identifier, and whether you hold gcloud credentials. Findings are only
interpretable against the tree that produced them.
**5. Read §2 Ground rules in full and do not skip it again by memory.** Re-read
it at every re-anchor. Section 2.3's four traps are the ones that manufacture
false findings, and a compacted session forgets them first.
---
### The ledger — how completeness is tracked
**Every check gets an id, a state, and a completion test. No check is done until
its row says so and carries a measurement.** The ledger is append-only, mirroring
R21: you never edit a row, you append a newer one. The latest row for an id wins.
Bootstrap it mechanically from this document, so the ids come from the prompt
rather than from your memory of it:
```bash
python3 - "$PROMPT" <<'EOF'
import re,sys,json,pathlib,hashlib
src=pathlib.Path(sys.argv[1]).read_text()
L=src.split("\n"); sec=sub=None; incode=False; rows=[]; n=0
for ln in L:
    if ln.strip().startswith("```"): incode=not incode; continue
    if incode: continue
    m=re.match(r'^## (\d+)\. ',ln)
    if m: sec=m.group(1); sub=None; continue
    m=re.match(r'^### (?:Stage (\d+)|(\d+\.\d+))',ln)
    if m: sub=("S"+m.group(1)) if m.group(1) else m.group(2); n=0; continue
    if re.match(r'^\s*[-*] ',ln) and sub and sec != "2":
        n+=1
        rows.append({"id":f"{sub}-{n:02d}","section":sub,
                     "text":re.sub(r'\s+',' ',ln.strip()[2:])[:300],
                     "state":"PENDING","measurement":None,"verdict":None,
                     "artefact":None,"note":None})
pathlib.Path(".qa").mkdir(exist_ok=True)
with open(".qa/ledger.jsonl","w") as f:
    for r in rows: f.write(json.dumps(r)+"\n")
print("checks:",len(rows))
EOF
```
Expect **149**. A different number means this document has been edited — stop and
reconcile before auditing, because the ledger and the prompt must describe the
same work.
The script deliberately excludes §2 Ground rules, §7 Recording findings,
§9 Stop conditions and §10 Scope boundaries. Their bullets are **standing rules
that govern every check**, not units of work: they have no "done" state and must
never enter the ledger. They bind for the whole audit, which is why §2 is re-read
at every re-anchor rather than ticked off once.
**Two things the ledger does not capture, tracked elsewhere on purpose.** A few
directives live in prose rather than bullets — §1.1's "build that table" is the
clearest — and each of those terminates in a numbered §8 deliverable item, so the
deliverable checklist is their completion test. And the phase transitions and
re-anchors are tracked as `PHASE-<n>` and `ANCHOR-<n>` rows, which are process
records rather than checks and are excluded from the 149.
**States**, and what each requires:
| State | Requires |
|---|---|
| `PENDING` | nothing — the bootstrap default |
| `IN_PROGRESS` | claimed by this session; carries the session ref |
| `DONE` | a `measurement` (the command/query with its denominator, ≥30 chars) **and** a `verdict` from the five in §2.1, **and** `artefact` naming which tree it was measured against — repo, supplied v4.2 archive, or a pinned template |
| `BLOCKED` | a named blocker and what would unblock it. Never a synonym for hard |
| `NOT_APPLICABLE` | a reason. "Superseded by a settled answer in §4" is valid; "seemed unimportant" is not |
Append a row after **each** check, not in batches — a batch lost to compaction is
work repeated. To read status:
```bash
python3 - <<'EOF'
import json,collections
last={}
for l in open(".qa/ledger.jsonl"):
    r=json.loads(l); last[r["id"]]=r
c=collections.Counter(r["state"] for r in last.values())
print(dict(c), "| total", len(last))
open_ids=[i for i,r in sorted(last.items()) if r["state"] in ("PENDING","IN_PROGRESS")]
print("open:",len(open_ids)); print(open_ids[:40])
bad=[i for i,r in last.items() if r["state"]=="DONE" and (not r.get("measurement") or len(r["measurement"])<30)]
if bad: print("DONE without a real measurement — NOT done:",bad)
EOF
```
**That last check is the completeness gate.** A `DONE` row whose measurement is
missing or under 30 characters is not done; reopen it. The audit is complete when
every id is `DONE`, `BLOCKED` or `NOT_APPLICABLE`, and no `DONE` fails the
measurement test.
---
### Phases, with entry and exit criteria
Work them in order. Each phase has a **blocking output** — do not enter the next
phase without it, because later phases are scoped by earlier answers.
| Phase | Covers | Blocking output before you may proceed |
|---|---|---|
| **P0 Anchor** | above | `.qa/prompt.sha256`, ledger at 168, baseline recorded |
| **P1 The three dominating facts** | §1.1, §1.2, §1.3 | Answers to all three. **§1.2 in particular reframes everything**: if a headless child genuinely cannot search, most of §3 becomes "what would have to be built", not "does it work" |
| **P2 The seven owner checks** | §4.1 – §4.7 | A verdict per check. These outrank the generic sweep, so they run before it, not after |
| **P3 The nine stages** | §3, Stages 1–9 | A verdict per stage and the seam map |
| **P4 Cross-cutting** | §5.1 – §5.5 | The invariant table, the gate sample, the test-honesty measurements |
| **P5 Synthesis** | §8 Deliverable | The fourteen deliverable items, in order |
**Why this order.** §1 scopes the rest. §4 is what the owner asked for by name.
§3 depends on §4's template and workbook findings — auditing Stage 8 before §4.4
means reading the report templates twice. §5 is the widest and cheapest to
resume, so it sits where an interruption costs least.
**Re-anchor at every phase boundary** using the protocol below, and record the
phase transition in the ledger as a row with id `PHASE-<n>`.
---
### Drift control — for the auditing session, not the pipeline
The audit is a long-running reasoning task, which is the exact shape §4.2 asks
the *pipeline* to defend against. Apply the same discipline to yourself.
**Re-anchor** — after every compaction, at every phase boundary, and every
20 completed checks. The protocol, in order:
1. Re-verify `.qa/prompt.sha256`. Mismatch → HARD HALT.
2. Re-read **§2 Ground rules** in full. Not from memory.
3. Run the ledger status command. Work only from `open:`; never re-derive what is done.
4. Answer the five drift questions below in writing, in the ledger, as a row with id `ANCHOR-<n>`.
**The five drift questions.** Each targets a failure this audit is specifically
prone to:
| # | Question | Why it is asked |
|---|---|---|
| 1 | Which artefact am I measuring — the repo, the supplied v4.2 archive, or a pinned template? | The installed skill is two versions behind the real one (§1.3). Measuring the wrong tree produces a confident, false report |
| 2 | Am I still using the pinned template ids, and have I checked none of the three superseded ids crept back in? | Three superseded drafts exist and read almost identically |
| 3 | Have I started treating any `[LEAD]` as established? | §2.5. Leads are hypotheses. A compacted session remembers the claim and forgets the marker |
| 4 | Have I re-opened a question §4 records as settled? | Four are settled by the final workbook. Re-litigating them wastes the audit and produces contradictory findings |
| 5 | Does every finding I have recorded carry a measurement I could re-run today? | The one test that separates a finding from an opinion |
**Drift tells — stop and re-anchor immediately if you catch yourself doing any of
these.** They are symptoms, and each has been observed in this codebase's own
history:
- Citing `apps/dma-insights/` (the legacy snapshot) as evidence the live system has something
- Writing "836 subcapabilities" or "17 categories" — the retired counts
- Auditing for the 13 MECE dimensions, which the final workbook has removed
- Reporting a gate as working because a test passes, without checking the test can fail
- Producing a finding whose measurement is a description rather than a command
- Softening a verdict instead of recording `BLOCKED` — the audit equivalent of the Rebuttal rule *"Reject means drop or re-rank, never soften the wording"*
- Summarising a section of this prompt back to yourself instead of re-reading it
**Budget and checkpoint.** Mirror R27: at every phase boundary, and whenever the
context feels tight, append every open row's current state and **stop cleanly**
rather than pushing on. A checkpointed audit resumes; an exhausted one repeats
work and contradicts itself. State plainly in your handoff which phase you
reached and which ids are open.
**Model change mid-audit.** If the serving model changes, record it as an
`ANCHOR-` row. Do not re-verdict completed checks — re-verdicting from a new
model without new measurement is drift wearing the costume of diligence. Continue
from `open:`.
---
### What "complete" means
Three conditions, all of them:
1. **Every ledger id** is `DONE`, `BLOCKED` or `NOT_APPLICABLE`, and no `DONE` row fails the ≥30-character measurement test.
2. **Every deliverable item** in §8 is written — all fifteen, including the ones that are uncomfortable: the refuted leads, and what you could not determine.
3. **Every `BLOCKED` row names what would unblock it.** A blocker without a remedy is an unanswered question presented as a result.
Report the ledger counts in the deliverable. An audit that says "complete"
without them is asking to be believed rather than checked, which is the failure
this whole document exists to prevent.
---
## 1. The three facts that dominate this audit
Establish these first. Everything else is scoped by them.
### 1.1 The human is the current safety net, and the plan removes them
Read the PR #2 description on the default branch. Its central admission:
> *Every defect below was reported from a **rendered page**, by a person, after
> this connector had said PASS. The contract was satisfied and the page was
> still wrong.*
Thirteen defects, all found by a human reading output that had already passed
every gate. **The target architecture deletes that human.** So the real
question behind every check below is: *which of those thirteen defect classes
would a gate catch today, and which would now ship silently?*
Build that table. It is the single most valuable artefact you can produce.
For each of the thirteen: the gate that now catches it (name it and prove it
fires), or **nothing does**.
### 1.2 A headless session cannot run web research
`plugins/dma-insights/scripts/agent_run.py` — the sanctioned headless dispatch
(`claude -p --agent dma-insights:<name>`) — carries this preamble, verbatim:
> *You carry the DMA Insights connector tools but **NOT** the claude.ai
> enrichment connectors (Clay, Exa, Tavily, Vibe-Prospecting, Indeed). Where
> your rulebook requires an external search you cannot run, do NOT fabricate
> and do NOT skip silently: add the exact query… to a `search_requests` array…
> The orchestrating session runs them through the real connectors, registers
> what they return, and re-invokes you.*
It also notes trigger-fired sessions carry Bash but **no Agent tool**, so the
produce → challenge → consolidate routing cannot fan out in-process.
`dma-research` is search-saturated. The final workbook's `DQ_Bank` carries
**4,255 diagnostic questions — five per subcapability across 851 subcaps** — and
each fires at least one search, before the proxy and negative-finding ladders add
more. (Do not quote the installed v2.3 figure of 6–10 queries per subcap across a
10-tier plan: that is the superseded query model. The live shape is five facets
per subcap plus a category integrating question.) If the headless child cannot
search, the research stage cannot run headless without an orchestrator that can.
**This is the pivotal enablement question of the whole audit.** Determine
precisely:
- Can a Routine's *top* session hold the enrichment connectors? (Routine
  creation accepts a `connectors` grant — establish whether that reaches a
  fired session, and whether it survives to a dispatched child.)
- If only the top session has them, what is the actual loop — how many
  dispatch/re-invoke round trips does one assessment need at 851 subcaps ×
  6–10 queries, and is that tractable inside a Routine's execution budget?
- What happens today if a headless child needs a search and no orchestrator is
  listening? Does it emit `search_requests` and halt, or does it proceed with
  a thinner evidence base and no one notices? **Test this; do not reason about
  it.** The failure mode that matters is the silent one.
- Note honestly: in *your* session, Slack MCP tools may be available. **An
  agent session holding a Slack tool is not the product having a Slack intake
  path.** Do not confuse the two.
### 1.3 The installed research skill is two major versions behind the real one
**The plugin ships a `dma-research` that is not the skill the practice runs.**
Measured on the default branch against the owner-supplied `dma-research.skill`
archive:
| | Installed (`plugins/dma-insights/skills/dma-research/`) | Supplied archive |
|---|---|---|
| Version | **v2.3** | **v4.2** (CHANGELOG) — SKILL.md banner still reads *v3.0* |
| Files | 26 | 94 |
| Taxonomy | **~836 subcaps, 17 categories** | **851 subcaps, 16 categories, 9 sub-verticals** |
| Knowledge graph (`kg/`) | absent | 16 category packs, semantic index, SV binder, source catalog |
| MECE DQs, `dq_facet`, Stage-2a, `floors_gate`, negative-finding ladders, `ledger.jsonl`, `challenge_verdict`, `kg_reader`, `proxy_escalation`, `insight_card` | **0 hits each** | all present, gate-enforced |
The installed version uses the **wrong taxonomy** — 836/17 is the v5.0 count,
and the 16-category adjudication is settled (user-confirmed 2026-08-04). It has
**none** of the MECE diagnostic-question machinery and **none** of the
reasoning-challenge machinery the owner is asking you to audit.
Three consequences, all of which shape the whole audit:
1. **Auditing the installed skill measures the wrong artefact.** **Stages 5 and 6** of §3 below are written against the **supplied v4.2**, because that is the intended system. Where you test the installed one, label the finding as version drift, not as a design flaw.
2. **The single largest enablement gap may be a packaging problem, not an engineering one** — the reasoning rigour the target architecture needs largely *exists*, and is not shipped. Establish exactly what it would take to land v4.2 in the plugin: manifest wiring, script dependencies (`scripts/requirements.txt`), the `kg/` build artefacts, and whether `package_plugin.py`'s validator accepts a skill of 94 files with a compiled knowledge graph.
3. **Everything downstream inherits the wrong universe.** `dma-assessment`'s description also still says "17 categories / ~836 subcapabilities". Determine whether the wrong counts are only description text or reach the coverage maths — a coverage gate computed against 836 passes while 15 cells go unresearched.
Also record, as findings in the supplied skill itself:
- **Internal version inconsistency** — SKILL.md header says `v3.0`; CHANGELOG's top entry is `v4.2`.
- **Gate id `G10` is overloaded.** `references/protocols/safeguard_gates.md` defines G10 as **"No Toolkit Blending"** (a BLOCK gate on binding one sub-vertical toolkit). But Rule 16 and `scripts/build/dq_generator.py` cite **G10** for **platform-agnostic DQs (no vendor names)**, and `scripts/build/validate_kg.py:93` implements *that* meaning. Two different gates, one id. Verify, then judge which is the mis-citation — a gate id that means two things cannot be reasoned about.
## 2. Ground rules
### 2.1 The five verdicts
Every check lands in exactly one. The last two carry this audit.
| Verdict | Means |
|---|---|
| **PRESENT–SOUND** | Built, and you proved it works by running it, or by reading its test and confirming the test can fail |
| **PRESENT–DEFECTIVE** | Built and wrong. Name the defect, the measurement, the blast radius |
| **PRESENT–HUMAN-DEPENDENT** | Works **only** because a person does a step, checks a result, or moves a file. **In the target architecture this is a blocker.** Name the human and the step |
| **ABSENT–BY–DESIGN** | Not built, and the repo says so — a charter line, a rejected-alternative note, an open decision. Cite the line |
| **ABSENT–UNNOTICED** | Not built, and nothing acknowledges the hole. **Highest-value finding class** |
### 2.2 Authority order (from `CLAUDE.md`)
1. **Backend Schema** (`docs/text/DMA Insights - Backend Schema.txt`) — tables, enums, constraints, DDL
2. **TRD** — architecture, tiers, connector contracts, validation, GCP mapping
3. **Surface Specification** — payload field contracts. *Payload shapes are law; never invent a field*
4. **Implementation Plan** — stage order and per-stage QA
5. **PRD** — intent
6. **QA Report** — already-resolved contradictions. **Check here first when two sources disagree**
7. **Prototype** — layout, interaction, rendering, band-resolver boundaries only
A conflict this order does not resolve is a finding. Record it; never pick a
side silently.
### 2.3 Four traps that will produce false "it exists" findings
**(a) The legacy snapshot.** `apps/dma-insights/` is a *reference-only* snapshot
of the prior app (2026-07-16) — "do not extend it, do not import from it." It
is roughly half the repo's Python and answers almost every grep. Several
target-flow capabilities exist **there and nowhere else**. Treat a hit under
`apps/dma-insights/` as evidence of **absence** in the live system unless you
find the live counterpart under `apps/{api,mcp,worker,web}`, `packages/shared`,
`migrations/`, `plugins/dma-insights/`, `scripts/` or `infra/`. Also,
`apps/dma-insights/startup-data/` is 93 clients of **content** — a term hit
there is client data, not a feature. Prefix searches:
```bash
grep -rn PATTERN apps/api apps/mcp apps/worker apps/web packages migrations plugins scripts infra
```
**(b) "issue register" means two unrelated things.** The user's deliverable is
the **governance** issue register — `issue_register.csv`, sequential `ISS-XXX`
ids, from `dma-governance` (schema at
`skills/dma-governance/schemas/issue_register.schema.json`). The connector's
`context.issue_register` (gated by **CG-46**) is a completely different object:
the **client's own open matters** — regulatory and business issues that cap
named cells. They share a name and nothing else. A grep for `issue_register`
finds the wrong one and will make you declare the deliverable built.
**(c) `EVIDENCE|HYBRID|INFERRED` in `apps/mcp/dma_mcp/gates.py` is a
`posture_basis` chip on a payload field.** It is not the PUBLIC/HYBRID/INTERNAL
evidence mode of Stage 3. Different concept entirely.
**(d) The installed `dma-research` is not the real one** (§1.3). Grepping
`plugins/dma-insights/skills/dma-research/` for MECE, Stage-2a, floors or
challenge machinery returns **zero** — that is version drift, not a design
absence. Audit Stages 5-6 against the **owner-supplied v4.2 archive**, and state
which artefact each finding came from. Getting this backwards produces a report
saying the practice has no reasoning discipline, which is false and would send a
rectifier to build what already exists.
### 2.4 Evidence discipline
Match the standard the system enforces on itself in `record_finding`: a
`measurement` is the command, query, HTTP status or count **with its
denominator**, minimum 30 characters.
- "Absent" means you searched and can show the search — state the command and its zero result.
- "Present" means you ran it, or read a test and confirmed the test can fail.
- Counts carry denominators: "76 of 105 client folders", not "most".
- A passing test is not proof of a behaviour until you check the test **exercises** it. This repo has been bitten precisely there: the `python-tests` CI job once ran worker and mcp only, and the API's 251 tests had never run in CI at all.
- A skipped test is not a passing test. The suite's skip ceiling is 12 for that reason.
### 2.5 Leads are hypotheses, not findings
Items marked `[LEAD]` come from an earlier pass. **Verify or refute each one
yourself** and report the refutations. An audit that inherits another's errors
has laundered them.
## 3. Stage-by-stage enablement audit
For each stage: verdict, findings, **and the specific change that would make it
headless-capable**.
### Stage 1 — Request ingestion (Slack, or a typed Routine)
**Target:** a request enters from Slack deal desk or from the owner typing into
a Routine. The Drive watcher is retired.
`[LEAD]` No Slack ingress exists in the live pipeline. Intake is
`dmai-package-scan`, `*/30 * * * *`, firing the `dmai-worker` Job against
`INTAKE_FOLDER_ID` (the "General DMAs" tree,
`1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo`, set in `infra/deploy.sh`). **Verify.**
Audit:
- **Inventory the Routine mechanism as an intake front door.** `routines.json`, `scripts/setup_routines.py`, `scripts/agent_run.py`. A Routine already fires a headless session on a schedule. What is missing between that and "the owner types a request and it runs"? Be concrete: a request payload shape, a place to put it, a way to pass it to the fired session, a way to see it ran.
- **What retiring the Drive scan actually costs.** The scan is charter-**mandatory** — "the package scan is how runs come to exist." Removing it means something else must create `runs` rows, allocate `run_seq`, resolve the entity, and stage artefact bytes to GCS. Enumerate every side effect of the scan that a Slack/Routine path would have to replicate. Read `apps/worker/job_main.py` end to end for this; it is the specification whether or not anyone wrote one.
- **Two irreversibilities.** `source_cell` and GCS artefact bytes **cannot be backfilled**, and the ingested tier is **read-only once scanned**. A request-driven intake that creates a run before the artefacts exist may create an unfixable run. Trace whether the new path can avoid that.
- Failure handling: `MAX_INGEST_ATTEMPTS`, `PACKAGE_FAILURE_KIND`, `intake_status.py` states (`no_run`, `run_unparsed`, `parsed_unsynthesised`, `synthesised_unpromoted`, `promoted_current`, `promoted_superseded`). Which of these survives a change of front door? Who sees a stuck request when no human is watching?
- If Slack is the front door: authentication, authorisation (**who may request a DMA?**), rate limiting, and replay. A Slack message is untrusted input that would trigger an expensive autonomous job.
### Stage 2 — Triage and duplicate detection
**Target:** detect duplicate requests; put clarifying queries back to the
requestor.
`[LEAD]` No requestor, ticket, or request entity exists in the live pipeline —
so there is nothing to triage and nobody to ask. Existing dedupe operates on
**evidence links and content hashes**, not requests. Known open item
**MEM-0092: 109 of 287 pending runs duplicated.** **Verify, and re-measure.**
Audit:
- Is the 109/287 figure still current? `list_pending_runs`, `scripts/ingestion_status.py`, `scripts/synthesis_queue.py`. A stale number in the memory is itself a finding.
- `package_key()` in `apps/worker/job_main.py` documents two **distinct** production folders both named "Corporate America Credit Union - DMA". Read it. What happens on a name collision, and what happens when one client is requested twice under different names?
- `apps/worker/dma_worker/entity_resolution.py` — what does it match on, and what is the **false-merge** risk? A false merge blends two institutions' evidence *upstream* of the `foreign`-evidence check, so invariant 4 would never see it. Establish whether that is true.
- **"Sharing further queries to requestor" is a conversation, and the target architecture has no human in the session.** Design question the audit must answer: does the Routine ask and wait (and where does the answer land), or does it proceed on assumptions and record them? What exists today to support either? A clarification loop with no addressee is the shape to look for.
### Stage 3 — Classify PUBLIC / HYBRID / INTERNAL
**The supplied v4.2 research skill already has this concept** and branches on
it: Rule 12 fires a **5-Layer Analysis (HYBRID/INTERNAL)** — Explicit → Implicit
→ Absence → Contradiction → Strategic — and Rule 20's negative-finding ladder
adds an internal rung "**+internal in HYBRID**". So the classification is not
missing from the *practice*; establish whether it is missing from the *product*.
`[LEAD]` In the live application the concept appears to live **only in the
legacy snapshot** —
`apps/dma-insights/backend/app/services/parsers/client_profile.py`
(`Evidence Mode: (PUBLIC|HYBRID)`) and `package_persist.py`
(`PUBLIC/RESEARCH_HANDOFF`, `HYBRID`, `INTERNAL+PUBLIC`). A search of the live
tree for `evidence_mode` appears to return nothing. **Verify.** Remember trap
2.3(c).
Audit:
- Does the **Backend Schema** (authority 1) define an evidence-mode or assessment-type column? If the schema defines it and the code ignores it, that is worse than absence — record it that way.
- If absent live: what silently substitutes? Every assessment is being treated as one mode. Which, and is that the safe default?
- Who decides the mode in an unattended run? A classification requiring human confirmation is PRESENT–HUMAN-DEPENDENT and must be designed out or explicitly kept as the one human gate.
- Do `dma-research` and `dma-assessment` branch on evidence mode at all? If not, the classification would be decorative even once captured.
- **Do not mistake serve-time redaction for intake-time classification.** Invariant 5 strips `internal_only` for customer audience and `entity_ids` in cohort patterns for *every* audience — server-side, in the app. That protects the six surfaces. It does **not** protect a `.docx`, an `.xlsx`, or a `.csv`. See Stage 8.
### Stage 4 — Load internal documents
Audit:
- Is there any internal-document ingest distinct from public research? If Stage 3 is absent, this cannot be gated — say so and follow the consequence.
- How is internal evidence **marked** so redaction can act and a reader can tell provenance? Check tiers T1–T5, ERS, and claim classes. The installed v2.3 skill says "Flag in workbook Column U when internal evidence contradicts public evidence" — but **contract v3 forbids any column beyond K**, so that flag now has nowhere to live. Establish where an internal-vs-public contradiction is recorded under contract v3 (`Evidence_Detail`? `Negative_Findings`? the working area that gets stripped?), and whether it is machine-readable downstream or lost.
- Invariant 4 requires every cited id to resolve, belong to this entity and run, and carry a **verbatim 50–500 character excerpt**. Can an internal document satisfy that when the artefact is not fetchable by the connector? Follow one internal-sourced citation end to end. If internal citations systematically fail the evidence gate, internal evidence is being silently dropped and HYBRID assessments are thinner than they appear — quantify.
- Credentials: `plugins/dma-insights/docs/secrets.md`. In an unattended run, whose credential opens the internal document?
### Stage 5 — Per-subcap research and the **MECE diagnostic questions**
Audit this against the **supplied v4.2** skill (§1.3). This is the deepest
section; give it the most time.
#### 5.1 What MECE actually means here — correct your prior
The MECE partition is **within one subcap, across five evidence facets** — it is
*not* a partition of the taxonomy across subcaps. Rule 16:
> **5 MECE diagnostic questions per subcap** — five OPEN questions
> (`works` / `fails` / `value` / `contradicts` / `corroborates` — never yes/no),
> rendered in dma-p1 prose, **platform-agnostic** (no vendor names) and
> **temporal**. The four primaries fire as **one volley** — contradictory
> evidence is checked at once. `corroborates` fires once a dominant claim
> exists. Every fact is tagged `dq_facet` and, when dated, `event_date` +
> `temporal_role`. Questions are **tailored at runtime** —
> `kg_reader briefs --sv {SV} --context ctx.json` binds the sub-vertical lexicon
> and client specifics; never fire the generic render on a classified engagement.
So there are two distinct MECE properties, and both need testing:
- **Within-subcap (the five facets).** Are they *exhaustive* — is there evidence
  about a subcap that fits none of the five? And *exclusive* — can one fact be
  legitimately tagged into two facets, and if so what breaks?
- **Across subcaps.** Rule 22's **anti-clone guard** is the mechanism:
  *sibling subcaps sharing >60% identical evidence IDs across ≥3 rows = validator
  warning.* Note it is a **warning**, not a block. Establish what happens when it
  fires in an unattended run: does anything stop, or does the category close with
  smeared evidence?
Read: `scripts/build/dq_generator.py`, `scripts/build/validate_kg.py`,
`scripts/build/build_kg.py`, `references/specs/research_brief_spec.md`,
`kg/packs/P*/P*C*.json`, `scripts/engine/kg_reader.py`.
#### 5.2 Measure the DQ set against the real denominator
- **851 subcaps** = 686 universal + 165 SV-scoped overlays, across **16
  categories** and **9 sub-verticals** (CU, RB, CL, CIB, AM, RIA, IC, IB, FC).
  Confirm the KG carries a five-facet DQ set for **every** one. Report the
  fraction with all five, the fraction with a facet missing, and the fraction
  whose rendered text is byte-identical to a sibling's.
- **The generic-render trap.** Rule 16 forbids firing the generic render on a
  classified engagement. What *enforces* that? If a run can proceed with generic
  DQs, the whole SV-tailoring layer is optional in practice — and in an
  unattended run nobody will notice the questions were never client-specific.
- **G10 platform-agnostic.** `validate_kg.py:93` checks no tech-vocab
  vendor/product name appears in any question text, at **build time only**
  ("Not run during engagements", per the script table). A build-time gate does
  not protect a runtime-tailored question — `kg_reader briefs --context ctx.json`
  injects client specifics *after* validation. **Can client context reintroduce a
  vendor name into a DQ after G10 has passed?** Test it. If yes, that is a
  headline finding: the gate cannot see the artefact that is actually asked.
- **Sub-vertical overlay scope** derives from the subcap ID suffix, "never the
  Tier cell". Verify the binder honours that, and that a variant plus its base
  cannot both enter one engagement set.
- **Open-question enforcement (G7).** DQs must never be yes/no. Is that checked
  mechanically, or asserted? A yes/no DQ collapses the evidence space and is the
  most direct route to a one-sided conclusion.
#### 5.3 The volley, and the fidelity chain
The four primaries fire **as one volley** precisely so contradiction is checked
*at the same time* as confirmation, rather than after a claim has hardened. That
design intent is the thing to test.
- Does anything **prove the volley actually fired all four**? Rule 28 requires
  `dq_answers` — one answered, `[E-xxx]`-cited line per facet — and Rule 27's
  `floors_gate --require-synthesis` FAILs on "missing any of the 5 `dq_answers`".
  Confirm that gate fires on a real deficient record; do not read it and believe it.
- **`contradicts` is the load-bearing facet.** Rule 25 states the contradicts
  probe fires for **every** subcap regardless of sweep coverage. Verify. Then
  check the subtler failure: the 7-dim challenge FAILs `counter_evidence` when
  "q.negative never fired, **or fired and a hit was ignored**". Which of those
  two is mechanically detectable, and which relies on the model's own honesty?
  The second is the one that fails silently.
- **Facet-coverage lying.** `synthesis_quality` FAILs when "facet_coverage claims
  contradict the ledger (e.g. `contradicts:"checked_none_found"` but
  `q.contradicts` never ledgered)". This is a genuinely good self-consistency
  check — confirm it is implemented and can fail, because it is the main defence
  against a synthesis that *claims* the volley it never fired.
- **Query fidelity.** Sample 20–30 subcaps across all four pillars: read the
  brief's DQs and its pre-built queries, and judge — *would an answer to this
  query be an answer to this DQ?* Report the drift rate with its denominator. A
  query that drifts returns evidence answering a different question, mapped back
  to the original subcap and cited — a wrong ceiling with a valid citation,
  invisible to every gate that checks resolution rather than responsiveness.
- **`map-fact` mapping quality.** Rule 26 maps sweep facts to subcaps via a
  TF-IDF semantic index over all 851 briefs. Sample its output: how often does a
  fact land on a subcap it does not actually bear on? Rule 11's "one fetch → many
  subcap facts" multiplies any systematic mapping error across the taxonomy.
### Stage 6 — Synthesis, reasoning traps, and the challenge machinery
The supplied v4.2 has a serious, gate-enforced challenge layer. Your job is
**not** to praise it. It is to find where a wrong conclusion still survives, and
to establish which gates degrade to nothing without a human.
#### 6.1 The named traps — enforced, or written?
For each: find the enforcement, prove it can fail, and say what happens when it
fires in an unattended run.
| Trap | Rule / gate | What you must establish |
|---|---|---|
| Premature scoring | R1 — ceiling bands only, never M1–M5 | What stops a score leaking into the handoff? |
| Unlabeled assertion | R2 — `FACT`/`INFERENCE`/`HYPOTHESIS`/`CEILING_ESTIMATE` | Validated enum or free text? |
| **Presence ≠ Utilization** | R5 + `URF-01..06` + G11 | The dominant over-estimation trap. Does anything *detect* a presence fact scored as utilization, or only ask for a flag? |
| Single-source dependency | R6 — `web_search` ≥70% and first; `SG-01..06` | Is the 70% floor measured, or aspirational? |
| Tier inflation | `tier_hygiene` dim — "vendor PR as T2" | Measured misassignment rate on a real ledger |
| Evidence smearing | **R22 anti-clone**, >60% shared ids over ≥3 rows | It is a *warning*. What consumes it? |
| Thin evidence | R18/R29 floors — ≥3 items / ≥2 sources / ≥1 T1–T3 per subcap; ≥20 items per category; category ≥0.80, engagement ≥0.85 | Does `floors_gate.py` actually block Phase C? Force a below-floor run |
| False absence | R20 ladder rungs 1–4; **R30 proxy escalation** — 6 proxy classes, ≥3 or `PROXY_GAP` | A proxy hit must become INFERENCE with a validation question, "never FACT, never silently not-found". Test that it cannot become FACT |
| Stealth-shallow close | R32 — `closed_below_floor`, `absence_undeclared` | Both are described as *mechanically* detected. Verify both |
| Analyst shorthand | R31 — `shallow_reading`, `no_deep_dive` | Can a gate really tell a reading from a label? Probe its false-negative rate |
| Stale evidence | R31 — `stale_sources_no_currency_probe` at >24 months vs run-date | Is run-date the real today, or a frozen constant? |
| Evidence fishing | R28 — fetched source yielding <3 facts needs `thin_source_reason` | Does the reason get *judged*, or merely be non-empty? |
| Restatement as insight | R33 — composer rejects patterns lifting a 12+-word run verbatim | A 12-word window is a crude proxy for paraphrase. What does a lightly reworded restatement do? |
| Uncertainty collapse | `uncertainty_framework.md`, ±0.8 cap, `ceiling_band_delta` (0/−1/−2, **down only**) | Enforced at handoff? Does a capped band still render as a band? |
#### 6.2 The challenge layer — where it is strong, and where it is circular
Read `references/protocols/challenge_protocol.md` and the cards in
`references/cards/`. The structure:
- **Subcap challenge, 7 dimensions** — `evidence_diversity`, `tier_hygiene`, `recency_decay`, `m_delta_fit`, `counter_evidence`, `precedence`, `synthesis_quality`. Any FAIL ⇒ overall FAIL. ≥2 CONCERN ⇒ CONCERN, delta −1.
- **Category challenge, 5 dimensions** — `coverage_honesty`, `floor_compliance`, `conflict_resolution`, `single_source_concentration` (>40% one domain), `theme_coherence`.
- **Stage-2a contingency**, cases **A–H**, `scripts/engine/contingency.py`, fed `contradicts_strength`; a hit forces divergence handling (Case H).
- **Resolution loop** — FAIL on `counter_evidence`/`synthesis_quality`, or `found_open`, or Stage-2a divergence → fire `clarification_route` queries → re-run Stage-2a → re-challenge. *"Never exit via silence — an unexamined conflict is a research failure, not a finding."*
- **Append-only ledger** (R21) — conflicts preserved, never resolved by deletion.
Now attack it:
- **The challenger is the same model as the author.** A self-challenge pass shares the author's blind spots by construction. What in this design gives the challenge *independent* purchase — a different card, a different context window, a different model tier? Compare with the plugin's own answer elsewhere: `learning-grader` and `learning-testgen` are independent **by construction** because they carry no write tools. Does the research challenge have an equivalent structural guarantee, or only an instruction to be adversarial?
- **"Max 2 iterations; unresolved ⇒ `provisional: true` + ceiling_band_delta."** So an unresolved challenge does not block — it *degrades and proceeds*. In an unattended run, who ever reads `provisional: true`? Trace whether provisional status survives into the handoff, the workbook, the report and the app surfaces, or dies at the skill boundary. **If it dies, the challenge layer is advisory in production.**
- **`ceiling_band_delta` shifts DOWN only (0/−1/−2).** Deliberate conservatism — but it means a challenge can never correct an *under*-estimate. Combined with R30's "proxy hit ⇒ INFERENCE, never FACT", is there a systematic downward bias? That is not necessarily wrong, but it should be a stated design choice rather than an emergent one. Establish which it is.
- **Circular corroboration.** `corroborates` fires once a dominant claim exists — i.e. *after* the claim. Does anything check that two "independent" corroborating sources do not trace to one origin (a vendor press release and the trade-press article quoting it)? `single_source_concentration` counts domains, which will not catch this. Design the probe and run it.
- **Conflicts parked as `open_conflict`.** The exit requires a tie-breaker attempted plus a client discovery question logged. In an unattended run **there is no one to ask the discovery question.** What is the terminal state of an `open_conflict` when no human ever answers? Does the assessment publish with the conflict unresolved, and is that visible on the surfaces?
- **Batching.** Subcap challenges are batched per capability "to bound cost (~150–250 tok/subcap)". Does batching dilute scrutiny — is a 12-subcap capability challenged as rigorously as a 3-subcap one? Measure verdict distribution against batch size.
- **`orient.py` skeletons.** R32 requires syntheses be written by filling `orient.py --skeleton <SID>` templates, with `STUB_` values failing the gates. Good. But a template invites *form-filling*: does anything detect a synthesis that is structurally complete and substantively empty — every field populated, nothing actually reasoned? This is the trap a schema cannot catch, and the one an unattended run will produce most often.
#### 6.3 The trap that beats every gate
Construct the adversarial case explicitly and see how far it travels: a
conclusion that is **internally consistent, fully cited, correctly tiered,
ladder-complete, challenge-passing — and wrong**, because the evidence answers a
different question than the DQ asked (Stage 5.3), or because presence was read as
utilization, or because both corroborating sources trace to one origin.
Walk it from evidence through synthesis, challenge, floors, handoff, scoring and
onto a rendered surface. **Name every gate it passes.** That path is the
audit's most valuable single output, because it is exactly what an unattended
pipeline will ship.
#### 6.4 Where synthesis notes live
R32 is emphatic: *"conversation memory is DISPOSABLE in Cowork; disk is truth"* —
every session opens with `orient.py --run $RUN` and closes with compact → floors
→ orient rerun. The append-only `01_evidence/ledger.jsonl` is the durable record.
- Is `$RUN` durable, or a container-local path? If the ledger lives only in an
  ephemeral filesystem, "disk is truth" is true only until the container exits.
  **In the target architecture the container always exits.**
- R34 notes ledger appends are `O_APPEND` atomic and ids are minted via
  `ledger.new_evidence_id(run)` under `fcntl` locking, "parallel-safe". `fcntl`
  locks are per-host. If headless dispatch ever runs on more than one machine,
  that guarantee is void. Establish whether it can.
- R23's **checksum halt** — `kg_reader.py guard` HARD HALTs on build-checksum
  mismatch. In an unattended run, a hard halt with no listener is a silent stall.
  What surfaces it?
- Does any of this reach the DMAI app, or does it stay on disk? See Stage 8.
### Stage 7 — Scoring
- **The handoff seam.** `dma-assessment` consumes `research_handoff.json` (RESEARCH_HANDOFF mode; skips Phase 1; imports `locked_peer_set[]` if present). Does a handoff written by the *current* `dma-research` satisfy the *current* `dma-assessment`? Two independently edited skills drift; test with a real handoff rather than reading both.
- **Bands.** Four bands, strict less-than, on the **RAW** score before display rounding: `<2 Activating · <3 Building · <4 Competing · ≥4 Differentiating`; null → no score. `band_t` is a four-value enum; **M5/Transformational must not exist in code, enum or prose.** *Careful:* the **rubric** is legitimately M1–M5 (a workbook scoring level) — only the **band** enum is four-valued. Confirm the DB generated column and `apps/web/lib/bands.js` agree, and that the golden-run fixture test asserting agreement exists and can fail.
- **Caps bind or decorate?** Trace one cap from the issue register through to a served number. `overview.ceilings` (O1b), G14, the ±0.8 uncertainty cap.
- **Grain** reconciles at 0.05 tolerance across pillar/category/cell. `scripts/gate_j_surface_parity.py`.
- Peer medians: computed or stored? Invariant 8 — counts are computed, never stored, where a source of truth exists.
- Run `skills/dma-assessment/scripts/validate_scoring_quality.py` and `qa_auditor.py`. **Prove they fail on bad input.**
### Stage 8 — Reports, workbooks, and the issue register: **the publication gap**
This is the largest *net-new build* the target architecture implies, and the
audit must size it precisely.
`[LEAD]` The connector's **33 tools submit JSON page payloads only.** There
appears to be **no tool that publishes an `.xlsx`, a `.docx`, or the governance
`issue_register.csv` to the app.** **Verify.** Then note the constraint that
makes this hard rather than easy:
> The connector **explicitly rejected a by-reference submit** (producer writes
> to GCS, connector reads). Read the rationale in `apps/mcp/README.md`: it does
> not reduce the bytes a producer must emit; it requires the producer to hold a
> bucket credential the connector would then trust — *invariant 2 read
> backwards*; and the practical form of that credential is a signed URL, i.e. a
> secret in a URL that lands in transcripts and logs. `dmai-mcp` holds only
> `objectViewer` on the artefact bucket, with `dmai-worker` its only writer.
So the audit must answer, for each of the four new deliverables:
| Deliverable | Questions |
|---|---|
| Governance **issue register** (`ISS-XXX`) | Is it structured enough to serve (schema exists)? Which surface renders it? Is it internal-only, and what enforces that? Does it collide with `context.issue_register` (CG-46) in naming, routing, or a reader's mind? |
| **Research workbook** (.xlsx) | Bytes, not JSON. Does it go in GCS with a serving route, or is it re-expressed as payload? Who may download it? |
| **Scoring workbook** (.xlsx) | Same, plus: it holds the scores the six surfaces already serve. What reconciles the two representations? A workbook that disagrees with the heatmap is worse than no workbook |
| **Client research report** + **assessment report** (.docx) | Client-facing. **Invariant 5's redaction walker protects payloads, not documents.** A `.docx` leaves the app's audience machinery entirely. What stops internal-only content reaching a client here? |
Then:
- Does invariant 2 ("content enters only through the connector") **permit** file publication at all, or does enabling this require an adjudicated change to the charter? If the latter, say so plainly — that is an owner decision, not an engineering one, and the audit's job is to surface it, not settle it.
- Does invariant 3's atomicity extend to the new artefacts? Today promotion is all-six-pages-or-none. Should a run be promotable with surfaces but no workbook? State the options; do not choose.
- Citation validation: `(E-xxx, Source, Tier, Date)` is mandatory in workbook and report. Measure what fraction of citations in a real report resolve to a registered evidence id.
- `dma-assessment` STEP 0 retrieves `DMA_Assessment_Report_Template.docx` "from the project knowledge base" — an **external dependency with no version pin in the repo**. In an unattended run, what happens when it is missing or has changed?
### Stage 9 — Finalise and publish
- **Atomic promotion**: all six pages, one transaction, `SELECT … FOR UPDATE` on the run row, ordered writers. The **writer registry is an ordered list of 34 section writers** and order is load-bearing (unordered acquisition deadlocks under concurrent promotes). Find the stability test; confirm it can fail.
- Retention: promoted staging rows are retained so one page can be fixed and re-promoted. Verify, and verify `get_staged_payload` reads a superseded submission back (its documented recovery route).
- **A failing SG discloses and still promotes; a failing evidence reason never does.** Test both directions.
- Rejection ledger — `scripts/gate_k_rejections_return.py`, `list_open_rejections`. Its failure mode is **silent** (the queue simply stays empty). In unattended operation this is the only thing that makes a refusal visible. Prove it is wired.
- What marks a DMA **final**? Is there a terminal state, or does finality mean "someone stopped working on it"? Trace `runs.status`.
- `withdraw_run` removes a run from `serving_directory`; confirm `is_active=false` alone does **not** (the documented trap: the directory keeps publishing the client's name beside pages that 404).
- Charter: **not done until live in prod.** `scripts/verify_deployed.py` byte-compares the deployed bundle; `infra/deploy.sh` must call it. Run it if you have credentials; if not, say so rather than inferring a production state.
## 4. The seven owner-specified checks
Seven areas the owner named directly. Each gets its own verdict and its own place in the deliverable. Findings here outrank the generic sweep.
**The three canonical templates are pinned.** They are Google files owned by `mishley.otiende@zennify.com`, and they are the authority for §§4.4–4.7. Read all three before starting those checks.
| Template | Drive id | Type |
|---|---|---|
| `DMA Workbook` — *DMA Scoring Workbook, contract v3* | `18IoJD5jn9aIe3E_F2omxqIZrjnHQwfR2pD0-_nUe5zc` | Sheet |
| `Client_Profile_Research_Template_v8` | `142FoFcgs2-zzMm2_y4ykQW_gSUVbIOWSMHV_sgITs0Y` | Doc |
| `DMA_Assessment_Report_Template_v8` | `1FPr7wNuo2-Fk7PPTvk1VkQxYBvjLbEWwU7kZQY8TuDA` | Doc |
**Use these ids and no others.** Three earlier drafts are superseded and must not be
audited against: `1gYwDYxeIWfnNcOiCzBMvw-kom9SQsvtLgb-Vc0_Knqs` (client profile),
`1DFB53Se1cz5xeqYqsjxjpAiCenZg5jdRaB5yFB336hA` (assessment report) and
`1R7H82bxPCSnzw3ygm6ty2-eltpoPHSnA8Z6ZCa2aFOM` (`DMA_Workbook_TEMPLATE`). If any
appears in the repo, the skills or a rendered document, that is a finding: a
renderer bound to a superseded draft produces an artefact nobody has approved.
**The final workbook settles four questions an earlier draft of this audit left
open. Do not re-open them:**
| Question | Settled answer, from the workbook itself |
|---|---|
| One workbook or two? | **One.** "DMA Scoring Workbook, contract v3" — a single research-stage file. The Client Profile still routes artefacts to a separate `{{RESEARCH_WORKBOOK}}` and `{{SCORING_WORKBOOK}}`; that is now a template-to-template conflict, and the workbook is the newer authority |
| Which MECE scheme? | **The five facets** — works / fails / value / contradicts / corroborates, "MECE by construction". `DQ_Bank` holds **4,255 questions = 5 × 851**. The 13-dimension scheme (EXISTENCE, OWNERSHIP, …) has **zero** occurrences. Do not audit for it |
| Who owns which column? | **Research writes A, B, C, F, G, K; assessment writes D, E, H, I, J** ("EMPTY and gray. Non-empty during research is a FAIL"). The earlier draft's "D–K all belong to assessment" is superseded |
| Which taxonomy? | `Run_Metadata` states `taxonomy_version v7.0 — 4 pillars, 16 categories, 851 subcaps`, `subcaps_universal 686`. The settled counts, asserted in the artefact |
Note what this changes: the skills say the templates come "from the project knowledge base" with no identifier. They now have identifiers. **A first-class finding is whether anything in the repo or the skills resolves to these ids** — if not, the pipeline still cannot find the templates it is required to use, and pinning them here does not fix that.
### 4.1 The entry document, and routing at three moments
**What must be true:** one `.md` loads first, stays resident, and routes an agent to the right documentation — without exceeding the size a resident file can afford.
The entry chain today, verified on the default branch:
- `plugins/dma-insights/hooks/hooks.json` fires **SessionStart** → `scripts/hooks/session_brief.py`
- That prints ~50 words: route before you produce · one surface → that page's producer → finding-challenger → page-consolidator · only surface-producer submits or promotes · read `get_memory_digest` first · end with qa-overseer · **routing table: `skills/dma-surface-production/05-lifecycle/routing.md`**
- The routed-to file is **17 KB** (`routing.md`); its siblings in `05-lifecycle/` are `1-gates.md` (**42 KB**), `surface-map.md` (18 KB), `2-versioning.md`, `client-memory.md`
Audit, at each of the three moments the owner named:
**At session start.** Does the hook actually fire in a *headless, trigger-fired* session, or only in an interactive one? The hooks are declared in the plugin manifest; establish whether `claude -p --agent …` (the `agent_run.py` path) loads plugin hooks at all. **If it does not, the routing rule never enters an unattended run** — and every dispatched producer starts unrouted. This is the single highest-value check in 4.1.
**While the session runs.** `session_brief.py` prints **only** when `source ∈ {startup, clear}`. Its docstring gives the reason:
> *resumes and compaction continuations already carry the brief in context, and re-printing it on every continuation is noise.*
Test that assumption rather than accepting it. After a real compaction, is the brief still in context? Compaction summarises; a 50-word line early in a long session is exactly the kind of thing a summariser drops. If it does drop, the routing rule is gone mid-run and **nothing reprints it** — the hook has deliberately excluded the one moment it would be needed.
**As the session proceeds into new work.** Does anything re-assert routing when the agent changes page, or when a sub-agent is dispatched? `agent_run.py` prepends a DISPATCH-MODE preamble, but that preamble covers connectors and output format — **not** the routing table. Check whether a dispatched producer is told how to route, or only how to report.
**Size.** Nothing enforces a limit: `plugins/dma-insights/scripts/audit_skills.py` checks broken references and that scripts answer `--help`, and has **no word or line ceiling**. Measured:
| SKILL.md | words | lines |
|---|---:|---:|
| `dma-first-call-deck` | 9,091 | **903** |
| `dma-assessment` | 5,986 | **852** |
| `dma-surface-production` | 5,138 | **587** |
| `dma-research` (installed v2.3) | 4,439 | 629 |
| `dma-rectifier` | 3,868 | 413 |
| `dma-governance` | 2,133 | 332 |
| *supplied `dma-research` v4.2* | *5,065* | *409* |
Against the ~500-line working guidance for a resident SKILL.md, three exceed it and one is near double. Establish the real ceiling for this harness, measure each file against it, and say which are over. Then ask the harder question: **is `routing.md` at 17 KB a routing table or a second manual?** A router that must itself be read in full has not reduced anything. Judge whether an agent can reach the right rulebook from the brief plus a scan, or whether it must read 17 KB first — and note that `1-gates.md` at 42 KB sits behind it.
**Reachability.** Pick five plausible tasks (repair one card; a failed CG-30; author the context page; a rejected insight card; resume after compaction). For each, trace the path from the 50-word brief to the file that answers it. Count the hops and the bytes. Any task needing more than two hops is a routing failure, whatever the table says.
### 4.2 Drift, memory, resumability, compaction
**What must be true:** the workflow resists model drift; memory is updated continuously and recalled on demand; a run whose tokens ran out can be resumed from its last state; compaction is used deliberately rather than survived.
**Correct an earlier reading before you start.** A previous draft of the workbook
carried a **Pipeline state** sheet (`CURRENT STAGE`, `Last written by`, `Blocked`,
a stage table with `May write` and `Gate that closes it`). **The final workbook
has removed it.** There is no longer a workbook-resident state machine, and no
`Blocked` cell for an operator to read. Do not audit for one; audit the
consequence — the run-state story now rests entirely on the skill side, and the
workbook contributes only three anchors:
- `Run_Metadata.run_id`, which the validator compares to `run_manifest.run_id` for equality — *"a workbook carrying another run's id is the one error nothing downstream can recover from"*
- `Run_Metadata.kg_checksum`, where **`kg_reader guard` verifies on resume and a mismatch is a hard halt** — the single strongest resume anchor in the system
- The **CHAIN INTEGRITY** sheet, whose checks are live formulas rather than typed values: scored rows vs `selected_subcaps`, facts registered, subcaps synthesised vs rows passing the floor, negative findings per ladder-complete absence, dated facts on the timeline, `NO_EVIDENCE` rows each needing a negative finding or remediation, and questions available per subcap (expected 5). *"Counts are formulas, so they cannot flatter the run."*
So the question is no longer "which of two state machines wins". It is:
- **Does the skill-side state (R32's `orient.py --run $RUN`, R21's append-only `01_evidence/ledger.jsonl`, R27's rule that a subcap is closed only when the ledger holds its synthesis, negative or remediation record) agree with CHAIN INTEGRITY?** They are computed from different substrates — one from JSONL on disk, one from spreadsheet formulas. Force them apart on a real interrupted run and see whether anything notices.
- **`kg_checksum` is a resume anchor that survives the container**, because the workbook is a Drive file. Establish whether `orient.py` actually reads it, or whether only `kg_reader guard` does — and what a resumed Routine on a fresh container can reconstruct from the workbook alone.
- **Nothing now carries `Blocked`.** In an unattended run, what states a run is stuck and why? If the answer is CHAIN INTEGRITY's `{{OK | INVESTIGATE}}` verdict cells, establish who or what reads them.
**Drift.** Two distinct meanings; separate them.
- *Instruction drift within a run* — R23 **path citation + checksum halt**: every phase action names the `kg/` or `references/` file it executed from, and `kg_reader.py guard` HARD HALTs on a build-checksum mismatch. The Client Profile template adds a second lock: the catalogue **content hash** (SHA-256 over catalogue rows, computed at load) is written into `Handoff_Lock`, and *"the assessment stage compares against it and refuses to score if the catalogue has moved."* Verify both fire. Then ask the unattended question: **a hard halt with no listener is a silent stall.** What surfaces it?
- *Behavioural drift across runs* — the findings memory (`record_finding` → `record_refinement` → `resolve_finding` → `report_recurrence`). `report_recurrence` is the load-bearing one: a fix that did not hold. Check `get_memory_digest`'s `recurrences_in_window` is populated and that anything reads it.
**Drift in the counts — the template already solves this and the skills do not.** The Client Profile's Document Control block requires pillar, category, capability, subcapability, tier and gate counts to be *"derived by counting catalogue rows at render time. **Never write one as a literal in prose.**"* That rule, if enforced, ends the 836/851 and 16/17 problem at the document layer. Establish whether the renderer enforces it, and whether the same rule reaches the skills — which still carry the literals in their descriptions.
**Resumability — the token-exhaustion case the owner named.** R27's budget rule: check `ledger.py stats` at every capability close, and **≥40 search-ops in a conversation → checkpoint and STOP**. `templates/schemas/checkpoint.schema.json` defines the checkpoint.
Test the actual failure, do not read about it: **kill a run mid-category and resume it.** Does `orient.py` reconstruct where it was? Does the workbook's Pipeline state agree? Is the partially-worked subcap correctly pending rather than silently closed?
Then the durability question that decides all of it: **`$RUN` is a path.** If it is container-local, "disk is truth" holds only until the container exits — and in the target architecture the container always exits. Establish where `$RUN` lives, what persists it, and what a resumed Routine firing on a *fresh container* can recover. Note that the workbook is a Drive file and therefore *does* survive the container: if the ledger does not, the workbook may be the only durable state, and the resumability story should be built on it rather than on `$RUN`.
Also: R34 states ledger appends are `O_APPEND` atomic and ids are minted via `ledger.new_evidence_id(run)` under `fcntl` locking, "parallel-safe". **`fcntl` locks are per-host.** If dispatch ever spans machines, that guarantee is void.
**Compaction efficiency.** R27 forbids `cat` on `kg` packs, `engagement_set.json`, `evidence_index.json` and `ledger.jsonl` — read through `worklist` / `next` / `map-fact` / floors summaries instead. R32 requires syntheses be written by filling `orient.py --skeleton <SID>` templates, with `STUB_` values failing the gates. Audit: is compaction *used* (deliberate compact at category close, state on disk, cheap re-hydrate) or merely *survived*? And does the skeleton discipline invite form-filling — a synthesis structurally complete and substantively empty? A schema cannot catch that, and it is what an unattended run will produce most often.
### 4.3 Token optimisation across the knowledge graph
**What must be true:** the KG makes the work cheaper, measurably.
The claimed mechanisms, each with a number to verify:
| Mechanism | Claim | Verify |
|---|---|---|
| Lean briefs | `briefs --lean` is **~35% smaller** than the disk pack | Measure both on the same capability |
| Work card | `kg_reader.py next` returns one card, **≤~750 tok** | Measure the real distribution, not the cap |
| Category funnel (R25) | B-I sweep then B-II only for below-floor subcaps: **+25–32%** saved in doc-rich/large categories, **+11%** granular, **+3%** even when the sweep is a dud | Reproduce on ≥3 categories of differing shape |
| Batched challenge | ~150–250 tok/subcap | Measure, and check batching does not dilute scrutiny |
| Semantic index (R26) | TF-IDF over 851 briefs, offline, deterministic — replaces guesswork mapping | Cost to load vs. benefit |
| Never-cat rule (R27) | Never `cat` kg packs, `engagement_set.json`, `evidence_index.json`, `ledger.jsonl` | Is it enforced, or an instruction an agent under pressure will break? |
| Scope modes | `OFFERING` ≈ 6–12 conversations for 3 offerings; `T1_CORE` (686 universal) ≈ 27–33 | Are the budgets honest? Measure one real run against its band |
Then the questions the numbers do not answer:
- **Where does the budget actually go?** Instrument one category end to end and apportion tokens across brief loading, search results, synthesis writing, and challenge. Optimising the wrong term is the usual mistake.
- **Is the semantic index load amortised?** A TF-IDF index over 851 briefs costs something to hold. At what engagement size does it pay for itself?
- **What happens at the budget wall?** ≥40 search-ops → checkpoint and STOP is a *soft* rule an agent applies to itself. Unattended, does it stop, or does it keep going and blow the context? Test it.
- **Does the funnel ever cost more than it saves?** R25 claims +3% even on a dud sweep. Verify the floor case rather than trusting it — a sweep that surfaces nothing still spent its queries.
- **The reports are budgeted too, and nothing connects the two budgets.** Both report templates carry per-section LENGTH bands with a *blocking* lower bound and an advisory upper, summed into a document total at render time. A run that exhausts its token budget mid-research still owes 500–800 words of executive summary and 700–1,100 of strategic intelligence. Establish what happens: does the run stop before it can write, or write thin and fail the blocking minimum?
### 4.4 Report templates, and linkage to productized offerings
Both report templates are far more prescriptive than the skills describe, and both are now pinned by id above. **Read them before auditing this section**; most of what follows can only be judged against the real documents.
**What the templates enforce that the skills do not mention:**
- **Section controls.** Every section opens with PURPOSE / FEEDS / INPUTS / **LENGTH** (lower bound blocking, upper advisory) / **MINIMUM DATA** / MUST INCLUDE / MUST NOT / **FAIL IF**. Establish which of these FAIL IF conditions are mechanically checked and which are prose an agent may ignore. A blocking minimum nobody measures is advisory.
- **Document Control and Catalogue Binding.** Catalogue version, content hash, resolution path (`WORKBOOK_META` → `CATALOGUE_MANIFEST` → `CONNECTOR`, recorded in `{{CATALOGUE_SOURCE}}`), structure counts **counted, never asserted**, and: *"If any field resolves to UNRESOLVED, the render fails and the profile is not handed off."* Verify the render actually fails.
- **Surface Alignment.** Each report section names the app surfaces it feeds and whether this document is the **source of truth** or merely supporting. This is the cleanest statement of the report↔app contract anywhere in the system.
For the Client Profile, three sections are declared source of truth:
| Section | Feeds | Status |
|---|---|---|
| 1 Firmographics | O2 firmographics strip | **Source of truth** (after run manifest and entity profile) |
| 5 Strategic Intelligence | I1, T1/T2, O7, O12, C5 | **Source of truth for the leadership roster** |
| 6 Client Priorities | H1 focus areas, P2b starters | **Source of truth for every verbatim quote and page number** |
And the template states the measured cost of getting them wrong: *"57 of 138 clients shipped with no focus areas at all, and 53 shipped machine scoring text where a client quote belonged. Both failures start in this document."* **Re-measure both figures against the current corpus** — they are the sharpest available test of whether the template is being followed.
**Offering linkage — where the reports actually reach a productized offering.** Three places, and all three are free text:
- Client Profile §2.2 Top findings → column **"Zennify relevance"**, filled as `{{SOLUTION_NAME}} because {{WHY}}`
- Client Profile §5.1 Insight cards → **"Implication (so what)"**, filled as `{{SOLUTION_ALIGNMENT}}`
- Assessment Report §8 Recommendations → the Solution block
None of these is an `offering_id`. Against that, `kg/catalog/offering_map.json` (schema `kg-v3.1`) holds the real linkage, measured on the supplied archive:
- **23 distinct `offering_id`s** — matching the skill's "23 offerings" claim
- **458 of 851 subcaps carry a mapping — 393 do not**
- Each mapping carries `offering_id`, `offering` (display name) and a `rationale`
- **`OFF-PMI` ships two display names** — "Post-Merger Integration" and "Post-Merger Integration Solution" — 24 (id, name) pairs across 23 ids
So the finding to establish precisely:
- **Is offering linkage referential or asserted?** If `{{SOLUTION_NAME}}` is typed prose, a report can name an offering that does not exist, misname one that does, or split `OFF-PMI` in two — and nothing catches it. The fix is small (resolve the token against `offering_map.json` and fail the render on a miss) and the audit should say so.
- **What happens on the 393 unmapped subcaps?** Does a finding there reach a report with no offering, silently? Is the unmapped set deliberate — subcaps Zennify has no offering for, a legitimate answer — or an incomplete map? The `rationale` field suggests curation; sample and decide.
- R33's **LINKAGE** move rejects "linkages to unknown objectives". Does it also reject an unknown offering? If not, objectives are validated and offerings are not.
**Also check:** whether the placeholder sweep is enforced (a delivered report containing `{{CLIENT_NAME}}` is the failure it exists to prevent); whether `render_client_report.py`'s template v6.3 matches the pinned Doc; and whether the two reports reconcile numerically at 0.05.
**What v8 changed, and what it did not.** The assessment report's heading numbering — where `# 4.` was followed by `### 5.1`, and `# 6.` by both `### 5.1` and `### 7.2` — **is fixed**: every subsection in v8 now matches its parent. Do not re-report it; confirm it and move on. v8 also **adds two subsections to §3 Issue Impact and Cap Analysis**:
- **§3.2 When each cap lifts** — `Rule · Applies while · Lifts when · Expected lift date · Capability released · Score on lift`, with *"Where a rule has no horizon, write UNDETERMINED rather than a guess."* This is new contract surface: audit whether `Cap_Triggers` actually carries a lift condition and horizon per rule, or whether the columns have no source. A cap with no lift date is the finding a client resists hardest.
- **§3.3 Aggregate effect** — the combined score impact of all caps.
The Client Profile v8 is **substantively unchanged** from the prior draft: same eight sections, same Surface Alignment table and its 57-of-138 measurement, same §6.4 counter-evidence pass, same §8.1 artefact map. Its findings below stand as written.
### 4.5 Peer synthesis: category grain for reports, platform grain for the app
**The owner's rule:** peer synthesis and benchmarking happen **strictly at category level for the reports**, and **at the specific platform level for the recommendations in the web app**.
**Measured against the three templates and the app contracts, the rule is not what the system does.** Lay this out precisely; it is the clearest conflict in the audit.
| Where | Structure | Grain |
|---|---|---|
| **Workbook** (final, contract v3) | *no peer sheet at all* — `Peer_Benchmarks` existed in the superseded draft and has been **removed** | **NONE** ❌ |
| **Assessment report** §6.1 Peer scores | `Peer · Overall · Strongest pillar · Weakest pillar · AI posture` | entity + pillar |
| **Assessment report** §6.2 Strategic positioning | `Pillar · Entity · Peer median · Peer best · Position · Rank` | **PILLAR** ❌ |
| **Assessment report** §6.5 Peer deployment | `Product · Peer · Verdict · Basis · Source · As at` | **PLATFORM** ✅ |
| **Client Profile** §4.1 Peer comparison | `Peer · Size tier · Key metric · Geography · Overlap % · Rationale` | peer selection, no scores |
| **Client Profile** §5.2 Peer technographic scan | `Platform · Entity · Peer1..N · Source · Confidence` → `Platform_Peer_Adoption` | **PLATFORM** ✅ |
| **App** `heatmap.workbook_scores.categories` | `peer_median` + mandatory `source_cell` | **CATEGORY** |
| **App** `heatmap.workbook_scores.pillars` | `peer_median` + mandatory `source_cell` | **PILLAR** ❌ |
| **App** `overview.scores.pillars[]` | `peer_median`, `delta`, `peer_n`, `peer_basis`, `proxy_disclosure` | **PILLAR** ❌ |
| **App** `platform.platform_story` / `techstack.techstack` | `peer_score`, `peer_deployments`, `peer_coverage` | **PLATFORM** ✅ |
So:
- **Nothing stores peer scores at category grain any more.** The superseded workbook draft had a `Peer_Benchmarks` sheet keyed on `Category_ID`; the final contract-v3 workbook has **no peer sheet at all**. So the owner's rule — peer benchmarking at category level for the reports — currently has **no data source and no renderer**: the workbook does not hold it and the assessment report aggregates straight to pillar at §6.2. This is the sharpest form of the finding. Establish what the reports are actually benchmarking against, where those figures come from, and what it would take to restore a category-grain peer store. **Do not resolve whether the rule or the artefacts should change — that is the owner's call.**
- **Three app surfaces benchmark at pillar grain**, outside both halves of the rule. **Do not resolve this silently — it is an owner decision if the rule and the contracts genuinely disagree.** Present the options: change the rule to admit pillar grain, change the surfaces, or state that the rule governs reports only and the app's pillar row is intentional.
- **The platform half of the rule is satisfied and well built.** §6.5's discipline is the strongest peer control in the system: *"Ask what each peer runs at this layer rather than whether each peer runs this product: a peer on a different product at the same layer is a stronger finding than an unknown."* Verdicts are `DEPLOYED | NOT FOUND | NOT ESTABLISHED`; a descending evidence-class ladder decides which verdict a source supports; **peers that could not be established are listed rather than dropped**, because *"two of five deployed with three unknown is not forty per cent adoption"*; and where the peer set has no public technographic footprint at all, the coverage share is **omitted entirely**. Verify the renderer honours all four rules, and that **AG-04** — which enforces the same shape on the payload side — covers every surface naming a peer, not just `techstack`.
- **Peer set immutability.** Locked in Client Profile §4.1, written to `Handoff_Lock`, read from there by the assessment stage; workbook peers locked at R1 with scores written at A2. The selection discipline is *same sub-vertical, comparable asset size, same regulator jurisdiction, no merger*. Verify the lock survives the handoff and that nothing re-selects downstream.
- **The peer fallback ladder** on `overview.scores.pillars` — (a) recompute at lower N, floor N=3, emitting `peer_n`; (b) adjacency inference labelled INFERENCE with a widened band; (c) proxy ceiling — has no counterpart in either report template. Establish whether the reports degrade peer figures at all, and if not, whether app and report can therefore print different peer medians for the same client. **A peer median silently computed from three peers reads identically to one computed from ten.**
### 4.6 Challenging a platform recommendation
**Correct the obvious conclusion before drawing it.** The disconfirmation discipline the owner is asking about **exists and is well specified** — in the Assessment Report template, not in the engine. The gap is enforcement, not design.
**What the template already requires.** Every recommendation carries a **Rebuttal**:
> *A claim that survives its strongest counter-argument can be defended in the room; a claim that does not survive was going to fail there instead. Arguing against your own conclusion is the step that gets skipped, and it is the only one that catches a recommendation that is well formed, correctly cited and wrong.*
| Step | What must be recorded |
|---|---|
| **A. Hypothesis** | The claim, held at a stated confidence, *before* defending it |
| **B. Steelman against** | The strongest case for not doing this, argued properly |
| **B. Falsifier** | What would disprove the claim, from the client's own words where possible, with the conditions under which the steelman holds and fails |
| **B. Cheaper alternative** | The lower-cost intervention closing the same gap, and why it was not chosen — or a statement that none exists |
| **B. Case for waiting** | The reason to do this later, or a statement that none was found after looking |
| **C. Domain test** | Plausible for this sub-vertical at this size under this regulator? **And would this sentence be true of any institution in the sub-vertical?** If yes, it needs this entity's own figure, event or executive attached before it ships |
| **D. Probes run** | *"Each probe fires a search; a probe not run is not a probe."* |
| **E. Verdict** | `ACCEPT / REJECT / UNCERTAIN`. **"Reject means drop or re-rank the recommendation, never soften the wording."** |
And a seven-probe set, each with a firing condition and a check:
| Probe | Fires when | Check |
|---|---|---|
| Platform out of vertical | The platform serves a different sub-vertical | Relevance against the served cell set |
| Anchor cell of the wrong entity type | The target cell names another sub-vertical | Terminal segment of the cell id |
| Dependency inversion | Sequenced ahead of what it needs | The depends-on chain |
| Stale metric in the impact table | A current figure disagrees with the served score | Recompute against `Subcap_Scores` |
| KPI baseline with no source | The baseline has no date or evidence | `Evidence_Register` lookup |
| Gate asserted with no backing cells | A readiness verdict has no cells behind it | The readiness contract |
| **Initiative already underway** | The client may have started or dropped this | Search entity + initiative + *paused, completed, replaced, delayed* |
The last probe is precisely the owner's "is the solution already there?". So the question is no longer *what should be asked* — the template asks it. The question is **whether anything makes it happen.**
**What the engine does, and does not do.** `packages/shared/platform_fit.py` models incumbency arithmetically and well:
- `Cell.incumbent_covers` → `INCUMBENT_COVERAGE_DISCOUNT = 0.5`: a gapped cell an installed third-party incumbent already covers is **halved, not zeroed** — *"the capability can still be improved or integrated, but it is not net-new ground."*
- `Cell.family_absent` → confirmed-ABSENT in the register → **greenfield ground**, weighted `W_ABSENT`
- Fed from the promoted techstack register by `linked_subcap_ids`: CONFIRMED/INFERRED holds a cell, ABSENT is greenfield, **CLAIMED binds nothing**
- `STATE_TOO_NARROW` / `STATE_OUT_OF_VERTICAL` give an honest null rather than a 0.0, plus a discard list
But a search of `platform_fit.py` and `apps/mcp/dma_mcp/fit.py` for `contradict` / `refute` / `counter-evidence` / `disconfirm` returns **nothing**. The engine scores; it never tries to be wrong. **Verify, then answer the enforcement question:**
- Is the Rebuttal block **required** to render, or can a recommendation ship without one? Is any of the seven probes machine-checked — three of them (stale metric, KPI baseline, gate with no backing cells) are mechanical and could be gates today.
- Does the payload carry the rebuttal at all? `platform.recommendations` is the surface; establish whether steelman, falsifier, cheaper alternative and verdict have fields, or die in the .docx.
- **The contradiction that matters most:** a **missing** register row and a **confirmed-absent** one both produce greenfield. Establish whether the engine can distinguish "we know it is not there" from "we never looked". If it cannot, every unscanned estate is systematically over-recommended — and the "Initiative already underway" probe is the only thing standing between that and a client.
- Note the precedent for what a *specified but unenforced* discipline is worth: Client Profile §6.4 runs a **counter-evidence pass** on client priorities with the same shape (paused/completed/replaced? plausible for sub-vertical and size? client framing or vendor framing? → `SHIP | SHIP_LOW_CONF | DROP`). Two counter-evidence disciplines, both in templates, neither obviously in code. Check both.
**Parameters actually used** (state them, then check each is evidenced):
```
fit = 100 × (0.528·opportunity + 0.208·interconnect + 0.064·greenfield
             + 0.20·stated_alignment)
           × readiness_multiplier (green 1.00 / amber 0.85 / red 0.62)
           capped by vertical_relevance, ceiling 99.0
```
- **Readiness multiplies, never adds** — a red-prerequisite platform cannot reach the hot band. Motive: 95 of 470 cards previously scored hot with every prerequisite failing. Verify the multiplier, and that an *unmapped* readiness phrase reads RED while an *absent* one reads amber.
- **Alignment quotes the client's own stated objective or is omitted** — omission renormalises to the three-term blend and reports `impact_fallback`; sending 0 is a different claim. Is a fabricated `alignment_quote` catchable?
- **`depends_on` repairs rank** so a workload never outranks its foundation — and the "Dependency inversion" probe checks the same chain. Are they the same check twice, or two checks that can disagree?
- **CG-30** recomputes every card at submit (score off by >0.05, rank out of order, or an undeclared null → refused). **CG-31** pins the overview tiles to the engine's four factors and the card's composite/rank at 0.05.
### 4.7 Research and scoring workbook: one template, aligned with the app
**The canonical shape is settled — audit against it, not against the drafts.**
| Sheet | Holds |
|---|---|
| `DQ_Bank` | all **4,255** questions — five per subcap across 851, filterable by `SubCap_ID` or `Facet` |
| `Evidence_Detail` | one row per fact — `Fact_ID`, `SubCap_IDs`, **`DQ_Facet`** |
| `Negative_Findings` | one row per ladder-complete absence, keyed `SubCap_ID` |
| `P1..P4_Subcap_Scoring` | the 11-column contract row, keyed `SubCap_ID` |
| `Subcap_Synthesis` | keyed `SubCap_ID` then `DQ_Facet`; validator-required; challenge dimension 7 audits it |
| `Entity_Timeline` | dated facts, keyed `Fact_ID` |
| `Coverage` | live formulas `=C/B`, one row per category |
| `Run_Metadata` | mirrors `run_manifest`; `run_id` equality is a validator check |
| `REF_Diagnostic_Questions` · `REF_DQ_Model` · `REF_Contract` | reference sheets, added for the operator |
**The column contract, and the seven validator rules.** Research writes
**A** `SubCap_ID` · **B** `SubCap_Name` · **C** `Category` · **F** `Evidence_IDs`
· **G** `Source_URLs` · **K** `Proxy_Searched`. Assessment writes **D** `Score` ·
**E** `Confidence` · **H** `Evidence_Ceiling` · **I** `Caps_Applied` ·
**J** `Rationale`, all *"EMPTY and gray. Non-empty during research is a FAIL"*.
Each of these is a named, testable rule — force each to fail and confirm it does:
1. Required sheets present — fails when any of the six contract sheets is missing
2. Header equality per scoring sheet — the 11 headers differ in **name or order**, or a column is added
3. Row count equals scope — a selected subcap missing, or an unselected one present
4. Assessment columns empty — D, E, H, I or J carries a value during research
5. URL present — F is set and not `NO_EVIDENCE` while G contains no `http`
6. Banned placeholder — G contains `multiple searches` in any casing
7. `run_id` equality — `Run_Metadata.run_id` differs from `run_manifest.run_id`
**The strip step, and the hole in it — audit this first.** The workbook appends a
**working area in columns L to AG** on each pillar sheet, holding the synthesis
and the negative-finding ladder inline *"so a researcher works one subcap on one
row"*. It **must be removed before handoff**, and the workbook says why:
> *`validate_workbook.py` reads only columns 1 to 11 for its header test, so the
> appended block passes it. dma-assessment v5.5 is stricter and accepts eleven.*
Verified: `validate_workbook.py:25` reads `range(1,12)`. So an **unstripped
workbook passes its own validator and is then rejected downstream** — a failure
that surfaces one stage late, with no signal at the stage that could have caught
it.
The workbook prescribes the remedy: *"Run `scripts/strip_working_area.py`, or by
hand: on each of the four pillar sheets select columns L through the last,
delete, and save."*
**`strip_working_area.py` does not exist.** Searched the repository and the
supplied v4.2 archive; zero hits in either. So the only working remedy today is
the manual one — four sheets, by hand — which in the target architecture has
nobody to perform it. Confirm the absence yourself, then treat it as the
canonical **PRESENT–HUMAN-DEPENDENT** example: a mandated step, with a named
script that was never written, guarding a failure the upstream validator is
structurally blind to.
Also establish what the strip costs. The workbook claims *"Nothing that matters
downstream. The synthesis reaches assessment through `research_handoff.json`, not
through the workbook, and the negative findings…"* — verify that
`research_handoff.json` really carries the synthesis, because if it does not, the
strip deletes the analytical core and the validator will not notice.
**Alignment with the app.** Verified in `apps/worker/dma_worker/workbook_parser.py`:
- `_is_pillar_tab` matches `^P\d+($|[_ ])`, and `P1_Subcap_Scoring` survives the `_NOT_SCORING` exclusion list
- `P{n}_Subcap_Scoring` is explicitly **authoritative** over `P{n}_Scoring_Detail` — settled by measurement, because 23 of 154 corpus workbooks are merged files carrying both and the parser was reading every cell twice (1,420 rows for a 710-cell assessment)
- `_SCORE_KEYS` begins with `"score"`, matching column D; `SubCap_ID` is among the anchors tried
**The sheet names line up — and the Client Profile's do not.** The workbook and
the app agree on `P{n}_Subcap_Scoring`. But Client Profile §8.1 routes twelve
artefacts to a `{{SCORING_WORKBOOK}}` naming `Evidence_Register`, `Coverage_Map`,
`Gate_Log`, `Handoff_Lock`, `Cap_Triggers`, `Evidence_Request`, `Catalogue_Meta`,
`Search_Log`, `Audit_Trail`, `Platform_Peer_Adoption`, **`Subcap_Scores`**,
`Firmographics` and `Focus_Areas`. **None of those sheets exists in the final
workbook.** Enumerate the full mismatch and decide, per artefact, whether the
sheet was dropped deliberately, renamed, or moved to a second file that no longer
exists. Two consequences to trace specifically:
- **Assessment Report §3.2 "When each cap lifts"** reads its severity-to-cap rule set from `Cap_Triggers` — a sheet the workbook no longer has. The newest section of the newest report template reads a table that was deleted. Confirm and report.
- **`Platform_Peer_Adoption`** is where Client Profile §5.2 writes the peer technographic scan, and where Assessment Report §6.5 gets its platform-grain peer rows. Without it, the one half of the owner's peer rule that *was* satisfied loses its store too. Check whether §6.5 has another source.
**Also check:**
- **Grey-cell discipline is now a validator rule** (check 4), not just a convention. Force a score into D during research and confirm the validator fails. This is the research skill's rule 1 (NO SCORING) finally enforced at the file boundary — verify it actually is.
- **Row count equals scope** (check 3) is how a FOCUSED run (R34) stays honest. Confirm the app can still distinguish "not in scope for this engagement" from "in scope and unscored" once the workbook only carries the selected rows.
- **`DQ_Facet` on every fact in `Evidence_Detail`** is what makes facet coverage computable. The chain table warns: *"an untagged fact shows as an uncovered facet."* Measure the untagged rate on a real run.
- **The chain has eight joins** (`DQ_Bank`→`Evidence_Detail`→`Negative_Findings`→contract row→`Subcap_Synthesis`→`Entity_Timeline`→`Coverage`→`Run_Metadata`), each with a stated failure. Walk all eight against a real workbook and report which joins hold.
**The counts discrepancy is a skill finding, not a workbook one.** The superseded
workbook draft documented that `diagnostic_questions.md` is described in the
research skill's manifest as *"All ~836 diagnostic questions"* while holding
**71** capability patterns, and that `capability_criteria.md` holds **85** = 17 × 5,
built on the retired 17-category count. The final workbook has dropped that block
and simply carries 4,255 real questions. **Verify the two file-level claims
directly against the skill** — they remain findings about the skill even though
the artefact that reported them is gone.
## 5. Cross-cutting audits
### 5.1 Autonomy readiness (do this as a standalone pass)
Walk the whole pipeline once more asking only: **what breaks with no human in
the loop?**
- Every place a person currently reads, confirms, moves a file, answers a question, or notices something is wrong. Enumerate them. Each is PRESENT–HUMAN-DEPENDENT.
- Every failure that is currently **silent**. In attended operation a silent failure is caught by someone eventually; unattended, it is permanent. Rank these above loud failures.
- **Budget and termination.** 851 subcaps × 6–10 queries, plus dispatch round trips (§1.2). What bounds a run? What happens at the bound — does it stop, degrade, or hang? Note the precedent: two CI jobs once hung 33 minutes against a six-hour default, which is why **Gate L** now bounds every CI job. Is there an equivalent clock on an autonomous assessment?
- **Idempotency and replay.** If a Routine fires twice, or retries after a partial failure, what happens? Duplicate runs, duplicate evidence, double-counted enrichment?
- **Observability.** When an unattended run produces a wrong assessment, how would anyone find out? Enumerate every alerting path and rate each: real alert, log line nobody reads, or nothing.
- `scripts/synthesis_watchdog.py`, `backlog_sweep.py`, `goal_status.py`, `ingest_readiness.py` — what do they watch, and does anything consume their output?
### 5.2 The twelve invariants
From `CLAUDE.md`. For **each**: name the enforcing mechanism, the test proving
it, and whether that test can fail. An invariant with no mechanism is
ABSENT–UNNOTICED however true it currently happens to be. Give extra weight to:
- **(1)** No model calls at request time — `gate_a_no_inference_imports.py`. Does it cover transitive imports and the web layer?
- **(2)** Content enters only through the connector — and see Stage 8, which strains it.
- **(5)** Redaction server-side, default-deny. Test the **negative**: would the walker catch a *newly added* `internal_only` field, or is marking effectively opt-in?
- **(7)** No colour in any payload; score→band→hex in exactly **one** frontend module. Confirm `apps/web/lib/bands.js` is the only one and `#62D7B8` (not `#B0EDD3`) is the M2 value that renders.
- **(10)** The server allocates identifiers — agent mints only `ic_id, f_id, fa_id, ts_id, wn_id` + authored `rec_id`. Prove a client-supplied id elsewhere is **rejected**, not ignored.
### 5.3 Gate coverage
Roughly **AG-01…AG-12, CG-01…CG-50, ET-01…ET-09**, plus SG. Sample across all
four families:
- Does the gate have a test that makes it **fire**? A gate tested only in the passing direction is untested.
- Does its refusal name **the gate, the JSON path and the arithmetic** (invariant 12)?
- `explain_gate` should return a definition and threshold history — sample several; is the history real?
- Which gates have **never** fired in production? Cross-reference the rejection ledger. Never-fired means redundant or broken; distinguish.
- **Map the gates onto the thirteen §1.1 defects.** Which of those defects does the current gate set catch, and which would ship silently today?
### 5.4 Test-suite honesty
- Full suites at HEAD: **3,807 Python passed, 12 skipped** (ceiling 12), **240 web passed**, **35 schema passed**. Reproduce. A different number is a finding.
- Read all 12 skips. Is any hiding an untested behaviour rather than an absent environment? Confirm none is "no migrated local database" — that skip means the DB-backed suites did not run at all.
- Sample ~10 tests across services: **could this fail?** Mutate the code and confirm red. `scripts/mutation_check.py` may help.
- Gate E has a negative control in CI. Which other gates need one and lack it?
### 5.5 Documentation-to-reality drift
- The skill descriptions for `dma-research` and `dma-assessment` still say **"17 categories"** and **"~836 subcapabilities"** against a settled **16 / 851**. Establish blast radius: description text only, or the maths too?
- `plugins/dma-insights/docs/MCP-TOOLS.md` is generated from `apps/mcp/server.py` by `scripts/gen_mcp_tools_md.py` and **nothing regenerates it** (known gap, commit `df1688f`). In sync now? What other generated artefacts lack a freshness check? (`docs/text/` has a CI reproducibility check; what does not?)
- `gate_h_prompt_persistence_claims.py` exists because a producer prompt claimed a stored field was dropped. Are there other prompt claims that were true when written and are false now?
## 6. Instruments
Run `.notes` and repo scripts as available. `gcloud`/production checks and the
supplied `dma-research (4).skill` archive from Drive have already been staged
for this session — see the session's own tool log rather than re-fetching. If a
listed script or path does not exist, that absence is itself a finding, not a
blocker to the rest of the check.
Connector read tools (all safe): `list_pending_runs`, `list_open_rejections`,
`list_withdrawn_runs`, `get_run_progress`, `get_client_state`,
`get_staged_payload`, `get_validation_verdict`, `explain_gate`,
`get_page_contract`, `get_evidence`, `list_enrichment_gaps`,
`get_memory_digest`, `list_defect_classes`, `search_findings`,
`list_open_findings`, `list_reviewer_feedback`. See
`plugins/dma-insights/docs/MCP-TOOLS.md`.
**Call `search_findings` and `get_memory_digest` before recording anything.**
Much may already be known — a re-report is noise, a **recurrence** is signal,
and they are recorded differently.
## 7. Recording findings
- `search_findings(query, mode="auto")` — **first, always.**
- `record_finding({...})` — required: `title`, `observed`, `measurement` (≥30 chars, with denominator), `component`, `defect_class` (from `list_defect_classes` — a foreign key), `severity`, `raised_by_kind`, `raised_by`.
- `report_recurrence(...)` — a finding that was **resolved and came back**. Highest-value signal; never file it as new.
- Do **not** call `record_refinement` or `resolve_finding`. You are not fixing.
Severity, calibrated for **autonomous operation**:
| | |
|---|---|
| **BLOCKER** | Wrong content can reach a client unattended; an invariant is unenforced; or a stage cannot run headless at all |
| **MAJOR** | The stage needs a human, and the target architecture has none |
| **MINOR** | Works, but fails silently |
| **INFO** | Drift, staleness, documentation gap |
## 8. Deliverable
1. **Ledger status** — the counts from `.qa/ledger.jsonl`: total, `DONE`, `BLOCKED`, `NOT_APPLICABLE`, and any `DONE` row failing the measurement test. Plus the phase you reached and the prompt fingerprint you ran under. An audit that claims completeness without these is asking to be believed rather than checked.
2. **Autonomy verdict** — one paragraph: can this repo run an unattended DMA end to end today? If not, the shortest list of things that must be true.
3. **Stage table** — the nine stages, one of the five verdicts each, one sentence of justification.
4. **The §1.1 thirteen-defect table** — each historical defect against the gate that now catches it, or **nothing does**.
5. **Headless blockers** — led by the §1.2 enrichment-connector finding, with the measured round-trip cost of the dispatch loop.
6. **Skill-version reconciliation** — what shipping v4.2 into the plugin costs (manifest, `scripts/requirements.txt`, `kg/` artefacts, packaging-validator limits), and what stays broken until it lands. State plainly whether the reasoning rigour the owner wants is *missing* or merely *unshipped* — the answers imply very different work.
7. **MECE DQ report** — five-facet completeness across all 851 briefs (histogram, with denominators), anti-clone (R22) collision count, the generic-render and post-G10 vendor-name findings, and the DQ→query drift rate.
8. **Reasoning-trap report** — the Stage 6.1 table completed with enforcement status; a verdict on the Stage 6.2 challenge layer's independence, on whether `provisional: true` survives to the app, and on the terminal state of an `open_conflict` with no human to ask; plus the Stage 6.3 walk-through naming every gate the wrong-but-perfect conclusion passes.
9. **The seven owner-specified checks (§4)** — one verdict each, in order, each with its measurement:
   1. entry document and routing — does the SessionStart hook fire headless at all, and does the brief survive compaction
   2. drift, memory, resumability, compaction — the kill-and-resume test; whether the skill-side ledger and the workbook's CHAIN INTEGRITY agree; and what now reports a stuck run, since `Blocked` is gone
   3. token optimisation — the claimed percentages reproduced or refuted, plus a token apportionment for one category
   4. report templates and offering linkage — whether anything resolves the three pinned ids (and whether a superseded id is still referenced), and whether `{{SOLUTION_NAME}}` is referential or free text
   5. peer grain — **nothing stores peer at category grain any more**; the assessment report renders pillar at §6.2 and three app surfaces render pillar; name the owner decision
   6. platform-recommendation challenge — the Rebuttal block and its seven probes exist in the template; establish what enforces them and whether the payload carries them
   7. workbook — the seven validator rules each forced to fail; the **missing `strip_working_area.py`** and the validator's blindness past column 11; and the twelve Client Profile §8.1 tabs that no longer exist
10. **Publication gap** — what building the four new deliverables costs, and whether it strains invariant 2 enough to need an owner decision.
11. **ABSENT–UNNOTICED register.**
12. **Findings**, worst first, each with measurement and `MEM-####`.
13. **Refuted leads** — every `[LEAD]` you disproved, and how.
14. **Could not determine** — with the access that would settle each.
15. **The three things to build first**, with the argument for that order.
A finding without a measurement is an opinion, and this repo will reject it.
## 9. Stop conditions
Stop and report immediately, without finishing the sweep:
- **Client data crossing an audience boundary** — an `entity_id` in a cohort pattern served to any audience, or `internal_only` content in a customer projection or a client-facing document.
- **A `foreign` evidence id** — a row belonging to another institution. Invariant 4: this halts production. Quarantine and escalate; never route around it.
- **Two institutions merged into one entity.**
- **A live credential in the repo or in any log you read.** Report location and rotation path; **never echo the value.** Known standing item: an owner-grade service-account key and a GitHub PAT are reported to sit in a shared Google Doc ("Secrets and Variables") awaiting the owner's decision — confirm rather than re-report that one.
## 10. Scope boundaries
- **Do not extend or import from `apps/dma-insights/`** (legacy snapshot). Auditing it as a source of divergence is in scope; treating it as the system is not.
- **Do not resolve the open decisions.** Retention for superseded runs (default: retain), `CLAIMED` vs `INFERRED` visual treatment, and partitioning (**not yet** — do not pre-build) are deliberately open. Finding them open is not a finding.
- **The 16-category adjudication is settled.** v7.0 has 16, not 17 (user-confirmed 2026-08-04). Code or maths following 17 is a bug; do not re-open the question.
- **Do not design the new architecture.** Your job is to establish what stands between here and it, precisely enough that someone can plan. Where a choice is the owner's — most obviously whether invariant 2 may admit file publication — surface it as a decision, do not settle it.
- **Change no behaviour.** No fixes, no refactors, no "while I was there."
- If a genuine conflict survives the §2.2 authority order, **stop and ask.**
