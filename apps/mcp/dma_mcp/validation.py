"""Validation pass 1 (stage 2.4) — structural and editorial.

Format sweeps against the contract registry: required sections and
fields, types, invented fields, the universal envelope, empty-state
ladders, and id-pattern discipline. Every reason names the gate, the
JSON path and the concrete conflict — a verdict an agent cannot act on
produces another failed submission.

Pass 2 (evidence resolution, grain locks, band words, V4) runs
separately: checking extractions against database rows is different
work from format sweeps, and the split keeps both legible.
"""
from __future__ import annotations

import json
from pathlib import Path

from .contracts import ENVELOPE, PAGES, sections
from .dates import ACCEPTED as DATE_SHAPES, resolve as resolve_date
from .identifiers import EID_TOKEN_RE, agent_id_class

_AGENT_ID_KEYS = ("ic_id", "f_id", "fa_id", "ts_id", "wn_id", "rec_id")

_TYPE_CHECK = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "list": lambda v: isinstance(v, list),
    "object": lambda v: isinstance(v, dict),
}


def _reason(gate, section, path, message):
    return {"gate_id": gate, "section": section, "path": path,
            "message": message, "severity": "block"}


def _valid_empty_state(es) -> bool:
    return (isinstance(es, dict) and bool(es.get("reason"))
            and isinstance(es.get("sources_searched"), list)
            and len(es["sources_searched"]) > 0)


def validate_pass1(page: str, payload: dict) -> list:
    if page not in PAGES:
        return [_reason("CG-01", None, page, f"unknown page {page!r}; pages are {list(PAGES)}")]
    if not isinstance(payload, dict):
        return [_reason("CG-03", None, page, "payload must be an object of sections")]

    reasons = []
    contract = sections(page)

    for name in payload:
        if name not in contract:
            reasons.append(_reason(
                "CG-04", name, name,
                f"section {name!r} is not in the {page} contract — payload "
                "shapes are law; call get_page_contract and re-shape"))

    for name, sec in contract.items():
        body = payload.get(name)
        if body is None:
            if sec.get("required", True):
                reasons.append(_reason(
                    "CG-01", name, name,
                    f"required section {name!r} missing — promotion requires "
                    "a passing submission on every required section"))
            continue
        if not isinstance(body, dict):
            reasons.append(_reason("CG-03", name, name,
                                   f"section {name!r} must be an object"))
            continue

        fields = sec["fields"]
        empty = body.get("empty_state")
        empty_declared = empty is not None
        if empty_declared and not _valid_empty_state(empty):
            reasons.append(_reason(
                "CG-06", name, f"{name}.empty_state",
                "an explicit empty state must name its reason and the "
                "sources_searched — an absence with no ladder is rejected"))

        for fname in body:
            if fname not in fields:
                reasons.append(_reason(
                    "CG-04", name, f"{name}.{fname}",
                    f"field {fname!r} is not in the {page}.{name} contract"))

        for fname, spec in fields.items():
            val = body.get(fname)
            if val is None:
                if spec["required"] and fname in ENVELOPE:
                    reasons.append(_reason(
                        "CG-05", name, f"{name}.{fname}",
                        f"envelope field {fname!r} is required on every "
                        "section, empty states included"))
                elif spec["required"] and not empty_declared:
                    reasons.append(_reason(
                        "CG-02", name, f"{name}.{fname}",
                        f"required field {fname!r} missing and no explicit "
                        "empty state declared"))
                continue
            check = _TYPE_CHECK.get(spec["type"])
            if check and not check(val):
                reasons.append(_reason(
                    "CG-03", name, f"{name}.{fname}",
                    f"{fname!r} must be {spec['type']}, got "
                    f"{type(val).__name__}"))
                continue
            if spec["type"] == "list" and spec.get("item_type") in ("object", "string"):
                want = dict if spec["item_type"] == "object" else str
                for i, item in enumerate(val):
                    if not isinstance(item, want):
                        reasons.append(_reason(
                            "CG-03", name, f"{name}.{fname}[{i}]",
                            f"items of {fname!r} must be "
                            f"{spec['item_type']}s (the item schema is in "
                            "the field's doc text)"))
                        break

        # id-pattern discipline
        for i, e in enumerate(body.get("e_ids") or []):
            if isinstance(e, str) and not EID_TOKEN_RE.fullmatch(e.split(":")[0]):
                reasons.append(_reason(
                    "ET-03", name, f"{name}.e_ids[{i}]",
                    f"{e!r} is not an evidence id the recogniser accepts"))
        reasons.extend(_check_agent_ids(name, body))
        reasons.extend(_check_enum_fields(page, name, body))
        reasons.extend(_check_date_fields(page, name, body))

    return reasons


