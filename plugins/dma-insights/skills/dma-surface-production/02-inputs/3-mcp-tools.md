# The MCP connector

33 tools in six groups. Read tools are free, idempotent and side-effect free. Write
tools are the only path into anything the product serves. Input schemas live
server-side in `apps/mcp` (the `server.py` signatures, validated in `dma_mcp/*`) —
this document is the map, not the schema; the connector's own refusals are the
contract's enforcement.

## Read and discover — always safe, call freely

| Tool | Purpose |
|---|---|
| `list_pending_runs` | Runs awaiting synthesis (INGESTED/CLAIMED/SYNTHESISING), oldest first, each row carrying its claim state plus `run_seq`, `runs_for_request` and `is_latest_for_request`, with corpus-level `duplicate_requests` and `surplus_runs`. No per-page staging counts — that is `get_run_progress`. |
| `list_open_rejections` | Every payload the connector has refused and nobody has repaired, across all runs. Read this FIRST in any producer session. |
| `get_client_state` | What is currently served for a client, plus prior runs and enrichment drift — the diff target for a rerun. |
| `get_report_bundle` | The parsed assessment package for one run: scores with source cells and grain ids, evidence, the twelve report sections, recommendations, peers, raw tables, value chains. This is the agent's input. |
| `get_capability_catalogue` | Canonical cell ids and names for the run's pinned catalogue version, plus the alias bridge. Resolve every cell id and name through this — never copy a name out of report prose. |
| `get_page_contract` | The payload contract for one page: field tuples plus per-field `doc` text, and the `transport` envelope (byte limits, chunking steps). |
| `get_evidence` | Resolve e_ids to full rows. Returns `found / not_found / foreign` separately; `foreign` halts production. |
| `get_platform_fit` | The fit score for each candidate platform, computed server-side and read by you — never recomputed, never re-ranked. |
| `get_run_progress` | Per-page status, what is blocking promotion, and the current claim — where a resuming session sees where it left off. |
| `get_staged_payload` | What you last submitted for a page — staged, verbatim, unredacted. The read half of submit; makes the one-section repair possible across sessions. |

## Claim — one write, no content

| Tool | Purpose |
|---|---|
| `claim_run` | Exclusive expiring lease (default 90 min), one session per run. Refused while another session's lease is live (returns the holder and a hint); renewal by the same holder extends it; a lapsed lease is taken over silently. Staged work survives a lapse — the staged rows are the state, the lease is only mutual exclusion. |

## Write and lifecycle — the only path into served content

| Tool | Purpose |
|---|---|
| `register_evidence` | Mint an id for an enrichment source before citing it. Server allocates `e_id`, computes `ers`; dedup by content hash, scoped to the entity; excerpt verified verbatim against the fetched artefact. |
| `open_payload` | Open a chunked upload for a page too large to emit in one call; returns the connector-allocated `upload_id` and the byte limits. |
| `append_payload_part` | Send one part of a chunked payload. Returns a receipt, never a verdict — a part is inert until the whole assembles. |
| `submit_page_payload` | Validate (both passes), supersede the live row, stage, return the verdict — plus the rejection tickets the verdict opened, bumped or closed, and what the findings memory already knows about the gates that fired. |
| `promote_run` | All six pages, one transaction, all or nothing. Re-promotion is idempotent; promoted staging rows are retained. |
| `withdraw_run` | Take a promoted run off the client surface with a recorded reason (30-char minimum). Removes the run from `serving_directory` — delisted, not merely unopenable. Nothing is deleted; the way back is re-promoting. |
| `list_withdrawn_runs` | (read) Every currently withdrawn run with its reason and who withdrew it. |

## Findings memory — writes about defects, never about clients

For agents: a QA agent reporting what it measured, a rectifier asking "have we seen
this before", a weekly pass reading what came back. The one rule through all of
them: a finding that cannot say how it was measured is an opinion, and a resolution
that cannot name the change that closed it cannot be checked for recurrence. Both
are refused. No serving content is written here.

