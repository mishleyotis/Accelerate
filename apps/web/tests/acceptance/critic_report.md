# Completeness critic — adversarial audit of the curated acceptance set

Audited at HEAD `14f1016`, 15 August 2026, against
`9d492ce9-DMA_Insights__Production_Acceptance_and_Adversarial_QA.md`
(14,091 lines · 2,428 headings) and the three merge outputs in
`apps/web/tests/acceptance/`.

**Verdict: INCOMPLETE.** The register/dedupe architecture is sound and the
document criticism is largely correct and well evidenced. But 55 headings are
unaccounted, 63 of the 463 canonical checks carry no rule text anywhere, whole
families of the document's own P0 checks were dropped without an exclusion
record, three exclusions are refuted by the repository, and the file reports a
CI gate ("Gate E") and an enforcement boundary that do not exist at HEAD.

---

## 1 · Heading census reconciliation

| | |
|---|---|
| Headings in the source document (`grep -c "^#"`) | **2,428** |
| Level 1 / 2 / 3 | 1,027 / 1,337 / 64 |
| Doc surface ranges derived from level-1 non-numbered headings | 127 (114 after folding the Narrative and Test-System sub-headings into their parents) |
| Inventory sections | 122 (16 registers + 87 included + 19 excluded) |
| Headings inside a doc range that maps to an inventory section | **2,373** |
| **UNACCOUNTED** | **55** |

Method: every heading was assigned to the doc surface range containing it; each
inventory section was mapped onto a range by `doc_line`. A heading is accounted
if its range carries at least one inventory entry (included, excluded or
register). Two readings were computed:

- **Strict** (each doc surface needs its own entry): **91 unaccounted**.
- **Lenient** (granting the single `Health — H3 / V1 / H5 / H7 / H8` entry
  authority over all five Health sub-ranges, 36 headings): **55 unaccounted**.
  This is the figure reported above — the most generous defensible reading.

### The 55 unaccounted headings — three whole surfaces, silently dropped

| Doc range | Surface | Headings | Doc checks lost |
|---|---|---|---|
| 6245–6292 | **Insights — Technology landscape** (T2) | 9 | §8 render contract only; carries invariant 8 ("T2 landscape recomputes from the T1 register") |
| 6830–6956 | **Insights — Recommendations** | 23 | `IR-01`..`IR-06`, six P0 |
| 6957–7087 | **Insights — Recommendation modal** | 23 | `INR-01`..`INR-12`, eleven P0 + one P1 |

