# Rulebook: heatmap · v1 (2026-08-19)

The heatmap page's anti-pattern rulebook: what a promoted heatmap looks like when
it is right (Baxter, run `c1351d25`) and the measured, gated failures that reached
promotion before the gates existed (chiefly Logix, run `d7ed1d90`). The **heatmap
producer reads it before authoring, as Method step 2**, beside `get_memory_digest`
+ `search_findings`; the **rectifier is its only writer** — an edit with no finding
behind it is an opinion. Entries raised by a USER or REVIEWER are **PERMANENT and
never retired**. Baxter is **v5.0-shaped — 17 categories including P1C5, 706
cells — its shape-specific counts are v5.0 facts, not contracts**; v7.0 has 16.

---

## H4 · Workbook grain scores

### Baxter positive pattern

Every grain the workbook states is served with the location it was struck in:

> `"P1": {"score": 3.11, "peer_median": 2.9, "source_cell": "Pillar_Summary!C2"}`

> `"P1C1": {"score": 3.57, "peer_median": 3.0, "source_cell": "Category_Detail!D2"}`

> "The grid is the run's ground truth: every served cell's raw score by pillar and
> category, before any rounding or colour. Everything argued elsewhere resolves back
> to a cell here, and the two active cross-pillar caps show as the scores they hold
> down — the data layer beneath an otherwise modern estate." (narrative_thread)

Shape notes, measured: all 4 pillars and all 17 categories carry `score` +
`peer_median` + `source_cell` — the stated figure, never a recomputed mean; peer
figures exist at exactly these two grains and on no cell; the thread says what this
section adds (CG-23/CG-29 discipline) rather than restating the page.

### Anti-patterns

- **MEM-0088 / SILENT-PARSER-DROP** — the stated pillar and category grains can be
  lost at ingest with no observation — measured on Logix: `get_report_bundle`
  rollups returned pillars=0, categories=0 against Baxter's 4/17, no
  parser_observation explaining it; downstream the promoted Logix H4 serves **no
  score at either zoom**, only cohort peer medians, with a partial empty_state:
  "this run's workbook rollup rows did not survive ingestion" — the rule: an empty
  grid zoom is an ingest fault to name in `empty_state` and route, never a figure
  to recompute by averaging subcapabilities; cap logic and analyst override are
  applied when the stated figure is struck, so a recomputed mean is a number no
  source states.
- **MEM-0028 / (no gate sees a label)** — the workbook's category labels name a
  different capability domain from the pinned catalogue — measured: 17 of 17 labels
  differ from `get_capability_catalogue`, 4 substantively — the rule: every rendered
  pillar/category/cell NAME resolves through the catalogue, never the workbook label
  column and never report prose; nameless cells mean a catalogue pin to fix on the
  run (0 of 765 cells named on one run scored against v5.0 and joined to the
  16-category catalogue), not a name to copy.
- **MEM-0086 / CITATION_NAMES_THE_CONTAINER_NOT_THE_SPAN** — three peer figures were
  cited to the dataset's download page, which carries no institution figure —
  measured on Logix: a regex for every named peer and every quoted figure over all
  37 cited rows matched 0 — the rule: the cited span carries the figure; a peer
  median whose evidence row does not contain the number is uncited, and
  `peer_basis = cannot_estimate` with a null median is the honest fallback.
- **MEM-0085 / ET-09** — the gate refuses a run's own named peer cohort as
  contamination whenever peer scoring is pending — measured on Logix: 2 blocking
  ET-09 reasons on `peer_reference` fields while `peer_scores` had 0 rows, and the
  heatmap payload naming the same five institutions passed — the rule: the
  connector's verdict decides, and a false positive is reported with
  `report_recurrence`, never dodged by renaming the cohort obliquely.
- **(no MEM) / 9-antipatterns §6** — a peer figure computed from a different cohort
  than the one beside it; no gate sees two bases on one surface — measured: 14 of 16
  categories carried a peer median and two carried none because the cohort was
  assembled once and never revisited — the rule: one cohort, one pass, for every
  peer figure on the page (pillar, category, inherited cell proxy, focus area), with
  its size stated; the deleted `score + 0.3` peer-tick arithmetic stays deleted, so
  a missing peer figure is visibly missing, never plausibly present.

### Exclusion set

