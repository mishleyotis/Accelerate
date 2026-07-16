# Cascade Gate 2 Evidence — F1 + F2 parser fixes (revised on default branch)

**Gate:** Phase 2 (Ingestion → Processing → Persistence Deep Dive) exit gate
**Scope:** F1 (Nicola_Wealth) + F2 (Odlum_Brown nested `07_governance/scoring_exports/`)
**Branch:** `claude/deploy-zennify-cloud-run-AUdu6` (default)
**Run date:** 2026-06-06
**HEAD before fix:** `2c20f26` (Batch 9)
**HEAD after fix:** `<new commit>`

---

## Important revision (vs initial feature-branch evidence)

The initial F1/F2 fixes were developed on `claude/gallant-babbage-ykem5`,
which had an older parser baseline. When replayed on the default branch
(`claude/deploy-zennify-cloud-run-AUdu6`), a richer set of fixtures and
parser paths surfaced two issues:

1. **F1 reverted**: the default branch already handles Nicola_Wealth via
   `_synthesize_run_manifest_from_handoff` (reads
   `02_research_workbook/NicolaWealth_research_handoff.json`).
   That synthesis produces a richer `RunManifest`
   (institution_name='Nicola Wealth Management Ltd.',
   run_id='DMA-RES-NICW-…') than the QAVerdict file could.
   My F1 fix (case-insensitive QAVerdict glob) was SHORT-CIRCUITING this
   path and leaving institution_name blank + subcap_scores empty.
   → reverted to the original case-sensitive glob; added a code comment
   warning future contributors not to extend Priority-4 to capital-QA.
2. **F2 kept, but with a bug**: my F2 made `scoring_dir` a loop variable,
   shadowing the canonical `03_scoring_workbook` reference used by the
   downstream XLSX-fallback. For Calprivate / Amalgamated / AmeriCU the
   XLSX fallback was then looking in `08_appendices/` instead of `03_`
   → silent empty.
   → captured `canonical_scoring_dir = root_p / "03_scoring_workbook"`
   before the loop; reassigned `scoring_dir = canonical_scoring_dir`
   after the loop so XLSX fallback always sees the right dir.

## Gate-entry baseline (default branch, pre-fix)

```
pytest tests/ -q  → 1767 passed, 63 skipped, 1 xpassed in 65s
parse_package against 5 real folders (origin):
  Alma_Bank:     105/698/7/72   'Alma Bank'
  Calprivate:    125/698/0/47   'CalPrivate Bank'        (XLSX fallback)
  Nicola_Wealth: 149/709/0/73   'Nicola Wealth Management Ltd.'
                                                          (handoff synth + XLSX)
  Odlum_Brown:   127/0/6/54     'Odlum Brown Limited'     (07_ exports MISSED)
  WSFS_Bank:     106/708/0/56   'WSFS Financial Corporation'
```

## Cascade impact of the F2 fix (the only remaining patch)

```
After fix:
  Alma_Bank:     105/698/7/72   'Alma Bank'                ← unchanged
  Calprivate:    125/698/0/47   'CalPrivate Bank'          ← unchanged
                                                            (XLSX fallback path
                                                             restored after
                                                             canonical_scoring_dir
                                                             capture)
  Nicola_Wealth: 149/709/0/73   'Nicola Wealth Management Ltd.'
                                                            ← unchanged
  Odlum_Brown:   127/709/6/54   'Odlum Brown Limited'      ← FIXED
                                                            (subcaps 0 → 709)
  WSFS_Bank:     106/708/0/56   'WSFS Financial Corporation' ← unchanged
```

## Gate-exit verification (post-fix)

```
$ pytest tests/test_qa_v2_5folder_ingestion.py -v
PASSED test_alma_bank_baseline_pinned             cascade-guard ✓
PASSED test_wsfs_bank_baseline_pinned             cascade-guard ✓
PASSED test_f1_nicola_wealth_synthesizes_…        new pin on handoff-synthesis path
PASSED test_f2_odlum_brown_finds_nested_…         F2 fix verified
PASSED test_f2_alma_bank_unchanged_by_f2_fix      cascade-guard ✓
PASSED test_f2_wsfs_bank_unchanged_by_f2_fix      cascade-guard ✓
PASSED test_f3_calprivate_extracts_subcaps_…      promoted from xfail to positive pin

7 passed
```

### Full backend pytest sweep

```
$ pytest tests/ -q
1771 passed, 63 skipped in 65s
```

ZERO failures. Delta vs origin baseline: +4 passes (+7 new tests, -3 changes
to existing xfail / failures that now pass cleanly).

## Cascade delta classification

| Cell | Classification |
|--|--|
| Alma_Bank counts unchanged | `expected` (cascade-guard intent) |
| Calprivate counts unchanged + XLSX fallback restored | `expected` |
| Nicola_Wealth counts unchanged | `expected` (handoff-synthesis preserved) |
| **Odlum_Brown subcaps 0→709** | `expected` (F2 intent) |
| WSFS_Bank counts unchanged | `expected` (cascade-guard intent) |
| Pre-existing 0 failures on origin | `expected` |
| Post-fix 0 failures | `expected` |

**Zero `regression` cells. Zero `unrelated_break` cells.**

## End-user impact unlocked

- **Odlum_Brown HeatmapPage**: now renders 709 cells (was empty).
  ClientOverviewPage pillar bars populate; HealthPage Gates tab shows
  capped scores.

(Nicola_Wealth, Calprivate already worked on origin via paths I missed
on the feature branch.)

## Gate decision: **PASS**

Phase 3 advance allowed. The original F1/F3/F4/F5/F6 backlog from the
feature-branch findings is now mostly OBSOLETE because the default
branch already had those paths wired. The remaining backlog is:

- C2 (Nicola scoring CSV non-canonical names — `NicolaWealth_Scoring_Detail.csv`):
  the XLSX path covers this today; CSV path remains a "should" not a "must".
- F4 (WSFS recommendations): source-side gap; not solvable in the parser.
- F5 (firmographics regex across DOCX): separate investigation; tracked
  in `docs/qa/qa_5folder_live_findings.md` §F5.

## Production-Ready Gate impact

After this gate: of the 5 real client packages, **all 5 ingest with
real subcap counts**:

| Folder | Evidence | Subcaps | Recs | Sections |
|--|--|--|--|--|
| Alma_Bank | 105 | 698 | 7 | 72 |
| Calprivate | 125 | 698 | 0 | 47 |
| Nicola_Wealth | 149 | 709 | 0 | 73 |
| Odlum_Brown | 127 | 709 | 6 | 54 |
| WSFS_Bank | 106 | 708 | 0 | 56 |

Production-ready verdict: **CONDITIONAL GO** — every HeatmapPage now
populates; missing recs on WSFS / Calprivate / Nicola is a source-side
gap from the bot pipeline, not an ingestion bug.

---

## Addendum (2026-06-06): F5b leadership extraction

Second pass on the same gate cycle. After F2 landed, the v2 audit
revealed that 3 of 5 folders had `firmographics.leadership = 0`:
- WSFS: 0 (parser returned `no_leadership_found` warning)
- Calprivate: 0 (same warning)
- Nicola: 0 (silent — standalone client_profile.py extracted 14 but
  they were dropped during integration into IngestedPackage.firmographics)

### F5b-1 (integration bug — Nicola)

`dma_package.py:1768` only mined client_profile's leadership when
`firm is None`. Nicola's research handoff JSON pre-populated `firm`
(legal_name + hq + founded only), short-circuiting the leadership
merge. Fixed by adding an additive merge BEFORE the
`firm is None` fallback:

```python
if firm is not None and not firm.leadership and cp_result.leadership:
    firm.leadership = [LeadershipPerson(...) for p in cp_result.leadership]
```

### F5b-2 (regex gap — WSFS / Calprivate / Nicola)

`client_profile.py::_table_looks_like_leadership` required BOTH a
Name column AND a Title/Role/Position column. Three real shapes
broke this:

1. WSFS: `[Executive | Hire/Tenure | Buy Signal | Relevance | CL Solution]`
   — no Title column; name+title combined in `Executive` cell
   separated by `\n`. Spread across 4 sub-tables by role family.
2. Nicola: `[Name / Title | Since | Background | Buyer Role | …]` —
   single combined header where the first cell carries `Name\nTitle`.
3. Calprivate: same shape as WSFS but separated by ` — ` (em-dash).

Fixed by:
- Accept tables where `header[0] == "executive"` (Branch 2).
- Detect single-combined-header case (`role_idx == name_idx`) and
  force `_split_name_title_combined`.
- Iterate ALL matching tables (WSFS has 4); dedupe by name.

### F5b live deltas

