#!/usr/bin/env python3
"""Every serving column's SQL type, read off the migrations that create it.

WHY THIS EXISTS. MEM-0136 and MEM-0194, both BLOCKER, both the same shape: a
producer put a prose locator ("¶4 of the release (Sharps quote)") into
`heatmap_focus_areas.source_page`, which is an INTEGER column. Every submit
gate passed it. It failed at `promote_run` as a raw Postgres error —

    SQLSTATE 22P02  invalid input syntax for type integer: "¶4 of the ..."

— which names a parameter index and nothing a producer can act on. MEM-0194
then measured the whole surface: 135 values type-checked across 33 tables,
6 mismatches, all numeric columns receiving strings.

The data to catch it already ships. `writer_spec.json` maps every section
field to its column; the migrations give that column's type. This joins them
into one file so the check is a dictionary lookup at submit rather than a DDL
parse at runtime.

The same column name can be different types in different tables —
`source_page` is INTEGER in `heatmap_focus_areas` and TEXT in the answer
index — so the index is keyed by (table, column) and never by column alone.

    python3 scripts/gen_column_types.py [--check]

`--check` regenerates and exits 1 if the committed file is stale, which is
what CI runs: a migration that changes a type must not leave the gate
enforcing the old one.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations" / "versions"
OUT = ROOT / "apps" / "mcp" / "dma_mcp" / "column_types.json"

#: `CREATE TABLE [IF NOT EXISTS] name (` … `)` — the body is scanned line by
#: line rather than parsed, because these are hand-written DDL strings and a
#: real parser would be a bigger dependency than the problem.
_CREATE = re.compile(
    r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s*\(",
    re.I)
_ALTER_ADD = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s+"
    r"ADD\s+COLUMN\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_]\w*)\s+"
    r"([A-Za-z][\w ]*(?:\([^)]*\))?(?:\s*\[\])?)", re.I)
_ALTER_TYPE = re.compile(
    r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+)?([A-Za-z_][\w.]*)\s+"
    r"ALTER\s+(?:COLUMN\s+)?([A-Za-z_]\w*)\s+(?:SET\s+DATA\s+)?TYPE\s+"
    r"([A-Za-z][\w ]*(?:\([^)]*\))?(?:\s*\[\])?)", re.I)

#: A line inside a CREATE TABLE body that declares a column. Constraint lines
#: (PRIMARY KEY, UNIQUE, CHECK, FOREIGN KEY, CONSTRAINT, EXCLUDE) are not
#: columns and are skipped by name.
_COL = re.compile(r"^\s*([A-Za-z_]\w*)\s+"
                  r"([A-Za-z][\w ]*(?:\([^)]*\))?(?:\s*\[\])?)")
_NOT_A_COLUMN = re.compile(
    r"^\s*(PRIMARY|UNIQUE|CHECK|FOREIGN|CONSTRAINT|EXCLUDE|LIKE|"
    r"PARTITION|GENERATED)\b", re.I)

#: The serving tier does not write `CREATE TABLE name (`. It declares a dict
#: of `"table_name": (f"""<column body>""", "grain")` and builds the DDL by
#: iterating it — see migrations/versions/0008_serving_tier.py. Missing this
#: form is not a partial index, it is an empty one for exactly the tables the
#: gate cares about, so it is matched explicitly.
_DICT_TABLE = re.compile(
    r'["\']([a-z_][a-z0-9_]*)["\']\s*:\s*\(\s*[rbf]{0,2}"""(.*?)"""',
    re.S)

#: Bodies are templated with {ENVELOPE}-style placeholders that expand to more
#: columns. The placeholder itself is not a column and must not be read as one.
_PLACEHOLDER = re.compile(r"^\s*\{[A-Za-z_]\w*\}\s*,?\s*$")


def _norm(sqltype: str) -> str:
    """The type, without the modifiers that do not change what fits in it."""
    t = re.sub(r"\s+", " ", sqltype).strip().upper()
    for tail in (" NOT NULL", " NULL", " PRIMARY KEY", " UNIQUE", " DEFAULT",
                 " GENERATED", " REFERENCES", " COLLATE", " CHECK"):
        i = t.find(tail)
        if i > 0:
            t = t[:i]
    return t.strip().rstrip(",").strip()


def _bodies(sql: str):
    """(table, body) for every table declared in this migration, in both
    forms the repo uses: literal `CREATE TABLE name (…)` and the serving
    tier's `"name": (f\"\"\"…\"\"\", grain)` dict."""
    for m in _CREATE.finditer(sql):
        depth, i = 1, m.end()
        while i < len(sql) and depth:
            if sql[i] == "(":
                depth += 1
            elif sql[i] == ")":
                depth -= 1
            i += 1
        yield m.group(1).split(".")[-1], sql[m.end():i - 1]
    for m in _DICT_TABLE.finditer(sql):
        yield m.group(1), m.group(2)


