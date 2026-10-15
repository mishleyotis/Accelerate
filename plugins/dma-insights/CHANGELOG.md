# dma-insights — plugin changelog

## Unreleased

- **First promotions read incomplete: no peers, two platforms, stale pages**
  (`docs/AAA-WCNY-FIRST-PROMOTION-2026-10-15.md`). AAA Western and Central
  New York promoted with every peer median null, 2 opportunity tiles and 4
  of 6 recommended platforms unranked. Three causes, each hidden on a rerun
  by the previous promotion:
  - **The cohort could not see assessed peers** (`apps/mcp/dma_mcp/cohort.py`):
    it read promoted runs only and matched `sub_vertical = 'IB'` literally,
    so six scored brokerages ("Insurance Brokers", "Insurance Brokerages
    (IB)", NULL; all unpromoted) were invisible and IB read 2 against a
    floor of 3. One run per entity now — promoted first, else the latest
    scored — sub-vertical resolved through the alias table (NULL inferred
    from one sub-vertical's variant cells), withdrawn runs excluded.
  - **The evidence floor was judged on arbitrary cells**
    (`packages/shared/platform_fit.py`): with every gap tied, the five
    "driving" cells were the alphabetically-first unevidenced ones (the
    neutral prior outranks a T3/T4 citation), so six of eight candidates
    read strength 0.0. `judged_cells` orders by claim, then evidence; the fit
    score does not move.
  - **Pages staged before what they read**: a deferred techstack now ships
    FIRST on version B (`pipeline._stage_pages_b`), and promote refuses
    **CG-ORDER** — "register not promoted / page not yet shipped / rows not
    yet registered" text, and a heatmap evidence index missing ids other
    pages cite.
- **A locked peer set the owner ruled out had no path but withdrawal**
  (`engine/prelim.py`): at AAA Western and Central New York (2026-10-14) the
  PRELIM conductor locked five other AAA clubs and the owner ruled "No AAA
  clubs at all"; `widen-peers` only adds and `lock_peer_set` refuses any
  different set. `engine.prelim replace-peers` swaps the set wholesale under
  `widen-peers`' guards — only while no Peer_Median, quartile or Peer_Scores
  is written against it, only with the owner, reason and selection rule
  recorded (Provenance and a non-blocking `PEER_SET_REPLACED` Gate_Log row).
  The locked basis token stays; every grid row's `Peer_Basis` carries the
  new rule, and every `Tech_Peer_Deployments` row about a peer outside the
  new set is retired (counted in the Gate_Log row), so the platform page
  never argues from a ruled-out peer. Re-asserting the locked set only
  prunes such rows. Tests: `test_replace_peers_2026_10_14.py`.
- **AAA Western and Central New York: 13 of 16 categories failed round 1
  on 75 cells; seven root causes now refused at the write**
  (`docs/AAA-WCNY-ROOT-CAUSES-2026-10-14.md`). Owner, 2026-10-14: "look into
  why the categories seem to be failing … enforcing solutions that would
  ensure these never recur."
  - **The evidence engine searched for a domain that does not exist**
    (`apps/evidence-engine/evidence_engine/tools.py`): `lstrip("www.")`
    stripped the characters, so `westerncentralnyaaa.com` became
    `esterncentralnyaaa.com` — every `site:` probe missed and the club's own
    pages stopped matching as its own. Prefix-only now; any domain starting
    with w was exposed. Needs the evidence service redeployed.
  - **A declared absence the gate fails as boilerplate is refused by
    `declare_absence`** (13 cells): the writer composes `What_We_Found` from
    `--hunted` and now runs the gate's own predicates over it.
  - **The orchestrator sheet's absence command matches the ledger**
    (`workflows/dma-pillar-research.js`): it carried `--validation-question`
    without `--inferable` (11 refusals of the sheet's own line) and told
    evidenced cells to route a bounding negative through `absence` (22
    refusals). A test scans every prompt surface for half the pair.
  - **No synthesis over an owed volley nobody fired** (`ledger.append_synthesis`):
    the gate blocks `volleys_incomplete` and the challenger fails
    `facet_coverage`, so 10 cells paid two challenges for one search; the
    write now names the gap for the pre-challenge repair wave.
  - **A CEILING_ESTIMATE carries its ± `Uncertainty`**, the challenge packet
    shows it and the challenger reads it (P2C3.6.4 failed for a range it
    could not see).
  - **The register refuses test/staging hosts and dates a page once**
    (`ledger.append_evidence`): a `test.` site's "$15 gift card" and one URL
    banded CURRENT and UNVERIFIED both failed challenges.
  - **In-session agents briefed from a file under the run root are booked**
    (`cost.capture_workflows`): 41 agents, $28.04, had named the root, not
    the run id.
  Tests: `test_aaa_wcny_root_causes_2026_10_14.py`,
  `apps/evidence-engine/tests/test_entity_domains_2026_10_14.py`.

## 1.27.1 — 2026-10-12 — a research share always funds a whole round, and the Interac run reaches promotion

Owner, R-INTERAC-20261010: "I see workflows failing and being restarted.
Please diagnose and fix the above to ensure this never recurs."

Twelve of sixteen category workflows returned `AT_STAGE_BUDGET` or handed
back cells nothing could close, with the envelope $49.77 from its ceiling.
Eleven defects — three in the driver↔governor budget handshake, two in how
concurrent agents and successive handoffs name their files, three in how a
gate term reaches an agent able to close it, two rules a challenger kept
having to state that the engine could check at the write, and one contract
rule HANDOFF enforced that the write never did:

- **The share** (`engine/pipeline.py`): with the envelope funding the scope,
  shares were `remaining × cells / total` — blind to the ~$1.40 orchestrator
  and challenge every category pays whatever its size. P3C2/P3C4 got $0.81,
  P1C3 $1.22, P4C1 $1.49 against a $1.74 first wave: refused in
  milliseconds, no agent run. A share is now never below one whole round at
  the governor's own `tier_usd` (`_round_floor_usd`: every first-wave batch
  + orchestrator + challenge), plus a cells-proportional part of any
  surplus; when the floors do not all fit, whole categories are allocated
  cheapest first (the existing deferral), never undersized shares.
- **The spend order** (`workflows/dma-pillar-research.js`): only wave 1 held
  the orchestrator-and-challenge reserve, so the gap wave and round 2 spent
  it on collectors — P1C3, P3C1, P3C2, P4C4 ended "syntheses written,
  challenge not affordable", repair evidence bought and never synthesised.
  Every wave now holds the reserve; a synthesis is written only when its
  challenge is funded; an unfunded gap wave is skipped and the category goes
  to its challenge with what it has.
- **The verdict**: a round-2 wave that did not fit replaced the round-1 gate
  verdict (FAIL with its cells) with a bare `AT_STAGE_BUDGET`; it now hands
  back the verdict.
- **The ops files**: the prompts said "ONE ops file" without naming it, and
  sixteen workflows share one session — P4C1's challenger re-ran a file
  P1C3's had overwritten in the scratchpad and recorded P1C3's verdicts
  again. Every collector, orchestrator and challenge prompt now names its own
  `OPS DIR` under `<run>/07_qa/ops/`, unique per category, role, pass and
  batch (the round-1 gap pass is tagged `1g`, so it no longer shares a tag
  with round 2) and deterministic, so a resume still replays from cache.
- **The unclosable cell** (`engine/floors_gate.py`): a declared absence a
  repair wave later attached evidence to is no longer a declared absence and
  has no synthesis author, so `record_challenge` refuses it — yet the gate
  reported it `challenge_missing` and handed it back every round (P1C1: five
  cells; P4C1.4.3). It is now the blocking term `absence_superseded`, and
  the orchestrator's prompt names those cells as its own: a synthesis from
  the attached rows closes them.
- **The term nobody was told about**: `absence_single_tool` was the commonest
  blocking term on the run and the collector's repair lines never named it;
  with the evidence engine timing out under sixteen workflows, collectors
  fell straight to WebSearch — which is not an enrichment tool — so every
  repair wave re-failed (P3C2.2.CIB1: 27 searches over three rounds, all
  `web_search`). The repair lines now route every term in
  `floors_gate.BLOCKING_TERMS` (hoisted to a module constant, test-asserted
  against the prompt), `absence_single_tool` through searxng / the engine /
  edgar, and an engine error or timeout falls to searxng, not WebSearch.
- **Stale challenge packets**: every handoff restarts its rounds at r1, so
  `briefs/wf_challenge_<CAT>_r1` kept packets from earlier handoffs that
  judge text no longer there; the challenge step now clears it first and
  works only the packets it just built.
- **The ceiling nobody was shown** (`engine/brief.py`, `engine/ledger.py`):
  five challenge FAILs on `ceiling_reasoning`, a round each — a 5.0 ceiling
  on one source identity (P3C2.2.CIB1, twice), 3.0 on T4/T5 rows
  (P1C2.6.2), bands contradicting the stated number. `assessment.ceiling_for`
  already computed the number `score` refuses above; the writer never saw
  it. `brief reuse` now prints `evidence_ceiling` {value, band_max, why} per
  cell, the orchestrator prompt concludes at it, and the ledger refuses a
  `Ceiling_Band` above the evidence's band at the write.
- **The citation nobody could take back** (`engine/ledger.py`,
  `engine/cli.py`): when the rows a repair wave attached to a declared
  absence answer another question (P4C2: an ad brand-lift study on a
  BI-inventory cell, fraud ML on a content-generation cell), the orchestrator
  rightly writes no synthesis — and with no write that removes a citation,
  `absence_superseded` could never close (four cells). `attach --detach
  --why` (`ledger.detach_evidence`) takes the row back from a declared
  absence only — never from a synthesised cell — both directions of the
  link, a Provenance 'detach' row; the absence then stands. The orchestrator
  prompt detaches instead of reporting a gap no one can close.
- **The facet answered with no search behind it** (`engine/ledger.py`):
  P2C1 failed 12 of 15 cells on `facet_coverage` — the evidence engine
  timed out, no contradicts volley was logged, and the syntheses answered
  `DQ_Contradicts` anyway. A `DQ_<facet>` stating a finding now needs a
  Search_Log row on that cell for that facet, else `NOT_RUN: <why>`; the
  ledger refuses it at the write and the orchestrator prompt says so.
  The challenge packet's `facets_answered` no longer counts a `NOT_RUN` /
  `NO_FINDING` field (it told challengers a volley fired that the record
  says did not); those facets ride in `facets_not_run`.

- **The URL rule 5 asked for at HANDOFF, never at the write**
  (`engine/ledger.py`): with all sixteen categories passed and $219.61 of
  RESEARCH spent, HANDOFF refused the workbook — 19 cells cited evidence with
  no URL in `Source_URLs`. 46 internal rows carried the local `01_intake/`
  path (38 bare, 8 `file://`) though `intake_manifest.json` holds each
  document's Drive URL, 5 carried none, and one Clay reading (E-031) was
  registered with no URL. Now an intake path is verified verbatim against the
  landed document and recorded as the manifest's source of record; a local
  path with none, and a connector reading with no URL, are refused at the
  write. `engine.cli rehome-intake` re-points a register written before the
  rule (a row moves only when exactly one landed document quotes its span)
  and `engine.cli cite-record` gives a URL-less connector reading the record
  it reports on — both Provenance-logged. Tests:
  `test_intake_source_of_record_2026_10_11.py`.

- **A re-strike kept its old ending** (`engine/assessment.py`,
  `workflows/dma-pillar-scoring.js`): the rescore prompt said to put the
  critic's reason "at the head of the existing rationale", so 7 of the 8 P3
  rows the critic moved still concluded "final 3 (Competing)" or "final 2.5"
  beside a struck 2.0–2.5, and named M4 as the gap from M2. The critic passed
  the scores and could not move text. `rubric_problems` now refuses a
  rationale whose last "final N" is not the score struck, and the rescore
  prompt rewrites the rationale: the struck level argued, the level
  immediately above as the gap, arithmetic that lands on the score.
  The same rescore argued "ADJ_STALE -0.3" on three rows (P2C1.8.3,
  P3C3.1.1, P4C3.2.2) whose Caps_Applied read "none applied"; an `ADJ_`
  label the rationale applies with a delta is now written to Caps_Applied
  ("ADJ_STALE -0.3 (stated in the rationale)") when `--adj`/`--caps` did not
  already name it — a hand-struck score may state its adjustment in prose,
  so the write records it rather than refusing. A label named only as not
  owed is not an application.

- **SCORING was never priced** (`engine/pipeline.py`, `engine/cost.py`,
  `workflows/dma-pillar-scoring.js`): the stage cost $87.52 against a $25
  envelope — 11 scorers $67.82 ($0.095 a row), 8 critic rounds $15.87, 4
  rescores $1.52, solutions $0.73. The handoff printed "est $None", handed
  every pillar the whole envelope as its `remaining`, and the workflow logged
  the envelope and checked nothing. `cost.SCORING_TIER_USD` holds the
  measured prices; `_scoring_price` prices each pillar from its briefs' rows,
  refuses before dispatch when a binding envelope cannot fund the stage
  (naming the `--stage-budget SCORING=` that would), and hands each pillar
  its share; the workflow prices every scorer (its first critic round held
  in reserve), critic and rescore before starting it, and reports rather
  than enforces an envelope the owner made non-binding. Tests:
  `test_scoring_budget_2026_10_12.py` (the real workflow under node at
  shares from $0 to $40, `scoring_governor_harness.mjs`).

- **A one-peer set nobody could widen** (`engine/prelim.py`): REPORTS
  refused client_research §4 ("fails below three; the engagement owner
  widens the set") while `lock_peer_set` refused any different set, so no
  command existed for the owner's decision. `engine.prelim widen-peers`
  adds peers to the locked set only — every locked peer stays — only while
  no Peer_Median, quartile or Peer_Scores is written against it, and only
  with the owner, reason and selection rule recorded (Provenance and a
  non-blocking `PEER_SET_WIDENED` Gate_Log row). Tests:
  `test_widen_peers_2026_10_12.py`.

- **Report probes ran and could not be logged** (`engine/pipeline.py`): the
  REPORTS probe round checkpointed each category's search window but not
  RELAY's, which the probe lanes' connector searches log under and which
  RESEARCH had left at 955 against 60. All 56 probe searches ran, every
  `engine.cli search` was refused, and the writers saw peer absences with
  no search behind them. The probe round now opens a fresh RELAY window
  too. Test: `test_widen_peers_2026_10_12.py`.

- **Connector readings landed as package evidence** (`apps/worker`,
  `engine/assemble.py`): the ingest hardcoded `origin='package'` and never
  read the workbook's `Origin`, so every Clay/Vibe technographic reading
  reached the server with no tool and ET-12 ("the register cites no machine
  technographic scan") could never pass for an engine-produced run — the
  "worker fix in flight" of 2026-10-09 had not landed. Both readers now carry
  `origin` and the retrieval time (read when stated, never reported missing),
  `evidence_index.json` exports them, a connector row lands as `connector`
  with its tool, and a re-scan corrects a row an earlier ingest landed as
  `package`. Every other origin is unchanged. Needs a worker deploy.
  Tests: `apps/worker/tests/test_connector_origin_lands_2026_10_12.py`.
- **SG-V4 labels counted as prose** (`engine/pipeline.py`): `publisher` and
  `source_domain` join the verbatim leaves the driver's budget skips (9 of the
  Interac heatmap's 20 counted FAILs).

- **A version-A page could stop the whole run** (`engine/pipeline.py`):
  techstack failed ET-07/ET-12 against evidence the server ingested before
  the workbook's repairs (links attached later, connector provenance the
  worker dropped), and a page halted on version A stopped every later stage.
  `--defer-to-b PAGE` (an owner decision, logged as a non-blocking
  `PAGES_DEFERRED_TO_B` Gate_Log row and remembered on resume) moves it:
  PAGES_A no longer owes it and PAGES_B produces it against version B.

- **A report re-tripped GS-RPT-NOTOKENS on its own gate table**
  (`engine/gold_standard.py`, `engine/reports.py`): the finding quoted the
  leftover tokens with their braces, the report's gate table rendered every
  Gate_Log row ever written, and the client research report then failed the
  token check on an old gate message, not on any template residue — the
  package refused at PACKAGE. The finding names tokens without braces, and
  the gate table renders the latest verdict per gate and scope.

- **PAGES_B stopped before any page could state an identity citation**
  (`engine/page_preflight.py`, `engine/pipeline.py`): the preflight treated
  every unlinked row a report section cites (annual reports, roster, company
  overview — 35 on Interac) as an overview-page halt, and offered "attach it
  to a cell" — the misattribution ET-07 exists to stop. Report-section
  citations are now advisory, like timeline ones: the page producer states
  them on the surface (`r_layer.probes_run`, the connector's own exception).
  A page deferred to version B also ships LAST, and its refusal no longer
  stops overview, insights, platform and context from shipping first.

- **One cited intake document passed for seven** (`engine/intake.py`): HANDOFF
  checked only that SOME internal evidence existed, so the largest intake
  document — a 133 KB proposal deck — had no evidence row and no record of
  being read (most of it was slides reused from another client's proposal,
  which would have been foreign evidence). Every landed document is now cited
  or declared read with the reason (`engine.intake declare-read`, recorded in
  the manifest with who and when); HANDOFF names the silent ones.

Tests: `tests/skills/research_engine/test_research_budget_floor_2026_10_11.py`
— the driver's shares swept across envelope sizes, and the real workflow
source run under node (`research_governor_harness.mjs`) at every share from
$0 to $7: a category either runs no agent or its last collector is followed
by a synthesis and a challenge, and never spends past its share.

## 1.27.0 — 2026-10-12 — find the registrant, for every sub-vertical in the US and Canada

Owner: "The tool is supposed to be find registrant as we deal with 9
subverticals in US and Canada."

- **`find_registrant` replaces EDGAR's SEC-only company search.** The old
  lookup answered for public companies only — IMA Financial Group, a private
  broker, came back with nothing. The evidence engine now routes by
  sub-vertical (CU, RB, CL, CIB, AM, RIA/WM, IC, IB, FC) and country to the
  registry that holds the institution, all free and keyless:
  NCUA (charter, type, assets, members, field of membership, HQ, CEO),
  FDIC BankFind (certificate, primary regulator, assets), SEC Investment
  Adviser Public Disclosure and FINRA BrokerCheck (CRD, SEC number), the
  Farm Credit Administration directory (UNINUM), OSFI (Canadian federally
  regulated institutions) and SEC EDGAR (any public or Form D parent, CIK).
  NAIC/state insurance departments and Canadian provincial and securities
  regulators publish no registry API; they are searched on their own hosts
  and come back as `candidates`, never as records. Every registry asked
  reports ok, no_match, candidates, error or not_run, and `ambiguous` when
  two records tie.
- **Measured live** (2026-10-12): IMA Financial Group, Inc. → EDGAR CIK
  1673769 (the SEC-only search had returned 0); Navy Federal → NCUA charter
  5536, Vienna VA, $204.4B, 15.5M members; First Technology → NCUA 23521,
  San Jose CA; Glacier Bank → FDIC 30788; Edelman Financial Engines →
  IAPD/BrokerCheck CRD 104510; Edward Jones → CRD 250; Horizon Farm Credit →
  FCA 720345; Manufacturers Life → OSFI. Three defects found and fixed on the
  way: sector words alone made matches ("Colonial Farm Credit" read as
  "Horizon Farm Credit"), EDGAR answered HTTP 500 to a comma, and NCUA's
  search misses a name carrying "Federal Credit Union".
- The tool's description says which gold columns a record fills
  (Firmographics Regulator, identifier, charter type, HQ, status, assets,
  members — stated, never held; the record URL as a T1 Source_URL read
  through `engine.cli fetch`) and that the identifier is the ET identity
  anchor. Research agents are told to identify the registrant first.
- **A per-class brief records the rungs it searched.** Verified live after
  the 1.26.0 deploy: `find_customer_review_evidence` reported
  `ladder_searched: ["news"]` (inferred from SearXNG answering) while it had
  probed only review-site hosts, so an absence's Negative_Ladder would have
  cited a search that never ran. Every `site:<rung>` probe now counts as its
  rung, and a per-class brief takes its rungs from its probes alone.

## 1.26.0 — 2026-10-11 — research tools named for what they find, split by source class

Owner: "For each of the MCP tools, avoid generic names, split by
functionality to ensure thorough results, as per gold standard
requirements. Ensure clear description of tools", and "Apart from evidence
tiers, check the gold standard scoring workbook columns eg excerpts, URLs,
dates etc."

- **A tool surface for the four research services.** Agents no longer see
  `research_brief`, `fetch` or `get_company_facts`. `scripts/evidence_proxy.py`
  serves `evidence`, `searxng`, `fetch` and `edgar` through
  `references/research_tool_surface.json` (`scripts/research_tool_surface.py`):
  39 tools, each with a specific name, a description that names the source
  class, the tier it earns and the gold-workbook columns its output fills,
  and preset arguments the agent cannot override. Calls are mapped back to
  the upstream tool; an upstream tool the surface does not name (EDGAR's
  insider-trading reads) is not exposed. The snapshot stays the upstream
  listing; upstream names still pass through for a session bound earlier.
- **Split by source class, so quiet classes are searched in their own
  right.** `find_evidence_all_sources` stays the batched first call; the
  cells it leaves unanswered are chased with `find_regulator_evidence`,
  `find_trade_press_evidence`, `find_news_wire_evidence`,
  `find_job_posting_evidence`, `find_customer_review_evidence`,
  `find_academic_evidence`, `find_contradicting_evidence` and
  `find_corroborating_evidence`; the entity's own site has
  `read_entity_newsroom` / `_careers` / `_investor_pages` / `_about_pages`.
  The engine gained `research_brief(source_classes=[…])`: `site:` probes over
  the source registry's hosts for the class (the sub-vertical's pack first,
  rotated across a batch's questions; `site:gov` for regulators) and only
  hits that classify into it are kept, counted in `search.class_filtered`.
- **Measured live before shipping** (local pinned SearXNG + Parallel, IMA
  Financial Group, P1C1.1–P1C1.2's 16 cells and twelve class-matched
  questions). Two defects were found and fixed in the same change: a
  regulator-class brief carded **15 T1 spans from BDC filings that list the
  entity as a borrower** — the page named the entity, the span was about the
  fund — so a per-class card must now name the entity in its own excerpt
  and an `ambiguous` match is dropped (`search.off_entity_dropped`); and
  quoting the legal name with its `, Inc.` suffix starved job-board and
  review-site probes, so per-class probes use the plain name and lead with a
  bare `site:<host> "<name>"`. After the fixes, on class-matched questions
  the review tool returned 2 App Store cards where the all-sources call
  returned none of that class; the trade-press tool 11 cards covering all
  15 cells from the two insurance trade titles the all-sources call also
  reached; the regulator tool an honest 0 for a private broker. Limits: `site:` probes rely on Google CSE, DuckDuckGo and
  Brave (Bing and Parallel ignore the operator), so a rested Google CSE
  thins the class tools; Indeed and LinkedIn pages are found but refused by
  robots.txt and are probed last — Indeed postings come through the Indeed
  connector.
- **Gold columns in every description.** A card tool says which
  Evidence_Detail column each field fills — Source_Name, Source_URL, Tier
  (registry, never typed; own domain never T1), Date_Published (a date the
  page states, never the retrieval date), Claim_Type, SubCap_IDs, Excerpt
  (verbatim 50–500, sentence-complete) — and what the ledger computes (E_ID,
  ERS, Recency, Retrieved_At, Access_Status, the scoring row's Evidence_IDs
  and Source_URLs). A search tool says a snippet is never an Excerpt; an
  EDGAR tool says how a filing becomes a T1 row.
- **The page-read guard now fires on the plugin's own readers.** They were
  listed in `deny_whole_page_fetch.FETCHERS` but missing from the hook's
  matcher; the matcher now carries every reader and searcher it lists.
- Grants, the challenge slice (`find_contradicting_evidence`,
  `find_corroborating_evidence`), `search_order` (every find_* brief
  counts), the rate gate, source health, auto-approve, the workflow, relay,
  agent bodies and docs read the new names; `docs/EVIDENCE-ENGINE-TOOLS.md`
  carries the generated surface table.

## 1.25.0 — 2026-10-11 — the research connectors bind, stay bound, and answer under load

Owner: "Confirm connector reachability especially the open source ones …
Fix accessibility issues so these connectors bind always in case sessions
restart and at the beginning", then, from a live round: "The open-source
evidence engine timed out twice at 60 seconds in P3C4, with 16 workflows
hitting it at once."

- **Parallel and alphaXiv were silently unbound.** Both are also claude.ai
  connectors at the same URL; when the account attaches them Claude Code
  suppresses the plugin's server ("Suppressing plugin MCP server …
  duplicates a claude.ai connector") and the tools bind as
  `mcp__Parallel_Search__*` / `mcp__alphaXiv__*` — names no manifest held,
  so every research agent ran without Parallel (the IMA session bound 4 of
  6). The registry now grants both spellings (`SHADOWED_BY_CLAUDE_AI` in
  `scripts/provision_agent_tools.py`), alphaXiv contributes its three read
  tools, and the rate gate, source health, page-read guard, auto-approve,
  relay, `agent_run` and the doctor all read the alias. Tests pin every copy.
- **A cold start no longer costs a session its tools.** The CLI gives a
  server 30 s to answer `initialize` and never asks twice; the research
  services run at min-instances 0 and the proxy could spend a 60 s token
  mint plus 3×120 s upstream, or answer an empty tool list "until the next
  initialize" that never came. `evidence_proxy.py` now answers within
  `DMA_RESEARCH_INIT_BUDGET_S` (20 s), lists the last-known tools (runtime
  cache, else `references/research_layer_tools.json`), recovers in the
  background and sends `notifications/tools/list_changed`; a call made while
  warming waits for the service. Proved end to end against a 25 s cold stub.
- **Searches run at the sources' rate, not 1/s.** The engine's fan-out
  waited on the per-WEBSITE politeness bucket (1/s, burst 1) keyed by the
  source name, and the configured source buckets (SearXNG 4/s, Parallel
  1.4/s) were never acquired. Load harness (`apps/evidence-engine/eval/load.py`,
  the 686-cell IMA volley through the real Engine, simulated sources): the
  old wiring dropped 2,744 of its queries at the budget and ran 48 Parallel
  calls; the fixed wiring dropped 11 and ran 1,036, answering all 346 of an
  instance's questions in 14.4 min (5x scale; 11–15 min projected for the
  whole run on two instances), 0 errors.
- **Sixteen workflows share one queue, in the proxy.** Every agent in a
  session shares one proxy process, which handled one message at a time.
  Calls now run concurrently; heavy calls (`research_brief`, `crawl_entity`,
  `filings_evidence`) pass an admission gate (`DMA_RESEARCH_ADMIT`, 12 —
  both engine instances busy, each brief inside Cloud Run's 300 s) and the
  rest wait locally where no server clock runs; light calls never wait
  behind them. A Cloud Run 429/503 (instances full or cold) is retried, not
  handed to the collector as an outage; a waiting call sends progress when
  the client gave a token. `.mcp.json` gives evidence a 30-minute per-server
  `timeout` (it overrides the environment's `MCP_TOOL_TIMEOUT=60000`, which
  had cut briefs that then finished server-side: IMA P1C1 probe, 31 cards
  stored, 0 returned) and the raw fallbacks 180 s. The availability marker
  follows each call's transport outcome, so `search_order.py` lifts
  brief-first when the engine dies mid-session and restores it after.
- **The engine bounds its own search phase.** `EE_SEARCH_PHASE_BUDGET_S`
  (120 s, a guard inside Cloud Run's 300 s): queries still queued for a
  source token are cut and counted (`search.budget_cut`); started calls are
  never cancelled (coalesced joiners from other briefs ride on them).
- **Collectors queue every brief at once.** One message fires every
  capability's `research_brief` of the batch; one optional message of
  fallbacks; then one write turn per capability (was: search, write, search,
  write — each later brief joined the back of a sixteen-category queue).
- **A small category gets at least one full wave.** Shares were split by
  cells alone, so a two-cell category got $0.38 against a $1.84 floor (one
  batch + orchestrator + challenge) and closed AT_STAGE_BUDGET with money
  left. Each invocation is now floored at its fixed costs and the rest is
  split by cells; the shares still partition the envelope.

## 1.24.0 — 2026-10-11 — the six connectors, batched and ordered

Owner: "There were 6 connectors mentioned … Ensure all are mapped to the
agents and well orchestrated. The goal is to avoid calling web search
severally and batch queries to the open source connectors first … getting
back the tool results in schemas … that align with gold standard scoring
workbook requirements."

- **Mapped**: `research-evidence-collector` and `technographic-scanner` now
  hold the raw research fallbacks (`searxng`, `fetch`, `edgar`, `parallel`)
  beside the engine; `alphaxiv` is mapped to the research tier (collector,
  conductor, web specialist) and contributes tools the day its listing is
  captured (OAuth per user). Per-page producers unchanged (2026-09-14).
- **Batched**: `research_brief` takes `questions[]` as objects
  `{question, subcap_ids, facet}` — one search pass and one fetch slice for a
  whole capability, cards ranked PER QUESTION and returned with
  `item.linked_subcap_ids` = the caller's cells (echoed, never invented) and
  `by_question[]` naming what nothing answered; `max_cards`/`token_budget`
  per question; a per-call query budget (`query.per_question_budget`). The
  card is the gold evidence row: `engine.cli evidence-brief --cell
  CELL=QUESTION …` prints one search line per question and one evidence line
  per card, `--subcap` filled from the cells the engine echoed.
- **Ordered**: the research workflow's collector prompt and the collector's
  manifest put ONE batched `research_brief` per capability first, the raw
  layer next, Exa/Tavily after, WebSearch last; `hooks/search_order.py`
  (PreToolUse on WebSearch/Exa/Tavily search; PostToolUse counter) refuses a
  research actor's general search before its first brief and past three per
  brief while `evidence_proxy.py`'s availability marker
  (`/root/.dma/research_layer/evidence.json`) says the engine is up; it steps
  aside when the engine is down or answered an error. FAILS OPEN.
- **Contract**: `connector_contract` family `evidence` logs as
  `evidence_engine` (`contract.SEARCH_TOOL_OF_FAMILY`).
- **Deploy gate** (`infra/evidence-engine`): governs on question coverage
  recomputed from the results file (owner, same day: "Fix the above to
  ensure deploy happens"); same-URL recall reported beside it; the static
  egress NAT is opt-in (`EE_STATIC_EGRESS=1`); CI makes the identities'
  logging binding itself (the deployer holds projectIamAdmin).

## 1.23.0 — 2026-10-10 — the research layer

- **Evidence engine** (`apps/evidence-engine`, Cloud Run `dmai-evidence`,
  plugin server `evidence`, six tools): `research_brief` returns
  register-ready cards (verbatim sentence-complete span verified against the
  page, registry tier hint, licensed claim label, page-stated ISO date, origin
  cluster with syndication count, entity match, recency band) plus a coverage
  block with the saturation stop rule and flagged-never-resolved conflict
  candidates; `crawl_entity`, `filings_evidence` (edgartools in-process),
  `expand_context`, `verify_cards`, `coverage_report`. Contract and the diff
  from the brief's baseline: `apps/evidence-engine/docs/CARD-CONTRACT.md`.
- **Five connectors** declared in `.mcp.json`: `searxng`, `fetch`, `edgar`
  (self-hosted via Supergateway on secret paths; `infra/evidence-engine`),
  `parallel` and `alphaxiv` (vendor, `type: http`). Access through
  `scripts/evidence_proxy.py` + `evidence_auth_headers.sh` — siblings of the
  connector's proxy and helper, which are untouched.
- **Grants** by role (`scripts/provision_agent_tools.py`): engine on the
  research/servicing tier; verify slice on the verifiers and assemblers;
  raw fallbacks on the servicing tier only; per-page producers unchanged
  (owner decision 2026-09-14 stands; recorded in docs/CONNECTORS.md).
- **Hooks**: `rate_gate.py` (PreToolUse, raw fallbacks, fail open) and
  `source_health.py` (PostToolUse, all six); the whole-page-fetch guard lists
  the raw readers.
- **Doctor**: six `research layer:` rows (`scripts/research_layer.py`);
  WARNING for a raw fallback, BLOCKER for the engine only without a search
  fallback.
- **Docs**: `docs/EVIDENCE-ENGINE-TOOLS.md` (generated), CONNECTORS.md
  research-layer section, RESEARCH-PROTOCOL § Tools rung 3, the production
  evidence doctrine, `enrichment_sources.json` search connectors +
  `_free_chain`.
- **Measured** (`apps/evidence-engine/docs/EVAL-REPORT.md`, golden v1 from the
  repo's own corpus, Logix held out): excerpt fidelity 100 %, URL liveness
  100 %, boilerplate 0, syndication inflation 0, token reduction 82.6 % on
  re-found pages; source recall 37.1 % after the two tuning iterations the
  brief allows (fetchability-bound: WAF 403s and one client's own site; one
  free discovery source) — escalated, not tuned further. `tests/` in the
  engine: 302 offline tests; no client string in engine code (CI grep).
- **Not deployed**: every resource-creating step waits on
  `apps/evidence-engine/docs/DEPLOY-PLAN.md` approval.
