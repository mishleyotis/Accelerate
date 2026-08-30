# Distributional Sanity Checks

These checks catch issues that pass all individual rule checks but form suspicious
patterns when viewed in aggregate. They are run after all Category 1–8 checks pass.

**Severity**: All distributional flags are MEDIUM or LOW. They never block delivery
alone but are critical inputs to calibration analysis (Workflow B).

---

## DC-01: Score Clustering

**What it detects**: Lazy scoring — assigning the same score to many subcaps without
differentiation.

**Check**: For each pillar, compute the mode score and its frequency.
- FLAG (MEDIUM): >60% of subcaps in any pillar share the same score
- FLAG (LOW): >50% of subcaps in any pillar share the same score AND the pillar has >15 subcaps

**Why it matters**: Real institutions have variation. Uniform scoring suggests the assessor
defaulted to a "safe" score rather than differentiating based on evidence.

---

## DC-02: Confidence Inflation

**What it detects**: Overconfidence — assigning HIGH confidence when evidence quality
doesn't warrant it.

**Check**: Compute confidence distribution across all subcaps.
- FLAG (MEDIUM): >70% of subcaps have confidence = HIGH
- FLAG (LOW): >50% of subcaps have confidence = HIGH AND average ERS < 3.0

**Why it matters**: HIGH confidence requires ≥3 evidence items with composite ERS ≥ 3.0.
If most subcaps are HIGH, either the evidence is genuinely excellent (rare for public-only
assessments) or confidence is being inflated.

---

## DC-03: Evidence Tier Concentration

**What it detects**: Over-reliance on a single evidence tier, reducing triangulation quality.

**Check**: For each pillar, compute tier distribution percentage.
- FLAG (MEDIUM): Any pillar relies >80% on a single tier type
- FLAG (HIGH): Any pillar relies >90% on T5 evidence (marketing-only)

**Why it matters**: Good assessments triangulate across tiers. Heavy T5 reliance suggests
the assessor didn't search hard enough for authoritative sources.

---

## DC-04: Cap Saturation

**What it detects**: Evidence quality problems — too many scores being capped.

**Check**: Compute percentage of subcaps where Final_Score < Raw_Score.
- FLAG (MEDIUM): >30% of subcaps in any pillar are capped
- FLAG (LOW): >20% of subcaps overall are capped

**Why it matters**: High cap rates suggest the scoring was too generous before caps, or
that evidence quality is systematically low. Either case warrants review.

---

## DC-05: Rationale Homogeneity

**What it detects**: Copy-paste rationales — assessor reusing text across subcaps.

**Check**: For each pair of rationales within a pillar, compute text similarity
(Jaccard similarity on word tokens, or Levenshtein ratio).
- FLAG (HIGH): Any two rationales share >80% text similarity
- FLAG (MEDIUM): Any two rationales share >60% text similarity AND have different scores

**Why it matters**: Each subcap should have unique reasoning tied to specific evidence.
High similarity suggests the assessor is templating rather than analyzing.

---

## DC-06: Evidence Reuse Concentration

**What it detects**: Over-reliance on a single evidence item across many subcaps.

**Check**: For each evidence item, count how many subcaps cite it.
- FLAG (MEDIUM): Any single evidence item cited by >25% of subcaps in a pillar
- FLAG (LOW): Any single evidence item cited by >15% of all subcaps

**Why it matters**: A single 10-K or annual report can legitimately inform many subcaps,
but extreme concentration suggests shallow evidence collection.

---

## DC-07: Score-Confidence Alignment

**What it detects**: Mismatch between score level and confidence.

**Check**: Cross-tabulate scores and confidence levels.
- FLAG (MEDIUM): >3 subcaps have score ≥ 4.0 with confidence = LOW
- FLAG (MEDIUM): >5 subcaps have score = 1.0 with confidence = HIGH (is absence really that certain?)

**Why it matters**: High scores with low confidence suggest speculation. Very low scores
with high confidence may be legitimate (clear absence of capability) but warrant a check.

---

## DC-08: Peer Benchmark Plausibility

**What it detects**: Peer medians that are implausibly high or low.

**Check**: Compare institution category scores against peer medians.
- FLAG (MEDIUM): Institution scores >1.5 above peer median on >3 categories
  (either institution is exceptional or peers are scored too low)
- FLAG (MEDIUM): Institution scores >1.5 below peer median on >3 categories
  (either institution is weak or peers are scored too high)

**Why it matters**: Extreme divergence from peers deserves validation — it might be real,
but it might indicate a benchmarking error.

---

## Output Format

Distributional check results are appended to the Issue Register with category = "DISTRIBUTIONAL":

```csv
issue_id,severity,category,subcategory,affected_id,description,detection_evidence,fix_instruction,auto_fixable,status
ISS-075,MEDIUM,DISTRIBUTIONAL,DC-01,P2,Score clustering: 65% of P2 subcaps scored 2.5,Mode=2.5 freq=65%,Review P2 subcap differentiation,false,OPEN
```
