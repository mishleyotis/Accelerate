# Page: platform

Five sections sharing one recommendation id space. Produce them together — a phase citing a recommendation the payload does not describe fails.

**5 sections · 5 surfaces.** Submit with `submit_page_payload(run_id, page='platform', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The four standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `platform_story` | yes | P1 | D4 |
| `recommendations` | yes | P2 | D4 |
| `starters` | yes | P2b | D4 |
| `roadmap` | yes | P3 | D4 |
| `stairstep` | yes | P4 | D4 |

---

## P1 · Platform fit &amp; story

- **Section** `platform.platform_story` — **renders on** D4 (Platform)
- **Contract** Fit score per platform, the client-specific story, gap-to-platform mapping with backing sub-capabilities, and the readiness prerequisite gates.

### Must present

Five platform tiles, each with its fit score, the gaps it addresses, and a story that is about THIS client.

The fit score is computed by engine v2 and is deterministic — the agent EXPLAINS it, never recomputes or re-ranks it.

The breakdown modal must agree with the headline fit (570 of 685 cards disagreed).

Out-of-vertical rank-1 is a defect: a carrier platform must not top a bank's list.

story_md must be whole sentences — 501 cards shipped head-clipped mid-sentence.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| platforms[].fit_score | platform_fit.py engine v2 | fit = 100 × (0.66·opportunity + 0.34·readiness); read, never recomputed |
| platforms[].gaps[] | scoring workbook | the subcapabilities this platform addresses |
| platforms[].story_md | producer | grounded in the client's own gaps and stack |
| vertical guard | platform_fit_data.py | subvertical adjacency; carrier anchors must not surface on banks |

### Prompt

```
Produce the platform fit and story: which L3 platform areas address this client's assessed gaps, grounded, ranked, and with the irrelevant ones visibly discarded. STEP 1 - WORK FROM THE L3 CATALOGUE, NOT FROM VENDOR BRANDS The unit of recommendation is the L3 PLATFORM AREA and its L4 FEATURES. For every claim, the path L3 -> L4 -> sub-capability must be renderable, because that path is what makes the recommendation auditable rather than a vendor preference. Emit catalogue_path per gap row. A claim that cannot name the L4 feature that addresses the cell is not a fit claim. STEP 2 - GROUNDING (per gap row) {subcap_id, name, current_score, peer_score, gap, pillar, l3_area, l4_feature,  catalogue_path, e_ids[]}   current_score MUST equal what the heatmap serves for that id. Assert it within   +/-0.05 before emitting. Every row cites. A gap row with no evidence behind   the current score is not addressable, it is a guess. STEP 3 - FACTOR IN THE ENTITY'S OWN TECH STACK (this changes the answer) Read the stack register and apply it:   - CONFIRMED at this layer -> greenfield becomes EXTENSION. Reframe the     opportunity as adoption/depth, and say so; recommending what they already     own is the Tech Stack Mismatch failure.   - ABSENT with a demand signal (hiring, RFP, board commitment) -> RAISE     priority and cite the signal.   - Mid-migration -> a TIMING CONSTRAINT on everything downstream of it; carry     it into sequencing.   - CLAIMED but unconfirmed -> treat as absent for fit, and flag the     Marketing-Reality Gap. STEP 4 - DISCARD, WITH REASONS Drop a platform when relevance to the sub-vertical < 0.5; when the anchor cells belong to a different entity type (a carrier sub-capability on a bank - one measured defect class); when the client already runs it at that layer; or when it addresses fewer than 3 cells. Emit discarded[] {platform, reason, relevance}. Six clients ranked an out-of-vertical platform first, one with a relevance of 0.35 ignored. A ranking that cannot discard is a sort. STEP 5 - THE EFFORT PROFILE, AND WHERE EFFORT MATTERS MORE Rank the effort dimensions (integration, data quality, process redesign, change management, licensing) for THIS client, from the evidence. The profile must be consistent with the timeline's storyline: if the storyline attributes integration debt to a 2014 core conversion never revisited, integration ranks first. An effort profile that contradicts the history is one of them being wrong. STEP 6 - THE PLATFORM STORY  (90-150 words) Not a dossier and not a vendor pitch: what this platform would change for THIS client, which constraint it lifts, what it depends on, and what it does not solve. Name the cells. Cite. Must reconcile to the composite - if the story argues for a platform the arithmetic ranks third, say why. STEP 7 - THE REASONING LAYER (R-Layer, and it is the point of this page)  A State the rank-1 fit claim with its confidence.  B Argue the runner-up's case explicitly. Inside a 5-point margin, present both    and say the ranking is close.  C Is this platform plausible for this sub-vertical, size tier and regulator?  D Probes, each firing a required search: out-of-vertical rank-1; anchor-cell    entity-type mismatch; Tech Stack Mismatch; stale fit figure computed against    a superseded run; breakdown-not-equal-to-headline; a gap row whose current    score disagrees with the heatmap.  E ACCEPT / REJECT / UNCERTAIN. REJECT -> discard and re-rank. STEP 8 - RECONCILE THE ARITHMETIC WITH THE ANALYST Read the assessment report's platform sections. If the composite's rank-1 is a platform the report does not discuss, that disagreement is a finding: state it, say which won, lower confidence. Never ship an arithmetic rank that silently contradicts the analyst. GATES: S31_platform_distinctiveness; S13_platform_score_lead; S17_exec_fit_stale; breakdown-equals-headline; catalogue_path present per row.
```

---

## P2 · Recommendations

- **Section** `platform.recommendations` — **renders on** D4 (Platform)
- **Contract** Detail, impact, effort, sequencing and provenance. A derived recommendation must never present as analyst judgement.

### Must present

The analyst's recommendations with their detail: what, why, prerequisites, effort, and the capabilities each targets.

Analyst recommendations and synthesised ones must be distinguishable — 32 clients shipped synthetic recs laundered as analyst output.

The drilldown must carry the detail the panel promises.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| recommendations[] | recommendations_detail.json | the analyst's own recs |
| prerequisite_rec_ids | recommendation_validation.json | the dependency edges |
| provenance | producer | 'analyst' or 'synthesised' — required, never blank |
| target_subcap_ids | scoring workbook | must resolve to served cells |

### Prompt

```
Produce the recommendations: evidence-led, gated, sequenced, and honest about the cost of doing nothing. Per recommendation: {rec_id, title, l3_area, l4_feature, phase, provenance, dma_impact[],  root_cause, evidence_ids[], cost_of_inaction, prerequisites[], dependencies[],  sequencing_reason, effort_band, kpi_triple, validation_gate, claim_label}   provenance    ANALYST │ DERIVED. DERIVED means composed from the pack by rule.                 32 clients shipped derived rows presented as analyst                 recommendations. Never mislabel; the AE's credibility depends on                 knowing which is which.   dma_impact[]  one row per affected cell {subcap_id, name, current, target,                 delta}. current MUST equal what the heatmap serves. Assert it.   root_cause    30-60 words, CITED. Why the gap exists - not a restatement of                 the gap. This is the evidence-led requirement: a recommendation                 whose root cause is "score is low" has no root cause.   cost_of_inaction                 30-60 words. REQUIRED. What degrades if this does not happen,                 over what horizon, and which capability absorbs the damage.                 GROUND IT in one of: a dated regulator milestone, a peer                 trajectory, a contract or licence expiry, a migration date                 already in evidence, a stated board commitment. If nothing                 grounds a cost, write "no dated trigger established" - that is a                 better answer than invented urgency, and an AE can use it.   prerequisites[]                 what must be true before this can start, as cells and minimums.   validation_gate                 the readiness condition, expressed as a cell and a threshold                 ("P4C1 >= 2.0"), plus its current verdict MET │ NOT MET and the                 BACKING CELLS that produce that verdict. The readiness drilldown                 renders those backing cells, so the verdict must be traceable to                 them.   kpi_triple    {metric, baseline, target} - the baseline must be a figure that                 exists in the pack with an as_of, not an aspiration.   sequencing_reason                 20-40 words: why THIS phase. The dependency or gate that fixes                 its position. Must agree with the roadmap phases AND the                 stair-step curve - 17 clients shipped a sequence contradicting                 their own roadmap. CHALLENGE  B  Is there a cheaper intervention that closes the same gap? State it and why     it was not chosen. Is there a reason to do this LATER? If so, say it.  D  Probes: platform out-of-vertical; anchor cell of the wrong entity type;     dependency inversion; a stale metric in the impact table; a KPI baseline     with no source; a validation gate asserted with no backing cells.  E  REJECT -> drop the row rather than ship a recommendation you cannot     sequence or gate. GATES: S32_rec_detail (panel and roadmap agree; provenance present); cost_of_inaction non-empty; every current figure reconciles to the heatmap.
```

---

## P2b · Conversation starters

- **Section** `platform.starters` — **renders on** D4 (Platform)
- **Contract** 45–90 word say-it-aloud openers with distinct opening shapes. No codes, no bracketed ids mid-sentence, no score-first opening.

### Prompt

```
Produce the conversation starters: openers an AE can say out loud, each grounded in this client's evidence. Per starter: {rank, provenance, text, opens_on, named_gap_subcap_id,               peer_reference, e_ids[], their_system_reference, followup_question}   provenance      TEMPLATE_FILL │ ANALYST, and RENDER it. A rule-composed starter                   labelled as analyst work is a credibility risk for the AE.   text            45-90 words, and it must pass the SAY-IT-ALOUD TEST: no                   internal codes, no bracketed ids mid-sentence, no "PxCy.z", no                   score-first opening. Put the E-ID at the end.   VARY THE SHAPE - at most one starter per opening move:      - the gap opener          name the capability and what it blocks      - the peer opener         what a comparable institution did, dated      - the timing opener       the window and what closes it      - the their-words opener  quote their own executive (from O12)      - the contradiction opener two of their facts that do not fit together      - the system opener       something in THEIR stack the gap depends on     A set that all opens the same way is a template, not a set. This is the     measured failure: 685 of 685 used one shape.   peer_reference  a NAMED comparable institution and a DATED action, or omit the                   field. "Peers are investing in data platforms" is filler; if                   you cannot name and date it, do not imply it.   their_system_reference                   something from the tech stack register - a platform they run, a                   migration in flight - so the opener shows we looked at their                   environment rather than their score.   followup_question                   what to ask after they respond. A Discovery Question, never a                   toolkit diagnostic question. QUOTE HYGIENE (measured: 76 starters across 39 clients shipped garbled quotes) Quoted material must be a clean, complete, verbatim sentence from a resolvable source. If the mined excerpt is truncated, mid-word or missing its subject, DO NOT REPAIR IT and do not use it - drop to a non-quoting shape. Never invent the missing half of a sentence. CLAIM HYGIENE Never inflate scope. A measured defect had starters claiming a platform "addresses 629 linked capabilities". Cite the count you can name, or state none. CHALLENGE  B  Would the client push back? A claim resting on one source or a stale figure     will not survive the room - change it.  D  Probes: score-first opening; codes in spoken text; a peer reference with no     name or date; an inflated capability count; a quote that does not resolve; a     claim contradicting another surface.  E  REJECT -> replace with a different opening shape rather than softening a     claim you cannot support. GATES: S31_platform_distinctiveness (client-specific, not templated); provenance rendered; no codes in spoken text; every claim cited; opening shapes varied.
```

---

## P3 · Transformation roadmap

- **Section** `platform.roadmap` — **renders on** D4 (Platform)
- **Contract** Sequenced phases referencing the same recommendation ids the page already carries. Order is meaning.

### Must present

Phased sequencing with each phase's capabilities, dependencies and horizon.

Phase order must not contradict the recommendation prerequisites (17 clients did).

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| phases[] | recommendations_detail.json + assessment report | {phase, horizon, capabilities[], depends_on[]} |
| metrics | workbook | any metric quoted must be current, not carried from a prior run |

### Prompt

```
**REISSUED** — added referential integrity against the recommendation set, an
acyclicity assertion, budgets and an explicit undetermined state.

