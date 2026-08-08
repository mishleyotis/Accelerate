# Rectification run — <YYYY-MM-DD>

Window: <from> – <to> (UTC) · Session: <session_ref> · Trigger: weekly | manual

## STEP 0 — Handshake

| | |
|---|---|
| Memory tools seen | `<n>` — <names, or the contract each mapped to> |
| Open findings | `<open_count>` |
| Oldest open | `<date>` |
| Newest sighting | `<date>` |

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

### Cluster 1 — <class name>

- **Rung:** R<n> (<preventive|detective>, <added|widened|narrowed>)
- **Previous rung for this class:** R<n> or none — <if a recurrence, confirm this
  rung is strictly above it>
- **Reason (15–40 words, what the catch depends on):**
- **Artefacts:**
- **Check:** `<id>` — `<command>` → pass
- **Negative control:** `<method>` `<reference>` → failed as expected: `<the
  failure line>`
- **Closes:** `<finding ids>`
- **Ceiling / rung not reached:** <the rung you could not reach and why, or none>

## STEP 7 — Written back

| Call | Count |
|---|---|
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
