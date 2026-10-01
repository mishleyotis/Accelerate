# Deliverable 8 — Reasoning-trap report

Three parts, as specified: the §6.1 trap table completed with **enforcement status**; verdicts
on the §6.2 challenge layer's independence, on whether `provisional: true` survives to the app,
and on the terminal state of an `open_conflict` with no human to ask; and the §6.3 walk-through
naming every gate the wrong-but-perfect conclusion passes.

---

## Part A — The §6.1 trap table, with enforcement status

**Enforcement status vocabulary.** *MECHANICAL* = code computes it and can block.
*SHAPE-ONLY* = code runs but tests length, format or presence rather than substance.
*PROSE-ONLY* = stated in a markdown table or a YAML prompt card, no code.
*ABSENT* = not implemented anywhere, in either tree.

| Trap | Rule | Enforcement | Measurement |
|---|---|---|---|
| **Premature scoring** | R1 | **MECHANICAL** on the workbook path; **UNGUARDED** on the handoff path | `validate_workbook.py` control FAILS=0; inject `D2=3` (Score) and `H3='M3'` (Evidence_Ceiling) → **FAILS=2, exit 1, both named (2/2 caught)**. But `research_handoff.json` carries `v1_compat.capability_ceilings.P1C1 = 3.0` — a float maturity score minted at `build_handoff.py:100` — for a category whose own `floor_pass_rate` is **0.041**. |
| **Unlabeled assertion** | R2 | **ABSENT at runtime** | `ledger.py append` has no schema step. A synthesis with `claim_label 'PROBABLY_TRUE'` passes `floors_gate --require-synthesis` (**gate PASS, exit 0, dq_gaps []**) and lands verbatim in the handoff, which then jsonschema-validates because `research_handoff_v2.schema.json` types `research_synthesis` as `{"type":["object","null"]}` with **zero property constraints**. Asymmetry: the same bogus label at *fact* level instead **crashes** — `KeyError: 'PROBABLE'`, `build_handoff.py:33`, bare traceback. |
| **Presence ≠ Utilization** | R5, URF-01..06, G11 | **ABSENT** | The doc calls it an ABSOLUTE RULE and a gate. `grep -rni 'utilization\|utilisation' scripts/ --include=*.py` → **4 hits, none in `scripts/engine`**: a build-time query template, a report heading, and the literal `"tech_utilization": []` at `build_handoff.py:102`. `grep -rn 'URF' scripts/` → **1 hit** (that same heading). `grep -rn 'SG-0' scripts/ --include=*.py` → **0**. All 16 safeguard gates exist only as a 16-row markdown table. |
| **Single-source dependency** | R6, SG-01..06 | **PROSE-ONLY** (aspirational floor) | The 70% connector-diversity floor is never computed. `grep -rn 'connector' scripts/engine/*.py scripts/deliver/*.py` → 2 hits, **neither aggregates**. Every search record carries `connector`, so the share *is* computable — a 12-line probe returns `web_search share 100%` on the reference ledger — but no script computes it and the handoff reports the literal `"fetches": 0`. |
| **Tier inflation** | `tier_hygiene` | **ABSENT** (unmeasurable as built) | `kg/sources/source_catalog.json` holds an authoritative tier for **576 sources** and evidence items carry `kb_source_id` — but `kb_source_id` is consumed **exactly once in the whole codebase** (`populate_workbook.py:89`, writes a cell). Nothing joins declared tier to catalogue tier. On the skill's own reference ledger, the **1 of 3** items carrying a `kb_source_id` declares **T2** against catalogue **US-005 (SEC EDGAR) = T1** — a 1-of-1 mismatch on the only checkable item. Tier drives **35%** of the ERS core and is a free model choice from a 5-value enum. |
| **Evidence smearing** | R22, SG-09 | **ABSENT at run level** | See deliverable 7 §2. The only clone logic is over brief *query* sets at KG **build** time, appends to `warns`, and never changes the exit code. |
| **Thin evidence** | R18, R29 | **MECHANICAL per-subcap; the category floor is COMPUTED AND DISCARDED** | Control: `floors_gate.py --category P1C1 --require-synthesis` → **gate FAIL, exit 1, 47/49 FLOOR_FAILED**. But the R29 ≥20-item category minimum is thrown away by the gate expression at `floors_gate.py:44-46`: `(not category or rate < 1.0 or cat_items >= cat_min)`. Engagement scope → **gate PASS, exit 0** with `category_min20:false, category_evidence_items:3, category_min_required:20`. The 20-item floor binds only in the single case of a per-category call at exactly `rate == 1.0`. |
| **False absence** | R20, R30 | **ABSENT / SHAPE-ONLY** | R30's *"a proxy hit = INFERENCE, never FACT"* is enforced **nowhere**: the only readers of `proxy_class` are `followup.py:57` (gated on `absence_claimed`) and `floors_gate.py:110` — neither touches a positive claim. R20's *"rungs 1–4 logged"* is unchecked: a 2-rung ladder with 2 proxy classes **passes**, and `render_client_report.py:110` then prints the fixed string *"confirmed absent (4-rung ladder, 2 proxy classes)"* **to the client**. Ladders are self-attested: 3 fabricated negatives shared 1 identical query set and **0 of the 4 claimed queries appear in the search ledger**. |
| **Stealth-shallow close** | R32 | **SHAPE-ONLY**, and evaded by one word | `absence_undeclared` is a 6-alternative regex: on a 14-phrasing battery it detects **4/14 (28.6%)** and raises **3/3 false positives** on non-absence sentences containing `"no "`. End to end: *"…has **no** documented segment-strategy artefact"* → **gate FAIL**; the one-word paraphrase *"…**lacks any** documented segment-strategy artefact"* → **gate PASS, exit 0, dq_gaps []**. `closed_below_floor` *is* mechanical but is bypassed by writing a `negative` instead — conclusion `NO_EVIDENCE` makes the row count as PASSED. |
| **Analyst shorthand / shallow reading** | R31 | **SHAPE-ONLY** | `shallow_reading` is `len(rd) < 180 or rd[-1] not in '.?!"' or rd.count(' ') < 25`; `no_deep_dive` is `len(what_we_found) < 300`; `so_what_missing` is `len(...) < 30`. Four identical 216-char / 34-space content-free filler readings plus a 400-char padded `what_we_found` → **gate PASS, dq_gaps []**. |
| **STUB values** | R32's claim | **FALSE as documented** | *"STUB_ values fail the gates"* is not true: `grep -rn STUB scripts/` = 15 hits, **all inside `orient.py`'s own template, 0 detectors**. The verbatim output of `orient.py --skeleton`, still carrying **31 literal STUB strings**, needs only a self-issued waiver plus a 2-row timeline to reach **gate PASS, exit 0**. Setting `dq_answers.contradicts` to `'n/a'`, `'-'`, `'STUB'` or `'no'` each gives gate PASS (**4 of 4 stub values accepted**). |
| **Stale evidence** | R31 | **MECHANICAL, and reversible with one added fact** | The cleanest single defect in the cluster. Two runs, **identical 2019-01 sources**: honest → **gate FAIL**, `dq_gaps ['P1C1.4.1:stale_sources_no_currency_probe(2019-01)']` (proves it fires). Add **one** fact tagged `event_date 2028 / temporal_role 'planned' / aspirational true` → **gate PASS, dq_gaps [], followups {}** — and ERS core rises **2.7 → 3.7**, total **1.77 → 2.43 (+37%)**. `ers_v2.best_date` takes `max(event_date, publish_date)` with **no future guard**. Separately, `RUN_TODAY` is an unvalidated env var: `RUN_TODAY=2019-06` turns a 2019-01 source from ARCHIVAL/1.0 to **CURRENT/5.0**. |
| **Evidence fishing** | R28 | **MECHANICAL but out of domain, and the reason is never judged** | Three-way test on a 90-page report mined for 1 fact: `web_fetch` + no reason → **gate FAIL** `thin_sources ['E-110']` (control). `web_search` + `read_depth fetched` → **PASS** — out of the gate's domain, and the skill's **own golden fixture** tags its only `read_depth:'fetched'` item `connector:'web_search'`, so **0 of 3 items are in-domain**. `thin_source_reason='x'` (1 character) → **PASS**, though the same codebase demands ≥30 chars for a waiver justification. |
| **Restatement as insight** | R33 | **SHAPE-ONLY, with a structural hole** | `has_verbatim_run(n=12)` catches **5/7** reworded variants; a reordered or lightly reworded restatement escapes. And `if len(fw) < n: return False` makes any fact **under 12 words structurally un-restatable** — **3 of the 4** facts in the reference ledger are under 12 words. |
| **Uncertainty collapse** | — | **NOT the documented model** | Implemented uncertainty is `0.2 + 0.15*(hi-lo)` over ceiling hints — a reachable set of exactly `{0.2, 0.35, 0.5, 0.65, 0.8}` with **0.5 as the no-evidence default**. The documented model (per-category base ±0.3–0.5 plus URF and gap modifiers, cap ±0.8, *"if exceeded mark Cannot reliably estimate"*) is not implemented: `grep -rn 'reliably estimate' scripts/` → **0**. |

