# The memory tools

These are the contracts this skill was written against. **Names are discovered,
not assumed.** At STEP 0, list the connector's tools and map by contract; if a
name differs, use the connector's and record a finding against this file.

In a session the tools appear namespaced:
`mcp__plugin_dma-insights_connector__<name>`.

## The store

Two tables behind six tools.

**findings** — one row per distinct defect, not per sighting. Carries an
embedding (384-dim, the connector's bundled model, L2-normalised,
`vector_cosine_ops`) and a tsvector, so the same row is reachable semantically
and lexically. Sightings accumulate on the row; the sighting count is the
class signal.

**refinements** — one row per change made in response. Carries the rung, the
artefacts touched, the check that proves it, the findings it closes, and —
the field that makes this a loop — **whether it held**: set false when a
recurrence is reported against it.

## `record_finding(finding) → {finding_id, deduped, sightings}`

Idempotent by fingerprint. `deduped: true` with `sightings: 4` means this is the
fourth sighting of a finding that already exists, which is information you act
on immediately: four sightings of one path is a recurrence, four sightings
across four paths is a class.

Send the shape in `templates/finding.schema.json`. Required in practice:
`invariant`, `path`, `locus`, `verb`, `observed`, `source`, `session_ref`.
Optional but worth the keystrokes: `surface`, `run_id`, `excerpt`,
`would_have_caught_it`, `internal_only[]`.

NEVER pre-suppress a duplicate by deciding yours is one. Record it; the store
decides, and a suppressed sighting is a sighting the class never gets credit
for.

## `search_findings(query, mode, filters) → [{finding_id, score, status, refinements[]}]`

`mode` is semantic, lexical, or both. **Run both.** They fail in opposite
directions: semantic search blurs exact tokens (`sequencing_basis` matches every
roadmap field), lexical search misses paraphrase (a verifier's "the label and the
figure came from different rows" will never lexically match "grain violation").
Union the results and dedupe by `finding_id`.

Each hit carries the refinements recorded against it. A hit with a refinement
whose `held` is true, and a fresh sighting in front of you, is a recurrence —
which is the single most important thing this call can tell you.

## `list_open_findings(filters) → [finding]`

The routine's primary read and the handshake's probe. Filter by window, surface,
locus, severity, minimum sightings. Order is meaningful: request it by sighting
count or recency and say which you used, because the cluster ranking in
`01-loop/2-clustering.md` is not the store's default order and you must
re-rank yourself.

## `record_refinement(refinement) → {refinement_id}`

The shape is in `templates/refinement.schema.json`:

```
{rung: R1|R2|R3|R4|R5, mode: preventive|detective, direction: added|widened|narrowed,
 artefacts: [path…], check: {kind: test|gate|constraint|script|none,
                             id, command, result},
 negative_control: {method, ran, failed_as_expected, output},
 closes: [finding_id…], ceiling: {rung, reason} | null,
 reason: "15–40 words naming what this catch depends on"}
```

`check.kind: none` is legal and means R1 or R2 — a refinement with no check.
It is recorded, and it **does not close anything**. That asymmetry is the point:
you may improve a skill with prose, and you may not call the class closed with
prose.

## `resolve_finding(finding_id, refinement_id, check) → {status}`

Refuses without a refinement. That refusal is the mechanised form of "no closing
without a check", and it is why the resolve tool takes the refinement rather
than a boolean. If you find yourself wanting to resolve something with no
refinement, the finding is not resolved.

Preconditions you must satisfy before calling, in full in `01-loop/4-closing.md`:
the check exists and is named, it passes on the fixed state, and it fails on the
state that produced the finding.

## `report_recurrence(finding_id, refinement_id, evidence) → {recurrence_count}`

Marks the refinement as not held and re-opens the finding with its history
intact. `evidence` names the new sighting: where, when, and — the field that
distinguishes the three recurrence kinds — **whether the existing check was run
against the new instance and what it said**. A check that passes on a genuine
instance is a scope defect, not an ignored instruction, and only this field
tells them apart.

## Failure handling

| What happened | Do |
|---|---|
| Tool absent from the listing | STOP the run. Report `memory unreachable`. Change nothing |
| Tool present, errors | Retry once. Then STOP, same report, naming the error |
| Tool present, store empty | Continue only to record; report `memory empty` and do not conclude that nothing has ever been found |
| Name differs from this file | Use the connector's. Complete the run. Record a finding against this file |

None of these degrade into "carry on from the transcript". See
`01-loop/1-memory-first.md` for why that refusal is absolute.
