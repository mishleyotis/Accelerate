# DMA Insights MCP connector — tool reference

Generated from `apps/mcp/server.py` at commit `3e2d5e3bf9` (2026-08-24) by `gen_tools_md.py`. Signatures and defaults are read from the source with `ast`; the description of each tool is that tool's own docstring, verbatim. Regenerate rather than hand-edit.

**33 tools.** Python MCP SDK over streamable HTTP, deployed as the `mcp` Cloud Run service on session-mode pooling (promotion holds locks).

## What constrains every tool here

These are properties of the connector, not advice — a tool that appears to offer a way around one is being misread.

| | |
|---|---|
| **Content enters only here** | The API writes annotations and alert actions and nothing else. No endpoint writes serving content. |
| **Promotion is atomic across all six pages** | One transaction, `SELECT … FOR UPDATE` on the run row, ordered writers, all-or-nothing. Promoted staging rows are retained, so one page can be fixed and re-promoted without re-synthesising five. |
| **Evidence fails closed** | Every cited id must resolve, belong to this entity and this run, and carry a verbatim 50–500 character excerpt. `get_evidence` returns `found` / `not_found` / `foreign`, and **`foreign` halts production**. |
| **The server allocates identifiers** | The agent mints only `ic_id`, `f_id`, `fa_id`, `ts_id`, `wn_id` and authored `rec_id`. Everything else comes from the catalogue or from `register_evidence`. |
| **Verdicts name the gate, the JSON path and the arithmetic** | Gate families: AG (analysis), SG (safeguard), ET (entity/identity), CG (contract/grain). A failing SG discloses and still promotes; a failing evidence reason never does. |
| **No model call on the serving path** | The bundled 384-dim embedding model runs only inside this connector, at submit, for the V4 grounding check. |

## Index

