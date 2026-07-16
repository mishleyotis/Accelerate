# NLP / derive script intelligence upgrades

Captured from the Stage-2 Claude refinement pass (per-client subagents reading
the whole report package). Each note names the script, what it produced that was
weak/wrong, and the concrete upgrade so the deterministic layer reaches the
refinement quality WITHOUT the overlay. Fold these in incrementally; re-run the
94-client regen + pack_quality_gate after each.

## PRIORITY — root causes (systemic, affect many clients)

### section_analysis.py — unresolved DOCX E-IDs → "evidence drawer empty everywhere"
- **Symptom (user-reported, all pages):** clicking any evidence chip opens an
  empty drawer.
- **Cause:** `insights.narrative.per_pillar` (and likely other narrative
  builders) carry E-IDs from the **DOCX's own citation scheme** (e.g. E-202,
  E-312, E-300, E-327, E-329) which are **absent from the package evidence
  index** (E-001..E-140). The chips reference IDs that don't exist in
  `evidence_index`, so EvidenceDrawer resolves nothing.
- **Fix:** reconcile every DOCX-cited E-ID against the run's evidence index —
  map by URL/claim/excerpt to the canonical E-ID, or DROP the citation if it
  can't be mapped. Never emit a chip whose E-ID isn't in `evidence_index`.
- **Also:** heading→section sentence boundaries emit truncated sentences
  ("However, and at/below median.") — tighten the boundary so partial
  sentences aren't shipped.

### deepen_narrative.py + derive_insights.py — evidence misattribution
- **Symptom:** insight/finding WHAT quotes evidence about a *different* topic
  (e.g. "Onboarding trails peers by 1.1" whose what_text is a Fitch-BBB rating
  sentence; a "strategic posture" finding whose WHY quotes patronage $).
- **Cause:** evidence is selected by co-citation / link-graph proximity and
  spliced verbatim with **no topical-relevance check**; the same subcap_id gets
  multiple different labels across overview/insights/narrative because naming
  isn't resolved through one canonical source.
- **Fix:** (i) gate evidence selection on **topical alignment** (keyword or
  embedding match to the capability name + `research_handoff` pillar
  key_gaps), not graph proximity; (ii) lead what_text with the capability
  message + score/gap from the **authoritative scoring table**
  (`ASSESSMENT_SUMMARY.md` Phase-5 / `recommendation_summary.json`); (iii)
  resolve ONE canonical label per subcap_id via `CatalogueResolver` shared
  across overview + insights + narrative; (iv) source so_what from the matching
  REC (`impact` / `cross_pillar_unlocks`), not the generic "sequencing it first
  lifts …" template.

### derive_financials.py — treats PARTIAL 5-yr trend as a hard blocker
- **Symptom:** `financial_trajectory: null` / "trend data gap" even when the
  package has real figures (Capital Farm: loans $12.99B→$13.17B, patronage,
  ratings all present and ignored; Greenstone had a full 3-yr series available).
- **Cause:** treats `financial_baseline.json five_year_trend: PARTIAL` as a
  stop, surfacing only `size_tier`.
- **Fix:** when no ≥2-year assets/NI series exists, mine `financial_baseline.
  metrics{}` + evidence findings for discrete latest-year values AND any 2-point
  series (loans, credit-quality, patronage) and populate the
  `highlights[]`/`events[]`/`ratings{}` shape `FinancialTrajectoryCard` already
  renders (the "real depth, no chart" branch). Confirm each number against a
  source; compute CAGR only with ≥2 same-metric years.

### derive_sentiment.py — per-source regexes pointed at DOCX prose, not evidence
- **Symptom:** collapses to one row "Public Sources / neutral / null" though the
  package has Glassdoor/Yelp/Google-Play/BBB ratings (in the evidence corpus).
- **Cause:** per-source regexes (Glassdoor/Yelp/Google Play/BBB) run over DOCX
  prose + the aggregate `A6_Sentiment_Analysis.csv` single row, missing the
  actual ratings that live in `evidence_index`/`A1_Evidence_Inventory`.
- **Fix:** run the same per-source regexes over the evidence corpus findings and
  emit per-source scored + qualitative rows BEFORE the aggregate-CSV fallback.
  Correct mislabeled scores (e.g. an App-Store rating tagged as a BBB "/5").

### focus_area_synthesizer.py — scaffolding titles + fake "verbatim" quotes
- **Symptom:** title "Sharpen strategic posture" (scaffolding), and
  `verbatim_quote` is a *synthesized recommendation*, not a real quote.
