# Agents — the index

Forty-seven agent files live in taxonomy folders under
`plugins/dma-insights/agents/` (owner, 2026-08-20: "every agent and subagent
organized well into folders and subfolders so it is easy to follow"); this
file says what each one owns, which tier it belongs to, and who is allowed
to call it.

The tree on disk IS the tier structure described below —
**[The taxonomy on disk](#the-taxonomy-on-disk)** shows it and states the
loading contract that makes nesting safe. This index stays load-bearing for
OWNERSHIP: a folder tells you an agent's family; only the tables here and
the surface map tell you which payload sections it owns.

Two companion files answer the questions this one deliberately does not. The
pipeline — what runs before what, and how a repair is sized down to one
surface — is
`plugins/dma-insights/skills/dma-surface-production/05-lifecycle/routing.md`.
The surface census — every one of the 38 surfaces and 15 drilldown panels, its
payload section, its rulebook anchor and its gate families — is
`plugins/dma-insights/skills/dma-surface-production/05-lifecycle/surface-map.md`.
When this index and the surface map disagree about who owns a surface, the
surface map wins and the disagreement is a finding, because the map is what the
`package-vetter` checks each new Surface Specification version against.

---

## Every agent

Surface ids are the Surface Specification's (O1…O12, I1, H1…H9, P1…P4, C1…C5,
T1…T3, DD-1…DD-15). Section keys are payload paths, and the payload path is the
unambiguous identifier when a routing ticket gets an id wrong.

| Agent | Tier | Surfaces or duties it owns | Invoked by |
|---|---|---|---|
| `surface-producer` | orchestrator | The whole run: claiming, assembly order, cross-page reconciliation, submission, promotion. **The only agent permitted to submit or promote.** | The `dma-surface-production` skill, the scheduled Cowork session, or an operator handing over a package |
| `overview-surface-producer` | per-surface producer | Router for D1 Overview — all thirteen surfaces when a whole page is in play | `surface-producer` |
| `overview-hero-producer` | per-surface producer | O1 `overview.scores` · O2 `overview.firmographics` — one card on the render | `surface-producer`, or `overview-surface-producer` while routing the page |
| `overview-whynow-producer` | per-surface producer | O3 `overview.why_now` and its inline signal expansion | `surface-producer` / `overview-surface-producer` |
| `overview-narrative-producer` | per-surface producer | O4 `overview.exec_summary` plus the `narrative_thread` on every overview section | `surface-producer` / `overview-surface-producer` — **last on the page** |
| `overview-opportunity-producer` | per-surface producer | O5 `overview.opportunity` — engine-scored tiles, factor breakdown, discard list | `surface-producer` / `overview-surface-producer` |
| `overview-findings-producer` | per-surface producer | O6 `overview.findings` and DD-9 | `surface-producer` / `overview-surface-producer` |
| `overview-people-producer` | per-surface producer | O7 `overview.leadership` · O12 `overview.thought_leadership` | `surface-producer` / `overview-surface-producer` |
| `overview-market-producer` | per-surface producer | O8 `overview.financial_series` (renders again as C6) · O9 `overview.sentiment` (re-projected as C4) | `surface-producer` / `overview-surface-producer` — **before the context producers** |
| `overview-governance-producer` | per-surface producer | O1b `overview.ceilings` · O10 and O11 `overview.evidence_coverage` — internal instrumentation, no client audience | `surface-producer` / `overview-surface-producer` |
| `insights-surface-producer` | per-surface producer | Router for D2 Insights — both surfaces | `surface-producer` |
| `insights-cards-producer` | per-surface producer | I1 `insights.insights` and DD-3, the four-tab modal | `surface-producer` / `insights-surface-producer` |
| `insights-landscape-producer` | per-surface producer | T2 `insights.landscape` — four tiles recounted from the T1 register, never stored | `surface-producer` / `insights-surface-producer` — **after the register settles** |
| `heatmap-surface-producer` | per-surface producer | Router for D3 Heatmap and the four D7 Health sections submitted on the heatmap page | `surface-producer` |
| `heatmap-grid-producer` | per-surface producer | H4 `heatmap.workbook_scores` — the run's ground truth | `surface-producer` / `heatmap-surface-producer` — **first on the page** |
| `heatmap-focus-producer` | per-surface producer | H1 `heatmap.focus_areas` and DD-10 | `surface-producer` / `heatmap-surface-producer` |
| `heatmap-evidence-producer` | per-surface producer | H2 `heatmap.cell_evidence` + DD-1 · H6 `heatmap.evidence` + DD-2 | `surface-producer` / `heatmap-surface-producer` |
| `heatmap-valuechain-producer` | per-surface producer | H9 `heatmap.value_chain` — envelope only; stages join server-side from `ccg_value_chains` | `surface-producer` / `heatmap-surface-producer` |
| `heatmap-signals-producer` | per-surface producer | H3 `heatmap.alerts` · H8 `heatmap.cohort_patterns` · H5 `heatmap.safeguard_gates` | `surface-producer` / `heatmap-surface-producer` |
| `heatmap-freshness-producer` | per-surface producer | H7 `heatmap.evidence_age` — the ladder every time-sensitive surface reads | `surface-producer` / `heatmap-surface-producer` |
| `platform-surface-producer` | per-surface producer | Router for D4 Platform — all five surfaces | `surface-producer` |
| `platform-fit-producer` | per-surface producer | P1 `platform.platform_story` · P2 `platform.recommendations` · DD-11, DD-13, DD-4 | `surface-producer` / `platform-surface-producer` — **first on the page** |
| `platform-conversation-producer` | per-surface producer | P2b `platform.starters` — 45–90 word say-it-aloud openers | `surface-producer` / `platform-surface-producer` |
| `platform-roadmap-producer` | per-surface producer | P3 `platform.roadmap` · P4 `platform.stairstep` — one order argued twice | `surface-producer` / `platform-surface-producer` |
| `context-surface-producer` | per-surface producer | Router for D5 Context — five authored surfaces (C6 is server-computed) | `surface-producer` |
| `context-timeline-producer` | per-surface producer | C1 `context.timeline` + DD-7 · C5 `context.acquisitions` + DD-14 | `surface-producer` / `context-surface-producer` |
| `context-risk-producer` | per-surface producer | C2 `context.issue_register` + DD-8 · C3 `context.regulatory_standing` | `surface-producer` / `context-surface-producer` |
| `context-sentiment-producer` | per-surface producer | C4 `context.context_sentiment` + DD-12 — a projection of O9, not a second measurement | `surface-producer` / `context-surface-producer` — **after O9 exists** |
| `techstack-surface-producer` | per-surface producer | Router for D6 Tech stack — T1 and the T3 per-row detail fields | `surface-producer` |
| `techstack-register-producer` | per-surface producer | T1 rows — `items[]`, `dropped[]`, `compliance_attestations` in `techstack.techstack` | `surface-producer` / `techstack-surface-producer` — **before the layers rollup** |
| `techstack-layers-producer` | per-surface producer | T1 shape — `layers[]`, `enrichment_status`, section `narrative_thread` in `techstack.techstack` | `surface-producer` / `techstack-surface-producer` |
| `finding-challenger` | challenge and consolidation | Per-claim adversarial verdicts on freshly produced section JSON; repairs nothing | `surface-producer`, after produce and **before** consolidation |
| `page-consolidator` | challenge and consolidation | One coherent page from challenged sections: cross-surface reconciliation, thread alignment, orphan evidence, the storyline challenge | `surface-producer`; refuses unchallenged input |
| `package-vetter` | QA and audit | ACCEPT / ACCEPT WITH FINDINGS / REFUSE on an assessment package before anything is parsed; also checks each new Surface Specification version against `surface-map.md` | An operator or the intake scheduler when a client folder arrives |
| `adversarial-verifier` | QA and audit | Attacks a payload, run or verdict that has already passed — grain, identity, arithmetic, absence, narrative | `surface-producer` or an operator, before a passing run is believed |
| `deployed-app-auditor` | QA and audit | Audits the live production `web` and `api` services over HTTP against the build invariants — redaction, bands, ETag, counts | An operator or scheduler after a deploy or a promotion |
| `qa-overseer` | learning loop | The findings memory: `record_finding`, `report_recurrence`, `resolve_finding`, `record_refinement`; reconciles open findings; hands the rectifier a worklist | `surface-producer` at the end of **every** production or repair, green or not |
| `rectifier` | learning loop | Durable changes to skills, agents, rulebooks and gates; edits the toolchain, never client content | `qa-overseer` with a worklist, the weekly cycle, or anyone about to edit a skill or agent file |
| `learning-grader` | learning loop | Scores a proposed refinement against the seven-dimension learning rubric; admission threshold 0.75 | `rectifier`, before it commits |
| `learning-testgen` | learning loop | 5–15 adversarial and regression cases per refinement, every one able to fail | `rectifier`, before it lands a fix |

---

## Orchestrator — one agent

`surface-producer` is the conductor and the single write point. Invariant 2 of
the build charter says content enters the application only through the
connector; this tier is the plugin-level expression of it. Every other agent in
this directory carries a `disallowedTools` deny list that closes
`submit_page_payload` and `promote_run`, so the invariant holds by construction
rather than by anyone remembering it.

It runs the pipeline in `05-lifecycle/routing.md` end to end:

```
route → produce → challenge → consolidate → submit → learn
```

and it sizes the route down. One flagged surface is one producer, one challenge,
one consolidation, one resubmit — never a re-production of six pages. Promotion
stays atomic across all six pages regardless of how small the repair was.

## Per-surface producers — thirty agents

This tier writes the JSON a client eventually reads. It splits two ways, and the
split is why the directory is large.

**Six page routers** — `overview-`, `insights-`, `heatmap-`, `platform-`,
`context-` and `techstack-surface-producer` — take a run id and a list of
surface names and produce a whole page's worth. They are what the routing table
in `05-lifecycle/routing.md` still routes to by need, and they remain the right
call when a fresh run needs a page authored from nothing.

**Twenty-four single-surface producers** own one to three sections each and
exist so that a one-card repair costs one agent invocation. They are not named
in the routing table yet; route to them from this index, from the surface map's
producer column, or straight from a verdict — the gate names the JSON path, the
path names the section, and the section appears in the table above.

All thirty run on the fast model tier (`sonnet`). None may submit, promote,
register evidence, claim or withdraw a run, or write files.

**Order within a page.** The dependencies are real, not stylistic; each one
exists because two surfaces render the same figure and a client can see both at
once.

- **Overview**: everything else first, `overview-narrative-producer` last — the
  executive summary and every section's `narrative_thread` are written from
  what the surfaces actually say, never the other way round.
- **Heatmap**: `heatmap-grid-producer` first. H4 is the run's ground truth, and
  every score quoted in a drawer, a focus area or a platform gate must agree
  with it within the 0.05 grain tolerance.
- **Platform**: `platform-fit-producer` first — the roadmap, the ladder and the
  starters all reconcile against P1 and P2 and none of them may exceed those
  claims.
- **Techstack**: `techstack-register-producer` before
  `techstack-layers-producer`, because the layer counts are recomputed from the
  rows and are stale the moment a row moves.
- **Cross-page**: `overview-market-producer` before `context-sentiment-producer`
  (C4 re-projects O9's bars and reconciles by `e_id`), and before anything reads
  C6 (C6 *is* `overview.financial_series` — there is no second row for it to
  land in). `techstack-register-producer` before `insights-landscape-producer`,
  because T2's four counts are recounted from T1 and never stored.

## Challenge and consolidation — two agents

Producers write; this tier decides whether what they wrote survives contact with
its own evidence. `finding-challenger` runs first and per claim: steelman, then
falsify, then a verdict — a claim it could not attempt to break is UNTESTED and
says so. `page-consolidator` runs second and per page: it resolves or overrules
every `BREAKS` verdict, reconciles every figure that appears twice, aligns the
narrative to the findings and lists orphan evidence.

The order is not negotiable and the consolidator enforces it — input arriving
without a challenge report is refused, because the consolidator's whole method
assumes per-claim verdicts already exist. Both reason on the strong tier
(`opus`), because checking is where depth pays.

## QA and audit — three agents

This tier surrounds the pipeline rather than sitting inside it, and each agent
watches a different moment.

`package-vetter` guards the way in, before a single figure is parsed, because
the parser is deterministic and silent: handed a workbook whose headers it does
not recognise it does not fail, it produces the wrong thing, and the wrong thing
promotes.

`adversarial-verifier` guards the moment a result is about to be believed. It is
invoked *after* something passes, on the premise that structure, identity and
arithmetic can all be correct about a claim that is false.

`deployed-app-auditor` guards the only claim the other two cannot make: what
production actually serves. Every other check inspects something on the way in,
and all of them can pass while the rendered page is wrong, because a redaction
walker, a generated column, a materialised view, a cache key, a compression
middleware and a frontend resolver sit between a valid payload and a client's
screen. A claim it has not fetched is a claim it has not audited.

All three are read-only against client content and run on `opus`.

## Learning loop — four agents

Everyone else's report dies with their session unless this tier writes it down.

`qa-overseer` runs at the end of every production or repair, green or not,
because a green run with a buried defect still has a finding in it. It is the
only agent that writes the findings memory. When a defect class recurs past its
threshold it hands `rectifier` a worklist — with the finding ids *and* the
rulebook file that should have prevented them, because a recurrence that got
past a rulebook is a defect in the rulebook too.

`rectifier` then changes the tools rather than the output, and it does not get
to mark its own work. `learning-grader` scores the proposed change against the
seven-dimension rubric and admits nothing below 0.75; `learning-testgen`
produces the cases that make the change's coverage claim checkable, every one of
which must be able to fail. Both are independent of the fixer **by
construction** — neither carries `Write`, `Edit` or any connector write tool, so
a grader cannot edit what it is scoring and cannot launder a verdict into a
finding. That independence lives in their front matter, not in a policy
paragraph.

---

## Scoring tier — five agents

Added 2026-09-03 after the owner reported reports being written before any
score existed. They own column D of the research workbook under
`engine.assessment`, which refuses every score that is not earned: the stage
opens only on a run whose categories all pass the floors gate with synthesis
required, a row is scored only after an independent challenge, a score never
exceeds its evidence ceiling (T1/T2 5.0 · T3 4.0 · T4 2.5 · T5 2.0 · no
evidence 2.0 · single source 3.0), and the rationale cites the row's own
E-ids. The four producers run in parallel; the critic may not have scored the
pillar it judges. The SCORING gate must be PASS before the assessment report
producer may write.

| Agent | Tier | Owns | Invoked by |
|---|---|---|---|
| `scoring-p1-producer` … `scoring-p4-producer` | scoring | one pillar's `engine.assessment score` rows, with the AI/data overlay | `research-conductor`, after every category gate is PASS |
| `scoring-critic` | scoring | the SCORING_CRITIC verdict per pillar | `research-conductor`, as each pillar lands |

---

## How a dispatch carries its context

Added 2026-09-03, after the owner reported that nothing orchestrated the
subagents. No agent in this plugin is dispatched with a prompt somebody
typed any more: `engine.brief batch` writes one bounded packet per lane and
the batch array that dispatches them, `engine.brief dispatch --category C`
is a producer's first command, and `engine.brief handback --category C` is
what it reports — computed from the sheets, so the conductor never has to
trust a lane's prose, and carrying `leads_for_other_categories` so one
lane's source reaches the lane whose cells need it. Packets are measured
against `BRIEF_CHAR_CEILING`: unbounded context sharing is the token bleed
under another name.

## The taxonomy on disk

```
agents/
  orchestration/            surface-producer · package-vetter · page-consolidator
  production/
    overview/               overview-surface-producer (router) + hero · narrative ·
                            opportunity · people · whynow · market · findings · governance
    heatmap/                heatmap-surface-producer (router) + grid · focus ·
                            evidence · valuechain · signals · freshness
    platform/               platform-surface-producer (router) + fit · conversation · roadmap
    context/                context-surface-producer (router) + risk · sentiment · timeline
    insights/               insights-surface-producer (router) + cards · landscape
    techstack/              techstack-surface-producer (router) + register · layers
  scoring/                  scoring-p1-producer … scoring-p4-producer · scoring-critic
  enrichment/               enrichment-planner · enrichment-web-specialist ·
                            enrichment-connector-specialist · enrichment-ledger-auditor
  checkers/                 finding-challenger · evidence-integrity-checker ·
                            numeric-reconciliation-checker · exclusion-boundary-auditor
  qa/                       adversarial-verifier · deployed-app-auditor · qa-overseer
  learning/                 rectifier · learning-grader · learning-testgen
```

The loading contract, stated because an earlier revision of this file asserted
the opposite: the plugin loader DOES discover agent files in subdirectories
(measured 2026-08-20 — a probe plugin with `agents/groupa/nested-agent.md`
registered both its flat and its nested agent in a live session; the plugin
reference is silent on recursion). Because silence is not a guarantee,
`plugin.json` also declares **every agent file individually** in its `agents`
array — the manifest schema accepts file paths only — so a loader that does
not recurse still sees the full roster. `scripts/package_plugin.py` fails the
build when the manifest and the tree disagree in either direction, which makes
"added a file, forgot the manifest" unshippable rather than silent. Agent
NAMES stay unique across all folders: routing and `skills:`/agent references
resolve by front-matter name, never by path.

Three other files carry per-agent facts and each of them can drift from the
directory:

- `05-lifecycle/surface-map.md` — the producer column for all 53 surfaces and
  panels. A surface with neither a producer nor a `server-computed` marker is a
  defect by the map's own no-orphan rule.
- `05-lifecycle/routing.md` — the by-need routing table, which currently names
  the six page routers and not the twenty-four single-surface producers.
- `plugins/dma-insights/README.md` — **stale**: it still describes fourteen
  agents, four per-page producers and a twelve-agent table. Treat this index as
  authoritative and correct the README when you next touch it.

---

## Adding a new agent

**One file, in its taxonomy folder, kebab-case.** Create
`plugins/dma-insights/agents/<family>/<name>.md` under the folder the tree
above assigns (a new family means a new folder AND a new tree entry here).
The `name` in front matter must equal the filename without `.md` and stay
unique across ALL folders; a mismatch is how an agent becomes unroutable
while looking present on disk. Then declare the file in `plugin.json`'s
`agents` array and bump `scripts/doctor.py` EXPECTED_AGENTS — the packager
and the doctor both fail loudly until you do, which is the point.

**Front matter may contain only these seven keys**, and nothing else:

| Key | What it must do |
|---|---|
| `name` | Equal the filename without `.md`, kebab-case |
| `description` | State **when to invoke it**, in one or two sentences — this string is the whole basis on which the router picks the agent, so it names the surfaces, the section paths and the verdict codes that should route here |
| `model` | `opus` for reasoning tiers, `sonnet` for producers, per the tier sections above |
| `effort` | Effort level for the tier |
| `maxTurns` | A real ceiling; producers sit between 60 and 200 |
| `skills` | Only these six exist: `dma-surface-production`, `dma-research`, `dma-assessment`, `dma-governance`, `dma-rectifier`, `dma-first-call-deck` |
| `disallowedTools` | The deny list below |

**The forbidden three: `mcpServers`, `hooks` and `permissionMode`.** These are
not permitted in plugin-provided agents at all. They were stripped from all
sixteen agents that existed on 2026-08-20 and must never be reintroduced —
an agent that declares one is a packaging defect, not a configuration choice.

**Every producing agent carries a deny list**, and it includes at minimum:

```
Write, Edit, NotebookEdit,
mcp__plugin_dma-insights_connector__submit_page_payload,
mcp__plugin_dma-insights_connector__promote_run,
mcp__plugin_dma-insights_connector__register_evidence,
mcp__plugin_dma-insights_connector__claim_run,
mcp__plugin_dma-insights_connector__withdraw_run
```

Producers additionally deny `open_payload` and `append_payload_part`; the
learning-loop graders additionally deny `record_finding`, `resolve_finding` and
`record_refinement`. `surface-producer` is the sole agent with no deny list,
because it is the sole agent permitted to submit and promote. `package-vetter`
and `rectifier` keep `Write`/`Edit` because their output is files, not payload —
they still deny every connector write tool.

**Never invent a connector tool name.** There are exactly 33, listed in
`plugins/dma-insights/skills/dma-surface-production/02-inputs/3-mcp-tools.md`. A
deny list naming a tool that does not exist denies nothing.

**Then update the doctor count, or the install reports broken.**
`plugins/dma-insights/scripts/doctor.py` checks component inventory by
**equality, not a floor** — a floor of `agents >= 5` once reported a clean
install while seven agent files were missing. Line 60:

```python
EXPECTED_AGENTS = 16   # 14 + insights-surface-producer + techstack-surface-producer, split out of context (2026-08-19)
```

This constant is **currently wrong**: the directory holds **40** agent files, so
`/dma-insights:doctor` fails its agents-inventory row today and will keep failing
until the constant and the comment are brought up to date. Whoever next adds or
removes an agent owns that correction along with their own increment.

**Finally, close the loop.** Add the agent's row to the table in this file; add
or reassign its rows in `05-lifecycle/surface-map.md` if it produces a surface;
and add it to `05-lifecycle/routing.md` if it should be reachable by need rather
than only by surface id. An agent that exists in exactly one of those four places
is an agent nobody will route to.
