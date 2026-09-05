# Routing — what goes to which agent, and why that is the speed

The pipeline exists so that the smallest true unit of work runs, not the
whole run. A one-card repair that re-produces six pages is the slow response
the hierarchy was built to remove.

## First: which pipeline is this request even for?

Three request shapes arrive at this system, and mistaking one for another
costs a whole wrong run — a research ask that gets answered by re-scanning
the intake Drive produces nothing, and an ingestion ask that spawns a
research run researches a client who already shipped.

| the request hands you | it is | route to |
|---|---|---|
| an entity + sub-vertical + evidence mode, and NO finished package | a research engagement — the package must be PRODUCED | `research-conductor` (the research tier below) |
| a finished `<Client> - DMA` folder, or "load/publish/make live this client" | package intake | `package-vetter` first, then production; the scheduled package scan is how the app itself notices the folder |
| a verdict, ticket, reviewer note or surface/page id | a repair | the surface and page tables below |

When a request could read as two of these, the decider is what EXISTS: no
client folder in the intake Drive → research; folder present and vetted →
production; run already promoted → repair. Check, don't infer.

## The pipeline, in order

```
route → produce → challenge → consolidate → submit → learn
```

| stage | agent | may submit? |
|---|---|---|
| produce | the per-surface producer that owns the named surface, or the page producer when a whole page is in scope | no |
| challenge | `finding-challenger` (dma-research discipline) | no |
| consolidate | `page-consolidator` (refuses unchallenged input) | no |
| submit + promote | `surface-producer` only | **yes** |
| learn | `qa-overseer` (writes the findings memory) | memory only |

The challenger runs BEFORE the consolidator, always: the consolidator's
method assumes per-claim verdicts exist, and it refuses input without them.
The qa-overseer runs at the END of every production or repair, green or not
— a green run with a buried defect still gets its finding recorded.

## Not every section is synthesised — check its disposition first

`produce → challenge → consolidate` is the path for a section that is
genuinely SYNTHESISED. Most sections are not. `references/section_sources.json`
(read it, or run `python3 -m engine.surface_export plan --page <page>`) gives
every section a disposition, and the page brief carries the same split:

- **convert** (`workbook` / `report`) — the section is FORMATTED from its
  workbook tab(s) or a challenged report section. It is **not re-synthesised
  and not re-challenged** — the research layer already challenged that
  content, and a second challenge is the duplicate work this split exists to
  remove. `engine.surface_export.scaffold` shapes and validates it against the
  page contract before `ship_page.py` spends a submission. This is the large
  majority of sections.
- **produce** (`enrichment` / `synthesis`) — a per-surface producer writes it,
  through `produce → challenge → consolidate`. `enrichment` sections need
  their enrichment registered as evidence first. This is the ONLY set the
  challenger and consolidator run on. Today that is `overview.leadership`,
  `overview.sentiment`, `overview.thought_leadership` and
  `heatmap.cohort_patterns`.
- **server** — the section submits `fields: {}` plus the page thread; the app
  joins the arrangement server-side (`heatmap.value_chain`).

So before dispatching a per-surface producer, confirm the section's
disposition is `produce`. A `convert` section routed through a producer is the
duplicate synthesis (and the duplicate challenge) this table is drawn to avoid.

The same map reaches the **card and the drawer**: `section_sources.json`'s
`cards` block (also `join://cards`, or `engine.surface_export cards --section
<page.section>`) gives every card array — each finding, insight, recommendation,
tile, bar, register row — its own route and the exact tab COLUMNS / report
section / enrichment facet that feed it; a card flagged `connector_authored`
(safeguard gates) or a key under `computed_never_sent` is written by the app and
must never be authored. `scaffold_card` refuses an item key the contract card
does not declare. The `drilldowns` atlas (`join://drilldowns`, `… drawers`)
says which drawer carries its own synthesis prompt (DD-1/2/3/4/7) and which
render the parent card's payload — so a drawer is never produced twice either.

## Dispatch mode — the top session orchestrates, one level deep

