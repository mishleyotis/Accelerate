# Clustering — ten findings, one defect

The single highest-leverage act in this loop is noticing that ten reports are
one problem. It is also the one most often skipped, because ten patches feel
like ten pieces of progress and one structural change feels like one.

The arithmetic says otherwise. Ten patches close ten findings and prevent
nothing; the class ships again next month under an eleventh field name. One
structural change closes ten and prevents the eleventh. The worked example is
exactly this, measured: five sightings patched one at a time over four
migrations, then one sweep that closed all five and made the sixth
unshippable.

## The fingerprint

A finding's identity is not its text — five different agents describe one
defect five ways. Identity is the fingerprint:

| Field | What it is | Normalisation |
|---|---|---|
| `invariant` | the charter invariant or gate family it violates | `AG`/`SG`/`ET`/`CG` + number where known, else the invariant's number |
| `path` | the JSON path, DB column, or file:symbol | array indices collapsed to `[]`; run ids, entity ids, e_ids, uuids stripped |
| `locus` | where in the pipeline it lives | one of `package · synthesis · submit · promote · serve · render` |
| `verb` | what went wrong | one of `discarded · fabricated · unchecked · miscited · misgrained · leaked · stale · unreachable` |
| `surface` | the page/section, where it has one | `overview.findings`, `heatmap.cell_evidence`, … |

Two sightings are the same finding when `invariant`, `verb` and the normalised
`path` agree. They are the same **class** — a cluster — when `invariant` and
`verb` agree and the paths differ. That distinction is the whole mechanism:
same path is a recurrence, different path is a class.

`python scripts/triage.py findings.json` computes all of this and prints the
clusters. It does the counting; you do the naming.

## Naming a class

A class name is **12–30 words** and it states the two points the defect lives
between. Not what the symptom looked like — where the gap is.

> A required contract field is validated at submit and silently discarded at
> promotion, because the writer spec has no column for it.

> A count is asserted on the payload and never re-derived at read, so it drifts
> from the register it claims to summarise.

> A cell id resolves in the workbook and belongs to another sub-vertical, so it
> passes every per-cell gate and renders on the wrong institution's grid.

Read those again and notice what they do: **the two points name the rung.**
"validated at X, discarded at Y" is a gap between two mechanisms, so the fix is
a sweep that resolves X against Y — R3 or above, and never a paragraph asking
people to remember. "asserted and never re-derived" names a stored value that
has a source of truth, so the fix is to stop storing it — R5. A class name that
does not contain two points is not finished; you have described a symptom.

Bad names, and what is wrong with them:

- *"Fields go missing"* — no points, no mechanism, no rung.
- *"The producer should be more careful with roadmap fields"* — names a culprit,
  and culprits cannot be fixed at any rung.
- *"`platform.roadmap.sequencing_basis` is dropped"* — that is a sighting, not a
  class. It is one path. The class is what it shares with the other four.

## Mind the grain

The recurrence that matters most in this build was not a new class. It was the
same class **one grain down**.

`CG-13` swept every required *section* field against the writer spec and closed
five sightings. It could not see the *item* level at all — the keys a section's
item shape declares in prose (`Per issue: {…}`) were never resolved against the
writer's `item:` bindings. So `context.issue_register.issues[].capped_subcap_ids`
was validated at submit and dropped at promotion for exactly as long as that
hole existed, alongside the finding's anchor score, the opportunity tile's
headline and the stack row's verification date — a further ten instances of a
class that was already considered closed.

The lesson is a question to ask every time you mechanise a class:

> **What is the level below the one this check sweeps, and does the same defect
> live there?**

Section has items. A run has pages. A table has columns and a column has a
type. A test has assertions and an assertion has a fixture. If the level below
exists, either sweep it in the same check or record an open finding saying you
did not — never leave it to be re-discovered by a client reading an empty card.

There is a second edge on the same blade. When the item shape is stated in
prose and read by a regular expression, a section whose lead-in noun is not in
that expression **opts out of the sweep silently**. That is why the census
treats an unparseable shape as a FAILURE and not a skip. Any check whose input
it might fail to parse must fail loudly on the parse, or it will report green
over the sections it never looked at.

## Ordering the work

Order clusters by, in this order:

1. **Recurrence depth** — a class whose fix has already failed once outranks a
   new class with more sightings. It is telling you something about your own
   rung choices.
2. **Client reach** — did it render, or could it? A defect a client read
   outranks one caught at submit.
3. **Sighting count** — the tie-break, and the weakest of the three. Sighting
   count is partly a measure of how often that surface gets audited.

Work the top of the ranking and say where you stopped. A run that opens six
clusters and finishes two has left four half-landed structural changes, and a
half-landed structural change reads as closed to everyone who comes after.
Finish fewer.

## When a cluster is not a cluster

Three sightings can share a fingerprint and still be three problems. Before
committing to one structural change, argue the other way once: is there a
single mechanism whose repair fixes all three, or are they three mechanisms
that happen to fail the same way? If you cannot name the one mechanism, you do
not have a class — you have a theme, and a structural change against a theme
lands somewhere general enough to catch nothing.
