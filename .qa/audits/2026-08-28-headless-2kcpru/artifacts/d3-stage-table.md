# Deliverable 3 — The nine stages, one verdict each

**Roll-up rule, stated so it can be argued with.** A stage's verdict is a judgement on
*the mechanism the stage exists to provide*, not a mechanical worst-of over its checks —
worst-of saturates at ABSENT–UNNOTICED on any stage with more than three checks and stops
carrying information. The constituent distribution is printed beside every verdict, and the
one check driving the call is named, so the roll-up is checkable against the ledger rather
than taken on trust.

**Ranking used where a tie had to be broken:** ABSENT–UNNOTICED ranks worst, because a gap
nobody has recorded cannot be scheduled, funded or assigned. PRESENT–DEFECTIVE is next: the
mechanism exists and misbehaves, which at least leaves something to fix. PRESENT–HUMAN-DEPENDENT
is the specific verdict this audit exists to find. ABSENT–BY–DESIGN is the only benign absence.

| # | Stage | Verdict | Constituent checks | Driving check | Justification |
|---|---|---|---|---|---|
| 1 | Request ingestion (Slack, or a typed Routine) | **ABSENT–UNNOTICED** | 2 AU / 3 PD | `S1-01` | `routines.json` holds 4 GCP Cloud Scheduler jobs and 0 Claude Routines, so the "front door" is a poller over a Drive tree — there is no request payload shape, no requester identity, no authorisation and no rate limit anywhere in the repo, and nothing records that these are missing. |
| 2 | Triage and duplicate detection | **PRESENT–DEFECTIVE** | 1 PS / 2 PD / 1 AU | `S2-03` | `package_key()` genuinely handles the two identically-named production folders (measured, sound), but `entity_resolution.py` is 86 lines of exact-match cascade whose two lowest rungs park a run at `PENDING_REVIEW` — a state with no asker, since one grep for clarification vocabulary across eight trees returns a single card label. |
| 3 | Classify PUBLIC / HYBRID / INTERNAL | **ABSENT–UNNOTICED** | 3 AU / 2 PD | `S3-03` | `evidence_mode` returns 0 hits across `apps/api`, `apps/mcp`, `apps/worker`, `packages`, `migrations`, `scripts` and `infra`; all 60 repo-wide hits are prototype render code and skill prose, so the classification reaches no code branch and neither authority 1 nor authority 2 defines a column for it. |
| 4 | Load internal documents | **ABSENT–UNNOTICED** | 1 AU / 3 PD | `S4-01` | `_classify_artefact` accepts exactly four shapes (`*manifest*.json`, `.xlsx/.xlsm`, `.docx`) so the `.json/.csv/.jsonl` evidence stores that 2 of 6 sampled production folders actually ship are unreadable, and the one enum value that could mark internal provenance (`evidence_origin_t → internal`) is unreachable from either writer. |
| 5 | Per-subcap research and the MECE diagnostic questions | **PRESENT–DEFECTIVE** | 2 PS / 8 PD / 2 AU | `S5-03` | The corpus itself is complete and machine-clean — 851 briefs, facet histogram `{5: 851}`, 4,255 DQ rows, `validate_kg.py` FAILS=0 — but every gate that would keep it honest is build-time only, and the one that matters most (G10, platform-agnostic) scans `dq[].q` while the queries actually fired live in `q.primary`, where 103 vendor names sit unchecked. |
| 6 | Synthesis, reasoning traps, and the challenge machinery | **PRESENT–DEFECTIVE** | 13 PD / 3 AU | `S6-12` | The detectors are real and can fail under mutation, but they measure length, format and presence rather than substance: a synthesis filled with structurally-valid, substantively empty prose produced gate output **byte-identical** to the archive's own golden fixture, at `confidence: HIGH`. |
| 7 | Scoring | **PRESENT–DEFECTIVE** | 6 PD | `S7-06` | The band fixture test exists and can fail, but it is DB-only; and the governance register that is supposed to audit scoring reads `P{n}_Scoring_Detail` while contract v3 ships `P{n}_Subcap_Scoring`, so a deliberately fabricated workbook and a good one produce byte-identical output at exit 0. |
| 8 | Reports, workbooks, and the issue register (the publication gap) | **ABSENT–UNNOTICED** | 2 AU / 2 PD | `S8-02` | Split verdict, stated plainly: the *file-publication* half is **ABSENT–BY–DESIGN** — all 33 connector tools emit JSON and invariant 2 is deliberate, so this is the owner decision the prompt says to surface — but the *governance issue register* half is unnoticed: a 7,160-byte JSON Schema with 16 fields and a writer, and no serving path at all. |
| 9 | Finalise and publish | **PRESENT–DEFECTIVE** | 3 PS / 3 PD / 1 AU | `S9-01` | Promotion is genuinely atomic, retention genuinely holds, and the SG-discloses-but-still-promotes rule is correct in code and in the registry — but invariant 11's stability test **cannot fail on order**, proven by mutation, and `run_status_t` has no terminal state, so nothing can ever say a run is finished. |

## What the distribution says

Four of nine stages are **ABSENT–UNNOTICED**, and they are the first four — the entire front
half of the pipeline, from "a request arrives" to "the internal documents are loaded", is
missing rather than broken. The five that are **PRESENT–DEFECTIVE** are the back half, which
exists, runs, and is wrong in ways that pass their own gates.

That shape matters for planning. A defective stage is a repair; an unnoticed-absent stage is
a design, a schema, a migration and an owner decision. The work in stages 1–4 is not the same
kind of work as the work in stages 5–9, and estimating them together will understate the front
half badly.

## A note on the fifth verdict

Across all 158 checks, **ABSENT–BY–DESIGN was awarded zero times**, and the one place it
belongs (the file-publication half of stage 8) is a half-verdict inside a row that had to be
split to say so. Not one absence in this system was found to be deliberate *and* recorded as
deliberate. That is a finding about the repo's self-documentation, not about any one stage:
where something is missing on purpose, the purpose is not written down anywhere a reader —
or an unattended agent — can find it.
