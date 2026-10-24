# Deliverable 11 — ABSENT–UNNOTICED register

**29 rows of 158 checks (18.4%).**

**What the label means, and why this register is separate from the findings list.**
ABSENT–UNNOTICED is not "missing". It is *missing, and no artefact in the repository records
that it is missing* — no TODO, no open decision, no test marked xfail, no schema column awaiting
a writer, no line in the memory. A PRESENT–DEFECTIVE item has a maintainer and a repair. An
item on this register has neither, because nothing has told anyone it exists. **This is the
register to work first**, not because these are the worst defects, but because they are the only
ones that cannot enter a backlog by themselves.

Every row carries the check id, so each is re-runnable against `ledger.jsonl`.

---

## A · Headless dispatch (1)

| Id | What is absent | Measurement |
|---|---|---|
| `1.2-03` | **Nothing parses `search_requests`.** A headless child that needs a web search has no way to ask for one, and no orchestrator answers. | `grep -rn 'search_requests'` across `apps/{api,mcp,worker,web}`, `packages`, `migrations`, `plugins`, `scripts`, `infra` = **11 hits, all prose or docstrings** — `agent_run.py:20,51` on the emit side, `routing.md:52`, `corpus_search.py:12,81,258`, `evidence_normalize`. Zero parsers, zero consumers. |

---

## B · Stage 1 — Request ingestion (2)

| Id | What is absent | Measurement |
|---|---|---|
| `S1-01` | **There is no front door.** The Routine mechanism is a scheduler, not an intake. Four of four pieces a request path needs are missing: a request payload shape, a requester identity, an authorisation rule, and a rate limit. | `cat plugins/dma-insights/routines.json` = **4 GCP Cloud Scheduler jobs** (`dmai-package-scan */30`, `corpus-gate-scanner 0 3 * * *`, `pack-exporter 0 2 * * *`, `enrich-loop 7 * * * *`) and **0 Claude Routines**. A query for any request/question/ticket table in the live schema returns nothing. |
| `S1-05` | **`data_source` is a lie told to the UI.** Every run reports `DRIVE_PARSE` regardless of origin, so the moment a second intake path exists the front end cannot distinguish them — and it already branches on the value. | `apps/api/dma_api/main.py:259` hardcodes `"data_source": "DRIVE_PARSE"` on **every** run in the entity projection — a string literal, not a column read. `apps/web/proto/pages-d1-overview.jsx:292` branches on it. |

---

## C · Stage 2 — Triage (1)

| Id | What is absent | Measurement |
|---|---|---|
| `S2-04` | **Nothing can ask a clarifying question.** `PENDING_REVIEW` (confidence 0.60 document-header / 0.40 folder-name) is where the system parks an unresolved entity — and it is a terminal park, because no mechanism exists to put the question to anyone. | `grep -rni 'clarif\|ask the requestor\|question back\|open_question'` across 8 trees = **1 hit in 8 trees**, and it is a payload **card label**, not an asking mechanism. |

---

## D · Stage 3 — PUBLIC / HYBRID / INTERNAL classification (3)

| Id | What is absent | Measurement |
|---|---|---|
| `S3-01` | **Neither authority defines the column.** Authority 1 (Backend Schema) and authority 2 (TRD) are both silent, so this is not code lagging a schema — the schema never had it. | Backend Schema `grep -ci evidence_mode` = **0**. TRD = **0**. The only adjacent construct is `posture_basis basis_t EVIDENCE / HYBRID / INFERRED` at schema line 521 — a payload field for a different purpose. |
| `S3-03` | **Nobody decides, because the field does not exist in the product.** In the practice a human decides at Phase A0 behind an approval gate; in the product there is no decider and nothing to decide with. | `grep -rn 'evidence_mode\|EVIDENCE_MODE'` across `apps/{api,mcp,worker}`, `packages`, `migrations`, `scripts`, `infra` = **0 of 60** repo-wide hits. All 60 are `apps/web/proto` + its render tests + skill prose. |
| `S3-05` | **Redaction is payload-only, and the unattended architecture writes files.** Serve-time redaction is genuinely default-deny and genuinely sound — but it protects JSON, and the target architecture has the agent writing internal-audience artefacts to Drive on every run, outside the walker's reach entirely. | `grep -rniE '\.docx\|\.xlsx\|\.csv\|content-disposition\|attachment;\|text/csv\|spreadsheetml'` over `apps/api/dma_api`, `apps/web/app`, `apps/web/lib` = **0 hits** — the serving path emits JSON only, so there is literally no file for the redaction walker to have been written against. |

