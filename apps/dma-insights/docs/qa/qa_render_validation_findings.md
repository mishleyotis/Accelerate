# Render-validation findings — 104 entities × 12 endpoints (2026-06-07; Batch 3 update)

## Batch 3 update (2026-06-07)

The shallow catalogue alias bridge
(``app/services/catalogue_alias_bridge.py``) landed in Batch 3 and
recovers the FAIL packages whose scoring workbooks emit
category-level ``SubCap_ID``s. Live post-batch numbers:

|  | OK | PARTIAL | FAIL | total |
|---|---:|---:|---:|---:|
| Before Batch 3 | 528 (42.3%) | 692 (55.4%) | **28 (2.2%)** | 1248 |
| **After Batch 3** | **536 (42.9%)** | 688 (55.1%) | **24 (1.9%)** | 1248 |

4 FAIL cells resolved: AMH overview + heatmap, Wescom overview +
heatmap. Both packages now ship 1085 ``subcap_scores`` rows each
(17 categories × 50-122 child subcaps per v7.0 catalogue), all
marked ``data_source='shallow_broadcast'`` with
``parent_category_id=<source category>``. The UI surfaces the
disclosure via the new ``HeatmapCell.data_source`` /
``parent_category_id`` fields.

End-to-end probe (American Homes 4 Rent):
- ``/overview`` → 4 pillar_scores (P1=2.78, P2=2.40, P3=2.66,
  P4=3.45), overall=2.82. Aggregation correctly rolls broadcast
  rows up to pillars.
- ``/heatmap?zoom=subcap`` → 1085 cells, all
  ``data_source='shallow_broadcast'``.
- ``/heatmap?zoom=pillar`` → 4 cells, aggregator propagates
  ``data_source='shallow_broadcast'`` to the pillar level so the
  UI disclosure surfaces at every zoom.

## The 12 remaining FAIL entities (DOCX-only / non-canonical layout)

| Entity | Reason |
|---|---|
| ameris-bank-123d | DOCX-only package (no 01_..08_ canonical layout); ``docx_only_package_no_manifest`` warning |
| atb-3551 | DOCX-only |
| dovenmuehle-mortgage-inc-0001 | ``01_evidence missing`` + no scoring artifacts |
| echelon-insurance-echelo-0001 | DOCX-only |
| gesa-b655 | DOCX-only |
| lpl-financials-7f12 | DOCX-only |
| mag-mutual-9f7a | DOCX-only |
| midfirst-bank-d1c3 | DOCX-only |
| propartners-financial-0001 | DOCX-only |
| spg-2c40 | DOCX-only |
| valley-bank-b208 | DOCX-only |
| ziphq-340f | DOCX-only |

These packages have NO scoring CSV / XLSX for the bridge to operate
on. Resolution requires the ``subcap_narrative_extractor`` (AI
Loop 6 in the CLAUDE.md AI-chain diagram) to parse the DOCX prose
and emit structured ``subcap_scores`` rows. Deferred to a future
batch that re-enables Vertex Pro structured-output extraction.

## Cascade effects observed (cross-harness)

- **Language audit (``qa_language_audit.py``):** 1515 → 1791
  violations (+276). AMH's 1085 broadcast rows + Wescom's 1085 rows
  each carry the parent (bot-emitted) rationale forward verbatim;
  the audit scans every persisted rationale. This is the expected
  behavior of the bridge (the operator mandate is "don't fabricate"
  -- the bridge inherits parent rationale rather than synthesizing
  per-child copy). Vertex language rewrite pass (Batch 6) will
  close this on the rendered surfaces.
- **Re-ingest discipline (Batch 2 ``skip_tables``):** the broadcast
  block sits inside the ``subcap_scores`` UPSERT loop, so the
  Batch-2 selective re-ingest correctly skips it when only
  non-scoring artifacts changed -- verified by re-running the
  Batch-2 demo after Batch 3 landed; document_sections hash stayed
  identical across a scoring-CSV mutation.
- **Heatmap aggregator:** the new ``_aggregate_data_source``
  helper rolls up ``data_source`` for pillar/category/capability
  zoom: any ``shallow_broadcast`` child makes the parent
  ``shallow_broadcast`` so the disclosure propagates upward. No
  cell silently presents a broadcast score as direct.
- **Tests:** 1877 passed, 0 failed (+12 from new bridge tests;
  +1 from active-voice rationale guard).

---



Per the operator mandate: "Please do a thorough check to validate
that the 100+ clients are rendered well within the app ... Do a
thorough check on each rendered segment for all the 100+ DMAs.
Check all pages pick correct stuff."

Harness: `app/scripts/qa_render_validation.py` (in-process FastAPI
ASGI probe; ADMIN role; bypasses auth via dependency override).
Output: `docs/qa/qa_render_matrix.tsv` (1248 rows = 104 entities
× 12 endpoints).

## Summary

| | OK | PARTIAL | FAIL | total |
|---|---|---|---|---|
| All cells | 528 (42.3%) | 692 (55.4%) | **28 (2.2%)** | 1248 |

Zero hard FAILs across 10 of 12 endpoints. 14 entities × 2 endpoints
fail (overview + heatmap) — same 14 entities, single root cause.

## Per-endpoint scores

