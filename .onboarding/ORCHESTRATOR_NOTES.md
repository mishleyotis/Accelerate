# DMA Insights Orchestrator — onboarding notes

Written 2026-08-30. Branch `claude/dma-insights-onboarding-zknopn`.
Durable state so this survives a context reset or a handoff.

## 1. Architecture map

Four deployables + one connector, GCP project `digital-maturity-assessor`,
region `us-central1`, project number **306195530103**.

| Service | Repo path | Role |
|---|---|---|
| `dmai-web` | `apps/web` | Next.js App Router SSR. Behind Cloud Run **integrated IAP**, `domain:zennify.com`. Verifies the forwarded `x-goog-iap-jwt-assertion` in `apps/web/lib/iap.js` (ES256 vs Google IAP JWKs). |
| `dmai-api` | `apps/api` | FastAPI + SQLAlchemy/asyncpg. 17 routes under `/v1`. Read path only; writes limited to annotations + alert actions behind `Idempotency-Key`. |
| `dmai-mcp` | `apps/mcp` | **The only writer of serving content.** Streamable HTTP MCP, mounted under a secret path token. Validation gates, atomic six-page promote, bundled 384-dim embedding model for V4 grounding at submit. |
| `dmai-worker` | `apps/worker` | Cloud Run Job. Package scan (TRD §07 ten steps) every 30 min: Drive intake -> runs. Also `INTAKE_STATUS` census mode. |
| `dmai-migrate` | `migrations/` | Alembic, expand-migrate-contract. `migrations/prod_apply.py` is the Job entrypoint. |

Verified live URLs (hash form and projnum form both work):
- api `https://dmai-api-dukrne5v4a-uc.a.run.app`
- web `https://dmai-web-dukrne5v4a-uc.a.run.app`
- mcp `https://dmai-mcp-dukrne5v4a-uc.a.run.app` (= `https://dmai-mcp-306195530103.us-central1.run.app`)

NOTE: `/healthz` is not a route on web/mcp. A Google-frontend 404 there does
NOT mean the service is absent. Probe `/` or an app path and read the body.

### Ingestion path (end to end)

```
Drive intake tree (General DMAs, folder 1xIClbzw-SRBJ0Et3SOWnb7YhcBM8b6mo)
  -> dmai-worker package scan (every 30 min, idempotent)   -> run row @ INGESTED
  -> synthesis session (Cowork) runs /dma-surface-production
       claim_run -> get_page_contract -> get_report_bundle -> get_capability_catalogue
       -> Clay enrichment -> register_evidence -> produce 6 pages
       -> submit_page_payload (per page, verdict returned)
       -> promote_run  (ONE transaction, all six pages or none)
  -> serving tables -> dmai-api /v1/entities/{display_id}/{page} -> dmai-web
```

`source_cell` and GCS artefact bytes cannot be backfilled. Ingested tier is
read-only once scanned.

## 2. The four rulebook artifacts

All four live in the **`dma-surface-production` skill**, the production
rulebook. In-repo copy: `plugins/dma-insights/skills/dma-surface-production/`.

| Artifact | Location |
|---|---|
| Gold standard | Baxter Credit Union, `baxter-credit-union-bcu`, promoted in production. Referenced throughout `SKILL.md`, `05-lifecycle/1-gates.md`, `03-pages/*`. |
| Rules tests (gates) | `05-lifecycle/1-gates.md` + `scripts/` (`check_payload.py`, `check_language.py`, `check_consistency.py`, `check_evidence.py`, `check_repetition.py`, `precheck_gates.py`, `vet_workbooks.py`) + the connector's own server-side gates. |
| Enrichment guidelines | `02-inputs/2-clay-enrichment.md` (+ `scripts/clay_plan.py`) |
| Reasoning guidelines | `04-craft/1-reasoning.md` (the R-Layer) (+ `04-craft/7-storyline-challenge.md`) |

**IMPORTANT — the installed plugin is AHEAD of this checkout.** The enabled
`dma-insights` plugin advertises 47 agents, 33 connector tools and 65 gates
incl. CG-44..CG-49; the repo tree here has 5 agents and ~15 tools. Read the
INSTALLED skill for current gate text; treat the repo copy as the older one.