`r_layer` never serves to any audience (Logix marks it in `internal_only`; the
serve layer strips it regardless — marking is still mandatory, invariant 5).
Customer-audience keys on this section are exactly `pillars`/`categories`
`{score, peer_median, source_cell}` plus the envelope; `empty_state` serves only
`{reason, closure_condition, closure, kind}` — the `sources_searched` array the
Logix empty_state carries is a probe ladder and drops at serve. Never emit an
M-code, cap ceiling or uncertainty band into this section's prose: `cap_level`,
`ceiling`, `uncertainty_band`, `urf_modifiers` are excluded key classes.

---

## H1 · Focus areas

### Baxter positive pattern

The quote is the client speaking, named person, named artefact:

> "John Sahagian (CDO): 'Legacy bots stop the conversation. Agentforce rolls with
> it. Freeda understands what the member means and keeps the conversation
> moving.'" — Salesforce customer story, BCU Agentforce (2026-01), CONFIRMED_CURRENT

> "BCU digital strategy pillars: Member-first, Tech Standards (API-driven,
> connectivity, scalability), Data Strategy (harness member intelligence for faster
> decisions)" — CULytics (2020-09), **UNCONFIRMED** — the honest currency verdict
> for a six-year-old statement nothing recent restates.

> currency_note: "Restated on a PYMNTS panel in Aug 2025; the 'patchwork quilt'
> warehouse refactor (CreditUnions.com) is in motion, so the priority is live in
> the client's current voice."

Shape notes, measured: 4 areas (contract range 3–5); every area carries
`involved_subcap_ids` over cells this run serves, `entity_score` beside
`peer_score` at the same grain, `new_evidence_ids` minting the step-2 currency
sweep as evidence (E-BCU-058-R2, E-BCU-061), and a per-area `r_layer`. One
UNCONFIRMED among four is the currency validation doing its job, not a defect.

### Anti-patterns

- **(no MEM) / S9_focus_invalid, S29_focus_grounding** — machine scoring text
  shipped as the client's quote — the pack's measured corpus: 53 clients shipped
  scoring-ledger annotations, cut-off diagnostic questions or `Score M1..M5` text
  as `verbatim_quote` — the rule: reject any quote candidate containing a
  capability code, "Score M", or a [Section] tag; the quote must read like a person
  wrote it about their own institution, and the Logix and Baxter quotes above are
  the calibration.
