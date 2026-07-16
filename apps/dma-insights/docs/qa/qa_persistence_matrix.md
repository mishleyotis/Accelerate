# DMA Insights — Persistence Matrix (24 canonical tables) — Batch 4

Per the v2 QA plan §2C and the integrated batched plan Batch 4 spec:
this doc captures, per table:
- the migration that created it
- PK + UNIQUE constraints (idempotency gates)
- FK behaviour (CASCADE / NO ACTION / SET NULL)
- indexes (especially partial + generated columns)
- the persist line range in `package_persist.py` post Batch 1-3 edits
- the persistence strategy (UPSERT / DELETE-INSERT / append-only)
- the idempotency proof
- the row-count baseline at gate exit (live DB after Batch 3)

Sources of truth:
- migrations 001-036 under `backend/alembic/versions/`
- `package_persist.py` (validated against current state, post Batch 3)
- live `psql` against the seeded DB
- the 4-scenario test contract in
  `backend/tests/test_qa_v2_reingest_scenarios.py`

---

## How to refresh this doc

```bash
cd apps/dma-insights/backend
# 1. Live row counts
PGPASSWORD=dma psql -h localhost -p 5432 -U dma -d dma_insights -c "
ANALYZE;
SELECT relname, n_live_tup FROM pg_stat_user_tables
 WHERE schemaname='public' ORDER BY n_live_tup DESC;"
# 2. 4-scenario contract regression
.venv/bin/python -m pytest tests/test_qa_v2_reingest_scenarios.py -v
```

---

## 24-table proof

### 1. `entities`

| Field | Value |
|---|---|
| Migration | 003_entities_runs |
| PK | `id` (UUID) |
| UNIQUE | `display_id` (VARCHAR(32)); `drive_folder_id` (partial UNIQUE WHERE NOT NULL) |
| FK in | (none — root entity) |
| Indexes | `(display_id)`, `(drive_folder_id)`, `(subvertical)` |
| Persist lines | 609-660 (post Batch 3) |
| Strategy | UPSERT (`ON CONFLICT display_id`) with advisory lock on `drive_folder_id` hash |
| Idempotency | YES; verified by Scenario A (identical re-ingest = 0 new rows) |
| Live count | 103 |

Notes (Batch 3): `_display_id_for(name, run_id, drive_folder_id)` salts with `sha1(drive_folder_id)[:8]` when the institution_name slug is degenerate, eliminating the prior `entity-0001` collision class (Pentegra+Virtuity+Penderfund all merged before; now distinct).

### 2. `firmographics`

| Field | Value |
|---|---|
| Migration | 003 + 027_firmographics_parsed_facts |
| PK | `entity_id` (referenced row also = PK) |
| FK | `entity_id` → entities ON DELETE CASCADE |
| Persist lines | 714-756 |
| Strategy | UPDATE only (Clay-safe; never INSERTs) — preserves Clay-synced leadership over parser-regex |
| Idempotency | YES; UPDATE-only block |
| Selective skip | YES (Batch 2) — gated on `_should_persist('firmographics')`; emits `selective_reingest_skip:firmographics` warning when skipped |
| Live count | 86 |

### 3. `runs`

| Field | Value |
|---|---|
| Migration | 003 + 029/030/031/033/034 (qa_verdict_l1/l2 + assumptions_register + audit_logs + material_manifest_hash + artifact_manifest_json) |
| PK | `id` (UUID) |
| UNIQUE | `request_id` |
| FK | `entity_id` → entities ON DELETE CASCADE |
| Indexes | `(request_id)`, `(entity_id, completed_at)`, partial `(status) WHERE ACTIVE` |
| Persist lines | 760-1005 (incl. SUPERSEDE block at 998-1005) |
| Strategy | UPSERT (`ON CONFLICT request_id`); advisory lock; synth `SYNTH-{sha1[:12]}` when run_id empty |
| Idempotency | YES; verified by Scenario A (run_id_1 == run_id_2 for identical content) |
| Cross-entity isolation | verified by `test_supersede_does_not_cross_entities` |
| SUPERSEDED transition | verified by Scenario C (new request_id flips prior ACTIVE → SUPERSEDED with superseded_by_run_id link) |
| Live count | 112 |

### 4. `ccg_catalog_versions`

| Field | Value |
|---|---|
| Migration | 012_ccg_catalogue |
| PK | `version` (VARCHAR(16)) |
| Persist lines | 893-920 (stub-INSERT on missing FK target) |
| Strategy | INSERT ON CONFLICT DO NOTHING |
| Idempotency | YES; re-ingest = no-op |
| Live count | 5 |

### 5. `ccg_subcaps` (auto-bootstrap branch)

