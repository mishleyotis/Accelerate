# ADR 0015 — Parser must accept variant shapes seen in all 5 real DMA samples

Date: 2026-05-28
Status: Accepted (closes the 2026-05-28 audit Agent 1 + Agent 3 register)

## Context

The 2026-05-28 audit pass uploaded 5 real DMA sample zips and ran the
existing `parse_package` orchestrator against each. Baseline result:

| Sample | status | sub | ev | rec | peer | iss | tch | inst | issue |
|---|---|---|---|---|---|---|---|---|---|
| Alma | OK | 698 | 105 | 7 | 5 | 9 | 33 | "Alma Bank" | reference |
| Calprivate | OK | 698 | 125 | 0 | 5 | **0** | **0** | **""** | manifest/issue/tech variants missed |
| Nicola | **FAIL** | — | — | — | — | — | — | — | `ValueError: no run manifest` |
| Odlum | OK | 709 | 127 | 0 | 4 | **0** | **0** | **""** | manifest/recs/tech variants missed |
| WSFS | OK | 708 | 106 | 0 | 4 | 7 | 25 | "WSFS Financial" | reference |

Two are reference (Alma + WSFS); three exposed P0/P1 parser variant
gaps with concrete data shapes that the n8n pipeline emits in
production. Without this ADR's fixes, the live deploy would fail to
ingest 3 of the 5 real samples — a P0 release blocker.

## Decisions

### Decision A — `parse_run_manifest` accepts the full real-sample key alias set

The run manifest's institution name appears under any of these keys
across the 5 samples:

| Sample | Key used |
|---|---|
| Alma | `institution_name` (canonical) |
| WSFS | `entity` |
| Odlum | `institution` |
| Calprivate | `entity_name` (+ `entity_legal_name` fallback) |
| Nicola | (no manifest — see Decision B) |

`package_json.parse_run_manifest` now reads them in priority order:
`institution_name → entity → institution → entity_name → entity_legal_name`.

### Decision B — synthesize run_manifest from research_handoff when none exists

Nicola Wealth ships with no `run_manifest.json` anywhere AND its
export CSVs lack the `# run_id:` header comment that the original
`_synthesize_run_manifest_from_exports` falls back to. The orchestrator
gains a new synthesis path `_synthesize_run_manifest_from_handoff` that:

1. Globs `02_research_workbook/*research_handoff*.json`,
   `07_governance/research_handoff.json`, and `08_appendices/*research_handoff*.json`.
2. Reads `assessment_id` as the run_id.
3. Reads `entity.legal_name` (or top-level `entity_name` /
   `institution_name`) as institution_name.
4. Reads `parameter_lock.rubric_version` + `parameter_lock.skill_version`.
5. Falls back to a deterministic SHA1-derived run_id when the handoff
   lacks `assessment_id`, so re-ingest is idempotent.

Synthesis ordering in `parse_package`:
1. Canonical `run_manifest.json` at any of 5 known paths.
2. Glob fallback for `*run_manifest*.json`.
3. Variant glob for `qa_verdict.json` / `audit_summary.json`.
4. Synthesize from `MANIFEST.json` (if present).
5. **NEW:** Synthesize from `*research_handoff*.json` (Nicola path).
6. Synthesize from export CSV `# run_id:` header (Regions path).

Every synthesis path emits a structured `parser_warning` so the
operator sees which fallback fired.

### Decision C — Issue register variant discovery covers all real-sample filenames

The 5 samples ship issue registers under 7 distinct filenames:

| Sample | Path |
|---|---|
| Alma | `07_governance/issue_register.csv` (canonical) |
| WSFS | `07_governance/issue_register.csv` (canonical) |
| Calprivate | `07_governance/GOV_issue_register.csv` + `08_appendices/A8_Issue_Register.csv` |
| Odlum | `07_governance/L2_issue_register.csv` |
| Nicola | `07_governance/A7_Issue_Register.csv` + `NicolaWealth_L2_IssueRegister.csv` + `03_scoring_workbook/export_issue_register.csv` |

