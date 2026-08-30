# The storyline challenge — five volleys before the AE sees it

The R-Layer (`1-reasoning.md`) challenges a **claim**. The page thread
(`3-page-narrative.md`) makes six surfaces into one **argument**. This is the step after
both: the run's whole storyline, taken through five adversarial volleys before it is handed
to an AE who will carry it into a room and be pushed back on.

The distinction matters because the failure modes are different. A claim fails by being
wrong. A storyline fails by being **right and useless** — true, cited, grain-locked, and
still something the client already knows, or cannot act on, or will wave away with one
sentence from their incumbent vendor. No gate catches that, because nothing about it is
malformed.

A volley is a challenge and the story's answer. Five of them, each from a different
quarter, because a story that survives one hostile reading has usually just survived the
one you find easiest to imagine.

## The five volleys

Run them in order. Order matters: each one assumes the story has survived the one before,
and volley 5 is worthless if the story has not yet earned the right to be spoken.

### Volley 1 · The client's own executive — "we know this already"

The challenge: read the storyline back as the CDO or CTO whose words are cited in it, and
answer honestly whether it tells them anything they do not already say about themselves in
public.

This volley kills more storylines than the other four together, and it should. A run whose
headline is assembled from the client's own conference talks has restated their position
back to them at consulting rates. The tell is that every sentence in the thread traces to
something the institution published.

The story passes when it can name the thing **the client has not said**: a connection
between two of their own facts they have not drawn together, a consequence of a decision
they announced but did not follow through, a measurement they publish that contradicts
another they publish. Their facts, your argument.

### Volley 2 · The sceptical finance officer — "what does this cost, and against what?"

The challenge: the storyline asks for money. Answer for it.

Not a business case — this product does not price work. What the volley tests is whether
the story has an honest **cost of acting now** and an honest **cost of not acting**, both
grounded, and whether the sequencing survives someone asking why not next year.

The story passes when the timing argument does not rest on urgency language. "The window
is closing" is not an answer; "the merger conversion locks the integration design in this
planning cycle, and afterwards the same work is a migration rather than a design choice"
is. If the only reason to act now is that acting now is good, the story fails this volley
and the honest repair is to drop the urgency, not to sharpen the adjectives.

### Volley 3 · The incumbent vendor — "our platform already does that"

The challenge: hand the storyline to the account team of every vendor already in the
estate and let them answer it.

This is the volley that catches an estate-reach claim built on what the assessment did not
find rather than on what the product does not do. A vendor whose documentation contradicts
your boundary claim will produce that documentation in the meeting, and the story does not
recover from it.

The story passes when each boundary claim cites the **vendor's own scope statement** — the
architecture page, the developer documentation, the product's own description of where it
ends. `6-techstack.md` holds the rule; this volley is where it is tested at storyline
grain. A boundary you cannot source is a boundary you do not assert.

### Volley 4 · The rival on the other shortlist — "this is generic, and it is stale"

The challenge: argue that the storyline would be true of any institution of this size in
this sub-vertical, and that its evidence is old.

Two attacks, both cheap for a rival to make. The first is the second half of the R-Layer's
domain test raised to storyline grain: if the thread survives having the client's name
swapped for a peer's, it is a fact about the sub-vertical. The second is arithmetic — take
the citation set behind the thread's load-bearing sentences and compute its age
distribution. A storyline whose spine rests on evidence over two years old is one press
release away from being obsolete in the room.

The story passes when the swap test breaks it — when replacing the entity's name makes
sentences false — and when the load-bearing citations are dated, recent and independent of
one another. Corroboration from one origin is one source; say so.

### Volley 5 · The AE holding it — "what do I say first, and what do I say when they push?"

The challenge: the AE has thirty seconds of attention and no assessment in front of them.
Ask the storyline for its opening sentence, the question that follows it, and the answer
to the first objection.

This volley tests deliverability rather than truth. A storyline can be correct and still
be unspeakable: too many clauses to say aloud, an opening that needs three definitions
first, a headline that lands as criticism, a next question the client cannot answer without
homework.

The story passes when the opening is one sentence an AE can say from memory, the following
question is one the client can answer from their own knowledge, and the first objection has
a cited answer that does not require re-explaining the assessment.

## Recording it

Volleys are recorded the way the R-Layer is recorded, and for the same reason: a challenge
you did not write down is one you can persuade yourself you ran.

```
storyline_challenge: {
  volleys: [
    { volley: 1..5,
      challenger: "client_executive" | "finance" | "incumbent_vendor" | "rival" | "ae",
      challenge:  the objection, in its own strongest form,
      answer:     the story's response, citing,
      outcome:    "held" | "changed" | "dropped",
      changed:    what the storyline now says that it did not before — required
                  when outcome is "changed" or "dropped" }
  ],
  survived: true | false
}
```

Three rules about the record.

**`outcome: "held"` five times is a finding, not a triumph.** A storyline that survives
every volley unchanged has usually been challenged gently. Re-run volley 1 and volley 4
with a harder version of the objection before believing it.

**`changed` names the difference, not the effort.** "Strengthened the evidence" is not a
record; "the timing claim moved off the leadership transition, which is undated, onto the
merger conversion, which has a filed date" is.

**A failed volley is allowed to reach the AE — annotated.** The alternative is a storyline
that quietly drops its weakest limb and presents the rest as though it were whole. If
volley 3 broke the boundary claim and no vendor scope statement could be found, the story
says so, and the AE knows not to lead with it. `survived: false` with the volleys attached
is a usable answer. A silently narrowed story is not.

## Where this sits in the workflow

After the six pages pass and `check_consistency.py` reconciles them, before `promote_run`.
It reads across pages by construction — the storyline is the thing the six threads add up
to — so it cannot be run per page, and running it before the pages pass wastes the effort
on prose that is about to change.

If a volley changes the storyline, the affected pages are resubmitted and the consistency
check is re-run. Promoted staging rows are retained, so repairing two pages and
re-promoting is cheap; that is exactly the case `05-lifecycle/2-versioning.md` describes.