**Fourteen traps. Enforcement: 1 fully mechanical and sound (R1 workbook path), 4 mechanical
but scoped wrong or reversible, 5 shape-only, 4 absent.** Not one of the fourteen tests whether
the evidence answers the question that was asked.

**A directional bias nobody wrote down.** Downward-only band movement *is* mechanically enforced
in three places (`challenge_verdict.schema.json` bounds `ceiling_band_delta` to
`minimum:-2, maximum:0`; the YAML card says *"only downward"*; `build_handoff.py:52` clamps with
`max(0, ...)`). The **rationale appears nowhere**: greps for `conservat|downward|only down|never
up|upward|raise the band` return 2 hits, one of them the word *"conservatorships"* in a source
catalogue. And it is not even consistently downward — `band_from_hints([])` returns `('M2', 0.5)`,
so **45 of 49** subcaps with **zero evidence** carry `ceiling_band: "M2"`, and the P1C1 rollup
reads **M3** at `floor_pass_rate: 0.041`. That fabricates a band upward from nothing, which is
the live app's invariant 9 (*never a default that looks like data*) violated in the skill tree.

---

## Part B — Three verdicts on the §6.2 challenge layer

### B1 · Is the challenge layer independent? — **NO. It is not a second opinion; it is the same opinion, unexecuted.**