Trigger-fired sessions DO carry the Agent tool, but only ONE nesting level:
a subagent cannot spawn further subagents (MEM-0106, measured 2026-08-20 —
an enclosing surface-producer subagent stalled the whole pipeline, then
overturned the package-vetter's REFUSE by its own re-analysis because it
could not dispatch the sanctioned re-vet). Two rules follow:

1. **The TOP session is the orchestrator.** It dispatches every routed
   stage DIRECTLY — the per-surface producers, the checkers, the
   consolidator, the vetter — via the Agent tool, in this file's order.
   Never delegate the pipeline to one enclosing orchestrator subagent: it
   cannot fan out, and an orchestrator that cannot dispatch improvises.
   Where the Agent tool is genuinely absent, `scripts/agent_run.py` runs a
   stage as a headless CLI session — same agents, same order, same
   refusals.
2. **Verdict integrity survives dispatch.** A package-vetter REFUSE is
   overturned only by a fresh, sanctioned re-vet dispatched from the top
   session — never by a producer's own re-analysis, however correct it
   reads.

Division of labour is unchanged: headless children and subagents reach the
DMA connector natively but carry NO claude.ai enrichment connectors — those
exist only in the top session, attached to the Routine. Connector-bound
searches (Clay, Exa, Tavily, Vibe-Prospecting, Indeed) run only in the top
session: a dispatched producer that needs one emits it in a
`search_requests` array (query + falsifier pairing + facet) instead of
fabricating or skipping; the top session executes the requests through its
real connectors, registers the evidence, logs the source outcomes in the
yield ledger, and re-invokes the producer with the evidence ids. Enrichment
honesty survives the hop: a search the top session refused or could not run
is recorded not-run, never invented.

## Two tiers of producer, and which tier a request reaches

There are thirty producing agents in two tiers, and the tier is chosen by
what the request *names*, not by how large the repair feels.

- **Six page producers** — `overview-`, `insights-`, `heatmap-`,
  `platform-`, `context-` and `techstack-surface-producer`. A request that
  names a **page** reaches one of these. A page producer no longer writes
  section bodies itself: it fans the page out to the per-surface producers
  below, and keeps page assembly, the page's narrative thread, the
  cross-surface reconciliation and the hand-off to `finding-challenger`.
- **Twenty-four per-surface producers** — one agent per surface, or per
  tightly-coupled pair of surfaces that would contradict each other if two
  agents wrote them. A request that names a **surface** reaches exactly one
  of these, directly; the page producer above it is not invoked at all.

**Repairing one surface never re-runs a page.** This is the rule the two
tiers exist to enforce. When a verdict, a rejection ticket, an audit finding
or a reviewer note names a JSON path, the path names a surface and the
surface names its owner — route to that owner alone, challenge its output,
consolidate the one page it belongs to, resubmit that one page. Producing
the other eleven overview sections to fix `overview.why_now` costs an hour
and eleven fresh chances to introduce a defect in content that was already
passing. A page producer is invoked when a page is genuinely being authored
or re-authored, never as a wrapper around a single-surface repair.

## The surface routing table — one surface, one owner

The authoritative census — every surface id, its owner, its payload section,
its rulebook anchor, its enrichment facets and its gate families — is
`surface-map.md` in this directory. This table routes by surface; the map
resolves by row.

