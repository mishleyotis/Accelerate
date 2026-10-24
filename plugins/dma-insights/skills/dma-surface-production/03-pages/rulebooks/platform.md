# Rulebook: platform · v2 (2026-08-19)

This is the platform page's anti-pattern rulebook: the measured record of what
a promoted platform page looks like when it is right (Baxter, run `c1351d25`)
and the named failures that reached promotion before the gates existed (chiefly
Logix, run `d7ed1d90`). The **platform producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — a producer never edits it, and an edit with
no finding behind it is an opinion. Entries flagged by a USER or REVIEWER are
**PERMANENT and never retired**, whatever later rounds conclude. Baxter is
**v5.0-shaped — 17 categories including P1C5, 706 cells — so every
shape-specific count quoted from it (5 tiles, 8 recommendations, 27–28 gap
rows) is a v5.0 fact of that run, not a contract**; a v7.0 run has its own.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `platform/P1.md` — P1 · Platform fit &amp; story (with DD-11, DD-13)
- `platform/P2.md` — P2 · Recommendations (with DD-4)
- `platform/P2b.md` — P2b · Conversation starters
- `platform/P3.md` — P3 · Transformation roadmap
- `platform/P4.md` — P4 · Stair-step curve
