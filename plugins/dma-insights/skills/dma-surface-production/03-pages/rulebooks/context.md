# Rulebook: context · v1 (2026-08-19)

The context page's anti-pattern rulebook: what a promoted context page looks like
when it is right (Baxter, run `c1351d25`) and the measured failures that reached
promotion before the gates existed (chiefly the same page's own pre-gate rounds,
plus Logix, run `d7ed1d90`). The **context producer reads it before authoring, as
Method step 2**, beside `get_memory_digest` + `search_findings`; the **rectifier
is its only writer** — a producer never edits it, and an edit with no finding
behind it is an opinion. Entries raised by a USER or REVIEWER are **PERMANENT and
never retired**, whatever later rounds conclude. Baxter is **v5.0-shaped — 17
categories including P1C5, 706 cells — so every shape-specific count quoted from
it is a v5.0 fact, not a contract**; a v7.0 run has 16 categories. C6 renders
`overview.financial_series` — one section, written once on the overview page; its
rulebook entry lives in the overview rulebook, and this page never authors it.

---

## C1 · Digital evolution timeline

### Baxter positive pattern

> "NEUTRAL — It adds a second member book and a second set of source systems to
> integrate, and takes no capability away, so the two integration cells score
> what they scored before it. The pressure is real and it is the why-now's
> claim, not this badge's." (`maturity_effect` on the announced merger — the
> badge reads the assessment, not the news; the same transaction anchors WN-1
> and is therefore never NEGATIVE here)

> "An email-based data breach occurred and was remediated. Fifty-four months
> have elapsed, beyond the assessment's twenty-four-month severity window, so
> the cap it once carried has been retired." (`body` on the 2021 breach,
> signal NEUTRAL — rung 1 of the borderline test answered by the caps log:
> `Cap Applied: None (>24mo; P4C4 cap retired)`, and the event says so)

> "By November 2022 the member-facing platform was Lumin Digital […] The switch
> date itself is not stated in any source reached, so this event marks when the
> replacement is first evidenced, not when it was decided." (dating honesty —
> no event carries a date its cited evidence does not)