| Field | Value |
|---|---|
| Migration | 012 |
| PK | `(version, subcap_id)` |
| Persist lines | 985-1027 |
| Strategy | INSERT only — fires when < 90% of parsed subcap_ids resolve |
| Idempotency | YES (ON CONFLICT DO NOTHING) |
| Live count | 4044 |

### 6. `subcap_scores`

| Field | Value |
|---|---|
| Migration | 004 + 035 + 036 (Batch 3: data_source + parent_category_id; VARCHAR(24)) |
| PK | `id` (UUID) |
| UNIQUE | `(run_id, subcap_id)` |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Indexes | `(entity_id, subcap_id)`, `(run_id)`, `(run_id, data_source)` (Batch 3) |
| CHECK | `score BETWEEN 1.0 AND 5.0`; `data_source IN ('direct','shallow_broadcast','llm_extracted','heuristic_fallback')` |
| Persist lines | 970-1144 |
| Strategy | UPSERT `(run_id, subcap_id)`; N/A rows (score ∉ [1,5]) skipped |
| Selective skip | YES (Batch 2) — `_should_persist('subcap_scores')`; emits `selective_reingest_skip:subcap_scores` |
| Batch 3 broadcast | category-shaped IDs (P1C1, P2C3) emit one UPSERT per v7.0 child with `data_source='shallow_broadcast'`; verified live on AMH + Wescom (1085 broadcast rows each) |
| Idempotency | YES; selective Scenario B (1-byte CSV mutation → counts stable) |
| Live count | 62854 (60K+ direct + 2K+ shallow_broadcast) |

### 7. `issue_register`

| Field | Value |
|---|---|
| Migration | 004 |
| PK | `id`; UNIQUE `(run_id, issue_id)` |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Persist lines | 1214-1240 |
| Strategy | UPSERT `(run_id, issue_id)` |
| Selective skip | YES (Batch 2) |
| Idempotency | YES |
| Live count | 503 |

### 8. `caps_applied_log`

| Field | Value |
|---|---|
| Migration | 028 + 032 (Batch 1: UNIQUE widened to (run_id, log_id, subcap_id)) |
| PK | `id`; UNIQUE `(run_id, log_id, subcap_id)` |
| FK | `run_id` → runs CASCADE |
| Indexes | `(run_id, subcap_id)`, `(entity_id, created_at DESC)` |
| Persist lines | 1250-1290 |
| Strategy | DELETE-then-INSERT per run_id |
| Selective skip | YES (Batch 2) — atomic skip of BOTH DELETE and INSERT |
| Per-(cap × subcap) layout | supported (Pentegra: 198 rows sharing cap_id='SEV-001' across distinct subcap_ids) |
| Idempotency | YES; DELETE-INSERT pattern |
| Live count | 3142 |

### 9. `recommendations`

| Field | Value |
|---|---|
| Migration | 004 |
| PK | `id`; UNIQUE `(run_id, rec_id)` |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Persist lines | 1306-1340 |
| Strategy | UPSERT `(run_id, rec_id)` |
| Selective skip | YES (Batch 2) |
| Idempotency | YES |
| Live count | 378 |

### 10. `peer_benchmarks`

| Field | Value |
|---|---|
| Migration | 005 |
| PK | UNIQUE `(subvertical, subcap_id, ccg_catalog_version)` |
| Persist lines | 1352-1368 |
| Strategy | UPSERT |
| Selective skip | YES (Batch 2) |
| Idempotency | YES |
| Live count | 85 |

### 11. `tech_stack_entries`

| Field | Value |
|---|---|
| Migration | 006 |
| PK | UNIQUE `(entity_id, tech_id)` |
| FK | `entity_id` → entities CASCADE |
| Persist lines | 1376-1398 |
| Strategy | UPSERT |
| Selective skip | YES (Batch 2) |
| Idempotency | YES |
| Live count | 680 |

### 12. `platform_scores`

| Field | Value |
|---|---|
| Migration | 005 |
| PK | UNIQUE `(run_id, platform_id)` |
| FK | `run_id` → runs CASCADE |
| Persist lines | 1400-1418 → 2147-2282 (`_persist_platform_scores`) |
| Strategy | UPSERT; reconstructs fit inputs from subcap_scores + insight_cards |
| Selective skip | YES (Batch 2) |
| Idempotency | YES |
| Live count | 465 |

### 13. `evidence_index`

