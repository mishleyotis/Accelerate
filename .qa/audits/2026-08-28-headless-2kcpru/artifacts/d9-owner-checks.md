# Deliverable 9 — The seven owner-specified checks (§4)

One verdict each, in the owner's order, each with the measurement that earned it. Same
roll-up rule as deliverable 3: the verdict judges the mechanism the check is about, the
constituent distribution is printed so the call can be argued with, and the driving ledger
row is named.

---

## 1 · Entry document and routing — **PRESENT–DEFECTIVE**
*Does the SessionStart hook fire headless at all, and does the brief survive compaction?*

**Distribution:** 4 PRESENT–DEFECTIVE. **Driving row:** `4.1-02`.

**Measurement.** The audit's own highest-value lead is **refuted**: headless
`claude -p --agent` *does* load plugin SessionStart hooks. Ran
`claude -p --permission-mode dontAsk --allowedTools=Bash` (v2.1.250) with an introspection
probe — the child returned `BRIEF_PRESENT` plus the 377-byte brief verbatim, and the result
repeated on the exact `agent_run.py` invocation.

The real hole is one layer up, and it is threefold. First, the brief is emitted on all five
SessionStart sources the CLI declares (`startup`, `resume`, `clear`, `compact`, `fork` —
377 B each) but **nothing reprints it after compaction**: no `PostCompact` hook is declared
though the harness supports one. Second — and this is the blocker — Claude Code delivers
SessionStart hooks **only to top-level sessions**: the parent transcript carries 4
`hookName:"SessionStart:startup"` attachments, and 3 of 3 subagent transcripts under the same
project carry **0**. The synthesis Routine prompt orders the top session to dispatch every
routed stage *directly* via the Agent tool, so the entire producer population is dispatched
through the one channel the brief provably does not reach. Third, `routing.md` is sound as a
routing table (17,392 B, 270 lines, two lookup tables, and
`test_every_agent_is_reachable_from_the_routing_table` really does fail under mutation), but
**48 of its 53 data rows carry a routing anchor that does not resolve.**

> **Self-correction, recorded rather than buried.** My first pass "confirmed" a sibling
> agent's claim of *50 of 55 rows* by re-running that agent's own grep. A verifier refuted
> the figure; re-measuring a different way gave **48 of 53 data rows**. Re-running someone
> else's command is not verification — verification is measuring the same thing a different
> way. The corrected figure is the one above; the procedural lesson is in `d16`.

---

## 2 · Drift, memory, resumability, compaction — **PRESENT–HUMAN-DEPENDENT**
*The kill-and-resume test; whether the skill-side ledger and the workbook's CHAIN INTEGRITY agree; and what now reports a stuck run, since `Blocked` is gone.*

**Distribution:** 4 PD / 2 AU / 2 PHD. **Driving row:** `4.2-05`.
*(Worst-of would say ABSENT–UNNOTICED; the sharper answer to what the owner actually asked
is that resumption requires a named human, so the human-dependency is the headline and the
two unnoticed absences are named underneath it.)*

**Named human and step:** the operator, at `dma-research` SKILL.md step (4) —
*"confirm entity + position with user."*

**Measurement — kill and resume.** On a fresh container a resumed run recovers nothing from
the workbook. `grep -n 'checksum' scripts/engine/orient.py` = **0 hits**; `orient.py:38` loads
`run_manifest.json` and reads exactly five fields (`run_id`, `entity`, `sv`, `evidence_mode`,
`categories`). The single strongest documented resume anchor, `kg_checksum`, is a string
**nothing writes and nothing reads**: `grep -rn kg_checksum` = 0 hits across 94 archive files
*and* 0 across the whole live tree; `grep -rn 'CHECKSUM}}'` = 0 in both, so nothing even fills
the template token. The template asserts a verification that no code performs.

**Measurement — do the two substrates agree?** They cannot be forced to, because **nothing
ever compares them**, and the JSONL side never reaches `orient` at all *(row `4.2-04`,
ABSENT–UNNOTICED)*. Drove a real run to a mid-category interrupt: bound the engagement set
(CU/T1_CORE, 686 of 851 selected; P1C1 = 47 subcaps), minted evidence ids through
`ledger.new_evidence_id`, appended evidence + search + synthesis — and the workbook's
CHAIN INTEGRITY block never sees any of it. Of the workbook's 7 verdict cells (`Coverage!D25:D31`),
**7 of 7 contain the literal unresolved token `{{OK | INVESTIGATE}}`** — no formula, so no
verdict is ever computed; 3 of the 7 rows are inert by construction.

