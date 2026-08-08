"""The memory's opening corpus — measured, not summarised.

A memory with nothing in it teaches nothing, and this build has already
produced a large, well-measured set of exactly the findings this store exists
to hold. Every entry below carries the measurement that produced it, taken on
2026-08-08 from production or from the tree at commit `ab81fe9`, with the
command or query in the `measurement` field so a reader can re-run it.

Where a defect could be measured from production TODAY, the current
measurement is what is recorded — not the anecdote. Three of these are
therefore recorded as still open with a live count (`0 of 5`, `0 of 51`,
`0 of 4`) even though a migration has already given them a column, because a
column is not a value and the surface is empty either way.

Two entries deliberately exercise the loop rather than only the store:

  * `SILENT_HEADER_ALIAS_DROP` is recorded, refined, resolved, and then a
    recurrence is reported against the refinement that did not hold — because
    it has now happened four times.
  * one finding is filed under a class that does not exist yet, so it arrives
    with a `new_class` definition. A class may be invented; it may not be
    invented silently.

The shape of each entry:

    {"finding": {...record_finding payload...},
     "refinement": {...record_refinement payload, minus finding_ids...},
     "resolve": bool,                      # close it with that refinement
     "recurrence": {...report_recurrence payload, minus finding_id...}}
"""

SESSION = "build-kickoff-wa1fkv"
QA = "agent:build-kickoff-memory"

