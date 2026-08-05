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

What the page now has without you: the cells in `linked_subcap_ids`, each at its served score
and band, and the recommendations touching the same cells. What it does not have, and only you
can supply, is **why those cells and not others** — which is what `dma_impact` is for.

Write 40–90 words that a reader can check:

- Name the cells, or the capability they share. "P4C3.1.2 and P4C3.1.4" or "the two integration
  cells", not "several data capabilities".
- Say what the product **reaches** and what it **does not**. A core banking platform of record
  reaching the ledger and not the member profile is the whole point of the row.
- Give the **mechanism**, not the correlation. "Episys holds the member record, so any unified
  profile has to read from it" explains; "Episys constrains P4C1" asserts.
- Cite. Usually the same `e_ids` as the row's detection basis; add one if the impact rests on a
  different source.

Three things not to do, each of which the old card did:

- **Never derive a score** and never project one. Scores come from the workbook (rule 1), and no
  source states a post-investment target, so there is no target to state.
- **Never restate what is already served.** The scores are on the page; repeating them as prose
  spends your budget saying nothing.
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
the card then names the peer set it would have searched, which is honest, and a fabricated share
is not.

Productive routes: vendor customer-story and press pages (Jack Henry, Fiserv, Corelation, Q2,
Alkami, Lumin, Salesforce, Snowflake, Databricks); the peer's own newsroom; trade press (CU
Times, CUToday, Finopotamus, American Banker); NCUA filings; conference case studies; and the
peer's careers postings, where a job description naming a system is often the only public
statement that exists.

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

### Prompt

For each row of the register you have already produced, write the drilldown.

Start from the row: its product, vendor, layer, status, evidence level, detection basis, its
`linked_subcap_ids` and its `e_ids`. Read the served score and band of each linked cell from the
bundle, and find every recommendation whose own cells intersect this row's.

Then answer, in `dma_impact`, the question a reader asks on arriving: *what does this product
have to do with the assessment?* Name the cells, say what the product reaches and what it does
not, give the mechanism, cite it. 40–90 words. If you cannot answer it from the evidence, leave
the field out — the page shows the cells alone, which is the truth.

Then research `peer_coverage` against the run's named peer set, per the rules above, and write
`peer_deployments[]` with a row per peer including the ones you could not establish.

Run `python scripts/check_language.py` before you submit. Every uncovered-area sentence has to
pass it, because that is the sentence a client reads about a vendor they are paying.
