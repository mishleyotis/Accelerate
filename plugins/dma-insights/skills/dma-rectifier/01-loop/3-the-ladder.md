# The ladder — where a fix belongs

Every fix lands somewhere. The question is never *whether* there is a rung, only
whether it was chosen or defaulted to. Defaulting produces R1 every time,
because R1 is where the file you already have open is.

```
R5  a schema constraint, enum, generated column or contract shape
    ── the defect cannot be represented ──────────────── a migration
R4  a connector gate that refuses it at submit or promote
    ── every session, whether or not it read the skill ── hours–a day
R3  a script or test that checks it locally or in CI
    ── every run, unattended, if someone runs it ─────── hours
R2  a worked example or measured exemplar in the skill
    ── when read, and followed ──────────────────────── an hour
R1  prose guidance in a skill or agent file
    ── when read, and remembered ────────────────────── minutes
```

The ranking is not about effort. It is about **what the catch depends on**:

- R1 depends on a reader reading and remembering.
- R2 depends on a reader reading; exemplars survive skimming where instructions
  do not, which is the only reason R2 sits above R1.
- R3 depends on someone running it — which CI can guarantee and a local
  workflow cannot.
- R4 depends on nothing. Every submission goes through it, including from a
  session that never loaded the skill and an agent written next year.
- R5 depends on nothing and cannot be turned off. The state is unrepresentable.

A recurrence is evidence that the thing your rung depended on did not happen.
That is why the recurrence rule is mechanical rather than a judgement call.

## The rules

**1 · A recurrence lands strictly above its previous rung.** If the last
refinement for this class was R1, the next is R2 or higher — and if the last was
R1 and the sighting is the third, go to R3 and stop rewriting sentences.
Rewriting the same guidance more emphatically is the same rung. The store
already recorded that the rung did not hold; more italics is not new
information.

**2 · A defect that reached a rendered client surface never lands below R3.**
Prose did not catch it the first time and the reader who missed it will be
someone else next time. If it rendered, mechanise it.

**3 · Name what the rung depends on, in the reason.** 15–40 words, and it must
answer: what has to happen for this catch to fire? "R3 — a pytest sweep in the
connector suite; fires on every CI run, so it depends on CI running, which the
nightly scanner guarantees." That sentence is what the next run reads when it
is deciding whether your rung held.

**4 · Higher is not automatically right.** R5 is wrong when:

- the value is legitimately absent sometimes — a NOT NULL constraint on a field
  whose honest answer is null converts a correct empty state into a promotion
  failure, which is invariant 9 violated in the other direction;
- the rule needs context the schema does not have — "the excerpt supports the
  sentence that cites it" is not expressible as a constraint;
- it would need a contract break in a system that is expand–migrate–contract,
  where the migration itself introduces a window in which both shapes exist;
- the constraint would encode a decision the charter deliberately leaves open.
  Check the open-decisions list before constraining anything.

R4 is wrong when the rule is about the *package* rather than the payload — a
gate cannot refuse a workbook that was never submitted. Those belong at R3 in
the vetting scripts.

**5 · When the right rung is out of reach this run, land the reachable one AND
leave the class open.** Record the refinement at the rung you reached, record an
open finding naming the rung you could not reach and why, and say it in the run
report. NEVER let "we did something" close a class. A class closed at R2 when it
needed R5 will be back, and it will be back looking like a new finding because
the old one is marked resolved.

## Worked rung choices from this build

| Class | Rung landed | Why that rung |
|---|---|---|
| Required contract field validated at submit, discarded at promotion | **R3** → CG-13 census sweep in the connector's own test suite | The gap is between two artefacts that both already exist (the contract and the writer spec). A sweep resolving one against the other catches every instance including future ones. R5 was wrong: the writer spec is data, and constraining it would not have covered the fields deliberately computed at read |
| The same class one grain down (item keys) | **R3, wider** + parse failure promoted to test failure | The recurrence proved the first R3 was scoped to one grain. Moving up would have meant R4, but a gate cannot see the writer spec; widening the same rung and making unparseable input fail loudly was the actual upstream move |
| A cell belonging to another sub-vertical rendered on a client's grid | **R4** → ET-05 at submit | The producer read the skill and still shipped 59 of them; the rule is checkable from the payload plus the run's own facts, which is exactly a gate's reach |
| M5 / Transformational as a reachable band | **R5** → four-value `band_t` enum + generated column | The state is representable in prose and in a resolver, and it must not be representable at all. A four-branch resolver plus an enum makes the fifth branch a type error |
| Colour in a payload | **R5** → no colour field exists in any contract | Same shape: the fix is that there is nowhere to put it |
| An agent concluding from an unpolled async task | **R2** → the measured exemplar in the enrichment playbook | Not mechanisable from outside the session: nothing downstream can tell a polled empty roster from an unpolled one. R2 is the ceiling here, and saying so is part of the record |

That last row matters as much as the others. Some classes have a ceiling below
R5, and naming the ceiling in the refinement is what stops the next run from
treating the recurrence as a rung-choice failure when it is a reachability
limit. State the ceiling; the recurrence rule then reads "already at ceiling —
the remaining lever is detection, not prevention".

## Detection as a rung of last resort

When prevention has a ceiling, the honest move is to add **detection** and say
that is what you did: a check that finds the defect after the fact and raises a
finding automatically. It does not prevent, so it is not R3 in the preventive
sense; record it as R3 with `mode=detective` and a reason naming what it cannot
prevent. A detective check that feeds this very store is how a ceiling class
keeps producing sightings instead of going quiet and being forgotten.
