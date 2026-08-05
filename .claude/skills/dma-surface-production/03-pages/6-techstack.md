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

- **Section** `techstack.techstack` — **renders on** D6 (Tech stack)
- **Contract** A sub-page per stack item: detection basis, evidence, the cells it touches and the gap it leaves.

### Prompt

No prompt exists in the design specification for this surface. Produce it from the contract above, the standing clauses and the seven-step form in `04-craft/5-prompt-standard.md`.