| Field | Value |
|---|---|
| Migration | 004 + 018 |
| PK | `id` (UUID); UNIQUE `(run_id, e_id)` (legacy idempotency key) |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Indexes | `(content_hash)`; partial `(is_stale)`; partial `(freshness_band)` |
| Generated columns | `freshness_band` (STORED), `is_stale` (STORED) |
| CHECK | `tier BETWEEN 1 AND 8` (Batch 1: tier clamp at `EvidenceRow.tier` validator) |
| Persist lines | 1208-1220 → 1456-1725 (`_persist_evidence` 5-branch decision engine) |
| Strategy | 5-branch dedup: `kept` / `dedup_same_entity` / `cross_entity_kept` / `duplicate_within_run` / `tier_upgrade` |
| Selective skip | YES (Batch 2) — atomic skip of the entire dedup TRIPLE (evidence_index + evidence_run_links + dedup_audit) when 01_evidence/* unchanged |
| Idempotency | YES on row content; dedup_audit append-only |
| Live count | 6685 |

### 14. `evidence_run_links`

| Field | Value |
|---|---|
| Migration | 018 |
| PK | `(evidence_id, run_id)` |
| FK | both CASCADE |
| Persist lines | inside `_persist_evidence` |
| Strategy | INSERT; composite PK makes it idempotent |
| Live count | 6834 |

### 15. `dedup_audit`

| Field | Value |
|---|---|
| Migration | 018 |
| PK | `id`; index `(run_id, source_e_id, kept_evidence_id, action)` |
| Persist lines | inside `_persist_evidence` |
| Strategy | append-only audit |
| Idempotency note | grows on every persist_package invocation (one row per evidence DECISION). Scenario A explicitly asserts the EXPECTED 2x growth on identical re-ingest (every prior decision re-logged). Production avoids growth via Batch-2 backfill skip (manifest hash equality → no persist call). |
| Live count | 34844 |

### 16. `document_sections`

| Field | Value |
|---|---|
| Migration | 007 |
| PK | `id`; UNIQUE `(run_id, section_kind, ordinal)` |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Indexes | `(run_id, section_kind)` |
| Persist lines | 1417-1430 → 1734-1842 (`_persist_document_sections`) |
| Strategy | DELETE-then-INSERT per run_id |
| Selective skip | YES (Batch 2) — atomic skip of BOTH DELETE and INSERT when no 04_reports/*.docx changed; Scenario B explicitly proves content_hash stays identical across a scoring-only mutation |
| Idempotency | YES via DELETE-INSERT |
| Live count | 7060 |

### 17. `document_lineage`

| Field | Value |
|---|---|
| Migration | 007 |
| PK | `id`; UNIQUE `(section_id, target_type, target_ref)` |
| FK | `section_id` → document_sections CASCADE (NOT a direct run_id reference) |
| Strategy | cascades from document_sections DELETE-INSERT |
| Idempotency | YES |
| Live count | 24165 |

### 18. `document_evidence_items`

| Field | Value |
|---|---|
| Migration | 007 |
| PK | `id` |
| FK | `section_id` → document_sections CASCADE |
| Strategy | cascades from document_sections |
| Live count | 14386 |

### 19. `focus_areas`

| Field | Value |
|---|---|
| Migration | 023 |
| PK | UNIQUE `(run_id, fa_id)` |
| FK | `run_id` → runs CASCADE; `entity_id` → entities CASCADE |
| Persist lines | 1422-1434 → 1885-1910 (`_persist_focus_areas`) |
| Strategy | DELETE-then-INSERT per run_id |
| Selective skip | YES (Batch 2) — atomic skip when no Client_Profile DOCX changed |
| Idempotency | YES |
| Live count | 456 |

### 20. `parser_observations`

| Field | Value |
|---|---|
| Migration | 026 |
| PK | `id`; UNIQUE `(parser_name, observation_kind, observed_value)` |
| Persist lines | 1450-1471 |
| Strategy | best-effort UPSERT; failure swallowed (table may not exist on pre-026 PG) |
| Idempotency | UPSERT increments occurrence_count |
| Live count | 166 |

### 21. `vertex_synthesis_cache`

| Field | Value |
|---|---|
| Migration | 019 |
| PK | `id`; UNIQUE `(target_kind, target_id, surface, input_fingerprint)` |
| Indexes | partial `(target_kind, target_id, surface) WHERE invalidated_at IS NULL`; `(catalogue_version, surface)`; partial `(input_fingerprint) WHERE invalidated_at IS NULL` |
| Persist lines | 2205-2214 (post-commit invalidation via `safe_mark_invalidated`) |
| Strategy | UPSERT with supersede chain |
| Invalidation contracts | `build_invalidation_for_new_run` (post-commit), `build_invalidation_for_catalogue_bump` (ccg_loader bump), `build_invalidation_for_feedback` (single-row from 👎) |
| Catalogue bump contract | verified by Scenario D (planted cache row → bump → invalidated_at set, invalidation_reason='catalogue_bump_invalidate') |
| Live count | 0 (no synthesis fires in test runs) |

### 22. `alerts`

| Field | Value |
|---|---|
| Migration | 005 |
| PK | `id` |
| FK | `entity_id` → entities NO ACTION |
| Indexes | partial `(entity_id, opened_at) WHERE closed_at IS NULL` |
| Strategy | rule-engine driven INSERT; UPDATE on action |
| Live count | 0 |

### 23. `job_executions`

| Field | Value |
|---|---|
| Migration | 020 + 024 (trigger_source widened to allow 'post_commit') |
| PK | `id` |
| CHECK | `trigger_source IN ('admin_ui','scheduler','pubsub','cli','post_commit')` |
| Indexes | `(started_at)` |
| Strategy | INSERT → UPDATE through 4-branch state machine (running / succeeded / failed / cancelled); wired through `workers._runner.track_job_execution` |
| Live count | 13 |

### 24. `customer_intelligence_profiles`

| Field | Value |
|---|---|
| Migration | 018 |
| PK | `entity_id` (= row identity) |
| FK | `entity_id` → entities CASCADE |
| Strategy | UPSERT; computed by `workers/intelligence_recompute` on Pub/Sub `dma.ingest.completed` |
| Live count | 0 (worker hasn't run on this DB) |

---

## 4-scenario contract proof

The `test_qa_v2_reingest_scenarios.py` file (NEW, Batch 4) pins
all 4 plan-mandated scenarios + a cross-entity supersede regression
guard. All 5 PASS against the live DB.

| Scenario | What it proves | Status |
|---|---|---|
| A — Same run, same data | Idempotent tables: counts byte-equal across re-ingest. Audit tables (dedup_audit): grow append-only, exactly 2x on second pass. | PASS |
| B — Scoring CSV mutated only | Selective re-ingest contract (Batch 2): `evidence_index`, `evidence_run_links`, `dedup_audit`, `document_sections`, `document_lineage`, `document_evidence_items`, `focus_areas`, `caps_applied_log`, `recommendations`, `issue_register` content_hash UNCHANGED before/after a 1-byte scoring CSV mutation; `subcap_scores` re-UPSERTs. | PASS |
| C — New request_id, same entity | Same entity row reused (drive_folder_id lookup hits); fresh run row inserted; prior run flips `status='SUPERSEDED'` + `superseded_by_run_id=<new>`; new row is ACTIVE. | PASS |
| D — Catalogue bump | Planted cache row tagged with old catalogue_version → `build_invalidation_for_catalogue_bump(old_version)` → `safe_mark_invalidated` → `invalidated_at = NOW()`, `invalidation_reason='catalogue_bump_invalidate'`. | PASS |
| Cross-entity isolation (regression guard) | Ingesting entity B's package does NOT flip entity A's ACTIVE run to SUPERSEDED. Both entities' latest runs remain ACTIVE. | PASS |

---

## Cascade integrity (Batches 1-3 contracts still hold)

| Contract | Source | Status |
|---|---|---|
| Tier clamp [1, 8] | EvidenceRow validator + 3 fallback layers (Batch 1) | enforced; no CheckViolation in the 113-package backfill |
| Score skip for N/A rows | persist_package (Batch 1) | enforced; Payments Canada's 38 N/A rows skipped |
| Caps UNIQUE `(run_id, log_id, subcap_id)` | Migration 032 (Batch 1) | enforced; Pentegra's 198 per-(cap × subcap) rows persist cleanly |
| Display_id collision-safe | `_display_id_for(name, run_id, drive_folder_id)` salt (Batch 1) | enforced; no `entity-0001` collisions |
| Synthetic run_id `SYNTH-{sha1[:12]}` | persist_package (Batch 1) | enforced; Haventree/Compeer/Elliott/CI Financials all get distinct run rows |
| Material manifest hash skip | Migration 033 + backfill skip-check (Batch 2) | 103/105 SKIPped on pass 2 of identical content |
| Per-artifact diff + skip_tables | Migration 034 + artifact_manifest.affected_tables (Batch 2) | proven live: 1-byte scoring CSV mutation → 13 of 21 tables skip, document_sections hash identical before/after |
| Shallow alias bridge | catalogue_alias_bridge + persist_package extension (Batch 3) | proven live: AMH + Wescom emit 1085 broadcast subcap_scores rows each |
| Heatmap data_source propagation | heatmap_aggregator._aggregate_data_source (Batch 3) | proven via ASGI probe: pillar zoom shows data_source='shallow_broadcast' propagated up |
| Active voice rationale | catalogue_alias_bridge.build_broadcast_rows + test_build_broadcast_rows_rationale_is_active_voice (Batch 3) | enforced |
