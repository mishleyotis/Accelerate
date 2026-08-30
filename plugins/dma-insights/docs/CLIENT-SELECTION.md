# Choosing the client: the owner names it, the Routine never does

**Status:** specification. The rule and the guards are LIVE; the Slack channel
is DESIGNED and NOT BUILT, and this document says which is which in every
section, because a spec that reads as a description of working software is
how a gap survives a handover.

---

## 1. The rule

> **A Routine fires on a schedule. A client is chosen by a PERSON, or by a
> gate that knows what is pending. A Routine that names a client is a defect.**

A Routine has no way to know which client matters this week. Pinning one into
its prompt produces that client forever, produces nothing once it is done, and
cannot be pointed at the client the owner actually wants without editing a
stored prompt in a web UI. `dma-synthesis-shore-united` said it in its own
hard rules — *"this Routine produces shore-united-bank-n-a and nothing else"* —
and it also pinned the gold standard's run id, which is superseded the next
time that client is produced.

### What is true today (LIVE)

| Routine | how it chooses its client |
|---|---|
| `dma-synthesis-sequence-a` | `run_gate.py pick` — the gate decides |
| `dma-synthesis-sequence-b` | `run_gate.py pick`, the cycle's second client |
| `dma-refresh-drift-daily` | `list_pending_runs` + a drift scan |
| `dma-watchdog` | client-agnostic: it sweeps runs, not clients |
| `dma-rectification-weekly` | client-agnostic: it works findings |
| `dma-assessment-intake` | scans the intake tree for unstarted folders |
| the four Cloud Scheduler jobs | take no client argument at all |

`dma-synthesis-shore-united` was the only pinned Routine and was deleted from
the routines UI on 2026-08-20.

### The guards (LIVE)

`scripts/tests/test_routine_prompt_commands.py` refuses a live prompt that
names either:

- **a client display_id** — matched as a SHAPE (lowercase, hyphenated, ending
  in an institution word), not as a list of the clients we have met, because
  a deny-list passes the next one;
- **a run uuid** — point at `fixtures/gold_manifest.json`, which names the
  current exemplar, never at a run that will be superseded.

`--client <display_id>` is the correct shape and does not match.

### What is NOT yet true, and is the real gap

There is **no owner-names-the-client channel at all**. `run_gate.py pick` has
no `--client`; its one human lever, `--prefer`, is documented as never passed
by any Routine. So the owner can stop a Routine, and can edit a stored prompt,
but cannot say *"do Alliant next"* through any interface that exists. Section 3
is that channel, and it is not built.

---

## 2. Duplicate runs: versioned inside the folder that already exists

**Status: LIVE.**

A second run for the same client does **not** get a second folder. It
supersedes the package in the folder that is already there, and the one that
was there is kept.

```
Alliant Credit Union - DMA/          <- the folder, name never changes
  DMA_Scoring_Workbook_…_2026-08-30.xlsx   the CURRENT package, at the root
  Client_Profile_Research_…_2026-08-30.docx  where every reader already looks
  DMA_Assessment_Report_…_2026-08-30.docx
  Technographic_Scan_…_2026-08-30.docx
  run_manifest.json
  01_evidence/…
  _superseded/
    R-2026-0114_2026-01-15/          <- the previous run, whole
      …its four deliverables, its own manifest…
      SUPERSEDED.json                <- run_id, superseded_by, superseded_at
```

**Why this shape and not another.** The system already versions runs, and it
does it server-side, not with folders: an entity has N runs, exactly one
active (`runs_active_uq`), and promotion demotes its predecessor to
`SUPERSEDED` and RETAINS it — which is the charter's own default for
superseded runs. This mirrors that on the folder rather than inventing a
second scheme.

**Why the folder keeps its name.** `runs.source_folder_id` keys on the folder.
Renaming it, or forking a second one, orphans every run that came before.

**What it replaced.** Until 2026-08-30 a second run silently MERGED into the
first: `open_folder` reported `created: false` and overwrote `run_manifest.json`
with the second run's identity, `package` copied the second run's deliverables
in beside the first's and overwrote all three fixed-name machine extras, and —
because deliverable filenames carry the reference date — a second run on a
different date left TWO scoring workbooks in one folder. The app's package scan
keeps exactly one artefact per kind, chosen by rank and then by iteration
order. The folder became a mix of two runs with an arbitrary winner.

**The archive is invisible to the scan.** `job_main.ARCHIVE_SEGMENT` skips any
path under `_superseded`, so a retained workbook can never be chosen over the
current one. Retention that created ambiguity would defeat itself.

---

## 3. The Slack channel: the owner names the client

**Status: DESIGNED, NOT BUILT.** No Slack surface exists anywhere in this
repository today — no script, no webhook, no handler. What follows is the
contract for building one, written against the interfaces that DO exist.

### 3.1 What it is for

