"""Zennify opportunity-map parser (Part 12.6 — first unconsumed artifact).

The analyst-judgment layer's highest-direct-sales-value artifact:
``A#_zennify_opportunities.csv`` / ``A#_Zennify_Opportunity_Map.csv``
ships in a slice of the corpus and was NEVER read before this module —
zero of its rows reached any surface.

Header fingerprints (matched via ``nlp.patterns``, NOT filename — the
A-number prefix drifts per package):

  canonical  Opportunity_ID, Opportunity, Priority, Trigger_Evidence,
             Zennify_Offering, Pillar_Alignment, Entry_Point
  solution   Priority, Opportunity, Solution, Evidence, Signal
  product    Priority, Salesforce_Product, Opportunity_Description,
             Urgency, Integration_Readiness

All variants normalize onto the canonical row shape
``{opportunity_id, opportunity, priority, trigger_evidence,
zennify_offering, pillar_alignment, entry_point}`` and persist as
``client_knowledge_sections`` rows (artifact_kind='zennify_opportunity',
body = composed text, provenance = the normalized row) so downstream
page agents (D1 why-now plays, D2 generated insights, D4 conversation
starters) can retrieve them.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from app.services.nlp import patterns

PARSER_KEY = "zennify_opportunities"

ARTIFACT_KIND = "zennify_opportunity"

_FINGERPRINTS: tuple[dict, ...] = (
    {"headers": [
        "opportunity_id", "opportunity", "priority", "trigger_evidence",
        "zennify_offering", "pillar_alignment", "entry_point",
    ]},
    {"headers": ["priority", "opportunity", "solution", "evidence", "signal"]},
    {"headers": [
        "priority", "salesforce_product", "opportunity_description",
        "urgency", "integration_readiness",
    ]},
    {"filename_regex": r"zennify_opportunit"},
)


def register_fingerprints() -> None:
    """Idempotent nlp.patterns registration for this parser's shapes."""
    already = {
        e["parser_key"] for e in patterns.registered()
    }
    if PARSER_KEY in already:
        return
    for fp in _FINGERPRINTS:
        patterns.register(fp, PARSER_KEY)


def _norm_header(h: str) -> str:
    return re.sub(r"\s+", "_", (h or "").strip().lower())


def read_csv_rows(path: Path) -> tuple[list[str], list[dict]]:
    """Comment-tolerant CSV read → (normalized_headers, row dicts).

    Corpus CSVs may open with ``# run_id: …`` comment lines — skip them
    before handing the stream to DictReader.
    """
    raw = path.read_text(encoding="utf-8", errors="replace")
    lines = [
        ln for ln in raw.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    ]
    if not lines:
        return [], []
    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    headers = [_norm_header(h) for h in (reader.fieldnames or [])]
    rows: list[dict] = []
    for r in reader:
        rows.append({
            _norm_header(k): (v or "").strip()
            for k, v in r.items() if k is not None
        })
    return headers, rows


def _normalize_row(row: dict, ordinal: int) -> dict:
    """Any observed header variant → the canonical opportunity row."""
    opportunity = (
        row.get("opportunity")
        or row.get("opportunity_description")
        or row.get("opportunity_name")
        or ""
    )
    offering = (
        row.get("zennify_offering")
        or row.get("solution")
        or row.get("salesforce_product")
        or row.get("zennify_solution")
        or ""
    )
    trigger = (
        row.get("trigger_evidence")
        or row.get("evidence")
        or row.get("trigger")
        or ""
    )
    priority = (
        row.get("priority") or row.get("urgency") or row.get("rank") or ""
    )
    entry_point = (
        row.get("entry_point")
        or row.get("signal")
        or row.get("integration_readiness")
        or row.get("entry")
        or ""
    )
    return {
        "opportunity_id": row.get("opportunity_id")
        or row.get("opp_id")
        or f"OPP-{ordinal:03d}",
        "opportunity": opportunity,
        "priority": priority,
        "trigger_evidence": trigger,
        "zennify_offering": offering,
        "pillar_alignment": row.get("pillar_alignment")
        or row.get("pillars")
        or row.get("pillar")
        or "",
        "entry_point": entry_point,
    }


def _compose_body(n: dict) -> str:
    parts = [n["opportunity"]]
    if n["zennify_offering"]:
        parts.append(f"Zennify offering: {n['zennify_offering']}")
    if n["priority"]:
        parts.append(f"Priority: {n['priority']}")
    if n["trigger_evidence"]:
        parts.append(f"Trigger evidence: {n['trigger_evidence']}")
    if n["pillar_alignment"]:
        parts.append(f"Pillar alignment: {n['pillar_alignment']}")
    if n["entry_point"]:
        parts.append(f"Entry point: {n['entry_point']}")
    return "\n".join(p for p in parts if p)


def parse_opportunities(path: Path, rel_path: str | None = None) -> list[dict]:
    """One knowledge-section dict per opportunity row.

    Section shape: ``{artifact_kind, source_path, heading, body, page,
    provenance}`` — provenance carries the full normalized row plus the
    parsed E-IDs from trigger_evidence so page agents can cite them.
    """
    _, rows = read_csv_rows(path)
    sections: list[dict] = []
    rel = rel_path or path.name
    for i, row in enumerate(rows, start=1):
        n = _normalize_row(row, i)
        if not (n["opportunity"] or n["zennify_offering"]):
            continue
        e_ids = re.findall(r"\bE-\d{1,4}\b", n["trigger_evidence"] or "")
        pillars = re.findall(
            r"\bP[1-4]C\d+(?:\.\d+)*\b|\bP[1-4]\b", n["pillar_alignment"] or "",
        )
        sections.append({
            "artifact_kind": ARTIFACT_KIND,
            "source_path": rel,
            "heading": f"{n['opportunity_id']}: {n['opportunity']}"[:250]
            if n["opportunity"] else n["opportunity_id"],
            "body": _compose_body(n),
            "page": None,
            "provenance": {
                **n,
                "e_ids": e_ids,
                "pillar_refs": pillars,
                "parser": PARSER_KEY,
                "raw_row": row,
            },
        })
    return sections
