# Worked example — the fields that were validated and then discarded

One real class from this build, traced end to end: five sightings, four
migrations, one census sweep, and a recurrence one grain down that moved the
rung again. Every artefact named here exists in the repository and can be read.

**The class, in one sentence:**

> A required contract field is validated at submit and silently discarded at
> promotion, because the writer spec has no column for it.

It is in the store's taxonomy under that name —
`CONTRACT_FIELD_DISCARDED_AT_PROMOTION`, seeded by migration 0035. Call
`list_defect_classes` and read its TELL and its PROBE before filing anything
that looks like it; the probe is a check you can run against a suspicion before
you have a finding at all.

Note the two points — *validated at submit*, *discarded at promotion*. That is
what a class name has to contain, and it is what tells you the rung before you
have written a line of code.

## The five sightings

Each was found on its own, fixed on its own, and read as a one-off.

**Sighting 1 — the leadership contact route** (`migrations/versions/0018_leadership_contacts.py`).
The leadership panel showed "Email · LinkedIn hidden until enriched" on every
row, forever, under real client names. `overview_leadership` had no column for a
contact route, so whatever the producer sent was validated and dropped. Fixed by
adding five columns. Recorded as a leadership-panel bug.

**Sighting 2 — `context_sentiment.context_tiles`** (`migrations/versions/0020_c4_context_tiles.py`).
The contract's only defined field for C4 had no column; the DDL instead mirrored
`overview_sentiment`. So whatever a producer submitted for C4 was discarded at
promotion, and the Context sentiment card rendered a **hardcoded prototype
fixture** — Glassdoor 3.8 (n=412), App Store 3.4 (n=8,200), a CFPB index of 24 —
under a real client's name, with evidence chips that opened a drawer saying the
id does not resolve. Fixed by authoring C4's own shape. Recorded as a
contract/DDL mismatch.

**Sighting 3 — `techstack.dropped`.** A product the scan surfaced that the
taxonomy had no home for: the best available signal that the taxonomy needs a
new category, discarded at promotion, so the signal stayed invisible across
every client.

**Sighting 4 — `overview.evidence_coverage.mix_implication`.** The sentence
saying what the tier and claim mix *means* for confidence. The histogram beside
it is shape; this is the reading, and O11's whole argument lives in it.

**Sighting 5 — `platform.roadmap.sequencing_basis`.** Why *this* ordering rather
than another. The phases were stored and their basis was not, so the roadmap
rendered an order with no argument for it — and every recommendation's
`sequencing_reason` had to agree with something the run could not keep.

Five sightings. Four different pages. Two different migrations' worth of
one-at-a-time repair before anyone wrote the sentence at the top of this file.

## What each one-at-a-time fix cost

Nothing much, individually. That is the trap. Each fix was small, correct, and
shipped; each closed one finding and prevented nothing; and the sixth field was
already in the contract waiting to be discovered by a client reading an empty
card. Ten patches close ten findings. One structural change closes ten and makes
the eleventh unshippable.

## Naming the class, and choosing the rung

The class was finally named while fixing sightings 3–5 together, and the name
made the rung obvious. The defect lives between two artefacts that **both
already exist**: the contract (`contracts_data.json`, which says a field is
required) and the writer spec (`writer_spec.json`, which says which column
promote writes it to). Nothing resolved one against the other. So the fix is not
a rule telling anyone to remember — it is a sweep.

| Rung considered | Verdict |
|---|---|
| R1 prose: "check the writer spec has a column" | Rejected. Five sightings say a reader is exactly what this depends on and exactly what fails |
| R2 exemplar | Rejected, same reason |
| **R3 a sweep in the connector's own test suite** | **Chosen.** Both inputs are data already in the repository; a test can resolve every required field against every writer column on every CI run |
| R4 a gate at submit | Wrong reach. A gate reads the payload; this defect is in the *spec*, and a payload that fills a doomed field looks perfect |
| R5 a constraint | Wrong shape. The writer spec is data, and some required fields legitimately have no column because they are recomputed at read |

