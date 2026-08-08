# Answered questions

An AE opens the intelligence panel mid-call and types a question. Nothing in
the application can write them an answer — it performs no inference at request
time, and it never will, because the moment it does, prose nobody reviewed
appears under a client's name.

So the answer has to already exist. You are the only component that reasons,
which makes you the only component that can write one. This is the surface
where that matters most: an answer is the text most likely to be copied out of
the page and pasted into an email with none of the page around it.

## What the app does without you, and why that is not enough

The panel already answers every question below by SELECTION — it finds the
promoted field that bears on the question and quotes it verbatim with its
citations, and where no question matches it ranks the run's own passages and
shows the best of them under "here is what this run states about that". That
is honest and it is instant, and it means a run that promotes no answers is
not a broken panel.

It is also a quotation, not an answer. Selection can hand back the executive
summary's three paragraphs; it cannot say *what this means for this
conversation*, because saying that is writing a sentence, and writing a
sentence at request time is the thing that is forbidden. An answer you write
during synthesis is the only version of that sentence anyone will ever get.

## The questions

One answer per row, per run. The panel groups them by the surface it is open
on, so an answer filed under the wrong surface is an answer nobody sees.

| Surface | Question |
|---|---|
| `entity` | What is the 30-second version of this assessment? |
| `entity` | What does the run say the overall posture is, and on what basis? |
| `entity` | What does this cost if nothing changes? |
| `entity` | What are the top findings this run stands behind? |
| `entity` | Where is the largest opportunity, and why there? |
| `why_now` | What changed recently, and what closes the window? |
| `why_now` | Why does the sequence have to start now? |
| `why_now` | What happens to this account without intervention? |
| `platform_story` | What is the case for this platform? |
| `platform_story` | What gaps does it close, and against which peers? |
| `platform_story` | What has to be true before this lands? |
| `focus_area` | Why is this a focus area? |
| `focus_area` | Which capabilities sit under it, and what is holding them down? |
| `subcap_narrative` | What does the run state about this cell? |
| `subcap_narrative` | What pulled this score down? |

The list is not yours to extend on a whim: `apps/api/dma_api/answers.py`
carries it and the panel carries a copy, and a test fails when the two ask
different things. A question worth adding is worth adding in all three.

The scoped surfaces — `platform_story`, `focus_area`, `subcap_narrative` — take
one answer PER THING. One "why is this a focus area?" for each focus area, each
carrying that area's `fa_id`; one "what does the run state about this cell?" per
cell you wrote a synthesis for. An answer about a different cell than the one
open is not a weaker answer, it is a wrong one, and the panel would rather show
nothing.

## The budget

**40–110 words.** Below forty it is a label and the reader opens the page
anyway; above a hundred and ten it is the page, and the panel is not a second
copy of the page. Two or three sentences, spoken register — this is text an AE
reads aloud on a call, so the say-it-aloud test from the conversation-starter
standard applies here too: no cell ids mid-sentence, no bracketed evidence ids
inside a clause, no score-first opening. Put the id at the end.

## Every answer is cited

From REGISTERED evidence, by the ids `register_evidence` gave you — the same
ids the rest of the payload uses, resolving to the same excerpts. The database
refuses an answer with an empty citation list: the row's own check constraint
says an answer carries evidence or it is not an answer.

This is stricter than it looks, and deliberately. Everything else on a page has
the page around it — a card sits beside its cell, a recommendation beside its
gap. An answer travels alone. Whatever it asserts, it asserts with nothing
nearby to check it against except the ids you attached.

An answer that would need a claim you cannot cite is not an answer to trim
until it fits the evidence. Rewrite it around what you CAN cite, or record the
absence.

## An answer you cannot ground is written as an absence

Not skipped, and never composed around the gap.

Skipping is worse than it sounds. The panel lists the questions this run can
answer; a question that promoted no row is simply absent from the list, and the
reader never learns that it was asked and could not be answered. An absence
row, by contrast, renders — the question is shown, and under it the reason.

```
answer_md        null
absence_reason   "The run has no dated evidence for the merger's
                  integration timetable; two searches of the credit
                  union's own filings and the NCUA merger notices
                  returned the approval and not the plan."
```

The reason follows the absence protocol (`01-start-here/4-absence-protocol.md`):
what you looked for, where you looked, what would close it. "No evidence
available" is not a reason, it is a shrug — and a shrug in an answer field is
the one thing here worse than saying nothing at all.

The composed alternative is the failure this whole discipline exists to
prevent: an answer assembled from three fields that individually cite well and
together assert a fourth thing nobody wrote. If the run cannot ground the
answer, the run cannot ground the answer.

## Where they go

`serving_answers` (migration 0026), written by the connector inside the promote
transaction with everything else — all six pages or none. Each row carries the
surface, the scope id where the question is scoped, the question, the answer,
the citations, and where on the six pages the reader can go to see the same
thing in context. Mark an answer `internal_only` when it reasons about the
account rather than about the institution: the customer audience reads this
panel too, and default-deny only protects what is marked.
