# Page: techstack

One section producing two surfaces plus a detail sub-page.

**1 sections · 2 surfaces.** Submit with `submit_page_payload(run_id, page='techstack', payload={...})`.

Read `01-start-here/1-standing-clauses.md` before writing any section on this page. The standing clauses apply to every section and are not repeated below.

## Sections on this page

| Section | Required | Surfaces | Renders on |
|---|---|---|---|
| `techstack` | yes | T1, T3 | D6 |

---

## T1 · Technology stack register

- **Section** `techstack.techstack` — **renders on** D6 (Tech stack)
- **Contract** Four layer cards — operations, customer engagement, data, infrastructure — each with a pillar tag and a detection count.

### Must present

The client's actual stack by layer — core, CRM, data, integration, channel — each entry a PRODUCT with its vendor and evidence.

A service or a category is not a product ('Django' as a product, 'CRM; Analytics/BI' as an entry).

Dropped candidates are reported, not silently discarded.

### Information sources

| Field / element | Source of truth | Where it comes from |
| --- | --- | --- |
| items[] | Research workbook tech rows; client profile | {vendor, product, layer, confidence, e_id} |
| layer | producer | core │ crm │ data │ integration │ channel │ security |
| dropped[] | producer | candidates rejected by the taxonomy, with the reason |
| compliance_attestations | profile / research | where the client states one |

### Prompt

```
**REISSUED** — the design specification carries two conflicting layer lists and the
prototype a third; the original prompt also omitted the status field the landscape strip
recomputes from.

STEP 1 — A PRODUCT, NOT A SERVICE OR A CATEGORY
"Salesforce Financial Services Cloud" is a product. "CRM", "Analytics/BI", "Django" are
not. vendor and product are separate fields.

STEP 2 — EMIT items[]
{ts_id, vendor, product, layer, pillar_id, status, evidence_level, detection_basis,
 as_of, linked_subcap_ids[], e_ids[]}

layer   OPS | CUST | DATA | INFRA
        OPS=Operations & core banking (P3) · CUST=Customer engagement (P2, primary gap)
        DATA=Data & analytics (P4) · INFRA=Infrastructure & cloud (P4)
        NOT L2–L5 — those keys collide with the L1–L4 evidence levels on the same card.

status  CONFIRMED | INFERRED | CLAIMED | ABSENT
        Required on every row. The landscape strip recomputes its four counts from this
        field; without it the strip is uncomputable.

evidence_level  L1–L4, and it governs the verb the prose may use.
detection_basis one clause, printed on the detail page.

STEP 3 — LAYER ROLLUP
Per layer: {layer, pillar_id, detected, expected, is_primary_gap}

STEP 4 — dropped[] IS REPORTED, NOT HIDDEN
A candidate you cannot cite is a rumour. Put it in dropped[] with the reason.

GATES: no service or category shipped as a product · every item cited · landscape counts
reconcile to the register
```

---

## T3 · Platform detail

- **Section** `techstack.techstack` — **renders on** D6 (Tech stack), one sub-page per row
- **Contract** Per row, in addition to the register fields: `dma_impact`, `peer_coverage`,
  `peer_deployments[]`. All three optional; a row that omits them renders its linked cells and
  says nothing more.

### What the drilldown must present

Three cards, and each one previously asserted something no source stated. That history is the
specification, so it is written out.

**1 · DMA assessment impact.** It computed `baseline = score − 1.2` and `target = score + 1.3`
for an absent product — two constants that appear in no source — and drew the result as
movement between two numbers. Asked what the impact was based on, the honest answer was
nothing.

Removing the arithmetic left a second, quieter defect that took a client read-through to see:
the prose that replaced it **explained the score**. "The core is the system of record behind
Technology Roadmap & Investment Planning: its release train sets what can be scheduled, so
roadmap decisions are planned around it" is a sentence about why a cell scored 2.5. That is not
the question. The reader is standing under a product name asking *what does the thing we
actually bought do for us here, and what does it not do yet* — and the score is already served
in the card beside the prose, so restating it spends the whole budget saying what the page
already said.

So `dma_impact` makes **four moves, in this order**, in 40–90 words. Miss one and the card
reverts to score commentary.

1. **The capability of the DEPLOYED product.** What this product, at the edition and scope this
   institution actually runs, does in THIS estate — not the vendor's catalogue, the deployed
   thing. Cite it: the vendor's documentation for that edition, the client's own statement, a
   job posting naming the module, the case study naming the deployment.
2. **The cells that reaches.** Name them, or the capability they share, and say what about the
   product reaches them. Read each linked cell's served score from the bundle to choose which
   cells are worth the words; never print the score back.
3. **The documented boundary.** Where this product stops, taken from the product's own
   documentation rather than from a hunch. This is the move the register cannot make for you and
   the one the card exists for.
4. **The Zennify pathway.** The integration or implementation work that carries the estate from
   that boundary to the capability the assessment says is missing. It has to follow from moves 2
   and 3; a service line bolted onto the end reads as a bolted-on service line.

