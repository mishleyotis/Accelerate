# Page cohesion

A page is not a container for surfaces. An AE reads it top to bottom in about ninety seconds
and takes one argument away from it. If the surfaces are individually correct and collectively
incoherent, the page has failed even though every gate passed.

## The rule

> **Before submitting a page, write its thread in one or two sentences. If you cannot, the
> surfaces are not yet a page.**

Each page payload carries a `narrative_thread` on its lead section — 45–75 words tracing the
line through the surfaces in the order they render. It is the last thing you write and the
first thing that tells you whether the page works.

## The thread each page must carry

### D1 Overview — *what is true, and what do I lead with*

The hero states the position. Why-now says the clock. The executive summary is the argument in
four moves. Opportunity and findings say where the value is. Leadership, financials and
sentiment say who and what context. Coverage, tier distribution and ceilings say how much of
the above to trust.

**Test:** the framing sentence in the hero and the top finding must be about the same thing.
If the hero says the gap is concentrated in data foundation and the first finding is about
channel experience, the reader does not know what the meeting is about.

### D2 Insights — *the argument, in priority order*

Act-now cards share a trigger and a clock. Plan-next cards are blocked by something that is
itself a card. Watch cards are honest about being early. The technology landscape says what
the estate can support.

**Test:** the act-now set must read as one story — the root constraint, then what it blocks,
then where the leverage is. If they are three unrelated observations, they are not triaged.

### D3 Heatmap — *where the capability actually sits*

Focus areas say what the client says matters. The grid says what the evidence scores. The
value chain says where it sits in how they operate. Cell evidence says why each number is
what it is.

**Test:** the focus areas and the weakest grid cells must be reconcilable. Where they diverge,
that divergence is itself the finding — the client's stated priorities and the assessed
capability disagree — and it should be stated, not left for the reader to notice.

### D4 Platform — *what to do, in what order, and why not sooner*

Fit says where the opportunity is. Readiness says what has to be true first. Recommendations
say what to do. The roadmap sequences them. The stair-step shows the climb. Starters say it
out loud.

**Test:** every roadmap phase traces to a recommendation, every recommendation traces to a
gap on the heatmap, and every starter is about one of them. A starter about something the page
does not otherwise mention has come from nowhere.

### D5 Context — *how they got here*

The timeline is the trajectory. The issue register is what is live. Regulatory standing is the
constraint. Sentiment is the outside view. Acquisitions explain discontinuities. The financial
series is the capacity.

**Test:** the timeline and the issue register must not contradict. If the timeline shows a
platform going live and the register shows the programme stalled, one of them is wrong or the
relationship between them is the finding.

### D6 Tech stack — *what they run, and what the shape of it says*

Four layers with pillar tags and detection counts. The summary line names the primary gap
layer.

**Test:** the gap layer must correspond to the weakest pillar on the heatmap. Two of four
detected at the data layer with a data-pillar tag, next to a strong data pillar score, means
one of the two is wrong.

### D7 Health — *how much of this to believe*

Alerts say where the evidence is thin. Gates say what constrained the assessment. The age
tracker says how current it is. Cohort patterns say whether this is idiosyncratic or
structural. Version diff says what moved.

**Test:** the thin-evidence cells and the low-confidence scores must be the same cells. If a
cell is scored with high confidence on two evidence items, the confidence is unearned.

## Cross-page threads

Three arguments run across pages and must not fracture:

| Thread | Runs through | Fractures when |
|---|---|---|
| **The primary constraint** | Hero framing → top finding → act-now insight → platform readiness → roadmap phase 1 | Each page names a different constraint |
| **The clock** | Why-now → act-now triage → roadmap horizon → cost of waiting | One page says urgent and another sequences it third |
| **The confidence** | Coverage → tier distribution → ceilings → thin alerts → gate results | The Overview reads confident and Health reads thin |

## How to write the thread

Write it last, from the surfaces you actually produced — not first, from what you intended.
A thread written in advance describes the page you meant to make.

```
narrative_thread (45-75 words)

  1  Name the single constraint the page is about.
  2  Say what it blocks, concretely.
  3  Say where the leverage is.
  4  Say what makes it timely.

If you cannot write it because the surfaces do not line up, the surfaces are the problem.
Fix them; do not write a thread that papers over them.
```

**A page that does not cohere is more expensive than a page with a thin card on it.** The thin
card costs one surface; the incoherent page costs the AE the argument.
