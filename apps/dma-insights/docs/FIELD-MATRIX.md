# Field matrix — backend Pydantic models ↔ frontend surfaces

Source-of-truth document for the field-level contract between the
FastAPI backend and the standalone production frontend. Maintained
alongside `backend/tests/test_response_shape_standalone_contract.py`
which enforces the critical-field invariants programmatically.

## How to read

Each section names one UI surface (D1 Overview, D3 Heatmap, etc.)
and lists the canonical fields the surface consumes. The contract
columns:

- **Backend field** — name in the Pydantic model
- **Schema** — Pydantic class declaring it
- **Frontend access** — how the standalone reads it
- **Audience** — `all` / `internal` (stripped when `?view=customer`)
- **Test pin** — which test file enforces non-drift

## D1 Overview — `/api/v1/entities/{id}/overview`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `entity_display_id` | `EntityOverviewResponse` | `r.entity_display_id` | all | test_response_shape_standalone_contract |
| `run_request_id` | `EntityOverviewResponse` | `r.run_request_id` | all | test_response_shape_standalone_contract |
| `pillar_scores[]` | `EntityOverviewResponse` | PillarBar component | all | test_response_shape_standalone_contract |
| `pillar_scores[].pillar` | `PillarScoreRow` | bar label | all | test_response_shape_standalone_contract |
| `pillar_scores[].score` | `PillarScoreRow` | bar value | all | test_response_shape_standalone_contract |
| `pillar_scores[].peer_median` | `PillarScoreRow` | tick position | internal | test_audience_strip (peer_median nested-key strip) |
| `pillar_scores[].peer_gap` | `PillarScoreRow` | direction arrow | internal | test_audience_strip |
| `evidence_freshness` | `EntityOverviewResponse` | freshness chip | all | test_response_shape_standalone_contract |
| `intelligence_profile` | `EntityOverviewResponse` | IntelligencePanel | all | test_response_shape_standalone_contract |
| `parser_warnings[]` | `EntityOverviewResponse` | D1 chip + import-audit drilldown | internal | test_audience_strip |

## D2 Insights — `/api/v1/entities/{id}/insights`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `items[]` | `InsightListResponse` | InsightCard renderer | all | test_response_shape_standalone_contract |
| `items[].title` | `InsightCardOut` | chip label | all | test_response_shape_standalone_contract |
| `items[].severity` | `InsightCardOut` | chip color | all | test_response_shape_standalone_contract |
| `items[].what_text` | `InsightCardOut` | modal body | all | n/a |
| `items[].linked_subcap_id` | `InsightCardOut` | subcap drill | all | n/a |
| `narrative` | `InsightListResponse` | narrative panel | internal | test_audience_strip |

## D3 Heatmap — `/api/v1/entities/{id}/heatmap`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `cells[]` | `HeatmapResponse` | heatmap renderer | all | test_response_shape_standalone_contract |
| `cells[].subcap_id` | `HeatmapCell` | cell ID | all | n/a |
| `cells[].score` | `HeatmapCell` | color value | all | test_response_shape_standalone_contract |
| `cells[].peer_median` | `HeatmapCell` | hover tooltip | internal | test_audience_strip |
| `cells[].peer_gap` | `HeatmapCell` | direction | internal | test_audience_strip |
| `cells[].peer_cohort_size` | `HeatmapCell` | thin-cohort caveat | internal | test_audience_strip |
| `catalogue_version` | `HeatmapResponse` | tag | all | test_response_shape_standalone_contract |
| `value_chain_buckets[]` | `HeatmapResponse` | value chain mode | all | n/a |

## D4 Platforms — `/api/v1/entities/{id}/platforms`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `cards[]` | `PlatformsResponse` | platform card grid | all | test_response_shape_standalone_contract |
| `cards[].platform_id` | `PlatformCard` | card key | all | n/a |
| `cards[].fit_score` | `PlatformCard` | fit bar | all | n/a |
| `pillar_offerings` | `PlatformsResponse` | pillar tab | all | test_response_shape_standalone_contract |
| `narrative` | `PlatformsResponse` | narrative panel | internal | test_audience_strip |