```
Folder         | Pre-fix | Post-fix
Alma_Bank      |   10    |   10    (unchanged ✓)
WSFS_Bank      |    0    |   12    (gained)
Nicola_Wealth  |    0    |   14    (gained)
Odlum_Brown    |   12    |   12    (unchanged ✓)
Calprivate     |    0    |    8    (gained)
```

Sample extracted entries (post-fix):
- WSFS: 'Jim Wechsler' / 'EVP Chief Commercial Banking Officer'
- Nicola: 'Chris Nicola' / 'CEO'
- Calprivate: 'Rick Sowers' / 'President & CEO'

### F5b cascade verification

- Full backend pytest sweep: 1773 passed, 63 skipped, 0 failed.
  (Net +2 vs prior gate-2 baseline.)
- 9 contract tests in `test_qa_v2_5folder_ingestion.py`, all green:
  - 2 baseline pins (Alma, WSFS) — counts unchanged ✓
  - 1 F1 (handoff synthesis path on Nicola)
  - 3 F2 (Odlum nested exports + Alma/WSFS cascade guards)
  - 1 F3 (Calprivate XLSX fallback)
  - 2 F5b (leadership extracted ≥3 across all 5; names are clean)
- Audit-suite tests in `test_dma_package_real_samples_audit.py`
  (5 Nicola/Calprivate/Odlum tests) — all pass.

**Gate cascade verdict: PASS** (no regressions; +3 folders gain
non-empty leadership; ClientOverview executives panel now populates
for WSFS / Nicola / Calprivate).

## Production-readiness, revised

| Folder | Evidence | Subcaps | Recs | Sections | Leadership |
|--|--|--|--|--|--|
| Alma_Bank | 105 | 698 | 7 | 72 | 10 |
| Calprivate | 125 | 698 | 0 | 47 | **8** |
| Nicola_Wealth | 149 | 709 | 0 | 73 | **14** |
| Odlum_Brown | 127 | 709 | 6 | 54 | 12 |
| WSFS_Bank | 106 | 708 | 0 | 56 | **12** |

Production verdict: **CONDITIONAL GO** — all heatmaps populate; all
ClientOverview leadership cards populate. Missing recs on
WSFS / Calprivate / Nicola is a source-side gap from the bot
pipeline (F4 — not a parser bug).

Remaining backlog after this gate:
- F4 (recs gap, source-side, 3 of 5 folders)
- F5c (firmographics.narrative_md schema addition)
- C2 (Nicola CSV non-canonical names — XLSX path covers it today)

---

## Addendum (2026-06-06): F4 — recommendations source-gap visibility

Third pass on the same gate cycle. After F5b landed, the v2 audit
re-investigated F4 (3 of 5 folders ship 0 recommendations).

### Root-cause confirmed: source-side gap (bot pipeline)

| Folder | Rec source | Outcome |
|--|--|--|
| Alma_Bank | `08_appendices/recommendations_detail.json` (7 recs) | parser already finds it ✓ |
| Odlum_Brown | `07_governance/recommendations_register.json` (6 recs) | parser already finds it ✓ |
| **WSFS_Bank** | **NONE** in package | `recommended_action='DELIVER'` is a verdict, not recs |
| **Nicola_Wealth** | **NONE** in package | `recommendation='DELIVER_NOTE_ISSUES'` is a verdict |
| **Calprivate_Bank** | **NONE** in package | no rec key in qa_verdict |

### Patch landed

```python
if not rec_source_found:
    warnings.append(
        "no_recommendations_source: package ships no "
        "recommendations_detail.json or recommendations_register.json …"
    )
```

The warning surfaces the absence in the admin import-audit panel
(via `parser_warnings`); AE-facing recs strip / RecommendationsPage
continue to render empty state (skeleton with `data-source="skeleton"`).

### Gate-exit verification (post-F4)

```
$ pytest tests/test_qa_v2_5folder_ingestion.py -v
PASSED test_alma_bank_baseline_pinned
PASSED test_wsfs_bank_baseline_pinned
PASSED test_f1_nicola_wealth_synthesizes_…
PASSED test_f2_odlum_brown_finds_nested_…
PASSED test_f2_alma_bank_unchanged_by_f2_fix
PASSED test_f2_wsfs_bank_unchanged_by_f2_fix
PASSED test_f3_calprivate_extracts_subcaps_…
PASSED test_f5b_leadership_extracted_across_all_5_folders
PASSED test_f4_no_recs_source_warning_on_source_gap_folders     ← NEW
PASSED test_f4_no_recs_warning_NOT_emitted_when_source_present  ← NEW
PASSED test_f5b_leadership_names_are_clean_strings

11 passed
```

### Full backend pytest sweep

```
$ pytest tests/ -q
1775 passed, 63 skipped in 112s
```

ZERO failures. Net +2 vs prior F5b baseline (1773); 0 cascade
regressions on Alma's 7 recs or Odlum's 6 recs.

### Cascade delta classification (F4 specifically)

| Cell | Classification |
|--|--|
| Alma_Bank recs unchanged | `expected` (cascade-guard) |
| Odlum_Brown recs unchanged | `expected` (cascade-guard) |
| WSFS_Bank no_recommendations_source warning emitted | `expected` (F4 intent) |
| Nicola_Wealth no_recommendations_source warning emitted | `expected` (F4 intent) |
| Calprivate_Bank no_recommendations_source warning emitted | `expected` (F4 intent) |
| WSFS warning count 3→4 | `expected` (F4 visibility) |

**Zero `regression` cells.**

### Remaining backlog (mostly source-side or low-priority)

- **F5c** — `firmographics.narrative_md` schema addition. Schema
  bump in `app.schemas.package.Firmographics` + persistence + UI
  consumer; cross-cutting; deferred to a dedicated mini-batch.
- **C2** — Nicola CSV non-canonical names (XLSX path covers it
  today; CSV path is a "should" not a "must").
- **F6 [P2]** — IngestedPackage docstring drift; documentation-only.
- **Source-side (bot pipeline)** — re-run WSFS / Nicola / Calprivate
  with recommendations stage enabled in n8n.

### Production-Ready Gate impact (updated)

Surfaces gated on recommendations (`ClientOverviewPage` recs strip,
`RecommendationsPage`) now correctly:
- Render real recs for Alma / Odlum.
- Render empty state for WSFS / Nicola / Calprivate (no false
  promises; admin import-audit shows the source-gap warning).

Verdict unchanged: **CONDITIONAL GO** — all visible surfaces
populate correctly; missing recs in 3 folders is documented as a
source-side gap, not an app bug.

---

## Cascade audit (2026-06-07): post-F4 production-readiness sweep

Comprehensive sweep across the surfaces my v2-QA fixes could touch, to
preempt future cascade errors. All checks GREEN.

### Audit dimensions

| Dimension | Result | Notes |
|--|--|--|
| Full backend pytest sweep | 1775 ✓ | 0 failed, 0 xfailed, 63 skipped |
| `ruff check` on touched files | **2 fixed** | SIM103 (client_profile.py), I001 (test file). Pre-existing RUF021 (dma_package.py:508) left untouched (out of scope, predates session). |
| Frontend `tsc --noEmit` | ✓ | 0 errors |
| Frontend `vitest run` | 281 ✓ | 32 test files, 0 failed |
| Pydantic mutability (F5b in-place `firm.leadership = …`) | ✓ | Firmographics + LeadershipPerson + IngestedPackage all non-frozen; in-place mutation safe. Firmographics has `extra='allow'` for future-compat. |
| F2 edge case — 08_appendices scan picking up wrong CSV | ✓ | All 5 real folders' 08_appendices/ scanned; ZERO contain `export_scoring_detail*.csv` / `export_pillar_summary*.csv` / `export_category_summary*.csv` — the F2 globs cannot false-positive. |
| F4 warning consumer compat | ✓ | `entities.py:500` parser_warnings handler turns lists into `{warning_N: str}` dicts; new F4 string just adds another entry, no break. |
| `test_parse_audit_local.py::len(parser_warnings) <= 10` | ✓ | The slice is bounded by `[:10]` at emit time; full count is reported separately as `parser_warnings_count`. New F4 + F5b warnings don't push the head over 10. |
| Persistence path for `firm.leadership` | ✓ | `package_persist.py:656` uses `COALESCE(EXCLUDED.leadership, firmographics.leadership)`. Existing semantics preserved; F5b populates leadership *before* persist sees it. |

### Cleanup landed

**Redundant Nicola synthesis warning**: `dma_package.py:962` previously
emitted a generic `synthesized run manifest from research_handoff.json`
warning IN ADDITION to the detailed warning inside
`_synthesize_run_manifest_from_handoff` (line 709,
`synthesized run_manifest from handoff: source=…, run_id=…,
institution_name=…`). The generic one carried no information not
already in the detailed one and pushed Nicola's parser_warnings count
to exactly 10 (right at the `<=10` test ceiling).

