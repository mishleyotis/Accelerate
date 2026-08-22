# The reasoning layer

Every gate in this system checks a claim **after** you have written it. The reasoning layer is
what you do **before** — and it is the only mechanism that catches a claim that is
well-formed, correctly cited, grain-locked and wrong.

The P1 platform prompt calls its version "the R-Layer, and it is the point of this page."
That is right, and it is not specific to P1. Any surface making a ranked, causal or
comparative claim runs the same five steps.

## The five steps

```
A  HYPOTHESIS        State the claim and its confidence, before defending it.
B  COUNTER-EVIDENCE  Argue the strongest case against it. Where the margin is thin,
                     present both and say the call is close.
C  DOMAIN TEST       Is this plausible for THIS sub-vertical, size tier and regulator —
                     and is it about this ENTITY rather than about its cohort?
D  FAILURE PROBES    Run the probe set for this surface. Each probe fires a search.
E  VERDICT           ACCEPT · REJECT · UNCERTAIN. Reject means re-rank or drop,
                     not soften.
```

**Write the verdict down.** Every surface making a ranked or causal claim carries
`r_layer: {hypothesis, counter, domain_test, probes_run[], verdict, confidence}`. A verdict
you did not record is a step you can convince yourself you took.

## Step B is the one that gets skipped

Arguing against your own conclusion feels like undermining the work. It is the opposite: a
claim that survives its strongest counter-argument is one you can defend in the room, and a
claim that does not survive was going to fail there instead.

The form that works, from a completed assessment:

> **The steelman:** these are low-risk personal productivity artefacts and inventorying them
> is overhead. **The falsifier** is the bank's own risk framing — shadow AI *"going rogue on
> you and you don't know what it's doing"*, unchallenged in the room. The steelman holds for
> a static estate and fails for one growing weekly.

Three things at once: it proves the objection was considered, it sources the falsifier from
**the client's own words** rather than your judgement, and it bounds the claim honestly
instead of overclaiming.

## Step C has two halves, and the second one appears on the second client

The first half is the familiar one: a claim has to be plausible for this sub-vertical, this
size tier and this regulator. A transformation office is an expectation at one scale and
not at another; a channel a charter does not permit is not a gap.

The second half only bites once you have produced more than one client in the same
sub-vertical, and then it bites hard, because the sub-vertical supplies most of the
vocabulary and the second run writes itself:

> **Would this sentence be true of any institution in this sub-vertical?**

