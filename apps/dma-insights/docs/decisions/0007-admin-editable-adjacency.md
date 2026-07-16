# ADR 0007 — Subvertical adjacency: admin-editable, not hardcoded

**Status**: Accepted (2026-05-20)

## Context

ADR 0006's `cross_vertical` mode weights cohort matches by an adjacency
matrix between the 9 sub-verticals (RB, CU, CL, CIB, FC, AM, RIA, IC, IB).
Defaults (1.0 self / 0.6 adjacent / 0.3 distant) are reasonable starting
points but the user wants to tune them post-launch based on real cross-cohort
recommendation quality.

## Decision

Adjacency is data, not code. New table:

```sql
CREATE TABLE ccg_subvertical_adjacency (
  from_code VARCHAR(8) NOT NULL REFERENCES ccg_subverticals(code),
  to_code VARCHAR(8) NOT NULL REFERENCES ccg_subverticals(code),
  weight NUMERIC(3,2) NOT NULL CHECK (weight >= 0.0 AND weight <= 1.0),
  updated_by UUID REFERENCES users(id),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  notes TEXT,
  PRIMARY KEY (from_code, to_code)
);
```

Seeded with defaults for all 9² = 81 pairs (1.0 self, 0.6 adjacent, 0.3
otherwise — initial groupings: {RB, CU, CL, FC} retail-lending cluster, {AM,
RIA} wealth cluster, {IC, IB} insurance cluster, CIB its own).

New admin page `/admin/rag-tuning`:

- 9×9 grid; click any cell to edit `weight` (slider 0.0–1.0 + notes).
- "Preview impact" button recomputes RAG cohort sizes against current ACTIVE
  runs and shows the diff.
- Every change writes an `audit_log` entry + bumps `updated_at`.

`rag_cohort.py` reads from this table (Redis-cached, 60s TTL — no service
restart needed on edit).

## Consequences

- Adds one table + one admin route + one Redis cache key prefix.
- Audit log captures every weight change with `updated_by` + `notes`.
- Defaults are seeded by migration `015_ccg_adjacency_seed`; admin overrides
  persist across catalogue version bumps (table is *not* version-scoped).
- New subvertical onboarding (ADR per resolved decision 8 in the plan)
  auto-extends the matrix with default weights against the new code.