| Tool | Purpose |
|---|---|
| `record_enrichment` | (write) Record that one facet of a client was enriched — facet from a fixed seven (leadership · firmographics · techstack · sentiment · why_now · platform_readiness · peer_scores), `source` required, `rows_written: 0` distinguishes "ran, found nothing" from "never ran". Call it every time; it is what makes `enriched_not_promoted` visible. |
| `record_finding` | (write) Record a defect. Idempotent by content — the same defect from three QA agents is one finding with three sightings. `measurement` has a 30-char floor. |
| `search_findings` | (read) "Have we seen this before?" — lexical, semantic, fuzzy or auto. Run before recording and before designing a fix. Read `paths_skipped`: a path that never ran is not evidence of absence. |
| `list_open_findings` | (read) Everything not closed — OPEN, INVESTIGATING and RECURRED — worst first (severity, then recurrences, then sightings), with age filters. |
| `list_enrichment_gaps` | (read) Every empty field on a run's live submissions — the worklist. Computed from staged payloads against the contract, never stored, never read from the served (redacted) projection. |
| `get_finding` | (read) One finding in full: every sighting in order, every refinement with its relation (ADDRESSES or CLOSES). Look here before changing anything. |
| `list_defect_classes` | (read) The shared vocabulary, each class with its tell and probe and open-finding count. `defect_class` is a foreign key into this. |
| `record_refinement` | (write) What you changed, in response to which findings. Server allocates REF-####; `commit_sha` or `change_ref` required — a refinement nobody can locate is a claim. Does NOT close anything. |
| `resolve_finding` | (write) Close a finding by naming the refinement that closed it. The refinement is required under a CHECK — no way around it. |
| `report_recurrence` | (write) A resolved finding that came back. Recorded against the refinement by name; the refinement's `held` flips false; same 30-char measurement floor. Refused if the finding was never resolved — use `record_finding`. |
| `get_memory_digest` | (read) The weekly pass in one call: what came back, what is new, which refinements held, which classes are still producing. |

## Reviewer feedback — the web app's Accept/Reject pair

| Tool | Purpose |
|---|---|
| `list_reviewer_feedback` | (read) Reviewer verdicts on insight cards straight from `annotations`, with the actor and whether each has been ingested into the memory yet. |
| `ingest_reviewer_feedback` | (write, memory only) Turn every un-ingested Accept/Reject into memory. Idempotent — a verdict becomes a finding exactly once. A REJECT becomes a finding against the synthesis skill carrying the card's own `r_layer` reasoning; an ACCEPT lands as a verdict row. `problems[]` names unreadable verdicts rather than counting them as nothing. |

## Inspect

| Tool | Purpose |
|---|---|
| `get_validation_verdict` | A prior submission's verdict, with superseded state — readable after the submission that produced it is superseded. |
| `explain_gate` | A gate's definition, rationale and threshold history — direction of movement visible. |

## Exchanges you will get wrong from memory

### get_page_contract

Returns field tuples **and** the per-field `doc` text. For a list-of-object field the `doc`
is the only place the item keys are stated — `required/type/item_type` tells you nothing
about the shape inside. Read it; do not recall it. `["transport"]` carries the byte limits
and the exact chunking steps.

### list_pending_runs — the duplicate disclosure

```
← { pending: [ { run_id, display_id, entity_name, request_id, status,
                 completed_at, run_seq, runs_for_request,
                 is_latest_for_request, claim: {held_by, live} | null } ],
    duplicate_requests, surplus_runs }
```

Measured 2026-08-19: 109 of 287 pending runs were surplus — 101 request ids carried
more than one run, near-identical in every other field. `is_latest_for_request` is the
run a producer should work; `runs_for_request` above 1 is a condition to report, not a
preference to exercise quietly.

### register_evidence

```
→ { run_id, item: { source_name, source_url, excerpt, claim_type, tier,
                    recency_tag, published_date, linked_subcap_ids[], facts[] } }
← { e_id, deduped, ers, errors[], adjustments[]? }
```

- The server allocates `e_id` and computes `ers`. Sending either is ignored.
- `excerpt` is verbatim, 50–500 characters, verified against the fetched artefact at
  registration — not at promote, so you can still repair the span.
- The source domain is identity-checked here. This is the cheapest identity check in the
  system and it catches the most.
