# Narrative Anti-Patterns: The 5 Traps of Technically Correct But Emotionally Flat Decks

## Overview

A deck can be factually sound, data-rich, and visually correct while still failing to persuade, engage, or mobilize. The five anti-patterns below are the most common causes of this failure. They describe not what's wrong with the design, but what's wrong with the story.

---

## TRAP 1: Insight Without Stakes

### Description
You've surfaced a genuine insight — a true, important finding buried in the data. But you haven't connected it to WHY it matters. The reader sees the insight and thinks "OK, so what?" rather than "Oh, we need to act."

### How It Manifests
- A chart clearly showing performance is below target, with no explanation of business impact
- A trend line with a label ("Q3 churn up 8%") but no context ("At this rate, we lose $2M revenue annually")
- An interesting anomaly ("Average deal cycle extended by 18 days") presented in isolation
- A competitor analysis showing market share loss without connecting to customer impact

### Detection Method
Read the slide's headline and main data point. Ask yourself:
- "If this is true, what happens next?"
- "Why would a decision-maker care about this number?"
- "What's the business consequence?"

If you can't answer these questions, the slide has Insight Without Stakes.

**Automated check**: Search the slide text for:
- Numbers without context (percentages, indices, deltas without explanation)
- Passive voice ("Performance declined") without active consequence ("Revenue at risk")
- Absence of phrases like "means," "results in," "implies," "prevents," "enables"

### Weak Example
```
SLIDE HEADLINE: "Customer Acquisition Cost Trends"
CHART: Line showing CAC rising from $450 to $620 over 12 months
BODY TEXT: "CAC increased 38% year-over-year."
```

Why it's weak: True data, but no stakes. Reader doesn't know: Is this bad? Compared to what? What's the implication?

### Strong Example
```
SLIDE HEADLINE: "Rising Acquisition Cost Erodes Unit Economics"
CHART: Line showing CAC rising from $450 to $620 alongside LTV holding steady at $3,200
BODY TEXT: "CAC up 38% YoY while lifetime value flat. LTV:CAC ratio dropped from 7.1x to 5.2x,
now below our 6x minimum profitability threshold. Without intervention, we'll be unprofitable
on new customer cohorts by Q3 2026."
```

Why it's strong: Data + consequence = stakes. Reader understands the business problem and urgency.

### How to Fix
1. **Identify the business consequence** of the insight:
   - Financial impact: revenue, cost, profitability, cash flow
   - Operational impact: cycle time, capacity, risk, dependency
   - Strategic impact: market position, competitive advantage, customer relationship
2. **Add a stakes statement** to the body text or callout box that directly connects insight to consequence
3. **Use "if this continues" framing** to project the trajectory:
   - "At current rates, we'll reach [crisis point] by [date]"
   - "This puts us [X] behind our [target/competitor/benchmark]"
4. **Quantify stakes when possible**: "This translates to $2M in annual revenue risk"
5. **Test the headline**: Does it tell the reader "what this means" not just "what we found"?

---

## TRAP 2: All Evidence, No Tension

### Description
You've assembled every proof point, every supporting chart, every data layer that backs up your central claim. The deck is airtight. But there's no narrative tension — no moment where the reader thinks "Wait, that's not obvious" or "How do we overcome that?" The story feels like a victory lap, not a quest.

### How It Manifests
- A sequence of slides all pointing in the same direction ("This is good, this is better, this is best")
- Absence of any counterargument, caveat, or competing perspective
- Evidence presented in ascending order of obviousness (weakest point first, strongest last)
- No slide that says "But there's a problem" or "Here's why this is hard"
- Every point is favorable to the conclusion; nothing complicates it

### Detection Method
Read through the deck's body slides (excluding intro/conclusion). Count:
- **Complication slides**: slides that introduce a problem, barrier, trade-off, or counterargument
- **Evidence slides**: slides that prove the main point

