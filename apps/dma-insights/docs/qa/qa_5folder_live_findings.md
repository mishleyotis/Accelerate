# v2 QA — Live parse evidence against the 5 real client folders

**Run command:** `.venv/bin/python qa_v2_5folder_audit.py`
**Run date:** 2026-06-06
**Baseline:** `HEAD = 788ff25` (Batch 9 + v2 under-leveraged matrix)
**Parser tested:** `app/services/parsers/dma_package.py:parse_package`
**Evidence file:** `apps/dma-insights/docs/qa/qa_5folder_parse_audit.json`

---

## Summary matrix (actual parse output)

| Folder | evidence | subcaps | recs | sections | warnings | qa_verdict | status |
|--|--|--|--|--|--|--|--|
| **Alma_Bank** | 105 | 698 | 7 | 72 | 0 | yes | ✓ ok |
| **Calprivate** | 125 | **0** | **0** | 47 | **0 (silent)** | **no** | ⚠ ok-but-broken |
| **Nicola_Wealth** | — | — | — | — | — | — | ❌ **PARSE_FAILED** |
| **Odlum_Brown** | 127 | **0** | **0** | 54 | **0 (silent)** | no | ⚠ ok-but-broken |
| **WSFS_Bank** | 106 | 708 | 0 | 68 | 0 | yes | ⚠ no-recs |

**3 of 5 real client packages fail to deliver a usable assessment
to the UI today.** Only Alma_Bank fully populates subcaps + recs.
Nicola_Wealth crashes. Calprivate + Odlum_Brown extract evidence
+ report sections but **zero scoring data** — the heatmap will be
empty for the AE.

---

## F1 [P0] — Nicola_Wealth: total parse failure (case-sensitive glob)

### Symptom
```
ValueError: no run manifest found under
  tests/fixtures/dma_packages_real_samples/Nicola_Wealth__DMA
  at app/services/parsers/dma_package.py:431
```

### Root cause
`dma_package.py:400` Priority-4 fallback globs
`subdir.glob("*qa_verdict*.json")` (lowercase). Nicola_Wealth ships
`07_governance/NicolaWealth_L2_QAVerdict.json` — uppercase
`QAVerdict`. Glob is case-sensitive on Linux/Mac → file skipped →
no run_manifest fallback → ValueError raised at line 431.

`parser.find` traversal (lines 370-402):
- Priority 1: searches 5 fixed `run_manifest.json` paths — Nicola has NONE
- Priority 2: globs `*run_manifest*.json` — Nicola has NONE
- Priority 3: searches `qa_verdict.json` + `audit_summary.json` literal — Nicola has NEITHER
- Priority 4: globs `*qa_verdict*.json` — Nicola ships `NicolaWealth_L2_QAVerdict.json` but lowercase glob MISSES it
- → raise at line 431

### Affected pages (end-user impact)
- **Every** dma-insights page for Wealth-management subvertical
  clients. Nicola is the canonical Wealth fixture; once landed in
  production, the entity row never appears in DirectoryPage,
  ClientOverviewPage 404s, HeatmapPage 404s, AdminPage Drive crawl
  surfaces this as `parse_failed` quarantine.
- **Customer-facing:** Wealth customers signing into the
  prospecting flow get "no DMA on file" — even though one was
  generated.

### Fix (file:line)
`app/services/parsers/dma_package.py:382-402` — change Priority 4
glob to case-insensitive:

```python
# BEFORE (line 400)
for p in sorted(subdir.glob("*qa_verdict*.json")):

# AFTER — case-insensitive glob via lowercase comparison
for p in sorted(subdir.iterdir()):
    name_lower = p.name.lower()
    if name_lower.endswith(".json") and "qa_verdict" in name_lower:
        if p not in manifest_candidates:
            manifest_candidates.append(p)
```

Same fix needed for the `*run_manifest*.json` glob at lines 382-388
(WSFS uses `run_manifest.json` lowercase, but future variants may
not).

### Validation
TDD-by-revert per Batches 7-9:
```python
# backend/tests/test_qa_v2_nicola_parse.py
def test_nicola_wealth_parse_succeeds_via_qaverdict_fallback():
    pkg = parse_package(NICOLA_FIXTURE_PATH)
    assert pkg is not None
    assert pkg.run_manifest is not None
    assert pkg.run_manifest.run_id  # populated from QAVerdict.json
    # Warning must be recorded (used variant manifest)
    assert any("variant manifest" in w for w in pkg.parser_warnings)
```

Revert-test: change `lower()` back, test fails with the same
`ValueError`. Restores TDD-by-revert audit trail.

