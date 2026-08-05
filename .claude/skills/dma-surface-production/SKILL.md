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

Read these two, in this order. They apply to every section and are not repeated in the
page packs.

1. `01-start-here/1-standing-clauses.md` — identity, grain, register, audience. Four rules that
   caused most of the measured defects in this product when they were left implicit.
2. `01-start-here/2-evidence.md` — tiers, recency, the rank score, the peer fallback ladder, and
   what to do when you cannot establish an id.
3. `01-start-here/3-language.md` — every gap is stated as available value. A client reads this.
4. `01-start-here/4-absence-protocol.md` — never say no until a documented ladder has failed.
5. `04-craft/4-card-anatomy.md` — the header, sub-header and budget each surface renders into.
6. `04-craft/1-reasoning.md` — the R-Layer. The only mechanism that catches a claim that is
   well-formed, correctly cited, grain-locked and wrong.

## The workflow

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

**Write the page's thread before you submit it.** A page is not a container for surfaces — an
AE reads it top to bottom and takes one argument away. Each page carries a `narrative_thread`
of 45–75 words tracing the line through its surfaces in render order. Write it last, from what
you actually produced. If you cannot write it, the surfaces are not yet a page. Per-page
threads and their tests: `04-craft/3-page-narrative.md`.

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
python scripts/check_consistency.py <rundir>/     # all six page payloads together
```

It reconciles the composite against the pillar means, the hero against the grid, gap rows
against served scores, roadmap ids against the recommendation set, landscape counts against the
register, O8 against C6, confidence against evidence count, and the framing sentence against
the top finding.

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

Resubmission supersedes cleanly. Submit, read, repair, resubmit as often as needed — there
is no merge, no accumulation and no cleanup. For the gate families and how to read a
verdict, see `05-lifecycle/1-gates.md`.

### 8 · Promote

```
promote_run(run_id) → all six pages, one transaction, all or nothing
```

If it returns `incomplete_run`, it names the missing and unpassed pages. Re-promotion is
idempotent, so a retry is safe.

## Ten rules that are not negotiable

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
12. **Frame every gap as available value.** Name what exists before naming what does not.
    Never assign fault, never describe a person or a team.
13. **A page tells one story.** Write its thread before you submit it.
14. **Argue against your own conclusion before you ship it.** A claim that survives its
    strongest counter-argument is one you can defend in the room.
15. **Never average two disagreeing figures.** The result is in no source. Quarantine and state
    the contradiction — the resolution is the finding.

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
| `01-start-here/2-evidence.md` | Always — tiers, recency, rank score, peer ladder, citation |
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
| `01-start-here/5-colour-and-bands.md` | Writing a band word, or describing the heatmap |
| `03-pages/<n>-<page>.md` | Before producing that page |

## Scripts

Run these rather than eyeballing — they are faster and they do not get tired.

```bash
python scripts/preflight.py --run-id <uuid>        # where the run stands, what is blocking
python scripts/check_payload.py <payload.json> --page <page>
                                                    # local checks before you submit:
                                                    # required fields, budgets, id patterns,
                                                    # internal_only marking, empty states
python scripts/score_prompt.py <prompt.txt>        # score a prompt you have written
                                                    # against the 14-attribute standard
python scripts/check_language.py <payload.json>    # accusatory framing, and gap statements
                                                    # with no adjacent asset
python scripts/clay_plan.py --domain <domain>      # the enrichment call sequence and the
                                                    # tier each data point registers at
python scripts/check_consistency.py <rundir>/      # cross-page reconciliation before
                                                    # promotion — the check no per-page
                                                    # gate can make
```

`check_payload.py` catches the cheap failures locally so your submissions spend their
round trips on the expensive ones — grain, identity and grounding, which only the server
can check.
