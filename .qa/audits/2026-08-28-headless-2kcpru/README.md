# Deep QA — DMA Insights: can this repo run an unattended, headless DMA?

**Final.** Read-only audit of `mishleyotis/Accelerate` at `cdea0e1`.
Prompt fingerprint `52ca18a5a10ae0b675387d0ad058d3dc6de4d5a0fd90246ca3c3e4acd5882ae7`.

## Status

| | |
|---|---|
| Checks | **158** — 156 `DONE`, 2 `BLOCKED`, 0 `NOT_APPLICABLE` |
| `DONE` rows failing the 30-char measurement gate | **0** |
| Phase reached | **P5** (deliverable), all phases closed in order |
| Findings | **151** — 51 BLOCKER, 80 MAJOR, 17 MINOR, 3 INFO |
| Verdicts | 99 PRESENT–DEFECTIVE · 29 ABSENT–UNNOTICED · 26 PRESENT–SOUND · 4 PRESENT–HUMAN-DEPENDENT · **0 ABSENT–BY–DESIGN** |
| Deliverable items | **15 of 15** |
| Repo state | **unchanged** — `cdea0e1`, working tree clean, verified byte-identical |

The two `BLOCKED` rows both carry PRESENT–DEFECTIVE and are blocked on data that does not exist
in either tree (no archived challenge-verdict corpus; no GCP credential for a live deploy probe).
Each names the access that would unblock it — see deliverable 14.

## Read this first

**`.qa/dma-headless-audit.html`** — the report. All fifteen deliverables in order, with a
navigation index at the top. 294 KB, self-contained, light and dark.

## The evidence behind it

| File | What |
|---|---|
| `.qa/ledger.jsonl` | Append-only. 514 rows, 162 unique ids — **collapse last-row-per-id** to read final state. Every `DONE` row carries a re-runnable measurement. |
| `.qa/audit-prompt.md` + `prompt.sha256` | The prompt this was run against, and its fingerprint. |
| `.qa/artifacts/findings.jsonl` | 151 findings: title, severity, component, observed, measurement, headless consequence. |

## Consolidated deliverables

| File | Item |
|---|---|
| `.qa/artifacts/d3-stage-table.md` | 3 — the nine stages, one verdict each, with the roll-up rule stated |
| `.qa/artifacts/s1.1-defect-gate-table.md` | 4 — the thirteen historical defects against the gate that now catches each |
| `.qa/artifacts/d6-shipping-v42.md` | 6 — what shipping v4.2 costs, and what stays broken until it lands |
| `.qa/artifacts/d7-mece-dq-report.md` | 7 — five-facet completeness, anti-clone, generic render, G10 vendor names, DQ→query drift |
| `.qa/artifacts/d8-reasoning-trap-report.md` | 8 — fourteen traps with enforcement status; three challenge-layer verdicts |
| `.qa/artifacts/s6.3-wrong-but-perfect.md` | 8 part C — the eight-leg walk-through, every gate the wrong conclusion passes |
| `.qa/artifacts/d9-owner-checks.md` | 9 — the seven owner-specified checks, in order, each with its measurement |
| `.qa/artifacts/d11-absent-unnoticed.md` | 11 — the 29-row register of gaps nothing records |
| `.qa/artifacts/d12-findings-worst-first.md` | 12 — all 151 findings worst-first, with `AUD-####` ids |
| `.qa/artifacts/d13-refuted-leads.md` | 13 — every `[LEAD]` disproved, and how |
| `.qa/artifacts/d14-could-not-determine.md` | 14 — with the access that would settle each |
| `.qa/artifacts/d15-build-first.md` | 15 — the three things to build first, and the argument for that order |
| `.qa/artifacts/s5.1-autonomy-registers.md` | 5.1 — the silent-failure and human-dependency registers |
| *(report section `#d5b`)* | 5.2–5.5 — the twelve invariants tested by mutation, gate coverage, test-suite honesty, doc drift |
| *(report section `#apxc`)* | Cross-check — reconciliation against an independent second audit run |
| `.qa/artifacts/d16-second-pass-verification.md` | Method — what a second pass changed, including two of my own errors |
| `.qa/artifacts/refutations.txt` | Raw refutation log |

## The owner's target, restated — the reframe that governs the rest