### Cascade gate considerations
- Gate 2 (parser change): re-run Alma+WSFS+Calprivate+Odlum +
  the 6 sanitised richbank-vintage fixtures; verify all still parse
  with same baselines (warning counts unchanged).
- Gate 3 (frontend): no UI changes; rendering paths unaffected.
- Gate 5 (TDD-by-revert): new contract test passes after fix, fails
  before.

---

## F2 [P0] — Odlum_Brown: 0 subcaps extracted (nested scoring_exports/ dir)

### Symptom
Parse status `ok`, evidence_count=127, but **subcap_scores_count=0**.
HeatmapPage will render zero cells; ClientOverviewPage pillar bars
empty; HealthPage Age/Gates tabs empty.

### Root cause
Odlum_Brown ships final scoring CSVs at:
```
07_governance/scoring_exports/export_category_summary.csv
07_governance/scoring_exports/export_pillar_summary.csv
07_governance/scoring_exports/export_scoring_detail.csv
```

But the parser scans only `03_scoring_workbook/` for `export_*.csv`
(`dma_package.py:744`). Odlum's `03_scoring_workbook/` contains
only the raw Layer-1 XLSX (`DMA_Assessment_Workbook_OdlumBrown_…
.xlsx`) and no exports.

The XLSX-only fallback either:
- Doesn't fire because the parser expects exports first
- Or fires but `scoring_workbook.py` returns 0 rows for Odlum's
  XLSX shape

Either way, end-user surface is empty.

### Affected pages
- **HeatmapPage** (`HeatmapPage.tsx:174` cell clicks) — all cells
  greyed
- **ClientOverviewPage** (`ClientOverviewPage.tsx:225-247` pillar
  bars) — all bars 0
- **HealthPage** (`HealthPage.tsx:478-493` 5 tabs) — Age tab shows
  100% undated, Gates tab shows no rules fired
- **InsightsPage** — no insight cards generated post-persist

### Fix (file:line)
`app/services/parsers/dma_package.py:730-744` scoring CSV scan —
add nested path:

```python
# BEFORE (around line 744)
scoring_dir = root_p / "03_scoring_workbook"

# AFTER
# Look in 03_scoring_workbook/, 07_governance/scoring_exports/,
# and 08_appendices/ for export_*.csv files (handles Odlum-style
# nested exports).
candidate_export_dirs = [
    root_p / "03_scoring_workbook",
    root_p / "07_governance" / "scoring_exports",
    root_p / "08_appendices",
]
exports_found = []
for d in candidate_export_dirs:
    if d.is_dir():
        exports_found.extend(sorted(d.glob("export_*.csv")))
```

### Validation
```python
def test_odlum_brown_finds_nested_scoring_exports():
    pkg = parse_package(ODLUM_FIXTURE_PATH)
    assert pkg.subcap_scores  # >0
    assert pkg.pillar_scores  # populated
    # No warning about missing exports
    assert not any("export" in w.lower() and "missing" in w.lower()
                   for w in pkg.parser_warnings)
```

### Cascade
- Gate 2: re-run Alma+WSFS to confirm they STILL prefer their
  own 03_ exports over any (non-existent) 07_ nested set.
- Specifically: the new dir-priority order must NOT load duplicate
  data when 03_ AND 07_ both have exports.

---

## F3 [P0] — Calprivate_Bank: 0 subcaps extracted (no CSV exports, XLSX-only)

### Symptom
Parse status `ok`, evidence_count=125, but **subcap_scores_count=0**
+ **recommendations_count=0**.

### Root cause
Calprivate ships `03_scoring_workbook/` with ONLY:
- `DMA_Assessment_Workbook_CPB_20260527.xlsx` (raw Layer-1)
- `calculation_chain.json` (1.5 KB; NEW field — under-leveraged
  per qa_ingestion_under_leveraged.md §C class)

NO `export_*.csv` files at all. The parser's docstring (lines 17-21)
expects all 4 export CSVs in 03_scoring_workbook. Since they're
missing, parser would need to read the raw XLSX via
`scoring_workbook.py` leaf parser.

The raw XLSX presumably succeeded (no warnings emitted), but
populated `subcap_scores=[]` — meaning the XLSX parser fell into a
silent-empty branch.

### Affected pages
Same as F2 — HeatmapPage, ClientOverviewPage pillar bars, HealthPage,
InsightsPage all empty for Calprivate.

### Investigation needed (Phase 2B audit cell)
Why does `scoring_workbook.py` return 0 rows for Calprivate XLSX?
Hypotheses:
1. Sheet name doesn't match parser expectations (per CLAUDE.md the
   parser looks for "Scoring" / "Score Sheet" / "Detail")
