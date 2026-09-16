---
name: dma-surface-production
description: Synthesise the DMA Insights payload for a client assessment and promote it through the DMA Insights MCP connector. Use this skill whenever the user mentions DMA synthesis, surface production, producing or refreshing a client's DMA Insights pages, promoting a run, submitting a page payload, fixing a failed verdict, re-running a client, asks for leadership contacts, thought-leadership signals, Clay enrichment or a technographic scan for a client, asks how a platform recommendation is justified or cross-checked, or names any surface or section id (O1, H4, P2b, C3, T1, overview.scores, heatmap.cell_evidence, and so on). Also use it whenever an assessment package folder is handed over and asked to be "turned into the app", "loaded", "published" or "made live", and whenever a submission has failed validation and needs repairing. If the task involves reading a completed Digital Maturity Assessment and turning it into rendered surfaces, this is the skill — do not improvise the payload shape from memory.
---

# DMA surface production

Turn one completed Digital Maturity Assessment into the payload the DMA Insights web
application serves, and promote it.

You are the only component in this system that reasons. The application performs no
inference at request time — everything a client sees was written here, validated at submit,
and persisted by promotion. That is why a mistake made here is not a runtime surprise but a
build-time failure a verdict can name, and why the discipline below is worth the effort.

## What you produce

**34 sections across 6 pages**, which render as **38 client surfaces** on 7 dashboards plus
15 drilldowns. Promotion requires a passing submission on **every one of the six pages** —
there is no partial promote and no half-built page a client could see.

| Page | Sections | Surfaces | Note |
|---|---|---|---|
| `heatmap` | 9 | 5 on D3, 4 on D7 | Produce first — everything else cites its linkage |
| `overview` | 12 | 13 on D1 | The page an AE is guaranteed to read |
| `insights` | 2 | 2 on D2 | Cards are claims, not topics |
| `platform` | 5 | 5 on D4 | One shared recommendation id space |
| `context` | 5 | 6 on D5 | Internal-only dashboard |
| `techstack` | 1 | 2 on D6 | Layered register plus a detail sub-page |

## Before you write anything

Read these, in this order. They apply to every section and are not repeated in the
page packs.

1. `01-start-here/1-standing-clauses.md` — identity, grain, register, audience, citation. Five rules that
   caused most of the measured defects in this product when they were left implicit.
2. `01-start-here/2-evidence.md` — tiers, recency, the rank score, the peer fallback ladder, and
   what to do when you cannot establish an id.
3. `01-start-here/3-language.md` — every gap is stated as available value. A client reads this.
4. `01-start-here/4-absence-protocol.md` — never say no until a documented ladder has failed.
5. `01-start-here/6-entity-shape.md` — sub-vertical, size tier, ownership and brand shape.
6. `01-start-here/7-memory-first.md` — what this build already knows about the defect you are
   about to make. `get_memory_digest` and `list_open_rejections` before you author; the recall
   the connector returns beside a refusal before you repair one.
   Which cells this run may serve, whether the peer cohort is a cohort, and which enrichment
   ladders can return anything at all for this entity.
6. `04-craft/4-card-anatomy.md` — the header, sub-header and budget each surface renders into.
7. `04-craft/1-reasoning.md` — the R-Layer. The only mechanism that catches a claim that is
   well-formed, correctly cited, grain-locked and wrong.
8. `04-craft/6-fields-the-app-depends-on.md` — every field whose absence degrades a real
   surface, with the observed consequence. Read it once; it is the difference between a
   payload that validates and a page that reads.

## The workflow

### 0 · Vet the workbooks

You are the first reader of the package and the only one who can refuse it. The parser is
deterministic: handed a workbook whose headers it does not recognise it does not fail, it
silently produces the wrong thing, and the wrong thing promotes. Peer columns that are really
statistics have invented peer institutions named "Median"; a `Priority` column read as an id
pattern dropped all eight recommendations; an unpinned catalogue version left 765 heatmap
cells nameless.

```bash
python scripts/vet_workbooks.py <package-dir>    # the mechanical checks
```

Then read both workbooks yourself for the judgement calls. Refuse a dirty workbook and say
exactly what is dirty — a refusal is a finding, not a failure. Full checklist, and the
matching/escalation/enrichment steps that follow it: `02-inputs/4-vetting.md`.

**Scores come from the scoring workbook. Evidence ids, excerpts, ERS and published dates come
from the research workbook. A score is never taken from the research workbook.**

Establish the entity's shape in the same pass and write it down: **sub-vertical, size tier,
ownership and brand set**. The workbook scores the whole catalogue, so it holds other
sub-verticals' variant cells — 59 of them reached a credit union's rendered heatmap — and the
peer cohort it names may sit in a different size class from the entity. Both are decided
here or discovered on a promoted page. `01-start-here/6-entity-shape.md`.