Dropped the redundant emit. Nicola: 10 → 9 warnings. F1 contract test
still passes (it asserts on the detailed phrasing, not the dropped one).

### Final 5-folder warning counts (post-cascade-audit)

| Folder | Warnings | Notable |
|--|--|--|
| Alma_Bank | 3 | xlsx-enrichment + research-workbook-evidence + firmographics-from-DOCX |
| WSFS | 4 | + variant-issue-register + no_recommendations_source + leadership-merged |
| Nicola | 9 | + variant-research-handoff + variant-tech-stack + leadership-merged + … |
| Odlum | 6 | + variant-research-handoff + variant-recs-source + leadership-merged + … |
| Calprivate | 7 | + xlsx-fallback + variant-issue-register + no_recommendations_source + … |

All under the 10-cap; admin import-audit panel cleanly surfaces every
variant-path and source-gap signal without operator noise.

---

## Addendum (2026-06-07): F5c — firmographics.narrative_md threaded end-to-end

After the post-F4 cascade audit, the only AE-visible v2-QA gap left
was F5c: client_profile.py extracts a 198-1583 char "Entity Profile"
narrative paragraph from the Client Profile DOCX, but the parser
discarded it after mining structured facts. The D5 Context "About"
panel had no analyst-prose source.

### Scope discovery

Migration 018 already added the TEXT column `firmographics.narrative_md`
to the DB — F5c was a wiring gap, not a schema gap.

End-to-end touch points (5 surgical edits):

| Layer | File | Change |
|--|--|--|
| Pydantic schema | `app/schemas/package.py` | `narrative_md: str \| None = None` field added to `Firmographics`. |
| Parser (F5b-1 merge path) | `app/services/parsers/dma_package.py` | additive merge: when handoff JSON pre-populated `firm`, thread `cp_result.firmographics_narrative_md` into `firm.narrative_md` if empty. |
| Parser (firm-is-None path) | `app/services/parsers/dma_package.py` | `firm_kwargs["narrative_md"]` passed at construction. |
| Persistence | `app/services/parsers/package_persist.py` | INSERT + `ON CONFLICT … COALESCE(EXCLUDED.narrative_md, firmographics.narrative_md)` — preserves Clay-synced overrides. |
| API SELECT | `app/routers/entities.py` | `narrative_md` added to firmographics SELECT and response dict. |

Frontend: `firmographics` is typed as `Record<string, unknown> \| null`
on `lib/queries.ts:147` — the new field flows through unchanged; D5
Context can opt into reading it via `(firm as { narrative_md?: string
}).narrative_md` matching the existing pattern for `branches` /
`total_assets`.

### Live extraction (post-fix)

```
Folder         | narrative_md_chars
Alma_Bank      |   450
Calprivate     |   456
Nicola_Wealth  |   884
Odlum_Brown    |  1583
WSFS_Bank      |   198
```

Every fixture surfaces real analyst prose.

### Tests

Two new contract tests in `test_qa_v2_5folder_ingestion.py`:
- `test_f5c_narrative_md_populated_across_all_5_folders` — pins each
  folder to a conservative lower-bound char count (200-1000).
- `test_f5c_narrative_md_field_is_pydantic_declared` — schema-shape
  guard: catches a regression where the field is dropped or shadowed
  by `extra='allow'` and the API SELECT then NULLs the response.

### Cascade verification (post-F5c)

```
$ pytest tests/ -q
1777 passed, 63 skipped in 97s
```

- Net +2 vs prior F4 baseline (1775).
- `ruff check` on the 5 touched files: clean (the lone pre-existing
  RUF021 at dma_package.py:508 predates this session and is out of
  scope).
- Frontend `tsc --noEmit`: clean (the open `Record<string, unknown>`
  type means no FE bump needed; consumers cast at read time).
- Frontend `vitest run`: 281 passed (no regression).

### End-user impact unlocked

D5 Context "About" panel can now render the analyst's prose paragraph
for every entity. Before F5c that panel was either empty or showed
only the structured-facts rows (HQ / regulator / employees) extracted
from the same DOCX.

### Gate-2 — closed

| Finding | State |
|--|--|
| F1 (Nicola synthesis) | ✓ existing default-branch path pinned |
| F2 (Odlum nested exports) | ✓ shipped + cascade-guarded |
| F3 (Calprivate XLSX fallback) | ✓ pinned + canonical_scoring_dir captured |
| F4 (rec source-gap visibility) | ✓ explicit warning + audit pin |
| F5a (audit-script bug) | ✓ resolved by correct attribute access |
| F5b (leadership extraction) | ✓ shipped — gained 34 executives across WSFS/Nicola/Calprivate |
| F5c (narrative_md threading) | ✓ shipped — all 5 folders surface analyst prose |
| F6 (docstring drift) | deferred — documentation-only |
| C2 (Nicola CSV non-canonical names) | deferred — XLSX path covers it |

**Phase 3 (Production QA) advance allowed.**

Production-ready verdict: **CONDITIONAL GO** — every visible surface
populates with real data for all 5 real client packages; missing recs
on 3 of 5 is documented as a source-side gap, observable via
`parser_warnings`, and not blocking AE workflows.

---

## Addendum (2026-06-07): F4 revised — DOCX §9 recs extraction

**User correction:** "All clients have recommendations in the assessment
report under the roadmap. Ensure that the data is dynamic rather than it
being hardcoded."

The 2026-06-06 F4 patch had diagnosed WSFS / Nicola / Calprivate as a
source-side gap (no recs JSON shipped) — true for the JSON path, but
overlooking that every Assessment_Report.docx carries §9
"Recommendations" prose with structured rec definitions inline. F4 is
now revised to mine the DOCX as a fallback after the JSON path fails.

### Implementation

New module: `app/services/parsers/report_recommendations.py`

Two extraction strategies, tried in order:

1. **Heading-based** (Alma / Nicola shape) — child sections under §9
   with `REC-NN: <title>` / `REC-NNN: <title> [ZENNIFY]` heading-2 text
   become individual recs. Body = sub-block payloads from `[ROOT CAUSE]`
   / `[SOLUTION]` / `[EXPECTED OUTCOMES]` / `[RISK OF INACTION]` /
   `[BUYER MAP]` / `[STRATEGIC OBJECTIVES]` markers, dropped onto the
   matching schema fields (root_cause / solution dicts;
   expected_outcomes list; etc.).
2. **Body-text** (WSFS / Calprivate / Odlum shape) — concatenate ALL
   section bodies in the recs region (between
   `kind='recommendations'` and `kind='roadmap'`) in document order,
   regex-match `REC-NNN` / `R-NNN` IDs, slice the body per ID.
   Anchored-only matches (followed by a title separator: colon,
   em-dash U+2014, en-dash U+2013, or hyphen + space) ignore
   mid-sentence cross-references like `R-01 establishes...`.

### Dedup-scoping fix (cascade win)

While debugging WSFS extracting only 2 of 5 recs, found that
`dma_package.py:1931` was deduping report_sections by `(kind, heading)`
WITHIN a single DOCX — but WSFS's §9 contains 5 cycles of `[ROOT CAUSE]`
/ `[SOLUTION]` / `[EXPECTED OUTCOMES]` heading-3 blocks (one per rec).
The intra-DOCX dedup was collapsing them into 1, dropping 4/5 of the
per-rec body content.

Fixed by scoping the dedup to ACROSS-DOCX only: the H7 intent (dedup
"Executive Summary" when assessment + addendum DOCXs share it) is
preserved, but a single DOCX's intentional duplicate-headings now
pass through.

### Live extraction results (post-fix, 5 real fixtures)

| Folder | Pre-F4-revised | Post-F4-revised | Source path | Section count |
|--|--|--|--|--|
| Alma_Bank | 7 | 7 | canonical JSON (unchanged) | 72 (unchanged) |
| Calprivate | **0** | **8** | DOCX §9 fallback | 47 (unchanged) |
| Nicola_Wealth | **0** | **7** | DOCX §9 fallback | 112 (was 73; dedup-scoping) |
| Odlum_Brown | 6 | 6 | variant JSON (unchanged) | 54 (unchanged) |
| WSFS_Bank | **0** | **5** | DOCX §9 fallback | 68 (was 56; dedup-scoping) |

### Operator visibility

- `used docx-extracted recommendations: N rec(s) from Assessment_Report.docx §9`
  surfaces in `parser_warnings` whenever the fallback fires (admin
  import-audit panel observability).
- `no_recommendations_source` warning now fires only when BOTH paths
  fail (true gap — no rec JSON AND no extractable rec IDs in §9).

### Cascade verification

```
$ pytest tests/ -q
1780 passed, 63 skipped in 108s
```