2. Header row drift (column rename like `SubCap_ID` → `Subcapability ID`)
3. Calprivate XLSX is a "shell" with no scoring data populated (bot
   shipped without scoring done)

### Fix (probable)
Once root cause confirmed:
- If sheet-name drift: extend `scoring_workbook.py` SHEET_NAME_HINTS
  to include Calprivate's sheet name
- If column-rename drift: add aliases for renamed columns
- If shell only: emit warning `e_scoring_xlsx_empty` so operator
  knows the package is incomplete; persist no rows; UI shows
  proper "scoring pending" state instead of silently-empty heatmap

### Cascade
- Gate 2: re-run all other folders to verify the new SHEET_NAME_HINTS
  / column aliases don't introduce false matches.

---

## F4 [P1] — WSFS_Bank: 0 recommendations extracted (no rec source in package)

### Symptom
Parse status `ok`, evidence_count=106, subcap_scores_count=708 (good!),
but **recommendations_count=0**.

### Root cause
WSFS_Bank package has NO `recommendations_detail.json` anywhere
(confirmed via `find … -iname "*recommend*"`). This may be:
- The bot didn't generate recommendations for WSFS
- A different file shape (e.g. recs in `qa_verdict.json` body)

### Affected pages
- **ClientOverviewPage** (`ClientOverviewPage.tsx` recommendations
  strip) — empty
- **RecommendationsPage** (if reached) — empty
- Bot loop doesn't close on the recs deliverable

### Investigation needed
Read WSFS's `qa_verdict.json` + governance files to see if recs are
in non-standard location.

### Cascade
- Low — additive parser support; doesn't break existing behaviour.

---

## F5 [P1] — Firmographics not populated for any folder (regression?)

### Symptom
For Alma_Bank, WSFS, Odlum_Brown, Calprivate: `firmographics_present:
true` but `firmographics_populated_fields: []` and `leadership_count: 0`.

### Root cause
`firmographics` object is created but its fields are all empty.
Per Batch 4.2, `client_profile.py` extracts firmographics via
regex. If the regex doesn't match the DOCX content, all fields
stay None.

Specifically:
- Alma_Bank ships `04_reports/AlmaBank_ClientProfile_Research_Report.docx` (54 KB)
- WSFS ships `04_reports/WSFS_Client_Profile_Research_Report.docx` (53 KB)
- Calprivate ships `04_reports/DMA_Client_Profile_CPB_20260527.docx` (55 KB)
- Odlum ships `04_reports/OdlumBrown_ClientProfile_FINAL.docx` (71 KB)

The Batch 4.2 regex SHOULD parse these. v2 audit will:
1. Run client_profile.py against each DOCX standalone
2. Inspect what fields ARE extracted (likely some are extracted
   but the AGGREGATE `firmographics_populated_fields` is empty due
   to attribute-access mismatch in our test script)
3. OR confirm regex truly fails — then this is the actual
   firmographics regression to fix

### Cascade
- Phase 2B leaf-parser audit (per the v2 plan) addresses this
  directly.

---

## F6 [P2] — `IngestedPackage` schema drift from `dma_package.py` docstring

### Symptom
The Pydantic model `IngestedPackage` exposes these fields (from
`pkg.__dict__` introspection):
```
category_scores, evidence, evidence_count, expected_subcap_count,
firmographics, issue_register, manifest, parser_warnings,
peers, pillar_scores, pillar_weights, qa_verdict, recommendations,
report_sections, run_manifest, subcap_scores, tech_stack
```

But `dma_package.py:11-40` docstring describes ALSO emitting:
- `focus_areas` (from client_profile.py per CLAUDE.md)
- `parser_observations` (per CLAUDE.md)
- `peer_scores` (renamed to `peers` in dataclass)

### Affected
- Persistence layer: `package_persist.py` may not be persisting
  focus_areas because they don't exist on the dataclass
- Phase 1 contract matrix: dataclass-as-source-of-truth diverges
  from docstring

### Fix
- Either rename docstring fields to match dataclass OR add the
  missing dataclass fields (focus_areas, parser_observations).
- Per the v2 Phase 1.4 schema↔TS matrix audit, the dataclass is
  also referenced from `package_persist.py:1587-1650`
  (focus_areas) which suggests the dataclass DOES expose
  focus_areas elsewhere — likely on `firmographics.focus_areas`?
- Investigation needed.

---

## Cascade-gate implications

For each fix above:

| Finding | Affected files | Gate-2 cascade check | Gate-3 cascade check | Gate-5 cascade check |
|--|--|--|--|--|
| F1 | dma_package.py:400 glob | Re-parse all 5 + 6 richbank — warning counts unchanged | None | New contract test + revert-test |
| F2 | dma_package.py:744 dir list | Re-parse all 5 — Alma/WSFS still prefer 03_ exports | None | New contract test |
| F3 | scoring_workbook.py SHEET_NAME_HINTS or column aliases | Re-parse all 5 — no false matches | None | New contract test |
| F4 | dma_package.py recs loader | Re-parse all 5 — Alma's 7 recs unchanged | None | New contract test |
| F5 | client_profile.py regex | Re-parse all 5 — Alma firmographics still populated | ClientOverviewPage header + footer render | Per-fixture firmographics contract test |
| F6 | IngestedPackage dataclass + docstring | Phase 1 schema matrix sourced from dataclass | None | Phase 1.4 schema contract test |

### Production-Ready Gate impact

If any of F1–F4 ships as-is, the v2 audit recommends **NO-GO** for
the Wealth-management subvertical (Nicola), Calprivate, and Odlum
clients. F5 + F6 are P1/P2 and acceptable for `CONDITIONAL GO` with
pre-launch remediation.

---

## Evidence (verbatim parse outputs)

Full JSON dumps per folder at
`apps/dma-insights/docs/qa/qa_5folder_parse_audit.json`. Sample
rows (Alma_Bank successful + Nicola_Wealth failing) in
`qa_evidence_snippets.txt`.

---

## Next steps

1. ☐ Investigate F3 root cause (Calprivate XLSX scoring_workbook
   silent empty) — run `scoring_workbook.py` standalone against
   Calprivate XLSX, capture extraction output
2. ☐ Investigate F4 root cause (WSFS recs source) — search WSFS
   for ANY recommendations payload; document
3. ☐ Investigate F5 root cause (firmographics regex on real DOCX)
   — run `client_profile.py` standalone against all 4 DOCX
4. ☐ Investigate F6 (focus_areas attribute) — grep
   `package_persist.py` for `focus_areas` usage; trace dataclass
5. ☐ Write the 4-6 contract regression tests (one per finding)
6. ☐ Land the parser fixes for F1, F2 as Phase-2A patches
7. ☐ Run cascade Gate 2 against the patches
8. ☐ Update STATUS.md with the v2 audit verdict

This artifact closes the LIVE-PARSE-EVIDENCE deliverable of Phase
2A in the v2 plan.

---

## F4 update (2026-06-06): confirmed source-side gap

### Investigation result
After landing F2 + F5b on the default branch, the F4 finding (WSFS /
Nicola / Calprivate ship 0 recommendations) was re-investigated:

| Folder | Rec files in package | Embedded recs in qa_verdict? |
|--|--|--|
| Alma_Bank | `08_appendices/recommendations_detail.json` (7 recs) | n/a |
| Odlum_Brown | `07_governance/recommendations_register.json` (6 recs) | n/a |
| **WSFS_Bank** | **NONE** | `recommended_action` = `'DELIVER'` (7-char verdict string, NOT recs) |
| **Nicola_Wealth** | **NONE** | `recommendation` = `'DELIVER_NOTE_ISSUES'` (19-char verdict, NOT recs) |
| **Calprivate_Bank** | **NONE** | no rec key in either qa_verdict shape |

The `recommended_action` / `recommendation` strings in the qa_verdict
JSONs are governance gate verdicts (deliver / hold / reject), not
subcap-level recommendation objects. Alma's canonical shape is:
```json
{"id":"REC-01","priority":"P0 — IMMEDIATE","title":"…","subcap_id":"…","description":"…", …}
```
There is no source in the WSFS / Nicola / Calprivate packages that can
be transformed into that shape.

### Verdict: source-side gap (bot pipeline)

The 3 packages were generated without the recommendations deliverable.
This is NOT a parser bug; it is upstream from the parser. Resolving it
requires the bot pipeline to add the recommendations stage for these
3 entities and re-run.

### Patch landed (visibility, not synthesis)
- `dma_package.py` now emits an explicit `no_recommendations_source`
  parser_warning when no rec JSON is found in either
  `07_governance/` or `08_appendices/`. The admin import-audit
  surface picks this up; AE-facing rec panels render the empty state
  (already covered by `data-source` markers).
- 2 contract tests in `test_qa_v2_5folder_ingestion.py` pin both
  branches: WSFS/Nicola/Calprivate → 0 recs + warning fires;
  Alma/Odlum → 7/6 recs + warning silent.

### Cascade impact
- 0 LOC changed in any rec parser
- 0 schema change
- 0 surface change
- +1 visibility warning per affected package (operator-facing only)
- Alma's 7 recs unchanged; Odlum's 6 recs unchanged
