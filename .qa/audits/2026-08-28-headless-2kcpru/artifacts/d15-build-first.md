# Deliverable 15 — The three things to build first, and the argument for that order

## 1 · Give a headless session the ability to run a web search

**Grant the search connectors to the Routines, or build the `search_requests` relay the preamble
already promises.** Today `dma-synthesis-sequence` carries Clay and Google Drive and nothing else;
the relay is 11 prose mentions and zero parsers.

**Why first:** everything in Stages 5 and 6 is downstream of evidence. Shipping the v4.2 reasoning
layer — 851 briefs, 4,255 diagnostic questions, a validator returning `FAILS=0` — buys nothing
while the questions cannot be asked. This is also the only item on the list that is *not* primarily
an engineering task: granting two connectors is a configuration change, and the relay is the
fallback if the grant cannot reach a fired session.

## 2 · Make one gate check correctness rather than consistency

**Start with the two one-line fixes whose correct constants already exist, with comments explaining
why they exist:**

- `apps/mcp/dma_mcp/validation2.py:1482` — replace the literal `"green"` with
  `platform_fit.READINESS_DEFAULT` (`"amber"`). The comment at `platform_fit.py:118` already says
  *"Green would reward a card that established nothing."* This alone drops the maximum fit a
  readiness-silent card can reach from **99.0 to 85.0**.
- `apps/mcp/dma_mcp/register.py:95` — count distinct **origins**, not distinct `source_domain`. The
  docstring already says "distinct ORIGINS". Today a vendor release syndicated to two trade outlets
  scores the maximum corroboration of 5.

**Why second:** these two break legs 1 and 4 of the eight-leg path in §6.3 — the wrong-but-perfect
conclusion that passes all 69 gates. They are the cheapest available defence against the exact
failure the human currently catches by reading a rendered page, and neither needs a design
decision. The deeper work — a gate that detects presence scored as utilization — follows from the
same principle and is genuinely new construction.

## 3 · Make a run survive its own container

**Persist `$RUN`, and fix `ledger.py stats`.** `$RUN` is container-local with nothing pushing it to
Drive or GCS, and `scripts/engine/ledger.py:125` raises `NameError: name '_stats' is not defined`
on every invocation — so R27's token-budget rule, the one the owner named by name, has never run.

**Why third and not first:** it is the item that makes the other two *hold* under real unattended
operation rather than the one that unblocks them. A pipeline that can search and can refuse a wrong
number still loses the work when the container exits, and still cannot tell anyone it is stuck —
there is no terminal run state, no run-level clock (the claim lease is 90 minutes of mutual
exclusion whose lapse is a silent handover), and the four watchdogs that exist are named in zero of
three live Routine prompts and zero CI steps.

## What deliberately is not on this list

**Shipping v4.2 into the plugin.** It is a small job — 944 KB against a 50 MB cap, no manifest edit,
dependencies already present — and it is the right thing to do. But it is not first, because its
own reasoning layer contains the defects measured in Stages 5 and 6: an all-`STUB` synthesis passes
`floors_gate --require-synthesis`, proxy-only evidence closes as `FACT` and publishes as M4 with
HIGH confidence, and `G1`–`G12` each mean two different things. Shipping it before item 1 delivers
rigour that cannot reach evidence; shipping it before item 2 adds a second gate family with the
same blind spot as the first.
