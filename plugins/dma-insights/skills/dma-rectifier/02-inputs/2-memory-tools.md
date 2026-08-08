# The memory tools

Eleven tools on the deployed connector, namespaced in a session as
`mcp__plugin_dma-insights_connector__<name>`. Read this before your first call;
several of them refuse inputs that look reasonable, and each refusal is load
bearing.

Two tables behind them. **findings** — one row per distinct defect, not per
sighting, carrying an embedding and a tsvector so the same row is reachable
semantically and lexically. **refinements** — one row per change made in
response, carrying the findings it answers and, through
`memory_refinement_outcome`, whether it **held**.

Every count in this store is computed at read from the two source tables.
Nothing keeps a counter — invariant 8, applied to the memory itself.

---

## `list_defect_classes() → {classes[…]}`

**Read this first, before recording anything.** `defect_class` is a foreign
key, not a label: a memory rots when one defect is filed under three synonyms,
and the FK is what stops that.

Each class carries a **tell** (how it presents) and a **probe** (the command or
query that detects it), plus how many findings are open under it. The probe is
the most useful field in the whole store — it is a ready-made check you can run
against a suspicion before you have a finding at all.

Eleven classes are seeded, including the one this skill's worked example
traces: `CONTRACT_FIELD_DISCARDED_AT_PROMOTION`. Others worth knowing by name
because they recur across components: `UNRECOGNISED_INPUT_READS_AS_EMPTY`,
`WRITE_PATH_WITH_NO_READ_PATH`, `PROVENANCE_NAMES_THE_TOOL`,
`REVIEWER_REJECTED_INSIGHT`, `STALE_BUILD_ARTEFACT_SERVED`.

A class may be **invented, never invented silently**: pass `new_class
{title, description, tell, probe}` to `record_finding` alongside an unknown
`defect_class`. If you cannot write a probe for your new class, you have not
understood the defect well enough to name it — write the finding under the
closest existing class and say why it fits badly.

## `search_findings(query, mode, limit, filters…) → {paths_run[], paths_skipped{}, results[]}`

"Have we seen this before?", asked both ways because it is asked both ways.
Run it **before** recording and before designing a fix.

| mode | what it does |
|---|---|
| `auto` (default) | lexical first, semantic as well, trigram only if neither matched |
| `lexical` | `websearch_to_tsquery` + `ts_rank_cd` over the finding's text |
| `semantic` | pgvector KNN over the embedding written at record time |
| `fuzzy` | `pg_trgm` on the title — a typo or an abbreviation sharing no lexeme |

**Read `paths_skipped` every time.** An empty result from a path that never ran
is not evidence of absence: "no encoder in this image" and "nothing matched"
are different answers, and only one of them means you may conclude the finding
is new. This is the same discipline `deployed-app-auditor` applies to
UNVERIFIABLE versus PASS, and it fails the same way when ignored.

Each result carries `matched_by[]` and per-path scores, so you can see **why**
it matched. A hit that matched only by fuzzy title similarity is a lead, not a
prior sighting.

## `record_finding(finding) → {finding_id, deduped, sightings, recurrences, status, …}`

Idempotent by content: the same defect reported by three QA agents is ONE
finding with three sightings. Dedup identity, unless you override with
`dedup_key`:

```
component | defect_class | (file_path or surface or gate_id) | title
```

Required: `title`, `observed`, `measurement`, `component`, `defect_class`,
`severity`, `raised_by_kind`, `raised_by`.

- **`measurement` is the field that makes this store worth having.** How it was
  measured — the command, the query, the HTTP status, the count **with its
  denominator**. Minimum 30 characters, and "it broke" is refused. A finding
  whose measurement is a feeling cannot be re-run, so nobody can ever tell
  whether the fix held.
- `component` is `api | mcp | web | worker | migrations | infra | skill:<name> |
  agent:<name>`. A finding about a skill is filed against that skill, which is
  what makes "which skill produces the most defects" answerable.
- `severity` is `BLOCKER | MAJOR | MINOR | INFO`.
- `raised_by_kind` is `QA_AGENT | REVIEWER | GATE | USER | BUILD_AGENT | TEST |
  MONITOR`, and `raised_by` names the agent, gate or person.

Worth the keystrokes: `measured_value`, `expected`, `file_path`, `surface`,
`gate_id`, `run_id`, `entity_id`, `fix_hint`, `note`, `session_ref`,
`source_ref` (an idempotency token for this sighting).

Recording a defect already marked RESOLVED returns a **warning telling you to
use `report_recurrence` instead**. Do that — it is how a failed fix gets
recorded against the fix that failed, and recording it as a fresh finding
severs exactly the link this whole loop is built to preserve.

NEVER pre-suppress a duplicate by deciding yours is one. Record it; the store
decides, and a suppressed sighting is one the class never gets credit for.

## `list_open_findings(component, severity, defect_class, status, min_age_days, max_age_days, limit)`

Everything not closed — OPEN, INVESTIGATING **and RECURRED**, because a fix
that did not hold is open again. Ordered by severity, then recurrences, then
sightings: the top of the list is what has hurt most often, not what arrived
most recently. Each row carries `sightings`, `recurrences` and `age_days`.

This is the handshake's probe at STEP 0.

## `get_finding(finding_id) → {sightings[…], refinements[…]}`

