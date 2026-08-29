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

## Stage 1 · Start the run

```
cd plugins/dma-insights/skills/dma-research
python3 -m engine.cli start \
    --run   DMA-2026-ACME-001 \
    --entity "Acme Credit Union" --entity-id acme-cu \
    --sv CU --scope FULL \
    --reference-date 2026-08-29
```

Creates the run tree and the workbook, **with its metadata already
resolved**. Two values are the anchors a resumed run reads and both are
refused if they still look like a template placeholder: `run_id` and
`catalogue_hash`. The audit found both shipping as `{{RUN_ID}}` and
`{{CHECKSUM}}` (AUD-0010).

* `--sv` and `--scope` are **validated**. An unknown sub-vertical or scope
  mode refuses; it used to select 686 cells and exit 0, turning an upstream
  classification failure into a plausible-looking run (AUD-0077).
* The engagement set is **seeded as rows**. A seeded row is the scope
  declaration — which is how the app later tells "in scope, unscored" from
  "does not apply" (AUD-0014).
* `Handoff_Lock` is written: catalogue version, catalogue hash, contract
  version. The assessment stage compares against it and refuses to score if
  the catalogue moved (AUD-0060).

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

## Stage 9 · Nothing is watching, so the run says when it has stopped

```
python3 -m engine.cli status --root /home/claude/dma_output
```

`STALLED` · `HALTED` · `GATE_FAILED` · `UNGATED` · `AT_BUDGET_CEILING` ·
`READY_FOR_HANDOFF` · `PROGRESSING`. The synthesis side had this and the
research side had nothing, so a turn that died mid-category left no artefact
saying so (AUD-0063). `UNGATED` exists because running out of cards is not
closure.

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
