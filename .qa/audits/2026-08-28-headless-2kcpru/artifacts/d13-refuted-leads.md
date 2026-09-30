# Deliverable 13 — Leads and premises this audit disproved

An audit that inherits another's errors has laundered them. These are the claims the
audit prompt itself carried — as `[LEAD]`s, as background framing, or as reproduction
targets — that measurement did not support. **One of them is my own.**

## Refuted

| # | The claim | What measurement showed |
|---|---|---|
| 1 | *"A search of the live tree for `evidence_mode` appears to return nothing."* | **60 hits.** But the distribution is the real finding: 0 in apps/api, apps/mcp, apps/worker, packages, migrations, scripts, infra; **24 in `apps/web/proto/`** and 13 in `apps/web/tests/` fixtures; 23 in `plugins/`. The skills carry an evidence mode and the application does not — and `apps/web/proto/README.md` says those modules are *"running in production"*, so `pages-d1-overview.jsx:290` renders `EVIDENCE · {run.evidence_mode}` **unguarded** against a field the API never sends. |
| 2 | §4.1: *does the SessionStart hook fire in a headless session at all?* — framed as the highest-value check | **It fires.** A `claude -p --agent` child returned the 377-byte brief verbatim. The hole is one layer over: SessionStart reaches only top-level sessions (parent transcript 4 attachments; **0 across 10 of 10 subagent transcripts**), and the live Routine dispatches every producer as an in-process subagent. Severity downgraded BLOCKER→MAJOR on verification, because the one agent that *does* get the brief is the orchestrator, which already carries the same text in its Routine prompt. |
| 3 | §4.6: *"a **missing** register row and a **confirmed-absent** one both produce greenfield … every unscanned estate is systematically over-recommended"* | **The engine distinguishes them.** Three estates with identical gaps: known-absent **64.80**, never-looked **56.80**, known-held **28.x**. A never-looked estate scores *lower*, not equal. The real gap is narrower and survives: `incumbent_covers` has no "we never looked" state. |
| 4 | §4.5: *"Nothing stores peer scores at category grain any more … no data source and no renderer"* | **The store is not missing; the feeder is.** `peer_scores.category_id`, the category-grain workbook parser, the serving column with its generated delta and the report's §4.2 category table all exist and are sound. The pinned workbook has no `Peer_Benchmarks` tab, and the parser's missing-tab branch is the one of seven that returns empty **without recording an observation**. |
| 5 | *"roughly AG-01…AG-12"* | **The AG family has 8 ids.** Numbers 6, 7, 8 and 10 do not exist — they belong to `dma-governance`'s own 108-check numbering, and `tests/skills/test_gate_guidance_reaches_producers.py` pins that collision in both directions and cannot pass vacuously. CG-01…50 and ET-01…09 are complete. Registry total: **69**. |
| 6 | *`Run_Metadata.kg_checksum` — "the single strongest resume anchor in the system"* | **Zero references in either tree.** Nothing writes `{{CHECKSUM}}` and nothing reads it. |
| 7 | *Gate id `G10` is overloaded* | True, and **twelve times worse**: every id `G1`–`G12` means one thing in `validate_kg.py` and a different thing in `safeguard_gates.md`. `G7` alone is "open-question DQ" vs "Artifact Pack (PNG visualizations)". |
| 8 | Full suites at HEAD: **3,807** Python passed | **3,808** passed, 12 skipped. The skip count matches exactly; the pass count is one higher. Also: the prompt's single-venv Instruments block cannot run both suites — `apps/api` pins `fastapi==0.115.*` (starlette <0.47) while `apps/mcp` pins `mcp==2.0.*` (starlette 1.6.0). Two venvs are required. |
| 9 | The `[LEAD]` that `MAX_BROKEN=8` makes the broken routing anchors *"invisible to CI"* | **Right conclusion, wrong mechanism.** The ceiling does suppress the default run (rc=0; `--max-broken 0` gives rc=1 and "8 broken references"). But `grep -rn 'audit_skills' .github/workflows/` returns **zero** — CI never runs the check at all, so the ceiling is moot. |

## Confirmed, so that the record is even

The `[LEAD]`s on **Slack ingress** (none exists; intake is the `*/30` Drive scan), on **the connector publishing JSON only** (33 tools, zero accepting bytes), and on **MEM-0092's duplicate runs** all held. The duplicate figure held *too* well: `surplus_runs` is still exactly **109** while the queue fell 287→282, so five runs left and not one duplicate was resolved.

## The one I got wrong myself

I independently "confirmed" a finding of **50 of 55** broken routing anchors — using the same
line-grep that produced it, so my confirmation added nothing and laundered its error. A verifier
refuted it; a third measurement, pinning the anchor *column* rather than grepping lines, gives
**48 of 53 data rows** (55 lines minus 2 markdown headers; the file's own prose says 53). The
defect is real and slightly smaller than claimed, and "every one of its rows" was false — three
rows already use correct paths.

**The lesson is procedural, not arithmetic:** re-running someone's command is not verification.
Verification is measuring the same thing a different way.
