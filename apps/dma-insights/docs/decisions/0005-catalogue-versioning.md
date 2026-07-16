# ADR 0005 — Capability catalogue: versioned `ccg_*` tables + alias bridge

**Status**: Accepted (2026-05-20)

## Context

Zennify ships a Comprehensive Capability Mapping every ~2 quarters. V7.0 is
the current canonical (4 pillar workbooks + Visualized Schema HTML, totals
locked at 16 categories / 136 L1 / 851 sub-caps / 165 T2 variants). Historical
DMAs were scored against v5.0 / v6.8; some sub-cap IDs renamed, split, or
merged across versions. Re-scoring 115 historical DMAs is infeasible.

## Decision

**Versioned `ccg_*` tables**. Every row carries a `version` column; PK
composite `(version, …)`. Every `runs` row pins `ccg_catalog_version` at
ingest, never rewritten. Catalogue updates are atomic + admin-gated:

1. Loader writes to a `staging.*` schema.
2. Runs all integrity validators (row counts, FK closure, congruence audit
   per §09 of the schema HTML, alias bridge from each workbook's
   `_R1_Source_Reference` tab).
3. Presents a diff payload at `/admin/catalogue` for admin approval.
4. On approval: atomic `BEGIN; INSERT … SELECT … FROM staging; UPDATE
   ccg_catalog_versions SET frozen_at=NOW(); COMMIT;`.
5. Frozen versions are immutable; revisions land as a new version.

**Alias bridge**: `ccg_subcap_aliases(prior_version, prior_subcap_id,
current_version, current_subcap_id, migration_action, migration_notes)`.
Loaded from each workbook's `_R1_Source_Reference` tab on every ingest. An
older `subcap_scores.subcap_id` from a v5.0 run can be rendered against v7.0
IDs at view time — no data lost on a catalogue bump, only translated.

**Per-run resolver**: `backend/app/services/catalogue_resolver.py` exposes
`resolve_subcap(scoring_subcap_id, run.ccg_catalog_version) → canonical_row`.
Every API/UI surface that touches a `subcap_id` reads through this resolver.
UI badges "Translated from v5.0 — original P2C3.1.4" when an alias was used.

## Cadence (resolved 2026-05-20)

Per-batch on upload. Loader watches `gs://dma-insights-catalogue-staging/`
via Cloud Scheduler hourly poll. Any new workbook set (matched by filename
prefix `Pillar_{1..4}_Comprehensive_Capability_Mapping_v{X}.xlsx`) triggers
the staging ingest. Manual quarterly trigger remains as a fallback.

## L1 ID stability (resolved 2026-05-20)

When a workbook supplies a canonical `L1_ID` column, the loader prefers it
as the new primary key and writes the prior derived slug into
`ccg_subcap_aliases` (migration_action=`l1_id_promoted`). Until then, the
derived `category_id + slug(L1_Capability_name)` stays canonical.

## Consequences

- Multi-generation DMAs coexist without rewriting history.
- The catalogue is data, not code; admin promotes versions without redeploy.
- Adds 25 new tables (one per canonical tab × four pillars, deduplicated).
- Loader is a Cloud Run Job — not in the request path.
