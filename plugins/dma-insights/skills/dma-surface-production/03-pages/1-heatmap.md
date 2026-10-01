# Page: heatmap

FIRST. Nine sections. Cell evidence establishes the linkage every other page cites, and the coverage figures the Overview reports are computed over the cells you link here. Four of these sections render on the Health dashboard.

**9 sections · 9 surfaces.** Submit with `submit_page_payload(run_id, page='heatmap', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `workbook_scores` | yes | H4 | D3 |
| `focus_areas` | yes | H1 | D3 |
| `cell_evidence` | yes | H2 | D3 |
| `evidence` | yes | H6 | D3 |
| `value_chain` | optional | H9 | D3 |
| `alerts` | yes | H3 | D7 |
| `safeguard_gates` | yes | H5 | D7 |
| `evidence_age` | yes | H7 | D7 |
| `cohort_patterns` | optional | H8 | D7 |

## Surfaces on this page — one file each

The per-surface files carry the contract, the must-present list, the information sources and the synthesis prompt for one surface. A producer reads the file for the surface it owns, never the whole page; the page-wide rules above apply to every one of them.

- `heatmap/H4.md` — H4 · Workbook grain scores
- `heatmap/H1.md` — H1 · Focus areas
- `heatmap/H2.md` — H2 · Cell evidence
- `heatmap/H6.md` — H6 · Evidence store
- `heatmap/H9.md` — H9 · Value-chain view
- `heatmap/H3.md` — H3 · Thin-evidence alerts
- `heatmap/H5.md` — H5 · Safeguard gates
- `heatmap/H7.md` — H7 · Evidence age tracker
- `heatmap/H8.md` — H8 · Cross-entity patterns
