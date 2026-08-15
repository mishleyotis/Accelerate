# DMA Insights — Production Acceptance and Adversarial QA (curated)

Curated from `DMA_Insights__Production_Acceptance_and_Adversarial_QA.md`
(14,091 lines · 2,428 headings · 93 surface sections, 14 August 2026) against
HEAD `14f1016`, 15 August 2026.

**This file is the reference root.** `inventory.json` is the machine-readable
index; `remediation_ledger.json` is the open-issue list.

> **Gate E does not exist at HEAD.** An earlier draft of this file described
> `inventory.json` as "what Gate E reconciles against", which asserted a CI
> gate nobody had built — the same class of defect as every entry in the
> shipped-defect table below, in the document meant to police it. The
> completeness critic caught it. Gate E is SPECIFIED here and UNENFORCED; it is
> hole H7 until a CI job reconciles doc ↔ inventory ↔ test tags and fails on
> anything unaccounted.

The source document is a **QA artefact, not a contract**. It sits below owner
adjudications, the Backend Schema, the TRD, the Surface Specification, the
Implementation Plan, the PRD and the QA Report. Where it contradicts one of
those, the contract wins and the contradiction is recorded here.

| | |
|---|---|
| Raw checks across the six curated slices | 2,139 |
| Canonical checks after dedupe | **463** |
| Inherited register references | 467 |
| **Dedupe ratio** | **4.62 : 1** |
| Registers | 16 |
| Surfaces included | 87 |
| Surfaces excluded (with mount evidence) | 19 |
| Shipped defects covered | **14 of 14** |
| Open holes (adopted but not enforced at HEAD) | 6 |

---

## 1 · Method, distilled

1. **Extract in canonical order.** Contract → payload → adapter → DOM →
   interaction → narrative. A check is written at the *earliest* layer that can
   refuse the defect. A rule enforceable at submit is worth more than the same
   rule at render, because the render check only fires for a run that already
   promoted.
2. **Every claim reconciles to its permitted source at the same grain.** The
   grain is the cell, not the category that contains it.
3. **Client-neutral throughout.** The reference institution is evidence of one
   implementation state, never an expected value and never a fixture constant.
   No client name, URL or figure appears in any check in this file.
4. **An absent component is a documented decision**, never another page's
   screenshot and never a silent pass.
5. **Evidence of a pass is a retained DOM + payload dump keyed by `qa_id`**,
   carrying route, entity, run, role, audience, viewport, timestamp and request
   or record id. A screenshot is illustration. The source document claims
   `Screenshot record - ATTACHED` on all 93 surfaces while its own §8.2 states
   that a screenshot cannot prove provenance; the artefact carries 100
   placeholder image refs with no image data behind them.
6. **Re-test before asserting.** Every FAIL in the source document is dated 14
   August. Several cite defects fixed on 14–15 August. A check that carries a
   stale FAIL forward is asserting history.

### RG-01..16 — release gate

| id | rule | verdict | layer |
|---|---|---|---|
| RG-01 | Every surface in the inventory is swept, with **targets derived from the router** so global chrome and overlays are covered, not page routes only. | AMEND | ci |
| RG-02 | The evidence record is a retained DOM + payload dump keyed by `qa_id`. A screenshot never substitutes for field provenance. | AMEND | ci |
| RG-03 | No client fact is an expected value. | ADOPT | narrative |
| RG-04 | Every rendered claim reconciles to its permitted source at the same grain. | ADOPT | payload |
| RG-05 | An unavailable or absent component is a documented failure or a not-applicable decision. | ADOPT | ci |
| RG-06 | All nine UI states are exercised on every surface that can reach them. | ADOPT | dom |
| RG-07 | Cross-surface reconciliation covers score, count, label **and lifecycle status**. | AMEND | payload |
| RG-08 | No client facts in fixtures. | ADOPT | ci |
| RG-09 | Keyboard operability and legibility at 320 px and 200 % zoom. | ADOPT | interaction |
| RG-10 | A dead or unreachable target is **blocking**, not a note. | AMEND | ci |
| RG-11 | Every shared contract a service reads is proven present **inside the built image**; the loader raises rather than degrading to `{}`. | ADD | ci |
| RG-12 | Contract path resolution is lazy and depth-independent; every module is imported under the image's directory depth. | ADD | ci |
| RG-13 | Every key a client module **reads** is written by an adapter and declared by a contract. | ADD | ci |
| RG-14 | A run promotes only with **fewer than 15 open alerts**, counted from the payload about to be written. | ADD | connector |
| RG-15 | A fix is reported live only after the deployed revision is compared to the commit containing it. | ADD | ci |
| RG-16 | The set of CI test targets equals the set of test directories discovered in the tree. | ADD | ci |

### Severity

- **P0** — blocks release. A wrong number, a wrong status, a missing required
  field, a fabricated claim, an inaccessible primary control, a leak across
  audience.
- **P1** — blocks sign-off but not deploy. Degraded interaction, a missing
  secondary state, a legibility failure at a supported viewport.
- **P2** — recorded, scheduled. Cosmetic or convenience.
- **P3** — observation only.

### Result vocabulary

| result | meaning |
|---|---|
| **PASS** | Executed at HEAD, evidence retained, assertion held. |
| **FAIL** | Executed, assertion did not hold. |
| **BLOCKED** | Could not execute — a dependency, a fixture or an environment prevented it. |
| **NOT-EXECUTED** | Never run. |
| **UNVERIFIED** | Run, but the result cannot be trusted — no evidence retained, or the deployed bytes were not proven to be the bytes under test. |

**BLOCKED is not a PASS.** Neither is NOT-EXECUTED and neither is UNVERIFIED.
All three are counted against the exit criteria, and a surface in any of those
three states blocks release exactly as a FAIL does. The source document carries
nine surfaces marked `NOT YET RE-EXECUTED` inside a document whose other
statuses are presented as measurement; it never says these block. They do.

**Every PASS is UNVERIFIED until paired with a deployed-bytes comparison.**
This is the exact gap that let four render fixes be reported live against a
revision built 58 minutes before those fixes existed.

### The nine UI states — not interchangeable

`loading` · `complete` · `sparse-valid` · `contradictory` · `quarantined` ·
`stale` · `unavailable` · `authorization-denied` · `responsive/AT variant`

They are nine different facts about the world. Collapsing any two is a defect:
*sparse-valid* (the producer searched and found little) is not *unavailable*
(nothing was asked); *quarantined* (a figure failed the identity gate) is not
*empty*. This is the general form of shipped defect 7 — a held field with a
297-character reason rendered as nothing at all, which is *complete-and-blank*
standing in for *quarantined*.

---

## 2 · The Baxter standard

The fourteen defects this build actually shipped, each with the check that now
catches it and where that check stands at HEAD.

| # | Shipped defect | Class | Caught by | Layer | State at HEAD |
|---|---|---|---|---|---|
| 1 | `enrichment_register.json` absent from the api image; loader swallowed `FileNotFoundError` into `{}`; 5 declared surfaces served without status while every test passed | repo-vs-image | **RG-11**, CI-15, HLT-ADD-01, OL-ADD-01, GS-10, DASH-07 | ci | **Enforced** — CI Gate D ships shared contracts into the image; the gap loader raises |
| 2 | `_register_paths` built `parents[3]` eagerly → `IndexError` in the 3-deep image layout, invisible in the repo | repo-vs-image | **RG-12**, CI-16, HLT-ADD-02, OL-ADD-02 | ci | **Enforced** — a repo-wide scanning test exists |
| 3 | 32 field paths null on 100 % of rows; 23 contract-asked and gated by nothing; no gate read ITEM keys; CG-18 wired to one field | contract coverage | **EN-01**, EN-02, CG-18, CID-ADD-01, OF-A1, SENT-ADD-01, OL-ADD-03, OFT-ADD-03, TL-ADD-01, INS-ADD-01 | connector | **HOLE 4** — machinery exists, declared on ~3 field specs only |
| 4 | A REMEDIATED regulatory matter drew as "→ open" while its drilldown said the opposite | cross-grain status | **ST-06**, C3-ADD-01, REG-014, IDM-ADD-01, NQ-11, CL-07, RG-07 | payload | Rule adopted; render-side reconciliation not yet asserted |
| 5 | 43 of 51 tech cards said "this run states no peer set" while the run named five; `data.js` read a key no adapter wrote | key provenance | **KP-04**, KP-01, TR-ADD-01, TTR-ADD-01, RG-13, WT-08 | ci | Instance fixed; **HOLE 2** — no gate prevents recurrence |
| 6 | Adapter read `cap_level`, a key no contract declares; contract's `capped_subcap_ids` had zero hits in the web tree | key provenance | **KP-01**, KP-02, IC-ADD-02, CID-ADD-02, WT-09 | ci | Instance fixed; **HOLE 2** |
| 7 | A HELD firmographic, quarantined *with* a 297-char reason, rendered no row at all | absence vocabulary | **AB-04**, OF-A3, C3-ADD-01, WT-11, INE-ADD-01, SENT-ADD-03 | dom | Rule adopted; coverage to confirm |
| 8 | `fmtPct(null)` → "0%"; `fmtAssets(0)` printed a stated zero identically to an unstated one | formatter honesty | **FM-01**, FM-02, FM-03, AB-05, OFT-ADD-01, WT-12, DASH-05, PROS-ADD-02 | dom | **Fixed** — regression guard |
| 9 | Duplicate CAGR row: pinned from the computed series *and* printed by the passthrough — two lists that drifted | list identity | **FM-04**, OF-A5, OFT-ADD-02, WT-13 | dom | **Fixed** — regression guard |
| 10 | 25 platform `peer_deployment` rows, each fully cited, rendered zero times | render reach | **KP-03**, TR-ADD-02, WT-10, PSS-03 | payload | Instance fixed; **HOLE 2** |
| 11 | A run promoted carrying 98 open alerts because nothing counted them | promote gate | **RG-14**, ALT-ADD-01, CI-18, H3-ADD-01, HLT-ADD-05, DASH-3.3, ALT-01 | connector | **Enforced** — `ALERT_CEILING = 15` at promote, with a test |
| 12 | `blocking_findings` promoted as JSON-encoded strings; CG-03 cannot see them because a serialised object *is* a valid string | type blindness | **CG-21**, INS-ADD-03, IDM-ADD-02, CI-19 | connector | **Enforced** — CG-21 refuses leaves that parse as JSON |
| 13 | Four render fixes reported live; deployed revision built 58 minutes *before* they were committed | deploy-vs-commit | **RG-15**, CI-14, HLT-ADD-03, INS-ADD-04, UA-09 | ci | **HOLE 1** — `verify_deployed.py` exists, wired nowhere |
| 14 | CI ran `apps/worker` and `apps/mcp` only; the API's 251 tests and the whole web suite had never run | suite coverage | **RG-16**, CI-01, TA-13, HLT-ADD-04, INS-ADD-05, DIR-A3 | ci | **HOLE 5** — api + web now run; lint, types, a11y, browser gate, smoke absent |