> "What the newest events change is the price of the gap, not the assessment of
> it." (`storyline` closing — the evidence sentence for `arc_shape:
> LEGACY_ANCHORED` lives here, in prose, not in the enum field)

Shape notes, measured: 11 events, every one dated to at least the month, every
`kind` one of the contract's eight words, every `signal` a single upper-case
token — 7 POSITIVE, 4 NEUTRAL, 0 NEGATIVE, and the zero is argued (retired cap,
forward obligation, unconverted announcements), not cosmetic; every badge and
its `maturity_effect` clause are one claim (POSITIVE↔ADVANCED,
NEUTRAL↔NEUTRAL, checked pairwise in the r_layer); `arc_shape` is the bare
token; `verified_sparse` untouched at 11 events. The last worked event —
leadership evolution as NEUTRAL, "the merger error with the sign flipped" — is
the check that the definition is a definition, not a way to make pages read
better.

### Anti-patterns

- **MEM-0010 / CG-09** — an enum-shaped field written with prose matches no
  filter — measured on this page: `signal` carried the consequence sentence on
  all ten events of a promoted run and D5's Positive/Neutral/Negative filters
  matched **zero of ten** on a page showing ten; the recurrence served
  `arc_shape: "strategy-first, substrate-later"` against a declared five-value
  vocabulary, and the same run's kinds included `TECHNOLOGY` (3) and
  `CAPABILITY` (1), reasonable words that match no filter — the rule: `signal`
  is `POSITIVE │ NEUTRAL │ NEGATIVE` exact case, `kind` is one of the eight,
  `arc_shape` is one of the five bare tokens with its evidence sentence in
  `storyline`; the consequence sentence lives in `maturity_effect` and `body`;
  null passes, a sentence never does. RECURRED — the vocabulary lived in two
  places and the second copy missed `arc_shape`; the connector's answer
  decides, and `scripts/check_payload.py` is the only pre-submit check that
  covers `arc_shape`. Pinned by
  `apps/mcp/tests/test_contract_vocabularies.py`
  (`test_prose_in_signal_is_refused_and_named`,
  `test_a_coined_event_kind_is_refused`,
  `test_the_served_arc_shape_is_refused_and_a_declared_one_passes`).
- **(no MEM) / AG-05** — the badge classifies the news instead of the
  assessment — measured on a promoted run (the page pack's table): the merger
  the run's own why-now cited as its **leading** reason to act shipped
  `NEGATIVE`; a forward statute whose caps-log row reads `None (forward
  obligation; informs P3C3)` shipped `NEGATIVE`; the remediated breach shipped
  `NEUTRAL` beside them, so a remediated breach outranked a merger and nothing
  about the news does that — the rule: decide in order — (1) the caps log via
  `get_report_bundle` (`Cap Applied: None (…)` or a retired cap is not
  NEGATIVE, whatever the event is about), (2) the counterfactual, (3)
  capability, not consequence; badge and sentence are one claim
  (POSITIVE↔ADVANCED, NEGATIVE↔CONSTRAINED, NEUTRAL↔NEUTRAL); and an event
  that anchors a why-now trigger is never NEGATIVE — AG-05 reads the sibling
  page's live submission, so whichever of context and overview is submitted
  second is where the verdict lands. Pinned by
  `apps/mcp/tests/test_event_direction.py`
  (`test_the_measured_contradiction_is_caught_from_the_context_side`,
  `test_the_badge_and_the_sentence_are_one_claim`).
- **MEM-0044 / CG-09** — a retained PASS is a dated observation, not current
  state — measured on this exact page: Baxter's context page was submitted
  before the `arc_shape` vocabulary entry landed, its PASS was retained, and
  every later promote carried it forward — live page, recorded PASS, 5 × CG-09
  + 2 × CG-10 against the current gate set — the rule: a page promoted under an
  older gate set has not been checked by today's gates; before re-promoting a
  retained context page, re-run today's validation over it and pay the debt
  deliberately, never assume the stored PASS means clean.
- **(no MEM) / measured (the pack)** — an event drawer that says nothing twice —
  `body`, `maturity_effect` and `capability_ids` were promoted and displayed by
  nothing, which is the whole of a timeline that "has no depth"; a `body` that
  restates its title opens a panel that says nothing twice — the rule: `body`
  is 25–45 words of what changed and what it replaced or enabled; an event
  bearing on no capability (a rebrand, a vendor renewal, a sponsorship) is not
  a digital-evolution event; select on bearing and inflection and state the
  selection basis beside `arc_shape`; fewer than 3 dated events → emit them,
  set `verified_sparse: true`, and never assert an arc from two points (16
  clients shipped two or fewer events — sparse timelines declare themselves).

### Exclusion set

The whole context page is `CUSTOMER_WITHHELD_PAGES` (`apps/api/dma_api/
redaction.py:76`) — withheld from the customer audience whole, served to the
internal audience including the AE role (recorded override, 2026-08-07). Withheld
is not unmarked: mark `r_layer` in `internal_only[]` — it is `NEVER_SERVED` for
every audience, but the strip is the backstop, not the mechanism. Logix marks
`["r_layer"]`; Baxter's promoted `internal_only: []` leaned on the backstop — do
not copy that. Nothing on the event row is an excluded key class: the customer
projection, if this page ever stops being withheld whole, keeps
`events{event_date, title, body, kind, signal, maturity_effect, capability_ids,
claim_label, e_ids}`, `storyline`, `arc_shape`, `verified_sparse` and
`empty_state{reason, closure_condition}` — an invented key drops at serve with
the drop counted (D1, fail-closed). No cap or M-code vocabulary in `body` or
`storyline`: a ceiling is stated as its arithmetic ("held at a 3.0 ceiling for
24 months"), never as a rubric code.

---

## C2 · Issue register &amp; Gantt

### Baxter positive pattern

> "Cap retired. The severity matrix held Information Security at a 3.0 ceiling
> while the incident sat inside its 24-month S2 window; at 54 months elapsed the
> ceiling lapsed and the six linked cells score on their own evidence. All six
> still read 3.0, so lifting the cap moved nothing […] It stays on the register
> as the dated origin of a ceiling a reader would otherwise find unexplained."
> (ISS-001 `rationale` — cap state named in the first two words, arithmetic
> checkable, the argument says something the title does not, and the last
> sentence answers the only question a `None` invites)

> "Cap: none today, and the reason is that the obligation is forward rather
> than a current shortfall. […] It caps nothing because no examination cycle
> has closed; it belongs because the first one will read those cells."
> (ISS-005 — `Cap Applied: None` is a finding, and the commonest one; the
> reason renders in the rationale, the cells stay in `linked_subcap_ids`)

> "UNVERIFIED — a standing pattern in the public review corpus rather than a
> dated incident. Searched the Illinois Attorney General breach register,
> National Credit Union Administration and Consumer Financial Protection Bureau
> enforcement pages, the Consumer Financial Protection Bureau complaint database
> and the entity's own newsroom; none carries an opening date for this matter,
> so none is asserted and the row is listed rather than drawn on the Gantt."
> (ISS-002 `opened_on_basis` — and the substance is repeated in the rationale,
> because the basis field is validated at submit and not persisted; prose is
> the only carrier that reaches the reader)

Shape notes, measured: 4 rows, one per matter; `linked_subcap_ids` populated on
every row (6 · 6 · 5 · 4 cells, each checked against the run's scored cells
before sending); `capped_subcap_ids: []` where the workbook's Issue Time Map
reads `Cap Applied: None` — all five workbook rows on this run — and every
rationale opens on the cap state; `status` is the register's own words
(`REMEDIATED`, `NEW OBLIGATION`, `ACTIVE`), never normalised; `resolved_on`
null where the event has not happened; enrichment took four one-citation rows
to two-to-five citations each, and the added ids are what let the rationales
argue rather than assert.

### Anti-patterns

- **MEM-0001 / CG-13** — item-grain contract keys with no column are validated
  at submit and dropped at promotion — measured: 18 keys across 9 serving
  tables, `context_issue_register` among them; every gate passed and the
  surfaces rendered empty under a real client's name — the rule:
  `capped_subcap_ids` **does** persist now (migration
  `0027_promotion_field_gaps`, JSONB, writer bound — the page pack said the
  opposite until 2026-08-18; the writer spec outranks any cached doc), but a
  per-item field the contract does not persist (`opened_on_basis`,
  `sources_searched` on an issue row) passes the gate and vanishes — send it
  *and* repeat the substance in `rationale`. RECURRED — pinned by
  `apps/mcp/tests/test_field_census.py`.
- **MEM-0002 / CONTRACT_FIELD_DISCARDED_AT_PROMOTION** — the columns 0027 added
  were still null on the served run — measured: `capped_subcap_ids` present on
  0 of 4 served issues while the writers were unbound or the run pre-dated the
  columns — the rule: a migration that appears to close this class does not
  close it; after submitting, read the **served** section body back and verify
  the caps landed; staging rows are retained, so one page re-promotes without
  re-synthesising five.
- **MEM-0049 / WRITE_PATH_WITH_NO_READ_PATH** — the bundle's `issues` array has
  a reader, a schema and no writer anywhere — measured: `issue_register_raw` is
  0 rows corpus-wide with 0 insert sites, so the empty array
  `get_report_bundle` hands you is indistinguishable from a package that
  carried nothing — the rule: the register is authored from the workbook's
  **Issue Time Map** and **Severity Cap Impact** report sections plus
  enrichment, never concluded absent from `bundle.issues == []`; "no matters
  found" is only ever a finding after the registries are searched and named.
- **(no MEM) / measured (the pack)** — issues not linked to the DMA — measured
  on a real run: 4 of 5 issues carried no capability linkage, so every
  drilldown opened onto nothing, and the panel printed "This matter names no
  capability cell" whenever no LEVEL was stated — which, with every row
  shipping an empty linkage list, was every row — the rule: two lists, two
  claims — `capped_subcap_ids` (a ceiling, with a `cap_level`, or it is not a
  cap) and `linked_subcap_ids` (bears-on, which every cap also joins); never
  leave a field null where the absence is the answer — a matter that caps
  nothing opens its rationale on `Cap: none` and argues it; a matter that
  bears on no cell is mis-scoped or unlinked, and the rationale says which.
- **(no MEM) / 9-antipatterns §7** — a field the renderer cannot read —
  measured: `capped_subcap_ids: [{...}]` read as a list of ids rendered
  `[object Object]`, three times — the rule: write each cap as
  `{subcap_id, cap_level}`, the shape the serving layer reads, and look at the
  rendered page; no contract gate can see a legal-but-unread shape.
- **(no MEM) / measured (the pack)** — a banner filtering for a status the
  register never uses — measured: the banner filtered for `OPEN` while the
  register's own words were `ACTIVE`, `NEW OBLIGATION` and `REMEDIATED`, so it
  showed nothing above a grid full of markers — the rule: `status` is the
  source's own word, verbatim, never null, never normalised to a vocabulary
  the source does not use; one matter never ships as many rows
  (`issue_dedup.collapse_issue_rows` — register key, exact title, prefix
  containment); do not compose a rationale for a bare row — across the corpus,
  228 of 236 bare register rows had genuinely nothing behind them, and
  title-only is honest.
- **MEM-0017 / REVIEWER_REJECTED_INSIGHT** — a reasoning trace that asserts
  what it never tested — the reviewer rejected IC-2 with "the counter-case is
  asserted rather than tested", and the same shape is measured on Logix's
  served C2: the r_layer probe states "The third matter's rationale is left
  empty deliberately" while served IR-003 carries a 60-word rationale — the
  trace describes a payload that is not the one beside it — the rule: every
  probe in `r_layer` states what was run against the payload being submitted,
  and a counter-case is tested against the served rows, not narrated.
  **PERMANENT — never retire** (raised_by_kind REVIEWER); test: MISSING —
  corpus entry open.
- **(no MEM) / measured (Logix, both payloads in hand)** — one document, two
  directions, one card apart — Logix IR-001 caps `P3C3.1.1` and `P3C3.6.1` at
  M3, live, citing E-CC-187/188/199, while C1's testimony event names the same
  two cells `POSITIVE` / "ADVANCED — …raises their ceiling" from the same
  three ids; the pack's rung 1 says a live cap on the named cells is not
  POSITIVE — no gate sees a C1↔C2 disagreement (AG-05 pairs the timeline with
  the why-now only) — the rule: before badging any event, check whether a
  register row caps the cells it names; the caps log outranks your reading of
  the document both ways.

### Exclusion set

Page withheld whole for the customer audience; mark `r_layer` regardless.
`capped_subcap_ids[].cap_level` is an **excluded key class** (`cap_keys` in
`packages/shared/serve_classes.json`): the M-code vocabulary is pinned out of
the customer body even though this page is withheld whole today — measured
escape: `cap_level='M3'` on Logix's served register. Keep M-codes inside
`capped_subcap_ids` and state ceilings in `rationale` as score arithmetic, never
as rubric codes. Per-item `provenance` is method vocabulary (excluded class) —
internal only. `opened_on_basis` and any `sources_searched` on a row are the
probe record: validate-only or stripped (`probe_keys`), so the search that
established a date absence is repeated in `rationale`, the one prose carrier
that reaches a reader. The customer projection keeps `issues{issue_id, title,
severity, status, opened_on, resolved_on, rationale, linked_subcap_ids,
capped_subcap_ids, e_ids}` (minus excluded classes) and `empty_state{reason,
closure_condition}`.

---

## C3 · Regulatory standing

### Baxter positive pattern

> `primary_regulator: "National Credit Union Administration (share insurance);
> Illinois Department of Financial and Professional Regulation (state
> charter)"` — charter type sets the second regulator: a state-chartered credit
> union answers to both, and both are on the card, each with its role named.

