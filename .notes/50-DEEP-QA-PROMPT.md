# Deep QA — DMA Insights: can this repo run an autonomous, headless DMA?

> Paste this whole document as the opening prompt of a QA session against
> `mishleyotis/Accelerate`, default branch `claude/dma-insights-onboarding-0ryrd0`.

---

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
      · the RESEARCH and SCORING workbooks     ← no path today
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

`dma-research` is search-saturated: **6–10 queries per subcapability across a
10-tier query system, over ~851 cells.** If the headless child cannot search,
the research stage cannot run headless without an orchestrator that can.

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

1. **Auditing the installed skill measures the wrong artefact.** Sections 5 and 6 below are written against the **supplied v4.2**, because that is the intended system. Where you test the installed one, label the finding as version drift, not as a design flaw.
2. **The single largest enablement gap may be a packaging problem, not an engineering one** — the reasoning rigour the target architecture needs largely *exists*, and is not shipped. Establish exactly what it would take to land v4.2 in the plugin: manifest wiring, script dependencies (`scripts/requirements.txt`), the `kg/` build artefacts, and whether `package_plugin.py`'s validator accepts a skill of 94 files with a compiled knowledge graph.
3. **Everything downstream inherits the wrong universe.** `dma-assessment`'s description also still says "17 categories / ~836 subcapabilities". Determine whether the wrong counts are only description text or reach the coverage maths — a coverage gate computed against 836 passes while 15 cells go unresearched.

Also record, as findings in the supplied skill itself:

- **Internal version inconsistency** — SKILL.md header says `v3.0`; CHANGELOG's top entry is `v4.2`.
- **Gate id `G10` is overloaded.** `references/protocols/safeguard_gates.md` defines G10 as **"No Toolkit Blending"** (a BLOCK gate on binding one sub-vertical toolkit). But Rule 16 and `scripts/build/dq_generator.py` cite **G10** for **platform-agnostic DQs (no vendor names)**, and `scripts/build/validate_kg.py:93` implements *that* meaning. Two different gates, one id. Verify, then judge which is the mis-citation — a gate id that means two things cannot be reasoned about.

---

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

### 2.3 Three traps that will produce false "it exists" findings

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

---

## 3. Stage-by-stage enablement audit

For each stage: verdict, findings, **and the specific change that would make it
headless-capable**.

---

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

---

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

---

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

---

### Stage 4 — Load internal documents

Audit:

- Is there any internal-document ingest distinct from public research? If Stage 3 is absent, this cannot be gated — say so and follow the consequence.
- How is internal evidence **marked** so redaction can act and a reader can tell provenance? Check tiers T1–T5, ERS, and claim classes. `dma-research` says "Flag in workbook Column U when internal evidence contradicts public evidence" — is that flag machine-readable downstream, or prose a human reads?
- Invariant 4 requires every cited id to resolve, belong to this entity and run, and carry a **verbatim 50–500 character excerpt**. Can an internal document satisfy that when the artefact is not fetchable by the connector? Follow one internal-sourced citation end to end. If internal citations systematically fail the evidence gate, internal evidence is being silently dropped and HYBRID assessments are thinner than they appear — quantify.
- Credentials: `plugins/dma-insights/docs/secrets.md`. In an unattended run, whose credential opens the internal document?

---

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

---

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
different question than the DQ asked (§5.3), or because presence was read as
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
---

### Stage 7 — Scoring

- **The handoff seam.** `dma-assessment` consumes `research_handoff.json` (RESEARCH_HANDOFF mode; skips Phase 1; imports `locked_peer_set[]` if present). Does a handoff written by the *current* `dma-research` satisfy the *current* `dma-assessment`? Two independently edited skills drift; test with a real handoff rather than reading both.
- **Bands.** Four bands, strict less-than, on the **RAW** score before display rounding: `<2 Activating · <3 Building · <4 Competing · ≥4 Differentiating`; null → no score. `band_t` is a four-value enum; **M5/Transformational must not exist in code, enum or prose.** *Careful:* the **rubric** is legitimately M1–M5 (a workbook scoring level) — only the **band** enum is four-valued. Confirm the DB generated column and `apps/web/lib/bands.js` agree, and that the golden-run fixture test asserting agreement exists and can fail.
- **Caps bind or decorate?** Trace one cap from the issue register through to a served number. `overview.ceilings` (O1b), G14, the ±0.8 uncertainty cap.
- **Grain** reconciles at 0.05 tolerance across pillar/category/cell. `scripts/gate_j_surface_parity.py`.
- Peer medians: computed or stored? Invariant 8 — counts are computed, never stored, where a source of truth exists.
- Run `skills/dma-assessment/scripts/validate_scoring_quality.py` and `qa_auditor.py`. **Prove they fail on bad input.**

---

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

---

### Stage 9 — Finalise and publish