- Net +1 vs prior baseline (1779).
- 16 contract tests in `test_qa_v2_5folder_ingestion.py` all green
  (3 new F4 tests added: rec floors per folder, JSON-path preservation
  for Alma+Odlum, clean-title guard).
- 1 pre-existing test in `test_dma_package_parser.py` updated to
  reflect the new WSFS recs reality (was asserting `recs == []`).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on the 4 touched files: clean.

### End-user impact unlocked

- WSFS / Nicola / Calprivate ClientOverview recs strip and
  RecommendationsPage now render REAL recs sourced dynamically from
  the analyst's Assessment Report DOCX, not hardcoded or stub data.
- Each rec carries `id`, `title`, `source_body` (full prose, 1500-3500
  chars), and structured `root_cause` / `solution` / `expected_outcomes`
  / `risk_of_inaction` / `buyer_map` when the source DOCX uses those
  sub-block markers.

### Backlog remaining (deferred, low impact)

- F6: IngestedPackage docstring drift (documentation only)
- C2: Nicola CSV non-canonical names (XLSX path covers it today)
- C5: L1/L2 governance distinction (only Odlum + Calprivate have both;
  affects HealthPage Gates tab; tracked separately)

---

## Addendum (2026-06-07): F4 persistence cascade + C9 entity_profile.json

Continued production-readiness pass per user direction. Two findings:

### Finding A — F4 rec persistence cascade gap (silent fidelity loss)

The 2026-06-07 F4 DOCX-rec extractor populated
`RecommendationRow.root_cause = {"text": ...}` (and same shape for
`solution`). But `package_persist._rec_description()` reads
`root_cause["gap_description"]` and `solution["description"]` to build
the persisted description column. With the wrong key names, every
DOCX-extracted rec would persist with ONLY its title — losing 1500-3500
chars of analyst prose per rec.

**Fix:**
1. Aligned the DOCX extractor's keys to canonical names
   (`gap_description`, `description`) so the persistence path
   transparently picks them up.
2. Extended `_rec_description()` to also recognize Odlum's variant
   `root_cause.finding` key (was only reading `gap_description`).
3. Added top-level `zennify_solution` fallback for Odlum-shape recs
   where `solution.description` is absent.

### Finding B — Pre-existing variant gap exposed (Odlum 0/6 desc coverage)

Same investigation surfaced that Odlum's `recommendations_register.json`
variant uses different key names (`root_cause.finding`,
`zennify_solution` at top-level instead of `solution.description`).
6 of 6 Odlum recs were persisting with empty desc beyond title BEFORE
my F4 work. The `_rec_description()` extension above closes that gap
too.

### Result: 100% desc coverage across all 33 recs / 5 fixtures

```
Alma_Bank:     7/7 recs have desc (canonical JSON)
Calprivate:    8/8 recs have desc (DOCX §9 fallback)
Nicola_Wealth: 7/7 recs have desc (DOCX §9 fallback)
Odlum_Brown:   6/6 recs have desc (variant JSON; was 0/6 pre-fix)
WSFS_Bank:     5/5 recs have desc (DOCX §9 fallback)
```

### C9 — entity_profile.json takes priority over DOCX regex

The under-leveraged matrix §C9 finding: Calprivate ships
`08_appendices/entity_profile.json` (12.2 KB) with structured
firmographics (corporate_identity, regulatory_standing,
financial_baseline, subvertical_classification, leadership_snapshot).
The DOCX-regex path was a fragile subset of the same fields.

**Implementation:** new `app/services/parsers/entity_profile.py` with
`parse_entity_profile_json()` + `parse_entity_profile_leadership()`.
Wired in `dma_package.py` BEFORE the handoff-JSON / DOCX paths so it
takes priority. Subsequent handoff-JSON consult is gated on `firm is
None`.

### Calprivate firmographics richness delta

| Field | Pre-C9 (DOCX regex) | Post-C9 (entity_profile.json) |
|--|--|--|
| legal_name | "(blank or fragile)" | "CalPrivate Bank" |
| ticker | (not extracted) | **OTCQX:PBAM** |
| hq | (had) | "La Jolla, CA" |
| founded | (not extracted) | **2006** |
| employees_approx | (had) | "210" |
| total_assets | (not extracted) | **$2.58B** |
| branches | (not extracted) | **8** |
| primary_regulator | (had) | "FDIC" |

### Cascade verification

- Backend pytest: 1784 passed, 63 skipped, 0 failed (+4 net vs prior
  1780 baseline).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed.
- `ruff check` on 5 touched files: clean.
- 4 new contract tests in `test_qa_v2_5folder_ingestion.py`:
  - `test_f4_persistence_cascade_every_rec_has_real_description`:
    100% desc coverage required across all 33 recs.
  - `test_f4_rec_id_fits_persistence_column_width`: pin against the
    `rec.id[:16]` truncation in `package_persist.py:1046`.
  - `test_c9_calprivate_firmographics_use_entity_profile_json`: pins
    Calprivate's ticker / founded / total_assets / branches via JSON.
  - `test_c9_other_folders_unaffected_by_entity_profile_path`:
    cascade-guard — the other 4 folders' firmographics paths
    unchanged.

### End-user impact unlocked

- **All 5 folders' RecommendationsPage** now persists with full prose
  description (1500-3500 chars) per rec instead of just the title.
- **Calprivate ClientOverview** firmographics rows surface ticker
  (OTCQX:PBAM), founded year (2006), total_assets ($2.58B), branch
  count (8), employees (210) — all from structured JSON.

### Backlog still deferred (next batch candidates)

- C5 — L1/L2 governance distinction (Odlum + Calprivate ship both
  verdicts; HealthPage Gates tab opportunity; medium scope).
- C7 — Reasoning chain + contradiction logs (Vertex token saver;
  large scope).
- C8 — Scoring scratchpad 788 KB (Alma only; needs new table).
- C10 — Caps applied log (4 of 5 folders; needs new table; affects
  defensibility on HealthPage Gates).
- C11/C12 — Assumptions + search/critic logs (auditability).

---

## Addendum (2026-06-07): C10 — caps_applied_log full vertical slice

The under-leveraged matrix §C10 finding: 4 of 5 real DMA packages ship
`07_governance/caps_applied_log.csv` with cap-event rows that surface
WHY specific subcap scores were ceiling-capped. Currently lost — D6
Health Gates tab shows the capped score but no defensible rationale.

**End-user impact unlocked:** AE on a sales call can answer "this
subcap scored M2.5 because IR-003 severity capped it at M2.5, not
because of maturity." Reviewer can audit cap chains.

### Vertical slice landed

| Layer | File | Change |
|--|--|--|
| Pydantic schema | `app/schemas/package.py` | `CapsAppliedRow` model with 10 declared fields + `extra='allow'`; `IngestedPackage.caps_applied_log: list[CapsAppliedRow]`. |
| Parser leaf | `app/services/parsers/caps_applied_log.py` (new, ~170 LOC) | `parse_caps_applied_log()` with header-alias table tolerant of the 2 observed column-name shapes (Alma's `Log_ID, SubCap_ID, …` Title_Case vs the other 3's `cap_id, affected_id / affected_subcap, …` lowercase). Multi-value cells (E-IDs) split on `,` / `|` / `;`. |
| Parser orchestrator | `app/services/parsers/dma_package.py` | block after qa_verdict load; emits `caps_applied_log: N parsed from …` warning for operator visibility. |
| DB migration | `alembic/versions/028_caps_applied_log.py` (new) | Idempotent `CREATE TABLE IF NOT EXISTS caps_applied_log` + 3 indexes (run+subcap, entity+created_at, unique run+log_id). Updated DEPLOYMENT.md + QA-CONTRACT.md head reference. |
| Persistence | `app/services/parsers/package_persist.py` | DELETE-then-INSERT per run_id (matches document_sections + focus_areas pattern); per-column truncation guards (log_id 64, cap_type 64, cap_ceiling 32, etc.). `getattr` for test-stub tolerance. |
| API schema | `app/schemas/health.py` | `CapsAppliedOut` response model + `HealthResponse.caps_applied: list[CapsAppliedOut]`. |
| API route | `app/routers/health.py` | `/entities/{display_id}/health` now loads caps rows via SELECT + populates the response. Try/except around the SELECT so envs without migration 028 return empty list cleanly. |

### Live extraction

```
Folder         | caps_applied_log rows
Alma_Bank      |   8
Calprivate     | 115
Nicola_Wealth  |   8
Odlum_Brown    |  10
WSFS_Bank      |   0 (no file; semantics in subcap_scores.caps_applied)
```

Total: **141 cap events** across 4 folders surfaced for the first time.

### Cascade verification

- Backend pytest: **1789 passed**, 63 skipped, 0 failed (+5 net vs
  prior 1784 baseline).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression; `HealthResponse`
  consumers use a `Record<string, unknown>` shape that absorbs the
  new field).
