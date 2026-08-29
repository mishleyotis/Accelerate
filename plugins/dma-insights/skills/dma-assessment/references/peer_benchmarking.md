# Peer Benchmarking Protocol

Read this file during Phase 2 of the assessment workflow.

---

## Peer Selection Methodology

### Step 1: Define Matching Criteria

**Primary Criteria (Must Match ALL)**:
- Same sub-vertical (e.g., Credit Union, not Regional Bank)
- Asset size within ±50% of target institution
- Same primary regulator jurisdiction

**Secondary Criteria (Should Match 2+)**:
- Similar geographic footprint (regional vs. national)
- Similar customer/member profile (consumer vs. commercial mix)
- Similar charter type or business model
- Similar product complexity
- No recent M&A distortion (within 24 months)

### Step 2: Identify Candidate Pool (10-15)

Sources for candidate identification:
- Regulatory filings (Call Reports, 10-Ks, NCUA reports)
- Industry rankings by asset size
- Trade publication lists (e.g., S&P Global, American Banker)
- Analyst coverage universe

### Step 3: Apply Secondary Filters

Score each candidate 0-3 per secondary criterion. Rank by total score. Select top 5.

### Step 4: Document Selection Rationale

For EACH selected peer, document:
```
PEER: [Name]
Assets: [$X.XB]
Members/Customers: [X.XM]
Geography: [Description]
Selection Rationale: [Why this peer is comparable to target]
Differences Noted: [Any factors that could affect comparison]
Sources: [How peer data was validated]
```

### Step 5: Validate with Stakeholder (if applicable)

Present proposed peer set to institution stakeholder. Incorporate feedback. Document
any stakeholder-driven changes with rationale.

---

## Peer Scoring Protocol

For each of 5 peers, for each of the 16 categories:

1. **Gather public evidence** (abbreviated search — focus on T1-T3 sources)
2. **Apply identical scoring methodology** (same rubrics, same decision tree, same caps)
3. **Document key evidence** supporting each peer score
4. **Note confidence level** for each peer score

### Quality Checks
- If any peer score is an outlier (>1.5 from others) → investigate
- Confirm evidence quality supports the outlier score
- Document explanation if outlier is valid
- If evidence is too thin to score → mark as LOW confidence

---

## Benchmark Calculation

For each of the 16 categories:

```python
peer_scores = [peer_1, peer_2, peer_3, peer_4, peer_5]
sorted_scores = sorted(peer_scores)

# For 5 peers:
median = sorted_scores[2]       # Middle value (3rd of 5)
p25 = sorted_scores[1]          # 2nd lowest
p75 = sorted_scores[3]          # 2nd highest
minimum = sorted_scores[0]      # Laggard threshold
maximum = sorted_scores[4]      # Leader threshold

# For 4 peers (if one peer is N/A):
median = (sorted_scores[1] + sorted_scores[2]) / 2
p25 = sorted_scores[0]
p75 = sorted_scores[3]

# For 3 peers:
median = sorted_scores[1]       # Middle value
p25 = sorted_scores[0]
p75 = sorted_scores[2]
```

**CRITICAL**: Calculate benchmarks fresh from peer scores. NEVER hardcode benchmark values.
The same calculated values must appear in EVERY artifact that references them. If a peer
score changes, all benchmarks must be recalculated.

---

## Benchmark Interpretation

### Gap Interpretation Matrix

| Gap vs Median | Gap vs P25 | Interpretation | Narrative Frame |
|--------------|-----------|---------------|----------------|
| > +0.75 | > +0.50 | LEADER | "Competitive strength; potential differentiator" |
| +0.25 to +0.75 | > +0.25 | ABOVE MEDIAN | "Above peer average; continue momentum" |
| -0.25 to +0.25 | Any | PEER PARITY | "Aligned with peers; not differentiating" |
| -0.75 to -0.25 | Any | BELOW MEDIAN | "Opportunity to strengthen toward peer parity" |
| < -0.75 | < -0.25 | PRIORITY AREA | "Meaningful improvement opportunity" |
| < -1.00 | < Min | CRITICAL AREA | "Significant improvement opportunity; immediate attention warranted" |

### Peer Comparison Narrative Pattern

```
[Institution]'s [category] score of [X.XX] positions it [interpretation] among
comparable [sub-vertical] institutions. The calculated peer median of [Y.YY]
(based on [N] comparable institutions: [Peer A] [score], [Peer B] [score],
[Peer C] [score], [Peer D] [score], [Peer E] [score]) indicates a [gap/lead]
of [+/-Z.ZZ].

[If below median]: This [gap amount] represents the [Nth] largest improvement
opportunity across the 16 categories assessed, driven primarily by [root cause
with evidence citation].

[If above median]: This [lead amount] reflects [specific institutional strength
with evidence citation], positioning [Institution] in the [top/second] quartile
among peers.
```

### Pillar and Overall Benchmark

Apply the same calculation methodology at pillar and overall levels:
- Pillar benchmarks: Calculate from peer pillar scores (which are weighted sums of category scores)
- Overall benchmarks: Calculate from peer overall scores (which are weighted sums of pillar scores)

**Validation**: Peer overall scores calculated bottom-up must match the weighted sum of
their pillar scores. If they don't, there's a calculation error — stop and fix.
