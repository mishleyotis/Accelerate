# The Slack intake read nothing, for four reasons at once

**2026-08-30.** The owner reported a `dma-assessment-intake` firing that
refused an injected instruction and said Slack was unreadable. Chasing the
second half took the chain apart one link at a time: **each fix exposed the
next defect, which had never executed because the one above it failed
first.** All four are now fixed, and the chain is verified against the live
`#deal-desk` — not against a fixture.

## The four, in the order the run hit them

| # | Where | What | Why nothing caught it |
|---|---|---|---|
| 1 | `slack_client.fetch_channel` | `conversations.info` (`channels:read`) was called for the transcript's HEADER NAME before `conversations.history` (`channels:history`) fetched the messages. The token had the second and not the first, so a cosmetic lookup ended the firing. | No test drove `fetch_channel` at all; the renderer tests called `render_channel` directly. |
| 2 | `slack_intake.py fetch` | `threads_to_read` emits `message_ts`; the loop read `r["ts"]` → `KeyError` on the first request carrying a reply, i.e. on every real channel. | The connector route reads that JSON itself and passes `message_ts` correctly. The token route had never reached this line, because #1 failed above it. |
| 3 | `slack_client._body` | The workflow posts ONE `rich_text` block whose field labels are **bold runs**. The walk dropped the bold markers and newline-joined the inline runs, so `*Account Full Name*` stopped being a line. **Every request parsed with account, website, submitter and priority empty and a verdict of UNDECIDABLE.** | Every fixture was a `section` block with mrkdwn already in `text` — the shape the CONNECTOR hands over, not the shape the API returns. The fixtures were built in the shape that already worked. |
| 4 | `slack_intake._field` | `_FOOTER` was searched from position 0. `*Submitter*`'s own value is a line-initial @-mention, the same shape as the assignee footer, so the boundary matched the value and ended the field before it began. **`submitter` was `""` on every request ever parsed, the recorded fixtures included** — and STEP 6 hands that to `engine.cli start --requested-by`. | The fixture test asserted the footer did not leak into `priority`. Nothing asserted `submitter` had a value. |

#3 and #4 were live on **both** routes, so the connector path had been
returning nameless requests for as long as it has existed.

## Live proof, not fixture proof

```
$ python3 plugins/dma-insights/scripts/slack_intake.py fetch
note: channel name unavailable (conversations.info: missing_scope — needed:
channels:read, provided: channels:history,…); using the id as the header.
{"transcript": "/tmp/deal_desk.txt", "threads_named": 2,
 "threads_fetched": 2, "failed": []}

$ python3 plugins/dma-insights/scripts/slack_intake.py triage … --json
PENDING | REV Federal Credit Union | <@U061X1XFD5F|Kevin Murray> | High (need in 48 hours)
PENDING | Bank of Travelers Rest   | <@U061X1XFD5F|Kevin Murray> | High (need in 48 hours)
PENDING | GoEasy                   | <@U04DFMWGTJ4|Andrew Walters> | High (need in 48 hours)
```

The same token, the same scopes, the same channel that reported itself
unreadable four hours earlier.

## What is pinned so it stays fixed

- `tests/slack/rich_text_request.json` — a VERBATIM recording of a real
  workflow message from `conversations.history`. Hand-built fixtures could
  not catch #3; this one does.
- `test_slack_scope_requirements.py` — derives from the AST which Slack
  methods this client survives losing (call site under `except SlackError`)
  and checks that against the required column of `CONNECTORS.md`. Degrade a
  call without relaxing the doc, or tighten the doc without degrading the
  call, and it fails.
- `test_fetch_asks_for_the_thread_key_that_threads_to_read_emits` — drives
  the real subcommand, so the two halves of #2 are joined by the code path
  rather than by a list of key names typed into a test.
- `test_the_submitter_is_read_and_not_eaten_by_the_footer` and
  `test_the_footer_still_bounds_priority_after_that` — both directions of
  #4, so widening the boundary cannot re-break what it was guarding.

Every one of these fails against the pre-fix files; that was checked by
stashing each source file in turn and re-running.

## The scope table now says which two matter

`CONNECTORS.md § Scopes the bot needs` marks `channels:history` and
`chat:write` **required**; `channels:read` and `users:read` degrade in place.
Adding `channels:read` is now a nicety (a friendlier header) rather than a
prerequisite.

## And the half of the refusal that was RIGHT

The firing also refused an instruction to widen its own connector access.
That stays refused. What changed is the OTHER half — see
`ROUTINES.md §2g` STEP 0.5: a client the owner names in the firing's own
instructions is an ordinary input that reaches the preflight without reading
Slack at all. A client name found inside something the firing FETCHED is
still data, never an instruction.