After assembly the owner restated the goal: **three output artifacts** (DMA Scoring Workbook
contract v3, Client Research Report, Assessment Report), **every agent recording to the
workbook**, the reports **curated from it** after evidence synthesis, all published to the app.
Report section `#d2b` measures the pipeline against that target: zero engine scripts can touch a
sheet (the workbook is written once, at the end, by one producer); the reports read five JSON
files and zero sheets; the de-facto research→assessment contract is `research_handoff.json`
(dma-assessment SKILL.md:401 switches on its presence) — an artifact the target does not name;
and of the three canonical artifacts, only the workbook has both a producer and an app-side
reader, the client report ships as `.md` the classifier rejects, and **no Assessment Report
renderer exists at all**. Repair hints that add readers of the JSON plane would entrench the
deviation; the repair direction under the target is to move recorded state into the workbook.

## Cross-checked against an independent second run

A separate execution of this audit (`claude-sonnet-5`, 24-agent fan-out, branch `…-82e4gl`,
**different prompt fingerprint** `bdc8fdab…`, 149 checks / 110 findings) was reconciled against
this one — see report appendix C. It independently corroborated a dozen measurements including
the 851/851 facet census, the toothless anti-clone WARN, the untailored render at exit 0, the
post-G10 vendor reinjection, and the invariant 7 violation. It surfaced **four** things this run
missed, each re-measured here from source before acceptance — most importantly that
`ACCEPTANCE.md:285` claims **CI enforcement** for the very invariant-7 rule nothing checks.

**Two of its conclusions did not survive re-measurement.** Its ABSENT–BY–DESIGN verdict on stage 8
rests on the PRD phrase "Read-only thereafter", which in context is step 4 of the ingestion
pipeline, not a scope decision about publication. And entity resolution is a five-rung confidence
cascade, not "a bare name-slug match". Two further divergences (drift rate, `map-fact` error rate)
are unit mismatches and a genuinely unresolved sampling difference, recorded as such rather than
averaged away.

## Two things to know before acting on this

**No memory writes were made** — note that the second run recorded 105 of its 110 findings, so a dedup pass is now mandatory before minting these. The prompt authorises writing findings to the findings memory,
and minting `MEM-####` ids is that write. It was not done: recording 151 rows is a write to the
production store (`{open: 275, resolved: 51, all: 326}`), several findings duplicate rows already
there, and the standing instruction in this session narrowed the deliverable to the report. The
findings carry local `AUD-####` ids instead. To mint them, run the list through
`register_finding` with a `defect_class` from `list_defect_classes`, after a `search_findings`
pass per row. Reversible in one sentence from the owner.

**One figure was corrected after a verifier refuted it.** The routing-anchor count shipped as
"50 of 55" and is **48 of 53 data rows** — the 55 counted header and separator rows. I had
"confirmed" the original by re-running the same grep, which laundered another agent's error
rather than testing it. The lesson is recorded in `d16`: *re-running someone's command is not
verification; verification is measuring the same thing a different way.*

## Scope honoured

Read-only on behaviour — no fixes, no refactors, nothing "while I was there". The three open
decisions (retention, `CLAIMED` vs `INFERRED`, partitioning) are left open. The 16-category
adjudication is treated as settled. `apps/dma-insights/` is audited as a source of divergence
and never treated as the system. The one decision that is genuinely the owner's — whether
invariant 2 may admit file publication — is surfaced with its options and **not chosen**.

No stop condition fired: no client data crossed an audience boundary, no `foreign` evidence id
was seen, no two institutions were merged, and no live credential was found in the repo or in
any log read. The known standing item (an owner-grade key and a PAT reported to sit in a shared
Doc awaiting the owner's decision) was confirmed as already-reported, not re-reported, and no
value was echoed.

## The independent second run

`.qa/cross-check/second-run-audit.md` is a separate execution of this audit supplied by the owner
(`claude-sonnet-5`, 24-agent fan-out, branch `…-82e4gl`, **different prompt fingerprint**
`bdc8fdab…`, 149 checks / 110 findings). Appendix C of the report reconciles the two line by line:
36 of its 49 BLOCKERs correspond to findings already here, six were genuinely new and are now
filed after independent re-measurement, two of its conclusions did not survive re-measurement, and
one of its claims is recorded UNTESTED because this session could not reach PR #2.

## Reproducing the report

`ledger.jsonl` and `.qa/artifacts/findings.jsonl` are the inputs; the report is generated from them,
so any figure in the HTML can be traced to a ledger row by its check id.
