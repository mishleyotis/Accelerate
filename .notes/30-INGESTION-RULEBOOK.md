# The ingestion rulebook, internalised

Four artifacts, in the order they build on each other. Each section ends with
how I will apply it to a new DMA.

---

## 1 · Gold standard — Baxter Credit Union (`baxter-credit-union-bcu`, SV2)

**What it is.** The promoted, production-serving run the whole build calibrates
against. Not a document: a *measured corpus*. Every threshold in the gate set
was set by measuring Baxter and checking that honest work passes.

**What it establishes, with the numbers:**

| Fact about Baxter | Why it is the calibration point |
|---|---|
| **706 cell syntheses** at an 8-gram phrasing overlap of **0.179** against a refusal line of 0.40 | A 700-cell per-cell page is demonstrably writable. If mine is refused for templating, the shape is wrong, not the scale |
| Content-word overlap up to **0.793** between two perfectly good cells | Honest prose about one institution shares vocabulary freely. Distinctness lives in *phrasing*, not in vocabulary |
| Lowest words-to-floor ratio **0.64**; lowest residual **4 content words** | Real content undershoots its budget sometimes and still passes |
| **69 `cell_evidence` rows out of 765 cells (9%)** on a clean verdict | `cell_evidence` was never a row-per-cell contract. A partial array is valid |
| Its broadest document bears on **53.7%** of its cells, legitimately | Breadth is not the defect. The W6 sole-evidence cap targets **monopoly**, not reach |
| **11 alert justifications at 0.90–0.97 overlap — and they pass** | Because each records `WORKED_ABSENT`/`UNWORKED` with its four searched sources. The exemption is the *record*, not the wording |
| Its **17 ceiling rationales were refused** — one template, document name swapped, two pairs byte-identical | Baxter is not uniformly good. It is the reference *and* the source of named defects (BAX-09, the four crossed `source_url` pairings E-CC-001…004) |
| **604 of 766 scored cells sit in clone blocks of 10+** | An OPEN finding about upstream assessment production, recorded not acted on. I must not read Baxter as flawless |

**How I will apply it.** Baxter is my calibration reference, not my template.
Before I submit a page I ask: does this read like Baxter's honest prose (facts
distinct, frame shared) or like Baxter's refused ceilings (frame distinct,
facts identical)? Where a threshold feels arbitrary I check what Baxter
measured at. And I carry its known defects forward as things to *not* repeat —
crossed excerpt/URL pairs, one document carrying a fifth of the run, a template
with the noun swapped.

---

## 2 · Rules tests — the pass/fail gates

**Four families, four failure behaviours.** The prefix is part of the id.

| Prefix | Family | Runs | On failure |
|---|---|---|---|
| `AG-nn` | Analytical | inside synthesis, per claim | the claim changes or is dropped |
| `SG-nn` | Safeguard | at submit, **and renders to the client** | recorded and disclosed; **does not block promotion** |
| `ET-nn` | Enrichment trigger | during synthesis | not a failure — a prompt to go and look |
| `CG-nn` | Corpus/contract | submit and build time | **fails the build** |

Plus two unnumbered structural passes at submit: **contract pass** (required
fields, types, word budgets, registers, terminal punctuation, id patterns) and
**evidence pass** (every id resolves, belongs to this entity and run, verbatim
excerpt, identity-checked domain). **Any evidence reason at all fails the
submission.**

**The ones a submission actually dies on:**

- **AG-03** — every claim-bearing *item* cites its own evidence. Fires per item,
  reads the required key from each field's own contract `doc`. Does not fire on
  a null row, a recorded absence carrying its ladder, or a section envelope.
  An inference cites what it was inferred *from*.
- **CG-15** — the only gate that reads prose for content. Five refusals:
  placeholder; prose under `ceil(floor × 0.5)`; a section all of whose content
  fields are vacuous; **template prose** (8-gram phrasing ≥0.40 **and** content-word
  overlap ≥0.40, connected group of 3+); prose that only restates a score or
  inventories evidence (residual ≤2 content words).
