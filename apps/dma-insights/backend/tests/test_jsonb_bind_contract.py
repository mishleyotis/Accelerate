"""Regression: every async-path INSERT/UPDATE that binds a JSONB column
MUST cast the bind via `CAST(:x AS JSONB)`.

asyncpg requires JSONB bind values to be already-serialized strings:

    asyncpg.exceptions.DataError: invalid input for query argument $N:
    [{'name': '…'}] ('list' object has no attribute 'encode')

The CAST(:x AS JSONB) signal forces the engineer to serialize the bind
value (otherwise the SQL is just `col = :x` and asyncpg can't tell what
shape `:x` should be sent as → it tries to encode the raw Python object
and crashes). Once the CAST is present, the dev must also json.dumps the
bind value — they will discover that at first run; this static check
catches the CAST omission BEFORE first run.

History (2026-06-04 deployment QA, all caught here after the bugs landed
in prod):
  - `firmographics.leadership` → AlmaBank ingest 500'd
    (fixed in `parsers/package_persist.py`)
  - `firmographics.{leadership,thought_leadership}` → clay webhook bug
    (fixed in `routers/clay.py`)
  - `runs.{scqa, why_now_signals, top_findings}` → bot-loop ingest bug
    in `routers/ingest.py` that crashed the
    `dma-insights-historical-backfill` Cloud Run Job repeatedly

If this test fails on a new file/line, audit the SQL: ensure every
JSONB column you bind to appears as `CAST(:bind AS JSONB)` in the
INSERT VALUES or UPDATE SET clause AND that the bind dict entry is
`"bind": json.dumps(value)` (or `None` when always-NULL).
"""

from __future__ import annotations

import pathlib
import re

import pytest

# JSONB columns across the live schema (collected from
# alembic/versions/). When a new JSONB col lands, add it here so the
# guard stays comprehensive.
JSONB_COLUMNS = {
    "after_json", "args", "batch_history", "before_json", "blob",
    "bot_payload", "bot_response", "diff_vs_prior_version", "flags",
    "hallucination_flags", "leadership", "materials_gs_urls",
    "mode_evidence_json", "output_json", "page_context", "parse_warnings",
    "parser_warnings", "poll_progress", "prerequisite_checks",
    "response_json", "response_schema", "retrieval_bundle", "scqa",
    "sentiment", "source_files", "source_sha256s", "summary",
    "thought_leadership", "top_findings", "uplift_per_pillar",
    "validation_report", "value", "why_now_signals",
}

# Files whose execute() calls go through asyncpg (the async session
# factory). Sync paths (workers using create_engine + psycopg3) handle
# dict/list natively and aren't covered here.
ASYNC_PATH_FILES = [
    "app/services/parsers/package_persist.py",
    "app/routers/ingest.py",
    "app/routers/clay.py",
    "app/routers/runs_new.py",
    "app/routers/rag.py",
    "app/services/chat_persistence.py",
    "app/services/post_commit_workers.py",
    "app/scripts/historical_backfill.py",
]


def _backend_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parents[1]


def _strip_on_conflict(sql: str) -> str:
    # Drop ON CONFLICT … clauses; EXCLUDED.col patterns are not binds
    # so they don't need the CAST treatment.
    m = re.search(r"\bON\s+CONFLICT\b", sql, re.IGNORECASE)
    return sql[: m.start()] if m else sql


def _find_sql_blocks(src: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    pattern = re.compile(r'text\(\s*"""(.+?)"""\s*\)', re.DOTALL)
    for m in pattern.finditer(src):
        ln = src[: m.start()].count("\n") + 1
        out.append((ln, m.group(1)))
    return out


def _audit_insert(rel_path: str, ln: int, sql: str) -> list[str]:
    failures: list[str] = []
    ins = re.search(
        r"INSERT\s+INTO\s+\w+\s*\(([^)]+)\)\s*VALUES\s*\(([\s\S]+?)\)\s*(?:RETURNING|$)",
        sql, re.IGNORECASE,
    )
    if not ins:
        return failures
    cols = [c.strip() for c in ins.group(1).split(",")]
    vals = [v.strip() for v in ins.group(2).split(",")]
    if len(cols) != len(vals):
        return failures
    for col, val in zip(cols, vals, strict=True):
        if col not in JSONB_COLUMNS:
            continue
        if val.upper() == "NULL":
            continue
        if not re.search(r"CAST\(\s*:\w+\s+AS\s+JSON", val, re.IGNORECASE):
            failures.append(
                f"  {rel_path}:{ln}  col={col}  bind_token={val!r}\n"
                f"    asyncpg needs `CAST(:x AS JSONB)` here; otherwise a "
                f"raw Python list/dict crashes with 'object has no attribute encode'."
            )
    return failures


def _audit_update(rel_path: str, ln: int, sql: str) -> list[str]:
    failures: list[str] = []
    set_match = re.search(
        r"\bSET\s+(.+?)(?:\bWHERE\b|\bRETURNING\b|$)",
        sql, re.IGNORECASE | re.DOTALL,
    )
    if not set_match:
        return failures
    set_clause = set_match.group(1)
    for assn in re.finditer(r"(\w+)\s*=\s*([^,]+?)(?:,|$)", set_clause, re.DOTALL):
        col, val = assn.group(1), assn.group(2).strip()
        if col not in JSONB_COLUMNS:
            continue
        # Skip non-bind expressions: NOW(), CURRENT_USER, sub-selects,
        # COALESCE(EXCLUDED.col, …) — we only care about bind references.
        if not val.startswith((":", "CAST(")):
            continue
        if val.upper() == "NULL":
            continue
        if not re.search(r"CAST\(\s*:\w+\s+AS\s+JSON", val, re.IGNORECASE):
            failures.append(
                f"  {rel_path}:{ln}  col={col}  bind_token={val!r}\n"
                f"    asyncpg needs `col = CAST(:x AS JSONB)` in SET clause."
            )
    return failures


@pytest.mark.parametrize("rel_path", ASYNC_PATH_FILES)
def test_async_jsonb_binds_use_cast_as_jsonb(rel_path: str) -> None:
    """Every JSONB column bound via :placeholder in an INSERT/UPDATE
    must use `CAST(:placeholder AS JSONB)`."""
    f = _backend_root() / rel_path
    if not f.exists():
        pytest.skip(f"{rel_path} not present in this checkout")
    src = f.read_text()
    failures: list[str] = []
    for ln, sql in _find_sql_blocks(src):
        body = _strip_on_conflict(sql)
        if "INSERT" in body.upper():
            failures.extend(_audit_insert(rel_path, ln, body))
        if "UPDATE" in body.upper() and "INSERT" not in body.upper():
            # Pure UPDATE — INSERT…ON CONFLICT DO UPDATE is handled by the
            # INSERT branch above, with ON CONFLICT stripped first.
            failures.extend(_audit_update(rel_path, ln, body))
    if failures:
        msg = (
            "JSONB columns bound via :x must use CAST(:x AS JSONB) so "
            "asyncpg can pass a json.dumps'd string. Raw Python list/dict "
            "binds crash mid-execute. Add the CAST and json.dumps the "
            "value at the call site.\n"
            + "\n".join(failures)
        )
        pytest.fail(msg)
