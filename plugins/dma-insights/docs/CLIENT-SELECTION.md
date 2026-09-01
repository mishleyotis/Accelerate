# Choosing the client: the owner names it, the Routine never does

**Status:** the rule, the guards and the Slack channel are all LIVE as of
2026-08-30. One manual step is outstanding and section 3.6 names it. Every
section says which of the two it is, because a spec that reads as a
description of working software is how a gap survives a handover — and
because this document spent half a day specifying a channel that already
existed.

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

### What was the gap, and what closed it

There was **no owner-names-the-client channel at all**: `run_gate.py pick` has
no `--client`, and its one human lever `--prefer` is passed by no Routine. The
answer turned out not to be a new interface. The requests were already
arriving in `#deal-desk` from a Slack workflow, and nothing read them —
section 3.

Note which queue is which, because they are easy to confuse and they are not
the same: `run_gate.py pick` chooses which already-ingested client to
SYNTHESISE; the Slack queue chooses which client to ASSESS from scratch. The
intake feeds `research-conductor`, not the gate.

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

## 3. The Slack channel — BUILT 2026-08-30, and not the way this section
## first specified it

**Status: LIVE**, with one manual step outstanding (3.6).

This section used to be a specification for a channel that did not exist:
three slash commands, a request file in the intake tree, a `--requests` flag.
None of that was built, and none of it will be — because the channel already
existed and nobody had looked at it.

> owner, 2026-08-30: *"It should usually prob the Slack channel … check the
> channel for new DMAs … For each message by the workflow, check the thread
> replies to confirm that I did not comment with the specific drive link for
> the delivered assessment."*

The requests do not need a `/dma run` command. They arrive already, from a
Slack workflow, in `#deal-desk`, with everything an assessment needs.

### 3.1 What is actually there

| | |
|---|---|
| channel | `#deal-desk` — `C0AD83KJ4DU` |
| the workflow | *Assessment and Research Request* — bot `B0ACUPDCMGF`, shortcut `Ft0ADDPFSHK6` |
| each request carries | Account Full Name · Website · Additional Context · Submitter · Priority (*Urgent 24h* / *High 48h*) |
| and ends | @-mentioning the owner: *"Please run the maturity assessment and account research, place in the account folder, and reply to this thread with a link to the folder"* |
| **NOT this flow** | *Hubbl Readout Request* — bot `B0ANFBBJ5D3`, same channel, similar shape, **a different person's queue** |

Every one of those identities lives in `scripts/slack_intake.py` and nowhere
else. A prompt that re-typed one would be a second source of truth, which is
the defect section 1 exists to prevent.

### 3.2 Pending, delivered, and the third state

> **DELIVERED** iff a reply in the thread is **from `U09TL2S4LLS`** *and*
> carries a **`drive.google.com/drive/folders/…` link**. Otherwise PENDING.
> Anything that cannot be evaluated is **UNDECIDABLE**.

Each clause is doing work, and the recordings under
`scripts/tests/slack/` are why:

- **not "the owner replied"** — the real Richwood Bank thread has a reply
  from the owner reading *"Let me retrieve it from my desktop."*
- **not "somebody replied"** — the real REV FCU thread's only reply is a
  colleague's *"FYI @Andrew"*.
- **not "there is a Drive link"** — the Hubbl workflow puts one in its own
  request.
- **not a FILE link** — `/file/d/…`, a Doc or a Sheet is not the folder the
  request asked for.

**UNDECIDABLE is the important one.** A request whose thread was not fetched
looks exactly like one nobody answered. Treating it as pending starts a
second assessment of a client who was already delivered, so an unread thread
is never PENDING. The exit codes keep the two apart: `0` there is work, `1`
there is none, `2` something could not be decided.

A resubmitted request — *"Resubmitting as my initial request error'd out"*,
which really happened — does not start two runs: the newest undelivered
request for an account is the live one and older ones read SUPERSEDED.

### 3.3 Why the script cannot call Slack

There is **no Slack credential in this repository** — no token, no key file,
nothing to mint one from. `drive_fetch.py` reaches Drive only because a
service-account key is provisioned; nothing equivalent exists for Slack.

So the work is split: the **session** reads the channel with the connector
tools it carries, and the **script** decides offline over the transcript. The
rule is then testable over recorded fixtures in CI and live in a firing, with
the same code deciding both — the technique `routine_health.py` documents.

```
slack_intake.py threads --transcript <saved>        # which threads to read
slack_intake.py triage  --transcript <saved> --threads <dir>
slack_intake.py request --client "Acme Credit Union"   # the manual path
slack_intake.py reply   --client … --folder-url … --served
```

### 3.4 The manual path

> owner: *"For manual interventions, I give the client name and the
> assessment starts."*

`slack_intake.py request --client "<name>"` emits a record in the **same
shape** as a Slack-borne one — same entity slug, same run-id rule, same
fields — so nothing downstream can tell them apart. A manual run that took a
different code path would be a second pipeline nobody tests.

### 3.5 The reply that closes the thread, and the trap under it

