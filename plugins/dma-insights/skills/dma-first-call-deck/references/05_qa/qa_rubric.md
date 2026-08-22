# QA Rubric — 12-Check System

Run on every batch. Automated checks via `scripts/04_qa/qa_checker.py`.

---

## Check 1: Headline Test + Scoring | HIGH

**Catches:** Label-style headlines that fail to make a claim.

**Detection:** For each editable slide (except 2, 8, 10, 11, 15, 22):
- **Fail patterns (any → flag):** ≤4 words; noun phrase without verb; starts with "The" + noun; contains "Overview of" / "Summary of"; generic labels ("Current State", "Next Steps", "Key Findings", "Assessment Results").
- **Pass patterns (all required):** contains verb; contains number/percentage; makes arguable claim; 8-25 words; specific enough to stand alone.
- **Score on 9-point rubric** (see brand_guidelines.md Section 8). Flag if < 7.

**Fix:** Rewrite using 4 headline patterns (Paradox, Quantified Impact, Gap→Outcome, The Window).

---

## Check 2: Glance Test (3-Second Rule) | MEDIUM

**Catches:** Slides too dense to scan in 3 seconds.

**Detection per slide:**
| Metric | Limit |
|---|---|
| Body word count | ≤75 words |
| Bullet count | ≤5 per slide |
| Words per bullet | ≤20 |
| Headline length | ≤25 words |
| Font size | ≥16pt body, ≥24pt title |
| Ideas per slide | 1 core idea |

**Exempt (data-dense):** Slides 6, 14.

---

## Check 3: Client-is-Hero | MEDIUM

**Catches:** Zennify positioning as protagonist.

**Violation patterns:** `Zennify` or `We` + transformation verb (transform, revolutionize, deliver, achieve, drive, lead, create, build). Also: "Our solution" + achievement verb, self-aggrandizing terms (innovative, superior, cutting-edge, world-class, best-in-class).

**Acceptable:** "Zennify recommends...", "Our assessment reveals...", "We've seen institutions achieve..."

**Exempt:** Slides 3, 10, 11, 12 (methodology).

---

## Check 4: MECE Consistency | MEDIUM

**Catches:** Overlapping or incomplete supporting points.

**Detection (Claude judgment):** For slides with 2+ bullets:
1. **Pairwise merge:** Can any 2 points be combined? → overlap
2. **Missing factor:** What would a skeptic say is absent? → gap
3. **Prove headline:** Do all points together prove the headline? → restructure if not

---

## Check 5: Brand, Source & Schema Alignment | CRITICAL

**Catches:** Placeholders, unauthorized colors, wrong fonts, fabricated data.

**5a Placeholder sweep:** grep 17+ patterns: `[Client]`, `[client]`, `[CLIENT]`, `[Customer]`, `[Company]`, `XXXX`, `XX.XX`, `Lorem`, `TBD`, `PL NAME`, `{{`, `}}`, `[DATA NEEDED]`, `[Insert`, `[Name]`, `[Title]`, `[Email]`, `[Date]`. Any remaining = CRITICAL.

**5b Color validation:** Post-edit grep all `srgbClr val=`. Compare against brand palette. Any unauthorized hex = HIGH.

**5c Font check:** grep all `typeface=`. Only DM Sans / DM Sans Medium. Any Arial, Calibri, Noto Sans = HIGH.

**5d Logo check:** Zennify logo shapes present on applicable slides.

**5e Source anchoring:** Every content_block in `slide_plan.json` has `source_facts[]` referencing valid `fact_bank.json` entries. 100% coverage required. Unanchored = CRITICAL.

**5f Schema integrity:** `validate_schema_integrity.py` cross-validates fact_bank ↔ slide_plan. Missing references = CRITICAL.

**5g Reframing check:** Scan for emotional adjectives absent from source. No invented consequences. No extrapolated projections.

---

## Check 6: Spacing & Shape Integrity | CRITICAL

**Catches:** New shapes, deleted shapes, position drift, formatting corruption.