The orchestrator now scans `07_governance/`, `08_appendices/`, AND
`03_scoring_workbook/` against 8 filename glob patterns. First
non-empty wins; the variant name surfaces as a warning.

### Decision D — Tech stack workbook discovery + sheet selection covers variants

Three orthogonal variants observed:

| Sample | Filename | First sheet | Tech sheet | Vendor column |
|---|---|---|---|---|
| Alma | `*_Explorium_Tech_Stack.xlsx` | `*_Tech_Stack` | first | `Vendor` |
| WSFS | `*_Explorium_Tech_Stack.xlsx` | `WSFS_Tech_Stack` | first | `Vendor` |
| Calprivate | `*_Technographic_Stack_Explorium.xlsx` | `Confirmed_Tech_Stack` | first | `Vendor / Product` (combined) |
| Odlum | `*_Explorium_TechStack.xlsx` (no underscore) | `Explorium_Match` (NOT tech) | `Confirmed_Tech_Stack` | `Technology` |
| Nicola | `*_Explorium_TechStack_Evidence.xlsx` | `Confirmed_Tech_Stack` (with preamble) | first | header at row 3 |

Patches:
1. Filename glob set expanded: `*Explorium*Tech_Stack*`, `*Explorium*TechStack*`,
   `*Technographic*Stack*Explorium*`, plus the inverted ordering variants.
2. Sheet selection priority: `Confirmed_Tech_Stack` > any `*_Tech_Stack`
   sheet > `wb.active` fallback. Skips `Explorium_Match`.
3. Header row detection scans the first 6 rows for a row with ≥ 2
   known column tokens; skips human-readable preamble rows.
4. Vendor-column matching does case-insensitive substring on:
   `vendor`, `vendor / product`, `vendor/product`, `technology`,
   `company`, `name` — so the combined Calprivate header registers.
5. Rejects rows where the vendor cell starts with `source:` / `note:` /
   `—` (preamble lines that survive the header detection).

### Decision E — Recommendations register variant discovery

Real samples ship recommendations under two locations:

- `08_appendices/recommendations_detail.json` (Alma — canonical)
- `07_governance/recommendations_register.json` (Odlum)

`parse_package` now tries the canonical first, then the register
variant. Other samples genuinely ship no JSON recommendations
(workbook-only); they remain at `recs=0` until the workbook recs
sheet parser lands (out of scope for this ADR).

### Decision F — Peer benchmarks variant shape (Nicola)

Nicola's `06_peers/02_peer_benchmarks.json` has shape:

```json
{
  "peer_set": ["Connor, Clark & Lunn Private Capital", "..."],  // string list
  "peer_overall_scores": {"CC&L_Private_Capital": 2.64, ...},   // sanitized keys
  "benchmarks": {"P1C1": {"peer_scores": {"...": 2.5}}, ...}
}
```

Two complications:
1. `peer_set` is a LIST OF STRINGS (peer names), not the prior
   dict-of-dicts shape.
2. `peer_overall_scores` keys are sanitized (`CC&L_Private_Capital`)
   while `peer_set` entries are full ("Connor, Clark & Lunn …").

Fix: detect string-list shape; synthesize one `PeerScore` per name;
resolve overall scores via a normalized key index (lowercase +
strip punctuation + drop suffixes like "Management" / "Limited" /
"Investment Counsel"). Aggregate per-pillar averages from
`benchmarks.{cat}.peer_scores`.

### Decision G — Firmographics fallback to client-profile DOCX

Alma and Odlum ship no `research_handoff.json` but DO ship a client
profile DOCX with extractable leadership + firmographics. The
existing `client_profile.parse_client_profile_path` extractor was
never called from `parse_package`.

Fix: when no handoff JSON is found, glob `04_reports/` for
`*ClientProfile*.docx` / `*Client_Profile*.docx` and synthesize a
minimal `Firmographics` with the institution name + leadership
list. Result: Alma gets 10 leadership rows from the DOCX; Odlum
gets 12. The D5 Context panel renders real data instead of the
empty state.