- **Fix:** name the concrete opportunity tied to `involved_subcap_ids`; require
  `verbatim_quote` to be an actual sourced span (with `source_path` + page) from
  the client-profile/evidence; drop "No X"/scaffolding titles (WAVE-1 S9 covers
  the reframe, this covers the quote provenance + validity).

## Per-client overlay status
- greenstone-farm-credit-s-3001 — done (financials 3yr, firmographics, sentiment)
- capital-farm-credit-0001 — done (financials 2pt+highlights, sentiment 3-source,
  leadership +CDO, 3 findings, 4 cards, focus retitled)
- (wave 1 in flight: farm-credit-mid-america, alliant-insurance, regions-bank)

## More systemic parser bugs (from Regions Bank overlay)

### client_profile.py `_extract_acquisitions()` — column-synonym miss (+ dedup)
- Regions §4.4 labels the acquired party column **"Entity"**, absent from the
  synonym list `(target,event,acqui,transaction,deal,company)` → the whole table
  is dropped → `acquisitions: 0` despite 2 real deals (EnerBank 2021, Sabal 2022).
- **Wintrust-style dedup note:** for Regions there were NO duplicates — the list
  was empty (extraction miss). But the in-loop dedup keys on
  `(dt, title[:60].lower())`; if the same deal appears with differing date grains
  it slips through as an un-deduped duplicate. **Fix:** (i) add
  `entity,name,firm,institution,business,subsidiary` to `i_target` synonyms;
  (ii) key dedup on `(normalized_target_name, year)`, not exact datetime — this
  prevents the Wintrust duplicate-acquisitions bug at the source.

### firmographics_facts.py / nlp/quantities.py — number/period parsing
- `branches` "253" — a comma-grouped "1,253" truncated at the thousands
  separator. Integer regex must treat `\d{1,3}(,\d{3})+` as ONE token.
- `revenue_usd` $1.9B — a **quarterly** (Q2) figure mislabeled annual. The
  revenue picker needs period-awareness (reject Q#/quarterly when an annual
  field is wanted).
- `aum_usd` $200B — the upper edge of the size-tier band "$100B-$200B" used as a
  point estimate. Never treat a tier-band edge as a precise figure; prefer the
  balance-sheet actual.

### overview_cards.financial_trajectory_card — CAGR + events
- Recomputed an asset CAGR and ignored the report's stated "+16.2% net-income
  CAGR"; events were unrelated leadership/product items. **Fix:** prefer the
  report's stated CAGR (label the metric); source `events[]` from the
  Scale-Metrics "Key Driver" column keyed to the same fy as the series.

