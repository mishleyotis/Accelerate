# The corpus map — what feeds each surface, measured, with fallbacks

Owner instruction, 2026-08-20: the corpus survey exists to map EVERYTHING —
not just where evidence ids hide, but how each surface's storyline is
synthesized from the package and which enrichment takes precedence. This
file is that map. It was measured against the full intake corpus (178
client folders, surveyed recursively 2026-08-20 — counts in § Measured
corpus below), not asserted from the spec.

Companion files: `05-lifecycle/surface-map.md` owns the census (owner,
rulebook anchor, gates per surface); `1-package.md` owns the landing table;
this file owns **source → storyline → enrichment precedence → absence
rule** per surface. `package_map.py` resolves the names below across every
structure generation; `corpus_search.py` is how "where else does this
live?" is answered mechanically.

## The resilience ladder — the order every lookup walks

1. **Resolve** — `package_map.py` names the artefacts; ambiguities go to
   the package-vetter, never guessed past.
2. **Corpus** — `corpus_search.py` across the WHOLE package (workbooks tab
   by tab, CSVs, JSON/JSONL ledgers, DOCX/PDF reports). The package
   usually already holds the answer.
3. **Web/connectors** — only when the corpus is empty; through the
   session's claude.ai connectors, logged in the yield ledger.
4. **Honest absence** — the recorded search, its date, and what would
   change the answer. Never a blank, never an invention.

## Per-surface synthesis map

### D1 Overview

| Surface | Package sources (primary → fallback) | Storyline inputs | Enrichment |
|---|---|---|---|
| O1 scores & peers | scoring wb `Pillar_Summary`/`Category_Detail` → `export_pillar_summary.csv`/`export_category_summary.csv` (54 corpus clients are export-ONLY — the exports are then the authority); peers: `06_peers/peer_comparison_table.csv` → `Peer_Benchmarks` tab | composite vs peer median AND vs full peer range (the sharper finding when below every individual peer); the package's own methodology caveats (e.g. peer-depth asymmetry) temper the claim | — (scores never enriched) |
| O2 firmographics | `run_manifest*.json` → `00/01_evidence/entity_profile` → Client Profile report | identity anchor: charter, regulator, scale — every later claim hangs on it | P2 verification (Explorium/Tavily) |
| O3 why-now | report strategic sections; `A7_time_maps.csv`; research wb `Entity_Timeline` | dated triggers + windows; consequence of waiting argued from the client's own events | **P1 currency re-check** — a package signal is as old as the assessment date |
| O4 exec summary | the report's own executive summary is an INPUT TO CHALLENGE, never copy | written last, over settled claims; the run's single thesis | — |
| O5 opportunity | fit engine (served) + `gap_priority` appendix + `recommendations_detail.json` | tiles mirror P1 exactly | rides the P1 set |
| O6 findings | governance issue registers; `gap_priority`; report findings sections | ranked by stated basis; quantified consequence per finding | P2 corroboration |
| O7 leadership | `entity_profile` (partial at best); package conflicts (e.g. a CDO identity the package left unresolved) ship as recorded absences | who owns the transformation; arrivals as why-now signals | **P0 — package rarely carries a roster**: Clay/web verification before any name renders |
| O8 financial | report figures → regulator series | trajectory direction argued with the outside world's numbers | P2 corroboration (filings) |
| O9 sentiment | **not in the package** (no sentiment store observed corpus-wide) | rated bars with n · scale · as_of | **P0 — enrichment-first** (Tavily app-store/review aggregates) |
| O10/O11 coverage | `A8_coverage.csv` → `export_coverage_stats.csv` | internal instrumentation; denominator reconciles to H4 | — (NEVER_SERVED) |
| O1b ceilings | `caps_applied_log.csv` (three header generations) + issue registers (BREACH-style caps with expiry) | what caps the score and until when | — (internal) |
| O12 thought leadership | **not in the package** | the entity's own public voice, dated, verbatim | **P0 — enrichment-first** (Exa) |

### D2 Insights · D3 Heatmap

