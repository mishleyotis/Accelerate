---
name: dma-research
description: >
  Conducts subcapability-level public evidence research for Digital Maturity Assessments
  of financial services institutions. Reads diagnostic questions from Pillar XLSX toolkits,
  generates targeted search queries for each of 851 subcapabilities, executes web searches,
  maps evidence to specific subcap rows, and populates the scoring workbook with evidence
  (leaving score columns empty for dma-assessment). NO scoring, NO maturity levels — ceiling
  estimates with uncertainty bands ONLY. ALWAYS use when the user mentions: DMA research,
  evidence collection, pre-assessment research, tech stack discovery, entity profiling,
  subvertical classification, or any request to gather evidence before DMA scoring.
  Also covers what the retired dma-p1, dma-orchestrator and dma-core skills did: P1 or
  Pillar 1 research, research handoff, CCG/RSG inspection, SIB assembly, ESG research
  (P1C5 lineage), public-only, internal-only or hybrid DMA research engagements.
---

# DMA Research Skill v2.5

This skill produces the **evidence foundation** for a Digital Maturity Assessment. It does
NOT score — it researches. Its output is the run's ONE scoring workbook with the evidence
columns populated and column D (Score) empty for `dma-assessment`.

Version history: `references/CHANGELOG.md`. Terms: `${CLAUDE_PLUGIN_ROOT}/docs/GLOSSARY.md`.

## Reading manifest — by phase

The engine (`engine.cli`, `engine.brief`, `engine.pipeline`, under `engine/`) is the run's
authority: it creates the workbook, serves the work, refuses what does not belong, and
computes every count. The prose below is what a person or a lane reads to work it.

| Phase | Read | Why |
|---|---|---|
| Session start | this file's *How a research run is worked* and *Rules*, `references/RESEARCH-PROTOCOL.md` | who you are in the run, and the loop |
| PRELIM | `references/subvertical_profiles.md`, `references/tech_discovery.md`, `references/source_catalogue.md` | the binding, the estate, the T1 sources |
| A category lane | `engine.brief dispatch` (the packet), `references/core_engine.md`, `references/deep_search_protocol.md`, `references/evidence_methodology.md` | the loop, the query ladder, the tiers |
| Declaring an absence | `references/org_capability_proxies.md`, `references/uncertainty_framework.md` | the proxy ladder and the ceiling estimate |
| Closing a category, closing the run | this file's *Closing*, `references/research_workbook_spec.md` | the gates in order, and what the sheets must carry |
| The client research profile | the report tier's brief (`report-research-producer`), `references/document_formatting.md` | written INTO the pinned template through `engine.cli narrative`, never from a remembered shape |

## How a research run is worked

You are one of three actors, and your dispatch brief says which:

- the **`research-conductor`** — drives `engine.pipeline`: PRELIM, the sixteen category
  lanes, the challenge pass, the floors gates, the handoff. It holds the connectors (Exa,
  Tavily, Clay) and services every lane's `search_requests` per capability batch;
- a **`research-pXcY-producer`** — one category of one run, under
  `references/RESEARCH-PROTOCOL.md`. It searches the open web, logs every search, notes as it
  goes, consolidates through the ledger's refusals, synthesises, and hands back. It holds no
  connector: a connector volley is EMITTED as a `search_requests` entry, never fired;
- a **relay subagent** (`enrichment-web-specialist`, `enrichment-connector-specialist`) —
  services one `briefs/relay_r<n>/` batch through the connector it holds and records each
  result with the tool that produced it.

**The workbook is the only record.** `engine.cli start` created it from `engine/contract.py`
(41 sheets, 33 columns per pillar sheet, every scoring row seeded with its `SubCap_Name`).
Evidence enters through `engine.cli evidence` (a verbatim 50–500-character excerpt, checked
against the text `engine.cli fetch` cached — because a span the run never read cannot be
audited); searches through `engine.cli search --subcap … --facet … --tool …`; syntheses
through `engine.cli synthesise`; absences through `engine.cli absence`. ERS and every count
are computed by the engine — never type one. Never write a JSON or XLSX beside the run:
the seven batch-era scripts are retired and refuse, each naming the engine command that
replaced it (the *Scripts* table below lists them).