- **CG-09** — a closed vocabulary takes one of its values, case-exact.
  `timeline.events[*].signal` ∈ POSITIVE│NEUTRAL│NEGATIVE;
  `techstack.items[*].status` ∈ CONFIRMED│INFERRED│CLAIMED│ABSENT.
- **AG-04** — a named peer's technographics carry `source_url` + `as_of`;
  a `peer_coverage` share needs a `peer_deployments[]` breakdown agreeing to
  within one peer; unestablished peers are `deployed: null` and count in the
  denominator.
- **ET-04** — a cited id resolves to a row carrying a verbatim **50–500 char**
  excerpt.
- **ET-05** — a run cites only its own sub-vertical's variant cells. One-sided:
  foreign only when the code names exactly one sub-vertical and it is not this
  entity's.
- **ET-01 / ET-09** — a foreign *citation* halts; prose naming another corpus
  client halts. Both mean the reasoning drifted onto the wrong entity.
- **CG-10** — a date that could not be established says so, on a named rung.
- **CG-11** — prose begins as a sentence (vendor orthography exempt: nCino, iOS).
- **CG-12** — a face field is a label, not a paragraph. **Repair is to MOVE the
  prose, not trim it.**
- **CG-14** — a linked cell exists on this run.
- **CG-16 / CG-17** — a required list is not silently empty; must-present members
  are stated or `quarantined` with a reason.
- **CG-01** — grain: a quoted figure and its named cell are one row, within 0.05.
- **SG-S8** — sentiment rests on more than one rated line. **Discloses, does not
  block.** Counted from rating rows, never from a declared `displayed_lines`.

**The citation stack V1–V4.** V1 cited ids ⊆ bundle · V2 no fabricated ids by
pattern *and* DB existence · V3 no fabricated entity tokens · V4 re-embed and
require semantic agreement. **V4 is the one that matters** — text can satisfy
V1–V3 and still say what the sources do not.

**Seven cross-surface reconciliation pairs**: O1↔H4 composite · O8↔C6 identical ·
T2 counts↔T1 register · O10 denominator↔H4 cell set · H3 alerts↔H2 cells ·
P3 roadmap ids↔P2 recs · run history↔O1.

**Local checkers, and when each runs:**

| Script | When |
|---|---|
| `check_repetition.py --at-scale N` | **before the 21st item**, not before submit — CG-15 is a property of the array |
| `check_payload.py --page --subvertical --cells` | before every submit (`--subvertical` turns ET-05 on, `--cells` turns CG-14 on; without them they print "not run", which is not a pass) |
| `check_language.py` | before every submit |
| `precheck_gates.py --evidence --bundle` | before every submit — runs the connector's own blocking gates locally, imports the gate modules rather than restating them |
| `check_evidence.py --review` | on the evidence register |
| `check_consistency.py <rundir> --subvertical` | across all six pages, before promotion |

**How I will apply it.** A submission is not free: it supersedes the staged row,
so a FAIL on a passing page costs the pass and blocks the promote for the other
five. So I run `check_repetition` at draft 20, then `check_payload` +
`check_language` + `precheck_gates` locally, and only then submit. I read a
verdict literally and **repair the cause, not the symptom** — a verdict saying
"quoted 2.34 resolves to 2.10" is telling me I paired a name and a figure from
different rows.

---

## 3 · Enrichment guidelines

**Two legal origins of evidence, and only two.** Package evidence is already in
the store — cite it, never create it. Enrichment is anything found outside the
package — **register first, cite second**. The server allocates the id and
computes ERS; registration is idempotent by content.