### intelligence_builder insight-card assembly — slot misalignment
- CP-F-* cards had what/why/so_what stitched from unordered evidence facts by a
  misaligned index (nCino card carried "BYOLLM" prose; CIAM carried "Secure Code
  Development"). **Fix:** populate WHAT/WHY/SO-WHAT from the Client Profile §4.1
  IC-00x cards, which already carry correctly-aligned verbatim prose per finding.

### focus_area_synthesizer title split — "| Rosie"
- Splitting a verbatim cell "F-003 | ROSIE-Salesforce NBA | ROSIE = 22 ML models"
  on `|` and picking a fragment yielded the broken title "| Rosie". **Fix:**
  strip the leading `F-0NN` token, take the first non-empty pipe segment as the
  title (third as body).

## LOB-awareness + chartable metrics (from Alliant Insurance overlay)

### derive_financials.py — bank-centric; no LOB/subvertical branch
- For an insurance BROKER (subvertical SV7) the module has no metric to bind:
  its `_RATIOS`/`_CASH` vocab is ROA/ROE/NIM/Tier-1 + Net-Income/Total-Assets/
  Deposits, and `_YEAR_ROW` expects a two-$-column bank table. It coerced
  revenue into `total_assets` and the unit-guard mis-rescaled to ~0 "K".
- **Fix:** branch on subvertical (`00_parameters.json`): brokers → revenue /
  premium_placed / organic_growth_pct / EBITDA, parsed from the package's own
  `08_appendices/A3_financial_trends.csv` (a structured, E-ID-cited trends table
  currently ignored) + `entity_profile.financials.revenue_trajectory`; pick the
  series key by LOB (revenue for brokers, not total_assets).

### FinancialTrajectoryCard.tsx / overview_cards — only charts assets/net_income
- `_SERIES_KEYS` maps revenue/premium but the card only charts
  total_assets/net_income_m, so a revenue series silently falls to the empty
  variant. **Fix:** add revenue/premium/aum as chartable bar keys with correct
  axis labels, OR pick the first non-null series key generically.

### derive_insights INS-REC — stringified Python dict leaks as what_text
- INS-REC cards shipped `what_text = "{'solution': 'MuleSoft Anypoint…', 'fit':…}"`
  (a `str(dict)`). **Fix:** render the solution dict to prose (solution + fit),
  never `str(dict)`; and never truncate on a hard char cap mid-sentence.

### SCQA — prefer the package's clean scqa.json
- `overview.narrative.scqa_md` is a garbled re-synthesis though the package has a
  clean analyst SCQA in `04_reports/scqa.json` + `report_synthesis.md`. **Fix:**
  use `scqa.json` verbatim when present; synthesize only when absent.

### Loader limitation — multiple findings share one subcap_id
- Draft emits 2 findings under P4C1, 2 under P1C3; the overlay's by-subcap merge
  patches both identically. **Fix at source:** give each finding a stable UNIQUE
  id so keyed merges (and the insight-card 1:1 mapping) target exactly one card.

## Fabrication + validity root causes (from Farm Credit Mid America overlay)

### derive_leadership.py — mints gap rows for FILLED seats (fabricated gaps)
- Appended CISO + CDO "gap" rows even though the Client Profile marks CISO
  (Tiffany Smith) and CDO (Daniel Brittain) FILLED and lists "Hire a CISO"/
  "Appoint a CDO" as R12-FORBIDDEN. Source of fabricated/accusatory leadership
  gaps. **Fix:** the CRITICAL_SEAT matcher must resolve functional/synonym
  titles (Chief Security Officer→CISO; "Head of Product Strategy, Data &
  Architecture"→CDO) and honor the profile's FILLED/CONSOLIDATED markers +
  R12 forbidden-phrase list before declaring any gap.

### focus_area_sanity.py — does not drop subvertical-NA items → "AI Claims Estimation"
- The invalid "AI Claims Estimation" focus on a Farm-Credit entity (user's
  "how is this a focus area?") is an **insurance-carrier-scope NA** subcap that
  was never dropped. **Fix:** cross-check the A5 subvertical-NA log / "Corrections
  Made During Research" and drop NA items; a focus/priority must map to an
  in-scope, evidenced capability for THIS subvertical.

### derive_financials.py — year-slotting (current banner leaks into an old FY)
- FCMA: the current $48.9B banner leaked into the FY2020 slot; the FY2025 record
  net income $600.4M was mis-slotted as FY2024. `_year_series_full` magnitude-
  based column disambiguation mis-assigns years and trusts the research-workbook
  table over the annual-report chained series. **Fix:** prefer an AR-stated
  chained series ("$44.1B … up from $39.5B 2023, $35.1B 2022…") over the
  workbook; bind each value to its labeled FY (never let a "current" banner
  occupy an earlier year); detect record-year labels; emit a reconciliation
  warning when workbook vs AR diverge >~10%; prefer the AR-stated CAGR.

### derive_sentiment.py — peer-attribution (a peer's NPS shown as the client's)
- "NPS 60" was grabbed from a PEER-benchmark sentence (FCSA, "LEADER among FCS
  peers") and attributed to FCMA. **Fix:** add a peer-name guard (reject figures
  whose subject is a locked peer or a "Peer NPS benchmark"/pipe-delimited peer
  list), mirroring the money-fence guard; harvest the client's own App Store/
  Google Play/Glassdoor rows from the evidence index + client-profile sentiment
  table.

### catalogue label mismatch — scoring-export (FCS) names vs resolved v2.4 labels
- Category/subcap labels ("Localization", "Mobile App Experience") are mismatched
  v2.4 catalogue names while the scoring export uses FCS names (P2C1 Digital
  Acquisition & Onboarding, P2C3 Customer Service). **Fix:** prefer the
  category/subcap names in the scoring-export CSVs (or bridge via
  `ccg_subcap_aliases`) when they disagree with the resolved catalogue; take the
  binding gap from the real category-summary CSV (widest negative), excluding NA.

## Wave-1 complete: greenstone, capital-farm-credit, regions-bank, alliant-insurance, farm-credit-mid-america (5 overlays committed).
