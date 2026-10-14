# PROMOTION REPLAY — Axis O — 28-09-2026 · dma-insights 1.20.0

Run replayed: goeasy Ltd., run 21e3ed62 (seq 15 of 18 under request DMA-RES-GSY-20260830-0002), heatmap page, staged submission ce93fc24 (FAIL, 2026-09-02, producer_version `heatmap-surface-producer@2026-09-02-final-transport`, contract cr-02dcace3b2e7, 1,523,847 bytes across 9 sections).

## Ideal sequence (from the connector's own contract)
| step | calls | bytes |
|---|---|---|
| list_open_rejections + get_run_progress | 2 | — |
| claim_run | 1 | — |
| register_evidence once, id map persisted | 0 here (368 of 368 rows kept their package ids: discovered_by = package) | — |
| local validation (self_heal + local CG-15) | 0 | — |
| open_payload + 12 parts of 131,072 B + get_upload_status | 14 | 1.52 MB |
| submit_page_payload with expect for cells, evidence, alerts, rows | 1 | — |
| verdict into the run manifest; repair only the named section via get_staged_payload(section, part) | ≤2 more submits | ≤0.3 MB |
| promote_run once | 1 | — |
| total | ≈20 calls, ≈1.8 MB, ≤3 submissions for the page | |

## What actually happened (as far as the connector exposes it)
| observation | value | attributed check |
|---|---|---|
| open rejections on this page | 199 (CG-27 86, CG-15 65, CG-11 48), attempts = 2 each, open 25 days | O-04, O-07 (28% local catch), O-01 (nobody read the list) |
| page status | FAIL; five other pages PASS; promotable = false | O-05 not measurable (history hidden) |
| claim | held_by goeasy-surfaceprod-20260902, expired, live = false | O-02 not exercised |
| submissions per page | not exposed; get_run_progress returns only the latest submission_id | O-03 UNKNOWN → tools_spec `list_submissions` |
| producer_version | one value on the staged row; free string | O-12 PARTIAL |
| evidence registration | 368 of 368 discovered_by = package; no minted rows on this page | O-11: no duplicates here; no id map exists for minted rows |
| chunking | sections over 131,072 B chunked (cell_evidence 860,087; alerts 295,113; evidence 224,246); `expect_of` supplies expect per big list (ship_page.py:169-290) | O-08 PASS, O-09 PASS |
| repair path | staged section reads by part work (this audit read evidence parts 1–2 and cell_evidence part 1) | O-10 PASS as a mechanism |
| later runs | seq 16 (0 cells), 17 (696), 18 (696, PROMOTED 2026-09-03): the page was re-produced on new runs instead of repaired on seq 15 | O-05 likely violated (re-synthesis), F-O13-030 (18 runs, 12 empty ingests) |
| promote | seq 18 promoted; premature calls not exposed | O-13 UNKNOWN |
| withdraw | not exercised (production side effect) | O-14 UNKNOWN |
| feedback loop | 542 findings and 106 refinements in 60 days; 491 open, 151 at BLOCKER severity, 9 RECURRED, 50 ageing unrefined at 51 days | O-16 wired, but the queue is not draining |

## Extra round trips attributed
- 199 rejections at attempts = 2 on one page means at least two full-page submissions (≈3 MB) where a section-level repair would have cost ≤0.3 MB → O-07 and O-10.
- Three more runs ingested (seq 16–18) to reach PROMOTED means re-synthesis of a run whose five other pages were passing → O-05 and F-O13-030.
- The swbc insights ET-04 row at attempts = 5: five identical repairs of "E-158:F1 has an empty excerpt" → O-04; the change of approach the tool asks for (re-register with an excerpt) was never taken.

## Regression seeds checked here
Seed 16 (verdicts found by a person): still true. 200 rejections are open and nothing in the plugin reads `list_open_rejections` at session start; the instruction exists only as prose. Seed 18 (the CG-01 supersede trap): the recovery mechanism is documented and readable by part; it was not triggered on this run because cell_evidence is present.