## D5 Context — `/api/v1/entities/{id}/context`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `timeline_events[]` | `ContextResponse` | timeline | internal | analyst+ role-gated |
| `firmographics` | `ContextResponse` | firmographics card | internal | analyst+ role-gated |
| `sentiment` | `ContextResponse` | sentiment chip | internal | analyst+ role-gated |
| `narrative` | `ContextResponse` | narrative panel | internal | test_audience_strip |

## D6 Health — `/api/v1/entities/{id}/health`

Analyst+ gated. All fields are internal by definition.

| Backend field | Schema | Frontend access | Audience |
|---|---|---|---|
| `thin_evidence_subcap_ids[]` | `HealthResponse` | safeguard chip | internal |
| `safeguard_gates[]` | `HealthResponse` | gates table | internal |
| `alerts[]` | `HealthResponse` | alerts list | internal |
| `narrative` | `HealthResponse` | narrative panel | internal |

## RAG answer — `/api/v1/rag/answer` + `/stream`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `answer` | `RagAnswerResponse` | chat bubble | all | n/a |
| `citations[]` | `RagAnswerResponse` | hover chips | all | test_sse_streaming_contracts |
| `cited_e_ids` | `RagAnswerResponse` | citation pins | all | test_sse_streaming_contracts |
| `gate` | `RagAnswerResponse` | cost telemetry | all | n/a |
| `model` | `RagAnswerResponse` | cost telemetry | all | n/a |
| `cohort_mode` | `RagAnswerResponse` | scope marker | all | n/a |
| `stale_pct` | `RagAnswerResponse` | stale disclaimer | all | test_sse_streaming_contracts |
| `learning_signal` | `RagAnswerResponse` | "boosted by feedback" | all | test_rag_cohort_and_learning_signal |

## Admin job execution — `/api/v1/admin/jobs/executions`

| Backend field | Schema | Frontend access | Audience | Test pin |
|---|---|---|---|---|
| `id` | `JobExecutionOut` | row key | admin-only | n/a |
| `job_name` | `JobExecutionOut` | job column | admin-only | test_response_shape_standalone_contract |
| `mode` | `JobExecutionOut` | mode column | admin-only | n/a |
| `status` | `JobExecutionOut` | status chip | admin-only | test_response_shape_standalone_contract |
| `started_at` | `JobExecutionOut` | start time | admin-only | n/a |
| `result_summary` | `JobExecutionOut` | result column | admin-only | test_response_shape_standalone_contract |
| `error_count` | `JobExecutionOut` | error badge | admin-only | n/a |
| `error_message` | `JobExecutionOut` | log drawer | admin-only | n/a |
| `stderr_tail` | `JobExecutionOut` | log drawer | admin-only | n/a |

## Auth — `/api/v1/auth/me`

| Backend field | Schema | Frontend access | Audience |
|---|---|---|---|
| `user_id` | `CurrentUserResponse` | sessionStorage hydrate | all |
| `email` | `CurrentUserResponse` | sidebar identity | all |
| `role` | `CurrentUserResponse` | role-gated routing | all |
| `name` | `CurrentUserResponse` | display name | all |
| `can_act_as` | `CurrentUserResponse` | acting-as clamp list | all |

## How to add a new field

1. Add the field to the relevant Pydantic schema in `backend/app/schemas/`
2. Decide its audience: `all` (rendered always) or `internal` (add the key to `INTERNAL_ONLY_KEYS` or `INTERNAL_ONLY_NESTED` in `app/services/audience_strip.py`)
3. Update the corresponding standalone JSX page to read it
4. Add a row to this file
5. If the field is "critical" (its absence breaks rendering), add an assertion to `tests/test_response_shape_standalone_contract.py`

## Maintenance contract

- This file is verified to exist by `test_response_shape_standalone_contract.py::test_field_matrix_doc_exists`.
- The audience column is enforced by `test_audience_strip.py` + the per-router strip tests.
- The role-gating column is enforced by `test_e2e_routes.py::test_every_route_is_either_public_or_auth_gated`.