## 3. Gold standard — Baxter Credit Union, as promoted

```
display_id   baxter-credit-union-bcu
run_id       c1351d25-a612-4dbe-b498-127bccaf6810
request_id   DMA-ASM-BCU-20260330-0001   run_seq 1   status PROMOTED
promoted_at  2026-08-19T14:53:37Z        assessment_date 2026-03-30
sub-vertical CU        composite 2.71 (Building)      scored_cells 765
pillars      P1 3.11 Competing | P2 2.54 | P3 2.71 | P4 2.53 (all Building)
open_alerts  11        refresh_due 2026-09-30
ccg_catalog_version  v5.0   <-- 17 categories INCLUDING P1C5 (ESG)
```

**Calibration caveat that matters:** Baxter is pinned to catalogue **v5.0**
(17 categories, 836 cells). A new DMA on **v7.0** has **16 categories, 851
cells, and no P1C5**. Do not copy Baxter's 17-category shape onto a v7.0 run.

Section census as served (internal audience), 32 sections:

| Page | Sections | Notable |
|---|---|---|
| overview | 10 | scores, firmographics, why_now, exec_summary, opportunity, findings(5), leadership(6), financial_series(6), sentiment(EMPTY), thought_leadership(5) |
| heatmap | 9 | workbook_scores, focus_areas(4), **cell_evidence 706 cells**, evidence(EMPTY), value_chain(8, server_derived), alerts(11), safeguard_gates, evidence_age(65), cohort_patterns(EMPTY) |
| insights | 2 | insights(8 cards), landscape(4 tiles) |
| platform | 5 | platform_story(5), recommendations(8), starters(5), roadmap(3 phases), stairstep |
| context | 5 | timeline(11), issue_register(4), regulatory_standing(EMPTY), context_sentiment(3), acquisitions(1) |
| techstack | 1 | techstack(51 items) |

Skill documents 34 sections / 6 pages; served shows 32 (overview 10 vs 12).
OPEN QUESTION - not yet resolved.

Section envelope shape (every section):
`{data, data_source, provenance, produced_at, producer_version, e_ids, empty_state}`
`data_source` observed values: `producer`, `server_derived`, `external`, `empty`.

Evidence discipline observed on Baxter: `cell_evidence` 88 section-level
e_ids over 706 cells; `platform_story` 32; `recommendations` 20;
`techstack` 29; `evidence_age` 59. Empty sections carry an explicit
`empty_state` rather than being absent.

Provenance to workbook cell is retained, e.g. pillar P1
`source_cell: "Pillar_Summary!C2"`.

## 4. Environment (this container)

| Component | State |
|---|---|
| Python 3.11.15 + backend deps | OK (`pip install --ignore-installed PyJWT pytest openpyxl pg8000 -r apps/api/requirements.txt -r migrations/requirements.txt`) |
| Node v22.22.2 / npm 10.9.7, `apps/web` deps | OK |
| Docker | daemon NOT running by default; start with `nohup dockerd --iptables=false --bridge=none &` |
| Postgres 16.15 + Redis (docker compose) | OK. Extensions vector/citext/pg_trgm/pgcrypto present; 108 tables after `alembic upgrade head` |
| gcloud 582.0.0 | Installed to scratchpad. **Must `unset CLOUDSDK_AUTH_ACCESS_TOKEN`** or every call fails ACCESS_TOKEN_TYPE_UNSUPPORTED |
| Identity | `dmai-routine@digital-maturity-assessor.iam.gserviceaccount.com` from `$DMA_ROUTINE_SA_KEY_B64` |

gcloud setup that works:
```bash
export PATH="<scratchpad>/google-cloud-sdk/bin:$PATH"
unset CLOUDSDK_AUTH_ACCESS_TOKEN
echo "$DMA_ROUTINE_SA_KEY_B64" | base64 -d > /tmp/sa.json
gcloud auth activate-service-account --key-file=/tmp/sa.json
gcloud config set project digital-maturity-assessor
```

### What this identity CAN and CANNOT do

