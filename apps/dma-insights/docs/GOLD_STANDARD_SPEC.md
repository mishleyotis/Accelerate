# What "gold standard" actually means — derived from the Claude overlays

Not "no misattribution" (that is only the *floor*). Reading the committed
overlays verbatim (FCMA, Regions, Alliant, Capital Farm, Greenstone), gold =
**six behaviors**, each with a real example. This is the target contract for the
generative synthesis AND the deep countercheck criteria.

## The six deep behaviors

**1. Thesis-first synthesis (not quote-splice).** Every finding/card leads with a
client-specific key message, then the grounding fact.
> *gold (Regions P1C4):* "Consumer Customer-360 gap — Salesforce Data Cloud
> greenfield. RCLIQ gives commercial bankers a functional Customer 360 (350+ data
> elements, 100% adoption) but there is no consumer equivalent…"
> *script today:* "At December 31 2024, Regions had total consolidated assets of
> ~$157.3B…" (a balance-sheet fact dumped under "CRM Integration").

**2. Cross-pillar / cross-LOB synthesis.** One insight fuses several evidence
points from different pillars/LOBs/systems.
> *gold (Regions):* connects a capability (Customer 360) + an LOB split
> (commercial vs consumer) + a revenue fact (Consumer = 58.8% of net interest
> income, 4M+ customers) + the platforms (July-2025 mobile app, Temenos core,
> Salesforce FSC). Scripts treat each subcap in isolation.

**3. Competitive/strategic, time-bound so-what.** The implication names the play,
the systems, and the urgency.
> *gold (FCMA):* "Vendor Gen-AI is already live in operations and lending;
> Salesforce must prove Agentforce/Einstein parity in the customer- and
> lending-facing moments **before the nCino/ServiceNow footprint hardens**."
> Scripts emit "Make X a near-term focus… lift it from 2.0 toward 4/5."

**4. A storyline threaded across surfaces.** FCMA's three insight cards form one
argument: (a) Zennify Salesforce is a live reference account (33× engagement,
385% ROI) → (b) ServiceNow Now Assist is a Gen-AI beachhead (CSO Tiffany Smith
validated) → (c) nCino Banking Advisor owns the lending moment → **defend/expand
the Salesforce layer against nCino/ServiceNow**. Scripts produce independent
cards with no throughline.

**5. Evidence CHALLENGED; contradictions RESOLVED before surfacing.** The clearest
example is Regions' issue register: instead of flagging "CFPB consent order" as a
risk, gold resolves it —
> "CFPB Consent Order 2022-CFPB-0008 was **terminated** July 21 2025 ($50M
> penalty + $141M redress paid, Bureau waived non-compliance) → Regions now
> carries a **clean** regulatory record"; each other penalty scoped precisely
> ("applies only to broker-dealer subsidiary Regions Securities LLC; the banking
> entity is unaffected"). Raw negatives are challenged, reconciled to the current
> true state, and scoped — not surfaced raw.

**6. Per-claim source verification + precision.** Every figure/name/date is
traced to a verbatim source. The overlays carry a `_verification` map:
> `financial_trajectory.series → {source: "04_reports/DMA_Client_Profile…docx
> (Section 2.2 Scale Metrics)", quote: "2020 $0.991B $155.2B … 2024 …"}`;
> `net_income[FY2024] → {source: "evidence_index.json (E-002,F1)", quote: "FY2024
> net income available to common shareholders of $1.8 billion, diluted EPS
> $1.93"}`. Exact numbers, named systems (Temenos, RCLIQ, Banking Advisor),
> dockets, dates — never approximations.

## Why this reframes the build (the honest correction)

- The **deterministic scripts** (clusters A–D + the semantic/knowledge layer) get
  the **data floor** right: correct financials, real sentiment, aligned evidence,
  no fabrication, no misattribution. Necessary, **not** gold.
- Behaviors 1–5 are **generative reasoning over a rich shared knowledge state** —
  they cannot be templated. This is precisely the **non-deterministic** system:
  Vertex composes each surface as a thesis/storyline from the L1 EntityKnowledge,
  L2 challenges every claim (topical support + ownership + contradiction
  resolution), a validator enforces behavior 6 (every claim → a verbatim in-corpus
  quote, fail-closed), and the result is **persisted** (stable pack, zero
  tokens/reload). The deterministic composer is the grounded fallback.

## The knowledge state the generative layer needs (L1, enriched)

To produce behaviors 1–5 the shared `EntityKnowledge` must hold, per entity:
capabilities (scored, peer-deltas, cross-pillar), the embedded evidence corpus,
**current platforms + competitors' footholds** (Salesforce/nCino/ServiceNow/…),
**buying signals** (hiring, RFPs, stated priorities, SI relationships),
financials (LOB-split), leadership (with seat status), regulatory events (with
resolution state), and the **contradiction set** (resolved). Every composer reads
this one state — a fact in one card is retrievable by any other (cohesion, no
silos).

## Deep countercheck (upgrades the mechanical one)

Per surface, score against the six behaviors, benchmarked to the overlays:
- thesis-first (lead sentence is a client-specific message, not a fact dump);
- cross-pillar linkage (≥2 distinct evidence sources / pillars fused);
- so-what is strategic + names a play + is time-bound;
- storyline coherence (cards share a throughline; consistent labels);
- contradiction-resolution (no raw negative that the corpus later resolves);
- per-claim verification (every figure/name/date → a verbatim corpus quote).
Defects (misattribution/dumps/oos/pipe-quotes) remain as the floor gate. Ship
only when the deterministic tier clears the floor AND the generative tier meets
the six behaviors across all 94.
