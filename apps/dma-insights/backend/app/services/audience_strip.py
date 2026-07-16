"""Audience-strip: server-side rule that removes internal-only fields from
any response when the request is `?view=customer`.

Frontend hides D5/D6 tabs, but that's defense-in-depth only — this layer is
the source of truth. Any new internal-only field must be added here.
"""
from __future__ import annotations

from typing import Any

# Top-level keys that are removed entirely when audience='customer'.
INTERNAL_ONLY_KEYS: frozenset[str] = frozenset(
    {
        "context",
        "health",
        "alerts",
        "safeguard_gates",
        "data_gaps",
        "internal_notes",
        "ers",  # evidence rationale shorthand
        "annotations_internal",
        "feedback_internal_only",
        "ops_history",
        # parser_warnings expose ingest-time structural issues — fine for
        # AE/Analyst/Admin but never appropriate for customer-facing share.
        "parser_warnings",
        # 2026-05-28 audit fix: peer-cohort scores + benchmarks are
        # commercially sensitive (we'd be telling a customer "here's
        # how your peers scored on the same DMA"). Stripped from every
        # `?view=customer` response across all surfaces (overview,
        # heatmap, insights drilldowns).
        "peer_benchmarks",
        "peer_internals",
        # 2026-07-02 D1 deep surfaces: capability ceilings + their internal
        # rationale are analyst estimates (never customer-appropriate), and
        # the sentiment scorecard is internal-only per the prototype.
        "uncertainty_bands",
    }
)

# Nested keys to strip wherever they appear (drawer payloads, etc.).
INTERNAL_ONLY_NESTED: frozenset[str] = frozenset(
    {
        "rationale_internal",
        "analyst_note",
        "drive_url",
        "ops_sheet_row_url",
        "internal_subcap_score_history",
        # 2026-05-28 audit fix: per-subcap peer fields are inlined in
        # heatmap cells + PillarBar rows, so the top-level
        # peer_benchmarks strip above doesn't reach them. Listing them
        # here ensures every nested dict that surfaces a peer metric
        # has it removed for customer audience.
        "peer_median",
        "peer_gap",
        "peer_delta",
        "peer_cohort_size",
        # nested in firmographics — the internal-only sentiment scorecard.
        "sentiment",
    }
)


def strip_internal(obj: Any, audience: str) -> Any:
    """Recursively strip internal-only fields from a JSON-safe object."""
    if audience != "customer":
        return obj
    if isinstance(obj, dict):
        return {
            k: strip_internal(v, audience)
            for k, v in obj.items()
            if k not in INTERNAL_ONLY_KEYS and k not in INTERNAL_ONLY_NESTED
        }
    if isinstance(obj, list):
        return [strip_internal(v, audience) for v in obj]
    return obj


def strip_and_respond(payload: Any, audience: str, response_model: type):
    """Apply audience-strip then return a wire-correct response.

    The naive pattern — `Model.model_validate(strip_internal(...))` —
    has a subtle bug: when `audience == 'customer'`, the strip REMOVES
    internal-only keys from the dict, but `model_validate` re-builds
    the model with `None` defaults for every optional field, so the
    JSON response surfaces `"parser_warnings": null`,
    `"peer_benchmarks": null`, etc. That defeats the customer-audience
    contract (`not.toHaveProperty(...)` still fails because the key is
    present, just null). This was a recurring class — every router that
    audience-stripped + revalidated leaked nulls for every stripped
    field.

    Contract:
      audience='customer' → JSONResponse(stripped_dict) — bypass schema
                            revalidation; the stripped keys stay GONE.
      audience='ae'/...   → response_model.model_validate(payload_dict)
                            — schema enforcement intact for internal
                            audiences.
    """
    from fastapi.responses import JSONResponse
    # Accept either a Pydantic model or an already-dumped dict.
    as_dict = (
        payload.model_dump(mode="json")
        if hasattr(payload, "model_dump")
        else payload
    )
    stripped = strip_internal(as_dict, audience)
    if audience == "customer":
        return JSONResponse(content=stripped)
    return response_model.model_validate(stripped)