These appear in `inventory.json` neither as sections nor on the excluded list,
and in `ACCEPTANCE.md` nowhere at all (`grep -n "technology landscape\|Insights
- Recommendation"` → 0 hits). The merge notes claim "the two Insights sections
are excluded and re-pointed" to Platform — the re-pointing was written in the
notes and never recorded in either artefact, and it accounts for two of the
three, not three. `INR-10` ("duplicate REC-NN codes across clients cannot
resolve without display ID") is the same display-id question the merge escalated
as the one open owner adjudication (BAX-33); the document answers it here and
the answer was dropped.

**The census also depends on an exclusion that is false** — see §5, hole C4:
`VersionDiff` is mounted at `pages-d5-d6-tech-runs.jsx:1591`, so the lenient
grant of 36 headings to `health.subsurfaces` rests on an untrue "not separately
mountable". Under the strict reading the number is 91.

---

## 2 · Spot-reads — 12 sections at random across all 14,091 lines

Read the doc, compared with `ACCEPTANCE.md` + `inventory.json`. Two of twelve
are clean. Ten lose checks; three change a check's meaning.

| # | Doc line | Surface | Doc checks | Carried | Verdict |
|---|---|---|---|---|---|
| 1 | 128–353 | §8/§9 composition oracle | 38 headings, 9 SV profiles | `CO-01`..`CO-06` | **MEANING LOST** |
| 2 | 354 | Global Shell and Auth | `GS-01`..`GS-10` | GS-01..06 + a **redefined** GS-10 | **MISS + COLLISION** |
| 3 | 887 | Global nav — Settings popover | `SET-01`..`SET-12` | SET-01..05 | **MISS ×7** |
| 4 | 1682 | Universal — Recommendation modal | `REC-01`..`REC-13` | URM-01..03 + URM-04 | **MISS ×7** |
| 5 | 2311 | Clients | `DIR-01`..`DIR-09` | DIR-01..05, +A1/A3 | **MISS ×4** |
| 6 | 3160 | Overview header — Meeting prep | `MPR-01`..`MPR-12` | OMP-01..03 | **MISS ×6** |
| 7 | 3542 | Overview — Firmographics | `OF-01`..`OF-07`, CQ-01/02 | OF-01 + 5 ADDs | **MISS ×6** |
| 8 | 4880 | Overview — Leadership | `OL-01`..`OL-07` | OL-01 + 3 ADDs | **MISS ×6** |
| 9 | 5905 | Overview — Sentiment detail | `SURF-01` only | EXCLUDE-AS-ROUTED | **CLEAN** |
| 10 | 8085 | Heatmap — Focus detail | `HFD-01`..`HFD-07` | HFD-01..07 + HFD-08 AMEND | **CLEAN** |
| 11 | 10714 | Context — Event detail | `SURF-01` only | `CEV-01` ADOPT | **INCONSISTENT** |
| 12 | 12546 | Alerts | `ALT-01`..`ALT-08` | ALT-01, ALT-02 (both re-pointed) | **MISS ×6 + COLLISION** |

Extra reads: Platform — Readiness gate (9665, doc carries only `SURF-01`;
curated `PRG-01` AMEND is a good save, `PRG-02`/`PRP-S6` carry no text) and
Insights — Recommendation modal (6957, entirely absent — see §1).

### Checks whose meaning changed in transcription

1. **`GS-10` collision.** The doc's `GS-10` is *"A network 401, 403, 404, 409,
   422, 429, and 500 produces a distinct recovery state; no generic success
   toast is emitted"* (P0, line 431). The curated `GS-10` is a **new ADD**
   ("a swallowed contract read renders an error state, not an empty one"). The
   id is reused and the document's rule — the only place in the whole corpus
   that enumerates the HTTP recovery states for the shell — is gone.
2. **`GS-04` displaced.** Doc `GS-04` is global search matching (exact name,
   partial, display ID, mixed case, diacritics, punctuation, no-match). The
   curated `GS-04` reads "the destination form must be asserted cross-entity",
   which is `GS-01`'s subject. The search-matching rule survives only by
   accident at `SRCH-10`.
3. **`ALT-01` / `ALT-02` both re-pointed.** Doc `ALT-01` is *"Role gate blocks
   navigation, direct URL, API, exported data, and count leakage for
   unauthorized roles"*; doc `ALT-02` is count reconciliation. The curated
   `ALT-01` carries the count reconciliation (i.e. doc ALT-02's subject) and the
   curated `ALT-02` carries workflow-vocabulary supersession — a subject that
   appears nowhere in the Alerts section. `UNWORKED` occurs at doc lines 7166
   and 8474–8555 only, all in **Heatmap — Thin-evidence alerts**. Adjudication
   B's claim in `ACCEPTANCE.md` that it supersedes "Alerts §1" is unsupported by
   the text.

### The dropped checks that matter most

Not padding — these are P0 rules the document states and the curated set does
not carry anywhere, by id or by paraphrase:

- **`SET-11`** — *customer audience cannot be escaped by refresh, deep link,
  second tab, or client-side state edit.* This is CLAUDE.md **invariant 5**.
- **`REC-12`** — customer redaction preserves uncertainty and cannot expose
  internal rationale through DOM/API/copy. Invariant 5.
- **`MPR-09`**, **`HFD-06`** (by-id only), **`OF-05`**, **`OL-06`**,
  **`ALT-06`** (cohort denominator + privacy suppression — invariant 5's
  "`entity_ids` stripped for *every* audience"), **`ALT-08`**, **`DIR-09`**.
- **`OF-02`** — *unknown/null differs from zero, empty string, not applicable,
  and intentionally redacted.* The document states shipped defect 8's own rule
  and the curation drops the id, keeping only the narrower `FM-01`/`FM-02`.
- **`DIR-07`** — *empty filter result differs from empty catalogue and API
  failure.* Shipped defect 1's class, stated by the document for the Clients
  page. The curation ADDs `DASH-07` for the Dashboard and drops the document's
  own equivalent for Clients.
- **`OL-04`** — enrichment conflicts never overwrite assessed facts silently;
  provenance and audit history remain. Adjudication G's own subject.
- **`GS-07`**, **`GS-08`** (sign-out clears caches; Back reveals no protected
  content), **`SET-08`**/**`SET-09`**/**`SET-10`**.

**Audience redaction is the systemic loss.** `grep -i "redact\|internal_only"
ACCEPTANCE.md` → **0 hits**; "audience" appears five times, all incidental. The
one invariant the charter says "the walker + tests + contract must make
unavoidable" has no register, no ADD and no adopted surface check. Every doc
check that asserted it was dropped.

### Composition oracle §8/§9 — reduced past the point of use

226 lines and 38 headings became six `CO-*` checks. Absent from the curated set
entirely (`grep -ci` on `ACCEPTANCE.md`): the **T1–T5 evidence tier ladder** with
its L5/L4/L2.5/L2 caps (0 hits for `T1`), the **absence ladder** (HIT /
NEGATIVE / NEGATIVE AND APPROPRIATE / NOT ATTEMPTED — 0 hits), the **R-layer**
verdict discipline (0 hits), the **comparability event** rule (0 hits), and
**atomic six-page promotion** (0 hits for "atomic" and "six pages") — which is
CLAUDE.md **invariant 3**. Invariant 11 (ordered writer registry) also has 0
hits; invariant 2's `Idempotency-Key` has 0 hits.

The document's §8.2 currency ladder ("current is under 18 months; recent 18–36;
legacy over 36") **conflicts with CLAUDE.md's 12/24/36/48-month
`CURRENT…ARCHIVAL` ladder**. This is a doc-vs-contract conflict of exactly the
kind §7.5 was built to record, and §7.5 does not record it.

---

## 3 · The Baxter standard — would each covering check actually catch it?

All 14 defects carry a covering `qa_id`. Judged on whether the check as written
asserts something that fails on the defect: **12 hold, 1 is materially wrong at
HEAD, 1 is honest-but-unwired (declared).** Two covering ids are dangling and
six are hollow.

| # | Primary cover | Would it catch? | Evidence at HEAD |
|---|---|---|---|
| 1 | `RG-11` — shared contract proven present *inside the built image*; loader raises rather than degrading to `{}` | **YES** | `ci.yml:44` Gate D + `scripts/gate_d_shared_files_ship.py`; `apps/api/tests/test_register_ships.py::test_a_missing_register_raises_rather_than_reading_as_empty` |
| 2 | `RG-12` — path resolution lazy and depth-independent; modules imported at image depth | **YES** | `test_register_ships.py::test_register_paths_survive_a_shallow_image_layout` |
| 3 | `EN-01` — submit-time ITEM-key census, any contract-asked path null across all rows blocks, naming path and row count | **YES if wired** | `grep -c must_present packages/shared/contracts_data.json` → **3**. Correctly declared as HOLE 4 |
| 4 | `ST-06` — lifecycle status identical at card face, detail tab, status arrow and drilldown; no arrow derived from anything but the stored status field | **YES** | Rule is concrete and falsifiable; render-side assertion not yet wired (declared) |
| 5 | `KP-04` — a negative-state sentence is bound to the key carrying the fact it denies, and may not render when that key is non-empty | **YES** | Instance fixed; no gate. HOLE 2 declared |
| 6 | `KP-02` — every contract-declared field has ≥1 reader in `apps/web`; a zero-hit field fails the build | **YES** | Would have failed on `capped_subcap_ids`. HOLE 2 declared |
| 7 | `AB-04` — a field with a recorded held reason renders its row and the substance of that reason, in reader language | **YES** | Directly inverts the defect |
| 8 | `FM-01`/`FM-02` — null in, null out; `fmtAssets(0)` visibly distinct from `fmtAssets(null)` | **YES** | Verified fixed: `utils.jsx:938` returns `null` |
| 9 | `FM-04` — pinned-row list and pinned-key list are one list; duplicate-slot scan | **YES** | Names the exact mechanism (two lists drifting) |
| 10 | `KP-03` — a promoted array with N>0 rows renders N>0 rows; served and rendered sets **diffed, not counted** | **YES** | "Diffed not counted" is the right assertion |
| 11 | `RG-14` — a run promotes only with **fewer than 15** open alerts | **YES for 98 — but the boundary at HEAD is wrong** | See below |
| 12 | `CG-21` — no payload leaf is a string that *parses* as JSON | **YES** | `apps/mcp/dma_mcp/gates.py`, `apps/mcp/tests/test_serialised_leaves.py` |
| 13 | `RG-15`/`CI-14` — deployed revision compared to the commit containing the fix; "could not compare" is FAIL | **YES if wired** | `grep -rn verify_deployed .github/ infra/` → 0 hits. HOLE 1 declared |
| 14 | `RG-16` — the set of CI test targets equals the set of test directories in the tree | **YES** | `ci.yml:87` now runs worker · mcp · api · scripts + a web job. HOLE 5 declared |

### Defect 11 — the file reports "Enforced" and the boundary is off by one

`ACCEPTANCE.md` states adjudication F correctly (**"fewer than 15"**) at `RG-14`
and then contradicts itself at `CI-18` ("Promote blocks at **≥ 15** open
alerts"), and the repository implements a third thing:

```
apps/mcp/dma_mcp/promote.py:179      if alerts > ALERT_CEILING:      # 15 promotes
apps/mcp/tests/test_alert_ceiling.py:45   assert not _open_alert_count(_live(15)) > ALERT_CEILING
```

The test **pins the wrong side of the boundary**: it asserts that a run with
exactly 15 open alerts promotes, which adjudication F forbids. `RG-14` still
catches the shipped 98, so defect 11 is covered — but the file's "**Enforced**"
claim and its `CI-18` wording are both wrong about HEAD, and the regression test
now protects the violation. Fix the comparison to `>=` and flip the test.

### Hollow and dangling covers

- **Dangling** — `INE-ADD-01` (cited for defect 7) and `H3-ADD-01` (cited for
  defect 11) appear in the Baxter table and **exist in neither artefact**.
- **Hollow** — `WT-08`..`WT-13` are the named covers for defects 5, 6, 7, 8, 9
  and 10. All six are verdict `ADOPT`, carry **no rule text in either
  artefact**, and **do not exist in the source document** (`grep -c WT-08` on
  the doc → 0). `ADOPT` means "correct as written; carry it" and there is
  nothing written. Six of fourteen defects are padded with ids that assert
  nothing. The defects survive only because each also has a real textual cover
  (`KP-*`, `FM-*`, `AB-04`).

---

## 4 · Client neutrality — PASS

| file | Baxter | BCU | Odlum | Zota | URLs | `.com` |
|---|---|---|---|---|---|---|
| `ACCEPTANCE.md` | 1 | 0 | 0 | 0 | 0 | 0 |
| `inventory.json` | 0 | 0 | 0 | 0 | 0 | 0 |
| `remediation_ledger.json` | 0 | 0 | 0 | 0 | 0 | 0 |

The single occurrence is the heading "## 2 · The Baxter standard" — the owner's
own neutral term for the shipped-defect list, not a client fact. No client
figures, assets, NPS, ratings or engagement percentages leaked. The `BAX-01`..
`BAX-41` ledger entries carry neutral rules only. **No violation.**

Related, and correct: the file strikes 15 fabricated corpus statistics and
escalates the "32 clients" figure that also appears in the Surface
Specification, rather than silently correcting a contract.

---

## 5 · Owner adjudications A–G — all seven present

| Adj. | Present | Superseded sources named |
|---|---|---|
| **A** no em dash | §3, `AB-01`, `OF-01` | Firmographics §8.3 ("an unknown field renders an em dash"), restated in Overview §1 |
| **B** no workflow vocabulary | §3, `AB-02`, `ALT-02`, `HRR-01`, `HTA-03` | `UNWORKED`/`WORKED_FOUND`/`WORKED_ABSENT` across eleven surfaces; Rerun feedback §8.3; **"Alerts §1" is a misattribution** — `UNWORKED` does not appear in the Alerts section |
| **C** omit the row | §3, `AB-03` | every "render the field as unavailable" instruction |
| **D** revenue is sub-vertical conditional | §3, `CO-03`, `OF-A2`, `WT-02`, `PROS-02` | Firmographics §8.3 must-present set vs its own §8.5 table; Prospecting §8.5 |
| **E** four bands only | §3, `BD-02` | Ceiling surface's M1–M5 scale, `OCU-08`'s "cap M3 applied", Hero §8.3's "Competitive"; Surface Spec O1b flagged upward |
| **F** < 15 open alerts | §3, `RG-14`, `ALT-ADD-01` | the doc's 109-alert reconciliation baseline — **but see §3, the HEAD boundary is `> 15`** |
| **G** scheduled enrichment routine | §3, `AB-06`, `IMP-02` | endpoint verified at `apps/api/dma_api/main.py:697` |

---

## 6 · Holes the merge did not report

**C1 — Three exclusions are refuted by the repository.** The merge claims
"exclusions are all grep-proven, never taken on the doc's say-so". Three are not.

- **Heatmap — Value-chain view**, excluded `EXCLUDE-UNTIL-CONTRACTED` on the
  strength of a comment inside `pages-live-client.jsx` — the 2,694-line **dead**
  pack the same file identifies as unmounted (HOLE 3). Refuted three ways:
  `packages/shared/contracts_data.json:72` defines `value_chain`;
  `apps/api/tests/test_value_chain.py` is a live suite over `read_value_chain`
  citing the Backend Schema; and CLAUDE.md line 70 lists value chain as
  **in scope**.
- **Context — Sentiment overview**, same verdict, same dead-code citation.
  Refuted: `contracts_data.json:689` states *"context_sentiment is REQUIRED …
  the only two optional sections in the 34 are heatmap.value_chain (H9) and
  heatmap.cohort_patterns (H8)"*; `live-adapter.jsx:1305` adapts it; and
  `SentimentGridInteractive` is **mounted** at
  `pages-d5-d6-tech-runs.jsx:249`. `ACCEPTANCE.md` itself says so two rows
  earlier when re-pointing the Overview sentiment detail — an internal
  contradiction inside the exclusion table.
- **Health — H3/V1/H5/H7/H8**, excluded as "not separately mountable".
  `VersionDiff` is mounted at `pages-d5-d6-tech-runs.jsx:1591`, and CLAUDE.md
  line 71 lists run/version diff as in scope. This exclusion is also what
  absorbs 36 otherwise-unaccounted headings.

Excluding a mounted, contract-required surface on the authority of dead code is
the same class as shipped defects 5, 6 and 10 — a claim about what is read or
mounted that nobody checked against what is written.

**C2 — 63 canonical checks carry no rule anywhere.** 63 of 463 (13.6%) have an
id, a verdict of `ADOPT`, a layer and a severity, and **no rule text in
`inventory.json`, no row in `ACCEPTANCE.md`, and no matching id in the source
document**. They cannot be executed, reviewed or disputed. Full list includes
`NAV-01`..`05`, `UED-01`..`06`, `UIP-01`..`04`, `URM-01`..`03`, `NOTF-01`..`04`,
`OEX-01`..`03`, `OMP-01`..`03`, `LOG-01`/`02`, `DNA-01`/`02`, `INTK-02`/`03`/`05`,
`CED-01`, `CEV-01`, `CID-S2`, `C3-AP`, `IED-01`, `IEA-01`, `HSG-02`, `HCSV-RG`,
`HRR-RG`, `PRG-02`, `PRP-02`, `PRP-S6`, `PSS-02`, `OV-A1`, `OV-A3`, `OWD-01`/`02`,
`OWE-01`, `CO-02`, `CO-05`, `WT-08`..`WT-13`.

Additionally, **236 of 463 curated ids do not exist in the document at all**;
143 of those carry `ADOPT`/`AMEND`/`SUPERSEDED`, verdicts that by definition
mean "carry the document's check". For the 89 that have a rule row in
`ACCEPTANCE.md` this is fine (coined id + text). For the rest it is not.

**C3 — 596 of the document's 793 P-graded check ids have no recorded
disposition.** Register absorption is the right architecture and the dedupe
ratio is real, but the artefacts contain **no absorbed-id map**. `ACCEPTANCE.md`
records the absorption exactly twice ("HSD-01..06 fully absorbed by OV"). For
every other surface, whether `MPR-09` was absorbed, superseded or lost is
unknowable from the artefact. Spot-reads show all three happened. A one-line
`absorbed_ids: []` per section would close this and make the census
self-verifying.

**C4 — "Gate E" does not exist.** `ACCEPTANCE.md` line 8: *"`inventory.json` is
what Gate E reconciles against"*, present tense. `ci.yml` has Gates A, B, C and
D and no E; `ls scripts/ | grep gate` returns four scripts. Reporting a gate as
present when it is not is the shape of shipped defect 13 inside the file written
to prevent it. State it as required-and-absent, or add hole H7.

**C5 — The artefacts poison the greps their own checks depend on.**
`ACCEPTANCE.md` and `inventory.json` live under `apps/web/`, so today
`grep -rn "Request DMA" apps/web` returns **16 hits** (7 + 9, all from these two
files) where the exclusion table cites **0**, and
`grep -riE "sourcequality|source_quality" apps/web` returns **4** where the
table cites 0. The code-only counts still hold (0 and 0; `CoverageByPillarCard`
is 6 in code, 11 with the artefacts). But `KP-02` ("a zero-hit contract field
fails the build"), `MT-01` and Gate C are specified as repo greps, and a
QA file that names every dead key and unmounted component will make each of them
find a phantom reader. Either exclude `tests/acceptance/**` from every gate's
scan path or move the artefacts out of `apps/web`.

**C6 — Invariant coverage gaps** (CLAUDE.md outranks the acceptance doc):
invariant 2 (`Idempotency-Key`) 0 hits, invariant 3 (atomic six-page promotion)
0 hits, invariant 5 (audience redaction) no dedicated check, invariant 11
(ordered writer registry) 0 hits. Invariants 4, 6, 7, 8, 9 and 10 are well
covered by `EV-02`, `BD-01`..`07`, `GR-07`, `FM-*` and `AB-*`.

**C7 — `SURF-01` is condemned and adopted.** §7.3 correctly calls
*"execute every component and subsection above"* unfalsifiable, and amends it at
`HCE-01` and `HRR-02`. On the ten surfaces where it is the **only** §4 check,
five were carried as untexted `ADOPT`s (`CEV-01`, `PRG-02`, `PRP-S6`, `HSG-02`,
`CID-S2`), i.e. the boilerplate was adopted under a new id. Apply the same
amendment everywhere or exclude those surfaces' §4 explicitly.

---

## 7 · What the merge got right

Recorded so the criticism above is not mistaken for a verdict on the whole.

- The **register architecture** and 4.62:1 dedupe are real and correctly
  computed; 930 check instances over 463 canonical ids reconcile exactly.
- The **fabricated-statistics audit** is excellent and independently
  reproducible, including escalating the "32 clients" figure found in the
  Surface Specification rather than silently correcting a contract.
- **Re-testing at HEAD** rather than inheriting 14 Aug statuses: verified for
  `fmtPct` (`utils.jsx:938` returns `null`), Gate D, the shallow-layout test,
  `ALERT_CEILING`, `CG-21`, CI's api/scripts/web jobs, and
  `/v1/ops/enrichment-loop` (`main.py:697`). All ten "fixed since" claims hold.
- **Holes H1–H6 are honestly declared**, and H1/H4/H5 reproduce exactly
  (`verify_deployed` → 0 refs; `must_present` → 3; no lint/type/a11y jobs).
- The three **doc-contradicts-contract** corrections (P1C5 `NOT_COMPARABLE`,
  Recommendations belong to Platform, `OPS/CUST/DATA/INFRA`) are right and
  correctly ordered.
- The **archetype exclusion** is genuinely grep-proven (0 hits in code) and the
  **stair-step inclusion** against a `NOT YET RE-EXECUTED` status is exactly the
  right instinct.
- `remediation_ledger.json` is internally sound: 41 entries, every
  `covering_qa_id` resolves to a real check after splitting the `/` lists.

---

## 8 · Required before this set can be called complete

1. Account for the three Insights surfaces (55 headings, 18 P0 checks) — include
   or exclude with evidence.
2. Reverse or re-evidence the three refuted exclusions (value chain, context
   sentiment, version diff); all three are in CLAUDE.md's in-scope list.
3. Give the 63 textless `ADOPT`s a rule, or demote them to explicit register
   inheritance.
4. Add an `absorbed_ids` list per section so the 596 unmapped doc ids get a
   disposition and the census self-verifies.
5. Build the missing **audience-redaction register** and restore `SET-11`,
   `REC-12`, `MPR-09`, `OF-05`, `OL-06`, `ALT-06`, `ALT-08`, `DIR-09`.
6. Restore `GS-07`..`GS-10` (and rename the ADD that took `GS-10`), `OF-02`,
   `DIR-07`, `OL-04`, and correct the `ALT-01`/`ALT-02` re-pointing.
7. Fix the alert ceiling to `>=` and flip
   `test_alert_ceiling.py:45`; correct `CI-18`'s wording to match `RG-14`.
8. Resolve the two dangling covers (`INE-ADD-01`, `H3-ADD-01`) and give
   `WT-08`..`WT-13` rules or drop them from the Baxter table.
9. Record the §8.2 currency-ladder conflict (18/36 months vs the contract's
   12/24/36/48) in §7.5.
10. Either build Gate E or stop saying it reconciles anything; exclude
    `tests/acceptance/**` from every grep-based gate.
