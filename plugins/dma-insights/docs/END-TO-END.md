# The pipeline, end to end, with nobody in the session

A completed Digital Maturity Assessment goes from a client folder to
promoted client surfaces without a human in the loop. This document is the
run: every command, what refuses and why, and what each stage hands the
next.

It exists because the headless-readiness audit measured the previous answer:
*"An unattended run to the owner's specification cannot currently finish:
one of its three mandatory deliverables has nothing that produces it, a
second is produced in a format the ingest classifier rejects, and the third
is produced once at the end from a substrate the agents never wrote."*
(AUD-0003.) Each stage below names the finding it answers, so a reader can
check the claim rather than take it.

---

## The one idea: the workbook is the record

The scoring workbook is not an export. It is where every research step
writes, as it happens, and every later stage reads from it — the gate, the
handoff, both reports, the app's ingest and the governance audit. There is
no second substrate for it to fall out of step with.

That is the whole of AUD-0001. Before it, `grep -rln 'openpyxl'` over the
research engine returned **zero files** — no research, synthesis, floors,
followup or ledger step could touch a sheet — and the workbook had one
producer that built a fresh `Workbook()` and saved it once at the end. Four
findings the audit had filed as siblings (the empty chain-integrity block,
the checksum nothing wrote, the auditor reading different sheets, the resume
that recovered nothing) are that one root.

Everything below follows from it.

---

## Stage 0 · Preflight the binding — with the financials, and with a person

```
cd plugins/dma-insights/skills/dma-research
python3 -m engine.preflight init --entity "Acme Credit Union" \
        --entity-id acme-cu --out $ROOT/preflight.json
# fill it, then:
python3 -m engine.preflight check --file $ROOT/preflight.json
```

The binding used to be two free-text flags. `vet_basis` refused FILLER —
`tbd`, `n/a`, anything under 20 characters — and accepted any fluent
sentence, which is the failure that actually costs a run: the 2026-08-29
Golden 1 calibration bound CU / FULL / PUBLIC on three strings the agent
wrote to itself, having read no financial statement and asked nobody.

So the basis is a DOCUMENT, and it carries three things a sentence cannot
fake:

1. **The financial-statement review.** Named statements with URLs, and the
   revenue lines read out of them, each naming the line of business it
   implies. An entity that publishes nothing records the search ladder in
   `financials.not_run` — registries, queries, dates — never an assertion.
2. **The LOB census.** Every material line of business (>= 10% of revenue),
   and for every plausible sub-vertical an ACCEPT or REJECT with a reason.
   A material LOB nobody examined is the multi-LOB trap: 165 variant cells
   selected on the strength of the first business found.
3. **The question, and the answer.** `AskUserQuestion` put to the engagement
   owner, recorded verbatim with who answered and when. The binding must
   MATCH the answer, and `check` refuses a preflight whose question was
   never asked. This is the only check in the engine that cannot be
   satisfied by reasoning harder — which is the point: an agent can talk
   itself into a sub-vertical and it cannot talk itself into a recorded
   human answer.

Two material LOBs, or two ACCEPTed sub-verticals, make the question
mandatory by rule. `check` prints every remaining problem at once so one
pass closes them all.

## Stage 1 · Start the run

```
python3 -m engine.cli start \
    --run   DMA-2026-ACME-001 \
    --entity "Acme Credit Union" --entity-id acme-cu \
    --reference-date 2026-08-29 \
    --preflight $ROOT/preflight.json
```

Sub-vertical, scope, evidence mode, `sv_basis`, `mode_basis` and
`lob_census` are all **derived** from the preflight — they are no longer
flags anyone can type. `start` does three further things in the same
command:

* **Banks the financial statements as evidence** and writes the review into
  `Report_Narrative` as `PRELIM-FIN`, so the Client Research Profile renders
  the review rather than researching the same statements again.
