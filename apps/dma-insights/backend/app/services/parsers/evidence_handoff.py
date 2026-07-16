"""Evidence handoff JSON parser.

When the analyst leaves an `app_payload_v1.json` in the DMA Drive folder,
its parse takes precedence over the research-workbook ingest on E-ID
conflict (per plan §① — "json wins").

The schema is `AppPayloadV1` (the same one the Claude project posts back
to `/ingest/assessment`). Here we accept the file from disk, validate, and
emit a `HandoffParseResult` ready to feed the ingest service.

State-branch contract:
  - File missing                  → caller decides; this fn is invoked by
                                    `drive_crawler` only when classify
                                    returns `evidence_handoff_json`.
  - File present but malformed JSON → HandoffParseResult.errors logged.
  - File valid JSON but bad shape  → pydantic ValidationError surfaced.
  - File valid                     → rows populated, warnings reflect any
                                    non-fatal anomalies (e.g. linked_e_ids
                                    that point at evidence not in this file).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.schemas.ingest import AppPayloadV1


@dataclass
class HandoffParseResult:
    payload: AppPayloadV1 | None = None
    rows_by_kind: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.payload is not None and not self.errors


def parse_handoff_text(text: str) -> HandoffParseResult:
    """Parse a JSON text blob into the canonical rowsets.

    Pure: no IO. The caller (drive_crawler / report_parser) reads the file
    contents and passes them in.
    """
    result = HandoffParseResult()
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        result.errors.append({"kind": "json_decode", "detail": str(e)})
        return result
    try:
        payload = AppPayloadV1.model_validate(raw)
    except Exception as e:  # pydantic ValidationError, etc.
        result.errors.append({"kind": "schema_validation", "detail": str(e)[:500]})
        return result

    result.payload = payload

    # Materialize per-kind row dicts so ingest can bulk insert without
    # re-walking the pydantic model.
    result.rows_by_kind["subcap_scores"] = [
        sc.model_dump(mode="json") for sc in payload.subcap_scores
    ]
    result.rows_by_kind["evidence"] = [
        ev.model_dump(mode="json") for ev in payload.evidence
    ]
    result.rows_by_kind["insights"] = [
        ic.model_dump(mode="json") for ic in payload.insights
    ]
    result.rows_by_kind["recommendations"] = [
        rec.model_dump(mode="json") for rec in payload.recommendations
    ]
    result.rows_by_kind["focus_areas"] = [
        fa.model_dump(mode="json") for fa in payload.focus_areas
    ]
    result.rows_by_kind["issue_register"] = [
        ir.model_dump(mode="json") for ir in payload.issue_register
    ]
    result.rows_by_kind["timeline_events"] = [
        te.model_dump(mode="json") for te in payload.timeline_events
    ]
    result.rows_by_kind["tech_stack"] = [
        ts.model_dump(mode="json") for ts in payload.tech_stack
    ]

    # Non-fatal: insight.linked_e_ids that don't appear in payload.evidence
    known_e_ids = {ev.e_id for ev in payload.evidence}
    for ic in payload.insights:
        for eid in ic.linked_e_ids:
            if eid not in known_e_ids:
                result.warnings.append({
                    "kind": "ic_links_unknown_evidence",
                    "ic_id": ic.ic_id,
                    "missing_e_id": eid,
                })

    # Non-fatal: recommendation.target_subcap_ids that don't appear in
    # subcap_scores (typically because the recommendation aspires to a
    # not-yet-scored subcap)
    known_subcap_ids = {sc.subcap_id for sc in payload.subcap_scores}
    for rec in payload.recommendations:
        for sid in rec.target_subcap_ids:
            if sid not in known_subcap_ids:
                result.warnings.append({
                    "kind": "rec_targets_unscored_subcap",
                    "rec_id": rec.rec_id,
                    "subcap_id": sid,
                })

    return result
