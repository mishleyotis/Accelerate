"""The read side of the promote writers (stage 5).

promote_run decomposes each section payload into typed columns across 34
serving tables; a page endpoint has to put the payload back together. That
inverse is derived from the SAME writer spec the connector writes with —
one description of the mapping, read in both directions, so a column that
moves cannot move in only one of them.

Three reassembly modes, matching the three writer grains:
  run    one row per run; `section:<dotted.path>` columns rebuild the
         section object directly.
  item   one row per item; `item:<key>` columns rebuild each item, and the
         list lands at `item_field`.
  item without item_field
         the H4 map inverse: rows carrying a category_id belong under
         `categories`, rows carrying only a pillar_id under `pillars` —
         the expander that flattened those object maps, run backwards.
`sys:` columns are the promotion's own stamps and `env:` columns are the
universal envelope: both belong in the response envelope, never inside
`data`.

`skip:` columns were never WRITTEN, but one family of them must still be
READ: the GENERATED ALWAYS columns. band, delta, grounded_on, age_months,
age_band, age_status, share_pct and below_threshold are computed by the
database from the promoted values, and they are exactly the figures a
surface has to show — an evidence row without its age band, or a category
without its peer delta, is a surface missing its point. The producer may
send those keys and they are validated at submit, but the DB's value is
the one that serves (invariants 8 and 9: computed, never stored twice,
never recomputed in the app). They come back read-only, under the column
name the schema gives them. Every other `skip:` column stays unread.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ENV_KEYS = ("e_ids", "internal_only", "empty_state")


@lru_cache(maxsize=1)
def _spec() -> dict:
    return json.loads(Path(__file__).with_name("writer_spec.json").read_text())


@lru_cache(maxsize=1)
def readers() -> dict:
    """(page, section) -> reader description."""
    out = {}
    for page in _spec()["specs"]:
        for w in page["writers"]:
            item_cols, section_cols, env_cols, sys_cols = {}, {}, {}, {}
            derived_cols = []
            for c in w["columns"]:
                kind, _, rest = c["source"].partition(":")
                # The spec carries SQL identifier quoting for reserved words
                # ("window"), which the WRITER needs and the reader must not
                # keep: the driver hands back the bare column name, so a
                # quoted key never matches and the field silently vanished.
                col = c["column"].strip('"')
                if kind == "item":
                    item_cols[col] = rest
                elif kind == "section":
                    section_cols[col] = rest
                elif kind == "env":
                    env_cols[col] = rest
                elif kind == "sys":
                    sys_cols[col] = rest
                elif kind == "skip" and "GENERATED ALWAYS" in rest:
                    derived_cols.append(col)
            out[(page["page"], w["section"])] = {
                "table": w["table"], "grain": w["grain"],
                "item_field": w.get("item_field"),
                "item_cols": item_cols, "section_cols": section_cols,
                "env_cols": env_cols, "sys_cols": sys_cols,
                "derived_cols": derived_cols,
            }
    return out


def page_sections(page: str) -> list[str]:
    """Section names for a page, in writer order (order is load-bearing)."""
    return [sec for (p, sec) in readers() if p == page]


def _set_path(target: dict, path: str, value) -> None:
    """Set a dotted path, creating dicts — and lists where a segment is an
    index (`platforms.0.story_md`)."""
    segs = path.split(".")
    cur = target
    for i, seg in enumerate(segs[:-1]):
        nxt = segs[i + 1]
        if seg.isdigit():
            raise ValueError(f"unsupported leading index in {path!r}")
        if nxt.isdigit():
            lst = cur.setdefault(seg, [])
            idx = int(nxt)
            while len(lst) <= idx:
                lst.append({})
            if i + 2 == len(segs):          # the index IS the last segment
                lst[idx] = None
                return
            cur = lst[idx]
            segs = segs[i + 2:]
            return _set_path(cur, ".".join(segs), value) if segs else None
        cur = cur.setdefault(seg, {})
    cur[segs[-1]] = value


def _json_maybe(value):
    """asyncpg/pg8000 hand JSONB back as text on some drivers; a dict or
    list passes through untouched. Never guesses at a non-JSON string."""
    if isinstance(value, (str, bytes)) and value[:1] in (b"{", b"[", "{", "["):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value
    return value


def assemble(page: str, section: str, rows: list[dict]) -> dict | None:
    """Rebuild one section's {data, envelope} from its serving rows, or None
    when the section did not promote (no rows: section_not_promoted)."""
    r = readers().get((page, section))
    if r is None:
        raise KeyError(f"unknown section {page}.{section}")
    if not rows:
        return None

    data: dict = {}
    env: dict = {}
    stamps: dict = {}

    def take_env(row: dict) -> None:
        for col, key in r["env_cols"].items():
            if col in row and key not in env:
                env[key] = _json_maybe(row[col])
        for col, key in r["sys_cols"].items():
            if col in row and key not in stamps:
                stamps[key] = row[col]

    def take_derived(row: dict, target: dict) -> None:
        """The database's own computed values, read-only. Absent columns are
        simply absent: a derived value is computed or null, never a default
        that looks like data (invariant 9)."""
        for col in r["derived_cols"]:
            if col in row and row[col] is not None and col not in target:
                target[col] = _json_maybe(row[col])

    if r["grain"] == "run":
        row = rows[0]
        take_env(row)
        for col, path in r["section_cols"].items():
            if col in row:
                _set_path(data, path, _json_maybe(row[col]))
        take_derived(row, data)
    elif r["item_field"]:
        items = []
        for row in rows:
            take_env(row)
            item = {}
            for col, key in r["item_cols"].items():
                if col in row:
                    _set_path(item, key, _json_maybe(row[col]))
            take_derived(row, item)
            items.append(item)
        # item_field can be a dotted path (`ladder.steps`) — the payload nests
        # it, so the reader must too. Assigning the dotted string as a literal
        # key produced a `data["ladder.steps"]` no consumer could ever find.
        _set_path(data, r["item_field"], items)
        # section-level columns repeat on every row; read them once
        for col, path in r["section_cols"].items():
            if col in rows[0]:
                _set_path(data, path, _json_maybe(rows[0][col]))
        # An item-grain section whose e_ids column carries the ITEM's own
        # citations still owes the envelope its section-level list — so it
        # is computed here as the union over the items, never stored
        # (invariant 8). Without this, rebinding e_ids to the item would
        # trade a missing per-card citation for a missing section one.
        #
        # The test is on the COLUMN, not on the payload key. It read
        # `.values()` — the keys the item lands under — so a writer that
        # rebinds the e_ids COLUMN to a differently-named item key was missed
        # exactly where it matters most: insight_cards binds
        # `e_ids <- item:supporting_e_ids`, so the column was consumed by the
        # item, no `env:e_ids` remained, and the guard tested for a key that by
        # construction is not there. Every insights section served with no
        # envelope citations at all.
        ev_col = "e_ids" if "e_ids" in r["item_cols"] else None
        if "e_ids" not in env and ev_col:
            key = r["item_cols"][ev_col]
            union, seen = [], set()
            for item in items:
                for e in item.get(key) or []:
                    if e not in seen:
                        seen.add(e)
                        union.append(e)
            env["e_ids"] = union
    else:
        # H4 map inverse: pillar rows and category rows share one table
        pillars, categories = {}, {}
        for row in rows:
            take_env(row)
            item = {}
            for col, key in r["item_cols"].items():
                if col in row and key not in ("pillar_id", "category_id"):
                    _set_path(item, key, _json_maybe(row[col]))
            take_derived(row, item)
            cat, pil = row.get("category_id"), row.get("pillar_id")
            if cat:
                categories[cat] = item
            elif pil:
                pillars[pil] = item
        if pillars:
            data["pillars"] = pillars
        if categories:
            data["categories"] = categories

    return {"data": data, "env": env, "stamps": stamps}