**Detection (pre/post diff):**
| Check | Method | Severity |
|---|---|---|
| Shape count per slide | Compare count pre vs post | CRITICAL if changed |
| `<a:off x= y=>` | Diff positions (except Slide 14 bars+markers) | HIGH if changed |
| `<a:ext cx= cy=>` | Diff sizes (except Slide 14 bars) | HIGH if changed |
| `<a:sz>` font sizes | Diff all | HIGH if changed |
| `<a:p>` count per shape | Diff paragraph count | HIGH if changed |
| `<a:r>` count per shape | Diff run count | HIGH if changed (formatting lost) |

---

## Check 7: Solution Slide Integrity | CRITICAL

**Catches:** Structural damage to Slides 17-19.

**Detection:** Shape count = 16 per slide. AUTO_SHAPE bg positions unchanged. Bold on Sh4/10/13 titles preserved. "Key capabilities" header as first line of Sh9/12/15 preserved.

---

## Check 8: Opportunity Language | HIGH

**Catches:** Gap/deficit/weakness language in the deck.

**Banned words:** gap, deficit, weakness, weak, fails, failing, lacks, lacking, immature, poor, low maturity, falls behind, trails, lags, underperforms, problem, issue, risk, threat, danger, below benchmark, below median.

**Suggested replacements:** opportunity, room for growth, area of focus, positioned to accelerate, highest-value transformation opportunity, early-stage, activating, building, priority investment area.

**Exempt:** Slides 5, 7 (read-only industry content).

**Context-aware:** "gap" in "capability gap → outcome" headline pattern is structural reference, not negative framing. Only flag when describing client's current state.

---

## Check 9: Text Overflow | HIGH

**Catches:** Text exceeding shape boundaries, headlines >2 lines.

**Pre-edit detection:** For every edited shape:
```
chars_per_line = shape_width_px / (font_size_pt × 0.55)
max_lines = shape_height_px / (font_size_pt × 1.3)
max_chars = chars_per_line × max_lines
```
If `len(text) > max_chars` → OVERFLOW flag.
Headlines: if estimated lines > 2 → HEADLINE_TOO_LONG.

**Post-edit:** Convert PPTX → PDF → images. Visually verify all flagged slides.

**Overflow actions:** Truncate bullets + `[...]`. Split body text across slides. Shorten headlines. Never reduce font (exception: >12pt AND <20% overflow → 1pt max reduction).

---

## Check 10: Sub-Vertical Consistency | HIGH

**Catches:** Wrong industry content for selected sub-vertical.

**Detection:**
- Slide 5 headline contains expected SV keyword
- Slide 7 pain points match SV
- Slides 1, 3 taglines match
- Slides 17-19 "Proven solutions for [X]" match

---

## Check 11: Narrative Trap Detection | HIGH

**Catches:** 5 anti-patterns that make a deck technically correct but fail to persuade.

| Trap | Detection | Fix |
|---|---|---|
| **Insight Without Stakes** | Data slides (9, 13, 14, 16): numbers without "means / results in / implies / enables / unlocks." >50% lacking → flag. | Add stakes: "This translates to..." |
| **All Evidence, No Tension** | Count complication slides (5, 7 provide tension). If tension softened beyond recognition by opportunity language → flag. | Verify Slide 7 retains its edge. |
| **Solution Without Urgency** | Slides 16, 20: search for "by [date]", "before", "deadline", "week of", "starts." Absent → flag. | Add timeline, cost-of-delay, decision deadline. |
| **Generic Close** | Slide 20: check for (1) restatement of ask, (2) action table + dates/owners, (3) deliverables, (4) goal statement. <3 of 4 → flag. | Implement mobilization close. |
| **Label Creep** | Headlines Slides 6-20: classify "Story" vs "Label." >30% labels → flag. | Convert labels using 4 patterns. |

---

## Check 12: Storyline Test | HIGH

**Catches:** Headlines that individually work but don't tell a coherent story.

**Detection:** Extract ALL headlines in order. Read top-to-bottom. Must tell:
1. Who they are + strategic context (Slides 1, 6)
2. Industry forces (5)
3. Pain they feel (7)
4. Where they stand on maturity (9, 13, 14)
5. What opportunities exist (16)
6. What solutions address them (17-19)
7. What to do next (20)

Write 1-paragraph summary. If reader can't follow AIDA arc from headlines alone → rewrite weakest.

---

## Input Dependency Graph

_Causal chain from input data → transformation → shape state._