CAN: mint ID/access tokens; call `dmai-api` authenticated (all 17 routes);
reach the MCP connector through `scripts/dma_connector.py` (it resolves the
path token from Secret Manager at call time).

CANNOT: `run.services.list/get`, `run.jobs.list`, `secretmanager.secrets.list`,
`projects.describe`, read `gs://digital-maturity-assessor-catalogue-staging/`,
and **cannot pass IAP to load `dmai-web`** (needs a human zennify.com Google
identity in a browser; documented as MEM-0065).

### Test suite state

- `tests/schema/` 34 passed, 13 skipped — GREEN
- `apps/web` `npm run test:web` 75 passed, 7 skipped, 0 failed — GREEN
- python units: **1239 passed, 2 failed, 4 skipped, 7 errors**
  - 7 errors in `apps/api/tests/test_computed_against_the_real_schema.py` and
    1 failure `apps/mcp/tests/test_bundle.py::test_catalogue_pins_the_run_version_with_names`
    -> all caused by the **catalogue not being seeded locally**
    (`ccg_versions` has no v7.0 row; FK `runs_ccg_catalog_version_fkey`).
    Seeding needs `python -m ccg_loader --version v7.0 --dir <xlsx>` with the
    v7.0 workbooks from the catalogue-staging bucket. BLOCKED on bucket read.
  - 1 failure `apps/mcp/tests/test_promote.py::test_a_retained_pass_is_revalidated_and_disclosed`
    -> asserts "disclosure must not block the promote"; got promoted=False.
    Relates to commit `6e008b1`. NOT catalogue-related. Genuine, unresolved.

## 5. Production state (read 2026-08-30)

- Catalogues: v5.0 (836 cells, 17 cats, not current); **v7.0 (851 cells, 16 cats, CURRENT)**
- Promoted runs: **8**; entities serving: **5** — Axos Bank, Logix FCU,
  T. Rowe Price, Gulf Coast Business Credit, Baxter CU
- Pending queue: **283 runs at INGESTED across 168 entities**,
  101 duplicate_requests, 110 surplus_runs, 13 claimed.
  Ingest is not the constraint; synthesis is.
- `scripts/synthesis_queue.py` selects which pending run to hand a producer
  and states a reason for every run it skips. Use it; do not walk the queue naively.

## 6. Open findings / questions for the user

1. **The auditor reports 25 blockers + 4 warnings against promoted Baxter.**
   `scripts/audit_promoted_client.py` against live production. Mixed quality:
   - Likely FALSE POSITIVE: `.scores.data.pillars[].proxy_disclosure` null on
     all 4 rows — all four have `peer_basis:"table"`, so no proxy was used and
     null is a stated absence, not a lost value. The newest commit
     (`de6d025`) was written to teach the auditor exactly this distinction and
     evidently does not yet cover this field.
   - Needs adjudication: `.findings.data.findings[].{name,score,subcap_id,peer_median}`
     null on all 5 rows. Baxter's findings are thematic/cross-pillar
     (e.g. F-1 "Data fragmentation is the root constraint") so they may not
     anchor to a single subcap by design.
   Baxter was promoted 2026-08-19, BEFORE these checks existed. Per SKILL.md:
   "A page that passed under an older gate set is not a page that passes now."
   This audit does NOT gate CI (CI runs it only against `fixtures/served`,
   which does not exist). **Do not change the gold standard without asking.**
2. Cannot log into `dmai-web` from this container (IAP + zennify.com domain).
3. Section count 32 served vs 34 documented (overview 10 vs 12).

## 7. Ingestion contract (short form)

Gold standard = Baxter (`baxter-credit-union-bcu`), v5.0-pinned, composite
2.71, 706 cell syntheses, six pages promoted atomically.

Bands, strict less-than on the RAW score before display rounding:
`<2 Activating | <3 Building | <4 Competing | >=4 Differentiating`; null = no score.
Four bands only. **M5/Transformational must not exist in code, enum or prose.**