### 1 · Orient

```
get_run_progress(run_id)     → where am I; which pages pass, fail, or are missing
get_client_state(display_id) → what is currently served, and prior runs
```

Never assume a run is fresh. A previous session may have staged work that survived, and a
rerun must be produced knowing what the last run said — the longitudinal surfaces read
across runs and a rerun produced as though it were a first run silently empties them.

If `get_run_progress` shows pages already passing, **do not re-synthesise them**. Repair
what failed, produce what is missing, and promote.

### 2 · Claim

```
claim the run (exclusive lease, expires)
```

One session per run. If the claim is refused, another session holds it — check
`get_run_progress` rather than working in parallel. If your lease expires mid-session,
staged work survives; re-claim and continue.

### 3 · Read the contract, then the package

```
get_page_contract(page)          → field tuples AND the per-field doc text
get_report_bundle(run_id)        → the parsed assessment
get_capability_catalogue(run_id) → canonical cell ids and names, plus the alias bridge
```

Read the contract rather than recalling it. A remembered shape that still type-checks is
how silently wrong content gets promoted. The `doc` text on each field is part of the
contract, not documentation — for a list-of-object field it is the only place the item keys
are stated.

Cell **names** come from the catalogue, never from report prose. Copying a name out of prose
is how raw taxonomy codes end up rendering as labels.

For what the package folder contains and which artefact is authoritative for what, read
`02-inputs/1-package.md`.

### 4 · Run Clay enrichment — now, not later

Enrichment is async and the pages that consume it come last. Start it immediately after
reading the bundle so results are waiting when you reach them.

```
find-and-enrich-company(domain from 01_evidence/entity_profile/)   → taskId
add-company-data-points(taskId, [Tech Stack, Annual Revenue, Headcount Growth,
                                 Recent News, Open Jobs, Latest Funding])
find-and-enrich-contacts-at-company(domain, contactFilters={C-suite titles})  → taskId2
add-contact-data-points(taskId2, [Find Thought Leadership, Summarize Work History])
get-task-context(taskId) ; get-task-context(taskId2)     ← POLL. Do not conclude.
```

`scripts/clay_plan.py --domain <domain>` prints the exact sequence with title filters and
the tier each returned data point registers at.

Clay closes the gaps public search cannot: **O7 leadership**, **O12 thought leadership**,
**T1 tech stack** — its technographic scan is the machine scan, and machine scans are T1,
never T4 — plus firmographics, why-now signals and the hiring evidence behind platform
readiness.

Three rules that matter more than the call sequence:

- **Cite the source, not the tool.** "Clay reports 340 employees" is not evidence; the filing
  Clay surfaced is. A value with no traceable source is an inference and is labelled one.
- **Never record an absence from a Clay call without polling first.** The search response
  carries base fields only. An empty leadership panel written before `get-task-context`
  resolved is an unfinished call rendered as a finding — Clay's own contract says the same.
- **The budget is one company call, one contact search, one contact enrichment, and at most
  two targeted custom points.** Enrichments cost credits and a DMA needs the leadership tier,
  not the org chart. Outside that, ask.

Full playbook and tier map: `02-inputs/2-clay-enrichment.md`.

### 5 · Produce, page by page

Work in this order and read the page pack before starting each one:

```
03-pages/1-heatmap.md    ← first: the linkage everything else cites
03-pages/2-overview.md   ← needs the coverage figures from heatmap work
03-pages/3-insights.md
03-pages/4-platform.md
03-pages/5-context.md
03-pages/6-techstack.md
```

Each pack carries, per surface: the contract, what must be presented, the
information-sources table naming the source of truth per field, and the synthesis prompt.
Every page is produced against its rulebook at `03-pages/rulebooks/<page>.md` — the Baxter
positive pattern, the learned anti-patterns and the page's exclusion set — applied by
default, not recalled from memory.

**Enrichment.** When a cell is thin or a field is empty, search. This is the
highest-value work on any surface: a cell with two evidence items and a successful search
becomes a cited cell; the same cell without one becomes a thin-evidence alert. Register
every source you find **before** citing it:

```
register_evidence(run_id, item) → {e_id, deduped, ers}
```

The server allocates the id and computes the rank score. Use the id you were given. An
invented evidence id is fabrication by construction even when a matching source genuinely
exists. Registration is idempotent by content, so registering the same annual report from
six surfaces returns the same id six times — that is expected, not a problem.

**Before you write an empty state, run the ladder.** An absence is a finding only if you can
show the search that established it. Every rung attempted is recorded and ships with the
payload — see `01-start-here/4-absence-protocol.md`. Most ladders hit; the ones that do not produce
a finding you can defend. Note the third result type: some absences are *correct posture*, not
gaps, and should be stated as such.