CORPUS = [

    # ── the class this build keeps producing ────────────────────────────
    {
        "finding": {
            "title": "Eighteen item-level contract keys had no column to be "
                     "promoted into",
            "observed":
                "CG-13 ('Every required field has somewhere to live') only "
                "ever resolved SECTION-level fields against the writers' "
                "bindings. The keys a section's ITEM shape declares — "
                "`Per issue: {...}`, `Per item: {...}` — were never swept, so "
                "eighteen declared keys across nine serving tables were "
                "validated at submit and dropped at promotion. Every gate "
                "passed and the surfaces rendered empty under a real client's "
                "name.",
            "measurement":
                "Counted from the sweep's own result: "
                "`python3 -c \"...len(COLUMNS)\"` over "
                "migrations/versions/0027_promotion_field_gaps.py returns 18 "
                "ADD COLUMN tuples across 9 tables (context_issue_register, "
                "overview_findings x4, overview_opportunity x2, "
                "platform_roadmap x2, techstack_items, heatmap_focus_areas, "
                "heatmap_cell_evidence x2, heatmap_cohort_patterns, and "
                "item_provenance on five tables).",
            "measured_value": "18 columns across 9 tables",
            "expected": "zero: a field the contract declares has a column "
                        "before it is ever validated",
            "component": "mcp",
            "file_path": "apps/mcp/dma_mcp/gates.py",
            "gate_id": "CG-13",
            "defect_class": "CONTRACT_FIELD_DISCARDED_AT_PROMOTION",
            "severity": "BLOCKER",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "The census must resolve the item grain, not only the "
                        "section grain. The item keys are stated ONLY in the "
                        "contract's per-field doc text, so a census that reads "
                        "field tuples alone cannot see them.",
        },
        "refinement": {
            "target_kind": "SCHEMA",
            "target": "migrations/0027_promotion_field_gaps.py",
            "change": "Nine ADD COLUMNs on nine serving tables, every one "
                      "nullable, for the eighteen item keys the writers could "
                      "not store; plus the two families that legitimately have "
                      "no column recorded in the test rather than left to be "
                      "re-discovered.",
            "rationale": "A field the contract declares and the writer cannot "
                         "store is a guaranteed empty surface with a clean "
                         "verdict — the worst combination available.",
            "commit_sha": "af4cd4b",
            "gate_added": "CG-13 (item grain)",
            "verification": "apps/mcp/tests/test_field_census.py",
            "applied_by": QA,
        },
        "resolve": True,
    },
    {
        "finding": {
            "title": "The columns 0027 added are still null on the served run",
            "observed":
                "0027 gave the item keys somewhere to live. The run currently "
                "served to a client still has none of them: the anchor cell a "
                "top finding quotes, the cells a regulatory matter caps, and "
                "the verification date on every technology register row are "
                "all absent on the live payload. Either the promoted run "
                "predates the columns and needs re-promoting, or the writers "
                "were never bound to the new keys. Both are unresolved and the "
                "surface is empty either way — which is exactly how this class "
                "survives a migration that appears to close it.",
            "measurement":
                "GET https://dmai-api-dukrne5v4a-uc.a.run.app/v1/entities/"
                "baxter-credit-union-bcu/{overview,context,techstack}"
                "?audience=internal&role=ADMIN with a Cloud Run ID token, "
                "2026-08-08: overview.findings = 5 items, `subcap_id` present "
                "on 0 and `score` on 0; context.issue_register = 4 issues, "
                "`capped_subcap_ids` present on 0; techstack = 51 register "
                "rows, `as_of` present on 0.",
            "measured_value": "0 of 5 anchors · 0 of 4 caps · 0 of 51 as_of",
            "expected": "a populated anchor on every finding, a cap list on "
                        "every capping issue, an as_of on every register row",
            "component": "mcp",
            "file_path": "apps/mcp/dma_mcp/writer_spec.json",
            "surface": "D1 overview · C2 issue register · techstack register",
            "defect_class": "CONTRACT_FIELD_DISCARDED_AT_PROMOTION",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Check the writer bindings first — a column with no "
                        "writer binding is 0027 repeated. If the bindings are "
                        "right, re-promote the run: promotion is atomic and "
                        "staging rows are retained, so one page can be "
                        "re-promoted without re-synthesising five.",
        },
    },
    {
        "finding": {
            "title": "Five platform tiles were promoted as one",
            "observed":
                "`platform_story.gap_rows` was sourced from "
                "`section:platforms.0.gaps` — the FIRST tile's gap rows out of "
                "five. The run submitted five platform tiles, each with its "
                "own fit_score, gaps and story; promotion kept one, and the "
                "client clicked the other four and found them empty. The "
                "column's own DDL comment described one tile's gaps because "
                "the DDL predated the five-tile shape, so the comment agreed "
                "with the bug.",
            "measurement":
                "GET /v1/entities/baxter-credit-union-bcu/platform"
                "?audience=internal&role=ADMIN, 2026-08-08: "
                "sections.platform_story.data.platforms is a list of 5 tiles — "
                "MuleSoft Anypoint Platform, Salesforce Data Cloud, Service "
                "Cloud consolidation, CRM Analytics, Cross-system workflow "
                "orchestration — each carrying its own gaps[], fit_score, "
                "rank and story_md. Before the writer-spec fix the same query "
                "returned tile 0 only: 1 of 5 kept, 4 discarded.",
            "measured_value": "5 of 5 tiles served (was 1 of 5)",
            "expected": "every tile the producer submitted",
            "component": "mcp",
            "file_path": "apps/mcp/dma_mcp/writer_spec.json",
            "surface": "D3 platform story",
            "defect_class": "CONTRACT_FIELD_DISCARDED_AT_PROMOTION",
            "severity": "BLOCKER",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
        },
        "refinement": {
            "target_kind": "COMPONENT",
            "target": "apps/mcp/dma_mcp/writer_spec.json",
            "change": "gap_rows now takes the whole `platforms[]` list rather "
                      "than `platforms.0.gaps`, and 0027 corrects the DDL "
                      "comment that had been describing the bug.",
            "rationale": "A stale DDL comment is worse than none: the next "
                         "reader trusts it and reproduces the defect.",
            "commit_sha": "af4cd4b",
            "verification": "GET /v1/entities/{id}/platform returns "
                            "platforms[] with cardinality equal to the "
                            "submitted tile count",
            "applied_by": QA,
        },
        "resolve": True,
    },

    # ── the class that wasted the most time ─────────────────────────────
    {
        "finding": {
            "title": "The app serves a compiled bundle, so a fix verified in "
                     "the browser may be verified against nothing",
            "observed":
                "apps/web serves `public/proto/js/*.js`, which are compiled "
                "from `proto/*.jsx`. Editing the .jsx and reloading changes "
                "nothing until the bundle is rebuilt. This is the most "
                "expensive class in this build, and the cost is not the wasted "
                "reload — it is that the defect gets RECORDED AS FIXED on the "
                "strength of a check that measured the old artefact.",
            "measurement":
                "`ls -l apps/web/proto/live-adapter.jsx "
                "apps/web/public/proto/js/live-adapter.js` — mtimes on "
                "2026-08-08 were jsx=1786173450 js=1786176720, i.e. the bundle "
                "is currently NEWER and the tree is clean. The defect is the "
                "verification hazard, not the current state: nothing in CI "
                "asserts the ordering, so the next edit re-opens it silently.",
            "measured_value": "3 of 3 sampled bundles currently newer than "
                              "their source; 0 checks enforce it",
            "expected": "a build step or CI check that refuses a bundle older "
                        "than its source",
            "component": "web",
            "file_path": "apps/web/public/proto/js/",
            "defect_class": "STALE_BUILD_ARTEFACT_SERVED",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Compare mtimes BEFORE trusting any browser "
                        "observation; every observation made while the bundle "
                        "is older than its source is void, including the ones "
                        "that looked like passes.",
        },
    },
    {
        "finding": {
            "title": "The deployed API answers 404 for a route its source "
                     "declares",
            "observed":
                "`main.py` declares `@app.get(\"/healthz\")` at line 67, and "
                "the deployed revision returns 404 for it while serving "
                "/v1/directory from the same request with the same token. The "
                "running artefact is older than the source that describes it — "
                "the same class as the stale browser bundle, one deployable "
                "over.",
            "measurement":
                "With a Cloud Run ID token for the service audience, "
                "2026-08-08: GET https://dmai-api-dukrne5v4a-uc.a.run.app/"
                "healthz -> HTTP 404 (Google frontend error page, not FastAPI's "
                "JSON 404); GET .../v1/directory -> HTTP 200 with 1 entity "
                "(baxter-credit-union-bcu, DMA-ASM-BCU-20260330-0001).",
            "measured_value": "404 on /healthz, 200 on /v1/directory",
            "expected": "200 {\"ok\": true, \"service\": \"dmai-api\"}",
            "component": "api",
            "file_path": "apps/api/dma_api/main.py",
            "defect_class": "STALE_BUILD_ARTEFACT_SERVED",
            "severity": "MINOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "A health route is the cheapest possible deployed-"
                        "revision probe. If it 404s, stop reasoning about the "
                        "service's behaviour from its source until it does not.",
        },
    },

    # ── the parser's two classes ────────────────────────────────────────
    {
        "finding": {
            "title": "A header spelling the parser does not know drops a "
                     "column with the row count unchanged",
            "observed":
                "The workbook parser matches headers against alias lists. An "
                "unlisted spelling matches nothing, the column is skipped, and "
                "every count-based check stays green because the ROWS are all "
                "there. Four separate occurrences this build, each found on a "
                "rendered page rather than at parse time.",
            "measurement":
                "apps/worker/dma_worker/workbook_parser.py (1372 lines): "
                "`_EV_ALIASES` carries 10 canonical keys over 40 header "
                "spellings, `_STAT_ALIASES` 11 keys over 66. Any spelling "
                "outside those 106 strings is dropped silently. The migrate "
                "Job's `VERIFY catalogue version=... platform_mapped=` line "
                "exists because the third occurrence lost a column and was "
                "found weeks later on a page.",
            "measured_value": "106 known header spellings; 4 losses to date",
            "expected": "an unrecognised header is NAMED at parse time",
            "component": "worker",
            "file_path": "apps/worker/dma_worker/workbook_parser.py",
            "defect_class": "SILENT_HEADER_ALIAS_DROP",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Assert per-COLUMN non-null counts after a parse, not "
                        "row counts. A row count cannot see this defect and "
                        "never will.",
        },
        "refinement": {
            "target_kind": "COMPONENT",
            "target": "migrations/prod_apply.py",
            "change": "The migrate Job prints `platform_mapped_cells` beside "
                      "the cell count in its VERIFY line, so a version that "
                      "loads 836 cells with 0 platform-mapped says so in the "
                      "deploy log at the moment it happens.",
            "rationale": "Right row count and green verification is the whole "
                         "signature of this class; the only fix is a "
                         "per-column number in the same log line.",
            "commit_sha": "07a6967",
            "verification": "VERIFY catalogue version=... platform_mapped=N",
            "applied_by": QA,
        },
        "resolve": True,
        "recurrence": {
            "measurement":
                "A fourth header spelling was lost after the VERIFY line "
                "landed: the line covers `platform_mapped_cells` on the "
                "catalogue load only, so any column outside that one counter "
                "is still dropped silently. Counted from the build's own "
                "history — four occurrences, one covered.",
            "measured_value": "1 of 4 occurrences covered by the VERIFY line",
            "reported_by": QA,
            "reported_by_kind": "BUILD_AGENT",
            "note": "The refinement was real and it held for the column it "
                    "counts. It did not generalise, which is the distinction "
                    "this store exists to keep.",
        },
    },
    {
        "finding": {
            "title": "A reader that cannot read its input reports nothing "
                     "rather than reporting that it could not read",
            "observed":
                "The distinction between 'this document contains nothing' and "
                "'I could not read this document' was not made anywhere in the "
                "parser, so an unreadable input became an empty result and "
                "flowed onward as data. A whole workbook parsed to nothing "
                "with no line naming which tab.",
            "measurement":
                "apps/worker/tests/test_silent_drop_classes.py holds 30 tests, "
                "one per shape measured on 2026-08-08 against the 171 client "
                "folders under the production intake tree, of which 153 carry "
                "a workbook the classifier recognises. "
                "`test_no_workbook_can_parse_to_a_silent_zero` is the general "
                "form; the other 29 are the specific spellings from that "
                "corpus.",
            "measured_value": "30 tests · 171 folders · 153 workbooks",
            "expected": "a NAMED observation per unit the reader could not "
                        "read",
            "component": "worker",
            "file_path": "apps/worker/dma_worker/workbook_parser.py",
            "defect_class": "UNRECOGNISED_INPUT_READS_AS_EMPTY",
            "severity": "BLOCKER",
            "raised_by_kind": "TEST",
            "raised_by": "apps/worker/tests/test_silent_drop_classes.py",
            "session_ref": SESSION,
        },
        "refinement": {
            "target_kind": "TEST",
            "target": "apps/worker/tests/test_silent_drop_classes.py",
            "change": "Thirty tests encoding one rule — a reader that does not "
                      "recognise its input must produce a NAMED observation, "
                      "never an empty result — built from real shapes in the "
                      "production corpus, rebuilt synthetically so no client "
                      "data lives in the repo.",
            "commit_sha": "4862582",
            "verification": "python3 -m pytest "
                            "apps/worker/tests/test_silent_drop_classes.py",
            "applied_by": QA,
        },
        "resolve": True,
    },

    # ── the matcher ─────────────────────────────────────────────────────
    {
        "finding": {
            "title": "A matcher rewritten to look for a normalised form "
                     "stopped matching and changed behaviour silently",
            "observed":
                "`headlineOf` finds the face boundary of a trigger sentence. "
                "Rewriting it to look for the NORMALISED em dash made it read "
                "for a character the payload does not contain: the payload "
                "holds whatever the producer wrote, and the hyphen "
                "normalisation happens at render, downstream of the matcher. "
                "The function kept returning a value — the whole string — so "
                "nothing raised and every card silently changed shape.",
            "measurement":
                "apps/web/proto/live-adapter.jsx:455. The current "
                "implementation matches on what FOLLOWS a full stop rather "
                "than what precedes it, and its own comment records the "
                "subtler earlier bug: guarding on the preceding character "
                "'protected decimals and broke every sentence that ends in a "
                "year, which in this corpus is most of them'.",
            "measured_value": "matcher returns the whole string for every "
                              "input when it reads the normalised form",
            "expected": "the face boundary of the producer's own sentence",
            "component": "web",
            "file_path": "apps/web/proto/live-adapter.jsx:455",
            "defect_class": "MATCHER_NORMALISATION_DRIFT",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Pin the matcher against REAL strings from the corpus "
                        "before changing it, including the un-normalised "
                        "forms. If the normalised form's corpus count is zero, "
                        "the matcher can never fire.",
        },
        "refinement": {
            "target_kind": "COMPONENT",
            "target": "apps/web/proto/live-adapter.jsx",
            "change": "headlineOf reads the PAYLOAD's own punctuation and "
                      "decides a sentence end on what follows the stop, not "
                      "what precedes it; the em dash is treated as a "
                      "legitimate face boundary only when it comes first.",
            "commit_sha": "f6d3592",
            "verification": "the source comment records both failure modes "
                            "beside the regex; no test pins it yet",
            "applied_by": QA,
        },
        "resolve": True,
    },

    # ── the environment ─────────────────────────────────────────────────
    {
        "finding": {
            "title": "A credential probe in this environment measures the "
                     "proxy, not the credential",
            "observed":
                "Outbound HTTPS goes through an agent proxy that substitutes "
                "its own credential. `GET /user` therefore answers 200 for an "
                "invalid token and for NO token at all, returning a real "
                "login. Any PAT-expiry check run here reports a healthy "
                "credential regardless of the credential's actual state. Two "
                "separate agents reached the same wrong conclusion from it, "
                "which is the tell that this is environmental rather than a "
                "mistake either of them made.",
            "measurement":
                "2026-08-08 from the build container: "
                "`curl -H 'Authorization: Bearer <deliberately invalid>' "
                "https://api.github.com/user` -> HTTP 200, body login="
                "mishleyotis, type=User. The same request with NO Authorization "
                "header -> HTTP 200. Two of two negative controls returned a "
                "successful identity.",
            "measured_value": "HTTP 200 for an invalid token and for no token",
            "expected": "401 for an invalid token",
            "component": "infra",
            "defect_class": "CREDENTIAL_SUBSTITUTION_PROBE",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Run the negative control FIRST. If a deliberately "
                        "invalid credential also succeeds, the probe is "
                        "measuring the proxy and every result from it is void "
                        "— including the reassuring ones. "
                        "`curl -sS \"$HTTPS_PROXY/__agentproxy/status\"` says "
                        "what is substituted.",
        },
    },

    # ── the vocabularies ────────────────────────────────────────────────
    {
        "finding": {
            "title": "An enum-shaped field was written with prose and matched "
                     "no filter",
            "observed":
                "`arc_shape` and the timeline's `kind` are typed by the "
                "contract as small vocabularies and were populated with "
                "sentences. TEXT columns store a sentence happily, so the "
                "payload looked fully populated while the filter, the legend "
                "and the colour rule that read the field all matched nothing.",
            "measurement":
                "GET /v1/entities/baxter-credit-union-bcu/context"
                "?audience=internal&role=ADMIN, 2026-08-08: 11 timeline "
                "events, `kind` values are single tokens — TECHNOLOGY 3, "
                "CHANNEL 2, LEADERSHIP 2, REGULATORY 2, CAPABILITY 1, M&A 1 — "
                "11 of 11 clean. Before CG-09 the same field carried prose and "
                "the timeline filter returned zero of every category.",
            "measured_value": "11 of 11 timeline kinds are single tokens",
            "expected": "a value from the contract's stated vocabulary",
            "component": "mcp",
            "gate_id": "CG-09",
            "surface": "C1 context timeline",
            "defect_class": "ENUM_FIELD_CARRIES_PROSE",
            "severity": "MAJOR",
            "raised_by_kind": "GATE",
            "raised_by": "CG-09",
            "session_ref": SESSION,
        },
        "refinement": {
            "target_kind": "GATE",
            "target": "CG-09",
            "change": "Enum-shaped payload fields are policed at SUBMIT "
                      "against the contract-vocabulary registry, where a bad "
                      "value can still be refused, instead of at promotion "
                      "where an enum column would abort the transaction on a "
                      "value the contract itself declares.",
            "commit_sha": "e90b752",
            "gate_added": "CG-09",
            "verification": "apps/mcp/tests/test_contract_vocabularies.py",
            "applied_by": QA,
        },
        "resolve": True,
    },

    # ── evidence provenance ─────────────────────────────────────────────
    {
        "finding": {
            "title": "Nineteen evidence rows cite the tool that found them "
                     "instead of the document",
            "observed":
                "Nineteen rows on the only promoted run name a prospecting "
                "tool as their source. Each has an excerpt, a claim type and a "
                "tier, so each passes the fail-closed evidence check — and "
                "none of them can be traced to anything a client could be "
                "shown, because all nineteen point at the tool's own landing "
                "page rather than at a document.",
            "measurement":
                "GET /v1/entities/baxter-credit-union-bcu/evidence"
                "?audience=internal&role=ADMIN&limit=200, 2026-08-08: 172 "
                "items; 19 match /vibe/i on source_name or source_url; those "
                "19 carry 12 DISTINCT source_names and exactly 1 distinct "
                "source_url — https://vibeprospecting.explorium.ai. Twelve "
                "different documents, one URL.",
            "measured_value": "19 of 172 rows · 12 names · 1 URL",
            "expected": "one source_url per document, resolving to the "
                        "document",
            "component": "mcp",
            "file_path": "apps/mcp/dma_mcp/register.py",
            "defect_class": "PROVENANCE_NAMES_THE_TOOL",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "`SELECT source_url, count(DISTINCT source_name) FROM "
                        "evidence_index GROUP BY 1 ORDER BY 2 DESC` — a URL "
                        "carrying many names is a tool, not a document.",
        },
    },
    {
        "finding": {
            "title": "The evidence identity check has never run on a single "
                     "row",
            "observed":
                "`identity_ok` is asserted only when a domain check actually "
                "ran, which is correct — a default that looks like a pass is "
                "the failure mode that rule exists to prevent. But the check "
                "has never had the input it needs (`known_entity_domains` is "
                "not supplied by the connector's registration path), so it "
                "abstains on every row, and an abstention on 100% of rows is "
                "indistinguishable from a deliberate design choice.",
            "measurement":
                "GET /v1/entities/baxter-credit-union-bcu/evidence"
                "?limit=200, 2026-08-08: `identity_ok` is null on 172 of 172 "
                "items. Separately, 87 of 172 rows have no published_date, "
                "which puts 97 rows in the UNVERIFIED recency band.",
            "measured_value": "identity_ok null on 172 of 172; 87 of 172 "
                              "undated",
            "expected": "a true/false on every row whose domain could be "
                        "resolved, and a stated reason on the rest",
            "component": "mcp",
            "file_path": "apps/mcp/dma_mcp/register.py",
            "defect_class": "CHECK_NEVER_RAN_READS_AS_UNKNOWN",
            "new_class": {
                "title": "A guard is wired but never receives its input, so it "
                         "abstains on every row",
                "description":
                    "The guard is written correctly and fails open to NULL "
                    "rather than to a false pass, which is right. What is "
                    "wrong is that nothing supplies the input it needs, so it "
                    "never runs — and because abstention is a legitimate "
                    "state, the 100% abstention rate reads as a design choice "
                    "rather than as a guard that was never connected.",
                "tell": "a nullable boolean that is NULL on 100% of rows, on a "
                        "column whose whole purpose is to be true or false.",
                "probe": "`SELECT count(*) FILTER (WHERE <col> IS NULL), "
                         "count(*) FROM <table>` — a ratio of 1.0 means the "
                         "check never ran. Then find the caller and check "
                         "whether it passes the guard's input at all.",
            },
            "severity": "MINOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
        },
    },

    # ── the reviewer feedback path ──────────────────────────────────────
    {
        "finding": {
            "title": "The Accept/Reject pair on every insight card wrote "
                     "nothing and could be read by nobody",
            "observed":
                "`annotations` has existed since migration 0007. No API "
                "endpoint, no MCP tool and no worker job ever selected from "
                "it, and the web adapter hardcoded `annotation: null`, so the "
                "control rendered on every card of every run and its effect "
                "was never visible again. The table also had no index but its "
                "primary key, which is what a table nobody reads looks like.",
            "measurement":
                "2026-08-08: `grep -rn \"FROM annotations\" apps/ scripts/` "
                "returned only the migration; "
                "`SELECT count(*) FROM annotations` = 0 (migrate Job VERIFY "
                "0033); the served insights page for "
                "baxter-credit-union-bcu carries 8 insight cards, each "
                "rendering the pair.",
            "measured_value": "0 readers · 0 rows · 8 cards rendering it",
            "expected": "a reader, and rows",
            "component": "api",
            "file_path": "apps/api/dma_api/annotations.py",
            "surface": "D1 insights",
            "defect_class": "WRITE_PATH_WITH_NO_READ_PATH",
            "severity": "BLOCKER",
            "raised_by_kind": "USER",
            "raised_by": "mishley.otiende@zennify.com",
            "session_ref": SESSION,
        },
        "refinement": {
            "target_kind": "COMPONENT",
            "target": "apps/api/dma_api/annotations.py + "
                      "apps/mcp/dma_mcp/feedback.py",
            "change": "A read half in annotations.py "
                      "(`read_insight_annotations`, `latest_verdicts`), "
                      "svc_mcp granted SELECT, two indexes on the table, and a "
                      "connector consumer that turns every verdict into "
                      "memory carrying the card's own text and its r_layer.",
            "rationale": "Reading annotations does not touch invariant 2: "
                         "that invariant constrains the API's WRITES, and a "
                         "SELECT adds no content.",
            "commit_sha": "ab81fe9",
            "verification": "list_reviewer_feedback + ingest_reviewer_feedback "
                            "against production",
            "applied_by": QA,
        },
        "resolve": True,
    },
    {
        "finding": {
            "title": "A signed-in analyst resolves to no user row, so every "
                     "attributable write refuses",
            "observed":
                "Authentication succeeds at the web BFF and authorisation "
                "lives in two deploy-time allowlists, but nothing ever wrote "
                "the `users` rows those allowlists imply — "
                "apps/web/lib/identity.js describes the allowlist as a "
                "placeholder for 'the users table' in its own comment. Every "
                "write that must be attributable therefore refuses a real "
                "signed-in person, and the refusal looks like a working safety "
                "check rather than a gap, which is why it survived the whole "
                "build.",
            "measurement":
                "2026-08-08, with a Cloud Run ID token: POST "
                "https://dmai-api-dukrne5v4a-uc.a.run.app/v1/entities/"
                "baxter-credit-union-bcu/insights/IC-1/annotation"
                "?audience=internal&role=ADMIN&actor=dma%40zennify.com with an "
                "Idempotency-Key and {\"action\":\"ACCEPT\"} -> HTTP 403 "
                "{\"error\":\"unknown_actor\"}. `SELECT count(*) FROM users` = "
                "0 against an allowlist of 2 addresses.",
            "measured_value": "403 unknown_actor · 0 user rows · 2 allowlisted",
            "expected": "201 with an annotation id",
            "component": "api",
            "file_path": "apps/api/dma_api/annotations.py:105",
            "defect_class": "UNPROVISIONED_IDENTITY",
            "severity": "BLOCKER",
            "raised_by_kind": "USER",
            "raised_by": "mishley.otiende@zennify.com",
            "session_ref": SESSION,
        },
        "refinement": {
            "target_kind": "SCHEMA",
            "target": "migrations/0033_reviewer_feedback_path.py",
            "change": "The committed allowlist is materialised as durable "
                      "`users` rows (ON CONFLICT DO NOTHING, so it may create "
                      "but never override), overridable at migrate time with "
                      "SEED_USERS. The 403 itself is untouched: an email not "
                      "on the allowlist still resolves to no user and is still "
                      "refused.",
            "rationale": "Enrolment cannot live in the write path — creating "
                         "the identity inside the check that guards it is the "
                         "check deleted. Just-in-time provisioning at sign-in "
                         "is the better mechanism and is still owed; the API "
                         "cannot observe a sign-in today.",
            "commit_sha": "ab81fe9",
            "verification": "migrate Job VERIFY 0033 user lines, then a real "
                            "201 from the annotation endpoint",
            "applied_by": QA,
        },
        "resolve": True,
    },
    {
        "finding": {
            "title": "The API takes the acting user's identity from a query "
                     "parameter",
            "observed":
                "`main.py`'s annotation and alert-action routes accept "
                "`actor` as a query parameter. The web BFF is the only "
                "intended caller and forwards the verified session email, but "
                "nothing in the API enforces that — any principal holding "
                "roles/run.invoker on the service can name any allowlisted "
                "actor and have the write attributed to them. Now that user "
                "rows exist, this stops being theoretical: the write "
                "succeeds.",
            "measurement":
                "apps/api/dma_api/main.py:212-216 declares "
                "`actor: str | None = None` as a route parameter, and "
                "apps/web/app/api/entity/[display_id]/insights/[ic_id]/"
                "annotation/route.js:42 sets it from the session. IAM on "
                "dmai-api lists 1 invoker binding (dmai-web) plus whatever a "
                "deploy adds; verified 2026-08-08 with "
                "`gcloud run services get-iam-policy dmai-api`.",
            "measured_value": "identity from an unauthenticated query "
                              "parameter",
            "expected": "identity derived from a signed assertion the API "
                        "verifies itself",
            "component": "api",
            "file_path": "apps/api/dma_api/main.py:212",
            "defect_class": "UNPROVISIONED_IDENTITY",
            "severity": "MAJOR",
            "raised_by_kind": "BUILD_AGENT",
            "raised_by": QA,
            "session_ref": SESSION,
            "fix_hint": "Carry the identity in a signed header the API "
                        "verifies (the BFF already mints an ID token for the "
                        "service), and keep the query parameter only for local "
                        "development behind an explicit flag. This is a change "
                        "to main.py, which this author does not own — it is "
                        "recorded rather than quietly patched.",
        },
    },
]