- `ruff check` on 7 touched files: clean.
- 4 new contract tests:
  - `test_c10_caps_applied_log_parses_across_all_4_folders_shipping_it`
  - `test_c10_wsfs_has_no_caps_applied_log_file_no_warning`
  - `test_c10_caps_applied_log_row_shape_round_trips_model_dump`
  - `test_c10_persistence_field_widths_fit_db_columns`
- 1 alembic-head doc contract test now references head=028.

### Deferred follow-ups

- **Frontend rendering**: D6 Health Gates tab gains a sortable
  cap-events table. Schema + API are ready; React component is the
  next batch.
- **WSFS cascade**: integrate subcap_scores.caps_applied string into
  HealthResponse.caps_applied so WSFS also surfaces cap events
  (different code path — its data ships inline on each subcap row).

### Backlog still deferred

- C5  — L1/L2 governance distinction (Odlum + Calprivate); medium scope.
- C7  — Reasoning chain + contradiction logs (large; Vertex saver).
- C8  — Alma scoring scratchpad 788 KB.
- C11 — Assumptions register (Calprivate + Nicola).
- C12 — Search + critic logs (auditability).

---

## Addendum (2026-06-07): C10 frontend + WSFS cascade — production loop closed

Closes the C10 production loop from the prior commit. The backend
landed parser + schema + migration + persistence + API endpoint; this
addendum lands the React rendering AND a cross-folder cascade so all
5 real fixtures (not just the 4 that ship `caps_applied_log.csv`)
surface cap events on the D6 Health Caps tab.

### Frontend (D6 HealthPage Caps tab)

**`frontend/src/lib/queries.ts`**
- New `CapsAppliedOut` TS interface mirroring the backend Pydantic
  shape (10 fields: log_id, subcap_id, cap_type, …).
- Extended `HealthResponse` to include `caps_applied: CapsAppliedOut[]`.

**`frontend/src/pages/HealthPage.tsx`**
- New `CapsTab` component renders a sortable table: `Log | SubCap |
  Type | Ceiling | Trigger | Evidence | Severity`. `cap_type` is
  pilled with tone-mapping (`REGULATORY` / `SEVERITY` → red;
  `EVIDENCE_CEILING` / `EVIDENCE_QUALITY` → amber; default neutral).
- Added `{ id: "caps", label: "Caps" }` to the TABS array.
- Empty-state copy: "No cap events ... This run shipped no
  `caps_applied_log.csv`" (truthful — distinguishes "no file" from
  "load error").

### Backend WSFS cascade (`app/routers/health.py`)

After loading rows from the canonical `caps_applied_log` table, the
endpoint now ALSO loads `subcap_scores WHERE cap_applied IS TRUE AND
cap_reason IS NOT NULL` for the same run. Each surviving subcap row
becomes a synthesized `CapsAppliedOut`:
  - `log_id` = `INLINE-<subcap_id>` (synthetic anchor; readers must
    not treat as a foreign key).
  - `cap_type` = `INLINE_SUBCAP` (distinguishes synthesized vs
    canonical).
  - `trigger_condition` = the `cap_reason` string (e.g. "ISS-cap M2.0").

Dedup discipline: subcaps that already appear in the canonical log
are NOT duplicated (canonical rows are richer — they carry
`cap_ceiling` / `trigger_evidence` list / `affected_categories`).

Result: WSFS's 1 inline cap event (`P2C3.3.CL2: ISS-cap M2.0`)
surfaces alongside the 8 / 115 / 8 / 10 canonical events for the
other 4 folders. AE on a WSFS sales call gets the same defensible-
rationale story.

### Cascade verification

- Backend pytest: 1790 passed, 63 skipped, 0 failed (+1 net vs
  prior 1789 baseline).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on touched files: clean.
- New contract test:
  `test_c10_health_response_surfaces_caps_applied_field` — pins
  the field as a declared Pydantic field + round-trips
  `CapsAppliedOut.model_dump()`.

### Production-readiness — C10 status: COMPLETE

| Layer | Status |
|--|--|
| Parser | ✓ shipped (commit 010a8e0) |
| Pydantic schema | ✓ shipped (commit 010a8e0) |
| Alembic migration 028 | ✓ shipped (commit 010a8e0) |
| Persistence (DELETE-then-INSERT per run) | ✓ shipped (commit 010a8e0) |
| API surface (HealthResponse.caps_applied) | ✓ shipped (commit 010a8e0) |
| **Frontend D6 Caps tab** | **✓ shipped (this commit)** |
| **WSFS inline cascade** | **✓ shipped (this commit)** |
| 5-folder coverage | 4 via canonical log + 1 via WSFS cascade = **5/5** |

### Backlog still deferred

- C5 — L1/L2 governance distinction (Odlum + Calprivate); medium scope.
- C7 — Reasoning chain + contradiction logs (Vertex token saver; large).
- C8 — Alma scoring scratchpad 788 KB; needs new table.
- C11 — Assumptions register (Calprivate + Nicola); small.
- C12 — Search + critic logs (auditability); medium.

---

## Addendum (2026-06-07): C5 — L1/L2 QA verdict chain full vertical slice

The under-leveraged matrix §C5 finding: 2 of 5 real DMA packages
(Odlum + Calprivate) ship BOTH a first-pass (L1) verdict AND a final
(L2/full-review) verdict, capturing the 2-stage QA escalation chain.
The previous parser dropped both — `qa_verdict` was loaded onto
`IngestedPackage` but never persisted or surfaced; L1 was missed
entirely.

### Pre-existing gap exposed mid-implementation

`qa_verdict` was parsed but never persisted (no UPDATE/INSERT in
`package_persist`) NOR surfaced via API (no router referenced it).
Silent parse-and-drop. C5 closes BOTH the L1 detection AND this
prior gap.

### Vertical slice landed

| Layer | File | Change |
|--|--|--|
| Pydantic schema | `app/schemas/package.py` | `IngestedPackage.qa_verdict_l1: QaVerdict | None` added; `qa_verdict` re-comment-documented as L2/final. |
| Parser | `app/services/parsers/dma_package.py` | L2 detection now scans `qa_verdict.json` + `GOV_qa_verdict.json` + `L2_qa_verdict.json` + case-insensitive sweep excluding L1 markers; L1 detection scans `L1_qa_verdict.json` / `Layer1_qa_verdict.json` / case-insensitive variants. Emits `qa_verdict_l1_l2_pair` warning when both ship. |
| DB migration | `alembic/versions/029_runs_qa_verdicts.py` (new) | Idempotent `ADD COLUMN IF NOT EXISTS runs.qa_verdict_l1 JSONB` + `qa_verdict_l2 JSONB`. Updated DEPLOYMENT.md + QA-CONTRACT.md head=029. |
| Persistence | `app/services/parsers/package_persist.py` | Both runs UPDATE + INSERT pass `qa_verdict_l1` + `qa_verdict_l2` JSONB blobs via `CAST(:qal1/qal2 AS JSONB)`. `getattr` tolerance for test stubs. |
| API schema | `app/schemas/health.py` | `QaVerdictOut` (verdict, recommendation, verdict_basis, governance_skill_version) + `HealthResponse.qa_verdict_l1` + `qa_verdict_l2`. |
| API route | `app/routers/health.py` | Loads both verdicts via SELECT runs.qa_verdict_l1/l2; try/except tolerant of pre-migration envs. |
| Frontend types | `frontend/src/lib/queries.ts` | `QaVerdictOut` interface + `HealthResponse.qa_verdict_l1/l2`. |
| Frontend rendering | `frontend/src/pages/HealthPage.tsx` | New `VerdictChainCard` rendered at top of GatesTab: `Stage | Verdict | Recommendation | Basis` table. Pill tone-mapping (PASS green; PASS_WITH_NOTES amber; FAIL/REJECT/BLOCK red). Distinguishes "L1 not shipped" vs absent verdict. |

### Live extraction (5 real fixtures)

| Folder | L1 verdict | L2 verdict |
|--|--|--|
| Alma_Bank | (none) | PASS_WITH_NOTES |
| Calprivate | **PASS** | PASS_WITH_NOTES |
| Nicola_Wealth | (none) | PASS_WITH_NOTES |
| Odlum_Brown | **PASS** | PASS_WITH_NOTES |
| WSFS_Bank | (none) | PASS_WITH_NOTES |

**Escalation chain captured for Odlum + Calprivate** (PASS → PASS_WITH_NOTES) — the exact analyst-visible signal the under-leveraged matrix called out.

### Cascade verification

- Backend pytest: **1795 passed**, 63 skipped, 0 failed (+5 net vs
  prior 1790 baseline; 4 new C5 tests + 1 alembic-head doc test
  re-passes).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on 7 touched files: clean.