**Every served cell gets a synthesis.** The drawer is the whole reason the grid is
clickable, and it was empty on 90% of a real run's cells. Coverage is the default, not an
achievement: a cell with its own evidence gets a cited synthesis, a cell whose parent
capability carries evidence gets an inherited one labelled as the inference it is, and a
cell with nothing gets the ladder that established that. Work outward from the cells other
surfaces cite — those must be cited grade, because a reader was sent there. Method and
`linking_stats` shape: `03-pages/1-heatmap.md`.

**Write the run thesis after the heatmap, and each page's thread before you submit it.** One
constraint, stated once, instantiated at five anchors — the hero framing, the top finding,
the act-now set, roadmap phase 1 and the timeline storyline. Six coherent pages describing
three different assessments is the failure no per-page gate can see. Each page then carries a
`narrative_thread` of 45–75 words tracing the line through its surfaces in render order,
written last, from what you actually produced. If you cannot write it, the surfaces are not
yet a page. `04-craft/3-page-narrative.md`.

**Four things the connector now refuses at registration, so know them before
you search rather than after** (W6, from one promoted run):

| What | Rule |
|---|---|
| Vendor collateral | A customer story, case study, press release, product page or vendor blog is **T5, ceiling L2, corroboration required** — whatever tier you type. One run registered a `fortinet.com/customers/<client>` page as T1 at ERS 4.20 and let it carry five cells of its only Differentiating category. |
| An absence | "The search returned no disciplinary actions" is the absence of a finding, not the presence of a control. It registers as an absence (INFERENCE, with the ladder), never as a FACT about a capability. Rephrasing it positively — "records a clean supervisory history" — is the same span and is refused the same way. |
| A related entity | A filing about a parent, subsidiary or affiliate may evidence **ownership, structure, group policy, regulatory registration, corporate history** — never the assessed entity's operational capability. Thirty top-band cells in one run rested on a subsidiary's officer list, telling a CIRO-regulated dealer its surveillance was Differentiating. The connector notes the relation on the row; reading the note is your job. |
| One document | A document may be the **only** citable source for at most 20% of a run's scored cells. Breadth is fine — the reference client's call report bears on 53.7% of its cells legitimately. What is refused is one source being the whole basis for a fifth of an assessment. The cap is per DOCUMENT: splitting a filing into eight ids does not divide its voice. |

Each of these refuses the LINKS, never the registration — a verified span is
never lost to them. What you lose is the cells the source cannot carry, which
is the finding.

**Verify before citing** when you are unsure:

```
get_evidence(run_id, e_ids) → {found, not_found, foreign}
```

`foreign` means a real row belonging to **another institution**. That is contamination:
stop, quarantine, escalate. Do not filter it out quietly and carry on — its presence means
your reasoning has drifted onto the wrong entity.

### 6 · Run the reasoning layer

Every gate checks a claim **after** you write it. The R-Layer is what you do before, and it is
the only thing that catches a claim that is well-formed, cited, grain-locked and wrong.

```
A  HYPOTHESIS        State the claim and its confidence, before defending it.
B  COUNTER-EVIDENCE  Argue the strongest case against it. Inside a thin margin,
                     present both and say the call is close.
C  DOMAIN TEST       Plausible for THIS sub-vertical, size tier and regulator?
D  FAILURE PROBES    Run the probe set for the surface. Each probe fires a search.
E  VERDICT           ACCEPT · REJECT · UNCERTAIN. Reject means re-rank or drop,
                     not soften.
```

Record it: any surface making a ranked or causal claim carries
`r_layer: {hypothesis, counter, domain_test, probes_run[], verdict, confidence}`. A verdict you
did not write down is a step you can convince yourself you took.

**Step B is the one that gets skipped.** Arguing against your own conclusion feels like
undermining the work; it is the opposite. Source the falsifier from the client's own words
where you can — that is what makes it survive the room.

**Cross-check every fact that appears twice.** Agreement from independent origins is
corroboration and raises the rank score. Agreement from one origin is one source. Disagreement
where one source outranks resolves by priority and is recorded. Disagreement between peers is a
contradiction: quarantine and state it. **Never average two disagreeing figures** — the result
is in no source, which is fabrication with extra steps.

Probe sets per surface, the nine contradiction classes and the cross-check procedure:
`04-craft/1-reasoning.md`. For the platform story — the highest-defect surface in the corpus —
`04-craft/2-platform-story.md`.

**Then check the whole run, not just the page.** Each page passes its submission independently,
so a contradiction *between* pages survives every per-page gate:

```bash
python scripts/check_consistency.py <rundir>/ --subvertical <CODE>   # all six together
```

