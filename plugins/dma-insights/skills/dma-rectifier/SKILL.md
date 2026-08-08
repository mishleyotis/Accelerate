---
name: dma-rectifier
description: Turn accumulated DMA findings — QA agent reports, failed verdicts, reviewer Accept/Reject on insight cards, CI failures, production audit FAILs — into durable improvements to the DMA skills, agents and gates. Use this skill whenever the user mentions rectification, refining a skill or agent from feedback, "why does this keep happening", a recurring defect, a regression that came back, closing out a QA issue register, the weekly refinement routine, or asks what past findings say about a problem in front of them. Also use it whenever a QA agent (adversarial-verifier, package-vetter, deployed-app-auditor) has just reported, whenever a reviewer rejects a card, and before editing any file under plugins/dma-insights/skills or plugins/dma-insights/agents — an edit with no finding behind it is an opinion. If the task is "we learned something, make it stick", this is the skill.
---

# DMA rectifier

Findings arrive from six places and none of them remembers the others. An
adversarial verifier finds a grain violation in one session; a reviewer rejects
an insight card in the web app on Tuesday; the nightly corpus gate scanner
fails in CI on Thursday; a producer repairs the same verdict for the fourth
time and does not know it is the fourth. Each is handled, each is forgotten,
and the same defect class ships again under a different field name.

This skill is the part that remembers. It reads the findings store before it
acts, groups sightings into defect classes, decides how far **upstream** each
class deserves to be fixed, changes the skills, agents and gates accordingly,
and records what it changed against what it closed — so the next run can ask
the only question that matters: **did the fix hold?**

It produces no client content. It cannot submit and it cannot promote.

## Why this is a loop and not a queue

A queue drains. A loop gets better. Four properties separate them, and each
one is a step you can skip without noticing:

1. **It reads memory before it acts.** Every finding is first asked *have we
   seen this before* — semantically and lexically, because the same defect is
   described in different words by a verifier, a reviewer and a stack trace.
   A first sighting and a recurrence are different problems with different
   correct responses.
2. **It clusters before it fixes.** Ten findings that are one defect class
   deserve one structural change, not ten patches. This build's own history is
   the proof and it is the worked example in `03-worked-example/1-discarded-fields.md`.
3. **It knows where a fix belongs.** There is a ladder from prose to schema.
   Choosing a rung is a deliberate, recorded step, not a side effect of which
   file happened to be open.
4. **It refuses to close what it cannot verify.** A finding is not resolved
   because a file was edited. It is resolved when the check that would have
   caught it exists, runs, passes on the fixed state **and fails on the state
   that produced the finding**.

## The cross-session property, and why STEP 0 exists

The requirement is that this loop learns through each run and iteration *in
this session or any other*. That is a claim about where findings live.

They live in the connector's findings store: tables in the same Cloud SQL
database the MCP service already speaks to, reached only through its tools.
Not in a session transcript, not in a scratchpad file, not in a commit message.
The connector is one deployed remote service shared by every session on every
machine, so a finding an adversarial verifier records in a Cowork session at
09:00 is readable by a rectifier run in a Claude Code session at 09:01, and by
next Monday's routine, and by a session that has never heard of either.

Two things make that real rather than aspirational:

- **Findings are recorded at the moment of sighting, by whoever saw them**, not
  summarised at the end of a session. A session that ends without recording has
  taught the system nothing, however good its report was. The QA agents record
  their own; the web app records reviewer verdicts; this skill records
  everything it drains out of the local channel.
- **Recording is idempotent by fingerprint.** The same defect recorded from two
  sessions does not become two rows — it becomes one row with two sightings,
  which is precisely the recurrence signal. Duplicate suppression is not
  tidiness here; it is the measurement.

So **STEP 0 is a handshake, not a formality**. If the memory tools do not
answer, this skill stops. It does not fall back to the transcript, because a
rectifier working from one session's scrollback is a queue processor wearing a
loop's name and it will re-fix things that were fixed in March.

## The run protocol

