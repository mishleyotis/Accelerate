# ADR 0014 — Final-audit P0 patches: deck-skip, zip-slip, classify-outcome, vertex-offline, SSE-text, uploadPackage, v5-backfill

Date: 2026-05-28
Status: Accepted (closes the 2026-05-28 principal-QA audit P0 register)

## Context

The 2026-05-28 principal-QA audit pass surfaced 7 confirmed defects
that the prior 1429-test suite missed. Each was a contract-shape bug
that real-world DMA package shapes (Calprivate, Nicola Wealth, Odlum
Brown, WSFS) would trip but the synthetic fixtures didn't exercise.

The audit was the first round to systematically inspect the 4
uploaded real-sample zips. Three of the seven defects (deck-skip,
SSE-text, uploadPackage) are direct consequences of the real-sample
inspection: every complete package zip carries a 55-65 MB pptx in
`05_narrative_deck/`, the backend SSE emits `data: {"text":...}`
not `{"token":...}`, and the standalone UI never had a ZIP-package
upload control.

## Decisions

### P0-1 — `/api/v1/ingest/package` skips deck entries before per-entry size gate

**Before:** `_MAX_UPLOAD_BYTES=50 MB` applied per-entry. Every entry
went through `extractall()`. A real complete package zip with a
59 MB deck PPTX failed with `oversize zip entry`.

**After:** Two-pass extraction. Pass 1 VALIDATES every entry +
classifies via `_zip_entry_should_skip(name)`. Skipped entries
(`05_narrative_deck/*`, `narrative_deck/*`, bare `*.pptx`/`*.key`)
emit `skipped_non_ingested_artifact:<filename>` warning. Pass 2
EXTRACTS only validated, non-skipped entries via `zf.extract(info, td_path)`.
Caps now:
- `_MAX_UPLOAD_BYTES = 100 MB` (compressed transport)
- `_MAX_PER_ENTRY_UNCOMPRESSED_BYTES = 50 MB` (per parsed entry)
- `_MAX_UNCOMPRESSED_TOTAL_BYTES = 200 MB` (cumulative parsed)

Real DMA packages now ingest cleanly. The decks land in
`parser_warnings` so the operator sees what was skipped.

### P0-2 — `historical_backfill._extract_zips` re-uses safe extractor

**Before:** `zf.extractall(zp.parent)` — zip-slip vulnerability,
no per-entry caps, no deck skip. Drive folders that contained
operator-uploaded zips were vulnerable.

**After:** Reuses `_zip_entry_should_skip` + `_MAX_PER_ENTRY_*`
constants from `ingest_package`. Returns `(extracted_count, warnings)`
so the caller folds warnings into the package's `parser_warnings`.
Signature change `int → tuple[int, list[str]]` is contained — the
single caller in `_ingest_folder` was updated.

### P0-3 — `_classify_outcome` accepts `already ingested` (space)

**Before:** Emitter at line 472 produced `SKIP:{folder} — already ingested (run REQ-… …)`.
Classifier at line 619 checked `if "already_ingested" in body_low` (underscore).
Every idempotent skip misclassified as `skipped_no_report` → retry-failed-only
re-attempted healthy folders.

**After:** Accepts `already_ingested`, `already ingested`, `idempotent`,
AND the unambiguous `folder unchanged since` marker. Forward-compat
for whichever shape future emitters use.

### P0-4 — Vertex offline fallback raises `VertexOfflineFallback`, not cached

**Before:** `_generate_via_vertex` returned `(body, 0, 0)` on Vertex
failure. The caller treated the offline body as a normal Vertex
response: validators_passed=True, fallback_used=False, cited_eids=[].
Both Redis L1 (15 min TTL) and `vertex_synthesis_cache` got the
offline message. Operators who fixed IAM/model/project still saw
"offline mode" until the TTL expired.

**After:** `_generate_via_vertex` raises `VertexOfflineFallback`
with `.body`, `.kind`, `.msg`, `.hint`. The router catches it
explicitly and sets `fallback_used=True` BEFORE the cache write
gates fire — both caches are bypassed. Once Vertex recovers, the
next /answer call goes straight to Vertex with no stale offline
message masking the recovery.

### P0-5 — Standalone SSE parser accepts `obj.text`