It reconciles the composite against the pillar means, the hero against the grid, gap rows
against served scores, roadmap ids against the recommendation set, landscape counts against the
register, O8 against C6, confidence against evidence count, and the framing sentence against
the top finding. It also refuses a cited cell belonging to another sub-vertical, a served cell
whose drawer says nothing, a coverage denominator that is not the served cell set, and a run
whose five narrative anchors are about different constraints.

### 7 · Submit and repair

```
submit_page_payload(run_id, page, payload, provenance, producer_version)
  → {submission_id, verdict}
```

A verdict names the gate, the JSON path and the arithmetic. Read it literally.

**Repair the cause, not the symptom.** A grain violation means the label and the figure came
from different rows — fix the pairing, not the sentence. A verdict saying a quoted 2.34
resolves to 2.10 is not asking you to write 2.10; it is telling you that you read the score
from one row and the name from another.

Run `scripts/check_language.py` before every submit. Everything on a client dashboard is read
by, or in front of, the client, and a gap stated as a deficiency invites defensiveness where
the same gap stated as available value invites a conversation. The finding does not change —
only whether the sentence is about what the institution failed to do or what is now available
to it.

**No prose field opens on an absence.** "No integration platform appears in a scan of more
than two hundred technologies" shipped to a client as the first line of a recommendation
card, which line-clamps to three lines, so it was most of what was read. Its own second
sentence already named the asset. Name it first: `01-start-here/3-language.md`.

Resubmission supersedes cleanly. Submit, read, repair, resubmit as often as needed — there
is no merge, no accumulation and no cleanup. For the gate families and how to read a
verdict, see `05-lifecycle/1-gates.md`.

### 8 · Challenge the storyline — five volleys

The six pages pass and reconcile. That makes the run correct; it does not yet make it
usable. An AE carries one story into a room and is pushed back on, and a storyline can be
true, cited, grain-locked and still worthless — because the client already says it, or
cannot act on it, or the incumbent vendor answers it in one sentence. No gate catches that:
nothing about it is malformed.

So before promoting, put the whole storyline through five adversarial volleys — the
client's own executive, the finance officer, the incumbent vendor, the rival on the
shortlist, and the AE who has to say it out loud. Each volley is a challenge and the
story's answer, recorded with what changed.

```
storyline_challenge: { volleys: [{volley, challenger, challenge, answer, outcome, changed}],
                       survived }
```

Five `held` outcomes is a finding, not a triumph — it usually means the objections were
written gently. A volley the story fails may still reach the AE, annotated; a story that
quietly drops its weakest limb and presents the rest as whole is the thing this step
exists to prevent.

The full method, the form each objection takes and what passing each volley requires:
`04-craft/7-storyline-challenge.md`. If a volley changes the storyline, resubmit the
affected pages and re-run `check_consistency.py` before moving on — staged rows are
retained, so that is cheap.

### 8b · Answer the questions the panel will be asked

Fifteen questions, listed in `04-craft/8-answered-questions.md`, grouped by the panel
surface they belong to and repeated per cell, focus area or platform where the question
is scoped. 40–110 words each, spoken register, cited from registered evidence.

The application answers these without you by quoting the promoted field that bears on
each one — so a run that skips this step still has a working panel. What it does not
have is the sentence that says what the run MEANS for the conversation, because writing
that sentence at request time is what the whole architecture forbids. This is the only
moment it can be written.

An answer the run cannot ground is written as an absence with its reason, never composed
around the gap: the question then renders with the reason under it, rather than
disappearing from the list and leaving the reader unaware it was ever asked.

### 9 · Promote

```
promote_run(run_id) → all six pages, one transaction, all or nothing
```

If it returns `incomplete_run`, it names the missing and unpassed pages. Re-promotion is
idempotent, so a retry is safe.

## The rules that are not negotiable

These are the ones that produced measured defects when they were left to judgement.

1. **Never assign a score.** Scores come from the workbook. You read them; you never derive,
   adjust or re-rank them.
2. **Never invent an identifier.** You create exactly five classes — `ic_id`, `f_id`,
   `fa_id`, `ts_id`, `wn_id` — plus agent-authored `rec_id`. Everything else is read from
   the catalogue or requested from the server.
3. **Register before you cite.** Always. And **cite at the item, not the section** — every
   card, signal, finding, ceiling row and register row carries its own evidence id, an
   inference included. The section envelope's `e_ids` is a union, not a substitute; gate
   **AG-03** blocks an item that asserts something and cites nothing. Naming a source in
   prose is not citing it — register it and use the id you are given. See standing clause 5.
   **Register from the artefact you fetched, in the same step you fetched it**: the excerpt
   and the `source_url` are one claim, and a true claim under a URL that does not contain it
   is fabrication by construction. `scripts/check_evidence.py`.
