# dma-rectifier

The part of the DMA system that remembers.

```
SKILL.md              the seven-step protocol, the ladder, the refusals
01-loop/              memory first · clustering · the ladder · closing
02-inputs/            where findings come from · the memory tool contracts
03-worked-example/    one real class, sighting to rung, end to end
04-routine/           the weekly Routine's spec — hand it to create_trigger
scripts/              drain_local.py · triage.py · rung.py
templates/            finding.schema.json · refinement.schema.json · run_report.md
```

## What it is for

Findings arrive from six places and none of them remembers the others: a
verifier in one session, a reviewer clicking REJECT in the web app on Tuesday,
a nightly CI failure on Thursday, a producer repairing the same verdict for the
fourth time without knowing it is the fourth. Each is handled, each is
forgotten, and the same defect class ships again under a new field name.

This skill reads the connector's findings store **before** it acts, groups
sightings into defect classes, decides how far upstream each class deserves to
be fixed, changes the skills, agents and gates accordingly, and records what it
changed against what it closed — so the next run can ask whether the fix held.

## The four properties

1. **Reads memory first.** STEP 0 is a handshake with the connector's memory
   tools and it refuses to continue from the transcript when they do not answer.
2. **Clusters before it fixes.** Identity is a fingerprint, not the text.
3. **Knows where a fix belongs.** Five rungs, prose to schema constraint; a
   recurrence lands strictly above the rung that did not hold.
4. **Refuses to close what it cannot verify.** A resolve needs a check that
   passes on the fixed state and **fails** on the state that produced the
   finding.

## Related

`${CLAUDE_PLUGIN_ROOT}/agents/rectifier.md` is the agent that runs this skill and is defined by what
it refuses. `04-routine/1-weekly-routine.md` is the scheduled trigger's spec —
cron, prompt, and the nothing-to-do branch written out in full.