- Idempotent by content hash, scoped to the entity. `deduped: true` with the same id back is
  the expected result of registering one source from several surfaces. A dedup hit merges
  `linked_subcap_ids` and fills a missing `published_date` (recomputing ERS); a *conflicting*
  date is reported in `adjustments` as a contradiction and the stored date stands.
- The per-document sole-evidence cap (W6) can accept the mint and refuse the links
  (`links_written: 0`): the id and span are kept, the further cells the document would have
  become the only voice for are not.

### get_evidence — the three-way split

```
← { found: [...], not_found: ["E-CC-003"], foreign: [{e_id, belongs_to}] }
```

`not_found` means fabricated or not yet registered. **`foreign` means a real row belonging
to another institution** — stop, quarantine, escalate. Do not filter it out and continue.

### get_platform_fit — you supply judgement, the engine supplies arithmetic

```
→ { run_id, candidates: [ { platform, l3_area, alignment?, alignment_quote?,
                            readiness, depends_on? } ] }
← { platforms: [ { factors, subtotal, readiness_multiplier, relevance, state,
                   rank, rank_basis, fit_basis, top_contributors[] } ],
    context: { ...counts, notes[] }, unmatched[], engine: { weights, ... } }
```

- `alignment` is 0..1 against an objective the **entity** states — quote it in
  `alignment_quote`. **Omit** it where you could not establish one: omitting renormalises to
  the three-term blend and reports `impact_fallback`; sending 0 claims you established that
  it serves nothing, which is a different claim.