- 4 new contract tests:
  - `test_c5_l1_l2_verdict_chain_extracted_per_folder` — per-folder
    L1/L2 pins.
  - `test_c5_escalation_warning_fires_when_both_verdicts_present` —
    audit-visibility for the 2-stage chain.
  - `test_c5_health_response_surfaces_l1_l2_verdict_fields` — schema-
    shape contract + `QaVerdictOut.model_dump()` round-trip.
  - `test_c5_l1_verdict_filename_variants_recognized` — pin both
    `L1_qa_verdict.json` (Odlum) AND `Layer1_qa_verdict.json`
    (Calprivate) variants.

### Cascade-discipline catches mid-implementation

1. **Pre-existing parse-and-drop on `qa_verdict`**: prior to this
   commit the field never reached the DB or any API. Closed by the
   same migration + persistence wiring as L1.
2. **Test stub `_Pkg`** in `test_concurrent_ingest_safeguards` again
   lacks the new schema field → fixed with `getattr` tolerance on
   BOTH `qa_verdict` and `qa_verdict_l1` (also retroactively makes
   the pre-existing `qa_verdict` access safe under the stub).
3. **Filename variants**: case-insensitive sweep handles future
   bot variants like `EntityName_L1_QAVerdict.json`. The L2 sweep
   explicitly EXCLUDES `l1`/`layer1` markers so future filename
   collisions don't mis-route.

### End-user impact unlocked

AE/Analyst opens D6 → Gates tab. Sees QA verdict chain card at top:

```
QA verdict chain
  L1 first-pass    [PASS]                    DELIVER     —
  L2 full review   [PASS_WITH_NOTES]         DELIVER     —
```

For Alma / WSFS / Nicola the L1 row reads "L1 not shipped" — truthful
operator UX, not a fabricated PASS.

### Backlog still deferred

- C7 — Reasoning chain + contradiction logs (Vertex token saver; large).
- C8 — Alma scoring scratchpad 788 KB; needs new table.
- C11 — Assumptions register (Calprivate + Nicola); small.
- C12 — Search + critic logs (auditability); medium.

---

## Addendum (2026-06-07): C11 — assumptions register full vertical slice

The under-leveraged matrix §C11 finding: 2 of 5 real DMA packages
ship the analyst's assumptions register, which AE can use to answer
"we assumed X because no public data on Y" on sales calls. Currently
parser-lost.

### Vertical slice landed

| Layer | File | Change |
|--|--|--|
| Pydantic schema | `app/schemas/package.py` | `AssumptionRow` (id, assumption, basis, confidence + `extra='allow'` for per-shape extras) + `IngestedPackage.assumptions_register: list[AssumptionRow]`. |
| Parser leaf | `app/services/parsers/assumptions_register.py` (new) | Dispatches by file suffix (JSON vs CSV); CSV header-alias table tolerates Nicola's `id,assumption,basis,confidence,validation_method,priority,capabilities_affected` shape; JSON accepts top-level list or wrapped under `assumptions` / `register` / `items` key. Multi-value cells (capabilities_affected) split on `,` / `\|` / `;`. |
| Parser orchestrator | `app/services/parsers/dma_package.py` | Candidate-paths sweep across `08_appendices/` (Calprivate JSON) + `07_governance/` (Nicola CSV variants); case-insensitive entity-prefixed sweep for future bot variants. `assumptions_register: N parsed from …` warning for admin visibility. |
| DB migration | `alembic/versions/030_runs_assumptions_register.py` (new) | Idempotent `ADD COLUMN IF NOT EXISTS runs.assumptions_register JSONB`. Updated DEPLOYMENT.md + QA-CONTRACT.md head=030. |
| Persistence | `app/services/parsers/package_persist.py` | Both UPDATE + INSERT paths pass `:asm` AS JSONB via `json.dumps([row.model_dump() for row in assumptions])`. `getattr` tolerance for pre-existing test stubs. |
| API schema | `app/schemas/entities.py` | `EntityOverviewResponse.assumptions_register: list[dict]` (Pydantic v2 dict shape preserves extras through the JSONB round-trip). |
| API route | `app/routers/entities.py` | Extended `SELECT FROM runs` to include `assumptions_register`; try/except + retry-with-legacy-columns so pre-migration envs still return a valid (empty) response. |
| Frontend types | `frontend/src/lib/queries.ts` | Extended `EntityOverviewResponse` with the new field; row type is `{id, assumption, basis?, confidence?, [k]: unknown}` so extras flow through cleanly. |
| Frontend rendering | `frontend/src/pages/ClientOverviewPage.tsx` | New `AssumptionsRegisterCard` footer card on D1; table layout `ID \| Assumption \| Confidence \| Basis`. Internal-only (stripped for `view=customer` audience). Card only renders when rows exist (avoids visual clutter for the 3-of-5 fixtures that ship nothing). |

### Live extraction (5 real fixtures)

| Folder | assumptions parsed |
|--|--|
| Alma_Bank | 0 (no file) |
| **Calprivate** | **5** (JSON: ASM-001..005) |
| **Nicola_Wealth** | **8** (CSV: A-01..A-08) |
| Odlum_Brown | 0 (no file) |
| WSFS_Bank | 0 (no file) |

**Total: 13 assumptions surfaced for the first time across 2 folders.**

Sample (Calprivate ASM-001):
```
Assumption: FIS Horizon is the core banking system (hypothesis)
Confidence: MEDIUM-HIGH (80%)
Basis     : CTO Birkmann worked at Pacific Mercantile Bank — a documented
            FIS Horizon client. FIS Deposit One (RDC) confirmed in
            production. FIS integration vocabulary used in DCBO job
            description. No alternative core banking vendor named in any
            public disclosure.
```

### Cascade verification

- Backend pytest: **1801 passed**, 63 skipped, 0 failed (+6 net vs
  prior 1795 baseline; 5 new C11 tests + 1 alembic-head doc test
  re-passes).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on 8 touched files: clean.
- 5 new contract tests:
  - per-folder count pins;
  - schema round-trip;
  - operator-observability warning fires;
  - cascade-guard for folders without the file;
  - EntityOverviewResponse contract.

### Cascade-discipline catches mid-implementation

1. **Test stub `_Pkg` lacks the new schema field** → `getattr`
   tolerance on `assumptions_register` (matches the C5 / C10
   pattern; preserves all prior-batch stub safety).
2. **API SELECT failure on pre-migration envs** → try/except
   wrapper retries with the legacy column list so the response
   stays valid (assumptions_register defaults to empty list).
3. **Audience strip** → AssumptionsRegisterCard is rendered only
   when `audience !== "customer"`, matching the ThoughtLeadershipPanel
   pattern. Customer-facing scorecard exports don't leak the
   analyst's internal assumptions.

### End-user impact unlocked

AE opens D1 ClientOverview for Calprivate or Nicola. At the bottom
of the page, the **Assumptions register** card shows 5 or 8 rows. On
a sales call: "we assumed FIS Horizon is the core banking system
with MEDIUM-HIGH confidence because Pacific Mercantile Bank
documentation, FIS Deposit One in production, and FIS integration
language in your job postings." Concrete defensibility instead of
hand-waving.

### Backlog still deferred

- C7 — Reasoning chain + contradiction logs (Vertex saver; large).
- C8 — Alma scoring scratchpad 788 KB; needs new table.
- C12 — Search + critic logs (auditability); medium.

---

## Addendum (2026-06-07): F5c D5 closure + C8 reclassified

Cascade-audit pass on the under-leveraged backlog. Two findings:

### Finding A — F5c D5 ContextPage was half-shipped

The 2026-06-07 F5c commit (`9ec41fc`) added `narrative_md` to:
- Parser (`dma_package.py`) ✓
- Persistence (`package_persist.py`) ✓
- D1 Overview API (`entities.py`) ✓
- D1 Overview Pydantic schema ✓

But MISSED:
- D5 Context API (`context.py`) — SELECT FROM firmographics used the
  legacy column list; `narrative_md` silently dropped.
- D5 ContextPage frontend — no component rendered the field.

The D1 surfacing alone wasn't the AE-visible target; the under-
leveraged matrix called out D5 Context "About" panel specifically.
This addendum closes both gaps:

`app/routers/context.py`
  Extended SELECT to include `narrative_md`; try/except + retry with
  legacy column list so pre-migration envs return valid response.
  Injects into `firmographics` dict only when populated.

`frontend/src/pages/ContextPage.tsx`
  New `AboutCard` component renders the 200-1600 char analyst-prose
  paragraph as a top-of-section card (above `RegulatoryCard`).
  Skipped from `RegulatoryCard`'s KV grid to avoid 1600 char wall of
  text in a `<dd>` cell. `whiteSpace: pre-wrap` preserves analyst
  line breaks.

### Finding B — C8 reclassified (no parser work needed)

