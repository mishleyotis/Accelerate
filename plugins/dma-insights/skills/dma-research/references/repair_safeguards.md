# Repair safeguards — what started each repair, and what now stops it recurring

Every issue that sent a cell back for repair on `arbor-bank-2026-10-05`
(2026-10-05), mapped to the safeguard that now catches it, the test that
pins the safeguard, and the finding that records it. The tests are also
registered in `fixtures/permanent_regressions.json`, where
`scripts/tests/test_permanent_regressions.py` fails the build if a pin is
renamed or removed.

"Where it bites" says when the defect is caught: **write** (the ledger
refuses the row), **gate** (the floors gate blocks the category and serves
the cell as repair), **packet** (what the independent challenger is shown),
**card** (what the repairing researcher is shown), **dispatch** (which categories the driver hands out).

## Mechanical safeguards (engine code, test-pinned)

| # | Issue that started a repair | Where it bites | Safeguard | Pinned by | Finding |
|---|---|---|---|---|---|
| 1 | A single-source claim had no exit: `single_source_fact` said "relabel INFERENCE", the write path said "relabel FACT", and both labels need two sources | gate + write | Every single-source repair text names the one exit all checkers accept: `CEILING_ESTIMATE` with `Ceiling_Band` and `Uncertainty` | `test_a_single_source_claim_has_an_exit_that_needs_no_new_source` | MEM-0583 |
| 2 | The challenge packet left out `Ceiling_Band` and `Uncertainty`, so `claim_label_fit` on a CEILING_ESTIMATE went NOT_RUN and the cell passed unjudged | packet | `brief._challenge_cell` ships `ceiling_band` and `uncertainty` | `test_the_packet_carries_the_band_a_ceiling_estimate_is_judged_on`, `test_the_packet_carries_the_fields_the_other_dimensions_read` | MEM-0584 |
| 3 | A CEILING_ESTIMATE was written with no `Uncertainty` (14 of 69 on this run) | write + gate | `quality.claim_label_supported` refuses it; the floors gate files it as `claim_unsupported` | `test_a_ceiling_estimate_without_its_band_is_refused` | MEM-0585 |
| 4 | Cells were re-synthesised without seeing the challenger's objection, and 5 of 9 failed again on the same objection | card | `floors_gate.repair_worklist` adds the latest FAIL's failed dimensions and rationale to the card as "the challenger failed: …" | `test_the_repair_card_carries_what_the_challenger_objected_to` | MEM-0586 |
| 4b | The card carried only the generic action for a gate term, never the finding's own reason. P3C3.3.1 was relabelled from one refused label to the other | card | `repair_cells` adds "<term>, here: <why>" for every finding that carries a reason. The `claim_unsupported` action names CEILING_ESTIMATE for a single-source claim | `test_the_repair_card_carries_each_findings_own_reason` | MEM-0592 |
| 5 | An INFERENCE citing two ids from the same page passed the write path's id count | gate | The floors gate resolves INFERENCE evidence to source identity (host, otherwise source name), the same way `single_source_fact` does for FACT | `test_an_inference_on_two_ids_of_one_source_is_blocked` | MEM-0587 |
| 6 | The entity's own site and social posts were registered at T1 (52 rows on this run) | write | `ledger.append_evidence` refuses own-site or social-host evidence at T1: register it at T2 if it is a hosted disclosure, T5 if it is marketing | `test_the_entitys_own_site_and_social_posts_are_never_t1` | MEM-0588 |
| 7 | Three rules tightened mid-run and five categories kept a stale recorded PASS: 17 claimed cells the live gate refuses were never dispatched | dispatch | `brief.categories_needing_dispatch` re-reads the live worklist (persist=False) and re-dispatches a recorded PASS that now names a claimed cell | `test_a_recorded_pass_the_live_gate_now_refuses_is_redispatched` | MEM-0589 |
| 8 | One website counted as two sources: six modules each parsed the host themselves and none stripped `www.`, so a single source looked corroborated (10 cells) and the same span was registered twice (10 rows) | write + gate + scoring | `contract.source_host` / `source_identity` / `url_key` are the only identity rule. All six callers use them, the dedupe compares `url_key`, and a test fails if a hand-rolled host split comes back | `test_www_and_bare_host_are_one_source_everywhere`, `test_no_module_derives_a_host_by_hand` | MEM-0590 |
| 9 | A stalled category could not be accepted as a gap. The driver asked a person to decide, but nothing could record the decision, and three gates refused it | dispatch + scoring + pages | `engine.waiver` / `engine.cli waive`. A **person** names cells in one category; only `challenge_failed` and `claim_unsupported` are waivable. The waiver covers the category only while every live blocker sits inside it. Waived cells stay null and are disclosed in `Caps_Applied_Log`, and H5 renders them as a `qa_hold` | `test_gap_waiver.py` (4 tests) | MEM-0591 |
| 9b | A waiver recorded after scoring had already opened was never disclosed, so its cells blocked the gate as plain "unscored" | scoring | `_stage_scoring` writes the waiver disclosure on every entry. `scoring_batch` never hands a waived, unscored cell to a scorer | `test_a_waiver_recorded_after_scoring_opened_is_still_disclosed` | MEM-0593 |
| 9c | The scoring critic failed P2 and P3 five rounds running, and no scorer saw it: the brief listed only unscored rows | scoring | `scoring_batch` puts the latest critic FAIL note in the pillar's brief and lists the cells it names as `rescore` rows | `test_a_critic_fail_reaches_the_scorer_with_the_cells_it_names` | MEM-0594 |
| 9d | A waiver was honoured by dispatch and scoring but not by the five other code paths that read the recorded gate. The report check refused both reports, and orient and the stage-advance hook kept asking for research the person had already accepted | reports + orient + watchdog + hook | `waiver.scoreable_verdict` is now the only reader of a category's floors verdict, and no engine module reads `floors_<cat>.json` itself. The watchdog does not count waived cells as unscored work | `test_every_downstream_reader_honours_a_covering_waiver` | pending (the findings connector disconnected mid-session) |
| 9e | Report sections sent back by the validator stalled for two rounds: the writer's brief named the sections, not the validator's reasons | reports | `report_batch` adds each REVISE/FAIL section's latest review (failed checks and note) as `validator_objections`; review notes are kept to 1500 chars, not 300 | `test_a_report_writer_sees_the_validators_objection` | pending (findings connector disconnected) |
| 10 | A FAILED challenge did not block the floors gate (fix carried in from `ccr-4d2dcfc5-77fgo8`) | gate | `challenge_failed` is a blocking term, and the cell is served as repair | `test_a_failed_challenge_blocks_and_is_served_as_repair` | MEM-0441 / MEM-0577 |
| 11 | A re-synthesised cell kept its stale verdict and was never re-challenged (fix carried in) | write | `append_synthesis` clears `Challenge_Verdict`; selection reads the live column, not the log | `test_re_synthesis_clears_the_stale_challenge_verdict` | MEM-0441 / MEM-0577 |
| 12 | A single-source INFERENCE passed the write path and failed the challenge (fix carried in) | write | `quality.claim_label_supported` refuses an INFERENCE with fewer than two ids | `test_a_single_source_inference_is_refused_at_write` | MEM-0441 / MEM-0577 |