- `readiness` is the prerequisite verdict (green/amber/red or the page's own phrase). An
  unmapped phrase reads as RED — the multiplier is a safety property; ABSENT reads amber.
  Readiness MULTIPLIES, so red prerequisites cannot reach the hot band.
- `l3_area` resolves which cells the candidate addresses — never a list you write.
  `depends_on` keeps a workload from outranking its foundation. Vertical relevance CAPS the
  fit and is computed server-side.
- Copy `top_contributors` into the payload; a breakdown a reader cannot walk back to named
  cells explains nothing. `unmatched` names candidates whose area reaches no served cell.
  Read `context.notes` — a term that could not run is said, never left to read as a term
  that ran and found nothing.

### open_payload / append_payload_part — the chunked transport

A contract-complete heatmap does not fit inline: measured 2026-08-08, 1,128,742 bytes
(Frost Bank) and 1,598,147 (Fisher Investments), with `cell_evidence` alone over 860 KB.
The inline budget is **131,072 bytes** of compact JSON per tool call
(`inline_max_bytes`; recommended part size the same; hard per-part ceiling 1 MiB;
abandoned uploads swept after 48 h). Do not cut the served set to fit — chunk.

```
→ open_payload { run_id, page, producer_version }
← { upload_id, limits: { inline_max_bytes: 131072, ... }, how }

→ append_payload_part { upload_id, part, parts_total,
                        path, fields: {...} | items: [...], item_count }
← a receipt, never a verdict
```

- Exactly one body per part: `fields` shallow-merges an object at `path` (path `""` is the
  payload root); `items` appends to the list at `path` (e.g. `"cell_evidence.cells"`).
- `part` is 1-based; `parts_total` must be the same on every part — the declaration is what
  makes an incomplete transmission detectable. Pass `item_count=len(items)` so a short part
  is caught at append, not assembled into a quietly shorter payload.
- Parts apply in ascending index at assembly; resending an index REPLACES it. A dropped
  connection costs one part, not the transmission.
- The upload is bound to its run and page at open, and the id is server-allocated —
  no part can be misrouted, no producer can append into an upload it does not own. An
  upload is submitted once; after submit it is CLOSED and appends are refused.

### submit_page_payload — two transports, one validation

```
→ { run_id, page, payload | upload_id, provenance, producer_version,
    expect: {"<section>.<field>": N}? }
← { submission_id,
    verdict: { status, reasons[], warnings[], counts },
    rejections: { opened[], reopened_or_bumped[], closed[], open_after },
    memory: { checked[], known{} } }
```

- Send `payload` inline **or** `upload_id` from `open_payload` — never both. The assembled
  whole goes through the same two passes an inline payload always has; transport refusals
  (CG-16 missing parts by index, CG-17 declared length) happen before any submission row is
  written, so a partial transmission has no state in which it is submittable.
- `expect` declares the assembled length of a path. With it, CG-17 catches a list truncated
  at a valid element boundary — the one truncation a JSON parse cannot see.
- Each reason carries `gate_id`, `section`, `path`, `message`, `severity`. SG results
  disclose in `warnings` and never block. Resubmission supersedes the previous row for that
  run and page — no merge, no accumulation.
- `rejections.closed` is how "did the repair land" is answered without diffing payloads: a
  refined copy clears exactly the tickets it was opened against. `attempts` past two on a
  bumped row means the repair is looping — change approach, not wording.
- `verdict.counts` carries the transport facts (`transport`, `parts`, `assembled_bytes`,
  `assembled_sha256`) so you can prove which assembly was judged.

### get_staged_payload — the index, the section, the parts

```
→ { run_id, page }                       ← the index: per-section bytes, keys, inline flag
→ { run_id, page, section }              ← that section, verbatim (if within budget)
→ { run_id, page, section, part: k }     ← chunk k of an oversize section
→ { run_id, page, submission_id: ... }   ← a SUPERSEDED submission instead of the live one
```

- A section over 131,072 bytes is DESCRIBED (`section_too_large`, with `bytes`, `parts`,
  `item_count`), never truncated — a truncated copy resubmitted would silently empty a
  complete section. Read it with `part=1..N`, concatenate the `chunk` strings in order,
  `json.loads` the result. Each chunk alone is not valid JSON and is not meant to be.
- `submission_id` is the recovery route for the one trap this tool has: a resubmit
  supersedes, so a new payload that omitted a section the old one carried fails CG-01 with
  the content behind a row you can no longer reach by default. Nothing is lost — pass the
  old id (`get_run_progress` had it) and read it back.
- What you receive is staged and unredacted — never the served projection. A payload with
  `internal_only` stripped cannot be resubmitted; it would promote the redaction.

### promote_run

```
← { promoted: true, promoted_at, stats }
← { promoted: false, error: "incomplete_run", missing_pages[], unpassed_pages[], hint }
← { promoted: false, error: "retained_pages_fail_current_gates", pages[], reasons, hint }
```

All six pages or none. Re-promotion is idempotent. A retained PASS issued by an earlier
gate set that fails today's gates refuses promotion for the pages named — a retained
verdict is a dated observation, not a current state. Resubmit only those pages.

### record_finding — the 30-character floor

```
→ { finding: { title, observed, measurement, component, defect_class,
               severity, raised_by_kind, raised_by, ... } }
← { finding_id: "MEM-0007", deduped, sighting_id, sightings, recurrences,
    status, content_hash, errors[] }
```

`measurement` must state the command, query, HTTP status or count **with its
denominator**, minimum 30 characters — "it broke" is refused. The same floor applies to
`report_recurrence`. Dedup identity (unless you pass `dedup_key`):
`component | defect_class | (file_path or surface or gate_id) | title`. A class not in
`list_defect_classes` needs `new_class: {title, description, tell, probe}` — a class may
be invented, never invented silently. Reporting a defect that is already RESOLVED returns
a warning telling you to use `report_recurrence` — that is how a failed fix gets recorded
against the fix that failed.

## Error taxonomy

Two shapes. Validation refusals arrive inside a submit verdict as `reasons[]`, each
naming the gate, the JSON path and the arithmetic. Everything else returns a structured
`{error: ...}` (or `errors[]` on the evidence and memory writes) with a remediation hint.

| Error | Means | Do |
|---|---|---|
| `unknown_run` / `unknown_entity` / `unknown_page` / `unknown_gate` / `unknown_submission` | The named id does not exist | Re-read the id from its source (`list_pending_runs`, `get_run_progress`, the page list); never guess |
| CG-05 envelope reasons | `payload` and `upload_id` both sent, or neither; bad `provenance`; missing `producer_version` | One transport per submit; provenance is one of `analyst · derived · producer`; version every submission |
| CG-16 (verdict reason) | Chunked upload incomplete, unknown, spent, or bound to a different run/page | Resend the missing part indexes against the same `upload_id`; a spent upload needs a new `open_payload` |
| CG-17 (verdict reason) | Assembled list length differs from `expect` | Find the short part, resend it, submit again — the declaration caught a truncation JSON cannot see |
| `unknown_upload` / `upload_closed` | Appending to an id that does not exist or is already assembled | `open_payload` first; an upload is submitted once |
| `bad_part_index` / `bad_parts_total` / `part_out_of_range` / `parts_total_disagreement` | Part arithmetic is inconsistent | 1-based `part`, identical `parts_total` on every part |
| `one_body` / `bad_fields` / `bad_items` / `item_count_mismatch` / `part_too_large` | A part's body is malformed, short, or over 1 MiB | Exactly one of `fields`/`items`; `item_count=len(items)`; split oversize parts |
| `contract_violation` (CG reasons) | Missing section, or a wrong type | Re-read the contract and re-shape |
| `grain_violation` (CG reasons) | A quoted figure does not resolve to its named cell | Re-read the score row; fix the pairing, not the prose |
| `unresolved_id` (evidence reasons) | A cited id does not exist | Verify it, or register the source first |
| `foreign_id` (evidence reasons) | The id resolves to a **different entity** | **Stop.** This is contamination — quarantine and escalate |
| `excerpt_length` / `excerpt_not_verbatim` / `excerpt_unverifiable` / `url_unreachable` | The span fails the 50–500 rule, is not in the fetched artefact, or cannot be fetched | Re-extract from the source; never repair a span by hand |
| `identity_quarantine` (verdict reasons) | A figure failed the identity gate | Emit the empty state with its reason; do not substitute |
| `incomplete_run` | Promote called before every page passed | Read `get_run_progress` and finish the blocking pages |
| `retained_pages_fail_current_gates` | A retained PASS predates the current gate set | Resubmit only the pages named |
| `section_too_large` / `no_such_part` / `no_staged_submission` / `unknown_section` | A staged read needs paging, or there is nothing live to read | Use `part=1..N`; pass `submission_id` for a superseded row |
| `not_promoted` / `reason_required` / `actor_required` | Withdraw preconditions | Only a promoted run withdraws; reason is 30 chars minimum, actor named |
| `bad_enrichment` | Facet not one of the fixed seven, or source missing | The facet list is closed — a typo would create a facet nobody watches |
| `measurement: N chars` (memory `errors[]`) | Below the 30-char floor | State the command/query/status with its denominator |
| `unknown_finding` / `unknown_refinement` | The memory id does not exist | `search_findings` / `get_finding` first |
| `catalogue_mismatch` | A cell id is not in the run's pinned version | Resolve it through `get_capability_catalogue` |
| `claimed: false` (not an error) | Another session's lease is live | Read `get_run_progress` rather than working in parallel |

## What is safe to assume

| Safe | Not safe |
|---|---|
| Reads never change anything — call them freely, in any order | That a read of the served projection equals the staged row — the serve layer redacts |
| Staged work survives a session ending or a lease lapsing | That the lease is the state — the staged rows are; the lease is only mutual exclusion |
| Re-claiming a run you held, or one whose lease lapsed, succeeds silently | That `claim_run` succeeds while another live session holds it — it refuses and names the holder |
| Re-registering a source is free and returns the same id, merging links and filling a missing date | That an id can be reused across entities, or that a conflicting date is silently overwritten — a contradiction is reported and stands |
| Resubmitting a page supersedes cleanly and closes exactly the rejection tickets the gate stopped firing on | That a resubmit merges with the prior row — a section the new payload omits is gone from the live row (recoverable via `submission_id`) |
| A part can be resent; the index is replaced | That a part is validated on arrival — nothing is judged until the whole assembles at submit |
| Re-promotion is idempotent; promoted staging rows are retained | That a partially promoted run exists — it cannot |
| A failing safeguard (SG) gate still promotes, disclosed | That a failing contract or evidence gate promotes — never |
| Withdrawing deletes nothing; re-promoting restores | That there is a restore tool — the way back is passing the gates again |
| Memory writes touch no serving content and cannot break a submit | That "changed" closes a finding — `record_refinement` then `resolve_finding`, deliberately two steps |
| The contract cannot drift from the validator | That a remembered field shape is still current |