**Search shape.** Five volleys per cell (`works`, `fails`, `value`, `contradicts`,
`corroborates`) plus the toolkit's `primary` question, fired at capability grain and logged
per cell — the floors gate counts them. Read pages as windows (`engine.cli fetch`), never
whole: a whole page is re-read on every later turn and was 76 % of one run's bill. The tool
precedence — which engine first, which connector when, what is emitted rather than fired — is
stated ONCE, in `references/RESEARCH-PROTOCOL.md` § *Tools: first choice, fallback, and what
you emit*; nothing in this skill restates it.

**Done** = `engine.cli gate --run <R> --category <C> --require-synthesis` prints PASS, then
`engine.brief handback --category <C>`. Nothing pauses for a person's go-ahead between
categories: the driver re-dispatches, and a lane that ran out of budget checkpoints and ends
its turn.

## Rules

Each rule names the failure it prevents; the engine refuses most of them outright.

| # | Rule | Why |
|---|---|---|
| 1 | **No scoring.** Ceiling estimates with uncertainty bands only; never a score. | Column D is struck by `engine.assessment score` from a challenged synthesis; a score written here is a score nobody challenged. |
| 2 | **Every claim labelled** `FACT` / `INFERENCE` / `HYPOTHESIS` / `CEILING_ESTIMATE` (`contract.CLAIM_LABELS`). The ledger derives the label from the tier when you omit it and refuses a FACT on T3 or weaker (`contract.FACT_TIERS`). | The scorer reads the label to decide what the evidence can carry; 77 FACT rows on T3/T4 in one staged run were the audit's blocker. |
| 3 | **Every claim cited** by evidence id, every evidence row by a specific URL (or `--origin internal`). | A claim with no row behind it cannot open a drawer, so the app renders it as nothing. |
| 4 | **Compact output** — one line per finding, no narration, no preview. | Your context is re-read on every turn; prose in chat is paid for on every turn after it. |
| 5 | **Presence ≠ utilization.** A product found is a ceiling estimate until utilization is evidenced. | "Uses Salesforce" and "uses Salesforce effectively" score two levels apart. |
| 6 | **Search at capability grain, log at the cell** — five volleys plus `primary` per cell, one query fired once for the group and logged against every cell it bears on. | `volleys_incomplete` and `primary_unfired` block the floors gate; `evidence_smear` blocks a cell whose citations are more than half shared. |
| 7 | **One workbook, one writer.** Nothing beside the run. | A second workbook is the "wrong structure every run" defect the retired writers produced. |
| 8 | **ERS and counts are computed.** `engine.cli ers recompute`; never a typed score. | A typed ERS is a number nobody can recompute (invariant 10). |
| 9 | **Read the card's questions first** — the toolkit's diagnostic questions drive the search. | A query the DQ did not shape is a generic search that answers a different question. |
| 10 | **Extract at fact level** `[E-xxx:Fy]` — one rich document read as windows yields facts for many cells. | Single-fact extraction pays for the same document once per cell. |
| 11 | **HYBRID / INTERNAL: five-layer analysis** — explicit, implicit, absence, contradiction, strategic — on every internal document. | Internal evidence read only for what it states misses what it omits. |
| 12 | **Peer set locked at PRELIM** (`engine.prelim peers`, 3–5 peers) and carried unchanged into scoring. | Peers chosen after the evidence is in are peers chosen to flatter it. |
| 13 | **70 % evidence-coverage floor per category** — the floors gate blocks on `coverage_below_floor`; the long tail is worked with the DQ facets as probes and the absence ladder, and honest absences are declared only AFTER a deep search. | Shallow categories where most cells are marked no-evidence without a proxy search (AUD-0115). |
| 14 | **Synthesise, then an INDEPENDENT challenge, before scoring.** A different actor records the challenge; `handoff.build` refuses a category that did not clear the gate with `--require-synthesis`. | A score should reflect a challenged claim, never raw evidence (AUD-0116). |

## Evidence tiers