- **MEM-0060 / CG-19** — a required list satisfied by `[]` writes no rows and the
  surface vanishes with nothing saying why — measured: enumerated across both
  promoted clients, exactly one unexplained empty content list each; 57 of 138
  corpus clients had no focus areas at all, which for a client with a full
  assessment is a synthesiser failure to diagnose, not an empty state to render —
  the rule: items, or a declared `empty_state` with the real reason, never a bare
  `[]`. **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_required_list_not_silently_empty.py`.
- **(no MEM) / CG-27** — an abbreviation expanded inside a verbatim span misquotes
  the source — measured while fixing the FCU/NCUA sweep (9-antipatterns §4): a
  tidy-up rewrote the chief executive's congressional testimony "greater CFPB
  scrutiny" — the very span that is Logix FA-1's `verbatim_quote` — the rule: a
  `verbatim_quote` is a byte-for-byte span and is never edited; spell out
  abbreviations in `name` and other authored labels instead; pinned by
  `apps/mcp/tests/test_round4_gates.py::test_a_verbatim_span_is_never_rewritten`.
- **(no MEM) / 9-antipatterns §6 + the pack's grain rule** — a focus-area score
  built from a different cell set than its peer figure is a grain violation — the
  Logix payload shows the honest form of the hard case: its empty_state declares
  the peer column empty because "the cohort this assessment names has never been
  scored", rather than importing a number from elsewhere — the rule: `entity_score`
  is the mean over `involved_subcap_ids`, `peer_score` the same cells' medians at
  the same grain, or null with the reason declared.
- **(no MEM) / provenance triple (S29)** — a quote without its source page cannot
  be shown to the client where it came from — measured: Logix carries
  `source_page` 2, 4, 1 on its three areas (document quotes); Baxter's four carry
  `source_page: null` because its quotes come from panels and web stories that
  have no pages — the rule: when the quote is from the Client Profile DOCX or any
  paged document, the triple document + page + filename is required; a null page is
  only honest for an unpaginated artefact, and the artefact must then be named
  exactly.

### Exclusion set

`focus_areas[*].r_layer` never serves — Logix marks all three per-item paths in
`internal_only`; do the same (producer marking stays mandatory even though the
serve layer also strips `r_layer` for every audience). Customer keys per area are
the contract fields (`fa_id, name, verbatim_quote, source_document, source_page,
source_filename, involved_subcap_ids, entity_score, peer_score, delta,
currency_status, currency_note, confidence, new_evidence_ids`); `empty_state`
serves `{reason, closure_condition}` only — its `sources_searched` drops. No probe
vocabulary (`queries_run`, `searched_on`) anywhere in area prose.

---

## H2 · Cell evidence

### Baxter positive pattern

The full grade shape, reported so nothing can hide:

> `linking_stats: {"cells_served": 706, "cells_scored": 706, "cells_cited": 169,
> "cells_inherited": 529, "cells_declared": 8, "cells_with_a_row": 706,
> "cells_with_no_row": 0, "rows_unlinkable": 0,
> "cells_cited_elsewhere_not_cited_here": 164}`

A cited synthesis that opens on the institution, not the corpus (P1C1.1.1,
grounded_on 4):

> "BCU names three strategy pillars in its own materials — member-first,
> application programming interface-driven technology standards, and a data
> strategy to harness member intelligence for faster decisions — with a chief
> digital officer appointed in 2023 … The articulation is unusually specific for a
> credit union. Its most complete public statement dates from 2020, so what is
> current is inferred from the appointments since."

An inherited synthesis that reasons to THIS cell (P1C1.1.4):

> "The vision BCU communicates is aimed outward: strategy pillars presented to an
> industry audience, an AI operating model set out from a conference stage. …
> How that message reaches 767 employees across 46 branches, and whether they can
> repeat it, is not something any external source can establish."

A declared synthesis that names the artefact the capability would have left
(P1C4.1.6, one of the eight, all `thin: true`):

> "User acceptance testing leaves artefacts — test plans, sign-off records, defect
> logs — and none is visible in BCU's public record … a sign-off record from the
> Elevate rollout would settle it."

Shape notes, measured: 706 of 706 cells carry a synthesis; grades 169/529/8;
`grounded_on == len(e_ids)` on all 706 (AG-02); the eight declared cells each name
different artefacts, which is why they pass CG-15's template check; no cell carries
a name — names resolve from the catalogue at read; items resolve at read from
`e_ids` (the drawer shows UNRESOLVED rather than silently dropping a dead id). Note
the v5.0 caveat: 706 and 169/529/8 are Baxter facts, not targets.

### Anti-patterns

- **MEM-0031 / CG-15, AG-03** — the cell-grain absence protocol had no storage, so
  producers invented it and both gates honoured the invention — measured: 394 of
  697 cells on one payload carried keys the item shape did not declare, buying a
  CG-15 and an AG-03 exemption seen by nobody; RECURRED (REF-0012 gave the columns,
  REF-0016 re-armed CG-15) — the rule: emit only the keys `get_page_contract`
  declares on `cells[*]` today (the shape has since gained `grade`, `state`,
  `closure_condition`, `sources_searched` columns); an undeclared key buys nothing
  and CG-04 refuses it.
- **MEM-0038 / CG-15 (ladder-rung predicate)** — the absence exemption is
  satisfiable by a constant — measured: 517 of 517 uncited cells bought it with the
  same two-rung ladder, `sources_searched[1] = 'Run ladder in section r_layer'` in
  a single GROUP BY bucket; the same 517 syntheses return 475 CG-15 blocks with the
  trio stripped — the rule: at least one rung names a host, URL or quoted query;
  a pointer to another section is refused by name; rungs are distinct per position
  once the cell's own identifiers are masked.
- **(no MEM) / CG-15** — one declared argument rendered four hundred times —
  measured: two 700-cell payloads refused on 2026-08-08 for following the grade
  table literally, and MEM-0080's session measured 99 of 633 generated declared
  syntheses falling into 23 template groups under
  `scripts/check_repetition.py` — the rule: name **what you looked for, not that
  you looked** (the eight Baxter declared cells are the worked examples); run
  `check_repetition.py` on the first twenty drafts, not on 708; where a cell
  defeats even that, omit it — declared-and-identical ranks below no row at all.
  Pinned by `apps/mcp/tests/test_vacuity.py`.
- **MEM-0041 / (computed at read)** — the drawer was exempted from needing a column
  because it is computed at read, and nothing computed it — measured on Baxter's
  own run c1351d25 pre-repair: `cells_citable` 0 of 706 while `cells_linked` 698,
  because no cited id resolved to an excerpt-bearing row — the rule: cite `e_ids`
  that resolve, in order (order is meaning); `grounded_on` is computed, never
  asserted; ids that resolve to another institution halt production (invariant 4).
- **MEM-0036 / CG-16, CG-17** — a contract-complete heatmap cannot be hand-emitted —
  measured: 1,360,972 bytes over 685 cells is 482 hand-typed parts; and a partially
  transmitted payload that staged would validate and serve a fraction (the 69-of-765
  reference case) — the rule: carry `cell_evidence` with the transport script
  (REF-0013), declare `expect={'heatmap.cell_evidence.cells': N}` so a truncation
  at a valid JSON boundary is caught (CG-17).
- **MEM-0080 / RULE_HELD_IN_TWO_PLACES_DRIFTS** — H2 cannot declare the served cell
  set O10's denominator is checked against — measured: O10 per-pillar denominators
  summed to 705 while `len(cells)` was 72 — the rule: one served cell set for every
  count on every page; `scripts/check_consistency.py` recomputes the cross-surface
  numbers and fails `cells_cited_elsewhere_not_cited_here`, which no per-page gate
  can see. Baxter promoted reporting 164 there — the shape made it visible; drive
  it to zero by working tier 1 of the coverage order first.
- **MEM-0032 / CHECKER_FALSE_POSITIVE** — the skill-local checker refuses the run's
  own T2 variant cells — measured: 32 of 35 `check_payload.py` blocks were variant
  ids the connector's own `_SUBCAP_RE` accepts (`precheck_gates.py`: 0 blocking);
  Baxter legitimately serves `P2C2.1.CU1` — the rule: the connector's answer
  decides; a local checker that disagrees is a drift finding to record, not an
  instruction to strip cells.
- **(no MEM) / measured on Logix d7ed1d90** — a single reach number lets 11%
  coverage sound like progress — measured: Logix `linking_stats` reports only
  `{cells_linked: 76, cells_scored: 705, cells_citable: 76, rows_unlinkable: 629}`,
  the pre-grade shape with no cited/inherited/declared split — the rule: report the
  grade shape Baxter reports, plus `cells_cited_elsewhere_not_cited_here`, the
  number to read first.

### Exclusion set

Per-cell `sources_searched` is contract-legal and **customer-stripped** (probe
class — measured on Logix: 4,527 strings over 680 cells served to the customer
body before the boundary existed). Item-level method vocabulary — `tier`, `ers`,
`recency_band`, `provenance`, `link_basis`, `discovered_by` — strips for the
customer audience; the drawer's customer face is the excerpt, source and claim
label. `r_layer` never serves. The customer allowlist keeps `linking_stats` to
`{cells_linked, cells_scored, rows_unlinkable}` — the grade counts drop by
default-deny until classified, so never rely on the client seeing them.
`empty_state` serves `{reason, closure_condition}`; `searched_on` drops.

---

## H6 · Evidence store

### Baxter positive pattern

One registered absence-check doing category-wide work through explicit linkage:

> `E-BCU-063 · T1 · FACT · "No NCUA enforcement actions found against BCU (searched
> enforcement database + formal orders). BCU state-chartered, NCUA"` — url is the
> regulator's own enforcement page; `supports_subcap_ids` fans out across the
> P3C3 compliance cells the finding actually bears on.

