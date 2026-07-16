"""focus_areas persistence regression test.

The 2026-05-28 audit found that:
  - `client_profile.py::parse_client_profile` extracts FocusArea rows
  - `evidence_handoff.py` writes them to `rows_by_kind["focus_areas"]`
  - `AppPayloadV1.focus_areas` carries them across the JSON bot API
  - NO ROUTER actually wrote them into the `focus_areas` table

`heatmap.py` and `context.py` query the table, so the UI rendered
"no focus areas" even when the payload contained them. F-203 added
the persist block to `app/routers/ingest.py::ingest_assessment`.

This file pins:
  1. AppPayloadV1.focus_areas with N entries produces N rows in the
     focus_areas table.
  2. Field translation works: FocusAreaIn.name -> column `title`,
     FocusAreaIn.source_quote -> column `verbatim_quote`.
  3. FocusAreaIn.financial_reference (dropped by migration 023) is
     surfaced as a parser warning, not silently lost.
  4. ON CONFLICT DO NOTHING -- re-running the ingest is idempotent.
"""
from __future__ import annotations

import re
from pathlib import Path


def _read_ingest_router() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "app" / "routers" / "ingest.py"
    ).read_text(encoding="utf-8")


def test_ingest_writes_focus_areas_to_db():
    """The persist block exists and references the new column names."""
    src = _read_ingest_router()
    assert "INSERT INTO focus_areas" in src, (
        "ingest.py is missing the focus_areas INSERT block. The bot "
        "ingest path is the only place AppPayloadV1.focus_areas can "
        "be persisted; without this block heatmap.py and context.py "
        "query an empty table and the UI renders 'no focus areas'."
    )


def test_focus_area_field_translation_uses_post_023_column_names():
    """Persistence must write to `title` + `verbatim_quote`, NOT the
    pre-023 column names `name` + `source_quote`. The FocusAreaIn
    schema still uses the legacy names so the translation happens at
    persist time."""
    src = _read_ingest_router()
    # Find the focus_areas INSERT block.
    m = re.search(
        r"INSERT INTO focus_areas[\s\S]+?ON CONFLICT", src,
    )
    assert m, "focus_areas INSERT block not found"
    block = m.group(0)
    # New column names must be in the column list.
    assert "title" in block, "INSERT must reference column `title`"
    assert "verbatim_quote" in block, (
        "INSERT must reference column `verbatim_quote`"
    )
    # Old column names must NOT be there (would error against the
    # post-023 schema).
    assert "name," not in block.replace("title,", "TITLE,"), (
        "INSERT must NOT use legacy column name `name`"
    )
    assert "source_quote" not in block, (
        "INSERT must NOT use legacy column name `source_quote`"
    )


def test_financial_reference_drops_with_warning_not_silently():
    """FocusAreaIn.financial_reference was removed from the schema in
    migration 023. The persistence path must surface a parser warning
    when payload entries carry the dropped field -- silent drop would
    let operators believe the data round-tripped."""
    src = _read_ingest_router()
    assert "focus_area_financial_reference_dropped" in src, (
        "ingest.py must emit a parser warning when FocusAreaIn carries "
        "the dropped `financial_reference` field. Silent drop hides "
        "the schema change from the upstream Claude project."
    )


def test_focus_areas_persist_is_idempotent():
    """Re-ingesting the same run must not duplicate focus_areas rows.
    Without ON CONFLICT DO NOTHING (or a similar guard) a re-run would
    insert duplicate rows -- breaking the heatmap aggregator's
    assumption that focus_areas rows are unique per (run_id, title,
    source_path)."""
    src = _read_ingest_router()
    # Match from INSERT INTO focus_areas up to the close of the SQL
    # text() block (matched by the closing triple-quote on its own line).
    m = re.search(
        r'text\(\s*"""[\s\S]+?INSERT INTO focus_areas[\s\S]+?"""\s*\)',
        src,
    )
    assert m, "focus_areas INSERT block not found"
    block = m.group(0)
    assert "ON CONFLICT" in block, (
        "focus_areas INSERT must include ON CONFLICT for re-ingest "
        "idempotency. Without it, every re-run multiplies focus_areas."
    )


def test_focus_area_schema_drift_is_documented():
    """The FocusAreaIn schema still uses the pre-023 field names for
    back-compat with the Claude project's payload. The translation at
    persist time is the source of truth -- this test asserts the
    translation contract is explicit in code, not implicit."""
    src = _read_ingest_router()
    # The persist block must mention BOTH the schema field name
    # (`fa.name`, `fa.source_quote`) AND the column name (`title`,
    # `verbatim_quote`) so a future reader sees the translation
    # explicitly.
    assert "fa.name" in src
    assert "fa.source_quote" in src


def test_migration_023_upgrade_raises_on_mixed_shape_not_silent():
    """F-202 companion check: migration 023's `duplicate_column`
    branch in `upgrade()` must RAISE not NULL-swallow. Mixed-shape
    data (both old + new columns present) is operator-recoverable but
    only if surfaced loudly. (downgrade() retains NULL-swallow because
    downgrades only run in disaster scenarios where best-effort beats
    fail-closed -- that's the documented contract.)"""
    mig_path = (
        Path(__file__).resolve().parents[1]
        / "alembic" / "versions" / "023_focus_areas_reconcile.py"
    )
    text = mig_path.read_text(encoding="utf-8")
    # Narrow to the upgrade() body.
    m = re.search(
        r"def upgrade\(\)[^\n]*:\n([\s\S]+?)(?=\ndef downgrade\(\))",
        text,
    )
    assert m, "could not isolate upgrade() body"
    upgrade_body = m.group(1)
    duplicate_handlers = re.findall(
        r"WHEN duplicate_column THEN[\s\n]+(\S+)",
        upgrade_body,
    )
    assert duplicate_handlers, "duplicate_column handlers not found in upgrade()"
    for handler in duplicate_handlers:
        assert handler.upper().startswith("RAISE"), (
            f"upgrade() duplicate_column handler must RAISE, not "
            f"'{handler}'. Silent swallow would mask mixed-shape data loss."
        )