* **Opens the client folder.** `<Entity> - DMA` is created locally and in
  the intake Drive, carrying `run_manifest.json` at `status: IN_PROGRESS`.
  Folder creation used to live in `package`, which runs at the END and
  refuses until all four deliverables exist — so a run that stopped early
  left nothing an operator could find. It exists from minute one now.
* **Registers the run** in the append-only run registry, pushed to Drive.
  That registry is how the watchdog knows this DMA exists after the
  container is gone.

Creates the run tree and the workbook, **with its metadata already
resolved**. Two values are the anchors a resumed run reads and both are
refused if they still look like a template placeholder: `run_id` and
`catalogue_hash`. The audit found both shipping as `{{RUN_ID}}` and
`{{CHECKSUM}}` (AUD-0010).

* The sub-vertical and scope are **validated**. An unknown value refuses; it
  used to select 686 cells and exit 0, turning an upstream classification
  failure into a plausible-looking run (AUD-0077).
* The engagement set is **seeded as rows**. A seeded row is the scope
  declaration — which is how the app later tells "in scope, unscored" from
  "does not apply" (AUD-0014).
* `Handoff_Lock` is written: catalogue version, catalogue hash, contract
  version. The assessment stage compares against it and refuses to score if
  the catalogue moved (AUD-0060).
* `REF_Method` is written: the bands, tiers, recency ladder, claim labels
  and challenge dimensions this workbook is read under, rendered from the
  contract so they cannot drift from it.

## Stage 1a · PRELIM — the institution, before its capabilities

```
python3 -m engine.prelim state --run $RUN --root $ROOT
```

Six sections, each closed by RESEARCH or by a DECLARED absence with its
ladder, and `orient` serves **no category card** until they are:

| section | closed by |
|---|---|
| `financials` | the preflight, at `start` (may never be declared away) |
| `firmographics` | `engine.prelim narrate --section firmographics` |
| `leadership` | `engine.prelim narrate --section leadership` |
| `timeline` | `engine.prelim timeline` x3+ |
| `peers` | `engine.prelim peers --peer … --rule …` (frozen before any score exists) |
| `tech_baseline` | `engine.cli techscan record` x1+ |

Golden 1 went straight from `start` to a category worklist: twenty evidence
rows about six subcapabilities and nothing at all about the institution.
`Entity_Timeline`, `Tech_Register` and `Peer_Benchmarks` were empty at the
end because no phase had ever been asked to fill them, and the Client
Research Profile — whose whole first half is the client — had no material to
render from. Every narrative section must cite registered evidence: the
report renders it verbatim to a client, and an uncited paragraph about a
named institution is the shape of a hallucination.

## Stage 1b · Build the knowledge graph, then route by category

```
python3 scripts/drive_fetch.py pull-toolkits --dest $ROOT/toolkits
python3 -m engine.kg build --run $RUN --toolkits $ROOT/toolkits
python3 -m engine.kg route --run $RUN            # 16 categories, each naming its agent
```

The four pillar toolkits carry the diagnostic questions and, per subcap,
where each answer lives (internal sources, public sources, Source Type).
`kg build` seeds the workbook's `DQ_Bank` — 9 questions per subcap: the
toolkit primary, five facet probes, three AI-overlay — each with a
`Mode_Fit`, so the run's declared `--mode` (PUBLIC / INTERNAL / HYBRID)
decides which are askable; the rest ride as `INT-Q:`/`PUB-Q:` discovery
questions, never silent gaps. `kg route` is the dispatch table: one
category → one researcher (`research-p1c1-producer` …
`research-p4c4-producer`), sixteen in all, orchestrated by
`research-conductor`; the per-agent loop is
`skills/dma-research/references/RESEARCH-PROTOCOL.md`.

## Stage 2 · Work the categories

```
python3 -m engine.cli orient --run $RUN --category P1C1
```

`orient` is the session opener, and the rule it now holds is: **it may not
say the state is clean while anything is open.**

* A subcap with evidence and no synthesis is `volleyed`, and it is served
  next. It used to be skipped, never re-served, never closed, while orient
  printed *"state clean — proceed to next_card"* (AUD-0006, AUD-0085).