**Measurement — what reports a stuck run?** For the *research* stage, nothing *(row `4.2-06`,
ABSENT–UNNOTICED)*. `Blocked` occurs **0 times** in the 189,980-character pinned workbook; the
only stuck-state token is those 7 unresolved cells, whose readers number 0. The synthesis stage
does have a real scheduled stall detector — but research, the stage this machinery belongs to,
has none.

**Measurement — one lock that does work.** The checksum HARD HALT is proven by mutation: two
checkpoints built from `kg/catalog/index.json` taxonomy checksums, one verbatim and one with
key `P1` replaced, gave a clean pass and a `checksum` halt respectively. It is the strongest
thing in this section — and per row `4.2-08`, every behavioural change it would trigger still
waits on a human: `ROUTINES.md` 2b, *"May not: Merge the PR."* The live connector confirms the
memory is real and being worked — `get_memory_digest(days=90)` returned
`{open: 275, resolved: 51, all: 326}` with 10 populated recurrence rows.

---

## 3 · Token optimisation — **PRESENT–DEFECTIVE**
*The claimed percentages reproduced or refuted, plus a token apportionment for one category.*

**Distribution:** 3 PD / 1 PS / 1 AU. **Driving row:** `4.3-04`.

**The claims are refuted as claims, not as engineering.** The headline `+25-32% / +11% / +3%`
figures appear in exactly **3 places repo-wide, all prose** — `SKILL.md:58`,
`CHANGELOG.md:176` (which asserts *"Token math verified BEFORE implementation"*), and a
comment at `validate_kg.py:175-176`. `grep -rln "25-32"` over all 99 archive files returns
those three and no measurement, no script, no fixture. The floor case is refuted on the
funnel's own arithmetic: a sweep that surfaces nothing still spent its 5 queries and its
fetches, so the sign of the claim is inverted.

**One claim reproduces and holds (`4.3-02`, PRESENT–SOUND).** The semantic index amortises at
n=1: `kg/graph/semantic_index.json` is 1,323,638 bytes — 592,435 cl100k tokens **if inlined** —
but it is never inlined; `map-fact` loads it in a subprocess (`json.loads` wall time 0.012 s)
and returns ~128 tokens. A single call is already cheaper than the 730-token lean brief it
replaces, let alone a 42,408–116,214-token pack.

**Apportionment for one category, end to end (P2C2, N=57 T1_CORE subcaps, 9 capabilities):**
runcard 1,386 tok + 57 × 796 rendered work cards (45,372) + 57 × 567 skeleton reads (32,319)
+ 57 × 1,229 filled syntheses (70,053) + 9 × 425 challenge passes. Search results dominate at
**42–79%** of the budget. Every KG optimisation carrying a measured number attacks the
21–58% deterministic term; none touches the dominant one.

**The wall is soft in the strongest sense — not merely unenforced but uninstrumented.**
`ledger.py stats`, the *only* tool R27 names for the budget check, **crashes on every
invocation**: `NameError: name '_stats' is not defined` at `scripts/engine/ledger.py:125`,
exit 1. And nothing connects the research budget to the report budget *(row `4.3-05`,
ABSENT–UNNOTICED)*: the two pinned Docs sum to a blocking minimum of 3,050 + N words that no
code counts.

---

## 4 · Report templates and offering linkage — **PRESENT–DEFECTIVE**
*Whether anything resolves the three pinned ids (and whether a superseded id is still referenced), and whether `{{SOLUTION_NAME}}` is referential or free text.*

**Distribution:** 10 PD / 5 AU / 2 PS. **Driving row:** `4.4-11`.

**`{{SOLUTION_NAME}}` is free text, at all three sites.** The pinned Client Profile §2.2
"Zennify relevance" cell reads verbatim `{{SOLUTION_NAME}} because {{WHY}}`;
`grep -rn '{{SOLUTION_NAME}}'` across the live tree and the archive returns **0 hits** outside
the Doc itself. No resolver, no catalogue lookup, no enum. The one slot that *is* rendered
today (§5.1 `{{SOLUTION_ALIGNMENT}}`) is written through unvalidated:
`A(f"**Zennify implication.** {lk['zennify_implication']}")`. A report can name an offering
that does not exist and nothing in either tree looks.

**The referential store exists twice and is reachable neither time** *(row `4.4-17`,
ABSENT–UNNOTICED)*. (1) The DB: migration `0004_catalogue_tier.py` defines `ccg_offerings`
(17 columns including `offering_id`, `offering_name`, `status`, `primary_vendors`,
`l3_platforms_used`) plus `ccg_offering_subcap_map`. (2) The archive:
`kg/catalog/offering_map.json`. `grep -rn 'offering_map|offering_id'` across `apps/*`,
`packages`, `scripts` and `plugins` = **0** — the only live hits are inside the migrations
that create the tables.