---

## E · Stage 4 — Internal documents (1)

| Id | What is absent | Measurement |
|---|---|---|
| `S4-01` | **There is no internal-document ingest, and the classifier that could have been one is orphaned.** | `apps/worker/job_main.py::_classify_artefact` (lines 58-99) accepts exactly **four shapes** — `*manifest*.json`, `.xlsx/.xlsm` (research \| workbook), `.docx` (report) — and returns `None` for everything else. The `.json/.csv/.jsonl` evidence stores that real client folders ship are unreadable to it. |

---

## F · Stage 5 — Research and MECE (2)

| Id | What is absent | Measurement |
|---|---|---|
| `S5-04` | **Nothing enforces Rule 16, and the generic render emits unsubstituted placeholders.** A headless agent firing `q.primary` verbatim searches for the literal string `{entity}`. | `kg_reader.py briefs … --lean` with no `--sv`, `--entity` or `--context` → **EXIT=0, no warning**, and the card carries literal `{entity}` in **all 5 DQs and all 5 queries**. `orient.py:89` — the mandated session opener — invokes `next` with no `--entity` and no `--context`, producing a card with **15 literal `{entity}` tokens**. No script creates `context.json`. |
| `S5-10` | **`facet_coverage` has three writers and zero readers.** This is the main defence against a synthesis that claims a volley it never fired, and it is not implemented. | `grep -rn facet_coverage scripts/` = **3 hits, all writers** (`orient.py:59`, `build_handoff.py:59`, `populate_workbook.py:102`). Zero readers, zero comparison against the ledger. Constructed proof: `facet_coverage.contradicts: 'not_checked'` — an **explicit admission the facet was never checked** — gives **gate PASS**. |

---

## G · Stage 6 — Reasoning traps (3)

| Id | What is absent | Measurement |
|---|---|---|
| `S6-02` | **Presence ≠ Utilization is called an ABSOLUTE RULE and a gate, and nothing detects it.** Nothing even asks for the flag in a machine-readable field. | `grep -rni 'utilization\|utilisation' scripts/ --include=*.py` = **4 hits, none in `scripts/engine`**. `grep -rn 'URF' scripts/` = **1**. `grep -rn 'SG-0' scripts/ --include=*.py` = **0**. End-to-end: a subcap whose entire evidence base is **4 proxy hits**, closed as `claim_label FACT`, → **gate PASS exit 0**, handoff `ceiling_band M4, uncertainty ±0.2, confidence HIGH`, schema VALID. |
| `S6-03` | **Three traps live only in YAML prompt cards** — single-source dependency (R6/SG-01..06), tier inflation, evidence smearing (R22). Every one of the 7 subcap and 5 category dimensions is a prompt, not a computation. | `grep -rn 'SG-0' scripts/` = **0**. Tier inflation is unmeasurable as built: `kb_source_id` is consumed **once in the whole codebase**, to write a spreadsheet cell. On the reference ledger the **1 of 1** checkable item declares **T2** against catalogue **T1**. |
| `S6-16` | **No gate in the 69 checks an external relation.** The wrong-but-perfect conclusion passes all of them; the register that would catch it is unshipped. | See `s6.3-wrong-but-perfect.md`, 8 legs, each measured. `register.py:95-113` docstring says *"Distinct ORIGINS"*; the SQL counts `count(DISTINCT e.source_domain)`. `grep -c 'URF-'` over the **installed** skill = **0**. |

---

## H · Stage 8 — Publication (2)