**Twelve challenge dimensions. Zero implemented.** Ran the roll call:

```
for d in evidence_diversity tier_hygiene recency_decay m_delta_fit counter_evidence \
         synthesis_quality coverage_honesty floor_compliance conflict_resolution \
         single_source_concentration theme_coherence; do grep -rn $d --include=*.py scripts/; done
→ 0 hits for 11 of 12
```

The twelfth, `precedence`, hits only the KG graph builder. `grep -rn counter_evidence` returns
5 hits — a YAML card, two protocol lines, and a hand-written smoke fixture — and **0 in
`scripts/`**. Every dimension is an LLM prompt line in a 10–24 line YAML file, evaluated by the
same model that wrote the synthesis, with no independent input.

**And its own independence proxy contradicts the rule it implements.** The correct rule *is*
written — `evidence_methodology.md:85-87`: *"Independent means different origins … same author,
same incentives."* The only mechanical proxy anywhere (`challenge_protocol.md:31`,
`category_challenge.yaml:13`) counts **domains**. Proved the gap with a probe: three sources for
one claim — a vendor press release (T4), a trade article **quoting it** (T3), and a wire
syndication **of the same release** (T4), all tracing to **one origin**. Result:
`floors_gate --require-synthesis` → `{evidence: 4, sources: 4, t1_t3: 2, status: 'PASS'}`,
**zero dq_gaps, zero followups**, handoff `{ceiling_band: 'M2-M4', confidence: 'HIGH',
floor_status: 'PASS'}`. The archive's own independence proxies read clean: 3 distinct
`source_name`, 3 distinct `netloc`, max domain share **0.33** against a **0.40** threshold.
`grep -rniE 'source_domain|syndicat|netloc|urlparse|republish' --include=*.py scripts/` → **0**.

**`corroboration_score` is a hand-entered 1–5 float passed straight into `ers_v2.compute()`
with no validation.**

**Batch dilution is unbounded by design.** 136 capabilities, sizes 2–29, median 5, mean 6.26;
**23 of 136 (17%) hold ≥10 subcaps and cover 247 of 851 subcaps (29%)**. One card pass over the
largest (P3C1.8, 29 subcaps) must ingest ~87 floor-minimum evidence items (~**37.7k tokens** of
ledger slice) and emit **29 × 7 = 203 dimension judgements**, against a **flat** output budget of
~150–250 tokens per subcap. The smallest (P1C4.10, 2 subcaps) ingests ~2.6k tokens for 14
judgements. That is a **14.5× ratio** in both input context and judgement count inside a single
pass, with no chunk cap: `challenge_protocol.md:5-7` mandates batching per capability **with no
size limit**, while R27 elsewhere caps a work card at ~750 tokens.