**Worked example — Symitar Episys, CONFIRMED, linked to P4C3.1.2.**

> Episys is BCU's system of record for members, accounts and postings, cloud-hosted since the
> 2025 Jack Henry renewal, and its release train sets what Technology Roadmap & Investment
> Planning can schedule in a quarter. Jack Henry publishes the reach beyond that boundary as a
> separate product: SymXchange is the web-services API third parties use to access the Symitar
> database. Zennify's pathway is that service layer and the contracts on top of it, so channel
> and analytics work stops queueing behind core releases.

Read it against the four moves. Sentence one carries the capability and the cell together —
cloud-hosted core of record, and the release train is *why* it bears on roadmap planning.
Sentence two is the boundary, and note where the boundary came from: **Jack Henry's own
developer documentation states that SymXchange is the API third parties use to access the
Symitar database**, which is the vendor saying that reaching the core is a separate product.
That is a fact about the architecture, not a complaint about the core, and it is citable.
Sentence three is the pathway, and it is the boundary turned into work.

Four things not to do, each of which a shipped version did:

- **Never derive a score** and never project one. Scores come from the workbook (rule 1), and no
  source states a post-investment target, so there is no target to state.
- **Never restate what is already served.** If the paragraph would still make sense with the
  product name swapped for a cell id, you have written a score commentary and not an impact.
- **Never assert a limitation the vendor's own documentation contradicts.** The boundary is the
  most quotable sentence on this page and the one most likely to be read back to you by the
  vendor's account team. Find the vendor's statement of scope first, write the boundary second.
  If the documentation says the product does the thing, then it does the thing — and the finding
  becomes that the estate has not configured it, which is a different sentence with a different
  owner and needs its own evidence.
- **Never assign fault.** See below.

**2 · Peer deployment.** It decided "✓ deployed" against a NAMED credit union from
`hashCode(ts_id + peerName) % 100`, over a `peer_coverage` that had no contract field and so
rendered "—% adopted" on a zero-width bar.

A technographic claim about a named institution is a research finding. `peer_coverage` is a
share in 0..1 of the run's named peer set; `peer_deployments[]` is the breakdown behind it, one
row per peer as `{peer, deployed, basis, source_url, as_of}`. Gate **AG-04** refuses a share
with no breakdown, a `deployed: true` row with no source or no date, and a share that disagrees
with its own breakdown by more than one peer.

**Include the peers you could not establish, with `deployed: null`.** Two of five deployed with
three unknown is not 40% adoption, and the card can only say so if the unknowns are in the list.
Where the peer set has no public technographic footprint at all, omit `peer_coverage` entirely —
`peer_deployments[]` with every row `null` still renders, and it renders the truth: five peers
searched, none established. A card that says that is worth more than a share that is not real.

#### The research protocol

The peer set is the run's own — read it from `peer_table` in the bundle, never assemble one.
For each product worth comparing, ask the same question of each named peer: *what is this peer
running at this layer?* Not "does this peer run this product" — the more useful answer is often
that a peer runs a **different** product at the same layer, and that is a `deployed: false` with
a source, which is a much stronger finding than an unknown.

**What establishes a deployment.** In descending order, and the first one that lands is the one
you cite:

| Class | Example | Verdict it supports |
|---|---|---|
| The vendor names the institution | Jack Henry's release announcing Alliant's Episys conversion; Salesforce's page titled "Alliant boosted data quality by 350% with Financial Services Cloud" | `deployed: true` |
| The institution names the vendor | a peer's own newsroom or annual report naming the platform | `deployed: true` |
| An implementation partner names the client AND the product | a systems integrator's case page naming both | `deployed: true` |
| A partner names the client but NOT the product edition | "GreenState implemented Salesforce" with no edition | `deployed: null` — the platform is established, the product is not |
| The peer is named on a COMPETING product at the same layer | Q2's own customer story placing GreenState on the Q2 Digital Banking Platform | `deployed: false`, with that source |
| Careers postings naming the system | a peer's job description requiring Episys PowerOn | `deployed: true` if the posting is the peer's own and dated |
| A vendor's aggregate claim | "seven of the top ten credit unions partner with Blend", naming none | `deployed: null` for every peer |
| A vendor release naming a DIFFERENT institution | PenFed's Agentforce deployment when PenFed is not in this run's peer set | nothing at all — it does not touch this cohort |

**What to do with a vendor claim.** A vendor page that names the institution is a source; a
vendor page that names a number is not. "Seven of the top ten" cannot be distributed across five
named peers, and a market-share figure cannot be pushed down onto a row. Where the only source
is an aggregate, every peer is `null` and the `basis` says which aggregate it was and why it
does not reach the row — that sentence is the finding.