4. **A quoted figure and its named cell are the same cell**, within 0.05, read from one row.
5. **Every figure passes the identity gate** — legal name, regulator, footprint, source
   domain, order of magnitude. On failure quarantine the field with its reason; never
   substitute a plausible value.
6. **A derived value is computed or null.** Never a sentinel, never NaN. Status follows
   band, band follows age, age follows a real date — or all three are null.
7. **Mark internal rungs in the payload.** `internal_only` carries the JSON paths the serve
   layer strips. A field you do not mark reaches the client.
8. **Absent beats wrong.** An honest empty state naming what you searched is a finding. A
   guessed field survives into a meeting and costs credibility.
9. **Counts are computed, not asserted.** Where a surface declares its grounding, the number
   is the length of the citation array.
10. **Order is meaning.** Findings are ranked, phases sequenced, events chronological. The
    app renders in the order you send.
11. **Run the ladder before you say no.** An absence with no recorded search is not a finding.
12. **Frame every gap as available value.** Name what exists before naming what does not —
    including in sentence order: **no prose field opens on an absence.** Never assign fault,
    never describe a person or a team.
13. **A page tells one story.** Write its thread before you submit it.
14. **Argue against your own conclusion before you ship it.** A claim that survives its
    strongest counter-argument is one you can defend in the room.
15. **Never average two disagreeing figures.** The result is in no source. Quarantine and state
    the contradiction — the resolution is the finding.
16. **Serve the entity's cell set, and count over the same one.** The workbook scores the
    whole catalogue; another sub-vertical's variant cells resolve in it and render nowhere.
    Never cite one, and compute every coverage figure over the cells the run actually serves.
17. **Every served cell opens a drawer that says something.** Cited, inherited or declared —
    a scored cell with no synthesis asserts a number and answers nothing about it.

## Colour: you never send one

Score → band → hex resolves in one module in the app. No payload field carries a hex value, a
CSS class or an outline instruction. You send the raw score, the band **word** where a surface
renders one, and semantic flags — `is_thin_evidence`, `below_threshold`, `is_primary_gap`.

But your prose has to agree with what renders, so know the boundaries. They are strict
less-than on the **raw** score, before display rounding:

```
< 2.0  Activating      2.0-2.99  Building
< 4.0  Competing       >= 4.0    Differentiating
null   no score
```

Three things worth knowing before you write a band word:

- **"Transformational" does not render.** The resolver has four branches; anything at or above
  4.0 returns Differentiating. Do not write M5 into prose.
- **A score of 2.97 displays as 3.0 and bands as Building.** Resolve the band from the raw
  value, not the rounded one.
- **"Stale" means two different things** — over 12 months in the freshness dot, 36 to 48 months
  on the evidence ladder. The evidence ladder governs anything you emit. Say the age; let the
  band speak.

Thin evidence adds a dashed outline and does not change the fill, because the fill means
maturity and nothing else. Full detail, including two hex values that disagree between sources:
`01-start-here/5-colour-and-bands.md`.

## Representing absence

An empty surface is a value, not an omission. A missing required field fails the contract;
an explicit empty state passes and renders correctly.

| Situation | Emit |
|---|---|
| No leadership found after a full search | empty roster, `verified_absent`, `sources_searched` |
| Fewer than three dated financial points | the points, `verified_sparse`, no trend |
| No stair-step derivable | null ladder, `empty_state` with the reason |
| A figure failed the identity gate | null value, `quarantined`, `quarantine_reason` |
| A cell's evidence is genuinely thin | `thin`, `sources_searched`, `closure_condition` |
| No peer figure available | `peer_basis=cannot_estimate`, median stays null |

## When you are asked to fix one card

You do not need a new assessment run. Promoted staging rows are retained, so:

1. Re-claim the run.
2. Resubmit only the affected page — it supersedes that page's staged row.
3. Call `promote_run` again. Five pages come from the retained rows, one from your new
   submission, and every section rewrites in one transaction.

Read `05-lifecycle/2-versioning.md` before doing this, and before any work on a rerun or a run
whose catalogue version differs from its predecessor.

## Where everything lives

```
01-start-here/   read before writing a single field
02-inputs/       where the material comes from
03-pages/        the surface contracts, in production order
04-craft/        how to make it good rather than merely valid
05-lifecycle/    gates, versioning, reruns
scripts/         run these rather than eyeballing
assets/          payload skeletons per section
```

## Reference files

