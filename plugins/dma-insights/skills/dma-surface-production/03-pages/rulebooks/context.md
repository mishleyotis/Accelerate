# Rulebook: context · v2 (2026-08-19)

The context page's anti-pattern rulebook: what a promoted context page looks like
when it is right (Baxter, run `c1351d25`) and the measured failures that reached
promotion before the gates existed (chiefly the same page's own pre-gate rounds,
plus Logix, run `d7ed1d90`). The **context producer reads it before authoring, as
Method step 2**, beside `get_memory_digest` + `search_findings`; the **rectifier
is its only writer** — a producer never edits it, and an edit with no finding
behind it is an opinion. Entries raised by a USER or REVIEWER are **PERMANENT and
never retired**, whatever later rounds conclude. Baxter is **v5.0-shaped — 17
categories including P1C5, 706 cells — so every shape-specific count quoted from
it is a v5.0 fact, not a contract**; a v7.0 run has 16 categories. C6 renders
`overview.financial_series` — one section, written once on the overview page; its
rulebook entry lives in the overview rulebook, and this page never authors it.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `context/C1.md` — C1 · Digital evolution timeline (with DD-7)
- `context/C2.md` — C2 · Issue register &amp; Gantt (with DD-8)
- `context/C3.md` — C3 · Regulatory standing
- `context/C4.md` — C4 · Sentiment overview (with DD-12)
- `context/C5.md` — C5 · Acquisition history (with DD-14)
- `context/C6.md` — C6 · Financial trajectory
