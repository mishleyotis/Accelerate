# Rulebook: heatmap · v2 (2026-08-19)

The heatmap page's anti-pattern rulebook: what a promoted heatmap looks like when
it is right (Baxter, run `c1351d25`) and the measured, gated failures that reached
promotion before the gates existed (chiefly Logix, run `d7ed1d90`). The **heatmap
producer reads it before authoring, as Method step 2**, beside `get_memory_digest`
+ `search_findings`; the **rectifier is its only writer** — an edit with no finding
behind it is an opinion. Entries raised by a USER or REVIEWER are **PERMANENT and
never retired**. Baxter is **v5.0-shaped — 17 categories including P1C5, 706
cells — its shape-specific counts are v5.0 facts, not contracts**; v7.0 has 16.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `heatmap/H4.md` — H4 · Workbook grain scores
- `heatmap/H1.md` — H1 · Focus areas (with DD-10)
- `heatmap/H2.md` — H2 · Cell evidence (with DD-1)
- `heatmap/H6.md` — H6 · Evidence store (with DD-2)
- `heatmap/H9.md` — H9 · Value-chain view
- `heatmap/H3.md` — H3 · Thin-evidence alerts
- `heatmap/H5.md` — H5 · Safeguard gates
- `heatmap/H7.md` — H7 · Evidence age tracker
- `heatmap/H8.md` — H8 · Cross-entity patterns
