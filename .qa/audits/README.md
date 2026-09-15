# Archived audits — dated, commit-pinned, and superseded

These are **historical records**, recovered 2026-08-30 from branches that were
never merged. Every one was a read-only audit that changed no code, and every
one describes the repository as it stood at the commit named in its own
header — not as it stands now.

| directory | audit | ran against | what it produced |
|---|---|---|---|
| `2026-08-28-headless-2kcpru/` | Deep QA: can this repo run an unattended headless DMA? | `cdea0e1` | 158 checks, 151 findings (51 BLOCKER / 80 MAJOR / 17 MINOR / 3 INFO), 15 deliverables |
| `2026-08-28-headless-82e4gl/` | Headless-readiness, 24-agent fan-out | `cdea0e1` | 150 checks, 111 deduplicated findings; 52 filed as new `MEM-####` |

## Read the counts as history, not as status

`cdea0e1` is hundreds of commits behind the current default branch, and a
large share of what these audits found has since been fixed — much of it
*because* of them, since their findings went into the shared findings memory
as `MEM-####` rows and were worked from there.

So "51 BLOCKER" is what was true on 2026-08-28. It is not an open count. The
live registers are:

- `.qa/AUD-DISPOSITIONS.json` — this repository's findings ledger, with a
  runnable check behind every FIXED claim (`scripts/aud_ledger.py --verify`)
- the connector's findings memory — `get_memory_digest`, `list_open_findings`

## Why they were kept rather than dropped

Two branches carried them and neither was merged, so the work was one branch
deletion away from being gone. They are the only record of what was measured
that day, they name the access that would have unblocked the two `BLOCKED`
rows, and an audit nobody can re-read is an audit that gets re-commissioned.

They also collided: both branches wrote `.qa/ledger.jsonl` and `.qa/prompt.sha256` with
different contents, so merging them naively would have silently kept one and
lost the other. That is why each lives under its own dated directory rather
than at `.qa/`.
