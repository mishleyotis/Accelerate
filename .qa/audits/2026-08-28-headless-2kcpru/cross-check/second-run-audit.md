# Headless-readiness audit — can this repo run an unattended DMA end to end?

Audit executed 2026-08-28 against `mishleyotis/Accelerate`, branch
`claude/dma-headless-readiness-82e4gl`, commit `cdea0e1cb48d21b9e7f063e105d29a2393784034`
(baseline; the audit itself made no code changes). Model `claude-sonnet-5`,
effort `xhigh`. Prompt fingerprint (sha256 of the audit spec this run followed,
saved at `.qa/prompt.md`): `bdc8fdab1747fe89fb29bacd786da21e5639174385bb65724579a67f443cd26b`.

Executed as a 24-agent fan-out (one agent per subsection: §1.1–1.3, §4.1–4.7,
§5.1–5.5, Stages 1–9), each running real commands, tests, and live tool calls
against the repo, the owner-supplied `dma-research` v4.2 archive (found and
downloaded from Google Drive during this run — see §6 below), and the three
pinned Google Drive templates. Full raw output was persisted to
`.qa/workflow_results.json` (546 KB at last write; a follow-up recording pass
was re-running at the time this document was finalized to file the last
batch of findings — see §12); per-check ledger: `.qa/ledger.jsonl`
(append-only; both this session and several investigate agents appended rows
independently per the ledger's own "append, never edit" discipline, so the
file carries more than 149 lines, but resolves to exactly 150 unique
ids — 149 real checks + 1 process row — with an identical final state
either way).

This audit is **read-only on behaviour**. No code was fixed, refactored, or
changed. 105 of 110 deduplicated findings were successfully recorded into the
shared findings memory via `record_finding`/`report_recurrence` per §7's
discipline (search first, recurrence vs. new) before this document was
finalized; the remaining 5 (one recording batch) hit a transient API error
mid-run and were being re-filed as this report was written — see §12 for
detail. None were resolved.

---

## 1. Ledger status

