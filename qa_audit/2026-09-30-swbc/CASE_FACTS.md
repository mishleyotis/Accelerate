# CASE FACTS — SWBC live-run QA (2026-09-30)

Persistent block. Updated as the run proceeds; every issue gets an ID and a status.

## Engagement
- Entity: SWBC (multi-LOB; hybrid DMA). Scope doc: Google Doc 1d4_FeFork3CVpTFc0JIoLKTTiFQeKmQ-oo3qanKBQgQ
- Fresh run. Branch: ccr-bcc99dc1-pabayz. Plugin version at start: 1.20.0
- Prior audit: qa_audit/2026-09-28 (structural; 42/43 fixed, F-H01-038 REPRODUCED)

## Objectives under test
- O1 Efficient research, token economy, auto-approved tools (few prompts)
- O2 Research ↔ web-app submission contract; heatmap evidence linkage built as research progresses; per-pillar parallel workflow, one per category (4×4)
- O3 Synthesis + all output artifacts match the gold-standard templates

## Environment facts
- claude CLI 2.1.285 present; gcloud absent; identity from the routine SA key file (dmai-routine@) — doctor OK
- Connector live: 34 tools; unauth probe -> 401 (enforced)
- Run root: /home/user/dma-runs/swbc ; toolkits: /home/user/dma-runs/toolkits (pulled from Drive, 2026-05-04 copies)
- Connector baseline written from session tools: clay, drive, exa, explorium, indeed, tavily present; quartr absent (optional)
- Server state for swbc: 1 prior run 7968492e (INGESTED 2026-09-11, v7.0, composite 2.01, 418 scored cells of 851); entity_name/sub_vertical/size_tier NULL; 6 facets enriched_not_promoted, peer_scores never_enriched
- Scope doc: multi-LOB (FIG/Institutional, Insurance P&C+benefits, Mortgage, Wealth, Swivel payments); hybrid mode; sponsor Angelica Palm (CMO)

## Binding (owner-confirmed 2026-09-30)
- Primary IB; supplementary IC, CL, RIA (variant cells only); HYBRID; FULL; 760 cells
- Internal doc landed: 01_intake/SWBC_Context_for_DMA_2026-09.md sha e024e3d4

## Issues register
| ID | Obj | Sev | Where | What | Status |
|---|---|---|---|---|---|
| I-01 | O1 | HIGH | apps/mcp/server.py list_pending_runs | Returns every pending run corpus-wide: 354 rows / 157 KB / 5,018 lines, 162 superseded; no display_id filter, no latest-only, no limit. One routine call overflows the tool-result budget. | OPEN |
| I-02 | O2 | HIGH | commands/run-assessment.md s1; engine.pipeline env | Toolkits (per-subcap diagnostic questions) never fetched: env shows toolkits ok:false as a soft row, command never mentions drive_fetch.py pull-toolkits; KG silently degrades to 71 category-level questions. | OPEN |
| I-03 | O1/O2 | HIGH | scripts/route_client.py; run-assessment s2 | No way to request a fresh/versioned run: any scored cell => READY_TO_SYNTHESISE and the command says stop. Existing run has 418/851 cells (49%) and NULL entity_name/sub_vertical, yet routes synthesis-ready - no coverage check. | OPEN |
| I-04 | O1 | LOW | doctor skill script dependencies | Fresh container: jsonschema missing; doctor fails until dma-deps install is run by hand (fix line present). | NOTED |
| I-05 | O1/O2 | MED | scripts/hooks/deny_credential_ops.py | Docs-URL rule denied any MENTION of a Google Docs URL as 'a shell fetch' - blocks --source-url/--url provenance for internal evidence in every HYBRID lane. Key-file rule also fires on mentions (kept: security control, low cost). | FIXED (fetch-only match; 8 regression cases) |
| I-06 | O2 | HIGH | engine/contract.py selected(); preflight binding | Multi-LOB entity could bind only ONE sub-vertical; other accepted LOBs' variant cells never researched. Owner decision: primary IB + supplementary IC/CL/RIA variant cells only, additive, no universal re-research. | FIXED (binding.supplementary_sub_verticals; SWBC 694 -> 760 cells) |
| I-07 | O1 | MED | engine/preflight.py skeleton | Row shapes lived in Python comments that json.dump drops; first fill refused 10 rows for unseen keys (source_name, implies_lob, lob, basis). | FIXED (_row_shapes in file) |
| I-08 | O2 | HIGH | engine/contract.py selected() + workbook seed guard | 38 of 165 variant cells (23%) carry bare tier T2; selector matched on tier label so they were unreachable for EVERY binding (IB lost 4: P1C1.4.IB1, P1C2.9.IB1, P4C1.9.IB1, P4C3.8.IB1). Seed guard also let them through unowned. | FIXED (sub_vertical_of from id suffix; all 165 resolve) |
| I-09 | O2 | HIGH | engine (no intake), run-assessment, SKILL.md | HYBRID mode was a label: 01_intake existed only in SKILL prose; lanes never told where internal docs are; no gate checks an internal citation exists. | FIXED (engine/intake.py; PREFLIGHT refuses empty intake; shared brief lists docs; HANDOFF refuses 0 internal rows) |
| I-10 | O3 | HIGH | engine/assemble.py open_folder; scripts/drive_fetch.py | Supersede checked only the LOCAL folder: fresh container reported "no previous package" while Drive root held the 2026-09-11 package (workbook, 2 reports, deck, handoff, preflight); push then OVERWROTE the prior run_manifest.json. Package scan would pick between two workbooks. | FIXED (drive_fetch archive-remote; open_folder calls it before first push; SWBC's 6 prior items moved to _superseded/prior-package_2026-09-16, 0 failed) |
| I-11 | O1 | MED | scripts/hooks/deliverable_gate.py | Gate denied EVERY push-package, including preflight.json that run-assessment step 3 instructs before any gold verdict can exist. | FIXED (working files exempt when both --file and --name are working files; 7 cases) |
| I-12 | O1 | MED | engine/cost.py; run-assessment s4 | `engine.cost estimate --run --root` (as documented) errors; the flag-less estimate priced the default selection (694) not the run (760). lane-fit joined root/run_id and crashed. | FIXED (estimate reads the run: $13.80 levered / $20 budget; lane-fit root fixed) |
| I-13 | O2 | MED | lane budget (340 turns) | P2C2 (353t) and P2C3 (345t) exceed a lane even at capability grain once supplementary variants are added -> guaranteed cold re-dispatch. | OPEN |
| I-14 | O1/O2 | MED | engine/cost.py schedule vs agent_run capacity | Schedule promises 16 parallel lanes / 34 min research; host cap is 8 lanes (4 CPU x 2) so research runs in 2 waves. | OPEN |
| I-15 | O1 | LOW | scripts/bootstrap_session.sh | Write(path) allow rules are ignored by Claude Code and print 3 warnings into every headless lane log; Edit rules already cover writes. | FIXED |
| I-16 | O1 | NOTE | engine.cost levers | Levered estimate applies x0.0169 to measured cost ($817 -> $13.80); to be checked against the real ledger. | WATCH |