Written in the form `04-craft/5-prompt-standard.md` requires, because the
weekly routine executes it unattended and an unstepped protocol is one an agent
skims.

```
STEP 0 — HANDSHAKE
  List the connector's tools. Confirm the memory tools are present and answer.
  Call the read side once for real: list_open_findings with a wide window.
  Record what you got: {tools_seen[], open_count, oldest_open, newest_sighting}.
  If the tools are absent or error: STOP. Report "memory unreachable — no
  rectification performed", name the failure, and change nothing. NEVER
  proceed from the transcript. A run that cannot read memory cannot know
  whether anything it is about to do has already been done.

STEP 1 — DRAIN THE LOCAL CHANNEL
  Anything visible only to this session is not yet memory. Sweep the working
  tree and this conversation for feedback that has never been recorded:
  qa_verdict.json, issue_register.csv, connector verdicts, pytest failures,
  auditor reports, the user's own words. `python scripts/drain_local.py <dir>`
  emits one record_finding payload per candidate. Record them BEFORE triage,
  so this run's clustering sees them and the dedup counts them as sightings.
  If none: say "local channel empty" and continue. That sentence is a result.

STEP 2 — SEARCH BEFORE YOU BELIEVE
  For every finding now in scope, ask memory whether it is new. Search BOTH
  ways: semantic (a verifier and a stack trace describe one defect in different
  words) and lexical (a JSON path, a gate id, a field name is an exact token
  and embeddings blur exact tokens). Two searches, union the results.
  Emit per finding: {finding_id, prior_ids[], prior_refinements[], is_recurrence}.
  A finding whose prior refinement exists and whose defect is back is a
  RECURRENCE, and recurrence is reported through the tool, not noted in prose —
  the store's job is to know that the fix did not hold.

STEP 3 — CLUSTER
  Fingerprint, group, name. `python scripts/triage.py findings.json` does the
  mechanical part; you do the naming. A class name is 12–30 words and states
  the two points the defect lives between — "validated at submit and discarded
  at promotion", "asserted on the payload and never re-derived at read".
  Where the two points are IS the choice of rung. Order clusters by
  (recurrence depth, client reach, sighting count), descending; work the top of
  that ranking first and say where you stopped. NEVER open a cluster you cannot
  finish this run — a half-landed structural change is worse than an open
  finding, because it reads as closed.

STEP 4 — CHOOSE THE RUNG
  Per cluster, one rung, chosen deliberately and with a recorded reason of
  15–40 words. The ladder and its rules are in `01-loop/3-the-ladder.md`.
  Two rules bind here and are not negotiable:
    · A recurrence lands STRICTLY ABOVE the rung its previous refinement
      landed on. Rewriting the same guidance more emphatically is the same
      rung, and the store already knows that rung did not hold.
    · A defect that reached a rendered client surface never lands below R3.
      Prose cannot catch what prose already failed to catch.
  If the rung you need is out of reach this run (an R5 needing
  expand–migrate–contract, say), land the reachable rung AND leave an open
  finding naming the rung you could not reach and why. NEVER let "we did
  something" close the class.

STEP 5 — CHANGE, WITH THE FINDING IN HAND
  Edit only artefacts you can name a finding for. Every edit carries, in its
  own text or in the refinement record, the finding ids it answers. An edit
  with no finding behind it is a preference, and preferences are how skills
  drift away from what was measured. Keep diffs small; one cluster per commit.

STEP 6 — GATES: PROVE THE CHECK WOULD HAVE CAUGHT IT
  Before any resolve, the negative control. Run the new check against the state
  that produced the finding — the original payload, the pre-fix file, a
  reconstructed fixture. It MUST fail there. A check that passes on both the
  broken and the fixed state closes nothing and will be believed anyway.
  Then run it on the fixed state; it must pass. Record both outcomes.
  `python scripts/rung.py refinement.json --repo <root>` asserts the claimed
  rung is what actually landed: an R3 claim resolves to an executable check, an
  R4 claim to a gate id in the connector's registry, an R5 claim to a migration
  or constraint. A claimed rung that does not resolve is downgraded to what it
  is, not argued about.

STEP 7 — WRITE BACK
  record_refinement for every change: {rung, artefacts[], check, closes[],
  reason, negative_control}. resolve_finding for every finding the refinement
  actually closed, naming that refinement — the store refuses a resolve with no
  refinement, which is the mechanised form of "no closing without a check".
  report_recurrence for every fix found not to have held.
  Then write the run report from `templates/run_report.md`. Findings you left
  open are part of the report, ordered, with the rung each is waiting on.
```