The connector **sends as the owner**, so the completion reply is itself what
makes the request read DELIVERED on the next pass. And `engine.cli start`
opens the client folder at minute one with `status: IN_PROGRESS` — a folder
link is postable long before there is anything in the folder.

`slack_intake.py reply` therefore **refuses to render a folder link without
`--served`**. Posting early would close the thread, drop the request out of
every future queue, and hand the requester an empty folder. There is no
override: a firing that wants to say something before then can say it without
a link, and a message without a link does not close the thread.

The reply is posted by whichever firing sees the run **PROMOTED**, which is
why the run carries `slack_channel`, `slack_thread_ts` and `requested_by` in
its `Run_Metadata`. The request is answered days later, from another
container; the thread has to travel with the run or the answer has nowhere to
go.

**Where it is actually posted — ROUTINES.md § 2a, STEP 3b (LIVE).** The
synthesis routines are the ones that see a promotion, so the reply belongs
to them and not to the intake, whose every firing is by definition before
the work is done. STEP 3b runs after STEP 3 has looked at what production
serves, and it reads the thread rather than being told it:

```
slack_intake.py thread-of --run <run_id>   -> {channel, thread_ts, answerable}
slack_intake.py reply --client "<Account>" --folder-url <url> --served --json
mcp__Slack__slack_send_message              -> that channel_id and thread_ts
```

`answerable: false` means the run records no thread — a manual run, or one
started before the intake carried it — and the routine posts **nothing**.
That is a state, not a failure, and it is distinguishable from a thread the
firing failed to read, which would leave a request open forever.

The channel comes off the run, never off the module constant: a run recorded
against another channel is not answered in `#deal-desk`. The connector sends
as the owner, so a thread id typed by hand is the owner messaging a stranger
— which is why nothing in either prompt types one.

Lane B (`dma-synthesis-sequence-b`) reads lane A's prompt as its
specification and inherits STEP 3b with the rest of it.

**Approval.** This section previously recorded a standing obligation —
*"whoever builds this must approve it in the same change that builds the
sender"* — and that obligation is discharged here.
`mcp__Slack__slack_send_message` is **CONDITIONAL**: allowed into
`C0AD83KJ4DU` and nowhere else, decided from the call's own `channel_id`. Not
blanket-approved, and not denied either — an out-of-scope send draws no
decision, so a person in an interactive session can still send wherever they
meant to. See `docs/CONNECTORS.md § Approval`.

### 3.6 Binding without a human, where there is nothing to decide

**Status: LIVE 2026-08-30** (owner: *"the run should bind to unambiguous
subvertical"*).

The binding question exists because a run bound to the wrong sub-vertical
researches the wrong 851 cells to completion. Where the LOB census leaves
exactly ONE reading there is no judgment left to make, and the question was
ceremony that cost every scheduled firing its purpose — the intake could
prepare a binding and never start one.

`engine.preflight autobind --file <preflight.json>` binds it and says so on
the record. **Unambiguous** is narrow, and every clause is load-bearing:

| clause | why it is there |
|---|---|
| exactly one `ACCEPT` | the thing being decided has one answer |
| at least one `REJECT` | the census actually **considered** alternatives. One candidate, accepted, nothing else weighed is not unanimity — it is a census that never looked, which is what a thin research pass emits |
| at most one MATERIAL line of business | scope across two is the owner's call whatever the candidate list says |

**The flag is never the authority.** `preflight check` recomputes
unambiguity from the census on every call, so `auto_bound: true` written by
hand over a multi-LOB entity is refused with *"the flag is not the authority
— this check recomputes it."* That is the test that matters
(`test_the_flag_is_not_the_authority`).

**Evidence mode auto-binds only to PUBLIC.** A request arriving in a Slack
channel carries no engagement letter, so public-only is what it actually
has. Auto-binding the most restrictive mode can only ever *under*-claim —
it withholds evidence the run might have been entitled to, costing depth.
Auto-binding INTERNAL would claim access nobody granted, which is the harm
the gate exists to prevent, so that direction is refused no matter what the
document says.

The record stays auditable either way: `asked: false` with `auto_bound:
true`, the answer reading `AUTO-BOUND: one ACCEPT (CU) against 2 REJECT(s)`,
and `answered_by: "lob_census (no human asked — census unambiguous)"`. You
can always tell an auto-bind from a human answer, which is the property that
makes this safe to have at all.

### 3.7 The one manual step that is still outstanding

**`dma-assessment-intake` carries no MCP connectors at all** — measured
2026-08-30 from its `job_config`, which has no connector grant of any kind.
It therefore cannot call `slack_read_channel`, and its STEP 1 stops and says
exactly that rather than pretending.

`update_trigger` cannot add connectors; only the Routine's own edit screen in
the claude.ai routines UI can, or a delete-and-recreate that would change the
trigger id and discard its run history. **A human must attach Slack to this
Routine.** Until then every firing is one cheap honest report — which is
still better than the hourly Drive scan it replaced.

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