Every shape's final fill/border/text/text-color can be traced back to one of:
- **A score** (→ `score_to_level_Ntier` → `LEVEL_*TIER[level][palette_key]` → hex)
- **A text input** (client name, insights, recs, priorities, etc.)
- **A static color** (from `STATIC_COLORS`, preserved across edits)
- **A theme reference** (from `THEME_REFS`, `schemeClr` preserved, never overridden)
- **An image input** (client logo, radar chart)

### Where to find the full graph

The complete per-shape chain tables + inverse index are in
[`references/_generated/input_dependency_graph.md`](../_generated/input_dependency_graph.md).
That file is **regenerated from `color_level_system.py`** via
`scripts/utils/generate_dependency_graph.py` — never edited by hand.

### High-level summary

Grouped by slide, the editable shapes depend on these unique input sources
(counts verified against `color_level_system.py`; for the full per-shape
chain, see `input_dependency_graph.md`):

| Slide | Roles | Unique Sources | Typical Drivers |
|---|---|---|---|
| 1 | 3 | 3 | headline, tagline (sv + date), client logo |
| 3 | 1 | 1 | subvertical descriptor |
| 6 | 36 | 32 | client name, headline, 6 quick facts, 3 priorities × 2, 5 platforms + summary, 3 metrics × 3 |
| 9 | 0 | 0 | static slide — no per-deck edits |
| 10 | 32 | 26 | client, subvertical, overall + peer, 4 pillar scores, 3 rec scores, 4 insights, 2 strengths, narrative |
| 13 | 33 | 20 | client, headline, 4 pillar scores (5-tier), 4 strengths, radar images |
| 14 | 145 | 61 | 17 capability scores (4-tier), 17 peer medians for marker x-position, headline, legend |
| 16 | 11 | 11 | headline, intro, 3 opportunity cards (name + gap + why), outcomes |
| 20 | 12 | 5 | headline, goal statement, next steps list, deliverables list, static chips |
| 21 | 1 | 1 | presenter email |

### How QA uses this

`cross_slide_checker.py` takes the same `input.json` the editors took, walks
every role in `ALL_SLIDE_ROLES`, and derives the expected fill/border/text_color
via the same chain documented in the dependency graph. When it reports a
mismatch, the error already cites the driver (the input source), the derived
transform, and the expected hex — no reverse lookup needed.

### Debugging a failure

When QA flags a CRITICAL, follow this protocol:

1. **Read the driver line** in the QA error — e.g., `s10.rec_scores[2] = 1.2`.
2. **Look up the driver in the dependency graph** to confirm which shapes it
   affects (in this case: Sh23, Sh24, Sh25 on Slide 10).
3. **Check the derived line** — e.g.,
   `score_to_level_4tier(1.2) = 'Activating'; LEVEL_4TIER['Activating']['card_bg']`.
4. **Confirm expected vs actual** — is the actual hex from a DIFFERENT level's
   palette (editor applied the wrong level)? Is it `scheme:*` (editor wrote
   schemeClr instead of srgbClr)? Is it an unrelated hex (template drift)?
5. **Fix at the root**:
   - Wrong level applied → re-run the editor with correct input JSON
   - schemeClr leaked through → check `apply_color_role` is being called
   - Unrelated hex → template has drift; re-run template_preparer

The dependency graph's `input_dependency_graph.md` includes a full Debugging
Guide with three worked examples for the common failure modes.

### Static and theme-ref chains

- **Static colors** don't depend on any input — they should always match
  `STATIC_COLORS[source]`. A mismatch means template drift or an accidental
  overwrite. The editors' `verify_*` functions catch this post-edit.
- **Theme references** should always be `<a:schemeClr val="...">`. The editors
  skip theme_ref roles in `apply_color_role` — if QA finds `srgbClr` on a
  theme_ref shape, a bug in a non-role-driven write path (or a manual edit)
  has corrupted it.

---

## Scoring

| Verdict | Criteria |
|---|---|
| **PASS** | All slides OK, no CRITICAL, ≤3 HIGH |
| **PASS WITH NOTES** | Minor MEDIUM issues, no CRITICAL |
| **FAIL** | Any CRITICAL, or >3 HIGH |

**Critical failures (auto-FAIL):** Leftover placeholders, fabricated data, unauthorized colors, broken layouts, removed logos, unanchored content, shape count mismatch, yellow highlights, wrong benchmark colors.