| Tier | Type | ERS weight | Score ceiling (`engine.assessment.TIER_CEILING`) | Examples |
|---|---|---|---|---|
| T1 | Regulatory / audited + verified machine scans (`contract.SCAN_TIER`) | 1.0 | 5.0 | Call reports, enforcement orders, Hubbl, BuiltWith, Wappalyzer, Explorium |
| T2 | Official disclosures + structured internal | 0.85 | 5.0 | Annual reports, 10-K, investor decks, discovery notes with specific tech or metrics |
| T3 | Third-party analysis | 0.7 | 4.0 | J.D. Power, Forrester, app ratings |
| T4 | Internal, unvalidated narrative | 0.55 | 2.5 | Unstructured memos, anecdotal claims |
| T5 | Marketing / claims | 0.3 | 2.0 | Website claims, brochures — requires corroboration |

A single source, whatever its tier, caps at 3.0; a FACT needs two source identities.

**Classifying an internal artefact** (one tree; `references/evidence_methodology.md` points here):

```
Machine-generated scan (Hubbl, BuiltWith, Wappalyzer, Explorium)?      → T1
Structured engagement notes, policy docs, board decks, roadmaps with
  specific tech or metrics?                                             → T2
Formal internal document, general, without specific metrics?            → T3
Informal memo, email, anecdotal claim?                                  → T4
```

Never file a machine scan as T4 — it silently suppresses the score through the T4 ceiling,
and the ledger refuses a named scan at any tier but T1.

