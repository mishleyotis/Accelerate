# Deliverable 7 — MECE DQ report

Five-facet completeness across all 851 briefs, anti-clone collision count, the generic-render
and post-G10 vendor-name findings, and the DQ→query drift rate. Every figure below carries its
denominator.

---

## 1 · Five-facet completeness — **COMPLETE, and machine-clean**

Walked all 16 category packs (`kg/packs/P*/P*C*.json`). The container key is `briefs` (a dict);
each brief carries `dq` as a list of `{f, q, sig}`.

| Measurement | Value | Denominator |
|---|---|---|
| Briefs walked | **851** | all 16 packs |
| Facet-count histogram | **`{5: 851}`** | every brief has exactly five |
| Occurrences of each facet name (`works`, `fails`, `value`, `contradicts`, `corroborates`) | **851 each** | 851 briefs |
| Briefs deviating from the canonical facet set | **0** | 851 |
| Briefs with the first four out of `works, fails, value, contradicts` order | **0** | 851 |
| Total DQ rows | **4,255** = 5 × 851 | matches the pinned workbook's `DQ_Bank` claim exactly |
| `validate_kg.py` on the shipped KG | `851 briefs \| FAILS=0 WARNS=10`, rc=0 | the 10 warnings are all W3 pack-size soft budget (266–464 KB) |

Within-subcap MECE is the strongest single artefact in the system. It is exhaustive by
construction and it verifies.

**And exclusivity holds too.** G8 — the build gate that enforces MECE exclusivity — is real and
mechanical: `validate_kg.py:142-156` computes pairwise token-Jaccard over each brief's five DQ
texts, with the subcap's own name tokens and stopwords removed, and fails above 0.6. The
shipped KG passes at FAILS=0.

**Open-question discipline holds across the whole corpus.** Scanned all **4,255** DQ texts with
a yes/no opener regex (`^(is|are|does|do|did|has|have|was|were|can|could|will|would|should)\b`):
**0 hits**.

> One deliberate structural asymmetry, verified rather than flagged: the **851** DQ rows with no
> `{entity}` placeholder are all and only the `corroborates` facet — one per brief. That is by
> design; that facet asks which independent sources reinforce the dominant claim, so it does not
> name the entity.

---

## 2 · Anti-clone (R22) collision count — **the gate that fires is not the gate that matters**

Two different guards share the name.

**The build-time one measures QUERIES and cannot block.** `grep -rn 'clone'` over the whole
archive = **4 code hits, all in `scripts/build/validate_kg.py`** (W2 at :39-46 over
primary-*query* sets; W4 at :161 over works-signal tuples); **0 hits in `scripts/engine/` or
`scripts/deliver/`**. Forced W2 by cloning 3 sibling primary-query sets in a KG copy →
`WARN W2 query-clone clusters (>=3 siblings identical): 1` and **EXIT=0**, because
`validate_kg.py:187` is `sys.exit(1 if fails else 0)` and a warning never changes the exit code.

**The runtime one that R22 and SG-09 actually describe does not exist in any file.**
R22/SG-09 specify *">60% identical **evidence IDs** across ≥3 sibling rows."*
`grep -rn subcap_evidence scripts/` = **6 consumers** (ledger writer, `followup`, `floors_gate`,
`orient`, `build_handoff`, `populate_workbook`), **none computing pairwise overlap**. The data
is present; the check is not. A 12-line probe computes it.

**Collision counts, measured:**

| Measurement | Value | Denominator |
|---|---|---|
| W2 query-clone clusters on the shipped KG | **0** (W2 never fires) | 851 briefs |
| Run-level evidence-id overlap clusters (my probe, >60% over ≥3 siblings) | **0** | the 4-subcap fixture — the only run on disk |
| **Sibling pairs at 100% shared evidence ids in the archive's own golden fixture** | **1** — `P1C1.1.2` / `P1C1.1.5`, both `= {E-001}` | 4 subcaps; nothing reports it |
| Byte-identical DQ text reused across different subcaps | **26 distinct texts covering 52 of 4,255 rows = 1.2%** | 4,255 DQ rows |

The 1.2% textual clone rate is genuinely low. The finding is not the rate — it is that the
golden fixture ships a 100%-overlap sibling pair that no code anywhere looks at.

---

## 3 · The generic-render finding — **placeholders reach the search engine**

`kg_reader.py:161` guards rendering with `if a.sv or ctx:`. With `ctx = {}` (falsy),
`dq_generator.render()` is **never called**, and `kg_reader`'s only four `sys.exit` guards
(lines 19, 26, 142, 146) all concern unknown category or ids. So:

```
kg_reader.py briefs --kg kg --capability P1C1.3 --set es_CU_FULL.json --ids P1C1.3.1 --lean
  (no --sv, no --entity, no --context)
→ EXIT=0, no warning
```

and the emitted card carries the **literal token `{entity}` in all 5 DQs and all 5 queries**,
plus literal `{sv_tiebreakers}` in the `contradicts` DQ. A headless agent firing `q.primary`
verbatim searches a web index for the literal string `"{entity}"`.

**This is not an edge case — it is the documented session opener.** `orient.py:89`, the
R32-mandated first command of every session, invokes `next ... --sv {man[sv]}` with **no
`--entity` and no `--context`**:

```
orient.py --run /tmp/smoke_run --category P1C1
→ next_card containing 15 literal '{entity}' tokens
```

**Root cause:** no script creates `00_entity_profile/context.json`. `grep -rn 'context.json'
scripts/` = **1 hit**, `render_client_report.py:41`, which silently degrades to `{}`.
Nothing enforces Rule 16, and no warning is emitted at any point.

---

## 4 · Post-G10 vendor names — **the gate scans the question; the query is what gets fired**

G10 (`validate_kg.py:93-116`) has both a **scope** gap and a **time** gap.

**SCOPE.** The gate scans exactly three things: each brief's `dq[].q`, each pack's
`category_dq.q`, and `category_dq.sweep_queries`. It **never** scans `b['q']['primary']` — the
per-brief pre-built search queries — or `b['routes'][].q`. Scanned the shipped KG with the
gate's **own** vocabulary (`kg/runtime/tech_vocab.json` plus its 12 hardcoded names), excluding
each subcap's own name tokens:

| Field | Vendor-name hits | Scanned by G10? |
|---|---|---|
| `dq[].q` (the diagnostic question) | **0** | yes — G10 works |
| `routes[].q` | **0** | no |
| **`q.primary` (the query actually fired)** | **103** | **no** |

Example: `P1C1.5.4` primary query — `"{entity}" Einstein OR Agentforce OR copilot`.
So the **question** is platform-agnostic and the **query sent to a search engine names vendors**.

**TIME.** Client context injects vendor names *after* build-time validation, with nothing
re-checking. Ran `kg_reader.py briefs --context` with a benign entity
(*"Riverbend Community Credit Union"*) and vendor-laden `extra_terms`: `routes[].q` vendor
occurrences went **0 → 22** on one capability of 8 briefs. And with a vendor-named entity,
`{entity}` substitution puts the vendor name into **32 of 40** rendered DQ texts (baseline 0).

G10 is a build-time gate guarding a runtime property.

---

## 5 · DQ→query drift rate — **40% of facets have no responsive query at all**

Sample: **28 subcaps**, 7 per pillar, stratified across all 16 categories, seed `20260828`.
Drift measured over the sample's **28 × 5 = 140 DQ/query pairs**:

| Band | Count | Share |
|---|---|---|
| **No responsive query at all** | **56 of 140** | **40%** |
| Partially responsive | ~56 of 140 | ~40% |
| Squarely served | ~28 of 140 | ~20% |

The 40% with nothing responsive is not scattered — it is **structural and facet-aligned**:
`corroborates` **28 of 28** and `value` **28 of 28**. Confirmed against the full 851:

- **`corroborates`** — **1 of 851** briefs has *any* query carrying corroboration vocabulary
  (`independent|corroborat|second source|third party|analyst`). The facet that exists to
  establish independence has, corpus-wide, essentially no query that would establish it.
- **`value`** — **231 of 851** have any query with outcome vocabulary
  (`result|impact|outcome|roi|benefit|savings|revenue|growth|cost`), and **none** names the
  consequences the DQ actually asks for.
- **`works`** demands *"trace the arc from earliest signal."* The earliest year token in **any**
  query per brief is 2023 for 209, 2024 for 190, 2025 for 189, and **absent entirely for 263**.
  **0 of 851 reach before 2023.** The facet asks for an arc; no query can see one.
- **`contradicts`** hunts adverse events rather than source disagreement — responsive to a
  different question than the one asked.
- **`fails`** is the only facet squarely served, and only where the archetype route matches
  (~17 of 28 in the sample).

**Why the drift is structural.** All **851** primary-query sets derive from **10 archetype
templates** (`build_kg.py:93-104`), and **821 of 851** first-primaries are literally
`"{entity}" <subcap name> <archetype suffix>`. Five distinct diagnostic questions are served by
one name-plus-suffix query. The questions are MECE; the searches behind them are not.

**A refuted hypothesis, reported per §2.5.** `q.negative` and `q.contradicts` are **not**
lexical near-duplicates: token Jaccard over 851 is **median 0.25, max 0.30**, and **0 of 851**
exceed G8's own 0.6 threshold. Their redundancy is *semantic* — both hunt adverse events — not
lexical, so no token-overlap gate would ever find it. The prompt's proposed detection mechanism
would not work; the underlying concern is real.

---

## 6 · What this means for an unattended run

The MECE corpus is the best-engineered thing in this system: complete, exclusive, open-question,
low-clone, and it verifies. Every one of those properties is established **at build time**, and
`SKILL.md:378` says so explicitly — `validate_kg.py` is *"build-time only … Not run during
engagements."*

At runtime, four things go wrong and none of them is visible:

1. The question is platform-agnostic; **the query is not** (103 vendor names in `q.primary`).
2. Client context injects **more** vendor names after the last check that could have seen them.
3. Two of the five facets — `corroborates` and `value` — have **no responsive query**, so an
   agent that fires the queries and answers the questions is answering two of them from nothing.
4. Without `--entity` and `--context`, which the documented session opener does not pass, the
   agent searches for the literal string `{entity}` at **exit 0, no warning**.

The corpus is MECE. The *search* is not, and no gate is positioned to notice the difference.