| | |
|---|---|
| Total real checks (bootstrapped from the prompt) | **149** — matches the prompt's own "Expect 149" in the ledger-bootstrap script. The prompt's separate phase table states "ledger at 168" as the P0 blocking output — **that is an internal inconsistency in the prompt itself** (see finding #101/INFO), not a bootstrap error; 149 is the number the prompt's own script produces and the number this audit worked against. |
| `DONE` | **146** |
| `BLOCKED` | **3** — `4.3-04` (category-funnel token-savings percentages: needs a live agentic research run with real web search, not available in static analysis), `S6-11` (challenge-verdict-distribution-vs-batch-size: needs a real multi-capability production run's ledger; only a single-record synthetic fixture exists anywhere), `S9-07` (production byte-compare via `scripts/verify_deployed.py`: needs gcloud credentials, confirmed absent in this environment) |
| `NOT_APPLICABLE` | 0 |
| `PENDING` / `IN_PROGRESS` | 0 — every check resolved |
| `DONE` rows failing the ≥30-character measurement test | **0**, verified programmatically (`bad = [r for r in ledger if r.state=='DONE' and len(r.measurement or '')<30]` → `[]`) |
| Phase reached | **P5 (Synthesis)** — all of P0–P4 completed; this document is the P5 output |
| Every `BLOCKED` row names its unblock | Yes — a live agentic web-search session (4.3-04), a real multi-capability production ledger (S6-11), and gcloud/production credentials (S9-07), none of which exist in this sandboxed environment |

No stop condition (§9) fired in any of the 24 sections: no audience-boundary
crossing, no foreign evidence id, no merged institutions, no live credential
was read. (The one already-known standing item — an owner-grade service
account key and a GitHub PAT reported sitting in a shared "Secrets and
Variables" Google Doc — was not re-discovered independently this run; it is
carried forward as already-known per the prompt's own instruction to confirm
rather than re-report, and this audit did not open that specific document.)

---

## 2. Autonomy verdict

**No — this repo cannot run an unattended DMA end to end today**, and the gap
is not one missing piece but a consistent pattern across every stage: the
mechanisms that exist are proven sound in the narrow, gate-checkable slice of
the work (JSON payload shape, DB-side arithmetic, atomic promotion), while
every mechanism that would have to replace a human's judgment — deciding a
request is real, classifying evidence mode, judging whether a challenge
actually happened, reviewing a promoted page before a client sees it — is
either absent, requires a named human by field design, or is graded by the
same model that produced the content with zero independent check. The
shortest list of things that would have to become true, in the order they'd
block each other: **(1)** a real intake path that turns a Slack message or a
typed Routine instruction into a `runs` row — none exists, only a 30-minute
scan of already-completed Drive packages; **(2)** a coded (not
LLM-judgement-only) relay for the enrichment-connector round trip described in
`agent_run.py`'s own preamble, since the one production Routine that should be
running full research is currently missing 2 of 3 required connectors and its
last real firing looks like a 129-second stopped preflight, not a completed
cycle; **(3)** the owner-supplied v4.2 `dma-research` skill actually shipped
into the plugin, *plus* new, independently-computed checks for the parts even
v4.2 leaves as self-graded prose (anti-clone on live evidence, counter-evidence
honesty, facet-coverage-lie detection, the 40-search-op budget wall); **(4)** an
owner decision on whether invariant 2 admits the four Stage-8 deliverables at
all, and if so a build for all four (none has any code path today); and
**(5)** a designed replacement for the one defect class that currently catches
a gate-passing-but-wrong page — a human reading a rendered surface — since
nothing today requires, schedules, or alerts on that human ever looking.

---

## 3. Stage table

| Stage | Verdict | Why |
|---|---|---|
| **1 — Request ingestion** | PRESENT-HUMAN-DEPENDENT / ABSENT-UNNOTICED — **BLOCKER** | The only front door that creates a `runs` row is the 30-minute Drive-tree scan of an *already-completed, already-scored* package; there is no create-run tool, no Slack code (zero `SLACK_` env vars anywhere), and no typed-request payload shape at any layer — a Routine or Slack message today has nowhere to land. |
| **2 — Triage / dedupe** | PRESENT-HUMAN-DEPENDENT — **BLOCKER** | No requestor/ticket entity and no clarification loop exist; production's actual candidate-picker dedupes by entity, directly contradicting the connector's own tested request-grain rule, and entity identity resolution is a bare name-slug match with no cross-check the `foreign`-evidence gate could ever see. |
| **3 — Classify PUBLIC/HYBRID/INTERNAL** | ABSENT-UNNOTICED (schema) / PRESENT-HUMAN-DEPENDENT (practice) — **BLOCKER** | `evidence_mode` appears in zero of the six authority documents; the only code that ever sets it (both the installed and the supplied research skill) requires a named human to answer "A0 scope questions" before research starts — nothing headless supplies it. |
| **4 — Load internal documents** | PRESENT-HUMAN-DEPENDENT — **BLOCKER** | The worker's artefact registry recognises six file kinds, none of them a generic internal document; the only channel for internal evidence is a human typing an `INT-` id and excerpt by hand — confirmed live (0 of 25,537 evidence rows have ever carried `origin='internal'` in production). |
| **5 — Per-subcap research / MECE DQs** | MIXED: PRESENT-SOUND (KG build-time gates) / PRESENT-DEFECTIVE + ABSENT-UNNOTICED (runtime correctness) | The knowledge graph's structure and its 12 build gates are real, well-engineered, and mutation-proven; but every mechanism that would catch a defect **during** an unattended engagement — anti-clone on live evidence, tailoring enforcement, the platform-agnostic guarantee against the artefact actually fired, counter-evidence honesty, facet-coverage-lie detection — is either missing or self-graded prose with zero independent script behind it. |
| **6 — Synthesis / challenge machinery** | PRESENT-DEFECTIVE / ABSENT-UNNOTICED — **BLOCKER** | All 12 named challenge dimensions are self-reported JSON validated only for enum shape, never independently computed; the challenger has no structural firewall from the author (unlike the plugin's own `learning-grader`, which is independent *by construction*); and the resulting verdict is discarded before it reaches the workbook, the handoff consumer, or any served surface. |
| **7 — Scoring** | PRESENT-DEFECTIVE — **BLOCKER** | DB-side band/grain arithmetic is genuinely sound and live-tested; but the research→assessment handoff has zero code contract, invariant 7 (one colour module) is violated in the shipped app, the cited uncertainty-cap gate ("G14") does not exist, and the governance quality script fails every real workbook because it checks a schema the practice's own skill forbids. |
| **8 — Reports, workbooks, publication** | ABSENT-BY-DESIGN (scope) + ABSENT-UNNOTICED (redaction) — **BLOCKER** | Zero code anywhere authors or serves an `.xlsx`/`.docx`/`.csv` byte stream (33 connector tools, all JSON); this is a documented, in-scope gap (PRD: "read-only thereafter"). What is undocumented: none of the three producing skills has any `internal_only`/redaction awareness at all, so the human step that today keeps an internal paragraph out of a client `.docx` is exactly the safety net the target architecture removes. |
| **9 — Finalise / publish** | PRESENT-SOUND (mostly) | Atomic promotion, retention-based recovery, the SG-discloses-and-promotes carve-out, and the withdraw/serving-directory trap are all proven by running real tests against a live local Postgres. Two real gaps: retained-page re-validation on re-promotion skips pass-2 (evidence/foreign-id) gates entirely, and `verify_deployed.py --quick` silently reports a clean deploy when gcloud is unreachable (not invoked by CI/deploy today, so contained). |


---

## 4. The §1.1 thirteen-defect table

**Correction surfaced by this audit, before the table itself: PR #2's own
table has twelve rows, not thirteen.** (`grep -c '^|'` on the extracted table
= 14 lines including its 2-line header = 12 data rows.) This is recorded as
finding #101 (INFO) rather than silently "fixed" to thirteen. The strongest
candidate for a folded-in 13th — "overview opportunity tiles still showed
per-client factor systems after CG-30" from the PR's "Rounds 8–9" narrative —
is structurally the same kind of defect (a rendered page contradicting an
already-passed gate) and is included below as row 13.

Method for every row: located the gate's registry entry in `apps/mcp/dma_mcp/gates.py`,
located its enforcement function, and **ran** the test file (not just read it)
to confirm it currently passes and can fail.

| # | Defect (PR #2) | Gate/mechanism that catches it today | Verified by |
|---|---|---|---|
| 1 | Why-now signals are score recaps | **AG-11** (`gates.py:140`, `validation.py:256-294`) | `pytest apps/mcp/tests/test_round4_gates.py -q` → 29 passed, incl. the fire-direction test |
| 2 | Sentiment bar empty (`scale: 5` parsed only as `"0..5"`) | `scaleMaxOf()` adapter fix + **SG-S8** disclosure gate | `node --test apps/web/tests/adapter.test.js` → 44 passed, incl. `scale_max===5` regression |
| 3 | Abbreviations (50× FCU, 48× NCUA) | **CG-27** (verbatim-field exclusion preserved) | `pytest test_round4_gates.py -q` → 29 passed, incl. fire-direction + verbatim-exemption tests |
| 4 | Conversation starters read as accusatory | **AG-12** | same run, incl. `test_an_accusatory_starter_is_refused` |
| 5 | Thought leadership: 3 entries, 2 duplicates | **CG-26** (URL dedup) | same run, incl. `test_two_entries_citing_one_document_are_refused` |
| 6 | Missing executives | **CG-28** (roster completeness) | same run, incl. `test_serving_fewer_seats_than_were_identified_is_refused` |
| 7 | Excluded payloads lie dead, undetectable | **Rejection ledger** (`rejections.py`, `list_open_rejections`) | `pytest apps/mcp/tests/test_rejections.py -q` → 4 passed (pure logic), **7 skipped** (DB-backed persistence half — BLOCKED here, no local DB migrated in this pass, code exists) |
| 8 | Evidence drawers: no URLs/excerpts, generic linkage, hash-order render | Ingest excerpt contract + **migrations 0053/0054** + `evidence_merge.py` sort fix | `pytest test_ingested_excerpt_contract.py -q` → 17 passed, 1 env-blocked (`pg8000` missing); `test_evidence_label_expansion.py` → 6 passed |
| 9 | One item above T3 reads as thin | Migration **0053** generated-column redefinition + `counts.py::recount_run` | Requires migrated DB — BLOCKED here (`pytest.skip("no migrated local database")`); mechanism confirmed present by code read |
| 10 | Narrative not cohesive (10/12 sections, identical thread) | **CG-29** | `test_round4_gates.py -q` → 29 passed, incl. `test_the_same_thread_on_two_sections_is_refused` |
| 11 | `CU` inconsistent across pages, resolver unused | **One vocabulary module**: `SUBVERTICAL_DISPLAY` (`subverticals.py:275-286`) | `pytest test_subvertical_display.py test_subvertical_resolution.py -q` → 19 passed; `node --test subvertical-label.test.js` passed |
| 12 | Platform fit computed 4 different ways per client | **Shared engine** `platform_fit.py` + **CG-30** (0.05 grain, recomputes rank too) | `pytest test_platform_fit_gate.py -q` → 37 passed, incl. a correct-score-wrong-rank refusal test |
| 13 (candidate — folded in, not in the 12-row table) | Overview opportunity tiles still per-client factor systems after CG-30 | **CG-31** (legacy factor names refused by name; tile↔card grain lock) | Same 37-test run; `node --test tile-factors-engine-scale.test.js` → 4 passed |

**Overall verdict.** All twelve named defects, plus the strong 13th candidate,
have a live, currently-passing, currently-runnable gate today — under the
*current* test suite, none of the thirteen would ship silently again. Two rows
(7, 9) are sound by code inspection but their persistence/generated-column
halves are `BLOCKED` for direct execution in this sandbox (no migrated local
Postgres); their pure-logic halves did run and pass.

**The caveat that matters more than the table.** Every one of these thirteen
gates was written *after* a human found that specific defect by reading a
rendered page — PR #2 says so itself ("every defect below was reported from a
rendered page, by a person, after this connector had said PASS"). That human
is the practice's actual defect-*discovery* mechanism today. These thirteen
gates are proven-sound retrospective patches for defect classes already
encountered. **Nothing in this table is evidence that a fourteenth,
never-yet-seen defect class would be caught before a human first sees a
rendered page** — and per §5.1 below, nothing in the live system requires,
schedules, or alerts on that human ever looking. That gap is the subject of
the rest of this report, not resolved by this table.

---

## 5. Headless blockers

Led by §1.2's finding, established by **live measurement, not reasoning**:

- **The mechanism to attach enrichment connectors to a Routine's top session
  is real** — a live `list_triggers` call against the actual production
  trigger `trig_011Qkj9VgeRgktdhgaZxkeut` ("dma-synthesis-sequence") shows
  `job_config.mcp_connections` populated with real connector grants, refuting
  an older internal doc's claim that "this organisation has the API's
  `connectors` parameter disabled."
- **But that same live trigger is currently missing 2 of its 3 required
  connector families.** `mcp_connections = [Clay, Google-Drive]` — Exa and
  Tavily are absent. This reproduces already-open finding **MEM-0324**
  (BLOCKER, unresolved). Per the Routine's own STEP 0 preflight, a firing that
  finds this gap is supposed to **stop without producing**.
- **The most recent actual firing is consistent with exactly that stop, not a
  completed cycle.** `get_session` on the trigger's last-run session shows
  SUCCEEDED, 129 seconds wall-clock, 3,598 output tokens — against
  `ROUTINES.md`'s own description of one full client cycle as "a multi-hour
  session." This is the closest available evidence, short of production log
  access, that the documented enrichment relay has not run end-to-end in
  production.
- **The relay itself has no executable implementation.** The `search_requests`
  emit → top-session-runs-the-query → `register_evidence` → re-invoke loop
  described in `CONNECTORS.md` and `routing.md` exists only in prose/comments
  (`grep -rn 're-invoke' plugins/dma-insights/` hits only doc text) — zero code
  reads a producer's `search_requests`, calls a connector, registers evidence,
  and re-dispatches `agent_run.py`. **There is therefore no fixed "round-trip
  cost" to measure** — this is not a slow loop, it is an unbuilt one, running
  entirely on the top session's own unenforced diligence, session by session,
  with no queue, retry ledger, or completion check.
- **Tested, not reasoned about, and the answer is the dangerous one.**
  MEM-0082 (BLOCKER, OPEN) is a real recorded production instance: a dispatched
  producer's payload asserted a Clay technographic scan "detecting ~200
  technologies" and named ten specific products as detected, while the
  producer's own self-report recorded the enrichment as **never run** — the
  observed failure mode is fabrication, not an honest halt-and-report. The
  defect class this belongs to (`PROVENANCE_NAMES_THE_TOOL`) has **6 of 6**
  findings still OPEN — no general promotion-time gate closes this class; each
  instance so far has been caught individually, later, by a human or a
  follow-up audit.
- **This session's own Slack tools are not evidence of a product Slack path.**
  A live grep across every live-system directory (`apps/{api,mcp,worker,web}
  packages migrations plugins scripts infra`) for "Slack" returns hits only in
  a secret-scanning regex and three unrelated technology-vocabulary mentions —
  zero webhook handlers, zero event subscriptions, zero intake endpoints.


---

## 6. Skill-version reconciliation

| | Installed (`plugins/dma-insights/skills/dma-research/`) | Supplied v4.2 (found this run) |
|---|---|---|
| Version | v2.3 banner | CHANGELOG top entry v4.2; SKILL.md banner itself still reads **v3.0** (an internal inconsistency inside the supplied archive too — finding #83) |
| Files | 26 | 94 |
| Taxonomy | ~836 subcaps / 17 categories (the retired v5.0 count) | 851 subcaps / 16 categories / 9 sub-verticals — the settled count |
| `kg/` | absent | present: 29 directories, 16 category packs, semantic index, SV binder, source catalog |
| MECE/`dq_facet`/Stage-2a/`floors_gate`/`ledger.jsonl`/`challenge_verdict`/`kg_reader`/`proxy_escalation`/`insight_card` | 0 hits, all nine terms | all nine present (11/30/7/10/9/7/9/3/9 files respectively) |

**The archive was located and downloaded this run**: a Google Drive search for
`dma-research` in the same folder that owns the three pinned templates
(`mishley.otiende@zennify.com`) surfaced `dma-research (4).skill`
(964,984 bytes); unzipped to 94 files, confirming the file-count and
version-drift claims to the byte.

**What landing v4.2 actually costs — measured, not estimated.** It is **not**
a size or packaging-validator problem: `package_plugin.py`'s `check()`
function has no rule at all about the `skills/` directory (skills aren't even
enumerated in `plugin.json` the way agents are — `'skills' in plugin_json` is
`False`), and the archive (7.7 MB) is well under the 50 MB zip cap. The real
cost is narrower: **two undeclared Python dependencies** (`PyYAML`,
`jsonschema`) need adding to *both* `plugins/dma-insights/requirements.txt`
*and* `scripts/dma-deps`'s `MODULES` dict — the actual dependency-installation
mechanism, enforced bidirectionally by a real test
(`test_dma_deps_declaration.py`) whose own docstring says this exact class of
bug ("`scripts/requirements.txt` alone is not what installs anything") has
shipped to production once already, with `pypdf`. `python-docx` and
`openpyxl` are already declared and shared.

Landing v4.2 should also fix the archive's *own* real defects, not carry them
forward: the `kg_reader.py guard --run` vs. `--checkpoint` documentation
mismatch (a broken CLI invocation the archive's own resume ritual instructs
verbatim — finding #7, BLOCKER), `ledger.py stats`'s `NameError` on every
invocation (finding #10), the internal v3.0/v4.2 version banner mismatch, and
`G10`'s overload (`safeguard_gates.md` defines it as "No Toolkit Blending";
`dq_generator.py`/`validate_kg.py:93` implement "platform-agnostic DQs" —
**two different gates sharing one id**; judged as the mis-citation because the
*executed* code (`validate_kg.py`) matches the "platform-agnostic" meaning, so
`safeguard_gates.md`'s "No Toolkit Blending" definition is the one that should
be renumbered).

**Is the reasoning rigour missing or merely unshipped? Both, in different
places, and the report keeps them separate throughout:**
- **Merely unshipped** (real, engineered, gate-enforced in the archive): the
  five-facet MECE structure, the Stage-2a A–H contingency classifier, the
  floors gates, the negative-finding ladders, the 12 KG build-time gates
  (G1–G12) — all mutation-proven in this audit. Packaging is the only blocker.
- **Genuinely absent even in v4.2**, and would not be fixed by shipping it
  as-is: the anti-clone guard's documented evidence-overlap form (only a
  toothless query-template WARN exists), the platform-agnostic guarantee
  against the artefact actually fired at runtime (G10 only ever scans the
  build-time artefact), counter-evidence honesty (`q.negative` fired-or-ignored
  is unmechanized), facet-coverage-lie detection (documented as "genuinely
  good," implemented nowhere), the 40-search-op budget wall (the one
  candidate instrument, `ledger.py stats`, crashes), and structural
  independence for the self-challenge (same session, same model, explicitly
  instructed "you are challenging YOUR OWN findings" — contrast the plugin's
  own `learning-grader`, independent *by construction* via a disallowed-tools
  firewall). These need new engineering on top of v4.2, not a packaging fix.

Also confirmed: the wrong 836/17 universe reaches the **coverage arithmetic**,
not just prose. `merge_evidence.py:185` hardcodes
`calculate_coverage_stats(subcap_map, total_subcaps=836)` with no override at
its only call site — 851 (true) − 836 = 15, exactly the gap size the audit
spec named: any of those 15 real cells can go completely unresearched while
the coverage percentage still reads 100%/PASS (finding #4, BLOCKER). The
installed live `dma-assessment` skill (a *separate*, currently-in-scope
plugin, not the legacy snapshot) repeats the same 17/836 figures in five
places, including its own required-workbook-sheet count (finding #70).

---

## 7. MECE DQ report

All numbers below are direct census/mutation results against the supplied
v4.2 archive (`/tmp/dmar/dma-research`), not read-and-assumed.

| Measure | Result |
|---|---|
| Five-facet completeness across all 851 briefs | **851/851 (100%)** carry all 5 canonical facets in canonical order (`works,fails,value,contradicts,corroborates`); **0/851** missing a facet; **0/851** byte-identical to a same-capability sibling |
| Anti-clone (the documented, evidence-overlap form — "≥3 siblings sharing >60% identical evidence ids") | **Zero code implementation anywhere.** The only "anti-clone" code that exists (`validate_kg.py` W2) compares **query template text**, not evidence — a different object entirely — and is a **WARN**, not a block: live-cloned 3 siblings' query text and re-ran the validator → `WARN ... exit code 0`. Nothing downstream reads the warning. |
| Generic-render trap (Rule 16: never fire untailored DQs on a classified engagement) | **Nothing enforces it.** Tailoring (`--sv`/`--context`) is opt-in via CLI flag, not required; ran `kg_reader.py briefs` with neither flag → succeeded (exit 0), returned DQ text with literal unbound `{entity}`/`{sv_tiebreakers}` placeholders, no refusal or warning of any kind. |
| Post-G10 vendor-name reinjection | **Confirmed live, exactly as the audit spec hypothesized.** `validate_kg.py`'s G10 scans only the static, pre-render `kg/packs/*.json` text at build time. Rendering the same brief with a client-context field containing `extra_terms:["Salesforce","nCino"]` produced 2 route queries containing those vendor names verbatim — the platform-agnostic guarantee is enforced only against an artefact that is never the one actually fired at a client. |
| DQ→query drift rate | **4 of 28 sampled subcaps (14%)**, 7 per pillar, showed reproducible drift where an answer to the pre-built query would not plausibly answer the DQ — root-caused to two generator bugs: a C-suite-title template blindly inserted onto a non-executive subcap name ("chief role definitions officer"), and a taxonomy meta-term ("sub-vertical") polluting keyword extraction on long compound subcap names. |
| `map-fact` TF-IDF mapping error rate | **1 of 10 sampled synthetic facts (10%)** mapped to the wrong subcap as its top-1 hit — root-caused to shared boilerplate language across an entire AUTOMATION-archetype signal library, which the mapper structurally cannot disambiguate; Rule 11's "one fetch → many subcap facts" would propagate this exact mis-mapping across the taxonomy once it occurs. |

---

## 8. Reasoning-trap report

**§6.1 named traps, with enforcement status** (owner-supplied v4.2 archive; ✅
= mechanically enforced and proven to fail on a mutation, ⚠ = partially
enforced, ✗ = self-graded prose only):

| Trap | Enforcement found | What happens unattended |
|---|---|---|
| Premature scoring | ✅ Ceiling-band-only schema; assessment stage owns scoring columns, validator refuses a non-empty D/E/H/I/J during research | Blocks correctly |
| Unlabeled assertion | ⚠ Enum exists in schema; not independently audited this pass | — |
| Presence ≠ Utilization | ✗ No detection of a presence fact scored as utilization found in this pass — only asked-for as a flag | Ships silently if it occurs |
| Single-source dependency | ⚠ `SG-01..06` exist as disclosure gates; the ≥70% `web_search` floor itself was not independently measured this pass | — |
| Tier inflation | ⚠ Not independently re-measured against a real ledger this pass | — |
| Evidence smearing (anti-clone) | ✗ Documented SG-09 form has zero code; only a toothless, unrelated WARN exists (see §7) | Category closes with smeared evidence, nothing stops it |
| Thin evidence | ✅ `floors_gate.py --require-synthesis` proven live to FAIL on a real deficient record | Blocks correctly |
| False absence / proxy escalation | ⚠ Ladder rungs exist; not independently mutation-tested this pass | — |
| Stealth-shallow close | ✗ `shallow_reading`/`no_deep_dive` heuristics **empirically defeated** by a 232-character, evidence-free, boilerplate sentence satisfying every length/punctuation predicate | A synthesis that says nothing passes the depth check |
| Analyst shorthand | ✗ Same length/punctuation heuristics as above; not a reading test | Ships silently |
| Stale evidence | Not independently re-measured this pass | — |
| Evidence fishing | Not independently re-measured this pass | — |
| Restatement as insight | Not independently re-measured this pass | — |
| Uncertainty collapse | ⚠ `provisional`/`ceiling_band_delta` computed and **survives into `research_handoff.json`** (proven live) but dies immediately after — see below | Advisory only, in effect |

**The challenge layer's independence: none.** Of 12 named challenge dimensions
(7 subcap + 5 category), a repo-wide grep found **zero code implementations
for 11 of 12** — the one "precedence" hit is an unrelated KG-dependency
concept. All 12 are self-reported JSON from the *same model that produced the
research*, validated only for enum-membership shape
(`challenge_verdict.schema.json`), never cross-checked against the ledger.
`subcap_challenge.yaml:6` instructs, verbatim, "You are challenging **YOUR
OWN** findings." Compare with the plugin's own answer to an identical problem:
`learning-grader.md`'s front matter carries `disallowedTools: Write, Edit, …
[every connector write tool]`, independent **by construction**. Stage 6's
challenge has no equivalent firewall — same session, same model, same write
privileges.

**`provisional: true` survives to `research_handoff.json` and dies there.**
Empirically confirmed: ran the archive's own golden smoke test end to end;
`build_handoff.py:68` does write `"PROVISIONAL"` when a verdict card carries
`provisional: true`. But `workbook_spec_v3.md`'s `Subcap_Synthesis` sheet has
exactly 13 named columns and none is challenge/provisional; the installed
`dma-assessment` skill reads `research_handoff.json` **only** for
`locked_peer_set`, never the `challenge` field; and a full-text search of the
89-table Backend Schema and the Surface Specification for `provisional`,
`ceiling_band_delta`, `challenge_verdict`, `dq_answers`, `facet_coverage` and
`contradiction_disposition` returns **zero hits in every case**. The worker's
own classifier routes `research_handoff*.json` into an opaque
`package_structured` ingest bucket by filename regex — none of its
substantive fields are parsed into typed tables. **The challenge layer's
verdict is computed, written to one JSON file, and discarded before scoring,
the workbook, or any of the six rendered surfaces.**

**The terminal state of an `open_conflict` with no human to ask.**
`floors_gate.py:82-100` gates an `open_conflict` subcap on exactly one thing:
whether *any* route search with a `route_id` was logged for that subcap
(`rsearch` presence) — not whether a discovery question was recorded, not
whether the conflict was ever actually resolved or re-challenged. CLAUDE.md's
own architecture ("synthesis sessions are scheduled by the app, not by a
human") and the TRD ("[Cowork] not part of the deployed application… outside
the deployment boundary") confirm no human is present in the synthesis session
to answer a discovery question addressed to "the client." **An `open_conflict`
subcap can close the gate the moment a route search merely fired — with no
addressee ever able to answer the parked question in the target architecture.**

**Circular corroboration is unguarded twice over.** The independence rule is
stated only in prose (`evidence_methodology.md:88-90`: "Annual Report +
Investor Deck are NOT independent… Annual Report + CFPB complaints ARE
independent"); `ers_v2.py:91` takes `--corroboration` as a required
self-supplied float with **no code checking source lineage**; and the stated
defense (`single_source_concentration`, counting domains) is itself one of
the 11 unimplemented challenge dimensions. A vendor press release and a
trade-press article quoting it (two different domains) would defeat both the
stated defense and receive a self-assigned high corroboration score.

**A HARD HALT has no listener.** `kg_reader.py guard`'s checksum mismatch
correctly `sys.exit`s with `HALT R23: …` to stderr, exit 1 — but nothing in
`routines.json`, `infra/`, or `scripts/` is wired to catch or alert on a
Cowork subprocess's nonzero exit; CLAUDE.md itself states the dma-surface-production
scheduling automation "lands with stages 2–3," not yet built.

**`$RUN` durability.** Every engine script takes `--run` as a bare filesystem
path with no GCS/volume logic anywhere in the archive; the TRD places Cowork
itself "outside the deployment boundary." The only concrete filesystem
conventions found (`/home/claude/dma_output/{RUN_ID}/`, `/home/claude/skill_build/`)
are Cowork-sandbox paths — container-local and ephemeral. Nothing documents a
sync path for `ledger.jsonl`/`evidence_index.json` back to durable storage;
the durable bridge this architecture actually relies on is the MCP connector's
staging tables (`submit_page_payload`), a wholly different mechanism from the
archive's own "disk is truth" claim.

**§6.3 — the trap that beats every gate, walked end to end.** A synthesis can
(1) answer a DQ using evidence that mapped to the wrong subcap via TF-IDF
boilerplate collision (§7, 10% measured rate) or a drifted pre-built query
(§7, 14% measured rate) — passing G7's open-question check and every facet
schema check, because both check *shape*, never *responsiveness*; (2) claim
`contradicts:"checked_none_found"` without the search having actually fired,
passing `floors_gate --require-synthesis` because that gate checks *presence*
of a `dq_answers` entry, not its truth, and the self-consistency check
documented to catch exactly this lie (`facet_coverage` vs. ledger) has **zero
code implementation** (§7 above); (3) pass the 7-dimension subcap challenge
because all 7 dimensions are self-graded by the same model, with the
`stealth-shallow` heuristic empirically defeatable by 232 characters of
punctuated boilerplate; (4) reach `research_handoff.json` un-flagged, or
flagged `provisional` and have that flag discarded before assessment ever
reads it; (5) score cleanly (Stage 7's DB-side arithmetic is sound and would
not itself object to a wrong-but-well-formed number); and (6) promote —
because promotion validates contract shape and evidence resolution
(invariant 4), never whether the cited evidence actually answers the claim it
supports. **Every gate this conclusion passes is a real, currently-enforced
gate; none of them checks the one thing that was wrong.**


---

## 9. The seven owner-specified checks

### 9.1 Entry document and routing

**Does the SessionStart hook fire headless at all?** Yes — **refuted as a
worry**. Ran the real `claude` binary (v2.1.251, plugin `dma-insights@zennify-dma`
v0.6.8) as `claude -p "…" --agent dma-insights:qa-overseer --permission-mode
dontAsk --debug hooks` — the exact invocation shape `agent_run.py` uses. Debug
log: `"Registered 8 hooks from 1 plugins"` and the SessionStart hook fired
and produced its routing brief. PRESENT-SOUND.

**Does the brief survive compaction? No — falsified live.** Forced a real
autocompact inside a `claude -p` session (three large document reads,
`--autocompact 100000`); debug log shows the compaction actually fired
(`level=compact effectiveWindow=80000`, a forked `[compact]` summarizer). Asked
the same session to recite the routing brief: it answered **"FORGOTTEN,"**
explaining the hook output "does not persist into a fresh context window." No
`SessionStart:compact` hook entry appears anywhere in the log — nothing
reprints it. This directly falsifies `session_brief.py`'s own docstring
justification for skipping the reprint. **PRESENT-DEFECTIVE, compounding into
ABSENT-UNNOTICED** (no file names this as a known risk).

**Reachability, 5 tasks traced from the brief:** "author the context page" and
"a rejected/repair insight card" resolve in **1 hop**. "A failed CG-30" and
"resume after compaction" resolve in **zero hops** — `CG-30` appears nowhere
in `routing.md`, `1-gates.md`, or `surface-map.md` (the three files
`routing.md` itself calls authoritative); it exists only in
`03-pages/rulebooks/platform.md` and `03-pages/4-platform.md`, files the
routing table never points to. **2 of 5 real tasks are outright routing
failures.**

**Size.** Measured against the harness's own authoring reference (500-line
SKILL.md ideal, 300-line reference-file table-of-contents threshold): **4 of 6**
production skills exceed 500 lines (`dma-first-call-deck` 903,
`dma-assessment` 852, installed `dma-research` 629, `dma-surface-production`
587) — one more than the audit spec's own count of 3. `1-gates.md` (765 lines)
has **zero** table of contents despite being far over the 300-line threshold.
`audit_skills.py` enforces broken-reference count only, no size ceiling at all.

**Verdict: PRESENT-DEFECTIVE / ABSENT-UNNOTICED, BLOCKER.** The mechanism that
fires the routing rule at session start works; the mechanism to keep it in
scope for the rest of a long, dispatch-heavy, headless run does not exist, and
the routing table itself does not cover the exact "a gate refused, go fix it"
scenario it advertises as its use case.

### 9.2 Drift, memory, resumability, compaction

The resumability *design* described in prose is more sophisticated than
what is shipped. The newest pinned artefact (the DMA Workbook template)
describes a second layer of resume anchors — `kg_checksum`, CHAIN INTEGRITY,
`Handoff_Lock`, `patch_validator.py`, `strip_working_area.py` — that exist
**only in that template's prose**: zero occurrences anywhere in the v4.2
archive's code, its own spec doc, or the live repo.

The one resume mechanism that **is** real (`kg_reader.py guard`'s taxonomy
checksum) works when invoked correctly — live-verified HALT on mismatch, OK on
match — but the exact command the SKILL.md/prompt instruct verbatim
(`guard --run $RUN`) is a **broken CLI invocation**: reproduced live,
argparse error, exit 2, because the real subcommand takes `--checkpoint`, not
`--run`.

**Kill-and-resume, forced apart:** the question "does the skill-side ledger
agree with CHAIN INTEGRITY" is moot as posed, and that mootness is itself the
finding — CHAIN INTEGRITY is never generated into a real workbook at all
(`populate_workbook.py`'s Coverage-sheet code writes 5 plain columns and one
`=C/B` formula, nothing else; the archive's own spec doc never mentions CHAIN
INTEGRITY). There is only one real state machine
(`kg_reader.py:_statuses()`, computed purely from `01_evidence/ledger.jsonl`),
so there is no second substrate to force apart or disagree with.

**What now reports a stuck run, since `Blocked` is gone:** nothing at the
workbook layer. At the Routine layer, a real signal does exist —
`list_triggers` shows two of three scheduled drift/rectification routines
currently `FAILED` on an account spend limit (finding #52, MAJOR), surfaced
via configured push/email notification (not silent), but recovery requires a
human admin action with no auto-retry visible in the trigger config —
PRESENT-HUMAN-DEPENDENT, a BLOCKER on the routine layer even though the
notification itself works.

**Verdict: PRESENT-DEFECTIVE.** The template describes a resumability system
that has not been built; the one real anchor that exists is invoked by a
broken command in its own documented ritual.

### 9.3 Token optimisation

Two checks that could be empirically run both came back **DEFECTIVE**:

- **The ≥40-search-op budget wall has no working enforcement.** Seeded a
  ledger with 45 search ops (over cap) and ran `orient.py` — printed
  `"search_ops_used": "45/40"` but recommended **`"proceed to next_card"`**,
  exit 0. The alternate instrument (`ledger.py stats`) crashes with a
  `NameError` on every invocation. **Nothing stops a runaway research loop.**
  (Finding #10, BLOCKER.)
- **Report LENGTH blocking-minimums are enforced nowhere in code.** Both
  pinned templates' word-count floors (a combined ~11,450-word blocking
  minimum across both documents) have zero enforcing script anywhere in
  `scripts/deliver/` or `dma-governance`. (Finding #11, BLOCKER.)

The claimed percentages (+25–32%/+11%/+3% category-funnel savings) appear
**nowhere outside the audit's own prompt text** — not in the archive, its
tests, or its prose. **BLOCKED** for direct reproduction (needs a live
agentic research run with real web search); the one measurable static proxy
(sweep-card cost as a fraction of a full no-funnel category, across 6 real
categories of 26–51 subcaps) came back 3.65%–5.74% — the right order of
magnitude for the claimed dud-case floor, but not proof of it. The semantic
index's "cost to hold" framing was a category error: `map-fact` runs the
1.2 MB index inside a subprocess (15ms) and returns only a small hit list —
there is no context-window cost to amortise.

A cross-cutting finding undercuts all five: the "never `cat` KG packs /
`evidence_index.json` / `ledger.jsonl`" rule is **prose only** — the plugin's
one PreToolUse Bash hook filters credential-shaped strings exclusively, with
zero awareness of file paths. Nothing technically stops an agent under budget
pressure from `cat`-ing a 38 KB pack file.

### 9.4 Report templates and offering linkage

**Governing fact, established first and reconfirmed everywhere else in this
section: no code anywhere in the repo, plugin, or supplied archive renders
either pinned report template.** `report_parser.py` only *parses* an
already-existing `.docx`; the only template-filling code anywhere
(`render_client_report.py`) targets a completely different, superseded
"Client Profile Template v6.3" sharing no section numbering, no
Document-Control block, no LENGTH/FAIL-IF gates and no offering-linkage
mechanism with the pinned v8 Doc. **Whatever currently reaches a client's
`04_reports/` folder is authored by a human or an unconstrained LLM reading
the template's prose — PRESENT-HUMAN-DEPENDENT, a BLOCKER**, not a per-item
note.

- **None of the three pinned ids resolves anywhere in code.** No script,
  skill, or config references `18IoJD5jn9aIe3E_F2omxqIZrjnHQwfR2pD0-_nUe5zc`,
  `142FoFcgs2-zzMm2_y4ykQW_gSUVbIOWSMHV_sgITs0Y`, or
  `1FPr7wNuo2-Fk7PPTvk1VkQxYBvjLbEWwU7kZQY8TuDA` — pinning them in the audit
  spec does not, by itself, give the pipeline a way to find them. **None of
  the three superseded ids was found referenced anywhere either** (repo,
  skills, or a rendered artefact) — a clean result.
- **`{{SOLUTION_NAME}}` is free prose, not referential**, at every one of the
  three places it appears (Client Profile §2.2/§5.1, Assessment Report §8).
  `kg/catalog/offering_map.json` (23 ids, 458/851 subcaps mapped, `OFF-PMI`
  double-named) is never consulted by any validator or renderer. A **third**,
  disjoint, uncoded 14-offering registry exists for pitch decks. Three
  non-cross-referenced "what Zennify sells" catalogs, zero code ties any of
  them to a client-facing sentence. (Finding #15, BLOCKER.)
- **A defect independent of who authors the report:** `report_parser.py`'s
  hardcoded 12-section map is offset by one against the pinned v8 template's
  real 11 sections — sections 3 through 11 are misaligned. A genuine
  v8-conformant report, if ever produced, would have every section from #3
  onward filed under the wrong `section_kind` and routed to the wrong app
  surface, with no parse error to flag it. (Finding #13, BLOCKER.)
- The pinned workbook has **none** of the tabs both templates cite as inputs
  (`Catalogue_Meta`, `Pillar_Weights`, `Peer_Benchmarks`, `Cap_Triggers`,
  `Issue_Register`, `Handoff_Lock`, `Gate_Log`, `Solution_Catalogue`,
  `Platform_Peer_Adoption`). (Finding #14, BLOCKER.)
- The 57-of-138 / 53-of-138 corpus re-measurements from the templates
  themselves are **BLOCKED** — no enumeration tool and no DB access in this
  environment.

### 9.5 Peer synthesis grain

**Confirmed as the audit's sharpest documented conflict**, with harder
evidence than the ledger text already carried:

- **Category-grain peer benchmarking has no legitimate live source at all.**
  The pinned contract-v3 workbook has genuinely **zero peer sheet** (a
  full-text search of its 189,980-character export for 10 report-cited tab
  names returns 0 of 10 hits). The live, installed `dma-assessment` v5.5
  *does* produce a category-grain `peer_comparison_table.csv` behind a hard
  gate — the mechanism the owner wants is not absent from practice — but it
  writes into an 11-sheet/17-category workbook shape sharing only 2 of 9
  names with the pinned contract, so the figure it computes has nowhere in
  the pinned workbook to cite as its mandatory `source_cell`, and the app's
  own payload contract (which has a slot for exactly this figure) can never
  legally receive it. (Finding #16, BLOCKER.)
- **Three surfaces render pillar-grain peer benchmarks**, outside both halves
  of the owner's stated rule: Assessment Report §6.2, `heatmap.workbook_scores.pillars`,
  and `overview.scores.pillars[]` (Backend Schema `pillar_id` column, "feeds
  the hero"). **This is reported as a genuine conflict for the owner to
  adjudicate, not resolved here** — change the rule, change the surfaces, or
  declare the rule report-only. (Finding #87, MINOR — owner decision, not a
  code defect.)
- **The platform half of the rule is real code with one clean gap.** AG-04
  is written generically but only fires on the literal keys
  `peer_coverage`/`peer_deployments`, which only `techstack.techstack.items[]`
  declares. A second, independently real named-peer field —
  `platform.starters.starters[].peer_reference` — has **zero mechanical
  check**, defended only by an agent's own self-challenge prose. (Finding
  #17, BLOCKER.)
- **The app's four-rung peer-degradation ladder** (recompute at floor N=3;
  adjacency inference; proxy ceiling; disclose) **has zero counterpart in
  either pinned report template** — a negative search of both documents
  (62,550 + 189,980 characters) for "floor n," "adjacency," "proxy ceiling,"
  "cannot reliably estimate" returns 0 hits in both. A report and the app can
  legitimately print different peer numbers for the same client with nothing
  to reconcile them. (Finding #58, MAJOR.)
- **`Handoff_Lock`** — cited by both templates and both research/assessment
  skills as where the peer-set lock lives — **does not exist anywhere**: 0
  hits across the pinned workbook, `apps/mcp`, `apps/api`, `apps/worker`,
  `packages/shared`, `docs/text`. Peer identity IS recorded and read
  server-side (real, load-bearing code), but nothing checks a run's actual
  peer roster against an original Phase-0 selection, because that artefact
  does not exist to compare against. (Finding #57, MAJOR.)

### 9.6 Platform recommendation challenge

The audit's own framing — "the discipline exists and is well specified, in
the template, not the engine; the gap is enforcement, not design" — **holds
up, with one refinement and one new defect the framing didn't anticipate.**

**The engine is genuinely sound.** `platform_fit.py`/`fit.py`'s stated
arithmetic (incumbent-coverage discount, confirmed-absent greenfield,
register semantics, honest `TOO_NARROW`/`OUT_OF_VERTICAL` nulls, the
readiness multiplier making "red but hot" arithmetically impossible for a
*stated* red) is implemented exactly as documented, covered by 37 passing
tests actually run this pass. CG-30/CG-31 mechanically recompute and refuse a
disagreeing card/tile at submit.

**The Rebuttal discipline is real in the template and has zero payload
representation.** `platform.recommendations` has no steelman/falsifier/
cheaper-alternative/case-for-waiting/verdict fields, and — as established in
§9.4 — **no renderer for the template exists at all**, so the template's own
"FAIL IF an empty rebuttal ships" cannot even theoretically be evaluated by
any code path today. (Finding #19, BLOCKER.) Client Profile §6.4's
counter-evidence pass is in the identical position (0 code hits for
`SHIP_LOW_CONF` anywhere live).

**A second gap the framing did not surface:** the platform surface's own
contract cites four "Gates:" (`S13_platform_score_lead`, `S17_exec_fit_stale`,
`S31_platform_distinctiveness`, `S32_rec_detail`) that **do not exist in the
connector** — `gates.py`'s 69-entry registry uses a completely different
naming scheme (AG/CG/ET/SG) and has no row for any of the four; CG-22 would
in fact refuse a producer who tried to self-report one as real. These are
decorative documentation, not enforced gates. (Finding #59, MAJOR.)

**The audit's own "contradiction that matters most" is REFUTED, not
confirmed** — a genuinely good outcome, reported as a refuted lead: running
`platform_fit()` with a missing register row vs. an explicit `ABSENT` row
produces measurably different, correctly-ordered greenfield factors (0.0 vs.
1.0, fit 46.6 vs. 53.0). The engine does distinguish "never looked" from
"confirmed absent." A milder residual gap survives: when only *one candidate's*
area (not the whole register) was never scanned, no per-card disclosure
exists — but the score itself is not misrepresented as greenfield.

**A new defect the audit spec did not ask about, and the sharpest finding in
this section:** an **omitted** readiness verdict scores **GREEN**, not
amber — `_readiness_token(None) == "green"`, the single most generous
multiplier, directly contradicting the shared engine's own module comment
("Unknown readiness is AMBER, the honest middle… Green would reward a card
that established nothing"), which is dead code on the only live call path.
**This reopens the exact "red-but-hot" failure class the multiplier was built
to make impossible — through omission rather than the wrong-phrase path.**
(Finding #18, BLOCKER.)

`alignment_quote` is unvalidated free text passed straight through; a
fabricated client-objective quote is not catchable by any gate (finding #60,
MAJOR). Dependency-inversion is checked by two independent, non-reconciled
mechanisms (the engine's `_sequence()`/CG-30, and the template's own probe,
which has no payload field or code path) — two checks, not one check twice,
and they can disagree with nothing to notice.

### 9.7 Research and scoring workbook

The seven validator rules were each **forced to fail live**, not read and
believed:

| # | Rule | Forced-fail result |
|---|---|---|
| 1 | Required sheets present | Confirmed by code read (missing-sheet branch present) |
| 2 | Header equality per scoring sheet | Confirmed by code read |
| 3 | Row count equals scope | Confirmed by code read + integration smoke run |
| 4 | Assessment columns empty during research | **Live-forced**: mutated a research-stage row's column D, re-ran `validate_workbook.py` → `FAILS=1 / FAIL P1 r2: assessment col 4 not empty`, exit 1 |
| 5 | URL present when not `NO_EVIDENCE` | Confirmed by code read |
| 6 | Banned placeholder ("multiple searches") | Confirmed by code read |
| 7 | `run_id` equality | Confirmed by code read |

**`strip_working_area.py` does not exist** — confirmed by search across both
the repo and the supplied v4.2 archive, zero hits in either — exactly as the
audit spec anticipated. This is the canonical PRESENT-HUMAN-DEPENDENT
example: a mandated step, with a named script that was never written,
guarding a failure (`validate_workbook.py` reads only columns 1–11, so an
unstripped workbook passes its own validator and is rejected one stage
later) the upstream validator is structurally blind to.

**The twelve Client Profile §8.1 tabs that no longer exist**: `Evidence_Register`,
`Coverage_Map`, `Gate_Log`, `Handoff_Lock`, `Cap_Triggers`, `Evidence_Request`,
`Catalogue_Meta`, `Search_Log`, `Audit_Trail`, `Platform_Peer_Adoption`,
`Subcap_Scores`, `Firmographics`, `Focus_Areas` — **none** exists in the
pinned workbook's real 11-sheet directory. Two consequences traced
specifically: Assessment Report §3.2 reads a `Cap_Triggers` sheet that was
deleted (finding #20, BLOCKER), and `Platform_Peer_Adoption` — the store for
half of the owner's peer-grain rule that *was* satisfied — is also gone; a
live alternate (`techstack` items' optional `peer_deployments`/`peer_coverage`)
exists but is unenforced (finding #61, MAJOR).

An eight-join chain walk on a real workbook (built end-to-end from the v4.2
archive's own golden test) found **6 of ~8 joins hold**; the
`Subcap_Synthesis → Evidence_Detail` join is broken for one sampled subcap
(a dangling `E-003` citation, uncaught by any of the seven validator rules) —
though the downstream `research_handoff.json` for the same subcap correctly
excludes it, so the defect happened to stay contained without anything
forcing that containment (finding #89, MINOR).

**Cross-cutting**: the pinned workbook directly self-contradicts about
whether `Subcap_Synthesis`/`Negative_Findings` are separate sheets or merged
into the pillar tabs — its own changelog says merged, its own sheet inventory
says merged, and its own body text three paragraphs later says "still exist,
and read these columns." Recorded per §10, not resolved.


---

## 10. Publication gap

**No tool, script, or code path in the live system publishes `.xlsx`/`.docx`/`.csv`
bytes.** `apps/mcp/server.py` has exactly 33 `@mcp.tool()` decorators, all
JSON/dict-payload based; a repo-wide grep for `Workbook()`/`.save(`/`Document()`
construction across `apps/api`, `apps/mcp`, `apps/worker`, `packages`,
`migrations` returns zero matches outside test fixtures. Promotion's atomic
unit is fixed at exactly six JSON pages (`PAGES = ("heatmap","overview",
"insights","platform","context","techstack")`) — there is no seventh slot in
the writer registry or the promote transaction for any of the four new
deliverables. This absence is **ABSENT-BY-DESIGN** as far as "does the app
author or re-emit these bytes" goes — the PRD explicitly scopes the workbook/
report/package as "Unchanged by this product," "read-only thereafter."

**What no design doc addresses is the actual risk this audit was asked to
chase.** Once these documents exist, invariant 5's redaction walker
(`apps/api/dma_api/redaction.py`) operates **exclusively** on in-memory JSON
section dicts for the six served surfaces — a grep for
`redaction`/`internal_only` awareness across all three producing skill trees
(`dma-assessment`, `dma-research`, `dma-governance`) returns **zero of three**
hits. The combination — the app doesn't touch these documents, and nothing
anywhere enforces redaction on them — is **ABSENT-UNNOTICED**, and in a
headless target architecture it is a **BLOCKER**, not a note, because the
human step that today stops an internal-only paragraph reaching a client via
the `.docx` path is exactly the safety net the target architecture removes.
(Finding #49.)

Per deliverable:

| Deliverable | Status |
|---|---|
| Governance issue register (`ISS-XXX`) | Schema exists (`plugins/dma-insights/skills/dma-governance/schemas/issue_register.schema.json`) but has **no live table, API route, or MCP tool** — entirely PRESENT-HUMAN-DEPENDENT (a person runs the governance skill and reads the CSV). Confirmed genuinely distinct from `context.issue_register`/CG-46 (trap 2.3(b)): different id space, no `ISS-` pattern constraint on the live field, coincidental label resemblance only. (Finding #81, MAJOR.) |
| Research workbook (.xlsx) | No renderer, no serving route; see §9.7 for the workbook's own internal gaps. |
| Scoring workbook (.xlsx) | Same absence, compounded by §9.5/§9.7's finding that the pinned workbook and the app's own served figures already have no reconciliation path for peer/cap data. |
| Client research report + assessment report (.docx) | No renderer exists anywhere (§9.4); currently PRESENT-HUMAN-DEPENDENT end to end; **the mandatory report-template dependency itself is unpinned and has already drifted into three different documents** (the pinned v8, the superseded v6.3 the only real renderer targets, and whatever a human is actually filling in today) — finding #80, MAJOR. |

**Does invariant 2 permit file publication at all?** `apps/mcp/README.md`
explicitly documents that a by-reference submit (producer writes to GCS,
connector reads) was **rejected by design** as "invariant 2 read backwards" —
the practical form of the alternative credential is a signed URL, a secret in
a URL that would land in transcripts and logs. **This is confirmed as a real
architectural wall, not a missing feature** — surfaced here as the owner-level
decision the audit was told to raise, not settle: either invariant 2 is
amended to admit a narrow, credential-free publication path for these four
artefacts, or a different mechanism (outside the connector entirely) is
adopted for them, with its own audience-boundary enforcement built from
scratch since invariant 5's walker cannot reach it.

**Does invariant 3's atomicity extend to the new artefacts?** No design doc
addresses this either way — genuinely open, not resolved here.

---

## 11. ABSENT–UNNOTICED register

The highest-value class per §2.1 — not built, and nothing anywhere
acknowledges the hole:

1. **No mechanism re-emits the SessionStart routing brief after a mid-run
   compaction** (§9.1) — the docstring's justification for skipping the
   reprint is actively false, and nothing in the repo names this as a risk.
2. **`CG-30` (and by extension any `CG-nn`-family production gate) is
   unreachable from `routing.md`/`1-gates.md`/`surface-map.md`** — the three
   files the routing table calls authoritative — despite being a real,
   currently-blocking gate.
3. **The documented SG-09 evidence-overlap anti-clone guard has zero code
   implementation** anywhere in the supplied v4.2 archive; only an unrelated,
   toothless WARN exists under the same "anti-clone" name.
4. **The generic (untailored) MECE-question render can fire on a classified
   engagement with no refusal, warning, or halt of any kind.**
5. **Facet-coverage-lying detection** ("genuinely good" self-consistency
   check per the audit's own framing) **has zero code anywhere** — only
   written as a FAIL condition inside the same self-graded challenge prose it
   is meant to police.
6. **`kg_checksum` and `Handoff_Lock`** — both cited by name across two pinned
   templates and two installed skills as load-bearing resume/consistency
   anchors — **exist nowhere in any code this audit could reach.**
7. **CHAIN INTEGRITY** — the newest template's own reconciliation mechanism —
   is never generated by the real workbook builder; the builder's own spec
   doc doesn't mention it either.
8. **`kg/catalog/offering_map.json`** (a real, curated, 458/851-subcap
   linkage artefact) **is never consulted by any validator or renderer** —
   built and correct, and silently unused.
9. **`report_parser.py`'s section-kind map is offset by one** against the
   pinned v8 template with no test or gate that would ever notice.
10. **The project's own acceptance ledger (`BD-04`) falsely claims CI
    enforcement** for invariant 7's one-colour-module rule; zero test anywhere
    checks it, and the module the ledger names is not even the one the live
    dashboards use.
11. **Gates A, B, C, D, F, K have no test file and no negative control at
    any level** — and unlike C/D/F (which the repo's own `mutation_check.py`
    docstring names as a known, unautomated gap), **A, B and K are not
    mentioned anywhere as a known gap** — genuinely unnoticed, not merely
    unfixed.
12. **Gate M (evidence URL/span)** — purpose-built after a client shipped
    with 85% unURLed evidence — **is never invoked anywhere in the pipeline**;
    only its own unit test ever runs it.
13. **`identifiers.find_fabricated()`** — built and unit-tested specifically
    to reject a client-supplied evidence id — **is dead code, called nowhere
    in production.**
14. **`explain_gate`'s `threshold_history`** is a permanently empty schema
    shell; nothing ever writes to it, though the connector tool advertises it
    as real history.
15. **`runs.status` has no terminal "final" value** — `CLAIMED`, `SYNTHESISING`,
    `STAGED` are declared in the enum and documented in the Backend Schema but
    are **never written by any live code path.**

---


## 12. Findings (worst first)

**110 distinct findings** survived deduplication across the 24 sections (112
raw, 2 collapsed as exact duplicates). All were run through the shared
findings memory's own discipline (`search_findings` first, then
`record_finding` for a genuinely new finding or `report_recurrence` for a
resolved-and-returned one, per §7) — **105 of 110 were successfully filed**
this run; the remaining 5 (one recording batch) hit a transient API error
mid-run and are being re-filed as this report is finalized. Exact `MEM-####`
ids for every filed finding are in `.qa/workflow_results.json`'s
`record_outcomes` array and are retrievable live via `search_findings` on any
title below — they are omitted from the static table here because several
titles matched an **already-open** finding (correctly filed as
`skipped_duplicate` rather than re-recorded, e.g. MEM-0324, MEM-0082, MEM-0092
are referenced by name throughout this report rather than re-filed) and the
id-per-row mapping is best read live rather than frozen into this document.

The full BLOCKER tier (49 findings) is reproduced in §§4–11 above with full
measurements. The table below is the complete worst-first index across all
four severities (BLOCKER 49 · MAJOR 33 · MINOR 18 · INFO 10), each row
traceable to its section and abridged measurement; the unabridged
`observed`/`measurement`/`failure_scenario` for every row is in
`.qa/workflow_results.json` and `.qa/ledger.jsonl`.

| # | Sev | Title | Section | Measurement (abridged) |
|---|---|---|---|---|
| 1 | BLOCKER | The dma-synthesis-sequence production Routine is still missing Exa and Tavily as of this audit, unchanged since MEM-0324 was raised | 1.2 | mcp__Claude_Code_Remote__list_triggers, 2026-08-28: data[2] (name='dma-synthesis-sequence', id trig_011Qkj9VgeRgktdhgaZxkeut) mcp_connections has 2 en... |
| 2 | BLOCKER | A dispatched producer fabricated an enrichment scan it never ran, and the defect class that would generally prevent recurrence has zero closed instances | 1.2 | get_finding('MEM-0082'): status OPEN, severity BLOCKER, 20 distinct strings across 5 pages depended on the fabricated scan; get_memory_digest open_by_... |
| 3 | BLOCKER | The search_requests / re-invoke enrichment relay described in the docs has no executable implementation | 1.2 | grep -rn 're-invoke' plugins/dma-insights/ returns matches only inside prose/comments in docs/ROUTINES.md, docs/CONNECTORS.md, skills/.../routing.md a... |
| 4 | BLOCKER | merge_evidence.py hardcodes the coverage denominator to the old 836-subcap taxonomy | 1.3 | grep -n 'calculate_coverage_stats' plugins/dma-insights/skills/dma-research/scripts/merge_evidence.py -> lines 185 (def, default=836) and 236 (call, n... |
| 5 | BLOCKER | session_brief.py's no-reprint-on-compact logic rests on a falsified assumption; nothing recovers the routing brief mid-run | 4.1 | Ran: `claude -p "Read [3 large docs/text/*.txt files fully]... then recite the SessionStart routing brief verbatim or say FORGOTTEN" --autocompact 100... |
| 6 | BLOCKER | The routing table itself cannot answer two of five realistic dispatch tasks within any bounded number of hops | 4.1 | grep -n "CG-30" on plugins/dma-insights/skills/dma-surface-production/05-lifecycle/1-gates.md and .../surface-map.md: zero matches in both (exit 1). g... |
| 7 | BLOCKER | Documented R23 anti-drift resume command is a broken CLI invocation, reproduced live | 4.2 | Live-executed in /tmp/dmar/dma-research: `python3 scripts/engine/kg_reader.py guard --run <checkpoint-dir>` -> argparse error, exit 2, reproduced dete... |
| 8 | BLOCKER | kg_checksum and Handoff_Lock catalogue-hash resume anchors exist only as prose in the newest pinned template, unimplemented in any code | 4.2 | grep -rn 'kg_checksum' across /tmp/dmar/dma-research/ and /home/user/Accelerate/{plugins,apps,packages,migrations,scripts,infra} = 0 of 0 files matche... |
| 9 | BLOCKER | CHAIN INTEGRITY reconciliation block is template-only; the actual workbook generator never produces it | 4.2 | populate_workbook.py lines ~128-136 (Coverage sheet build) write headers ['Category','In_Scope','With_Evidence','No_Evidence','Coverage_Pct'] only, 0 ... |
| 10 | BLOCKER | The R27 40-search-op budget wall has no working enforcement instrument | 4.3 | orient.py run against a seeded 45-search-op ledger printed do_first=['state clean - proceed to next_card'] at exit 0; ledger.py stats crashed with Nam... |
| 11 | BLOCKER | Report LENGTH blocking-minimums are enforced nowhere in code | 4.3 | grep -n 'LENGTH\/word\/min_words\/blocking' across scripts/deliver/*.py (4 files, 434 lines total) and plugins/dma-insights/skills/dma-governance/: 0 ... |
| 12 | BLOCKER | No renderer exists for either pinned v8 report template anywhere in the pipeline | 4.4 | grep -rln 'def render/generate_report/build_report/render_assessment/render_client' apps/worker apps/api apps/mcp plugins/dma-insights/skills/dma-surf... |
| 13 | BLOCKER | report_parser.py's hardcoded 12-section map is offset by one against the pinned v8 template's real 11 sections | 4.4 | Diff of report_parser.py:26-38's 12-entry SECTION_KINDS dict against the pinned Doc's 11-section table of contents (both read in full): sections 3 thr... |
| 14 | BLOCKER | Pinned DMA Workbook has none of the tabs both report templates depend on | 4.4 | openpyxl.load_workbook('dma_workbook.xlsx').sheetnames == 11 named sheets, enumerated above and verified against every tab name both templates cite by... |
| 15 | BLOCKER | Offering/solution linkage is unenforced free prose at every layer, and three disjoint offering catalogs exist with no cross-reference | 4.4 | grep -rn offering apps/mcp/dma_mcp/contracts_data.json apps/mcp/dma_mcp/writer_spec.json apps/api/dma_api/writer_spec.json packages/shared/contracts_d... |
| 16 | BLOCKER | Category-grain peer benchmarking has no legitimate live source: the workbook removed the sheet, the live skill targets a superseded workbook shape, and the app payload contract requires a source_cell that cannot be produced | 4.5 | grep across the 189,980-char pinned workbook export for 10 tab names referenced by the pinned Assessment Report as scoring-workbook inputs (Pillar_Rol... |
| 17 | BLOCKER | AG-04 does not cover every payload location naming a peer: platform.starters.peer_reference has zero mechanical check | 4.5 | grep -rn peer_reference apps/mcp/dma_mcp/*.py returns 0 hits; python3 JSON scan of contracts_data.json's 10 pages finds peer_coverage/peer_deployments... |
| 18 | BLOCKER | Omitted platform readiness silently scores GREEN, not the engine's own honest amber | 4.6 | Ran `_readiness_token(None)` and `_readiness_token('')` directly -> both return 'green'; `_readiness_token('SOMETHING WEIRD')` -> 'red'. Confirmed by ... |
| 19 | BLOCKER | platform.recommendations payload carries zero fields for the template-mandated Rebuttal block | 4.6 | Read apps/mcp/dma_mcp/contracts_data.json:652 (full field list, no rebuttal fields); `find /home/user/Accelerate -iname 'render_client_report*'` -> 0 ... |
| 20 | BLOCKER | Assessment Report §3.2 reads a Cap_Triggers sheet the workbook deleted | 4.7 | grep for 'Cap_Triggers' across the 189,980-character DMA Workbook export = 0 of 0 occurrences; openpyxl.load_workbook on a real workbook built via /tm... |
| 21 | BLOCKER | The only defect class that catches a gate-passing-but-wrong page depends entirely on an unenforced, unmeasured human step | 5.1 | grep -rn 'review_required/reviewed within/human review/SLA' apps/api apps/mcp apps/worker apps/web packages migrations plugins scripts infra -> 0 matc... |
| 22 | BLOCKER | Invariant 7 ("score→band→hex in exactly one frontend module") is violated in the live app: the module that actually renders client dashboards is a second, untested, undocumented duplicate of apps/web/lib/bands.js | 5.2, also ['S7'] | grep -rln "lib/bands" apps/web (excl. node_modules/.next) -> 1 file: apps/web/app/status/page.jsx. grep -rln "maturityHex/maturityClass/maturityLabel"... |
| 23 | BLOCKER | Invariant 2 has no built mechanism for any of Stage 8's four new deliverables (governance issue register, research workbook, scoring workbook, client/assessment reports) — confirmed, not merely suspected | 5.2 | `grep -c "^@mcp.tool()" apps/mcp/server.py` -> 33. `grep -rn "issue_register" apps/api apps/mcp apps/web packages` -> every hit is context.issue_regis... |
| 24 | BLOCKER | Gate A (no-inference-imports) has no test and no negative control | 5.4 | `ls scripts/tests/` contains no test_gate_a*.py; `grep -rln gate_a_no_inference_imports --include=*.py . / grep -v pycache` returns only scripts/gate_... |
| 25 | BLOCKER | Gate K (rejections return) has no test and no negative control | 5.4 | `ls scripts/tests/` contains no test_gate_k*.py; `grep -rln gate_k_rejections_return --include=*.py . / grep -v pycache` returns only the gate's own s... |
| 26 | BLOCKER | Gate M (evidence URL/span) is never invoked in the pipeline | 5.4 | `grep -rn gate_m_evidence_url_and_span --include=*.py --include=*.yml --include=*.sh .` (excluding __pycache__) returns exactly the gate's own source ... |
| 27 | BLOCKER | No request-driven front door exists; the synthesis Routine only picks pre-ingested runs, never creates one | S1 | live list_pending_runs returned 282 rows, all status INGESTED, none created by any request mechanism; run_gate.py lines 315-537 confirmed queue-only s... |
| 28 | BLOCKER | Slack ingress is entirely unbuilt — no auth, authz, rate limiting, or replay protection to evaluate because there is no code | S1 | grep -rn 'SLACK_' apps/api apps/mcp apps/worker apps/web packages migrations plugins/dma-insights scripts infra = 0 hits; grep -rni 'rate.?limit/throt... |
| 29 | BLOCKER | No alerting exists for a stuck/quarantined ingest; the only failure surface requires a human to look | S1 | job_main.py:220-223 (print-only quarantine log); infra/provision.sh:66 grants roles/monitoring.metricWriter; 0 hits for alert-policy/notification-chan... |
| 30 | BLOCKER | Production candidate-selection dedupes by entity, contradicting the connector's own tested request-grain rule | S2 | grep -n 'def _key' scripts/synthesis_queue.py -> line 76 'return run.get("display_id") or run.get("run_id")'; run_gate.py:372-378 fallback identical k... |
| 31 | BLOCKER | Entity identity resolution has no cross-check beyond a name-slug match; a false merge of two institutions is invisible to the foreign-evidence gate | S2 | grep -rn 'domain/primary_regulator/jurisdictions' apps/worker/dma_worker/persist.py returns exactly 3 lines (63, 282, 286), all writes at entity-creat... |
| 32 | BLOCKER | The stated twin/PENDING_REVIEW adjudication fallback ('a human or the worker dedup rules') has no automated half wired in, and no human is scheduled in this architecture | S2 | grep -rln 'pick_winner' . --include=*.py returns 2 files: apps/worker/dma_worker/dedup.py (definition) and apps/worker/tests/test_stage_1_1_1_2.py (it... |
| 33 | BLOCKER | No evidence-mode / assessment-type concept anywhere in the authority chain | S3 | grep -ni "evidence_mode/assessment_type/PUBLIC.*HYBRID.*INTERNAL" over 7 docs/text/*.txt files = 0 matches in all 7 |
| 34 | BLOCKER | No automated ingest path exists for internal documents; only a human-typed citation channel | S4 | 0 of 25,537 evidence_index rows carry origin='internal' in production, measured 2026-08-09 and quoted verbatim in apps/api/tests/test_computed_at_read... |
| 35 | BLOCKER | Anti-clone guard SG-09 (evidence-id overlap at category close) has zero code implementation anywhere | S5 | `grep -rn '60' scripts/` and `grep -rn sibling scripts/engine scripts/deliver` return zero relevant hits; `grep -rln clone scripts/engine scripts/deli... |
| 36 | BLOCKER | Generic (untailored) MECE-question render can fire on a classified engagement with no refusal | S5 | `python3 scripts/engine/kg_reader.py briefs --kg kg --capability P1C1.1 --ids P1C1.1.1 --set /tmp/smoke_es.json --lean --pretty` (no --sv/--context) e... |
| 37 | BLOCKER | G10 platform-agnostic gate does not see the runtime-rendered artefact, and client context can reintroduce a vendor name into it | S5 | render(brief P1C1.1.1, 'RB', lex, {entity:'Test Bank', extra_terms:['Salesforce','nCino']}) produced 2 route queries containing 'Salesforce nCino' ver... |
| 38 | BLOCKER | Counter-evidence and facet-coverage-honesty checks are self-graded by the same researching model with no independent script verification | S5 | grep for facet_coverage in scripts/ returns only a stub (orient.py:59) and pass-through copies (build_handoff.py:59, populate_workbook.py:102); grep f... |
| 39 | BLOCKER | All 12 named challenge dimensions are self-reported and schema-validated only — zero are independently computed | S6 | `for dim in evidence_diversity tier_hygiene recency_decay m_delta_fit counter_evidence synthesis_quality coverage_honesty floor_compliance conflict_re... |
| 40 | BLOCKER | The research challenge has no structural independence from the author, unlike the codebase's own answer to the same problem | S6 | references/cards/subcap_challenge.yaml:6 ('You are challenging YOUR OWN findings'); plugins/dma-insights/agents/learning/learning-grader.md:1-9 disall... |
| 41 | BLOCKER | The challenge/provisional disposition dies between the handoff and the app — confirmed empirically end-to-end | S6 | `python3 tests/golden/integration_smoke.py` printed `P1C1.1.1 record: {... 'challenge': 'PASS' ...}`; grep for 'ceiling_band_delta/challenge_verdict/p... |
| 42 | BLOCKER | Anti-form-filling gates on synthesis quality are purely syntactic and empirically defeatable by generic prose | S6 | A 232-character generic sentence with no specific reasoning content ('This source offers general context about the institution and its market position... |
| 43 | BLOCKER | Circular corroboration is unguarded by any code, and the one stated defense is itself unimplemented | S6 | scripts/engine/ers_v2.py:91 `ap.add_argument('--corroboration', type=float, required=True)`; grep -rn 'single_source_concentration' scripts/ = 0 hits. |
| 44 | BLOCKER | A HARD HALT (checksum guard) has no listener anywhere in the current repo | S6 | Empirical run of `kg_reader.py guard` with a mismatched checkpoint: stderr='HALT R23: ...', stdout='', exit=1. grep -rln 'dma-surface-production/dma-r... |
| 45 | BLOCKER | The dma-research run directory ($RUN) has no durability guarantee beyond one Cowork container's lifetime | S6 | grep across infra/ and migrations/ for a dma-research run-directory backup/sync path returned nothing; docs/text/DMA Insights - TRD.txt lines 60 and 1... |
| 46 | BLOCKER | qa_auditor.py always FAILs every canonical workbook regardless of quality, because it checks a schema the practice's own skill forbids | S7 | cd scratchpad && python3 qa_auditor.py --workbook good_workbook.xlsx --out-dir qa_out_good2 >/dev/null 2>&1; echo $? -> 1 (same as the deliberately ba... |
| 47 | BLOCKER | The ±0.8 uncertainty cap and its cited gate ('G14') have no enforcement anywhere in the codebase | S7 | mcp__plugin_dma-insights_connector__explain_gate(gate_id='G14') -> {"error": "unknown_gate", "gate_id": "G14"}; grep -noE '\"(AG/SG/ET/CG)-?[0-9]+\"' ... |
| 48 | BLOCKER | No tool, script, or code path in the live system publishes xlsx/docx/csv bytes — publication is 100% net-new build | S8 | grep -c "@mcp.tool()" apps/mcp/server.py -> 33 of 33 tools are JSON-only; grep -rn "Workbook()\/\.save(" apps/worker apps/api apps/mcp packages migrat... |
| 49 | BLOCKER | Redaction machinery (invariant 5) has no awareness of documents; producing skills have zero internal_only handling | S8 | grep -rln "internal_only/redact" plugins/dma-insights/skills/dma-assessment plugins/dma-insights/skills/dma-research plugins/dma-insights/skills/dma-g... |
| 50 | MAJOR | DISPATCH-MODE preamble tells a dispatched agent how to report, never how to route | 4.1 | Read plugins/dma-insights/scripts/agent_run.py lines 45-59 (the full PREAMBLE string) verbatim -- no occurrence of 'rout' anywhere in it. Cross-checke... |
| 51 | MAJOR | patch_validator.py and strip_working_area.py, both required by the pinned template's stated contract v3 / template v2.0.0, do not exist in any codebase available to this audit | 4.2 | find /tmp/dmar/dma-research -iname '*patch_validator*' -o -iname '*strip_working_area*' = 0 results; same search across /home/user/Accelerate/plugins ... |
| 52 | MAJOR | Both the daily drift-review and weekly rectification Routines are currently failing on an account spend limit, with recovery requiring a human admin | 4.2 | get_session on cse_01JW3PdfntTUHMztgx8euMH2 (weekly) and cse_013dbFU17CZnBG21buVB5361 (daily) both return status_bucket SESSION_STATUS_BUCKET_FAILED w... |
| 53 | MAJOR | Batched subcap self-challenge has no anti-rubber-stamp check | 4.3 | challenge_verdict.schema.json's only required properties are scope, target_id, dimensions, overall, ceiling_band_delta; 'rationale' is optional (addit... |
| 54 | MAJOR | The never-cat context-economy rule (R27) is unenforced prose | 4.3 | plugins/dma-insights/hooks/hooks.json PreToolUse/Bash matcher points only at deny_credential_ops.py; read the full 74-line file and its 6 DENIALS rege... |
| 55 | MAJOR | get_capability_catalogue's pillars field is empty for every run sampled, with no basis disclosure | 4.4 | Two live tool calls to mcp__plugin_dma-insights_connector__get_capability_catalogue (run_ids f7b03971-30fa-4b10-86f4-69956603acde and a326d784-3a63-4e... |
| 56 | MAJOR | Cap_Triggers, Issue_Register and Handoff_Lock -- the entire cap-lift and aggregate-effect data source for Assessment Report §3.2/§3.3 -- do not exist anywhere | 4.4 | grep -rn Cap_Triggers /tmp/dmar/dma-research = 0 hits across 99 files; pinned workbook sheetnames enumerated via openpyxl show no Cap_Triggers/Issue_R... |
| 57 | MAJOR | "Handoff_Lock" — the artefact both pinned report templates and the live dma-assessment skill cite as where the peer-set lock lives — does not exist anywhere in the pinned workbook or the live app | 4.5 | grep -rln 'Handoff_Lock' docs/text apps/mcp apps/api apps/worker packages/shared scripts (excluding legacy) returns 0 files; workbook's Run_Metadata t... |
| 58 | MAJOR | The app's four-rung peer-degradation ladder has no counterpart in either pinned report template | 4.5 | Negative search of the 62,550-char Assessment Report and the 189,980-char Client Profile export for 'floor n', 'lower n', 'adjacency', 'proxy ceiling'... |
| 59 | MAJOR | Platform surface's own contract cites gate ids (S13/S17/S31/S32) that do not exist in the connector | 4.6 | Parsed gates.py's GATES dict with a python regex -> 69 ids, all AG-/CG-/ET-/SG- prefixed; grep of every .py file under apps/mcp/dma_mcp for the litera... |
| 60 | MAJOR | alignment_quote is unvalidated free text; a fabricated client-objective quote is not catchable | 4.6 | grep -n 'alignment_quote' apps/mcp/dma_mcp/*.py -> 3 hits, all pass-through (fit.py:243,321; validation2.py:1481); grep 'alignment_quote' against both... |
| 61 | MAJOR | Platform_Peer_Adoption store gone; live replacement is optional and ungated | 4.7 | grep for 'Platform_Peer_Adoption' across the 189,980-character DMA Workbook export = 0 hits; packages/shared/contracts_data.json line 845 states 'peer... |
| 62 | MAJOR | App cannot tell FOCUSED-excluded subcaps from unscored ones | 4.7 | grep -rn "engagement_set/selected_subcaps/scope_mode/FOCUSED/CATEGORY_SUBSET" apps/worker/dma_worker/*.py apps/api/dma_api/*.py packages/shared -r (ex... |
| 63 | MAJOR | No cap on how many times a synthesis run may stall, lapse and be reclaimed; the same stall is independently re-recorded rather than escalated | 5.1 | search_findings('watchdog observability trigger-fired session cannot be seen from outside') returned 3 distinct OPEN findings (MEM-0267, MEM-0285, MEM... |
| 64 | MAJOR | Two of the routines most responsible for catching an unattended failure carry no notification configuration | 5.1 | Read plugins/dma-insights/docs/ROUTINES.md lines 500-508 (2c, no 'notifications' or 'push' token in the trigger row) and lines 620-660 (2d, same absen... |
| 65 | MAJOR | Three of four diagnostic scripts named for autonomy monitoring have zero automated consumers of their output | 5.1 | grep -n 'goal_status/backlog_sweep/ingest_readiness' .github/workflows/ci.yml -> 0 matches (rc=1); grep for the same terms in plugins/dma-insights/rou... |
| 66 | MAJOR | The project's own acceptance ledger falsely claims CI enforcement for the invariant-7 rule (BD-04) that does not exist anywhere in the repo | 5.2 | grep -rln "BD-04" apps/web/tests scripts (excluding the acceptance docs themselves, i.e. ACCEPTANCE.md/inventory.json) returns zero files. |
| 67 | MAJOR | Invariant 1's enforcing gate (scripts/gate_a_no_inference_imports.py) has zero test coverage — no negative control proves it can fail | 5.2 | `ls /home/user/Accelerate/scripts/tests/` lists 30 files; `find /home/user/Accelerate -iname "*test*gate_a*"` returns zero results. `python3 scripts/g... |
| 68 | MAJOR | Gates B, C, D, F have no test and no negative control | 5.4 | `ls scripts/tests/` has no test_gate_{b,c,d,f}*.py; repo-wide grep for each module name outside its own gate_*.py source returns zero hits; scripts/mu... |
| 69 | MAJOR | Chunked-payload pagination boundary/offset arithmetic is mutation-unverified | 5.4 | `python3 scripts/mutation_check.py --pairs` for the test_staged_readback.py pair: '3/6 mutants killed', survivors 'line 216: 1 -> 2', 'line 210: > -> ... |
| 70 | MAJOR | dma-assessment skill still builds a 17-category/836-subcap workbook against a settled 16/851 taxonomy | 5.5 | grep -n '17 categor/836 subcap' plugins/dma-insights/skills/dma-assessment/SKILL.md returned 6 hits (lines 5,6,69,152,162,433) against packages/shared... |
| 71 | MAJOR | Charter-claimed GCS artefact-byte persistence is not implemented in the live worker | S1 | 0 hits for storage.Client/google.cloud.storage/bucket in apps/worker/*.py; google-cloud-storage absent from apps/worker/requirements.txt; job_main.py:... |
| 72 | MAJOR | The ingested tier's 'read-only once scanned' invariant is not enforced by database grant | S1 | migrations/versions/0005_ingested_tier.py:252: GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO svc_worker, for every ingested-tier table |
| 73 | MAJOR | The documented 'four-signal entity cascade' is a three-signal cascade in production — the known-names cross-check never runs | S2 | grep -n 'resolve(' apps/worker/dma_worker/persist.py -A6 shows the single call: manifest_identity=inst.get('name'), request_id=manifest.get('run_id'),... |
| 74 | MAJOR | evidence_index.origin is never consulted by the redaction walker | S4 | grep -n 'origin' apps/api/dma_api/redaction.py returns 0 of 0 matches (empty result) against a 600+ line module that otherwise implements the full inv... |
| 75 | MAJOR | No credential anywhere in the repo opens an internal document in an unattended run | S4 | secrets.md, 158 lines, sections 1/1b/2/3 read in full; §3 'What is deliberately NOT here' (lines 140-147) lists 3 excluded credential classes, none of... |
| 76 | MAJOR | Pre-built query templates drift from their diagnostic questions for a reproducible, generalizable subset of subcaps | S5 | P1C2.1.4 'Role Definitions' -> query '"{e}" chief role definitions officer'; P4C1.9.RIA1 'Multi-Custodian Data Integration & Householding' -> queries ... |
| 77 | MAJOR | TF-IDF map-fact mapper mis-ranks a fact when its phrasing echoes shared archetype boilerplate | S5 | Query against kg/graph/semantic_index.json for a fact mirroring P2C2.5.3's own signal text returned Commercial Loan Application (0.178), Loan Servicin... |
| 78 | MAJOR | An id-collision under the fcntl allocator destroys the earlier evidence item's data in the same operation that detects it | S6 | Empirical run: `ledger.py append` (collision) -> `ledger.py compact` -> `{"id_collisions": 1, ...}` -> `floors_gate.py --require-synthesis` -> `gate: ... |
| 79 | MAJOR | peer_median is verified-and-not-stored at ingest tier but stored-and-unverified at serving tier | S7 | grep -n peer_median apps/mcp/dma_mcp/promote.py -> 0 hits; migrations/versions/0011_peer_scores_category_grain.py:1-8 states the intended design ('med... |
| 80 | MAJOR | dma-assessment's mandatory report-template dependency is unpinned and has already drifted into three different documents | S8 | SKILL.md:616 literal string 'DMA_Assessment_Report_Template.docx'; bundled file at plugins/dma-insights/skills/dma-assessment/templates/Digital_Maturi... |
| 81 | MAJOR | Governance issue_register.csv (ISS-XXX) is entirely PRESENT-HUMAN-DEPENDENT with no live-app counterpart | S8 | grep -rln "ISS-\\[0-9\\]/ISS-[0-9]{3}" apps/api apps/mcp apps/worker apps/web packages migrations scripts infra -> only apps/mcp/tests (unrelated: com... |
| 82 | MAJOR | promote_run's retained-page re-validation skips pass2 (evidence/foreign-id) gates entirely | S9 | grep -n 'validate_pass2/get_evidence' apps/mcp/dma_mcp/promote.py returns 0 of 574 lines; contrast with apps/mcp/dma_mcp/submit.py:230,236 which calls... |
| 83 | MINOR | dma-assessment's own SKILL.md still advertises the wrong taxonomy counts, live in the installed plugin | 1.3 | grep -n '17 categor\/~836\/836 subcap' plugins/dma-insights/skills/dma-assessment/SKILL.md -> 5 line hits (lines 5, 6, 69, 152, 162, 433) out of a liv... |
| 84 | MINOR | Landing v4.2 needs two undeclared Python dependencies in the plugin's real dependency-install path | 1.3 | diff plugins/dma-insights/skills/dma-research/scripts/requirements.txt /tmp/dmar/dma-research/scripts/requirements.txt shows +PyYAML>=6.0, +jsonschema... |
| 85 | MINOR | 4 of 6 production SKILL.md files exceed the harness's own 500-line authoring ceiling, and audit_skills.py enforces no size limit at all | 4.1 | Read /mnt/skills/examples/skill-creator/SKILL.md lines 89-98 verbatim: 'SKILL.md body - In context whenever skill triggers (<500 lines ideal)... Keep ... |
| 86 | MINOR | dma-assessment's own SKILL.md still hardcodes the superseded 17-category/~836-subcap taxonomy the pinned Client Profile template's render-time-counting rule exists specifically to prevent | 4.2 | grep -n '17 categories\\/836' plugins/dma-insights/skills/dma-assessment/SKILL.md matched 3 of the file's ~450+ lines (5, 152, 433), all carrying the ... |
| 87 | MINOR | Three surfaces (2 app payload sections, 1 pinned report section) benchmark at pillar grain, outside the owner's stated category(report)/platform(app) rule — owner decision, not resolved here | 4.5 | contracts_data.json:22 (heatmap.workbook_scores.pillars); Surface Spec line 72 ('peer_median / ... / per-pillar cohort median') and Backend Schema lin... |
| 88 | MINOR | Untagged dq_facet facts are silent, not individually caught | 4.7 | populate_workbook.py:80 `ed.cell(row=r, column=6, value=f_.get("dq_facet",""))`; floors_gate.py:76-99 `len(facets.get(s_, set()) - {None}) < 3` drops ... |
| 89 | MINOR | Dangling evidence citation in Subcap_Synthesis, uncaught by validator | 4.7 | Real workbook built via integration_smoke.py: Subcap_Synthesis row Evidence_IDs='E-001, E-002, E-003, E-004'; grep 'ledger.append(RUN,"evidence"' on t... |
| 90 | MINOR | A dropped-connection replay risk on the chunked payload transport is closed by a prompt instruction, not a server-side guard | 5.1 | Read apps/mcp/dma_mcp/transport.py:301-311 (per-part idempotency confirmed) and cross-checked against ROUTINES.md's dispatch-mode text: 'a submit that... |
| 91 | MINOR | identifiers.find_fabricated() — the function the codebase built and unit-tested specifically to "reject a payload minting an evidence id" — is never called anywhere in production code | 5.2 | `grep -rln "find_fabricated" /home/user/Accelerate` (excluding __pycache__ and a docs .txt) returns exactly 2 files: apps/mcp/dma_mcp/identifiers.py a... |
| 92 | MINOR | gate_threshold_history is a schema shell: explain_gate always returns an empty history | 5.3 | grep -rn 'INSERT INTO gate_threshold_history/changed_from/changed_to' across the repo's .py files returns exactly 2 hits total, both in the migration ... |
| 93 | MINOR | One of the 12 CI skips is a code-shape gap, not an environment gap | 5.4 | apps/mcp/tests/test_gap_false_positives.py line ~89: `if not real: pytest.skip("every overview section wraps its fields today")`; confirmed present am... |
| 94 | MINOR | MCP-TOOLS.md has no freshness check, unlike two of the three other generated artefacts examined | 5.5 | diff of a fresh regen (python3 plugins/dma-insights/scripts/gen_mcp_tools_md.py . <tmp>) against the committed file showed only the stamped-commit lin... |
| 95 | MINOR | fixtures/reference_surface_keys.json generator has no automated freshness check | 5.5 | grep -rln reference_surface_keys apps/ scripts/ fixtures/ returned 3 hits, none a *_test.py or tests/ file; by contrast python3 -m pytest apps/api/tes... |
| 96 | MINOR | Gate H checks only 25% of matching persistence-claim lines in the prompt corpus | 5.5 | Instrumented gate_h_prompt_persistence_claims.claim_lines() over the same 47 .md files the gate itself scans: 20 lines matched vs. the gate's reported... |
| 97 | MINOR | MEM-0092's duplicate figure is stale in its stated denominator and has not shrunk across three independent re-measurements | S2 | Tool result file /root/.claude/projects/-home-user-Accelerate/efa8fc94-fcad-50f6-b4fc-e5ab0bd63f5d/tool-results/mcp-plugin_dma-insights_connector-list... |
| 98 | MINOR | Directory route hardcodes data_source instead of deriving it, and the value will become false | S3 | apps/api/dma_api/main.py:228 (entity dict) and :258-259 (run dict) both hardcode data_source: "DRIVE_PARSE"; grep -n data_source apps/api/dma_api/main... |
| 99 | MINOR | Source-URL-less (internal) citations bypass verbatim verification by construction, and are auto-downgraded to INFERENCE | S4 | apps/mcp/dma_mcp/register.py lines ~194-219; test asserts the exact behaviour at apps/mcp/tests/test_register_evidence.py:131-142 (claim=='INFERENCE',... |
| 100 | MINOR | verify_deployed.py --quick silently reports a clean deploy when gcloud is unreachable | S9 | Ran `python3 scripts/verify_deployed.py --quick` (no gcloud installed): output showed 'dmai-web COULD NOT READ — [Errno 2] No such file or directory' ... |
| 101 | INFO | Audit prompt claims thirteen defects; PR #2's named table has twelve | 1.1 | grep -c '^/' on the extracted table content = 14 lines = 2 header lines + 12 data rows (file: /tmp/claude-0/-home-user-Accelerate/efa8fc94-fcad-50f6-b... |
| 102 | INFO | Rejection-ledger persistence tests and thin-evidence generated-column test are DB-gated and could not be executed in this sandbox | 1.1 | python3 -m pytest apps/mcp/tests/test_rejections.py -q -> '4 passed, 7 skipped'; python3 -m pytest apps/worker/tests/test_ingested_excerpt_contract.py... |
| 103 | INFO | Funnel savings percentages (+25-32%/+11%/+3%) are not computed or logged anywhere in the system | 4.3 | grep -rn '25.32\/R25' across references/, scripts/, templates/, tests/ (94 files) returned mentions of the funnel mechanism only, never a percentage; ... |
| 104 | INFO | Pinned workbook self-contradicts on Subcap_Synthesis sheet existence | 4.7 | Rows 14 and 23 of the DMA Workbook export: '2.0.0 / Subcap_Synthesis and Negative_Findings removed as sheets...' and '(synthesis + negatives) / Merged... |
| 105 | INFO | The end-to-end test proving invariant 10's fabrication rejection (ET-01/ET-02 firing through submit_page_payload) is DB-backed and did not execute in this audit environment | 5.2 | `python3 -m pytest apps/mcp/tests/test_validation_pass2.py::test_foreign_halts_and_fabricated_mint_is_named -rs` -> "SKIPPED [1] apps/mcp/tests/test_v... |
| 106 | INFO | Gate A's transitive-import and dependency-manifest coverage is structurally incomplete (source-line regex only) | 5.2 | grep -rniE "anthropic/openai/cohere/mistralai/litellm/groq/together/langchain/vertexai" apps/api/requirements.txt apps/mcp/requirements.txt apps/worke... |
| 107 | INFO | Only 2 of the registry's SG entries are real; 4 fabricated SG ids (SG-E1/E2/Q1/D1) previously rendered FAIL with no gate behind them, now caught by CG-22 | 5.3 | python3 enumeration of GATES dict keys shows SG family = {SG-S8, SG-V4} = 2 of 69 registered gates; connector memory finding MEM-0083 (via search_find... |
| 108 | INFO | Audit baseline stale by one Python test | 5.4 | `python -m pytest apps/worker/tests/ apps/mcp/tests/ apps/api/tests/ scripts/tests/ plugins/dma-insights/scripts/tests/ tests/skills/ infra/jobs/tests... |
| 109 | INFO | Trap 2.3(c) confirmed distinct: posture_basis is not Stage-3 evidence mode | S3 | apps/mcp/dma_mcp/gates.py:719 quoted verbatim: 'posture_basis is the EVIDENCE/HYBRID/INFERRED chip, not prose.' |
| 110 | INFO | runs.status has no terminal 'final' value; three of six declared enum states (CLAIMED, SYNTHESISING, STAGED) are never written by any live code path | S9 | grep -rn "SET status" apps/mcp/dma_mcp/*.py apps/worker/**/*.py migrations/versions/*.py (excluding *test*) → 4 files, 5 statements total, none settin... |


## 13. Refuted leads

Nine `[LEAD]` markers were carried in the audit prompt. Each was independently
verified or refuted this run, not inherited:

| Lead | Verdict |
|---|---|
| Stage 1: "No Slack ingress exists in the live pipeline" | **CONFIRMED** — independently re-derived from this session's own tools (§5 above), not merely inherited. |
| Stage 2: "MEM-0092: 109 of 287 pending runs duplicated" | **STALE, not refuted** — re-measured live: `duplicate_requests=101`, `surplus_runs=109` are numerically identical to the 2026-08-19 baked-in figure, while the total pending pool shrank 287→282. The backlog has not shrunk in 9+ days because the fuller dedup algorithm that would shrink it is never called from the live ingest path. |
| Stage 3: "A search of the live tree for `evidence_mode` appears to return nothing" | **REFUTED as literally stated** — it returns real hits under `apps/web` (prototype mocks + render-test fixtures). The substance survives: zero hits in any real serving-layer directory. |
| Stage 8: "The connector's 33 tools submit JSON page payloads only; no publish tool exists" | **CONFIRMED TRUE**, not a hypothesis — direct inspection stands the claim up as fact. |
| §4.1: "does `claude -p --agent` load plugin hooks in a headless session at all" (implied doubt) | **REFUTED** — directly tested with the real CLI; hooks load and fire exactly as `agent_run.py`'s invocation shape would produce. The real defect is downstream, at compaction, not at headless startup. |
| §4.6: "a missing register row and a confirmed-absent one both produce greenfield" (the audit's own "contradiction that matters most") | **REFUTED** — the engine measurably distinguishes the two (Greenfield 0.0 vs. 1.0, fit 46.6 vs. 53.0), code-verified and test-covered. |
| §4.6: "an unmapped readiness phrase reads RED while an absent one reads amber" | **HALF REFUTED, HALF CONFIRMED** — unmapped correctly reads RED; absent reads **GREEN**, not amber, which is the actual (and worse) defect, reported separately as finding #18. |
| §5.7 (S7): "`gate_j_surface_parity.py` is the grain-tolerance mechanism" | **REFUTED** — the script's own docstring says it never compares values, only cross-client structural shape; the real 0.05-tolerance arithmetic lives in `validation2.py`'s `_served_figures()`/CG-07/CG-08, separately confirmed live. |

## 14. Could not determine

Sixteen items, each with the access that would settle it:

| Item | What would settle it |
|---|---|
| Whether any `dma-synthesis-sequence` firing since MEM-0324 attempted full production in silent degraded mode vs. cleanly stopping at STEP 0 | Full turn-by-turn transcript of the last-run session, or Cloud Logging access |
| Whether the production Cloud Run trigger-fired container matches this sandbox's CLI version/hook-loading/autocompact behaviour | gcloud/production credentials |
| Whether the ROUTINES.md prompt text (distinct from the shorter SessionStart brief) survives a real multi-stage compaction | A full end-to-end synthesis Routine firing long enough to compact — not safely reproducible read-only without risking a real client run |
| Real-run token savings for the category funnel (+25–32%/+11%/+3%) | A live agentic research session with real web search/fetch and per-message token accounting |
| Whether a live promoted run's `platform.recommendations` already omits a readiness value on a hot-band card | A live Cloud SQL connection or gcloud credentials |
| Whether a human today informally performs a Rebuttal-equivalent check before a report ships | Interviews with the practice / visibility into how `.docx` reports are actually authored today |
| Whether the 23-of-154-merged-workbook measurement is still accurate; whether a live workbook exercises the pinned template's Subcap_Synthesis self-contradiction | Access to the actual intake corpus (GCS bytes / Cloud SQL) or gcloud credentials |
| Whether the DQ_Facet untagged rate is materially >0% on any real client run (only a 4-fact synthetic fixture was available) | A real client engagement's completed workbook or `research_handoff.json` |
| DB-backed proof that ET-01/ET-02 fire on fabricated/foreign evidence ids | A migrated local Postgres (docker present but not running in this sandbox) |
| Whether Gate A is a required GitHub branch-protection status check (vs. merely present in CI) | GitHub repo admin / branch-protection API access |
| Whether any of 12 zero-mention gates have fired in all of production history (only a 90-day window was queryable) | A live Cloud SQL query against `gate_results`, or gcloud credentials |
| Whether `run_seq` allocation is race-safe under true concurrent writers | A live Postgres connection to reproduce a concurrent-insert race |
| Whether intake-adjacent Routines (as opposed to the documented synthesis routines) have `connectors` grants configured at all | `claude.ai` routines UI / `list_triggers` scoped access, or gcloud credentials for Cloud Scheduler job bodies |
| Whether Cowork's multi-agent dispatch runs on one host or across machines (bears on the `fcntl` per-host guarantee) | Documentation/telemetry of Claude Cowork's own dispatch topology — outside this repo entirely |
| Real-world challenge-verdict distribution vs. batch size | A real multi-capability production run's ledger; only a single-record synthetic fixture exists anywhere |
| PR #2's table has 12 rows, not 13 — is a 13th genuinely missing from the PR, or is the audit prompt's count simply wrong | Whoever wrote the audit prompt / access to an earlier PR #2 revision, if one exists |

## 15. The three things to build first

In order, because each genuinely blocks the next from mattering:

1. **A real intake front door that creates a `runs` row from a typed request
   — Slack or Routine payload — replacing (or running alongside, during
   transition) the Drive scan.** Nothing else in this report matters if a
   request can't enter the system at all; today it cannot (§3, Stage 1). This
   also forces the two irreversibility questions (§0's `source_cell`/GCS
   bytes) to be answered by design rather than discovered in production, and
   forces an entity-identity fix (finding #31) since a new front door will
   create the exact false-merge risk that today only ever happens by name
   collision.

2. **A coded (not LLM-judgement-only) backstop for the two places this audit
   found the model currently grading its own work with zero independent
   check: the enrichment-connector relay (§5, §1.2) and the synthesis
   challenge layer (§8/reasoning-trap report, §6.1–6.2).** These are the two
   places a defect can be *fabricated* (MEM-0082, already observed in
   production) or *silently discarded* (`provisional` dying before it reaches
   any served surface) with the current architecture actively removing the
   one thing that has caught every defect found so far — a human reading a
   rendered page (§1.1's caveat). This is the single highest-leverage build:
   it is what stands between "gates that catch known defect shapes" (which
   this repo does well, per §1.1's table) and "a system that can be trusted
   with a defect shape nobody has seen yet."

3. **The owner decision on Stage 8, made once, in writing, so the four new
   deliverables can be built against a real target instead of guessed at.**
   Specifically: does invariant 2 admit a narrow publication path for
   `.xlsx`/`.docx`/`.csv`, and does invariant 3's atomicity extend to them?
   Everything downstream — a renderer for the two pinned report templates
   (§9.4), a reconciled peer-grain story (§9.5), the workbook's missing tabs
   (§9.7), and redaction reaching non-JSON documents (§10) — is either
   unbuildable or built against the wrong contract without this decision
   first. This is deliberately ranked third and not first: it is an owner
   decision, not an engineering task, and per §10's structural finding, the
   obvious shortcut (a signed GCS URL) has already been correctly rejected as
   "invariant 2 read backwards" — so the decision has real teeth and
   shouldn't be rubber-stamped just to unblock the queue.

---

*Full raw data: `.qa/workflow_results.json`. Per-check ledger:
`.qa/ledger.jsonl`. Audit prompt as run: `.qa/prompt.md`
(sha256 `bdc8fdab1747fe89fb29bacd786da21e5639174385bb65724579a67f443cd26b`).
Baseline: `.qa/baseline.json`.*