## Judgement safeguards (held by the independent challenger, no mechanical check)

These need a reading of the excerpt against the claim. Nothing in the engine
can decide them without a model call, so the safeguard is the independent
challenge, plus #4, which now hands the challenger's objection to whoever
repairs the cell.

| Issue that started a repair | Example cells | Held by |
|---|---|---|
| Undated or former-officer evidence stated in the present tense (invariant 9: undated is UNVERIFIED, never current) | P1C2.6.4, P4C4.1.1 | challenge `recency` + #4 |
| The claim names something no cited excerpt says | P1C2.9.RB1, P2C4.3.3, P3C1.3.RB1, P3C2.4.3 | challenge `evidence_sufficiency` + #4 (same shape as MEM-0288 downstream) |
| The claim is contradicted by its own cited row, and the contradiction field says "none found" | P4C3.4.1, P3C2.3.1 | challenge `contradiction_handling` + #4 |

If any of these recurs on a cell after the card carried the objection,
treat that recurrence as a finding against the researcher prompt, not
against the cell.

## Open work, recorded and not yet done

- **Re-grade arbor-bank's existing self-published rows.** By the user's
  decision (2026-10-05), #6 applies forward only. The run's 52 own-site or
  social rows at T1, cited by 55 cells, stay as filed until re-grading is
  scheduled (MEM-0588). This includes merging the 10 duplicate rows that the
  `www.` drift created (MEM-0590). Until then, P3C1.3.RB1 cannot pass its
  challenge: it cites one page three times at inflated tiers.