| surface | payload section | route to |
|---|---|---|
| O1 scores & peer benchmarks · O2 firmographics strip | `overview.scores` · `overview.firmographics` | `overview-hero-producer` |
| O3 why-now signals | `overview.why_now` | `overview-whynow-producer` |
| O4 executive summary · every overview `narrative_thread` | `overview.exec_summary` | `overview-narrative-producer` |
| O5 opportunity surface tiles | `overview.opportunity` | `overview-opportunity-producer` |
| O6 top findings (+ DD-9) | `overview.findings` | `overview-findings-producer` |
| O7 leadership panel · O12 thought-leadership signal | `overview.leadership` · `overview.thought_leadership` | `overview-people-producer` |
| O8 financial trajectory · O9 sentiment | `overview.financial_series` · `overview.sentiment` | `overview-market-producer` |
| O1b capability ceilings (+ DD-15) · O10/O11 evidence coverage and tier distribution | `overview.ceilings` · `overview.evidence_coverage` | `overview-governance-producer` |
| I1 insight cards (+ DD-3 modal) | `insights.insights` | `insights-cards-producer` |
| T2 technology landscape strip | `insights.landscape` | `insights-landscape-producer` |
| H4 workbook grain scores | `heatmap.workbook_scores` | `heatmap-grid-producer` |
| H1 focus areas (+ DD-10) | `heatmap.focus_areas` | `heatmap-focus-producer` |
| H2 cell evidence (+ DD-1 drawer) · H6 evidence store (+ DD-2 drawer) | `heatmap.cell_evidence` · `heatmap.evidence` | `heatmap-evidence-producer` |
| H9 value-chain view | `heatmap.value_chain` | `heatmap-valuechain-producer` (envelope only) |
| H3 thin-evidence alerts · H5 safeguard gates · H8 cross-entity patterns | `heatmap.alerts` · `heatmap.safeguard_gates` · `heatmap.cohort_patterns` | `heatmap-signals-producer` |
| H7 evidence age tracker | `heatmap.evidence_age` | `heatmap-freshness-producer` |
| P1 platform fit & story (+ DD-11, DD-13) · P2 recommendations (+ DD-4) | `platform.platform_story` · `platform.recommendations` | `platform-fit-producer` |
| P2b conversation starters | `platform.starters` | `platform-conversation-producer` |
| P3 transformation roadmap · P4 stair-step curve | `platform.roadmap` · `platform.stairstep` | `platform-roadmap-producer` |
| C1 digital evolution timeline (+ DD-7) · C5 acquisition history (+ DD-14) | `context.timeline` · `context.acquisitions` | `context-timeline-producer` |
| C2 issue register & Gantt (+ DD-8) · C3 regulatory standing | `context.issue_register` · `context.regulatory_standing` | `context-risk-producer` |
| C4 sentiment overview (+ DD-12) | `context.context_sentiment` | `context-sentiment-producer` |
| T1 register rows, `dropped[]`, attestations | `techstack.techstack` (`items[]`, `dropped[]`) | `techstack-register-producer` |
| T1 layer rollup, enrichment status, section thread | `techstack.techstack` (`layers[]`, `enrichment_status`) | `techstack-layers-producer` |
| T3 platform detail (`dma_impact`, `peer_coverage`, `peer_deployments[]`) | `techstack.techstack` (per-row) | `techstack-surface-producer` — the one page surface with no per-surface owner; its fields ride the register rows the register producer preserves byte-identically |
| C6 financial trajectory · V1 version diff · DD-5 new-run modal · DD-6 intelligence panel | — | server-computed — no producer (see `surface-map.md`) |

Where a row names two surfaces, they are one agent's job because they are
one claim argued twice: split them and the two halves drift. O8 and O9 are
the outside world's two measurements of the same client; P3 and P4 are one
order argued twice; C2 and C3 are the two halves of one risk claim; H2 and
H6 are the same evidence seen per-cell and per-run.

### Four ordered pairs the fan-out must respect

Most surfaces on a page are independent and go out in parallel. Four are
not, and a router that parallelises them will produce a page that
contradicts itself:

- **O9 before C4.** The context sentiment tiles project the overview's bars
  at Context depth and reconcile to O9 by `e_id`; `context-sentiment-producer`
  reads O9, it never re-polls.
- **T1 before T2.** `insights-landscape-producer` recomputes four tile counts
  from the register rows; if the register moves, it recounts rather than
  adjusts.
- **T1 before the layer rollup.** `techstack-layers-producer` recounts
  `layers[].detected` from `items[].status`; whenever
  `techstack-register-producer` adds, removes, restatuses or moves a row it
  says so in its return, and the rollup is re-run.
