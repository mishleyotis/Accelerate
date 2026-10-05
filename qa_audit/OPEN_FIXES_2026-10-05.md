# Open fixes logged during the Susser Bank run (2026-10-05)

Deferred at the owner's direction ("focus on scoring, reports and promotion;
other fixes may be logged and come after"). Record each in the findings
memory (record_finding) from a session that holds the connector.

1. **Scoring critic's moves never reach the scorers** (SCORING looped 4
   rounds, critic: "0 of 8 named rows rescored"). Once every row has a score,
   `brief.scoring_batch` offers no rows, so the critic's MOVE DOWN list in
   its Gate_Log detail is never handed to a scorer. Fix: route the critic's
   named rows (and target values) into the scoring brief as `rows_to_rescore`,
   the same way the research handoff now routes the floors gate's repair
   cells. Worked around today by applying the critic's 20 explicit moves
   through `engine.assessment score` under each pillar's scorer actor.
2. **Search_Log has no Actor column** (MEM-0576, open): connector searches
   on a cell are counted in RELAY's ceiling window.
3. **A resumed session loses Workflow, Agent, ToolSearch and the MCP
   connectors**; the rendered `agent_prompts` fallback assumes Agent exists.
   The headless `agent_run.py` path works for connector-free lanes
   (challenge, scoring) and should be the documented fallback for those.
4. **Repair agent stripped a source date to satisfy the ungrounded-figure
   check** (P3C1.7.1/7.2, harness flag "Security Test Removal"): the repair
   prompt should forbid editing a fact out of prose to pass a check.

## Wall-clock (owner, 2026-10-05: "running for hours — parallelize")

Measured on this run: SCORING alone 294 min (130 attempts over 112 lanes);
each research repair round ~45-55 min; whole run ~10 h of wall clock.

5. **Rule-based score checks belong in `engine.assessment score`, not the
   critic.** Every critic FAIL today was mechanical: the T5 cap (bank-only
   evidence <= 2.0), ADJ_STALE by evidence age against the run's reference
   date, and score above the row's own Ceiling_Band. Enforced at write time,
   the critic stops being a ~70-minute round trip to discover them.
6. **Critic per pillar, as soon as that pillar's lanes finish** (pipeline,
   not a barrier on all four pillars), with its moves routed straight back
   to that pillar's scorer (item 1).
7. **Workbook write lock is the throughput ceiling.** Every write is an
   openpyxl whole-file load + save (~10 s) under one run-wide lock, so ~30
   concurrent agents queue behind each other (and a gate timed out at
   120 s). An append-only journal (SQLite) with the xlsx rendered at stage
   boundaries removes the serialization.
8. **The conducting session is a serial bottleneck between rounds**: every
   research round waits for a human-attended session to start workflows and
   re-run the driver. A resumed session also loses Workflow/Agent/connectors
   (item 3). Let the driver loop rounds itself where the lane needs no
   connector (challenge, scoring, repair-by-correction).

## Status after the speed-and-enforcement branch

- 1, 5, 6 FIXED: `engine.assessment.mechanical_caps` / `stale_owed` enforce
  CAP-BAND, CAP-OWN (T5), ADJ_STALE and STALE_DATA->LOW at `score` and at the
  gate (`stale_unadjusted`); `critique --move CELL:TARGET:why` (required on a
  FAIL) is routed to the scorer as `rescore` rows, enforced by `score`, and
  blocks the gate as `critic_moves_pending`; a PASS withdraws the pillar's
  moves. Critic lanes are per pillar and skip passed pillars; the solutions
  duty and ready pillars' critics run beside the scorers.
- 6 (workflows): `workflows/dma-pillar-scoring.js` — one persisted workflow
  per pillar; `--scoring-mode workflow` (default with the real dispatcher)
  hands SCORING off like RESEARCH; the `stage_advance` hook names the
  Workflow calls. `--scoring-mode lanes` is the fallback without Workflow.
- 7 MEASURED, NOT FIXED: lock stress on the real 1.4 MB workbook — load
  2.0-3.2 s, save 1.7 s; 1 writer 16.4 writes/min, 8 writers 18.9 writes/min
  (p50 2.0 s, p95 46 s, max 70 s). Throughput is flat in the number of
  writers: the whole-file reload+save is the ceiling. The journal refactor
  (append-only SQLite, xlsx rendered at stage boundaries) remains the fix.
- 8 PARTIAL: scoring rounds are driver-looped headless (no session needed);
  research rounds still need the session (connectors).