**The "23 offerings" claim is arithmetically true and semantically wrong, and it duplicates
the opposite way to the one the prompt predicted.** Over 854 mappings: **23 distinct
`offering_id`, 18 distinct display names, 24 (id, name) pairs.** `OFF-PMI` carries two display
names — *"Post-Merger Integration Solution"* on 17 mappings and *"Post-Merger Integration"* on
8 — so a report naming one will never join a report naming the other. The live repo's own
registry says 14, not 23. Coverage: 458 of 851 subcaps mapped, **393 unmapped**, 0
mapped-not-in-universe; judged an **incomplete map rather than deliberate curation**, because
an unmapped subcap has no entry at all, so no rationale and no recorded decision exists for
any of the 393 — the absence of a mapping is indistinguishable from the absence of a decision.

**Two things here are sound.** The universe rebuilds independently from the packs to exactly
851, matching `index.json` (`4.4-08`); and all 854 mappings carry all four fields with zero
empties and a median rationale well above trivial length (`4.4-09`) — though `maturity_lift`
uses an **M1–M5** scale that contradicts the charter's four-band scheme, and the same column
sits unread in the live DB.

**Three template blocks are unwritable rather than merely unenforced** *(rows `4.4-02`,
`4.4-06`, `4.4-14`, `4.4-15`, all ABSENT–UNNOTICED)*. In the 189,980-character pinned
contract-v3 workbook export, the occurrence count for `Cap_Triggers`, `Solution_Catalogue`,
`Handoff_Lock`, `Platform_Peer_Adoption`, `Focus_Areas` and `Firmographics` is **0 each** —
six named source sheets that do not exist. The rule *"if any field resolves to UNRESOLVED, the
render fails"* has no implementing code: `grep -rn 'UNRESOLVED'` over the archive = 0.

---

## 5 · Peer grain — **PRESENT–DEFECTIVE**
*Nothing stores peer at category grain any more; the assessment report renders pillar at §6.2 and three app surfaces render pillar; name the owner decision.*

**Distribution:** 4 PD / 1 AU. **Driving row:** `4.5-01`.

**The premise is half-refuted, and the half that survives is the important one.** The
category-grain **store** exists end to end and is sound: `0011_peer_scores_category_grain.py`
adds `peer_scores.category_id`, and ingestion honours invariant 8 —
`persist.py:697-716` recomputes the median from the named-peer scores rather than storing a
supplied one. So the claim "nothing stores peer at category grain" is **false at the database**.

What is true is upstream: the **producing workbook has no peer content at all.** Reading the
pinned template (189,980 chars): `Benchmark` = 0, `Peer_Benchmarks` = 0, `Rollup` = 0,
`median` = 0, `Adoption` = 0; `peer` occurs 8 times, of which 4 are a
`Neg_Rung4_Peer_Vendor` column header. The store is real and its supply is empty.

**Grain census across the contract.** Scanning `packages/shared/contracts_data.json` (6 pages,
42 sections): **12 of 42 sections carry a `peer*` field**, and their declared grains are mixed —
`heatmap.workbook_scores.pillars` is pillar grain, other sections category. And the report
diverges bidirectionally from the app's ladder: searching the pinned Assessment Report v8
(62,550 chars) for the ladder's own vocabulary gives `peer_n` = 0, `N=3` = 0, `INFERENCE` = 0,
`peer proxy` = 0, `cannot reliably estimate` = 0, `widen` = 0. Neither document knows the
other's rules.

**The gate does not close the hole.** `AG-04` (`_check_peer_research`) run against six
constructed payloads: it correctly passes an honest 2-of-5 with three `deployed: null`
(coverage 0.4), and it **also passes** the version where the three unestablished peers are
simply *dropped*, leaving 2 rows both `deployed: true` at coverage 1.0. Dropping the peers you
could not establish scores better than admitting them.

**The peer-set lock is asserted and does not exist** *(row `4.5-04`, ABSENT–UNNOTICED)*. Both
pinned templates describe it as a working mechanism — Client Profile v8 §4.1: *"once this
section is approved, the peer set is immutable for the remainder of the assessment."*
`grep -rn 'Handoff_Lock|handoff_lock'` across nine trees including the legacy snapshot = **0**.