That last line is the subtlety that makes the check honest. Not every unstored
field is a defect. `techstack.layers` is a rollup over the item rows; a column
would be a second answer free to disagree with the rows beneath it, which is
what invariant 8 exists to prevent. So the sweep needed a register of
**deliberate** absences with the source each is recomputed from — which is why
`COMPUTED_AT_READ` in the test names a source per entry rather than listing
exemptions. An exemption list would have let the next real defect be added to it.

## The refinement

```
target_kind: TEST                      ← R3, in the store's vocabulary
target:      apps/mcp/tests/test_field_census.py::
             test_a_required_field_is_either_stored_or_deliberately_computed
change:      "Sweep every required contract field against the connector's
              writer spec; record deliberate absences with the source each is
              recomputed from."
applied_by:  rectifier
finding_ids: [the five sightings above]
commit_sha:  2aa7047
relation:    CLOSES
rationale:   "RUNG: R3 — resolves every required contract field against the
              connector's own writer spec on each CI run, so the catch depends
              only on CI running rather than on a reader remembering."
verification:"pytest apps/mcp/tests/test_field_census.py passes on HEAD; run
              against `git show <pre-0023>:apps/mcp/dma_mcp/writer_spec.json`
              it FAILS, naming techstack.dropped, mix_implication and
              sequencing_basis by path."
```

`record_refinement` with that payload closes nothing on its own — five separate
`resolve_finding(finding_id, "REF-…", verification)` calls do, and the
refinement argument is under a database CHECK so there is no way to skip it.

Its failure message names the class rather than the instance, which is what
makes it teach:

> CG-13: required contract fields with no column and no recorded reason — each
> is validated at submit and then discarded at promotion: …

The sweep found **nine** unstored required fields on its first run. Seven turned
out to be deliberate and now say so, with their source, in the test. Two were
the same defect the registry keeps producing. Sightings 3–5 were closed by it,
and 1 and 2 retroactively — they cannot recur.

## The negative control

`git show <sha>:apps/mcp/dma_mcp/writer_spec.json` from before 0023, run through
the sweep, must name `techstack.dropped`, `mix_implication` and
`sequencing_basis` by path. It does. Without that step the sweep might have been
iterating an empty collection and reporting green — the commonest way a check
closes nothing while looking convincing.

## The recurrence, and why it moved the rung again

CG-13 swept every required **section** field. It could not see the **item** level
at all: the keys a section's item shape declares in prose (`Per issue: {…}`) were
never resolved against the writer's `item:` bindings.

So `context.issue_register.issues[].capped_subcap_ids` was validated at submit
and dropped at promotion for exactly as long as that hole existed — and with it
the finding's anchor score, the opportunity tile's headline and the stack row's
verification date. `migrations/versions/0027_promotion_field_gaps.py` opens
"One defect, ten instances."

Read against `01-loop/4-closing.md`'s three recurrence kinds, this is the middle
one and not the first: **the rung was right, the scope was wrong.** The check
existed and did not fire, because it swept one grain and the defect had moved a
grain down. The response is therefore to widen the same rung, not to write
guidance — writing guidance would have left the hole precisely where it was.

Two changes landed:

1. **The same test one level down** — every item key declared in a section's item
   shape resolved against the writer's `item:` bindings, with its own register of
   deliberate absences.
2. **An unparseable shape became a FAILURE, not a skip.** The item shape lives in
   prose and is read by `validation2._PER_ITEM_RE`, which recognises the lead-in
   by noun. A section whose noun was missing from that list opted out of *both*
   the census and AG-03's citation check, silently — which is what `Per issue:`
   itself had done. A check that cannot parse its input must fail loudly, or it
   reports green over everything it never looked at.

The second change is the more valuable of the two, and it generalises: **any
check with a parser has a silent-skip failure mode**, and that mode is the one
which produces a green run over an unswept surface.

## What to take from this

- Five sightings is four too many. The class was nameable at the second.
- The class name contained the rung. "Validated at X, discarded at Y" is a gap
  between two existing artefacts, and a gap between two existing artefacts is
  always a sweep.
- The exemption register names a **source** per entry, not a permission. That is
  what stops it becoming the place future defects are filed.
- Ask what the grain below looks like. The recurrence was not a new class; it was
  this one, one level down, invisible to the check written for the level above.
- Prove the check fails on the broken state. It costs one `git show`.
