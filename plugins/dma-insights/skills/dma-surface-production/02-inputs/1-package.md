# The assessment package

Every client folder carries the same 15-folder structure —
8 at the top level and
7 nested.

```
<Client Name> - DMA/
├── 01_evidence/                     the evidence corpus
│   └── entity_profile/              firmographics and identity
├── 02_research_workbook/            raw research, per cell
├── 03_scoring_workbook/             THE scoring authority
│   └── exports/                     flattened score projections
├── 04_reports/                      Assessment Report + Client Profile
├── 05_narrative_deck/               client-facing deck — NOT a source
├── 06_peers/                        the peer cohort table
├── 07_governance/
│   ├── layer1_qa/                   first-line QA on the assessment
│   └── layer2_audit/                independent audit and calibration
└── 08_appendices/
    ├── recommendations/             recommendation detail
    ├── gap_priority/                ranked gap register
    └── research_appendix_csv/       issue register and flat exports
```

## What each folder holds

| Folder | Holds | Lands in |
|---|---|---|
| `01_evidence` | evidence_index.csv, per-item source captures, retrieval dates | `evidence_index · evidence_subcap_links` |
| └ `entity_profile` | legal name, charter, regulator, jurisdictions, assets, employees, branches | `entities · firmographics_raw` |
| `02_research_workbook` | search transcripts, technographic scans, dated events, sentiment captures | `document_sections · techstack_raw · timeline source` |
| `03_scoring_workbook` | one row per scored cell: score, confidence, evidence refs — and the cell address | `subcap_scores (with source_cell)` |
| └ `exports` | flattened score CSVs, rollups, toggle-cascade results | `subcap_scores rollups · run.scored_cells` |
| `04_reports` | Assessment Report DOCX (12 structured sections) and Client Profile Research Report DOCX | `document_sections · issue_register_raw` |
| `05_narrative_deck` | PPTX built from the report; not an ingest source | `— (not parsed; retained for lineage)` |
| `06_peers` | peer_comparison_table.csv — cohort membership and per-cell peer figures | `peer_scores` |
| `07_governance` | gate results, calibration notes, sign-off | `gate_results · parser_observations` |
| └ `layer1_qa` | per-cell QA findings, thin-evidence register | `gate_results (SG family) · heatmap_alerts source` |
| └ `layer2_audit` | calibration analysis, drift checks, issue register | `gate_results · calibration flags` |
| `08_appendices` | run_manifest.json and the machine-readable appendices | `run_manifest · recommendations_raw` |
| └ `recommendations` | recommendations_detail.json — impact, effort, sequencing, platform mapping | `recommendations_raw · platform_fits_raw` |
| └ `gap_priority` | ranked gaps with their anchor cells | `opportunity + findings synthesis input` |
| └ `research_appendix_csv` | issue_register.csv and the remaining structured appendices | `issue_register_raw` |

## Source priority

Where two artefacts disagree, the higher row wins and the disagreement is a parser
observation — never silently reconciled.

| # | Artefact | Authoritative for |
|---|---|---|
| 1 | Scoring workbook | Every score, every peer figure, and the cell each was read from |
| 2 | Assessment report | The twelve structured sections, gap prioritisation, roadmap |
| 3 | Client profile research report | Focus areas with verbatim quotes and page numbers, leadership, firmographics narrative |
| 4 | Package structured files | Evidence index, issue register, peer cohort, recommendation detail, run identity |
| 5 | Ops sheet and connectors | AE ownership, firmographic enrichment |

## The corpus is the whole package

Owner instruction, 2026-08-20: everything above except the bulky
`05_narrative_deck` is synthesis input. `drive_fetch.py pull` lands the tree
recursively; a synthesis that reads only the two workbooks re-derives what
`01_evidence`, `04_reports`, `06_peers`, `07_governance` and
`08_appendices` already hold — and re-derivation is where drift enters.
Consult the landing table above for where each artefact belongs.

Evidence ids are scoped to the client. The same `E-017` in two clients'
packages is two unrelated items — expected, never a finding. Inside one
package, duplicate **by content** decides: one id defined twice with
identical content dedups silently; defined twice with different content
refuses at vetting. Wherever an id leaves its client's namespace (a
cross-client ledger, a shared log), it carries the client slug as a prefix:
`t-rowe-price-group-inc:E-017`.

## Two folders to treat differently

**`03_scoring_workbook` is the only authority for a score.** Nothing else may set one. The
parser records the workbook cell address alongside every figure, and that address is what
makes the grain assertion checkable rather than aspirational.

**`05_narrative_deck` is not a source.** It is a rendering of the report, so treating it as
a source creates a second path to the same claim — and two paths to one claim eventually
disagree.

## Governance is an ingest source, not an archive

`07_governance/layer1_qa` and `layer2_audit` carry the assessment's own quality findings:
the thin-evidence register, calibration analysis and drift checks. Those seed the
thin-evidence alerts and the safeguard-gate results rather than being re-derived. An
assessment that already knows where it is weak should not have to be re-diagnosed.

## Identity signals, strongest first

| Signal | Read from |
|---|---|
| Entity identity, highest confidence | `08_appendices/run_manifest.json` |
| Request identifier | The manifest, or the folder name pattern |
| Legal name, charter, regulator, jurisdictions | `01_evidence/entity_profile/` |
| Sub-vertical and size tier | The manifest, confirmed against the profile |
| Completion date | The manifest; the folder timestamp is a fallback only |
| Catalogue version | The scoring workbook header |

**A folder name is the weakest signal.** Client folders are named by humans and the observed
set already varies — "- DMA", "- Claude DMA", "- Twilio DMA", "- DMA v2". That version
suffix is a human note about a rerun, not a catalogue version, and must not be read as one.

**The sub-vertical is the highest-consequence of these signals**, because it decides which
catalogue cells the run may serve as well as which regulator vocabulary and metric set
apply. The workbook scores the whole catalogue including other sub-verticals' variant cells,
so a run whose sub-vertical you did not establish is a run that will cite cells the app
never renders. Take it from the manifest, confirm it against the entity profile's charter
and regulator, and write it down at the vet step —
`01-start-here/6-entity-shape.md` for what follows from it.

Establish the entity's **ownership shape** in the same pass. Whether it files with a
securities regulator, files a call report, or files nothing at all decides which enrichment
ladders can possibly return anything, and it is the difference between an honest empty state
and a ladder that was run correctly against routes this entity does not have.
