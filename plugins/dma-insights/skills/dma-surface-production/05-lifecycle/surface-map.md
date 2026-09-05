# Surface map — the census, with owners

Every surface the Surface Specification defines, one row each, with the agent that
produces it. Counted from the spec extraction
(`docs/text/DMA Insights - Surface Specification.txt`), not asserted: **38 page
surfaces across the seven dashboards** (13 + 2 + 5 + 5 + 6 + 2 + 5 — the spec's own
cover count and CLAUDE.md's), **plus 15 drilldown panels** ("15 panels across three
shells. Five carry a synthesis prompt in the design specification; the rest render
from data their parent surface already holds"). A drilldown a click produces is a
surface, so the panels get rows too — 53 rows in all.

Reading the columns:

- **Producing agent** — the **per-surface producer** that owns the row, or
  **server-computed — no producer** where the app derives the render and there is
  honestly nothing to synthesise. The column used to name one of the six page
  producers; it now names the single agent whose whole attention is this surface,
  because that is the agent a one-surface repair routes to (`05-lifecycle/routing.md`).
  The page producers still exist and still own page assembly, the page narrative
  thread and the hand-off to `finding-challenger` — they simply no longer write
  section bodies, and naming one here would send a one-card repair through a
  wrapper that only passes it on. Two surfaces share an owner wherever splitting
  them would let one half contradict the other. **T3 is the one page surface with
  no per-surface owner**: its per-row detail fields ride the register rows, and the
  `techstack-surface-producer` retains that pass. H9 is the envelope-only case: its
  producer submits `fields: {}` and the arrangement joins `ccg_value_chains`
  server-side.
- **Rulebook anchor** — where the surface's rules live:
  `../03-pages/rulebooks/<page>.md § <ID>`, RELATIVE TO THIS FILE. The path used
  to be written `rulebooks/<page>.md`, which resolves under `05-lifecycle/`,
  where no `rulebooks/` directory has ever existed — 49 of the rows below
  pointed at nothing, and a producer following the routing chain as documented
  hit a file-not-found on the rulebook for whichever page it owned. Anchors are
  checked by `plugins/dma-insights/scripts/audit_skills.py`, whose broken-
  reference ceiling is now 0. (Applied by default per `03-pages/README.md`;
  the page pack
  `03-pages/<n>-<page>.md` carries the same anchors with the contract.
- **Enrichment facets** — the ledger's fixed seven (`leadership · firmographics ·
  techstack · sentiment · why_now · platform_readiness · peer_scores`) plus
  `thought_leadership`, per `02-inputs/enrichment_sources.json`. A dash means no
  ledger facet is registered for the surface: its enrichment, if any, travels the
  evidence ladder and exists only as registered evidence.
- **Gate families** — `AG · SG · ET · CG` per `1-gates.md`, with the spec's named
  gates where it asserts them (S-codes are the SG family; W/G/H codes are shown in
  the family they behave as). The **contract pass and evidence pass run on every
  submitted section**, and AG-03 (every claim-bearing item cites) and CG-15 (a
  payload that says nothing) sweep every produced surface — none of that is
  repeated per row.

Where a surface's content COMES FROM, and whether it is formatted or
synthesised, is not in this census — it is in `references/section_sources.json`
(generated; `python3 -m engine.surface_export plan`), which joins each payload
section to its workbook tab(s), its report section(s), its enrichment source
and a disposition (`workbook` / `report` / `enrichment` / `synthesis` /
`server`). Read it before producing: a `workbook` or `report` section is
formatted, not re-synthesised, and not re-challenged.

That map goes down to the **card and the drawer**. Every card array a section
renders — each finding, insight, recommendation, tile, bar, register row — is in
the same file under the section's `cards`, with its item keys, its nested
sub-cards, and the exact workbook tab COLUMNS / report section / enrichment facet
that feed it, plus its floor and the flags that say what NOT to author
(`connector_authored`, `computed_never_sent`). The 15 drawers (DD-1..DD-15) are
the top-level `drilldowns` block — each panel's parent card, the section it
renders, and whether it carries its own synthesis prompt (DD-1/2/3/4/7). Ask the
connector for `join://cards` and `join://drilldowns`, or run
`engine.surface_export cards --section <page.section>` and `… drawers`.

## The page census — 38 surfaces

| ID | Name | Dashboard | Parent (if drilldown) | Producing agent | Rulebook anchor | Payload section(s) | Enrichment facets | Gate families |
|---|---|---|---|---|---|---|---|---|
| O1 | Scores & peer benchmarks | D1 Overview | — | overview-hero-producer | ../03-pages/rulebooks/overview.md § O1 | overview.scores | — | CG (grain ±0.05) · AG |
| O2 | Firmographics strip | D1 Overview | — | overview-hero-producer | ../03-pages/rulebooks/overview.md § O2 | overview.firmographics | firmographics | ET (identity) · CG (recency) |
| O3 | Why-now signals | D1 Overview | — | overview-whynow-producer | ../03-pages/rulebooks/overview.md § O3 | overview.why_now | why_now | SG:S25 · CG · AG |
| O4 | Executive summary | D1 Overview | — | overview-narrative-producer (written last on the page, over settled claims) | ../03-pages/rulebooks/overview.md § O4 | overview.exec_summary | — | SG:S16,S20,S26,S1 · AG |
| O5 | Opportunity surface tiles | D1 Overview | — (tile click navigates to D4 · P1) | overview-opportunity-producer | ../03-pages/rulebooks/overview.md § O5 | overview.opportunity | — | SG:S13,S17,S31 · CG (breakdown = headline) · AG |
| O6 | Top findings | D1 Overview | — (rows expand → DD-9) | overview-findings-producer | ../03-pages/rulebooks/overview.md § O6 | overview.findings | — | SG:S14,S1,S20 · CG (W1 grain) · AG |
| O7 | Leadership panel | D1 Overview | — | overview-people-producer | ../03-pages/rulebooks/overview.md § O7 | overview.leadership | leadership | ET (identity) · CG (dated) · AG |
| O8 | Financial trajectory | D1 Overview | — | overview-market-producer | ../03-pages/rulebooks/overview.md § O8 | overview.financial_series | firmographics | SG:S6,S24,S27 · ET · CG (cross-surface) |
| O9 | Sentiment | D1 Overview | — | overview-market-producer | ../03-pages/rulebooks/overview.md § O9 | overview.sentiment | sentiment | SG:S8 · CG (n·scale·as_of) · AG |
| O10 | Evidence coverage | D1 Overview | — | overview-governance-producer | ../03-pages/rulebooks/overview.md § O10 | overview.evidence_coverage | — | CG (denominator; reconciles to H4 cell set) |
| O11 | Evidence tier distribution | D1 Overview | — | overview-governance-producer | ../03-pages/rulebooks/overview.md § O11 | overview.evidence_coverage | — | CG (counts reconcile) · AG |
| O1b | Capability ceiling & uncertainty | D1 Overview | — (rows expand → DD-15) | overview-governance-producer | ../03-pages/rulebooks/overview.md § O1b | overview.ceilings | — | AG (G14 framing; ±0.8 cap) · CG |
| O12 | Thought leadership signal | D1 Overview | — | overview-people-producer | ../03-pages/rulebooks/overview.md § O12 | overview.thought_leadership | thought_leadership | ET (identity) · CG (dated, verbatim) · AG |
| I1 | Insight cards | D2 Insights | — (card opens → DD-3) | insights-cards-producer | ../03-pages/rulebooks/insights.md § I1 | insights.insights | — | SG:S28,S2,S1 · AG |
| T2 | Technology landscape strip | D2 Insights | — | insights-landscape-producer (tile `basis`/`detail`/`named_items` only; counts recomputed from T1, never stored — produce after techstack-register-producer has settled T1) | ../03-pages/rulebooks/insights.md § T2 | insights.landscape | — (techstack, via T1) | CG (T2 ↔ T1 reconcile; CG-12 detail ≤ 90 chars) |
| H4 | Workbook grain scores | D3 Heatmap | — | heatmap-grid-producer | ../03-pages/rulebooks/heatmap.md § H4 | heatmap.workbook_scores | peer_scores | CG (grain; source_cell mandatory) |
| H1 | Focus areas | D3 Heatmap | — (cards expand → DD-10) | heatmap-focus-producer | ../03-pages/rulebooks/heatmap.md § H1 | heatmap.focus_areas | — | SG:S29,S9,S18 · CG (provenance triple) · AG |
| H2 | Cell evidence | D3 Heatmap | H4 (subcap row click → DD-1 drawer) | heatmap-evidence-producer | ../03-pages/rulebooks/heatmap.md § H2 | heatmap.cell_evidence | — | SG:S1 · CG (grain; synthesis-count equality; H13) · AG |
| H6 | Evidence store | D3 Heatmap | — (any evidence chip → DD-2 drawer) | heatmap-evidence-producer | ../03-pages/rulebooks/heatmap.md § H6 | heatmap.evidence | — | ET (ET-04 excerpts) · CG |
| H9 | Value-chain view | D3 Heatmap | — | heatmap-valuechain-producer — envelope only; the stages, their order, their cell membership and their not-scored counts remain **server-computed, no producer** (the agent submits `fields: {}` and the arrangement joins `ccg_value_chains`) | ../03-pages/rulebooks/heatmap.md § H9 | heatmap.value_chain (optional) | — | — (H4's served scores govern) |
| P1 | Platform fit & story | D4 Platform | — (tiles expand → DD-11; gate rows → DD-13) | platform-fit-producer | ../03-pages/rulebooks/platform.md § P1 | platform.platform_story | platform_readiness | SG:S31,S13,S17 · CG (breakdown = headline; catalogue_path) · AG |
| P2 | Recommendations | D4 Platform | — (row opens → DD-4) | platform-fit-producer | ../03-pages/rulebooks/platform.md § P2 | platform.recommendations | — | SG:S32 · CG · AG |
| P2b | Conversation starters | D4 Platform | — | platform-conversation-producer | ../03-pages/rulebooks/platform.md § P2b | platform.starters | — | SG:S31 · CG (no codes in spoken text) · AG |
| P3 | Transformation roadmap | D4 Platform | — | platform-roadmap-producer | ../03-pages/rulebooks/platform.md § P3 | platform.roadmap | — | CG (P3 ↔ P2 rec ids reconcile) |
| P4 | Stair-step curve | D4 Platform | — | platform-roadmap-producer | ../03-pages/rulebooks/platform.md § P4 | platform.stairstep | — | SG:S33 · CG (step order = roadmap = sequencing) |
| C1 | Digital evolution timeline | D5 Context | — (events expand → DD-7) | context-timeline-producer | ../03-pages/rulebooks/context.md § C1 | context.timeline | — | SG:S34 · CG (G6 arc ≥ 3 points; G9 dated; CG-09 signal) · AG |
| C2 | Issue register & Gantt | D5 Context | — (bars expand → DD-8) | context-risk-producer | ../03-pages/rulebooks/context.md § C2 | context.issue_register | — | CG (one row per matter; status never NULL) |
| C3 | Regulatory standing | D5 Context | — | context-risk-producer | ../03-pages/rulebooks/context.md § C3 | context.regulatory_standing | — | ET (G1 identity, G2 anchor) · CG · AG |
| C4 | Sentiment overview | D5 Context | — (tiles expand → DD-12) | context-sentiment-producer (projects O9's bars under the O9 prompt at Context depth — overview-market-producer must produce O9 first) | ../03-pages/rulebooks/context.md § C4 | context.context_sentiment | sentiment | SG:S8 · CG (reconciles to O9 by e_id) |
| C5 | Acquisition history | D5 Context | — (rows expand → DD-14) | context-timeline-producer | ../03-pages/rulebooks/context.md § C5 | context.acquisitions | — | CG (dated; status enum; consistent with C1, O3) · AG |
| C6 | Financial trajectory | D5 Context | — | server-computed — no producer ("There is nothing to produce": re-renders overview-market-producer's O8 row) | 03-pages/2-overview.md § C6 | overview.financial_series | — | — (O8's gates govern; C6 ↔ O8 asserted identical) |
| T1 | Technology stack register | D6 Tech stack | — | techstack-register-producer (`items[]`, `dropped[]`, `compliance_attestations`) + techstack-layers-producer (`layers[]`, `enrichment_status`, section `narrative_thread`, recounted from the rows) | ../03-pages/rulebooks/techstack.md § T1 | techstack.techstack | techstack | ET (cited or dropped[]) · CG (CG-09 status; CG-12 detection_basis) |
| T3 | Platform detail | D6 Tech stack | T1 (register row → per-item sub-page) | techstack-surface-producer — per-row `dma_impact`, `peer_coverage`, `peer_deployments[]`, all optional; the one page surface with no per-surface owner, because its fields ride the register rows techstack-register-producer preserves byte-identically | ../03-pages/rulebooks/techstack.md § T3 | techstack.techstack | techstack | AG (AG-04 peer technographics) · CG |
| H3 | Thin-evidence alerts | D7 Health (submitted on the heatmap page) | — | heatmap-signals-producer | ../03-pages/rulebooks/heatmap.md § H3 | heatmap.alerts | — | SG:S3,S30 · ET (ladder before alerting) · AG |
| H5 | Safeguard gates | D7 Health (submitted on the heatmap page) | — | heatmap-signals-producer | ../03-pages/rulebooks/heatmap.md § H5 | heatmap.safeguard_gates | — | CG (only gates actually applied; plain_label 6–24 words per CG-12) |
| H7 | Evidence age tracker | D7 Health (submitted on the heatmap page) | — | heatmap-freshness-producer | ../03-pages/rulebooks/heatmap.md § H7 | heatmap.evidence_age | — | CG (no NaN; status follows band) · ET (domain identity) |
| H8 | Cross-entity patterns | D7 Health (submitted on the heatmap page) | — | heatmap-signals-producer | ../03-pages/rulebooks/heatmap.md § H8 | heatmap.cohort_patterns (optional) | — | CG (cohort ≥ 5; threshold enforced; entity_ids stripped for every audience) |
| V1 | Version diff | D7 Health | — | server-computed — no producer (derived from the runs table; alias bridge across a catalogue bump) | — (no pack anchor; contract in 05-lifecycle/2-versioning.md) | — (derived, no section) | — | — (comparison rules in 2-versioning.md govern) |

Dashboard totals, counted: D1 13 · D2 2 · D3 5 · D4 5 · D5 6 · D6 2 · D7 5 = **38**,
matching the spec's cover ("Surface Spec · 38 surfaces") and CLAUDE.md's "38
client-facing surfaces across 7 dashboards". The spec's own per-page counts agree:
"Thirteen surfaces, twelve sections" (D1); "2 sections · 2 surfaces" (D2);
"9 sections · 5 surfaces" (D3, four sections handed to Health); "5 sections ·
5 surfaces" (D4); "Six surfaces from five sections" (D5); "1 sections · 2 surfaces"
(D6); "4 sections · 5 surfaces" (D7).

## The drilldown atlas — 15 panels

Every panel renders from the page response — none fetches — so a panel's payload
section is its parent's. Shells: drawer (DD-1, DD-2), modal (DD-3–DD-6), inline
expansion (DD-7–DD-15). Five carry their own synthesis prompt in the spec; DD-1's
was folded into H2's section prompt because a drilldown is not a submission unit
(see the reissue note in `03-pages/1-heatmap.md` § H2).

| ID | Name | Dashboard | Parent (opens from) | Producing agent | Rulebook anchor | Payload section(s) | Enrichment facets | Gate families |
|---|---|---|---|---|---|---|---|---|
| DD-1 | Synthesis drawer | D3 | H4 sub-capability row (payload is H2's) | heatmap-evidence-producer, via H2 | 04-craft/4-card-anatomy.md § DD-1; ../03-pages/rulebooks/heatmap.md § H2 | heatmap.cell_evidence | — | SG:S1 · CG (grain; H13) · AG |
| DD-2 | Evidence drawer | all pages | any evidence chip | heatmap-evidence-producer, via H6 | ../03-pages/rulebooks/heatmap.md § H6 | heatmap.evidence | — | SG:S1 · ET (resolvable URL; G16 recency) · CG |
| DD-3 | Insight modal | D2 | I1 card | insights-cards-producer, via I1 | ../03-pages/rulebooks/insights.md § I1 | insights.insights | — | SG:S28,S2,S1 · AG |
| DD-4 | Recommendation modal | D4 | P2 row | platform-fit-producer, via P2 | ../03-pages/rulebooks/platform.md § P2 | platform.recommendations | — | SG:S32 · CG · AG |
| DD-5 | New run modal | all pages | request-rerun control | server-computed — no producer (app chrome) | — (no pack anchor) | — | — | — |
| DD-6 | Intelligence panel | all pages | Open Intelligence control | no separate producer — renders parent payload | — (parent's anchor) | parent's | — | — (parent's gates govern) |
| DD-7 | Event detail | D5 | C1 timeline event | context-timeline-producer, via C1 | ../03-pages/rulebooks/context.md § C1 | context.timeline | — | SG:S34 · CG (G6) · AG |
| DD-8 | Issue detail | D5 | C2 register row | no separate producer — renders C2's payload (context-risk-producer) | ../03-pages/rulebooks/context.md § C2 | context.issue_register | — | — (C2's gates govern) |
| DD-9 | Finding expansion | D1 | O6 findings row | no separate producer — renders O6's payload (overview-findings-producer) | ../03-pages/rulebooks/overview.md § O6 | overview.findings | — | — (O6's gates govern) |
| DD-10 | Focus area expansion | D3 | H1 focus-area card | no separate producer — renders H1's payload (heatmap-focus-producer) | ../03-pages/rulebooks/heatmap.md § H1 | heatmap.focus_areas | — | — (H1's gates govern) |
| DD-11 | Platform tile expansion | D4 | P1 fit tile (O5 tiles navigate here cross-page) | no separate producer — renders P1's payload (platform-fit-producer) | ../03-pages/rulebooks/platform.md § P1 | platform.platform_story | — | — (P1's gates govern; breakdown must reproduce O5/P1 arithmetic) |
| DD-12 | Sentiment tile expansion | D5 | C4 context tile | no separate producer — renders C4's payload (context-sentiment-producer) | ../03-pages/rulebooks/context.md § C4 | context.context_sentiment | — | — (C4's gates govern) |
| DD-13 | Readiness gate expansion | D4 | P1 prerequisite gate row | no separate producer — renders P1's payload (platform-fit-producer) | ../03-pages/rulebooks/platform.md § P1 | platform.platform_story | — | — (P1's gates govern) |
| DD-14 | Acquisition expansion | D5 | C5 acquisition row | no separate producer — renders C5's payload (context-timeline-producer) | ../03-pages/rulebooks/context.md § C5 | context.acquisitions | — | — (C5's gates govern) |
| DD-15 | Ceiling rationale | D1 | O1b ceiling row | no separate producer — renders O1b's payload (overview-governance-producer) | ../03-pages/rulebooks/overview.md § O1b | overview.ceilings | — | — (O1b's gates govern) |