- **The rest of overview before O4.** `overview-narrative-producer` writes
  the argument last, because a thread written over claims that later change
  is a thread that describes a page that no longer exists.

## The page routing table — a page fans out

A request that names a page routes here. The page producer invokes the
surface producers listed, then assembles.

Agent names are written out in full here on purpose: a router that expands an
abbreviation guesses, and a guessed agent name is a route to nothing.

| page named | page producer | fans out to |
|---|---|---|
| overview / D1 | `overview-surface-producer` | `overview-hero-producer`, `overview-whynow-producer`, `overview-opportunity-producer`, `overview-findings-producer`, `overview-people-producer`, `overview-market-producer`, `overview-governance-producer`, then `overview-narrative-producer` last |
| insights / D2 | `insights-surface-producer` | `insights-cards-producer`, and `insights-landscape-producer` once T1 is settled |
| heatmap / D3 (+ the four D7 Health sections) | `heatmap-surface-producer` | `heatmap-grid-producer`, `heatmap-focus-producer`, `heatmap-evidence-producer`, `heatmap-valuechain-producer`, `heatmap-signals-producer`, `heatmap-freshness-producer` |
| platform / D4 | `platform-surface-producer` | `platform-fit-producer`, `platform-conversation-producer`, `platform-roadmap-producer` |
| context / D5 | `context-surface-producer` | `context-timeline-producer`, `context-risk-producer`, and `context-sentiment-producer` once O9 exists |
| techstack / D6 | `techstack-surface-producer` | `techstack-register-producer`, then `techstack-layers-producer`; the T3 detail pass stays with the page producer |

## The three checkers, and where each one runs

They are not optional and they are not interchangeable. Each answers a
question the producers cannot answer about themselves, and each runs at a
fixed point — a checker invoked after promotion is a post-mortem, not a
gate.

| checker | the question | runs |
|---|---|---|
| `evidence-integrity-checker` | does every cited id resolve, belong to this entity and this run, and carry a verbatim 50–500 character excerpt? | after any producer touches `heatmap.cell_evidence`, `heatmap.evidence` or `heatmap.evidence_age`, and before promotion. A `foreign` id HALTS production (invariant 4) |
| `numeric-reconciliation-checker` | does every figure rendered twice agree, at the 0.05 grain tolerance? | after the page-consolidator, before submit — the composite against the grid, the landscape counts against the register, the tiles against the engine |
| `exclusion-boundary-auditor` | does the customer projection carry anything internal — probe ladders, tiers, cap vocabulary, contact routes, reasoning traces, cohort entity ids? | before submit on any page, and again after promotion before a client link is shared |

All three are READ-ONLY by construction: they carry no write tool and no
submit or promote tool, so a checker cannot repair what it judges. Route
the repair to the surface's own producer.

## The enrichment tier — plan, then fetch, then audit the record

`enrichment-planner` reads `list_enrichment_gaps` and returns a ranked
worklist with a pathway per gap. The two specialists execute one pathway
each, and neither mints an evidence id — they return candidates for the
top session to register:

| you need | route to |
|---|---|
| which gaps are worth closing, by what route, in what order | `enrichment-planner` |
| a Clay call plan or a machine technographic scan | `enrichment-connector-specialist` |
| a web pathway, a contradictory source, or an empty state that must be earned | `enrichment-web-specialist` |
| proof that every facet's attempt is recorded with the outcome it actually had | `enrichment-ledger-auditor` |

The ledger auditor is the honesty check on the other three: it holds
`list_enrichment_gaps` beside each section's `enrichment_status` and
reports a facet that never ran but reads as though it found nothing
(MEM-0082). It is read-only.

## The learning pair — never invoked from a production session

`learning-grader` and `learning-testgen` belong to the weekly rectifier,
not to synthesis. The grader scores a proposed refinement against
`skills/dma-rectifier/assets/learning_rubric.json` at a 0.75 admission
threshold; the testgen writes 5–15 adversarial and regression cases per
admitted refinement, every one able to FAIL. Both are independent of the
fixer BY CONSTRUCTION — no write tool, no connector write tool — so
neither can edit what it grades or cases. A production session that finds
itself reaching for them is repairing the toolchain mid-run, which is the
rectifier's job and nobody else's.

