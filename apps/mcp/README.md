# mcp — MCP connector (Python MCP SDK, streamable HTTP)

The only door through which content enters: 13 production tools per TRD;
validation gate families AG/SG/ET/CG + contract pass + evidence pass; the
atomic six-page promote (SELECT … FOR UPDATE, ordered 34-writer registry).
Bundled 384-dim embedding model (CPU, L2-normalised) for the V4 grounding
check at submit — never on the serving path. HNSW index created once at
migration; scoped centroids 0.62/0.58/0.55/0.50; V4 abstains to NOT_RUN
below 5 members.

Deployed as the `mcp` Cloud Run service (session-mode pooling — promote
holds locks).

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
