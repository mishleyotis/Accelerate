# Closing — what resolve costs, and what recurrence means

A finding is not resolved because a file was edited. Editing a file is evidence
that someone had an opinion about the finding. Resolution is a claim that the
defect cannot recur unnoticed, and that claim needs a check behind it.

## The three conditions

```
resolve_finding(finding_id, refinement_id, verification="")
```

The refinement argument is **required and the column is under a CHECK**, so
there is no way around it. That constraint is this skill's central rule already
sitting at rung 5: without it, "did the fix hold?" has no subject. Note also
that `record_refinement` closes nothing on its own — two calls, deliberately,
because "changed" and "fixed" are two claims and only the second can be wrong
later.

A resolve is legitimate only when all three of these hold:

**1 · The check exists and is named.** A file path and a test or function name,
or a gate id, or a constraint name. Not "the skill now says". If the rung is R1
or R2 there is no check, and therefore **there is no resolve** — an R1 or R2
refinement is recorded, the finding stays open, and it closes when a later run
mechanises it or when the class goes quiet for long enough that the store's own
recurrence tracking closes it by silence. This is deliberate. A class fixed with
a paragraph is not closed; it is untested.

**2 · The check passes on the fixed state.** Run it. Paste the outcome into the
refinement, not a description of the outcome.

**3 · The check FAILS on the state that produced the finding.** This is the
negative control, and it is the condition that gets skipped.

## The negative control

Reconstruct the broken state and run the new check against it:

- the original payload from the verdict, or the finding's recorded excerpt;
- the pre-fix file, via `git stash`, a worktree, or `git show <sha>:<path>`;
- a fixture written to exhibit the defect, committed beside the check.

It must fail. If it passes on both the broken and the fixed state, the check is
checking something else, and the finding is not closed however green the run
looks. This failure mode is common and quiet: a sweep that iterates an empty
collection passes; an assertion whose subject is `None` passes; a regex that
never matches reports no violations.

Record it explicitly, in the refinement's `verification` — both directions in
one sentence, because that is the field a later run reads:

> `pytest apps/mcp/tests/test_field_census.py` passes on HEAD; run against
> `git show <pre-0023>:apps/mcp/dma_mcp/writer_spec.json` it **fails**, naming
> `techstack.dropped`, `mix_implication` and `sequencing_basis` by path.

A `verification` that says only that the check passes has recorded half the
control, and it is the half that proves nothing. There is no third option where
you were confident. `scripts/rung.py` blocks a `relation: CLOSES` whose
verification does not state both directions.

**A check with no negative control is the same defect class as a gate registry
naming a field the contract does not declare** — it polices nothing, silently,
forever, and everyone downstream believes it does. That is a finding about your
own work, and it goes in the store like any other.

## Never fix the check instead of the defect

If a check fails and the response is to change what the check expects, stop. The
only legitimate reasons to change a check's expectation are:

- the expectation was wrong against the authority order — and then the finding
  is about the check, cite the doc and the clause;
- the contract genuinely changed by adjudication — and then the adjudication is
  the citation.

"It was failing and now it passes" is not a resolution, it is a suppression, and
the store cannot tell the difference unless you say so. When you do weaken or
narrow a check, record it as a refinement with `rung=R3, direction=narrowed` and
the reason — so a later recurrence can find the moment the net got smaller.

## Recurrence

A recurrence is a sighting whose fingerprint matches a finding that a refinement
already closed. It is the most valuable single row in this store, because it is
the only direct measurement of whether this loop works.

```
report_recurrence(finding_id, measurement, reported_by,
                  after_refinement="", …) → {…}
```

Report it through the tool. Not in prose, not in the report only — the store's
job is to know that a fix did not hold. It records the recurrence against the
refinement **by name**, returns the finding to `RECURRED`, and flips that
refinement's `held` to false in the digest, which is what makes the next run
choose a higher rung without re-deriving the history.

`measurement` is required with the same 30-character floor as a finding: a
recurrence claim is only as good as the measurement that saw it come back. And
if the finding was never resolved by a refinement, the tool refuses and sends
you to `record_finding` — nothing can have failed to hold. Recording a live
recurrence as a fresh finding instead severs exactly the link this loop is
built on, which is why `record_finding` warns you when the defect is already
RESOLVED rather than quietly opening a second row.

Then read it properly, because three different things produce a recurrence and
they have different fixes:

| What happened | Signal | Response |
|---|---|---|
| The rung was too low | previous rung R1/R2, the guidance exists and was not followed | Move up. Mechanise. |
| The rung was right, the scope was wrong | previous rung R3/R4, the check exists and did not fire on this instance | Widen the same rung — usually a grain below, or an input the check silently could not parse |
| The rung is at its ceiling | the refinement recorded a ceiling and a reason | Not a rung failure. Add or improve detection, and record that the ceiling still holds |

The middle row is the one that looks like the first. A check that exists but did
not fire reads exactly like guidance that was ignored, and the difference is
found by running the existing check against the new instance. Do that before
concluding anything: if the check passes on a genuine instance of the defect, you
have a scope defect, and writing new guidance would leave the hole exactly where
it is.

## Closing by silence

A class can also close by going quiet. If a finding has had no sighting for a
defined window while the surfaces that would produce it have been exercised, the
store may close it — but only when the second half of that sentence is true.
"No sightings" during a period when nothing ran is not evidence, in the same way
that a `deployed-app-auditor` UNVERIFIABLE is not a PASS. When you close by
silence, record what was exercised in the window; a run that cannot say what was
exercised leaves the finding open.
