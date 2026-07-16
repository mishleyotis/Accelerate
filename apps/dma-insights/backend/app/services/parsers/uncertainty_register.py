"""Uncertainty register / bands parser (Part 12.6).

Sources (all previously unconsumed):

  - ``A#_Uncertainty_Register.csv``  — assumption-grade uncertainty
    rows (Assumption_ID / Falsification_Search / Outcome / …).
  - ``A#_uncertainty_bands.csv`` / ``A#_Uncertainty_Bands.csv`` —
    per-category band rows (Category / Final_Band / Ceiling_Estimate,
    or Cap_ID / Uncertainty_Band).
  - ``uncertainty_bands.json`` — per-cap dict
    ``{"P1C1": {base, urf, gap, total, note}, …}``.

Two outputs:

  1. knowledge sections (artifact_kind='uncertainty') — "what we could
     NOT verify" rows for the CeilingEstimateCard rationale + RAG
     disclaimers.
  2. a structured band list for the ``runs.uncertainty_bands`` JSONB
     column (migration 045) — written by the backfill when the column
     is empty.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from app.services.nlp import patterns
from app.services.parsers.zennify_opportunities import read_csv_rows

PARSER_KEY = "uncertainty_register"

ARTIFACT_KIND = "uncertainty"

_CAP_ID_RE = re.compile(r"^P[1-4](?:C\d+(?:\.\d+)*)?$")

_FINGERPRINTS: tuple[dict, ...] = (
    {"headers": [
        "assumption_id", "assumption", "basis", "falsification_search",
        "outcome", "confidence_impact",
    ]},
    {"headers": [
        "category", "evidence_strength", "base_uncertainty",
        "final_band", "ceiling_estimate",
    ]},
    {"headers": ["cap_id", "evidence_count", "avg_ers", "uncertainty_band"]},
    {"filename_regex": r"uncertainty_(register|bands)"},
)


def register_fingerprints() -> None:
    already = {e["parser_key"] for e in patterns.registered()}
    if PARSER_KEY in already:
        return
    for fp in _FINGERPRINTS:
        patterns.register(fp, PARSER_KEY)


def _band_value(v: str | float | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def parse_uncertainty(
    path: Path, rel_path: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """→ (knowledge_sections, structured_bands).

    ``structured_bands`` rows: ``{cap_id|category, band, ceiling_estimate,
    base, urf, gap, total, note}`` — only the keys the source carried.
    """
    rel = rel_path or path.name
    if path.suffix.lower() == ".json":
        return _parse_bands_json(path, rel)
    return _parse_register_csv(path, rel)


def _parse_bands_json(path: Path, rel: str) -> tuple[list[dict], list[dict]]:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    sections: list[dict] = []
    bands: list[dict] = []
    if not isinstance(data, dict):
        return sections, bands
    for cap_id, v in data.items():
        if not isinstance(v, dict) or not _CAP_ID_RE.match(str(cap_id)):
            continue
        band = {
            "cap_id": str(cap_id),
            **{
                k: v.get(k)
                for k in ("base", "urf", "gap", "total", "band", "note")
                if v.get(k) is not None
            },
        }
        bands.append(band)
        note = str(v.get("note") or "").strip()
        total = v.get("total")
        body_parts = [f"Uncertainty for {cap_id}"]
        if total is not None:
            body_parts.append(f"total band ±{total}")
        if note:
            body_parts.append(note)
        sections.append({
            "artifact_kind": ARTIFACT_KIND,
            "source_path": rel,
            "heading": f"Uncertainty band — {cap_id}",
            "body": " — ".join(body_parts),
            "page": None,
            "provenance": {"parser": PARSER_KEY, **band},
        })
    return sections, bands


def _parse_register_csv(path: Path, rel: str) -> tuple[list[dict], list[dict]]:
    headers, rows = read_csv_rows(path)
    sections: list[dict] = []
    bands: list[dict] = []
    hset = set(headers)
    for i, row in enumerate(rows, start=1):
        if "assumption" in hset:
            # Assumption-grade register (Global FCU shape).
            assumption = row.get("assumption", "")
            if not assumption:
                continue
            outcome = row.get("outcome", "")
            impact = row.get("confidence_impact", "")
            affected = row.get("affected_capabilities", "")
            caps = re.split(r"[|;,]\s*", affected) if affected else []
            body = "\n".join(p for p in (
                assumption,
                f"Basis: {row.get('basis', '')}" if row.get("basis") else "",
                f"Outcome: {outcome}" if outcome else "",
                f"Confidence impact: {impact}" if impact else "",
                f"Validation: {row.get('validation_method', '')}"
                if row.get("validation_method") else "",
            ) if p)
            sections.append({
                "artifact_kind": ARTIFACT_KIND,
                "source_path": rel,
                "heading": (
                    f"{row.get('assumption_id') or f'ASM-{i:03d}'}: "
                    f"{assumption}"
                )[:250],
                "body": body,
                "page": None,
                "provenance": {
                    "parser": PARSER_KEY,
                    "raw_row": row,
                    "affected_capabilities": [c for c in caps if c],
                },
            })
            continue
        cap = row.get("cap_id") or row.get("category") or ""
        band_v = _band_value(
            row.get("uncertainty_band") or row.get("final_band")
        )
        if not cap and not band_v:
            continue
        band = {
            k: v for k, v in {
                "cap_id": cap or None,
                "band": band_v,
                "ceiling_estimate": _band_value(row.get("ceiling_estimate")),
                "evidence_count": _band_value(row.get("evidence_count")),
                "note": _band_value(row.get("notes") or row.get("note")),
            }.items() if v is not None
        }
        if band:
            bands.append(band)
        body_bits = [f"{cap}: uncertainty {band_v or '(unspecified)'}"]
        if band.get("ceiling_estimate"):
            body_bits.append(f"ceiling estimate {band['ceiling_estimate']}")
        if band.get("note"):
            body_bits.append(str(band["note"]))
        sections.append({
            "artifact_kind": ARTIFACT_KIND,
            "source_path": rel,
            "heading": f"Uncertainty band — {cap or f'row {i}'}",
            "body": " — ".join(body_bits),
            "page": None,
            "provenance": {"parser": PARSER_KEY, "raw_row": row},
        })
    return sections, bands
