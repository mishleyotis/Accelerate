# TOOLS SPEC — Axis I — 28-09-2026 · dma-insights 1.20.0

## Existing custom surface
- DMA Insights MCP server: 34 tools (`apps/mcp/server.py`), ≈6.7k schema tokens, 21 read / 13 write, 0 tools unnamed by any skill or agent. Ungrouped on one server (>25). Near-duplicates: `list_open_findings` / `search_findings` / `get_finding`; `get_validation_verdict` overlaps `get_run_progress.blocking`. Missing read-your-own-writes: no `list_submissions(run_id, page)` (submission history per page), no `list_claims`, no `list_promotions`.
- Engine CLI (`engine.cli` plus 19 delegated families, 38 subcommands): most candidates below already exist as commands. The gap is wiring, not tools.

## Repeated mechanical actions (measured from the evidence available; no run transcripts on disk)
| action | evidence of repetition / error | existing tool | status |
|---|---|---|---|
| score adjustment arithmetic | 1 of 3 independent scorers slipped 3.0 − 0.3 (F-14) | none; `engine.assessment score` takes the final figure | NEW `score_apply` |
| verifying a synthesis claim against stored excerpts | 12 of 67 claims unsupported in 30 cells (D-04) | `quality` pinpointer checks numbers only | NEW `verify_claim` |
| CG-27 / CG-11 / CG-15 pre-checks | 199 refusals on one page; 28% caught locally | self_heal.py, check_language.py | EXTEND with CG-15 |
| declaring an absence with its ladder | 61 of 102 cells absent; 119 shared eight-word spans | `engine.cli absence` + hand-written synthesis | NEW `absence_project` |
| chunk planning for submit | parts of 131072 B; `expect_of` per list | ship_page.py | EXISTS (keep) |
| evidence re-registration | no local id map | server dedup only | NEW `evidence_id_map` |
| reading rejections and progress at session start | 200 open rejections unnoticed | list_open_rejections | EXISTS; needs the hook |
| handoff validation | no version field on the packet | none | NEW `handoff_validate` |
| template drift | tools exist, unwired | engine.template drift / report_drift / gold_standard | EXISTS; needs the hook |
| registry read/update | engine.registry log / beat / close / list | exists | EXISTS |
| checkpoint and resume | engine.assemble checkpoint; engine.cli resume | exists | EXISTS |
| log_search / evidence_register refusing unlogged retrieval | engine.cli search / evidence; excerpt_unverified refusal | exists | EXISTS |
| query cache lookup | none | Search_Log | NEW `query_cache_lookup` (as a ledger refusal) |
| recency compute | ledger.recency_band | exists; quarter dates unparsed | EXTEND |
| gate_check single entry point | engine.cli gate / engine.assessment gate / gold_standard / run_gate.py | four entry points | CONSOLIDATE as `gate_check` |
| cost_estimate → approval token | Vibe estimate-cost; engine.cost.schedule | partial | NEW `cost_estimate` |
| placeholder sweep / terminology density / agnostic lint | gold_standard hedges; check_language | partial | keep |
| entity_resolve across connectors | none (Indeed company filter unguarded) | — | NEW (LOW) |
| gap_dossier_write / proxy_brief_compose | engine.cli absence; engine.relay batch | partial | EXTEND absence with facets_status + validation_question; relay batch states prior queries |
| payload_project / payload_validate_local / submission_plan | surface_export.scaffold; self_heal; ship_page | exist | EXTEND validate_local with CG-15 |

## Specs
| name | signature | input → output | replaces (prose) | called by | proving test |
|---|---|---|---|---|---|
| `score_apply` | `engine.assessment apply --raw 3.0 --ceiling 5.0 --adj -0.3 [--cap …]` | numbers → `{final, band, arithmetic: "3.0-0.3=2.7"}`; band from `contract.band_of` | dma-assessment "final = min(raw, ceiling, caps) ± ADJ" | scoring-p*-producer before `engine.assessment score` | F-14 rerun: 3 of 3 identical finals |
| `verify_claim` | `engine.cli verify-claim --run R --subcap S --claim "…"` | claim + stored excerpts → `{verdict: entailed / partial / not_supported, span, e_id}` (lexical + number match; PARTIAL escalates to the model) | "check each claim against its stored excerpt" | heatmap-evidence-producer, finding-challenger | D-04 sample: ≥90% flagged before submit |
| `absence_project` | `engine.surface_export absence --run R --cells …` | Search_Log ladder per cell → deterministic `sources_searched[]`, `closure_condition`, `thin: true`, synthesis frame naming the cell's own artefact from the catalogue | 700 hand-written absence syntheses | heatmap-evidence-producer | local CG-15 check reports 0 shared claim spans |
| `payload_validate_local` (extend) | `self_heal.py … --cg15` | payload → CG-15 shared-span + vocabulary check mirroring validation2 | "read CG-15 before writing seven hundred of these" | precheck_submit hook | catch rate ≥80% on the goeasy replay |
| `evidence_id_map` | `engine.ship idmap --run R` | 07_qa/evidence_id_map.json {content_hash: server_id}; read before register_evidence | "register once" | ship_page, register step | 0 duplicate registrations on resubmit |
| `handoff_validate` | `engine.cli handoff --validate` | packet → schema_version, sha256, completeness verdict; consumer refuses mismatch | dma-research SKILL.md:798 contract | assessment open; PostToolUse hook | F-05 refuses naming "corrupt JSON" |
| `query_cache_lookup` | inside `ledger.append_search` | normalised query → existing row id or new | "check the log before searching" | engine.cli search; PreToolUse warn | C-8c: second identical query refused |
| `gate_check` | `engine.gate <gate_id> --run R` | one entry over floors / scoring / template / gold / local CG | four entry points | hooks, driver | every gate id in docs resolves to a runner (extend gen_gates_md --check) |
| `cost_estimate` | `engine.cost estimate --tool enrich-business --n 50` | → `{usd, token}`; the token file is consumed by the credit hook | "quote cost first" | credit PreToolUse hook | spend hook denies without a token |
| `list_submissions` (server) | `list_submissions(run_id, page)` | → [{submission_id, status, producer_version, submitted_at, rejections_opened, rejections_closed}] | none | promotion replay, O-03 | O-03 measurable |

Consolidation: group the 34 server tools as `read.*` (21), `write.*` (13, 11 after moving `record_finding` / `record_refinement` behind qa-overseer) and `workflow.*` (claim, open / append / submit, promote, withdraw); fold `get_validation_verdict` into `list_submissions`.
