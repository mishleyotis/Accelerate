# Colour and band conventions

**Short answer: you never send a colour.** Score → band → hex resolves in one module in the
app, and no payload field carries a hex value. But you do need the boundaries and the band
words, because your prose has to agree with what renders — and three inconsistencies in the
current definitions are worth knowing before you write.

## What the resolver actually does

Recovered from the prototype's own source. This is the single resolver; there is no second one.

```js
maturityLabel(s)                     maturityHex(s)
  s == null → (no score)               null → #E5E7EB   grey
  s <  2    → "Activating"             s<2  → #FFCB99   amber
  s <  3    → "Building"               s<3  → #62D7B8   mint
  s <  4    → "Competing"              s<4  → #27BBAF   brand teal
  else      → "Differentiating"        else → #139F94   deep teal
```

**Boundaries are strict less-than, on the raw score, before display rounding.** A score of
exactly 3.0 is Competing, not Building. A score of 2.97 that displays as 3.0 is **Building** —
the band comes from the raw value, the label from the rounded one, and they can disagree at the
boundary. When you write a band word, resolve it from the raw score.

## Three inconsistencies to know about

### 1 · M5 Transformational is unreachable

The resolver has four branches. Anything at or above 4.0 returns "Differentiating". A score of
4.6 does not render as Transformational, even though the maturity scale defines M5 and the
design documents publish a hex for it (#185F60).

**What to do:** use the four reachable band words. Do not write "Transformational" in prose —
it will not match what renders. If a genuine M5 appears in the workbook, say
"Differentiating, at the top of the band" and flag it as a parser observation.

### 2 · The M2 hex disagrees between sources

Prototype resolver: **#62D7B8**. Design documents: **#B0EDD3**. Same band, two colours.

**What to do:** nothing, in the payload — you send no colours. But if you are asked to describe
the palette, the resolver is the source of truth because it is what renders. Flag the
divergence rather than picking silently.

### 3 · Two freshness vocabularies, and they collide on one word

| Vocabulary | Boundaries | Bands |
|---|---|---|
| **Evidence recency** (`evidence.md`) | 12 / 24 / 36 / 48 months | CURRENT · RECENT · DATED · **STALE** · ARCHIVAL · UNVERIFIED |
| **Prototype `freshnessOf`** | 6 / 12 months | Current · Aging · **Stale** |

An item at 14 months is **RECENT** on the evidence ladder and **Stale** in the freshness dot.
Both render, on the same run.

**What to do:** the evidence ladder governs anything you emit — `recency_tag`, tier weighting,
the rank score, the age tracker. The freshness dot is a UI affordance with a tighter threshold.
Never write the word "stale" in prose about an evidence item; say the age and let the band
speak.

## What the payload carries, and what it must not

| Do send | Do not send |
|---|---|
| The raw score, to two decimals | Any hex value |
| The band **word**, where a surface renders one | A CSS class name |
| `recency_tag` from the evidence vocabulary | A freshness dot state |
| `is_thin_evidence` | An outline or border instruction |
| `below_threshold`, `is_primary_gap` — semantic flags | A colour name |

**Thin evidence adds a dashed outline; it does not change the fill.** The fill means maturity
and nothing else. So a thin cell at 3.2 is still brand teal — you mark it thin, and the app
decides how thin looks.

## Where your prose can contradict the colour

Four places, all avoidable:

1. **A band word resolved from the rounded score.** 2.97 displays 3.0 and bands as Building.
   Resolve from the raw value.
2. **A posture chip that disagrees with the composite's band.** LEADING beside a composite that
   bands as Building will read as an error whether or not the peer maths supports it. If the
   peer position genuinely justifies it, say so in the framing sentence.
3. **"Transformational"** — see above.
4. **A pillar described as strong whose cell fills read amber.** Check the fills you are
   describing, not your impression of the pillar.

## The rule

> Describe the number, not the colour. "Data foundation sits at 1.9" is checkable. "Data
> foundation is red" depends on a palette you do not control and cannot see.

Where a surface genuinely renders a band word — the hero ring label, a posture chip — resolve
it through the boundaries above, from the raw score, and let every other reference be numeric.