* At the search-op ceiling `do_first` leads with **STOP** and no card is
  handed over. The count used to be reported (45/40) and walked past
  (AUD-0037); the command that produced it crashed with `NameError` on every
  invocation (AUD-0008).
* Every question and query is rendered **with the entity bound**. A card
  still carrying a token is refused rather than issued — the previous one
  shipped fifteen literal `{entity}` placeholders and the agent fired them
  (AUD-0015).

Then, per card:

```
python3 -m engine.cli search    --run $RUN --subcap P1C1.1.1 --facet works --query '...'
python3 -m engine.cli evidence  --run $RUN --subcap P1C1.1.1 --source '...' --url https://... \
                                --tier T2 --published 2025-03-01 --excerpt '...'
python3 -m engine.cli synthesise --run $RUN --subcap P1C1.1.1 --json rec.json
```

Each write is checked **before it lands**:

| refusal | the finding |
|---|---|
| a query carrying an unbound token | AUD-0015 |
| an excerpt outside 50–500 verbatim characters | invariant 4 |
| a public source with no URL (register it `origin=internal` instead) | AUD-0029 |
| evidence naming a cell outside this run — the `foreign` halt | invariant 4 |
| placeholder or filler prose in any synthesis field | AUD-0009, AUD-0016 |
| prose naming no figure, date, proper noun or citation | AUD-0026 |
| a DQ facet neither answered nor `NOT_RUN: <reason>` | AUD-0017 |
| an absence claim with no `Absence_Claimed` and no proxy log | AUD-0079 |
| `FACT` resting on proxy searching alone | AUD-0021 |

## Stage 3 · Challenge — by somebody else

```
python3 -m engine.cli synthesise ... --actor surface-producer
# then, a DIFFERENT actor:
engine.ledger.record_challenge(wb, subcap, verdict=..., actor="finding-challenger",
                               dimensions={...seven...}, rationale="...")
```

The learning loop already had reviewer independence **by construction** —
`learning-grader` carries no Write/Edit and no connector write tool — and the
research challenge inverted it (AUD-0018, AUD-0024). Construction is not
available inside one library, so independence is made checkable: the
`Provenance` sheet records who did each step, and a verdict by the
synthesis's own author is refused.

All seven dimensions are required **by name**, and any `FAIL` forces an
overall `FAIL`. A zero-dimension verdict used to validate, and the shipped
card's own example silently omitted `synthesis_quality` (AUD-0102).

## Stage 4 · Gate the category

```
python3 -m engine.cli gate --run $RUN --category P1C1 --require-synthesis
```

Writes its verdict to **both** `$RUN/07_qa/floors_<cat>.json` and the
workbook's `Gate_Log`, and returns it. The previous gate printed to stdout
and had three readers and no writer, so a gate could FAIL with exit 1 and the
next `orient` report the state clean (AUD-0007). An **unrun** gate reads
`NOT_RUN`, never `PASS`.

Blocking terms: unresolved citations (AUD-0083), boilerplate, an unsupported
claim label, an undeclared absence, sibling evidence smearing (AUD-0076), a
missing or non-independent challenge, missing synthesis, DQ gaps, and the
≥20-item category floor — which used to be computed, reported, and not used
(AUD-0022).

## Stage 5 · Validate the workbook against its contract

```
python3 -m engine.cli validate --run $RUN
```

Seven rules, three of which never fired before:

* **rule 2** compares the **whole** header, so an added column is caught. The
  old slice stopped at column 11, and an unstripped 22-column working area
  passed the only gate on the file (AUD-0064).
* **rule 3** compares the **id set**, not a row count. Swapping in
  out-of-scope subcaps while holding the count constant used to pass
  (AUD-0014).
* **rule 5** has no blank branch. A blank `Evidence_IDs` is neither an E-id
  list nor the literal `NO_EVIDENCE`, and on a real workbook 44 of 49 rows
  were blank and it certified clean (AUD-0064).