- **Atomic promotion**: all six pages, one transaction, `SELECT … FOR UPDATE` on the run row, ordered writers. The **writer registry is an ordered list of 34 section writers** and order is load-bearing (unordered acquisition deadlocks under concurrent promotes). Find the stability test; confirm it can fail.
- Retention: promoted staging rows are retained so one page can be fixed and re-promoted. Verify, and verify `get_staged_payload` reads a superseded submission back (its documented recovery route).
- **A failing SG discloses and still promotes; a failing evidence reason never does.** Test both directions.
- Rejection ledger — `scripts/gate_k_rejections_return.py`, `list_open_rejections`. Its failure mode is **silent** (the queue simply stays empty). In unattended operation this is the only thing that makes a refusal visible. Prove it is wired.
- What marks a DMA **final**? Is there a terminal state, or does finality mean "someone stopped working on it"? Trace `runs.status`.
- `withdraw_run` removes a run from `serving_directory`; confirm `is_active=false` alone does **not** (the documented trap: the directory keeps publishing the client's name beside pages that 404).
- Charter: **not done until live in prod.** `scripts/verify_deployed.py` byte-compares the deployed bundle; `infra/deploy.sh` must call it. Run it if you have credentials; if not, say so rather than inferring a production state.

---

## 4. The seven owner-specified checks

Seven areas the owner named directly. Each gets its own verdict and its own
place in the deliverable. Findings here outrank the generic sweep.

---

### 4.1 The entry document, and routing at three moments

**What must be true:** one `.md` loads first, stays resident, and routes an
agent to the right documentation — without exceeding the size a resident file
can afford.

The entry chain today, verified on the default branch:

- `plugins/dma-insights/hooks/hooks.json` fires **SessionStart** → `scripts/hooks/session_brief.py`
- That prints ~50 words: route before you produce · one surface → that page's producer → finding-challenger → page-consolidator · only surface-producer submits or promotes · read `get_memory_digest` first · end with qa-overseer · **routing table: `skills/dma-surface-production/05-lifecycle/routing.md`**
- The routed-to file is **17 KB** (`routing.md`); its siblings in `05-lifecycle/` are `1-gates.md` (**42 KB**), `surface-map.md` (18 KB), `2-versioning.md`, `client-memory.md`

Audit, at each of the three moments the owner named:

**At session start.** Does the hook actually fire in a *headless, trigger-fired*
session, or only in an interactive one? The hooks are declared in the plugin
manifest; establish whether `claude -p --agent …` (the `agent_run.py` path)
loads plugin hooks at all. **If it does not, the routing rule never enters an
unattended run** — and every dispatched producer starts unrouted. This is the
single highest-value check in 4.1.

**While the session runs.** `session_brief.py` prints **only** when
`source ∈ {startup, clear}`. Its docstring gives the reason:

> *resumes and compaction continuations already carry the brief in context, and
> re-printing it on every continuation is noise.*

Test that assumption rather than accepting it. After a real compaction, is the
brief still in context? Compaction summarises; a 50-word line early in a long
session is exactly the kind of thing a summariser drops. If it does drop, the
routing rule is gone mid-run and **nothing reprints it** — the hook has
deliberately excluded the one moment it would be needed.

**As the session proceeds into new work.** Does anything re-assert routing when
the agent changes page, or when a sub-agent is dispatched? `agent_run.py`
prepends a DISPATCH-MODE preamble, but that preamble covers connectors and
output format — **not** the routing table. Check whether a dispatched producer
is told how to route, or only how to report.

**Size.** Nothing enforces a limit: `plugins/dma-insights/scripts/audit_skills.py`
checks broken references and that scripts answer `--help`, and has **no
word or line ceiling**. Measured:

| SKILL.md | words | lines |
|---|---:|---:|
| `dma-first-call-deck` | 9,091 | **903** |
| `dma-assessment` | 5,986 | **852** |
| `dma-surface-production` | 5,138 | **587** |
| `dma-research` (installed v2.3) | 4,439 | 629 |
| `dma-rectifier` | 3,868 | 413 |
| `dma-governance` | 2,133 | 332 |
| *supplied `dma-research` v4.2* | *5,065* | *409* |

Against the ~500-line working guidance for a resident SKILL.md, three exceed it
and one is near double. Establish the real ceiling for this harness, measure
each file against it, and say which are over. Then ask the harder question:
**is `routing.md` at 17 KB a routing table or a second manual?** A router that
must itself be read in full has not reduced anything. Judge whether an agent
can reach the right rulebook from the brief plus a scan, or whether it must
read 17 KB first — and note that `1-gates.md` at 42 KB sits behind it.

**Reachability.** Pick five plausible tasks (repair one card; a failed CG-30;
author the context page; a rejected insight card; resume after compaction). For
each, trace the path from the 50-word brief to the file that answers it. Count
the hops and the bytes. Any task needing more than two hops is a routing
failure, whatever the table says.

---

### 4.2 Drift, memory, resumability, compaction

**What must be true:** the workflow resists model drift; memory is updated
continuously and recalled on demand; a run whose tokens ran out can be resumed
from its last state; compaction is used deliberately rather than survived.

The supplied v4.2 skill is unusually strong here — audit whether the strength is
real and whether it reaches the app.

**Drift.** Two distinct meanings; separate them.

- *Instruction drift within a run* — R23 **path citation + checksum halt**: every phase action names the `kg/` or `references/` file it executed from, and `kg_reader.py guard` HARD HALTs on a build-checksum mismatch. Verify the halt fires. Then ask the unattended question: **a hard halt with no listener is a silent stall.** What surfaces it?
- *Behavioural drift across runs* — the findings memory (`record_finding` → `record_refinement` → `resolve_finding` → `report_recurrence`). `report_recurrence` is the load-bearing one: a fix that did not hold. Check `get_memory_digest`'s `recurrences_in_window` is populated and that anything reads it.

**Continuous update and recall.** R21 append-only `01_evidence/ledger.jsonl`;
conflicts preserved, never resolved by deletion; compaction only at category
close. R32 requires every session to OPEN with `orient.py --run $RUN` and follow
its `do_first`. Establish: is `orient.py` actually called first in practice, or
only instructed? Is there a mechanical check that a session read state before
writing?

**Resumability — the token-exhaustion case the owner named.** R27 sets a budget
rule: check `ledger.py stats` at every capability close, and **≥40 search-ops in
a conversation → checkpoint and STOP**. R32 closes every batch with compact →
floors → orient rerun. `templates/schemas/checkpoint.schema.json` defines the
checkpoint.

Test the actual failure, do not read about it: **kill a run mid-category and
resume it.** Does `orient.py` reconstruct where it was? Is the partially-worked
subcap correctly pending rather than silently closed? R27 says a subcap counts
as closed ONLY when the ledger holds its synthesis, negative or remediation
record, and `worklist` proves zero pending before a category closes — verify
both against a real interrupted run.

Then the durability question that decides all of it: **`$RUN` is a path.** If it
is container-local, "disk is truth" holds only until the container exits — and
in the target architecture the container always exits. Establish where `$RUN`
lives, what persists it, and what a resumed Routine firing on a *fresh
container* can actually recover. If the answer is nothing, resumability is a
same-container property and the headless plan needs a durable store.

Also: R34 states ledger appends are `O_APPEND` atomic and ids are minted via
`ledger.new_evidence_id(run)` under `fcntl` locking, "parallel-safe". **`fcntl`
locks are per-host.** If dispatch ever spans machines, that guarantee is void.

**Compaction efficiency.** R27 forbids `cat` on `kg` packs,
`engagement_set.json`, `evidence_index.json` and `ledger.jsonl` — read through
`worklist` / `next` / `map-fact` / floors summaries instead. R32 requires
syntheses be written by filling `orient.py --skeleton <SID>` templates, with
`STUB_` values failing the gates. Audit: is compaction *used* (deliberate
compact at category close, state on disk, cheap re-hydrate) or merely
*survived*? And does the skeleton discipline invite form-filling — a synthesis
structurally complete and substantively empty? A schema cannot catch that, and
it is what an unattended run will produce most often.

---

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

---

### 4.4 Report templates, and linkage to productized offerings

**Templates.** Two report paths, both template-bound, both with an unpinned
external dependency:

- `dma-assessment` Phase 7 **STEP 0** retrieves `DMA_Assessment_Report_Template.docx` "from the project knowledge base" — *"the ONLY acceptable report structure. Do NOT create ad hoc layouts."*
- Supplied v4.2 **R13** requires `DMA_Client_Profile_Research_Template.docx` from the project knowledge base *when present*, else falls back to `scripts/deliver/make_report_template.py`, with a placeholder sweep before delivery.

Audit:

- Neither template is version-pinned in the repo. In an unattended run, what happens when one is missing or has changed? The v4.2 path at least has a declared fallback; the assessment path says "the ONLY acceptable structure" and names no fallback at all. Establish what it actually does.
- Is the placeholder sweep enforced, or advisory? A delivered report containing `{{CLIENT_NAME}}` is the failure this exists to prevent.
- `render_client_report.py` composes via template **v6.3** structure. Confirm the renderer, the spec (`references/specs/client_report_spec.md`, `assets/report_template_spec.md`) and the template agree on version.
- The two reports must reconcile numerically at the 0.05 grain. Check.

**Productized offerings.** `kg/catalog/offering_map.json` (schema `kg-v3.1`) is
the linkage. Measured on the supplied archive:

- **23 distinct `offering_id`s** — matching the skill's "23 offerings" claim
- **458 of 851 subcaps carry an offering mapping — 393 do not**
- Each mapping carries `offering_id`, `offering` (display name) and a `rationale`
- **`OFF-PMI` ships two display names** — "Post-Merger Integration" and "Post-Merger Integration Solution" — 24 (id, name) pairs across 23 ids

So:

- **A report that links by display name splits `OFF-PMI` into two offerings.** Establish whether linkage is by id or by name anywhere it is rendered, and normalise the finding.
- **What happens to a finding on one of the 393 unmapped subcaps?** Does it reach a report with no offering linkage, silently? Is the unmapped set deliberate (subcaps Zennify has no offering for — a legitimate and useful answer) or an incomplete map? The `rationale` field suggests deliberate curation; verify by sampling.
- R33's **LINKAGE** move requires: named strategic objective → where value is or is not converting → *the Zennify implication*. The composer rejects "linkages to unknown objectives". Does it also reject a linkage to an unknown *offering*, or is the Zennify implication free text that need not resolve to `offering_map.json` at all? **If free text, offering linkage is asserted rather than referential** — the finding the owner is asking for.
- Does the DMA app surface offering linkage anywhere, or does it stop at the report? Cross-check against the platform recommendation surfaces.

---

### 4.5 Peer synthesis: category grain for reports, platform grain for the app

**The owner's rule:** peer synthesis and benchmarking happen **strictly at
category level for the reports**, and **at the specific platform level for the
recommendations in the web app**. Audit against that rule, and report every
place the system does peer comparison at a *different* grain.

Peer fields in the app's page contracts today:

| Surface | Peer content | Grain |
|---|---|---|
| `heatmap.workbook_scores.pillars` | `peer_median` + mandatory `source_cell` | **pillar** |
| `heatmap.workbook_scores.categories` | `peer_median` + mandatory `source_cell` | **category** |
| `overview.scores.pillars[]` | `peer_median`, `delta`, `peer_n`, `peer_basis`, `proxy_disclosure` | **pillar** |
| `overview.scores.posture` | LEADING/COMPETING/LAGGING/MIXED "justified against the peer set" | entity |
| `heatmap.focus_areas` | `peer_score` | focus area |
| `platform.platform_story` | `peer_score` | **platform** |
| `techstack.techstack` | `peer_deployments`, `peer_coverage` | **platform / vendor** |
| `platform.starters` | `peer_reference` | platform |

Two things fall out immediately, and both need a verdict rather than an
assumption:

- **The app benchmarks at pillar grain in two places** (`overview.scores.pillars`, `heatmap.workbook_scores.pillars`). If the rule is category-for-reports and platform-for-app, pillar-grain peer medians on the app are outside both. Establish whether the rule is being violated, or whether the rule is about *reports* only and the app's pillar row is intentional. **Do not resolve this silently — it is an owner decision if the contract and the rule genuinely disagree.**
- **`heatmap.workbook_scores` peer medians are STATED, not computed** — read from the workbook with a mandatory `source_cell`, "never recomputed by averaging subcapabilities". So the *reports'* category-grain peer figures and the *app's* category-grain peer figures should be the same numbers from the same cells. Verify they are, at 0.05 tolerance.

Then:

- **The peer fallback ladder** on `overview.scores.pillars` is elaborate: (a) recompute at lower N, floor N=3 (N=5 → sorted[2]; N=4 → mean(sorted[1..2]); N=3 → sorted[1]), emitting `peer_n` so the reader sees the basis shrank; (b) adjacency inference, labelled INFERENCE with one clause of reasoning and a widened band; (c) proxy ceiling. Verify each rung is implemented, that `peer_n` is actually emitted when the basis shrinks, and that an INFERENCE rung is labelled as such on the rendered surface — **a peer median silently computed from three peers reads identically to one computed from ten.**
- **Peer set immutability.** R14: 3–5 peers locked in Phase A, IMMUTABLE, saved to `peer_set.json`, carried into the handoff; `dma-assessment` imports `locked_peer_set[]` and "SCORES them; it does NOT re-select them". Verify the lock holds across the handoff, and that no downstream stage quietly re-selects.
- **Platform-grain peer claims are gated by AG-04**: where `peer_coverage` is stated, a per-peer breakdown must exist with one row per peer *including peers that could not be established* (`deployed: null`); every deployed row carries `source_url` and `as_of`; and the share must agree with its own breakdown to within one peer. The gate exists because "a verdict beside a NAMED institution was derived from a hash". Test it fires. This is the strongest peer control in the system — confirm it covers every surface that names a peer, not just `techstack`.
- **Category-level peer synthesis in the reports**: does `dma-assessment`'s Peer Analysis output actually work at category grain, and does the category challenge dimension `single_source_concentration` (>40% one domain) apply to peer evidence too?

---

### 4.6 Challenging a platform recommendation

**The owner's questions, in order:** is the solution already there? has the
agent looked for contradicting evidence? is there contradictory evidence that
would materially change the recommendation? what parameters and what questions?

**"Is it already there?" — this part is built.** `packages/shared/platform_fit.py`
models incumbency arithmetically:

- `Cell.incumbent_covers` → `INCUMBENT_COVERAGE_DISCOUNT = 0.5`. A gapped cell an installed third-party incumbent already covers is **halved, not zeroed** — "the capability can still be improved or integrated, but it is not net-new ground."
- `Cell.family_absent` → confirmed-ABSENT in the register → **greenfield ground**, weighted `W_ABSENT`
- Fed from the promoted techstack register by `linked_subcap_ids`: CONFIRMED/INFERRED holds a cell, ABSENT is greenfield, **CLAIMED binds nothing**
- `STATE_TOO_NARROW` / `STATE_OUT_OF_VERTICAL` produce an honest null rather than a 0.0, and a discard list

Verify each: force a candidate whose cells are all incumbent-covered and confirm
the fit falls; force an all-ABSENT family and confirm greenfield lifts it; check
CLAIMED really binds nothing.

**"Has it looked for contradicting evidence?" — this part appears absent.**
A search of `packages/shared/platform_fit.py` and `apps/mcp/dma_mcp/fit.py` for
`contradict` / `refute` / `counter-evidence` / `disconfirm` returns **nothing**.
The engine is a scoring function; it has no disconfirmation pass. **Verify, then
follow the consequence:**

- Does any *agent* run a disconfirmation pass on a platform card? Read `plugins/dma-insights/agents/production/platform/platform-fit-producer.md` — it asks whether the incumbent is named from the register and whether a discard is reasoned from vertical relevance. Is that a contradiction check, or a completeness check? They are different, and only the first answers the owner's question.
- The generic `finding-challenger` (steelman → falsify) exists. Is it invoked on `platform.platform_story` and `platform.recommendations`, and does its falsifier reach *the recommendation* or only the prose describing it?
- **The specific contradiction that matters most:** the client already runs something that solves this, and the register does not know. CLAIMED binds nothing and an un-scanned estate reads as ABSENT — so a **missing** register row and a **confirmed-absent** one both produce greenfield. Establish whether the engine can distinguish "we know it is not there" from "we never looked". If it cannot, every unscanned client looks like greenfield, and that is a systematic over-recommendation.

**Parameters actually used** (state them, then check each is evidenced):

```
fit = 100 × (0.528·opportunity + 0.208·interconnect + 0.064·greenfield
             + 0.20·stated_alignment)
           × readiness_multiplier (green 1.00 / amber 0.85 / red 0.62)
           capped by vertical_relevance, ceiling 99.0
```

- **Readiness multiplies, never adds** — a red-prerequisite platform cannot reach the hot band. Motive: 95 of 470 cards previously scored hot with every prerequisite failing. Verify the multiplier, and verify an *unmapped* readiness phrase reads as RED while an *absent* one reads as amber.
- **Alignment quotes the client's own stated objective or is omitted** — omission renormalises to the three-term blend and reports `impact_fallback`; sending 0 is a different claim. Check the incentive was not just asserted: does stating an above-blend alignment help, and is a fabricated `alignment_quote` catchable?
- **`depends_on` repairs rank** so a workload never outranks its foundation.
- **CG-30** recomputes every card from its own fields at submit — score off by >0.05, rank out of order, or a null the engine did not itself declare unrankable, all refused. **CG-31** pins the overview tiles to the engine's four factor names and the card's composite/rank at 0.05.

**The questions that should be asked and are not.** Draft the disconfirmation
set the system lacks, then check each against what exists: *Does the client
already run a product that covers these cells — and did we look, or merely not
find? Is the readiness verdict evidenced or inferred? Does any evidence
contradict the gap this recommendation rests on? Would the recommendation change
if the single largest contributing cell were wrong? What would have to be true
for this to be the wrong platform?* Report which have a mechanical answer today,
which are asked in prose, and which nobody asks.

---

### 4.7 Research and scoring workbook: one template, aligned with the app

**The contract (supplied v4.2, `references/specs/workbook_spec_v3.md`).**
File `{run}/02_workbook/DMA_Scoring_Workbook_{INST}.xlsx`, written by
`scripts/deliver/populate_workbook.py`, validated by
`scripts/deliver/validate_workbook.py` (**exit 1 blocks Phase D**).

Sheets: `P1_Subcap_Scoring` … `P4_Subcap_Scoring` (rows = engagement_set ∩
pillar, taxonomy order), `Evidence_Detail`, `Negative_Findings`,
`Subcap_Synthesis`, `Entity_Timeline`, `Coverage`, `Run_Metadata`.

Eleven columns, ownership split:

| Col | Header | Owner |
|---|---|---|
| A · B · C | `SubCap_ID` · `SubCap_Name` · `Category` | research |
| **D · E** | `Score` · `Confidence` | **assessment** (research leaves EMPTY) |
| F · G | `Evidence_IDs` · `Source_URLs` | research |
| **H · I · J** | `Evidence_Ceiling` · `Caps_Applied` · `Rationale` | **assessment** |
| K | `Proxy_Searched` | research |

`dma-assessment` v5.5 bans more than 11 columns.

**Alignment with the app — the scoring sheet lines up.** Verified in
`apps/worker/dma_worker/workbook_parser.py`:

- `_is_pillar_tab` matches `^P\d+($|[_ ])` and `P1_Subcap_Scoring` survives the `_NOT_SCORING` exclusion list
- `P{n}_Subcap_Scoring` is explicitly the **authoritative** tab over `P{n}_Scoring_Detail` — settled by measurement, because 23 of 154 corpus workbooks are merged files carrying both and the parser was reading every cell twice (1,420 rows for a 710-cell assessment)
- `_SCORE_KEYS` begins with `"score"`, matching column D
- `SubCap_ID` is among the anchors the parser tries

So do **not** report a scoring-sheet mismatch without re-measuring — the obvious
suspicion is wrong.

**Where alignment fails is the other six sheets.** Grepping the live app
(`apps/worker/dma_worker/`, `apps/mcp/dma_mcp/`) for each sheet name:

| Sheet | App references |
|---|---:|
| `Evidence_Detail` | 4 |
| `Negative_Findings` | **0** |
| `Subcap_Synthesis` | **0** |
| `Entity_Timeline` | **0** |
| `Coverage` | **0** |
| `Run_Metadata` | **0** |

`Subcap_Synthesis` is where R24's synthesis records land — dominant claim,
five-facet coverage, triangulation, contradiction disposition, ceiling
reasoning, timeline. `Negative_Findings` holds the ladder-complete absences.
`Entity_Timeline` holds the time model.

**Verify this before believing it**, then answer the question it raises: the
reasoning the v4.2 skill works hardest to produce may reach the app by a
different route — through the connector payloads the surface producers author,
rather than through the workbook. Establish **which route, if any**, carries
synthesis, negative findings and the timeline into the app. If neither does,
then the deepest analytical work in the pipeline stops at a spreadsheet nobody
downstream opens — and the owner's plan to publish the workbook to the app is
the fix, not a nice-to-have.

Also check:

- **One template, or several?** The installed v2.3 skill writes a different workbook (columns A–I, K, L, M, U, V; `Evidence_Detail` richness in column U). The corpus already holds multiple shipped variants — hence the parser's preference-ordered `_SCORE_KEYS` and its variant handling. Establish how many distinct workbook shapes are live, and whether v3 is genuinely the single standard or the newest of several.
- **Does `validate_workbook.py` block, or warn?** It claims exit 1 blocks Phase D. Force a bad workbook and confirm.
- **Grey-cell discipline.** Research must leave D, E, H, I, J empty. What happens if research writes a score there — does anything catch it, or does a research ceiling reach the app as an assessment score? This is invariant 1 of the research skill (NO SCORING) crossing a file boundary, and a spreadsheet has no gate of its own.
- **Row set.** Rows are `engagement_set ∩ pillar`. A FOCUSED run (R34) narrows the set. Does the app distinguish "not in scope for this engagement" from "in scope and unscored"? If not, a focused run renders as a thin assessment.

---

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

---

## 6. Instruments

```bash
# Environment (no docker daemon; install postgres directly)
apt-get install -y -q postgresql-16 postgresql-16-pgvector
pg_ctlcluster 16 main start
python3 -m venv .venv && .venv/bin/pip install -q pytest openpyxl pg8000 pypdf httpx \
  -r apps/api/requirements.txt -r migrations/requirements.txt
psql -h localhost -U postgres -d dma_insights -f infra/local/pg-init/01-iam-parity-users.sql
cd migrations && LOCAL_DATABASE_URL='postgresql+pg8000://postgres:local@localhost:5432/dma_insights' \
  alembic upgrade head        # expect >= 100 public tables, else alembic did not reach head

# Suites
LOCAL_DATABASE_URL='postgresql://postgres:local@localhost:5432/dma_insights' \
python -m pytest apps/worker/tests/ apps/mcp/tests/ apps/api/tests/ scripts/tests/ \
  plugins/dma-insights/scripts/tests/ tests/skills/ infra/jobs/tests/ -q -rs -rf
python -m pytest tests/schema/ -q
cd apps/web && npm ci && npm run build:proto && npm run test:web

# Architecture gates
for g in scan_secrets gate_a_no_inference_imports gate_c_no_render_dead_ends \
         gate_d_shared_files_ship gate_e_acceptance_coverage gate_f_declared_keys_have_readers \
         gate_h_prompt_persistence_claims gate_i_enrichment_drift gate_k_rejections_return \
         gate_l_ci_jobs_are_bounded; do python3 scripts/$g.py; done
python3 scripts/gate_b_ceiling_ratchet.py HEAD~1
python3 scripts/gate_j_surface_parity.py --reference-file fixtures/parity/reference-overview.json \
  --target-file fixtures/parity/target-overview.json --page overview   # exit 1 is CORRECT

# DQ / MECE work — INSTALLED v2.3 (the stale one; audit as drift, not design)
python3 plugins/dma-insights/skills/dma-research/scripts/extract_diagnostic_questions.py --help
python3 plugins/dma-insights/skills/dma-research/scripts/generate_query_plan.py --help
python3 plugins/dma-insights/skills/dma-research/scripts/validate_coverage.py --help

# DQ / MECE work — SUPPLIED v4.2 archive (the real system; Stages 5-6 target this)
unzip -q dma-research.skill -d /tmp/dmar && cd /tmp/dmar/dma-research
python3 scripts/build/validate_kg.py            # incl. G10 platform-agnostic, build-time only
python3 scripts/build/dq_generator.py --help    # generates the 5 MECE facets
python3 scripts/engine/kg_reader.py --help      # briefs / next / worklist / map-fact / guard
python3 scripts/engine/floors_gate.py --help    # --require-synthesis blocks Phase C
python3 scripts/engine/contingency.py --help    # Stage-2a cases A-H
python3 scripts/engine/ledger.py --help         # append-only ledger, stats
python3 scripts/engine/orient.py --help         # --skeleton, do_first
python3 scripts/engine/proxy_lib.py --help      # R30 proxy classes
python3 tests/golden/integration_smoke.py       # the skill's own golden run
python3 -c "import json;d=json.load(open('kg/catalog/index.json'));print(len(d))"
# facet completeness across all 851 briefs:
python3 - <<'EOF'
import json,glob,collections
c=collections.Counter(); miss=[]
for f in glob.glob('kg/packs/P*/P*C*.json'):
    for sid,b in (json.load(open(f)).get('subcaps') or {}).items():
        got=set((b.get('dq') or {}).keys())
        c[len(got)]+=1
        if len(got)<5: miss.append((sid,sorted(got)))
print('facet-count histogram:',dict(c)); print('incomplete:',len(miss), miss[:5])
EOF

# The seven checks (§4)
cat plugins/dma-insights/hooks/hooks.json                    # 4.1 what fires when
cat plugins/dma-insights/scripts/hooks/session_brief.py      # 4.1 the resident brief; note the source filter
for f in plugins/dma-insights/skills/*/SKILL.md; do printf '%6s w %5s l  %s\n' \
  "$(wc -w<$f)" "$(wc -l<$f)" "$f"; done                     # 4.1 size against the ~500-line guidance
wc -c plugins/dma-insights/skills/dma-surface-production/05-lifecycle/*.md   # 4.1 routing.md 17K, 1-gates.md 42K
python3 plugins/dma-insights/scripts/audit_skills.py         # 4.1 broken refs — note: NO size ceiling
# 4.4 offering linkage: ids, display-name collisions, unmapped subcaps
python3 - <<'EOF'
import json,collections
d=json.load(open('/tmp/dmar/dma-research/kg/catalog/offering_map.json'))['by_subcap']
ids=collections.defaultdict(set)
for v in d.values():
    for o in v: ids[o['offering_id']].add(o['offering'])
print('offering_ids:',len(ids),'| mapped subcaps:',len(d),'| unmapped of 851:',851-len(d))
print('ids with >1 display name:',{i:sorted(n) for i,n in ids.items() if len(n)>1})
EOF
# 4.5 every peer field and its grain, straight from the contract
python3 - <<'EOF'
import json,re
d=json.load(open('packages/shared/contracts_data.json'))
for p in d:
    for s,b in (d[p] or {}).items():
        h=sorted(set(re.findall(r'peer[a-zA-Z_]*',json.dumps(b))))
        if h: print(f'  {p}.{s}: {h}')
EOF
grep -nE 'incumbent_covers|INCUMBENT_COVERAGE_DISCOUNT|family_absent|STATE_TOO_NARROW' \
  packages/shared/platform_fit.py                            # 4.6 "already there" is modelled
grep -rniE 'contradict|refut|counter.evidence|disconfirm' \
  packages/shared/platform_fit.py apps/mcp/dma_mcp/fit.py    # 4.6 expect NOTHING — verify
grep -n -A8 '_NOT_SCORING *=\|def _is_pillar_tab\|_SCORE_KEYS *=' \
  apps/worker/dma_worker/workbook_parser.py                  # 4.7 what the app really accepts
for s in Evidence_Detail Negative_Findings Subcap_Synthesis Entity_Timeline Coverage Run_Metadata; do
  printf '  %-20s app-hits: %s\n' "$s" \
    "$(grep -rho "$s" apps/worker/dma_worker apps/mcp/dma_mcp 2>/dev/null | wc -l)"; done   # 4.7

# Pipeline + plugin state
python3 scripts/ingestion_status.py
python3 scripts/synthesis_queue.py
python3 scripts/audit_promoted_client.py
python3 plugins/dma-insights/scripts/audit_skills.py
python3 plugins/dma-insights/scripts/doctor.py
python3 plugins/dma-insights/scripts/agent_run.py --list
python3 plugins/dma-insights/scripts/setup_routines.py --help

# Production (needs gcloud + credentials — say so plainly if you lack them)
python3 scripts/verify_deployed.py
python3 scripts/verify_mcp_end_to_end.py
```

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

---

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

---

## 8. Deliverable

1. **Autonomy verdict** — one paragraph: can this repo run an unattended DMA end to end today? If not, the shortest list of things that must be true.
2. **Stage table** — the nine stages, one of the five verdicts each, one sentence of justification.
3. **The §1.1 thirteen-defect table** — each historical defect against the gate that now catches it, or **nothing does**.
4. **Headless blockers** — led by the §1.2 enrichment-connector finding, with the measured round-trip cost of the dispatch loop.
5. **Skill-version reconciliation** — what shipping v4.2 into the plugin costs (manifest, `scripts/requirements.txt`, `kg/` artefacts, packaging-validator limits), and what stays broken until it lands. State plainly whether the reasoning rigour the owner wants is *missing* or merely *unshipped* — the answers imply very different work.
6. **MECE DQ report** — five-facet completeness across all 851 briefs (histogram, with denominators), anti-clone (R22) collision count, the generic-render and post-G10 vendor-name findings, and the DQ→query drift rate.
7. **Reasoning-trap report** — the §6.1 table completed with enforcement status; a verdict on the §6.2 challenge layer's independence, on whether `provisional: true` survives to the app, and on the terminal state of an `open_conflict` with no human to ask; plus the §6.3 walk-through naming every gate the wrong-but-perfect conclusion passes.
8. **The seven owner-specified checks (§4)** — one verdict each, in order, each with its measurement:
   1. entry document and routing at the three moments — including whether the SessionStart hook fires at all in a headless run, and whether the brief survives compaction
   2. drift, memory, resumability, compaction — led by the kill-and-resume test and by where `$RUN` actually lives
   3. token optimisation across the KG — the claimed percentages reproduced or refuted, with a token apportionment for one category
   4. report templates and offering linkage — the unpinned template dependency, the `OFF-PMI` two-name split, the 393 unmapped subcaps, and whether linkage is referential or free text
   5. peer grain — every surface benchmarking at a grain other than category-for-reports / platform-for-app, with a verdict on the two pillar-grain surfaces
   6. platform-recommendation challenge — incumbency verified working, disconfirmation verified absent or present, and the draft question set with what answers each
   7. workbook template and app alignment — the scoring sheet re-measured, the six other sheets' fate established, and the grey-cell discipline tested
9. **Publication gap** — what building the four new deliverables costs, and whether it strains invariant 2 enough to need an owner decision.
9. **ABSENT–UNNOTICED register.**
10. **Findings**, worst first, each with measurement and `MEM-####`.
11. **Refuted leads** — every `[LEAD]` you disproved, and how.
12. **Could not determine** — with the access that would settle each.
13. **The three things to build first**, with the argument for that order.

A finding without a measurement is an opinion, and this repo will reject it.

---

## 9. Stop conditions

Stop and report immediately, without finishing the sweep:

- **Client data crossing an audience boundary** — an `entity_id` in a cohort pattern served to any audience, or `internal_only` content in a customer projection or a client-facing document.
- **A `foreign` evidence id** — a row belonging to another institution. Invariant 4: this halts production. Quarantine and escalate; never route around it.
- **Two institutions merged into one entity.**
- **A live credential in the repo or in any log you read.** Report location and rotation path; **never echo the value.** Known standing item: an owner-grade service-account key and a GitHub PAT are reported to sit in a shared Google Doc ("Secrets and Variables") awaiting the owner's decision — confirm rather than re-report that one.

---

## 10. Scope boundaries

- **Do not extend or import from `apps/dma-insights/`** (legacy snapshot). Auditing it as a source of divergence is in scope; treating it as the system is not.
- **Do not resolve the open decisions.** Retention for superseded runs (default: retain), `CLAIMED` vs `INFERRED` visual treatment, and partitioning (**not yet** — do not pre-build) are deliberately open. Finding them open is not a finding.
- **The 16-category adjudication is settled.** v7.0 has 16, not 17 (user-confirmed 2026-08-04). Code or maths following 17 is a bug; do not re-open the question.
- **Do not design the new architecture.** Your job is to establish what stands between here and it, precisely enough that someone can plan. Where a choice is the owner's — most obviously whether invariant 2 may admit file publication — surface it as a decision, do not settle it.
- **Change no behaviour.** No fixes, no refactors, no "while I was there."
- If a genuine conflict survives the §2.2 authority order, **stop and ask.**