| Id | What is absent | Measurement |
|---|---|---|
| `S8-01` | **The connector cannot emit a file, and whether it should is an unadjudicated owner decision.** *Half of this row is ABSENT–BY–DESIGN* — invariant 2 is deliberate. What is unnoticed is that no artefact anywhere states whether file publication is permitted, forbidden, or pending. | `grep -cE '^\s*@(mcp\|server\|app)\.tool' apps/mcp/server.py` = **33 tools, every one JSON**. A grep for `bytes\|base64\|.xlsx\|.docx\|.csv\|upload\|gs://\|signed_url\|blob\|content_type` over the same file returns 11 hits and **not one is an emission path**. |
| `S8-02` | **The governance issue register is structured and unservable.** A complete schema, a writer, and no serving path. | `plugins/dma-insights/skills/dma-governance/schemas/issue_register.schema.json` — **7,160 bytes**, `issue_id` pattern `^ISS-[0-9]{3}$`, **16 fields, 11 required**. Nothing serves it, and all three of its writers read the wrong sheet name (see the governance-register finding). |

---

## I · Stage 9 — Lifecycle (1)

| Id | What is absent | Measurement |
|---|---|---|
| `S9-05` | **No run can ever be finished.** `run_status_t` has no terminal-final value, so nothing can distinguish "still working" from "done, permanently". | `select unnest(enum_range(null::run_status_t))` returns exactly **7 values**: `INGESTED, CLAIMED, SYNTHESISING, STAGED, PROMOTED, SUPERSEDED, WITHDRAWN`. **None is terminal-final.** Only 3 writers exist across the live tree. The nearest thing to a lifecycle answer is a 6-month refresh cadence, which answers *when to redo it*, not *when it is done*. |

---

## J · Owner check 4.2 — Resumability (2)

| Id | What is absent | Measurement |
|---|---|---|
| `4.2-04` | **The two state substrates are never compared, and the JSONL side never reaches `orient` at all.** | Drove a real run to a mid-category interrupt: bound engagement set (CU/T1_CORE, 686 of 851; P1C1 = 47 subcaps), minted evidence ids, appended evidence + search + synthesis — and nothing reconciles the ledger against the workbook's CHAIN INTEGRITY block in either direction. |
| `4.2-06` | **Nothing reports a stuck research run.** The synthesis stage has a real scheduled stall detector; the research stage — where this machinery belongs — has none. | `Blocked` occurs **0 times** in the 189,980-character pinned workbook. The only stuck-state token is **7 unresolved `{{OK \| INVESTIGATE}}` cells**, whose readers number **0**. |

---

## K · Owner check 4.3 — Budget (1)

| Id | What is absent | Measurement |
|---|---|---|
| `4.3-05` | **Nothing connects the research budget to the report budget, and neither end is measured.** | Research side: no mechanical stop — the only tool R27 names for the budget check crashes with `NameError` at `ledger.py:125`. Report side: the two pinned Docs declare **blocking minimums summing to 3,050+ words** via `{{PROFILE_WORD_MIN}}` / `{{REPORT_WORD_MIN}}` template tokens that nothing resolves and no code counts. |

---

## L · Owner check 4.4 — Offering linkage (5)

| Id | What is absent | Measurement |
|---|---|---|
| `4.4-02` | **The `UNRESOLVED` render-failure rule has no implementing code.** The rule *"if any field resolves to UNRESOLVED, the render fails and the profile is not handed off"* cannot fire, because no field is ever resolved. | `grep -rn 'UNRESOLVED'` over the archive `--include=*.py --include=*.md` = **0**. `grep -n 'CATALOGUE\|catalogue_hash\|kg_checksum'` over `scripts/deliver/*.py` = **0**. |
| `4.4-06` | **`{{SOLUTION_COUNT}}` and `{{SOLUTION_CATALOGUE_VERSION}}` are counted from a sheet that is not in the workbook.** | Occurrence of `Solution_Catalogue` in the pinned contract-v3 workbook export (189,980 chars) = **0**. |
| `4.4-14` | **`Cap_Triggers` does not exist, so §3.2's six columns have no source.** The instruction *"write UNDETERMINED rather than a guess"* would apply to every row, which makes the subsection unwritable rather than honest. | Occurrence counts in the pinned Sheet's full export: `Cap_Triggers` **0**, `Solution_Catalogue` **0**, `Handoff_Lock` **0**, `Platform_Peer_Adoption` **0**, `Focus_Areas` **0**, `Firmographics` **0**. |
| `4.4-15` | **Neither the per-issue withheld points nor their aggregate exists**, though §3.3's own note says the two "must agree" and that the aggregate "is the figure an executive asks for first." | `grep -rni 'uncapped\|points_withheld\|withheld'` over the live tree, the archive **and** the legacy snapshot = **0 relevant hits**; every `withheld` match is the redaction vocabulary. |
| `4.4-17` | **The referential offering store exists twice and is reachable neither time.** | (1) `migrations/versions/0004_catalogue_tier.py` defines `ccg_offerings` (17 columns) and `ccg_offering_subcap_map`. (2) `kg/catalog/offering_map.json` in the archive. `grep -rn 'offering_map\|offering_id'` across `apps/*`, `packages`, `scripts`, `plugins` = **0 outside the migrations that create the tables**. |