Shape notes, measured: 98 rows, every excerpt a verbatim span (50–500 chars, never
a URL, never a summary); `claim_type` split FACT 83 / INFERENCE 15 — inference
labelled as such, never dressed as fact; `discovered_by: package` on package rows
so minted E-CC rows are distinguishable; tiers T1/T2/T3/T5 assigned by source
nature. 47 of 98 rows carry `published_date: null` — carried as null, never a
sentinel (invariant 9).

### Anti-patterns

- **MEM-0011 / PROVENANCE_NAMES_THE_TOOL** — nineteen rows cited the tool that
  found them instead of the document — measured on Baxter's own serving history:
  19 rows matched /vibe/i, 12 distinct source_names sharing exactly 1 URL,
  `vibeprospecting.explorium.ai` — the rule: a URL carrying many names is a tool;
  provenance names the document, and the probe is one GROUP BY away.
- **MEM-0087 / EVIDENCE-TIER-MISCLASSIFICATION** — a machine technographic scan can
  be registered below T1 and nothing refuses it — measured on Logix: E-CC-308 at
  T4, ers 3.75; the same content re-registered at T1 returned mean +0.85 — the
  rule: a machine technographic scan is **T1, never T4**; filing it low caps the
  capability and silently suppresses the score.
- **MEM-0020 / ET-01 (invariant 4)** — every id on one run resolved foreign to
  another entity — measured: 35 of 35 ids `foreign`, because the E-0NN namespace
  collides per-package — the rule: package evidence keeps its original id, anything
  else is registered through the connector which allocates the id; **never choose
  an id yourself** — an invented id is fabrication by construction even when the
  source is real; `foreign` halts production.