| Surface | Package sources | Storyline inputs | Enrichment |
|---|---|---|---|
| I1 insight cards | research wb `Subcap_Synthesis`; contradiction logs; issue registers | each card argues claim → mechanism → decision, grounded in register rows; the package's own contradictions become challenges | P2 corroborate+falsify per external claim |
| T2 landscape | `A4_Tech_Stack.csv` → techstack rows in evidence stores; Explorium validation xlsx as corroboration (auxiliary, never the register itself) | counts recomputed from T1 | rides T1 |
| H4 grid | scoring wb subcap tabs → `export_scoring_detail.csv` | grain: stated figures with source cells | — |
| H1 focus areas | Client Profile report quotes (verbatim, with page); internal notes when present (meeting notes, handoff notes exist in several folders) | client-stated priorities in the client's words, currency re-checked | P2 falsifier pass per named gap |
| H2/H6 evidence | ALL evidence stores via `evidence_normalize.py` (up to ten per package: `evidence_index.csv/json`, `ledger.jsonl`, `A3_evidence_register.csv`, `export_evidence_inventory.csv`, research wb tabs — locations vary by generation, incl. `07_governance/layer2_audit/`) | the register IS the story's ground | **P1 schema-fit retrieval** for rows the corpus cannot complete |
| H3 alerts | `layer1_qa` thin-evidence register; coverage exports | the run's honest residue; ladder queries logged | worked by the H3 ladder, corpus-first |
| H5 gates | `07_governance` gate results | server verdicts with plain labels | — |
| H7 evidence age | normalized dates (see § Enrichment precedence: dating) | aged against the pinned reference date; undated = UNVERIFIED | **P1 dating pass** |
| H8 cohort · H9 value chain | server-side | — | — |

### D4 Platform · D5 Context · D6 Techstack

| Surface | Package sources | Storyline inputs | Enrichment |
|---|---|---|---|
| P1 fit & story | fit engine; gap rows from H4; `recommendations_detail.json`; stack context from T1 | engine's four factors verbatim; greenfield claims walk the deep-search ladder before rendering | P2 peer deployments, demand signals |
| P2 recommendations | `recommendations_detail.json` → `Recommendations` tab | root cause → cost of inaction → KPI triple | P2 feasibility corroboration |
| P2b starters | H1 quotes + P1 stories | say-it-aloud, consultative, client-specific | — |
| P3/P4 roadmap | recommendations sequencing + engine | one order argued twice | — |
| C1 timeline | `A7_time_maps.csv`; `Entity_Timeline` tab; report history | arc from dated, cited events | P2 currency |
| C2/C3 issues & regulatory | issue registers — **three header generations measured** (`03_issues/L*.csv`, `07_governance/*issue*`, `A5_Issue_Register.csv`); regulator identity from O2 | open matters and the ceilings they place; refused registries recorded, never dressed as absence | P1 regulator records (NCUA/SEC/FINRA) |
| C4 context sentiment | projects O9 by `e_id` | three audiences at Context depth | rides O9 (P0 upstream) |
| C5 acquisitions | report history; timeline stores | deal records with integration statements | P2 deal verification |
| T1 register | `A4_Tech_Stack.csv`; Explorium/technographic xlsx (corroboration); evidence stores' tech rows | one row per named product; CONFIRMED needs a source row; ABSENT needs the ladder | **P0 for CONFIRMED status** — package rows alone rarely clear the bar |
| T3 platform detail | rides T1's rows byte-identically; `dma_impact` from H4 gap rows; `peer_coverage`/`peer_deployments` | per-product depth: what this stack item does to the assessed gaps | P2 peer-deployment shape (AG-04: per-peer breakdown or null, never a bare share) |

## Enrichment precedence — measured, not felt

Ranked by what the corpus can and cannot answer (see § Measured corpus):

- **P0 · package-blind facets** — no package store observed corpus-wide:
  sentiment (O9/C4), thought leadership (O12), leadership roster
  verification (O7), technographic CONFIRMED status (T1). These are
  enrichment-FIRST: the connector/web pass is the primary source and runs
  before the surface is written.
- **P1 · schema-fit retrieval** — the package holds the item but not the
  schema: evidence **dating** (whole generations carry `recency_tag` with
  zero dates; the flagship research workbook dates only a fraction of its
  rows), **URLs** (one generation has no URL column at all; another holds
  non-http values), **excerpts** (no evidence CSV in the corpus carries a
  50-char excerpt — they live in research workbooks and reports, which is
  why `evidence_normalize.py` corpus-fills before any web call). Runs
  before recency- and citation-dependent surfaces (H7, H2/H6, O3).
- **P2 · validation passes** — the package answers, the world confirms or
  falsifies: why-now currency, peer facts, financial series, focus-area
  falsifiers, recommendation feasibility. Run per rulebook during surface
  production.
- **P3 · opportunistic signals** — job postings as demand signals, social
  aggregates where a facet wants them. Degrade per facet when absent.

## Measured corpus (survey of 2026-08-20, all 178 client folders)

Numbers from `package_survey.py corpus` + `trends` — re-run any time; the
survey is a plugin command, so the next generation shift is measured, not
felt. 177 of 178 surveyed (one folder errored and is itself a finding).

- **Scoring truth comes in three shapes**: 95 clients carry an xlsx
  scoring workbook (79 in `03_scoring_workbook/`, 9 in `08_appendices/`,
  5 misfiled under `02_research_workbook/`, plus wrapper and
  `03_Assessment/workbook` variants); **54 clients are EXPORT-ONLY** —
  `export_scoring_detail.csv` and siblings are the score authority, no
  workbook ever reached Drive; **28 clients hold no scoring artefacts at
  all** (research-, briefing- or report-only — honestly not synthesis
  inputs, and G2 refuses them by name).
