# Page: platform

Five sections sharing one recommendation id space. Produce them together — a phase citing a recommendation the payload does not describe fails.

**5 sections · 5 surfaces.** Submit with `submit_page_payload(run_id, page='platform', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

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

### The fit score comes from `get_platform_fit`. Call it. Read it.

**Refused by CG-30.** The engine is real now and lives in
`packages/shared/platform_fit.py`; the connector runs it for you and re-runs it
at submit against your own inputs. A card whose `fit_score` differs by more
than 0.05, whose `rank` disagrees with the engine's ordering, or that carries
no score at all is refused.

Until 2026-08-19 the engine the contract named existed only in the legacy
snapshot, so there was nothing to read and two clients answered the gap two
ways — one shipped `76.5` read off the OPPORTUNITY tile, the other shipped five
nulls. That is the whole reason this section exists.

**You supply judgement. The run supplies fact.**

| You send | The engine reads from the run |
|---|---|
| `platform` — the name a client would say | which cells the L3 area reaches |
| `l3_area` — the catalogue area it belongs to | each cell's distance from the target band |
| `alignment` 0–1 + `alignment_quote` | the severity of the issues on each cell |
| `readiness` — the prerequisite verdict | how well each cell is evidenced |
| `depends_on` — platforms this one needs first | whether the register calls the family absent |
| | the run's whole gap surface, for interconnect |
| | **relevance** — the share of the area's cells this sub-vertical serves |

**`depends_on` is how a workload stays behind its foundation.** A card is
never ranked above something it depends on. This was found by scoring a real
client: its own summary asks whether to "fund the visible next step … or fix
the foundation those steps depend on first", and the engine put the workload
first because the foundation stated NOT READY YET. Name the dependency and the
page reads as the argument does.

**Relevance is computed, not sent.** It caps the fit, so an out-of-vertical
family cannot buy its way back with gap surface — "out-of-vertical rank-1 is a
defect". Below 0.5 the card comes back `OUT_OF_VERTICAL`.

**Read `state` before you write the story.** `TOO_NARROW` (fewer than three
cells — the contract's discard rule), `INSUFFICIENT_EVIDENCE` (the cells
DRIVING the score carry no evidence, however many others do), or
`OUT_OF_VERTICAL`. A card in any of those states is not a ranking position to
argue for; it is a discard with a reason.

**`top_contributors` is the traceability mandate.** Five cells with their own
gap, severity and evidence numbers — the ones the score actually rests on.
Cite them in `story_md`; a breakdown a reader cannot walk back to named cells
explains nothing.

**`alignment` is the objective in the client's own words.** Same 0–1 key the
findings ranking already uses: *"15–30 words PLUS a 0-1 score, quoting the
entity's OWN stated objective."* Quote it in `alignment_quote`. If you could
not establish an objective, **omit `alignment`** — omitting renormalises to the
three-term blend and reports `impact_fallback`, which is what the contract
instructs. Sending `0` is a different claim: it says you established that this
platform serves nothing they are trying to do.

**Readiness MULTIPLIES.** Red is ×0.62, so the highest reachable red fit is 62
and a platform whose prerequisites are failing cannot render hot. A 2026-06
audit found 95 of 470 cards scoring ≥80 with every prerequisite red; this is
that defect made arithmetically impossible. Do not argue a red platform into
first place in prose — the number will not support you and CG-30 will refuse
the card.

**Rank-1 has to be defensible as the client's own priority.** The engine gives
alignment a fifth of the weight precisely so that a broad platform serving no
stated objective does not outrank a narrower one that does. If the engine's
rank-1 is not the platform you would argue for, that is a signal about your
`alignment` inputs, not licence to re-order: fix the input, or say in
`story_md` why the arithmetic ranks it there and what you would argue instead.

The breakdown modal must agree with the headline fit (570 of 685 cards
disagreed). Everything needed to reproduce the number is on the row the engine
returns — `factors[]`, `subtotal`, `readiness_multiplier` — so copy them
rather than restating them.

Out-of-vertical rank-1 is a defect: a carrier platform must not top a bank's list.

story_md must be whole sentences — 501 cards shipped head-clipped mid-sentence.

### One tile per promoted L3 area, or the area renders empty

The page is organised by **L3 area tabs**, and the tab set is the union of the
`l3_area` on the recommendations and the `l3_area` on the story's own gap rows. A
story is filed under the area ITS GAP ROWS name. So a run that promotes
recommendations across five areas and a story covering one leaves **four tabs with
no story, no gap rows and an empty-state sentence** — which is what "the story is
not thorough and is not done for all areas" looks like from the client's side.

> Every L3 area this run promotes a recommendation against carries its own tile:
> fit score with its basis, gap rows, estate reach, peer deployments, readiness,
> a story and **its own `r_layer`**. A tile is not a heading; it is an argument.

Two consequences worth stating because both were shipped wrong:

- **An area with no engine tile still gets a tile — with `fit_score: null` and the
  reason.** The engine ranks a fixed set; an area the analyst promoted and the
  engine did not rank has no figure, and inventing one is worse than the null.
  Say which is which: *"the engine ranked four platforms for this run and this area
  was not among them."*
- **The per-item `r_layer` is where AG-01 is satisfied on this page.** A section
  `r_layer` covers the ranking; the per-tile one covers THAT tile's claim. Five
  tiles arguing from one shared reasoning trace is one argument wearing five hats.

### Peer deployment is research, not flavour

This is the field readers reach for first and the one most often absent: *what have
comparable institutions actually put in on this platform, and what does that mean
for us*. `peer_deployments[]` on a platform tile takes the same shape and the same
gate as it does on the tech register — `{peer, deployed, basis, source_url, as_of}`
with `peer_coverage` in 0..1 — and **AG-04 is not scoped to the register**, so it
fires here identically.

**Search per platform area, not per vendor.** The area is the question ("does this
peer run an integration layer"), the vendor is one possible answer. Searching only
the vendor name finds the one peer that bought that brand and misses the peer that
solved the same problem with another, which is a finding you needed.

Productive routes, in the order they pay:

| Route | What it establishes |
|---|---|
| The delivery partner's case study (Silverline, Slalom, Deloitte Digital, the SI named in the release) | The products, the start date and the go-live — the richest single source class |
| Vendor customer-story pages (Salesforce, MuleSoft, Q2, Alkami, Lumin, UiPath, Backbase, Snowflake) | Selection and, sometimes, outcomes |
| The peer's own newsroom | First-party, and the only class that can state present tense with authority |
| Trade press — CU Times, CUToday, Finopotamus, American Banker, FinTech Futures | Corroboration and dating |
| The peer's careers postings | Often the only public statement a platform exists at all |
| **The run's own report** — benchmark and peer sections | Frequently names peer platforms outright, and it is already inside the run |

**Establishing a deployment.** A row is `deployed: true` only with a source URL and
an `as_of`. Everything else is `deployed: null` **with the searches recorded in the
basis** — not omitted, because a peer left out of the list implies it was checked.

| What you found | Verdict | Why |
|---|---|---|
| Named institution, named product, dated source | `true` | The claim and its basis are the same statement |
| A competing platform announced later on the same layer | `false` | An established competing answer is an answer |
| A vendor release naming a DIFFERENT institution | `null` | It is evidence about someone else. Never let a customer list stand in for a customer |
| A vendor page with no date anywhere | `null`, or `true` only if another source dates it | `as_of` is not optional and a copyright footer is a weak substitute — if you use one, say so in the basis |
| An announcement more than four years old with no later confirmation | `null`, with the finding written out in full | A 2018 pilot does not establish what runs today. Record the vendor, the date and why it does not carry, so the reader gets the finding without the false present tense |
| Two institutions publishing under one name | `null` on identity, with the ambiguity stated | Attributing a platform to the wrong institution is the one error the reader can catch and never forgive |

**Scope the share to what the breakdown supports.** One established of five is one
established of five — never "20% of peers have not adopted", which asserts four
negatives you did not establish. Where nothing is established, **omit
`peer_coverage` entirely** and let the breakdown speak.

**Then name the integration pathway.** A peer deployment that stops at "GreenState
runs MuleSoft" is trivia. The pathway is three sentences and it is the point of the
research:

1. **What the peer put in, and what it produced** — dated, cited, in their terms.
2. **Which capability of THIS client's that connects to** — by cell and score, so
   the reader can see the same problem in their own numbers.
3. **What sits on that pathway from us** — the offering, named, and tied to the
   assessment's own gap-to-solution mapping where the report states one.

The third sentence is AE-facing commercial framing, so **mark its path in
`internal_only`** and keep the client-facing value in the first two. A client
dashboard that pitches at the client reads as a brochure; the same finding without
the pitch reads as analysis, and the AE still has the pitch.

Honesty binds harder here than anywhere on the page, because every claim is about
an institution that is not in the room and can be phoned:

- A peer deployment you cannot cite is `null` with a stated basis, never a guess.
- Never average disagreeing figures — state both and say they disagree.
- Never claim a peer deployed something on the strength of a vendor press release
  that names a different institution.
- Read the product precisely. "Member 360 on Financial Services Cloud" is not "Data
  Cloud", and promoting one to the other to make the story tidier is a fabrication
  that a competitor will correct in the meeting.

### Estate reach is derived from the register, never asserted

*"Where the estate does not yet reach"* is a computation, and it was being written
from impression. The register already carries `linked_subcap_ids` per row, so reach
is arithmetic:

> A cell is **reached** when at least one register row lists it among its linked
> capabilities. Every other cell this run scores in that category is **not yet
> reached**. Both numbers come out of the register; neither is a judgement.

Emit the derivation with the numbers, not just the conclusion: per category, how
many cells this run scores, how many a register row is linked to, which ones, and
which products hold that layer with their status. Then say **why the non-reach is
established** — and that sentence is where the register's status vocabulary earns
its keep:

- **ABSENT on a recorded negative search** is the strongest form. The layer is open
  and the run can prove it looked.
- **INFERRED** may be described as a signal only. An inferred product is not a
  governed layer, and reading it as one is how a page recommends what the client
  already owns — or refuses to, wrongly.
- **CONFIRMED at this layer** turns the whole tile into extension and adoption
  depth. Say so explicitly, in the story as well as the reach block.
- **An unresolved research flag** in the assessment's own "what we could not assess"
  section is a reason to hold, and citing it is stronger than any inference.

Distribution is usually the finding. When every reached cell sits in one capability
group and the cells scoring lowest have no register row at all, that pattern is the
sentence: *the estate reaches the channels, and the record of what happened across
them is where the next capability sits.* Write it as available value, never as
fault — `01-start-here/3-language.md` governs, and the reader may be the person who
chose the incumbent.

### Readiness carries its reasoning, or it is a list of conditions

The readiness panel reads from `recommendations[].prerequisites[]` — **not** from
the story — so readiness reasoning written anywhere else renders nowhere. Two row
shapes, and they render differently:

- **A cell threshold** `{cell, minimum, current, verdict}` renders as a badge, a
  progress bar and a drilldown of backing cells. It carries no prose and needs none.
- **A condition** `{condition, note, basis}` renders as a sentence with a
  supporting sentence and a badge. **This is the only place on the page where
  readiness can reason**, so it is where the reasoning goes.

A condition with no `note` states a requirement and argues nothing. A good `note` is
40–80 words and answers three questions in this order:

1. **What is already true**, and how it was established — the evidence, the named
   owner, the gate that is met. Readiness prose that opens on what is missing reads
   as a blocker list; opening on what is in place reads as a plan.
2. **What must be true first**, and why it is a real prerequisite rather than a
   formality. "An ungoverned API layer becomes a second point-to-point estate" is a
   reason; "governance is important" is not.
3. **The sequencing basis** — the dependency or the date that fixes this phase.
   Where a statutory deadline moves a phase ahead of its fit rank, say that a date
   ordered it and a rank did not. Where the engine's rank and the sequence disagree,
   state the disagreement on the card and name the gate that decided it.

Keep the reasoning in the `note` and the codes in the structured fields. The panel
renders `cell` as a badge already; a sentence that says "P4C3 ≥ 2.5" spends the
reader's attention on grammar they do not have.

### Sentence case, on every prose field

Measured on a real client page: readiness conditions, their notes and their basis
badges all rendered lower-case mid-card — *"architecture decision owner named for
the platform"* — because they were written as fragments in a dictionary and never
read as sentences. They are sentences on the screen.

> Every string that renders as prose begins with a capital letter and ends in
> terminal punctuation. Check the payload, not your intention — scan every string
> before submitting.

The exception is exact, and inverting it breaks the page: **contract vocabularies
keep their declared spelling.** `opens_on`, `horizon` (`next two quarters │ this
year │ beyond`), `peer_basis`, `provenance`, `signal`, stack `status`,
`producer_version`, JSON paths in `internal_only`, ids and URLs are matched
literally by the renderer or the serve layer, and capitalising them silently drops
the row out of its filter. AG-05 polices the spelling; case is part of it.

A one-line scan is enough: walk every string in the payload, skip the vocabulary
keys, and flag anything whose first alphabetic character is lower-case.

### The candidate set comes from the catalogue, and the vertical bounds it first

Two questions have to be answered before a single relevance is scored, and
answering them in the wrong order is what makes this page read as generic.

**Where do candidates come from?** From the catalogue's own per-cell platform
vocabulary — `l3_platform_areas` and `l4_features` on every cell the run serves,
which arrive in `get_report_bundle` and on `/subcaps`. Rank the platforms the
run's own cells NAME, by how many of those cells each one reaches and how far
below the composite they sit. That sweep is the candidate set. Baxter Credit
Union's 706 served cells name 220 distinct platforms between them; a page whose
candidates were the client's existing Salesforce estate plus two invented
solution categories was not drawing from the catalogue at all, and it showed —
Databricks, Twilio, Tableau and nCino each address cells this client scores and
none of the four appeared anywhere on the page, as a tile or as a discard.

If the vocabulary comes back empty on every cell, that is a **catalogue load
defect, not licence to invent candidates**. Say so and stop; do not fill the
silence with vendor names you happen to know.

**Which of those candidates are eligible?** The ones inside this entity's
vertical. The vertical bounds the candidate set BEFORE relevance is scored, so a
platform outside it never enters, is never weighed, and has no discard to render.
This is a gate, not a guideline: **ET-06** refuses a discard whose stated reason
argues from vertical or entity type, and refuses one whose anchor cells belong to
another sub-vertical. Run `scripts/precheck_gates.py … --bundle` before submitting
and it will tell you locally.

### `discarded[]` is the field a reader actually looks for

A platform list with no recorded alternatives reads as the only option anyone
considered, and the first question in the room is "why not X". `discarded[]`
answers it before it is asked: `{platform, reason, relevance}`.

**A discard is a platform that was genuinely in contention.** It reached the
shortlist, the arithmetic weighed it, and something specific about THIS estate
put it below the line. Three grounds do that honestly: the client already runs it
at that layer (an adoption conversation, not a fit one), it addresses fewer than
three of this run's cells, or its relevance sits below 0.5 against the cells it
does reach. Sequencing is a fourth: a platform that only pays off after another
platform lands is set aside on order, not on merit — say which one it waits for.

Out-of-vertical is **not** on that list any more, and putting it there was the
defect. Baxter Credit Union's page carried "Insurance policy administration and
claims" at relevance 0.15, with the reason "Out of vertical: its anchor cells
belong to a carrier entity type". The producer knew, wrote it down, and spent one
of six client-facing cards explaining to a credit union why an insurance carrier
product does not apply to them. That is not thoroughness — it is a card that
tells the client their assessment shopped in the wrong industry, and it costs the
slot a real alternative should have had.

Two rules on the reason. It is about **fit for THIS institution**, never a
criticism of the product — "addresses two of this client's cells" is a fit
statement; "weak analytics" is a product review, and it is both unnecessary and
unsupportable. And it is specific enough to be checkable: name the cell count
from the catalogue sweep, and name the incumbent from the stack register when the
layer is occupied. "Twilio reaches two served cells, below the three-cell floor,
and Genesys Cloud, Glia and Tethr are all confirmed at that layer" is checkable.
"Not a strong fit" is not.

**A ranking that cannot discard is a sort.** Six clients ranked an out-of-vertical
platform first, one of them with a relevance of 0.35 that was simply ignored. The
fix for that is the boundary above, not a lower number: a relevance of 0.05 on a
carrier product still renders a card.

### Coverage prose names what is available, never what is missing

This page's characteristic language failure is the templated line — "what *vendor*
does not cover" — generated per row and grounded in nothing. It is unusable twice
over: it is not data-backed, and it reads as accusatory about a product the client
may have chosen deliberately.

Write the other side instead. Name what exists, what it reaches, and where the
next capability sits. The finding does not change; only whether the sentence is
about a failure or about available value. `01-start-here/3-language.md` owns the
rule and it is not optional on this page.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| platforms[].fit_score | `get_platform_fit` (packages/shared/platform_fit.py) | fit = 100 × (0.528·opportunity + 0.208·interconnect + 0.064·greenfield + 0.20·alignment) × readiness_multiplier; read, never recomputed. The Spec's "0.34 × readiness" is a mis-transcription — 0.26 + 0.08 = 0.34, and those are interconnect and greenfield, not readiness (owner adjudication 2026-08-19) |
| platforms[].gaps[] | scoring workbook | the subcapabilities this platform addresses |
| platforms[].story_md | producer | grounded in the client's own gaps and stack |
| platforms[].estate_reach | the run's own tech register | `linked_subcap_ids` per row against the cells this run scores — computed, never asserted |
| platforms[].peer_deployments[] | research, per the protocol above | one row per named peer, including the ones you could not establish |
| readiness prose | recommendations[].prerequisites[] | the panel reads from there; reasoning written elsewhere renders nowhere |
| vertical guard | platform_fit_data.py | subvertical adjacency; carrier anchors must not surface on banks |

### Prompt

```
Produce the platform fit and story: which L3 platform areas address this client's assessed gaps, grounded, ranked, and with the irrelevant ones visibly discarded. STEP 1 - DRAW THE CANDIDATE SET FROM THE CATALOGUE, AND BOUND IT BY THE VERTICAL FIRST The candidates are the platforms the run's OWN CELLS name: l3_platform_areas and l4_features on every served cell, from get_report_bundle or /subcaps. Rank them by how many of this run's cells each reaches and how far below the composite those cells sit; that sweep IS the candidate set. Then bound it: a platform outside this entity's vertical is not a candidate, and the bound applies BEFORE any relevance is scored, so it never enters and never needs discarding (ET-06 refuses it either way). One client's 706 cells named 220 distinct platforms; a page built from the client's existing estate plus two invented solution categories missed Databricks, Twilio, Tableau and nCino entirely. An empty vocabulary on every cell is a CATALOGUE LOAD DEFECT - report it, do not invent candidates to fill the silence. The unit of recommendation is the L3 PLATFORM AREA and its L4 FEATURES. For every claim, the path L3 -> L4 -> sub-capability must be renderable, because that path is what makes the recommendation auditable rather than a vendor preference. Emit catalogue_path per gap row. A claim that cannot name the L4 feature that addresses the cell is not a fit claim. STEP 2 - GROUNDING (per gap row) {subcap_id, name, current_score, peer_score, gap, pillar, l3_area, l4_feature,  catalogue_path, e_ids[]}   current_score MUST equal what the heatmap serves for that id. Assert it within   +/-0.05 before emitting. Every row cites. A gap row with no evidence behind   the current score is not addressable, it is a guess. STEP 3 - FACTOR IN THE ENTITY'S OWN TECH STACK (this changes the answer) Read the stack register and apply it:   - CONFIRMED at this layer -> greenfield becomes EXTENSION. Reframe the     opportunity as adoption/depth, and say so; recommending what they already     own is the Tech Stack Mismatch failure.   - ABSENT with a demand signal (hiring, RFP, board commitment) -> RAISE     priority and cite the signal.   - Mid-migration -> a TIMING CONSTRAINT on everything downstream of it; carry     it into sequencing.   - CLAIMED but unconfirmed -> treat as absent for fit, and flag the     Marketing-Reality Gap. STEP 4 - DISCARD, WITH REASONS A discard is a platform that was GENUINELY IN CONTENTION: it reached the shortlist, the arithmetic weighed it, and something about THIS estate put it below the line. Drop it when the client already runs it at that layer (adoption, not fit); when it addresses fewer than 3 of this run's cells; when relevance against the cells it does reach is < 0.5; or when it only pays off after another platform lands - say which one it waits for. Out-of-vertical is NOT a discard ground: that platform was excluded at STEP 1 and a card explaining to a client why another industry's product does not apply to them is a defect, not thoroughness (one credit union's page spent a card on insurance policy administration at relevance 0.15; lowering the number would not have helped, the card was the problem). Each reason names the cell count from the STEP 1 sweep and, where the layer is occupied, the incumbent from the stack register. Emit discarded[] {platform, reason, relevance}. A ranking that cannot discard is a sort. STEP 5 - THE EFFORT PROFILE, AND WHERE EFFORT MATTERS MORE Rank the effort dimensions (integration, data quality, process redesign, change management, licensing) for THIS client, from the evidence. The profile must be consistent with the timeline's storyline: if the storyline attributes integration debt to a 2014 core conversion never revisited, integration ranks first. An effort profile that contradicts the history is one of them being wrong. STEP 6 - THE PLATFORM STORY  (90-150 words) Not a dossier and not a vendor pitch: what this platform would change for THIS client, which constraint it lifts, what it depends on, and what it does not solve. Name the cells. Cite. Must reconcile to the composite - if the story argues for a platform the arithmetic ranks third, say why. STEP 7 - THE REASONING LAYER (R-Layer, and it is the point of this page)  A State the rank-1 fit claim with its confidence.  B Argue the runner-up's case explicitly. Inside a 5-point margin, present both    and say the ranking is close.  C Is this platform plausible for this sub-vertical, size tier and regulator?  D Probes, each firing a required search: candidate-set provenance (did the    candidates come from the catalogue's per-cell vocabulary, and was the    set bounded by the vertical before scoring); out-of-vertical rank-1;    anchor-cell entity-type mismatch; Tech Stack Mismatch; stale fit figure computed against    a superseded run; breakdown-not-equal-to-headline; a gap row whose current    score disagrees with the heatmap.  E ACCEPT / REJECT / UNCERTAIN. REJECT -> discard and re-rank. STEP 8 - RECONCILE THE ARITHMETIC WITH THE ANALYST Read the assessment report's platform sections. If the composite's rank-1 is a platform the report does not discuss, that disagreement is a finding: state it, say which won, lower confidence. Never ship an arithmetic rank that silently contradicts the analyst. GATES: ET-06 candidate set bounded by the vertical; S31_platform_distinctiveness; S13_platform_score_lead; S17_exec_fit_stale; breakdown-equals-headline; catalogue_path present per row.
```

---

## P2 · Recommendations

- **Section** `platform.recommendations` — **renders on** D4 (Platform)
- **Contract** Detail, impact, effort, sequencing and provenance. A derived recommendation must never present as analyst judgement.

### Must present

The analyst's recommendations with their detail: what, why, prerequisites, effort, and the capabilities each targets.

Analyst recommendations and synthesised ones must be distinguishable — 32 clients shipped synthetic recs laundered as analyst output.

The drilldown must carry the detail the panel promises.

### Six fields that render, and were displayed by nothing

Every one of these was promoted, served, and shown to no one — which is the whole
of this page being read as shallow. The reasoning was written; it never reached the
screen. They render now, so write them as if the AE is reading them in front of the
client, because that is where they land.

| Field | What a good one contains | What an empty one costs |
|---|---|---|
| `root_cause` | 30–60 words, cited: why the gap EXISTS. A root cause of "the score is low" is not one | The recommendation is a wish. Nobody can tell whether it addresses the cause or the symptom |
| `cost_of_inaction` | 30–60 words, GROUNDED in one of: a dated regulator milestone, a peer trajectory, a contract or licence expiry, a migration date in evidence, a stated board commitment. If nothing grounds it, write "no dated trigger established" | The recommendation competes with everything else on the client's list and loses, because nothing says what waiting costs |
| `sequencing_reason` | 20–40 words: the dependency or gate that fixes this phase. Must agree with the roadmap AND the stair-step — 17 clients shipped a sequence contradicting their own roadmap | The order looks arbitrary, and an arbitrary order invites re-ordering by whoever is loudest |
| `kpi_triple` | `{metric, baseline, target}` where the **baseline is a figure that exists in the pack with an `as_of`** — never an aspiration | Nobody can tell later whether it worked |
| `validation_gate` | The readiness condition as a cell and a threshold (`P4C1 >= 2.0`), its verdict `MET │ NOT MET`, and the BACKING CELLS producing that verdict — the drilldown renders them, so the verdict must be traceable | A readiness claim with nothing behind it, and a drilldown that opens onto an assertion |
| `r_layer` | The recorded hypothesis, counter, domain test, probes and verdict | AG-01 blocks the submission |

`provenance` is `ANALYST │ DERIVED`, required, never blank. DERIVED means composed
from the pack by rule. **32 clients shipped derived rows presented as analyst
recommendations** — a derived recommendation must never present as analyst
judgement, and the distinction is the reader's basis for trusting the rest.

`dma_impact[]` is one row per affected cell, and each row's `current` **must equal
what the heatmap serves** — assert it, within 0.05, before emitting.

### The gates this page dies on

- **AG-01** blocks a ranked or causal claim with no `r_layer`. **Sequencing is a
  causal claim**: putting phase 2 after phase 1 asserts a dependency, so the roadmap
  needs its reasoning recorded as much as the ranking does.
- **AG-03** fires per ITEM. Every recommendation, phase and starter that asserts
  something carries its own non-empty evidence list, read from the keys its field's
  contract `doc` declares. An inference cites the source it was drawn FROM.
- **Cross-page reconciliation.** `scripts/check_consistency.py` reconciles roadmap
  phase ids against the recommendation set and gap rows against served scores. Run
  it before submitting — no per-page gate can make that check, because each page
  passes its own submission independently.

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

**Each phase's `rationale` renders**, and it was displayed by nothing until
recently — so the roadmap showed an order with no argument for it. A phase whose
rationale restates its own title tells the reader nothing they could not see; the
rationale's job is the DEPENDENCY: what must be true before this phase, and what
this phase makes possible.

`narrative_thread` was null on all 34 promoted sections of a real run. This page
carries one like every other: write it last, from what you actually produced. See
`04-craft/3-page-narrative.md`.

Two earlier defects worth one clause each, because they explain why thin fields are
now visibly thin: the roadmap rationale and the conversation starters rendered a
PROTOTYPE FIXTURE under a real client's name — prose naming Synovus, BMO, Truist
and "1,800 users" — because the promoted fields were never read. They are read now.
A thin field is no longer invisibly replaced by fiction; it is simply thin, which is
the honest failure and the one you can fix.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| phases[] | recommendations_detail.json + assessment report | {phase, horizon, capabilities[], depends_on[], rationale} |
| phases[].rationale | producer | the dependency that fixes this phase's position; renders on the card |
| phases[] rec ids | the recommendation set | every phase cites ids P2 describes; reconciled by `check_consistency.py` |
| sequencing_basis | producer | why this ordering rather than another |
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