The required sheet set **is** the generated sheet set — one object — so the
authority artefact cannot fail the gate meant to admit it (AUD-0012,
AUD-0061). A pre-v3 workbook is migrated by `patch_validator.py`, the script
the template's own changelog prescribes and that existed in no tree
(AUD-0011); it refuses rather than dropping a column it cannot map.

## Stage 5b · Is there anything IN the workbook?

```
python3 -m engine.completeness check --run $RUN
```

The validator checks SHAPE, and a sheet with correct headers and no rows
passes it — which is how the Golden 1 workbook validated clean while six of
its tabs were empty. This checks content: every tab is populated,
or carries a recorded reason in `Run_Metadata.empty_sheet_reasons`
(`engine.completeness declare --sheet … --reason "…"`). An empty tab with a
reason is a disclosure; an empty tab without one blocks the handoff and the
package. Nine sheets may never be declared empty at all — the run does not
exist without them.

## Stage 6 · Hand off, and report

```
python3 -m engine.cli handoff --run $RUN
python3 -m engine.cli report  --run $RUN            # both .docx
```

`research_handoff.json` is emitted as a **read-only index** over the
workbook's sheets and says so in its own `_contract` block. The workbook is
the handoff; `dma-assessment` Phase 0 opens it, validates it, compares
`Handoff_Lock.catalogue_hash` and **HARD STOPs** on drift (AUD-0002,
AUD-0032). An unresearched subcap carries a **null** band, not a default that
looks like data, and a category ceiling stays a band word rather than
becoming a float score (AUD-0078). A facet that never ran is `NOT_RUN` with
its reason, never `[]` (AUD-0138).

Both reports are **curated from the workbook** — the numbers in the document
are read from the sheets at render time, so the two cannot disagree
(AUD-0052). The render refuses on:

* one unresolvable citation anywhere (AUD-0033);
* a section under its blocking word minimum (AUD-0105);
* fewer than eight insight cards — the template's number, not the renderer's
  three (AUD-0145);
* a section every one of whose declared inputs is empty (AUD-0107). A focused
  engagement that leaves three pillar sheets empty **states its scope**
  instead, because refusing that would reject a correct run.

The filenames are the ones the app's classifier accepts. The previous client
report shipped as `client_profile.md`, which `classify()` returns `None` for,
so it was uningestable (AUD-0003).

## Stage 7 · Strip the working area — last, and only when it is safe

```
python3 -m engine.cli strip --run $RUN
```

The script the pinned workbook mandates, which existed nowhere in any tree
(AUD-0011). It **refuses** while `Triangulation`, `Why_It_Matters` and
`DMA_Impact` have no surviving copy: the workbook claims stripping costs
"nothing that matters downstream", and that is true of seven fields and false
of three, which the handoff did not carry (AUD-0065).

## Stage 7b · Assemble the client folder, and ship it

```
python3 -m engine.techscan render --run $RUN
python3 -m engine.assemble package --run $RUN --push
python3 -m engine.memory backup --run $RUN && python3 -m engine.memory cleanup --run $RUN --apply
```