**Before:** Standalone backend-loader.js yielded
`{ token: obj.token || obj.delta || "" }`. Backend SSE emits
`event: token\ndata: {"text":"..."}`. Every chunk yielded `""`.
The chat panel accumulated nothing and fell back to local scripted
answers even when Vertex streamed real grounded content.

**After:** `{ token: obj.text || obj.token || obj.delta || "" }` —
accepts the actual backend shape AND retains the legacy aliases.

### P0-6 — Standalone adds `DMA.admin.uploadPackage(file)` for `/ingest/package`

**Before:** Standalone only exposed `DMA.admin.uploadAssessment(file)`
which posted JSON to `/ingest/assessment` (bot-replay endpoint).
A complete-package zip had no UI affordance — operators had to
shell out to `curl`.

**After:** `DMA.admin.uploadPackage(file)` posts multipart/form-data
to `/api/v1/ingest/package` with a 180s timeout (real packages
take 30-60s to ingest). The existing `uploadAssessment` keeps its
JSON contract for AppPayloadV1 replay. The two routes are no
longer confusable.

### P1-7 — Drive-backfill catalogue defaults to `v5.0`, not `v7.0`

**Before:** `_rubric_version_to_catalog(None)` returned `"v7.0"`
unconditionally. Historical Drive backfills (which predate the
v7 catalogue) got mis-mapped to v7.0 — every legacy `P1C1.1`-shape
subcap ID failed to resolve through aliases that didn't exist.

**After:** `_rubric_version_to_catalog(None, data_source="DRIVE_BACKFILL")`
returns `settings.backfill_default_catalogue_version` (v5.0).
Manual operator uploads still default to v7.0. New env var
`DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION` (defaults to v5.0) is
required by `preflight-parameters.sh` in `DEPLOY_MODE=live`.

Also: `persist_package` now self-heals when the catalogue version's
FK target row in `ccg_catalog_versions` doesn't exist — inserts a
placeholder row + emits `catalogue_version_stub_inserted:<version>`
warning so the operator sees the loader still needs to run.

## Tests

`backend/tests/test_audit_final_p0_patches.py` — 13 focused tests,
one (or more) per defect, each would FAIL if the fix were reverted:

| Test | Defect |
|---|---|
| test_zip_entry_should_skip_excludes_05_narrative_deck | P0-1 |
| test_max_per_entry_uncompressed_bytes_cap_is_50_mb | P0-1 |
| test_ingest_package_zip_with_60mb_deck_skips_deck_not_413 | P0-1 |
| test_historical_backfill_extract_zips_returns_tuple_with_warnings | P0-2 |
| test_historical_backfill_extract_zips_rejects_zip_slip | P0-2 |
| test_historical_backfill_extract_zips_skips_deck_entries | P0-2 |
| test_classify_outcome_accepts_already_ingested_space_variant | P0-3 |
| test_vertex_offline_fallback_is_exception_not_tuple | P0-4 |
| test_generate_via_vertex_raises_offline_fallback_on_import_error | P0-4 |
| test_standalone_sse_parser_accepts_text_field | P0-5 |
| test_standalone_admin_upload_package_exists_and_targets_ingest_package | P0-6 |
| test_drive_backfill_missing_rubric_resolves_to_v5_default | P1-7 |
| test_backfill_default_catalogue_version_in_settings | P1-7 |

## Release gate impact

- Backend sweep: **1441 → 1454 tests** (+13 audit patches + 0 regressions
  + existing tests adapted for the new `_MAX_UPLOAD_BYTES=100 MB` cap).
- Frontend vitest: **234 / 234** (unchanged — patches are source-level).
- ruff: clean.
- Standalone bundle: **372 KB** (unchanged).

## Cross-references

- ADR 0005 — catalogue versioning (per-run resolver pins v5 vs v7).
- ADR 0010 — Clay connector HMAC (sibling fail-closed pattern).
- ADR 0012 — /ingest/assessment dual-auth (sibling /ingest/* endpoint).
- ADR 0013 — Two-phase deploy (preflight-parameters.sh now requires
  the new `DMA_BACKFILL_DEFAULT_CATALOGUE_VERSION` in live mode).
- `docs/QA-CONTRACT.md` PD-08 (parser fidelity) — real-sample matrix
  was the surface the audit confirmed.
- `docs/QA-CONTRACT.md` PROD-06 (Vertex grounding) — offline-not-cached
  contract.
