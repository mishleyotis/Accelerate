"""Regression: medium-priority QA findings (M-4, M-5).

Independent QA (2026-06-06) identified:

M-4: Frontend Dashboard + Directory hard-coded `open_alerts: 0` for
     every entity card because `EntitySummary` didn't carry the field.
     The orange alert chip never lit up on entity cards even when
     /api/v1/alerts returned open rows for that entity.

M-5: Frontend Dashboard read `data.insight_count` via cast; the field
     was never in `DashboardResponse`, so the "Insight cards" KPI always
     rendered "—".

The fixes are minimal:
  - EntitySummary gains `open_alerts: int = 0`, populated by a
    correlated COUNT(*) against `alerts WHERE closed_at IS NULL` in
    the entities-list SQL.
  - DashboardTile.kind union gains `"insight_count"`; the dashboard
    handler emits the tile by running COUNT(*) FROM insight_cards
    JOIN runs WHERE runs.status='ACTIVE'.

This file pins both contracts as static-AST checks (no DB) so
schema drift fails CI Stage 1 loud.
"""
from __future__ import annotations

import inspect

from app.schemas.entities import DashboardTile, EntitySummary

# ── M-4: EntitySummary.open_alerts ────────────────────────────────────


def test_entity_summary_carries_open_alerts() -> None:
    """EntitySummary MUST have an `open_alerts: int` field with a
    default of 0 (so seed fixtures without alerts don't break)."""
    fields = EntitySummary.model_fields
    assert "open_alerts" in fields, (
        "EntitySummary must declare `open_alerts: int`. The frontend "
        "Dashboard + Directory read this verbatim to render the orange "
        "alert chip on entity cards."
    )
    # Pydantic v2: FieldInfo.annotation carries the declared type.
    annotation = fields["open_alerts"].annotation
    assert annotation is int, (
        f"open_alerts must be `int` (no Optional/None), got {annotation!r}"
    )
    default = fields["open_alerts"].default
    assert default == 0, (
        f"open_alerts must default to 0 so entities without any alerts "
        f"yet still serialise cleanly. Got {default!r}."
    )


def test_entities_list_sql_includes_open_alerts_subquery() -> None:
    """The list_entities SQL must include a subquery against the
    `alerts` table that counts open rows per entity. The exact form
    isn't pinned, but the presence of an alerts-table reference IS
    -- without it, open_alerts is always 0 (the schema default) and
    we're back to the pre-fix behaviour."""
    from app.routers import entities as entities_module

    src = inspect.getsource(entities_module.list_entities)
    assert "FROM alerts" in src, (
        "list_entities SQL must SELECT from the `alerts` table to "
        "populate EntitySummary.open_alerts. Without it the field is "
        "always 0 (the schema default) and the alert chip never lights."
    )
    assert "closed_at IS NULL" in src, (
        "The alerts subquery must filter on `closed_at IS NULL` to "
        "count OPEN alerts only -- not the historical total."
    )


# ── M-5: DashboardTile.kind ∋ "insight_count" + handler emits it ───────


def test_dashboard_tile_kind_includes_insight_count() -> None:
    """DashboardTile.kind must accept the literal "insight_count" so
    the frontend Dashboard can find the tile by kind == "insight_count"
    and render its value as the KPI."""
    # Pydantic v2 wraps Literal types as a tuple via typing.get_args.
    from typing import get_args
    kind_field = DashboardTile.model_fields["kind"]
    literals = set(get_args(kind_field.annotation))
    assert "insight_count" in literals, (
        f"DashboardTile.kind missing 'insight_count' literal -- "
        f"frontend KpiCard would render '—' indefinitely. "
        f"Allowed kinds: {sorted(literals)}"
    )


def test_dashboard_handler_emits_insight_count_tile() -> None:
    """The dashboard handler must populate the insight_count tile
    from a real COUNT(*) against `insight_cards`."""
    from app.routers import entities as entities_module

    src = inspect.getsource(entities_module.dashboard)
    assert "insight_count" in src, (
        "dashboard handler must reference `insight_count` (the tile "
        "kind it emits)."
    )
    assert "insight_cards" in src, (
        "dashboard handler must SELECT from `insight_cards` to populate "
        "the insight_count tile. Without it, the tile would render 0 "
        "even when ACTIVE runs have insight_cards rows."
    )
    # The query must scope to ACTIVE runs so superseded runs' cards
    # don't inflate the count.
    assert "ACTIVE" in src, (
        "insight_count query must filter on `runs.status='ACTIVE'` so "
        "superseded runs' cards don't inflate the count. If you removed "
        "the filter, the count will jump every time a re-run lands."
    )