def _envelopes(sql: str) -> dict:
    """`NAME = f\"\"\"…\"\"\"` bodies that table declarations splice in by
    placeholder. ENVELOPE carries run_id, promoted_at and the rest onto every
    serving table, so leaving it unexpanded loses a quarter of the columns."""
    out = {}
    for m in re.finditer(r'^([A-Z][A-Z0-9_]*)\s*=\s*[rbf]{0,2}"""(.*?)"""',
                         sql, re.S | re.M):
        out[m.group(1)] = m.group(2)
    return out


def build() -> dict:
    types: dict[str, dict[str, str]] = {}
    for path in sorted(MIGRATIONS.glob("*.py")):
        sql = path.read_text(errors="ignore")

        env = _envelopes(sql)
        for table, body in _bodies(sql):
            cols = types.setdefault(table, {})
            # expand {ENVELOPE}-style placeholders before reading columns
            for name, text in env.items():
                body = body.replace("{" + name + "}", text)
            depth = 0
            for raw in body.splitlines():
                line = raw.split("--")[0]
                if _PLACEHOLDER.match(line):
                    continue
                if depth == 0 and not _NOT_A_COLUMN.match(line):
                    m = _COL.match(line)
                    if m:
                        cols[m.group(1)] = _norm(m.group(2))
                depth += line.count("(") - line.count(")")

        # Later migrations win: a column added or retyped after CREATE is the
        # shape the database actually has.
        for m in _ALTER_ADD.finditer(sql):
            types.setdefault(m.group(1).split(".")[-1], {})[m.group(2)] = \
                _norm(m.group(3))
        for m in _ALTER_TYPE.finditer(sql):
            types.setdefault(m.group(1).split(".")[-1], {})[m.group(2)] = \
                _norm(m.group(3))
    return {t: dict(sorted(c.items())) for t, c in sorted(types.items()) if c}


def main() -> int:
    built = build()
    if "--check" in sys.argv:
        if not OUT.exists():
            print(f"{OUT} is missing — run scripts/gen_column_types.py",
                  file=sys.stderr)
            return 1
        have = json.loads(OUT.read_text())
        if have != built:
            only_new = {t: {c: v for c, v in cols.items()
                            if have.get(t, {}).get(c) != v}
                        for t, cols in built.items()}
            only_new = {t: c for t, c in only_new.items() if c}
            print("column_types.json is STALE — a migration changed a column "
                  "type and the gate is still enforcing the old one. "
                  "Regenerate with scripts/gen_column_types.py. Differences: "
                  + json.dumps(only_new)[:1200], file=sys.stderr)
            return 1
        print(f"column_types.json is current "
              f"({len(built)} tables, "
              f"{sum(len(c) for c in built.values())} columns)")
        return 0
    OUT.write_text(json.dumps(built, indent=1, sort_keys=True) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(built)} tables, "
          f"{sum(len(c) for c in built.values())} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