### Holes — adopted but not enforced at HEAD

A defect whose covering check exists only as prose is not covered. These six
are named so they cannot be quietly counted as done.

| # | Hole | Bears on | Evidence |
|---|---|---|---|
| **H1** | **`scripts/verify_deployed.py` is referenced by neither `.github/workflows/ci.yml` nor `infra/`.** Nothing compares deployed bytes to HEAD. | defect 13 | `grep -rn verify_deployed .github/ infra/` → no matches |
| **H2** | **No key-provenance gate exists.** Defects 5, 6 and 10 were each fixed by hand, three times, in the same class. Nothing stops the fourth. | defects 5, 6, 10 | no script or test cross-references read keys against written keys |
| **H3** | **No mount-parity gate.** Five components are defined, exported and mounted nowhere — `CoverageByPillarCard`, `EvidenceTierCard`, `CeilingEstimateCard`, `FinancialTrajectoryCard`, and `LiveClientPage`, a 2,694-line page pack `app/route.js` ships to every browser regardless. Gate C covers em-dash dead ends, not dead components. | doc's own dead surfaces | each has exactly 6 grep hits: definition, comment, export, and their compiled twins |
| **H4** | **ITEM-key census not enforced.** `must_present` machinery exists in `validation.py`, but is declared on roughly 3 field specs across the registry. 23 contract-asked ITEM keys remain ungated. | defect 3 | `grep -c must_present packages/shared/contracts_data.json` → 3 declarations |
| **H5** | **CI lacks lint, type checks, accessibility, the browser QA gate and authenticated deployment smoke.** | defect 14 | `ci.yml` jobs: gates, schema-qa, python-tests, web-tests, promoted-client-audit |
| **H6** | **Only one promoted client is exercised.** The owner's instruction is to stress-test against **two**. The nine-sub-vertical fixture matrix the doc demands is unachievable from two real clients and must be declared synthetic or it becomes a licence to copy client facts into fixtures. | RG-03, RG-08, CO-04 | qa-gate defaults to a single reference entity |

---

## 3 · Owner adjudications

These supersede the document wherever they meet it. The document predates all
seven.

