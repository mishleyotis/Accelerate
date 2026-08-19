# Antipatterns — nine payloads that passed every gate and were still wrong

Each of these was **promoted**. Every one satisfied the contract, cleared
validation, and was found by a person reading the rendered page. They are
listed here because a gate catches a shape and this file catches an intent:
the gate is named beside each so you can see what now refuses it, and where
no gate can see it, that is said plainly.

---

## 1 · A why-now signal that recaps the assessment's own scores

**Refused by AG-11.**

```
✗ "A five-member same-sub-vertical cohort read on 19 August 2026 sits at
   2.52, 2.70, 2.50 and 2.36 across the four pillars against this run's
   1.60, 1.52, 1.75 and 1.43."
```

Every figure in that sentence is this assessment's own output. Why-now answers
**what changed outside this institution that makes now the moment**; the scores
answer the heatmap's question, over ground the reader has already covered.
A recap does not merely add nothing — it occupies a slot a real signal needed.

```
✓ "Quinte and Logix announced on 9 June 2026 that CaseHUB has been the central
   hub for the institution's fraud investigations for more than a decade."
✓ "Logix reported $9.688 billion of assets to the National Credit Union
   Administration for the June 2026 cycle."
```

**The test:** can you name the date it happened and the source that reported
it? If the answer is "our own scoring", it is not a signal.

---

## 2 · A conversation starter that opens on an accusation

**Refused by AG-12.**

```
✗ "Two things you have told the market do not quite line up."
✗ "What it cannot do is answer a question."
✗ "You do not measure contact-centre deflection."
```

The client reads these. Every gap in this assessment is an opportunity stated
from the wrong end, and stating it from the wrong end costs the conversation
without buying a single fact.

```
✓ "There is money sitting in the gap between two things you have already said
   publicly, and I think it is yours to take."
✓ "Your app does the transactional work well. The next thing it could do is
   answer a question, and that is where your cost sits."
```

The follow-up question is part of the starter. A consultative opening followed
by "why do you not track that?" is still an accusation.

---

## 3 · Two thought-leadership entries citing one document

**Refused by CG-26.**

Two entries carried the same URL: one congressional testimony, quoted twice,
with different quotes, different evidence ids and different alignments. Not
duplicates by any field check. Duplicates to every reader — same link, same
author, same date.

A second quote from a document you have already cited belongs **inside that
entry**, citing both evidence ids. The freed slot belongs to a document the
ladder has not reached.

---

## 4 · An abbreviation on a client surface

**Refused by CG-27.**

Fifty occurrences of `FCU` and forty-eight of `NCUA` reached promoted prose. A
reader outside this industry does not know them; a reader inside it does not
need them shortened. Spell it out on first use in the field; the short form is
fine afterwards.

**The exception is not politeness.** A quote, an excerpt, a source's own title
and a person's stated role are **verbatim**. An excerpt is a byte-for-byte span
of a fetched artefact, and expanding an abbreviation inside one misquotes the
source and breaks the verifier. Measured while fixing this: a tidy-up rewrote a
chief executive's congressional testimony from "greater CFPB scrutiny" to the
full phrase. Never edit a quote.

---

## 5 · An executive dropped because contact enrichment found nothing

**Refused by CG-28 where the section names the seat; otherwise nothing sees it.**

The roster **is** the accountability set. Contact enrichment is a convenience
on top of it. A seat that owns a finding belongs on the page whether or not a
work address came back — dropping it makes the institution look smaller than it
is and hides the owner of the gap you are discussing.

Serve the seat with the fields you have. Let the contact route be the thing
that is absent, on the contact field, not on the person.

Run the contact search for **every** officer the entity names, not only the
ones you expect to resolve. Measured: three seats served, six more returned by
one search — chief information security officer, chief administrative officer,
chief legal officer among them.

---

## 6 · A peer figure computed from a different cohort than the one beside it

**No gate sees this.** Two bases on one surface is invisible to every check.

Fourteen of sixteen categories carried a peer median and two carried none,
because the cohort that produced them was assembled once and never revisited.
Compute every peer figure — pillar, category, cell, focus area — from **one**
cohort, in one pass, and state its size and membership.

A focus area spans several cells and names them: its peer is the mean of those
cells' medians, not a number from somewhere else.

---

## 7 · A field the renderer cannot read

**No gate sees this either, and it is the most expensive one here.**

Four times in one codebase a payload field was present, contract-legal and
**unread**:

| Written | Read as | What the page showed |
|---|---|---|
| `"scale": 5` | only `"0..5"` parsed | five grey rails over five real ratings |
| `prerequisites: ["P4C2.1.1 >= 2.5"]` | only objects | "no readiness gate applies" over nine gates |
| `capped_subcap_ids: [{...}]` | list of ids | `[object Object]`, three times |
| `rollups.detected` | recomputed locally | "0 of 6 detected" over six named products |

No contract gate can see any of them, because the contract is satisfied. The
only defence is to **look at the rendered page** and to write the field in the
shape the renderer already reads — and where you introduce a second legal
shape, say so, because someone has to teach the reader about it.

---

## 8 · A refused payload nobody knows about

**Now surfaced by `list_open_rejections`.**

A submission that fails validation supersedes the passing row for its page and
then sits there. Three refusals in one day were each found by a person reading
a verdict, and one of them stranded 1.36 MB of cell evidence for a day.

**Read `list_open_rejections` first, before choosing a run.** Each row carries
a stable `rejection_id`; submit a refined payload for that page and
`submit_page_payload` tells you which rows it closed. `attempts` past two means
the repair is not landing — change approach rather than repeat.

---

## 9 · An absence explained instead of removed

A field with nothing in it must render **no row**. A label, a dash and a
sentence explaining the absence is worse than silence: it spends the reader's
attention on our bookkeeping.

The exception is a **producer-authored reason** that is real information about
the institution — "a credit union returns its surplus to members, so no revenue
figure exists to state". That renders. A status word — "queued for enrichment",
"held", "pending", "not available" — never does, because it names a workflow
the reader is not party to.

Where a whole column is null by construction, declare it in
`packages/shared/enrichment_register.json` under `absent_columns`. The server
checks the rows and says nothing unless the column really is empty, so the run
that fills it drops the note without anyone editing a file.