**Register from the artefact you fetched, in the same step you fetched it.**
The excerpt and the `source_url` are **one claim**. A true claim under a URL
that does not contain it is fabrication by construction — that is exactly how
Baxter's E-CC-001/002 shipped, and one of them was cited nine times.
Re-extract, never retype: whitespace re-flow is safe, joining two passages is
not; 50–500 chars, contiguous, case-insensitive.

**Clay is the enrichment engine.** Budget for one run: 1 company call
(Tech Stack · Annual Revenue · Headcount Growth · Recent News · Open Jobs ·
Latest Funding) + 1 leadership contact search + 1 contact enrichment
(Find Thought Leadership · Summarize Work History) + at most 2 targeted custom
points against a named gap. **Outside that, ask.**

- **Run it immediately after reading the bundle**, before the heatmap — it is
  async and the pages that consume it come last.
- **Tier follows the source, not the tool.** `Tech Stack` is **T1** (a machine
  technographic scan) — filing it T4 caps the capability at L2.5 and silently
  suppresses the score. `Recent News` T3, `Summarize Work History` T3,
  `Open Jobs` T2–T3.
- **Cite the source, not the tool.** "Clay reports 340 employees" is not
  evidence; the filing Clay surfaced is.
- **Never record an absence from a Clay call without polling `get-task-context`
  first.** The search response carries base fields only.
- **A name-similar match is an identity FAILURE.** The returned *title* must
  match the person searched for. Surname + employer is not identity.
- Resolve on the domain the entity's own registry uses. A brand-domain
  technographic scan is evidence about that brand's estate, not the enterprise's.
- A source that 403s to automated fetch (Glassdoor, Indeed, ZipRecruiter,
  Trustpilot, BBB profiles) is **uncitable** — find it elsewhere, carry it as a
  labelled inference with its route, or omit it and record the rung.

**The absence protocol is the other half of enrichment.** Never emit an empty
state until a documented proxy ladder has failed; every rung attempted is
recorded and ships with the payload. Four results, and they are different
findings: **HIT** · **NEGATIVE** · **NEGATIVE AND APPROPRIATE** (the absence is
correct posture, not a gap) · **NOT ATTEMPTED** (not an absence — emit nothing).
Check the ladder fits the entity's shape: a rung beginning "filings", "proxy",
"Section 16" or "call report" presumes a filer, and running it against a
non-filer produces a NOT ATTEMPTED recorded as a verified absence.

**Standing scoping decision (build owner, 2026-08-14, reversible):** a
subcapability whose evidence set is empty is **not mine to write** — skip it,
leave it out of the array, do not chase evidence for it. Enrichment effort goes
to heatmap tiers 1 and 2 (cells another surface cites; cells below threshold).
A run is promotable with those cells unwritten. This does **not** license
skipping a cell that has citable evidence, or one another surface cites.

**How I will apply it.** Clay first, register as I go, tier from the source,
poll before concluding, and run the shape-appropriate ladder before any empty
state. When a scan and the register disagree I work the four-step resolution
(compare `as_of` → ask what the scan observed → check for subsidiary/predecessor/
partial estate → quarantine and state it) and never average.

---

## 4 · Reasoning guidelines — the R-Layer

Every gate checks a claim **after** it is written. The R-Layer is what happens
**before**, and it is the only thing that catches a claim that is well-formed,
correctly cited, grain-locked and wrong.

```
A  HYPOTHESIS        the claim and its confidence, before defending it
B  COUNTER-EVIDENCE  the strongest case against it
C  DOMAIN TEST       plausible for THIS sub-vertical, size tier, regulator —
                     and about this ENTITY, not its cohort
D  FAILURE PROBES    the probe set for the surface; each probe fires a search
E  VERDICT           ACCEPT · REJECT · UNCERTAIN (reject = re-rank or drop,
                     never soften)
```

Recorded as `r_layer: {hypothesis, counter, domain_test, probes_run[], verdict,
confidence}` on any surface making a ranked or causal claim.

- **Step B is the one that gets skipped.** Source the falsifier from the
  client's own words where possible — that is what makes it survive the room.
