# Fields the app depends on

Every entry below is a field the rendering layer reads. Where it is absent or
off-contract, a real surface degrades in a specific, observed way. This is not a
second contract — the page packs remain authoritative for shape — it is the list
of places where "technically valid" and "renders correctly" came apart in
production, with the consequence named so the cost of skipping one is visible.

Read this once. Then, when a page pack asks for a field listed here, know that
something on the page has nowhere else to get it.

## Closed vocabularies — a sentence in an enum field breaks a filter

| Field | Values | What a wrong value did |
|---|---|---|
| `context.timeline.events[*].signal` | `POSITIVE │ NEUTRAL │ NEGATIVE` | A consequence SENTENCE was written here. The column is TEXT, so promotion succeeded, and the D5 timeline's Positive/Neutral/Negative filters matched **zero of ten** events on a page with ten. |
| `context.timeline.events[*].maturity_effect` | prose, 1–2 sentences | This is where the consequence sentence belongs. |
| `techstack.techstack.items[*].status` | `CONFIRMED │ INFERRED │ CLAIMED │ ABSENT` | Required per row. There is no `PARTIAL`. |
| `heatmap…band` | `Activating │ Building │ Competing │ Differentiating` | Four bands. **Never write M5 or "Transformational"** — the resolver has four branches and anything ≥4.0 is Differentiating. |

Gate **CG-09** now refuses an off-vocabulary value at submit. Case matters: the
renderer compares against the declared spelling, so `positive` misses the filter
exactly as prose does.

## Every claim-bearing item cites its own evidence

Gate **AG-03**. Per ITEM, not per section. A why-now card, finding,
recommendation, insight, timeline event, issue, tech row, alert, cap, gate
result, phase or conversation starter that asserts something must carry a
non-empty evidence list of its own.

**An inference cites too** — the source it was drawn from. "No evidence yet" on
a card that makes a claim is not an empty state; it is an uncited claim.

## Leadership contact routes

`overview.leadership.roster[*]` now carries, per person:

| Field | Note |
|---|---|
| `email` | a work address, from a cited source |
| `linkedin_url` | full URL |
| `phone` | a line that is actually this person's. **Never a switchboard number on an individual's row** — that misrepresents it. |
| `enriched_at` | the date the route was established |
| `enrichment_basis` | WHERE it came from |

`enrichment_basis` is not decoration. **"Clay reports it" is not a source** — the
filing or profile Clay surfaced is. Without it, a contact route is the one field
on the panel asserting something with no provenance, and the panel says so.

These are established in YOUR session (step 4, Clay) and written into the roster
item. The app makes no third-party call while serving, so a route that is not
promoted does not exist for the reader. Mark the paths `internal_only`.

Do not attach a contact to the wrong person. A name-similar match is an identity
failure: a search for a Chief Data Officer that returns an intern with the same
surname is not that person, and quarantining the field is correct.

## Firmographics — state the footprint here

`jurisdictions` currently lives only in `context.regulatory_standing`, and the
context dashboard is **withheld from the AE role**. The AE landing view is what
the field reads, so a footprint stated only there is invisible to the person the
page is written for.

State the footprint in `overview.firmographics` as well. It is public
firmographic data, not internal. The same reasoning applies to any figure an AE
needs that you are tempted to state only on D5.

Every firmographic field also renders its own provenance, so a value with no
`source_e_id`/`as_of` renders as a bare number.

## Values the app computes — do not send them

Counts are computed, never asserted (invariant 8). Specifically:

- **CAGR** is computed from the financial series' first and last dated points
  over the real number of years between them. Send ≥2 dated points and it
  appears; send one and it correctly does not.
- **`grounded_on`** is the length of the citation array.
- **Landscape counts** are recomputed from the T1 register.
- **Pillar shares and thin-evidence flags** are the database's generated columns.

What the app CANNOT compute, and therefore needs from you:

- **Peer medians.** They exist at category and pillar grain in the workbook and
  nowhere else. Send them. With none, the heatmap shows no tick, no delta and no
  "at peer" badge — which is correct but says nothing. At subcap grain the app
  inherits the category median and labels it a proxy; do not restate it per cell.
- **Peer technographic deployment.** `peer_coverage` has no contract field, so
  the tech-stack detail states "not researched" and names the peer set it would
  search. A per-peer verdict is a research finding; it cannot be derived.

## Reasoning that renders

These render in full and were previously written and never shown, which is the
whole of the "shallow" reading:

- insight cards: `severity_rationale`, `alternative_explanation`,
  `validation_question`, `claim_label`, and the whole `r_layer`
- recommendations: `root_cause`, `cost_of_inaction`, `sequencing_reason`,
  `kpi_triple`, `validation_gate`, `r_layer`
- why-now: `cost_of_acting_now` — REQUIRED, and the honest other side of the
  argument. A card with only the upside is the shallow one.
- timeline: `storyline` and `arc_shape`
- roadmap: each phase's `rationale`
- platform: `discarded[]` with reasons — the "why not X" a reader looks for

Write them as if they will be read, because they are.

## Linkage that makes a page traceable

| Link | Why |
|---|---|
| `issue.linked_subcap_ids` | An issue with no cell cannot be tied to the DMA, and the drilldown says so. **Every matter that constrains a capability must name it.** |
| `event.capability_ids` | The route from a historical event back to the grid. |
| `techstack.linked_subcap_ids` | The tech detail's DMA impact is exactly these cells at their served scores. With none, it claims no impact. |
| `insight.linked_subcap_id` / `affects` | Also how the pillar is derived when `pillar_id` is absent. |
| `focus_area.subcaps` | Matched exactly. A cell the focus area does not name is not in its drilldown. |
| `value_chain` stages' own `subcaps` | The stage's cell membership is a claim about THIS client's operating model. |

## Insights: theme and pillar

`theme` and `pillar_id` were null on all eight cards of a real run, so the D2
theme lens collapsed to one bucket called "Other" and the pillar lens grouped
everything under nothing.

State `pillar_id` per card. State `theme` from the O6 vocabulary:

```
DATA FOUNDATION │ WORKFLOW │ DECISIONING │ CHANNELS │ TIMING │
RISK & COMPLIANCE │ OPERATING MODEL
```

**"Other" is not a theme.** If a card fits none of the seven, the card is
probably two claims — split it, or pick the one the evidence actually supports.
Untriaged cards now group by pillar with the reason stated on the page, which is
honest and still visibly incomplete.

## Sentiment

One line is not a sentiment picture, and gate S8 exists to say so. A run that
promotes a single NPS figure renders one bar and an honest "not established" for
every other audience. Search the public sources per `03-pages/2-overview.md`
before concluding an audience is unmeasurable, and record the ladder.

## Excerpts

The registration floor is 50 characters. A corpus whose excerpt median is 80 is
passing the gate and saying nothing — and 27 of 120 items in one run had **no
excerpt at all**. An excerpt is the sentence a reader would quote back. Take the
whole claim, not the fragment that clears the floor.

## Dates

`runs.completed_at` becomes every evidence item's `reference_date`. Without it,
the GENERATED `age_months` is null and `recency_band` is `UNVERIFIED` for EVERY
item — 120 items, 45 of them dated, all unverified, and a FACT then rendered
beside an "unverified" label. Check the manifest, and check the request id's own
`…-YYYYMMDD-NNNN` token before concluding there is no date.
