# ADR 0002 — AE assignment: hybrid Ops Sheet + Drive owner + admin override

**Status**: Accepted (2026-05-20)

## Context

There are ~115 historical DMAs in Drive (folder `1uvt3kh8vPIygFwUNfKQSol0m5OYj2O0P`,
naming pattern `{Client Name} - DMA`). The DMA Ops Sheet records new requests
with an `assigned_to` first-name string (e.g. `"Mishley"`). The product needs
"My clients" / "All clients" filters on `/clients`, which requires resolving
every entity to a `users.email`.

Three problems:

1. The historical DMAs have no explicit AE on most rows.
2. The Ops Sheet stores first names, not emails — we must JOIN through
   `ops_team.name → ops_team.calendar_id` (= Zennify email).
3. Drive folder ownership is also a signal (folder owner / most recent file
   modifier), but lower confidence than the sheet.

## Decision

Hybrid resolution, three sources, in priority order:

1. **Ops Sheet `Requests.assigned_to`** (highest confidence). Mirrored into
   `ops_requests` by `sheet_poller` every 5 min; resolved to `users.id` via
   `ops_team`. Fuzzy match (Levenshtein ≤ 2) handles typos; ambiguous matches
   go to admin's "Needs Assignment" queue.
2. **Drive folder owner inference** (medium confidence). `drive_crawler`
   reads each `{Client} - DMA` folder's owner + most recent file modifier
   and proposes candidates with confidence weights. Anything < 0.85
   confidence lands in PENDING_REVIEW.
3. **Admin manual override** (always wins). Admin → Assignments page lets
   admin re-assign any entity; writes `entity_assignments(source='admin_manual')`.

Source-of-truth table: `entity_assignments(entity_id, user_id, source,
source_ref, confidence, assigned_at, superseded_at)`. Soft-delete on reassign
(set `superseded_at`); never hard-delete (audit trail).

## Consequences

- Backfill is a one-shot `workers/backfill_assignments.py` reading every row
  of the Ops Sheet + Drive folder owners.
- "My clients" filter is `WHERE entity_assignments.user_id = current_user AND
  superseded_at IS NULL`.
- Ambiguity is surfaced, never auto-resolved — admin sees the queue.