**A — "Never place an em dash."** An empty field is enriched and shown, or its
row is omitted.
*Supersedes:* Firmographics §8.3 ("an unknown field renders an em dash, never
a guess and never a dict repr"), restated in Overview §1. → `AB-01`, `OF-01`.
Enforced at HEAD by CI Gate C.

**B — "It should not state queued for enrichment or held. It should enrich and
clarify real time and give the real data."** No workflow vocabulary reaches the
reader.
*Supersedes:* the `UNWORKED / WORKED_FOUND / WORKED_ABSENT` states required
across eleven surfaces; Alerts §1; Rerun feedback §8.3's "queued, validating,
ingesting, synthesizing, challenging, promoting" as required user-visible
content; the boilerplate "state unknown, sparse, quarantined, not-run and
not-comparable conditions explicitly." → `AB-02`, `ALT-02`, `HRR-01`, `HTA-03`.
Admissible **only** on the analyst-gated Health view.

**C — When a value genuinely cannot be sourced: omit the row.** Chosen over a
plain statement and over a best-guess value.
*Supersedes:* every "render the field as unavailable" instruction. → `AB-03`.

**D — `revenue` is sub-vertical conditional, not universal.** A credit union
has no revenue line.
*Supersedes:* Firmographics §8.3's universal must-present set, which its own
§8.5 sub-vertical table contradicts in the same section; and `WT-02`, which
asserts financial fields as a uniform expectation while Prospecting §8.5
contradicts it in the same document. → `CO-03`, `OF-A2`, `WT-02`, `PROS-02`.

**E — Four maturity bands only.** `M5` / "Transformational" must not exist in
code, enum, payload or prose.
*Supersedes:* the Ceiling surface's `M1-M5` scale and `OCU-08`'s exemplar
"cap M3 applied" — and the Surface Specification's own O1b, which is flagged
upward. → `BD-02`. Also corrects the doc's Hero §8.3, which writes the band word
as "Competitive"; the enum is **Activating · Building · Competing ·
Differentiating**, strict less-than, on the raw score before display rounding.

**F — A run promotes only with fewer than 15 open alerts.**
*Supersedes:* the doc's treatment of "the Dashboard's 109 open alerts" as
context for a reconciliation failure. 109 is not a baseline to reconcile
against — it is a state that should never have promoted. → `RG-14`, `ALT-ADD-01`.
Enforced at HEAD.

**G — "There should be a working enrichment routine; not you doing it as Claude
Code."** Enrichment is a scheduled job, observable at
`GET /v1/ops/enrichment-loop`. → `AB-06`, `IMP-02`. Endpoint exists at HEAD.

---

## 4 · Registers

The document repeats the same check once per surface — 28 overlays each carry
the same six modal rules, 15 drawers each carry the same evidence rules. Each
family below is **one** entry; surfaces inherit it and record only their delta.
This is where the 4.62 : 1 dedupe lives.

### OV — Overlay behaviour · inherited by 28 overlays

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| OV-01 | One activation opens one correctly labelled overlay carrying the exact opener, client, run and audience context. | ADOPT | dom | P0 |
| OV-02 | Focus enters correctly, remains contained for modal overlays, background is inert. | ADOPT | interaction | P0 |
| OV-03 | Close, Escape and permitted backdrop close **once** and restore focus to the exact opener. | ADOPT | interaction | P0 |
| OV-04 | Header, body, footer and close remain reachable at 320×568 and 200 % zoom and are screen-reader navigable. | ADOPT | interaction | P0 |
| OV-05 | Loading, empty, auth, not-found, validation, conflict, rate-limit, server, timeout and offline states are distinct. | ADOPT | dom | P0 |
| OV-06 | A client, run, audience or route change cancels or ignores stale responses; no cross-context leakage. | ADOPT | interaction | P0 |
| OV-07 | Each overlay in a stack exposes a **distinct** accessible name on its close control. | ADD | interaction | P1 |

*OV-07 added:* the document observes duplicate Close names making stacked
overlays ambiguous, and asserts nothing about it.

### EV — Evidence integrity · inherited by 15 drawers

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| EV-01 | Membership equals the opener's set exactly — never a pillar-wide or all-client fallback. | ADOPT | payload | P0 |
| EV-02 | Every cited id resolves, belongs to this entity and run, and carries a verbatim 50–500 char excerpt. `foreign` halts production. | ADOPT | connector | P0 |
| EV-03 | `grounded_on` is the length of the citation array — computed, never stored. | ADOPT | payload | P0 |
| EV-04 | The ERS scale is identical between store and drawer; internal rationale is suppressed for customer audience. | ADOPT | payload | P0 |
| EV-05 | Dead or redirected URLs, duplicate and orphan E-IDs, private sources and a 10,000-char excerpt render deliberately. | ADOPT | dom | P1 |
| EV-06 | Coverage and evidentiary sufficiency are **separate metrics**; 100 % coverage never implies sufficient evidence. Both are measured from the promoted payload at test time. | AMEND | narrative | P0 |
| EV-07 | A source locator renders as an actual link, with its href resolving to the cited source. | ADD | dom | P1 |

*EV-06 amended:* the doc states this as a single-client measurement (749 cells,
699 thin IDs). The rule is right; the constants must never be hard-coded — a
fixed threshold turns one client's accident into an acceptance criterion.
*EV-07 added:* the doc records source URLs rendering as plain text on two
surfaces and issues no check for it.

### GR — Grain and rollup

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| GR-01 | The score chip and the anchor chip name the **same** cell. | AMEND | payload | P0 |
| GR-02 | Every aggregate cell ships both candidates, its `source_cell` and the `score_source` flag, so a disagreement is measurable rather than invisible. | ADOPT | payload | P0 |
| GR-03 | A stated rationale's leaf count and the actual leaf count agree at **every** grain. Zero tolerance. | AMEND | payload | P0 |
| GR-04 | A rollup equals the declared weighted or mean value of its scored leaves under a documented rounding rule, within the 0.05 grain tolerance. | ADOPT | connector | P0 |
| GR-05 | Expanded and collapsed totals never double-count. | ADOPT | payload | P0 |
| GR-06 | **P1C5 does not aggregate in a v7.0 run.** | AMEND | payload | P0 |
| GR-07 | Counts are computed, never stored where a source of truth exists. | ADOPT | payload | P0 |

*GR-01/GR-03 amended:* the rules are correct; the doc's supporting figures
("2.77 on 59 clients", "169 versus 36") are one client's measurements at best
and fabricated at worst. Measure at test time.
*GR-06 amended — a correction the document gets backwards:* `HCD-15` asks that
fragmented P1C5 variants "reconcile to the aggregate definition and do not
silently omit cells." P1C5 is the **killed 17th category**. v7.0 has 16
categories and all 31 P1C5 cells resolve `NOT_COMPARABLE`. In a v7.0 run there
is nothing to aggregate — it must render `NOT_COMPARABLE`. The aggregation rule
applies only to v5.0-pinned runs.

### BD — Maturity bands

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| BD-01 | Four bands, strict less-than, on the **raw** score before display rounding: `<2` Activating · `<3` Building · `<4` Competing · `≥4` Differentiating. | ADOPT | payload | P0 |
| BD-02 | `band_t` has exactly four values. `M5` / "Transformational" appears in no code, enum, payload or prose. | SUPERSEDED (adj. E) | ci | P0 |
| BD-03 | The DB generated column and the frontend resolver agree for every score in a golden run. | ADOPT | ci | P0 |
| BD-04 | No colour in any payload; score → band → hex in exactly one frontend module. | ADOPT | ci | P0 |
| BD-05 | Thin evidence is a dashed outline; fill means maturity and nothing else. | ADOPT | dom | P1 |
| BD-06 | A null score is no score — never zero. | ADOPT | dom | P0 |
| BD-07 | The band words are Activating, Building, Competing, Differentiating. | AMEND | dom | P0 |

### AB — Absence and enrichment

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| AB-01 | No em dash as a fallback anywhere. | SUPERSEDED (adj. A) | ci | P0 |
| AB-02 | No workflow vocabulary reaches the reader. | SUPERSEDED (adj. B) | dom | P0 |
| AB-03 | A value that genuinely cannot be sourced **omits its row**. | SUPERSEDED (adj. C) | dom | P0 |
| AB-04 | A field with a recorded held reason renders its row and the substance of that reason, in reader language. | ADD | dom | P0 |
| AB-05 | A stated zero is visibly distinct from an unstated value. | ADD | dom | P0 |
| AB-06 | Enrichment is a scheduled job, observable at `GET /v1/ops/enrichment-loop`. | ADD | ci | P1 |

### FM — Formatter honesty

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| FM-01 | Null in, null out, for every formatter. A null never answers with a measurement. | ADD | dom | P0 |
| FM-02 | `fmtAssets(0)` is visibly distinct from `fmtAssets(null)`. | ADD | dom | P0 |
| FM-03 | No formatter returns a sentinel that reads as data. | ADD | dom | P0 |
| FM-04 | The pinned-**row** list and the pinned-**key** list are one list; a pinned slot is excluded from passthrough, asserted by a duplicate-slot scan. | ADD | dom | P0 |

### KP — Key provenance · **HOLE 2**

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| KP-01 | Every key a client module reads is declared by a contract and written by an adapter. | ADD | ci | P0 |
| KP-02 | Every contract-declared field has at least one reader in `apps/web`. A zero-hit contract field fails the build. | ADD | ci | P0 |
| KP-03 | A promoted array with N > 0 rows renders N > 0 rows, or its omission is recorded with a reason. Served set and rendered set are **diffed**, not counted. | ADD | payload | P0 |
| KP-04 | A negative-state sentence is bound to the key carrying the fact it denies, and may not render when that key is non-empty. | ADD | dom | P0 |

### MT — Mount parity · **HOLE 3**

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| MT-01 | Every component defined in a page pack is mounted on a route or deleted. | ADD | ci | P0 |
| MT-02 | A declared surface resolving to no mounted component is EXCLUDE with grep evidence — never a silent pass. | ADD | ci | P0 |
| MT-03 | No page pack ships to the browser unmounted. | ADD | ci | P1 |

*MT-02 exists because the document issues P0 DOM checks against seven surfaces
it simultaneously reports as absent, five of them with an `ATTACHED` screenshot
of the place the surface would have been.*

### ST — State vocabulary

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| ST-01 | The nine UI states are distinct and never interchangeable. | ADOPT | dom | P0 |
| ST-02 | `not-run`, `unavailable`, `failed`, `waived`, `passed` are five distinct gate states; `not-run` carries an explicit reason. | ADOPT | payload | P0 |
| ST-03 | A failing safeguard **discloses and still promotes**; a failing evidence reason never does. | ADOPT | connector | P0 |
| ST-04 | An SG `plain_label` is 8–18 words. | ADOPT | connector | P1 |
| ST-05 | `caps[]` and `gates[]` are two arrays, never one blob. | AMEND | payload | P0 |
| ST-06 | A record's lifecycle status is identical at card face, detail tab, status arrow and drilldown; no arrow is derived from anything but the stored status field. | ADD | payload | P0 |

### Connector verdicts — CG / AG / SG / ET

| id | rule | verdict | layer | sev |
|---|---|---|---|---|
| CG-03 | Declared field types agree with delivered types. | ADOPT | connector | P0 |
| CG-18 | Every contract-asked ITEM key sits in a `must_present` set or a recorded waiver. | AMEND | connector | P0 |
| CG-21 | No payload leaf is a string that **parses** as a JSON object or array. | ADOPT | connector | P0 |
| EN-01 | Submit-time ITEM-key census: any contract-asked path null across all rows blocks, naming path and row count. An unparseable item shape is a FAILURE, not a skip. | ADD | connector | P0 |
| EN-02 | Registry coverage ratchet: the count of specs carrying `must_present` may not fall, and a new ITEM key without one fails. | ADD | ci | P0 |
| AG-01 | Analysis gates name the gate, the JSON path and the arithmetic. | ADOPT | connector | P0 |
| SG-01 | Safeguard results render with `plain_label` and an explicit `NOT_RUN` reason. | ADOPT | connector | P0 |
| ET-01 | Entity and identity gates resolve to this entity and run. | ADOPT | connector | P0 |
| CG-GRAIN | Contract and grain agreement within the 0.05 tolerance. | ADOPT | connector | P0 |

*CG-21's own source comment states the reasoning better than the doc does: CG-03
"cannot see this and never will — it asks whether a list's items are the
declared type, and a JSON-encoded object IS a valid string." This is why the
serialised-leaf rule needs its own gate rather than a widening of an existing
one, and why defect 12 is a distinct class.*

### NQ — Narrative and data integrity

`NQ-01`..`NQ-12` adopted, with two amendments:

- **NQ-06** — a signal may not be the assessment itself (circular). Rule
  adopted; the doc's "shipped on 11 clients" discarded.
- **NQ-11** — add lifecycle status to the reconciled attribute set. Also: the
  doc's "765 subcapabilities" is an unsourced served-cell subset naming no
  catalogue. v7.0 is 851 cells across 16 categories; v5.0 is 836 across 17. A
  served count is a per-run subset and must say so — this is exactly the grain
  slippage NQ-11 exists to catch, committed by the document itself.

### CI / TA — test-system

| id | rule | verdict | state at HEAD |
|---|---|---|---|
| CI-01 | Every suite in the tree runs in CI. | AMEND | api + web **fixed**; lint, types, a11y, browser gate, smoke **absent** |
| CI-14 | Deployed bundle compared byte-level against a local build of HEAD; "could not compare" is FAIL. | AMEND | **HOLE 1** |
| CI-15 | Shared contracts ship in the image; loader raises. | ADOPT | enforced (Gate D) |
| CI-16 | No eager `parents[N]`; modules imported at image depth. | ADOPT | enforced |
| CI-17 | Submit-time ITEM-key census. | ADOPT | **HOLE 4** |
| CI-18 | Promote blocks at ≥ 15 open alerts. | ADOPT | enforced |
| CI-19 | Serialised-leaf gate. | ADOPT | enforced (CG-21) |
| TA-07 | A required production-path test that **skips** fails the job. | AMEND | not enforced |
| TA-11 | Name the code path, image digest and suite. A count of test *files* is not a measure of coverage in either direction. | AMEND | — |

*TA-11 amended because the document places "318 backend and 67 frontend test
files" for the legacy snapshot beside "four JavaScript test files" for the
active web, correctly notes the legacy count cannot be reported as coverage,
and then uses the active figure as a current measure anyway.*

### BAX — neutral loophole rules

`BAX-01`..`BAX-15` are all **AMEND**: re-expressed client-neutrally. The
document's §10 register is built on a named promoted client, cites ten of its
URLs and quotes its assets, engagement percentages, NPS, app-store rating and
count. Its own §10 scope note and §8.6 forbid encoding a named reference client
as expected output, and its counterchecks 1–6 restate the sources inline
without the non-normative caveat. **No URL, name or figure was carried into any
check in this file.** The neutral rules are in `remediation_ledger.json` under
`bax_id`.

### Composition oracle and sub-vertical matrix

| id | rule | verdict |
|---|---|---|
| CO-01 | Pillar weights are **read from the run manifest**, never asserted. §8.3 and the 9.x profiles hardcode 25/30/20/25 as acceptance facts; weights belong to the manifest. | AMEND |
| CO-03 | The must-present set is sub-vertical conditional. | SUPERSEDED (adj. D) |
| CO-04 | The nine-sub-vertical fixture matrix can only be **synthetic** with two real clients, and must declare itself so — unqualified it is a licence to copy client facts into fixtures, which RG-08 forbids. | AMEND |
| CO-06 | Classification precedes composition; the classifier's output is read from the run, never inferred by the test. | AMEND |

---

## 5 · Surfaces

87 included surfaces. Each inherits the registers listed and records only its
delta. Full machine-readable form — every `qa_id`, verdict, layer, severity and
defect linkage — is in `inventory.json`.

### Global shell and navigation

**Global Shell and Auth** (doc 354) · inherits RG-01, RG-02, ST-01
`GS-01`..`GS-06` ADOPT. `GS-04` AMEND — the post-auth destination must be
asserted **cross-entity**, not only on the default entity. `GS-10` ADD (P0,
dom) — a swallowed contract read renders an error state, not an empty one
*(defect 1)*.

**Global navigation and responsive** (495) · `NAV-01`..`NAV-05` ADOPT.

**Global nav — Search popover** (621) · inherits OV
`SRCH-01`..`SRCH-06` ADOPT. `SRCH-10` AMEND — the doc requires search to match
"name and display ID"; the shipped matcher searches name and domain and never
the display id. **The doc asserts a behaviour nobody built and calls it P0
without flagging the gap.** Recorded as a genuine spec-vs-implementation
conflict (BAX-33) rather than silently adopted.

**Global nav — Notifications popover** (757) · inherits OV
`NOTF-01`..`NOTF-04` ADOPT. `NOTF-05` AMEND (P0) — the unread count reconciles
with the Alerts page and the Dashboard *(defect 11)*.

**Global nav — Settings popover** (887) · `SET-01`..`SET-05` ADOPT.

**Global client context bar** (1021) · `CB-01`..`CB-05` ADOPT.

**Client bar — Run selector** (1148) · inherits OV
`RSEL-01`..`RSEL-05` ADOPT. `RSEL-11` AMEND — the doc demands a 100-run
execution; with two clients this is a **synthetic fixture** and must be declared
one, never presented as a corpus measurement.

**Global universal actions** (1278) · `UA-01`..`UA-06` ADOPT, `UA-04` AMEND —
a control reporting completion must prove the write. `UA-09` ADD (P0) — no
surface reports an action complete on the strength of a client-side toast
*(defect 13 class)*.

**Universal — Intake modal (NewRunModal)** (1409) · inherits OV
`INTK-01` AMEND — **the doc's status is stale.** It records "No Request DMA
control or modal entry point was rendered." `NewRunModal` *is* mounted at
app-root and opened from Dashboard and Clients. The real defect is different:
the submit is fake. `INTK-04` ADD (P0) — the three-step confirm produces a
server-side run record; a toast is not a submit.

**Universal — Evidence drawer** (1536) · inherits OV + EV · `UED-01`..`UED-06` ADOPT.
**Universal — Recommendation modal** (1682) · inherits OV · `URM-01`..`URM-03` ADOPT.
`URM-04` ADD (P0) — provenance reads `analyst` or `synthesised`, never blank.
*The rule is real; the doc's "32 clients shipped synthetic recs laundered as
analyst output" is not — and the same fabricated 32 appears verbatim in the
Surface Specification, so the contract carries the fabrication too. Flagged
upward.*
**Universal — Intelligence panel** (1814) · inherits OV · `UIP-01`..`UIP-04` ADOPT.

### Dashboard and Clients

**Dashboard** (1941) · inherits RG-07, ST-06
`DASH-01`, `DASH-02`, `DASH-05` ADOPT. `DASH-3.3` AMEND (P0) — the alert count
reconciles three ways: Dashboard, Alerts page, notification bell. `DASH-06` ADD
— the tile is computed from the same payload the promote gate counted.
`DASH-07` ADD — an empty tile from a failed contract read renders an error
state, never a zero *(defect 1)*.

**Dashboard — New assessment** (2067) · inherits OV · `DNA-01`, `DNA-02` ADOPT.

**Clients** (2311) · `DIR-01`, `DIR-03`..`DIR-05` ADOPT. `DIR-02` AMEND (see
SRCH-10). `DIR-A1` ADD — header and rows read **one** materialised view; a
header count and a row count computed by different paths drift. `DIR-A3` ADD —
the directory suite runs in CI *(defect 14)*.

**Clients — New run** (2437) · inherits OV · `CNR-01` ADOPT, `CNR-02` AMEND —
this and "Clients - Request DMA modal" describe **one** control.

### Overview

**Overview** (2679) · `OV-A1`, `OV-A3` ADOPT. `OV-A2` AMEND — the hero ring and
the run row agree to the displayed precision. *The doc's "disagreed at 1dp on 26
clients" cannot be true; this system has two.*

**Overview — Header and actions** (2788) · `OH-01`..`OH-03` ADOPT.

**Overview header — Scorecard export** (2911) · inherits OV
`OEX-01`..`OEX-03` ADOPT. `OEX-04` ADD (P0) — an export that cannot be proven
complete is **BLOCKED, not PASS**. The doc records "export completion was not
proven" on three surfaces and passes them anyway.

**Overview header — Meeting prep panel** (3160) · inherits OV · `OMP-01`..`OMP-03` ADOPT.

**Overview — Hero maturity card** (3409) · inherits BD
`OHERO-01`, `OHERO-02` ADOPT. `OHERO-A1` AMEND — band vocabulary (adj. E).

**Overview — Firmographics** (3542) · inherits AB, FM
`OF-01` SUPERSEDED (adj. A/C — the em-dash rule; HEAD already implements
omission). `OF-A2` SUPERSEDED (adj. D — revenue is sub-vertical conditional;
§8.3 contradicts its own §8.5 table in the same section). `OF-A1` ADD
*(defect 3)*, `OF-A3` ADD *(defect 7)*, `OF-A4` ADD *(defect 8)*, `OF-A5` ADD
*(defect 9)*. **This one surface carries four of the fourteen shipped defects.**

**Overview — Why Now** (3673) · `OWN-01`, `OWN-02` ADOPT. `OWN-A1` AMEND — a
signal may not be the assessment itself.
**Why Now — Signal drilldown** (3808) · inherits OV, ST-06 · `OWD-01`, `OWD-02` ADOPT.
**Why Now — Evidence drawer** (3931) · inherits OV + EV · `OWE-01` ADOPT.

**Overview — Executive Summary** (4074) · `OES-01`..`OES-03` ADOPT.
**Executive Summary — Evidence drawer** (4206) · inherits OV + EV · `OESE-01` ADOPT.

**Overview — Opportunity surface** (4349) · `OO-01`, `OO-02` ADOPT. `OO-A1`
AMEND — **re-tested at HEAD 2026-08-15: FIXED.** The doc reports "displayed
ranks did not follow the displayed scores"; the list is now sorted by score
descending before render and rank *is* the sort. Carried as a regression guard,
not a live defect.

**Overview — Top findings** (4479) · inherits GR-01 · `OTF-01` ADOPT, `OTF-02` AMEND.
**Top findings — Finding drilldown** (4611) · inherits OV, ST-06 · `TFD-01`,
`TFD-02` ADOPT; `TFD-8C-06` AMEND — the release-linkage boilerplate is
unfalsifiable as written; bound to the 15-alert ceiling and a named commit.
**Top findings — Evidence drawer** (4737) · inherits OV + EV · `TFE-AM-01` AMEND
(grain rule kept, "59 clients" discarded), `TFE-ADD-01` ADD *(defect 5)*.

**Overview — Leadership** (4880) · `OL-01` ADOPT; `OL-ADD-01` *(defect 1)*,
`OL-ADD-02` *(defect 2)*, `OL-ADD-03` *(defect 3)* ADD.

**Overview — Financial trajectory** (5002) · inherits FM
`OFT-01` ADOPT. `OFT-ADD-01` ADD — **re-tested at HEAD: FIXED**, `fmtPct(null)`
returns null and `fmtAssets(0)` is distinct from unstated. `OFT-ADD-02` ADD —
**re-tested: FIXED**, the duplicate CAGR row is gone (computed wins, stated
falls back with its own basis). Both carried as regression guards.
`OFT-ADD-03` ADD *(defect 3)*.

**Overview — Sentiment** (5775) · `OS-01`, `OS-02` ADOPT.
`SENT-ADD-01`/`02` ADD — **the doc's own checks do not test its own required
content.** §8.3 requires "each bar names its source, its rating and its sample
size", and not one of `OS-01`..`OS-07` asserts that *n* is rendered. The
adapter already carries `n`, `scale` and `as_of` — a contract field adapted and
never drawn. `SENT-ADD-03` ADD *(defect 7)*.

**Overview — Thought leadership** (6026) · `TL-01` ADOPT, `TL-ADD-01` ADD.

### Insights

**Insights** (6146) · `INS-01` ADOPT; `INS-ADD-02` *(defect 11)*, `INS-ADD-03`
*(defect 12)*, `INS-ADD-04` *(defect 13)*, `INS-ADD-05` *(defect 14)* ADD.
**Insights — Insight cards** (6293) · `IC-AM-01` AMEND — every
`linked_subcap_id` resolves to a served cell, **zero tolerance**. The doc's "15
of 119 dead links" is one 14-Aug measurement on one client and must never
become a budget. `IC-ADD-02` ADD *(defect 6 — `capped_subcap_ids`, not the
phantom `cap_level`)*.
**Insights — Detail modal** (6422) · inherits OV, ST-06 · `IDM-ADD-01`
*(defect 4)*, `IDM-ADD-02` *(defect 12)* ADD.
**Insights — Evidence actions** (6562) · inherits OV · `IEA-01` ADOPT.
**Insights — Evidence drawer** (6687) · inherits OV + EV · `IED-01` ADOPT.

### Heatmap

**Heatmap** (7088) · inherits GR, BD-06, EV-06
`HM-01`..`HM-07` ADOPT. `HM-08` AMEND — export must be proven complete.
`HM-09` AMEND — uncertainty-band counts reconcile at the same grain, zero
tolerance; the doc's 749/699 and 169-vs-36 figures are measurements, not
thresholds. `HM-10` AMEND — focus-area quotes must be the **client speaking**,
verbatim, with a page number: not the scoring ledger's annotation, not a
cut-off diagnostic question, not machine scoring text. *The rule is excellent;
"57 of 138 clients had none" is fabricated.*

**Heatmap — Grid and drilldowns** (7285) · `HG-02`, `HG-04`..`HG-07` ADOPT.
`HG-01` AMEND — **P1C5 in a v7.0 run resolves NOT_COMPARABLE; there is nothing
to aggregate** (see GR-06). `HG-03` AMEND — selecting one capability displayed
all 40 subcaps of its parent category; a parent-wide result at a child grain is
a **grain defect**, not a UI nit. `HG-08` ADD — a blank category label is a
payload defect; assert every cell carries a catalogue-sourced label.

**Heatmap — Subcap synthesis drawer** (7413) · inherits OV + EV + GR ·
`HSD-07`..`HSD-13` ADOPT (`HSD-01`..`06` fully absorbed by OV).
**Heatmap — Category synthesis drawer** (7551) · inherits OV + EV + GR ·
`HCD-07`..`HCD-13` ADOPT. `HCD-14` AMEND — generalised to every category, zero
tolerance. `HCD-15` **SUPERSEDED** — P1C5 is the killed ESG category.
**Heatmap — Evidence drawer** (7691) · inherits OV + EV · `HME-07`..`HME-12` ADOPT.
**Heatmap — Cell evidence drawer** (7834) · inherits OV + EV · `HCE-01` AMEND —
`SURF-01` as written ("execute every component and subsection above") is the
generic execution instruction restated and asserts nothing; bound to cell
membership and the `grounded_on` arithmetic. `HCE-02` ADD — the source locator
renders as a link.
**Heatmap — Focus areas** (7957) · `HF-01`..`HF-06` ADOPT. `HF-07` ADD (P0) —
focus cards shipped as clickable divs with no role, accessible name or keyboard
tab stop; assert all three on every card.
**Heatmap — Focus detail** (8085) · inherits OV · `HFD-01`..`HFD-07` ADOPT,
`HFD-08` AMEND — an empty linked-insight state omits its row (adj. C).
**Heatmap — Thin-evidence alerts** (8462) · `HTA-01` AMEND — the run reported
**zero** thin cells, so the denominator and eligibility rule must be proven
before a zero is accepted; *a zero that nothing computed is defect 11's class.*
`HTA-02` AMEND — renders under Analyst Health, not Heatmap; re-pointed.
`HTA-03` SUPERSEDED (adj. B).
**Heatmap — Safeguard gates** (8584) · inherits ST · `HSG-01` AMEND (re-pointed
to Health), `HSG-02` ADOPT, `HSG-03` ADD — the promoted run carries an **empty**
gate array; build positive, failed, waived and unavailable fixtures. *The
emptiness is real at HEAD; the doc's "all 93 committed client packages" is not.*

### Platform

**Platform** (8705) · `PLAT-01`..`PLAT-08` ADOPT, `PLAT-09` AMEND — export
completion unproven and ranking not reconciling to displayed scores are both P0
and neither may pass unproven.
**Platform — Stair-step curve** (8802) · `PSS-01` AMEND — the doc records
`NOT YET RE-EXECUTED`, i.e. **no live result at all**. Mount **verified at
HEAD**: `StairstepCurve` is rendered from the D3/D4 page pack. An unexecuted
surface is UNVERIFIED and blocks release. `PSS-02` ADOPT. `PSS-03` ADD — the
"No stair-step ladder promoted for this run" empty state is reached only when
the array is genuinely absent, not when a key is misread *(defect 10 class)*.
**Platform — Affinity cards** (8851) · `PA-01`..`PA-07` ADOPT. `PA-08` AMEND —
rank **is** the sort. *The same class was fixed on the Overview opportunity
surface at HEAD; re-test whether this list received the same fix.*
**Platform — Fit breakdown modal** (8981) · inherits OV, GR-04 · `FIT-07`..`FIT-13` ADOPT.
**Platform affinity — Evidence drawer** (9118) · inherits OV + EV · `PAE-07` ADOPT.
**Platform — Recommendations** (9261) · `PR-01` AMEND — **the doc misroutes
this.** It holds *Insights* for having no Recommendations section; the Surface
Specification places Recommendations on **Platform** (`platform.recommendations`
· `ClientPlatform` + `RecommendationModal`). The doc sits below the Surface
Specification; the contract wins. `PR-02` ADD (provenance).
**Platform — Recommendation modal** (9390) · inherits OV · `PRM-01`, `PRM-02` ADOPT.
**Platform recommendations — Evidence drawer** (9522) · inherits OV + EV · `PRE-01` ADOPT.
**Platform — Readiness gate** (9665) · `PRG-01` AMEND — "All 17 gates were
clickable" promotes one client's **instance count** to a release threshold; the
rail renders one row per distinct prerequisite, so the gate is the rule, not 17.
`PRG-02`, `PRP-S6` ADOPT.
**Platform — Conversation starters** (9785) · `PC-01` AMEND — the doc allows a
starter "explicitly framed as a question" while the producer's D4 starters are
talking points, and requires 45–90-word openers while the promoted starters are
60–90-word paragraphs. Read the bound from the contract, not the doc. `PC-02`
AMEND — the gate is non-duplication and evidence binding at whatever N the run
produced; "PASS - Five non-duplicative starters" is one run's count.
**Platform — Copy confirmation toast** (9910) · `PCT-01` ADOPT, `PCT-ADD-01`
ADD — what is copied equals what is displayed, byte for byte.
**Platform — Roadmap phases** (10028) · `PRP-01` AMEND (rule kept, "17 clients
did" discarded), `PRP-02` ADOPT.

### Context

**Context** (10149) · `CTX-01` ADOPT. `CTX-04` AMEND — the doc's "committed
data exceeded the allowed defaulted-date rate" **states no rate and no
allowance anywhere in the document**; the surviving rule is that dates are
validated at ingestion *and again* at render. `CTX-05` AMEND — a sparse
timeline declares itself; "16 clients had two or fewer events" does not survive.
**Context — Timeline and issue register** (10438) · `CTIR-01` AMEND — one matter
must not ship as many rows *(the named third-party anecdote is not evidence
about this build)*. `CTIR-S5` AMEND *(defect 4)*. `CTIR-S6` AMEND — §3.1
"Dated event sequence" carries **dependency-graph accept clauses** (acyclic
ordering, gates, prerequisites) copy-pasted from the roadmap surface; a timeline
has no gates and no cycles. Replaced with monotonic ordering and date validity.
**Context — Evidence drawer** (10571) · inherits OV + EV · `CED-01` ADOPT.
**Context — Event detail** (10714) · inherits OV, ST-06 · `CEV-01` ADOPT.
**Context — Issue detail** (10835) · inherits OV, ST-06 · `CID-S2` ADOPT
*(defect 4)*; `CID-ADD-01` *(defect 3)*, `CID-ADD-02` *(defect 6)* ADD.
**Context — Regulatory standing** (10250) · `C3-AP` ADOPT, `C3-ADD-01` ADD
*(defects 4 and 7 together — a searched-and-held field renders a row naming the
field and the substance of the reason; a REMEDIATED matter may not draw as
open)*, `C3-01` AMEND (NOT YET RE-EXECUTED → UNVERIFIED, blocks release).
**Context — Acquisitions** (10346) · `C5-01` AMEND (UNVERIFIED).

### Health, Tech Stack, Runs and analyst surfaces

**Health** (10956) · inherits ST, RG-14
`HLT-02` ADOPT *(defect 11)*; `HLT-ADD-01`..`05` ADD *(defects 1, 2, 13, 14,
11)*. `HLT-03` AMEND — **the doc asserts as fact that "the register is
payload-produced; the legacy deriver is switched off."** At HEAD the page still
calls the legacy alert deriver, which walks subcap thin flags rather than the
promoted alerts section. *The doc records a fix that did not happen.*
`HLT-04` AMEND — the review basis names the wrong files for every Health
surface; a reviewer following the doc opens the D3 heatmap pack while
`ClientHealth` and `VersionDiff` live in the D5/D6 pack.

**Health — CSV export** (11301) · `HCSV-01` AMEND — **§3.5 is titled
"Formula-injection and delimiter safety" and its accept clause is
numeric-recompute boilerplate.** Nothing in it tests injection. Replaced with a
real suite: leading `=`, `+`, `-`, `@`, tab and CR; embedded quotes, commas and
newlines; encoding asserted. `HCSV-RG` ADOPT.
**Health — Rerun feedback** (11426) · `HRR-01` SUPERSEDED (adj. B). `HRR-02`
AMEND — the doc's `CQ-01` is *"Countercase … : SURF-01 - P0 - Execute every
component and subsection above"* — the generic execution instruction restated as
its own countercase, asserting nothing. Replaced with the out-of-order-attempt
countercase from the surface's own §8.6. `HRR-RG` ADOPT.

**Tech Stack** (11550) · `TECH-01` **SUPERSEDED** — the doc's source contract
lists layer keys `core / crm / data / integration / channel / security`. The
build's keys are **OPS · CUST · DATA · INFRA**, chosen precisely because
L2–L5-style keys collide with the L1–L4 evidence levels rendered on the same
card. `TECH-02` AMEND — status is **required per row** with four values
(`CONFIRMED · INFERRED · CLAIMED · ABSENT`); the prototype's three-status set is
superseded. `TECH-07` ADOPT.
**Tech Stack — Technology rows** (11642) · inherits KP · `TR-01` ADOPT.
`TR-04` AMEND — the negative-evidence and search-scope contract is proven **per
source type**; "86 of 93 committed clients" is fabricated. `TR-ADD-01`
*(defect 5)*, `TR-ADD-02` *(defect 10)*, `TTR-ADD-01` *(defect 5)* ADD.
**Tech Stack — Evidence actions** (11770) · `TEA-01` AMEND — **the required-content
list is the Heatmap cell-evidence contract copied verbatim**: anchor chip,
"N evidence items · score X · CONFIDENCE", `supports:` chips. A
technology-detection record has no cell score and no cross-cell supports
relation. Adopting it would **invent fields**, which the authority order forbids.
**Tech Stack — Evidence drawer** (11894) · `TED-01` AMEND (same copied contract).
**Tech Detail** (12037) · inherits OV · `TD-01`, `TD-02` ADOPT.

**Runs** (12164) · `RUN-01` ADOPT. `RUN-09` **EXCLUDE** — "All 93 committed
clients have exactly one ACTIVE run" passes vacuously over a population that
does not exist. `RUN-10` AMEND — "765 subcapabilities" is an unsourced
served-cell subset naming no catalogue.
**Runs — Rerun assessment** (12300) · `RRA-01` AMEND — **re-tested: the
trigger-rerun control is still a stub at HEAD.**
**Alerts** (12546) · `ALT-01` AMEND *(defect 11)*, `ALT-02` SUPERSEDED (adj. B),
`ALT-ADD-01` ADD (adj. F).
**Prospecting** (12675) · `PROS-01` AMEND — **re-tested: the crash is still live
at HEAD.** `PROS-02` SUPERSEDED (adj. D). `PROS-ADD-02` ADD *(defect 8)*.
**Admin** (12803) · `ADM-01` ADOPT.
**Import and Jobs** (12933) · `IMP-01` ADOPT, `IMP-02` ADD (adj. G).
**Import Audit** (13064) · `IMA-01` AMEND — **re-tested: still live at HEAD.**
**Login and Errors** (13193) · `LOG-01`, `LOG-02` ADOPT.
**Narrative and Data Integrity** (13329) · `REG-014` ADD *(defect 4)*.
**Test-System Audit** (13632) · `REG-007` AMEND (**re-tested: still live**),
`TA-13` AMEND — the doc's CI finding is **half solved**; adopting it verbatim
would report a solved problem and hide the unsolved remainder.

---

## 6 · Excluded surfaces, with mount evidence

19 surfaces. Each carries the check that proves the exclusion. **None was
excluded on the document's own say-so** — the document reports several of these
as FAIL *and* attaches a screenshot claiming to evidence them.

| Surface | doc | Evidence |
|---|---|---|
| Overview — Source quality banner | 3286 | `grep -rniE 'sourcequality\|source_quality' apps/web` → **0 hits**. The Overview page renders header, SnapshotStrip, WhyNowStrip, SCQACard, OpportunitySurfaceStrip, TopFindingsCard, LeadershipPanel, FinancialTrajectoryD1, SentimentCard, ThoughtLeadershipPanel — no banner. *The doc concedes the absence and still issues seven P0 DOM checks.* |
| Overview header — Rerun modal | 3034 | No rerun modal exists. The header renders one button whose `onClick` pushes a toast. `drawers.jsx` exports only EvidenceDrawer, InsightModal, IntelligencePanel, RecommendationModal, NewRunModal. `ORR-01..11` assert a dialog that does not exist; the underlying fake-completion defect is carried at `UA-09` / `INTK-04`. |
| Overview — Coverage by pillar | 5131 | `CoverageByPillarCard` — **6 grep hits**: definition, comment, export, and their three compiled twins. Nothing mounts it. The Overview pack records the removal from D1 on 2026-08-05: these cards report on the assessment's own workings, which is D7 Health's job. |
| Overview — Evidence tiers | 5259 | `EvidenceTierCard` — identical 6-hit dead-definition pattern. |
| Overview — Ceiling and uncertainty | 5379 | `CeilingEstimateCard` — identical pattern. **Additionally specified on an M1–M5 scale** with an exemplar reading "cap M3 applied", which adjudication E forbids outright. |
| Ceiling — Detail accordion | 5507 | Child of an unmounted card. |
| Ceiling — Evidence drawer | 5633 | Child of an unmounted card. |
| Overview — Sentiment detail | 5905 | **Excluded as routed.** DD-12 is specified as an inline open from a sentiment context tile (`SentimentGridInteractive`), which is mounted on the **Context** page, not Overview. The doc's observed FAIL measures the Overview bars against a Context contract. Checks survive, re-pointed. |
| Universal — Request DMA modal | 1409 | `grep 'Request DMA' apps/web` → **0 hits**. Exactly one intake modal exists (`NewRunModal`, mounted at app-root, opened from two page-header buttons). Merged into "Universal — Intake modal". |
| Dashboard — Request DMA modal | 2185 | **Duplicate** of the same single mounted modal. |
| Clients — Request DMA modal | 2553 | **Duplicate.** The doc concedes at its own line 2565 that the live Clients page has no Request DMA action. |
| Runs — Request DMA modal | 12419 | Specified across 22 headings with 12 P0 checks while its own observed result states "No Request DMA control or modal is rendered on Analyst Runs." Verified absent. The twelve overlay rules are salvaged onto the OV register. |
| Heatmap — Archetype control | 8212 | `grep -rni 'archetype' apps/web --include=*.jsx --include=*.js` → **0 hits**. No control, popover, state, URL param or export field anywhere in the web tree. The doc's own observed result agrees, and it still issues six P0 checks. |
| Heatmap — Archetype popover | 8333 | Child of a control with zero hits. `HAP-01..07` assert a listbox that does not exist; the doc's `CQ-01` for this surface is `HAP-01` restated as its own countercase, asserting nothing. |
| Heatmap — Value-chain view | 7237 | The only mount is inside the unmounted `LiveClientPage` pack, which declares `value_chain` **ENVELOPE_ONLY**: "no contract field exists to promote yet." Nothing to assert against. |
| Heatmap — Evidence store | 7187 | No separate store surface is mounted; the census it describes is the **EV register**, asserted at the connector and on each drawer. |
| Context — Sentiment overview | 10298 | `context_sentiment` is declared **ENVELOPE_ONLY** — the D5 sentiment contract names no payload field yet. C4 requires tiles "expanding inline to the items behind it"; there is nothing to expand. |
| Context — Financial series | 10394 | **Excluded as routed.** The Context section list is timeline, issue_register, regulatory_standing, context_sentiment, acquisitions. `financial_series` is registered under **Overview**; C6's checks are carried on "Overview — Financial trajectory". |
| Health — H3 / V1 / H5 / H7 / H8 | 11063 | Five sub-surfaces carrying `NOT YET RE-EXECUTED` and stale file references. Their substantive checks are carried on "Health"; they are not separately mountable. |

**Also found, and the document does not notice it at all:** `pages-live-client.jsx`
is 2,694 lines defining ~50 `Live*` components and `LiveClientPage`, which is
referenced only by its own definition and its `window` assignment. `app/route.js`
ships it to every browser regardless. A page pack this size shipping unmounted
is the same class as the three named dead cards — hence `MT-01`..`MT-03` and
**HOLE 3**.

---

## 7 · Problems found in the source document

### 7.1 Fabricated corpus statistics

**This system has two promoted clients.** Every population claim above 2 is
fabricated and must never seed a fixture, a threshold, a denominator or a
regression baseline. Each is struck; where the underlying *rule* is sound, the
rule is carried without the number.

| Claim | doc | Disposition |
|---|---|---|
| "the committed 93-client corpus" | 2007 | struck |
| "All 93 committed clients have exactly one ACTIVE run" | 12241 | `RUN-09` EXCLUDE — passes vacuously |
| "All 93 committed client packages have empty safeguard_gates" | 11034 | emptiness is real at HEAD; denominator struck |
| "86 of 93 committed clients contain absent-technology rows" (×2) | 11621, 11709 | struck; contract proven **per source type** instead |
| "57 of 138 clients had none" (focus areas) | 7098 | struck; the verbatim-quote rule survives as `HM-10` |
| "a hero ring and a run row that disagreed at 1dp on **26** clients" | 2693 | struck; `OV-A2` survives |
| "'completed a Digital Maturity Assessment' shipped on **11** clients and is circular" | 3785 | struck; `OWN-A1` / `NQ-06` survive |
| "a cell serving 2.77 on **59** clients" (×4) | 4491, 4586, 4623, 4746 | struck; the grain rule survives as `GR-01` |
| "**32** clients shipped synthetic recs laundered as analyst output" (×4) | 6839, 9533, 9676, 9797 | struck; provenance rule survives as `URM-04` / `PR-02`. **The same 32 appears verbatim in the Surface Specification — the contract carries the fabrication too. Flagged upward.** |
| "Phase order must not contradict prerequisites (**17** clients did)" | 10125 | struck; `PRP-01` survives |
| "**16** clients had two or fewer events" (×4) | 10165, 10448, 10583, 10721 | struck; declare-sparse rule survives |
| "dead links were **15 of 119**" | 6394 | one 14-Aug single-client measurement; carried as **zero tolerance**, never a budget |
| "749 heatmap cells and 699 thin-evidence IDs"; "100 % coverage plus 93.3 % thin cells" | 7088, 3350 | single-client measurements stated as properties; must be **measured at test time**, never hard-coded |
| "All 17 gates were clickable"; "PASS - Five non-duplicative starters" | 9672, 9741, 9866 | instance counts promoted to release thresholds |
| Named third-party client anecdote ("shipped 13 rows for one matter", ×3) | 10165, 10448, 10846 | one-row-per-matter rule kept; the anecdote is not evidence about this build |

### 7.2 Internal contradictions

1. **The same number is both reconciled and irreconcilable.** Line 24 lists
   "Analyst Alerts reports zero open alerts across zero entities and Dashboard
   reports 109" as a P1 blocker; line 1947 says "109 open alerts … reconciled".
2. **Firmographics §8.3 contradicts §8.5 in the same section** — a universal
   must-present set including revenue, beside a sub-vertical table giving credit
   unions shares, loans, net-worth ratio and members and *no revenue line*.
3. **WT-02 contradicts Prospecting §8.5** on universal financial fields.
4. **Five surfaces claim `Screenshot record - ATTACHED` while reporting "no
   module was rendered."** A screenshot of an absent surface is an image of a
   page, not evidence about the surface — as the doc's own §1 says.
5. **Every surface claims an attached screenshot while §8.2 states a screenshot
   cannot prove provenance.** The artefact carries 100 placeholder refs with no
   image data.
6. **Three surfaces describe one control** (the Request DMA modals), and a
   fourth asserts 12 P0 checks against a surface its own observed result
   reports as non-existent.
7. **Two Health assertions of fact are wrong**: the legacy alert deriver is not
   switched off, and every Health surface's review basis names the wrong files.

### 7.3 Copy-paste and unfalsifiable checks

- **Health CSV §3.5** is titled "Formula-injection and delimiter safety" and its
  accept clause is numeric-recompute boilerplate. → `HCSV-01`.
- **Context §3.1** "Dated event sequence" carries dependency-graph clauses
  (acyclic ordering, gates, prerequisites) from the roadmap surface. → `CTIR-S6`.
- **Tech Stack evidence surfaces** carry the Heatmap cell-evidence contract
  verbatim, including a cell score and a `supports:` relation a detection record
  does not have. → `TEA-01` / `TED-01`.
- **`SURF-01`** — "Execute every component and subsection above" — appears as
  its own countercase on several surfaces, asserting nothing. → `HCE-01`,
  `HRR-02`.
- **The §8.4 cohesion sentence** ("This surface must reinforce the run thesis
  without duplicating a neighbor's job") appears identically in twelve headings.
  Naming no field, path or arithmetic, it can neither pass nor fail. Every
  instance amended to a concrete identity assertion — same anchor cell id, same
  run id, same denominator at origin and destination.
- **§8.3 / §9.x hardcode pillar weights** (25/30/20/25) as acceptance facts;
  weights belong to the run manifest and must be read. → `CO-01`.

### 7.4 Stale statuses — re-tested at HEAD `14f1016`, 15 August 2026

Every FAIL/PARTIAL in the document is dated 14 August, against commit `08a8f48`.

**Fixed since — carried as regression guards, not live defects:**
`fmtPct(null)` now returns null · `fmtAssets(0)` prints `$0` distinctly from
unstated · the duplicate CAGR row is gone · opportunity rank now follows the
sort · `ALERT_CEILING = 15` is enforced at promote with a test · CG-21 refuses
serialised-JSON leaves · CI Gate D ships shared contracts into the image · the
eager-`parents[N]` scanner exists · CI now runs api + scripts + web ·
`capped_subcap_ids` and `peer_deployments` are read.

**Still live at HEAD — confirmed by re-test:** the Prospecting crash · Import
Audit staleness · the Alerts-vs-Dashboard contradiction · the non-native switch
(`REG-007`) · the trigger-rerun stub · the intake modal's fake submit.

**Never executed at all:** nine surfaces marked `NOT YET RE-EXECUTED`. These are
UNVERIFIED and block release; the document does not say so.

**Half-solved, and dangerous to adopt verbatim:** the CI finding. Adopting
"CI does not run apps/api/tests" as written would report a solved problem and
hide the unsolved remainder (lint, type checks, accessibility, the browser gate,
authenticated smoke).

### 7.5 Where the document contradicts a higher contract

| Document says | Contract says | Winner |
|---|---|---|
| An unknown field renders an em dash | Owner adj. A / C | Adjudication |
| `UNWORKED` / `WORKED_FOUND`; "queued, validating, ingesting…" as user-visible | Owner adj. B | Adjudication |
| Revenue is universally required | Owner adj. D | Adjudication |
| Ceiling on an `M1-M5` scale; "cap M3 applied" | Owner adj. E, invariant 6 | Adjudication *(and the Surface Specification's O1b is flagged upward)* |
| 109 open alerts as a reconciliation baseline | Owner adj. F | Adjudication |
| Band word "Competitive" | Invariant 6 enum | Invariant |
| Recommendations belong to Insights | Surface Spec: `platform.recommendations` | Surface Spec |
| Tech layer keys `core/crm/data/integration/channel/security` | CLAUDE.md: `OPS · CUST · DATA · INFRA` | CLAUDE.md |
| 3 tech-stack statuses | `CONFIRMED · INFERRED · CLAIMED · ABSENT`, required | CLAUDE.md |
| P1C5 variants reconcile to an aggregate | v7.0 has 16 categories; all 31 P1C5 cells are `NOT_COMPARABLE` | CLAUDE.md adjudication |
| Search matches "name and display ID" | The matcher searched name and domain | **The document** — adjudicated 2026-08-15, see 7.6 (BAX-33) |

### 7.6 Two decisions taken 2026-08-15

**BAX-33 — the document was right; the app was fixed.** `DIR-02` and `SRCH-10`
both require entity search to match "name and display ID" and both mark it P0.
Measured at HEAD, three controls answered that one question three different
ways — the global popover and the directory filter matched name and domain, the
prospecting picker matched name alone, and **none of the three matched the
display id**. The display id is in the URL of every client page, on every alert
row and on the printed scorecard: it is the string a reader is most likely to
paste, and it was the one string that matched nothing.

The alternative — mark the check wrong and delete it — would have recorded a
directory that cannot find an entity by its own identifier as intended
behaviour. The rule now lives in one place (`entityMatches` in `utils.jsx`) and
all three controls call it, because three controls disagreeing about one
question is the drift class, not an accident. `DIR-02` and `SRCH-10` move
AMEND → **ADOPT**, and `entity-search.test.js` asserts both the behaviour and
the single-rule property, each proven to fail under mutation.

**The fabricated corpus reached the contract, and was removed there.** The
design documents assert corpus measurements throughout — "86 of 93 committed
clients", "32 clients shipped synthetic recs", "26 clients disagreed at 1dp".
This system has two promoted clients. In `docs/` those numbers are inert and
the files are read-only, so they are recorded here and flagged upward, not
edited.

But six of them had been copied into **`contracts_data.json`**, which is not a
document: `get_page_contract` returns each field's `doc` text and the synthesis
skill treats it as part of the contract, so the producer reads those clauses as
fact and calibrates on them. They were removed and each rule kept — "provenance
required, never blank" never needed a denominator. One of the six named a
client (`SunStrong`) inside prose that ships to every producer; that is either
client information in a shared file or a false measurement wearing a client's
name, and both are removals.

`test_contract_text_is_evidence.py` now fails CI on any corpus-scale claim or
client name in contract prose. It also closes a hole found while looking: the
runtime contract (`apps/mcp/dma_mcp/`) and the deploy source
(`packages/shared/`) are **two committed copies with nothing asserting they
agree** — a contract fix could validate against one shape and promote against
another.

---

### 7.7 What the document could not have found

Three defects surfaced on 15 August that no check in the source document
names, because all three are invisible from the outside: the payload is
correct, the promotion is correct, the suite is green, and the content is not
on the page.

**`platform_story` served 16 keys per platform and the page read two**
(`BAX-11`, and the reported "blanks instead of sourced or inferred"). The
ranked fit score, the readiness verdict, the estate reach, both pathways and
25 cited peer rows were promoted and shown nowhere. The cause was the page
breaking its own written rule — the story block was gated on the *derived*
tile-to-area join, so when that produced no area, all five stories vanished.

**`QA_GATES` returned `[]` under LIVE** while the run served one cap row and
two SG gates, every one cited. The card renders its heading and badge from
that array, so production showed `Safeguard gates · G01–G10` and `0 / 10 PASS`
over an empty table — a ten-gate denominator no run defines — while a
**failing** V4 grounding gate sat unrendered. The only `NOT_RUN` renderer in
the tree is in `pages-live-client.jsx`, which is mounted nowhere (H3).

**The enrichment job could not read `submissions`.** It scanned 287 runs,
printed `0 gap(s)` and exited 1. The summary line is the dangerous part: a
routine that cannot see the payloads reports the same number as one that saw
them and found nothing.

Finding the first took a hand census against a live payload. **Gate F** is
that census automated — it runs against the contract, so it needs no promoted
run, and it is ratcheted at 37 rather than zero because many declared keys
legitimately have no reader. Its baseline is now a worklist, and it caught its
own first improvement (38 → 37) on the commit that added it.

The general lesson the document's method cannot reach: **every one of these
was a read path missing under a correct write path.** The document tests what
a surface shows; nothing in it can ask what a surface was *given* and did not
show.

### 7.8 The worklist audit — nine items whose only closure was fabrication

With the enrichment loop finally running in production (287 runs · 7 gaps · 1
resolved · 6 recorded with reasons · 0 failed), the worklist it produces became
worth auditing rather than trusting. Every field the gap predicate can flag was
classified against its own contract doc, per page, and every false-positive
claim was then put to an independent skeptic that defaulted to refuting.

**Fourteen of twenty-three claims were refuted** — a real kill rate, and mostly
one mistake: treating "recomputed at read" as "do not send". Validated at
submit and not persisted are different statements, and only the second is what
invariant 8 governs. `insights.landscape.tiles`, `techstack.layers`,
`cell_evidence.linking_stats` and `evidence_coverage.item_count` are all
required at submit and all correctly gaps.

**Nine survived**, in three shapes: one predicate bug (`value_chain.fields` —
a phantom field manufactured by a falsy `{}`), two fields the producer *cannot*
author, and six whose absence is *mandated* in a stated state.

The pattern worth carrying: a check that tells someone to fix something they
must not fix is worse than no check. Every one of these would have pushed a
producer toward fabrication — the single worst outcome this system has — and
each was contradicted by the field's own contract text, which nothing was
reading.

### 7.9 The badge the owner reported four times, and why rewording it failed

The owner reported "scan did not run" on 14 August and three more times on 15
August, the last one after a fix had shipped. Both of the first two fixes were
real and neither reached the cause.

- **Fix 1** was the wording. `EnrichmentFlag` said "Scan did not run", which is
  a status of *our* pipeline — adjudication B's class, missed because it is
  phrased as a finding. Reworded to a statement about the reading.
- **Fix 2** was the cause, one layer down, and it was in the register. Three
  surfaces — firmographics, sentiment, thought leadership — declared `clay` as
  a source and declared **no way to observe it**: no `basis_key`, no
  `contact_keys`. `enriched` was therefore 0 for every run this product has
  ever promoted, `ran` was `false` by construction, and the component read
  `!s.ran`. **No payload could ever have cleared the badge.** Rewording it left
  a false statement on screen in better prose.

The reason no basis key exists is not an oversight — it is the shape of the
evidence. The synthesis skill requires citing the *source*, not the tool, so a
Clay-surfaced call report and a searched one produce an identical row. The
question is not false on those surfaces, it is **unanswerable**, and `false`
was invariant 9 exactly: a default that looks like data. `ran` is now
three-valued and serves `null` with its reason; the component tests
`=== false`.

Two further defects fell out of looking at the same file:

- `overview.sentiment` declared `"counts": "employee"` against a section whose
  list is `bars`. Every promoted run served `count: 0, thin: true` — "no
  retrievable rating carrying its sample size, scale and date was established"
  — beneath **seven rated bars**, while the connector's SG-S8 passed those same
  seven. Renderer and gate disagreed for the whole life of the feature because
  the container name was written in two files and compared in none.
- `_register_paths()` read the gitignored `apps/api/shared/` build artefact
  **before** the tracked `packages/shared/` source. In the image that ordering
  is invisible (the repo path is guarded out); in a checkout it meant the suite
  answered from a copy left behind by an earlier deploy. Caught by writing a
  test that failed for the wrong reason. Repo path now wins wherever it exists.

**REM-070 · REM-071 · REM-072 — closed.** Tests:
`test_counts_names_a_list_the_section_contract_actually_declares`,
`test_every_surface_declares_whether_ran_is_observable`,
`test_an_unobservable_surface_serves_null_not_false`,
`test_ran_is_measured_before_redaction_strips_what_it_measures`,
`test_the_repo_path_wins_wherever_it_exists`, and
`a null \`ran\` is silence, not a finding` (web). Confirmed in the opened app
against the payload the new API computes, both audiences, with a **negative
control**: the same checks run against the pre-fix payload fail on the two
badge assertions, so they are not vacuous.

The class to carry forward is `DECLARED_DEPENDENCY_WITH_NO_OBSERVABLE`: a
register may not name a source for a surface that has no way to show the source
reached it. Declaring the dependency and leaving the observation
unimplemented does not produce silence — it produces a permanent negative,
stated to the reader as a finding.

### 7.10 A fail-closed rule that refuses a whole format

**MEM-0070 — closed.** `register_evidence` verifies an excerpt verbatim against
the fetched artefact, which is right. The fetcher decoded every response as
UTF-8, which meant a PDF was compared as mojibake and *could not* verify. The
second client made this measurable: its WAF answers 403 to every HTML path
while `/docs/*.pdf` returns 200, so its client agreement, statement guides and
every career posting are reachable **only** as PDFs. A producer working it
registered **0 of 3 PDF sources against 13 of 13 HTML** ones, having confirmed
by hand that its span was present in the bytes.

This is the worst shape a fail-closed rule can take, and it is worth naming as
a class. A refusal that is *indistinguishable from catching a fabrication*, but
fires on a true citation, leaves an honest producer exactly two moves: drop a
true finding, or go find a source it can pass. Both degrade the corpus, and
neither is visible in any count — the run just looks thin. Regulatory filings,
annual reports and client agreements are overwhelmingly PDFs, so this refused
the T1 and T2 tiers the product rests on.

Fixed as extraction only: no fuzzy matching, no repair, the verbatim comparison
unchanged. Magic bytes decide the dispatch rather than the URL or the header
alone, and a scanned PDF returns `None` (unreachable) rather than `""`, so an
absent text layer does not read as a mismatched excerpt.

The second finding is procedural and larger. The fetcher lived in `server.py`,
which imports the MCP SDK at module scope, so **no test in the suite could
import it**. That is why a one-line defect survived in production through every
gate this repo has. It now lives in `dma_mcp/fetching.py` with 8 tests,
including a negative control that fails if UTF-8 decoding was not the cause,
and the two real-filing shapes a synthetic one-liner would miss — a span
wrapped across lines, and a citation past page 1.

Class: `LOGIC_NO_TEST_CAN_IMPORT`. Untestable placement is not a style
question; it is the reason a defect gets to be permanent.

### 7.11 Open, and the owner's call — the alert ceiling on the second client

Not a defect. Recorded here because it is the one thing blocking two-client
execution, and because resolving it silently would be the wrong move.

`ALERT_CEILING = 15` was set by the build owner on 2026-08-14 after a run
promoted carrying 98 open alerts, with the explicit instruction *"do not delete
them to clear the gate"*. The second client still stands at 98 and a producer
working it in good faith could not honestly get below the ceiling. Its argument,
which is worth weighing and is **not yet independently measured**: a large share
of those alerts are cells where no public source could observe the capability
for a firm of that type — consumer-credit decisioning at a firm that does no
consumer lending, TCFD disclosure at a private provincial dealer — for which
`WORKED_ABSENT` is the *correct* output, not a gap. The ceiling cannot tell
that from "thin because nobody looked", so both count the same.

Any fix is a governance change with an obvious hazard: a producer-declared
"correct absence" exemption turns the ceiling advisory and reopens exactly the
fabrication route the owner closed. **Left open deliberately, for the owner.**
The measurement is being redone first, because MEM-0070 above made that
client's own disclosures citable for the first time and may move the number
without any gate change.

### 7.12 When the owner removes a surface a check was guarding

The build owner looked at the platform dossier's peer roster and said: *"This
part on peers should not even be there; unnecessary detail."* Removing it broke
two assertions — `PEER SET · 5` and a named peer — both carrying MEM-0068,
whose finding was that **25 cited peer_deployment rows were served and rendered
zero times**.

The tempting move is to delete the assertions along with the block. The
opposite move — restore the block because a check demands it — is worse. Both
skip the actual question: *did the removal orphan the evidence, or was the block
redundant with something that survived?*

Measured in the opened app against the live production payload. It was
redundant. `PEER POSITION` renders per platform and states the peer position in
prose that **names** the established peer ("GreenState is the…", "Lake Michigan
Credit Union runs UiPath and…"), and `Considered and set aside · 8` gives the
discarded set its route. The cited rows still reach a reader. The owner's
instinct was right and the roster was a second telling of the same thing.

So the assertions were **re-pointed, not deleted**: `PEER POSITION` present, and
a peer NAMED rather than counted. One incidental correction fell out — the old
check asserted `Alliant Credit Union`, a name this run mentions *only* inside a
discarded platform's rationale, so it was testing a string that never had to
render. `GreenState` is the peer the run actually establishes.

The rule: an owner removing a surface retires the **assertion**, never the
**finding**. Re-point the check at whatever now carries the guarantee, and if
nothing does, that is a regression to report rather than a check to delete.

**Verification standard used throughout this section**: every claim above was
confirmed by opening the app against payloads pulled from the **deployed API**,
not from fixtures — 65 assertions across five suites, both audiences, all
green.

### 7.13 The out-of-scope cells do NOT depress the score — measured, hypothesis wrong

The second client's alert queue measured 98: **13** closeable now · **33**
correct-absence · **45** thin-unresearched · **7** unreachable (host blocked).
The 33 are base cells the entity has no business having — consumer-credit
decisioning at a firm that originates no credit, BaaS at a firm with no partner
distribution, TCFD at a private dealer bound by neither OSFI B-15 nor IFRS S2.

I put it to the owner that those 33 were probably also **depressing the
composite**, since they score at mean 1.91 against a run mean of 2.76. The
owner said measure it first. That was the right call: **the hypothesis is
wrong.**

Method validated before use — the aggregation here (category = mean of its
cells, pillar = mean of its categories, composite = pillar-weighted 25/30/20/25)
reproduces the workbook's own stated numbers exactly: composite 2.76, P1 2.96,
P2 2.11, P3 3.33, P4 2.88.

| | with the 33 | without | delta |
|---|---|---|---|
| P1 | 2.96 | 2.96 | +0.00 |
| P2 | 2.11 | 2.12 | +0.00 |
| P3 | 3.33 | 3.34 | +0.00 |
| P4 | 2.89 | 2.89 | +0.00 |
| **composite** | **2.76** | **2.76** | **+0.00** |

No pillar moves, no category moves by more than 0.10, no band changes. The
reason is the aggregation shape: the 33 sit *inside* categories whose means
they do not shift — the nine P1C5 cells all score 3.0 against a P1C5 mean of
exactly 3.000, and the P2C2 cells score 1.5 against a P2C2 mean of 1.492. They
are representative of their categories, not outliers dragging them.

**So the scoping fix is justified by the alert queue and by what a reader sees
— 33 cells rendering as gaps that are not gaps — and NOT by score fairness.**
Recording that distinction because the wrong rationale would have survived into
the change and been repeated as fact.

### 7.14 What the measurement found instead: clone blocks

Looking for the score effect surfaced something larger, in the **upstream
assessment** rather than in this app — the app is faithfully serving what the
workbook says.

Odlum's `P2C3` carries **59 cells with the identical score (2.5), the identical
confidence (HIGH) and the identical four evidence ids**, with one rationale
reading "Evidence from research corpus mapped to subcap".

Generalising it — cells sharing an identical evidence set *and* an identical
score, in blocks of ten or more:

| | scored cells | in a clone block of 10+ | single id reaching most cells | ids reaching ≥40 cells |
|---|---|---|---|---|
| second client | 709 | **224 (32%)** | 186 (26%) | 19 |
| reference client | 766 | **604 (79%)** | 191 (25%) | 36 |

The reference client — the one promoted and serving in production — is the
worse of the two. Its largest block is 43 cells at score 3 from five evidence
ids, spanning one category.

A shared source is not itself a defect: one annual report legitimately bears on
many capabilities. What the clone block measures is a shared source producing
**one score across many distinct capabilities** — a single judgement wearing
many hats, rendered as 766 independent readings. This is BAX-09 ("one T5 item
supporting 47 cells") measured across the corpus rather than spotted once.

The connector already caps this for evidence a producer registers
(`source_rules.sole_evidence_reach`, W6, keyed on the canonicalised document).
It does **not** apply to ingested workbook evidence, which is where all of the
above lives. That asymmetry is the gap.

**OPEN, for the owner** — this is a finding about assessment production, not a
bug in the serving app, and closing it means either a corpus gate at ingest or
a change to the assessment skill. Recorded, not acted on.

---

## 8 · Files

- `ACCEPTANCE.md` — this file, the reference root.
- `inventory.json` — 122 sections, 463 canonical checks, per-check verdict,
  layer, severity and defect linkage. What Gate E WILL reconcile against once it exists (H7); today it is an index, not an enforced contract.
- `remediation_ledger.json` — 41 issues (3 FIXED, 38 open), each with its
  neutral rule, its `bax_id`, its covering `qa_id` and a re-test note. The
  open rows carry `verify_first: true` because the document reported them
  broken on 14 August and several were fixed after that pass.
- `checks-platform.json`, `checks-safeguard-gates.json`,
  `checks-customer.json` — opened-app check sets for `tests/open-app.js`.
  Each drives the real controls (`click_text` steps, including the
  icon-only settings popover and the AE→Analyst switch every session lands
  behind) and asserts against the settled DOM, so a disclosure that renders
  nothing cannot pass as one that is merely collapsed.