| Endpoint | OK | PARTIAL | FAIL | Notes |
|---|---|---|---|---|
| `runs` | 104 | 0 | 0 | every entity has at least 1 persisted run ✓ |
| `health` | 104 | 0 | 0 | health endpoint always serves (may have 0 alerts) ✓ |
| `overview` | 87 | 3 | **14** | 14 entities have 0 pillar scores (root cause below) |
| `evidence` | 87 | 17 | 0 | 17 packages ship no evidence rows; parser surfaces a `01_evidence missing` warning |
| `heatmap` | 0 | 90 | **14** | PARTIAL = <100 cells; small packages dominate. 14 FAIL = same root cause as overview |
| `focus_areas` | 70 | 34 | 0 | 34 packages lack `04_reports/*Client_Profile*.docx` |
| `recommendations` | 54 | 50 | 0 | 50 packages parse 0 recommendations |
| `techstack` | 22 | 82 | 0 | tech stack is a 06_peers / Explorium-feed artifact; most packages don't ship it |
| `insights` | 0 | 104 | 0 | rule engine hasn't been triggered to write `insight_cards` rows |
| `context` | 0 | 104 | 0 | firmographics — many packages enrich fewer than 3 of the 6 tracked fields |
| `platforms` | 0 | 104 | 0 | `platform_scores` is a post-persist derived table; populated by the platform-scoring rule engine |
| `intelligence` | 0 | 104 | 0 | intelligence-profile is computed by the `intelligence_recompute` worker on a Pub/Sub trigger — not yet run for these entities |

## The 14 FAIL root cause

Every FAIL traces to one of three classes; the 14 overview/heatmap
fails are all the first class.

### Class A — Category-level subcap_ids in the source workbook (14 entities)

The bot pipeline emits these packages with `SubCap_ID` at category
depth (`P1C1`, `P2C3`) instead of canonical subcap depth
(`P1C1.1.1`, `P2C3.2.4`). The catalogue v7.0 has 1236 subcap-level
rows; none of the category-level IDs match, so `CatalogueResolver`
returns `SubcapNotFound` for every row and `subcap_scores` is empty.
The parser warning surfaces the gap:

> ``catalogue_unresolved:694/694 subcaps unresolved against v7.0``
> ``catalogue_empty_for_version: ZERO of 694 parsed subcaps resolved
>   against v7.0. Likely the catalogue loader has not populated
>   ccg_subcaps rows for this version (placeholder ccg_catalog_
>   versions row only). Run the ccg_loader job with --version=v7.0
>   and the correct --workbooks-dir before this package can surface
>   scores.``

The warning text is misleading — the catalogue IS populated for
v7.0 (1236 rows), but at a deeper taxonomy than what these packages
emit. Affected entities:

`american-homes-4-rent-lp-0001`, `ameris-bank-123d`, `atb-3551`,
`dovenmuehle-mortgage-inc-0001`, `echelon-insurance-echelo-0001`,
`gesa-b655`, `lpl-financials-7f12`, `mag-mutual-9f7a`,
`midfirst-bank-d1c3`, `propartners-financial-0001`, `spg-2c40`,
`valley-bank-b208`, `wescom-financial-wescom--0001`, `ziphq-340f`.

**Recommended remediation:** none of these are an app-side bug —
the bot pipeline needs to re-emit at subcap-level for v7.0, OR the
catalogue needs a "shallow alias bridge" that maps each category
ID to its first-N subcap children. We document but don't ingest
score noise.

### Class B — DOCX-only packages without canonical layout

E.g. Ameris Bank, ATB. Warning:
``docx_only_package_no_manifest: no MANIFEST.json or canonical
01_..08_ layout; ingesting DOCX report(s) only``. Document_sections
+ E-IDs persist, but no scoring. These overlap with Class A.

### Class C — Missing evidence sub-folder

E.g. Dovenmuehle. Warning: ``01_evidence missing — no evidence
rows ingested``. Overview / heatmap still render zero-score because
of Class A; would otherwise render skeleton fine.

## The 692 PARTIAL cells — operator-visible, not bugs

Most PARTIAL cells are deliberate "data hasn't been computed yet"
states rather than wiring failures:

- `insights`, `platforms`, `intelligence` — derived tables populated
  by post-commit workers / rule engines that haven't run for these
  in the local-DB context. In production these populate on the
  Pub/Sub fan-out within seconds of ingest.
- `context`, `techstack`, `recommendations`, `focus_areas`,
  `evidence` — PARTIAL when the source package didn't emit the
  corresponding artifact. These render the skeleton with a
  `data-source="skeleton"` marker per the wireframe contract.
- `heatmap` with <100 cells — small package; the page renders
  correctly with fewer cells.

## Action items

1. **(Documentation, not code)** Flag the 14 Class-A entities in
   `STATUS.md` as "awaiting bot-pipeline re-emit at subcap depth".
   The data IS in the DB; just at the wrong granularity to surface
   as scores.
2. **(Operator-facing)** Improve the misleading `catalogue_empty_
   for_version` warning text to distinguish "catalogue has 0 rows"
   from "catalogue has rows but at a different taxonomy depth".
3. **(Worker)** Run `intelligence_recompute` post-deploy so
   intelligence-profile cells flip from PARTIAL → OK across the
   104 entities.
4. **(Reproduce)** `python -m app.scripts.qa_render_validation
   --output docs/qa/qa_render_matrix.tsv` produces the current
   matrix; running it after each parser/persist change is a
   one-shot regression check.

## Live commands

```bash
# Smoke test on 5 entities
python -m app.scripts.qa_render_validation --limit 5

# Full corpus → matrix file
python -m app.scripts.qa_render_validation --output docs/qa/qa_render_matrix.tsv

# Exit code: 0 if no FAILs, 1 otherwise — wire into CI as a regression gate
```
