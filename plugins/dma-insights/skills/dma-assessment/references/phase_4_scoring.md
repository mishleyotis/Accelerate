# Phase 4: Scoring & Workbook Production

Moved out of `SKILL.md` on 28-09-2026 (QA audit F-B04-027: the skill file was over 500 lines, and a file nobody can read in one sitting is a file nobody reads). The SKILL.md reading manifest says which phase reads this.

## Phase 4: Scoring & Workbook Production

**On a research-engine run (a `DMA_Scoring_Workbook_*.xlsx` with a
`Run_Metadata.stage` key), this phase IS the engine's SCORING stage — do not
build a second workbook.** The driver's `python3 -m engine.assessment open --run <R>`
refuses until every category's floors gate is PASS (the conductor runs it, not the scorer); each score goes in
through `engine.assessment score` (refuses an unchallenged row, a score
above its evidence ceiling, a rationale that cites none of the row's E-ids,
a blank AI/data overlay); the four `scoring-p<N>-producer` agents run one
pillar each in parallel and `scoring-critic` records the SCORING_CRITIC
verdict per pillar; `engine.assessment rollup` then `engine.assessment gate`
must record PASS before Phase 7 may start. The A–K columns below are the same
sheet — column D is what the stage writes.

Execute Phase Gate Protocol. Apply ERR-001, ERR-002, ERR-003, ERR-004, ERR-005, ERR-008, ERR-009.

**Read first:** `references/scoring_methodology.md`, `references/workbook_specification.md`.

**Load evidence per-capability** (see "Evidence Loading During Scoring" in Memory section).

**OUTPUT FORMAT: the run's existing P#_Subcap_Scoring sheets, columns A–K (see "Workbook Column Structure" above).**
Each row = one subcap ID (e.g., P1C1.1.1). Column D = final score. Column J = rationale.
If your sheet has <50 rows, you are scoring at the WRONG LEVEL — STOP.

### Capability Micro-Loop (repeat for each capability — 136 in v7.0, `contract.counts()`)

**3a. RETRIEVE** subcap list + diagnostic Qs from Pillar XLSX Column H.
List every subcap ID under this capability (e.g., P1C1.1.1, P1C1.1.2, P1C1.1.3...).
Each subcap becomes ONE ROW in the workbook.

**3b. MAP EVIDENCE** to each subcap individually. Different diagnostic Qs → different facts from same source. Evidence minimum check: ≥3 items or BLOCKED.

**INTERNAL EVIDENCE PRIORITY CHECK (HYBRID/INTERNAL mode — fires before public evidence mapping):**
1. Check: does internal evidence exist for this subcap? (Hubbl scans, discovery notes, client docs)
2. If YES: classify using decision tree — NEVER default to T4:
   - Hubbl/BuiltWith/Wappalyzer scan → T1 (machine-verified)
   - Structured discovery notes with specific tech/metrics → T2
   - Client-provided policy docs, board decks, roadmaps → T2
   - General internal doc without specific metrics → T3
   - Informal memo, anecdotal claim → T4
3. Internal T1/T2 evidence RAISES the evidence ceiling (not constrained by public T3-T5 caps)
4. When internal contradicts public: internal T1/T2 wins unless public T1 disagrees
5. Log in rationale: "Internal evidence [INT-xxx] classified as T2, overrides public T5 ceiling"

**3c. SCORE EACH SUBCAP** using 8-step decision tree: Collect evidence → Tier classify → Evidence ceiling (Col H) → M-level match → Negative adjustments → Resolve contradictions → Apply caps (Col I) → Final score (Col D) + rationale (Col J).

**3d. WRITE RATIONALE (Column J)** — ≥150 chars, using this template:
```
[EVIDENCE]: [E-xxx:Fy] shows [fact]. [SECOND SOURCE]: [E-yyy:Fz] confirms/contradicts.
[MATURITY MATCH]: Maps to M[N] "[descriptor]" because [why]. [GAP TO NEXT]: Missing [element].
[COUNTER]: [opposing evidence or "None identified"]. [CEILING]: [cap check].
[SO WHAT]: For [Institution], this means [specific impact].
```
FORBIDDEN: "Category-based scoring", "Based on public evidence analysis", anything generic.

**3e. DIFFERENTIATION CHECK:** >60% same score within a capability = STOP. 100% identical = HARD BLOCK.

**3f. CONFIDENCE-ERS CROSS-VALIDATION:** HIGH requires ERS≥2.5. Single-source caps at MEDIUM.

**3g. LOG REASONING CHAIN** to `reasoning_chain_log.json`.

### Post-Scoring Steps

5. **THERE IS NO WORKBOOK GENERATION STEP.** The workbook exists since `engine.cli start`;
   every score you struck is already in its column D. A "single Python script" that reads a
   scratchpad and generates an XLSX is the retired `scripts/assessment_runner.py`'s defect
   (a fresh `openpyxl.Workbook()`, 11 sheets, no `SubCap_Name`s, no formatting, the retired 17-category count)
   and the `deny_artefact_writes` PreToolUse hook refuses it. If a sheet is missing, the
   workbook is not the run's — stop and find the run's (`engine.cli status --run <R>`).

5.5. **EVIDENCE COMPLETENESS GATE (blocks Phase 5):** `engine.assessment score` already
   refused a score with no E-ids, a rationale under 150 characters, a rationale citing nothing
   the row carries, or a score above the row's evidence ceiling — so a row that carries a
   score carries its proof. Confirm with `engine.assessment state --run <R> --root <ROOT>`
   (unscored rows, ceilings, critic verdicts) and `engine.cli validate --run <R> --root <ROOT>`.
6. **Calculation chain — `engine.assessment rollup --run <R> --root <ROOT> --headline "…"`:**
   capability → category → pillar → overall, weights from the run's `Pillar_Weights` (the
   sub-vertical's), written to Pillar_Summary, Category_Detail (16 rows), Pillar_Rollup,
   Category_Rollup and Executive_Summary in one call; `engine.grains recompute` re-derives the
   stated grains and refuses a copy that drifts past the 0.05 tolerance. Then
   `engine.assessment gate --run <R> --root <ROOT>` must record PASS (every selected row
   scored, a SCORING_CRITIC verdict per pillar from an actor that struck none of them,
   differentiation, ceilings) before Phase 5.
7. Run Workbook QA (G.1-G.9 from `references/quality_assurance.md`).
8. **RUN `scripts/validate_scoring_quality.py`** — exit code 1 = BLOCK Phase 5.
9. Generate canonical export CSVs to `$DMA_ROOT/04_scoring/exports/`.

---
