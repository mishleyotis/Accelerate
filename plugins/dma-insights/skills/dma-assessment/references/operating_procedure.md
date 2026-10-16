# Operating procedure — context, memory and the run tree

How the scoring stage is worked without exhausting a context window, and where its state
lives. Rewritten 29-09-2026 (QA audit F-L11-042 / prompt-craft scorecard row 3): the
previous version described a JSON checkpoint plane (one file per phase beside the run, a
scoring scratchpad converted to a second workbook) beside a skill whose first rule
is that it BUILDS NO WORKBOOK. The workbook the engine created is the state; nothing else is.

## The state is the workbook

- `engine.cli start` created the run's one workbook (`${CLAUDE_PLUGIN_ROOT}/skills/dma-research/engine/contract.py`: 41 sheets) and
  `engine.assessment open` flips it to the scoring stage. Every `engine.assessment score` is
  a durable write to column D of that workbook; every critique, rollup and gate lands in its
  tabs (`Gate_Log`, the scoring packet `07_qa/scoring.json`). There is no scratchpad to
  convert and no checkpoint file to save: a score written is a score kept.
- **Resume** is `engine.assessment state --run <R> --root <ROOT>`: which pillars are open,
  which rows are unscored, which critiques and gates are recorded. Never re-derive position
  from the conversation; a remembered position that disagrees with `state` is wrong.
- The run id and the evidence mode are in the run manifest (`run_manifest_v3`,
  `engine.assemble`), pinned at `engine.cli start` and immutable; every artefact the run
  produces carries them, and `engine.cli validate` refuses a mismatch.

## Context discipline

| Phase | Budget | How |
|---|---|---|
| 0 setup | ~2,000 tokens | `engine.assessment state`; the brief the driver handed you |
| 4 scoring | ~25,000 per pillar | one capability at a time (5–12 rows), from the scoring packet |
| 4.5 critic | ~8,000 | `engine.assessment critique`, table output |
| 5–6 analysis, recommendations | ~10,000 | computed output; `engine.assessment solution` |
| 7 deliverables | ~15,000 | `engine.cli narrative write`, section by section |
| 8 QA | ~4,000 | `engine.assessment gate`, `engine.gold_standard` — computed verdicts |

**Anti-bloat rules**

1. Go straight to the command — no "Let me now…" and no restated methodology; it is in the
   references.
2. Phase-gate acknowledgements: at most five lines.
3. Scoring rationales go into the workbook through `engine.assessment score --rationale`,
   never into chat; chat gets one summary line per capability
   ("P1C1: 8 rows scored, range 1.5–3.0, 3 caps applied").
4. Deliverables: the command and its output, not explanatory prose.
5. Approaching the context limit: finish the capability you are on, then end the turn —
   the workbook holds everything, and `engine.assessment state` is the resume.

**One capability at a time.** The driver's packet (`engine.brief scoring-batch`) carries,
per unscored row, the dominant claim, the claim label, the ceiling band, the challenge
verdict and the evidence count — what a scorer needs to strike the row without opening the
evidence register whole. Score all the rows of one capability so they DIFFERENTIATE (the
gate refuses a capability whose rows all carry one score), chain the `score` commands in one
Bash call, then take the next capability. Never load the full evidence index into context:
`engine.brief reuse --subcap <cell>` reads one cell's rows when a rationale needs the excerpt
itself.

**If chat stalls or requires "continue"**, you are printing too much. The commands write to
the workbook; chat gets the summary line.

## Memory

- The **scoring packet** (`07_qa/scoring.json`, written by `engine.assessment gate`) is the
  stage's own record of every scored row, its arithmetic and its gate terms; the handoff to
  the report tier verifies it.
- The **QA memory** (`references/qa_error_log.md`, the master template) is copied once per
  run to `<run root>/07_qa/qa_error_log.md` and read at every phase gate; an entry added
  during the run is a finding the qa-overseer records into the findings memory at the end.
- **Caching:** evidence is immutable once registered; peers are immutable after PRELIM;
  scores are mutable, and a cap change invalidates the rollup downstream — re-run
  `engine.assessment rollup` and the gate rather than editing a figure.

## The run tree

The run root is `<ROOT>/<RUN_ID>/`; `engine.runstate.SUBDIRS` owns the subdirectories
(`00_entity_profile`, `01_evidence`, `02_search`, `07_qa`, `09_deliverables`), and the package
the run ships (`engine.assemble package`) is the `<Entity> - DMA` client folder with its four
deliverables — the scoring workbook, the client research profile, the assessment report and
the technographic scan. Nothing is written by hand into the tree; the commands own their
paths, and `engine.cli validate` and `audit_dead_contracts.py` refuse an artefact nothing
reads.
