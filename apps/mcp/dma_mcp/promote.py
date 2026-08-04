"""promote_run (stage 2.5) — all six pages, one transaction, all or nothing.

The run row is taken FOR UPDATE (one promote per run at a time); the 34
section writers then run in REGISTRY ORDER — the ordering is load-
bearing, unordered acquisition deadlocks under concurrent promotes of
different runs. Each writer deletes its section's rows for this run and
rewrites them from the live PASSING submission, so re-promotion is
idempotent and fixing one page re-promotes six pages from five retained
staged rows plus one new one. Any writer failure rolls back everything.

Writers are data, not code: writer_spec.json (extracted from the 0008
DDL against the contract registry, adversarially verified) maps every
table column to its payload source. A column the spec cannot source is
NULL; a column the DDL generates is never written.
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import PAGES, SERVING_TABLES

_SPEC_PATH = Path(__file__).with_name("writer_spec.json")
_SPEC = None


def writer_registry() -> list:
    """The ordered writer list. Order = contracts.SERVING_TABLES order,
    which is the registry's canonical page/section order — stable, and
    tested to stay so."""
    global _SPEC
    if _SPEC is None:
        by_key = {}
        for page_spec in json.loads(_SPEC_PATH.read_text())["specs"]:
            for w in page_spec["writers"]:
                by_key[(page_spec["page"], w["section"])] = w
        _SPEC = [((page, section), by_key[(page, section)])
                 for (page, section) in SERVING_TABLES
                 if (page, section) in by_key]
        missing = [k for k in SERVING_TABLES if k not in by_key]
        if missing:
            raise RuntimeError(f"writer_spec.json lacks writers for {missing}")
    return _SPEC


def _value(source, ctx, section, item):
    kind, _, field = source.partition(":")
    if kind == "skip":
        return ...                     # sentinel: column never written
    if kind == "sys":
        return ctx[field]
    if kind == "env" or kind == "section":
        return section.get(field) if isinstance(section, dict) else None
    if kind == "item":
        return item.get(field) if isinstance(item, dict) else None
    raise ValueError(f"unknown source {source!r}")


def promote_run(conn, run_id) -> dict:
    registry = writer_registry()
    cur = conn.cursor()
    try:
        cur.execute("""SELECT entity_id FROM runs WHERE id = %s FOR UPDATE""",
                    (run_id,))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return {"promoted": False, "error": "unknown_run"}
        entity_id = row[0]

        cur.execute(
            """SELECT enum_label(page), enum_label(status), id, payload,
                      producer_version, enum_label(provenance)
                 FROM submissions
                WHERE run_id = %s AND superseded_at IS NULL""", (run_id,))
        live = {r[0]: {"status": r[1], "id": r[2], "payload": r[3],
                       "producer_version": r[4], "provenance": r[5]}
                for r in cur.fetchall()}
        missing = [p for p in PAGES if p not in live]
        unpassed = [p for p, s in live.items() if s["status"] != "PASS"]
        if missing or unpassed:
            conn.rollback()
            return {"promoted": False, "error": "incomplete_run",
                    "missing_pages": sorted(missing),
                    "unpassed_pages": sorted(unpassed),
                    "hint": "promote requires a PASS row for every page"}

        stats = {p: {"sections": 0, "rows_written": 0} for p in PAGES}
        for (page, section), writer in registry:
            sub = live[page]
            ctx = {"run_id": run_id, "entity_id": entity_id,
                   "producer_version": sub["producer_version"],
                   "provenance": sub["provenance"]}
            payload = sub["payload"] or {}
            section_payload = payload.get(section)
            n = _write_section(cur, writer, ctx, section_payload)
            stats[page]["sections"] += 1
            stats[page]["rows_written"] += n

        # one active promoted run per entity: demote the previous one
        cur.execute("""UPDATE runs SET is_active = FALSE, status = 'SUPERSEDED'
                        WHERE entity_id = %s AND is_active AND id <> %s""",
                    (entity_id, run_id))
        cur.execute("""UPDATE runs SET status = 'PROMOTED', is_active = TRUE,
                                       promoted_at = now()
                        WHERE id = %s""", (run_id,))
        cur.execute("""UPDATE submissions SET promoted_at = now()
                        WHERE run_id = %s AND superseded_at IS NULL""",
                    (run_id,))
        conn.commit()
        cur.execute("SELECT promoted_at FROM runs WHERE id = %s", (run_id,))
        return {"promoted": True,
                "promoted_at": cur.fetchone()[0].isoformat(),
                "stats": stats}
    except Exception:
        conn.rollback()
        raise


def _write_section(cur, writer, ctx, section_payload) -> int:
    """Delete-then-rewrite one section's rows from the live submission.
    promoted_at columns take SQL now() so every row of the promotion
    carries one transaction instant."""
    table = writer["table"]
    if writer["grain"] == "none":
        return 0
    cur.execute(f"DELETE FROM {table} WHERE run_id = %s", (ctx["run_id"],))
    if section_payload is None:
        return 0
    if writer["grain"] == "item":
        items = section_payload.get(writer["item_field"]) or []
        rows = [i for i in items if isinstance(i, dict)]
    else:
        rows = [None]

    cols, exprs, per_row_sources = [], [], []
    for c in writer["columns"]:
        if c["source"].startswith("skip:"):
            continue
        cols.append(c["column"])
        if c["source"] == "sys:promoted_at":
            exprs.append("now()")
        else:
            exprs.append("%s")
            per_row_sources.append(c)
    written = 0
    for item in rows:
        values = []
        for c in per_row_sources:
            v = _value(c["source"], ctx, section_payload, item)
            if v is ...:
                v = None
            if c.get("jsonb") and v is not None:
                v = json.dumps(v)
            values.append(v)
        cur.execute(
            f'INSERT INTO {table} ({",".join(cols)}) VALUES ({",".join(exprs)})',
            values)
        written += 1
    return written