`assemble package` builds `<Entity> - DMA` — the four client deliverables
plus the machine extras — verifies it against the output contract
(`engine.assemble verify`: workbook validation, the ≤15%-unURLed
evidence check in gate-M's shape, folder-name form) and, with `--push`,
creates-or-finds the folder under the intake Drive and uploads. Memory
cleanup runs last and **refuses** while any notebook entry is NOTED or
BLOCKED — the backup must land before the notebooks go.

## Stage 8 · Ingest

The package now holds four artefacts, and each has a producer **and** a
reader:

| artefact | produced by | read by |
|---|---|---|
| `DMA_Scoring_Workbook_<client>_<date>.xlsx` | `engine.cli` (throughout) | `workbook_parser.parse_scoring_workbook` / `parse_research_workbook` |
| `DMA_Assessment_Report_<client>_<date>.docx` | `engine.cli report` | `report_parser.parse_report` |
| `Client_Profile_Research_<client>_<date>.docx` | `engine.cli report` | `classification.classify` → `client_profile` |
| `Technographic_Scan_<client>_<date>.docx` (+ `technographic_scan.json`) | `engine.techscan render` | `workbook_parser.parse_technographic_scan` |

On the app side:

* a research-stage workbook reports `in_scope_unscored`, not `toggled_out`,
  and states its stage **once** rather than filing every row as a defect
  (AUD-0014);
* every evidence row keeps its `SubCap_IDs` linkage — the column the census
  reported present and the read never used (AUD-0067);
* `01_evidence/evidence_index.json` is classified, parsed and merged
  asymmetrically: it fills what the workbook left blank and never overwrites
  what the workbook stated (AUD-0091);
* the report parser kinds a section by its **heading**, so a v8 report's §3
  is not stored as `trend_analysis` (AUD-0039);
* `get_run_progress` reports what the intake could not read, so a producer
  can tell an unrecognised column from an entity with nothing to say
  (AUD-0030).

## Stress-testing the pipeline

`scripts/stress_research_pipeline.py --toolkits <dir> --workdir <dir>`
drives every stage above through the same CLI the agents use, against the
REAL pillar toolkits, and passes only when each stage does the right thing
— which for the bad-note consolidation, the self-challenge, the unfinished
floors gate, the L2 layer key, the blocked cleanup and the incomplete
package is a refusal with a named reason. 20/20 measured 2026-08-29.

## Stage 9 · A run that stops says so — and then gets restarted

```
python3 -m engine.registry pull            # Drive's copy of the population
python3 -m engine.cli status --root /home/claude/dma_output
python3 -m engine.watchdog --revive        # act, don't just report
```

`STALLED` · `HALTED` · `GATE_FAILED` · `UNGATED` · `AT_BUDGET_CEILING` ·
`READY_FOR_HANDOFF` · `PRELIM_OPEN` · `NO_CLIENT_FOLDER` ·
`MISSING_LOCALLY` · `PROGRESSING`. The synthesis side had this and the
research side had nothing, so a turn that died mid-category left no artefact
saying so (AUD-0063). `UNGATED` exists because running out of cards is not
closure.

Two later defects, both closed:

* **It could not see a new DMA.** `sweep` listed `$DMA_RUN_ROOT`, a
  directory that does not survive the container, so a scheduled firing found
  zero runs and printed "no research runs" — indistinguishable from a
  healthy queue. Every `start` now writes an append-only **registry** row
  and pushes it to Drive; the sweep reads that, so a run this container has
  never seen still appears, as `MISSING_LOCALLY`, carrying the command that
  brings its workbook back.
* **It could not restart anything.** Every state was a report. A watchdog
  that detects a stall and takes no action has moved the stall from "nobody
  noticed" to "somebody noticed and nothing happened". `--revive`
  re-dispatches the stopped stage through `scripts/agent_run.py` under the
  owning agent's own front matter; where dispatch is genuinely unavailable
  it returns `NOT_RUN` with the reason and the resume prompt, never a silent
  pass. `HALTED` (the catalogue moved) and `UNREADABLE` are never revived
  automatically — those are decisions, not restarts.

Every row carries a `resume` plan naming the agent and the prompt, so the
hourly watchdog routine dispatches rather than composes.

Resume needs no human:

```
python3 -m engine.cli resume --run $RUN
```

reads the entity, the checkpoint and any catalogue drift out of the
workbook. The documented resume had three steps, of which one command did not
exist, one was a person, and one read a checkpoint no script wrote
(AUD-0010).

---

## What still needs a person

`scripts/aud_ledger.py --open` lists every finding this pass did not close,
worst first, with the file it names. Nine BLOCKERs remain open; none of them
is in the research→assessment→ingest path this document describes, and each
is stated rather than absorbed.
