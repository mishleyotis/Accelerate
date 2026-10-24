# Page: insights

Two sections. Cards must be claims, not topics. The landscape strip recomputes its counts from the tech-stack register, so techstack can be produced before or after but the counts must reconcile.

**2 sections · 2 surfaces.** Submit with `submit_page_payload(run_id, page='insights', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `insights` | yes | I1 | D2 |
| `landscape` | yes | T2 | D2 |

## Surfaces on this page — one file each

The per-surface files carry the contract, the must-present list, the information sources and the synthesis prompt for one surface. A producer reads the file for the surface it owns, never the whole page; the page-wide rules above apply to every one of them.

- `insights/I1.md` — I1 · Insight cards
- `insights/T2.md` — T2 · Technology landscape strip