## The no-orphan rule

A surface with no producing agent and no server-computed marker is a defect — it is
a card that will render empty under a real client's name, and nothing will have
failed. Every row above carries one or the other; a row that carries neither may
not be added.

The **package-vetter checks each new Surface Specification version against this
map**: a surface id the new spec defines that this map does not carry, a map row
whose spec section has vanished, or a producer column that names an agent that does
not exist under `plugins/dma-insights/agents/` is a finding to record
(`record_finding`) before any production run uses the new spec. The map is updated
in the same change that resolves the finding, never silently.

Three drift classes this census already carries, so the vetter knows they are
deliberate and not omissions:

- **Pack contracts that outgrew the spec.** The spec says "no prompt block exists"
  for six of the 38 (T2, T3, H9, C4, C6, V1); the pack has since given T2, T3 and
  C4 authored contracts (tile prose, per-row detail cards, the O9 projection). The
  map records the pack's reality; the spec quote records where it started.
- **Ids the tasking vocabulary implies but the spec never defines.** There are no
  T4–T8 anywhere in the Surface Specification — the T-family stops at T3, with T2
  rendering on Insights. The directory, refresh-cadence and run-history chrome
  carry no surface ids in the spec (the directory reads one materialised view,
  invariant 8) and sit outside this census. Do not mint ids for any of these.
- **Owner rows that are not one-agent-one-row.** The column names per-surface
  producers, but three rows deliberately break the one-to-one shape and none of
  them is an orphan. **T1** carries two owners because the register rows and the
  rollup computed from them are different claims with different failure modes —
  `techstack-register-producer` writes `items[]` and `dropped[]`,
  `techstack-layers-producer` recounts `layers[]` from what it finds there. **T3**
  names a *page* producer because no per-surface agent owns it; its fields ride
  the register rows, so the pass belongs to the agent that already assembles the
  page. **H9** names a producer for an envelope whose contents are server-joined.
  A vetter reading these three as drift should read this paragraph first; a fourth
  such row appearing without a paragraph explaining it is a finding.

**OPEN items:** none. Every id in both tables is grounded in a spec section
heading or, for the pack-only deltas above, in the named pack file.