---

## M · Owner checks 4.5 – 4.7 (3)

| Id | What is absent | Measurement |
|---|---|---|
| `4.5-04` | **The peer-set lock is asserted by both pinned templates as a working mechanism and exists nowhere.** Client Profile v8 §4.1: *"once this section is approved, the peer set is immutable for the remainder of the assessment."* | `grep -rn 'Handoff_Lock\|handoff_lock'` across `apps/{api,mcp,worker,web}`, `packages`, `migrations`, `scripts`, `infra`, `plugins` **and** the legacy `apps/dma-insights` snapshot = **0**. |
| `4.6-08` | **§6.4's counter-evidence pass is in neither the engine nor any skill** — while the adjacent §6.2 discipline, from the same section of the same template, *did* become code. | The pinned Client Profile §6.4 exists verbatim with named columns (*"Paused, completed or replaced?"*, *"Plausible for this sub-vertical and size?"*, *"Client framing or vendor framing?"*). Nothing implements any of them. |
| `4.7-05` | **`Platform_Peer_Adoption` has no source on either side.** The write side names a sheet that does not exist; the read side names nothing at all and is a live-research instruction — which stage 1 established there is no connector to serve. | `grep -rn 'Platform_Peer_Adoption'` over the whole repo **and** the whole archive = **0 hits in both trees**. Client Profile v8 §5.2 states the scan *"is written to Platform_Peer_Adoption in the scoring workbook."* |

---

## N · Cross-cutting 5.1 — Autonomy readiness (2)

| Id | What is absent | Measurement |
|---|---|---|
| `5.1-02` | **Fourteen silent failures, ranked above the loud ones.** In attended operation a silent failure is caught by someone eventually; unattended, it is permanent. | Full register with a re-runnable command each in `s5.1-autonomy-registers.md` (register B). Examples: `ledger.py stats` → `NameError` at `scripts/engine/ledger.py:125`; omitted readiness → coerced green; `validate_kg` warnings that never change an exit code. |
| `5.1-03` | **There is no clock on an autonomous assessment**, and the repo has the precedent to know it needs one. Nothing bounds a run; at no bound does it stop, degrade or hang, because no bound exists. | 851 subcaps × 6–10 queries plus dispatch round trips, with no termination condition. `gate_l_ci_jobs_are_bounded.py` exists **precisely because** two CI jobs once hung 33 minutes against GitHub's six-hour default — the lesson was learned for CI and never applied to assessments. |

---

## Reading the register

**The repeated shape.** Fifteen of the 29 rows are the *same defect*: a named mechanism —
`kg_checksum`, `Handoff_Lock`, `Cap_Triggers`, `Platform_Peer_Adoption`, `Solution_Catalogue`,
`UNRESOLVED`, `search_requests`, `facet_coverage`, `URF-01..06`, `SG-01..06`, `points_withheld`,
`offering_map`, `context.json`, `checkpoints/`, `DQ_Bank` — is **asserted by a template, a
protocol or a docstring as though it worked**, and has no implementation on either side of the
join. Every one of them reads as functioning to anyone who reads the documents rather than the
code, which is exactly what an unattended agent does.

**Where they cluster.** The front of the pipeline (stages 1–4: **7 rows**) is absent because it
was never built. The document layer (owner checks 4.4–4.7: **9 rows**) is absent because the
templates were written against a workbook contract that later changed and nothing reconciled
them. Those are two different problems needing two different repairs, and only the second is
cheap.

**The one row that is half by design.** `S8-01` is the only place in 158 checks where an absence
turned out to be deliberate — and even there, the deliberation is inferred from invariant 2
rather than stated. **ABSENT–BY–DESIGN was awarded zero times outright.** Nothing in this
repository says "we left this out on purpose, and here is why."