| File | Read it when |
|---|---|
| `01-start-here/1-standing-clauses.md` | Always, before writing any section |
| `01-start-here/6-entity-shape.md` | Before planning the run — sub-vertical scoping, size tier, ownership, brands |
| `04-craft/6-fields-the-app-depends-on.md` | Once, early — what breaks on the page when a field is missing |
| `02-inputs/4-vetting.md` | Before parsing anything; when a workbook looks unusual |
| `01-start-here/2-evidence.md` | Always — tiers, recency, rank score, peer ladder, citation, and why the excerpt and the `source_url` are one claim |
| `02-inputs/1-package.md` | Orienting in the assessment folder; deciding which artefact wins |
| `02-inputs/3-mcp-tools.md` | Any tool call whose exchange you are unsure of |
| `05-lifecycle/1-gates.md` | Reading a verdict; understanding what will be asserted |
| `05-lifecycle/2-versioning.md` | Reruns, catalogue bumps, fixing one page |
| `04-craft/5-prompt-standard.md` | Producing a surface that has no prompt, or improving one |
| `02-inputs/2-clay-enrichment.md` | Running enrichment; deciding what tier a Clay output is |
| `01-start-here/4-absence-protocol.md` | Before writing any empty state |
| `01-start-here/3-language.md` | Writing anything a client will read |
| `04-craft/3-page-narrative.md` | Before submitting a page |
| `04-craft/4-card-anatomy.md` | Writing to a budget; knowing which header a field lands in |
| `04-craft/1-reasoning.md` | Any ranked, causal or comparative claim |
| `04-craft/2-platform-story.md` | Before producing D4 — the highest-defect surface |
| `04-craft/7-storyline-challenge.md` | After the six pages pass, before you promote — five volleys against the run's whole story |
| `04-craft/8-answered-questions.md` | Before you promote — the fifteen questions the intelligence panel asks of the run |
| `01-start-here/5-colour-and-bands.md` | Writing a band word, or describing the heatmap |
| `03-pages/<n>-<page>.md` | Before producing that page |
| `03-pages/rulebooks/<page>.md` | With the page pack — the rulebook every page is produced against, applied by default |

## Where you record, and when your page can ship

Two vocabularies meet here. An assessment agent writes into workbook **tabs**;
the connector accepts page **sections**. Nothing joined them, so an agent
filling `Entity_Timeline` had no way to know it was the only input to the
context page's timeline, and no way to know that finishing it made a page
submittable. That is why ingestion was an afterthought: you cannot submit as
you go if you cannot tell what "done" means for one page.

`references/tab_recording_map.json` is that join, GENERATED from the worker's
own `_TAB_TARGET` and the live page contracts — never hand-written, because a
hand-written map is one refactor away from being confidently wrong.

| Workbook tab | Page section it feeds | Binding |
|---|---|---|
| `Issue_Register` | `platform.stairstep` | proposed |
| `Recommendations` | `platform.recommendations` | verified |
| `Solution_Catalogue` | `platform.platform_story` | proposed |
| `Platform_Peer_Adoption` | `techstack.techstack` | verified |
| `Tech_Peer_Deployments` | `techstack.techstack` | verified |
| `Tech_Register` | `techstack.techstack` | verified |
| `Technographic_Scan` | `techstack.techstack` | verified |

29 tabs are read in all: 13 feed a
page, and the remaining 10 are run config, provenance and gate
logs that feed no client surface — the parser marks those
`not_client_facing`, so their absence from the table is not a gap.

**Read the Binding column literally.** Only 5 of the 29 mappings are
marked `verified` — checked field by field against `get_page_contract`.
14 are `proposed`: read off the tab's shape and not
yet confirmed. A `proposed` binding is a good guess about where your work
lands, not a promise, and it is worth confirming against the contract
before you rely on it.

### Ship as you go

```bash
python scripts/ship_page.py <run_id> all --sections sections/ --incremental
```

Run it after every producer returns. It asks the contract which sections each
page REQUIRES, ships every page that has them, and names what the rest are
waiting on. A page already passing is simply resubmitted with the same
content, so re-running is free.

The connector RETAINS staged rows, so five pages can sit staged and passing
while the sixth is still being produced. **Promotion stays atomic across all
six** — staging is not serving, and no client sees a half-built run. What
moves earlier is validation, gate refusals and the byte cost of transport, to
where a producer can still act on them cheaply. When the last producer
returns, the sixth page ships and the run promotes: the client page is live as
the assessment ends, not as a separate exercise afterwards.

## Bind to the template, and to the copy the agent wrote last

`references/canonical_sources.json` names the scoring-workbook template, the
Golden 1 CU package as the measured reference, and the shapes known to be
wrong. It is checked in so the answer to "which template?" survives between
sessions and is reviewable in a diff rather than remembered.

```bash
python scripts/check_template.py <workbook.xlsx>    # BEFORE synthesis
python ../../scripts/inspect_client_folders.py --client "<name>"
```