If complication slides = 0, you have All Evidence, No Tension.

**Automated check**: Search for language that indicates tension:
- Problem words: "risk," "barrier," "challenge," "gap," "constraint," "trade-off," "but," "however," "despite"
- If these words appear in fewer than 20% of body slides, tension is low

### Weak Example
```
DECK STRUCTURE:
- Slide 3: Market opportunity is huge ($5B TAM)
- Slide 4: Our solution addresses the core need (strong product-market fit)
- Slide 5: Early traction shows strong demand (20 pilots, 8 converting)
- Slide 6: Team has domain expertise (10+ years B2B SaaS)
- Slide 7: Why we'll win (3 competitive advantages)
- Slide 8: Revenue projections ($5M by Year 3)
```

Why it's weak: Every slide says "this is good." There's no "but what about...?" The reader never encounters a moment of doubt that makes the resolution meaningful.

### Strong Example
```
DECK STRUCTURE:
- Slide 3: Market opportunity is huge ($5B TAM)
- Slide 4: Our solution addresses the core need (strong product-market fit)
- Slide 5: Early traction shows strong demand (20 pilots, 8 converting)
- **Slide 6: The execution challenge: Sales cycle is 9-12 months, requiring premium support (high CAC)**
- Slide 7: How we overcome this: Hybrid sales model + strategic partnerships (CAC reduction 40%)
- Slide 8: Team has domain expertise + execution track record (mitigates risk)
- Slide 9: Why we'll win (3 competitive advantages, 2 mitigated risks)
- Slide 10: Revenue projections ($5M by Year 3, with sensitivity to churn/CAC)
```

Why it's strong: Slide 6 introduces real tension (high CAC is a problem). Slide 7 resolves it (partnerships lower CAC). The journey feels earned, not inevitable.

### How to Fix
1. **Identify the real barrier** to your main conclusion:
   - Is there a counterargument? (e.g., "Market is crowded")
   - Is there a constraint? (e.g., "Sales cycle too long")
   - Is there a trade-off? (e.g., "Lower margin to gain share")
   - Is there an assumption risk? (e.g., "Assumes customer adoption velocity")
2. **Add a "complication" slide** that puts this barrier on screen. Don't minimize it; name it directly.
3. **Follow with a "resolution" slide** that explains how you overcome the barrier. This is more compelling than "Here's why we'll win" — it's "Here's why we'll win DESPITE this challenge."
4. **Reorder evidence to create narrative flow**: Problem → Evidence that the problem is real → Solution → Evidence solution works → Conclusion
5. **Use headers and sequencing** to make tension visible:
   - "The Opportunity" (Slide 3)
   - "The Challenge" (Slide 6) ← Tension introduced
   - "How We Overcome It" (Slide 7-8) ← Tension resolved

---

## TRAP 3: Solution Without Urgency

### Description
You've convinced the reader that your recommendation is correct. The logic is sound. But there's no sense that action is needed NOW. The reader nods and thinks "Yes, we should do this... eventually." Meanwhile, weeks pass and nothing happens.

### How It Manifests
- The recommendation is presented without a timeline ("We should invest in X")
- No explanation of what happens if we DON'T act ("If we delay, Y becomes irreversible")
- Absence of urgency language: "immediately," "by Q2," "before the market shifts," "while competitors are sleeping"
- No slide showing the cost of delay or the window of opportunity
- The closing doesn't say "Here's what we do next week"

### Detection Method
Find the slide where your main recommendation is stated. Then ask:
- "Does this slide say WHEN we need to act?"
- "Does this slide say WHAT HAPPENS if we don't act?"
- "Does this slide tell me the decision needed BY when?"

If you answer "no" to any of these, the slide has Solution Without Urgency.

**Automated check**: Search the recommendation slide(s) for time-specific language:
- Explicit deadlines: "by Q2," "before March," "in the next 60 days"
- Consequence of delay: "if we wait," "by then," "the window closes," "competitors will"
- Decision points: "decide by," "approve by," "start by"