| # | Tool | Group | What it is for |
|---:|---|---|---|
| 1 | [`get_report_bundle`](#get-report-bundle) | Read the assessment | The parsed assessment: scores with source cells and all four grain ids, stated pillar/categor… |
| 2 | [`get_capability_catalogue`](#get-capability-catalogue) | Read the assessment | Canonical cell ids and NAMES for the run's pinned catalogue version, plus the alias bridge |
| 3 | [`get_page_contract`](#get-page-contract) | Read the assessment | Field tuples AND per-field doc text, verbatim |
| 4 | [`get_evidence`](#get-evidence) | Read the assessment | The three-way split: found / not_found / foreign |
| 5 | [`get_platform_fit`](#get-platform-fit) | Read the assessment | The fit score for each candidate platform, computed here and READ by you — never recomputed,… |
| 6 | [`list_pending_runs`](#list-pending-runs) | Run and session state | Runs awaiting synthesis (INGESTED/CLAIMED/SYNTHESISING), oldest first, with their claim state |
| 7 | [`claim_run`](#claim-run) | Run and session state | Exclusive expiring lease — one session per run |
| 8 | [`get_run_progress`](#get-run-progress) | Run and session state | Per-page status, what is blocking, and the current claim — so a resuming session sees where i… |
| 9 | [`get_client_state`](#get-client-state) | Run and session state | What is currently served and every prior run — a rerun produced as though it were a first run… |
| 10 | [`list_open_rejections`](#list-open-rejections) | Run and session state | Every payload this connector has REFUSED and nobody has repaired |
| 11 | [`register_evidence`](#register-evidence) | Author and submit | Mint before you cite |
| 12 | [`open_payload`](#open-payload) | Author and submit | Open a CHUNKED upload for a page too large to emit in one call, and get back the connector-al… |
| 13 | [`append_payload_part`](#append-payload-part) | Author and submit | Send one part of a chunked payload |
| 14 | [`submit_page_payload`](#submit-page-payload) | Author and submit | Validate (both passes), supersede the live row, stage, return the verdict |
| 15 | [`get_staged_payload`](#get-staged-payload) | Author and submit | What you last submitted for a page — STAGED, verbatim, unredacted |
| 16 | [`get_validation_verdict`](#get-validation-verdict) | Verdicts and promotion | A prior submission's verdict, with superseded state |
| 17 | [`explain_gate`](#explain-gate) | Verdicts and promotion | A gate's definition and threshold history — direction of movement visible |
| 18 | [`promote_run`](#promote-run) | Verdicts and promotion | All six pages, one transaction, all or nothing |
| 19 | [`withdraw_run`](#withdraw-run) | Verdicts and promotion | Take a promoted run off the client surface, with a recorded reason |
| 20 | [`list_withdrawn_runs`](#list-withdrawn-runs) | Verdicts and promotion | Every currently withdrawn run with its reason and who withdrew it |
| 21 | [`record_enrichment`](#record-enrichment) | Enrichment ledger | Record that one FACET of a client was enriched |
| 22 | [`list_enrichment_gaps`](#list-enrichment-gaps) | Enrichment ledger | Every empty field on this run's live submissions — your worklist |
| 23 | [`record_finding`](#record-finding) | Findings memory | Record a defect in the findings memory |
| 24 | [`search_findings`](#search-findings) | Findings memory | "Have we seen this before?" — asked both ways, because it is asked both ways |
| 25 | [`list_open_findings`](#list-open-findings) | Findings memory | Everything not closed — OPEN, INVESTIGATING and RECURRED — worst first |
| 26 | [`get_finding`](#get-finding) | Findings memory | One finding in full: every sighting in order, and every refinement made against it with its r… |
| 27 | [`list_defect_classes`](#list-defect-classes) | Findings memory | The shared vocabulary, with each class's TELL (how it presents) and PROBE (the command or que… |
| 28 | [`record_refinement`](#record-refinement) | Findings memory | What you CHANGED, in response to which findings |
| 29 | [`resolve_finding`](#resolve-finding) | Findings memory | Close a finding by naming the refinement that closed it |
| 30 | [`report_recurrence`](#report-recurrence) | Findings memory | A finding that was resolved and came back |
| 31 | [`get_memory_digest`](#get-memory-digest) | Findings memory | Everything a weekly refinement pass needs, in one call: what came back, what is new, which re… |
| 32 | [`list_reviewer_feedback`](#list-reviewer-feedback) | Reviewer feedback | Read reviewer verdicts on insight cards straight from `annotations`, with the actor and wheth… |
| 33 | [`ingest_reviewer_feedback`](#ingest-reviewer-feedback) | Reviewer feedback | Turn every un-ingested Accept/Reject into memory |

## Read the assessment

Pure reads of what the package and the catalogue already say. None of them write; all of them are safe to call again.

### `get_report_bundle`

```python
get_report_bundle(run_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |

The parsed assessment: scores with source cells and all four grain
ids, stated pillar/category grains, evidence, the twelve report
sections, recommendations, peers, raw tables and value chains.

### `get_capability_catalogue`

```python
get_capability_catalogue(run_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |

Canonical cell ids and NAMES for the run's pinned catalogue version,
plus the alias bridge. Resolve every cell id and name through this —
never copy a name out of report prose.

### `get_page_contract`

```python
get_page_contract(page: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `page` | `str` | **required** |

Field tuples AND per-field doc text, verbatim. The doc is part of
the contract: for list-of-object fields it is the only place the item
keys are stated.

### `get_evidence`

```python
get_evidence(run_id: str, e_ids: list) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `e_ids` | `list` | **required** |

The three-way split: found / not_found / foreign. Foreign is the
dangerous bucket — a real row belonging to another institution; stop,
quarantine, escalate.

### `get_platform_fit`

```python
get_platform_fit(run_id: str, candidates: list) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `candidates` | `list` | **required** |

The fit score for each candidate platform, computed here and READ by
you — never recomputed, never re-ranked (the contract's rule, and the
same one `register_evidence` applies to the rank score).

You supply judgement only, per candidate:
  `platform`         the platform's name as a client would say it
  `l3_area`          the catalogue L3 area it belongs to; the cells it
                     addresses are resolved from this, not from a list
                     you write
  `alignment`        0..1, how well it serves an objective the ENTITY
                     states. Quote that objective in `alignment_quote`.
                     OMIT it where you could not establish one — omitting
                     renormalises to the three-term blend and reports
                     `impact_fallback`, which is the contract's
                     instruction; sending 0 says you established that it
                     serves nothing, which is a different claim.
  `readiness`        the prerequisite verdict — green/amber/red, or the
                     page's own phrase ("READY WITH CONDITIONS"). An
                     unmapped phrase is read as RED, because the
                     multiplier is a safety property; an ABSENT one is
                     amber, the honest middle.
  `depends_on`       platforms this one needs FIRST. A card is never
                     ranked above something it depends on, so a workload
                     cannot outrank the foundation it sits on — the
                     defect this found on a real client.

Everything else is the run's: which cells the area reaches, each cell's
distance from the target band, the severity of the issues on it, how well
it is evidenced, and whether the register calls the family absent.

Readiness MULTIPLIES rather than adding, so a platform whose prerequisites
are red cannot reach the hot band. That is deliberate: a 2026-06 audit
found 95 of 470 cards scoring hot with every prerequisite failing.

Vertical relevance CAPS the fit and is computed here, not sent: it is the
share of the area's cells this entity's sub-vertical actually serves. An
out-of-vertical family cannot buy its way back with gap surface.

Each row comes back with `factors`, `subtotal`, `readiness_multiplier`,
`relevance`, `state`, `rank`, `rank_basis`, `fit_basis` and
`top_contributors` — the cells the score rests on, with their own gap,
severity and evidence numbers. Copy them; a breakdown a reader cannot
walk back to named cells explains nothing.

## Run and session state

Which runs exist, who holds them, and what is still outstanding. `list_open_rejections` is the one to read first in any producer session.

### `list_pending_runs`

```python
list_pending_runs() -> dict
```

*No parameters.*

Runs awaiting synthesis (INGESTED/CLAIMED/SYNTHESISING), oldest
first, with their claim state.

### `claim_run`

```python
claim_run(run_id: str, session_id: str, producer_version: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `session_id` | `str` | **required** |
| `producer_version` | `str` | **required** |

Exclusive expiring lease — one session per run. Refused while
another session's lease is live; staged work survives a lapse.

### `get_run_progress`

```python
get_run_progress(run_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |

Per-page status, what is blocking, and the current claim — so a
resuming session sees where it left off. Pages already passing must
not be re-synthesised.

### `get_client_state`

```python
get_client_state(display_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `display_id` | `str` | **required** |

What is currently served and every prior run — a rerun produced as
though it were a first run silently empties the longitudinal surfaces.

### `list_open_rejections`

```python
list_open_rejections(display_id: str = '', page: str = '', limit: int = 200) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `display_id` | `str` | `''` |
| `page` | `str` | `''` |
| `limit` | `int` | `200` |

Every payload this connector has REFUSED and nobody has repaired.

Read this FIRST in any producer session, before choosing a run. A
refused submission supersedes the passing row for its page and then sits
there: `get_run_progress` shows it, but only for one run and only if you
already know to ask, so a session that ends leaves no trace anything is
outstanding. Measured three times in one day on this build — a heatmap
that dropped `cell_evidence` and failed CG-01, an overview refused on
ET-07 and again on ET-09 — and every one was found by a person reading a
verdict rather than by the system saying so.

Each row carries a stable `rejection_id` keyed on (run, page, gate,
path). Submit a refined payload for that page and the rows it clears are
the rows it was opened against — `submit_page_payload` returns them under
`rejections.closed`, so "did the repair land" is answerable without
diffing payloads.

`attempts` is the number to read first. Past two it means the repair is
not landing and the next attempt should CHANGE APPROACH rather than
repeat: three identical fixes for one gate is the loop this field exists
to make visible.

Safeguard (SG) results never appear here. The charter says a failing
safeguard discloses and still promotes, so it is not an outstanding
repair.

## Author and submit

The write path. Content enters the system only here, and only through `submit_page_payload`.

### `register_evidence`

```python
register_evidence(run_id: str, item: dict) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `item` | `dict` | **required** |

Mint before you cite. The server allocates the id and computes the
rank score; dedup is by content, scoped to the entity; the excerpt is
verified verbatim against the fetched artefact.

### `open_payload`

```python
open_payload(run_id: str, page: str, producer_version: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `page` | `str` | **required** |
| `producer_version` | `str` | `''` |

Open a CHUNKED upload for a page too large to emit in one call, and get
back the connector-allocated `upload_id` every part is sent against.

A contract-complete heatmap does not fit inline: measured 2026-08-08,
1,128,742 bytes for Frost Bank and 1,598,147 for Fisher Investments, with
`cell_evidence` alone 862,351 / 1,208,289 across ~700 served cells. Rule 17
wants a drawer row for EVERY served cell, so that is the contract's size —
do not cut the served set to fit. Read
`get_page_contract(page)["transport"]` for the byte limits and the exact
step list.

The upload is bound to this run and page at open, so no part can be
misrouted into another page's payload later, and the id is server-allocated
(invariant 10) so no producer can append into an upload it does not own.

### `append_payload_part`

```python
append_payload_part(upload_id: str, part: int, parts_total: int, path: str = '', items:
    list = None, fields: dict = None, item_count: int = 0) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `upload_id` | `str` | **required** |
| `part` | `int` | **required** |
| `parts_total` | `int` | **required** |
| `path` | `str` | `''` |
| `items` | `list` | `None` |
| `fields` | `dict` | `None` |
| `item_count` | `int` | `0` |

Send one part of a chunked payload. Returns a receipt, never a verdict —
nothing is validated until the whole assembles.

Exactly one body per part:
  fields={...}  shallow-MERGES an object at `path` (path '' is the payload
                root, so a whole small section is one part)
  items=[...]   APPENDS to the list at `path`, e.g.
                path="cell_evidence.cells"

`part` is 1-based; `parts_total` is your declared part count and must be
the SAME on every part — that declaration is what makes an incomplete
transmission detectable rather than merely smaller than intended. Pass
`item_count=len(items)` so a part that arrived short is caught here rather
than assembling into a quietly shorter payload.

Parts are applied in ascending index at assembly, so the same set of parts
always assembles to the same bytes. Resending an index REPLACES it: a
dropped connection costs one part, not the transmission.

### `submit_page_payload`

```python
submit_page_payload(run_id: str, page: str, payload: dict = None, provenance: str =
    'producer', producer_version: str = '', upload_id: str = '', expect: dict = None) ->
    dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `page` | `str` | **required** |
| `payload` | `dict` | `None` |
| `provenance` | `str` | `'producer'` |
| `producer_version` | `str` | `''` |
| `upload_id` | `str` | `''` |
| `expect` | `dict` | `None` |

Validate (both passes), supersede the live row, stage, return the
verdict. Reasons name the gate, the JSON path and the arithmetic;
SG results disclose in warnings and never block.

Two transports, one validation. Send `payload` inline for a page that fits
in one call, or `upload_id` from open_payload for one that does not — the
connector assembles the parts server-side and both passes then run over the
assembled whole, exactly as they do for an inline payload. Never both.

`expect={"<section>.<field>": N}` declares the assembled length of a path.
With it, CG-17 catches a list truncated at a valid element boundary (which
parses as JSON and so is otherwise invisible); a missing part is refused by
CG-16 naming the indexes, and in neither case is a submission row written.

### `get_staged_payload`

```python
get_staged_payload(run_id: str, page: str, section: str = '', submission_id: str = '',
    part: int = 0) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `page` | `str` | **required** |
| `section` | `str` | `''` |
| `submission_id` | `str` | `''` |
| `part` | `int` | `0` |

What you last submitted for a page — STAGED, verbatim, unredacted.

The read half of submit, and what makes the one-card repair the skill
documents actually possible across sessions: retention keeps the staged
row, this hands it back, you edit the one section and resubmit.

Without a `section` you get the index — every section's name, byte size
and top-level keys. Ask for the one you are repairing. A section over the
inline budget is DESCRIBED rather than returned, because a truncated copy
resubmitted would silently empty a complete section.

`part` reads an OVERSIZE section in numbered chunks: call once without it
to learn `parts`, then part=1..N, concatenate the `chunk` strings in order
and json.loads the result. The read half of the chunked write, and for the
same reason — a section you can submit in parts you must be able to read
in parts, or a resubmit that drops one strands it.

`submission_id` reads a SUPERSEDED submission instead of the live one.
That is the recovery route for the one trap this tool has: a resubmit
supersedes, so if your new payload omitted a section the old one carried
— most easily because the section was over the inline budget and the read
DESCRIBED it rather than returning it — the resubmit fails on CG-01 and
the content is behind a row you can no longer reach. Nothing is lost from
the database; pass the old id (`get_run_progress` had it) and read it back.

This is not the served projection: the serve layer strips `internal_only`
and redacts for audience, and a payload with those removed cannot be
resubmitted — it would promote the redaction.

## Verdicts and promotion

What the gates said, and moving a run on or off the client surface.

### `get_validation_verdict`

```python
get_validation_verdict(submission_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `submission_id` | `str` | **required** |

A prior submission's verdict, with superseded state.

### `explain_gate`

```python
explain_gate(gate_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `gate_id` | `str` | **required** |

A gate's definition and threshold history — direction of movement
visible.

### `promote_run`

```python
promote_run(run_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |

All six pages, one transaction, all or nothing. incomplete_run
names the missing and unpassed pages; re-promotion is idempotent.

### `withdraw_run`

```python
withdraw_run(run_id: str, reason: str, actor: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `reason` | `str` | **required** |
| `actor` | `str` | **required** |

Take a promoted run off the client surface, with a recorded reason.

Removes the run from `serving_directory`, which is the only window the
API reads — so the entity stops being LISTED, not merely stops being
openable. Setting is_active=false does not do this: the run stays in
the view and the directory keeps publishing the client's name beside a
set of pages that 404.

Nothing is deleted. Promoted rows, annotations and alerts are retained;
the alerts leave the queue with the run and return with it, still open.
`reason` is required at 30 characters and is stored on the run.

There is no restore tool. A withdrawn run returns by being re-promoted,
which clears the withdrawal — the way back is passing the gates again.

### `list_withdrawn_runs`

```python
list_withdrawn_runs() -> dict
```

*No parameters.*

Every currently withdrawn run with its reason and who withdrew it.

## Enrichment ledger

Holds together the two halves of "the work was done but it is not showing": what was enriched, and what is still empty.

### `record_enrichment`

```python
record_enrichment(display_id: str, facet: str, source: str, run_id: str = '', account:
    str = '', rows_written: int = 0, note: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `display_id` | `str` | **required** |
| `facet` | `str` | **required** |
| `source` | `str` | **required** |
| `run_id` | `str` | `''` |
| `account` | `str` | `''` |
| `rows_written` | `int` | `0` |
| `note` | `str` | `''` |

Record that one FACET of a client was enriched. Call it every time.

This is the MCP half of the enrichment-versioning contract. Without it,
an enrichment that ran in this session and a surface that never got it
are two facts nobody holds together — which is the whole of "the work was
done but it is not showing", reported three rounds running across
leadership, why-now, sentiment and the tech register.

Call this AFTER the enrichment returns and BEFORE (or after) you submit
the page — the order does not matter, because the version is what orders
them. `promote_run` records the promotion side automatically from the
sections it writes, so a facet enriched and never promoted shows up as
`enriched_not_promoted` in `get_client_state` and in the app, and blocks
the client being called done.

facet         one of leadership · firmographics · techstack · sentiment ·
              why_now · platform_readiness · peer_scores. Not a free
              string: a typo would silently create an eighth facet that
              nobody watches, so the database refuses it.
source        REQUIRED. clay · explorium · exa · indeed · manual · … The
              answer to "run it again how?", which is the only question a
              stale facet raises.
account       WHICH account ran it, and worth the keystrokes: the same
              technographic scan returned empty twice under one account
              and sixty technologies under another, and with no record of
              which, the two runs were afterwards indistinguishable.
rows_written  how many rows the enrichment produced. 0 is a real answer
              and a useful one — it distinguishes "ran, found nothing"
              from "never ran".

Returns {enrichment_version, facet, entity_id, enrichment: {...}} where
the last is the same drift summary `get_client_state` reports.

### `list_enrichment_gaps`

```python
list_enrichment_gaps(run_id: str, page: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `run_id` | `str` | **required** |
| `page` | `str` | `''` |

Every empty field on this run's live submissions — your worklist.

Build owner, 2026-08-14: "Never place an em dash. There should always be a
way to send a signal to the MCP to give us an enrichment of the empty
field." This is that signal, and it is COMPUTED rather than queued: the set
of empty fields is derivable from the staged payloads against the contract
at any moment, so a stored request could only go stale — it would keep
asking for a field a later re-promote had already filled. Nothing is
clicked, nothing is written, and the list cannot drift from what the
surfaces actually show.

Every gap here is a spot where a reader currently sees "Not stated". Close
one and the surface fills; there is no separate step to mark it done.

THE THREE KINDS, worst first:

  must_present_member  a member the contract names on EVERY sub-vertical is
                       neither stated nor held. Its absence is never a
                       property of this client, so this is the class to
                       work first.
  empty_required       a required field is empty and the section declares
                       no empty state.
  empty_optional       an optional field is empty.

WHAT IS NOT HERE, deliberately. A field QUARANTINED with a reason is not a
gap — the producer ran the ladder, the figure failed the identity gate, and
the reason is the finding. Neither is a section that declared its
`empty_state` with a ladder: the search happened and is recorded. Nor a
boolean, whose absence IS its value. If you want a field to leave this list
without finding the value, that is the route — state the ladder, do not
invent the figure.

Reads the STAGED submissions, never the served projection: the serve layer
strips `internal_only` paths and redacts cohort `entity_ids` for every
audience, and a list built from what the API returns would report redaction
working correctly as content you failed to write.

Pass `page` to narrow to one page. Returns {gaps[], count, by_kind,
pages_read}, each gap carrying its contract `doc` text and `closes_with`.

## Findings memory

What went wrong, how it was measured, what was changed, and whether the change held. These write no serving content.

### `record_finding`

```python
record_finding(finding: dict) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `finding` | `dict` | **required** |

Record a defect in the findings memory. Idempotent by content — the same
defect reported by three QA agents is ONE finding with three sightings.

finding = {
  title           str  REQUIRED  one line: what is wrong
  observed        str  REQUIRED  what was actually seen
  measurement     str  REQUIRED  HOW it was measured — the command, query,
                                 HTTP status or count WITH its denominator.
                                 Minimum 30 chars. "it broke" is refused.
  component       str  REQUIRED  api | mcp | web | worker | migrations |
                                 infra | skill:<name> | agent:<name>
  defect_class    str  REQUIRED  a class id from list_defect_classes
  severity        str  REQUIRED  BLOCKER | MAJOR | MINOR | INFO
  raised_by_kind  str  REQUIRED  QA_AGENT | REVIEWER | GATE | USER |
                                 BUILD_AGENT | TEST | MONITOR
  raised_by       str  REQUIRED  the agent, gate or person BY NAME

  measured_value  str  the number/status itself ("403", "0 of 8")
  expected        str  what it should have been
  file_path       str  surface str (Surface Spec id)  gate_id str
  run_id / entity_id / annotation_id   where applicable
  fix_hint        str  what to do about it
  note            str  free text for THIS sighting
  session_ref     str  the chat, Cowork session or CI job that saw it
  source_ref      str  an idempotency token for this sighting
  dedup_key       str  override the dedup identity (see below)
  new_class  {title, description, tell, probe}
                  required ONLY when defect_class is not yet known — a
                  class may be invented, never invented silently
}

Dedup identity, when you do not pass dedup_key:
    component | defect_class | (file_path or surface or gate_id) | title

Returns {finding_id: "MEM-0007", deduped, sighting_id, sightings,
         recurrences, status, content_hash, errors[]}.
Reporting a defect that is already RESOLVED returns a warning telling you
to use report_recurrence instead — that is how a failed fix gets recorded
against the fix that failed.

### `search_findings`

```python
search_findings(query: str, mode: str = 'auto', limit: int = 10, component: str = '',
    defect_class: str = '', severity: str = '', status: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `query` | `str` | **required** |
| `mode` | `str` | `'auto'` |
| `limit` | `int` | `10` |
| `component` | `str` | `''` |
| `defect_class` | `str` | `''` |
| `severity` | `str` | `''` |
| `status` | `str` | `''` |

"Have we seen this before?" — asked both ways, because it is asked both
ways. Run this BEFORE recording a finding and before designing a fix.

mode:
  auto      (default) lexical first; semantic as well; trigram only if
            neither matched
  lexical   websearch_to_tsquery + ts_rank_cd over the finding's text
  semantic  pgvector KNN over the embedding written at record time
  fuzzy     pg_trgm similarity on the title — for a typo or an
            abbreviation that shares no lexeme with the corpus

Filters (all optional): component, defect_class, severity, status.

Returns {paths_run[], paths_skipped{path: reason}, results[]}. Read
paths_skipped: an empty result from a path that never ran is not evidence
of absence — "no encoder in this image" and "nothing matched" are
different answers. Each result carries matched_by[] and per-path scores,
so you can see WHY it matched.

### `list_open_findings`

```python
list_open_findings(component: str = '', severity: str = '', defect_class: str = '',
    status: str = '', min_age_days: int = 0, max_age_days: int = 0, limit: int = 50) ->
    dict
```

| Parameter | Type | Default |
|---|---|---|
| `component` | `str` | `''` |
| `severity` | `str` | `''` |
| `defect_class` | `str` | `''` |
| `status` | `str` | `''` |
| `min_age_days` | `int` | `0` |
| `max_age_days` | `int` | `0` |
| `limit` | `int` | `50` |

Everything not closed — OPEN, INVESTIGATING and RECURRED — worst first.

RECURRED counts as open because a fix that did not hold is open again.
Ordered by severity, then recurrences, then sightings: the top of this
list is what has hurt most often, not what arrived most recently.

min_age_days / max_age_days filter by age in days since first sighting
(0 means no bound). Each row carries sightings, recurrences and age_days,
all computed at read time — nothing in this store keeps a count.

### `get_finding`

```python
get_finding(finding_id: str) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `finding_id` | `str` | **required** |

One finding in full: every sighting in order, and every refinement made
against it with its relation (ADDRESSES or CLOSES). This is where you look
before changing anything — if a refinement already exists and the finding
recurred, the change that failed is named here.

### `list_defect_classes`

```python
list_defect_classes() -> dict
```

*No parameters.*

The shared vocabulary, with each class's TELL (how it presents) and
PROBE (the command or query that detects it), and how many findings are
open under each.

Read this before recording a finding. A memory rots when one defect is
filed under three synonyms, which is why defect_class is a foreign key.

### `record_refinement`

```python
record_refinement(refinement: dict) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `refinement` | `dict` | **required** |

What you CHANGED, in response to which findings. The server allocates
REF-####.

refinement = {
  target_kind  str REQUIRED  SKILL | AGENT | COMPONENT | GATE | TEST |
                             SCHEMA | DOC | PROCESS
  target       str REQUIRED  named the way its owner names it:
                             skill:dma-surface-production, agent:rectifier,
                             CG-13, apps/mcp/dma_mcp/promote.py
  change       str REQUIRED  what was changed, in prose
  applied_by   str REQUIRED
  finding_ids  [str] REQUIRED  the findings this answers — they must exist
  commit_sha   str \ ONE of these two is REQUIRED: a refinement nobody
  change_ref   str /  can locate is a claim, not a change
  gate_added   str  the gate added in response, so the memory holds the
                    fix beside the defect
  rationale / verification / relation (ADDRESSES | CLOSES)
}

Recording a refinement does NOT close anything. Call resolve_finding for
that — deliberately two steps, because "changed" and "fixed" are two
claims and only the second one can be wrong later.

### `resolve_finding`

```python
resolve_finding(finding_id: str, refinement_id: str, verification: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `finding_id` | `str` | **required** |
| `refinement_id` | `str` | **required** |
| `verification` | `str` | `''` |

Close a finding by naming the refinement that closed it. The refinement
is REQUIRED and there is no way around it: the column is under a CHECK.

Without it, "did the fix hold?" has no subject — and that question is the
only thing this store exists to answer. Pass `verification` (a test name, a
gate id, a probe) when you have one.

### `report_recurrence`

```python
report_recurrence(finding_id: str, measurement: str, reported_by: str, reported_by_kind:
    str = 'QA_AGENT', after_refinement: str = '', measured_value: str = '', note: str =
    '', session_ref: str = '', source_ref: str = '') -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `finding_id` | `str` | **required** |
| `measurement` | `str` | **required** |
| `reported_by` | `str` | **required** |
| `reported_by_kind` | `str` | `'QA_AGENT'` |
| `after_refinement` | `str` | `''` |
| `measured_value` | `str` | `''` |
| `note` | `str` | `''` |
| `session_ref` | `str` | `''` |
| `source_ref` | `str` | `''` |

A finding that was resolved and came back. THIS IS THE SIGNAL THAT
MATTERS — a fix that did not hold is more informative than one that did.

The recurrence is recorded against the refinement BY NAME (defaults to the
one that closed the finding), the finding returns to RECURRED, and that
refinement's `held` flips to false in the digest. `measurement` is required
with the same 30-char floor: a recurrence claim is only as good as the
measurement that saw it come back.

If the finding was never resolved by a refinement, this refuses and tells
you to use record_finding instead — nothing can have failed to hold.

### `get_memory_digest`

```python
get_memory_digest(days: int = 7) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `days` | `int` | `7` |

Everything a weekly refinement pass needs, in one call: what came back,
what is new, which refinements held, which defect CLASSES are still
producing, and what nobody has changed anything about.

Read it in that order. `recurrences_in_window` names the refinements that
did not hold — their targets are where the next change belongs.
`open_by_class` says which SHAPE of defect this build is still producing; a
class with several open findings is a process problem, not several bugs.

## Reviewer feedback

Reviewer verdicts on insight cards, and their route into the findings memory.

### `list_reviewer_feedback`

```python
list_reviewer_feedback(display_id: str = '', ic_id: str = '', run_id: str = '', limit:
    int = 50) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `display_id` | `str` | `''` |
| `ic_id` | `str` | `''` |
| `run_id` | `str` | `''` |
| `limit` | `int` | `50` |

Read reviewer verdicts on insight cards straight from `annotations`,
with the actor and whether each has been ingested into the memory yet.

This is a READ. Invariant 2 constrains the API's writes, not anyone's
reads: no content enters a serving table here and no component gains a
write it did not have.

### `ingest_reviewer_feedback`

```python
ingest_reviewer_feedback(limit: int = 200) -> dict
```

| Parameter | Type | Default |
|---|---|---|
| `limit` | `int` | `200` |

Turn every un-ingested Accept/Reject into memory. Idempotent — run it on
a schedule and again by hand five minutes later; a verdict becomes a
finding exactly once.

A REJECT becomes a finding against the SYNTHESIS SKILL, carrying the card's
own text and its `r_layer`: a verdict with no claim attached teaches
nothing, and it is the recorded reasoning the reviewer refused, not the
headline. An ACCEPT lands as a verdict row (which is what makes the reject
RATE measurable) and, on a card that was previously rejected, as a sighting
saying so.

Returns {ingested, skipped, findings_raised[], problems[], verdict_tally,
reject_rate}. `problems` is never empty for the wrong reason: an
unreadable verdict is left un-ingested and named, not counted as nothing.

---

_33 tools · generated from `apps/mcp/server.py` @ `3e2d5e3bf9`._