**Recency** (`contract.RECENCY_LADDER`, months before the run's pinned reference date):
CURRENT (<12) · RECENT (<24) · DATED (<36) · STALE (<48) · ARCHIVAL (≥48) · UNVERIFIED
(undated, or dated in the future). Undated is a band, never current; a quarter or a month is
a date (`2025-Q4` resolves to the quarter's end).

## Claim labels

| Label | Citation rule | Shape |
|---|---|---|
| FACT | evidence ids on T1/T2, two source identities | `[E-003] NCUA Q4 2024 (T1, CURRENT): assets $4.2B. (FACT)` |
| INFERENCE | 2+ evidence ids + the logic | `[E-012, E-015] AppExchange listing + a "Salesforce Admin" posting: likely FSC. (INFERENCE)` |
| HYPOTHESIS | evidence ids + the proxy attempts | `[E-030] no digital officer title in leadership; board bios searched, no tech background [E-031]. (HYPOTHESIS — validate against the org chart)` |
| CEILING_ESTIMATE | evidence ids + the uncertainty | `P4C3 ceiling 3.5 (±0.5): presence confirmed [E-018], utilization unknown. (CEILING_ESTIMATE)` |

A "not found" is a HYPOTHESIS only with the proxy searches listed; without them it is a
research failure, and `engine.cli absence` refuses it because the Search_Log will not show
the searches. The payload's H6 `claim_type` is a different field with its own enum, owned by
the page contract (`get_page_contract heatmap`); the surface producers read that contract,
never this table.

## Research checks (RS-01 … RS-06)

Checks on THIS SKILL's own search behaviour, computed by the floors gate and the handback.
They are not connector gates, never appear in a payload, and `explain_gate` does not know
them — which is why they carry the `RS-` prefix and not `SG-`: they were `SG-01…SG-06` until
2026-08-23, and the collision cost a production session a contradiction it could not settle.
The `SG-` namespace belongs to `apps/mcp/dma_mcp/gates.py` alone.

- RS-01: at least one search per cell ran through an enrichment connector, logged with the
  tool that ran it (`absence_single_tool`); a lane emits it, the conductor services it
- RS-02: every askable volley of every cell has a logged `engine.cli search` row
  (`volleys_incomplete`, `primary_unfired`)
- RS-03: the entity's primary site and its filings were read through `engine.cli fetch`, so
  their excerpts verify
- RS-04: connector results are layered onto the web search results, never replacing them
- RS-05: negative results are recorded — every empty cell is DECLARED through
  `engine.cli absence` with its ladder (`absence_undeclared_empty`)
- RS-06: the financial trajectory covers five years (PRELIM's banked series; the scoring
  stage refuses to open without it)

## Internal evidence (HYBRID / INTERNAL runs)

1. **Load internal evidence first** — the conductor's `drive_fetch.py pull` lands the client's
   documents under the run root (`01_intake/`; `run_manifest.json` names the path). Read the
   NAMED artefact your card lists; an artefact the pull did not land is a `search_requests`
   entry with `"tool": "drive"`, never a gap.
2. **Classify with the one tree above** — never default internal evidence to T4.
3. **Cross-reference** against public evidence; note agreements and contradictions
   (`engine.memory note --kind contradiction`).
4. **Weight correctly:** internal T2 outweighs public T3–T5 for the same cell.
5. **Register with `--origin internal`** and a verbatim excerpt.
6. **Gate:** in HYBRID / INTERNAL mode, more than half the cells with no internal citation
   means the documents were not read — stop and say so.

## Diagnostic question patterns

| Pattern | Evidence needed | Query strategy |
|---|---|---|
| "Does [entity] have…" | existence proof | search for the thing |
| "Is [thing] documented…" | T2+ documentation | annual reports, filings |
| "Is there a defined process…" | process maturity T2/T3 | process descriptions, job posts |
| "Are metrics tracked…" | measurement T1/T2 | reported metrics, KPIs |
| "Is [thing] automated…" | technology T3/T4 | platform, vendor, case study |
| "Is there board oversight…" | governance T1/T2 | proxy statements, charters |
| "Are results used to improve…" | optimization T2/T3 | iteration evidence, A/B testing |
| "Is [capability] integrated across…" | enterprise adoption T2/T3 | cross-department mentions, unified platform |

### Evidence sufficiency by question type

| Question type | Minimum evidence | Below minimum |
|---|---|---|
| Existence | 1 confirming, OR the declared absence with its ladder | `engine.cli absence` only after the proxy rungs are fired |
| Process maturity | 2 sources | thin — flag for internal validation |
| Measurement | 1 T1/T2 with actual values | T3+ only → INFERENCE, no hard data |
| Technology | 1 presence + 1 utilization | presence alone → CEILING_ESTIMATE |
| Governance | 1 T1/T2 governance item + a proxy search | board composition only → HYPOTHESIS with the proxy log |
| Optimization | 2 improvement-cycle references | single mention → HYPOTHESIS, low confidence |
| Enterprise adoption | 2+ cross-department references | single department → ceiling 3.0 |

**Proxy rule for the governance and strategy categories (P1C1–P1C4).** Governance evidence
is indirect, so a "not found" there is usually a search that stopped early. For every such
cell, before declaring: board bios for tech or digital background; C-suite digital
appointments (CDO, CTO, CIO); leadership with digital titles; conference presentations by
leadership; strategic-plan filings or investor-deck mentions. Each is a logged
`engine.cli search --subcap <cell> --facet <f>` and a rung named in `--ladder` /
`--proxy-log` when you declare.

## Workbook columns

The shape is `engine/contract.py: PILLAR_COLUMNS` — 33 columns per pillar sheet, printed by
`python3 -m engine.cli columns`. Columns A–K are the app-facing set; `Score` (column D) is the
assessment stage's and is struck only by `engine.assessment score`. The research tier writes
through the four commands above and never by column letter. `references/research_workbook_spec.md`
holds the write-up protocol for `What_We_Found` and the source-format rules, and a test pins
its column list to the contract.

## Closing

**A category** (`references/RESEARCH-PROTOCOL.md` § *Closing your category*):
`engine.cli gate --category <C> --require-synthesis` → PASS; `engine.memory status` shows
nothing NOTED or BLOCKED; `engine.memory backup`; `engine.brief handback`.

**The run** (the conductor, through `engine.pipeline`), every command refusing on its own
terms:

1. `engine.cli gate … --require-synthesis` for every category in scope.
2. `engine.cli validate --run <R> --root <ROOT>` — shape, vocabularies, cross-references,
   rule 8 (no absence flag without its Provenance row).
3. `engine.cli ers recompute` — ERS is computed, never typed.
4. `engine.cli complete check` — every tab filled or its emptiness declared with a reason.
5. `engine.cli handoff` — the versioned packet (`research_handoff_v2`, sha256 sidecar) the
   scoring stage verifies before it opens; it carries the run id, evidence mode, the locked
   peer set and the completeness verdict.

The client research profile is the report tier's: `report-research-producer` writes it
section by section through `engine.cli narrative write` into the pinned template
(`${CLAUDE_PLUGIN_ROOT}/references/templates/client_profile_template.md`), and `report-validator` passes no section
whose citations it did not open.

## Domain-specific rules

**P4 stricter thresholds:** HIGH = T1/T2 + corroboration + utilization; MEDIUM = T3 + stack
confirmed; LOW = T4/T5 or any red flag. Inferred technology caps at 3.0. Tenure over ten
years on a basic tier → internal validation.

**Floors the gate holds a category to:** one T1 regulatory anchor; two T1/T2 financial
sources; the five-year trend; the issue search across every regulator; sentiment attempted;
every technographic layer carrying a `Tech_Register` row; the org proxies; the diagnostic
questions loaded; coverage at or above the floor.

**Tech utilization:** `references/tech_discovery.md` (evidence levels 1–4, utilization
levels, URF-01–06 red flags, vendor tenure, recency protocol).

**Uncertainty:** `references/uncertainty_framework.md` (base ±0.3–0.5, red flags +0.1–0.2,
evidence gaps +0.1–0.2, capped at ±0.8).

**Org proxies:** `references/org_capability_proxies.md` (LinkedIn density, job seniority,
Glassdoor culture, their effect on P1C4 / P4 ceilings).

## Reference files

| File | Read when | Contents |
|---|---|---|
| `references/RESEARCH-PROTOCOL.md` | every lane, first | the loop, the volleys, the tools rule, the absence ladder, the budget |
| `references/core_engine.md` | before the first card | diagnostic question → search → evidence → row, through the engine |
| `references/deep_search_protocol.md` | before the first card | the ten-tier query ladder, proxy signals |
| `references/evidence_methodology.md` | before the first card | ERS factors, fact-level extraction, five-layer analysis, red flags |
| `references/research_workbook_spec.md` | closing | the `What_We_Found` write-up protocol, source format, and the contract's columns |
| `references/source_catalogue.md` | PRELIM | KB source ids, URLs, query templates |
| `references/subvertical_profiles.md` | PRELIM | decision tree, T1 sources, financial metrics per sub-vertical |
| `references/tech_discovery.md` | PRELIM and P4 | tech categories, utilization, URF-01–06, vendor tenure |
| `references/org_capability_proxies.md` | declaring an absence | LinkedIn density, job seniority, Glassdoor |
| `references/uncertainty_framework.md` | declaring an absence | base uncertainty, red-flag modifiers, the ±0.8 cap |
| `references/document_formatting.md` | the report tier | Zennify branding, DM Sans, python-docx |
| `references/CHANGELOG.md` | never in a run | version history |
| `references/diagnostic_questions.md` | fallback only | ONE question per category, not per subcapability — 71 in all. Not a substitute for the toolkits; a run that falls back to it runs on 8 % of the coverage the name implies, and must say so. |

Retired on 29-09-2026 (QA audit F-L11-042, the batch era): `batch_execution_protocol.md`
and `context_window.md` (retired: the six-batch, wait-for-continue procedure);
`safeguard_gates.md` (retired: the 16 research-era gates — the live SG family is the
connector's); `deliverables_spec.md` (retired: the D0–D6 / A1–A9 set — the package's four
deliverables are the workbook, the two reports and the technographic scan).

## Scripts

| Script | Status |
|---|---|
| `scripts/extract_diagnostic_questions.py` | **RETIRED** (refuses): the engine reads the toolkits at `engine.cli start`; `engine.cli orient` serves the questions per cell |
| `scripts/generate_query_plan.py` | **RETIRED** (refuses): the work card from `engine.cli orient` is the plan (F-J02-011) |
| `scripts/calculate_ers.py` | **RETIRED** (refuses): `engine.cli ers recompute` computes ERS where the evidence is banked |
| `scripts/merge_evidence.py` | **RETIRED** (refuses): `engine.cli attach` reuses a registered row; `engine.cli validate` checks cross-references |
| `scripts/populate_workbook.py` | **RETIRED** (refuses): it built a second workbook beside the run; `engine.cli start` creates the one workbook |
| `scripts/validate_coverage.py` | **RETIRED** (refuses): `engine.cli gate` is the coverage gate |
| `scripts/validate_workbook.py` | **RETIRED** (refuses): it validated the 22-column layout the engine replaced; `engine.cli validate` |

Every retired script refuses with `REFUSED` and names its engine command; a reference that
runs one fails loud rather than silently building the wrong artefact.