## Tests pinned

`backend/tests/test_dma_package_real_samples_audit.py` — 16 tests,
each pinned to a specific real sample shape and the decision letter
above. The tests run against the real fixture corpus at
`backend/tests/fixtures/dma_packages_real_samples/`.

| Test | Decision pinned |
|---|---|
| `test_alma_real_sample_baseline_counts` | reference |
| `test_calprivate_real_sample_institution_name_via_entity_name_alias` | A |
| `test_calprivate_real_sample_minimum_counts` | C+D |
| `test_calprivate_real_sample_tech_stack_uses_technographic_variant` | D |
| `test_nicola_real_sample_synthesizes_run_manifest_from_handoff` | B |
| `test_nicola_real_sample_minimum_counts` | B+C+D+F |
| `test_nicola_real_sample_peers_via_peer_overall_scores_shape` | F |
| `test_odlum_real_sample_institution_via_institution_alias` | A |
| `test_odlum_real_sample_recommendations_via_register_variant` | E |
| `test_odlum_real_sample_firmographics_via_client_profile_docx` | G |
| `test_odlum_real_sample_minimum_counts` | C+D+G |
| `test_odlum_real_sample_tech_stack_picks_confirmed_sheet_not_explorium_match` | D |
| `test_wsfs_real_sample_baseline_counts` | reference |
| `test_every_real_sample_has_non_blank_institution_name` | A+B (cross-sample) |
| `test_every_real_sample_meets_minimum_subcap_count` | xlsx fallback (cross-sample) |
| `test_every_real_sample_has_firmographics_or_warns` | G (cross-sample) |

Plus the new operator helper at
`backend/app/scripts/inspect_dma_samples.py` — exit-1 when any
sample below threshold.

## After-fix sample matrix

| Sample | sub | ev | rec | peer | iss | tch | sect | firm | leaders |
|---|---|---|---|---|---|---|---|---|---|
| Alma | 698 | 105 | 7 | 5 | 9 | 33 | 72 | Y | 10 |
| Calprivate | 698 | 125 | 0 | 5 | 3 | 25 | 47 | Y | 0 |
| Nicola | 709 | 149 | 0 | 5 | 3 | 32 | 73 | Y | 0 |
| Odlum | 709 | 127 | 6 | 4 | 5 | 12 | 54 | Y | 12 |
| WSFS | 708 | 106 | 0 | 4 | 7 | 25 | 56 | Y | 0 |

All 5 samples meet audit acceptance (sub ≥ 690, ev ≥ 100, firm = Y).

## Out of scope

- Workbook `Recommendations` sheet parsing (WSFS/Nicola/Calprivate
  ship recs in the assessment workbook, not as JSON). Tracked as
  P2 follow-up.
- Leadership-from-handoff: Calprivate / Nicola / WSFS handoff JSON
  carry leadership lists in shapes the firmographics parser doesn't
  fully resolve yet (visible as `leaders=0` in the matrix above).
  P2 follow-up.
- Subcap mappings from Odlum's `subcaps_supported` column (category-
  level rather than full IDs). The evidence parser currently treats
  these as unlinked; D3 still renders the evidence rows but without
  per-subcap linkage. Tracked as P-LIVE follow-up requiring the
  catalogue alias bridge to resolve category-level IDs.

## Cross-references

- ADR 0005 — catalogue versioning (per-run resolver pins the right
  catalogue version even when the synthesized manifest's
  `rubric_version` is None).
- ADR 0013 — two-phase deploy (the new `inspect_dma_samples` helper
  is a recommended dry-run step in DEPLOYMENT.md §0.6 before live
  Drive backfill).
- ADR 0014 — final-audit P0 patches (ingest_package deck skip +
  rag offline-not-cached) — sibling commit; orthogonal scope.
- `docs/QA-CONTRACT.md` PD-08 (parser fidelity) — the real-sample
  matrix is the authoritative regression corpus.