One finding in full: every sighting in order, and every refinement against it
with its relation (`ADDRESSES` or `CLOSES`).

**This is where you look before changing anything.** If a refinement already
exists and the finding recurred, the change that failed is named here — and its
`target_kind` tells you which rung it landed on, which is the input to the
recurrence rule.

## `record_refinement(refinement) → {refinement_id}`

The server allocates `REF-####`. Required: `target_kind`, `target`, `change`,
`applied_by`, `finding_ids`, and **one of `commit_sha` or `change_ref`** — a
refinement nobody can locate is a claim, not a change.

`target_kind` is the ladder, in the store's vocabulary:

| Rung | `target_kind` | `target` looks like |
|---|---|---|
| R1 · prose | `DOC`, `PROCESS`, or `SKILL`/`AGENT` with no example | `skill:dma-surface-production` |
| R2 · worked example | `SKILL` / `AGENT` | `agent:surface-producer` |
| R3 · script or test | `TEST`, or `COMPONENT` for a bundled checker | `apps/mcp/tests/test_field_census.py` |
| R4 · connector gate | `GATE`, and set `gate_added` | `CG-13` |
| R5 · schema constraint | `SCHEMA` | `migrations/versions/0034_findings_memory.py` |

Two conventions this skill adds on top, because the store has no rung column
and the rung must survive to the next run:

- **Open `rationale` with `RUNG: R<n> — `**, then the 15–40 word reason naming
  what the catch depends on. `target_kind` and the stated rung must agree; if
  they do not, the `target_kind` is the truth and your rung claim is aspiration.
- **Put the negative control in `verification`**, both directions in one
  sentence: the check, that it passes on the fixed state, and that it fails on
  the state that produced the finding, with how that state was reconstructed.

`gate_added` exists so the memory holds the fix beside the defect. Use it.

**Recording a refinement closes nothing.** That is deliberate — "changed" and
"fixed" are two claims and only the second one can be wrong later.

## `resolve_finding(finding_id, refinement_id, verification="")`

Closes a finding by naming the refinement that closed it. The refinement is
required and **the column is under a CHECK**, so there is no way around it.
That constraint is this skill's central rule expressed at rung 5: without it,
"did the fix hold?" has no subject.

Pass `verification` — a test name, a gate id, a probe — whenever you have one,
and you should always have one, because a refinement with no check does not
close anything (see `../01-loop/4-closing.md`).

## `report_recurrence(finding_id, measurement, reported_by, …)`

**The signal that matters.** A fix that did not hold is more informative than
one that did.

The recurrence is recorded against the refinement by name (defaulting to the
one that closed the finding), the finding returns to `RECURRED`, and that
refinement's `held` flips to false in the digest. `measurement` is required with
the same 30-character floor: a recurrence claim is only as good as the
measurement that saw it come back.

If the finding was never resolved by a refinement this refuses and tells you to
use `record_finding` — nothing can have failed to hold.

## `get_memory_digest(days=7) → { … }`

Everything a weekly pass needs, in one call, and the routine's primary read.
Its own `reading` field states the order; follow it:

1. `recurrences_in_window` — each names the refinement that did not hold. Its
   target is where the next change belongs.
2. `new_findings_in_window`
3. `refinements_in_window` — with `held` per refinement.
4. `open_by_class` — which **shape** of defect this build is still producing. A
   class with several open findings is a process problem, not several bugs.
   This is the store doing your clustering for you, at the class grain.
5. `ageing_unrefined` — open 14+ days with nothing changed about it. The
   quietly accumulating half of the backlog.

## `list_reviewer_feedback(...)` and `ingest_reviewer_feedback(limit=200)`

The web app's Accept/Reject pair. `list_reviewer_feedback` reads verdicts
straight from `annotations` with the actor and whether each has been ingested;
it is a read, and invariant 2 constrains writes, not reads.

`ingest_reviewer_feedback` turns every un-ingested verdict into memory and is
idempotent — run it on a schedule and again by hand five minutes later, and a
verdict becomes a finding exactly once.

- A **REJECT** becomes a finding against the **synthesis skill**, carrying the
  card's own text and its `r_layer`. The defect is in what produced the claim,
  not in the application that rendered it, and it is the recorded reasoning the
  reviewer refused — not the headline.
- An **ACCEPT** lands as a verdict row, which is what makes the reject *rate*
  measurable. One reject against fifty accepts is a different problem from one
  against two.
- `problems[]` is never empty for the wrong reason: an unreadable verdict is
  left un-ingested and named, not counted as nothing.

Call it at STEP 1 of every run. A rejection sitting un-ingested in `annotations`
is feedback the loop cannot see.

## Failure handling

| What happened | Do |
|---|---|
| Tool absent from the listing | STOP the run. Report `memory unreachable`. Change nothing |
| Tool present, errors | Retry once. Then STOP, same report, naming the error |
| `search_findings` returns nothing but `paths_skipped` is non-empty | You have not established that the finding is new. Say so; do not conclude |
| Store empty | Continue only to record; report `memory empty` and do not conclude that nothing has ever been found |
| A name differs from this file | Use the connector's. Complete the run. Record a finding against this file, component `skill:dma-rectifier` |

None of these degrade into "carry on from the transcript".
`../01-loop/1-memory-first.md` says why that refusal is absolute.
