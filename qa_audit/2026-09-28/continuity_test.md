# CONTINUITY TEST — Axis N — 28-09-2026 · dma-insights 1.20.0

## Run manifest (N-01) — FAIL
Three shapes exist for `run_manifest.json`: engine (`engine/assemble.py:162`, nested `institution`, no `$schema`), governance (`generate_governance_outputs.py:390`, `$schema: run_manifest_v2`, versions defaulting to "5.0"), and the auditor's expectation (`gov_auditor.py:261`, flat `institution_name`, `overall_score`, `pillar_scores`, `evidence_count`). The engine manifest carries entity, sub-vertical, mode, scope, reference date, catalogue version and hash, workbook contract, engine version and deliverables, but not stage or phase, checkpoints, open gaps, open rejections, approvals or a decision-log path. Those live in `07_qa/pipeline_state.json`, the Gate_Log sheet, `07_qa/cost_ledger.jsonl`, `preflight.json` and the connector. The state index is split across at least five files.

## Stage packets (N-02, N-03) — FAIL
| boundary | packet | version | hash | completeness verdict | consumer check |
|---|---|---|---|---|---|
| research → assessment | 09_deliverables research handoff (JSON) | none | none | floors verdict per category, not bound to a workbook revision | pipeline: file exists; assessment.research_ready: floors only, never `verify_handoff_lock` |
| assessment → reports | scored workbook + Gate_Log SCORING row + 07_qa/scoring.json (orphan) | Handoff_Lock v7 | catalogue_hash | SCORING gate PASS | engine.narrative preconditions |
| reports → package | pinned Docs + report_templates controls | template digest | yes (binding) | gold_standard package | assemble verify (≤15% un-URLed evidence) |
| package → promotion | 07_qa/verdicts_<ver>.json, verdict_<page>_<ver>.json | version in the filename | none | six PASS | ship_page / driver reads |

## Decision log (N-04) — PARTIAL
Binding decisions persist in `preflight.json` (who answered, when, verbatim) and refusals in the Gate_Log; connector baselines in `connectors_baseline.json`. There is no single decision log, and budget raises (`--max-usd`) are not recorded as approvals.

## Cold resume (N-05)
| boundary | walked | result |
|---|---|---|
| research close | mechanically, through the plugin's own lifecycle suite (REQ 5b: an empty run root still sees the run; STALLED reported; the resume plan names an agent; --revive dispatches) and `engine.cli resume` on the synthetic run | position, mode, binding and catalogue drift recovered from the workbook; no parameter loss for the fields the workbook holds |
| assessment close | not walked (needs a scored run and model lanes) | UNKNOWN |
| report close | not walked | UNKNOWN |

Output diff against an uninterrupted run: not measurable here (no model-driven run was executed within the no-credit boundary).

## N-06 Enrichment held server-side — FAIL (traced on goeasy)
`get_client_state('goeasy-ltd')`: the promoted run (seq 18) shows peer_scores, platform_readiness, techstack and why_now as `never_enriched`, `blocking` = 4, `done` = false. `list_enrichment_gaps` on the staged run returns 0 gaps because it reads staged payloads, not client state. The conductor's PRELIM buys enrichment but never reads the server's held facets first.

## N-07 Approvals — PARTIAL
Preflight answers persist and `start` reads them (never re-asked). Budget raises and connector approvals are not written anywhere a resume reads.

## N-08 Registry — PASS
`dma_run_registry.jsonl` holds log, beat and close events with root, workbook and client-folder pointers; Drive push and pull merge.

## N-09 Drive mirror — PASS by design
The client folder is opened at start with the manifest at IN_PROGRESS; `engine.memory backup` runs per category; the package is pushed at PACKAGE. The failure path has no remediation queue (F-08).

## Schemas proposed
- `run_manifest.schema.json` (engine-owned): schema_version, run_id, entity, binding {sub_vertical, mode, scope, basis_ref}, reference_date, catalogue {version, hash}, templates {digest, files}, contracts {page: cr-id}, stage, phase, checkpoints[], packets {stage: {path, sha256, schema_version, verdict}}, open_gaps_ref, rejections[], approvals[{kind, by, at, value}], decision_log_ref.
- `stage_packet.schema.json`: schema_version, stage, produced_at, sha256, completeness {verdict, blocking[]}, inputs[{path, sha256}].
