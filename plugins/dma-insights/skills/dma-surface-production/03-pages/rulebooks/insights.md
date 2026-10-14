# Rulebook: insights · v2 (2026-08-19)

The insights page's anti-pattern rulebook: what a promoted insights page looks
like when it is right (Baxter, run `c1351d25`) and the named, measured failures
that reached a rendered page (Logix, run `d7ed1d90`, and the memory findings
behind each entry). The **insights producer reads it before authoring, as
Method step 2**, alongside `get_memory_digest` + `search_findings`; the
**rectifier is its only writer** — an edit with no finding behind it is an
opinion. Entries flagged by a USER or REVIEWER are **PERMANENT and never
retired**. Baxter is **v5.0-shaped — 17 categories including P1C5, 706 cells —
so every shape-specific count quoted from it (8 cards, tiles 16/30/2/3) is a
v5.0 fact of that run, not a contract**; a v7.0 run (16 categories) has its own.

## Surfaces — one rulebook file each

A producer reads the file for the surface it owns; a page producer reads every file listed here. A drilldown's rules ride in the file of the surface it opens from.

- `insights/I1.md` — I1 · Insight cards (with DD-3)
- `insights/T2.md` — T2 · Technology landscape strip
