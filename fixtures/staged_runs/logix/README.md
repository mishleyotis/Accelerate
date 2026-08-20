# Staged run fixtures — Logix, run d7ed1d90

The six page payloads of a run the connector PASSED on every page and then
promoted (`d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb`, promoted 2026-08-19),
reassembled section by section from `get_staged_payload`.

They drive `tests/skills/test_check_payload_false_positives.py`, whose claim
cannot be made from unit fixtures: on a whole payload the connector accepted,
the local checker raises none of the four repaired false-positive classes
(AG-03, raw taxonomy code, CG-09, terminal punctuation). Six cases, one per
page.

## Why this directory is empty in git

The same property that makes these payloads worth testing against makes them
unpublishable. `get_staged_payload` returns staged rows **verbatim** — "not
redacted, not the served projection" (`apps/mcp/dma_mcp/staged.py`) — so a
whole-payload fixture is the un-redacted internal record of a named
institution. Measured on this run, 2026-08-20:

| | count |
|---|---|
| `r_layer` reasoning records | 45 |
| `internal_only` blocks | 34 |
| named individuals' LinkedIn profile URLs | 7 |
| work email addresses at the client's own domains | 3 |

plus the ceilings, cohort-pattern and conversation-starter sections that
`redaction.py` withholds from a customer body by name. This repository is
public, and `.gitignore` has said since the beginning that client information
never enters it. So the payloads are gitignored and the six cases **skip in
CI** — reported in the run's skip list (`-rs`), not hidden.

## Filling it

On a machine that already holds connector credentials:

    python3 scripts/fetch_staged_fixtures.py d7ed1d90-d406-4e8e-9ab0-75f91a0c15bb

and the six cases run. `DMA_STAGED_DIR` points them at a different directory
for a local investigation against another run.

The script follows the tool's own contract — the section index first, then each
section, and a section over the inline budget by numbered `part` with its
`chunk` strings concatenated. Measured shape of this run:

| page | sections | bytes |
|---|---|---|
| context | 5 | 31,966 |
| heatmap | 9 | 1,539,550 |
| insights | 2 | 29,076 |
| overview | 12 | 137,100 |
| platform | 5 | 85,801 |
| techstack | 1 | 38,926 |

## What was wrong before

Those six cases sat dead for months for a different reason: they pointed at a
directory inside a finished Claude session's scratchpad — a path on no machine
anyone would ever run them on — so they skipped everywhere while counting as
coverage. Pointing them at the repository was half the fix; a one-command way
to materialise the payloads, instead of a paragraph telling you to assemble
them by hand, is the other half.
