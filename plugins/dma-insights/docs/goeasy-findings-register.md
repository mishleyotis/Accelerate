# goeasy Ltd. findings register — root causes and the gates that close them

Every issue observed while producing the goeasy-Ltd package (2026-09-01), the root
cause, and the durable fix. The gate that now makes each one loud lives in
`engine/gold_standard.py`; every gate is exercised by
`tests/skills/research_engine/test_gold_standard.py`. The gold standard those gates
are calibrated to is the **Golden 1 Credit Union** reference package
(`docs/GOLD-STANDARD.md`), named by the engagement owner as the best so far.

The findings share ONE deep root cause: **the work went around the pipeline.** The
run's assessment stage was never run; the research workbook was hand-scored in place
and the reports were authored by a general agent to the client template. So the
engine's real gates (`validator`, `completeness`, `quality`, `report_spec`) never ran
on what shipped, and there was no single gate that knew what a *finished* package must
contain. `gold_standard.py` is that missing gate, and it is meant to be run by the
PRODUCER on its own output before returning — not by a reviewer after.

| ID | Issue observed | Root cause | Gate |
|----|----------------|-----------|------|
| GSY-15 | The 23-sheet **research** workbook shipped where the 43-sheet **assessment** workbook belonged (no Executive_Summary, Firmographics, Focus_Areas, Issue_Register, Solution_Catalogue, weighted rollups, M-band labels). | The assessment stage (`dma-assessment`) that builds the gold-standard workbook was never run; the research workbook was hand-scored. | `GS-WB-STAGE` |
| GSY-17 | No Executive_Summary dashboard (overall + M-band, peer median, gap, coverage, headline). | Same — the dashboard is an assessment-stage artefact. | `GS-WB-DASHBOARD` |
| GSY-16 | Evidence gaps were hidden (first left N/A, then silently proxy-scored) instead of disclosed. The reference **scores every cell AND discloses** `Scored / Unknown_EvidenceGap / Coverage_Pct` per category. | No coverage-disclosure contract; the producer improvised gap handling three different ways in one session. | `GS-WB-COVERAGE`, `GS-RPT-COVERAGE` |
| GSY-01 | 380 subcaps rendered blank (unscored). | No packaged scoring step; scoring policy was improvised. | `GS-WB-SCORES` |
| GSY-02 | `0` in a Priority column; `N/A` in value columns. | A priority formula that could reach 0; a fill that used banned tokens. | `GS-WB-NOZERO`, `GS-WB-NOHEDGE` |
| GSY-03 | `SubCap_Name` blank on 656 rows. | The research engine leaves column B empty; nothing populated it from the catalogue. | `GS-WB-NAMES` |
| GSY-04 | Peer scores and platform readiness read "Not established this run"; hedges throughout the reports. | Peer benchmarking and readiness were never computed; hedge language was accepted. | `GS-WB-PEERS`, `GS-RPT-NOHEDGE` |
| GSY-05 | Reports built as **blank** `.docx` — the client's fonts/theme/header were thrown away. | The author called `Document()` (blank) instead of authoring into the branded template; the engine renderer was bypassed. | `GS-RPT-BRANDING` |
| GSY-06 | Reports missing template sections (produced §1–6 of an 8/11-section template). | The full template section list was never read before authoring. | `GS-RPT-SECTIONS` |
| GSY-07 | Leftover `{{TEMPLATE_TOKENS}}`. | No token sweep. | `GS-RPT-NOTOKENS` |
| GSY-08 | Reports shallow — authored from summary docs, not the 568-row evidence base. | No depth floor; no requirement to mine the evidence tabs. | `GS-RPT-CITATIONS`, `GS-RPT-LENGTH` |
| GSY-09 | No AI-and-data overlay (the template requires one per pillar). | No section-content contract for the overlay. | `GS-RPT-AIOVERLAY` |
| GSY-10 | Recommendations had no rebuttal (deferred as "surface-stage"). | Rebuttal treated as a downstream artefact; it is an argument and is always authorable. | `GS-RPT-REBUTTALS` |
| GSY-11 | Confusion over a fifth band. Clarified: the maturity **score** is numeric (the reference writes "2.25 (M2)"); only a reachable fifth **band** word must never appear — inventing one is the invariant 6 breach, and it is forbidden in code, enum and prose. | An over-strict reading of the band invariant that would have failed the reference itself. | `GS-RPT-BANDS` |
| GSY-12 | Pillar_Summary duplicated to 8 rows during recompute. | **NOT an engine bug** — reproduced in isolation, `grains._replace` is correct. It was caused by hand-editing the workbook out-of-band between engine calls. The fix is to stop editing the workbook outside the engine, which GSY-15's gate enforces by requiring the assessment artefact. | `GS-WB-GRAINS` |
| GSY-13 | Report figures drifted from the workbook when scores changed. | No reconcile check between the two. | `GS-RPT-RECONCILE` |
| GSY-14 | Package not verified conducive for app ingestion. | No ingestion gate. | `GS-ING-*` |
| GSY-18 | Reports and workbook lacked depth — no multi-year financial trajectory (the reference carries a 5-year+ series; a public issuer's is richer still). | No depth floor for financials; the series was authored only when asked, then had to be back-filled. | `GS-WB-FINANCIALS`, `GS-RPT-FINANCIALS` |
| GSY-19 | Subcaps closed as "no evidence" with no enrichment effort; most runs evidence-deficient; the five volleys and the DQ set never fired (owner, 2026-09-03). | `absence_unsearched` cleared on ONE logged query and the DQ-coverage check ran only on synthesised rows — a cell could close empty on a single `works` search. | `volleys_incomplete` and `absence_undeclared_empty` (blocking floors-gate terms); `engine.cli absence` is the only way to close an empty cell |
| GSY-20 | Report writing started before scoring; reports did not follow the required format. | No scoring stage existed on the research workbook; `report_spec` sections were invented in code rather than read from the owner's Docs; nothing checked scoring or completeness before a write. | `engine.assessment` (open/score/critique/rollup/gate), `narrative.stage_preconditions`, `references/templates/report_templates.json` |
| GSY-21 | Workbook shape drifted every run — missing fields, no formatting, blank subcap names. | Contract carried 11 core pillar columns and none of the template's dashboard, rollup, profile or overlay tabs; `SubCap_Name` was never seeded; no header formatting. | Contract v6 (40 sheets), `catalogue_v70_names.json` seeding, `_format_sheet`, `engine.template bind`, `GS-WB-NAMES` |
| GSY-22 | Every Gap_to_Peer shipped null. | `prelim.peers` froze the set and left `Peer_Median` blank; no writer for the figure existed anywhere. | `engine.prelim peer-median` (basis vocabulary, quartile sanity, `cannot_estimate` → honest null) |
| GSY-23 | Token bleed at promotion — the six pages produced from scratch after the assessment ended. | Nothing told the surface producer which pages the workbook could already feed. | `engine.ship state` (`ready_pages` / `dispatch_now`), `engine.assemble checkpoint`, `ship_page.py --incremental` |

| GSY-24 | No orchestration between the main agent and its subagents: sixteen category lanes worked the same entity and could see nothing the others had found, a resumed lane got a COUNT of its notes rather than the notes, and the conductor either dispatched with "the run id and nothing else" (the lane re-finds the background) or pasted its own context (the token bleed). | `orient` carried PRELIM's background and nothing since; `memory.status` reported counts; no view existed of the run's own state, and no dispatch packet existed at all. | `engine.brief` — `shared`, `dispatch`/`batch`, `reuse`, `handback`; bounded by `BRIEF_CHAR_CEILING`, derived from the sheets, wired into the conductor's dispatch, all sixteen producer manifests and the session hook. Acceptance: `tests/acceptance/test_acceptance_orchestration.py`. |

## The one-turn discipline (why issues were caught in QA, not prevented)

The session reached the gold standard by **iteration** — each defect was found by the
owner, fixed, re-filed. The cost of that is in `docs/GOLD-STANDARD.md`: a producer must
(1) read the deliverable contract and the reference before authoring, (2) author to it,
and (3) run `gold_standard` on its OWN output and not return until it passes. A finding
that a gate catches is a finding the producer should have caught in step 3. The gate is
the producer's pre-flight, not the reviewer's post-mortem.
