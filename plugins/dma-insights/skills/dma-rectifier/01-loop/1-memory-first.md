# Memory first — what STEP 0 proves, and what it refuses

The loop's whole claim is that a finding sighted anywhere is available
everywhere. That claim is only as good as the first thing this skill does, so
the first thing it does is prove it rather than assume it.

## Where the memory actually is

```
    Cowork session          Claude Code session        the web app
    (surface-producer,      (rectifier, verifier,      (a reviewer clicking
     package-vetter)         deployed-app-auditor)      ACCEPT / REJECT)
           │                        │                        │
           └────────────┬───────────┴────────────┬───────────┘
                        │                        │
                  MCP connector             API annotation
                  (remote HTTP,             (anchor_kind =
                   one deployment)           insight_card)
                        │                        │
                        └───────────┬────────────┘
                                    ▼
                        findings store — Cloud SQL
                        findings + refinements,
                        embedding + tsvector per finding
```

Three properties follow from that picture and each is load-bearing:

**One store, not one per session.** The connector is a single Cloud Run
service. Every session in every surface talks to the same rows. There is no
sync, no export, no "let me summarise what we learned" — a finding is visible
the moment it is recorded, to everything.

**Both retrievals, because they fail differently.** Each finding carries an
embedding and a tsvector. Semantic search finds the sighting a verifier
described as "the label and the figure came from different rows" when you
searched for "grain violation". Lexical search finds the one that mentions
`platform_roadmap.sequencing_basis` exactly, which an embedding will happily
blur into every other roadmap field. Run both and union. A search that runs one
way and reports "no prior sighting" is a claim you have not established.

**Dedup by fingerprint is the measurement, not housekeeping.** Two agents
recording the same defect produce one finding with two sightings. That number
is how a class announces itself, and it only counts correctly if everyone
records rather than deciding theirs is a duplicate and staying quiet. Record
it. Let the store decide.

## The handshake

```
tools = list the connector's tools
assert the memory contracts are all present   ← by contract, not by name
probe  = list_open_findings(window = wide, limit = small)
```

Record `{tools_seen[], open_count, oldest_open, newest_sighting}` in the run
report. Those four numbers are the evidence that memory was read, and a later
reader can tell a genuinely quiet week (`open_count` small, `newest_sighting`
recent) from a broken pipe (`newest_sighting` weeks old while three QA agents
have run since).

## What it refuses

**No memory, no rectification.** If the tools are absent, error, or return a
store that has never been written to, STOP. Report `memory unreachable` or
`memory empty`, name which, and change nothing.

The temptation at this point is to carry on from the session transcript,
because the transcript *does* contain findings and they *do* look actionable.
Refuse it. A rectifier working from one session's scrollback:

- cannot tell a first sighting from the fourth, so it fixes at the wrong rung;
- cannot see the refinement that already closed this class in March, so it
  re-opens settled ground;
- cannot record what it did anywhere the next run will look, so the next run
  starts from the same blank page.

Every one of those failures produces a plausible-looking report. That is why
this is a refusal and not a preference.

**A tool name that has drifted is itself a finding.** If the connector exposes
`search_findings_semantic` and `search_findings_lexical` where this skill
expects one `search_findings(mode=…)`, use what exists, complete the run, and
record a finding against this skill's `02-inputs/2-memory-tools.md`. Documentation
that names a tool the server does not have is the same defect class as a gate
registry naming a field the contract does not declare — it polices nothing,
silently, forever.

## STEP 1 — draining the local channel

Between the handshake and the work sits one more guarantee. Feedback that
exists only in this session is not memory yet, and if you triage before
recording it, this run's clustering cannot see it and the dedup cannot count it
as a sighting.

Sweep for:

| Artefact | Typically from |
|---|---|
| `qa_verdict.json`, `issue_register.csv` | `dma-governance` audits |
| connector verdict JSON (`gate`, `path`, `arithmetic`) | a failed `submit_page_payload` |
| pytest / CI failure output | `corpus-gate-scanner`, a stage's QA bullets |
| an auditor's PASS/FAIL/UNVERIFIABLE table | `deployed-app-auditor` |
| the user's own message | anything |

`python scripts/drain_local.py <dir>` finds the file-shaped ones and emits a
`record_finding` payload per candidate. The user's own words it cannot see —
those you record yourself, quoting them, with `source=user`.

Record first. Triage second. If the sweep finds nothing, write "local channel
empty" and continue; an empty sweep that was run is a different fact from a
sweep that was skipped, and only one of them belongs in a report.
