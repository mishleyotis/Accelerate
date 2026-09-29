# Rulebook: techstack · v2 (2026-08-19)

This is the techstack page's anti-pattern rulebook: the measured record of what
a promoted technology register looks like when it is right (Baxter, run
`c1351d25`) and the named failures that reached promotion before the gates
existed (chiefly Logix, run `d7ed1d90`, the worked test client). The
**techstack producer reads it before authoring, as Method step 2**, alongside
`get_memory_digest` + `search_findings`; the **rectifier is its only writer** —
a producer never edits it, and an edit with no finding behind it is an opinion.
Entries flagged by a USER or REVIEWER are **PERMANENT and never retired**,
whatever later rounds conclude. Baxter is **v5.0-shaped — 17 categories
including P1C5, 706 cells — so every shape-specific count quoted from it
(51 register rows, a 5-peer cohort, 16/30/2/3 status split) is a v5.0 fact of
that run, not a contract**; a v7.0 run has its own.

The census for this page, so nothing is minted to fill it: the Surface
Specification's D6 defines exactly two surfaces — T1, the register, and T3,
the per-row detail sub-page a register row opens — and the T-family stops at
T3. T2 recounts THIS register but renders on the insights page (its rulebook
entry is `rulebooks/insights.md § T2`; the split is the spec's own), the
run/version diff is V1 on Health, server-computed with no producer, and there
are no T4–T8 anywhere in the Surface Specification — the surface map
(`05-lifecycle/surface-map.md`) says so and forbids minting ids for the
directory, refresh-cadence and run-history chrome that tasking vocabulary
sometimes calls by those names.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `techstack/T1.md` — T1 · Technology stack register
- `techstack/T3.md` — T3 · Platform detail
