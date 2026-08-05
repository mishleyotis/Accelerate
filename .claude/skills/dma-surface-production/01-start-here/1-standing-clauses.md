# The five standing clauses

These apply to **every section on every page**. They are stated once here rather than
repeated in 34 prompts, because a rule repeated 34 times is a rule that gets edited in 33
places. Audience marking in particular appeared in only 5 of 37 prompts in the source
specification, and the failure direction is a field reaching a client.

---

## 1 · Identity

Every figure, quote, document and source domain is about **this** entity. Assert all five,
per item, every time:

| # | Assert | Catches |
|---|---|---|
| 1 | Legal name matches, suffixes and trading names resolved | A same-named institution in another market |
| 2 | Regulator matches this entity's own | A regulator from another charter type — an instant contradiction |
| 3 | Footprint and jurisdictions are consistent | The fastest contamination check available |
| 4 | Source domain belongs to this entity or a neutral registry | The cheapest check, and the one that catches the most |
| 5 | Order of magnitude agrees with any other figure for the same metric | Two figures differing materially are a contradiction to resolve, not two data points to render |

**On failure:** quarantine the field, emit the reason, escalate. Never substitute a
plausible value and never render a partial identity.

Why this is worth doing per figure rather than per run: one contaminated profile put another
institution's assets, regulator and five-state footprint onto five surfaces simultaneously.
One root cause, five surfaces, every instance catchable by one rule applied at the figure.

---

## 2 · Grain

Any `<label> at N/5` you write must resolve to a served cell within **0.05**.

```
WRONG   "Data Warehouse & Data Lake … at 1.6/5"
        ← the name of a sub-capability with the CATEGORY's mean

RIGHT   subcap_id = P4C1.2.1
        name      = "Data Warehouse & Data Lake"
        score     = 1.6          ← both read from the SAME row
```

Round **once**. Rounding to two decimals and then to one is not the same function as
rounding once, and ties diverge between the two paths.

One line pairing a sub-capability's score with a category's id produced 125 violations
across the corpus. This is the single most common defect in the product.

---

## 3 · Register

A client reads this prose.

| Banned | Why |
|---|---|
| Consultant register — leverage, journey, best-in-class | Says nothing, and signals a template |
| Deficit framing — lacks, fails to | The client is in the room. State what is true, not what is missing about them |
| Raw taxonomy codes in prose | Internal grammar. Humanise the name; codes belong in drilldown provenance |
| Score-predicate openers | A card that opens by restating a score has told the reader nothing new |
| Markdown in a field that renders as text | Only explicitly typed markdown fields are stripped; everything else renders literally |

**The verb is governed by the evidence level.** Writing "uses" on level-three evidence is a
fabrication, not a style choice.

| Level | Basis | Permitted language |
|---|---|---|
| L1 | Vendor named in a T1/T2 source, deployment confirmed | implemented · deployed · uses · powers |
| L2 | Official partnership announcement or case study | partnered with · selected · announced |
| L3 | Two or more independent signals | likely uses · signals suggest · inferred from hiring |
| L4 | A single weak source | may use · potential · unconfirmed |

---

## 4 · Audience

List in `internal_only` every JSON path the customer must not receive.

**Strip for the customer audience:**
rank scores and tier weights · scoring rationale · synthetic provenance · internal codes
(render capability *names* instead) · cross-entity `entity_ids` (stripped for **every**
audience, including internal)

**Withhold entirely from the customer audience:**
capability ceilings · sentiment · thought leadership · the whole Context dashboard · the
whole Health dashboard

**Do NOT mark internal — honesty renders to the client:**
thin-evidence markers · quarantine markers and their reasons · failing safeguard gates

An assessment that states its own weaknesses is more credible than one that appears
complete. Hiding them is how a document gets caught out in the room.

There is no default. A field you do not mark reaches the client, and the frontend cannot
hide a field nobody told it about.

---

## 5 · Citation at the item

**Every item that asserts something carries its own evidence id.** Not the section — the
item. The envelope's `e_ids` is the section's union, and it is not a substitute: a reader
does not drill into a section, they drill into a *card*, a *signal*, a *finding*, a *ceiling
row*, a *register row*. An item with no id of its own renders as "No direct evidence yet"
and is unfalsifiable in the room.

This was measured, not theorised: one promoted run served four why-now signals, five
findings and seventeen ceiling rows with a populated section envelope and **not one
per-item citation**. Every card on the page said *no evidence*. Gate **AG-03** now blocks
that submission, and it reads the requirement from each field's own item schema — if the
contract names `e_ids`, `supporting_e_ids`, `evidence_ids`, `new_evidence_ids`,
`source_e_id` or `e_id` in the item keys, that key must be non-empty on every claim-bearing
item.

**An inference is a claim.** `claim_label: INFERENCE` changes the tier and the permitted
language — it buys no exemption from citing. An inference cites what it was inferred *from*;
that is precisely what makes it an inference rather than an assertion. Same for a ceiling
estimate: the modifiers came from somewhere, and that somewhere has an id.

**Naming a source in prose is not citing it.** "PYMNTS — BCU Data Culture panel" written
into `source_document` is a string; it does not resolve, does not open a drawer, and cannot
be checked. Call `register_evidence` on it and cite the id you get back. If you found the
source well enough to name it, you found it well enough to register it.

Two shapes owe no citation, and only two:

| Shape | Why | What it must carry instead |
|---|---|---|
| A null-valued row | It asserts no figure (derived-or-null) | `value: null` — not a sentinel, not a guess |
| A recorded absence | The absence *is* the finding | `sources_searched[]` / `queries_run[]` — the ladder that established it |

A state that asserts a **find** with an empty id list is neither of those. `WORKED_FOUND`
with `new_evidence_ids: []` is a contradiction — the state says you found something and the
payload says you did not. Fix the pairing: either cite the id or set the state to
`WORKED_ABSENT` with its ladder.
