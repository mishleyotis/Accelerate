# The MCP connector

12 tools. Read tools are free, idempotent and side-effect free. Write tools are the
only path into anything the product serves.

| Tool | Group | Purpose |
|---|---|---|
| `list_pending_runs` | Discover | Runs awaiting synthesis, with per-page staging counts and the current claim. |
| `get_client_state` | Discover | What is currently served for a client, plus prior runs — the diff target for a rerun. |
| `get_report_bundle` | Read | The parsed assessment package for one run. This is the agent's input. |
| `get_page_contract` | Read | The payload contract for one page: field tuples plus per-field spec text. |
| `get_capability_catalogue` | Read | The catalogue pinned to the run, with the alias bridge for renamed cells. |
| `get_evidence` | Read | Resolve ids to full rows. Returns found, not-found and foreign separately. |
| `register_evidence` | Write | Mint an id for an enrichment source. Call before citing it. |
| `submit_page_payload` | Write | Stage one page and return a structured verdict. |
| `promote_run` | Write | Atomically promote every page of a run into the serving tables. |
| `get_validation_verdict` | Inspect | Re-read a submission's verdict, including superseded ones. |
| `get_run_progress` | Inspect | Per-page status, and what is blocking promotion. |
| `explain_gate` | Inspect | A gate's definition, rationale, threshold and change history. |

## Exchanges you will get wrong from memory

### get_page_contract

Returns field tuples **and** the per-field `doc` text. For a list-of-object field the `doc`
is the only place the item keys are stated — `required/type/item_type` tells you nothing
about the shape inside. Read it; do not recall it.

### register_evidence

```
→ { run_id, item: { source_name, source_url, excerpt, claim_type, tier,
                    recency_tag, published_date, linked_subcap_ids[], facts[] } }
← { e_id, deduped, ers, errors[] }
```

- The server allocates `e_id` and computes `ers`. Sending either is ignored.
- `excerpt` is verbatim, 50–500 characters, and is verified against the fetched artefact at
  registration — not at promote, so you can still repair the span.
- The source domain is identity-checked here. This is the cheapest identity check in the
  system and it catches the most.
- Idempotent by content hash, scoped to the entity. `deduped: true` with the same id back is
  the expected result of registering one source from several surfaces.

### get_evidence — the three-way split

```
← { found: [...], not_found: ["E-CC-003"], foreign: [{e_id, belongs_to}] }
```

`not_found` means fabricated or not yet registered. **`foreign` means a real row belonging
to another institution** — stop, quarantine, escalate. Do not filter it out and continue.

### submit_page_payload

```
→ { run_id, page, payload, provenance, producer_version }
← { submission_id, verdict: { status, reasons[], warnings[], counts } }
```

Each reason carries `gate_id`, `section`, `path`, `message`, `severity`. Resubmission
supersedes the previous row for that run and page — no merge, no accumulation.

### promote_run

```
← { promoted: true, promoted_at, stats }
← 409 { error: "incomplete_run", missing_pages[], unpassed_pages[], hint }
```

All six pages or none. Re-promotion is idempotent.

## Error taxonomy

| Code | Means | Do |
|---|---|---|
| `unknown_page` | Not one of the six | Read the page list |
| `contract_violation` | Missing section, or a wrong type | Re-read the contract and re-shape |
| `grain_violation` | A quoted figure does not resolve to its named cell | Re-read the score row; fix the pairing, not the prose |
| `unresolved_id` | A cited id does not exist | Verify it, or register the source first |
| `foreign_id` | The id resolves to a <strong>different entity</strong> | <strong>Stop.</strong> This is contamination — quarantine and escalate |
| `excerpt_not_verbatim` | The span is not in the fetched artefact | Re-extract from the source; never repair by hand |
| `identity_quarantine` | A figure failed the identity gate | Emit the empty state with its reason; do not substitute |
| `incomplete_run` | Promote called before every page passed | Read run progress and finish the blocking pages |
| `lease_expired` | The claim lapsed mid-synthesis | Re-claim and resubmit — staged work survives |
| `catalogue_mismatch` | A cell id is not in the run's pinned version | Resolve it through the catalogue |

## What is safe to assume

| Safe | Not safe |
|---|---|
| Staged work survives a session ending | That accepted means rendering — accepted is staged |
| Re-registering a source is free and returns the same id | That an id can be reused across entities |
| Resubmitting a page supersedes cleanly | That a partially promoted run exists — it cannot |
| The contract cannot drift from the validator | That a remembered field shape is still current |
| A failing safeguard gate still promotes | That a failing contract or evidence gate promotes |