STEP 1 — RETRIEVE THE PHASING
If the package states phasing, use it and record source_kind=retrieved. Derive only if it
does not, and label it derived.

STEP 2 — EMIT
{phase_id, phase, horizon, rec_ids[], capabilities[], depends_on[], rationale, provenance}
horizon plain terms: next two quarters | this year | beyond.
rationale 30–60 words: why this phase sits here and not earlier.

STEP 3 — REFERENTIAL INTEGRITY
Every rec_id must resolve to a recommendation THIS payload describes. A phase citing a
recommendation the page does not carry is a dead link in a document an AE reads aloud.

STEP 4 — SEQUENCING IS THE CONTENT
A phase cannot precede a phase it depends on. Assert the dependency graph is acyclic before
emitting. Order is meaning.

STEP 5 — METRICS
Any figure quoted comes from THIS run and resolves to its named cell.

STEP 6 — ABSENCE
If prerequisites do not determine a sequence, say so and emit the phases unordered with
sequencing_basis=undetermined. Do not invent an order to look decisive.

GATES: rec_ids resolve within the payload · dependency graph acyclic · grain lock
```

---

## P4 · Stair-step curve

- **Section** `platform.stairstep` — **renders on** D4 (Platform)
- **Contract** The maturity ladder and its clusters, or an explicit reason it is not derivable — never a blank card.

### Must present

The ladder from current maturity to target, step by step, with what each step unlocks.

An absent ladder renders a stated empty state, not "Couldn't load stairstep."

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| ladder | workbook current scores + roadmap | {from_level, to_level, steps[]} |
| empty_state | producer | the sentence to render when no ladder is derivable |

### Prompt

```
Produce the stair-step maturity curve. It must RESPOND to the findings - a ladder that would look the same for any client is a template with a name on it. The curve is scoped to a theme (measured scopes: "Data foundation", "Loan origination"), so everything below is per-theme. Per step: {step_level, label, covered_subcap_ids[], current_position, blocking_findings[],  unlocks, effort_band, entry_condition, e_ids[]}   current_position   which step the client occupies TODAY, computed from the                      served scores of covered_subcap_ids. Assert it equals those                      scores - the step the client stands on is a measurement,                      not a judgement.   blocking_findings[] THE POINT OF THE CARD. The specific findings that prevent                      the client reaching this step, BY ID, with their citations.                      They must be findings that exist elsewhere in the pack -                      a blocking finding invented for the ladder is a                      fabrication. A step with no blocking findings above the                      client's current position is unexplained: either find the                      blockers or drop the step.   unlocks            20-40 words: what becomes possible AT this step that was                      not possible below it, in client outcomes rather than                      capability names.   entry_condition    the readiness threshold, as cells and minimums, matching                      the corresponding recommendation's validation_gate.   effort_band        S │ M │ L, consistent with the platform page's effort                      profile. CONSISTENCY (blocking)   - current_position == the served scores for the covered cells.   - blocking_findings ⊂ the findings the pack actually serves.   - step order == roadmap phase order == recommendation sequencing_reason.   - covered_subcap_ids are all cells THIS run serves, and all belong to the     theme this curve is scoped to. CHALLENGE  D Probes: a step whose blockers are not in the pack; a current_position that    disagrees with the heatmap; an order that contradicts the roadmap; a generic    ladder (if no step names a client-specific blocker, the curve is a template).  E REJECT -> rebuild from the findings rather than shipping a generic ladder. GATES: S33_pack_surface_completeness (the surface is exported at all - it was absent for 138 clients until the exporter was fixed); step-order consistency.
```
