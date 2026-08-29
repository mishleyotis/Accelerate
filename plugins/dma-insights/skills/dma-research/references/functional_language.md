# Functional language — how the research writes so a client can read it

Every narrative field an agent writes (`Why_It_Matters`, `DMA_Impact`,
`Report_Narrative` bodies, the deep-dive sections) ends up in front of the
client. These are the writing requirements. Two of them are ENFORCED by
refusal (`engine/quality.py`: the accusatory lexicon and the ungrounded-
figure check); the rest are the standard the challenge pass and the report
QA judge against.

## 1 · Communicate impact as consequence, not adjective

An impact sentence names **what changes, for whom, by when** — never how
good or bad something is. The test: delete the sentence — does the reader
lose a fact or an opinion?

- ✗ "Their onboarding is significantly behind peers."
- ✓ "Onboarding completes in 9 minutes online but business accounts still
  require a branch visit [E-0142:F1] — the acquisition funnel's first
  drop-off sits on the segment the 2026 growth plan leans on."

Every impact claim traces to a cited figure or a stated absence; the
forward half (what it means for 2026) is the analyst's argument and is
labelled by its claim label, not dressed as a sourced fact.

## 2 · Frame gaps as the opportunity they open

A gap statement has three parts, in order: **the evidence** (what is and
is not there, cited), **what becomes possible** when it is closed, and
**what it builds on** that the client already has. Blame constructions
("failed to", "neglected to", "refuses to") are refused in impact fields —
not as politeness, but because fault-framing is unfalsifiable and
opportunity-framing is testable against the evidence.

- ✗ "The credit union has failed to implement real-time fraud monitoring."
- ✓ "Fraud review runs on a daily batch [E-0201:F2]. Moving to real-time
  scoring would let the existing alerting workflow act inside the
  authorization window — the workflow itself is already in place."

## 3 · Never accusatory, never a verdict on people

Verdict words (woefully, negligent, incompetent, dismal …) are refused in
EVERY field. Findings describe capabilities, artefacts and measurements;
they never characterise the people who built them. The production side
enforces the same rule as gate S2_accusatory — writing it here means the
research prose survives that gate unchanged.

## 4 · Cross-check, and treat disinformation as a tier problem

- Nothing rests on one list's say-so: **RRF (k=60) ranks by consensus
  across differently-shaped probes**, so a claim's source earned its rank
  by appearing wherever the question was asked from several angles. A
  single-list winner that no other probe surfaces stays a lead, not
  evidence.
- The `contradicts` volley runs **before** `corroborates`, so the
  disconfirming source is hunted while it can still change the claim.
- Source tier is the disinformation control: an unattributable or
  promotional source registers at the tier it earns, a claim carried only
  by such sources cannot wear FACT (`claim_label_supported`), and a
  contradiction between tiers is recorded with an OPEN disposition the
  synthesis must argue — never silently resolved toward the friendlier
  source.

## 5 · Every figure has a chain of custody (the hallucination rule)

The pipeline's anti-hallucination stack, and where each layer bites:

1. **RRF + verbatim excerpts** — evidence enters as a 50–500 char verbatim
   span of a consensus-ranked source. Prose cannot mint evidence.
2. **Ungrounded-figure refusal** (`quality.ungrounded_numbers`) — a number
   asserted in any source-claim field (`What_We_Found`, the five DQ
   fields, `Dominant_Claim`, `Triangulation`) that appears in NO excerpt
   registered to the subcap is refused BY NAME. The repair is to cite the
   source that states it or remove the figure — there is no third option.
3. **Citation resolution** — every `[E-xxx]` must resolve in
   Evidence_Detail; a dead citation refuses the report render (AUD-0033),
   and the app-side `get_evidence` returns `foreign` and halts on an id
   from another run (invariant 4).
4. **Curated-at-render figures** — report numbers are read from the
   workbook sheets at render time (AUD-0052), so a report cannot disagree
   with the workbook it summarises.
5. **The independent challenge** — a different actor falsifies the
   synthesis on all seven dimensions before the category closes.

## 6 · Sentences that survive the challenge

Write so the challenger has something to bite on: one claim per sentence,
the citation inside the sentence that needs it, the claim label doing real
work (an INFERENCE reads as one), and absences stated with their ladder
("no X found across A, B, C" — never "they don't have X"). Hedge words
without a stated reason ("likely", "presumably") are what
`is_fluent_but_empty` exists to catch — either give the basis or downgrade
the label.
