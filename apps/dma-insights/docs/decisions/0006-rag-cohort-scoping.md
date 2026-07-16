# ADR 0006 — RAG cohort scoping: three-mode router

**Status**: Accepted (2026-05-20)

## Context

The Claude project queries DMA Insights' RAG API for prior evidence relevant
to the assessment it's generating. The cohort question is non-trivial:

- A pure Credit Union entity wants CU peers only (cohort = `single`).
- A CU that also runs commercial lending wants CU + commercial lending peers
  (`multi_lob`).
- A new entity in a subvertical with N < 3 needs to broaden to adjacent
  verticals or starve (`cross_vertical`).
- The user wants knobs over cohort weights (some pairs are closer than others).

## Decision

Three-mode router in `backend/app/services/rag_cohort.py`. Auto-derived from
the calling entity's profile unless explicitly overridden:

| Mode | When | Filter |
|---|---|---|
| `single` | Entity has exactly one subvertical and `lobs.length ≤ 1` | `entity.subvertical = :sv` |
| `multi_lob` | Entity has one subvertical but `lobs.length ≥ 2` | Union: `subvertical = :sv OR lobs && :lobs`; `cohort_match=1.0` exact, `0.7` LOB-overlap |
| `cross_vertical` | Caller forces, OR multi-subvertical entity, OR cohort N < 3 | All entities; `cohort_match = ccg_subvertical_adjacency.weight` (1.0 self / 0.6 adjacent / 0.3 distant by default; admin-editable) |

Every response includes a `cohort_mode` + `n` field so the Claude project
knows what it received. If N < 3 in the requested cohort, response is 200
with body `{ insufficient_cohort: true, n, fallback: "cross_vertical_median",
… }` — never silently fakes peer data.

## Consequences

- Adjacency is no longer a static matrix in code; see ADR 0007.
- IntelligencePanel internal calls follow the same logic — a DMA on a CU that
  also operates a brokerage gets evidence across both, weighted.
- Result: `cohort_mode` field on every RAG response; UI/Claude consumer can
  decide whether to display "matched only same-subvertical" or "broadened to
  adjacent" affordance.
