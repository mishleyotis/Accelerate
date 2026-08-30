# Read what this build already knows, before you author anything

**Every defect you are about to make has probably been made before, measured,
fixed, and recorded with the fix.** The connector has held that record since
migration 0034 — findings, how each was measured, the refinement that closed
it, and whether it came back. Until 2026-08-19 this skill named none of those
tools on any of its pages, so every run began from zero and the same defect
classes were rediscovered four rounds running by a person looking at a
rendered page.

## At the start of a run

Call **`get_memory_digest`** and **`list_open_rejections`** before you author a
section.

* `get_memory_digest` — what recurred, what is open, what was changed
  recently. A finding with `status: RECURRED` is a fix that did not hold: do
  not repeat it.
* `list_open_rejections` — refusals outstanding across every run, not just
  this one. An open row against your page is work already identified. If one
  names your run, that is the first thing to repair.

## When something is refused

`submit_page_payload` returns `memory.known` alongside `rejections`. It is
keyed by the gate that fired, and each entry carries `last_refinement` — what
was changed the last time this gate produced a finding — and
`gate_added_then`. **Read it before you edit the payload.** A gate whose
`times_seen` is above one is a defect class, not an accident.

`memory.checked` names the gates that were asked. An empty `known` for a gate
in `checked` means this store has nothing on it. An absent gate means it was
never asked — the two are not the same, and neither is evidence of a clean
history.

## Before you promote

Call **`search_findings`** with the shape of anything you are unsure about —
it searches semantically and lexically over the same rows, so a defect
described in different words still surfaces. Then **`record_finding`** for
anything you hit that this store does not already hold, with `measurement`
filled in: a finding that cannot say how it was measured is an opinion, and
the column refuses it.

## Why this is not optional

The memory is only as good as its read path. A store written by the rectifier
and read by no producer is `WRITE_PATH_WITH_NO_READ_PATH` — a defect class
this build already has a name for, applied to itself.