## Everything else

| you need | route to |
|---|---|
| a package to vet before anything is parsed | `package-vetter` |
| a passing run about to be believed | `adversarial-verifier` |
| what production actually serves | `deployed-app-auditor` |
| a defect class that keeps recurring | `rectifier` |

## The research tier — upstream of every package

Surface production consumes a finished assessment package; the research
tier is what produces one. A research engagement (an entity, a
sub-vertical, an evidence mode) routes to **`research-conductor`**, which
binds the run against a PREFLIGHT the engagement owner answered, opens the
client folder, closes the PRELIM phase, builds the knowledge graph from the
pillar toolkits, and dispatches one researcher per catalogue category —
sixteen, generated from one template by `scripts/gen_research_agents.py`,
each bound to its grain and nothing else. A repair that names a category
(a FAILED floors gate, a challenged subcap) routes to that category's
researcher directly, never through a full re-run — the same
smallest-true-unit rule as the per-surface producers above.

| category | agent |
|---|---|
| P1C1 Digital Strategy & Vision | `research-p1c1-producer` |
| P1C2 Governance & Risk Appetite | `research-p1c2-producer` |
| P1C3 Innovation Management & Funding | `research-p1c3-producer` |
| P1C4 Culture & Change Enablement | `research-p1c4-producer` |
| P2C1 Digital Marketing & Acquisition | `research-p2c1-producer` |
| P2C2 Onboarding & Fulfillment | `research-p2c2-producer` |
| P2C3 Omnichannel Servicing & Support | `research-p2c3-producer` |
| P2C4 Personalization & Proactive Engagement | `research-p2c4-producer` |
| P3C1 Core Process Automation | `research-p3c1-producer` |
| P3C2 Operational Risk & Fraud Management | `research-p3c2-producer` |
| P3C3 Compliance, Supervision & Surveillance | `research-p3c3-producer` |
| P3C4 Business Resilience & Third-Party Management | `research-p3c4-producer` |
| P4C1 Data Management & Governance | `research-p4c1-producer` |
| P4C2 Analytics & AI Enablement | `research-p4c2-producer` |
| P4C3 Technology Architecture & Integration | `research-p4c3-producer` |
| P4C4 Information Security & Cybersecurity | `research-p4c4-producer` |

**Three phases run BEFORE any category is dispatched, and each is a gate
rather than a habit:**

| phase | what it is | what refuses without it |
|---|---|---|
| **preflight** | the financial-statement review, the LOB census, and the `AskUserQuestion` exchange that CONFIRMED the sub-vertical and the evidence mode | `engine.cli start` — sub-vertical, scope, mode and all three bases are DERIVED from the preflight, not typed |
| **client folder** | `<Entity> - DMA` opened at START, `status: IN_PROGRESS`, pushed to intake | nothing; but the watchdog reports `NO_CLIENT_FOLDER`, because a run that stops early with no folder leaves an operator nothing to find |
| **PRELIM** | firmographics, financials, leadership, timeline, peers, technology baseline — the institution, before its capabilities | `orient` serves NO category card while it is open |

A request that reads as research but names no entity, or names one whose
sub-vertical is genuinely ambiguous, is a QUESTION for the engagement
owner, not a run to start on a guess. That is the one place in this
pipeline where stopping to ask beats proceeding well.