- **Step C's second half bites on the second client in a sub-vertical:**
  *would this sentence be true of any institution in this sub-vertical?* If yes
  it is a fact about the sub-vertical or a shared vendor, not a finding about
  this client. Two honest moves: attach entity-specific evidence, or move it to
  where cohort facts belong (H8). Softening is not one of them.
- **Four probes fire on every surface:** foreign variant cell · cohort scale ·
  shape-blind ladder · cohort sentence.
- **Nine contradiction classes:** grain · magnitude · cross-surface · source rank ·
  self-description · arithmetic vs analyst · temporal · confidence · vocabulary.
- **Cross-check every fact appearing twice.** Agreement from independent origins
  corroborates and raises the rank score; agreement from one origin is one
  source (an annual report and an investor deck are not two). Disagreement where
  one outranks resolves by priority and is recorded. Disagreement between peers
  is a contradiction: quarantine and state it. **Never average — the result is
  in no source.**
- **UNCERTAIN is a legitimate outcome and it renders.** Lower the confidence,
  put the counter beside it, name what would settle it.
- The R-Layer is **not** hedging, **not** a disclaimer, and **not** optional on
  strong claims.

**Beyond the R-Layer, two whole-run steps before promotion:**

- **Storyline challenge, five volleys** — the client's executive, the finance
  officer, the incumbent vendor, the rival on the shortlist, the AE who must say
  it out loud. Recorded as `storyline_challenge.volleys[]`. **Five `held`
  outcomes is a finding, not a triumph** — it usually means the objections were
  written gently.
- **Fifteen answered questions** (`04-craft/8-answered-questions.md`), 40–110
  words each, spoken register, cited. An answer the run cannot ground is written
  as an absence with its reason, never composed around the gap.

**How I will apply it.** Every ranked, causal or comparative claim gets all five
steps written down before it is submitted. I run the sub-vertical test hardest
on the exec summary's complication, the top findings, the act-now cards and the
platform story. I record UNCERTAIN rather than softening, and I treat five
survived volleys as a signal to make the objections harder.

---

## Cross-cutting: the five standing clauses

1. **Identity** — five assertions per figure (legal name · regulator · footprint ·
   source domain · order of magnitude). On failure quarantine with the reason;
   never substitute a plausible value. **And assert the identity of my own
   working copy first**: namespace the scratchpad by `run_id`, assert `run_id` +
   `display_id` at every bundle read, re-assert after any pause.
2. **Grain** — any `<label> at N/5` resolves to a served cell within 0.05, both
   read from the same row. Round once. The single most common defect (125
   violations across the corpus).
3. **Register** — no consultant vocabulary, no deficit framing, no raw taxonomy
   codes in prose, no score-predicate openers, no markdown in text fields. **The
   verb is governed by the evidence level** (L1 uses/deployed · L2 partnered/
   selected · L3 likely uses/signals suggest · L4 may use/unconfirmed).
4. **Audience** — list every `internal_only` JSON path. There is no default; a
   field I do not mark reaches the client. Strip rank scores, rationale, internal
   codes, `entity_ids` (every audience). Withhold ceilings, sentiment, thought
   leadership, Context and Health dashboards from customers. **Do NOT mark
   internal**: thin-evidence markers, quarantine markers, failing safeguard gates.
5. **Citation at the item** — every asserting item carries its own id. The
   section envelope is a union, not a substitute. Naming a source in prose is not
   citing it.

**Language.** Every gap is stated as available value, and **no prose field opens
on an absence** — name the asset first, in sentence order. Later sentences are
exempt.

**Colour.** I never send one. Raw score + band word + semantic flags only.
Bands are strict less-than on the **raw** score: `<2 Activating · <3 Building ·
<4 Competing · ≥4 Differentiating`; null → no score. **M5/Transformational does
not render and must not appear in prose.** 2.97 displays as 3.0 and bands as
Building.