- **MEM-0070 + MEM-0074 / (register_evidence error states)** — a paraphrase and an
  unreadable container return the same error, and a bot-gate wears the same word as
  an absence — measured: a byte-verbatim PDF span returned `excerpt_not_verbatim`
  (pypdf finds it in the same URL's bytes); www.ciro.ca returns `url_unreachable …
  HTTP 403 (served by cloudflare)` while odlumbrown.com fetches fine — the rule:
  distinguish cannot-read / not-present / refused-robot; do not register a row you
  did not read, do not register a URL you could not retrieve, and never convert a
  403 into an absence claim.
- **MEM-0079 / ET-07** — a row registered without cell links costs three
  submissions one round trip at a time — measured: 9 unlinked rows, 11 ET-07 blocks
  across 3 submissions; re-registering byte-identical content WITH
  `linked_subcap_ids` dedupes onto the same e_id and moves the links — the rule:
  register with `linked_subcap_ids`, or for genuinely capability-free rows
  (registry records, XBRL periods) name the id where `_stated_unlinked` reads it.
- **MEM-0094 / ET-07 vs CG-04 (resolved by REF-0037)** — the gate prescribed a
  repair the contract refuses — measured: 12 ET-07 blocks on the index, then CG-04
  refused the prescribed `r_layer` statement because `heatmap.evidence` has no such
  key — the rule: the index is identity-grain (REF-0037 registered it beside
  `evidence_age`); its rows make no capability claim, so do not author `r_layer`
  into this section, and route a gate-vs-contract contradiction to the rectifier
  instead of forcing either side.

### Exclusion set

`tier` and `ers` strip for the customer audience even here — the census section
that explains the method is never served, and these are the same vocabulary
escaping row by row (measured on Logix: `evidence rows[16].tier` served before the
boundary). `discovered_by` strips (Logix marks `evidence[*].discovered_by` in
`internal_only`; do the same). Customer keys per row: `e_id, source_name, url,
excerpt, claim_type, published_date, supports_subcap_ids, surfaces`. `empty_state`
serves `{reason, closure_condition}` only.

---

## H9 · Value-chain view

### Baxter positive pattern

The whole promoted body is the envelope, and the thread says why:

> "This run promotes no value-chain view: the assessment scoped its reading to the
> capability grid, and no stage-by-stage mapping was produced to serve here. The
> page's line runs from the grid's raw scores through the focus areas and alerts
> into the per-cell evidence drawers…" (narrative_thread; `e_ids: []`, no stages,
> no fields)

Shape notes: `fields: {}` is the answer, not a gap — the arrangement is a property
of the catalogue for this sub-vertical and version, derived server-side from
`ccg_value_chains` × `ccg_vc_mapping`. Logix's empty_state shows the other honest
case: it names the exact derivation fault ("the catalogue carries a credit-union
value chain at v7.0 … but the run returns no cell-to-stage mapping") and a
closure_condition that places the fix upstream of the payload.

### Anti-patterns

- **(no MEM) / CG-04** — an invented stage list is a contract fork, not a helpful
  addition — the section contract has no fields for stages, order or membership to
  fork into, and CG-04 refuses keys outside the contract — the rule: author the
  envelope and, where the chain cannot stand up, the `empty_state` naming which of
  the two causes you established (no chain authored for this sub-vertical at this
  version, vs a chain that exists and a run that does not render it) — never
  borrow a neighbouring sub-vertical's chain, which renders the client's own
  operating model back to them incorrectly.
- **(no MEM) / measured on Logix d7ed1d90** — an identifier rewritten by a label
  pass — measured: the served Logix empty_state reads "VC-credit union-01 through
  VC-CU-08", the first stage id expanded mid-identifier — the rule: an id is a
  span, not a label (CG-27's own exception); quote stage ids byte-for-byte, and
  remember `chain_id` names one STAGE, not an arrangement — only `sub_vertical` +
  `version` identify a chain, so never present a `chain_id` as a chain's name.

### Exclusion set

Envelope only: `e_ids`, `internal_only`, `narrative_thread`, `produced_at`,
`producer_version`, `empty_state {reason, closure_condition, closure, kind}`,
`r_layer` (never served). The `sources_searched` Logix put in this empty_state
drops at serve — record derivation probes there for the internal audience if
useful, but never let the customer-facing `reason` depend on them.

---

## H3 · Thin-evidence alerts

### Baxter positive pattern

An alert is a work item with a state, a licence and a named closure artefact:

> `P1C3.4.4 · WORKED_ABSENT · HIGH` — justification: "IP/patents: the assessment
> ran PUBLIC-mode research and recorded this cell as NO_EVIDENCE. Cannot score
> without internal evidence. The evidence that exists licenses a ceiling estimate
> only; the internal artefact named in the closure condition settles it." —
> closure_condition: "INT-020: Does BCU hold proprietary technology patents or
> trademarks?"

Shape notes, measured: 11 alerts, states split UNWORKED 6 / WORKED_ABSENT 5 —
never merged into one count; every alert carries `sources_searched`,
`queries_run`, `runs_open` and a closure_condition specific enough for the next
person to work; `evidence_count` states the deficit plainly. Logix's queue shows
the ladder actually run: 14 alerts, 29 real queries logged, justifications naming
the artefact whose absence sets the score ("A model inventory leaves an artefact —
a register naming each model, its owner, its purpose and its approval date").

### Anti-patterns

- **MEM-0063 / (promote's `open_alerts` count)** — a run promoted with 98 open
  alerts because nothing anywhere counted them — measured: severity {high 59,
  medium 39} on the served dashboard, zero count checks in promote or validation;
  the owner's ceiling of 15 landed as ALERT_CEILING (REF-0034) and was then
  **retired 2026-08-16** when a PUBLIC-mode client honestly owed 621 — a ceiling
  that refuses the corpus leaves deletion as the only escape, the one repair its
  refusal text forbade — the rule that survives: the count is computed from the
  payload being written and returned on every promote (`open_alerts`, invariant 8);
  classify every thin cell UNWORKED / WORKED_FOUND / WORKED_ABSENT and never delete
  an alert to shrink a queue. **PERMANENT — never retire** (raised_by_kind USER);
  test: `apps/mcp/tests/test_alert_ceiling.py`.
- **MEM-0074 + MEM-0072 / (three error states, two words)** — a refused retrieval
  recorded as an absence — measured: entity WAFs and a Cloudflare-gated regulator
  403 the verifier while serving humans the same day (Logix's own
  `sources_searched` records logixbanking.com answering "this run's evidence
  verifier with an HTTP 403 … a refused retrieval path, which records nothing
  about the institution") — the rule: **a 403 must never become WORKED_ABSENT**;
  a blocked rung is recorded as refused-robot and the fact is cited from a source
  that is not bot-gated.
- **MEM-0038 / CG-15 (ladder-rung predicate)** — 98 alerts, 1 distinct ladder —
  measured: `count(DISTINCT sources_searched) = 1` across the whole queue on the
  run that also bought the H2 exemption with a constant — the rule: an alert's
  ladder names the hosts, URLs and quoted queries actually run for THAT cell;
  Baxter's per-alert INT-nn closure questions and Logix's per-cell query pairs are
  the calibration.
- **(no MEM) / measured on Baxter c1351d25** — the queue and the grid disagree
  about which cells are thin — measured on the promoted positive reference itself:
  the 11 alerted subcap_ids and the 8 cells `cell_evidence` marks `thin: true` are
  **disjoint sets** (intersection 0); no gate sees the join — the rule: H3 and H2
  must agree — every alerted cell is one the payload declared under-evidenced, and
  the reference client is audited like any other (the lesson of MEM-0064, itself
  USER-raised and permanent where it is homed, pinned by
  `apps/mcp/tests/test_serialised_leaves.py`); check the join before submit,
  because nothing else will.

### Exclusion set

`queries_run`, `sources_searched` and `searched_on` are probe-class keys and strip
for the customer audience (measured: 29 raw search strings served in Logix alerts
before the boundary). `justification` and `closure_condition` **stay** —
owner adjudication 2026-08-14: a producer's real reason renders, a probe never
does. `r_layer` never serves (Baxter and Logix both mark it). Severity, state,
`evidence_count`, `runs_open`, score and subcap_id serve to the customer.

---

## H5 · Safeguard gates

### Baxter positive pattern

Both arrays, each doing its own job, nothing invented:

> caps[0]: `CAPG-01 · kind: cap · ceiling: "3.0"` — "Cross-pillar: P4C1<2.5→P2C4
> cap 3.0 — applied to 15 cells by the assessment's cap log" — with the six e_ids
> that evidence the cap.

> gates[0]: `SG-V4 · NOT_RUN` — plain_label: "Every claim is checked against this
> assessment's own evidence before it reaches you" — not_run_reason: "No embedding
> tier attached at submit; grounding abstained and recorded itself"

> gates[1]: `SG-S8 · PASS` — plain_label: "Sentiment rests on more than one line" —
> detail: "6 rated rows across customer and industry audiences"

Shape notes: every gate_id is a real registry gate; NOT_RUN is disclosed with its
reason rather than laundered into PASS; the cap's rationale is the workbook's own
cap-log reason, not an invention to explain a low score. Logix shows the other
honest form: `gates: []` with an empty_state stating that the connector writes SG
results to `gate_results` at submit, "one authored here would either duplicate a
machine measurement or assert one that never ran" — while its caps[] carries what
the assessment itself applied (PUBLIC-mode cap across all 16 categories, peer
comparison pending).

### Anti-patterns

- **MEM-0083 / CG-22** — fabricated safeguard gate_ids rendered FAIL with no real
  gate behind them — measured on Logix's promoted heatmap: SG-E1, SG-E2, SG-Q1,
  SG-D1, `explain_gate` returning unknown_gate for all four — the rule: every
  `gates[].gate_id` is a gate the registry knows; a genuine disclosure with no
  registry gate belongs in `caps[]`; a retired gate still counts as real, and a
  removed rule must not answer (`SG-AC1` returns unknown_gate by test). Pinned by
  `apps/mcp/tests/test_safeguard_gate_ids.py`.
- **(no MEM) / the section's own contract line** — a gate reporting PASS because it
  did not run is worse than one reporting FAIL — Baxter's SG-V4 NOT_RUN with its
  recorded reason is the worked example — the rule: `not_run_reason` is REQUIRED
  wherever result is NOT_RUN; a failing SG discloses and still promotes (invariant
  12), so there is never a reason to suppress or upgrade a result.
- **(no MEM) / measured on both payloads** — one blob where two arrays belong — the
  original prompt emitted neither a result nor a plain label, and the prototype's
  single "safeguard gates" blob is a listed correction — the rule: `caps[]` is what
  the ASSESSMENT applied (read from the workbook cap log and QA verdict), `gates[]`
  is what the SUBMISSION's SG family found; `plain_label` is a human sentence,
  8–18 words, on every client-visible gate.

### Exclusion set

`caps[].ceiling` is an excluded key class and **drops for the customer audience**
(the generated allowlist keeps `{cap_id, kind, rationale, affected_categories,
e_ids}`) — so the `rationale` must carry the story without leaning on the M-code
or numeric ceiling, which the client will not see. `uncertainty_band`,
`cap_level`, `urf_modifiers` likewise never reach customer prose. `r_layer` never
serves; `empty_state` serves `{reason, closure_condition}` and its
`sources_searched` drops.

---

## H7 · Evidence age tracker

### Baxter positive pattern

A row pins both dates so the age is reproducible, and identity is checked:

> `{"e_id": "E-CC-006", "title": "NCUSO.org National Credit Union Administration
> Data", "identity_ok": true, "source_domain": "ncuso.org",
> "reference_date": "2026-03-30", "published_or_asof": "2025-09-01"}`

Shape notes, measured: 65 rows, one pinned `reference_date` across all of them
(the run's as-of date, rendered — age is meaningless without the date it was
computed against); `published_or_asof` real on 65 of 65, so `stale_pct: 0.0` and
`undated_pct: 0.0` are computed facts, not defaults; `identity_ok: true` on every
row after resolving each domain. Logix carries the fully derived triple and shows
the derivation holding: bands {current 10, aging 5, undated 5, stale 4, dated 2}
mapping exactly to statuses {FRESH, AGING, UNDATED, STALE, DATED}, 26 of 26
consistent, with an age like `16.6` months computed from its two dates.

### Anti-patterns

- **(no MEM) / the H7 gate line ("no NaN in any age cell; status derived from
  band")** — a status asserted over an uncomputable age — the measured render the
  prompt records: "NaN mo … FRESH" on every row, a positive status over a null
  computation — the rule: absent or unparseable `published_or_asof` ⇒
  `age_months: null`, `band: undated`, `status: UNDATED`; **never NaN, never a
  sentinel, never a status a computed band did not produce** (invariant 9).
  Undated is UNVERIFIED, never current — 24 corpus clients shipped 100% undated
  evidence while quoting current figures, which is why `undated_pct` is reported
  on every run (both reference payloads report it).
- **(no MEM) / the same gate line** — a third freshness vocabulary — the band set
  is exactly `current / aging / dated / stale / undated` over the 12/24/36
  boundaries the ERS Recency factor already uses; both promoted payloads conform —
  the rule: do not invent a vocabulary; the prototype's Current/Aging/Stale dot at
  6/12 months is a listed correction, and the payload never carries its labels.
- **(no MEM) / identity gate ("every source domain identity-checked")** — a domain
  belonging to a different institution counted toward coverage — the rule:
  `identity_ok: false` quarantines the row, escalates, and keeps it out of
  coverage and the tier mix; both payloads measure 100% `identity_ok: true`, which
  is the state to preserve, not a check to skip.
- **(no MEM) / measured on Logix d7ed1d90** — ageing rows that cannot open —
  Logix's empty_state states the honest scope: the panel ages the 26 excerpt-
  bearing cited sources, because a row with no excerpt "can be neither aged …
  nor listed here, because listing it would put an evidence chip on the panel that
  opens onto nothing" — the rule: the tracker's population is the citable corpus;
  quarter-precision dates ("2025-Q4") ARE dates and resolve to quarter end, never
  to undated.

### Exclusion set

Customer rows serve `{e_id, title, source_domain, published_or_asof, age_months,
band, status, identity_ok, reference_date}` plus the two roll-ups — note `band`
and `status` here are contract keys and serve; it is the evidence-method class
(`recency_band`, `tier`, `ers`) that strips elsewhere. `r_layer` never serves;
`empty_state` serves `{reason, closure_condition}` and Logix's `sources_searched`
in it drops.

---

## H8 · Cross-entity patterns

### Baxter positive pattern

A cohort too small to publish is declared, challenged and withheld — not padded:

> insufficient_cohorts[0]: `{sub_vertical: "SV2", cohort_size: 1,
> insufficient_cohort: true}` — r_layer hypothesis: "No SV2 cohort pattern can be
> published: one promoted run against a threshold of five." — counter: "Could
> adjacent sub-verticals stand in? No — a cohort is same-sub-vertical by
> definition (spec H8), and widening it would publish a comparison the spec
> forbids." — domain_test: "A one-member cohort cannot be anonymised at any k;
> withholding is the only compliant output."

> empty_state: "Cohort patterns need at least five promoted runs in the same
> sub-vertical to clear the k-anonymity threshold; this corpus serves one promoted
> SV2 run, so no pattern can be stated." — closure_condition: "Five or more
> promoted SV2 runs"

Shape notes: `patterns: []` with the reason is the correct output at corpus size
one; the r_layer records the widening temptation and refuses it explicitly. Logix
adds the second discipline: the five institutions its assessment names as
financial peers are "checked against this rule and set aside" — a named peer list
is not a scored cohort, so it raises no count.

### Anti-patterns

- **(no MEM) / the H8 gate line ("threshold enforced or the exception
  labelled")** — a below-threshold row served under a threshold header — the
  measured render the prompt records: a 50% row under a ">=60%" header, an
  unenforced threshold or a mislabelled header, both defects — the rule:
  `threshold_pct` (measured: 60, and Logix serves it) is enforced; a pattern shown
  below it carries `below_threshold: true`; `share_pct` renders with numerator and
  denominator visible, because "67%" alone hides that it is 4 of 6.
- **(no MEM) / invariant 5, `ALWAYS_STRIP`** — another entity's identity on a
  client-scoped page — `entity_ids[]` exists for internal audit and is stripped
  for **every** audience by the serve layer's `ALWAYS_STRIP` mechanism, not by
  producer goodwill — the rule: emit counts and shares only; verify on the
  rendered output, not the payload; never let a pattern statement, action or
  structural explanation name or fingerprint a cohort member (one outlier's
  identifying detail is as bad as a name).
- **(no MEM) / the H8 prompt's cohort rules, measured on both payloads** — a
  pooled or stale cohort — never pool across sub-verticals (a Farm Credit
  association and a regional bank do not share a loan-origination cohort);
  `cohort_size < 5` ⇒ `insufficient_cohort: true` and nothing published (Baxter's
  worked example above); where the cohort's runs span more than 18 months, say so;
  and before calling anything a cohort pattern, check the shared-technology
  explanation — a shared weakness across entities running the same core is a fact
  about the VENDOR, and for SV9 specifically the FPI/AgVantis/district-bank check
  is mandatory — the rule: a withheld pattern costs nothing; a wrong one gets
  repeated to clients.

### Exclusion set

`entity_ids` strips for every audience (`ALWAYS_STRIP`) — its presence in the
generated allowlist is irrelevant because the strip runs first; treat it as
audit-trail only. `r_layer` (including `insufficient_cohorts[].r_layer`) never
serves. `empty_state` serves `{reason, closure_condition}`; the
`sources_searched` both payloads carry there drops. Customer-visible pattern keys:
`sub_vertical, category_id, category_name, pattern_statement, affected_count,
cohort_size, share_pct, threshold_pct, below_threshold, confidence,
structural_explanation, action`.
