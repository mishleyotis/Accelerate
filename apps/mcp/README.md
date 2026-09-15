# mcp — MCP connector (Python MCP SDK, streamable HTTP)

The only door through which content enters: 23 production tools — the TRD's
original 15 plus those added since (the fit engine, staged-payload reads,
withdrawal, the enrichment ledger, gate explanation) — and the 11 memory and
feedback tools below, 34 in all;
validation gate families AG/SG/ET/CG + contract pass + evidence pass; the
atomic six-page promote (SELECT … FOR UPDATE, ordered 34-writer registry).
Bundled 384-dim embedding model (CPU, L2-normalised) for the V4 grounding
check at submit — never on the serving path. HNSW index created once at
migration; scoped centroids 0.62/0.58/0.55/0.50; V4 abstains to NOT_RUN
below 5 members.

Deployed as the `mcp` Cloud Run service (session-mode pooling — promote
holds locks).

## Chunked payload transport (MEM-0030)

`submit_page_payload` used to take the payload as one inline JSON object, so a
producing agent had to emit a whole page as literal tokens in a single tool
call. A contract-complete heatmap does not fit. Measured 2026-08-08 by two
independent producers: **Frost Bank 1,128,742 bytes** compact (~282k tokens),
`cell_evidence` alone **862,351 across 697 served cells**; **Fisher Investments
heatmap 1,598,147**, `cell_evidence` **1,208,289 across 708 cells** — and the
barest still-compliant reduction of that section still measured 347,509.

Rule 17 wants a drawer row for every served cell, so that is the contract's
size, not an authoring choice. It also explains the reference client:
`baxter-credit-union-bcu` serves **69 `cell_evidence` rows out of 765 cells —
9%**, on a clean verdict. That was never a synthesis decision; it is what fit.

| tool | for |
|---|---|
| `open_payload` | open a chunked upload; the CONNECTOR allocates the `upload_id` (invariant 10) and binds it to one run and one page |
| `append_payload_part` | one part: `fields={…}` shallow-merges an object at a dotted path, `items=[…]` appends to the list there. Returns a receipt, never a verdict |
| `submit_page_payload(upload_id=…)` | assemble server-side, then validate and stage exactly as an inline payload |

Two transports, **one validation**. Past the point where `payload` is in hand
the code is transport-blind: `validate_pass1` and `validate_pass2` run over the
assembled whole byte-for-byte as they always have. The two gates this added,
CG-16 (the received part set is exactly `{1..parts_total}`) and CG-17 (a
declared assembled length matches), judge whether the payload ARRIVED and never
what it says — they fire before any submission row exists, so an incomplete
transmission is unsubmittable rather than merely invalid. Resending a part
index replaces it; a dropped connection costs one part, not the transmission.

**Rejected: a by-reference submit** (producer writes to GCS, connector reads).
It does not reduce what the producer must emit — the bytes are written either
way — it needs the producer to hold a bucket credential the connector would
then trust, which is invariant 2 read backwards, and the practical form of that
credential is a signed URL, i.e. a secret in a URL that lands in transcripts
and request logs. `dmai-mcp` also holds only `objectViewer` on the artefact
bucket, with `dmai-worker` provisioned as its only writer.

`get_page_contract(page)["transport"]` states the limits, the step list and the
measured sizes, so the next producer reads the ceiling off the contract instead
of discovering it by building 1.6 MB and failing. Tables: migration 0040
(`payload_uploads`, `payload_upload_parts`, `svc_mcp` only).

## The findings memory (11 further tools)

`dma_mcp/memory.py` and `dma_mcp/feedback.py` hold the store of what went
wrong, how it was measured, what was changed about it and whether the change
held — tables in migrations 0034/0035. These tools write no serving content
and stage no page; they exist for agents:

| tool | for |
|---|---|
| `record_finding` | report a defect. Idempotent by content hash — one defect, many sightings |
| `search_findings` | "have we seen this before" — lexical, semantic and trigram, each path named |
| `list_open_findings` | everything not closed, worst first (RECURRED counts as open) |
| `get_finding` | one finding with every sighting and every refinement against it |
| `list_defect_classes` | the shared vocabulary, with each class's tell and probe |
| `record_refinement` | what changed, where, in response to which findings, with the sha |
| `resolve_finding` | close a finding by NAMING the refinement that closed it |
| `report_recurrence` | a fix that did not hold, recorded against the fix by name |
| `get_memory_digest` | one call for a weekly refinement pass |
| `list_reviewer_feedback` | reviewer Accept/Reject verdicts, straight from `annotations` |
| `ingest_reviewer_feedback` | turn every verdict into memory, carrying the card and its `r_layer` |

Two rules the schema enforces rather than the prose: a finding cannot be
stored without saying **how it was measured**, and cannot be closed without
naming the **refinement** that closed it. Recurrence is the signal that
matters, so it is the one thing recorded against a named change.

Embedding happens at RECORD time, inside this service, with the same model
V4 uses at submit (`EMBED_MODEL_DIR=/model`, baked into the image by the
Dockerfile — not a deploy-time env var). Invariant 1 forbids a model call on
the SERVING request path; this is not one. Both paths are live in production:
`search_findings` returned `paths_run: ['lexical','semantic']` on the first
query after seeding. Where a path cannot run it is named in `paths_skipped`
with its reason rather than silently absent — an empty result from a path
that never ran is not evidence of absence.

Seed the store with `python3 apps/mcp/seed_memory.py` (through the deployed
connector) or `--direct` against a local database.