> **OWNER DECISION, surfaced and deliberately not settled.** Three options, unchanged from
> the prompt: **(a)** widen the rule to admit pillar grain for the app strip, since
> `overview.scores.pillars` already carries the whole peer set at pillar grain; **(b)** hold
> category grain as the contract and make the workbook produce it, which means adding the peer
> sheets that are currently absent; **(c)** declare the report's §6.2 pillar rendering a
> presentation choice over a category-grain store, and gate the difference. This audit
> establishes the facts each option has to live with; it does not choose.

---

## 6 · Platform-recommendation challenge — **PRESENT–DEFECTIVE**
*The Rebuttal block and its seven probes exist in the template; establish what enforces them and whether the payload carries them.*

**Distribution:** 7 PD / 5 PS / 1 AU. **Driving row:** `4.6-05`.

**What enforces them: almost nothing, and the gate that looks like it does is a shape check.**
Ran the AG-01 block (`validation2.py:3430-3445`) verbatim over 7 crafted recommendation
payloads. It refuses **only 2 of 7** — a missing `r_layer` key, and `r_layer = {}`. It
**passes** `r_layer = {'verdict': 'ACCEPT'}` with nothing argued, and it passes
`r_layer = {'verdict': 'banana'}`, a value outside the vocabulary entirely, because the
predicate tests `not isinstance(rl, dict) or not rl.get("verdict")` and never looks at the
verdict's *value*. A recommendation cannot ship with **no** rebuttal object, but ships freely
with an **empty** one — precisely the case the pinned template's own FAIL IF names.

**Whether the payload carries them: one field of eight.** `vacuity.item_keys('platform',
'recommendations', 'recommendations')` returns a frozenset of **17 keys, and `r_layer` is not
among them** — yet `('platform','recommendations')` *is* in `_RANKED_SECTIONS`, so AG-01
demands a field the contract does not define. Of the template's A/B/B/B/B/C/D/E block, only
`counter` has a payload home, and it is unchecked. Steelman-with-conditions, cheaper
alternative and case-for-waiting die in the `.docx`.

**Five things here are genuinely sound, and they are the best-built code in the audit.**
The incumbent discount is real and test-pinned (`INCUMBENT_COVERAGE_DISCOUNT = 0.5`, applied
after the severity clamp and evidence damping, measured on 10 identical gapped cells).
Alignment-omission renormalisation is live and correct (`W_ABSENT` rides at its audited 0.064).
The honest-null states are complete (`STATE_READY` / `INSUFFICIENT_EVIDENCE` / `TOO_NARROW` /
`OUT_OF_VERTICAL`, `MIN_CELLS=3`, `RELEVANCE_DISCARD=0.5`) and the engine self-discloses when
the vertical guard had nothing to bind on. CG-30 and CG-31 are both load-bearing and proven to
fire under mutation at the 0.05 tolerance.

**And one of those sound gates carries the single cheapest defect in the system.** CG-30
recomputes the card through the real engine — but builds its engine input with
`"readiness": r.get("readiness") or "green"` (`validation2.py:1482`). An **omitted** readiness
becomes green, multiplier 1.00, so the engine returns exactly what the card shipped and
agreement is guaranteed by construction. Max reachable fit rises from 62.0 to **99.0**.
Meanwhile `platform_fit.py:119` already defines `READINESS_DEFAULT = "amber"` with a comment
saying exactly why: *"Green would reward a card that established nothing."* Two live modules,
opposite written rationales, one line apart in effect.

**The prompt's mechanism for the estate problem is refuted; its conclusion survives.** Three
estates with identical gaps, varying only register knowledge: KNOWN-ABSENT fit **64.80**
(greenfield 1.0) / NEVER-LOOKED **56.80** (greenfield 0.0) / KNOWN-HELD **28.40**. A missing
row does *not* produce a spurious greenfield bonus. An unscanned estate is still
systematically over-recommended — but through a **missing incumbent discount**, not a false
bonus. Same conclusion, different cause, and the fix is different too.

**The two dependency chains cannot catch each other** (`4.6-11`): one machine-run chain over
platforms (`_sequence()` repairs rank by stable best-available pass) and one unexecuted human
chain over recommendations and phases. Nothing compares them. And §6.4's counter-evidence pass
exists verbatim in the pinned Client Profile and in **neither** the engine nor any skill
*(row `4.6-08`, ABSENT–UNNOTICED)* — while the adjacent §6.2 discipline, from the same section
of the same template, did become code.

---

## 7 · Workbook — **PRESENT–DEFECTIVE**
*The seven validator rules each forced to fail; the missing `strip_working_area.py` and the validator's blindness past column 11; and the twelve Client Profile §8.1 tabs that no longer exist.*

