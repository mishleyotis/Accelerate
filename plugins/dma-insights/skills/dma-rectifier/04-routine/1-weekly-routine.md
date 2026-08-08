# The weekly rectification Routine

The specification for the scheduled trigger. **This file does not create it** —
it is the exact spec to hand to `create_trigger`, and the parameters below are
final rather than illustrative.

## The parameters

```
name:        DMA weekly rectification
cron:        0 13 * * 1                       # UTC — Monday 13:00
mode:        create_new_session_on_fire = true
environment: the environment holding the DMA Insights checkout with the
             dma-insights@zennify-dma plugin enabled
model:       opus
notifications: {push: true, email: true}      # fresh-session mode supports these
prompt:      the standalone instruction below, verbatim
```

Fresh session per firing, not a bound session. A bound session would carry a
transcript from week to week, and a rectifier that remembers its own last run
in-context is precisely the thing this design refuses — memory is the store, and
the run must prove it can read the store rather than inheriting a summary. A
fresh session also forces STEP 0 to be real every week.

## Why Monday 13:00 UTC

**Weekly**, because the unit of value is a defect *class*, and a class needs
several sightings to become visible. A daily run sees one sighting and patches
it, which is the queue behaviour this skill exists to replace. A monthly run
lets a class ship four more times.

**Monday** because the window it reads is then a complete, closed week
(Monday 00:00 UTC to Monday 00:00 UTC), and because refinements land before the
week's production runs rather than into the middle of them. A Friday run would
land skill changes that sit unreviewed over a weekend and are first exercised by
whoever starts on Monday without having read them.

**13:00 UTC** is 06:00 America/Los_Angeles during PDT — before the US working
day, so a refinement is reviewable when the maintainer arrives rather than
arriving mid-flight. It also sits after Sunday night's `corpus-gate-scanner` and
`pack-exporter` nightlies, so the week's final CI signal is already in the store
when the window is read.

Cron is UTC and does not follow daylight saving: from early November this fires
at 05:00 local instead of 06:00. That is stated rather than corrected — it is
still pre-workday, and a Routine that drifts by an hour twice a year is better
than one whose schedule nobody can predict from its cron line. Changing it means
editing the cron, not adding logic.

## What it reads

1. The connector's tool listing, and `list_open_findings` — the handshake.
2. Open findings sighted in the closed window, plus **every open finding with a
   recurrence**, regardless of window. A recurrence does not age out; it is the
   loop's own error signal.
3. For each cluster it opens, the prior refinements against its findings — which
   rung was tried, whether it held.
4. The repository working tree, for the local channel drain and for the artefacts
   it is about to change.

## What it does

The seven steps in `SKILL.md`, in order, with one addition specific to running
unattended: **a budget**. Open at most three clusters, and finish every one you
open. A half-landed structural change reads as closed to everyone who comes
after, and an unattended run has nobody to notice.

## What it writes back

| Where | What |
|---|---|
| the findings store | a refinement per change; a resolve per finding actually closed; a recurrence report per fix found not to have held; new findings for anything drained from the local channel |
| the repository | a branch and one commit per cluster, named paths only, message naming the class and the finding ids it closes |
| the run report | `templates/run_report.md`, attached to the notification |

It opens a PR; it does not merge one. Skills and agents are read by every future
session, and a change to them with no human in the loop is a change nobody
reviewed being executed by everybody. The exception is nothing — including
"the change is obviously correct".

## When there is nothing to do

Say so and stop.

```
No open findings above threshold in the window <from>–<to>.
Handshake: <n> tools, <open_count> open findings, newest sighting <date>.
Local channel: empty.
Nothing changed.
```

Record the run as examined-and-empty in the store so the next run can tell "the
window was read and held nothing" from "no one looked" — the same distinction
`deployed-app-auditor` draws between PASS and UNVERIFIABLE, and for the same
reason: a report that reads green because nobody looked is worse than no report,
because it will be believed.

Explicitly forbidden on an empty week:

- lowering the threshold until something qualifies;
- scanning the codebase for defects nobody sighted, and recording them as
  findings — a finding is an *observation*, and inventing them corrupts the
  sighting counts that every rung decision depends on;
- writing a refinement for a finding that does not exist;
- "tidying" a skill. An edit with no finding behind it is a preference.

An empty week is the system working. It should be the most common outcome once
the ladder is being used properly, and a run of empty weeks followed by a
recurrence is exactly the signal the store exists to produce.

## The prompt to give `create_trigger`

Standalone — each firing starts from nothing.

```
Load the dma-rectifier skill and run one weekly rectification cycle.

Window: the closed week ending at the most recent Monday 00:00 UTC. Also
include every open finding carrying a recurrence, whatever its age.

Follow the skill's seven steps in order. STEP 0 is a real handshake: if the
connector's memory tools are absent or do not answer, stop, report "memory
unreachable — no rectification performed", and change nothing. Do not work
from anything else.

Budget: open at most three clusters and finish every one you open. Order by
recurrence depth, then client reach, then sighting count.

Every change needs a finding behind it. Every resolve needs a refinement, a
check that passes on the fixed state, and a negative control proving that
check fails on the state that produced the finding. A recurrence lands
strictly above the rung its previous refinement landed on.

Write back through the memory tools: record_refinement, resolve_finding,
report_recurrence. Then open a PR on a branch with named paths only, one
commit per cluster, each message naming the class and the finding ids it
closes. Do not merge it.

If there is nothing above threshold: say so, record the run as
examined-and-empty, and stop. Do not lower the threshold, do not scan for
defects nobody sighted, and do not tidy anything.

Report: the handshake numbers, the clusters you opened and the rung each
landed on with its reason, what you closed and the negative control for each,
what you left open and the rung it is waiting on, and the PR link.
```