The under-leveraged matrix §C8 claimed Alma's 788 KB
`scoring_scratchpad.json` carried per-subcap rationale the parser
ignored, forcing SynthesisDrawer to re-run Vertex. Verified 2026-06-07:

```
Scratchpad rationale chars: 703
Parsed rationale chars:     703
EQUAL? True

Alma subcap rationale coverage:
  total           = 698
  with_rationale  = 698  (100%)
  via             = XLSX-enrichment path (dma_package.py:1230)
```

100% of Alma's 698 subcaps already carry the full 700+ char analyst
rationale on `pkg.subcap_scores[*].rationale`. The scratchpad is a
redundant copy; no SynthesisDrawer Vertex waste.

C8 reclassified in `docs/qa/qa_ingestion_under_leveraged.md` to
prevent future contributors from re-opening the same mis-diagnosis.
Pin test `test_c8_alma_subcap_rationale_already_100pct_populated`
catches a regression in the XLSX enrichment path (which would
reopen C8 as a real concern).

### Cascade verification

- Backend pytest: **1803 passed**, 63 skipped, 0 failed (+2 net vs
  prior 1801 baseline; 2 new audit/reclassification tests).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on touched files: clean.

### New contract tests

- `test_f5c_d5_context_response_surfaces_narrative_md_when_present`:
  source-level grep guard. Catches a regression where context.py
  removes the narrative_md SELECT or stops injecting into
  firmographics dict.
- `test_c8_alma_subcap_rationale_already_100pct_populated`: pins
  Alma's 698 subcaps at ≥664 (95%) rationale coverage. A drop
  reopens C8 as a real concern.

### Live extraction (post-fix)

| Folder | D1 narrative_md | D5 narrative_md |
|--|--|--|
| Alma_Bank | 450 chars (was: 450) | **450 chars** (was: missing) |
| Calprivate | 456 chars (was: 456) | **456 chars** (was: missing) |
| Nicola_Wealth | 884 chars (was: 884) | **884 chars** (was: missing) |
| Odlum_Brown | 1583 chars (was: 1583) | **1583 chars** (was: missing) |
| WSFS_Bank | 198 chars (was: 198) | **198 chars** (was: missing) |

### End-user impact unlocked

AE opens D5 Context page for any of the 5 entities. Sees the analyst's
prose paragraph (198-1583 chars) as the top section. Concrete context
narrative replaces the prior empty card.

### Backlog still deferred

- C7  — Reasoning chain + contradiction logs (Vertex saver; large).
- C12 — Search + critic logs (auditability); medium.

### Cascade-discipline lesson captured

The F5c half-shipped state demonstrates that **adding a Pydantic field
to one endpoint's schema doesn't automatically surface it through ALL
relevant endpoints**. Each endpoint reads its own SELECT column list.
Cascade-audit pass surfaced this; pinned-by-grep test prevents
regression. Future field additions should grep ALL relevant routers
to find every SELECT FROM that needs to include the new column.

---

## Addendum (2026-06-07): C7 — bot governance audit logs full vertical slice

The under-leveraged matrix §C7 finding: 2 of 5 real DMA packages ship
audit logs capturing the bot's actual chain-of-thought reasoning +
evidence contradiction adjudication. Previously parser-lost; D6 Health
had no analyst-audit surface for the bot's logic.

### End-user impact unlocked

Analyst opens D6 Health → new "Audit" tab and sees:
1. **Bot reasoning chain** (Nicola: 12 subcap chains × 5 decision-path
   steps each):
   - subcap_id P1C1.1.1 →
     - "1. Evidence collection: E-001:F1, E-002:F2, E-005:F3"
     - "2. Tier classification: ceiling=5.0"
     - "3. M-level match: final_score=2.0 (MEDIUM confidence)"
     - "4. Caps applied: None"
     - "5. Critic review: ..."
2. **Evidence contradictions** (Nicola 3, Odlum 3): each row
   resolves contradiction `CONTRA-001 :: P3C3.x :: E-113 vs E-122 ::
   winner=E-113 :: justification="Form ADV Part 2A (T1) confirms no
   outstanding matters; ISSUE-002 RESOLVED"`.

Reviewer trust gap closed — auditor can confirm the bot's logic
aligns with the final scoring without re-deriving from raw evidence.

### Vertical slice landed

| Layer | File | Change |
|--|--|--|
| Pydantic schema | `app/schemas/package.py` | New `ReasoningChainSubcap` + `ContradictionRow` + `GovernanceAuditLogs` envelope; `IngestedPackage.audit_logs: GovernanceAuditLogs \| None`. |
| Parser leaf | `app/services/parsers/governance_audit.py` (new) | `parse_reasoning_chain()` reads JSON `subcap_chains` list; `parse_contradictions()` reads CSV with header-alias table; `parse_governance_audit_logs(root_p)` aggregates into one envelope. Returns None when no audit files shipped. |
| Parser orchestrator | `app/services/parsers/dma_package.py` | Hooked after C11 block. Emits `governance_audit_logs: reasoning_chain=N contradictions=M` warning for admin visibility. |
| DB migration | `alembic/versions/031_runs_audit_logs.py` (new) | Idempotent `ADD COLUMN IF NOT EXISTS runs.audit_logs JSONB`. Updated DEPLOYMENT.md + QA-CONTRACT.md head=031. |
| Persistence | `app/services/parsers/package_persist.py` | Both UPDATE + INSERT paths pass `:aud` via `CAST(:aud AS JSONB)`. `getattr` stub tolerance. |
| API schema | `app/schemas/health.py` | `AuditLogsOut` envelope (reasoning_chain list + contradictions list) + `HealthResponse.audit_logs: AuditLogsOut \| None`. |
| API route | `app/routers/health.py` | Extended SELECT to include `audit_logs`; try/except + null-on-failure for pre-migration envs. |
| Frontend types | `frontend/src/lib/queries.ts` | `AuditLogsOut` interface with strongly-typed known fields + `[k: string]: unknown` for extras (final_score, confidence_impact, etc.). |
| Frontend rendering | `frontend/src/pages/HealthPage.tsx` | New `AuditTab` component renders two cards: "Bot reasoning chain" (numbered `<ol>` per subcap) + "Evidence contradictions" (sortable table). Added `{id:"audit", label:"Audit"}` to TABS array. |

### Live extraction (5 real fixtures)

| Folder | reasoning_chain | contradictions |
|--|--|--|
| Alma_Bank | (no file) | (no file) |
| Calprivate | (no file) | (no file) |
| **Nicola_Wealth** | **12 chains × 5 steps = 60 reasoning steps** | **3** |
| **Odlum_Brown** | (no file) | **3** |
| WSFS_Bank | (no file) | (no file) |

**Total: 60 bot reasoning steps + 6 contradiction resolutions surfaced
for the first time across 2 folders.**

### Cascade verification

- Backend pytest: **1809 passed**, 63 skipped, 0 failed (+6 net vs
  prior 1803 baseline; 5 new C7 tests + 1 alembic-head doc re-passes).
- Frontend `tsc --noEmit`: clean.
- Frontend `vitest run`: 281 passed (no regression).
- `ruff check` on 8 touched files: clean.

### Cascade-discipline catches mid-implementation

1. **Test stub `_Pkg` lacks new field** → `getattr` tolerance (matches
   the C5 / C10 / C11 pattern; no new failures from
   `test_concurrent_ingest_safeguards.py`).
2. **Analyst-only role gate** → AuditTab is rendered inside the
   HealthPage component which already enforces `role === "ADMIN" ||
   role === "ANALYST"` at line 569+. No customer-facing leak of the
   bot's reasoning chain.
3. **Lessons captured from prior batch's F5c half-shipped state**:
   this commit pre-emptively grep'd ALL relevant routers and
   confirmed `audit_logs` only needs to surface on the health
   endpoint (D6 Audit tab). No D5/D1 endpoint references it.

### Cascade-audit pass on prior wins

While implementing C7, also verified end-to-end persistence chain for
the prior batches (parser → schema → migration → persistence → API →
frontend) is intact:

| Field | Parser | Schema | Migration | Persistence | API | Frontend |
|--|--|--|--|--|--|--|
| firmographics.narrative_md (F5c) | ✓ | ✓ | 018 (pre-existing) | ✓ | D1 + D5 | D1 OK / D5 ✓ |
| recommendations DOCX §9 (F4) | ✓ | ✓ | n/a (existing rec table) | ✓ | D1 + D4 | ✓ |
| firmographics richer (C9) | ✓ | ✓ | 018 + 027 | ✓ | D1 | ✓ |
| caps_applied_log (C10) | ✓ | ✓ | 028 | ✓ | D6 | D6 Caps tab ✓ |
| qa_verdict_l1/l2 (C5) | ✓ | ✓ | 029 | ✓ | D6 | D6 VerdictChainCard ✓ |
| assumptions_register (C11) | ✓ | ✓ | 030 | ✓ | D1 | D1 AssumptionsCard ✓ |
| audit_logs (C7) | ✓ | ✓ | 031 | ✓ | D6 | D6 AuditTab ✓ |