Never: assign a score; invent an identifier (only `ic_id, f_id, fa_id, ts_id,
wn_id` + authored `rec_id`); cite before registering; average two disagreeing
figures; send a colour; say no before running the absence ladder.
Always: computed-or-null (never NaN/sentinel); mark `internal_only` paths;
counts = length of the citation array; frame every gap as available value and
never open a prose field on an absence; one story per page (`narrative_thread`
45-75 words); argue against your own conclusion (R-Layer) before shipping.

`foreign` from `get_evidence` = contamination -> stop, quarantine, escalate.

## 8. Rulebook summaries (internalized)

### 8.1 Gates — the pass/fail gates (`05-lifecycle/1-gates.md`)

Four families, four failure behaviours. The prefix is part of the id.

| Prefix | Family | Runs | On failure |
|---|---|---|---|
| `AG-nn` | Analytical | in synthesis, per claim | claim changes or is dropped |
| `SG-nn` | Safeguard | at submit; **renders to the client** | disclosed, **does not block promotion** |
| `ET-nn` | Enrichment trigger | during synthesis | not a failure — go enrich |
| `CG-nn` | Corpus | build time, over the pack | fails the build |

Plus two structural passes at submit: **contract pass** (required fields, types,
word budgets, registers, id patterns) and **evidence pass** (ids resolve, belong
to this entity+run, excerpts verbatim, domains identity-checked).
**Any evidence reason at all fails the submission.**

Gates that block most often:
- **AG-03** every claim-bearing ITEM cites evidence (not the section envelope).
  An inference cites the source it was drawn from. Does not fire on: a null row,
  a recorded absence carrying its ladder, or a section envelope.
- **CG-15** the only gate that reads prose for content. Refuses: placeholders
  (`N/A`, `TBD`, `-`, ...); prose under `ceil(floor x 0.5)` words; a section
  where every present content field is vacuous; **template prose** (8-word
  shingle overlap >= 0.40 AND content-word overlap >= 0.40, connected group of
  3+); prose that only restates a score or inventories evidence (residual <= 2
  content words). Exemptions: a section with a valid `empty_state` (reason AND
  `sources_searched`); an item recording an absence on the ladder **with the
  search that established it, on the keys that item's own contract declares**.
  `thin: true` is NOT an exemption. `narrative_thread` repeated across a page is fine.
- **CG-09** closed vocabularies, case-sensitive.
  `timeline.events[].signal` = `POSITIVE|NEUTRAL|NEGATIVE`;
  `techstack.items[].status` = `CONFIRMED|INFERRED|CLAIMED|ABSENT`. Null passes.
- **AG-04** a named peer's technographics must carry their source. Blocks.
- **CG-10** dating; **CG-14** cell linkage; **ET-05** sub-vertical scope;
  **ET-01/ET-04** citations; **CG-16/CG-17** chunked-transport integrity.

Local checkers, run BEFORE spending a round trip (a FAIL supersedes a passing
staged row and blocks the whole promote):
```
scripts/vet_workbooks.py <package-dir>            # step 0, refuse a dirty workbook
scripts/check_repetition.py drafts.json --page P --at-scale N   # at draft 20, NOT at submit
scripts/check_payload.py payload.json --page P --subvertical CODE --cells bundle.json
scripts/check_language.py payload.json
scripts/check_evidence.py get_evidence.json --review
scripts/precheck_gates.py payload.json --page P --evidence E.json --bundle B.json
scripts/check_consistency.py <rundir>/ --subvertical CODE      # before promote
```
Without `--subvertical` and `--cells`, ET-05 and CG-14 print "not run" — which
is NOT a pass.

**CG-15 thresholds are calibrated on Baxter.** Baxter's 706 honest cell
syntheses peak at 0.179 8-gram overlap against a 0.40 refusal line (2.2x margin);
its lowest words-to-floor ratio is 0.64; its lowest residual is 4 content words.
Fisher (708) and Frost (677) were refused at 1.000. So a 700-cell page is
demonstrably writable: if mine is refused, the SHAPE is wrong, not the scale.
Rule in one line: **name what you looked for, not that you looked.**

### 8.2 Enrichment (`02-inputs/2-clay-enrichment.md`)

Runs during synthesis, started EARLY (async, and the pages that consume it come
last). Output becomes registered evidence like any other source.