One thing: **letting a person say which client to assess, and getting an answer
back.** Not a chat interface to the pipeline, not a place to approve gates, not
a second way to run the skill. Every one of those is a larger surface with its
own failure modes, and the owner's problem is narrower — the schedule decides
what happens and nobody can decide *who it happens to*.

### 3.2 The three commands

| what the owner types | what it does |
|---|---|
| `/dma queue` | lists the clients the gate would pick next, in order, with why each is eligible — nothing is started |
| `/dma run <client>` | puts that client at the head of the queue for the next synthesis firing |
| `/dma status [<client>]` | the run's state, its gate verdicts, and the health of every Routine |

`/dma run` **requests**, it does not fire. A Slack message that starts a two-hour
run synchronously is a Slack message that times out, and a request that lands in
a queue is one the next scheduled firing picks up whether or not the person is
still watching.

### 3.3 Where the request lands

A **request file in the intake tree**, beside the client folders the whole
system already reads:

```
General DMAs/_requests/<iso8601>_<display_id>.json
  { "display_id": …, "requested_by": …, "requested_at": …,
    "reason": …, "slack_channel": …, "slack_ts": … }
```

Not a database table, and deliberately: the routines already authenticate to
Drive under the service account, `drive_fetch.py` already lists and pulls that
tree, and a request that lives where the packages live needs no new credential,
no new network path and no new failure mode. `slack_ts` is carried so the
answer can be threaded onto the question.

### 3.4 What the Routine does with it

One change to `run_gate.py pick`, and it is the change the gap needs:

```
run_gate.py pick [--requests <dir>]
```

- read the request files oldest-first;
- a request whose client is **eligible** (a vetted package, no active run,
  not already served without a refresh due) is picked, and its file moves to
  `_requests/_taken/`;
- a request whose client is **not** eligible is answered with the reason and
  moved to `_requests/_refused/` — never silently dropped, because a request
  that vanishes is indistinguishable from one nobody read;
- with no requests, `pick` behaves exactly as it does today.

The Routine prompt still names no client. It names the request directory.

### 3.5 What answers back

The Routine that acts on a request replies in the thread it came from, using
`mcp__Slack__slack_send_message` with the carried `slack_channel` and
`slack_ts`.

**That tool is deliberately NOT auto-approved today**, and whoever builds this
must approve it in the same change that builds the sender. A send publishes to
an external surface: it reaches people and it is not retractable, so it is
recorded in `_DELIBERATELY_PROMPTING` rather than inheriting a blanket allow
from this document merely naming it. Until that decision is made, a scheduled
firing that calls it stops on a permission prompt nobody can answer — the
exact failure that abandoned `dma-refresh-drift-daily`. Build the approval and
the sender together, or the channel's answer path is a hang.

Three replies, and no others:

1. **taken** — client, run id, and the expected finish (`engine.cost schedule`
   prints it: ~97 minutes at the measured shape);
2. **refused** — the eligibility reason, verbatim from the gate;
3. **finished** — the six-page state, the gate verdicts, and the client folder
   link.

Anything else belongs in the run's own record, not in a chat message.

### 3.6 What must NOT be built into it

- **No approval flow.** A gate that a person can wave through in Slack is a
  gate that will be waved through in Slack.
- **No prompt editing.** The whole point is that the prompt stops naming
  clients; a channel that edits prompts re-creates the defect with a nicer
  interface.
- **No credentials in the channel.** The service account authenticates the
  Drive path; Slack carries a client name and a reason.
- **No second scheduler.** `/dma run` requests; the existing Routines fire.

### 3.7 Before it is built

`routine_health.py` already reports what `/dma status` would report, from a
`list_triggers` response, and `readiness.py` composes it with the other seven
lanes (`docs/PRODUCTION-READINESS.md`). Whoever builds the channel should
call those rather than re-deriving them, so the two cannot disagree about
whether a Routine is healthy.

---

## 4. Production readiness of the Routines themselves

**Status: LIVE checker, two open items that are not code.**

`python3 scripts/routine_health.py --file <list_triggers output> --strict`

reports a VERDICT per Routine with the next move, not a status word, because
the two failure classes this project has actually met need completely different
responses:

| verdict | what it means |
|---|---|
| `HEALTHY` | last run SUCCEEDED |
| `IN_FLIGHT` | PENDING inside two of its own intervals — running, not stuck |
| `FAILED` | read the session's `post_turn_summary` FIRST: the one measured instance was a spend limit, not a defect |
| `ABANDONED` | check `pending_action`: a connector prompt the plugin's hook allows means the hook did not RUN — a stale install, which a session cannot heal because hooks bind once at session start |
| `PENDING` | outlived two of its own intervals: an ABANDONED nothing reclassified |
| `DISABLED` | paused; not broken, and not doing anything |

Measured 2026-08-30: 3 healthy, 1 in flight, 2 needing attention.
