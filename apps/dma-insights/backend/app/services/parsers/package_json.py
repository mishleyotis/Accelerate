"""JSON leaf parsers for the canonical DMA package layout.

Pure transforms — directory walking lives in `dma_package.py`. Each
parser returns the typed envelope object directly (or `None` when the
file is missing — callers degrade gracefully).
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from app.schemas.package import (
    Firmographics,
    LeadershipPerson,
    PackageManifest,
    PeerScore,
    QaVerdict,
    RecommendationRow,
    RunManifest,
)


def _date_or_none(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def parse_top_manifest(blob: str) -> PackageManifest:
    """Parses the top-level `MANIFEST.json`."""
    d = json.loads(blob)
    return PackageManifest(
        engagement=d.get("engagement", ""),
        run_id=d.get("run_id", ""),
        package_date=_date_or_none(d.get("package_date")),
        framework=d.get("framework"),
        overall_score=d.get("overall_score"),
        verdict=d.get("verdict"),
    )


def parse_run_manifest(blob: str) -> RunManifest:
    """Parses `07_governance/run_manifest.json` (ALMA / Odlum) or
    `08_appendices/run_manifest.json` (WSFS / Calprivate). Schema
    `run_manifest_v2`.

    Real-sample shape variants observed in the 4 uploaded zips:
      Alma          → institution_name + run_id + subvertical_*
      WSFS          → entity + assessment_id (l1_run_id)
      Odlum         → institution + run_id   (NOT institution_name)
      Calprivate    → entity_name + entity_legal_name + run_id
                      (also stashes entity_name; missing institution_*)
      Nicola        → NO run_manifest.json — synthesized upstream
    """
    d = json.loads(blob)
    # WSFS uses `assessment_id` / `l1_run_id`; ALMA uses `run_id`.
    rid = d.get("run_id") or d.get("l1_run_id") or d.get("assessment_id") or ""
    # Institution name aliases — observed in real samples:
    #   institution_name      Alma          (canonical)
    #   entity                WSFS
    #   institution           Odlum
    #   entity_name           Calprivate
    #   entity_legal_name     Calprivate fallback
    name = (
        d.get("institution_name")
        or d.get("entity")
        or d.get("institution")
        or d.get("entity_name")
        or d.get("entity_legal_name")
        or ""
    )
    # ALMA: `sub_vertical` like "SV1 Regional Banks"; WSFS: `subvertical` + `_code`.
    sv_name = d.get("subvertical_name") or d.get("subvertical") or d.get("sub_vertical")
    return RunManifest(
        run_id=rid,
        research_run_id=d.get("research_run_id") or d.get("l0_run_id"),
        institution_name=name,
        evidence_mode=d.get("evidence_mode"),
        rubric_version=str(d.get("rubric_version")) if d.get("rubric_version") else None,
        skill_version=d.get("skill_version") or d.get("governance_skill_version"),
        subvertical_code=d.get("subvertical_code"),
        subvertical_name=sv_name,
        pillar_weights=d.get("pillar_weights"),
        pillar_scores=d.get("pillar_scores"),
        overall_score=d.get("overall_score") or d.get("pillar_weighted_average"),
        assessment_date=_date_or_none(d.get("assessment_date")),
    )


def parse_peer_score(blob: str) -> PeerScore:
    """Parses `06_peers/peer_scores_*.json`."""
    d = json.loads(blob)
    return PeerScore(
        peer_id=d.get("peer_id") or d.get("ticker") or "",
        peer_name=d.get("peer_name") or d.get("name") or "",
        ticker=d.get("ticker"),
        assets=d.get("assets"),
        rationale=d.get("rationale"),
        scores={k: float(v) for k, v in (d.get("scores") or {}).items()},
    )


def parse_qa_verdict(blob: str) -> QaVerdict:
    """Parses `07_governance/qa_verdict.json`.

    Two variants observed:
      - ALMA: keys `verdict` / `recommendation` / `verdict_basis`
      - WSFS: keys `overall_verdict` / `recommended_action` / `verdict_note`
    Both also expose either `issue_count_genuine_only` or
    `pass1_results.{critical,high,…}` for severity breakdowns.
    """
    d = json.loads(blob)
    verdict = (
        d.get("verdict") or d.get("overall_verdict") or "UNKNOWN"
    )
    rec = d.get("recommendation") or d.get("recommended_action")
    basis = d.get("verdict_basis") or d.get("verdict_note")
    breakdown = d.get("issue_count_genuine_only")
    if not breakdown:
        p1 = d.get("pass1_results") or {}
        if p1:
            breakdown = {
                "CRITICAL": int(p1.get("organic_critical") or p1.get("critical") or 0),
                "HIGH": int(p1.get("organic_high") or p1.get("high") or 0),
                "MEDIUM": int(p1.get("medium") or 0),
                "LOW": int(p1.get("low") or 0),
            }
    return QaVerdict(
        verdict=str(verdict),
        recommendation=rec,
        verdict_basis=basis,
        issue_count_genuine_only=breakdown,
        governance_skill_version=str(d.get("governance_skill_version") or "") or None,
    )


def parse_recommendations(blob: str) -> list[RecommendationRow]:
    """Parses `08_appendices/recommendations_detail.json`."""
    d = json.loads(blob)
    out: list[RecommendationRow] = []
    for rec in d.get("recommendations", []):
        # `id` may be `REC-01` or `R7`-style; normalize to `REC-{n}`.
        rid = str(rec.get("id") or "").strip()
        if rid and not rid.upper().startswith("REC-"):
            m = "".join(ch for ch in rid if ch.isdigit())
            rid = f"REC-{int(m):02d}" if m else rid
        out.append(RecommendationRow(
            id=rid,
            priority=rec.get("priority"),
            title=rec.get("title") or "(untitled)",
            ownership=rec.get("ownership"),
            technographic_status=rec.get("technographic_status"),
            root_cause=rec.get("root_cause"),
            solution=rec.get("solution"),
            peer_benchmark=rec.get("peer_benchmark"),
            cross_pillar_unlock=rec.get("cross_pillar_unlock"),
            counter_arguments=rec.get("counter_arguments", []),
            expected_outcomes=rec.get("expected_outcomes", []),
            strategic_objectives=rec.get("strategic_objectives", []),
        ))
    return out


def parse_firmographics(blob: str) -> Firmographics:
    """Parses `02_research_workbook/research_handoff.json` → entity block.

    The handoff JSON has a top-level `entity` dict plus a `leadership_map`
    list under `phase_3_outputs` (WSFS shape) or no leadership section
    (ALMA — leadership lives in client-profile DOCX). We extract what's
    present and let downstream parsers fill the rest from Explorium /
    Clay enrichment.
    """
    d = json.loads(blob)
    entity = d.get("entity") or {}
    # research_handoff_v2 (Haventree etc.) nests the entity firmographics
    # under `parameter_lock.institution` instead of a top-level `entity`.
    if not entity:
        inst = (d.get("parameter_lock") or {}).get("institution")
        if isinstance(inst, dict):
            entity = inst
    leadership_raw = (
        (d.get("phase_3_outputs") or {}).get("leadership_map")
        or d.get("leadership_map")
        or entity.get("leadership")
        or []
    )
    leadership: list[LeadershipPerson] = []
    for p in leadership_raw:
        if not isinstance(p, dict):
            continue
        leadership.append(LeadershipPerson(
            name=p.get("name") or p.get("full_name") or "",
            title=p.get("title") or p.get("role"),
            tenure=p.get("tenure") or p.get("years_at_firm"),
            background=p.get("background") or p.get("notes"),
        ))
    # `total_assets` may be reported as a string field name variant.
    total_assets = (
        entity.get("total_assets")
        or entity.get("total_assets_q1_2026")
        or entity.get("total_assets_2025")
    )
    employees = entity.get("employees_approx") or entity.get("employees")
    return Firmographics(
        legal_name=entity.get("legal_name") or entity.get("name"),
        ticker=entity.get("ticker"),
        hq=entity.get("hq") or entity.get("headquarters"),
        founded=entity.get("founded"),
        total_assets=str(total_assets) if total_assets is not None else None,
        employees_approx=str(employees) if employees is not None else None,
        primary_regulator=entity.get("primary_regulator") or d.get("primary_regulator"),
        cra_rating=entity.get("cra_rating"),
        leadership=[p for p in leadership if p.name],
    )