`check_template.py` measures a workbook against the worker's own
`_TAB_TARGET` — 29 tabs, each bound to the surface it feeds — and prints
which are missing or empty **and what starves as a result**. It imports that
map rather than copying it: a second copy of the list here would be wrong the
first time the app changed.

A template is not correct because it is named "template". Measured 2026-09-03:

| Workbook | tabs | read-tabs with data |
|---|---|---|
| Golden 1 CU (the reference) | 43 | **28 of 29** |
| Bank of Travelers Rest — assessment | 20 | 11 of 29 |
| Bank of Travelers Rest — scoring (research v5) | 23 | 13 of 29 |

BOTR's two workbooks are COMPLEMENTARY — one holds `Firmographics`,
`Focus_Areas`, `Issue_Register`, `Subcap_Scores`; the other holds
`Entity_Timeline`, `Tech_Register`, `Report_Narrative`, `Provenance`.
Together ~26 of 29; separately 11 and 13. That is what binding to a split,
older template produces, and it is why eighteen of that entity's nineteen
runs landed with zero scored cells while the scores sat in a sibling file.

### One workbook and one report per client folder

`inspect_client_folders.py` reports VERSIONS, STALE PICK, DUPLICATES and
EMPTY PICK from the live tree. On BOTR it found four workbooks at three
depths in one folder, three byte-identical, with the scan reading neither the
newest nor the one with scores.

The scan now defends itself — copy directories (`memory-backup/`, `archive/`,
`old/` and siblings) are excluded, equal-ranked candidates break the tie on
**modified time** rather than filename, and a ranked workbook stating no
scored cell falls through to a sibling that has them. None of that makes the
copies harmless: a producer should still leave exactly one workbook and one
report in the client folder, and put working copies outside the intake tree.

## Shipping a page: write files, run one command

**Never retype a payload into `append_payload_part`.** Write each section to
`sections/<page>.<section>.json` and ship the directory:

```bash
python scripts/self_heal.py --sections sections/ --page overview \
       --entity "<the entity's legal name>"      # blocking vs advisory
python scripts/ship_page.py <run_id> overview --sections sections/ --dry-run
python scripts/ship_page.py <run_id> overview --sections sections/
python scripts/ship_page.py <run_id> all --sections sections/ --promote
```

`ship_page.py` assembles the sections, plans the parts, opens the upload,
sends every part **from disk** through `plugins/dma-insights/scripts/mcp_raw.py`,
submits with the `expect` counts, and prints the verdict's status and blocking
reasons — nothing else.

### Why this is not optional

Golden 1 CU (2026-09-02) shipped its six pages by printing the payload in
4000-character chunks and having subagents retype them into
`append_payload_part`, comparing byte receipts to catch drift. That cost about
**330,000 subagent tokens for one page, done twice**, and it was never
necessary: `mcp_raw.py` has spoken JSON-RPC to the connector from a file on
disk since 2026-08-20.

The cost is the smaller half. Retyping is the ONLY step in this pipeline that
can invent content, and on that run it did — an agent paraphrased
`P4C3.5.6.reach_note` from "Both spans establish" to "Two spans establishing".
A two-byte receipt delta was the only thing that caught it, and the substituted
phrasing genuinely exists on a sibling cell, so a reviewer would have read it
as ordinary variation. **A file on disk cannot paraphrase itself.** Every byte
receipt, chunk-boundary check and `emit_part --check` step this skill used to
require exists to detect a failure mode the file path removes.

Measured on the same six pages: the planner produces byte-identical parts
(overview: 39,639 / 39,624 / 34,197 / 14,622 / 23,431) in under a second.

### The order that saves the most

1. `self_heal.py` first — it restates the gates that cost a cycle, over the
   section files, for free. **A submission SUPERSEDES the staged row**, so a
   FAIL on a page that was passing costs that pass and blocks the promote for
   the other five.
2. `--dry-run` next, to see the part plan and the `expect` counts.
3. Submit. On a FAIL, fix the SECTION FILE and resubmit — never loop
   resubmitting until the wording happens to pass.
4. `--promote` only when all six report PASS; promotion is atomic across all
   six and refuses rather than half-succeeding.

### What self_heal.py blocks on, and what it only advises

**Blocking** — each restates a connector gate: `ET-09` (the entity's own name
with a leading article, matched CASE-INSENSITIVELY, which is how three manual
sweeps missed the same twelve strings), `CG-12` face budgets (path-keyed:
`basis` is a chip only under `prerequisites`), `CG-44` (a `peer_median` and a
`delta` with a null `score` — it names the recoverable figure), and unmarked
`r_layer` (redaction is default-deny).

