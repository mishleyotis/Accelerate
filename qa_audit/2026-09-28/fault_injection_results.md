# FAULT INJECTION RESULTS — 28-09-2026 · dma-insights 1.20.0

Harness: the plugin was copied to the scratchpad (`plugin_copy/`), a synthetic run was created by the plugin's own `scripts/stress_run_lifecycle.py` (34/34 checks passed, kept at `synth/lifecycle`), and each fault was injected on a fresh copy of that run. No client data, no credits.

| id | fault | expected | observed | result |
|---|---|---|---|---|
| F-01 | search/fetch error | bounded retry → fallback → logged degradation | not injected (needs a model-driven lane); `engine.pipeline` documents one retry for timeout/empty, none for own-terms failure; `--lane-retries 1` default | UNKNOWN |
| F-02 | 429/timeout | backoff, budget accurate | not injected; `cost_ledger.jsonl` + `--max-usd` refuse a second budget (documented, lifecycle REQ tested STOPPED state) | UNKNOWN |
| F-03 | plausible wrong data | sanity check rejects | CG-32 refuses a Clay task handle read as a result (server); Indeed `search_jobs` company filter has no guard in code | PARTIAL |
| F-04 | session dies mid-unit | resume, no duplicates, RUN_ID unchanged | `engine.cli resume --run R-STRESS-LIFE` recovers entity/mode/position/catalogue_drift from the workbook; registry + watchdog name the resume plan (stress REQ 5b 7/7) | PASS |
| F-05 | corrupt handoff JSON | schema validation fails loudly; nothing consumes it | `engine.assessment open` refused, but for floors NOT_RUN, never for the corrupt file; `engine.cli strip` refused naming missing fields (not "corrupt JSON") — the packet has no schema version to validate against | PARTIAL |
| F-06 | frozen-asset hash mismatch | hard HALT before work | tier of P1C1.1.1 changed in the copied catalogue → `resume` reports `catalogue_drift` (2d783cd2… vs ba439a73…), but `orient` served the P1C1 card and `search` appended a Search_Log row; `pipeline run` blocked earlier on a missing connector baseline, so drift was never reached | FAIL |
| F-07 | sub-agent over budget | partial return with status | `engine.brief handback` is computed from the sheets and has the same shape whether the lane finished or died (verified on the synthetic run) | PASS |
| F-08 | Drive mirror fails | remediation entry, work continues, user told | `--no-push` continues; no remediation queue artefact found (grep) | PARTIAL |
| F-09 | memory write rejected | merge+retry, never silent | no cap, no version token, no lock on any memory file (contracts_census Task 2) | FAIL |
| F-10 | schema version skew | consumer refuses naming both | engine contract set to v8: `validate` FAILS=0; `resume` reports "workbook contract 'v7' != engine's 'v8'" and continues | FAIL (names both, does not refuse) |
| F-11 | orphaned run | named owner | `dma_run_registry.jsonl` + `engine.watchdog` (STALLED / UNREADABLE with resume command) — owner is the watchdog routine | PASS |
| F-12 | injected instruction in fetched page | treated as data | not injected; `deny_whole_page_fetch` limits lanes to 240-char windows from `engine.cli fetch` (measured deny for research agent_type) | UNKNOWN |
| F-13 | relative dates | resolved against injected date | `recency_band` against the run's pinned reference_date 2026-08-30: 2026-05-01→CURRENT, 2025-06-30→RECENT, 2024-01-15→DATED, 2022-01-01→ARCHIVAL, None/'last quarter'/'garbage'→UNVERIFIED; '2025-Q4'→UNVERIFIED although the page contract says quarter dates ARE dates | PASS (3/3) with one contract mismatch |

## F-14 reproducibility (same ledger, three independent Sonnet scorers, subcap P1C1.1.1, 4 items)

| run | score | band | ceiling | label | rule cited | arithmetic |
|---|---|---|---|---|---|---|
| 1 | 2.5 | Building | 5.0 | INFERENCE | M3 match, −0.3 ARCHIVAL adjustment | states 3.0 − 0.3 = 2.5 (slip) |
| 2 | 2.7 | Building | 5.0 | INFERENCE | same | correct |
| 3 | 2.7 | Building | 5.0 | INFERENCE | same | correct |

Score range 0.2; band agreement 3/3; label agreement 3/3; rationale overlap: all three cite E-068/069/070/071 and the same two rules. The band rule held; the arithmetic did not (1 of 3). Recommendation: the adjustment arithmetic becomes an engine command (tools_spec.md `score_apply`). Note: all three cited "ceiling 5.0 (M5)" — the M5 vocabulary comes from dma-assessment SKILL.md:198-199 (F-L14-041).

## Idempotency and remediation paths
- Evidence registration refuses an excerpt the run never fetched (`excerpt_unverified`) — fail-closed, verified.
- Workbook writes are serialised by a file lock (doctor: "concurrent workbook writers SAFE").
- Duplicate queries are NOT deduplicated at the write (F-D05-033).
- Ledger rows are append-only; `append_payload_part` replaces by index (server contract).
- No remediation queue artefact exists for Drive or memory failures.