# Payload fields whose promoted column is a Postgres enum. Generated from
# the live schema and the writer spec (scripts/gen_enum_fields.py), because
# a value the enum rejects is not a JSON-type error — it type-checks as a
# string and then aborts the promote transaction, which is the one place a
# failure must never surface. The first production promote of this
# connector died exactly there: prose written into an EVIDENCE│HYBRID│
# INFERRED chip.
_ENUM_FIELDS = None


def _enum_fields() -> dict:
    global _ENUM_FIELDS
    if _ENUM_FIELDS is None:
        try:
            _ENUM_FIELDS = json.loads(
                Path(__file__).with_name("enum_fields.json").read_text())["enum_fields"]
        except Exception:
            _ENUM_FIELDS = {}
    return _ENUM_FIELDS


def _at_path(body, path):
    """Yield (json_path, value) for a spec path, following `[*]` lists."""
    head, _, rest = path.partition("[*].")
    if not rest:
        if isinstance(body, dict) and head in body:
            yield head, body[head]
        return
    items = body.get(head) if isinstance(body, dict) else None
    if isinstance(items, list):
        for i, item in enumerate(items):
            if isinstance(item, dict) and rest in item:
                yield f"{head}[{i}].{rest}", item[rest]


def _check_date_fields(page: str, section: str, body) -> list:
    """A field promoted into a DATE column must resolve to one. Month and
    quarter precision are legitimate (the prompts ask for them) and resolve;
    anything else is rejected here rather than aborting the promote."""
    out = []
    spec = None
    try:
        spec = json.loads(
            Path(__file__).with_name("enum_fields.json").read_text()).get("date_fields", {})
    except Exception:
        return out
    for path in spec.get(f"{page}.{section}", ()):
        for jpath, value in _at_path(body, path):
            if resolve_date(value) is False:
                out.append(_reason(
                    "CG-09", section, f"{section}.{jpath}",
                    f"{str(value)[:40]!r} does not resolve to a date — this field is "
                    f"promoted into a DATE column and accepts {DATE_SHAPES}"))
    return out


def _check_enum_fields(page: str, section: str, body) -> list:
    out = []
    for path, spec in _enum_fields().get(f"{page}.{section}", {}).items():
        for jpath, value in _at_path(body, path):
            if value is None or value in spec["values"]:
                continue
            shown = value if isinstance(value, str) and len(value) <= 60 else f"{str(value)[:57]}…"
            out.append(_reason(
                "CG-09", section, f"{section}.{jpath}",
                f"{shown!r} is not a value of {spec['enum']} — this field is promoted "
                f"into an enum column and takes one of {' │ '.join(spec['values'])}"))
    return out


def _check_agent_ids(section, node, path=None) -> list:
    """Agent-created ids (five classes + authored rec_id) must match
    their patterns wherever they appear in the section tree."""
    out = []
    path = path or section
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{path}.{k}"
            if k in _AGENT_ID_KEYS and isinstance(v, str):
                if agent_id_class(v) != k:
                    out.append(_reason(
                        "ET-03", section, p,
                        f"{v!r} does not match the {k} pattern — the agent "
                        "creates exactly five id classes plus authored rec_id"))
            else:
                out.extend(_check_agent_ids(section, v, p))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            out.extend(_check_agent_ids(section, item, f"{path}[{i}]"))
    return out