> `license_type: "federally insured, state-chartered credit union"` — as the
> registry words it, which is what makes the two-regulator claim checkable;
> `jurisdictions` closes with "United States (employer-endorsed membership
> reaches all fifty states)", the shape the overview footprint reconciles
> against.

> "No enforcement action exists against BCU on any searched register: the
> National Credit Union Administration orders index and the institution's own
> record both return nothing, and the one remediated 2021 breach in the issue
> register carried no order." (`empty_state.reason` — with four named rungs in
> `absence_of_enforcement.sources_searched` and a `closure_condition` naming
> what would change it)

> "The absence is a verified finding with its search stated, not an
> assumption." (`narrative_thread` — and the r_layer counter records the
> ladder's own bound: the state regulator's enforcement channel was not among
> the four sources searched, so the absence is verified against federal and
> self-published sources only — the verification states its limits instead of
> overclaiming)

Shape notes, measured: `enforcement_actions: []` with the absence verified, not
assumed; `charter_date` from the registry; the Illinois CRA appears here as
jurisdictional fact, on C2 as a NEW OBLIGATION row, and on O3 as a dated
why-now signal — all three carrying the same February 2025 effective date.
Logix carries the other honest shape: charter verified **by number, not by
name** (charter 1999 → legal name, type, status, state), and the bureau placed
in `additional_regulators` with its perimeter arithmetic stated ("supervisory
authority attaches on crossing $10 billion; the institution reported $9.688
billion") — a future supervisor is not a current one.

### Anti-patterns

- **(no MEM) / measured (the pack)** — a regulator stated and then nothing —
  measured prose length on a real run: **21 words for the whole card** — the
  rule: the analysis is what the actions cap and what a verified absence
  supports; a standing card that names a regulator and stops has not been
  analysed.
- **(no MEM) / measured (the pack)** — a view-evidence control hardcoded to an
  id belonging to no run — the drawer answered "no evidence in this tier" on a
  card whose chip was a control — the rule: every `e_id` on this card resolves
  for THIS run; an unresolvable id is a dead control, not a cosmetic issue.
- **MEM-0020 / ET (foreign)** — every cited id resolved foreign to another
  entity — measured: 35 of 35 probed ids on one run belonged to a different
  entity (the E-0NN namespace collides per-package) and nothing on the run
  could be cited — the rule: `get_evidence` returns `found / not_found /
  foreign` and **foreign halts production**; regulator identity is verified by
  charter number / CIK / RSSD, never by name — a same-named institution's
  action attributed here is the identity error this card quarantines for.
- **MEM-0011 / PROVENANCE_NAMES_THE_TOOL** — evidence citing the tool that
  found it instead of the document — measured: 19 rows carrying 12 distinct
  source_names and exactly 1 URL, a prospecting tool's landing page — the
  rule: `primary_regulator`, `license_type` and every enforcement action cite
  the regulator's **own registry or order page**, never an aggregator, a
  marketing page, or the tool that surfaced them; a URL carrying many names is
  a tool, not a document.
- **MEM-0074 / UNRECOGNISED_INPUT_READS_AS_EMPTY** — a bot-gated registry read
  as a clean record — measured: the regulator's site returned HTTP 403 served
  by Cloudflare while the entity's own site fetched fine; the undifferentiated
  "url_unreachable" made a bot filter look like an absence — the rule: **a 403
  must never become a verified absence.** A refused registry is a rung naming
  its refusal and its status code; `absence_of_enforcement.verified: true`
  requires the registries actually searched, and a rung that did not complete
  is recorded as exactly that (Logix's acquisitions ladder does this: "errored
  on this run and returned nothing, so it is recorded as a rung that did not
  complete rather than as a rung that found nothing").
- **MEM-0038 / CG-15** — an absence exemption bought with a template — measured:
  517 of 517 uncited cells carried one constant two-rung ladder naming no host,
  no query, no date and no result; 98 of 98 alerts shared 1 distinct ladder —
  the rule: every rung of `sources_searched` names its own source and outcome
  ("NCUA administrative orders index, searched by name: no action recorded");
  on a multi-brand entity the sweep runs under **every** name and says so — a
  verified absence that names one of seven brands is not a verified absence.
- **(no MEM) / 9-antipatterns §4 (CG-27)** — an abbreviation on a client
  surface — measured: 48 occurrences of `NCUA` reached promoted prose — the
  rule: spell regulator names out in every label and prose field (both
  reference payloads write "National Credit Union Administration" in full);
  the exception is a verbatim span — never edit a quote to expand an
  abbreviation inside it.

### Exclusion set

Page withheld whole for the customer audience; mark `r_layer`.
`absence_of_enforcement.sources_searched` and `empty_state.sources_searched`
are probe ladders (`probe_keys` class — `sources_searched`, `queries_run`,
`searched_on` strip for the customer body); `empty_state.reason` and
`closure_condition` stay client-facing per the 2026-08-14 owner adjudication —
a producer's real reason renders, a probe never does. `jurisdictions` is read
across the page boundary: the overview firmographics footprint renders from
`regulatory_standing.jurisdictions` (the AE-role adjudication in
`apps/api/dma_api/redaction.py:80-88` exists partly because that fetch 403'd),
so a footprint disagreement is a contradiction to resolve or quarantine, never
variation to average. Enforcement rows keep `{issue_id, regulator, kind,
opened_on, status, summary, remediation_status, e_id}` in the customer
projection — `capped_subcap_ids` on an action carries the cap class rules from
C2.

---

## C4 · Sentiment overview

### Baxter positive pattern

> "95,033 ratings at 4.87 is the largest and highest-rated app in the named
> cohort, and the release cadence behind it is current to April 2026. The
> member-facing channel is an asset, not a gap: it supports P2C1.1.1 at its
> assessed level rather than capping it." (a customer-tile `note` — ends by
> naming the cell and states support rather than a cap, because nothing on
> this run's sentiment caps a cell and the notes say so instead of forcing one)

> "Eighty-eight per cent of employees call this a great place to work against
> 57% at a typical U.S.-based company […] The publisher states the percentage
> and not the response count, so the row carries no sample size." (the
> employee tile's rated line — a reachable employer-side source found after
> the three obvious sites refused, with the limit disclosed in the note
> rather than the row dropped)

> "Glassdoor — HTTP 403 to automated retrieval; a source that cannot be fetched
> cannot be cited" (a `sources_searched` rung — every rung names its own
> refusal with the status code; the ladder is what makes an absence a finding)

> "Reconciliation — every row here appears in overview.sentiment.bars by e_id
> and by rating […] No figure exists on this page that is not on O9." and
> "the 4.57 quoted in the market-tile notes reproduces exactly from the four
> served peer ratings (4.56, 4.64, 4.58, 2.99)." (r_layer probes — C4 is a
> re-projection of O9, and the median arithmetic is checked, not asserted)