The researchers write only their own category, only through the engine CLI
(the workbook's refusals are the write control); the conductor gates,
renders the four deliverables, checks that every workbook tab is populated
or has a stated reason (`engine.completeness check` — the validator checks
shape, that checks content), completes and ships the `<Entity> - DMA`
folder, and runs the memory backup-then-cleanup lifecycle. None of them
touches the connector's write tools — a research run that is ready for
surface production enters, like every package, through the package-vetter.

## Orchestration — what one agent hands the next

REPORTED 2026-09-03 by the engagement owner: "There is no orchestration
existing between the subagents and main agents. Ensure efficient context
management and information sharing where needed."

Every dispatch in this table now carries a BRIEF rather than a prompt
somebody typed. `engine.brief` is four derived views over the run's own
sheets, so there is no second record to drift and no context to paste:

| command | what it hands over |
|---|---|
| `engine.brief batch --out-dir <D>` | one bounded packet per category plus the `agent_run.py --batch` array — the conductor's whole dispatch |
| `engine.brief dispatch --category C` | that category's packet: the run's shared state, each open cell's owed volleys AND the evidence already registered for it, sibling sources worth reading, the lane's own notebook digest, its search budget |
| `engine.brief reuse --subcap X` | what the run already holds for X — read before searching, because the run has paid for it |
| `engine.brief handback --category C` | what the category established, computed from the sheets, plus the leads its sources open for OTHER categories |

Two rules follow from it, and both are enforced rather than advised: a
producer's FIRST command is its brief (the manifests say so, and the session
hook repeats it), and an empty cell cannot be declared absent while the
register names it (`ledger.declare_absence` refuses; the floors gate carries
`absence_over_evidence` blocking and `evidence_unattached` advisory). Every
packet is measured against `BRIEF_CHAR_CEILING` — context sharing that is
not bounded is the token bleed under another name.

## The scoring tier — column D, after the research and before the reports

REPORTED 2026-09-03 by the engagement owner: "Report writing starts without
scoring happening." Nothing had owned the scores — `dma-assessment` built a
separate workbook and the report producers read whatever they found. Five
agents now own the SCORING stage of the research workbook, and the stage is
gated at both ends by the engine rather than by the manifest.

| what | agent | may critique? |
|---|---|---|
| open the stage (`engine.assessment open`) — refused until every category's floors gate is PASS with `--require-synthesis`, PRELIM is complete and the template binding is recorded | `research-conductor` | n/a |
| P1's scores: one `engine.assessment score` per subcap — refuses an unchallenged row, a score above the evidence ceiling, a rationale under 150 chars or citing none of the row's own E-ids, an incomplete AI/data overlay | `scoring-p1-producer` | no |
| P2 / P3 / P4, the same, in parallel | `scoring-p2-producer` · `scoring-p3-producer` · `scoring-p4-producer` | no |
| the SCORING_CRITIC verdict per pillar — re-derives a sample, checks ceilings and differentiation; `engine.assessment critique` refuses a scorer as its own critic | `scoring-critic` | **only** |
| the rollup (`engine.assessment rollup`: Pillar_Rollup, Category_Rollup, Coverage_Map, Executive_Summary) and the SCORING gate | `research-conductor` | n/a |

The four producers run **in parallel**, one pillar each, and the critic runs
per pillar as pillars land. `engine.assessment gate` blocks on `unscored`,
`critic_missing`, `rollup_missing`, `score_above_ceiling`, `unchallenged_scored`,
`overlay_incomplete`, `no_differentiation` and the rest, and records its
verdict in `Gate_Log`. **No report section can be written until that verdict
is PASS**: `engine.narrative write` runs the stage preconditions and refuses.
After the gate, `engine.assemble checkpoint` ships the scored workbook to
the client folder so the app can ingest it while the reports are written.

## The report tier — the four deliverables' prose

The 2026-08-30 coverage audit measured sixteen report sections with **no
owner at all**: the renderer read `Report_Narrative` and refused a missing
section, and nothing in the roster wrote one. Four agents close it, and the
split is an independence rule rather than a taste.

| what | agent | may review? |
|---|---|---|
| the Client Research Profile's 8 sections (the pinned Doc) | `report-research-producer` | no |
| the DMA Assessment Report's 11 sections (the pinned Doc) | `report-assessment-producer` | no |
| every section's verdict, and the whole-report adversarial pass | `report-validator` | **only** |
| the technographic scan, as a deliverable rather than a side effect | `technographic-scanner` | n/a |