If none of these appear, urgency is missing.

### Weak Example
```
SLIDE HEADLINE: "Recommendation: Pivot to Enterprise Segment"
BODY TEXT:
- Enterprise segment shows 3x better unit economics
- 60% of target customers express strong interest
- Our product roadmap aligns with enterprise needs
- We have capacity to support this shift

NEXT STEPS: [missing]
```

Why it's weak: Logical recommendation, but no sense of time. Reader thinks "Interesting, maybe we should explore this."

### Strong Example
```
SLIDE HEADLINE: "Recommendation: Pivot to Enterprise by Q2 2026"
BODY TEXT:
- Enterprise segment shows 3x better unit economics
- 60% of target customers express strong interest in H1 2026 buying window
- Our product roadmap aligns with enterprise needs
- We have capacity to support this shift

COST OF DELAY:
- 3 competitors are targeting same enterprise segment
- Typical H1 sales cycles commit budget by Feb/Mar
- If we wait until Q3, we miss the peak buying window
- Projected revenue impact of 6-month delay: $1.2M

DECISION NEEDED: By Jan 31, 2026
ACTIONS STARTING: Week of Feb 3
```

Why it's strong: Recommendation is time-bound. Consequence of delay is quantified. Decision deadline is explicit.

### How to Fix
1. **Identify the window of opportunity**:
   - Is there a market window? (e.g., "Peak buying season is Q1")
   - Is there a competitive window? (e.g., "Competitors are 6 months behind")
   - Is there a technical window? (e.g., "We need 8 weeks to build before customer deadline")
   - Is there a regulatory/strategic window? (e.g., "New regulation effective June 1")
2. **Calculate the cost of delay** in business terms:
   - "If we delay until Q3, we miss [X] revenue opportunity"
   - "Waiting 6 months means competitors ship first, costs us [Y% market share]"
   - "Each week of delay costs [Z] in customer acquisition"
3. **Add a "Cost of Delay" slide** before the recommendation:
   - Show what happens to the business if we don't act in time
   - Make it tangible (revenue, market position, competitive risk)
4. **State the decision deadline explicitly** in the recommendation slide:
   - "We need to decide by [DATE]"
   - "We need to start by [DATE]"
5. **Add a "Next Steps" slide** with:
   - Specific actions (not vague "explore" language)
   - Clear owners
   - Explicit dates
   - Example: "Week of Jan 24: Product team scopes enterprise roadmap. By Feb 1: Security review. By Feb 15: Sales enablement + collateral ready."

---

## TRAP 4: Generic Close ("Questions?")

### Description
Your deck has been compelling. The story has clarity, tension, and a strong recommendation. Then the last slide says "Questions?" or worse, "Thank You." The moment to mobilize is lost. The reader's mind drifts away. You've built momentum and then released it into nothing.

### How It Manifests
- Final slide is generic ("Questions?" "Thank you" "Contact us")
- No restatement of the key decision or action
- No clarity on what the reader should DO as a result of this presentation
- No sense of what success looks like or how progress will be measured
- Closing doesn't reference the stakes established in the opening

### Detection Method
Read your final slide. Ask:
- "If the reader remembers only one thing from this deck, what would I want it to be?"
- "What decision or action am I asking for?"
- "What does success look like if they take this action?"
- "What should they do this week as a result of this presentation?"

If the final slide doesn't answer these, it's a Generic Close.

**Automated check**: Final slide should contain:
- A restatement of the main recommendation/insight (not just "Questions?")
- A specific call to action (not vague)
- A decision deadline or next date
- A success metric or expected outcome

If 0 of these appear, it's generic.

### Weak Example
```
SLIDE 9 (Final):
HEADLINE: "Questions?"

[blank space for questions]
```

