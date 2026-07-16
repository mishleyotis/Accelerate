"""Generic section miner — the fallback rung of the pattern registry.

Part 12.6: "for any MATERIAL artifact with no matched parser, extract
text (docx paragraphs / csv rows / json flatten / md) into
client_knowledge_sections artifact_kind 'generic' with
record_pattern_gap."

A NEW report variant that matches no registered fingerprint still flows
into the per-client knowledge array: its text is sectioned here,
persisted with ``derived_from: generic_miner`` provenance, and a
``PATTERN_GAP`` entry is recorded so the registry learns the shape.

Caps: ``MAX_SECTIONS_PER_ARTIFACT`` sections per file (default 200 per
the plan) and a byte ceiling per file so a runaway artifact can't flood
the table or stall a parse.
"""
from __future__ import annotations

import json
from pathlib import Path

ARTIFACT_KIND = "generic"

MAX_SECTIONS_PER_ARTIFACT = 200
MAX_TEXT_BYTES = 2 * 1024 * 1024      # skip text-likes above 2 MB
MAX_DOCX_BYTES = 8 * 1024 * 1024      # skip DOCX above 8 MB
MIN_BODY_CHARS = 24                    # drop trivial fragments
MAX_BODY_CHARS = 4000                  # clip runaway cells/paragraphs


def _section(rel: str, heading: str | None, body: str, provenance: dict) -> dict:
    return {
        "artifact_kind": ARTIFACT_KIND,
        "source_path": rel,
        "heading": (heading or None) and str(heading)[:250],
        "body": body[:MAX_BODY_CHARS],
        "page": None,
        "provenance": {"derived_from": "generic_miner", **provenance},
    }


def _flatten_json(obj: object, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten a JSON value into (dotted_key, scalar-ish text) pairs."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            out.extend(_flatten_json(v, key))
    elif isinstance(obj, list):
        # Lists of scalars → one joined entry; lists of dicts → recurse
        # with index keys (bounded).
        if all(isinstance(x, str | int | float | bool) or x is None for x in obj):
            joined = "; ".join(str(x) for x in obj if x is not None)
            if joined:
                out.append((prefix or "items", joined))
        else:
            for i, x in enumerate(obj[:50]):
                out.extend(_flatten_json(x, f"{prefix}[{i}]"))
    elif obj is not None:
        out.append((prefix or "value", str(obj)))
    return out


def mine_generic(
    path: Path,
    rel_path: str | None = None,
    cap: int = MAX_SECTIONS_PER_ARTIFACT,
) -> list[dict]:
    """Extract capped generic sections from a csv/json/md/txt/docx file.

    Never raises for content-level problems — a corrupt file returns []
    (the caller records the pattern gap / warning either way).
    """
    rel = rel_path or path.name
    suffix = path.suffix.lower()
    try:
        size = path.stat().st_size
    except OSError:
        return []
    try:
        if suffix == ".docx":
            if size > MAX_DOCX_BYTES:
                return []
            return _mine_docx(path, rel, cap)
        if size > MAX_TEXT_BYTES:
            return []
        if suffix == ".json":
            return _mine_json(path, rel, cap)
        if suffix in (".csv", ".tsv"):
            return _mine_csv(path, rel, cap)
        if suffix in (".md", ".txt"):
            return _mine_text(path, rel, cap)
    except Exception:
        return []
    return []


def _mine_json(path: Path, rel: str, cap: int) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    pairs = _flatten_json(data)
    # Group flat pairs into one section per top-level key so retrieval
    # gets coherent chunks instead of one row per leaf scalar.
    groups: dict[str, list[str]] = {}
    for key, val in pairs:
        top = key.split(".", 1)[0].split("[", 1)[0]
        groups.setdefault(top, []).append(f"{key}: {val}")
    sections: list[dict] = []
    for top, lines in groups.items():
        body = "\n".join(lines)
        if len(body) < MIN_BODY_CHARS:
            continue
        sections.append(_section(rel, top, body, {"kind": "json_flatten"}))
        if len(sections) >= cap:
            break
    return sections


def _mine_csv(path: Path, rel: str, cap: int) -> list[dict]:
    from app.services.parsers.zennify_opportunities import read_csv_rows
    headers, rows = read_csv_rows(path)
    sections: list[dict] = []
    for i, row in enumerate(rows, start=1):
        body = "\n".join(
            f"{k}: {v}" for k, v in row.items() if v
        )
        if len(body) < MIN_BODY_CHARS:
            continue
        # The first non-empty cell is the best row label available.
        first_val = next((v for v in row.values() if v), "")
        sections.append(_section(
            rel, f"row {i}: {first_val}"[:250], body,
            {"kind": "csv_row", "headers": headers[:24], "row_index": i},
        ))
        if len(sections) >= cap:
            break
    return sections


def _mine_text(path: Path, rel: str, cap: int) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    sections: list[dict] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) >= MIN_BODY_CHARS:
            sections.append(_section(rel, heading, body, {"kind": "md_section"}))
        buf.clear()

    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            flush()
            heading = line.lstrip("# ").strip()
            continue
        buf.append(line)
        if len(sections) >= cap:
            break
    flush()
    return sections[:cap]


def _mine_docx(path: Path, rel: str, cap: int) -> list[dict]:
    try:
        import docx  # python-docx
    except Exception:
        return []
    document = docx.Document(str(path))
    sections: list[dict] = []
    heading: str | None = None
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if len(body) >= MIN_BODY_CHARS:
            sections.append(_section(rel, heading, body, {"kind": "docx_section"}))
        buf.clear()

    for para in document.paragraphs:
        style = (getattr(para.style, "name", "") or "").lower()
        text = (para.text or "").strip()
        if not text:
            continue
        if style.startswith("heading") or style.startswith("title"):
            flush()
            heading = text
            continue
        buf.append(text)
        if len(sections) >= cap:
            break
    flush()
    return sections[:cap]