Shape notes, measured: three tiles, `customer │ employee │ market`, all
emitted; every rendered number carries `rating`, `scale`, `n` (or a disclosed
null with the reason in the note) and `as_of`; the WalletHub row (2.4 on 356
reviews) was **withheld** because its source refuses the verifier's fetch — a
low reading that cannot carry a resolving chip is recorded in the ladder, not
rendered; the bureau letter grade (E-CC-052) and the CFPB hit count (E-CC-053)
stay out of the tiles — no scale, no sample, no bar; four peer app ratings are
cited as the cohort, each note saying it is context for P2C1.1.1, not a cap.

### Anti-patterns

- **(no MEM) / CONTRACT_FIELD_DISCARDED_AT_PROMOTION (MEM-0001's class),
  measured (the pack)** — a fixture rendered as a finding — before this
  section had a column, whatever a producer submitted for C4 was discarded at
  promotion and the card rendered a hardcoded prototype fixture under a real
  client's name — Glassdoor 3.8 (n=412), App Store 3.4 (n=8,200), a CFPB index
  of 24, none of them the client's, with chips opening a drawer that said the
  id does not resolve — the rule: an unbound field is not a soft failure;
  verify the served body carries your rows and your e_ids, and every chip
  resolves for this run.
- **MEM-0071 / enrichment register** — two components disagreeing about one
  dataset, and the one that renders is wrong — measured: `enrichment_status`
  counted a key (`employee`) no sentiment section has ever had, serving
  `count=0, thin=true` over 7 rated bars that SG-S8 had passed on the same
  submission — the rule: C4 re-projects `overview.sentiment.bars`; produce O9
  first, then project by `e_id` and `rating` — a figure here that is not on O9
  is a forgotten bar or a second, unreconciled measurement, both defects; a
  badge that contradicts the payload is reported with `report_recurrence`,
  never silently re-enriched around.
- **(no MEM) / 9-antipatterns §7** — a field the renderer cannot read —
  measured: `"scale": 5` parsed only as the string `"0..5"` drew five grey
  rails over five real ratings; Logix's served C4 row carries the numeric
  `"scale": 5` while Baxter's carries `"1-5 stars"` — the rule: write the
  shape the renderer already reads, and look at the rendered page; a second
  legal shape needs someone to teach the reader about it.
- **(no MEM) / SG-S8, measured (Logix)** — a missing tile read as nobody
  looked — Logix served 1 tile of 3, and what renders for an absent audience
  is "EMPLOYEE · Not established for this run", which a client reads as an
  unsearched audience — the rule: emit all three tiles; an empty one ships
  `rows: []` with a ladder in which every rung names its own refusal — the
  blocked sites (Glassdoor, Indeed, ZipRecruiter all 403) are where the search
  starts, not stops: Great Place To Work, Comparably, Built In and the
  institution's own culture pages are reachable and have been registered on a
  live run. Do not synthesise a second audience to fill the grid, and do not
  promote an unrated row into a tile — SG-S8 counts rated rows itself, never
  a declared count, discloses at one line and still promotes; thinness is
  disclosed, never hidden and never padded. Pinned by
  `apps/mcp/tests/test_sentiment_gate.py`
  (`test_c4_tiles_are_counted_the_same_way`,
  `test_the_count_is_computed_not_read_from_the_payload`).
- **MEM-0089 / UNRECOGNISED_INPUT_READS_AS_EMPTY** — the entity's own domain
  refuses the verifier — measured on Logix: 11 of 26 uncitable rows were on
  logixbanking.com, connector 403 / direct fetch 200 — the rule: a
  self-published figure (the 96% would-recommend on the entity's own site)
  whose only source refuses the verifier is a ladder rung, not an `e_id`; a
  bureau grade is not a rating (no scale, no sample — ladder or note, never a
  tile number).

### Exclusion set

Page withheld whole for the customer audience; mark `r_layer`.
`sources_searched` on a tile (the employee ladder) is a probe ladder — the
`probe_keys` class strips it from any customer body; `empty_state.reason` and
`closure_condition` stay. The ratings themselves are owned by
`overview.sentiment.bars` — O9 serves them to the customer audience under its
own rules, so a number this page carries that O9 does not is also an audience
leak in waiting, not just a reconciliation defect. Tile rows keep `{source,
rating, scale, n, as_of, url, e_id, note}` in the projection; no `tier`, `ers`
or `recency_band` on a row — recency is expressed through `as_of` and the
18/36-month reading rules, not through method vocabulary.

---

## C5 · Acquisition history

### Baxter positive pattern

> "The announcement of 1 June 2026 gives the institution a dated planning
> window and a concrete business case for integration work already on its
> roadmap; no close date is published, so no closed_on is stated. Nothing has
> converted, so the three affected cells score what they scored before it."
> (`effect_note` on the one row — status `ANNOUNCED`, `closed_on: null`,
> `maturity_effect: NEUTRAL`, and the forward cost argued in prose)

> "The row was first written as a negative maturity effect, on the reading
> that a conversion through the weakest layer is a constraint. It is not one
> yet: status is ANNOUNCED, no close date is published and no system has
> moved […] TEMPORARILY_CONSTRAINED is the honest value once a cutover is in
> flight and it would be wrong to assert it now, before one is scheduled."
> (r_layer counter — the first draft's error caught and argued, which is what
> a counter is for)

> "Scale honesty — scale_metrics is null; searched the served payloads for a
> target-size figure and none exists, so none is quoted." (r_layer probe — a
> null that is a recorded search, not an oversight)

Shape notes, measured: one row, dated to the day from the announcement; the
same transaction carries the same date and the same direction on C1 (M&A,
NEUTRAL) and is WN-1's claim on O3 — the AG-05 triangle closed by
construction; `affected_subcap_ids` resolve to served surfaces. Logix carries
the honest empty shape: `rows: []` with a six-rung `empty_state` whose
decisive rung is the **regulator's** (a federal credit union cannot merge
without an NCUA record; charter 1999 continuously active since 1937), the five
audited financial statements read for business-combination notes, and an
errored enrichment recorded as "a rung that did not complete rather than as a
rung that found nothing" — organic growth stated as a strategic posture, not
left as blank space.