- 28 wrapper packages (everything one level down); 13 clients carry more
  than one scoring workbook (version stacks); 2 carry INTERIM/DRAFT
  copies beside the live one.
- **Evidence schema gaps, quantified** (69,766 rows profiled across every
  evidence/governance table under 2 MB): 27% carry a date, **1.5% carry a
  50-char excerpt** — which is why P1 schema-fit retrieval exists and why
  `evidence_normalize.py` corpus-fills before any web call. `url` is a
  header in 196 tables, absent in whole generations.
- **Where evidence tables actually live**: `07_governance/` dominates
  (262 tables), then `01_evidence/` (119), `08_appendices/` (119),
  `03_scoring_workbook(+/exports)` (125), `02_research_workbook` (24),
  `02_Evidence/` (5) — five naming generations, one resolver
  (`package_map.py`).
- Workbook naming: `DMA_Scoring_Workbook_*` and
  `DMA_Assessment_Workbook_*` are the same artefact, two generations.
- Duplicate client folders needing HUMAN adjudication (the matcher
  refuses to guess): two identically-named "Corporate America Credit
  Union - DMA"; case-twins "MidFirst/Midfirst Bank" and
  "DovenMuehle/Dovenmuehle Mortgage"; "IMA Financial" vs "IMA Financial
  Group" resolving to one identity.
- The flagship package (T. Rowe Price) normalized: 754 evidence records,
  751 schema-complete from the package itself, 3 web gaps — a package
  answers ~99.6% of its own schema when ALL its stores are read.

An update to this file that changes a number re-runs the survey first.

## A missing URL: the recovery ladder

Reported 2026-08-23 by opening a drawer — "no URLs on the T. Rowe
evidence". Measured over the COMPLETE served set: 757 of 894 items carried
none, against 153 of 154 on the Baxter exemplar. Not one of them had been
researched wrong. The package stated 753 of 757 in its own workbook
register and 748 of 752 in `01_evidence/evidence_index.json`.

That is the shape this defect almost always has, so the ladder starts
where the answer usually already is. **Climb it in order and stop at the
first rung that answers — a web search for a URL the package is holding
costs a day and can find a different document that says something
similar.**

1. **The evidence register the run was built from.** `URL_or_Citation` on
   the scoring workbook's `Evidence_Master`, `URL` on the research
   workbook's `Evidence_Detail`. `evidence_normalize.py` already merges
   both; read its output before anything else.
2. **The package's JSON evidence stores.** `01_evidence/evidence_index
   .json` and `01_evidence/ledger.jsonl` carry a `url` per record and are
   the richest store in a canonical package. They are keyed by the
   package-LOCAL id (`E-002`), which the store minted to `E-TROW-002`:
   `local_id_of_stored` runs the mint backwards and is the only key that
   joins them.
3. **The reports.** `04_reports/*.docx` cite their sources inline, and the
   DOCX twin of every PDF indexes fully — `corpus_search.py --eid E-017`
   finds the citation without opening anything by hand.
4. **The rest of the corpus.** `corpus_search.py search --query` over
   `07_governance/`, `08_appendices/` and the manifests. A URL is an opaque
   string that appears literally, so a corpus hit on the id's own line is
   recognition rather than inference.
5. **Only now, the web.** The session's connectors — Exa and Tavily for the
   document, Quartr for a transcript, Drive for a file the package
   references but does not contain. Search for the DOCUMENT the source name
   already names, not for the claim: the row states "T. Rowe Price Group,
   Inc. 2026 Proxy Statement (DEF 14A)", and that is a filing with one
   canonical location, not a topic to go reading around.

**What is never a URL.** `multiple`, `N/A`, `see source`, `TBD`, a local
file path, or a bare hostname standing in for a document. A row the ladder
cannot answer keeps `url: null` and goes out as a gap naming what is
needed. An unopenable link is worse than an honest blank, because the
blank is visible and the link is not.

**Explorium / Vibe-Prospecting is the honest exception, and it is a
warning rather than a refusal.** A technographic scan is a machine
observation with no document behind it, so it is minted with the entity's
own front door — 18 T. Rowe items and 15 Baxter items carry
`https://<entity>.com` and nothing more specific. That is truthful about
ORIGIN and misleading as a CITATION: the reader clicks expecting the claim
and lands on a home page. Say so in the source name ("Vibe Prospecting
enrich-business technographic scan"), never dress it as a document, and
never go looking for a deeper URL that does not exist.

`scripts/gate_m_evidence_url_and_span.py` measures all of this over the
complete set and fails the run rather than sampling it.
