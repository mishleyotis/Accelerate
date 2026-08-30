# Rectification run — <YYYY-MM-DD>

Window: <from> – <to> (UTC) · Session: <session_ref> · Trigger: weekly | manual

## STEP 0 — Handshake

| | |
|---|---|
| Memory tools seen | `<n>` — <names, or the contract each mapped to> |
| Defect classes | `<n>` from `list_defect_classes` — <any invented this run, with their PROBE> |
| Open findings | `<open_count>` (OPEN + INVESTIGATING + RECURRED) |
| Recurrences in window | `<n>` |
| Ageing unrefined (14d+) | `<n>` |
| Oldest open | `<date>` |
| Newest sighting | `<date>` |
| Search paths skipped | <any `paths_skipped` reason seen this run; a path that never ran is not evidence of absence> |

<If the newest sighting is old while QA agents have run since, say so here. A
quiet store and a broken pipe look identical in the open count and different in
this row.>

## STEP 1 — Local channel

`<n>` findings drained and recorded from this session's working tree, or
`local channel empty`. List each with its source artefact.

## STEP 2–3 — Clusters

| # | Class (12–30 words, two points) | Sightings | Recurrence depth | Client reach | Opened |
|---|---|---|---|---|---|
| 1 | | | | | yes / no |

Ordering used: recurrence depth, then client reach, then sighting count.
Stopped after `<n>` clusters — budget, not exhaustion. Say which.

## STEP 4–6 — What changed

### Cluster 1 — <defect_class> · <class name in 12–30 words>

- **`target_kind` → rung:** `<TEST|GATE|SCHEMA|SKILL|AGENT|DOC|PROCESS|COMPONENT>`
  → R<n>
- **Previous `target_kind` for this class:** R<n>, from `get_finding` — or
  UNKNOWN, and say so rather than assuming none. If a recurrence, confirm this
  rung is strictly above it, or that you ran the existing check and it passed on
  a genuine instance (a scope defect: widen the same rung)
- **`rationale`:** `RUNG: R<n> — ` + 15–40 words naming what the catch depends on
- **`target` / artefacts:**
- **`commit_sha` or `change_ref`:**
- **`verification` (the negative control, both directions):** passes on the
  fixed state; fails on `<how the broken state was reconstructed>` with
  `<the failure line>`
- **`gate_added`:** <where target_kind is GATE>
- **Closes:** `<finding ids>` — or ADDRESSES only, and why
- **Ceiling / rung not reached:** <the rung you could not reach and why, or none>

## STEP 7 — Written back

| Call | Count |
|---|---|
| `ingest_reviewer_feedback` | ingested / skipped / problems |
| `record_finding` | |
| `record_refinement` | |
| `resolve_finding` | |
| `report_recurrence` | |

## Left open

| Finding | Class | Waiting on rung | Why not this run |
|---|---|---|---|

## Did the previous fixes hold?

| Refinement | Rung | Held | Evidence |
|---|---|---|---|

<The only direct measurement of whether this loop works. A refinement marked
not-held names the recurrence kind: rung too low, scope too narrow, or ceiling
reached — and only running the existing check against the new instance tells the
first two apart.>

## PR

`<link>` — opened, not merged. One commit per cluster, named paths only.

---

**Nothing-to-do form.** When there is nothing above threshold, the whole report
is these four lines and no others:

```
No open findings above threshold in the window <from>–<to>.
Handshake: <n> tools, <open_count> open findings, newest sighting <date>.
Local channel: empty.
Nothing changed.
```

Recorded as examined-and-empty. The threshold was not lowered, the codebase was
not scanned for defects nobody sighted, and nothing was tidied.
