"""Org-capability proxy parser (Part 12.6).

Sources (previously unconsumed):

  - ``A#_Org_Capability.csv`` / ``A#_org_capability.csv`` /
    ``A#_Org_Capability_Assessment.csv`` — workforce/tech-leadership
    proxy metrics (Metric / Value / Source / Capability_Signal …, or
    Dimension / Metric / Value / … variants).
  - ``org_capability_proxies.json`` — structured workforce composition
    + tech-leadership roster proxies.

Output: knowledge sections (artifact_kind='org_capability') feeding
ceiling modifiers + leadership context. Signal polarity is classified
via ``nlp.polarity.signal`` and numeric metrics extracted via
``nlp.quantities.extract_metrics`` into the provenance dict.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.nlp import patterns
from app.services.nlp.polarity import signal as polarity_signal
from app.services.nlp.quantities import extract_metrics
from app.services.parsers.zennify_opportunities import read_csv_rows

PARSER_KEY = "org_capability"

ARTIFACT_KIND = "org_capability"

_FINGERPRINTS: tuple[dict, ...] = (
    {"headers": ["metric", "value", "source", "capability_signal"]},
    {"headers": ["metric", "value", "interpretation", "source", "recency"]},
    {"headers": [
        "dimension", "metric", "value", "source", "capability_impact",
    ]},
    {"filename_regex": r"org_capabilit"},
)


def register_fingerprints() -> None:
    already = {e["parser_key"] for e in patterns.registered()}
    if PARSER_KEY in already:
        return
    for fp in _FINGERPRINTS:
        patterns.register(fp, PARSER_KEY)


def _polarity_of(*texts: str) -> str | None:
    joined = " ".join(t for t in texts if t).strip()
    if not joined:
        return None
    try:
        return polarity_signal(joined)
    except Exception:
        return None


def parse_org_capability(
    path: Path, rel_path: str | None = None,
) -> list[dict]:
    rel = rel_path or path.name
    if path.suffix.lower() == ".json":
        return _parse_proxies_json(path, rel)
    return _parse_csv(path, rel)


def _parse_csv(path: Path, rel: str) -> list[dict]:
    _, rows = read_csv_rows(path)
    sections: list[dict] = []
    for i, row in enumerate(rows, start=1):
        metric = row.get("metric") or row.get("dimension") or ""
        value = row.get("value", "")
        if not metric and not value:
            continue
        interp = (
            row.get("capability_signal")
            or row.get("interpretation")
            or row.get("capability_impact")
            or ""
        )
        ceiling = (
            row.get("p1c4_ceiling_impact")
            or row.get("ceiling_impact")
            or ""
        )
        body = "\n".join(p for p in (
            f"{metric}: {value}" if metric else value,
            interp,
            f"Ceiling impact: {ceiling}" if ceiling else "",
            f"Source: {row.get('source', '')}" if row.get("source") else "",
        ) if p)
        cap_refs = re.findall(r"\bP[1-4]C\d+(?:\.\d+)*\b", " ".join(
            (interp, ceiling, row.get("capability_impact", "")),
        ))
        quantities = []
        try:
            quantities = list(
                extract_metrics(f"{metric}: {value}") or []
            )[:4]
        except Exception:
            quantities = []
        sections.append({
            "artifact_kind": ARTIFACT_KIND,
            "source_path": rel,
            "heading": (metric or f"Org capability row {i}")[:250],
            "body": body,
            "page": None,
            "provenance": {
                "parser": PARSER_KEY,
                "raw_row": row,
                "polarity": _polarity_of(interp, ceiling),
                "cap_refs": cap_refs,
                "quantities": [dict(q) for q in quantities],
            },
        })
    return sections


def _parse_proxies_json(path: Path, rel: str) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    sections: list[dict] = []
    if not isinstance(data, dict):
        return sections
    for key, block in data.items():
        if key in ("run_id",) or block is None:
            continue
        heading = key.replace("_", " ").strip().title()
        if isinstance(block, dict):
            lines = []
            for k, v in block.items():
                if isinstance(v, str | int | float | bool):
                    lines.append(f"{k.replace('_', ' ')}: {v}")
            body = "\n".join(lines)
        elif isinstance(block, list):
            body = "\n".join(str(x) for x in block if x)
        else:
            body = str(block)
        if not body.strip():
            continue
        sections.append({
            "artifact_kind": ARTIFACT_KIND,
            "source_path": rel,
            "heading": f"Org capability — {heading}"[:250],
            "body": body,
            "page": None,
            "provenance": {
                "parser": PARSER_KEY,
                "block": key,
                "polarity": _polarity_of(body[:400]),
            },
        })
    return sections