## The ladder

Five rungs. Higher is better and more expensive, and the whole point of naming
them is that "more expensive" stops being a reason to stay low by default.

| Rung | What it is | Catches it | Cost |
|---|---|---|---|
| **R1** | Prose guidance in a skill or agent file | When read, and remembered | minutes |
| **R2** | A worked example or measured exemplar beside the guidance | When read, reliably — an exemplar is followed where an instruction is skimmed | an hour |
| **R3** | A script or test that checks it locally / in CI | Every run, before submit, unattended | hours |
| **R4** | A connector gate that refuses it at submit or promote | Every submission, for every session, including ones that never read the skill | hours to a day |
| **R5** | A schema constraint, enum, generated column or contract shape that makes it unrepresentable | Never happens again, by construction | a migration |

R1 and R2 depend on a reader. R3 depends on someone running it. R4 and R5 do
not depend on anyone. That is the entire ranking, and it is why a recurrence
must move up: the sighting you are looking at is evidence that the rung you
chose depends on something that did not happen.

Full rules — how to pick, when R5 is wrong, what to do when the rung is out of
reach: `01-loop/3-the-ladder.md`.

## Clustering, and the identity of a finding

A finding's identity is not its text. Two sightings are the same defect when
their **fingerprint** matches: the invariant or gate touched, the normalised
JSON path (array indices collapsed, run and entity ids stripped), the surface,
and the failure verb. `scripts/triage.py` computes it; the normalisation is
what lets `overview.findings[3].score` and `overview.findings[11].score` be one
finding rather than two.

Watch the **grain**. The census class in the worked example was mechanised at
section grain and recurred at item grain, because the sweep resolved the keys a
section declares and never the keys its items declare. Same class, one level
down, invisible to the check written for the level above. When you write a
check, state which grain it sweeps — and ask, out loud, what the level below it
looks like.

Method, the fingerprint fields, and how to name a class:
`01-loop/2-clustering.md`.

## Where findings come from

| Source | Arrives as | Highest signal in it |
|---|---|---|
| `adversarial-verifier` | ranked findings, blocking / material / noted | the attack that came up empty — it tells you which surface is probed |
| `package-vetter` | REFUSE / ACCEPT WITH FINDINGS | a refusal is a finding; a package that should have been refused and was not is a rectifier finding about the vetter |
| `deployed-app-auditor` | PASS / FAIL / UNVERIFIABLE per check | UNVERIFIABLE is not a failure of the auditor — it is a finding about observability |
| `surface-producer` | failed verdicts, repairs, storyline volleys | a verdict repaired more than twice is a class, not a run |
| the web app | an annotation, `anchor_kind=insight_card`, action ACCEPT or REJECT, with the card's text and its `r_layer` | a REJECT whose `r_layer.verdict` was ACCEPT — the reasoning layer accepted what a human reader rejected |
| CI and the schedulers | pytest failures, `corpus-gate-scanner`, `pack-exporter` | a test that had to be changed to pass is a finding about the test |

Reviewer verdicts are the only feedback in this system from a human looking at
a **rendered** surface, and they are internal workflow: annotations are refused
for the customer audience, so their text is internal and any finding quoting a
card body carries `internal_only` on that path. Redaction does not stop at the
serving layer.

The full mapping — what each source's output looks like, which fields become
which finding fields, and how to read an `r_layer` against a rejection:
`02-inputs/1-feedback-sources.md`.

## The memory tools