Before a word: `engine.cli narrative preconditions --report <key>` must be
empty. It lists every failing precondition at once — PRELIM open, no
template binding, a category gate not PASS, the workbook incomplete, and
for the assessment report a SCORING gate that is not PASS. Then the producer
reads the pinned template (`references/templates/<report>.md`) and
`gold_reference.json`; the section spec it writes to is loaded from
`report_templates.json`, so a remembered shape cannot be written.

A section is written through `engine.narrative write`, which refuses prose
that is not an argument — and a body that is not the Doc's: the section's
blocks in order, its card shape (`P1`..`P4` deep dives, `REC-NN`), and the
countable MINIMUM DATA of its control block (five to seven findings, five
fiscal years, the four layers, an AI-and-data overlay per pillar). It must
also state what was weighed AGAINST its own
conclusion, the proxy ladder behind any absence it asserts, the assumptions
it made and which way they cut, the bias it carries, and every inference
tagged with what would confirm it. `Accuracy_Basis` is computed from the
workbook — citation density, ERS mass, how many cited sources support a
challenged subcap — never typed.

`engine.narrative review` refuses a verdict from a section's own author by
name, so the producer/validator split is enforced by the ledger and not by
the manifest. The renderer refuses an unreviewed section, which is why the
validator is on the critical path rather than beside it.

The two producers are **independent of each other** and run in parallel; the
validator runs per section as sections land, then once more over the whole
report. Producers consume the finished research run and never re-run it —
the same rule the surface producers follow.

## Two routes that used to dead-end

Five tasks were traced from the session brief through this table. Three
resolved in two hops. These two did not, and both are fixed here rather than
left to be rediscovered.

### A reviewer Accepted or Rejected an insight card

The rule above routes "when a verdict, a rejection ticket, an audit finding or
a reviewer note **names a JSON path**". Reviewer feedback does not name one:
`list_reviewer_feedback` is keyed by `ic_id` / `display_id` / `run_id` and
carries no path column, so the reviewer channel — the one way a human's
judgement re-enters the pipeline — was the only repair channel this table
could not resolve. Unattended, a rejected card either went unrepaired or was
repaired by re-producing the whole insights page, which is exactly the cost
the two tiers exist to prevent.

**Route by id prefix.** Every authored id belongs to one surface:

| id prefix | what it is | payload section | route to |
|---|---|---|---|
| `ic_id` | an insight card | `insights.insights` | `insights-cards-producer` |
| `rec_id` | a recommendation | `platform.recommendations` | `platform-fit-producer` |
| `f_id` | a top finding | `overview.findings` | `overview-findings-producer` |
| `fa_id` | a focus area | `heatmap.focus_areas` | `heatmap-focus-producer` |
| `ts_id` | a techstack register row | `techstack.techstack` | `techstack-register-producer` |
| `wn_id` | a why-now signal | `overview.why_now` | `overview-whynow-producer` |

These are the six id classes the agent is permitted to mint (invariant 10), so
the table is closed: an id that is not one of these was not authored here, and
a note naming one is a bug report about the id allocator, not a surface repair.

### After a compaction, a resume or a fork

A synthesis firing that produces six pages **will** compact. When it does, the
routing rule, the memory rule and the submit boundary are whatever the
summariser chose to keep — and there was no file that said what to do about
it, so an agent that lost the brief mid-run had nowhere to route even if it
knew to look.

**On the first turn after a compaction, resume or fork, before any other tool
call:**

1. Re-read this file. It is the whole rule; it is 17 KB and it is cheaper than
   one wrong page.
2. `get_run_progress(run_id)` — what is already staged is what you do not
   redo. Staged sections survive compaction; your memory of writing them does
   not.
3. `list_open_rejections(run_id)` and `get_validation_verdict(run_id)` — a
   verdict that landed before the compaction is still the current instruction.
4. Only then take work, and take it through the routing tables above.

The plugin's `SessionStart` hook prints an abbreviated form of this on all
five start sources — `startup`, `clear`, `resume`, `compact`, `fork` — and its
`SubagentStart` hook prints it to every dispatched producer, which do not
inherit the parent's context. If you are reading this because a hook told you
to, that is the mechanism working.