**Distribution:** 4 PD / 3 PS / 1 AU / 1 PHD. **Driving row:** `4.7-07`.

**The parser layer is sound, and proven so three ways.** `_is_pillar_tab` resolves
`P1_Subcap_Scoring` correctly and rejects the decoys (`4.7-01`). `_TAB_PRECEDENCE` is
most-specific-first with its reason stated in code — 23 of 154 corpus workbooks merged, 1,420
rows for a 710-cell assessment — and swapping positions 0 and 2 breaks it under mutation, so
the ordering is load-bearing and tested (`4.7-02`). Column D and the `SubCap_ID` anchor were
confirmed from the emitted `score_col_letter` on a **live parse**, not by reading the tuple
(`4.7-03`).

**The validator rules fire — for whoever runs them, which is nobody in the deployable system**
*(row `4.7-06`, PRESENT–HUMAN-DEPENDENT)*. Built 13 minimal `.xlsx` with openpyxl 3.1.5 and
ran each through `validate_workbook.py`. Rule 4 (grey cells) forced red correctly:
`D=3` on a P1 row gave `FAILS=1 / FAIL P1 r2: assessment col 4 not empty`, exit 1. The rules
are real and forced red. **Named human and step:** the researcher or operator executing
`python scripts/deliver/validate_workbook.py` by hand — nothing in the deployable system runs it.

**The blindness is a swap, not a count.** `wb_rows_missing` → `'P1: rows=1 expected=2 (scope)'`,
exit 1. `wb_rows_extra` → `'rows=3 expected=2'`, exit 1. But `wb_rows_swap` — `P1C1.1.2`
replaced by the entirely **out-of-scope** `P4C9.9.9`, count unchanged at 2 — gives
**`FAILS=0`, exit 0**. The validator checks cardinality, never membership.

**And the app mislabels genuinely-excluded cells as gaps.** `toggled_out` is documented at
`workbook_parser.py:176` as *"variant cells excluded by the toggle cascade"* — i.e. **not in
scope** for this sub-vertical. The app labels **44 of 49** such cells as though they were
missing work.

**The facet denominator is honest but tiny** (`4.7-08`): `find . -name '*.xlsx'` = **0 files**
in the repo, and 0 of 186 legacy client folders carry a facet, so the only obtainable real run
had to be generated (`integration_smoke.py` → `wb.xlsx`, `validate_workbook: FAILS=0`), and its
`Evidence_Detail` holds 4 fact rows.

**Of the nine handoff joins, 7 hold and 2 fail** (`4.7-09`). J1 (`DQ_Bank → SubCap_ID`) has
nothing to join to: `populate_workbook.py` never writes `DQ_Bank`, so the question bank exists
only in the hand-built template — the generated workbook has 10 sheets and none of them is it.

**`Cap_Triggers` and `Platform_Peer_Adoption` have no source on either side** *(rows `4.7-04`,
`4.7-05`)*. The Assessment Report v8 §3 control block declares
*"INPUTS: Scoring workbook: Issue_Register, Cap_Triggers, Subcap_Scores, Caps_Applied_Log"* and
*"the severity to cap mapping in force, read from Cap_Triggers."* `grep -rn 'Platform_Peer_Adoption'`
across the whole repo and the whole archive = **0 hits in both trees**. The write side names a
sheet that does not exist; the read side names nothing at all.

---

## Roll-up across the seven

| # | Owner check | Verdict |
|---|---|---|
| 1 | Entry document and routing | PRESENT–DEFECTIVE |
| 2 | Drift, memory, resumability, compaction | **PRESENT–HUMAN-DEPENDENT** |
| 3 | Token optimisation | PRESENT–DEFECTIVE |
| 4 | Report templates and offering linkage | PRESENT–DEFECTIVE |
| 5 | Peer grain | PRESENT–DEFECTIVE |
| 6 | Platform-recommendation challenge | PRESENT–DEFECTIVE |
| 7 | Workbook | PRESENT–DEFECTIVE |

Six defective, one human-dependent, none sound and none absent-by-design. The pattern across
all seven is the same: **the mechanism exists, it can be forced red under mutation, and
nothing in an unattended run invokes it.** Six of the seven checks turned up at least one
mechanism that is asserted by a template and implemented nowhere — `kg_checksum`,
`Handoff_Lock`, `Cap_Triggers`, `Platform_Peer_Adoption`, `Solution_Catalogue`, `UNRESOLVED`.
That is the single most repeated defect shape in the audit.