Budget per run — standing authorisation, ask outside it:
1 company enrichment call (Tech Stack, Annual Revenue, Headcount Growth, Recent
News, Open Jobs, Latest Funding) + 1 leadership contact search (C-suite/tech
titles) + 1 contact enrichment (Find Thought Leadership, Summarize Work History)
+ 0-2 targeted Custom points against a named gap already tried by search.

Tier follows the underlying source, not the tool:
`Tech Stack` = **T1** (machine technographic scan; filing it T4 caps at L2.5 and
silently suppresses the score — commonest misclassification in the corpus);
`Annual Revenue`/`Latest Funding` T1-T2 only when a filing is behind it, else
modelled = inference; `Open Jobs` T2-T3; `Find Thought Leadership` T2-T3;
`Recent News` T3; `Summarize Work History` T3; Custom = tier of what it returns.

Three rules above the call sequence:
- **Cite the source, not the tool.** "Clay reports 340 employees" is not
  evidence; the filing Clay surfaced is.
- **Never record an absence from Clay without polling `get-task-context` first.**
  The search response carries base fields only.
- **Resolve on the right domain.** From `01_evidence/entity_profile/`, never a
  guess. A brand-domain technographic scan is evidence about that brand's estate,
  not the enterprise's.

Clay closes: O7 leadership, O12 thought leadership, T1 tech stack, O2
firmographics, O3 why-now, C5 acquisitions, P1 platform readiness (Open Jobs is
the cheapest capability signal).

### 8.3 Reasoning (`04-craft/1-reasoning.md`)

The R-Layer — the only mechanism that catches a claim that is well-formed,
cited, grain-locked and **wrong**. Runs BEFORE writing; gates run after.

```
A HYPOTHESIS       state the claim and its confidence first
B COUNTER-EVIDENCE argue the strongest case against it
C DOMAIN TEST      plausible for THIS sub-vertical/size tier/regulator —
                   and about this ENTITY, not its cohort?
D FAILURE PROBES   run the surface's probe set; each probe fires a search
E VERDICT          ACCEPT | REJECT | UNCERTAIN (reject = re-rank or drop, never soften)
```
Record `r_layer: {hypothesis, counter, domain_test, probes_run[], verdict, confidence}`
on any surface making a ranked or causal claim.

**Step B is the one that gets skipped.** Source the falsifier from the client's
own words where possible.
**Step C second half:** "Would this sentence be true of any institution in this
sub-vertical?" If yes it is a fact about the sub-vertical or a shared vendor, not
a finding about this client. Attach entity-specific evidence or move it — softening
is not an option.

Four probes fire on EVERY surface: foreign variant cell; cohort scale (peer
median outside the entity's size class); shape-blind ladder; cohort sentence.

Cross-check every fact appearing twice. Independent origins = corroboration
(raises rank score). Disagreement where one outranks = resolve by priority and
record. Disagreement between peers = contradiction: quarantine and state it.
**Never average two disagreeing figures.**

After the six pages pass: **storyline challenge, five volleys** (client executive,
finance officer, incumbent vendor, rival on the shortlist, the AE) recorded as
`storyline_challenge`. Five `held` outcomes is a finding, not a triumph.
Then **8b: the fifteen answered questions**, 40-110 words each, spoken register,
cited from registered evidence.

## 9. Confirmed session facts

- Baxter `sub_vertical` code is **SV2** (= CU). Use the code, not the label,
  for `--subvertical`.
- Baxter carries **3 runs** on one request id: run_seq 1 PROMOTED,
  run_seq 2 SUPERSEDED, run_seq 3 INGESTED (a re-upload duplicate). This is the
  duplicate-run class `scripts/synthesis_queue.py` exists to filter.
- The MCP connector is NOT wired as a session MCP server here (no
  `submit_page_payload` etc. in the tool list). Reach it through
  `python3 scripts/dma_connector.py <tool> '<json>'`, which resolves the path
  token from Secret Manager per call. VERIFIED WORKING for
  `list_pending_runs` and `get_client_state`.
- Clay MCP tools ARE available in-session (`mcp__Clay__*`).