The contracts this skill was written against are in
`02-inputs/2-memory-tools.md`. Names are **discovered, not assumed**: at STEP 0
list what the connector exposes and map by contract. If a name differs from the
one written here, use the connector's and record a finding about the drift —
a skill naming a tool that no longer exists is exactly the defect class this
skill exists to close.

```
record_finding(finding)     → {finding_id, deduped, sightings}
search_findings(query, mode) → [{finding_id, score, status, refinements[]}]
list_open_findings(filters)  → [finding]
record_refinement(refinement)→ {refinement_id}
resolve_finding(finding_id, refinement_id, check) → {status}
report_recurrence(finding_id, refinement_id, evidence) → {recurrence_count}
```

Findings and refinements carry **provenance**: which agent or surface produced
the sighting, in which session, from which run — so a cluster can be read back
to its origins and a refinement can be attributed. A finding with no provenance
is an assertion; cite the artefact it came from the way a payload cites
evidence, with the path and the excerpt, not a summary of it.

## Register

This skill's output is read by the people who maintain the skills, and it is
also read back by agents at synthesis time. Two rules follow:

- Name the mechanism, not the culprit. "The writer spec has no column for this
  key" is actionable; "the producer forgot" is not, and no agent can act on it.
- A finding states what was observed, where, and what would have caught it. It
  does not state a fix in the finding — the fix is the refinement, and keeping
  them separate is what lets one refinement close six findings.

## Nothing to do is a result

Some weeks there is nothing above threshold. Say so and stop. Record the run as
examined-and-empty so the next run can tell "the window was read and held
nothing" from "no one looked". NEVER lower the threshold to have something to
report, NEVER go hunting the codebase for defects nobody sighted, and NEVER
manufacture a refinement for a finding that does not exist. An empty week is
the system working; a fabricated refinement is a change to a skill with no
measurement behind it, which is the thing this skill exists to prevent.

## The worked example

`03-worked-example/1-discarded-fields.md` traces one real class from first
sighting to the rung it landed on: a required contract field validated at
submit and silently discarded at promotion. Five sightings under four different
field names before anyone named the class; then one census sweep
(`CG-13`, `apps/mcp/tests/test_field_census.py`) that closed all five and made
the sixth impossible to ship. Then the recurrence — the same class one grain
down — which proved the first mechanisation was scoped too narrowly and moved
the rung again. Read it before your first cluster; it is the shape of the job.

## Scripts

```bash
python scripts/drain_local.py <dir>            # feedback in the working tree that
                                               # memory has never seen; emits
                                               # record_finding payloads

python scripts/triage.py <findings.json>       # fingerprint, cluster, flag
                                               # recurrences, and state the minimum
                                               # rung each cluster requires

python scripts/rung.py <refinement.json> --repo <root>
                                               # does the claimed rung resolve to
                                               # something that exists — a check, a
                                               # gate id, a constraint
```

All three are stdlib-only and deterministic. They do the mechanical half; the
naming, the rung choice and the negative control are judgement and stay with
you.

## Reference files

| File | Read it when |
|---|---|
| `01-loop/1-memory-first.md` | Always, before STEP 0 — what the handshake proves and what it refuses |
| `01-loop/2-clustering.md` | STEP 3 — fingerprint fields, grain, how to name a class |
| `01-loop/3-the-ladder.md` | STEP 4 — the five rungs, the recurrence rule, when R5 is wrong |
| `01-loop/4-closing.md` | STEP 6–7 — the negative control, what resolve requires, what recurrence means |
| `02-inputs/1-feedback-sources.md` | Reading a QA report, a verdict or a reviewer rejection into a finding |
| `02-inputs/2-memory-tools.md` | Any memory tool call whose exchange you are unsure of |
| `03-worked-example/1-discarded-fields.md` | Before your first cluster |
| `04-routine/1-weekly-routine.md` | The weekly Routine's spec — cron, inputs, outputs, and the empty week |
| `templates/finding.schema.json` | Writing a finding |
| `templates/refinement.schema.json` | Writing a refinement |
| `templates/run_report.md` | STEP 7 |