**How to record an absence.** `deployed: null` with a `basis` naming *what was searched*, in the
peer's own terms: "Searched Jack Henry, Fiserv and Corelation client releases and the
institution's own newsroom; no public source names its core processor." Never "not researched",
which describes the producer rather than the world, and never a bare `false`, which asserts an
absence nobody established. The card prints three verdicts — Deployed, Not found, Not
established — and each one has to be earned separately.

**Dated sources age, and the basis says so.** A 2004 core-conversion release is real evidence
and it is twenty-two years old. State it: `as_of` carries the source's date, and the `basis`
says the reading is uncontradicted rather than current. Never average two disagreeing figures
and never quietly prefer the newer one — where two sources disagree, both go in the basis.

Productive routes: vendor customer-story and press pages (Jack Henry, Fiserv, Corelation, Q2,
Alkami, Lumin, Salesforce, Snowflake, Databricks); the peer's own newsroom; trade press (CU
Times, CUToday, Finopotamus, American Banker); NCUA filings; conference case studies; the
peer's careers postings, where a job description naming a system is often the only public
statement that exists; and app-store listings, whose package identifiers frequently name the
digital banking vendor outright.

**3 · What the product does not cover.** Four hardcoded sentences per branch, identical for
every product and every client, asserting blocked prerequisites and "operating cost stays
elevated — manual workflows persist" that nothing in the run supported. Under a vendor's name it
read as an accusation, and it was not data-backed.

Read `01-start-here/3-language.md` and apply it literally. The framing rule is not politeness:
the reader is often the person who chose the incumbent, and a sentence about what a vendor fails
to do invites a defence of the vendor instead of a conversation about the gap.

- **Available value, not fault.** "The estate does not yet reach the member profile" — not "the
  vendor does not support member profiles".
- **The client's own words** where the assessment has them.
- **A cell, or nothing.** An uncovered area that names no cell is an opinion.

#### Deriving estate reach — two inputs, never a third

This card is the one most likely to be written from feel, because everyone in the room has an
opinion about what a core "can't do". It has exactly two inputs, and a claim that comes from
neither does not go on the page.

**Input 1 — the register's own arithmetic.** The cells in this product's own pillar that the
register does NOT link to it, lowest score first. That set is computed by the surface from
`linked_subcap_ids` and the run's served cells; you do not write it, and you must not contradict
it. If you think the product reaches a cell that list contains, the repair is to add the cell to
`linked_subcap_ids` — with evidence — not to argue with the card underneath.

**Input 2 — the product's own documented capability boundary.** The vendor's statement of what
the product is for. Symitar Episys is a core of record and Jack Henry documents SymXchange as
the separate API third parties use to reach it; Agentforce is an agent platform and Salesforce
documents the unified profile it grounds on as Data Cloud's job. Both are the vendor describing
its own architecture, and both are citable. Register the source and cite it on the row.

Everything else is feel. In particular:

- **Not from the product's age.** "Legacy" is not a capability boundary and a 2003 build's
  detected presence establishes presence, not exposure.
- **Not from the absence of a public case study.** A vendor whose site has no example of the
  thing has not said the product cannot do the thing.
- **Not from the gap you would like to sell.** If the pathway came first and the boundary was
  written to justify it, the boundary is the wrong way round. Find the vendor's scope statement,
  and if it says the product covers the capability, the honest finding is that the estate has
  not configured it — say that instead, and evidence it separately.

### Prompt

For each row of the register you have already produced, write the drilldown.

Start from the row: its product, vendor, layer, status, evidence level, detection basis, its
`linked_subcap_ids` and its `e_ids`. Read the served score and band of each linked cell from the
bundle, and find every recommendation whose own cells intersect this row's.

Then answer, in `dma_impact`, the question a reader asks on arriving: *what does this platform
do for us here, and what does it not reach yet?* Four moves, in order, 40–90 words: the
capability of the deployed product (cited); the cells that reaches; the product's own documented
boundary (cited to the vendor); and the Zennify pathway across it. Write it for **every** row —
a register where a third of the rows explain themselves and the rest are silent reads as a
register the producer got bored of. If a row genuinely cannot be answered from evidence, leave
the field out and say so in the run notes; the page then shows the cells alone, which is the
truth.

Before you write the boundary for any row, go and read the vendor's own scope statement, and
register it as evidence if it is not already in the store. That fetch is the difference between
a boundary and an opinion, and it is usually one page.

Then research the peer set, per the protocol above, for every product significant enough that a
reader would ask "who else runs this?" — the core, the digital channel, the CRM estate, the
integration layer, and every ABSENT row (a peer comparison on an absence is the most valuable
one on the page). Write `peer_deployments[]` with a row per named peer, including the ones you
could not establish, and set `peer_coverage` only where the breakdown supports it.

The detection_basis is not the place for any of this. It is ONE CLAUSE inside 160 characters —
gate **CG-12** enforces it — because it renders as the register row's single muted line under
the product name. Everything you were tempted to append to it belongs in `dma_impact`.

Run `python scripts/check_language.py` before you submit. Every uncovered-area sentence has to
pass it, because that is the sentence a client reads about a vendor they are paying.
