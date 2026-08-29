# Routing — what goes to which agent, and why that is the speed

The pipeline exists so that the smallest true unit of work runs, not the
whole run. A one-card repair that re-produces six pages is the slow response
the hierarchy was built to remove.

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
creates the run on the workbook substrate, builds the knowledge graph from
the pillar toolkits, and dispatches one researcher per catalogue category —
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

The researchers write only their own category, only through the engine CLI
(the workbook's refusals are the write control); the conductor gates,
renders the four deliverables, assembles and ships the `<Entity> - DMA`
folder, and runs the memory backup-then-cleanup lifecycle. None of them
touches the connector's write tools — a research run that is ready for
surface production enters, like every package, through the package-vetter.

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