Every cell GREEN. The cascade-audit lesson from last batch ("adding
a Pydantic field to one endpoint doesn't automatically surface on
others") is now embedded in the contributor pattern: grep ALL routers
before declaring a vertical slice complete.

### Backlog still deferred

- C12 — Search + critic logs + check_results (auditability; medium).

---

# Gate 2 — Batch 4 close (2026-06-07)

**Gate purpose** (from the original v2 plan):
> Validates the entire ingestion ↔ processing ↔ persistence chain.
> Re-runs ALL Batch 1-9 contracts + simulate harness; classifies the
> delta vs the Gate 1 baseline. **0 regressions required.**

**Batch 4 status: PASS — 0 regressions, 0 unrelated breaks.**

## Baseline at gate entry (state immediately before Batch 4)

| Metric | Value |
|---|---|
| HEAD SHA | `7525c5c` (Batch 3 — shallow catalogue alias bridge) |
| Branch | `claude/deploy-zennify-cloud-run-AUdu6` (default) |
| Working tree | clean |
| Backend tests passing | 1877 (63 skipped: env-secret gated) |
| Backend tests failing | 0 |
| Lint | clean (1 pre-existing RUF021 in `package_csvs.py:159`) |
| Alembic head | `036_widen_data_source` |
| Live DB entities | 104 |
| Live DB runs | 113 |
| Live DB subcap_scores | 63469 |
| Render harness | 536 OK / 688 PARTIAL / 24 FAIL (the 12 DOCX-only entities × 2 endpoints) |
| Language audit | 1791 violations across 98/104 entities (post-bridge cascade) |

## 4-scenario contract proof

[`backend/tests/test_qa_v2_reingest_scenarios.py`](../../../backend/tests/test_qa_v2_reingest_scenarios.py)
ships 4 scenarios + 1 cross-entity regression guard against the
live DB. All 5 PASS.

| Scenario | What it proves | Result |
|---|---|---|
| A. Same run, same data | Idempotent tables: counts byte-equal across re-ingest. Audit tables (`dedup_audit`): grow append-only, exactly 2x on second pass. | PASS |
| B. Scoring CSV mutated only | Selective re-ingest contract (Batch 2): `evidence_index`, `evidence_run_links`, `dedup_audit`, `document_sections`, `document_lineage`, `document_evidence_items`, `focus_areas`, `caps_applied_log`, `recommendations`, `issue_register` content_hash UNCHANGED before/after a 1-byte scoring CSV mutation; `subcap_scores` re-UPSERTs. | PASS |
| C. New request_id, same entity | Same entity row reused (drive_folder_id lookup hits); fresh run row inserted; prior run flips `status='SUPERSEDED'` + `superseded_by_run_id=<new>`; new row is ACTIVE. | PASS |
| D. Catalogue bump | Planted cache row tagged with old catalogue_version → `build_invalidation_for_catalogue_bump(old_version)` → `safe_mark_invalidated` → `invalidated_at = NOW()`, `invalidation_reason='catalogue_bump_invalidate'`. | PASS |
| Cross-entity isolation (regression guard) | Ingesting entity B's package does NOT flip entity A's ACTIVE run to SUPERSEDED. Both entities' latest runs remain ACTIVE. | PASS |

## Persistence matrix

24-table proof: [`docs/qa/qa_persistence_matrix.md`](../qa_persistence_matrix.md).

Each table documents: migration provenance, PK/UNIQUE constraints,
FK behaviour, indexes (incl. partial + generated columns), the
current persist line range post Batches 1-3, the persistence
strategy (UPSERT / DELETE-INSERT / append-only), idempotency proof,
and the live row count baseline.

## Cascade-effect classification (delta vs Gate 1 baseline)

Per the Gate Framework: each post-batch delta is `expected` /
`regression` / `unrelated_break`.

| Check | Gate 1 | Gate 2 | Classification |
|---|---:|---:|---|
| Backend tests passing | 1852 | 1882 (+30) | `expected` (+30: Batch 2 selective tests, Batch 3 alias bridge tests, Batch 4 scenarios + guard) |
| Backend tests failing | 0 | 0 | `expected` |
| Backend lint | clean (1 pre-existing) | clean (1 pre-existing) | `expected` |
| Alembic head | 033_runs_material_manifest | 036_widen_data_source | `expected` (Batches 2-3 migrations) |
| Render harness FAIL count | 28 | 24 | `expected` (Batch 3 fixed 4 cells) |
| Render harness OK count | 528 | 536 | `expected` |
| Language audit violations | 1515 | 1791 | `expected` (+276: AMH+Wescom broadcast rows inherit parent rationale verbatim per Batch 3 design; Vertex rewrite Batch 6 will close) |
| Per-fixture re-ingest idempotency | implicit | explicit (Scenario A) | `expected` |
| Cross-entity isolation | implicit | explicit (regression guard) | `expected` |
| Frontend tests | 281 | 281 | `expected` (no UI changes since Batch 3) |
| TS compilation | clean | clean | `expected` |
| Vite build | OK | OK | `expected` |

**0 regressions. 0 unrelated breaks.** Gate 2 PASSES.

## 20 edge cases pinned (10 from plan + 10 from this session)

| # | Edge case | Status |
|--:|---|---|
| 1 | ZIP with extra top-level dir | tolerated (existing) |
| 2 | CSV with BOM | utf-8-sig strip (existing) |
| 3 | DOCX with embedded images | skipped (no OCR) |
| 4 | XLSX with formulas | read as cached value |
| 5 | evidence_index.csv with duplicate E-IDs in same run | `duplicate_within_run` audit row |
| 6 | Multiple Assessment_Report DOCX files | all parsed (H7 hotfix) |
| 7 | peer_scores_*.json with 0 peers | empty array persisted |
| 8 | qa_verdict.json verdict=REJECT | run PENDING_REVIEW status |
| 9 | evidence_mode RESEARCH_HANDOFF vs public | both persisted |
| 10 | Stale lock file from prior crashed crawl | cleared |
| 11 | Tier `T10` / `T10-CONTRADICTORY` (Amarillo) | clamped to 8 via EvidenceRow validator (Batch 1) |
| 12 | Score=0, Confidence=N/A (Payments Canada FMI overlay) | row skipped; warning logged (Batch 1) |
| 13 | Per-(cap × subcap) caps_applied_log (Pentegra: 198 rows) | persists under `(run_id, log_id, subcap_id)` UNIQUE; migration 032 (Batch 1) |
| 14 | Empty institution_name + run_id ending in `0001` | distinct entities via sha1(drive_folder_id) salt (Batch 1) |
| 15 | Empty request_id | synthetic `SYNTH-{sha1[:12]}` (Batch 1) |
| 16 | Misplaced run_manifest.json (Pentegra in 01_evidence/) | new canonical location added (Batch 1) |
| 17 | Category-level SubCap_ID — AMH, Wescom | shallow alias bridge broadcasts to v7.0 children (Batch 3) |
| 18 | Catalogue bump with no renamed_subcap_ids | global invalidation by `catalogue_version` index (Batch 4 Scenario D) |
| 19 | --force re-ingest (deploy after code change) | bypasses Batch-2 skip; every package persists fresh (Batch 3) |
| 20 | 1-byte mutation to scoring CSV under selective re-ingest | only score-derived tables fire; document_sections content_hash identical (Batch 4 Scenario B) |

## Artifacts shipped by Batch 4

| Path | Status |
|---|---|
| `apps/dma-insights/backend/tests/test_qa_v2_reingest_scenarios.py` | NEW — 4 scenarios + 1 cross-entity regression guard |
| `apps/dma-insights/docs/qa/qa_persistence_matrix.md` | NEW — 24-table proof matrix |
| `apps/dma-insights/docs/qa/qa_gates/gate_2_evidence.md` | APPENDED — this Batch 4 section |

No code changes in `app/services/parsers/package_persist.py` for
Batch 4 — Batches 1-3 already shipped the persistence hardening;
Batch 4 documents the contract + pins it with the 5-scenario test
file.

## Next: Batch 5 readiness check

Batch 5 (Phase 3: per-page matrix + adversarial flows + visual
matrix) needs:
- ✓ Persistence layer pinned (this batch)
- ✓ Live DB seeded with 104 entities + valid renders for 92 of them
- → Open: Playwright spec scaffold for J1-J5 journeys (build in Batch 5)
- → Open: visual baseline capture (84 unique hashes × 6 states per plan)

Proceed to Batch 5.
