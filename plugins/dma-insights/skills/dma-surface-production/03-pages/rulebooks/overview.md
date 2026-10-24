# Rulebook: overview · v2 (2026-08-19)

This is the overview page's anti-pattern rulebook: the measured record of what a
promoted overview looks like when it is right (Baxter, run `c1351d25`) and the
named, gated failures that reached promotion before the gates existed (chiefly
Logix, run `d7ed1d90`). The **overview producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — a producer never edits it, and an edit with no
finding behind it is an opinion. Entries flagged by a USER or REVIEWER are
**PERMANENT and never retired**, whatever later rounds conclude. Baxter is
**v5.0-shaped — 17 categories including P1C5, 706 cells — so every shape-specific
count quoted from it is a v5.0 fact, not a contract**; a v7.0 run (Logix: 16
categories, 705 cells) has its own counts. The card-level firmographics rulebook
entry lives here, under O2, per D2 — the context rulebook points at it.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `overview/O1.md` — O1 · Scores &amp; peer benchmarks
- `overview/O2.md` — O2 · Firmographics strip
- `overview/O3.md` — O3 · Why-now signals (with O3 drilldown)
- `overview/O4.md` — O4 · Executive summary
- `overview/O5.md` — O5 · Opportunity surface tiles
- `overview/O6.md` — O6 · Top findings (with DD-9)
- `overview/O7.md` — O7 · Leadership panel
- `overview/O8.md` — O8 · Financial trajectory
- `overview/O9.md` — O9 · Sentiment (with DD-12)
- `overview/O1b.md` — O1b · Capability ceiling &amp; uncertainty (with DD-15)
- `overview/O10.md` — O10 · Evidence coverage
- `overview/O11.md` — O11 · Evidence tier distribution
- `overview/O12.md` — O12 · Thought leadership signal
