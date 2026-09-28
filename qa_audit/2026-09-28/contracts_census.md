# Stage contracts census — dma-insights 1.20.0 — 28-09-2026

NOTE: I did NOT write /tmp/claude-0/.../scratchpad/qa/contracts_census.md. My mode is strictly read-only (no file creation, including temp files), so the full census is below. Paste it into that path if you need it on disk.

## SUMMARY (under 40 lines)
- Contract edges: 61 producer→consumer edges across about 40 artefacts. All paths are under /home/user/Accelerate/plugins/dma-insights unless marked apps/.
- How consumers check what they read:
  - 15 validate: jsonschema, explicit key checks or a hash check.
  - 3 check weakly.
  - 5 check against the WRONG (older) schema.
  - 29 trust a plain json.load or a file-exists test.
  - 3 are LLM docs only.
  - 6 artefacts are orphans or dead schemas.
- jsonschema is never actually called. gov_auditor.py:50 imports it and never uses it. The three governance schemas/*.schema.json files have no loader.
- Version skew (worst first):
  1. run_manifest.json has 3 incompatible shapes:
     - engine assemble.py:162: no $schema, nested `institution.name`.
     - generate_governance_outputs.py:390: `$schema: run_manifest_v2`, with versions.rubric and taxonomy defaulting to "5.0" (:495-498).
     - gov_auditor.py:261 IV-02 needs FLAT keys (institution_name, overall_score, pillar_scores, evidence_count) that neither producer writes, so every run gets a guaranteed CRITICAL FAIL.
     - calibration_engine.py:339 reads a top-level rubric_version and backend run_id.py:90 reads a top-level assessment_date. Nobody writes either.
  2. Workbook sheet names: gov_auditor.py:57 and research/scripts/validate_workbook.py:53 require v3-era tabs (Summary, Calculation_Chain, P*_Scoring_Detail, Evidence_Index). The engine is v7 (contract.py:920 WORKBOOK_CONTRACT="v7") and writes P*_Subcap_Scoring / Evidence_Detail. generate_governance_outputs.py:182 therefore silently produces an EMPTY evidence_index.csv. The legacy row counts add to 847 (203+291+164+189), not 851.
  3. dma-assessment SKILL.md:419 says the workbook is "contract v3"; the engine writes "v7". dma-research SKILL.md:798 requires top-level `assessment_id`, `evidence_mode` and `locked_peer_set[]` in the handoff, but handoff.py:172-204 emits none of them (the peer set is a pipe-joined string inside `_contract.handoff_lock`).
  4. research_handoff.json has NO version field. The account research skill says "Handoff v2 with v1 compatibility block", while handoff.py deliberately has no v1 compat (AUD-0078).
  5. fixtures/gold_manifest.json pins ccg_catalog_version "v5.0" (asserted at scripts/tests/test_gold_traceability.py:49). The engine catalogue is v7.0.
  6. The governance_skill_version is hard-coded differently everywhere:
     - "2.1" in gov_auditor.py:2021/2194, calibration_engine.py:504 and regression_runner.py:457.
     - "2.2" in assessment qa_auditor.py:500.
     - The SKILL.md headers say v2.4 (plugin) and v2.5 (account).
  7. run_id regexes disagree:
     - qa_verdict.schema.json:25 needs `DMA-[A-Z0-9]{4}-...`.
     - validate_contracts.py needs `{2,6}`.
     - The engine accepts any `[A-Za-z0-9._-]{3,64}`.
     - The research SKILL uses DMA-RES-....
  8. validate_contracts.py:183 accepts only 8 sub-verticals (no Farm Credit); the plugin skills say 9.
- Trust gaps:
  - The handoff docstring and the assessment SKILL say scoring "compares Handoff_Lock.catalogue_hash and refuses". engine/assessment.research_ready (:131) never calls verify_handoff_lock. Only validator.py:443 (through handoff.build) and watchdog.py:148 enforce it; runstate.resume:201 only reports drift.
  - floors_{CAT}.json verdicts are not tied to a workbook revision, so a stale PASS is trusted by handoff.py:158 and assessment.py:141.
  - strip_working_area.py:78-83 checks "the 3 fields survive" by looking for the key NAMES in the JSON. handoff.py always emits those keys, even with null values, so the check is close to vacuous.
- Orphans (written, no code reader):
  - 07_qa/handbacks/*.json (record_handback.py:172). Its own text says "the re-dispatch reads this file", but nothing does.
  - 00_entity_profile/context.json (runstate.py:176).
  - bundle_manifest.json (bundle_handoff.py:153).
  - 07_qa/scoring.json (assessment.py:854; the Gate_Log row is what gets read).
  - references/canonical_sources.json (SKILL.md:565 only).
- Memory file caps: NONE stated in code for any memory file.
  - The run notebooks 03_memory/<CAT>.md and /root/.dma/clients/<slug>.md have no cap, no version token and no lock.
  - client_memory.py:176-177 reads the whole file and writes it back non-atomically. drive_fetch.push_memory:265 overwrites the Drive copy blindly (no etag), so the last writer wins across sessions.
  - memory.consolidate (:343 read → :361 write) can drop entries that memory._append adds between the read and the write.
  - The only caps are server-side, in apps/mcp dma_mcp/memory.py (Postgres, not files): digest days 1..365 (:766), search limit 1..100 (:363), open findings 1..500 (:462).

Divergence table (account = /root/.claude/skills/synced/…/X/SKILL.md, plugin = plugins/dma-insights/skills/X/SKILL.md):
| skill | acct sha256[:16] / lines | plugin sha256[:16] / lines | header ver acct→plugin | categories | subcaps | M5 hits | handoff/contract version strings |
|---|---|---|---|---|---|---|---|
| dma-assessment | c65df987c24aa7df / 866 | 023cbc4f9325966e / 906 | v5.5 → v5.6 changelog (title still v5.5) | acct desc "17" (+legacy note says 16); plugin "16" | acct desc "~836" (body 851); plugin 851 | 8 / 6 (plugin keeps the M5 table at :188 despite "four bands") | both say "contract v3"; engine is v7 |
| dma-research | 0ca235260e5629bb / 416 | 9a2c2c142b50bff8 / 802 | v3.0 (taxonomy v7) → **v2.5 (legacy XLSX toolkit)** | acct 16; plugin none stated | 851 / 851 (plugin :442 says 129 capabilities vs 136) | 1 / 1 | acct: "Workbook contract v3", "Handoff v2 w/ v1 compat"; plugin: no version, 06_handoff/ tree (engine uses 09_deliverables) |
| dma-governance | e211438975c143b9 / 297 | d9f197927410cb4f / 332 | v2.5 (113 checks) → v2.4 (108 checks) | – | – | 0 / 0 | both "aligned with assessment v5.4"; code writes 2.1 |
| dma-first-call-deck | 212065e5092e5698 / 385 | c7382181b0bb93bb / 903 | v2.0 → unversioned | – | – | 0 / 0 | none |
The drift runs in both directions: the account copy is NEWER for research and governance and OLDER for assessment and first-call-deck.

---------------------------------------------------------------------
## FULL CENSUS (intended content of contracts_census.md)

### Task 1 — Contract edges (P = plugins/dma-insights; E = P/skills/dma-research/engine)
Check column: V = validates · W = weak · X = validates against a wrong/old schema · T = trusts (json.load / exists) · D = LLM doc · O = orphan

| # | Artefact | Producer (file:line) | Consumer (file:line) | Version field: producer / consumer expects | Check |
|---|---|---|---|---|---|
| 1 | DMA_Scoring_Workbook_*.xlsx (run root) | E/runstate.py:167 start → workbook.create; all writes via E/ledger.py (flock `<wb>.xlsx.lock`, workbook.py:258/309) | E/validator.py:120 (called by handoff.py:64, assemble.py:516) | Handoff_Lock.workbook_contract "v7" (contract.py:920), engine_version "7.0.0" (:921), catalogue_hash / same | V (required sheets, 7 rules, catalogue_hash :443) |
| 2 | workbook Handoff_Lock | workbook.py:548 _write_handoff_lock | E/runstate.py:201 resume | catalogue_hash + workbook_contract / same | W (reports drift, never refuses) |
| 3 | workbook Handoff_Lock | same | E/watchdog.py:148 | same | V (HALTED on drift) |
| 4 | workbook | engine | P/skills/dma-governance/scripts/gov_auditor.py:57,222 | v7 sheets / v3-era tabs (Summary, Calculation_Chain, P*_Scoring_Detail, Evidence_Index, Absent_Evidence_Log, QA_Validation_Log) | X |
| 5 | workbook | engine | P/skills/dma-assessment/scripts/generate_governance_outputs.py:180-185 | Evidence_Detail / looks for "Evidence_Index" → empty CSV plus warning | T/X |
| 6 | workbook | engine | P/skills/dma-research/scripts/validate_workbook.py:47-55 | v7 / P*_Scoring_Detail, row counts 203/291/164/189 | X |
| 7 | workbook | engine | apps/worker/dma_worker/workbook_parser.py:482,495 | reads workbook_contract as an observation only | T (tolerant) |
| 8 | workbook | engine | P/skills/dma-assessment/SKILL.md:419-437 | engine v7 / doc says "contract v3" | D (skew) |
| 9 | research_handoff.json (09_deliverables/) | E/handoff.py:303-305; E/pipeline.py:1670-1672 | E/pipeline.py:710 HANDOFF verify | none (only `_contract`, run.catalogue_version, engine_version) | T (is_file only) |
| 10 | research_handoff.json | same | E/strip_working_area.py:75-83 (cli.py:689) | none | W (key-name substring match; keys are always emitted) |
| 11 | research_handoff.json | same | P/skills/dma-assessment/SKILL.md:439 (non-authoritative index); P/scripts/hooks/deny_bulk_read.py:42 blocks reads | none | D |
| 12 | research_handoff.json | same | P/skills/dma-research/SKILL.md:798-802 contract | requires assessment_id, evidence_mode, locked_peer_set[] top-level / not emitted | D (skew) |
| 13 | 07_qa/floors_{CAT}.json | E/floors_gate.py:713 | floors_gate.read_verdict:722 → handoff.py:158, assessment.py:141, orient.py:86 | none | T (None if unparsable; no workbook-revision binding) |
| 14 | 07_qa/scoring.json | E/assessment.py:854 | no code reader (the Gate_Log SCORING row is read instead; watchdog.py:286 text only) | none | O |
| 15 | 07_qa/pipeline_state.json | E/pipeline.py:385,411-416 (atomic) | E/watchdog.py:96; E/brief.py:2118; scripts/hooks/_runctx.pipeline_state → stage_advance.py:316,441,559; guard_driver_lock.py:182 | none | T ({} on error) |
| 16 | run-root/driver.lock | E/runstate.py:364-418 (atomic) | P/scripts/hooks/guard_driver_lock.py:15-51 | none; both STALE 1800 s (runstate.py:299 / guard:52) | V (keys pid/host/beat) |
| 17 | 07_qa/search_relay.jsonl | E/relay.py:210 _append (O_APPEND, no lock) | relay._events:217 / requests:235; scripts/hooks/harvest_on_return.py:169,315; stage_advance.py | none | W (needs `id`; torn lines skipped) |
| 18 | 07_qa/relay_batch_r{n}.json (+.md) | E/relay.py:944-949 | E/pipeline.py:575-609,1509; stage_advance.py:307,317,412; harvest_on_return.py:301-311 | none | T |
| 19 | 07_qa/handbacks/<agent>-<ts>.json | P/scripts/hooks/record_handback.py:172-177 | NONE (only tests/skills/test_record_handback.py:86) | none | O |
| 20 | Search_Log sheet | E/ledger.py:505,599 append_search | E/relay.py:596 reconcile; floors_gate; cost; handoff.py:249 | in workbook | V (ledger refusals plus validator) |
| 21 | Evidence_Detail → 01_evidence/evidence_index.json | E/assemble.py:137 evidence_index_doc, :409 | E/assemble.py:519 verify | none | V (≤15 % un-URLed) |
| 22 | evidence_index.json | same | apps/dma-insights backend parse_evidence_index | none | T |
| 23 | evidence_index.json | same (key `items`) | P/skills/dma-research/scripts/populate_workbook.py:127-128,301 (legacy, expects evidence_items / subcap_coverage) | none | X |
| 24 | caps_applied_log.csv / contradiction_log.csv / evidence_index.csv | generate_governance_outputs.py:528-530 | P/skills/dma-assessment/scripts/validate_contracts.py:224,283,342 | none | V (columns, enums) |
| 25 | same CSVs | same | gov_auditor.py:199,215 | none | V (per-check explicit) |
| 26 | same CSVs plus run_manifest | same | bundle_handoff.py:37-40,115-121,146-154 | none | V (presence, sha256 into bundle_manifest.json) |
| 27 | bundle_manifest.json | bundle_handoff.py:153 | none | none | O |
| 28 | run_manifest.json (engine shape) | E/assemble.py:162 manifest_doc, :407,:457 | E/gold_standard.py:683; E/watchdog.py:306 | no $schema; workbook_contract, engine_version, catalogue_version | T |
| 29 | run_manifest.json (v2 shape) | generate_governance_outputs.py:380-411,560 | validate_contracts.py:77-199 | "$schema":"run_manifest_v2", versions.rubric/taxonomy default "5.0" / expects run_manifest_v2 | V (nested keys; $schema mismatch only WARN) |
| 30 | run_manifest.json | either | gov_auditor.py:260-275 IV-02 | expects FLAT institution_name, overall_score, pillar_scores, evidence_count | X (guaranteed CRITICAL) |
| 31 | run_manifest.json | either | P/skills/dma-governance/scripts/calibration_engine.py:45,339 | top-level rubric_version / assessment_skill_version (neither written) | X |
| 32 | run_manifest.json | either | regression_runner.py:58-63 | none | T |
| 33 | run_manifest.json | either | apps/worker/dma_worker/persist.py:43-116,304-308,458 | duck-types versions / framework_version | T (tolerant) |
| 34 | run_manifest.json | either | apps/dma-insights/backend/app/services/parsers/run_id.py:90 | top-level assessment_date (neither writes) | X |
| 35 | P/skills/dma-governance/schemas/run_manifest.schema.json (const run_manifest_v2 :22), qa_verdict.schema.json, issue_register.schema.json | hand-written | no loader (gov_auditor.py:50 imports jsonschema, never calls it) | – | O (dead schema) |
| 36 | qa_verdict.json | gov_auditor.py:2226 ("2.1" :2021/2194); assessment qa_auditor.py:520 ("2.2", rubric "5.0" :499-500) | P/skills/dma-rectifier/scripts/drain_local.py:171-173 | schema pattern ^\d+\.\d+$ not enforced | T |
| 37 | issue_register.csv | qa_auditor.py:452; gov_auditor | drain_local.py:53 | none | T |
| 38 | 03_memory/<CAT>.md | E/memory.py:179 _append | memory.parse:271 / consolidate:308 | none | V (each entry re-passes ledger refusals) |
| 39 | 03_memory status | E/memory.py:291 | record_handback.py:143 | none | T |
| 40 | 07_qa/memory_backup.json | E/memory.py:563 | memory.py:530; stage_advance.py:368,376; pipeline.py:668 | sha256 digests (change detection) | T |
| 41 | /root/.dma/clients/<slug>.md | P/scripts/client_memory.py:169,177; drive_fetch.py:253-258 | drive_fetch.push_memory:265 (blind PATCH); agents | none | T |
| 42 | dma_run_registry.jsonl | E/registry.py:71 | registry.read:102 / latest:118 / open_runs:128 | none | T |
| 43 | connectors_baseline.json | E/pipeline.py:857 | hooks/guard_dispatch.py:124,308; scripts/connector_contract.py:195; E/relay.py:1205 | none | T |
| 44 | template_binding (Run_Metadata digest plus 00_entity_profile/template_binding.json) | E/template.py:196-201 | template.binding_state:208; readers contract.py:816, workbook.py:508, narrative.py:364, brief.py:284, reports.py:602 | pinned_digest()[:16] | V (hash) |
| 45 | 00_entity_profile/context.json | E/runstate.py:176 | none in plugin | none | O |
| 46 | 00_entity_profile/kg.json | E/kg.py:517 | E/kg.py:296 | none | T |
| 47 | technographic_scan.json | E/techscan.py:537,571 | E/assemble.py:396; E/gold_standard.py:655 | none | T |
| 48 | 01_evidence/entity_timeline.json | E/assemble.py:411 | app C1 surface (backend) | none | T |
| 49 | <page>.<section>[.<shard>].json | E/surface_export.py:207 write_section (scaffold validates vs contract :140-196) | P/skills/dma-surface-production/scripts/ship_page.py:102-105 | producer_version free string | T |
| 50 | page payload (submit_page_payload) | ship_page.py:265-290 | P/scripts/hooks/precheck_submit.py:22-70 | envelope keys; rejects M5 and hex | V |
| 51 | page payload | ship_page via scripts/mcp_proxy.py | apps/mcp/dma_mcp/validation.py:1388 pass1; validation2.py:3501 pass2 | producer_version required non-null only (contracts.py:30) | V |
| 52 | 07_qa/verdicts_{ver}.json, verdict_{page}_{ver}.json | E/pipeline.py:1820,1845 | E/brief.py:1827-1841; E/pipeline.py:263-272 | version in the filename | T |
| 53 | report bundle (get_report_bundle) | apps/mcp/dma_mcp/bundle.py:42-152 (DB, ccg_catalog_version) | agents via the MCP connector | ccg_catalog_version | T (client side) |
| 54 | /root/.dma/bundles/<slug>/state.json | agent-authored (surface-production/05-lifecycle/client-memory.md:102-117) | hooks/artifact_cadence.py:63-78 | none | T (newest mtime wins) |
| 55 | references/section_sources.json | scripts/gen_recording_map.py:338 | E/surface_export.py:74; E/brief.py:1743; E/template.py:193 | workbook_contract "v7" / never compared | T |
| 56 | references/tab_recording_map.json | gen_recording_map.py:432 | E/ship.py:57; apps/worker workbook_parser.py:3039 | "v7" / not compared | T |
| 57 | references/card_bindings.json, drilldown_atlas.json | hand plus gen | gen_recording_map.py:114-116 | none | T |
| 58 | references/canonical_sources.json | hand | only skills/dma-surface-production/SKILL.md:565 | none | O / D |
| 59 | fixtures/gold_manifest.json | hand (fetched 2026-08-20) | scripts/tests/test_gold_traceability.py:17-55 | ccg_catalog_version "v5.0" asserted :49; engine v7.0 | V (sha256) plus skew |
| 60 | fixtures/served_sections.json | hand | client_memory.py:43,69; gen_recording_map.py:74; apps/mcp/dma_mcp/resources.py:146 | none | T |
| 61 | E/data/catalogue_v70_tier.json | build | E/contract.py:40 (catalogue_hash); validate_contracts.py:44-50 | v70 in the filename | V (hash) |

### Task 2 — Memory surfaces
| Path | Writer(s) | Reader(s) | Cap | Version token / read-before-write |
|---|---|---|---|---|
| <run>/03_memory/<CAT>.md | E/memory.py:179 _append (append-only); :361 consolidate rewrite | memory.parse:271, status:291, consolidate:308; record_handback.py:143 (via status); drive backup | none | no token; consolidate reads (:343) then writes (:361) with NO lock, so a concurrent _append is lost; the workbook flock does not cover notebooks |
| <run>/07_qa/memory_backup.json | memory.py:563 | memory.py:530; stage_advance.py:368; pipeline.py:668 | none | per-file sha256 digests (idempotence only) |
| Drive "memory-backup" folder | drive_fetch push-backup (memory.py:549) | drive_fetch pull-backup (memory.restore:575); cleanup-backup (memory.cleanup:638, refuses until consolidated) | none | digests only |
| /root/.dma/clients/<slug>.md ($DMA_CLIENT_MEMORY_DIR) | client_memory.py:169 init, :176-177 note; drive_fetch.pull:253-258 (lands only if no local copy) | drive_fetch.push_memory:265; agents (session_brief / agent_run "READ MEMORY FIRST" agent_run.py:116) | none (client-memory.md states none) | no token; non-atomic read-modify-write; Drive PATCH without etag/If-Match, so last writer wins |
| Drive "<slug> — synthesis memory.md" (drive_fetch.py:83) | push_memory:265 | pull:245 | none | none |
| /root/.dma/bundles/<slug>/{state.json, folder_ids.json} | agents; drive_fetch.py:315-330 | artifact_cadence.py:63-78 | none | none |
| /root/.dma/agent_logs/*.jsonl | scripts/agent_run.py:545-554 | relay.lane_output:394; verify.py:125 | none | n/a |
| <run-root parent>/dma_run_registry.jsonl | registry.py:71 | registry.read/latest/open_runs; Drive push/pull :141-160 | none | none |
| Server memory (Postgres findings/refinements) | apps/mcp/dma_mcp/memory.py:154 record_finding, :529 record_refinement | :760 memory_digest, :350 search_findings, :455 list_open_findings, :705 recall_for_gates | days 1..365 (:766); search 1..100 (:363); open 1..500 (:462); recall 3 | content_hash sha256 dedup (:97); id minted under lock (:115) |

### Task 3 — Divergence (see the table in the summary). Supporting line refs:
- acct dma-assessment:5-6 "8 sub-verticals … 17 categories, 144 capabilities, ~836"; :152/:162 body says 851 / 16 (v7.x); :166-167 legacy 17 / ~836 note.
- plugin dma-assessment:5-7 "9 sub-verticals … 16 categories, 136 capabilities, 851 … four bands"; :18 v5.6 changes; :23 "Category count is 16 (v7.0), not 17"; :188 still lists the M5 Transformational row (contract.py:279 BANDS has 4 bands; precheck_submit.py:24 rejects M5).
- acct dma-research:6,13,18 "v3.0 … Taxonomy v7.0 … Workbook contract v3 … Handoff v2 with v1 compatibility block".
- plugin dma-research:14 "v2.5", :6 "Pillar XLSX toolkits … 851", :217 06_handoff/, :442 "129 capabilities", :798 required handoff keys.
- governance: acct :13,18 v2.5 / 113 checks; plugin :13,18 v2.4 / 108 checks.
- first-call-deck: acct :17 "v2.0" (385 lines); plugin :17 unversioned (903 lines).