> **BLOCKED sub-check, recorded honestly.** The audit asks for verdict distribution measured
> against batch size. **No corpus of real challenge verdicts exists in either tree**:
> `grep -rln '"scope": *"subcap"'` returns 2 files, both the card template and a single
> hand-written synthetic PASS. Zero real runs on disk. The dilution figures above are structural
> (capability sizes, token budgets, judgement counts) and are measured; the verdict distribution
> is **not measurable today**. It unblocks with one archived run directory carrying a populated
> `01_evidence/ledger.jsonl` with `kind=verdict` records — then it is a one-line group-by.

### B2 · Does `provisional: true` survive to the app? — **NO. It survives exactly one hop, then dies at a file nothing reads.**

Traced across both trees. In the archive, `provisional` has **6 hits** (a card example, a
protocol line, a schema property, `build_handoff.py:68`, a smoke fixture). It **does** survive
one hop: `build_handoff.py:68` emits `subcap_records[].challenge = "PROVISIONAL"` and
`research_handoff_v2.schema.json:155` enums it.

Then it dies, and the death is total:

| Consumer | `provisional` reach |
|---|---|
| `populate_workbook.py` | `grep -c challenge` = **0** |
| `dma-assessment` skill (the next consumer) | `ceiling_band` **0**, `subcap_records` **0**, `research_synthesis` **0**, `provisional` **0** — it reads only `locked_peer_set[]` |
| Live repo (`apps/{api,mcp,worker,web}`, `packages`, `migrations`, `plugins`, `scripts`, `infra`) | `subcap_records` **0** / `ceiling_band` **0** / `ceiling_band_delta` **0** |
| Pinned Assessment Report v8 | `grep -ic provisional` = **0** |

**And it is optional upstream, so the normal unattended outcome is not `PROVISIONAL` — it is
`null`.** Nothing requires a verdict to exist: `grep -c verdict` = **0** in `floors_gate.py`,
`followup.py`, `validate_workbook.py` and `render_client_report.py`, and
`challenge_verdict.schema.json` is **never validated at runtime** (1 hit, a docstring). Measured
on the probe run: **49 handoff records, challenge distribution `{PASS: 1, None: 48}`**, and a
floor-PASS subcap reached `confidence: HIGH` with `challenge: null`.

Worse, the one path that *does* carry a verdict launders it. `'PROVISIONAL' if v.get('provisional')
else v.get('overall')` means **the word FAIL never reaches the handoff for a provisional record** —
a failed, provisional challenge still emits `confidence: 'HIGH'` and an unchanged uncertainty of
0.35. `ceiling_band_delta` *does* apply (a verdict delta of −2 moved M2-M3 → M1), so the machinery
works; it is simply never required to run.

**Verdict: the challenge layer is advisory in the archive and invisible in the product.**

### B3 · Terminal state of an `open_conflict` with no human to ask — **PARKED, PASSING, INVISIBLE.**

Ran the protocol's own exit condition unattended. A conflict record was ledgered, the tie-breaker
fired as a `route_id`-carrying search, a client discovery question was logged, and the synthesis
was parked with `contradiction_disposition: 'open_conflict'` and `claim_label: FACT` — exactly as
the protocol prescribes. Then, with no human to ask:

| Where it went | Result |
|---|---|
| `floors_gate --require-synthesis` | **dq_gaps naming the subcap: NONE.** `unclarified_hypotheses: False` — `floors_gate.py:100` short-circuits on `claim_label != 'FACT'`, and this record *is* FACT, so the branch that would catch it is skipped. Floor row **PASS**. |
| Handoff | `{ceiling_band: 'M2-M4', confidence: **'HIGH'**, challenge: null}` |
| It **is** carried into the machine artefacts | `research_synthesis.contradiction_disposition = 'open_conflict'`, `conflict_register` = 2 entries, workbook cell `Subcap_Synthesis!Contradiction_Disposition = 'open_conflict'` |
| Client-facing render | **Invisible.** `render_client_report.py:79-80` splits on `claim_label == 'FACT'`, so the conflicted subcap is listed under **"B.2 Priority Capabilities (HIGH confidence)"**, "B.3 Caution Capabilities (LOW confidence)" is left **EMPTY**, `report_gaps: []`, and the string `open_conflict` appears **nowhere** in `client_profile.md`. |
| App reach | `grep -rn 'open_conflict\|contradiction_disposition\|conflict_register'` across `apps/{api,mcp,worker,web}`, `packages`, `migrations`, `plugins`, `scripts`, `infra` = **0 / 0 / 0**. `grep -rn Subcap_Synthesis` live = 1 hit, prose in a corpus map, not a parser. `classify('client_profile.md')` returns **None** — the artefact registry requires `.docx`. |