### Anti-patterns

- **(no MEM) / AG-05 + CG-09, measured (the pack)** — a maturity effect in the
  wrong vocabulary and the wrong direction — measured on a promoted run: the
  row shipped `maturity_effect: "negative"`, a lowercase word from the
  timeline's `signal` vocabulary rather than one of this field's four, on the
  same transaction the why-now was naming as the reason to act — the rule:
  `ADVANCED │ CONSTRAINED │ NEUTRAL │ TEMPORARILY_CONSTRAINED`, exact; the
  same transaction carries the same direction on C1 and O3; `ANNOUNCED` with
  no close date has moved no system, so the honest value is `NEUTRAL` with
  the forward cost in `effect_note` — asserting `TEMPORARILY_CONSTRAINED`
  before a cutover is scheduled dates a constraint that has not started,
  and smoothing a live cutover to `NEUTRAL` is the same error mirrored.
  CG-09 now derives this field's four words from the contract doc itself, so
  a lowercase or borrowed word is refused at submit. Pinned by
  `apps/mcp/tests/test_event_direction.py` and
  `apps/mcp/tests/test_contract_vocabularies.py`
  (`test_arc_shape_is_policed_without_being_hand_added` — the
  derived-vocabulary path that covers every doc-declared vocabulary).
- **MEM-0060 / CG-17** — `required: true` satisfied by `[]`, and the surface
  vanishes with nothing to explain it — measured: an empty required list
  passed every gate (`if val is None`), wrote zero rows, and the section
  served with no items key and no empty_state — the rule: an empty `rows`
  ships **with a declared `empty_state`** naming the rungs searched (Logix's
  six-rung ladder is the exemplar), or it does not ship; the honest route
  must stay open, so never invent a transaction to avoid the empty state.
  **PERMANENT — never retire** (raised_by_kind USER); test:
  `apps/mcp/tests/test_required_list_not_silently_empty.py`.
