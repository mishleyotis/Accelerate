# TEMPLATE ALIGNMENT — Axis M — 28-09-2026 · dma-insights 1.20.0

## M-01 Template inventory
| template | source | version | sha256 (template_binding.json of the synthetic run) | filled by |
|---|---|---|---|---|
| workbook_template.json (sheet structure, columns) | references/templates/ | requires_plugin_version 1.20.0 | 0671b4a6487d0168… | engine.workbook.create (research), engine.assessment stage (assessment tabs) |
| report_templates.json (control blocks) | references/templates/ | 1.20.0 | 7c6d78cb338d3189… | engine.narrative |
| client_profile_template.md | references/templates/ | — | 034756e7e75d6a75… | report-research-producer via engine.cli report |
| assessment_report_template.md | references/templates/ | — | 6a33fe1c597d750a… | report-assessment-producer |
| report_shell.docx | references/templates/ | — | f91347d6b7b9cf36… | engine.reports (copy, then fill) |
| gold_reference.json (Golden 1 measurements) | references/templates/ | — | 6056ddd32c740067… | gold_standard gate |
| combined digest | template.pinned_digest | — | c341416eaa504f352d66237fcaec537bd7749d0feebbd23db88359e91b9dbecf | pinned into Run_Metadata.template_binding at start |
| page contracts ×6 | `get_page_contract(page)` (server) | contract_version cr-02dcace3b2e7 on the heatmap staged row | server-side | per-surface producers; surface_export.scaffold |
| catalogue v7.0 | engine/data/catalogue_v70_tier.json | v7.0 | 2d783cd2997ed4c5… (cell ids + tiers) | every stage |
| deck templates (9 sub-vertical PPTX) | dma-first-call-deck assets | unversioned in SKILL.md | not pinned per run | first-call deck |

## Checks
| id | result | evidence |
|---|---|---|
| M-01 | PASS for engine templates; deck templates unversioned | table above |
| M-02 | PASS (pin); mid-run change not injected | `engine.template bind` writes the digest at start; `binding_state` reports stale; `orient` withholds cards while blank or stale. Only the catalogue was mutated in this audit (F-06): detected at resume, not halted |
| M-03 | PASS | report_shell.docx copied then filled by engine.reports; workbook created from workbook_template.json |
| M-04 | PARTIAL | `references/section_sources.json` and `tab_recording_map.json` (generated, workbook_contract v7) map every page section and card to workbook tabs and columns or report sections. No single map links workbook column ↔ report section ↔ contract path; the report side is per-section prose controls |
| M-05 | UNKNOWN | no shipped deliverables on disk; `engine.template report_drift` and `gold_standard` exist to run against them |
| M-06 | PASS | the driver passes the contract PATH in page briefs; surface-producer refuses a remembered shape; `scaffold_card` refuses item keys the contract does not declare |
| M-07 | PARTIAL | `producer_version` is a free string (`heatmap-surface-producer@2026-09-02-final-transport`); the template digest is in the workbook but not in the payload; the contract version is recorded server-side only |
| M-08 | FAIL | `engine.template drift(path)`, `report_drift()` and `gold_standard workbook / report / package` (27 GS ids) exist as tools; no hook runs them on a deliverable write and nothing blocks a push (grep scripts/hooks: none) |
| M-09 | UNKNOWN | no run to measure; record drift per stage in run_manifest.gates |

## `template_diff` today
`engine.template drift <workbook>` compares sheet headers to workbook_template.json; `report_drift()` compares the two report Docs' section trees; `gold_standard report` checks placeholders, hedges and bands; `gold_standard package` checks the four deliverables. Missing: formulas, named ranges and data validations on the workbook; renamed-header detection is header-set only.

## Hook specs for M-08
1. PostToolUse on Bash matching `engine.cli report`, `engine.assemble package`, `engine.techscan render`, `engine.cli strip`: run `gold_standard <artefact>` and `engine.template drift`; write `{artefact, sha, verdict, at}` into `run_manifest.gates`; exit 0 with a systemMessage on FAIL; 1–3 s, acceptable at stage boundaries only.
2. PreToolUse on Bash matching `drive_fetch.py push`, and Stop at PACKAGE: read `run_manifest.gates`; deny (exit 2) while any deliverable's latest verdict is not PASS; under 50 ms.
3. Positive test: a report with an unfilled `[X.XX]` placeholder records FAIL and the push is denied. Negative test: PASS on all four allows the push. Deletes the prose "Do not hand back an artefact until the gate prints PASS" in the conductor and surface-producer manifests.