**Advisory** — the sibling-null rule: a field populated on some rows of a list
and null on others. That is how a producer drops a field mid-list, and also how
the contract expresses a tri-state (`deployed` is null on purpose; a peer with
no public filing has no `source_url`). A heuristic never holds a gate it cannot
justify, so a human reads these.

## Scripts

Run these rather than eyeballing — they are faster and they do not get tired.

```bash
python scripts/ship_page.py <run> <page|all> --sections DIR [--promote]
                                                    # assemble, plan, submit from DISK.
                                                    # The only supported way to move a
                                                    # payload — see the section above for
                                                    # what retyping one cost and what it
                                                    # invented
python scripts/self_heal.py --sections DIR --page <page> --entity "<legal name>"
                                                    # the gates that cost a cycle on a real
                                                    # run, replayed locally for free:
                                                    # ET-09 (case-insensitive), CG-12 face
                                                    # budgets, CG-44 empty bars, unmarked
                                                    # r_layer. Blocking vs advisory
python scripts/preflight.py --run-id <uuid>        # where the run stands, what is blocking
python scripts/check_payload.py <payload.json> --page <page> \
       --subvertical <CODE> --cells <bundle.json>
                                                    # local checks before you submit:
                                                    # required fields, budgets, id patterns,
                                                    # internal_only marking, empty states.
                                                    # --subvertical turns ET-05 ON and
                                                    # --cells turns CG-14 ON; without them
                                                    # those two print "not run", which is
                                                    # not a pass
python scripts/check_repetition.py <drafts.json> --page <page> --at-scale 708
                                                    # BEFORE you write the 21st item of a
                                                    # large array, not before submit:
                                                    # CG-15's template rule compares items
                                                    # against each other, so no per-item
                                                    # check can see it, and the shape that
                                                    # refuses 708 cells is visible in 20
python scripts/score_prompt.py <prompt.txt>        # score a prompt you have written
                                                    # against the 14-attribute standard
python scripts/check_language.py <payload.json>    # accusatory framing, fields that OPEN on
                                                    # an absence, gap statements with no
                                                    # adjacent asset, lost capitals
python scripts/check_evidence.py <get_evidence.json> --review
                                                    # the evidence register, not a page:
                                                    # one excerpt under two hosts, a
                                                    # source_url that is not a document,
                                                    # a search page, a tool cited as a source
python scripts/clay_plan.py --domain <domain>      # the enrichment call sequence and the
                                                    # tier each data point registers at
python scripts/check_consistency.py <rundir>/ --subvertical <CODE>
                                                    # cross-page reconciliation before
                                                    # promotion — the check no per-page
                                                    # gate can make: foreign variant cells,
                                                    # silent drawers, coverage denominators
                                                    # and the run's one constraint
python scripts/precheck_gates.py <payload.json> --page <page> \
       --evidence <get_evidence.json> --bundle <get_report_bundle.json>
                                                    # the connector's own blocking gates,
                                                    # run locally: ET-01/ET-04 citations,
                                                    # CG-10 dating, ET-05 sub-vertical
                                                    # scope, CG-14 cell linkage
```

`check_payload.py` catches the cheap failures locally so your submissions spend their
round trips on the expensive ones — grain, identity and grounding, which only the server
can check.

`check_repetition.py` runs at a different moment from all the others: **while you are
still deciding how to write, not after you have written**. CG-15 refuses three or more
items of one field that share both their phrasing and their content words, so it is a
property of the ARRAY and invisible inside any single item — on 2026-08-08 two producers
met it at submit, one of them having already built all 708 heatmap cells. Twenty drafts
are enough to see it. The promoted Baxter run's 706 cell syntheses score 0.179 against a
line of 0.40, so a 700-cell page is demonstrably writable; if yours is refused, the shape
is the problem and not the scale. `03-pages/1-heatmap.md` says what to change.

`precheck_gates.py` sits between the two, and it exists because a submission is not
free. Submitting supersedes the staged row, so a FAIL on a page that was passing costs
you the pass until you repair it — and inside a promotion window, that blocks the
promote for every other page too. The gates it runs need the run's own facts (which
evidence rows exist and what they carry, which cells the run serves) but not a database,
so two tool calls you have already made are enough: `get_evidence` for every id the page
cites — `--list-cited` prints them so one call covers the page — and `get_report_bundle`.

It imports the connector's gate modules rather than restating them. A second copy of a
gate is a second answer to the same question, and the answer that matters is the
server's.

Run it on a page you did not write, too. The heatmap promoted on the run this was
written for returned **120 blocking reasons** when first checked this way: 79 foreign
sub-vertical cells sitting inside focus-area cell lists, 11 alerts naming cells the run
does not carry, 28 evidence rows whose stored excerpt cannot be cited, 2 lowercase
openings. A page that passed under an older gate set is not a page that passes now, and
finding that out from this costs nothing.