- **(no MEM) / measured (the pack)** — an inline fixture on the card — until
  recently this card rendered two invented credit unions with an
  `evidence: []` that was never shown; it reads from the payload now — the
  rule: an honest empty state and a visibly thin row both beat what they
  replaced, and neither is a reason to compose a transaction or assert a
  status you cannot date (an announced deal rendered as closed, a branch
  purchase described as a whole-institution acquisition, and an integration
  called complete while the timeline shows cutover activity are the standing
  probes).
- **(no MEM) / measured (the pack)** — a serial acquirer flattened into equal
  rows — ten transactions in five years is not ten rows of equal weight — the
  rule: rank by integration consequence on a named cell, group the rest, put
  the volume in `scale_metrics` (the acquirer's own terms: branches, deposits,
  members, FTE), and say that is what you did; a cross-charter approval notice
  is the best-evidenced row on the card and is about this entity's
  transaction — cite it here, hand it to C1 and O3 with the same date, and
  never let it set C3's `primary_regulator`.

Firmographic card notes: the card-level firmographics rulebook entry lives in
the **overview rulebook, under O2** (per D2) — read it there; what this page
owes it is reconciliation, not authorship. `regulatory_standing.jurisdictions`
feeds the footprint O2 renders; a registry record cited for the entity's shape
(Baxter's E-CC-006, charter 68187; Logix's E-CC-200, charter 1999) supports no
capability cell and **says so** in a cited-but-unlinked disclosure rather than
being forced onto one; and the asset series C5's organic-growth reading is
checked against belongs to `overview.financial_series` (C6) on one metric
definition — this page never re-measures it.

### Exclusion set

Page withheld whole for the customer audience; mark `r_layer`.
`empty_state.searched_on` is a probe key (`probe_keys` class) and strips from
any customer body — Logix's served empty_state carries it; `empty_state.reason`
and `closure_condition` stay, and the reason must be the producer-authored kind
that renders ("grown organically, verified against the regulator's charter
record"), never a workflow status word (9-antipatterns §9). Rows keep
`{closed_on, target_name, kind, status, scale_metrics, integration_target,
affected_subcap_ids, maturity_effect, effect_note, e_ids}` in the customer
projection — no `tier`, `ers`, `provenance` or `discovered_by` on a row, and
no M-code vocabulary in `effect_note`.