The protocol's honesty mechanism works perfectly right up to the last hop, where the filter keys
on `claim_label` instead of `contradiction_disposition`. **A conflict the system correctly
recorded is published as a high-confidence priority capability.**

---

## Part C — The §6.3 walk-through

The full eight-leg table, every leg measured, is in **`s6.3-wrong-but-perfect.md`**. Summarised
here because it is the deliverable's centrepiece.

**The claim traced:** *"Institution X has deployed [Platform] across its servicing estate"* —
supporting a Competing band on the servicing cells and a **hot** platform-fit card recommending
the adjacent module. The fact underneath is true-but-misread: the vendor announced a **signed
contract**. Presence, not utilization.

**Every gate it passes, and why:**

| # | Gate | Why it passes |
|---|---|---|
| 1 | ERS corroboration | `_corroboration()` counts `count(DISTINCT e.source_domain)` while its **own docstring** says *"Distinct ORIGINS … Two documents from one domain are one source."* One syndicated release on three domains ⇒ `independents=3` ⇒ **corroboration 5, the maximum**, at ERS weight 0.20. |
| 2 | **ET-01, ET-02** / invariant 4 | All three citations genuinely resolve, are entity- and run-correct, and carry verbatim excerpts. Invariant 4 is about **provenance**, never about **responsiveness**. |
| 3 | Presence ≠ utilization | The app *correctly* registers a presence fact as presence. **Nothing anywhere compares the registered status against the score the cell received.** No gate in the 69 addresses it. |
| 4 | **CG-30** | The card omits `readiness`. `validation2.py:1482` builds the engine input with `r.get("readiness") or "green"` → multiplier **1.00** → the engine returns exactly what the card shipped. **Agreement guaranteed by construction.** Max reachable fit **62.0 → 99.0**. |
| 5 | **CG-31** | The tile copies the card; both wrong the same way. CG-31 pins tile↔card and **never** tile↔ground-truth — the exact mechanism the memory records as **MEM-0095**'s fourth sighting, observed **after** REF-0038 landed. |
| 6 | **AG-11, AG-12, CG-27, CG-29** | All four are **instance detectors**. Measured across the wider prose sweep: **16 of 19 same-class variants ship silently** across 5 prose gates, with **5 of 5 benign controls correctly silent**. Written without digits, without the nine `_ACCUSATORY` patterns, without an acronym outside the 30-entry `EXPANSION` map, and with a per-section thread, the prose is invisible to every one. |
| 7 | Grain reconciliation (0.05) | A consistently-wrong number reconciles perfectly. Grain checks arithmetic **consistency**, never correctness. |
| 8 | **Promotion** | 69 gates: **67 `block`, 2 `disclose`**. Nothing above raised a blocking reason, and the two `disclose` gates (SG-V4, SG-S8) **could not block even if they fired**. |

**What stops it today: nothing in the application.** The one control that would — R5 + URF-01..06
+ the 7-dimension `counter_evidence` challenge — lives in the **unshipped** v4.2 research skill.
`grep -c 'URF-' plugins/dma-insights/skills/dma-research/` = **0**.

**The shape of the failure.** Every gate in the path checks an **internal relation** — does the
id resolve, does the tile match the card, does the arithmetic reconcile, does the prose avoid a
known string. Not one checks the **external relation**: does this evidence answer the question
that was asked, and does the score match what the evidence actually shows. That is precisely the
judgement a human reviewer supplies, and it is the judgement the unattended architecture removes.

**Two of the eight legs are one-line fixes whose correct constants already exist in the repo:**

- **Leg 4** — change `r.get("readiness") or "green"` to use `READINESS_DEFAULT`, which already
  sits at `platform_fit.py:119` as `"amber"`, with a comment saying exactly why:
  *"Green would reward a card that established nothing."*
- **Leg 1** — count distinct **origins** rather than distinct **domains**. The docstring already
  specifies the right rule; only the SQL disagrees with it.

Fixing those two breaks the chain at legs 1 and 4 and costs two lines. It does not fix leg 3,
which is the real one.