### Strong Example
```
SLIDE 9 (Final):
HEADLINE: "Decision Needed by Feb 15: Commit to Enterprise Pivot"

KEY TAKEAWAY:
Pivoting to enterprise segment unlocks 3x better unit economics and
positions us ahead of competitors in the market's premium segment.
Our 90-day window to gain share closes in June.

WHAT WE'RE ASKING FOR:
- Finance: Approve budget reallocation for enterprise sales team (due Feb 15)
- Product: Confirm enterprise roadmap commitment (due Feb 10)
- Sales: Hire enterprise AE and begin prospect outreach (start Feb 20)

SUCCESS LOOKS LIKE (Q2 2026):
- 3 enterprise pilots signed, 2+ expanding
- Enterprise ARR run rate: $500K+
- Team operating at planned capacity

NEXT MEETING: Feb 17 (post-decision alignment)

Questions or concerns?
```

Why it's strong: Reader knows exactly what's being asked, when decision is needed, and what success looks like. They can act immediately.

### How to Fix
1. **Restate the core insight/recommendation** in 1-2 sentences:
   - Not the full argument (they've heard it), but the essential takeaway
2. **Make the ask specific and measurable**:
   - NOT: "We should prioritize this"
   - YES: "We need to allocate $500K to hiring and commit to launch by May 1"
3. **Define success in concrete terms**:
   - "By end of Q2, we'll know this succeeded if [specific metric hits target]"
   - "We'll measure progress by [specific KPI], reviewed on [cadence]"
4. **Name owners and deadlines**:
   - "Finance leads budget review, due Feb 15"
   - "Product confirms roadmap, due Feb 10"
   - "Execution starts the week of Feb 20"
5. **End with a clear next step**:
   - "Next meeting: Feb 17 to align post-decision"
   - Or: "You'll receive a 1-pager with detailed plans by [DATE]"
   - Or: "Please confirm your commitment by [DATE]"

---

## TRAP 5: Label Creep

### Description
Your opening slides have strong, specific headlines. They tell a story: "Market Shift Creates Risk" → "Our Core Segment Is Shrinking" → "Competitors Are Moving Faster." But by Slide 5, headlines have become generic labels: "Financials," "Timeline," "Appendix." The narrative thread is lost. You're no longer telling a story; you're presenting a report.

### How It Manifests
- Opening slides: Specific, story-driven headlines
  - "Retail Consolidation Is Eliminating Our Customer Base"
- Middle slides: Still specific
  - "Our Largest 10 Customers Account for 60% of Revenue"
- Later slides: Generic labels take over
  - "Market Analysis"
  - "Financial Projections"
  - "Implementation Timeline"
  - "Q&A"
- Reader's sense of narrative urgency weakens as they progress
- Supporting evidence slides don't reinforce the main story; they feel like a data dump

### Detection Method
Extract the headline from EVERY slide (at least slides 2-8, the body of the deck). Create a list:

```
Slide 2: "Retail Consolidation Is Eliminating Our Customer Base"
Slide 3: "Our Largest Customers Are Under Increasing Pressure"
Slide 4: "Competitors Are Diversifying; We're Stuck"
Slide 5: "Market Analysis"              ← LABEL, not story headline
Slide 6: "Financial Projections"        ← LABEL, not story headline
Slide 7: "Timeline"                      ← LABEL, not story headline
```

**Automated check**: Classify each headline as "Story Headline" (makes a claim or shows a consequence) or "Label Headline" (categorizes content without making a point).

If more than 30% of body slides use Label Headlines, you have Label Creep.

### Weak Example
```
Slide 2: "Market Opportunity: $5B"
Slide 3: "Competitive Positioning"
Slide 4: "Financial Projections"
Slide 5: "Timeline"
Slide 6: "Team"
Slide 7: "Use of Funds"
```

Why it's weak: These are category labels, not story headlines. They tell you what section you're in, not why the content matters.

### Strong Example
```
Slide 2: "$5B TAM with 40% CAGR — Market Is Expanding Faster Than Supply"
Slide 3: "We're the Only Vendor with Both [Feature] and [Feature] — Competitors Are 12+ Months Behind"
Slide 4: "Unit Economics Improve with Scale — $800K CAC Breaks Even in Year 2"
Slide 5: "Revenue Reaches $50M by Year 5 — Assuming 35% Churn, 25% New Logos per Year"
Slide 6: "Go-to-Market Fully Funded by Month 8 — Sales Team Hired by Q2, Reaches Productivity by Q4"
Slide 7: "Founding Team Has 8+ Exits — Technical Expertise Proven, Go-to-Market Tested"
Slide 8: "$10M Seed Round Covers Runway Through Series A — Hired 15 People, Build Core Product"
```

Why it's strong: Every headline makes a point, not just labels a section. Reader can skim headings and still follow the story.

### How to Fix
1. **Review every body slide headline** (at minimum, slides 2-8)
2. **For each Label Headline, convert it to a Story Headline**:
   - OLD: "Market Analysis" → NEW: "40% CAGR Growth But Market Consolidation Limiting Small Players"
   - OLD: "Financial Projections" → NEW: "Unit Economics Improve 30% by Year 3 with Scale"
   - OLD: "Timeline" → NEW: "Critical Path: 12 Weeks to MVP, 6 Months to Series A Readiness"
3. **The conversion formula**:
   - Identify the key insight or finding from that slide's data
   - Ask: "Why does the reader care about this?"
   - Rewrite the headline to answer that question, not just label the section
4. **Test for consistency**:
   - Read just the headlines of slides 2-8 in sequence
   - Do they tell a coherent story? If you read ONLY the headlines, would you understand the argument?
5. **Use parallel structure** where possible:
   - Example: "Platform risk → Regulatory risk → Competitive risk" (each headline follows same pattern)
   - Helps reader track the narrative through supporting evidence

---

## Summary Table: Quick Reference

| Trap | What It Is | How to Detect | Quick Fix |
|------|-----------|---------------|-----------|
| **Insight Without Stakes** | Finding without business impact | "So what?" test: If this is true, why does it matter to the business? | Add a stakes statement connecting insight to revenue/risk/strategy |
| **All Evidence, No Tension** | Every slide supports conclusion; no barriers | Count slides with "problem/challenge/barrier" language; if <20%, tension is low | Add a "complication" slide naming the real barrier, then show how you overcome it |
| **Solution Without Urgency** | Recommendation without deadline or cost-of-delay | Check recommendation slide: Does it say WHEN to act? WHAT happens if we don't? | Add timeline, cost-of-delay calculation, explicit decision deadline |
| **Generic Close** | Final slide is "Questions?" not a mobilization call | Does final slide restate the ask, define success, name next steps? | Restate key ask, define success metrics, name owners + deadlines, end with next meeting date |
| **Label Creep** | Headlines change from story to category labels | Extract headlines; classify as "Story Headline" or "Label Headline"; count labels | Convert label headlines to story headlines that make a claim or show consequence |

---

## Implementation Notes for Zennify Skill

The zennify-narrative skill should include automated detection for all 5 traps:

1. **On slide creation**: Check headline + body for stakes language; if body text lacks "means," "results in," "implies," flag as Insight Without Stakes risk
2. **On slide_plan generation**: Analyze sequence of slide topics; if 80%+ are evidence slides with no complication/challenge slides, flag as All Evidence, No Tension risk
3. **On recommendation slides**: Check for time language (by, by Q, deadline, starts); if missing, flag as Solution Without Urgency risk
4. **On closing slide**: Verify it contains a call to action + success metric + next step; if not, flag as Generic Close risk
5. **On headline review**: Compare first slide headline pattern to final slides; if last 3 slides are all labels, flag as Label Creep risk

For each risk detected, provide a rewrite suggestion with concrete examples from the deck's own data.

End of narrative_traps.md