## Gates, and reading a verdict

A verdict names a gate id and the JSON path it fired on. The **path** is what
routes — through the tables above, to one producer. The **gate id** is what
tells you what to change:

- `05-lifecycle/1-gates.md` explains the gates that block most often at
  length, and carries a generated census of all 69 ids in the connector's
  registry. No id the connector can emit is absent from it.
- `explain_gate(gate_id)` is the connector's own authority: the registry's
  wording plus the threshold history, live, for any id.

Do not repair a gate you have not read. A guessed rule passes the gate it was
guessed against and fails the next one.

## Sizing the route

- **One surface flagged** (a reviewer note, a failed gate on one path):
  route exactly that surface to **its per-surface producer**, challenge it,
  consolidate the ONE page, resubmit the one page, promote. The page
  producer does not run. Nothing else runs.
- **Two or three surfaces on one page flagged**: their per-surface producers
  in parallel (subject to the ordered pairs above), one challenge pass, one
  consolidation, one submit. Still no page producer — it earns its place
  only when the page as a whole is being authored.
- **One page wrong as a page** (the storyline is incoherent, the thread
  contradicts the sections, most surfaces need rewriting): the page producer,
  which fans out to all its surface producers, assembles, and hands one page
  to the challenger.
- **A fresh run**: pages fan out in parallel — each page's produce →
  challenge → consolidate chain is independent of the others until the
  cross-page reconciliation, which the surface-producer runs before
  submitting the set. Promotion stays atomic across all six.
- **Repair after a verdict**: the gate names the JSON path; the path names
  the surface; the surface names the per-surface producer. Do not re-produce
  a page to fix a field the verdict located for you, and do not route through
  the page producer to reach a surface producer it would only pass through to.

## Producers consume the research; they never redo it

The package a producer opens already carries a gated category's worth of
work per grain: fused-and-cited evidence with verbatim excerpts, five
volleys answered or NOT_RUN with reasons, an independent challenge, a
technographic register, and the absence ladders. The corpus map
(`02-inputs/5-corpus-map.md`) turns that into an ordered ladder per
surface — **climb it in order and stop at the first rung that answers**,
and the first rung is the package/workbook, not the web. A producer that
re-searches a fact `Evidence_Detail` already states pays three times: the
tokens of the search, the risk of a second answer that now needs
reconciling, and a fresh chance to cite a worse source than the one the
run's RRF consensus already ranked. New searching belongs only to gaps the
enrichment planner names — and a dispatched producer emits those as
`search_requests` for the top session (see Dispatch mode above), never
fires them itself.

## Memory duties per stage

Producers of both tiers read the page rulebook at
`03-pages/rulebooks/<page>.md` before the memory digest — the rulebook is
applied by default, not recalled. Producers read (`get_memory_digest`,
`search_findings`) before authoring; a per-surface producer scopes both to
its own surfaces, which is the second reason the split is fast — a narrower
search returns findings that actually bind. The challenger reports
recurrences against finding ids but records nothing. The qa-overseer alone
writes: `record_finding` for the new, `report_recurrence` for the repeat,
`resolve_finding` for the fix that held, `record_refinement` for the method
that worked. Twice-recurred goes to the rectifier with the finding ids — and
with the rulebook file that should have prevented them, because a recurrence
that got past a rulebook is a defect in the rulebook too.

## Speed notes

The page producers and the twenty-four per-surface producers run on the fast
model tier; the challenger, consolidator and overseer reason on the strong
tier — checking is where depth pays. Producers return JSON, not prose about
JSON. The PreToolUse hook refuses a doomed submit before the network sees it;
treat a hook refusal exactly like a gate refusal, because it is quoting one.

A per-surface producer that finds it cannot fix its surface without changing
a neighbour's says so in its return rather than reaching across the
boundary. Two agents writing the same key is how a page passes every
per-section check and still contradicts itself.