If yes, it is a fact about the sub-vertical — or about a shared vendor — and it is not a
finding about this client. Two honest moves, and softening it is neither: attach the
entity-specific evidence that makes it particular (this institution's own figure, its own
executive's words, its own dated event), or move it to where cohort facts belong. H8 exists
for exactly this, and its own challenge step says the same thing from the portfolio side —
where every entity runs the same core, a shared weakness is a finding about the vendor and
that is the more useful finding.

The test costs one question per claim and it is the difference between a repeatable process
and a template with a name on it. Run it hardest on the surfaces that carry the argument:
the exec summary's complication, the top findings, the act-now cards and the platform
story.

## Probe sets, by surface

Each probe fires a search. A probe you did not run is not a probe.

| Surface | Probes |
|---|---|
| **O1 hero** | Does the composite equal the mean of the four pillar means? Does the posture survive the peer basis actually available? Does the framing sentence name the same constraint as the top finding? |
| **O6 findings** | Is the rank order strategic alignment or gap width in disguise? Does each finding have a rejected alternative that is genuinely plausible? Do the five form a thread? |
| **O1b ceilings** | Is the ceiling set by evidence absence or by low performance? Those are different findings and only one is a ceiling. |
| **I1 insights** | Does each act-now card have a dated trigger? Is any plan-next card blocked by something that is not itself a card? |
| **H2 cell evidence** | Does every excerpt speak to the capability, or merely to its category? Is any cell's whole drawer empty — a linking failure, not a gap? |
| **H4 grid** | Does any quoted figure resolve to a different grain than the id beside it? |
| **P1 platform** | Out-of-vertical rank 1. Anchor-cell entity-type mismatch. Tech Stack Mismatch. A fit figure computed against a superseded run. Breakdown not equal to headline. A gap row whose score disagrees with the heatmap. |
| **P2 recommendations** | Does the client already own this? Does provenance say derived where the card reads as analyst judgement? |
| **C3 regulatory** | Is regulatory silence being read as evidence of control effectiveness? It is not. |
| **T1 stack** | Is any entry a service or a category rather than a product? Does any status exceed what the evidence level licenses? |

Four probes fire on **every** surface once the entity's shape is established, because each
of them produced a confidently wrong card rather than a thin one:

| Probe | Fires when |
|---|---|
| **Foreign variant cell** | A cited cell's id ends in a sub-vertical code that is not this entity's — it resolves in the workbook and renders nowhere |
| **Cohort scale** | The peer median's cohort is not within the entity's own size class, so every delta arrow is confident and unsupported |
| **Shape-blind ladder** | An absence was recorded from a ladder whose rungs presume a filer this entity is not |
| **Cohort sentence** | The claim would be true of any institution in this sub-vertical (above) |

## Contradiction classes

These are the inconsistencies worth hunting, because each has been observed and each renders
plausibly.

| Class | Looks like | Where to catch it |
|---|---|---|
| **Grain** | A figure quoted under a name from a different row | Grain lock, per quoted figure |
| **Magnitude** | Two figures for one metric differing by more than a quarter | Identity gate, assertion 5 |
| **Cross-surface** | Hero says one constraint, findings say another | The seven reconciliation pairs |
| **Source rank** | The workbook and the report disagree and the report won | Source priority — the workbook wins on scores |
| **Self-description** | The entity's claim contradicts a registry | Registry wins. The contradiction is itself a finding |
| **Arithmetic vs analyst** | The engine ranks a platform the report never discusses | State the disagreement, say which won, lower confidence |
| **Temporal** | The timeline shows a platform live; the register shows the programme stalled | Either one is wrong, or the relationship is the finding |
| **Confidence** | A cell scored HIGH on two evidence items | Confidence must be earned by the evidence count |
| **Vocabulary** | The same word carrying two meanings on one screen | Check the band word against the served score, not against your prose |

## Cross-checking a fact

A fact appearing twice is an opportunity, not a redundancy.

```
1  Find every place the fact appears — package, report, enrichment, prior run.
2  Do they agree?
     YES, from independent ORIGINS      -> corroborated. Raise the rank score.
     YES, from the same origin          -> ONE source. An annual report and an
                                          investor deck are not two.
     NO, and one source outranks        -> higher priority wins; record the
                                          disagreement as a parser observation.
     NO, and they are peers             -> a CONTRADICTION. Do not average and
                                          do not pick. Quarantine and state it.
3  Never resolve a disagreement silently. The resolution is the finding.
```

**Averaging two disagreeing figures produces a number that is in no source.** That is
fabrication with extra steps.

## What the reasoning layer is not

- **Not hedging.** "May potentially indicate" is not epistemic care; it is an unfalsifiable
  sentence. State the claim, state its confidence, name what would refute it.
- **Not a disclaimer.** A caveat at the end does not license an overclaim at the start.
- **Not optional on strong claims.** The stronger the claim, the more the counter-argument
  earns. A weak claim nobody would challenge does not need a steelman; a rank-1 platform
  recommendation does.

## When the verdict is UNCERTAIN

Uncertain is a legitimate outcome and it renders. Emit the claim with its confidence lowered,
the counter-argument beside it, and what would settle it — the same shape as a limiting
absence, because that is what it is. An uncertain claim stated as uncertain is worth more than
a confident claim that is wrong, and both cost the same to produce.
