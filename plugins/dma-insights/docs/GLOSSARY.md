# Glossary — one term per concept

Measured 28-09-2026 (QA audit, prompt-craft scorecard § L-12): fourteen concepts were
named several ways across the skills and agents — "the thing one agent hands the next"
had nine names, "tier" seven meanings, an absence sixteen spellings. A reader who meets
two names assumes two things. This file is the one owner of the prose vocabulary; code
identifiers keep their names, and a document that needs a synonym says which entry it
means. Every SKILL.md names this file in its reading manifest.

| Concept | Use | Do not use | Notes |
|---|---|---|---|
| What one agent hands the next | **brief** (what a lane receives: `engine.brief dispatch`), **handback** (what a lane returns: `engine.brief handback`), **handoff packet** (the versioned research→scoring packet from `engine.cli handoff`) | packet (bare), card, report, notifications block, registration worklist, dispatch brief | a *card* is only `orient`'s work card for one cell |
| A dispatched research worker | **lane** (a `research-pXcY-producer` run for one category) | subagent, child, researcher, research agent, worker, actor | *actor* is the engine's provenance field (`--actor`), not a role name |
| The run's single source of truth | **the workbook** | substrate, ledger, register, evidence store, corpus, package | the *register* is the workbook's evidence sheet; the *package* is the client folder the workbook ships in |
| "ledger" | **the ledger** = the workbook's write path and its refusals (`engine/ledger.py`) | — | the findings memory is "the findings memory"; costs are "the cost log"; source yield is "the yield log"; enrichment is "the enrichment record" |
| A check that can refuse | **gate** (`floors gate`, the connector's AG/SG/ET/CG gates, `engine.assessment gate`) for a check that blocks; **check** (RS-, AP-, EC-, PV-, V1–V11, R1–R5) for one that reports | verdict (the gate's OUTPUT), refusal (the ledger's), rung (a ladder step), self-check | a refusal names its reason and the repair |
| The result of a check | **PASS / FAIL / NOT_RUN** (with a reason on NOT_RUN); a checker that must say more uses its own documented enum (HOLDS/BREAKS/UNTESTED, ACCEPT/REFUSE) and says so once | PASS_WITH_NOTES for a gate that ran | NOT_RUN never means "ran and found nothing" — that is NO_FINDING |
| Where a run lives | **run root** (`<ROOT>/<RUN_ID>/`, from `--root`; `engine.runstate.SUBDIRS` names its subdirectories); **client folder** (the `<Client> - DMA` Drive folder the package ships to) | RUN_DIR, rundir, DMA_ROOT, ASSESSMENT_DIR, package-dir | no container path is ever written in prose |
| The unit of scoring | **cell** (in engine and payload prose), **subcap** (`--subcap`, the id `P1C1.1.1`) | subcapability, sub-capability, row, grain | *grain* is the level of a figure (pillar/category/cell), not a thing |
| "card" | **work card** (`orient`'s), **insight card** (I1), **rec card** (P2) — always qualified | card (bare) | |
| "tier" | **evidence tier** (T1–T5), **query rung** (the ten-step search ladder), **size band** (peer sizing), **agent tier** (research / scoring / report / production / enrichment) | tier (bare) | the model is "the model", never a tier |
| An absence | **declared absence** (a cell closed through `engine.cli absence`, with its ladder); **NO_FINDING after n searches** (a volley that ran and found nothing); **NOT_RUN: reason** (a volley that never ran); **thin** (evidence under the floor, on a surface); **verified_absent / verified_sparse** (the payload's empty-state tokens) | NO_EVIDENCE (the seeded default, never a finding), ABSENT (a `Tech_Register` status only), EVIDENCE_THIN, empty_state (bare), Coverage Unknown, [DATA NEEDED] | |
| The orchestrating actor | **the conductor** (`research-conductor`, an agent) and **the driver** (`engine.pipeline`, a program) — the driver runs, the conductor decides; **the top session** is the interactive parent that dispatches | orchestrator, invoker, Routine (a Routine fires a session; it does not orchestrate) | the surface-producer conducts production, never research |
| Score words | **score** (1–5, a quarter-point), **level** (M1–M5 / L1–L5, the score's rubric name from `engine/rubric.py`), **band** (the four display words), **ceiling** (the score the evidence allows, numeric) | M-band, tier band, 5-tier | four bands, strict less-than, on the raw score |
| The claim label | **claim label** in prose; the workbook column is `Claim_Label`, the evidence sheet's is `Claim_Type`, the payload's H6 field is `claim_type` and H2's is `claim_label` — the contract fixes which key where | Dominant_Claim as a label (it is the claim's text) | vocabulary: `contract.CLAIM_LABELS` |
| Agent names | **bare names** in prose (`research-conductor`); the `dma-insights:` prefix only where a tool call needs it | role phrases as names ("the per-surface producer" names a class, not an agent) | |
